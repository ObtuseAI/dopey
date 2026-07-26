"""Run the paper-money tournament engine."""
from __future__ import annotations

import json

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .paper_money_tournament_engine import simulate_paper_tournament
from .strategy_competition_engine import build_strategy_leaderboard
from .winner_loser_elimination import build_winner_loser_records


ARTIFACT_DIR = ARTIFACT_ROOT / "tournament"
TRADES_PATH = ARTIFACT_DIR / "paper_tournament_trades.jsonl"
SCORES_PATH = ARTIFACT_DIR / "paper_tournament_strategy_scores.jsonl"
LEADERBOARD_PATH = ARTIFACT_DIR / "paper_tournament_leaderboard.jsonl"
PROMOTIONS_PATH = ARTIFACT_DIR / "winner_promotion_records.jsonl"
ELIMINATIONS_PATH = ARTIFACT_DIR / "loser_elimination_records.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "paper_money_tournament_summary.json"
PROOF_PATH = ARTIFACT_DIR / "paper_money_tournament_proof.jsonl"


def run_paper_money_tournament_engine() -> dict:
    candidates = read_jsonl(ARTIFACT_ROOT / "options_engine" / "model_priced_trade_candidates.jsonl")
    trades, scores = simulate_paper_tournament(candidates)
    leaderboard = build_strategy_leaderboard(scores)
    promotions, eliminations = build_winner_loser_records(scores)
    top = leaderboard[0] if leaderboard else {}
    summary = {
        "artifact_type": "paper_money_tournament_summary",
        "paper_tournament_version": "dopey-paper-money-tournament-v1",
        "paper_tournament_status": "complete" if trades else "blocked_no_trade_candidates",
        "paper_tournament_trade_count": len(trades),
        "strategy_score_count": len(scores),
        "leaderboard_count": len(leaderboard),
        "winner_promotion_count": len(promotions),
        "loser_elimination_count": len(eliminations),
        "paper_champion_count": sum(1 for record in promotions if record["promotion_level"] == "paper_champion"),
        "public_data_paper_champion_count": sum(1 for record in promotions if record.get("public_data_paper_champion")),
        "fixture_only_champion_count": sum(1 for record in promotions if record.get("fixture_only_champion")),
        "top_strategy": top.get("strategy_family", ""),
        "top_strategy_net_pnl": top.get("net_paper_pnl", 0.0),
        "top_strategy_market_data_source_type": top.get("market_data_source_type", ""),
        "scoreboard_is_money_first": True,
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(TRADES_PATH, trades, False)
    write_jsonl(SCORES_PATH, scores, False)
    write_jsonl(LEADERBOARD_PATH, leaderboard, False)
    write_jsonl(PROMOTIONS_PATH, promotions, False)
    write_jsonl(ELIMINATIONS_PATH, eliminations, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("paper-money-tournament", summary["paper_tournament_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "paper_tournament_trades": str(TRADES_PATH),
        "paper_tournament_strategy_scores": str(SCORES_PATH),
        "paper_tournament_leaderboard": str(LEADERBOARD_PATH),
        "winner_promotion_records": str(PROMOTIONS_PATH),
        "loser_elimination_records": str(ELIMINATIONS_PATH),
        "paper_money_tournament_summary": str(SUMMARY_PATH),
        "paper_money_tournament_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_paper_money_tournament_engine()
    print(json.dumps({
        "paper_tournament_status": summary["paper_tournament_status"],
        "paper_tournament_trade_count": summary["paper_tournament_trade_count"],
        "top_strategy": summary["top_strategy"],
        "summary_path": summary["artifact_paths"]["paper_money_tournament_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
