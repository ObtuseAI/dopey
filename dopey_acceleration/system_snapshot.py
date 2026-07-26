"""Transactional projection of DOPEY's current paper-research state."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from dopey_backtest.forward_evidence_integrity import POLICY_REPLAY_PATH
from dopey_universe.universe_registry import UNIVERSE_REGISTRY_PATH

from .capabilities import CATALOG_PATH, discover_capabilities
from .common import REPO_ROOT, stable_hash, write_json_atomic
from .compounding import FORWARD_LEDGER_PATH, build_compounding_plan
from .readiness import (
    ACTION_GATE_PATH,
    CONTEXT_GATE_PATH,
    NEWS_MANIFEST_PATH,
    SWING_SUMMARY_PATH,
    UNIVERSE_SUMMARY_PATH,
    build_readiness_acceleration_plan,
)
from .schedule import (
    ACTIVE_IMPROVEMENT_POLICY_PATH,
    SCHEDULE_STATE_PATH,
    build_schedule_plan,
)
from .storage_pressure import measure_storage_pressure
from .universe import build_universe_expansion_plan


SYSTEM_SNAPSHOT_PATH: Final[Path] = (
    REPO_ROOT / "artifacts" / "dopey" / "acceleration" / "system_snapshot.json"
)
SOURCE_PATHS: Final[dict[str, Path]] = {
    "action_readiness_gate": ACTION_GATE_PATH,
    "context_evidence_gate": CONTEXT_GATE_PATH,
    "equity_swing_summary": SWING_SUMMARY_PATH,
    "universe_summary": UNIVERSE_SUMMARY_PATH,
    "universe_registry": UNIVERSE_REGISTRY_PATH,
    "news_manifest": NEWS_MANIFEST_PATH,
    "schedule_state": SCHEDULE_STATE_PATH,
    "autonomous_improvement_policy": ACTIVE_IMPROVEMENT_POLICY_PATH,
    "forward_walk_ledger": FORWARD_LEDGER_PATH,
    "forward_policy_replay": POLICY_REPLAY_PATH,
    "capability_catalog": CATALOG_PATH,
}


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_hashes() -> dict[str, str]:
    return {
        source_id: _file_hash(path)
        for source_id, path in sorted(SOURCE_PATHS.items())
    }


def _projection_hash(record: dict[str, Any]) -> str:
    return stable_hash(record)


def build_system_snapshot(
    repo_root: Path,
    observed_at: datetime,
) -> dict[str, Any]:
    if repo_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(
            f"repository root mismatch: expected={REPO_ROOT}, actual={repo_root}"
        )
    if observed_at.tzinfo is None:
        raise ValueError("system snapshot observed_at must be timezone-aware")
    as_of = observed_at.astimezone(timezone.utc)
    source_hashes_before = _source_hashes()
    readiness = build_readiness_acceleration_plan(repo_root)
    schedule = build_schedule_plan(repo_root, as_of, ())
    universe = build_universe_expansion_plan(repo_root, 50)
    compounding = build_compounding_plan(repo_root)
    capabilities = discover_capabilities(repo_root)
    storage_pressure = measure_storage_pressure(repo_root, True)
    source_hashes_after = _source_hashes()
    projections = {
        "readiness": readiness,
        "schedule": schedule,
        "universe": universe,
        "compounding": compounding,
        "capabilities": capabilities,
        "storage_pressure": storage_pressure,
    }
    assertions = [
        {
            "assertion_id": "source_files_stable_during_projection",
            "passed": source_hashes_before == source_hashes_after,
            "expected": source_hashes_before,
            "actual": source_hashes_after,
        },
        {
            "assertion_id": "active_symbol_count_consistent",
            "passed": readiness["active_symbol_count"]
            == universe["active_symbol_count"],
            "expected": readiness["active_symbol_count"],
            "actual": universe["active_symbol_count"],
        },
        {
            "assertion_id": "paper_only_boundary_consistent",
            "passed": all(
                projection.get("paper_only") is True
                and projection.get("live_blocked") is True
                for projection in projections.values()
                if isinstance(projection, dict)
                and "paper_only" in projection
            ),
            "expected": "paper_only=true,live_blocked=true",
            "actual": "projection_flags_checked",
        },
    ]
    body: dict[str, Any] = {
        "artifact_type": "transactional_system_snapshot",
        "snapshot_version": "dopey-system-snapshot-v1",
        "as_of": as_of.isoformat(),
        "snapshot_status": (
            "consistent"
            if all(assertion["passed"] for assertion in assertions)
            else "mixed_generation_detected"
        ),
        "source_hashes": source_hashes_after,
        "source_paths": {
            source_id: str(path)
            for source_id, path in sorted(SOURCE_PATHS.items())
        },
        "projection_hashes": {
            name: _projection_hash(projection)
            for name, projection in projections.items()
        },
        "consistency_assertions": assertions,
        **projections,
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "snapshot_id": f"snapshot:{stable_hash(body)[:24]}"}
    write_json_atomic(SYSTEM_SNAPSHOT_PATH, output)
    return output
