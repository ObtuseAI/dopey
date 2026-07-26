"""Append-only failure-mode registry for DOPEY."""
from __future__ import annotations

import json
from pathlib import Path


FAILURE_MODE_REGISTRY_VERSION = "dopey-failure-mode-registry-v1"
FAILURE_MODE_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "failure_modes"
FAILURE_MODE_REGISTRY_PATH = FAILURE_MODE_ARTIFACT_DIR / "failure_mode_registry.jsonl"


def write_failure_mode_registry(record: dict, path: Path | str | None = None) -> Path:
    target = Path(path) if path else FAILURE_MODE_REGISTRY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def latest_failure_mode_summary(path: Path | str | None = None) -> dict:
    target = Path(path) if path else FAILURE_MODE_REGISTRY_PATH
    if not target.exists():
        return {
            "failure_mode_registry_version": FAILURE_MODE_REGISTRY_VERSION,
            "registry_path": str(target),
            "failure_mode_records_available": False,
            "failure_modes_detected": 0,
            "top_failure_modes": [],
            "mitigation_hints": [],
        }
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {
            "failure_mode_registry_version": FAILURE_MODE_REGISTRY_VERSION,
            "registry_path": str(target),
            "failure_mode_records_available": False,
            "failure_modes_detected": 0,
            "top_failure_modes": [],
            "mitigation_hints": [],
        }
    last = json.loads(lines[-1])
    modes = last.get("failure_modes", [])
    ranked = sorted(
        modes,
        key=lambda mode: (
            {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(mode.get("severity", "low"), 0),
            mode.get("evidence_score", 0.0),
            mode.get("recurrence_count", 0),
        ),
        reverse=True,
    )
    return {
        "failure_mode_registry_version": FAILURE_MODE_REGISTRY_VERSION,
        "registry_path": str(target),
        "failure_mode_records_available": True,
        "failure_modes_detected": len(modes),
        "top_failure_modes": [
            {
                "failure_mode_id": mode.get("failure_mode_id", ""),
                "affected_family": mode.get("affected_family", ""),
                "severity": mode.get("severity", ""),
                "recurrence_count": mode.get("recurrence_count", 0),
                "mitigation_hint": mode.get("mitigation_hint", ""),
                "recommended_mutation_constraint_update": mode.get("recommended_mutation_constraint_update", ""),
            }
            for mode in ranked[:8]
        ],
        "mitigation_hints": last.get("mitigation_hints", [])[:8],
        "constraint_updates": last.get("constraint_updates", [])[:8],
    }
