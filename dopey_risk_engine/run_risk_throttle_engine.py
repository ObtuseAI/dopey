"""Run the paper-only risk throttle engine."""
from __future__ import annotations

import json
from collections import Counter

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .kill_switch_engine import build_kill_switch_records
from .risk_throttle_engine import build_risk_throttle_records


ARTIFACT_DIR = ARTIFACT_ROOT / "risk"
THROTTLES_PATH = ARTIFACT_DIR / "risk_throttle_records.jsonl"
KILL_SWITCH_PATH = ARTIFACT_DIR / "kill_switch_records.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "risk_throttle_summary.json"
PROOF_PATH = ARTIFACT_DIR / "risk_throttle_proof.jsonl"


def run_risk_throttle_engine() -> dict:
    trades = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_trades.jsonl")
    scores = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_strategy_scores.jsonl")
    throttles = build_risk_throttle_records(trades, scores)
    kills = build_kill_switch_records(throttles)
    counts = Counter(record["throttle_type"] for record in throttles)
    summary = {
        "artifact_type": "risk_throttle_summary",
        "risk_throttle_version": "dopey-risk-throttle-v1",
        "risk_throttle_status": "complete" if trades else "blocked_no_trades",
        "risk_throttle_count": len(throttles),
        "kill_switch_count": len(kills),
        "throttle_type_counts": dict(sorted(counts.items())),
        "research_blocked_globally": False,
        "live_capital_at_risk": False,
        "paper_only": True,
        "live_blocked": True,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(THROTTLES_PATH, throttles, False)
    write_jsonl(KILL_SWITCH_PATH, kills, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("risk-throttle-engine", summary["risk_throttle_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "risk_throttle_records": str(THROTTLES_PATH),
        "kill_switch_records": str(KILL_SWITCH_PATH),
        "risk_throttle_summary": str(SUMMARY_PATH),
        "risk_throttle_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_risk_throttle_engine()
    print(json.dumps({
        "risk_throttle_status": summary["risk_throttle_status"],
        "risk_throttle_count": summary["risk_throttle_count"],
        "kill_switch_count": summary["kill_switch_count"],
        "summary_path": summary["artifact_paths"]["risk_throttle_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

