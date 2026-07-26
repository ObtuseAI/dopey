"""Adversarial stress engine: red-team the live forward-walk book.

Runs deterministic worst-case scenarios against every OPEN forward-walk
position before reality does: underlying gaps (+/-5%, +/-10%), IV shocks
(-50% crush, +100% spike), liquidity holes (spread widening to 3x on exit),
and combined black-swan composites. Positions are repriced with the
Black-Scholes engine at shocked spot/IV, exits pay the widened spread.

Outputs a per-position worst case, a book-level survival verdict, and repair
items when concentration or worst-case loss breaches limits - forcing the
entry policy to evolve against synthetic disasters instead of live ones.
A failure to survive is recorded, never smoothed. Paper-only, live-blocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from dopey_options.chain_snapshot_loader import load_latest_chain_snapshot
from dopey_options.option_pricing_models import (
    MODEL_REPRICING_VERSION,
    option_pricing_input,
    price_european_option,
)
from dopey_options.risk_free_rate import resolve_risk_free_rate
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
)
STRESS_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "adversarial_stress"
STRESS_RESULTS_PATH = STRESS_ARTIFACT_DIR / "adversarial_stress_results.jsonl"
STRESS_SUMMARY_PATH = STRESS_ARTIFACT_DIR / "adversarial_stress_summary.json"
STRESS_REPAIR_PATH = STRESS_ARTIFACT_DIR / "adversarial_stress_repair_items.jsonl"

SPREAD_WIDENING_FACTOR = 3.0
BASE_HALF_SPREAD_PCT = 0.025
BOOK_WORST_CASE_LIMIT_PCT = 0.60  # worst-case loss must not exceed 60% of book premium
SINGLE_NAME_CONCENTRATION_LIMIT = 0.25
STRESS_POLICY_VERSION = "dopey-adversarial-stress-policy-v2"


class ForwardBookBinding(TypedDict):
    source_forward_book_position_count: int
    source_forward_book_position_ids_hash: str
    source_forward_book_snapshot_hash: str


class QuoteSnapshotBinding(TypedDict):
    source_quote_snapshot_status: str
    source_quote_snapshot_date: str
    source_quote_snapshot_hash: str
    source_quote_matched_contract_count: int
    source_quote_fallback_contract_count: int


class StressPolicyBinding(TypedDict):
    stress_policy_version: str
    stress_policy_hash: str
    stress_pricing_model_version: str
    stress_risk_free_rate: float
    stress_risk_free_rate_source: str


SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "scenario_id": "gap_down_5",
        "spot_shock": -0.05,
        "iv_shock": 0.25,
        "liquidity_hole": False,
    },
    {
        "scenario_id": "gap_up_5",
        "spot_shock": 0.05,
        "iv_shock": 0.10,
        "liquidity_hole": False,
    },
    {
        "scenario_id": "gap_down_10_vol_spike",
        "spot_shock": -0.10,
        "iv_shock": 1.00,
        "liquidity_hole": True,
    },
    {
        "scenario_id": "gap_up_10",
        "spot_shock": 0.10,
        "iv_shock": 0.20,
        "liquidity_hole": False,
    },
    {
        "scenario_id": "iv_crush_50",
        "spot_shock": 0.0,
        "iv_shock": -0.50,
        "liquidity_hole": False,
    },
    {
        "scenario_id": "flash_liquidity_hole",
        "spot_shock": -0.03,
        "iv_shock": 0.30,
        "liquidity_hole": True,
    },
    {
        "scenario_id": "black_swan_composite",
        "spot_shock": -0.15,
        "iv_shock": 1.50,
        "liquidity_hole": True,
    },
)


def build_stress_policy_binding() -> StressPolicyBinding:
    """Bind stress evidence to the exact deterministic valuation policy."""
    risk_free_rate, risk_free_source = resolve_risk_free_rate()
    policy = {
        "stress_policy_version": STRESS_POLICY_VERSION,
        "pricing_model_version": MODEL_REPRICING_VERSION,
        "scenarios": list(SCENARIOS),
        "spread_widening_factor": SPREAD_WIDENING_FACTOR,
        "base_half_spread_pct": BASE_HALF_SPREAD_PCT,
        "book_worst_case_limit_pct": BOOK_WORST_CASE_LIMIT_PCT,
        "single_name_concentration_limit": SINGLE_NAME_CONCENTRATION_LIMIT,
    }
    return {
        "stress_policy_version": STRESS_POLICY_VERSION,
        "stress_policy_hash": reproducibility_hash(policy),
        "stress_pricing_model_version": MODEL_REPRICING_VERSION,
        "stress_risk_free_rate": risk_free_rate,
        "stress_risk_free_rate_source": risk_free_source,
    }


def build_forward_book_binding(
    positions: list[dict[str, Any]],
) -> ForwardBookBinding:
    """Bind derived risk evidence to one exact, order-independent forward book."""
    normalized_positions = sorted(
        (dict(position) for position in positions),
        key=lambda position: (
            str(position.get("position_id", "")),
            reproducibility_hash(position),
        ),
    )
    position_ids = [
        str(position.get("position_id", "")) for position in normalized_positions
    ]
    return {
        "source_forward_book_position_count": len(normalized_positions),
        "source_forward_book_position_ids_hash": reproducibility_hash(
            {"position_ids": position_ids}
        ),
        "source_forward_book_snapshot_hash": reproducibility_hash(
            {"open_positions": normalized_positions}
        ),
    }


def _contract_key(
    record: dict[str, Any],
) -> tuple[str, str, str, float] | None:
    symbol = record.get("symbol")
    expiry = record.get("expiry")
    option_type = record.get("option_type")
    strike = record.get("strike")
    if not all(
        isinstance(value, str) and value for value in (symbol, expiry, option_type)
    ):
        return None
    try:
        strike_value = float(strike)
    except (TypeError, ValueError):
        return None
    return symbol, expiry, option_type, strike_value


def _unavailable_quote_snapshot(error: Exception) -> dict[str, Any]:
    return {
        "chain_snapshot_status": f"unavailable_{type(error).__name__}",
        "snapshot_date": "",
        "files_loaded": 0,
        "row_count": 0,
        "symbols": [],
        "reason_codes": [f"quote_snapshot_load_error:{type(error).__name__}"],
        "rows": [],
        "quote_derived": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _load_current_quote_snapshot() -> dict[str, Any]:
    try:
        return load_latest_chain_snapshot()
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        return _unavailable_quote_snapshot(error)


def _quote_snapshot_binding(
    snapshot: dict[str, Any],
    positions: list[dict[str, Any]],
) -> QuoteSnapshotBinding:
    if not positions:
        empty_binding = {"source_quote_snapshot_status": "not_required_empty_book"}
        return {
            "source_quote_snapshot_status": "not_required_empty_book",
            "source_quote_snapshot_date": "",
            "source_quote_snapshot_hash": reproducibility_hash(empty_binding),
            "source_quote_matched_contract_count": 0,
            "source_quote_fallback_contract_count": 0,
        }
    status = str(snapshot.get("chain_snapshot_status", "unverified"))
    rows_value = snapshot.get("rows")
    rows = (
        [dict(row) for row in rows_value if isinstance(row, dict)]
        if isinstance(rows_value, list)
        else []
    )
    snapshot_evidence = {
        "chain_snapshot_status": status,
        "snapshot_date": str(snapshot.get("snapshot_date", "")),
        "files_loaded": snapshot.get("files_loaded"),
        "row_count": snapshot.get("row_count"),
        "symbols": snapshot.get("symbols"),
        "reason_codes": snapshot.get("reason_codes"),
        "rows": rows,
        "quote_derived": snapshot.get("quote_derived"),
        "paper_only": snapshot.get("paper_only"),
        "live_blocked": snapshot.get("live_blocked"),
    }
    available_contracts = {
        key for row in rows if (key := _contract_key(row)) is not None
    }
    matched_count = sum(
        1
        for position in positions
        if (
            (position_key := _contract_key(position)) is not None
            and position_key in available_contracts
        )
    )
    return {
        "source_quote_snapshot_status": status,
        "source_quote_snapshot_date": str(snapshot.get("snapshot_date", "")),
        "source_quote_snapshot_hash": reproducibility_hash(snapshot_evidence),
        "source_quote_matched_contract_count": matched_count,
        "source_quote_fallback_contract_count": len(positions) - matched_count,
    }


def build_current_quote_snapshot_binding(
    positions: list[dict[str, Any]],
) -> QuoteSnapshotBinding:
    """Build the current read-only quote binding for readiness comparison."""
    return _quote_snapshot_binding(_load_current_quote_snapshot(), positions)


def stress_summary_integrity_valid(summary: dict[str, Any]) -> bool:
    """Verify a stress summary's hash and immutable paper-only boundary."""
    claimed_hash = summary.get("reproducibility_hash")
    unhashed = dict(summary)
    unhashed.pop("reproducibility_hash", None)
    return (
        summary.get("artifact_type") == "adversarial_stress_summary"
        and summary.get("paper_only") is True
        and summary.get("live_blocked") is True
        and isinstance(claimed_hash, str)
        and bool(claimed_hash)
        and reproducibility_hash(unhashed) == claimed_hash
    )


def stress_summary_matches_forward_book(
    summary: dict[str, Any],
    positions: list[dict[str, Any]],
) -> bool:
    binding = build_forward_book_binding(positions)
    return all(summary.get(key) == value for key, value in binding.items())


def stress_summary_matches_current_policy(summary: dict[str, Any]) -> bool:
    binding = build_stress_policy_binding()
    return all(summary.get(key) == value for key, value in binding.items())


def stress_summary_has_complete_quotes(
    summary: dict[str, Any],
    positions: list[dict[str, Any]],
) -> bool:
    if not positions:
        return (
            summary.get("source_quote_snapshot_status") == "not_required_empty_book"
            and summary.get("source_quote_matched_contract_count") == 0
            and summary.get("source_quote_fallback_contract_count") == 0
        )
    return (
        summary.get("source_quote_snapshot_status") == "real_chain_snapshot_validated"
        and summary.get("source_quote_matched_contract_count") == len(positions)
        and summary.get("source_quote_fallback_contract_count") == 0
    )


def run_adversarial_stress_engine() -> dict[str, Any]:
    ledger = _load_ledger()
    positions = ledger.get("open_positions", [])
    summary, results, repair_items = _stress_book(positions)
    STRESS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(STRESS_RESULTS_PATH, results)
    _write_jsonl(STRESS_REPAIR_PATH, repair_items)
    _write_json(STRESS_SUMMARY_PATH, summary)
    return summary


def compute_book_stress(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Stress the given open book in-process and return a fresh summary.

    Entry-time callers must never depend on yesterday's artifact: a stress
    summary whose open_position_count mismatches the current book fails the
    entry guard, so evidence is computed at the decision point instead.
    Input positions are deep-copied; quote enrichment never leaks back into
    the caller's ledger.
    """
    import copy

    summary, _results, _repair_items = _stress_book(copy.deepcopy(list(positions)))
    return summary


def _stress_book(
    positions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    forward_book_binding = build_forward_book_binding(positions)
    quote_snapshot_binding = _enrich_with_current_quotes(positions)
    stress_policy_binding = build_stress_policy_binding()
    stress_risk_free_rate = stress_policy_binding["stress_risk_free_rate"]
    if not positions:
        summary = {
            "artifact_type": "adversarial_stress_summary",
            "stress_status": "no_open_positions_book_trivially_survives",
            "scenario_stress_green": True,
            "concentration_green": True,
            "open_position_count": 0,
            "paper_only": True,
            "live_blocked": True,
            **forward_book_binding,
            **quote_snapshot_binding,
            **stress_policy_binding,
        }
        summary["reproducibility_hash"] = reproducibility_hash(summary)
        return summary, [], []
    results: list[dict[str, Any]] = []
    book_entry_premium = sum(float(position["entry_fill"]) for position in positions)
    scenario_book_pnl: dict[str, float] = {}
    for scenario in SCENARIOS:
        book_pnl = 0.0
        for position in positions:
            shocked_value = _shocked_exit_value(
                position,
                scenario,
                stress_risk_free_rate,
            )
            pnl = shocked_value - float(position["entry_fill"])
            book_pnl += pnl
            results.append(
                {
                    "artifact_type": "adversarial_stress_result",
                    "scenario_id": scenario["scenario_id"],
                    "position_id": position["position_id"],
                    "symbol": position["symbol"],
                    "option_type": position["option_type"],
                    "strike": position["strike"],
                    "entry_fill": position["entry_fill"],
                    "shocked_exit_value": round(shocked_value, 6),
                    "shocked_pnl": round(pnl, 6),
                    "spot_shock": scenario["spot_shock"],
                    "iv_shock": scenario["iv_shock"],
                    "liquidity_hole": scenario["liquidity_hole"],
                    "paper_only": True,
                    "live_blocked": True,
                }
            )
        scenario_book_pnl[scenario["scenario_id"]] = round(book_pnl, 6)
    worst_scenario = min(scenario_book_pnl, key=scenario_book_pnl.get)
    worst_pnl = min(
        scenario_book_pnl[worst_scenario], 0.0
    )  # only losses count against the limit
    worst_pct_of_book = (
        abs(worst_pnl) / book_entry_premium if book_entry_premium > 0 else 0.0
    )
    concentration = _max_symbol_concentration(positions, book_entry_premium)
    repair_items: list[dict[str, Any]] = []
    if worst_pct_of_book > BOOK_WORST_CASE_LIMIT_PCT:
        repair_items.append(
            _repair(
                "worst_case_loss_limit_breach",
                f"scenario {worst_scenario} loses {worst_pct_of_book:.1%} of book premium (> {BOOK_WORST_CASE_LIMIT_PCT:.0%})",
                "reduce max concurrent positions or per-name sizing in forward walk entry policy",
            )
        )
    if concentration["share"] > SINGLE_NAME_CONCENTRATION_LIMIT:
        repair_items.append(
            _repair(
                "single_name_concentration_breach",
                f"{concentration['symbol']} holds {concentration['share']:.1%} of book premium (> {SINGLE_NAME_CONCENTRATION_LIMIT:.0%})",
                "cap per-symbol premium share at entry time",
            )
        )
    scenario_stress_green = worst_pct_of_book <= BOOK_WORST_CASE_LIMIT_PCT
    concentration_green = concentration["share"] <= SINGLE_NAME_CONCENTRATION_LIMIT
    survival = (
        "book_survives_all_scenarios"
        if scenario_stress_green and concentration_green
        else "book_vulnerable_repair_required"
    )
    summary = {
        "artifact_type": "adversarial_stress_summary",
        "stress_status": survival,
        "open_position_count": len(positions),
        "book_entry_premium_units": round(book_entry_premium, 6),
        "scenario_book_pnl": scenario_book_pnl,
        "worst_scenario": worst_scenario,
        "worst_book_pnl": worst_pnl,
        "worst_pct_of_book_premium": round(worst_pct_of_book, 6),
        "scenario_stress_green": scenario_stress_green,
        "max_single_name_share": round(concentration["share"], 6),
        "max_single_name_symbol": concentration["symbol"],
        "concentration_green": concentration_green,
        "limits": {
            "book_worst_case_limit_pct": BOOK_WORST_CASE_LIMIT_PCT,
            "single_name_concentration_limit": SINGLE_NAME_CONCENTRATION_LIMIT,
        },
        "repair_item_count": len(repair_items),
        "long_premium_note": "long options: max loss per position is bounded by premium paid; stress verifies book-level aggregation and liquidity-hole exits",
        "paper_only": True,
        "live_blocked": True,
        **forward_book_binding,
        **quote_snapshot_binding,
        **stress_policy_binding,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary, results, repair_items


def _enrich_with_current_quotes(
    positions: list[dict[str, Any]],
) -> QuoteSnapshotBinding:
    """Attach current spot/IV from the latest validated snapshot so shocks start
    from today's market state; positions without a current quote keep entry state
    and are flagged."""
    if not positions:
        return _quote_snapshot_binding({}, positions)
    snapshot = _load_current_quote_snapshot()
    binding = _quote_snapshot_binding(snapshot, positions)
    if snapshot.get("chain_snapshot_status") != "real_chain_snapshot_validated":
        return binding
    by_contract = {
        (row["symbol"], row["expiry"], row["option_type"], float(row["strike"])): row
        for row in snapshot["rows"]
    }
    for position in positions:
        row = by_contract.get(
            (
                position["symbol"],
                position["expiry"],
                position["option_type"],
                float(position["strike"]),
            )
        )
        if row is not None:
            position["current_spot"] = float(row["underlying_spot"])
            position["current_iv"] = float(row["implied_vol"])
        else:
            position["valued_at_entry_spot_fallback"] = True
    return binding


def _shocked_exit_value(
    position: dict[str, Any],
    scenario: dict[str, Any],
    risk_free_rate: float,
) -> float:
    # Stress from CURRENT state, not entry state: a 25-days-held option must be
    # shocked at its remaining DTE, or near-expiry gamma/theta risk is understated.
    valuation_date = str(position.get("last_mark_date") or position["entry_date"])
    base_spot = float(position.get("current_spot") or position["entry_spot"])
    spot = base_spot * (1.0 + float(scenario["spot_shock"]))
    iv = max(
        float(position.get("current_iv") or position["entry_iv"])
        * (1.0 + float(scenario["iv_shock"])),
        0.01,
    )
    from datetime import date

    try:
        dte = max(
            (
                date.fromisoformat(position["expiry"])
                - date.fromisoformat(valuation_date)
            ).days,
            1,
        )
    except ValueError:
        dte = 20
    pricing = price_european_option(
        option_pricing_input(
            symbol=str(position["symbol"]),
            option_type=str(position["option_type"]),
            strike=float(position["strike"]),
            expiry=str(position["expiry"]),
            valuation_date=valuation_date,
            underlying_price=max(spot, 0.01),
            time_to_expiry_years=max(dte / 365.0, 0.0),
            implied_vol=min(iv, 5.0),
            risk_free_rate=risk_free_rate,
            dividend_yield=0.0,
            pricing_source_tier="model_priced",
        )
    )
    mid = max(float(pricing.model_price), 0.0)
    half_spread = BASE_HALF_SPREAD_PCT * (
        SPREAD_WIDENING_FACTOR if scenario["liquidity_hole"] else 1.0
    )
    return max(mid * (1.0 - half_spread), 0.0)


def _max_symbol_concentration(
    positions: list[dict[str, Any]], book_premium: float
) -> dict[str, Any]:
    by_symbol: dict[str, float] = {}
    for position in positions:
        by_symbol[str(position["symbol"])] = by_symbol.get(
            str(position["symbol"]), 0.0
        ) + float(position["entry_fill"])
    if not by_symbol or book_premium <= 0:
        return {"symbol": "", "share": 0.0}
    symbol = max(by_symbol, key=by_symbol.get)
    return {"symbol": symbol, "share": by_symbol[symbol] / book_premium}


def _repair(reason: str, detail: str, action: str) -> dict[str, Any]:
    return {
        "artifact_type": "adversarial_stress_repair_item",
        "reason": reason,
        "detail": detail,
        "suggested_action": action,
        "recorded_as_pass": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _load_ledger() -> dict[str, Any]:
    if LEDGER_PATH.exists():
        parsed = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    return {"open_positions": [], "closed_trades": [], "last_marking_date": ""}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
