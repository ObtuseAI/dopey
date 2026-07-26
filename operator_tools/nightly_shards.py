"""Resumable, content-addressed pytest shards for the nightly harness."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as element_tree
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
from typing import Any, TypedDict

from dopey_research_pipeline.artifact_io import write_json_atomic
from operator_tools.process_tree import (
    ProcessTreeTerminationError,
    run_captured_process_tree,
)


class NightlyShardResult(TypedDict):
    shard_id: str
    suite_fingerprint: str
    status: str
    returncode: int | None
    timed_out: bool
    reused_checkpoint: bool
    test_file_count: int
    test_files: list[str]
    summary_line: str
    passed: int
    failed: int
    errors: int
    skipped: int
    junit: str
    output_log: str
    failure_class: str
    resume_test_files: list[str]
    resume_evidence_status: str
    process_tree_terminated: bool


DURATION_HISTORY_VERSION = "dopey-nightly-test-duration-history-v2"
DURATION_EWMA_ALPHA = 0.35
ORDERED_TEST_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "test_public_signal_research_breakthrough_v2.py",
        "test_public_signal_research_breakthrough_v3.py",
        "test_public_signal_research_breakthrough_v4.py",
        "test_public_signal_research_breakthrough_v5.py",
        "test_public_signal_research_breakthrough_v6.py",
        "test_public_signal_research_breakthrough_v7.py",
    ),
    (
        "test_broker_readiness_preflight.py",
        "test_read_only_detector_manual_approval_packet.py",
        "test_read_only_detector_dry_run_validator.py",
        "test_read_only_detector_approval_intake_validator.py",
        "test_read_only_detector_approval_to_run_handoff_gate.py",
        "test_read_only_detector_pre_run_safety_scanner.py",
        "test_human_approved_read_only_broker_capability_detector.py",
        "test_read_only_detector_post_run_evidence_contract.py",
    ),
)


def _parse_pytest_tail(output: str) -> dict[str, Any]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    tail = lines[-1] if lines else ""
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    parts = tail.replace(",", " ").split()
    for index in range(1, len(parts)):
        prior = parts[index - 1]
        if not prior.isdigit():
            continue
        word = parts[index]
        if word in counts:
            counts[word] = int(prior)
        elif word in {"error", "errors"}:
            counts["errors"] = int(prior)
    return {"summary_line": tail, **counts}


def _duration_scale(test_files: tuple[Path, ...], duration_hints: dict[str, float]) -> float | None:
    ratios = [
        duration_hints[f"tests/{path.name}"] / max(float(path.stat().st_size), 1.0)
        for path in test_files
        if f"tests/{path.name}" in duration_hints
    ]
    return median(ratios) if ratios else None


def _estimated_duration(path: Path, duration_hints: dict[str, float], scale: float | None) -> float:
    hint = duration_hints.get(f"tests/{path.name}")
    if hint is not None:
        return max(hint, 0.001)
    if scale is not None:
        return max(float(path.stat().st_size) * scale, 0.001)
    return max(float(path.stat().st_size), 1.0)


def _ordered_test_units(test_files: tuple[Path, ...]) -> tuple[tuple[Path, ...], ...]:
    by_name = {path.name: path for path in test_files}
    consumed: set[str] = set()
    units: list[tuple[Path, ...]] = []
    for group in ORDERED_TEST_GROUPS:
        present = tuple(by_name[name] for name in group if name in by_name)
        if present:
            units.append(present)
            consumed.update(path.name for path in present)
    units.extend((path,) for path in test_files if path.name not in consumed)
    return tuple(units)


def build_test_shards(
    tests_dir: Path,
    shard_count: int,
    duration_hints: dict[str, float],
) -> tuple[tuple[Path, ...], ...]:
    if shard_count <= 0:
        raise ValueError(f"nightly shard count must be positive: shard_count={shard_count}")
    test_files = tuple(sorted(tests_dir.glob("test_*.py"), key=lambda path: path.name))
    if not test_files:
        raise FileNotFoundError(f"nightly test discovery found no files: tests_dir={tests_dir}")
    actual_shard_count = min(shard_count, len(test_files))
    scale = _duration_scale(test_files, duration_hints)
    weighted_units = [
        (
            unit,
            sum(_estimated_duration(path, duration_hints, scale) for path in unit),
        )
        for unit in _ordered_test_units(test_files)
    ]
    weighted_units.sort(key=lambda item: (-item[1], tuple(path.name for path in item[0])))
    shards: list[list[tuple[Path, ...]]] = [[] for _ in range(actual_shard_count)]
    shard_weights = [0.0 for _ in range(actual_shard_count)]
    for unit, weight in weighted_units:
        index = min(range(actual_shard_count), key=lambda item: (shard_weights[item], item))
        shards[index].append(unit)
        shard_weights[index] += weight
    output: list[tuple[Path, ...]] = []
    for shard_units in shards:
        ordered_units = sorted(shard_units, key=lambda unit: min(path.name for path in unit))
        output.append(tuple(path for unit in ordered_units for path in unit))
    return tuple(output)


def suite_fingerprint(
    repo_root: Path,
    shards: tuple[tuple[Path, ...], ...],
    control_files: tuple[Path, ...],
    source_files: tuple[Path, ...],
) -> str:
    digest = hashlib.sha256()
    resolved_root = repo_root.resolve(strict=True)
    inputs = {
        path.resolve()
        for path in (
            *(path for shard in shards for path in shard),
            *control_files,
            *source_files,
        )
    }
    for path in sorted(inputs, key=lambda item: str(item)):
        if not path.exists():
            raise FileNotFoundError(f"nightly fingerprint input is missing: path={path}")
        try:
            relative = path.relative_to(resolved_root).as_posix()
        except ValueError as error:
            raise ValueError(
                f"nightly fingerprint input is outside the repository: path={path}, repo_root={resolved_root}"
            ) from error
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _production_source_files(repo_root: Path) -> tuple[Path, ...]:
    excluded_parts = frozenset({".git", ".venv", "artifacts", "__pycache__"})
    return tuple(
        sorted(
            (
                path
                for path in repo_root.rglob("*.py")
                if not excluded_parts.intersection(path.relative_to(repo_root).parts)
            ),
            key=lambda path: path.relative_to(repo_root).as_posix(),
        )
    )


def _control_files(repo_root: Path) -> tuple[Path, ...]:
    required = (repo_root / "tests" / "conftest.py", repo_root / "pyproject.toml")
    seed_archive = repo_root / "tests" / "fixtures" / "runtime_artifact_seed_v1.zip"
    seed_manifest = repo_root / "tests" / "fixtures" / "runtime_artifact_seed_v1_manifest.json"
    seed_presence = (seed_archive.exists(), seed_manifest.exists())
    if any(seed_presence) and not all(seed_presence):
        raise FileNotFoundError(
            "nightly artifact seed controls must exist as a pair: "
            f"archive={seed_archive.exists()}, manifest={seed_manifest.exists()}"
        )
    return required + ((seed_archive, seed_manifest) if all(seed_presence) else ())


def _test_file_from_classname(classname: str) -> str | None:
    if not classname.startswith("tests.test_"):
        return None
    module_name = classname.split(".", 2)[1]
    return f"tests/{module_name}.py"


def _junit_durations(path: Path) -> dict[str, float]:
    root = element_tree.parse(path).getroot()
    durations: dict[str, float] = {}
    for case in root.iter("testcase"):
        test_file = _test_file_from_classname(str(case.attrib.get("classname", "")))
        if test_file is None:
            continue
        durations[test_file] = durations.get(test_file, 0.0) + float(case.attrib.get("time", "0") or 0.0)
    return durations


def _refresh_duration_history(nightly_dir: Path) -> dict[str, float]:
    durations: dict[str, float] = {}
    variances: dict[str, float] = {}
    checkpoint_root = nightly_dir / "shard_checkpoints"
    checkpoint_paths = sorted(
        checkpoint_root.glob("*/shard-*.json"),
        key=lambda path: (path.stat().st_mtime_ns, str(path)),
    )
    for checkpoint_path in checkpoint_paths:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(checkpoint, dict):
            raise TypeError(f"nightly shard checkpoint must be an object: path={checkpoint_path}")
        status = str(checkpoint.get("status", ""))
        if status not in {"passed", "failed"}:
            continue
        junit_value = checkpoint.get("junit")
        if not isinstance(junit_value, str) or not junit_value:
            if status == "failed":
                continue
            raise ValueError(f"nightly shard checkpoint lacks a JUnit path: path={checkpoint_path}")
        junit_path = Path(junit_value)
        if not junit_path.exists():
            if status == "failed":
                continue
            raise FileNotFoundError(f"nightly shard JUnit evidence is missing: path={junit_path}")
        for test_file, duration in _junit_durations(junit_path).items():
            previous = durations.get(test_file)
            if previous is None:
                durations[test_file] = duration
                variances[test_file] = 0.0
                continue
            delta = duration - previous
            durations[test_file] = (
                DURATION_EWMA_ALPHA * duration
                + (1.0 - DURATION_EWMA_ALPHA) * previous
            )
            variances[test_file] = (
                (1.0 - DURATION_EWMA_ALPHA)
                * (
                    variances.get(test_file, 0.0)
                    + DURATION_EWMA_ALPHA * delta * delta
                )
            )
    history_path = nightly_dir / "test_duration_history.json"
    write_json_atomic(
        history_path,
        {
            "history_version": DURATION_HISTORY_VERSION,
            "test_file_count": len(durations),
            "duration_seconds_by_test_file": dict(sorted(durations.items())),
            "duration_variance_by_test_file": dict(
                sorted(variances.items())
            ),
            "estimator": "exponentially_weighted_mean_and_variance",
            "ewma_alpha": DURATION_EWMA_ALPHA,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    return durations


def _checkpoint_result(path: Path, fingerprint: str) -> NightlyShardResult | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"nightly shard checkpoint must be an object: path={path}")
    if str(value.get("suite_fingerprint", "")) != fingerprint or value.get("status") != "passed":
        return None
    return NightlyShardResult(
        **{
            **value,
            "reused_checkpoint": True,
            "failure_class": str(value.get("failure_class", "")),
            "resume_test_files": list(value.get("resume_test_files", [])),
            "resume_evidence_status": str(
                value.get("resume_evidence_status", "not_required")
            ),
            "process_tree_terminated": bool(
                value.get("process_tree_terminated", False)
            ),
        }
    )


def _resume_test_files(
    checkpoint_path: Path,
    fingerprint: str,
    relative_files: list[str],
) -> list[str]:
    if not checkpoint_path.exists():
        return relative_files
    value = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("suite_fingerprint") != fingerprint
        or value.get("status") != "inconclusive_timeout"
    ):
        return relative_files
    raw_resume = value.get("resume_test_files")
    if not isinstance(raw_resume, list) or not all(
        isinstance(path, str) for path in raw_resume
    ):
        return relative_files
    allowed = set(relative_files)
    return [path for path in raw_resume if path in allowed] or relative_files


def _completed_test_files(path: Path) -> tuple[set[str], str]:
    if not path.exists():
        return set(), "partial_junit_missing"
    try:
        root = element_tree.parse(path).getroot()
    except element_tree.ParseError:
        return set(), "partial_junit_invalid"
    completed = {
        test_file
        for case in root.iter("testcase")
        if (
            test_file := _test_file_from_classname(
                str(case.attrib.get("classname", ""))
            )
        )
        is not None
    }
    return completed, "partial_junit_verified"


def _run_shard(
    python_executable: str,
    repo_root: Path,
    nightly_dir: Path,
    shard_index: int,
    test_files: tuple[Path, ...],
    fingerprint: str,
    timeout_seconds: int,
) -> NightlyShardResult:
    shard_id = f"shard-{shard_index:03d}"
    checkpoint_dir = nightly_dir / "shard_checkpoints" / fingerprint
    checkpoint_path = checkpoint_dir / f"{shard_id}.json"
    prior = _checkpoint_result(checkpoint_path, fingerprint)
    if prior is not None:
        return prior
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    junit_path = checkpoint_dir / f"{shard_id}.xml"
    output_path = checkpoint_dir / f"{shard_id}.log"
    relative_files = [str(path.relative_to(repo_root)).replace("\\", "/") for path in test_files]
    execution_files = _resume_test_files(
        checkpoint_path,
        fingerprint,
        relative_files,
    )
    command = [
        python_executable,
        "-m",
        "pytest",
        *execution_files,
        "-q",
        "--no-header",
        f"--junitxml={junit_path}",
    ]
    returncode: int | None
    try:
        completed = run_captured_process_tree(
            command,
            repo_root,
            None,
            timeout_seconds,
        )
    except ProcessTreeTerminationError as error:
        raise RuntimeError(
            "nightly shard timed out and its process tree could not be "
            f"proven terminated: shard_id={shard_id}, error={error}"
        ) from error
    returncode = completed["return_code"]
    timed_out = completed["timed_out"]
    output = completed["stdout"] + completed["stderr"]
    output_path.write_text(output, encoding="utf-8")
    parsed = _parse_pytest_tail(output)
    status = "inconclusive_timeout" if timed_out else "passed" if returncode == 0 else "failed"
    completed_files, resume_evidence_status = (
        _completed_test_files(junit_path)
        if timed_out
        else (set(execution_files), "not_required")
    )
    resume_test_files = (
        [
            path
            for path in relative_files
            if path not in completed_files
        ]
        if timed_out
        else []
    )
    result = NightlyShardResult(
        shard_id=shard_id,
        suite_fingerprint=fingerprint,
        status=status,
        returncode=returncode,
        timed_out=timed_out,
        reused_checkpoint=False,
        test_file_count=len(test_files),
        test_files=relative_files,
        summary_line=str(parsed["summary_line"]),
        passed=int(parsed["passed"]),
        failed=int(parsed["failed"]),
        errors=int(parsed["errors"]),
        skipped=int(parsed["skipped"]),
        junit=str(junit_path),
        output_log=str(output_path),
        failure_class=(
            "timeout_budget_exhaustion"
            if timed_out
            else "correctness_failure"
            if returncode != 0
            else ""
        ),
        resume_test_files=resume_test_files,
        resume_evidence_status=resume_evidence_status,
        process_tree_terminated=completed["process_tree_terminated"],
    )
    write_json_atomic(checkpoint_path, result)
    return result


def run_sharded_suite(
    python_executable: str,
    repo_root: Path,
    tests_dir: Path,
    nightly_dir: Path,
    shard_count: int,
    worker_count: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    if worker_count <= 0:
        raise ValueError(f"nightly worker count must be positive: worker_count={worker_count}")
    if timeout_seconds <= 0:
        raise ValueError(f"nightly shard timeout must be positive: timeout_seconds={timeout_seconds}")
    duration_hints = _refresh_duration_history(nightly_dir)
    shards = build_test_shards(tests_dir, shard_count, duration_hints)
    control_files = _control_files(repo_root)
    source_files = _production_source_files(repo_root)
    fingerprint = suite_fingerprint(repo_root, shards, control_files, source_files)
    with ThreadPoolExecutor(max_workers=min(worker_count, len(shards))) as executor:
        results = list(
            executor.map(
                lambda indexed: _run_shard(
                    python_executable,
                    repo_root,
                    nightly_dir,
                    indexed[0],
                    indexed[1],
                    fingerprint,
                    timeout_seconds,
                ),
                enumerate(shards, start=1),
            )
        )
    statuses = [result["status"] for result in results]
    suite_status = (
        "inconclusive_timeout"
        if "inconclusive_timeout" in statuses
        else "complete_failures"
        if "failed" in statuses
        else "complete_green"
    )
    counts = {
        name: sum(int(result[name]) for result in results)
        for name in ("passed", "failed", "errors", "skipped")
    }
    summary_line = (
        f"{counts['passed']} passed, {counts['failed']} failed, {counts['errors']} errors, "
        f"{counts['skipped']} skipped across {len(results)} resumable shards; status={suite_status}"
    )
    return {
        "suite_status": suite_status,
        "suite_fingerprint": fingerprint,
        "shard_count": len(results),
        "duration_hint_file_count": len(duration_hints),
        "balancing_policy": "ewma_duration_and_variance_then_source_size_bootstrap",
        "reused_checkpoint_count": sum(result["reused_checkpoint"] for result in results),
        "summary_line": summary_line,
        **counts,
        "shards": results,
        "paper_only": True,
        "live_blocked": True,
    }
