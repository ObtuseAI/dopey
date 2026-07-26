"""Trade-loss coach: post-close anatomy of the forward walk's CLOSED trades.

WHAT THIS IS (V21 adaptable #2, the honest kernel of the "ratchet trace-replay
optimizer"): a diagnostic that reads trades the forward walk has actually
CLOSED, classifies each loss by its mechanism, aggregates the pattern, and -
when a pattern is strong enough - emits a CANDIDATE HYPOTHESIS formatted for
the foundry / exit-policy-search to test on HELD-OUT eras.

WHAT THIS IS NOT: a self-rewriting loop. It never edits logic, never tunes a
parameter, and its hypotheses carry no weight until they pass the held-out
discipline. Rewriting the system to fit its own recent losers is in-sample
curve-fitting with extra steps - the exact refused half of the idea.

Loss taxonomy (from the walk's own close reasons + entry/exit anatomy):
- theta_bleed        time_stop close with a mild net loss (decay + friction)
- adverse_move_stop  premium_stop close (direction wrong and/or IV collapsed;
                     indistinguishable without exit IV, labeled honestly)
- expired_worthless  expiry settlement at intrinsic zero
- friction_scratch   time_stop close within one commission+spread of flat
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from dopey_options.liquidity_engine import (
    ENTRY_POLICY_VERSION,
    EXIT_POLICY_VERSION,
    FORWARD_EXIT_MAX_RELATIVE_SPREAD,
    forward_entry_liquidity_rejection_reasons,
    forward_exit_quote_rejection_reasons,
    quote_relative_spread,
)
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
HYPOTHESES_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "trade_loss_hypotheses.json"
CHAIN_ROOT = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"

FRICTION_SCRATCH_BAND = 0.08   # |return| under ~spread+commission => scratch
MIN_BUCKET_FOR_HYPOTHESIS = 10  # no pattern claim on fewer closed trades
LOSS_SHARE_FOR_HYPOTHESIS = 0.60

HYPOTHESIS_TEMPLATES: dict[str, dict[str, str]] = {
    "theta_bleed": {
        "hypothesis": "time-stop losses are decay-dominated: holding-period/tenor interaction may be mis-set",
        "testable_via": "exit_policy_walkforward_search grid over max_holding_steps and tenor band, train<=2021 validate>2021, promote only if BOTH eras improve",
    },
    "adverse_move_stop": {
        "hypothesis": "stopped entries were directionally wrong at entry: the emitting family may lack forward information",
        "testable_via": "baseline_arbitration per family (cohort-matched random entries) + foundry rank-IC on the family's feature, held-out eras only",
    },
    "liquidity_hole_stop": {
        "hypothesis": "stop fills were dominated by non-executable or severely dislocated option quotes",
        "testable_via": "forward entry hard filters plus executable-exit quote deferral and quote-quality attribution on every exit",
    },
    "expired_worthless": {
        "hypothesis": "positions rode to zero: force-close / time-stop interaction leaves dead premium on the book",
        "testable_via": "exit_policy_walkforward_search with earlier force-close DTE, both-eras rule",
    },
    "friction_scratch": {
        "hypothesis": "scratches imply signals resolve slower than the holding window: cadence/holding mismatch",
        "testable_via": "foundry horizon sweep on family features (longer forward-return windows), held-out eras",
    },
}


def classify_closed_trade(trade: dict[str, Any]) -> str:
    reason = str(trade.get("exit_reason", trade.get("close_reason", trade.get("reason", ""))))
    trade_return = float(trade.get("trade_return", 0.0))
    if reason == "premium_target" or trade_return > 0:
        return "winner"
    if reason in {"expiry_intrinsic", "expiry_settlement", "force_close_expiry"}:
        return "expired_worthless" if trade_return <= -0.90 else "adverse_move_stop"
    if reason == "premium_stop":
        exit_spread = trade.get("exit_relative_spread")
        if isinstance(exit_spread, (int, float)) and float(exit_spread) > FORWARD_EXIT_MAX_RELATIVE_SPREAD:
            return "liquidity_hole_stop"
        return "adverse_move_stop"
    if reason == "time_stop":
        return "friction_scratch" if abs(trade_return) <= FRICTION_SCRATCH_BAND else "theta_bleed"
    return "other"


def run_trade_loss_coach() -> dict[str, Any]:
    try:
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary = _base("blocked_missing_forward_ledger")
        write_json_atomic(HYPOTHESES_PATH, summary)
        return summary
    closed = list(ledger.get("closed_trades", []))
    if not closed:
        summary = _base("no_closed_trades_yet_coach_waiting")
        write_json_atomic(HYPOTHESES_PATH, summary)
        return summary

    rows: list[dict[str, Any]] = []
    for trade in closed:
        quote_anatomy = _trade_quote_anatomy(trade)
        enriched_trade = {**trade, **quote_anatomy}
        rows.append({
            "position_id": trade.get("position_id"),
            "symbol": trade.get("symbol"),
            "candidate_strategy": trade.get("candidate_strategy"),
            "signal_family": trade.get("signal_family"),
            "close_reason": trade.get("exit_reason", trade.get("close_reason", trade.get("reason"))),
            "trade_return": trade.get("trade_return"),
            "marking_sessions": trade.get("holding_sessions", trade.get("marking_sessions")),
            **quote_anatomy,
            "loss_mode": classify_closed_trade(enriched_trade),
        })
    by_mode: dict[str, int] = {}
    by_family_mode: dict[str, dict[str, int]] = {}
    for row in rows:
        mode = row["loss_mode"]
        by_mode[mode] = by_mode.get(mode, 0) + 1
        family = str(row.get("signal_family", "unknown"))
        by_family_mode.setdefault(family, {})[mode] = by_family_mode.get(family, {}).get(mode, 0) + 1

    losers = [row for row in rows if row["loss_mode"] not in {"winner", "other"}]
    hypotheses: list[dict[str, Any]] = []
    if len(closed) >= MIN_BUCKET_FOR_HYPOTHESIS and losers:
        for mode, template in HYPOTHESIS_TEMPLATES.items():
            mode_count = by_mode.get(mode, 0)
            if mode_count and mode_count / len(losers) >= LOSS_SHARE_FOR_HYPOTHESIS:
                hypotheses.append({
                    "loss_mode": mode,
                    "share_of_losses": round(mode_count / len(losers), 4),
                    "closed_sample": len(closed),
                    **template,
                    "status": "candidate_untested",
                    "weight_until_held_out_pass": 0.0,
                })

    summary = _base("trade_loss_coach_complete")
    summary.update({
        "closed_trades": len(closed),
        "entry_policy_replay_version": ENTRY_POLICY_VERSION,
        "entry_policy_replay_rejected_trade_count": sum(
            1 for row in rows if row.get("entry_policy_rejection_reasons")
        ),
        "entry_policy_replay_is_not_an_outcome_claim": True,
        "exit_policy_replay_version": EXIT_POLICY_VERSION,
        "exit_policy_replay_rejected_trade_count": sum(
            1 for row in rows if row.get("exit_policy_rejection_reasons")
        ),
        "exit_policy_replay_is_not_an_outcome_revision": True,
        "loss_mode_counts": dict(sorted(by_mode.items())),
        "loss_modes_by_family": by_family_mode,
        "hypotheses": hypotheses,
        "hypothesis_gate": {
            "min_closed_sample": MIN_BUCKET_FOR_HYPOTHESIS,
            "min_loss_share": LOSS_SHARE_FOR_HYPOTHESIS,
        },
        "trade_rows": rows,
    })
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(HYPOTHESES_PATH, summary)
    return summary


def _trade_quote_anatomy(trade: dict[str, Any]) -> dict[str, Any]:
    entry_quote = _contract_quote(trade, str(trade.get("entry_date", "")))
    exit_quote = _contract_quote(trade, str(trade.get("exit_date", "")))
    if entry_quote is None or exit_quote is None:
        return {
            "quote_anatomy_status": "missing_contract_quote_snapshot",
            "entry_relative_spread": trade.get("entry_relative_spread"),
            "exit_relative_spread": trade.get("exit_relative_spread"),
        }
    entry_spot = float(entry_quote["underlying_spot"])
    exit_spot = float(exit_quote["underlying_spot"])
    underlying_return = exit_spot / entry_spot - 1.0 if entry_spot > 0.0 else 0.0
    strategy = str(trade.get("candidate_strategy", ""))
    directional_alignment_return = -underlying_return if strategy == "long_put" else underlying_return
    entry_rejection_reasons = forward_entry_liquidity_rejection_reasons(
        float(entry_quote["bid"]),
        float(entry_quote["ask"]),
        int(entry_quote["volume"]),
        int(entry_quote["open_interest"]),
    )
    exit_rejection_reasons = forward_exit_quote_rejection_reasons(
        float(exit_quote["bid"]),
        float(exit_quote["ask"]),
    )
    return {
        "quote_anatomy_status": "complete",
        "entry_policy_rejection_reasons": list(entry_rejection_reasons),
        "entry_volume": int(entry_quote["volume"]),
        "entry_open_interest": int(entry_quote["open_interest"]),
        "entry_relative_spread": round(
            quote_relative_spread(float(entry_quote["bid"]), float(entry_quote["ask"])),
            6,
        ),
        "exit_policy_rejection_reasons": list(exit_rejection_reasons),
        "exit_volume": int(exit_quote["volume"]),
        "exit_open_interest": int(exit_quote["open_interest"]),
        "exit_relative_spread": round(
            quote_relative_spread(float(exit_quote["bid"]), float(exit_quote["ask"])),
            6,
        ),
        "entry_underlying_spot": entry_spot,
        "exit_underlying_spot": exit_spot,
        "underlying_return": round(underlying_return, 6),
        "directional_alignment_return": round(directional_alignment_return, 6),
    }


def _contract_quote(trade: dict[str, Any], snapshot_date: str) -> dict[str, str] | None:
    if not snapshot_date:
        return None
    symbol = str(trade.get("symbol", ""))
    path = CHAIN_ROOT / snapshot_date / f"{symbol}_chain.csv"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        matches = [
            row
            for row in csv.DictReader(handle)
            if str(row.get("expiry", "")) == str(trade.get("expiry", ""))
            and str(row.get("option_type", "")) == str(trade.get("option_type", ""))
            and float(row.get("strike", "nan")) == float(trade.get("strike", 0.0))
        ]
    if len(matches) > 1:
        raise ValueError(f"duplicate contract quote rows: path={path}, position_id={trade.get('position_id')}")
    return matches[0] if matches else None


def _base(status: str) -> dict[str, Any]:
    return {
        "artifact_type": "trade_loss_hypotheses_summary",
        "coach_status": status,
        "evidence_class": "diagnostic_hypotheses_only_zero_weight_until_held_out_pass",
        "not_edge_evidence": True,
        "strategy_promotion_allowed": False,
        "never_edits_logic_or_parameters": True,
        "paper_only": True,
        "live_blocked": True,
    }


if __name__ == "__main__":
    result = run_trade_loss_coach()
    print(json.dumps({k: v for k, v in result.items() if k != "trade_rows"}, indent=2)[:900])
