"""Content-addressed verification for evaluator and constitutional protected files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast


ASCENDANCY_DYNAMIC_STATE_PATHS = frozenset(
    {
        "APPROACH_REGISTRY.jsonl",
        "CANDIDATE_LINEAGE.jsonl",
        "EXPERIMENT_REGISTRY.jsonl",
        "EXPERIMENT_REGISTRY.jsonl.head.json",
        "FAILURE_REGISTRY.jsonl",
        "HOLDOUT_BUDGET.json",
        "HYPOTHESIS_REGISTRY.jsonl",
        "PROOF_LEDGER.jsonl",
        "PROOF_LEDGER.jsonl.head.json",
        "shadow_trading/FORWARD_EVIDENCE.jsonl",
        "shadow_trading/FORWARD_EVIDENCE.jsonl.head.json",
    }
)
ASCENDANCY_PROTECTED_SOURCE_ROOTS = (
    "dopey/ascendancy",
    "dopey/constitution",
    "dopey/settlement",
    "dopey/truth",
    # dopey_live is the only package that can reach a real broker: every
    # source change there must be deliberate (edit -> regenerate
    # PROTECTED_MANIFEST.json via build_ascendancy_protected_manifest ->
    # freeze test green), never incidental.
    "dopey_live",
    "sealed_evaluator_client",
    "verifier",
)
ASCENDANCY_PROTECTED_PATHS = frozenset(
    {
        "ARTIFACT_PROVENANCE.json",
        "DATA_MANIFEST.json",
        "DOPEY_CONSTITUTION.md",
        "DYNAMIC_ANCHOR_TRUST.json",
        "ENVIRONMENT_V1_FREEZE.json",
        "FORWARD_EVIDENCE_TRUST.json",
        "PROMOTION_AUTHORITY_TRUST.json",
        "SEALED_EVALUATOR_TRUST.json",
        "dopey/ascendancy/__init__.py",
        "dopey/ascendancy/baselines.py",
        "dopey/ascendancy/behavioral_firewall.py",
        "dopey/ascendancy/contracts.py",
        "dopey/ascendancy/execution_quality.py",
        "dopey/ascendancy/forward_signatures.py",
        "dopey/ascendancy/gates.py",
        "dopey/ascendancy/identity.py",
        "dopey/ascendancy/ledger.py",
        "dopey/ascendancy/negative_controls.py",
        "dopey/ascendancy/negative_control_generation.py",
        "dopey/ascendancy/paired_evaluation.py",
        "dopey/ascendancy/policy_ids.py",
        "dopey/ascendancy/pricing.py",
        "dopey/ascendancy/promotion.py",
        "dopey/ascendancy/readiness_frontier.py",
        "dopey/ascendancy/attribution.py",
        "dopey/ascendancy/retirement.py",
        "dopey/ascendancy/router.py",
        "dopey/ascendancy/stress.py",
        "dopey/ascendancy/tickets.py",
        "dopey/ascendancy/v1_resources.py",
        "dopey/constitution/__init__.py",
        "dopey/constitution/authority.py",
        "dopey/constitution/evidence_law.py",
        "dopey/constitution/execution_seal.py",
        "dopey/constitution/invariants.py",
        "dopey/constitution/mutation_protection.py",
        "dopey/constitution/permissions.py",
        "dopey/constitution/readiness_law.py",
        "dopey/settlement/__init__.py",
        "dopey/settlement/accrual.py",
        "dopey/settlement/calibration.py",
        "dopey/settlement/grading.py",
        "dopey/settlement/ledger.py",
        "dopey/settlement/operational.py",
        "dopey/settlement/predictions.py",
        "dopey/settlement/run_accrual_monitor.py",
        "dopey/settlement/run_operational_settlement.py",
        "dopey/settlement/run_settlement_cycle.py",
        "dopey/settlement/runtime.py",
        "dopey/truth/__init__.py",
        "dopey/truth/agent_ablation.py",
        "dopey/truth/causal_evaluation.py",
        "dopey/truth/cohorts.py",
        "dopey/__init__.py",
        "dopey_core/config.py",
        "dopey_execution/__init__.py",
        "dopey_execution/alpaca_options_adapter.py",
        "dopey_execution/broker_capability_detector.py",
        "dopey_execution/errors.py",
        "dopey_execution/execution_intent.py",
        "dopey_execution/robinhood_mcp_adapter.py",
        "dopey_execution/tradier_options_adapter.py",
        "dopey_governor/__init__.py",
        "dopey_governor/live_order_gate.py",
        "dopey_governor/promotion_policy.py",
        "dopey_governor/trade_permission_kernel.py",
        "data_contracts/universe_v1.json",
        "environments/environment_v1.json",
        "dopey_live/__init__.py",
        "dopey_live/control.py",
        "dopey_live/ledger.py",
        "dopey_live/models.py",
        "dopey_live/robinhood_gateway.py",
        "dopey_live/service.py",
        "dopey_live/settlement.py",
        "dopey_live/signals.py",
        "sealed_evaluator_client/__init__.py",
        "sealed_evaluator_client/aggregate_contract.py",
        "sealed_evaluator_client/budget.py",
        "sealed_evaluator_client/signatures.py",
        "pyproject.toml",
        "verifier/__init__.py",
        "verifier/audit.py",
        "verifier/dynamic_anchor.py",
        "verifier/environment_freeze.py",
        "verifier/external_root.py",
        "verifier/path_policy.py",
        "verifier/protected_manifest.py",
    }
)


def discover_protected_python_sources(
    repository_root: Path,
    relative_roots: tuple[str, ...],
) -> frozenset[str]:
    root = repository_root.resolve(strict=True)
    discovered: set[str] = set()
    for relative_root in relative_roots:
        source_root = (root / relative_root).resolve(strict=True)
        try:
            source_root.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"protected source root escapes repository: path={relative_root}"
            ) from error
        if not source_root.is_dir():
            raise ValueError(f"protected source root is not a directory: path={relative_root}")
        discovered.update(
            source_path.relative_to(root).as_posix()
            for source_path in source_root.rglob("*.py")
            if source_path.is_file()
        )
    return frozenset(discovered)


def verify_protected_source_coverage(
    repository_root: Path,
    protected_paths: frozenset[str],
    relative_roots: tuple[str, ...],
) -> None:
    discovered = discover_protected_python_sources(repository_root, relative_roots)
    protected_sources = frozenset(
        path
        for path in protected_paths
        if any(path == root or path.startswith(f"{root}/") for root in relative_roots)
        and path.endswith(".py")
    )
    if discovered != protected_sources:
        missing = sorted(discovered.difference(protected_sources))
        absent = sorted(protected_sources.difference(discovered))
        raise ValueError(
            "protected Python source coverage differs from the sealed file set: "
            f"unprotected={missing}, absent={absent}"
        )


def verify_ascendancy_protected_source_coverage(repository_root: Path) -> None:
    verify_protected_source_coverage(
        repository_root,
        ASCENDANCY_PROTECTED_PATHS,
        ASCENDANCY_PROTECTED_SOURCE_ROOTS,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_protected_manifest(
    repository_root: Path,
    relative_paths: tuple[str, ...],
) -> dict[str, object]:
    root = repository_root.resolve(strict=True)
    if not relative_paths or len(relative_paths) != len(set(relative_paths)):
        raise ValueError("protected manifest requires unique file paths")
    files: dict[str, str] = {}
    for relative_path in sorted(relative_paths):
        target = (root / relative_path).resolve(strict=True)
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError(f"protected file escapes repository: path={relative_path}") from error
        if not target.is_file():
            raise ValueError(f"protected path is not a file: path={relative_path}")
        files[relative_path] = file_sha256(target)
    body = {"schema_version": "dopey-protected-manifest-v1", "files": files}
    encoded = json.dumps(body, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return {**body, "manifest_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def verify_protected_manifest(repository_root: Path, manifest_path: Path) -> None:
    decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or not isinstance(decoded.get("files"), dict):
        raise ValueError("protected manifest must contain a file-hash mapping")
    manifest = cast(dict[str, object], decoded)
    files = cast(dict[str, str], manifest["files"])
    rebuilt = build_protected_manifest(repository_root, tuple(files))
    if rebuilt != manifest:
        raise ValueError("protected manifest mismatch; evaluator or constitution changed")


def build_ascendancy_protected_manifest(repository_root: Path) -> dict[str, object]:
    verify_ascendancy_protected_source_coverage(repository_root)
    return build_protected_manifest(repository_root, tuple(sorted(ASCENDANCY_PROTECTED_PATHS)))


def verify_ascendancy_protected_manifest(repository_root: Path, manifest_path: Path) -> None:
    verify_ascendancy_protected_source_coverage(repository_root)
    decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or not isinstance(decoded.get("files"), dict):
        raise ValueError("Ascendancy protected manifest must contain a file-hash mapping")
    files = cast(dict[str, str], decoded["files"])
    if frozenset(files) != ASCENDANCY_PROTECTED_PATHS:
        raise ValueError("Ascendancy protected manifest file set was expanded or shrunk")
    verify_protected_manifest(repository_root, manifest_path)
