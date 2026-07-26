"""Run the disabled live-gate status writer."""
from __future__ import annotations

import json

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_json, write_json, write_jsonl

from .live_gate_status import build_live_gate_status


ARTIFACT_DIR = ARTIFACT_ROOT / "live_gate"
STATUS_PATH = ARTIFACT_DIR / "live_gate_status.json"
BLOCKERS_PATH = ARTIFACT_DIR / "live_gate_blockers.jsonl"
PROOF_PATH = ARTIFACT_DIR / "live_gate_proof.jsonl"


def run_live_gate_status() -> dict:
    evolution = read_json(ARTIFACT_ROOT / "evolution" / "evolution_loop_summary.json")
    status, blockers = build_live_gate_status(evolution)
    write_json(STATUS_PATH, status)
    write_jsonl(BLOCKERS_PATH, blockers, False)
    write_jsonl(PROOF_PATH, [proof_record("live-gate-status", status["live_gate_status"], status)], False)
    return {**status, "blocker_count": len(blockers), "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "live_gate_status": str(STATUS_PATH),
        "live_gate_blockers": str(BLOCKERS_PATH),
        "live_gate_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_live_gate_status()
    print(json.dumps({
        "live_gate_status": summary["live_gate_status"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "broker_connection_enabled": summary["broker_connection_enabled"],
        "summary_path": summary["artifact_paths"]["live_gate_status"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
