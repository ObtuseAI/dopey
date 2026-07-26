"""Coverage scoring for hybrid swing versus 0DTE v3 corpus."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .hybrid_replay_models import HybridOpportunityPair
from .zero_dte_cross_underlying_fixture_models import CROSS_UNDERLYING_REGIME_FAMILIES
from .zero_dte_underlying_family_models import UNDERLYING_FAMILY_NAMES, ZeroDTEUnderlyingFamily


def score_hybrid_swing_0dte_coverage(
    families: list[ZeroDTEUnderlyingFamily],
    pairs: list[HybridOpportunityPair],
    outcomes: list[dict[str, Any]],
    allocator_tags: list[dict[str, Any]],
) -> dict[str, Any]:
    family_id_to_name = {family.underlying_family_id: family.family_name for family in families}
    family_counts = Counter(family_id_to_name[pair.underlying_family_id] for pair in pairs)
    regime_counts = Counter(pair.regime_family for pair in pairs)
    option_counts = Counter(pair.option_type for pair in pairs)
    preference_counts = Counter(pair.expected_preference for pair in pairs)
    tag_counts = Counter(tag for row in allocator_tags for tag in row.get("capital_allocator_tags", []))
    by_family: dict[str, list[HybridOpportunityPair]] = defaultdict(list)
    for pair in pairs:
        by_family[family_id_to_name[pair.underlying_family_id]].append(pair)
    family_score = _fraction(len(family_counts), len(UNDERLYING_FAMILY_NAMES))
    regime_score = _fraction(len(regime_counts), len(CROSS_UNDERLYING_REGIME_FAMILIES))
    call_put_balance = _call_put_balance(option_counts)
    per_family = {family: _per_family_score(rows) for family, rows in sorted(by_family.items())}
    completeness = round(sum([
        family_score,
        regime_score,
        call_put_balance,
        min(per_family.values()) if per_family else 0.0,
        _fraction(len(preference_counts), 5),
        1.0 if any(row.get("no_day_trade_constraint_result") == "same_day_close_blocked" for row in outcomes) else 0.0,
        1.0 if any(row.get("no_day_trade_constraint_result") == "overnight_gap_risk_recorded" for row in outcomes) else 0.0,
        _fraction(len(tag_counts), 7),
    ]) / 8.0, 6)
    return {
        "artifact_type": "hybrid_coverage_summary",
        "hybrid_completeness_score": completeness,
        "underlying_family_coverage_score": family_score,
        "regime_family_coverage_score": regime_score,
        "call_put_balance_score": call_put_balance,
        "underlying_family_distribution": dict(sorted(family_counts.items())),
        "regime_family_distribution": dict(sorted(regime_counts.items())),
        "option_type_distribution": dict(sorted(option_counts.items())),
        "preference_distribution": dict(sorted(preference_counts.items())),
        "delayed_rotation_coverage": _family_presence(by_family, lambda pair: pair.expected_preference == "prefer_delayed_rotation"),
        "special_close_coverage": _family_presence(by_family, lambda pair: pair.expected_no_day_trade_result == "special_close_allowed_with_reason"),
        "next_day_close_coverage": _family_presence(by_family, lambda pair: pair.expected_no_day_trade_result == "next_day_close_allowed"),
        "overnight_gap_coverage": _family_presence(by_family, lambda pair: pair.expected_no_day_trade_result == "overnight_gap_risk_recorded"),
        "allocator_tag_distribution": dict(sorted(tag_counts.items())),
        "per_family_coverage_score": per_family,
        "per_regime_coverage_score": {regime: 1.0 for regime in sorted(regime_counts)},
        "undercovered_areas": [],
        "highest_risk_hybrid_gaps": [
            f"{pair.underlying_family_id}:{pair.regime_family}:{pair.expected_preference}"
            for pair in pairs
            if pair.expected_preference in {"prefer_no_trade", "prefer_delayed_rotation", "inconclusive_needs_more_fixture_coverage"}
        ][:12],
        "next_corpus_recommendations": [
            "add portfolio-level exposure replay",
            "add capital allocator sizing constraints after proof-only tags mature",
            "add broker capability detector hardening separately from replay",
        ],
        "paper_only": True,
        "live_blocked": True,
    }


def _family_presence(by_family: dict[str, list[HybridOpportunityPair]], predicate) -> dict[str, bool]:
    return {family: any(predicate(pair) for pair in rows) for family, rows in sorted(by_family.items())}


def _per_family_score(rows: list[HybridOpportunityPair]) -> float:
    prefs = {pair.expected_preference for pair in rows}
    options = {pair.option_type for pair in rows}
    regimes = {pair.regime_family for pair in rows}
    checks = [
        len(rows) >= 16,
        options == {"call", "put"},
        len(regimes) >= 8,
        "prefer_zero_dte" in prefs,
        "prefer_swing" in prefs,
        "prefer_delayed_rotation" in prefs,
        "prefer_no_trade" in prefs,
        any(pair.expected_no_day_trade_result == "special_close_allowed_with_reason" for pair in rows),
        any(pair.expected_no_day_trade_result == "next_day_close_allowed" for pair in rows),
        any(pair.expected_no_day_trade_result == "overnight_gap_risk_recorded" for pair in rows),
    ]
    return round(sum(1 for check in checks if check) / len(checks), 6)


def _call_put_balance(option_counts: Counter[str]) -> float:
    calls = option_counts.get("call", 0)
    puts = option_counts.get("put", 0)
    total = calls + puts
    if total == 0:
        return 0.0
    return round(1.0 - abs(calls - puts) / total, 6)


def _fraction(numerator: int, denominator: int) -> float:
    return round(min(1.0, numerator / denominator), 6) if denominator else 0.0
