"""Adversarial signal panel: bull/bear/risk lenses over each new paper entry.

WHAT THIS IS (V21 adaptable #5, post-admission visibility): after the forward
walk marks and enters, this stage re-reads TODAY'S new entries and attaches a three-lens
adversarial record to each - the bull case (the signal's own claim), the bear
case (every unfavorable context the stack already measures), and the risk desk
view (book concentration, Greeks, the honest Kelly ceiling). The verdict is
RECORDED, not enforced by this post-admission stage. The upstream prospective
entry guard independently enforces equivalent bear/risk verdicts before entry.

WHY record-only: a gate must be EARNED. As closed trades accrue, panel verdicts
join to outcomes; if "would_refuse" entries measurably underperform on held-out
data, the evidence case for enforcement can be made through the normal
discipline. Until then this is bookkeeping for that future test.

Kelly honesty: with the historical lane showing no net edge after costs, the
Kelly-optimal fraction is 0 - the ceiling is stated, and the 1-contract paper
sizing stands OUTSIDE it by design (research needs observations); real sizing
would not be defensible on current evidence. Paper-only, live-blocked.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from dopey_calibration.signal_settlement import (
    calibration_context,
    family_trust_for,
    load_calibration_summary,
)
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_risk_engine.forward_entry_guard import ENTRY_GUARD_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
ENTRY_CONTEXT_PATH = REPO_ROOT / "artifacts" / "dopey" / "market_context" / "entry_context_fusion.jsonl"
MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
BOOK_RISK_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_book_risk" / "forward_book_risk.json"
PANEL_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "adversarial_panel.json"

SYMBOL_PREMIUM_SHARE_LIMIT = 0.25  # mirrors the book-concentration repair line
BEAR_FLAGS_REFUSE = 3
BEAR_FLAGS_REDUCE = 2


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _entry_context_by_symbol() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        for line in ENTRY_CONTEXT_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                rows[str(record.get("symbol", ""))] = record
    except (OSError, json.JSONDecodeError):
        pass
    return rows


def build_panel_record(
    position: dict[str, Any],
    context: dict[str, Any],
    macro: dict[str, Any],
    book: dict[str, Any],
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(position.get("symbol", ""))
    side = "call" if str(position.get("candidate_strategy", "")) == "long_call" else "put"
    bias_key = f"long_{side}_entry_bias"

    # BULL lens - the signal's own case, stated plainly.
    signal_age_days = None
    try:
        signal_age_days = (date.fromisoformat(str(position["entry_date"])) - date.fromisoformat(str(position["signal_date"]))).days
    except (KeyError, ValueError):
        pass
    bull = {
        "signal_family": position.get("signal_family"),
        "signal_age_calendar_days": signal_age_days,
        "entry_bias_for_side": context.get(bias_key, "unknown"),
        "sector_regime": context.get("sector_regime", "unknown"),
    }

    # BEAR lens - every unfavorable context the stack already measures.
    attention = macro.get("attention", {}) if isinstance(macro.get("attention"), dict) else {}
    crowded = {str(s) for s in attention.get("crowded_symbols", [])}
    congress = macro.get("congress", {}) if isinstance(macro.get("congress"), dict) else {}
    notable_selling = {str(s) for s in congress.get("notable_selling", [])}
    vol_ts = macro.get("vol_term_structure", {}) if isinstance(macro.get("vol_term_structure"), dict) else {}
    bear_flags: list[str] = []
    if bool(context.get("earnings_blackout")):
        bear_flags.append("earnings_blackout_window")
    if str(context.get("gamma_regime", "")).startswith("short_gamma"):
        bear_flags.append("dealer_short_gamma_amplifying")
    if str(context.get("crowd_state", "")) == "crowded" or symbol in crowded:
        bear_flags.append("crowded_attention")
    if str(context.get(bias_key, "")) == "unfavorable":
        bear_flags.append("fusion_bias_unfavorable_for_side")
    if bool(context.get("surface_tear_present")):
        bear_flags.append("vol_surface_tear")
    if str(vol_ts.get("state", "")) == "backwardation":
        bear_flags.append("vix_term_backwardation")
    if symbol in notable_selling:
        bear_flags.append("congress_notable_selling")
    fundamentals = macro.get("fundamentals", {}) if isinstance(macro.get("fundamentals"), dict) else {}
    if symbol in set(fundamentals.get("short_candidate_flags", [])):
        # valuation-excess screen: bearish for the name; for a long CALL entry
        # it is a red flag, for a long PUT it is the thesis - flag either way,
        # the record keeps the side so the join can split them later
        bear_flags.append("speculative_excess_fundamentals")

    # RISK lens - the book as it stands.
    premium_by_symbol = book.get("premium_at_risk_by_symbol", {}) if isinstance(book.get("premium_at_risk_by_symbol"), dict) else {}
    total_premium = sum(float(v) for v in premium_by_symbol.values()) or 1.0
    symbol_share = float(premium_by_symbol.get(symbol, 0.0)) / total_premium
    greeks = book.get("book_dollar_greeks", {}) if isinstance(book.get("book_dollar_greeks"), dict) else {}
    risk_flags: list[str] = []
    if symbol_share > SYMBOL_PREMIUM_SHARE_LIMIT:
        risk_flags.append(f"symbol_premium_share_{symbol_share:.2f}_exceeds_{SYMBOL_PREMIUM_SHARE_LIMIT}")
    risk = {
        "symbol_premium_share": round(symbol_share, 4),
        "book_dollar_delta": greeks.get("delta_dollars"),
        "book_dollar_vega": greeks.get("vega_dollars"),
        "risk_flags": risk_flags,
        "kelly_ceiling": {
            "historical_edge_after_costs": "none_demonstrated",
            "kelly_fraction_ceiling": 0.0,
            "note": "1-contract paper sizing stands outside the ceiling for research observation only",
        },
    }

    # VERDICT - bear + risk flags ONLY. The calibration lens below is advisory
    # and is deliberately NOT read here: a gate must be earned on held-out
    # evidence, and contested-truth trust is recorded, never enforced.
    if len(bear_flags) >= BEAR_FLAGS_REFUSE or "earnings_blackout_window" in bear_flags or risk_flags:
        verdict = "would_refuse"
    elif len(bear_flags) >= BEAR_FLAGS_REDUCE:
        verdict = "would_reduce"
    else:
        verdict = "would_proceed"

    # CALIBRATION lens - the contested-truth reality check the bull case must
    # beat (phantom-settlement trust for this signal family). Advisory-only:
    # it colors the record for the future held-out enforcement test but moves
    # neither the verdict nor sizing today. Uncalibrated families read 'unrated'.
    family = str(position.get("signal_family", "") or "unknown")
    calibration_lens = family_trust_for(family, calibration)
    calibration_lens["lens_role"] = "contested_truth_advisory_recorded_never_enforced"
    calibration_lens["does_not_affect_verdict"] = True

    return {
        "position_id": position.get("position_id"),
        "symbol": symbol,
        "candidate_strategy": position.get("candidate_strategy"),
        "entry_date": position.get("entry_date"),
        "signal_family": family,
        "bull_lens": bull,
        "calibration_lens": calibration_lens,
        "bear_lens": {"flags": bear_flags, "flag_count": len(bear_flags)},
        "risk_lens": risk,
        "panel_verdict_recorded_not_enforced": verdict,
        "prospective_entry_guard_enforced_upstream": True,
        "prospective_entry_guard_version": ENTRY_GUARD_VERSION,
    }


def run_adversarial_signal_panel() -> dict[str, Any]:
    ledger = _load_json(LEDGER_PATH)
    if not ledger:
        summary = _base("blocked_missing_forward_ledger")
        write_json_atomic(PANEL_PATH, summary)
        return summary
    last_entry_date = str(ledger.get("last_entry_date", ""))
    new_entries = [
        position for position in ledger.get("open_positions", [])
        if str(position.get("entry_date", "")) == last_entry_date
    ]
    if not new_entries:
        summary = _base("no_new_entries_panel_idle")
        summary["last_entry_date"] = last_entry_date
        write_json_atomic(PANEL_PATH, summary)
        return summary
    context_by_symbol = _entry_context_by_symbol()
    macro = _load_json(MACRO_SUMMARY_PATH)
    book = _load_json(BOOK_RISK_PATH)
    calibration = load_calibration_summary()  # read the phantom lane once, reuse per record
    records = [
        build_panel_record(position, context_by_symbol.get(str(position.get("symbol", "")), {}), macro, book, calibration)
        for position in new_entries
    ]
    verdicts = [record["panel_verdict_recorded_not_enforced"] for record in records]
    summary = _base("adversarial_panel_recorded")
    summary.update({
        "entry_date": last_entry_date,
        "entries_reviewed": len(records),
        "verdict_counts": {v: verdicts.count(v) for v in sorted(set(verdicts))},
        "calibration_context": calibration_context(calibration),
        "records": records,
    })
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(PANEL_PATH, summary)
    return summary


def _base(status: str) -> dict[str, Any]:
    return {
        "artifact_type": "adversarial_signal_panel_summary",
        "panel_status": status,
        "evidence_class": "visibility_only_recorded_never_enforced",
        "not_edge_evidence": True,
        "strategy_promotion_allowed": False,
        "entries_never_blocked_or_resized_by_this_stage": True,
        "prospective_entry_guard_enforced_upstream": True,
        "prospective_entry_guard_version": ENTRY_GUARD_VERSION,
        "enforcement_requires": "held_out_evidence_that_refused_entries_underperform",
        "paper_only": True,
        "live_blocked": True,
    }


if __name__ == "__main__":
    result = run_adversarial_signal_panel()
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))
