"""Run the P&L scoreboard and performance cockpit."""
from __future__ import annotations

import json

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .performance_cockpit import render_performance_cockpit
from .pnl_scoreboard import build_pnl_scoreboard


ARTIFACT_DIR = ARTIFACT_ROOT / "scoreboard"
SUMMARY_PATH = ARTIFACT_DIR / "pnl_scoreboard_summary.json"
CSV_PATH = ARTIFACT_DIR / "pnl_scoreboard_strategy_rows.csv"
HTML_PATH = ARTIFACT_DIR / "performance_cockpit.html"
MD_PATH = ARTIFACT_DIR / "performance_cockpit.md"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "scoreboard_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "scoreboard_proof.jsonl"


def run_performance_cockpit() -> dict:
    trades = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_trades.jsonl")
    scores = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_strategy_scores.jsonl")
    promotions = read_jsonl(ARTIFACT_ROOT / "tournament" / "winner_promotion_records.jsonl")
    eliminations = read_jsonl(ARTIFACT_ROOT / "tournament" / "loser_elimination_records.jsonl")
    summary = build_pnl_scoreboard(trades, scores, promotions, eliminations, CSV_PATH)
    render_performance_cockpit(summary, MD_PATH, HTML_PATH)
    quality_flags = []
    if not scores:
        quality_flags.append({"artifact_type": "scoreboard_quality_flag", "flag_id": "missing-scores", "severity": "warning", "message": "no tournament scores loaded"})
    for record in quality_flags:
        record["flag_hash"] = stable_hash(record)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(QUALITY_FLAGS_PATH, quality_flags, False)
    write_jsonl(PROOF_PATH, [proof_record("pnl-scoreboard", summary["pnl_scoreboard_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "pnl_scoreboard_summary": str(SUMMARY_PATH),
        "pnl_scoreboard_strategy_rows": str(CSV_PATH),
        "performance_cockpit_html": str(HTML_PATH),
        "performance_cockpit_markdown": str(MD_PATH),
        "scoreboard_quality_flags": str(QUALITY_FLAGS_PATH),
        "scoreboard_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_performance_cockpit()
    print(json.dumps({
        "pnl_scoreboard_status": summary["pnl_scoreboard_status"],
        "top_strategy": summary["top_strategies_by_net_pnl"][0]["strategy_family"] if summary["top_strategies_by_net_pnl"] else "",
        "summary_path": summary["artifact_paths"]["pnl_scoreboard_summary"],
        "html_path": summary["artifact_paths"]["performance_cockpit_html"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

