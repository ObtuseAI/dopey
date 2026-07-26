"""CLI for the coach-requested point-in-time trend-channel audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dopey.technical.history_adapter import load_validated_symbol_history
from dopey_chart_vision.channel_containment_audit import build_channel_containment_audit
from dopey_equity_swing.market_structure import resample_bars
from dopey_research_pipeline.artifact_io import write_json_atomic


def run_channel_containment_audit(
    coach_artifact: Path,
    history_manifest: Path,
    output_root: Path,
) -> dict[str, Any]:
    session_value: Any = json.loads(coach_artifact.read_text(encoding="utf-8"))
    if not isinstance(session_value, dict):
        raise TypeError(f"coach artifact must be a JSON object: path={coach_artifact}")
    replay = session_value.get("evidence_coach", {}).get("blind_replay", {})
    if not isinstance(replay, dict):
        raise TypeError(f"coach replay must be a JSON object: path={coach_artifact}")
    symbol = str(replay.get("symbol", ""))
    timeframe = str(replay.get("timeframe", ""))
    daily_rows, _proof = load_validated_symbol_history(symbol, history_manifest)
    rows = resample_bars(daily_rows, timeframe)
    audit = build_channel_containment_audit(session_value, rows)
    session_hash = str(session_value["session_hash"])
    artifact_path = output_root / f"{session_hash}.json"
    if artifact_path.exists():
        existing: Any = json.loads(artifact_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing != audit:
            raise ValueError(
                f"channel audit identity conflict: path={artifact_path}, session_hash={session_hash}"
            )
    else:
        write_json_atomic(artifact_path, audit)
    write_json_atomic(output_root / "latest_audit.json", audit)
    return {
        "audit_status": audit["audit_status"],
        "outcome_status": audit["outcome_status"],
        "audit_hash": audit["audit_hash"],
        "channel_observation_count": audit["channel_observation_count"],
        "contained_observation_count": audit["contained_observation_count"],
        "latest_containment_state": (
            audit["latest_observation"]["containment_state"]
            if audit["latest_observation"] is not None
            else "missing"
        ),
        "artifact_path": str(artifact_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit point-in-time trend-channel containment")
    parser.add_argument("--coach-artifact", type=Path, required=True)
    parser.add_argument("--history-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    result = run_channel_containment_audit(
        arguments.coach_artifact,
        arguments.history_manifest,
        arguments.output_root,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
