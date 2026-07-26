"""Build deterministic hybrid swing versus 0DTE v3 fixtures."""
from __future__ import annotations

from collections import Counter

from .hybrid_replay_models import HybridOpportunityPair, hybrid_pair_hash
from .swing_option_models import SwingOptionCandidate, swing_option_candidate_hash
from .zero_dte_cross_underlying_fixture_builder import FAMILY_ORDER, build_zero_dte_underlying_families
from .zero_dte_underlying_family_models import ZeroDTEUnderlyingFamily


HYBRID_TEMPLATE_FIELDS: tuple[str, ...] = (
    "regime",
    "option",
    "preference",
    "rotation",
    "no_day_trade",
    "zero_dte_decision",
    "swing_decision",
    "hold_days",
    "risk_tier",
)

HYBRID_CASE_TEMPLATES: tuple[tuple[str, str, str, str, str, str, str, int, str], ...] = (
    ("bull_trend", "call", "prefer_zero_dte", "open_zero_dte_special_lifecycle", "special_close_allowed_with_reason", "approved_special_lifecycle", "swing_allowed", 2, "moderate"),
    ("bear_trend", "put", "prefer_swing", "open_swing_next_day_close_plan", "next_day_close_allowed", "approved_but_gamma_sensitive", "swing_allowed", 3, "moderate"),
    ("chop_decay", "call", "prefer_swing", "open_swing_theta_reduction", "next_day_close_allowed", "blocked_theta_decay", "swing_allowed", 4, "moderate"),
    ("false_breakout", "put", "prefer_no_trade", "reject_both", "no_entry_no_day_trade_risk", "blocked_false_signal", "blocked_false_signal", 2, "high"),
    ("false_breakdown", "call", "prefer_delayed_rotation", "delay_rotation_until_next_day", "same_day_close_blocked", "blocked_same_day_churn", "swing_allowed_delayed", 2, "moderate"),
    ("gap_and_fade", "put", "prefer_swing", "open_swing_gap_risk_managed", "overnight_gap_risk_recorded", "blocked_gap_fade", "swing_allowed", 5, "high"),
    ("gap_and_go", "call", "prefer_zero_dte", "open_zero_dte_momentum", "special_close_allowed_with_reason", "approved_special_lifecycle", "swing_allowed", 2, "moderate"),
    ("iv_expansion", "call", "prefer_swing", "prefer_later_expiry", "next_day_close_allowed", "blocked_iv_overpayment", "swing_allowed", 5, "moderate"),
    ("iv_crush", "put", "prefer_no_trade", "reject_iv_crush", "no_entry_no_day_trade_risk", "blocked_iv_crush", "blocked_iv_crush", 3, "high"),
    ("macro_shock", "call", "prefer_delayed_rotation", "delay_rotation_until_macro_clear", "same_day_close_blocked", "blocked_macro_shock", "swing_allowed_delayed", 4, "high"),
    ("event_whipsaw", "put", "inconclusive_needs_more_fixture_coverage", "hold_for_more_fixture_coverage", "next_day_close_allowed", "blocked_event_whipsaw", "swing_allowed", 3, "high"),
    ("late_day_liquidity_decay", "call", "prefer_swing", "open_swing_avoid_late_liquidity", "next_day_close_allowed", "blocked_liquidity_decay", "swing_allowed", 2, "moderate"),
    ("pin_near_strike", "put", "prefer_swing", "open_swing_avoid_pin", "next_day_close_allowed", "blocked_pin_risk", "swing_allowed", 4, "moderate"),
    ("mean_reversion", "call", "prefer_zero_dte", "open_zero_dte_reversion", "special_close_allowed_with_reason", "approved_special_lifecycle", "swing_allowed", 2, "moderate"),
    ("trend_persistence", "put", "prefer_swing", "open_swing_trend_persistence", "next_day_close_allowed", "approved_but_theta_sensitive", "swing_allowed", 5, "low"),
    ("range_bound", "put", "prefer_no_trade", "reject_range_chop", "no_entry_no_day_trade_risk", "blocked_range_bound", "blocked_range_bound", 2, "high"),
)


def build_hybrid_underlying_families_v3() -> list[ZeroDTEUnderlyingFamily]:
    return build_zero_dte_underlying_families()


def build_hybrid_swing_candidates_v3(
    families: list[ZeroDTEUnderlyingFamily],
) -> list[SwingOptionCandidate]:
    candidates: list[SwingOptionCandidate] = []
    for family_index, family in enumerate(families):
        for template_index, template in enumerate(HYBRID_CASE_TEMPLATES):
            candidate = _swing_candidate(family, family_index, template_index, template)
            candidates.append(SwingOptionCandidate(**{**candidate.to_dict(), "candidate_hash": swing_option_candidate_hash(candidate)}))
    return candidates


def build_hybrid_opportunity_pairs_v3(
    families: list[ZeroDTEUnderlyingFamily],
    swing_candidates: list[SwingOptionCandidate],
) -> list[HybridOpportunityPair]:
    swing_by_id = {candidate.candidate_id: candidate for candidate in swing_candidates}
    pairs: list[HybridOpportunityPair] = []
    pair_index = 0
    for family_index, family in enumerate(families):
        for template_index, template in enumerate(HYBRID_CASE_TEMPLATES):
            pair_index += 1
            swing_id = _swing_candidate_id(family_index, template_index)
            swing = swing_by_id[swing_id]
            regime, option_type, preference, rotation, no_day_trade, zero_dte_decision, swing_decision, _hold_days, _risk_tier = template
            draft = HybridOpportunityPair(
                pair_id=f"hybrid-v3-pair-{pair_index:03d}",
                underlying_family_id=family.underlying_family_id,
                synthetic_underlying_symbol=family.synthetic_underlying_symbol,
                regime_family=regime,
                option_type=option_type,
                zero_dte_candidate_id=f"hybrid-zero-dte-{pair_index:03d}",
                swing_candidate_id=swing.candidate_id,
                shared_signal_id=f"hybrid-signal-{family_index + 1:02d}-{template_index + 1:02d}",
                shared_thesis=_shared_thesis(family.family_name, regime, preference),
                zero_dte_expected_decision=zero_dte_decision,
                swing_expected_decision=swing_decision,
                expected_preference=preference,
                expected_rotation_action=rotation,
                expected_no_day_trade_result=no_day_trade,
                paper_only=True,
                live_blocked=True,
                pair_hash="",
            )
            pairs.append(HybridOpportunityPair(**{**draft.to_dict(), "pair_hash": hybrid_pair_hash(draft)}))
    return pairs


def hybrid_family_distribution(pairs: list[HybridOpportunityPair]) -> dict[str, int]:
    return dict(sorted(Counter(pair.underlying_family_id for pair in pairs).items()))


def hybrid_regime_distribution(pairs: list[HybridOpportunityPair]) -> dict[str, int]:
    return dict(sorted(Counter(pair.regime_family for pair in pairs).items()))


def _swing_candidate(
    family: ZeroDTEUnderlyingFamily,
    family_index: int,
    template_index: int,
    template: tuple[str, str, str, str, str, str, str, int, str],
) -> SwingOptionCandidate:
    regime, option_type, preference, _rotation, _no_day_trade, _zero_dte_decision, swing_decision, hold_days, risk_tier = template
    case_number = family_index * len(HYBRID_CASE_TEMPLATES) + template_index + 1
    liquidity = _liquidity_score(family.option_liquidity_archetype, risk_tier)
    spread = _spread_pct(family.spread_archetype, risk_tier)
    gamma = 0.08 if preference == "prefer_zero_dte" else 0.04
    theta = -0.18 if preference == "prefer_swing" else -0.32
    if swing_decision.startswith("blocked"):
        liquidity = min(liquidity, 0.22)
        spread = max(spread, 0.18)
    draft = SwingOptionCandidate(
        candidate_id=_swing_candidate_id(family_index, template_index),
        underlying_family_id=family.underlying_family_id,
        synthetic_underlying_symbol=family.synthetic_underlying_symbol,
        option_type=option_type,
        trade_date="2026-07-06",
        expiry=f"2026-07-{13 + (template_index % 10):02d}",
        days_to_expiry=max(hold_days + 1, 2),
        strike=round(100.0 + (case_number % 17), 2),
        moneyness="atm" if template_index % 3 == 0 else ("slightly_otm" if template_index % 3 == 1 else "slightly_itm"),
        open_price=round(1.05 + (case_number % 9) * 0.09, 4),
        risk_tier=risk_tier,
        proof_score=round(0.52 + (template_index % 5) * 0.08, 4),
        signal_confidence=round(0.5 + (template_index % 6) * 0.07, 4),
        liquidity_score=round(liquidity, 4),
        slippage_score=round(spread * 0.6, 4),
        spread_pct=round(spread, 4),
        delta=round(0.52 if option_type == "call" else -0.52, 4),
        gamma=round(gamma, 4),
        theta=round(theta, 4),
        vega=round(0.18 + hold_days * 0.015, 4),
        implied_volatility=round(0.28 + (template_index % 7) * 0.025, 4),
        event_risk_score=round(0.75 if regime in {"event_whipsaw", "macro_shock"} else 0.35, 4),
        regime_score=round(0.8 if preference in {"prefer_zero_dte", "prefer_swing"} else 0.42, 4),
        expected_hold_days=hold_days,
        explicit_thesis=_shared_thesis(family.family_name, regime, preference),
        explicit_exit_plan="sell_to_close on next eligible trading day or later; never normal same-day churn",
        entry_action="buy_to_open",
        exit_action="sell_to_close",
        paper_only=True,
        live_blocked=True,
        candidate_hash="",
    )
    return draft


def _swing_candidate_id(family_index: int, template_index: int) -> str:
    return f"hybrid-swing-{family_index + 1:02d}-{template_index + 1:02d}"


def _shared_thesis(family_name: str, regime: str, preference: str) -> str:
    return f"{family_name} {regime} fixture thesis with expected {preference}; offline synthetic evidence only"


def _liquidity_score(archetype: str, risk_tier: str) -> float:
    base = {"deep": 0.86, "medium": 0.62, "thin": 0.28}.get(archetype, 0.58)
    if risk_tier == "high":
        return base - 0.18
    if risk_tier == "low":
        return base + 0.08
    return base


def _spread_pct(archetype: str, risk_tier: str) -> float:
    base = {"tight": 0.03, "normal": 0.06, "wide": 0.14, "wide_on_gap": 0.16, "wide_near_close": 0.15, "variable": 0.1}.get(archetype, 0.08)
    return base + (0.05 if risk_tier == "high" else 0.0)
