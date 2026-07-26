"""Build explainable bullish and bearish research rankings for the desktop.

The ranking layer consumes governed research artifacts. It never converts
attention into direction, treats a rank score as a probability, constructs an
order, or promotes a strategy. Direction must come from independent playbook
detections; attention only determines which directional hypotheses deserve
research first.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from statistics import fmean
from typing import Final, Literal, cast

from dopey.protocols.identity import canonical_hash

from .playbook_settlement import PLAYBOOK_TRUST_VERSION


PLAYBOOK_RANKING_VERSION: Final[str] = "dopey-playbook-rankings-v2"
SHORT_TERM_MAX_SESSIONS: Final[int] = 10
LONG_TERM_MIN_SESSIONS: Final[int] = 20
LIST_SIZE: Final[int] = 10
OVERALL_SIZE: Final[int] = 5

HorizonBucket = Literal["short_term", "long_term"]
DirectionalBias = Literal["bullish", "bearish"]


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"playbook ranking field must be numeric: field={field}, value={value!r}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            f"playbook ranking field must be finite: field={field}, value={value!r}"
        )
    return number


def _optional_finite_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    return _finite_number(value, field)


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"playbook ranking field must be an object: field={field}")
    return cast(dict[str, object], value)


def _mapping_or_empty(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return {}
    return cast(dict[str, object], value)


def _records(value: object, field: str) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"playbook ranking field must be an array: field={field}")
    output: list[dict[str, object]] = []
    for index, item in enumerate(value):
        output.append(_mapping(item, f"{field}[{index}]"))
    return output


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _score01(value: object, field: str) -> float:
    number = _finite_number(value, field)
    if number < 0.0:
        raise ValueError(f"score cannot be negative: field={field}, value={number}")
    normalized = number / 100.0 if number > 1.0 else number
    return min(normalized, 1.0)


def _parse_utc(value: str, field: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp must be timezone-aware: field={field}, value={value}"
        )
    return parsed.astimezone(timezone.utc)


def _parse_iso_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise TypeError(f"date must be an ISO string: field={field}, value={value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"date must use ISO YYYY-MM-DD form: field={field}, value={value!r}"
        ) from error


def _horizon_bucket(raw_horizons: object) -> HorizonBucket | None:
    if not isinstance(raw_horizons, (list, tuple)) or not raw_horizons:
        return None
    horizons: list[int] = []
    for value in raw_horizons:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        horizons.append(value)
    if max(horizons) <= SHORT_TERM_MAX_SESSIONS:
        return "short_term"
    if min(horizons) >= LONG_TERM_MIN_SESSIONS:
        return "long_term"
    return None


def _directional_bias(value: object) -> DirectionalBias | None:
    if value == "long":
        return "bullish"
    if value == "short":
        return "bearish"
    return None


def _percentile_by_detection(
    detections: Sequence[Mapping[str, object]],
) -> dict[str, float]:
    grouped: dict[tuple[str, str, str], list[tuple[str, float]]] = defaultdict(list)
    for detection in detections:
        detection_id = str(detection.get("detection_id", ""))
        setup_id = str(detection.get("setup_id", ""))
        bias = _directional_bias(detection.get("direction"))
        horizon = _horizon_bucket(detection.get("horizon_days"))
        if not detection_id or not setup_id or bias is None or horizon is None:
            continue
        strength = _finite_number(
            detection.get("strength"), f"detections[{detection_id}].strength"
        )
        grouped[(setup_id, bias, horizon)].append((detection_id, strength))

    percentiles: dict[str, float] = {}
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: (item[1], item[0]))
        denominator = max(len(ordered) - 1, 1)
        index = 0
        while index < len(ordered):
            end = index
            while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
                end += 1
            percentile = (
                ((index + end) / 2.0) / denominator if len(ordered) > 1 else 0.5
            )
            for row_index in range(index, end + 1):
                percentiles[ordered[row_index][0]] = percentile
            index = end + 1
    return percentiles


def _attention_by_symbol(
    attention_snapshot: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if attention_snapshot.get("future_observation_consumed") is not False:
        raise ValueError(
            "attention snapshot must assert future_observation_consumed=false"
        )
    if attention_snapshot.get("universe_research_input_allowed") is not True:
        raise ValueError(
            "attention snapshot is not eligible for universe or playbook research input"
        )
    output: dict[str, dict[str, object]] = {}
    for row in _records(attention_snapshot.get("symbols"), "attention.symbols"):
        symbol = str(row.get("symbol", "")).upper().strip()
        status = str(row.get("status", ""))
        if not symbol or status not in {"scored", "partial"}:
            continue
        if row.get("attention_score") is None:
            continue
        _score01(
            row.get("attention_score"), f"attention.symbols[{symbol}].attention_score"
        )
        output[symbol] = row
    return output


def _universe_by_symbol(
    universe_summary: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if universe_summary.get("status") != "evolved":
        raise ValueError(
            "evolving universe is not eligible for playbook research: "
            f"status={universe_summary.get('status')!r}"
        )
    if universe_summary.get("maximum_active_universe_size") != 500:
        raise ValueError(
            "evolving universe must use the owner-directed 500-symbol cap: "
            f"actual={universe_summary.get('maximum_active_universe_size')!r}"
        )
    if universe_summary.get("registry_mutated") not in {True, False}:
        raise TypeError("evolving universe must report registry_mutated as a boolean")
    output: dict[str, dict[str, object]] = {}
    for row in _records(
        universe_summary.get("ranked_members"), "universe.ranked_members"
    ):
        symbol = str(row.get("symbol", "")).upper().strip()
        tier = str(row.get("resulting_tier", ""))
        if (
            not symbol
            or tier not in {"core", "probation"}
            or row.get("research_tradable") is not True
            or row.get("ranking_eligible_for_playbook") is not True
        ):
            continue
        _score01(
            row.get("selection_score"),
            f"universe.ranked_members[{symbol}].selection_score",
        )
        output[symbol] = row
    return output


def _swing_by_symbol(
    swing_theses: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for thesis in swing_theses:
        symbol = str(thesis.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        if (
            thesis.get("paper_only") is not True
            or thesis.get("live_blocked") is not True
        ):
            raise ValueError(
                f"swing thesis violates research boundary: symbol={symbol}"
            )
        output[symbol] = dict(thesis)
    return output


def _role_by_symbol(symbol_dossiers: Sequence[Mapping[str, object]]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for dossier in symbol_dossiers:
        symbol = str(dossier.get("symbol", "")).upper().strip()
        role = str(dossier.get("role", ""))
        if symbol:
            roles[symbol] = role
    return roles


def _fundamentals_by_symbol(
    fundamental_confirmations: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for raw_symbol, raw_record in fundamental_confirmations.items():
        symbol = str(raw_symbol).upper().strip()
        if not symbol or not isinstance(raw_record, Mapping):
            raise TypeError(
                "fundamental confirmation map requires nonempty symbol keys and object values"
            )
        record = dict(raw_record)
        if str(record.get("symbol", "")).upper().strip() != symbol:
            raise ValueError(
                "fundamental confirmation key does not match its record: "
                f"key={symbol!r}, record_symbol={record.get('symbol')!r}"
            )
        output[symbol] = record
    return output


def _trust_score(
    setup: Mapping[str, object], horizon: HorizonBucket
) -> tuple[float, str, int, float | None, int, float]:
    settled_value = setup.get("settled", 0)
    if (
        isinstance(settled_value, bool)
        or not isinstance(settled_value, int)
        or settled_value < 0
    ):
        raise TypeError(
            f"setup trust settled count must be a nonnegative integer: value={settled_value!r}"
        )
    settled = int(settled_value)
    state = str(setup.get("trust_state", "unrated_missing_trust"))
    contested_hit_rate = _optional_finite_number(
        setup.get("effective_contested_hit_rate"),
        "setup_trust.effective_contested_hit_rate",
    )
    raw_evidence_count = setup.get("effective_contested_settled", 0)
    if (
        isinstance(raw_evidence_count, bool)
        or not isinstance(raw_evidence_count, int)
        or raw_evidence_count < 0
    ):
        raise TypeError(
            "setup trust scored observation count must be a nonnegative integer: "
            f"value={raw_evidence_count!r}"
        )
    evidence_count = int(raw_evidence_count)
    hit_rate = contested_hit_rate
    empirical = 0.0 if hit_rate is None else min(max(hit_rate, 0.0), 1.0)
    baseline_relative_skill = max(2.0 * empirical - 1.0, 0.0)
    maturity = min(evidence_count / 30.0, 1.0)
    score = (
        baseline_relative_skill * maturity
        if state == "rated" and evidence_count >= 30
        else 0.0
    )
    if horizon == "long_term":
        score = 0.0
    return score, state, settled, hit_rate, evidence_count, baseline_relative_skill


def _liquidity_score(avg_dollar_volume: float) -> float:
    if avg_dollar_volume <= 0.0:
        return 0.0
    floor = math.log10(5_000_000.0)
    ceiling = math.log10(1_000_000_000.0)
    return min(
        max((math.log10(avg_dollar_volume) - floor) / (ceiling - floor), 0.0), 1.0
    )


def _directional_support(thesis: Mapping[str, object], bias: DirectionalBias) -> float:
    key = "equity_bullish_score" if bias == "bullish" else "equity_bearish_score"
    value = thesis.get(key)
    return 0.0 if value is None else _score01(value, f"swing_thesis.{key}")


def _attention_reasons(attention: Mapping[str, object]) -> list[str]:
    components = _mapping_or_empty(attention.get("component_scores"))
    available: list[tuple[float, str]] = []
    for component_id, raw_component in components.items():
        component = _mapping_or_empty(raw_component)
        if component.get("score") is None:
            continue
        available.append(
            (
                _score01(component.get("score"), f"attention.{component_id}.score"),
                component_id,
            )
        )
    return [component_id for _, component_id in sorted(available, reverse=True)[:2]]


def _confidence_label(
    family_count: int,
    positive_skill_setup_count: int,
    attention_completeness: float,
    opposing_count: int,
) -> str:
    if (
        family_count >= 3
        and positive_skill_setup_count >= 1
        and attention_completeness >= 0.75
        and opposing_count == 0
    ):
        return "higher_research_confidence_not_probability"
    if family_count >= 2 and attention_completeness >= 0.5:
        return "moderate_research_confidence_not_probability"
    return "low_research_confidence_needs_diligence"


def _recommendation_state(
    score: float,
    positive_skill_setup_count: int,
    missing_evidence: Sequence[str],
    valuation_gate: str,
) -> str:
    if valuation_gate == "blocked_missing_current_valuation":
        return "screen_flag_missing_current_valuation"
    if valuation_gate == "blocked_insufficient_valuation_evidence":
        return "screen_flag_insufficient_valuation_evidence"
    if valuation_gate == "blocked_valuation_contradiction":
        return "screen_flag_valuation_contradiction"
    if score >= 65.0 and positive_skill_setup_count > 0 and not missing_evidence:
        return "advance_to_deeper_work"
    if score >= 50.0:
        return "watchlist_needs_trigger"
    return "screen_flag_only"


def _category_id(horizon: HorizonBucket, bias: DirectionalBias) -> str:
    return f"{horizon}_{bias}"


def _valuation_context(
    fundamental: Mapping[str, object],
    bias: DirectionalBias,
    horizon: HorizonBucket,
    market_data_as_of: str,
    source_sha256s: frozenset[str],
) -> dict[str, object]:
    if not fundamental:
        return {
            "valuation_status": "missing_current_point_in_time_valuation",
            "valuation_gate": "blocked_missing_current_valuation",
            "valuation_fit_score": 0.0,
            "peer_relative_valuation_support_score": None,
            "growth_adjusted_value_score": None,
            "risk_flags": ["missing_current_point_in_time_valuation"],
            "raw_metrics": {},
            "source_snapshot_sha256": None,
            "as_of_date": None,
            "list_eligible": horizon == "short_term",
            "method": "no_neutral_imputation_missing_valuation_scores_zero",
        }
    required_values = {
        "artifact_type": "equity_fundamental_confirmation",
        "fundamental_status": "real_snapshot_scored",
        "point_in_time_status": "exact_market_frontier_snapshot",
        "future_observation_consumed": False,
        "paper_only": True,
        "live_blocked": True,
        "as_of_date": market_data_as_of,
    }
    mismatches = {
        key: (fundamental.get(key), expected)
        for key, expected in required_values.items()
        if fundamental.get(key) != expected
    }
    if mismatches:
        raise ValueError(
            "valuation evidence violates its point-in-time contract: "
            f"mismatches={mismatches!r}"
        )
    source_sha256 = fundamental.get("source_snapshot_sha256")
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or source_sha256 not in source_sha256s
    ):
        raise ValueError(
            "valuation evidence lacks a source hash bound to the Playbook source manifest: "
            f"source_snapshot_sha256={source_sha256!r}"
        )
    raw_metrics = _mapping(fundamental.get("raw_metrics"), "fundamental.raw_metrics")
    valuation_evidence_status = str(
        fundamental.get("valuation_evidence_status", "unreported")
    )
    if valuation_evidence_status != "peer_relative_scored_sufficient":
        reason_codes = _string_list(fundamental.get("reason_codes"))
        return {
            "valuation_status": valuation_evidence_status,
            "valuation_gate": "blocked_insufficient_valuation_evidence",
            "valuation_fit_score": 0.0,
            "peer_relative_valuation_support_score": None,
            "growth_adjusted_value_score": None,
            "risk_flags": sorted(
                set(["insufficient_current_valuation_evidence", *reason_codes])
            ),
            "raw_metrics": raw_metrics,
            "source_snapshot_sha256": source_sha256,
            "as_of_date": market_data_as_of,
            "list_eligible": horizon == "short_term",
            "valuation_evidence_status": valuation_evidence_status,
            "valuation_peer_counts": _mapping_or_empty(
                fundamental.get("valuation_peer_counts")
            ),
            "method": "no_neutral_imputation_insufficient_valuation_scores_zero",
        }
    valuation_support = _score01(
        fundamental.get("valuation_support_score"),
        "fundamental.valuation_support_score",
    )
    growth = _score01(fundamental.get("growth_score"), "fundamental.growth_score")
    quality = _score01(fundamental.get("quality_score"), "fundamental.quality_score")
    forward_pe = _optional_finite_number(
        raw_metrics.get("forward_pe"), "fundamental.raw_metrics.forward_pe"
    )
    price_to_sales = _optional_finite_number(
        raw_metrics.get("price_to_sales"),
        "fundamental.raw_metrics.price_to_sales",
    )
    profit_margin = _optional_finite_number(
        raw_metrics.get("profit_margin"),
        "fundamental.raw_metrics.profit_margin",
    )
    free_cashflow = _optional_finite_number(
        raw_metrics.get("free_cashflow"),
        "fundamental.raw_metrics.free_cashflow",
    )
    growth_adjusted_value = 0.55 * valuation_support + 0.25 * growth + 0.20 * quality
    if bias == "bullish":
        valuation_fit = (
            0.45 * valuation_support + 0.30 * growth + 0.25 * quality
            if horizon == "short_term"
            else growth_adjusted_value
        )
        contradiction = (
            quality < 0.25
            or (valuation_support < 0.20 and growth < 0.60)
            or (price_to_sales is not None and price_to_sales > 30.0)
            or (forward_pe is not None and forward_pe > 100.0)
            or (
                profit_margin is not None
                and profit_margin < 0.0
                and free_cashflow is not None
                and free_cashflow < 0.0
            )
        )
    else:
        valuation_fit = (
            0.45 * (1.0 - valuation_support)
            + 0.30 * (1.0 - quality)
            + 0.25 * (1.0 - growth)
        )
        contradiction = valuation_support > 0.80 and growth > 0.60 and quality > 0.65
    risk_flags: list[str] = []
    if valuation_support < 0.25:
        risk_flags.append("peer_relative_valuation_stretch")
    if valuation_support < 0.35 and growth < 0.50:
        risk_flags.append("valuation_stretch_not_growth_supported")
    if forward_pe is not None and forward_pe > 60.0:
        risk_flags.append("absolute_forward_pe_extreme")
    if price_to_sales is not None and price_to_sales > 15.0:
        risk_flags.append("absolute_price_to_sales_extreme")
    if profit_margin is not None and profit_margin < 0.0:
        risk_flags.append("negative_profit_margin")
    if free_cashflow is not None and free_cashflow < 0.0:
        risk_flags.append("negative_free_cashflow")
    if contradiction:
        risk_flags.append(f"{bias}_valuation_contradiction")
    valuation_gate = (
        "blocked_valuation_contradiction"
        if contradiction
        else "passed_current_point_in_time_valuation"
    )
    return {
        "valuation_status": "current_point_in_time_peer_relative_valuation",
        "valuation_gate": valuation_gate,
        "valuation_fit_score": round(valuation_fit, 6),
        "peer_relative_valuation_support_score": round(valuation_support, 6),
        "growth_adjusted_value_score": round(growth_adjusted_value, 6),
        "growth_score": round(growth, 6),
        "quality_score": round(quality, 6),
        "risk_flags": sorted(set(risk_flags)),
        "raw_metrics": raw_metrics,
        "source_snapshot_sha256": source_sha256,
        "as_of_date": market_data_as_of,
        "list_eligible": not (horizon == "long_term" and contradiction),
        "method": (
            "peer_relative_forward_pe_and_price_to_sales_with_growth_quality_context; "
            "not_intrinsic_value_or_return_probability"
        ),
    }


def _build_recommendation(
    symbol: str,
    horizon: HorizonBucket,
    bias: DirectionalBias,
    aligned: Sequence[Mapping[str, object]],
    opposing: Sequence[Mapping[str, object]],
    percentiles: Mapping[str, float],
    setup_trust: Mapping[str, object],
    attention: Mapping[str, object],
    universe: Mapping[str, object],
    swing_thesis: Mapping[str, object],
    fundamental: Mapping[str, object],
    market_data_as_of: str,
    source_sha256s: frozenset[str],
) -> dict[str, object]:
    ranked_aligned = sorted(
        aligned,
        key=lambda detection: (
            -percentiles.get(str(detection.get("detection_id", "")), 0.0),
            str(detection.get("setup_id", "")),
        ),
    )
    top_detections = ranked_aligned[:5]
    signal_percentiles = [
        percentiles.get(str(detection.get("detection_id", "")), 0.0)
        for detection in top_detections
    ]
    signal_score = fmean(signal_percentiles) if signal_percentiles else 0.0
    family_count = len(
        {str(row.get("family", "")) for row in aligned if row.get("family")}
    )
    agreement_score = min(family_count / 3.0, 1.0)

    trust_rows: list[tuple[float, str, int, float | None, int, float]] = []
    for detection in top_detections:
        setup_id = str(detection.get("setup_id", ""))
        raw_trust = setup_trust.get(setup_id)
        trust_rows.append(_trust_score(_mapping_or_empty(raw_trust), horizon))
    trust_score = fmean(row[0] for row in trust_rows) if trust_rows else 0.0
    positive_skill_setup_count = sum(1 for row in trust_rows if row[0] > 0.0)

    attention_score = _score01(
        attention.get("attention_score"), f"attention[{symbol}].attention_score"
    )
    completeness = _score01(
        attention.get("completeness_ratio"), f"attention[{symbol}].completeness_ratio"
    )
    selection_score = _score01(
        universe.get("selection_score"), f"universe[{symbol}].selection_score"
    )
    avg_dollar_volume = _finite_number(
        universe.get("avg_dollar_volume_20d"),
        f"universe[{symbol}].avg_dollar_volume_20d",
    )
    liquidity_score = _liquidity_score(avg_dollar_volume)
    directional_support = (
        _directional_support(swing_thesis, bias) if swing_thesis else 0.0
    )
    opposition_penalty = min(len(opposing) / max(len(aligned) + len(opposing), 1), 1.0)
    valuation = _valuation_context(
        fundamental,
        bias,
        horizon,
        market_data_as_of,
        source_sha256s,
    )
    valuation_fit_score = float(cast(float, valuation["valuation_fit_score"]))

    if horizon == "short_term":
        weighted_score = (
            0.29 * signal_score
            + 0.13 * agreement_score
            + 0.14 * trust_score
            + 0.11 * attention_score
            + 0.08 * liquidity_score
            + 0.07 * selection_score
            + 0.10 * directional_support
            + 0.08 * valuation_fit_score
            - 0.15 * opposition_penalty
        )
    else:
        weighted_score = (
            0.21 * signal_score
            + 0.10 * agreement_score
            + 0.12 * trust_score
            + 0.07 * attention_score
            + 0.06 * liquidity_score
            + 0.06 * selection_score
            + 0.16 * directional_support
            + 0.22 * valuation_fit_score
            - 0.15 * opposition_penalty
        )
    research_priority_score = round(min(max(weighted_score, 0.0), 1.0) * 100.0, 2)
    valuation_gate = str(valuation["valuation_gate"])
    if valuation_gate == "blocked_missing_current_valuation":
        research_priority_score = min(research_priority_score, 49.99)
    elif valuation_gate == "blocked_insufficient_valuation_evidence":
        research_priority_score = min(research_priority_score, 47.49)
    elif valuation_gate == "blocked_valuation_contradiction":
        research_priority_score = min(research_priority_score, 44.99)

    missing_evidence = _string_list(attention.get("missing_components"))
    if horizon == "long_term":
        missing_evidence.append("long_term_horizon_not_independently_settled")
    if not swing_thesis:
        missing_evidence.append("equity_swing_thesis_unavailable")
    if positive_skill_setup_count == 0:
        missing_evidence.append("no_positive_horizon_matched_setup_skill")
    if valuation_gate == "blocked_missing_current_valuation":
        missing_evidence.append("current_point_in_time_valuation_unavailable")
    if valuation_gate == "blocked_insufficient_valuation_evidence":
        missing_evidence.append(
            "current_valuation_peer_or_metric_evidence_insufficient"
        )
    if valuation_gate == "blocked_valuation_contradiction":
        missing_evidence.append("direction_conflicts_with_current_valuation_context")
    missing_evidence = sorted(set(missing_evidence))

    category = _category_id(horizon, bias)
    recommendation_id = (
        "playbook-recommendation:"
        + canonical_hash(
            {
                "symbol": symbol,
                "category": category,
                "market_data_as_of": market_data_as_of,
                "detection_ids": [
                    str(row.get("detection_id", "")) for row in top_detections
                ],
                "valuation_source_sha256": valuation.get("source_snapshot_sha256"),
            }
        )[:24]
    )
    attention_drivers = _attention_reasons(attention)
    attention_label = str(
        attention.get("freshness_status", attention.get("status", "unknown"))
    )
    side_word = "bullish" if bias == "bullish" else "bearish"
    horizon_word = "short-term" if horizon == "short_term" else "long-term"

    catalysts: list[dict[str, object]] = []
    earnings_date = swing_thesis.get("earnings_date") if swing_thesis else None
    if isinstance(earnings_date, str) and earnings_date:
        catalysts.append(
            {
                "catalyst_type": "earnings",
                "date": earnings_date,
                "status": "observed_in_governed_earnings_snapshot",
            }
        )

    risks = [
        "research rank is not a calibrated return probability",
        "setup-family trust may change as forward settlements accrue",
    ]
    if bias == "bearish":
        risks.append("bearish stock research cannot synthesize a short-stock order")
    if opposition_penalty > 0.0:
        risks.append("independent playbook detections disagree on direction")
    risks.extend(
        f"valuation risk: {reason}"
        for reason in cast(Sequence[str], valuation["risk_flags"])
    )

    trust_details = [
        {
            "setup_id": str(detection.get("setup_id", "")),
            "source_trust_state": trust_rows[index][1],
            "trust_state": (
                "positive_baseline_relative_skill"
                if trust_rows[index][0] > 0.0
                else "no_positive_horizon_matched_skill"
            ),
            "settled": trust_rows[index][2],
            "scored_observations": trust_rows[index][4],
            "hit_rate": None
            if trust_rows[index][3] is None
            else round(float(trust_rows[index][3]), 4),
            "baseline_relative_skill_vs_50pct": round(trust_rows[index][5], 6),
            "score_contribution_before_weight": round(trust_rows[index][0], 6),
            "horizon_match": (
                "unavailable_no_independent_long_horizon_settlement"
                if horizon == "long_term"
                else "short_horizon_bucket_applicable"
            ),
        }
        for index, detection in enumerate(top_detections)
    ]
    setup_details = [
        {
            "detection_id": str(detection.get("detection_id", "")),
            "setup_id": str(detection.get("setup_id", "")),
            "family": str(detection.get("family", "")),
            "within_setup_percentile": round(
                percentiles.get(str(detection.get("detection_id", "")), 0.0) * 100.0,
                2,
            ),
            "horizon_days": list(detection.get("horizon_days", []))
            if isinstance(detection.get("horizon_days"), (list, tuple))
            else [],
            "details": _mapping_or_empty(detection.get("details")),
            "lineage": _string_list(detection.get("lineage")),
        }
        for detection in top_detections
    ]

    thesis_summary = (
        f"{symbol} surfaced as a {horizon_word} {side_word} research candidate from "
        f"{len(aligned)} aligned detections across {family_count} independent setup families."
    )
    why_now = [
        f"Top within-setup signal percentile: {round(max(signal_percentiles, default=0.0) * 100.0, 1)}.",
        f"Attention priority score: {round(attention_score * 100.0, 1)}; state: {attention_label}.",
        f"Twenty-session average dollar volume: ${avg_dollar_volume:,.0f}.",
    ]
    if attention_drivers:
        why_now.append(
            "Primary attention drivers: " + ", ".join(attention_drivers) + "."
        )
    if valuation_gate == "passed_current_point_in_time_valuation":
        why_now.append(
            "Horizon-aware valuation fit: "
            f"{round(valuation_fit_score * 100.0, 1)}; peer-relative and not intrinsic value."
        )
    else:
        why_now.append("Valuation gate: " + valuation_gate.replace("_", " ") + ".")

    return {
        "recommendation_id": recommendation_id,
        "symbol": symbol,
        "category": category,
        "horizon": horizon,
        "horizon_label": "1-10 trading sessions"
        if horizon == "short_term"
        else "20+ trading sessions",
        "directional_bias": bias,
        "prediction_label": f"{horizon_word}_{side_word}_prediction_research",
        "research_priority_score": research_priority_score,
        "rank_score_is_not_probability": True,
        "recommendation_state": _recommendation_state(
            research_priority_score,
            positive_skill_setup_count,
            missing_evidence,
            valuation_gate,
        ),
        "confidence_label": (
            _confidence_label(
                family_count,
                positive_skill_setup_count,
                completeness,
                len(opposing),
            )
            if valuation_gate == "passed_current_point_in_time_valuation"
            else "low_research_confidence_valuation_gate_blocked"
        ),
        "thesis_summary": thesis_summary,
        "variant_wedge": "not_established_screen_candidate_requires_company_and_expectations_diligence",
        "why_now": why_now,
        "first_rejection": (
            f"{len(opposing)} opposing {horizon_word} detections remain"
            if opposing
            else "no opposing detection in the current governed scan; source and model risk remain"
        ),
        "what_would_make_investable": [
            "fresh company, catalyst, valuation, and expectations evidence",
            "independently settled horizon-matched setup support",
            "continued liquidity and tradability eligibility",
        ],
        "what_would_kill_it": [
            "directional setup agreement reverses",
            "attention or market evidence becomes stale or incomplete",
            "tradability, liquidity, or universe eligibility fails",
        ],
        "catalysts": catalysts,
        "risks": risks,
        "missing_evidence": missing_evidence,
        "score_breakdown": {
            "within_setup_signal": round(signal_score * 100.0, 2),
            "independent_family_agreement": round(agreement_score * 100.0, 2),
            "forward_trust": round(trust_score * 100.0, 2),
            "direction_neutral_attention": round(attention_score * 100.0, 2),
            "liquidity": round(liquidity_score * 100.0, 2),
            "universe_selection": round(selection_score * 100.0, 2),
            "swing_directional_support": round(directional_support * 100.0, 2),
            "valuation_fit": round(valuation_fit_score * 100.0, 2),
            "opposition_penalty": round(opposition_penalty * 100.0, 2),
        },
        "setup_evidence": setup_details,
        "trust_evidence": trust_details,
        "attention_context": {
            "score": round(attention_score * 100.0, 2),
            "status": str(attention.get("status", "unknown")),
            "freshness_status": attention_label,
            "completeness_ratio": round(completeness, 4),
            "drivers": attention_drivers,
            "missing_components": _string_list(attention.get("missing_components")),
            "provenance_sha256": attention.get("provenance_sha256"),
            "directional_use": "research_priority_only_never_direction",
        },
        "tradability": {
            "research_tradable": True,
            "tier": universe.get("resulting_tier"),
            "market_cap": universe.get("market_cap"),
            "avg_dollar_volume_20d": round(avg_dollar_volume, 2),
            "selection_score": round(selection_score * 100.0, 2),
            "reason_codes": _string_list(universe.get("reason_codes")),
            "evidence_hash": universe.get("evidence_hash"),
        },
        "technical_evidence": _mapping_or_empty(
            swing_thesis.get("technical_confirmation")
        ),
        "fundamental_evidence": dict(fundamental),
        "valuation_context": valuation,
        "list_eligible": bool(valuation["list_eligible"]),
        "competing_context": _mapping_or_empty(swing_thesis.get("external_context")),
        "research_invalidation_price": swing_thesis.get("invalidation_price"),
        "market_data_as_of": market_data_as_of,
        "execution_state": "research_ranked_not_execution_instruction",
        "order_construction_allowed": False,
        "trade_promotion_allowed": False,
        "bearish_expression_policy": (
            "directional_research_only; no short-stock order; any loss-limited option expression "
            "requires a separately enabled options gate and independent quote, lifecycle, risk, "
            "paper-twin, and broker-review checks"
        ),
    }


def build_playbook_rankings(
    scan_report: Mapping[str, object],
    trust_report: Mapping[str, object],
    attention_snapshot: Mapping[str, object],
    universe_summary: Mapping[str, object],
    swing_theses: Sequence[Mapping[str, object]],
    fundamental_confirmations: Mapping[str, Mapping[str, object]],
    symbol_dossiers: Sequence[Mapping[str, object]],
    source_artifacts: Sequence[Mapping[str, object]],
    generated_utc: str,
    refresh_interval_minutes: int,
) -> dict[str, object]:
    """Return one content-addressed, non-executable Playbook UI artifact."""

    if scan_report.get("status") != "complete":
        raise ValueError(
            f"playbook scan is not complete: status={scan_report.get('status')!r}"
        )
    detector_error_count = scan_report.get("detector_error_count", 0)
    if (
        isinstance(detector_error_count, bool)
        or not isinstance(detector_error_count, int)
        or detector_error_count != 0
    ):
        raise ValueError(
            "playbook scan contains detector errors and cannot be ranked: "
            f"detector_error_count={detector_error_count!r}"
        )
    if (
        trust_report.get("paper_only") is not True
        or trust_report.get("live_blocked") is not True
    ):
        raise ValueError("playbook trust artifact violates its paper/live boundary")
    if trust_report.get("playbook_trust_version") != PLAYBOOK_TRUST_VERSION:
        raise ValueError(
            "playbook trust artifact has incompatible rating semantics: "
            f"expected={PLAYBOOK_TRUST_VERSION}, "
            f"observed={trust_report.get('playbook_trust_version')!r}"
        )
    if isinstance(refresh_interval_minutes, bool) or refresh_interval_minutes < 60:
        raise ValueError(
            "playbook refresh interval must be an integer of at least 60 minutes"
        )

    generated = _parse_utc(generated_utc, "generated_utc")
    source_rows = [dict(source) for source in source_artifacts]
    source_sha256s = frozenset(
        str(source.get("sha256"))
        for source in source_rows
        if isinstance(source.get("sha256"), str)
    )
    detections = _records(scan_report.get("detections"), "scan.detections")
    attention = _attention_by_symbol(attention_snapshot)
    universe = _universe_by_symbol(universe_summary)
    swing = _swing_by_symbol(swing_theses)
    fundamentals = _fundamentals_by_symbol(fundamental_confirmations)
    roles = _role_by_symbol(symbol_dossiers)
    setup_trust = _mapping(trust_report.get("per_setup"), "trust.per_setup")
    percentiles = _percentile_by_detection(detections)

    eligible_symbols = {
        symbol
        for symbol in universe
        if symbol in attention
        and symbol in roles
        and roles.get(symbol, "")
        not in {"context_only_volatility_index", "index_or_sector_etf"}
    }
    aligned_groups: dict[
        tuple[str, HorizonBucket, DirectionalBias], list[dict[str, object]]
    ] = defaultdict(list)
    all_groups: dict[tuple[str, HorizonBucket], list[dict[str, object]]] = defaultdict(
        list
    )
    market_dates: set[date] = set()
    for detection_index, detection in enumerate(detections):
        symbol = str(detection.get("symbol", "")).upper().strip()
        horizon = _horizon_bucket(detection.get("horizon_days"))
        bias = _directional_bias(detection.get("direction"))
        if symbol not in eligible_symbols or horizon is None or bias is None:
            continue
        as_of_date = _parse_iso_date(
            detection.get("as_of_date"),
            f"scan.detections[{detection_index}].as_of_date",
        )
        market_dates.add(as_of_date)
        aligned_groups[(symbol, horizon, bias)].append(detection)
        all_groups[(symbol, horizon)].append(detection)

    if not market_dates:
        raise ValueError(
            "no eligible directional detections survived playbook source gates"
        )
    attention_as_of = _parse_iso_date(
        attention_snapshot.get("market_as_of_date"),
        "attention.market_as_of_date",
    )
    if market_dates != {attention_as_of}:
        raise ValueError(
            "playbook directional and attention evidence must share one market frontier: "
            f"directional={sorted(value.isoformat() for value in market_dates)!r}, "
            f"attention={attention_as_of.isoformat()!r}"
        )
    market_data_as_of = attention_as_of.isoformat()
    recommendation_rows: list[dict[str, object]] = []
    for (symbol, horizon, bias), aligned in sorted(aligned_groups.items()):
        opposite_bias: DirectionalBias = "bearish" if bias == "bullish" else "bullish"
        opposing = [
            row
            for row in all_groups[(symbol, horizon)]
            if _directional_bias(row.get("direction")) == opposite_bias
        ]
        recommendation_rows.append(
            _build_recommendation(
                symbol,
                horizon,
                bias,
                aligned,
                opposing,
                percentiles,
                setup_trust,
                attention[symbol],
                universe[symbol],
                swing.get(symbol, {}),
                fundamentals.get(symbol, {}),
                market_data_as_of,
                source_sha256s,
            )
        )

    category_ids = (
        "short_term_bullish",
        "short_term_bearish",
        "long_term_bullish",
        "long_term_bearish",
    )
    ranked_by_category: dict[str, list[dict[str, object]]] = {}
    for category in category_ids:
        rows = [
            row
            for row in recommendation_rows
            if row["category"] == category and row["list_eligible"] is True
        ]
        ranked_by_category[category] = sorted(
            rows,
            key=lambda row: (
                -float(cast(float, row["research_priority_score"])),
                str(row["symbol"]),
            ),
        )[:LIST_SIZE]

    recommendations: dict[str, dict[str, object]] = {}
    lists: dict[str, list[str]] = {}
    for category in category_ids:
        ranked = ranked_by_category[category]
        ids: list[str] = []
        for rank, row in enumerate(ranked, start=1):
            record = {**row, "rank": rank}
            recommendation_id = str(record["recommendation_id"])
            recommendations[recommendation_id] = record
            ids.append(recommendation_id)
        lists[category] = ids

    overall_candidates = sorted(
        (
            row
            for row in recommendations.values()
            if _mapping_or_empty(row.get("valuation_context")).get("valuation_gate")
            == "passed_current_point_in_time_valuation"
        ),
        key=lambda row: (
            -float(cast(float, row["research_priority_score"])),
            str(row["symbol"]),
            str(row["category"]),
        ),
    )
    overall_ids: list[str] = []
    seen_symbols: set[str] = set()
    for row in overall_candidates:
        symbol = str(row["symbol"])
        if symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        overall_ids.append(str(row["recommendation_id"]))
        if len(overall_ids) == OVERALL_SIZE:
            break
    lists["overall"] = overall_ids

    missing_counts = {
        category: LIST_SIZE - len(lists[category]) for category in category_ids
    }
    list_status = (
        "complete_research_rankings"
        if all(value == 0 for value in missing_counts.values())
        and len(overall_ids) == OVERALL_SIZE
        else "partial_insufficient_eligible_candidates"
    )
    input_fingerprint = canonical_hash(
        {
            "sources": source_rows,
            "scan_hash": scan_report.get("reproducibility_hash"),
            "attention_hash": attention_snapshot.get("snapshot_sha256"),
            "universe_hash": universe_summary.get("reproducibility_hash"),
            "trust_version": trust_report.get("playbook_trust_version"),
            "fundamental_confirmations_hash": canonical_hash(fundamentals),
        }
    )
    body: dict[str, object] = {
        "artifact_type": "ranked_equity_prediction_playbook",
        "schema_version": PLAYBOOK_RANKING_VERSION,
        "source_playbook_trust_version": PLAYBOOK_TRUST_VERSION,
        "playbook_status": list_status,
        "generated_utc": generated.isoformat(),
        "market_data_as_of": market_data_as_of,
        "attention_as_of": attention_as_of.isoformat(),
        "attention_generated_utc": attention_snapshot.get("generated_at_utc"),
        "refresh_interval_minutes": refresh_interval_minutes,
        "next_refresh_due_utc": (
            generated + timedelta(minutes=refresh_interval_minutes)
        ).isoformat(),
        "universe_active_count": universe_summary.get("active_after"),
        "universe_maximum_count": 500,
        "eligible_single_stock_count": len(eligible_symbols),
        "valuation_covered_symbol_count": sum(
            symbol in fundamentals for symbol in eligible_symbols
        ),
        "long_horizon_valuation_ineligible_count": sum(
            row["horizon"] == "long_term" and row["list_eligible"] is False
            for row in recommendation_rows
        ),
        "lists": lists,
        "missing_slots_by_list": missing_counts,
        "recommendations": recommendations,
        "recommendation_count": len(recommendations),
        "source_artifacts": source_rows,
        "input_fingerprint": input_fingerprint,
        "ranking_method": {
            "direction_source": "independent_price_setup_detections_only",
            "attention_use": "direction_neutral_research_priority_only",
            "strength_normalization": "within_setup_direction_horizon_percentile",
            "cross_setup_raw_strength_compared": False,
            "long_term_trust_independently_settled": False,
            "forward_trust_method": (
                "positive_skill_above_50pct_directional_baseline; unrated_zero; "
                "minimum_30_scored_observations; long_term_zero_until_independently_settled"
            ),
            "valuation_use": "first_class_horizon_aware_directional_fit_and_hard_long_horizon_gate",
            "missing_valuation_neutral_imputation_allowed": False,
            "short_term_valuation_weight": 0.08,
            "long_term_valuation_weight": 0.22,
            "intrinsic_value_claimed": False,
            "weight_calibration_status": "provisional_policy_weights_pending_horizon_matched_forward_ablation",
            "automatic_weight_tuning_allowed": False,
            "calibration_objectives": [
                "directional_brier_score",
                "expected_calibration_error",
                "rank_information_coefficient",
                "net_return_after_costs_by_horizon_and_regime",
                "maximum_drawdown_and_tail_loss",
            ],
            "short_term_weights": {
                "signal": 0.29,
                "agreement": 0.13,
                "forward_trust": 0.14,
                "attention": 0.11,
                "liquidity": 0.08,
                "universe": 0.07,
                "swing_directional_support": 0.10,
                "valuation": 0.08,
            },
            "long_term_weights": {
                "signal": 0.21,
                "agreement": 0.10,
                "forward_trust": 0.12,
                "attention": 0.07,
                "liquidity": 0.06,
                "universe": 0.06,
                "swing_directional_support": 0.16,
                "valuation": 0.22,
            },
            "rank_score_is_not_probability": True,
            "no_padding_when_insufficient": True,
        },
        "display_language": {
            "short_term_bullish": "Short-term bullish prediction research",
            "short_term_bearish": "Short-term bearish prediction research",
            "long_term_bullish": "Long-term bullish prediction research",
            "long_term_bearish": "Long-term bearish prediction research",
            "overall": "Top overall research plays",
            "boundary": "Research-ranked; not an execution instruction",
        },
        "rank_score_is_not_probability": True,
        "order_construction_allowed": False,
        "trade_promotion_allowed": False,
        "live_execution_allowed": False,
        "broker_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    return {**body, "content_hash": content_hash, "reproducibility_hash": content_hash}
