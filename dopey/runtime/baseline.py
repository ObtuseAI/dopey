"""Snapshot the pre-vNext evidence baseline without changing research output."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash


ARTIFACT_TYPE_PATTERN = re.compile(r'"artifact_type"\s*:\s*"([^"]+)"')


def collect_artifact_schema_counts(artifact_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(artifact_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        relative_parts = path.relative_to(artifact_root).parts
        if "exports" in relative_parts or "vnext" in relative_parts:
            continue
        with path.open("rb") as handle:
            prefix_bytes = handle.read(16384)
        try:
            prefix = prefix_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            artifact_type = "invalid_utf8_json_artifact"
        else:
            match = ARTIFACT_TYPE_PATTERN.search(prefix)
            artifact_type = match.group(1) if match else "untyped_json_artifact"
        counts[artifact_type] = counts.get(artifact_type, 0) + 1
    return counts


def _load_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required baseline artifact is missing: path={path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"baseline artifact must be a JSON object: path={path}")
    return value


def build_baseline_report(
    readiness_path: Path,
    forward_walk_path: Path,
    calibration_path: Path,
    supervisor_path: Path,
    test_files: Sequence[Path],
    artifact_schema_counts: Mapping[str, int],
    captured_at: str,
    source_revision: str,
) -> dict[str, Any]:
    readiness = _load_object(readiness_path)
    forward_walk = _load_object(forward_walk_path)
    calibration = _load_object(calibration_path)
    supervisor = _load_object(supervisor_path)
    stage_results = supervisor.get("stage_results", {})
    body: dict[str, Any] = {
        "artifact_type": "dopey_v4_baseline_report",
        "baseline_version": "DOPEY_V4_BASELINE_REPORT_v1",
        "captured_at": captured_at,
        "source_revision": source_revision,
        "readiness": {
            "readiness_status": readiness.get("readiness_status"),
            "action_ready": readiness.get("action_ready"),
            "missing_requirements": readiness.get("missing_requirements", []),
            "forward_closed_trades": readiness.get("forward_closed_trades"),
            "forward_closed_trades_required": readiness.get("forward_closed_trades_required"),
            "reproducibility_hash": readiness.get("reproducibility_hash"),
        },
        "forward_evidence": {
            "closed_trade_count": forward_walk.get("closed_trade_count"),
            "closed_win_count": forward_walk.get("closed_win_count"),
            "closed_net_pnl_premium_units": forward_walk.get("closed_net_pnl_premium_units"),
            "not_profitability_claim": forward_walk.get("not_profitability_claim"),
            "reproducibility_hash": forward_walk.get("reproducibility_hash"),
        },
        "calibration": {
            "signal_calibration_status": calibration.get("signal_calibration_status"),
            "settled_total": calibration.get("settled_total"),
            "overall_hit_rate": calibration.get("overall_hit_rate"),
            "contested_total": calibration.get("contested_total"),
            "contested_hit_rate": calibration.get("contested_hit_rate"),
            "probability_calibration_error_available": calibration.get("expected_calibration_error") is not None,
        },
        "supervisor": {
            "supervisor_status": supervisor.get("supervisor_status"),
            "stages_total": supervisor.get("stages_total"),
            "stages_green": supervisor.get("stages_green"),
            "stages_completed_degraded": supervisor.get("stages_completed_degraded"),
            "stages_failed_absorbed": supervisor.get("stages_failed_absorbed"),
            "stage_statuses": {
                str(name): str(record.get("stage_status", "unknown"))
                for name, record in stage_results.items()
            },
            "stage_duration_telemetry_status": "not_recorded_in_current_supervisor_summary",
        },
        "tests": {
            "test_file_count": len(test_files),
            "test_files": [path.as_posix() for path in sorted(test_files)],
            "result_status": "inventory_snapshot_not_test_execution",
        },
        "artifact_schema_counts": dict(sorted(artifact_schema_counts.items())),
        "runtime_cost": {
            "status": "partial_missing_per_stage_duration_cpu_memory_and_provider_cost",
            "known_stage_count": len(stage_results),
        },
        "baseline_limitations": [
            "test_inventory_is_not_a_fresh_full_suite_result",
            "current_supervisor_summary_has_no_per_stage_duration_telemetry",
            "accuracy_is_not_probability_calibration",
        ],
        "paper_only": True,
        "live_blocked": True,
        "action_ready": False,
        "strategy_promotion_allowed": False,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}


def write_baseline_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(report), sort_keys=True, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
