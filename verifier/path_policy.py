"""Fail-closed candidate filesystem policy; no candidate can target protected roots."""

from __future__ import annotations

from pathlib import Path

from .protected_manifest import ASCENDANCY_DYNAMIC_STATE_PATHS


PROTECTED_ROOTS = frozenset(
    {
        "dopey/constitution",
        "dopey/ascendancy",
        "dopey/truth",
        "dopey/settlement",
        "verifier",
        "sealed_evaluator_client",
        "environments",
        "DOPEY_CONSTITUTION.md",
        "DATA_MANIFEST.json",
        "DYNAMIC_ANCHOR_TRUST.json",
        "DYNAMIC_STATE_ANCHOR_RECEIPT.json",
        "ENVIRONMENT_V1_FREEZE.json",
        "FORWARD_EVIDENCE_TRUST.json",
        "PROMOTION_AUTHORITY_TRUST.json",
        "PROTECTED_MANIFEST.json",
        "SEALED_EVALUATOR_TRUST.json",
        "HOLDOUT_BUDGET.json",
        "APPROACH_REGISTRY.jsonl",
        "ARTIFACT_PROVENANCE.json",
        "HYPOTHESIS_REGISTRY.jsonl",
        "FAILURE_REGISTRY.jsonl",
        "CANDIDATE_LINEAGE.jsonl",
        "EXPERIMENT_REGISTRY.jsonl",
        "PROOF_LEDGER.jsonl",
    }
).union(ASCENDANCY_DYNAMIC_STATE_PATHS)
ALLOWED_CANDIDATE_ROOTS = frozenset({"candidates", "hypotheses", "experiments", "worktrees"})
FORBIDDEN_CANDIDATE_FILENAMES = frozenset({"DOPEY_DEPLOYMENT_TRUST_ROOT.json"})


def assert_candidate_write_path_allowed(repository_root: Path, requested_path: Path) -> None:
    resolved_root = repository_root.resolve(strict=True)
    resolved_target = requested_path.resolve(strict=False)
    try:
        relative = resolved_target.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise PermissionError(
            f"candidate write path escapes repository: requested_path={requested_path}"
        ) from error
    if any(relative == protected or relative.startswith(f"{protected}/") for protected in PROTECTED_ROOTS):
        raise PermissionError(f"candidate write targets protected root: relative_path={relative}")
    if resolved_target.name in FORBIDDEN_CANDIDATE_FILENAMES:
        raise PermissionError(
            "candidate write impersonates an external trust-root contract: "
            f"relative_path={relative}"
        )
    if not any(relative == allowed or relative.startswith(f"{allowed}/") for allowed in ALLOWED_CANDIDATE_ROOTS):
        raise PermissionError(f"candidate write path is not allowlisted: relative_path={relative}")
