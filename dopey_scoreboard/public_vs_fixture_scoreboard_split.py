"""Separate public-data and fixture-fallback paper scoreboards."""
from __future__ import annotations

from collections import defaultdict

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "scoreboard"
SUMMARY_PATH = ARTIFACT_DIR / "public_vs_fixture_scoreboard_split.json"
PUBLIC_SCORES_PATH = ARTIFACT_DIR / "public_data_strategy_scores.jsonl"
FIXTURE_SCORES_PATH = ARTIFACT_DIR / "fixture_fallback_strategy_scores.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "scoreboard_split_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "scoreboard_split_proof.jsonl"


def run_public_vs_fixture_scoreboard_split() -> dict:
    scores = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_strategy_scores.jsonl")
    trades = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_trades.jsonl")
    public_scores = [score for score in scores if str(score.get("market_data_source_type", "")).startswith("public")]
    fixture_scores = [score for score in scores if score.get("market_data_source_type", "fixture_fallback") == "fixture_fallback"]
    public_trades = [trade for trade in trades if str(trade.get("market_data_source_type", "")).startswith("public")]
    fixture_trades = [trade for trade in trades if trade.get("market_data_source_type", "fixture_fallback") == "fixture_fallback"]
    flags = []
    if public_scores and fixture_scores:
        flags.append(_flag("mixed-score-sources-present", "note", "public and fixture results are present and split"))
    if not public_scores:
        flags.append(_flag("no-public-score-source", "warning", "no public-data strategy scores were found"))
    summary = {
        "artifact_type": "public_vs_fixture_scoreboard_split",
        "scoreboard_split_version": "dopey-public-vs-fixture-scoreboard-split-v2",
        "scoreboard_split_status": "complete",
        "public_data_primary": bool(public_scores),
        "public_strategy_score_count": len(public_scores),
        "fixture_strategy_score_count": len(fixture_scores),
        "public_trade_count": len(public_trades),
        "fixture_trade_count": len(fixture_trades),
        "public_data_top_strategies": _top_rows(public_scores),
        "fixture_fallback_top_strategies": _top_rows(fixture_scores),
        "public_data_symbol_pnl": _symbol_pnl(public_trades),
        "fixture_fallback_symbol_pnl": _symbol_pnl(fixture_trades),
        "merged_without_labels": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PUBLIC_SCORES_PATH, public_scores, False)
    write_jsonl(FIXTURE_SCORES_PATH, fixture_scores, False)
    write_jsonl(QUALITY_FLAGS_PATH, flags, False)
    write_jsonl(PROOF_PATH, [proof_record("public-vs-fixture-scoreboard-split", "complete", summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def _top_rows(scores: list[dict]) -> list[dict]:
    return sorted(scores, key=lambda score: float(score.get("net_paper_pnl", 0.0)), reverse=True)[:5]


def _symbol_pnl(trades: list[dict]) -> list[dict]:
    values: dict[str, float] = defaultdict(float)
    for trade in trades:
        values[str(trade["underlying_symbol"])] += float(trade["paper_pnl"])
    return [
        {"symbol": symbol, "paper_pnl": round(value, 4)}
        for symbol, value in sorted(values.items(), key=lambda item: item[1], reverse=True)[:10]
    ]


def _flag(flag_id: str, severity: str, message: str) -> dict:
    record = {"artifact_type": "scoreboard_split_quality_flag", "flag_id": flag_id, "severity": severity, "message": message}
    record["flag_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "public_vs_fixture_scoreboard_split": str(SUMMARY_PATH),
        "public_data_strategy_scores": str(PUBLIC_SCORES_PATH),
        "fixture_fallback_strategy_scores": str(FIXTURE_SCORES_PATH),
        "scoreboard_split_quality_flags": str(QUALITY_FLAGS_PATH),
        "scoreboard_split_proof": str(PROOF_PATH),
    }
