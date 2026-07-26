"""Run autonomous signal, strategy, and long-premium research engine."""
from __future__ import annotations

import json
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_json, safety_state, stable_hash, write_json, write_jsonl
from dopey_data_ingestion.autonomous_open_data_validator_bridge import SUMMARY_PATH as BRIDGE_SUMMARY_PATH
from dopey_options_autonomy.open_options_data_autonomy_plan import SUMMARY_PATH as OPTIONS_SUMMARY_PATH

from .autonomous_long_premium_options_research import build_long_premium_option_intents
from .autonomous_signal_factory import build_autonomous_signal_candidates
from .autonomous_strategy_search import build_autonomous_strategy_candidates


ARTIFACT_DIR = ARTIFACT_ROOT / "research_autonomy"
SIGNALS_PATH = ARTIFACT_DIR / "autonomous_signal_candidates.jsonl"
STRATEGIES_PATH = ARTIFACT_DIR / "autonomous_strategy_candidates.jsonl"
INTENTS_PATH = ARTIFACT_DIR / "autonomous_long_premium_option_intents.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_research_engine_summary.json"
PROOF_PATH = ARTIFACT_DIR / "autonomous_research_engine_proof.jsonl"


def run_autonomous_research_engine() -> dict[str, Any]:
    bridge = read_json(BRIDGE_SUMMARY_PATH)
    options = read_json(OPTIONS_SUMMARY_PATH)
    valid_real_dataset = bool(bridge.get("valid_real_dataset", False))
    quote_priced = bool(options.get("quote_priced_backtest_allowed", False))
    signals = build_autonomous_signal_candidates(valid_real_dataset)
    strategies = build_autonomous_strategy_candidates(signals)
    intents = build_long_premium_option_intents(strategies, quote_priced)
    summary = {
        "artifact_type": "autonomous_research_engine_summary",
        "research_engine_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "research_status": "research_candidates_generated" if valid_real_dataset else "blocked_no_accepted_real_data",
        "signal_candidate_count": len(signals),
        "strategy_candidate_count": len(strategies),
        "intent_count": len(intents),
        "long_call_count": sum(1 for record in intents if record["intent"] == "long_call"),
        "long_put_count": sum(1 for record in intents if record["intent"] == "long_put"),
        "no_trade_count": sum(1 for record in intents if record["intent"] == "no_trade"),
        "valid_real_dataset": valid_real_dataset,
        "quote_priced_backtest_allowed": quote_priced,
        "model_priced_research_allowed": not quote_priced,
        "real_options_evidence": quote_priced,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(SIGNALS_PATH, signals)
    write_jsonl(STRATEGIES_PATH, strategies)
    write_jsonl(INTENTS_PATH, intents)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-research-engine-proof-v1", summary["research_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_signal_candidates": str(SIGNALS_PATH),
        "autonomous_strategy_candidates": str(STRATEGIES_PATH),
        "autonomous_long_premium_option_intents": str(INTENTS_PATH),
        "autonomous_research_engine_summary": str(SUMMARY_PATH),
        "autonomous_research_engine_proof": str(PROOF_PATH),
    }


def main() -> int:
    result = run_autonomous_research_engine()
    print(json.dumps({
        "research_status": result["research_status"],
        "strategy_candidate_count": result["strategy_candidate_count"],
        "no_trade_count": result["no_trade_count"],
        "summary_path": result["artifact_paths"]["autonomous_research_engine_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

