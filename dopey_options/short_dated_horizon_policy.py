"""Fail-closed research policy for 1DTE through weekly option horizons.

The policy separates contract availability from research maturity. A chain row
can make a horizon observable, but it cannot prove forecast skill, executable
edge, or live readiness. Short-dated options remain research-only and the
owner-controlled options execution switch remains outside this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Final, Mapping, Sequence


SHORT_DATED_HORIZON_POLICY_VERSION: Final[str] = (
    "dopey-short-dated-horizon-research-policy-v1"
)
MINIMUM_INDEPENDENT_SETTLEMENTS: Final[int] = 200
MINIMUM_REGIME_BUCKETS: Final[int] = 5
MINIMUM_SETTLEMENTS_PER_REGIME: Final[int] = 30

REQUIRED_MICROSTRUCTURE_FIELDS: Final[tuple[str, ...]] = (
    "quote_timestamp_utc",
    "underlying_quote_timestamp_utc",
    "contract_symbol",
    "bid_size",
    "ask_size",
    "expiry_timestamp_utc",
    "exercise_style",
    "settlement_type",
    "multiplier",
    "adjustment_status",
)

REQUIRED_PROMOTION_GATES: Final[tuple[str, ...]] = (
    "point_in_time_underlying_forecast_calibrated_for_exact_horizon",
    "independent_expiry_outcomes_meet_sample_and_regime_floors",
    "after_spread_slippage_and_fees_lower_confidence_bound_positive",
    "quote_staleness_and_adverse_selection_stress_green",
    "exercise_assignment_settlement_and_pin_risk_replay_green",
    "portfolio_gamma_vega_gap_and_premium_at_risk_limits_green",
    "independent_paper_execution_and_reconciliation_green",
)

PRIMARY_RESEARCH_SOURCES: Final[tuple[dict[str, str], ...]] = (
    {
        "source_id": "cboe_available_weeklys",
        "url": "https://www.cboe.com/available_weeklys",
        "role": "listed weekly expiration and settlement taxonomy",
    },
    {
        "source_id": "cboe_xsp_specification",
        "url": (
            "https://www.cboe.com/tradable_products/sp_500/"
            "mini_spx_options/specifications"
        ),
        "role": "exercise style, expiration clock, multiplier, and settlement",
    },
    {
        "source_id": "occ_options_disclosure_document",
        "url": (
            "https://www.theocc.com/company-information/documents-and-archives/"
            "options-disclosure-document"
        ),
        "role": "standardized option lifecycle and risk disclosure",
    },
    {
        "source_id": "oic_exercising_options",
        "url": "https://www.optionseducation.org/optionsoverview/exercising-options",
        "role": "exercise, assignment, dividend, and post-close risk",
    },
    {
        "source_id": "finra_zero_dte_risk",
        "url": (
            "https://www.finra.org/investors/insights/"
            "zeroing-in-options-trading-strategy"
        ),
        "role": "short-dated leverage, expiration, and day-trade risk",
    },
)


@dataclass(frozen=True)
class HorizonDefinition:
    """Exact calendar-DTE lane and its distinct research hypothesis."""

    lane_id: str
    minimum_dte_calendar: int
    maximum_dte_calendar: int
    hypothesis_role: str
    dominant_risks: tuple[str, ...]


HORIZON_DEFINITIONS: Final[tuple[HorizonDefinition, ...]] = (
    HorizonDefinition(
        lane_id="one_dte",
        minimum_dte_calendar=1,
        maximum_dte_calendar=1,
        hypothesis_role="overnight_gap_and_next_session_expiry",
        dominant_risks=(
            "overnight_gap",
            "expiry_gamma",
            "theta",
            "pin_and_assignment",
        ),
    ),
    HorizonDefinition(
        lane_id="two_dte",
        minimum_dte_calendar=2,
        maximum_dte_calendar=2,
        hypothesis_role="two_session_catalyst_and_convexity",
        dominant_risks=(
            "overnight_gap",
            "gamma_acceleration",
            "theta",
            "liquidity_cliff",
        ),
    ),
    HorizonDefinition(
        lane_id="three_dte",
        minimum_dte_calendar=3,
        maximum_dte_calendar=3,
        hypothesis_role="short_swing_path_with_expiry_pressure",
        dominant_risks=(
            "path_dependency",
            "event_jump",
            "volatility_crush",
            "spread_cost",
        ),
    ),
    HorizonDefinition(
        lane_id="four_dte",
        minimum_dte_calendar=4,
        maximum_dte_calendar=4,
        hypothesis_role="short_swing_with_week_boundary_and_event_risk",
        dominant_risks=(
            "weekend_or_holiday_clock",
            "event_jump",
            "volatility_term_shift",
            "spread_cost",
        ),
    ),
    HorizonDefinition(
        lane_id="weekly_five_to_nine_dte",
        minimum_dte_calendar=5,
        maximum_dte_calendar=9,
        hypothesis_role="weekly_catalyst_and_directional_swing",
        dominant_risks=(
            "catalyst_miss",
            "volatility_crush",
            "term_structure",
            "early_assignment_for_american_style_options",
        ),
    ),
)


def build_short_dated_horizon_audit(
    snapshot_date: str,
    chain_rows: Sequence[Mapping[str, Any]],
    input_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit exact horizon coverage without granting promotion or execution."""
    normalized_rows = tuple(_normalize_row(row, snapshot_date) for row in chain_rows)
    available_fields = sorted(
        set.intersection(*(set(row) for row in normalized_rows))
        if normalized_rows
        else set()
    )
    missing_snapshot_fields = sorted(
        set(REQUIRED_MICROSTRUCTURE_FIELDS) - set(available_fields)
    )
    lanes = tuple(
        _audit_lane(definition, normalized_rows, missing_snapshot_fields)
        for definition in HORIZON_DEFINITIONS
    )
    horizon_row_count = sum(int(lane["contract_row_count"]) for lane in lanes)
    observable_lane_count = sum(
        1 for lane in lanes if int(lane["contract_row_count"]) > 0
    )
    capture_status = (
        "blocked_no_short_dated_contract_rows"
        if observable_lane_count == 0
        else "blocked_incomplete_short_dated_capture_contract"
        if missing_snapshot_fields
        else "eligible_for_prospective_paper_capture_only"
    )
    result: dict[str, Any] = {
        "artifact_type": "short_dated_option_horizon_research_audit",
        "policy_version": SHORT_DATED_HORIZON_POLICY_VERSION,
        "snapshot_date": snapshot_date,
        "snapshot_contract_row_count": len(normalized_rows),
        "short_dated_contract_row_count": horizon_row_count,
        "observable_lane_count": observable_lane_count,
        "required_lane_count": len(HORIZON_DEFINITIONS),
        "capture_status": capture_status,
        "available_snapshot_fields": available_fields,
        "missing_required_microstructure_fields": missing_snapshot_fields,
        "minimum_independent_settlements_per_lane": (
            MINIMUM_INDEPENDENT_SETTLEMENTS
        ),
        "minimum_regime_buckets_per_lane": MINIMUM_REGIME_BUCKETS,
        "minimum_settlements_per_regime": MINIMUM_SETTLEMENTS_PER_REGIME,
        "required_promotion_gates": list(REQUIRED_PROMOTION_GATES),
        "horizon_lanes": list(lanes),
        "zero_dte_structural_status": {
            "research_lane": "separate_from_one_through_nine_dte",
            "current_governed_chain_schema_accepts_zero_dte": False,
            "same_session_round_trip_permitted": False,
            "status": "blocked_separate_intraday_and_lifecycle_evidence_required",
        },
        "input_evidence": dict(input_evidence),
        "primary_research_sources": [dict(source) for source in PRIMARY_RESEARCH_SOURCES],
        "underlying_direction_may_ignore_historical_option_evidence": True,
        "option_payoff_and_execution_may_ignore_current_option_evidence": False,
        "promotion_allowed": False,
        "option_execution_enabled": False,
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order": True,
    }
    result["reproducibility_hash"] = _reproducibility_hash(result)
    return result


def _normalize_row(
    row: Mapping[str, Any],
    expected_snapshot_date: str,
) -> dict[str, Any]:
    normalized = dict(row)
    observed_snapshot_date = str(normalized.get("snapshot_date", "")).strip()
    if observed_snapshot_date != expected_snapshot_date:
        raise ValueError(
            "short-dated audit row snapshot mismatch: "
            f"observed={observed_snapshot_date!r}, "
            f"expected={expected_snapshot_date!r}"
        )
    raw_dte = normalized.get("dte_calendar")
    if isinstance(raw_dte, bool):
        raise TypeError(f"short-dated audit DTE must be an integer: value={raw_dte!r}")
    try:
        dte = int(raw_dte)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"short-dated audit DTE must be an integer: value={raw_dte!r}"
        ) from error
    if dte < 0:
        raise ValueError(f"short-dated audit DTE cannot be negative: value={dte}")
    normalized["dte_calendar"] = dte
    normalized["symbol"] = str(normalized.get("symbol", "")).strip().upper()
    normalized["expiry"] = str(normalized.get("expiry", "")).strip()
    if not normalized["symbol"] or not normalized["expiry"]:
        raise ValueError(
            "short-dated audit row requires symbol and expiry: "
            f"symbol={normalized['symbol']!r}, expiry={normalized['expiry']!r}"
        )
    return normalized


def _audit_lane(
    definition: HorizonDefinition,
    rows: Sequence[Mapping[str, Any]],
    missing_snapshot_fields: Sequence[str],
) -> dict[str, Any]:
    lane_rows = tuple(
        row
        for row in rows
        if definition.minimum_dte_calendar
        <= int(row["dte_calendar"])
        <= definition.maximum_dte_calendar
    )
    symbols = sorted({str(row["symbol"]) for row in lane_rows})
    expiries = sorted({str(row["expiry"]) for row in lane_rows})
    if not lane_rows:
        research_status = "blocked_missing_exact_horizon_contracts"
    elif missing_snapshot_fields:
        research_status = "blocked_missing_intraday_microstructure_and_lifecycle_fields"
    else:
        research_status = "eligible_for_prospective_paper_capture_only"
    return {
        **asdict(definition),
        "contract_row_count": len(lane_rows),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "expiry_count": len(expiries),
        "expiries": expiries,
        "missing_required_microstructure_fields": list(missing_snapshot_fields),
        "research_status": research_status,
        "prospective_outcome_count": 0,
        "promotion_allowed": False,
        "execution_allowed": False,
    }


def _reproducibility_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("reproducibility_hash", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
