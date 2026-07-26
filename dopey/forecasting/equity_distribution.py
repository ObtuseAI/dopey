"""Past-only empirical equity price distributions with prequential diagnostics.

This module deliberately does not turn chart levels or heuristic scores into
probabilities. It finds non-overlapping historical observations from the same
explicitly defined market regime, estimates a weighted empirical return
distribution, and reports how that procedure behaved when replayed using only
information known at each historical decision time.

The intervals are historical analogue quantiles. They are not conformal
intervals and carry no finite-sample coverage guarantee.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import TypedDict, cast

from dopey.protocols.identity import canonical_hash


EQUITY_DISTRIBUTION_FORECAST_VERSION = "dopey-equity-distribution-forecast-v2"


class EquityPriceBar(TypedDict):
    date: str
    close: float
    adjusted_close: float
    volume: int


@dataclass(frozen=True)
class EquityForecastPolicy:
    horizon_trading_days: int
    short_lookback: int
    medium_lookback: int
    long_lookback: int
    maximum_analogue_count: int
    minimum_analogue_count: int
    minimum_effective_sample_size: float
    minimum_active_feature_count: int
    recency_half_life_observations: int
    lower_interval_quantile: float
    upper_interval_quantile: float
    neutral_log_return_band: float
    minimum_diagnostic_predictions: int
    maximum_diagnostic_predictions: int


class EquityForecastPolicyRecord(TypedDict):
    horizon_trading_days: int
    short_lookback: int
    medium_lookback: int
    long_lookback: int
    maximum_analogue_count: int
    minimum_analogue_count: int
    minimum_effective_sample_size: float
    minimum_active_feature_count: int
    recency_half_life_observations: int
    lower_interval_quantile: float
    upper_interval_quantile: float
    neutral_log_return_band: float
    minimum_diagnostic_predictions: int
    maximum_diagnostic_predictions: int


class ForecastQuantile(TypedDict):
    quantile: float
    log_return: float
    price: float


class EmpiricalDirectionalMass(TypedDict):
    bearish: float
    neutral: float
    bullish: float
    method: str
    calibrated_probability_claimed: bool


class PriceDistribution(TypedDict):
    reference_price: float
    weighted_expected_price: float
    weighted_expected_simple_return: float
    weighted_expected_log_return: float
    median_log_return: float
    interval_width_pct_of_reference: float
    return_and_price_quantiles: tuple[ForecastQuantile, ...]
    directional_empirical_mass: EmpiricalDirectionalMass
    benchmark_weighted_expected_log_return: float
    benchmark_median_log_return: float
    rolling_beta_to_benchmark: float
    beta_scaled_benchmark_baseline_median_log_return: float
    benchmark_relative_median_log_return: float
    baseline_selection_uses_subject_regime_and_features: bool
    analogue_effective_sample_size: float
    interval_method: str
    conformal_method_claimed: bool
    exchangeability_assumed: bool
    finite_sample_coverage_guaranteed: bool


class PointForecastGuardrail(TypedDict):
    guardrail_status: str
    selected_method: str
    selected_log_return: float | None
    selected_price: float | None
    selection_reason: str
    prequential_mae_skill_vs_beta_scaled_benchmark: float | None
    selection_uses_only_past_prequential_diagnostics: bool
    accuracy_improvement_claimed: bool


class AnalogueRecord(TypedDict):
    observation_date: str
    label_end_date: str
    regime_id: str
    distance: float
    normalized_weight: float
    subject_forward_log_return: float
    benchmark_forward_log_return: float


class AnalogueEvidence(TypedDict):
    current_regime_id: str
    eligible_same_regime_count: int
    selected_non_overlapping_count: int
    overlap_purged_count: int
    active_feature_count: int
    active_feature_names: tuple[str, ...]
    analogue_count_required: int
    effective_sample_size_required: float
    selected_analogues: tuple[AnalogueRecord, ...]
    labels_strictly_precede_forecast: bool
    overlapping_label_windows_selected: bool


class RegimeDiagnostic(TypedDict):
    regime_id: str
    prediction_count: int
    observed_interval_coverage: float
    mean_absolute_log_return_error: float
    beta_scaled_benchmark_mean_absolute_log_return_error: float


class PrequentialDiagnostics(TypedDict):
    diagnostic_status: str
    prediction_count: int
    minimum_prediction_count: int
    first_prediction_date: str | None
    last_prediction_date: str | None
    nominal_interval_coverage: float
    observed_interval_coverage: float | None
    mean_absolute_log_return_error: float | None
    beta_scaled_benchmark_mean_absolute_log_return_error: float | None
    mae_skill_vs_beta_scaled_benchmark: float | None
    directional_accuracy: float | None
    beta_scaled_benchmark_directional_accuracy: float | None
    mean_absolute_benchmark_relative_error: float | None
    mean_multiclass_brier_score: float | None
    beta_scaled_benchmark_mean_multiclass_brier_score: float | None
    uniform_mean_multiclass_brier_score: float | None
    brier_skill_vs_beta_scaled_benchmark: float | None
    brier_skill_vs_uniform: float | None
    mean_multiclass_log_loss: float | None
    beta_scaled_benchmark_mean_multiclass_log_loss: float | None
    uniform_mean_multiclass_log_loss: float | None
    log_loss_skill_vs_beta_scaled_benchmark: float | None
    log_loss_skill_vs_uniform: float | None
    proper_score_probability_method: str
    proper_scores_are_prequential: bool
    overlapping_diagnostic_label_windows_scored: bool
    regime_diagnostics: tuple[RegimeDiagnostic, ...]
    training_labels_strictly_precede_each_prediction: bool
    same_or_future_outcomes_used_for_training: bool
    coverage_diagnostic_only: bool
    coverage_guarantee_claimed: bool
    promotion_allowed: bool


class EquityDistributionForecast(TypedDict):
    artifact_type: str
    version: str
    forecast_status: str
    symbol: str
    benchmark_symbol: str
    as_of_date: str
    horizon_trading_days: int
    aligned_history_count: int
    aligned_history_first_date: str
    aligned_history_last_date: str
    subject_source_id: str
    benchmark_source_id: str
    policy: EquityForecastPolicyRecord
    feature_names: tuple[str, ...]
    price_distribution: PriceDistribution | None
    point_forecast_guardrail: PointForecastGuardrail
    analogue_evidence: AnalogueEvidence
    prequential_diagnostics: PrequentialDiagnostics
    input_rows_modified: bool
    uses_provider_close_for_price_return_measurement: bool
    adjusted_close_used_for_price_target: bool
    corporate_action_semantics_validated: bool
    historical_option_evidence_consumed: bool
    not_edge_evidence: bool
    not_trade_decision: bool
    strategy_promotion_allowed: bool
    order_construction_allowed: bool
    paper_only: bool
    live_blocked: bool
    reproducibility_hash: str


@dataclass(frozen=True)
class _AlignedBar:
    date: date
    subject_close: float
    subject_volume: int
    benchmark_close: float


@dataclass(frozen=True)
class _FeatureSnapshot:
    observation_index: int
    observation_date: date
    regime_id: str
    values: tuple[float, ...]
    rolling_beta: float


@dataclass(frozen=True)
class _LabeledAnchor:
    snapshot: _FeatureSnapshot
    label_start_index: int
    label_end_index: int
    label_end_date: date
    subject_forward_log_return: float
    benchmark_forward_log_return: float


@dataclass(frozen=True)
class _SelectedAnalogue:
    anchor: _LabeledAnchor
    distance: float
    normalized_weight: float


@dataclass(frozen=True)
class _AnalogueSelection:
    current_regime_id: str
    eligible_same_regime_count: int
    overlap_purged_count: int
    active_feature_names: tuple[str, ...]
    selected: tuple[_SelectedAnalogue, ...]


@dataclass(frozen=True)
class _Distribution:
    log_return_quantiles: tuple[tuple[float, float], ...]
    expected_subject_log_return: float
    expected_subject_price_multiple: float
    expected_benchmark_log_return: float
    median_benchmark_log_return: float
    effective_sample_size: float
    bearish_mass: float
    neutral_mass: float
    bullish_mass: float


@dataclass(frozen=True)
class _DiagnosticObservation:
    observation_date: date
    regime_id: str
    interval_hit: bool
    model_absolute_error: float
    baseline_absolute_error: float
    model_direction_correct: bool
    baseline_direction_correct: bool
    benchmark_relative_absolute_error: float
    model_brier_score: float
    baseline_brier_score: float
    uniform_brier_score: float
    model_log_loss: float
    baseline_log_loss: float
    uniform_log_loss: float


_FEATURE_NAMES: tuple[str, ...] = (
    "subject_short_log_return",
    "subject_medium_log_return",
    "subject_long_log_return",
    "subject_medium_realized_volatility",
    "subject_long_realized_volatility",
    "subject_long_drawdown",
    "subject_volume_log_ratio",
    "benchmark_medium_log_return",
    "benchmark_long_log_return",
    "benchmark_medium_realized_volatility",
    "relative_medium_log_return",
    "relative_long_log_return",
    "rolling_beta_to_benchmark",
    "rolling_correlation_to_benchmark",
)


def canonical_equity_forecast_policy() -> EquityForecastPolicy:
    """Return the explicit v1 research policy used by the operator adapter."""

    return EquityForecastPolicy(
        horizon_trading_days=10,
        short_lookback=5,
        medium_lookback=20,
        long_lookback=60,
        maximum_analogue_count=30,
        minimum_analogue_count=12,
        minimum_effective_sample_size=6.0,
        minimum_active_feature_count=8,
        recency_half_life_observations=1260,
        lower_interval_quantile=0.1,
        upper_interval_quantile=0.9,
        neutral_log_return_band=0.005,
        minimum_diagnostic_predictions=30,
        maximum_diagnostic_predictions=60,
    )


def short_horizon_equity_forecast_policy(
    horizon_trading_days: int,
) -> EquityForecastPolicy:
    """Return the stricter policy for one-to-five-session forecasts.

    Each horizon is independently replayed and scored. Results from one horizon
    are never treated as evidence for another horizon or for an option payoff.
    """
    if horizon_trading_days < 1 or horizon_trading_days > 5:
        raise ValueError(
            "short-horizon equity forecast requires one through five trading "
            f"days: horizon_trading_days={horizon_trading_days}"
        )
    neutral_band = 0.005 * math.sqrt(horizon_trading_days / 10.0)
    return EquityForecastPolicy(
        horizon_trading_days=horizon_trading_days,
        short_lookback=5,
        medium_lookback=20,
        long_lookback=60,
        maximum_analogue_count=60,
        minimum_analogue_count=20,
        minimum_effective_sample_size=10.0,
        minimum_active_feature_count=8,
        recency_half_life_observations=1260,
        lower_interval_quantile=0.1,
        upper_interval_quantile=0.9,
        neutral_log_return_band=neutral_band,
        minimum_diagnostic_predictions=60,
        maximum_diagnostic_predictions=120,
    )


def _policy_record(policy: EquityForecastPolicy) -> EquityForecastPolicyRecord:
    return {
        "horizon_trading_days": policy.horizon_trading_days,
        "short_lookback": policy.short_lookback,
        "medium_lookback": policy.medium_lookback,
        "long_lookback": policy.long_lookback,
        "maximum_analogue_count": policy.maximum_analogue_count,
        "minimum_analogue_count": policy.minimum_analogue_count,
        "minimum_effective_sample_size": policy.minimum_effective_sample_size,
        "minimum_active_feature_count": policy.minimum_active_feature_count,
        "recency_half_life_observations": policy.recency_half_life_observations,
        "lower_interval_quantile": policy.lower_interval_quantile,
        "upper_interval_quantile": policy.upper_interval_quantile,
        "neutral_log_return_band": policy.neutral_log_return_band,
        "minimum_diagnostic_predictions": policy.minimum_diagnostic_predictions,
        "maximum_diagnostic_predictions": policy.maximum_diagnostic_predictions,
    }


def build_equity_distribution_forecast(
    symbol: str,
    subject_rows: Sequence[EquityPriceBar],
    subject_source_id: str,
    benchmark_symbol: str,
    benchmark_rows: Sequence[EquityPriceBar],
    benchmark_source_id: str,
    as_of_date: str,
    policy: EquityForecastPolicy,
) -> EquityDistributionForecast:
    """Build one deterministic, research-only equity return distribution."""

    normalized_symbol = _validated_identity(symbol, "symbol")
    normalized_benchmark = _validated_identity(benchmark_symbol, "benchmark_symbol")
    _validated_identity(subject_source_id, "subject_source_id")
    _validated_identity(benchmark_source_id, "benchmark_source_id")
    as_of = _parse_date(as_of_date, "as_of_date")
    _validate_policy(policy)
    aligned = _align_history(subject_rows, benchmark_rows, as_of)
    minimum_history = policy.long_lookback + policy.horizon_trading_days + 1
    if len(aligned) < minimum_history:
        return _abstention_forecast(
            normalized_symbol,
            normalized_benchmark,
            as_of,
            subject_source_id,
            benchmark_source_id,
            aligned,
            policy,
            "abstain_insufficient_aligned_history",
            _empty_analogue_evidence(policy, "unknown"),
            _empty_diagnostics(policy),
        )
    current_snapshot = _feature_snapshot(aligned, len(aligned) - 1, policy)
    if current_snapshot is None:
        return _abstention_forecast(
            normalized_symbol,
            normalized_benchmark,
            as_of,
            subject_source_id,
            benchmark_source_id,
            aligned,
            policy,
            "abstain_unidentifiable_current_market_features",
            _empty_analogue_evidence(policy, "unknown"),
            _empty_diagnostics(policy),
        )
    anchors = _labeled_anchors(aligned, policy)
    diagnostics = _build_prequential_diagnostics(anchors, policy)
    eligible = tuple(
        anchor
        for anchor in anchors
        if anchor.label_end_index < current_snapshot.observation_index
    )
    selection = _select_analogues(current_snapshot, eligible, policy)
    analogue_evidence = _analogue_evidence(selection, policy)
    if len(selection.selected) < policy.minimum_analogue_count:
        return _abstention_forecast(
            normalized_symbol,
            normalized_benchmark,
            as_of,
            subject_source_id,
            benchmark_source_id,
            aligned,
            policy,
            "abstain_insufficient_same_regime_non_overlapping_analogues",
            analogue_evidence,
            diagnostics,
        )
    distribution = _distribution(selection.selected, policy)
    if distribution.effective_sample_size < policy.minimum_effective_sample_size:
        return _abstention_forecast(
            normalized_symbol,
            normalized_benchmark,
            as_of,
            subject_source_id,
            benchmark_source_id,
            aligned,
            policy,
            "abstain_insufficient_effective_analogue_sample",
            analogue_evidence,
            diagnostics,
        )
    price_distribution = _price_distribution(
        aligned[-1].subject_close,
        current_snapshot.rolling_beta,
        distribution,
    )
    body = _forecast_body(
        normalized_symbol,
        normalized_benchmark,
        as_of,
        subject_source_id,
        benchmark_source_id,
        aligned,
        policy,
        "research_distribution_available_no_edge_or_coverage_claim",
        price_distribution,
        analogue_evidence,
        diagnostics,
    )
    return cast(
        EquityDistributionForecast,
        {**body, "reproducibility_hash": canonical_hash(body)},
    )


def _validated_identity(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(
            f"equity forecast requires non-empty identity: field={field_name}"
        )
    return normalized.upper() if field_name.endswith("symbol") else normalized


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"equity forecast date must be ISO-8601: field={field_name}, value={value}"
        ) from error


def _validate_policy(policy: EquityForecastPolicy) -> None:
    positive_integers = {
        "horizon_trading_days": policy.horizon_trading_days,
        "short_lookback": policy.short_lookback,
        "medium_lookback": policy.medium_lookback,
        "long_lookback": policy.long_lookback,
        "maximum_analogue_count": policy.maximum_analogue_count,
        "minimum_analogue_count": policy.minimum_analogue_count,
        "minimum_active_feature_count": policy.minimum_active_feature_count,
        "recency_half_life_observations": policy.recency_half_life_observations,
        "minimum_diagnostic_predictions": policy.minimum_diagnostic_predictions,
        "maximum_diagnostic_predictions": policy.maximum_diagnostic_predictions,
    }
    invalid = {name: value for name, value in positive_integers.items() if value <= 0}
    if invalid:
        raise ValueError(
            f"equity forecast policy values must be positive: invalid={invalid}"
        )
    if not policy.short_lookback < policy.medium_lookback < policy.long_lookback:
        raise ValueError(
            "equity forecast lookbacks must be strictly increasing: "
            f"short={policy.short_lookback}, medium={policy.medium_lookback}, long={policy.long_lookback}"
        )
    if policy.minimum_analogue_count > policy.maximum_analogue_count:
        raise ValueError(
            "minimum analogue count cannot exceed maximum: "
            f"minimum={policy.minimum_analogue_count}, maximum={policy.maximum_analogue_count}"
        )
    if not (
        math.isfinite(policy.minimum_effective_sample_size)
        and 0.0 < policy.minimum_effective_sample_size <= policy.maximum_analogue_count
    ):
        raise ValueError(
            "minimum effective sample size must be finite, positive, and cannot exceed maximum analogue count: "
            f"effective={policy.minimum_effective_sample_size}, maximum={policy.maximum_analogue_count}"
        )
    if policy.minimum_active_feature_count > len(_FEATURE_NAMES):
        raise ValueError(
            "minimum active feature count exceeds available features: "
            f"minimum={policy.minimum_active_feature_count}, available={len(_FEATURE_NAMES)}"
        )
    if not 0.0 < policy.lower_interval_quantile < 0.5:
        raise ValueError(
            "lower interval quantile must be between zero and one half: "
            f"value={policy.lower_interval_quantile}"
        )
    if not 0.5 < policy.upper_interval_quantile < 1.0:
        raise ValueError(
            "upper interval quantile must be between one half and one: "
            f"value={policy.upper_interval_quantile}"
        )
    if (
        not math.isfinite(policy.neutral_log_return_band)
        or not 0.0 <= policy.neutral_log_return_band <= 0.5
    ):
        raise ValueError(
            "neutral log-return band must be finite and within [0, 0.5]: "
            f"value={policy.neutral_log_return_band}"
        )
    if policy.minimum_diagnostic_predictions > policy.maximum_diagnostic_predictions:
        raise ValueError(
            "minimum diagnostic predictions cannot exceed maximum: "
            f"minimum={policy.minimum_diagnostic_predictions}, maximum={policy.maximum_diagnostic_predictions}"
        )


def _validated_rows(
    rows: Sequence[EquityPriceBar],
    field_name: str,
    as_of: date,
) -> tuple[tuple[date, float, float, int], ...]:
    output: list[tuple[date, float, float, int]] = []
    previous_date: date | None = None
    for row_number, row in enumerate(rows, start=1):
        row_date = _parse_date(str(row["date"]), f"{field_name}[{row_number}].date")
        if previous_date is not None and row_date <= previous_date:
            raise ValueError(
                "equity forecast rows must be unique and strictly chronological: "
                f"field={field_name}, row_number={row_number}, date={row_date.isoformat()}"
            )
        previous_date = row_date
        if row_date > as_of:
            continue
        close = float(row["close"])
        adjusted_close = float(row["adjusted_close"])
        raw_volume = float(row["volume"])
        volume = int(raw_volume)
        if (
            not math.isfinite(close)
            or not math.isfinite(adjusted_close)
            or close <= 0.0
            or adjusted_close <= 0.0
        ):
            raise ValueError(
                "equity forecast prices must be finite and positive: "
                f"field={field_name}, date={row_date.isoformat()}, close={close}, adjusted_close={adjusted_close}"
            )
        if not math.isfinite(raw_volume) or raw_volume < 0.0 or raw_volume != volume:
            raise ValueError(
                "equity forecast volume must be a nonnegative integer: "
                f"field={field_name}, date={row_date.isoformat()}, volume={raw_volume}"
            )
        output.append((row_date, close, adjusted_close, volume))
    return tuple(output)


def _align_history(
    subject_rows: Sequence[EquityPriceBar],
    benchmark_rows: Sequence[EquityPriceBar],
    as_of: date,
) -> tuple[_AlignedBar, ...]:
    subject = _validated_rows(subject_rows, "subject_rows", as_of)
    benchmark = _validated_rows(benchmark_rows, "benchmark_rows", as_of)
    subject_by_date = {row[0]: row for row in subject}
    benchmark_by_date = {row[0]: row for row in benchmark}
    common_dates = tuple(sorted(set(subject_by_date).intersection(benchmark_by_date)))
    if as_of not in common_dates:
        raise ValueError(
            "equity forecast as-of date must exist in both subject and benchmark histories: "
            f"as_of_date={as_of.isoformat()}"
        )
    return tuple(
        _AlignedBar(
            date=row_date,
            subject_close=subject_by_date[row_date][1],
            subject_volume=subject_by_date[row_date][3],
            benchmark_close=benchmark_by_date[row_date][1],
        )
        for row_date in common_dates
    )


def _log_return(values: Sequence[float], end_index: int, lookback: int) -> float:
    return math.log(values[end_index] / values[end_index - lookback])


def _sample_deviation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError(
            "rolling covariance requires equal samples with at least two observations: "
            f"left={len(left)}, right={len(right)}"
        )
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    return sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    ) / (len(left) - 1)


def _feature_snapshot(
    rows: Sequence[_AlignedBar],
    index: int,
    policy: EquityForecastPolicy,
) -> _FeatureSnapshot | None:
    if index < policy.long_lookback:
        return None
    subject_prices = tuple(row.subject_close for row in rows)
    benchmark_prices = tuple(row.benchmark_close for row in rows)
    subject_daily = tuple(
        math.log(subject_prices[position] / subject_prices[position - 1])
        for position in range(index - policy.long_lookback + 1, index + 1)
    )
    benchmark_daily = tuple(
        math.log(benchmark_prices[position] / benchmark_prices[position - 1])
        for position in range(index - policy.long_lookback + 1, index + 1)
    )
    benchmark_deviation = _sample_deviation(benchmark_daily)
    subject_deviation = _sample_deviation(subject_daily)
    benchmark_variance = benchmark_deviation**2
    if benchmark_variance <= 0.0 or subject_deviation <= 0.0:
        return None
    covariance = _covariance(subject_daily, benchmark_daily)
    beta = covariance / benchmark_variance
    correlation = covariance / (subject_deviation * benchmark_deviation)
    subject_short = _log_return(subject_prices, index, policy.short_lookback)
    subject_medium = _log_return(subject_prices, index, policy.medium_lookback)
    subject_long = _log_return(subject_prices, index, policy.long_lookback)
    benchmark_medium = _log_return(benchmark_prices, index, policy.medium_lookback)
    benchmark_long = _log_return(benchmark_prices, index, policy.long_lookback)
    subject_medium_volatility = _sample_deviation(
        subject_daily[-policy.medium_lookback :]
    )
    benchmark_medium_volatility = _sample_deviation(
        benchmark_daily[-policy.medium_lookback :]
    )
    peak = max(subject_prices[index - policy.long_lookback : index + 1])
    drawdown = math.log(subject_prices[index] / peak)
    prior_volumes = tuple(
        rows[position].subject_volume
        for position in range(index - policy.medium_lookback, index)
    )
    volume_ratio = math.log(
        (rows[index].subject_volume + 1.0) / (median(prior_volumes) + 1.0)
    )
    values = (
        subject_short,
        subject_medium,
        subject_long,
        subject_medium_volatility,
        subject_deviation,
        drawdown,
        volume_ratio,
        benchmark_medium,
        benchmark_long,
        benchmark_medium_volatility,
        subject_medium - beta * benchmark_medium,
        subject_long - beta * benchmark_long,
        beta,
        max(-1.0, min(1.0, correlation)),
    )
    if not all(math.isfinite(value) for value in values):
        return None
    regime_id = "|".join(
        (
            "benchmark_up" if benchmark_long >= 0.0 else "benchmark_down",
            "vol_expanding"
            if benchmark_medium_volatility > benchmark_deviation
            else "vol_stable_or_contracting",
            "relative_strong" if values[10] >= 0.0 else "relative_weak",
        )
    )
    return _FeatureSnapshot(index, rows[index].date, regime_id, values, beta)


def _labeled_anchors(
    rows: Sequence[_AlignedBar],
    policy: EquityForecastPolicy,
) -> tuple[_LabeledAnchor, ...]:
    anchors: list[_LabeledAnchor] = []
    for index in range(policy.long_lookback, len(rows) - policy.horizon_trading_days):
        snapshot = _feature_snapshot(rows, index, policy)
        if snapshot is None:
            continue
        label_end_index = index + policy.horizon_trading_days
        anchors.append(
            _LabeledAnchor(
                snapshot,
                index + 1,
                label_end_index,
                rows[label_end_index].date,
                math.log(
                    rows[label_end_index].subject_close / rows[index].subject_close
                ),
                math.log(
                    rows[label_end_index].benchmark_close / rows[index].benchmark_close
                ),
            )
        )
    return tuple(anchors)


def _robust_feature_scales(
    anchors: Sequence[_LabeledAnchor],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[int, ...]]:
    centers: list[float] = []
    scales: list[float] = []
    active_indexes: list[int] = []
    for feature_index in range(len(_FEATURE_NAMES)):
        values = tuple(anchor.snapshot.values[feature_index] for anchor in anchors)
        center = median(values)
        scale = 1.4826 * median(tuple(abs(value - center) for value in values))
        centers.append(center)
        scales.append(scale)
        if scale > 1e-12:
            active_indexes.append(feature_index)
    return tuple(centers), tuple(scales), tuple(active_indexes)


def _distance(
    current: _FeatureSnapshot,
    candidate: _FeatureSnapshot,
    centers: Sequence[float],
    scales: Sequence[float],
    active_indexes: Sequence[int],
) -> float:
    squared = sum(
        (
            ((current.values[index] - centers[index]) / scales[index])
            - ((candidate.values[index] - centers[index]) / scales[index])
        )
        ** 2
        for index in active_indexes
    )
    return math.sqrt(squared / len(active_indexes))


def _intervals_overlap(left: _LabeledAnchor, right: _LabeledAnchor) -> bool:
    return not (
        left.label_end_index < right.label_start_index
        or right.label_end_index < left.label_start_index
    )


def _select_analogues(
    current: _FeatureSnapshot,
    eligible: Sequence[_LabeledAnchor],
    policy: EquityForecastPolicy,
) -> _AnalogueSelection:
    same_regime = tuple(
        anchor for anchor in eligible if anchor.snapshot.regime_id == current.regime_id
    )
    if len(same_regime) < policy.minimum_analogue_count:
        return _AnalogueSelection(current.regime_id, len(same_regime), 0, (), ())
    centers, scales, active_indexes = _robust_feature_scales(same_regime)
    active_names = tuple(_FEATURE_NAMES[index] for index in active_indexes)
    if len(active_indexes) < policy.minimum_active_feature_count:
        return _AnalogueSelection(
            current.regime_id, len(same_regime), 0, active_names, ()
        )
    ranked = list(
        (
            _distance(current, anchor.snapshot, centers, scales, active_indexes),
            anchor,
        )
        for anchor in same_regime
    )
    ranked.sort(
        key=lambda record: (
            record[0],
            -record[1].snapshot.observation_index,
            record[1].snapshot.observation_date,
        )
    )
    selected: list[tuple[float, _LabeledAnchor]] = []
    overlap_purged_count = 0
    for distance, anchor in ranked:
        if any(_intervals_overlap(anchor, existing[1]) for existing in selected):
            overlap_purged_count += 1
            continue
        selected.append((distance, anchor))
        if len(selected) == policy.maximum_analogue_count:
            break
    raw = tuple(
        (
            anchor,
            distance,
            (1.0 / (1.0 + distance))
            * 0.5
            ** (
                (current.observation_index - anchor.snapshot.observation_index)
                / policy.recency_half_life_observations
            ),
        )
        for distance, anchor in selected
    )
    weight_total = sum(record[2] for record in raw)
    if weight_total <= 0.0:
        return _AnalogueSelection(
            current.regime_id, len(same_regime), overlap_purged_count, active_names, ()
        )
    normalized = tuple(
        _SelectedAnalogue(anchor, distance, raw_weight / weight_total)
        for anchor, distance, raw_weight in raw
    )
    return _AnalogueSelection(
        current.regime_id,
        len(same_regime),
        overlap_purged_count,
        active_names,
        normalized,
    )


def _weighted_quantile(
    values_and_weights: Sequence[tuple[float, float]],
    quantile: float,
) -> float:
    if not values_and_weights:
        raise ValueError("weighted quantile requires at least one observation")
    ordered = sorted(values_and_weights, key=lambda record: record[0])
    threshold = quantile * sum(record[1] for record in ordered)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _distribution(
    selected: Sequence[_SelectedAnalogue],
    policy: EquityForecastPolicy,
) -> _Distribution:
    subject = tuple(
        (record.anchor.subject_forward_log_return, record.normalized_weight)
        for record in selected
    )
    benchmark = tuple(
        (record.anchor.benchmark_forward_log_return, record.normalized_weight)
        for record in selected
    )
    quantile_levels = tuple(
        sorted(
            {
                policy.lower_interval_quantile,
                0.25,
                0.5,
                0.75,
                policy.upper_interval_quantile,
            }
        )
    )
    quantiles = tuple(
        (quantile, _weighted_quantile(subject, quantile))
        for quantile in quantile_levels
    )
    bearish_mass, neutral_mass, bullish_mass = _weighted_directional_mass(
        subject, policy.neutral_log_return_band
    )
    return _Distribution(
        quantiles,
        sum(value * weight for value, weight in subject),
        sum(math.exp(value) * weight for value, weight in subject),
        sum(value * weight for value, weight in benchmark),
        _weighted_quantile(benchmark, 0.5),
        1.0 / sum(record.normalized_weight**2 for record in selected),
        bearish_mass,
        neutral_mass,
        bullish_mass,
    )


def _weighted_directional_mass(
    values_and_weights: Sequence[tuple[float, float]],
    neutral_band: float,
) -> tuple[float, float, float]:
    bearish = sum(
        weight for value, weight in values_and_weights if value < -neutral_band
    )
    bullish = sum(
        weight for value, weight in values_and_weights if value > neutral_band
    )
    return bearish, max(0.0, 1.0 - bearish - bullish), bullish


def _laplace_smoothed_probabilities(
    masses: tuple[float, float, float],
    effective_sample_size: float,
) -> tuple[float, float, float]:
    denominator = effective_sample_size + 3.0
    probabilities = tuple(
        (mass * effective_sample_size + 1.0) / denominator for mass in masses
    )
    return cast(tuple[float, float, float], probabilities)


def _proper_scores(
    probabilities: tuple[float, float, float],
    realized_direction: int,
) -> tuple[float, float]:
    realized_index = realized_direction + 1
    brier = sum(
        (probability - (1.0 if index == realized_index else 0.0)) ** 2
        for index, probability in enumerate(probabilities)
    ) / len(probabilities)
    log_loss = -math.log(max(probabilities[realized_index], 1e-12))
    return brier, log_loss


def _price_distribution(
    current_price: float,
    rolling_beta: float,
    distribution: _Distribution,
) -> PriceDistribution:
    quantiles = tuple(
        ForecastQuantile(
            quantile=round(quantile, 6),
            log_return=round(log_return, 8),
            price=round(current_price * math.exp(log_return), 6),
        )
        for quantile, log_return in distribution.log_return_quantiles
    )
    median_log_return = next(
        value
        for quantile, value in distribution.log_return_quantiles
        if quantile == 0.5
    )
    benchmark_baseline = rolling_beta * distribution.median_benchmark_log_return
    return {
        "reference_price": round(current_price, 6),
        "weighted_expected_price": round(
            current_price * distribution.expected_subject_price_multiple, 6
        ),
        "weighted_expected_simple_return": round(
            distribution.expected_subject_price_multiple - 1.0, 8
        ),
        "weighted_expected_log_return": round(
            distribution.expected_subject_log_return, 8
        ),
        "median_log_return": round(median_log_return, 8),
        "interval_width_pct_of_reference": round(
            (quantiles[-1]["price"] - quantiles[0]["price"]) / current_price, 8
        ),
        "return_and_price_quantiles": quantiles,
        "directional_empirical_mass": {
            "bearish": round(distribution.bearish_mass, 8),
            "neutral": round(distribution.neutral_mass, 8),
            "bullish": round(distribution.bullish_mass, 8),
            "method": "weighted_historical_analogue_mass_not_calibrated_probability",
            "calibrated_probability_claimed": False,
        },
        "benchmark_weighted_expected_log_return": round(
            distribution.expected_benchmark_log_return, 8
        ),
        "benchmark_median_log_return": round(
            distribution.median_benchmark_log_return, 8
        ),
        "rolling_beta_to_benchmark": round(rolling_beta, 8),
        "beta_scaled_benchmark_baseline_median_log_return": round(
            benchmark_baseline, 8
        ),
        "benchmark_relative_median_log_return": round(
            median_log_return - benchmark_baseline, 8
        ),
        "baseline_selection_uses_subject_regime_and_features": True,
        "analogue_effective_sample_size": round(distribution.effective_sample_size, 8),
        "interval_method": "recency_similarity_weighted_same_regime_historical_analogue_quantiles",
        "conformal_method_claimed": False,
        "exchangeability_assumed": False,
        "finite_sample_coverage_guaranteed": False,
    }


def _direction(value: float, neutral_band: float) -> int:
    if value > neutral_band:
        return 1
    if value < -neutral_band:
        return -1
    return 0


def _diagnostic_observations(
    anchors: Sequence[_LabeledAnchor],
    policy: EquityForecastPolicy,
) -> tuple[_DiagnosticObservation, ...]:
    observations: list[_DiagnosticObservation] = []
    scored_targets: list[_LabeledAnchor] = []
    for target in reversed(anchors):
        if any(_intervals_overlap(target, scored) for scored in scored_targets):
            continue
        eligible = tuple(
            candidate
            for candidate in anchors
            if candidate.label_end_index < target.snapshot.observation_index
        )
        selection = _select_analogues(target.snapshot, eligible, policy)
        if len(selection.selected) < policy.minimum_analogue_count:
            continue
        distribution = _distribution(selection.selected, policy)
        if distribution.effective_sample_size < policy.minimum_effective_sample_size:
            continue
        lower = next(
            value
            for quantile, value in distribution.log_return_quantiles
            if quantile == policy.lower_interval_quantile
        )
        upper = next(
            value
            for quantile, value in distribution.log_return_quantiles
            if quantile == policy.upper_interval_quantile
        )
        model = next(
            value
            for quantile, value in distribution.log_return_quantiles
            if quantile == 0.5
        )
        beta = target.snapshot.rolling_beta
        baseline = beta * distribution.median_benchmark_log_return
        realized = target.subject_forward_log_return
        realized_relative = realized - beta * target.benchmark_forward_log_return
        forecast_relative = model - baseline
        realized_direction = _direction(realized, policy.neutral_log_return_band)
        model_probabilities = _laplace_smoothed_probabilities(
            (
                distribution.bearish_mass,
                distribution.neutral_mass,
                distribution.bullish_mass,
            ),
            distribution.effective_sample_size,
        )
        baseline_masses = _weighted_directional_mass(
            tuple(
                (
                    beta * record.anchor.benchmark_forward_log_return,
                    record.normalized_weight,
                )
                for record in selection.selected
            ),
            policy.neutral_log_return_band,
        )
        baseline_probabilities = _laplace_smoothed_probabilities(
            baseline_masses,
            distribution.effective_sample_size,
        )
        uniform_probabilities = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
        model_brier, model_log_loss = _proper_scores(
            model_probabilities, realized_direction
        )
        baseline_brier, baseline_log_loss = _proper_scores(
            baseline_probabilities, realized_direction
        )
        uniform_brier, uniform_log_loss = _proper_scores(
            uniform_probabilities, realized_direction
        )
        observations.append(
            _DiagnosticObservation(
                target.snapshot.observation_date,
                target.snapshot.regime_id,
                lower <= realized <= upper,
                abs(realized - model),
                abs(realized - baseline),
                _direction(model, policy.neutral_log_return_band)
                == _direction(realized, policy.neutral_log_return_band),
                _direction(baseline, policy.neutral_log_return_band)
                == _direction(realized, policy.neutral_log_return_band),
                abs(realized_relative - forecast_relative),
                model_brier,
                baseline_brier,
                uniform_brier,
                model_log_loss,
                baseline_log_loss,
                uniform_log_loss,
            )
        )
        scored_targets.append(target)
        if len(observations) == policy.maximum_diagnostic_predictions:
            break
    return tuple(reversed(observations))


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def _skill_score(model_score: float, baseline_score: float) -> float:
    if baseline_score <= 0.0:
        raise ValueError(
            "proper-score baseline must be positive: "
            f"model_score={model_score}, baseline_score={baseline_score}"
        )
    return 1.0 - model_score / baseline_score


def _regime_diagnostics(
    observations: Sequence[_DiagnosticObservation],
) -> tuple[RegimeDiagnostic, ...]:
    output: list[RegimeDiagnostic] = []
    for regime in sorted({observation.regime_id for observation in observations}):
        members = tuple(
            observation
            for observation in observations
            if observation.regime_id == regime
        )
        output.append(
            RegimeDiagnostic(
                regime_id=regime,
                prediction_count=len(members),
                observed_interval_coverage=round(
                    sum(member.interval_hit for member in members) / len(members), 8
                ),
                mean_absolute_log_return_error=round(
                    _mean(tuple(member.model_absolute_error for member in members)), 8
                ),
                beta_scaled_benchmark_mean_absolute_log_return_error=round(
                    _mean(tuple(member.baseline_absolute_error for member in members)),
                    8,
                ),
            )
        )
    return tuple(output)


def _build_prequential_diagnostics(
    anchors: Sequence[_LabeledAnchor],
    policy: EquityForecastPolicy,
) -> PrequentialDiagnostics:
    observations = _diagnostic_observations(anchors, policy)
    count = len(observations)
    sufficient = count >= policy.minimum_diagnostic_predictions
    if not observations:
        return _empty_diagnostics(policy)
    model_mae = _mean(tuple(record.model_absolute_error for record in observations))
    baseline_mae = _mean(
        tuple(record.baseline_absolute_error for record in observations)
    )
    model_brier = _mean(tuple(record.model_brier_score for record in observations))
    baseline_brier = _mean(
        tuple(record.baseline_brier_score for record in observations)
    )
    uniform_brier = _mean(tuple(record.uniform_brier_score for record in observations))
    model_log_loss = _mean(tuple(record.model_log_loss for record in observations))
    baseline_log_loss = _mean(
        tuple(record.baseline_log_loss for record in observations)
    )
    uniform_log_loss = _mean(tuple(record.uniform_log_loss for record in observations))
    return {
        "diagnostic_status": (
            "prequential_diagnostic_available_no_coverage_guarantee"
            if sufficient
            else "insufficient_prequential_diagnostic_predictions"
        ),
        "prediction_count": count,
        "minimum_prediction_count": policy.minimum_diagnostic_predictions,
        "first_prediction_date": observations[0].observation_date.isoformat(),
        "last_prediction_date": observations[-1].observation_date.isoformat(),
        "nominal_interval_coverage": round(
            policy.upper_interval_quantile - policy.lower_interval_quantile, 8
        ),
        "observed_interval_coverage": round(
            sum(record.interval_hit for record in observations) / count, 8
        ),
        "mean_absolute_log_return_error": round(model_mae, 8),
        "beta_scaled_benchmark_mean_absolute_log_return_error": round(baseline_mae, 8),
        "mae_skill_vs_beta_scaled_benchmark": (
            round(1.0 - model_mae / baseline_mae, 8)
            if sufficient and baseline_mae > 0.0
            else None
        ),
        "directional_accuracy": round(
            sum(record.model_direction_correct for record in observations) / count, 8
        ),
        "beta_scaled_benchmark_directional_accuracy": round(
            sum(record.baseline_direction_correct for record in observations) / count,
            8,
        ),
        "mean_absolute_benchmark_relative_error": round(
            _mean(
                tuple(
                    record.benchmark_relative_absolute_error for record in observations
                )
            ),
            8,
        ),
        "mean_multiclass_brier_score": round(model_brier, 8),
        "beta_scaled_benchmark_mean_multiclass_brier_score": round(baseline_brier, 8),
        "uniform_mean_multiclass_brier_score": round(uniform_brier, 8),
        "brier_skill_vs_beta_scaled_benchmark": (
            round(_skill_score(model_brier, baseline_brier), 8) if sufficient else None
        ),
        "brier_skill_vs_uniform": (
            round(_skill_score(model_brier, uniform_brier), 8) if sufficient else None
        ),
        "mean_multiclass_log_loss": round(model_log_loss, 8),
        "beta_scaled_benchmark_mean_multiclass_log_loss": round(baseline_log_loss, 8),
        "uniform_mean_multiclass_log_loss": round(uniform_log_loss, 8),
        "log_loss_skill_vs_beta_scaled_benchmark": (
            round(_skill_score(model_log_loss, baseline_log_loss), 8)
            if sufficient
            else None
        ),
        "log_loss_skill_vs_uniform": (
            round(_skill_score(model_log_loss, uniform_log_loss), 8)
            if sufficient
            else None
        ),
        "proper_score_probability_method": "laplace_smoothed_weighted_empirical_directional_mass",
        "proper_scores_are_prequential": True,
        "overlapping_diagnostic_label_windows_scored": False,
        "regime_diagnostics": _regime_diagnostics(observations),
        "training_labels_strictly_precede_each_prediction": True,
        "same_or_future_outcomes_used_for_training": False,
        "coverage_diagnostic_only": True,
        "coverage_guarantee_claimed": False,
        "promotion_allowed": False,
    }


def _empty_diagnostics(policy: EquityForecastPolicy) -> PrequentialDiagnostics:
    return {
        "diagnostic_status": "insufficient_prequential_diagnostic_predictions",
        "prediction_count": 0,
        "minimum_prediction_count": policy.minimum_diagnostic_predictions,
        "first_prediction_date": None,
        "last_prediction_date": None,
        "nominal_interval_coverage": round(
            policy.upper_interval_quantile - policy.lower_interval_quantile, 8
        ),
        "observed_interval_coverage": None,
        "mean_absolute_log_return_error": None,
        "beta_scaled_benchmark_mean_absolute_log_return_error": None,
        "mae_skill_vs_beta_scaled_benchmark": None,
        "directional_accuracy": None,
        "beta_scaled_benchmark_directional_accuracy": None,
        "mean_absolute_benchmark_relative_error": None,
        "mean_multiclass_brier_score": None,
        "beta_scaled_benchmark_mean_multiclass_brier_score": None,
        "uniform_mean_multiclass_brier_score": None,
        "brier_skill_vs_beta_scaled_benchmark": None,
        "brier_skill_vs_uniform": None,
        "mean_multiclass_log_loss": None,
        "beta_scaled_benchmark_mean_multiclass_log_loss": None,
        "uniform_mean_multiclass_log_loss": None,
        "log_loss_skill_vs_beta_scaled_benchmark": None,
        "log_loss_skill_vs_uniform": None,
        "proper_score_probability_method": "laplace_smoothed_weighted_empirical_directional_mass",
        "proper_scores_are_prequential": True,
        "overlapping_diagnostic_label_windows_scored": False,
        "regime_diagnostics": (),
        "training_labels_strictly_precede_each_prediction": True,
        "same_or_future_outcomes_used_for_training": False,
        "coverage_diagnostic_only": True,
        "coverage_guarantee_claimed": False,
        "promotion_allowed": False,
    }


def _analogue_evidence(
    selection: _AnalogueSelection,
    policy: EquityForecastPolicy,
) -> AnalogueEvidence:
    selected_records = tuple(
        AnalogueRecord(
            observation_date=record.anchor.snapshot.observation_date.isoformat(),
            label_end_date=record.anchor.label_end_date.isoformat(),
            regime_id=record.anchor.snapshot.regime_id,
            distance=round(record.distance, 8),
            normalized_weight=round(record.normalized_weight, 8),
            subject_forward_log_return=round(
                record.anchor.subject_forward_log_return, 8
            ),
            benchmark_forward_log_return=round(
                record.anchor.benchmark_forward_log_return, 8
            ),
        )
        for record in selection.selected
    )
    return {
        "current_regime_id": selection.current_regime_id,
        "eligible_same_regime_count": selection.eligible_same_regime_count,
        "selected_non_overlapping_count": len(selection.selected),
        "overlap_purged_count": selection.overlap_purged_count,
        "active_feature_count": len(selection.active_feature_names),
        "active_feature_names": selection.active_feature_names,
        "analogue_count_required": policy.minimum_analogue_count,
        "effective_sample_size_required": policy.minimum_effective_sample_size,
        "selected_analogues": selected_records,
        "labels_strictly_precede_forecast": True,
        "overlapping_label_windows_selected": False,
    }


def _empty_analogue_evidence(
    policy: EquityForecastPolicy,
    regime_id: str,
) -> AnalogueEvidence:
    return {
        "current_regime_id": regime_id,
        "eligible_same_regime_count": 0,
        "selected_non_overlapping_count": 0,
        "overlap_purged_count": 0,
        "active_feature_count": 0,
        "active_feature_names": (),
        "analogue_count_required": policy.minimum_analogue_count,
        "effective_sample_size_required": policy.minimum_effective_sample_size,
        "selected_analogues": (),
        "labels_strictly_precede_forecast": True,
        "overlapping_label_windows_selected": False,
    }


def _forecast_body(
    symbol: str,
    benchmark_symbol: str,
    as_of: date,
    subject_source_id: str,
    benchmark_source_id: str,
    aligned: Sequence[_AlignedBar],
    policy: EquityForecastPolicy,
    forecast_status: str,
    price_distribution: PriceDistribution | None,
    analogue_evidence: AnalogueEvidence,
    diagnostics: PrequentialDiagnostics,
) -> dict[str, object]:
    return {
        "artifact_type": "research_only_equity_distribution_forecast",
        "version": EQUITY_DISTRIBUTION_FORECAST_VERSION,
        "forecast_status": forecast_status,
        "symbol": symbol,
        "benchmark_symbol": benchmark_symbol,
        "as_of_date": as_of.isoformat(),
        "horizon_trading_days": policy.horizon_trading_days,
        "aligned_history_count": len(aligned),
        "aligned_history_first_date": aligned[0].date.isoformat() if aligned else "",
        "aligned_history_last_date": aligned[-1].date.isoformat() if aligned else "",
        "subject_source_id": subject_source_id,
        "benchmark_source_id": benchmark_source_id,
        "policy": _policy_record(policy),
        "feature_names": _FEATURE_NAMES,
        "price_distribution": price_distribution,
        "point_forecast_guardrail": _point_forecast_guardrail(
            price_distribution,
            diagnostics,
        ),
        "analogue_evidence": analogue_evidence,
        "prequential_diagnostics": diagnostics,
        "input_rows_modified": False,
        "uses_provider_close_for_price_return_measurement": True,
        "adjusted_close_used_for_price_target": False,
        "corporate_action_semantics_validated": False,
        "historical_option_evidence_consumed": False,
        "not_edge_evidence": True,
        "not_trade_decision": True,
        "strategy_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _point_forecast_guardrail(
    price_distribution: PriceDistribution | None,
    diagnostics: PrequentialDiagnostics,
) -> PointForecastGuardrail:
    """Avoid deploying an analogue point estimate that trails its baseline."""
    if price_distribution is None:
        return {
            "guardrail_status": "unavailable_without_price_distribution",
            "selected_method": "abstain",
            "selected_log_return": None,
            "selected_price": None,
            "selection_reason": "forecast_distribution_unavailable",
            "prequential_mae_skill_vs_beta_scaled_benchmark": diagnostics[
                "mae_skill_vs_beta_scaled_benchmark"
            ],
            "selection_uses_only_past_prequential_diagnostics": True,
            "accuracy_improvement_claimed": False,
        }
    skill = diagnostics["mae_skill_vs_beta_scaled_benchmark"]
    if skill is not None and skill > 0.0:
        selected_method = "historical_analogue_median"
        selected_log_return = float(price_distribution["median_log_return"])
        reason = "analogue_positive_prequential_mae_skill"
    else:
        selected_method = "beta_scaled_benchmark_baseline_median"
        selected_log_return = float(
            price_distribution[
                "beta_scaled_benchmark_baseline_median_log_return"
            ]
        )
        reason = (
            "analogue_mae_skill_not_positive"
            if skill is not None
            else "analogue_mae_skill_not_yet_available"
        )
    return {
        "guardrail_status": "point_forecast_selected_no_accuracy_claim",
        "selected_method": selected_method,
        "selected_log_return": round(selected_log_return, 8),
        "selected_price": round(
            float(price_distribution["reference_price"])
            * math.exp(selected_log_return),
            6,
        ),
        "selection_reason": reason,
        "prequential_mae_skill_vs_beta_scaled_benchmark": skill,
        "selection_uses_only_past_prequential_diagnostics": True,
        "accuracy_improvement_claimed": False,
    }


def _abstention_forecast(
    symbol: str,
    benchmark_symbol: str,
    as_of: date,
    subject_source_id: str,
    benchmark_source_id: str,
    aligned: Sequence[_AlignedBar],
    policy: EquityForecastPolicy,
    forecast_status: str,
    analogue_evidence: AnalogueEvidence,
    diagnostics: PrequentialDiagnostics,
) -> EquityDistributionForecast:
    body = _forecast_body(
        symbol,
        benchmark_symbol,
        as_of,
        subject_source_id,
        benchmark_source_id,
        aligned,
        policy,
        forecast_status,
        None,
        analogue_evidence,
        diagnostics,
    )
    return cast(
        EquityDistributionForecast,
        {**body, "reproducibility_hash": canonical_hash(body)},
    )
