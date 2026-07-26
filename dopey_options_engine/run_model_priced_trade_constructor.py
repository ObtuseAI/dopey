"""Run the model-priced trade constructor."""
from __future__ import annotations

import json
from collections import Counter

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .model_priced_trade_constructor import construct_model_priced_trades


ARTIFACT_DIR = ARTIFACT_ROOT / "options_engine"
CANDIDATES_PATH = ARTIFACT_DIR / "model_priced_trade_candidates.jsonl"
SELECTION_PATH = ARTIFACT_DIR / "option_selection_proxy_records.jsonl"
GREEKS_PATH = ARTIFACT_DIR / "model_priced_greeks_proxy_records.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "model_priced_trade_constructor_summary.json"
PROOF_PATH = ARTIFACT_DIR / "model_priced_trade_constructor_proof.jsonl"


def run_model_priced_trade_constructor() -> dict:
    signals = read_jsonl(ARTIFACT_ROOT / "signals" / "aggressive_signal_candidates.jsonl")
    rankings = read_jsonl(ARTIFACT_ROOT / "signals" / "signal_quality_rankings.jsonl")
    features = read_jsonl(ARTIFACT_ROOT / "chart_vision" / "chart_feature_records.jsonl")
    features_by_symbol: dict[str, dict] = {}
    for feature in features:
        features_by_symbol[str(feature["symbol"])] = feature
    rankings_by_signal = {str(record["signal_id"]): record for record in rankings}
    candidates, selection_records, greeks_records = construct_model_priced_trades(signals, features_by_symbol, rankings_by_signal)
    counts = Counter(candidate["trade_intent"] for candidate in candidates)
    invalid_structures = [
        candidate for candidate in candidates
        if candidate["trade_intent"] not in {"long_call", "long_put", "no_trade"} or candidate["option_side"] not in {"call", "put", "none"}
    ]
    summary = {
        "artifact_type": "model_priced_trade_constructor_summary",
        "model_priced_trade_constructor_version": "dopey-model-priced-trade-constructor-v1",
        "model_priced_options_status": "candidates_generated" if candidates else "blocked_no_signals",
        "option_trade_candidate_count": len(candidates),
        "long_call_candidate_count": int(counts.get("long_call", 0)),
        "long_put_candidate_count": int(counts.get("long_put", 0)),
        "no_trade_count": int(counts.get("no_trade", 0)),
        "paper_trade_allowed_count": sum(1 for candidate in candidates if candidate.get("paper_trade_allowed")),
        "quote_priced": False,
        "model_priced": True,
        "unsupported_structure_count": len(invalid_structures),
        "naked_selling_allowed": False,
        "spreads_allowed": False,
        "short_vol_allowed": False,
        "undefined_risk_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(CANDIDATES_PATH, candidates, False)
    write_jsonl(SELECTION_PATH, selection_records, False)
    write_jsonl(GREEKS_PATH, greeks_records, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("model-priced-trade-constructor", summary["model_priced_options_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "model_priced_trade_candidates": str(CANDIDATES_PATH),
        "option_selection_proxy_records": str(SELECTION_PATH),
        "model_priced_greeks_proxy_records": str(GREEKS_PATH),
        "model_priced_trade_constructor_summary": str(SUMMARY_PATH),
        "model_priced_trade_constructor_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_model_priced_trade_constructor()
    print(json.dumps({
        "model_priced_options_status": summary["model_priced_options_status"],
        "option_trade_candidate_count": summary["option_trade_candidate_count"],
        "paper_trade_allowed_count": summary["paper_trade_allowed_count"],
        "summary_path": summary["artifact_paths"]["model_priced_trade_constructor_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

