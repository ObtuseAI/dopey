"""Integration proof for deterministic CI shards and fail-closed mutation evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from dopey_audit import epistemic_mutation_ledger
from dopey_audit.epistemic_mutation_ledger import (
    EpistemicMutationConflictError,
    EpistemicMutationLedgerCorruptionError,
    EpistemicMutationLedgerWriteError,
    JsonValue,
    append_epistemic_mutation_evaluation,
    audit_epistemic_mutation_ledger,
    verify_epistemic_mutation_ledger,
)
from operator_tools import process_tree
from operator_tools.ci_shards import CiShardPlan, build_ci_shard_plan


LEDGER_PATH = Path("artifacts/dopey/epistemic/research_mutations.jsonl")


def _sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _write_ci_fixture(repository_root: Path, ordered_names: tuple[str, ...]) -> Path:
    tests_directory = repository_root / "tests"
    manifest_directory = repository_root / ".github" / "ci"
    tests_directory.mkdir(parents=True)
    manifest_directory.mkdir(parents=True)
    entries: list[str] = []
    for name in ordered_names:
        relative = f"tests/{name}"
        (repository_root / relative).write_text(
            f"def test_{name.removeprefix('test_').removesuffix('.py')}():\n    assert True\n",
            encoding="utf-8",
        )
        entries.append(relative)
    manifest_path = manifest_directory / "fast_subset.txt"
    manifest_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return manifest_path


def _append_mutation(
    repository_root: Path,
    mutation_id: str,
    baseline_fitness: float,
    candidate_fitness: float,
) -> dict[str, JsonValue]:
    return append_epistemic_mutation_evaluation(
        repository_root,
        LEDGER_PATH,
        mutation_id,
        "2026-07-26T12:00:00+00:00",
        _sha256(f"{mutation_id}-code"),
        _sha256(f"{mutation_id}-data"),
        _sha256(f"{mutation_id}-baseline"),
        _sha256(f"{mutation_id}-candidate"),
        baseline_fitness,
        candidate_fitness,
        {"measurement_source": "deterministic_fixture"},
    )


def _membership_by_file(plan: CiShardPlan) -> dict[str, int]:
    membership: dict[str, int] = {}
    for shard in plan["shards"]:
        shard_number = shard["shard_number"]
        for test_file in shard["test_files"]:
            membership[test_file] = shard_number
    return membership


def test_ci_shard_membership_is_order_independent_complete_and_incremental(
    tmp_path: Path,
) -> None:
    names = tuple(f"test_case_{index:02d}.py" for index in range(12))
    manifest_path = _write_ci_fixture(tmp_path, names)

    first = build_ci_shard_plan(tmp_path, manifest_path, 4)
    manifest_path.write_text(
        "\n".join(f"tests/{name}" for name in reversed(names)) + "\n",
        encoding="utf-8",
    )
    reordered = build_ci_shard_plan(tmp_path, manifest_path, 4)

    assert reordered == first
    assigned = [
        test_file for shard in first["shards"] for test_file in shard["test_files"]
    ]
    assert sorted(assigned) == sorted(f"tests/{name}" for name in names)
    assert len(assigned) == len(set(assigned))
    assert all(shard["test_files"] for shard in first["shards"])

    prior_membership = _membership_by_file(first)
    added_name = "test_incremental_addition.py"
    (tmp_path / "tests" / added_name).write_text(
        "def test_incremental_addition():\n    assert True\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + f"tests/{added_name}\n",
        encoding="utf-8",
    )
    expanded = build_ci_shard_plan(tmp_path, manifest_path, 4)
    expanded_membership = _membership_by_file(expanded)

    assert {
        test_file: expanded_membership[test_file] for test_file in prior_membership
    } == prior_membership


def test_ci_manifest_rejects_duplicate_and_uncontained_paths(tmp_path: Path) -> None:
    manifest_path = _write_ci_fixture(tmp_path, ("test_alpha.py",))
    manifest_path.write_text(
        "tests/test_alpha.py\ntests/test_alpha.py\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate entries"):
        build_ci_shard_plan(tmp_path, manifest_path, 1)

    manifest_path.write_text("tests/../outside.py\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contained relative path"):
        build_ci_shard_plan(tmp_path, manifest_path, 1)

    same_shard_names: list[str] = []
    desired_assignment: int | None = None
    for index in range(100):
        name = f"test_same_shard_{index}.py"
        relative = f"tests/{name}"
        assignment = (
            int.from_bytes(
                hashlib.sha256(relative.encode("utf-8")).digest()[:8],
                byteorder="big",
                signed=False,
            )
            % 2
        )
        if desired_assignment is None:
            desired_assignment = assignment
        if assignment == desired_assignment:
            same_shard_names.append(name)
        if len(same_shard_names) == 2:
            break
    empty_shard_manifest = _write_ci_fixture(
        tmp_path / "empty-shard",
        tuple(same_shard_names),
    )
    with pytest.raises(ValueError, match="empty shards"):
        build_ci_shard_plan(
            tmp_path / "empty-shard",
            empty_shard_manifest,
            2,
        )


def test_mutation_ledger_preserves_history_and_requires_rollback_on_drop(
    tmp_path: Path,
) -> None:
    improved = _append_mutation(tmp_path, "mutation-improved", 0.40, 0.55)
    resolved_ledger = tmp_path / LEDGER_PATH
    first_append = resolved_ledger.read_bytes()

    degraded = _append_mutation(tmp_path, "mutation-degraded", 0.55, 0.51)
    records = verify_epistemic_mutation_ledger(tmp_path, LEDGER_PATH)
    audit = audit_epistemic_mutation_ledger(tmp_path, LEDGER_PATH)

    assert improved["decision"] == "eligible_for_operator_review"
    assert improved["execution_authority"] == "none"
    assert degraded["decision"] == "rollback_required"
    assert degraded["rollback_required"] is True
    assert degraded["history_rewrite_permitted"] is False
    assert degraded["rollback_evidence"] == {
        "required": True,
        "target_artifact_hash": _sha256("mutation-degraded-baseline"),
        "candidate_evidence_preserved": True,
        "history_rewrite_permitted": False,
    }
    assert resolved_ledger.read_bytes().startswith(first_append)
    assert len(records) == 2
    assert audit["integrity_status"] == "verified"
    assert audit["record_count"] == 2

    exact_retry = _append_mutation(tmp_path, "mutation-degraded", 0.55, 0.51)
    assert exact_retry == degraded
    assert len(verify_epistemic_mutation_ledger(tmp_path, LEDGER_PATH)) == 2


def test_mutation_ledger_tamper_fails_closed_and_blocks_future_append(
    tmp_path: Path,
) -> None:
    _append_mutation(tmp_path, "mutation-original", 0.50, 0.60)
    resolved_ledger = tmp_path / LEDGER_PATH
    record = json.loads(resolved_ledger.read_text(encoding="utf-8"))
    record["candidate_fitness"] = 0.99
    resolved_ledger.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tampered_bytes = resolved_ledger.read_bytes()

    audit = audit_epistemic_mutation_ledger(tmp_path, LEDGER_PATH)

    assert audit["integrity_status"] == "corrupt_fail_closed"
    assert audit["decision"] == "rollback_required"
    assert audit["corruption"] is not None
    assert audit["corruption"]["failure_code"] == "entry_hash_mismatch"
    with pytest.raises(EpistemicMutationLedgerCorruptionError):
        _append_mutation(tmp_path, "mutation-after-corruption", 0.60, 0.70)
    assert resolved_ledger.read_bytes() == tampered_bytes


def test_mutation_ledger_detects_valid_prefix_truncation_and_id_conflicts(
    tmp_path: Path,
) -> None:
    _append_mutation(tmp_path, "mutation-one", 0.20, 0.30)
    _append_mutation(tmp_path, "mutation-two", 0.30, 0.40)
    resolved_ledger = tmp_path / LEDGER_PATH
    lines = resolved_ledger.read_text(encoding="utf-8").splitlines()
    resolved_ledger.write_text(lines[0] + "\n", encoding="utf-8")

    truncated = audit_epistemic_mutation_ledger(tmp_path, LEDGER_PATH)

    assert truncated["integrity_status"] == "corrupt_fail_closed"
    assert truncated["corruption"] is not None
    assert truncated["corruption"]["failure_code"] == "head_anchor_state_mismatch"

    conflict_root = tmp_path / "conflict"
    conflict_root.mkdir()
    _append_mutation(conflict_root, "mutation-conflict", 0.40, 0.50)
    with pytest.raises(EpistemicMutationConflictError):
        _append_mutation(conflict_root, "mutation-conflict", 0.40, 0.60)


def test_anchor_write_failure_is_explicit_and_future_appends_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_anchor_replace(_source: Path, _destination: Path) -> None:
        raise OSError("injected anchor persistence failure")

    monkeypatch.setattr(
        epistemic_mutation_ledger,
        "_replace_file",
        fail_anchor_replace,
    )

    with pytest.raises(
        EpistemicMutationLedgerWriteError,
        match="head anchor",
    ):
        _append_mutation(tmp_path, "mutation-interrupted", 0.40, 0.50)

    audit = audit_epistemic_mutation_ledger(tmp_path, LEDGER_PATH)
    assert audit["integrity_status"] == "corrupt_fail_closed"
    assert audit["corruption"] is not None
    assert audit["corruption"]["failure_code"] == "head_anchor_missing"

    with pytest.raises(EpistemicMutationLedgerCorruptionError):
        _append_mutation(tmp_path, "mutation-after-interruption", 0.50, 0.60)


def test_mutation_ledger_rejects_paths_outside_contained_artifact_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(PermissionError, match="contained artifact root"):
        append_epistemic_mutation_evaluation(
            tmp_path,
            Path("outside.jsonl"),
            "mutation-escape",
            "2026-07-26T12:00:00+00:00",
            _sha256("code"),
            _sha256("data"),
            _sha256("baseline"),
            _sha256("candidate"),
            0.4,
            0.5,
            {"measurement_source": "deterministic_fixture"},
        )


def test_platform_test_seam_does_not_mutate_global_os_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_os_name = os.name

    monkeypatch.setattr(process_tree, "_runtime_platform_name", lambda: "nt")

    assert process_tree._runtime_platform_name() == "nt"
    assert os.name == observed_os_name
