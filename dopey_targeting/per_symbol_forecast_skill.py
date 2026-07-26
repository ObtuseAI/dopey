"""Measure point-in-time per-symbol skill without manufacturing conviction.

The primary observations are contested, direction-graded playbook settlements.
Daily re-fires with overlapping forward windows are collapsed into one effective
observation. A symbol-family can earn a directional verdict only after:

* at least 30 non-overlapping effective observations;
* both chronological eras clear their evidence floors; and
* a deterministic circular-shift null rejects accidental alignment.

Scanner fitness is currently aggregate-only, so it is never smeared across
symbols. Rank IC is also explicitly unavailable until detections carry a
point-in-time continuous score. These absences are surfaced, not imputed.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import fmean

from dopey.protocols.identity import canonical_hash
from dopey.strategy_engineering.playbook_settlement import (
    is_rating_eligible_settlement,
    uses_legacy_direction_assumption,
)

from .models import TargetingPolicy

FORECAST_SKILL_VERSION = "dopey-per-symbol-forecast-skill-v1"
DRIFT_LOOKBACK_DAYS = 20
JsonObject = dict[str, object]


@dataclass(frozen=True)
class SettlementObservation:
    detection_id: str
    setup_id: str
    symbol: str
    family: str
    as_of_date: date
    settle_date: date
    horizon_days: int
    prediction_sign: float
    forward_return: float
    drift_adjusted_outcome: float
    contested_truth: bool


@dataclass(frozen=True)
class EffectiveObservation:
    start_date: date
    end_date: date
    prediction_score: float
    forward_return: float
    drift_adjusted_outcome: float
    raw_observation_count: int


@dataclass(frozen=True)
class SettlementLoad:
    observations: tuple[SettlementObservation, ...]
    rejected_reason_counts: Mapping[str, int]
    duplicate_detection_count: int


def iter_jsonl(path: Path) -> Iterator[JsonObject]:
    """Stream JSON objects and fail loudly on malformed evidence."""

    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "invalid JSONL evidence: "
                    f"path={path}, line_number={line_number}, error={error}"
                ) from error
            if not isinstance(value, dict):
                raise TypeError(
                    "JSONL evidence row must be an object: "
                    f"path={path}, line_number={line_number}, "
                    f"actual={type(value).__name__}"
                )
            yield value


def _required_text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing non-empty string field: key={key}")
    return value.strip()


def _required_float(record: Mapping[str, object], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool):
        raise ValueError(f"numeric field cannot be boolean: key={key}, value={value}")
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"missing finite numeric field: key={key}, value={value}") from error
    if not math.isfinite(parsed):
        raise ValueError(f"numeric field must be finite: key={key}, value={value}")
    return parsed


def _required_positive_int(record: Mapping[str, object], key: str) -> int:
    parsed = int(_required_float(record, key))
    if parsed <= 0:
        raise ValueError(f"integer field must be positive: key={key}, value={parsed}")
    return parsed


def _parse_date(record: Mapping[str, object], key: str) -> date:
    raw = _required_text(record, key)
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"date field must be ISO-8601: key={key}, value={raw}") from error


def _horizon_adjusted_drift(prior_drift: float, horizon_days: int) -> float:
    gross_drift = 1.0 + prior_drift
    if gross_drift <= 0.0:
        raise ValueError(
            "prior drift cannot be compounded: "
            f"prior_drift={prior_drift}, horizon_days={horizon_days}"
        )
    return gross_drift ** (float(horizon_days) / float(DRIFT_LOOKBACK_DAYS)) - 1.0


def _parse_settlement(record: Mapping[str, object]) -> SettlementObservation:
    if record.get("graded") is not True:
        raise ValueError("not_direction_graded")
    direction = _required_text(record, "direction")
    if direction not in {"long", "short"}:
        raise ValueError(f"unsupported_direction:{direction}")
    setup_id = _required_text(record, "setup_id")
    if uses_legacy_direction_assumption(record):
        raise ValueError("legacy_direction_assumption_quarantined")
    if not is_rating_eligible_settlement(record):
        raise ValueError("rating_policy_ineligible_settlement")
    horizon_days = _required_positive_int(record, "horizon_days")
    forward_return = _required_float(record, "forward_return")
    prior_drift = _required_float(record, "prior_drift")
    adjusted_drift = _horizon_adjusted_drift(prior_drift, horizon_days)
    return SettlementObservation(
        detection_id=_required_text(record, "detection_id"),
        setup_id=setup_id,
        symbol=_required_text(record, "symbol").upper(),
        family=_required_text(record, "family"),
        as_of_date=_parse_date(record, "as_of_date"),
        settle_date=_parse_date(record, "settle_date"),
        horizon_days=horizon_days,
        prediction_sign=1.0 if direction == "long" else -1.0,
        forward_return=forward_return,
        drift_adjusted_outcome=forward_return - adjusted_drift,
        contested_truth=record.get("contested_truth") is True,
    )


def load_playbook_settlements(path: Path) -> SettlementLoad:
    """Load and deduplicate settlement evidence with explicit rejection counts."""

    return load_playbook_settlement_records(iter_jsonl(path))


def load_playbook_settlement_records(
    records: Iterable[Mapping[str, object]],
) -> SettlementLoad:
    """Load only caller-validated settlement records into forecast evidence."""

    observations: list[SettlementObservation] = []
    rejected: Counter[str] = Counter()
    seen_detection_ids: set[str] = set()
    duplicate_count = 0
    for record in records:
        try:
            observation = _parse_settlement(record)
        except ValueError as error:
            reason = str(error)
            if ":" in reason:
                reason = reason.split(":", maxsplit=1)[0]
            rejected[reason] += 1
            continue
        if observation.detection_id in seen_detection_ids:
            duplicate_count += 1
            continue
        seen_detection_ids.add(observation.detection_id)
        observations.append(observation)
    observations.sort(
        key=lambda item: (
            item.symbol,
            item.family,
            item.setup_id,
            item.as_of_date,
            item.settle_date,
            item.detection_id,
        )
    )
    return SettlementLoad(
        observations=tuple(observations),
        rejected_reason_counts=dict(sorted(rejected.items())),
        duplicate_detection_count=duplicate_count,
    )


def _collapse_overlapping(
    observations: Sequence[SettlementObservation],
) -> tuple[EffectiveObservation, ...]:
    if not observations:
        return ()
    ordered = sorted(
        observations,
        key=lambda item: (item.as_of_date, item.settle_date, item.detection_id),
    )
    clusters: list[list[SettlementObservation]] = []
    cluster: list[SettlementObservation] = []
    cluster_end: date | None = None
    for observation in ordered:
        if cluster_end is None or observation.as_of_date > cluster_end:
            if cluster:
                clusters.append(cluster)
            cluster = [observation]
            cluster_end = observation.settle_date
            continue
        cluster.append(observation)
        cluster_end = max(cluster_end, observation.settle_date)
    if cluster:
        clusters.append(cluster)

    effective: list[EffectiveObservation] = []
    for members in clusters:
        effective.append(
            EffectiveObservation(
                start_date=min(item.as_of_date for item in members),
                end_date=max(item.settle_date for item in members),
                prediction_score=fmean(item.prediction_sign for item in members),
                forward_return=fmean(item.forward_return for item in members),
                drift_adjusted_outcome=fmean(
                    item.drift_adjusted_outcome for item in members
                ),
                raw_observation_count=len(members),
            )
        )
    return tuple(effective)


def _mean_directional_excess(
    observations: Sequence[EffectiveObservation],
) -> float:
    return fmean(
        item.prediction_score * item.drift_adjusted_outcome
        for item in observations
    )


def _directional_hit_rate(
    observations: Sequence[EffectiveObservation],
) -> float:
    hits = sum(
        1
        for item in observations
        if item.prediction_score * item.forward_return > 0.0
    )
    return float(hits) / float(len(observations))


def _circular_shift_p_value(
    observations: Sequence[EffectiveObservation],
) -> tuple[float | None, int]:
    count = len(observations)
    if count < 2:
        return None, 0
    predictions = [item.prediction_score for item in observations]
    outcomes = [item.drift_adjusted_outcome for item in observations]
    observed = abs(fmean(a * b for a, b in zip(predictions, outcomes)))
    null_values: list[float] = []
    for shift in range(1, count):
        shifted = outcomes[shift:] + outcomes[:shift]
        null_values.append(abs(fmean(a * b for a, b in zip(predictions, shifted))))
    exceedances = sum(1 for value in null_values if value >= observed)
    return (float(exceedances + 1) / float(len(null_values) + 1), len(null_values))


def _era_metrics(
    observations: Sequence[EffectiveObservation],
) -> tuple[JsonObject, JsonObject]:
    midpoint = len(observations) // 2
    eras = (observations[:midpoint], observations[midpoint:])
    metrics: list[JsonObject] = []
    for index, era in enumerate(eras, start=1):
        metrics.append(
            {
                "era": f"chronological_half_{index}",
                "effective_samples": len(era),
                "start_date": era[0].start_date.isoformat() if era else None,
                "end_date": era[-1].end_date.isoformat() if era else None,
                "mean_directional_excess": (
                    round(_mean_directional_excess(era), 8) if era else None
                ),
                "directional_hit_rate": (
                    round(_directional_hit_rate(era), 6) if era else None
                ),
            }
        )
    return metrics[0], metrics[1]


def _verdict(
    observations: Sequence[EffectiveObservation],
    mean_excess: float,
    hit_rate: float,
    p_value: float | None,
    eras: Sequence[Mapping[str, object]],
    policy: TargetingPolicy,
) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    if len(observations) < policy.minimum_effective_samples:
        reasons.append("effective_sample_floor_not_met")
    for era in eras:
        if int(era["effective_samples"]) < policy.minimum_era_samples:
            reasons.append(f"{era['era']}_sample_floor_not_met")
    if p_value is None:
        reasons.append("circular_shift_null_unavailable")
    if reasons:
        return "insufficient_evidence", tuple(reasons)

    era_means = [float(era["mean_directional_excess"]) for era in eras]
    significant = p_value is not None and p_value <= policy.maximum_null_p_value
    if (
        significant
        and mean_excess >= policy.positive_excess_floor
        and hit_rate >= policy.positive_hit_rate_floor
        and all(value > 0.0 for value in era_means)
    ):
        return "positive_verified", ()
    if (
        significant
        and mean_excess <= -policy.positive_excess_floor
        and hit_rate <= policy.negative_hit_rate_ceiling
        and all(value < 0.0 for value in era_means)
    ):
        return "negative_verified", ()
    return "flat", ("directional_skill_not_verified_against_all_floors",)


def _family_skill(
    observations: Sequence[SettlementObservation],
    policy: TargetingPolicy,
) -> JsonObject:
    contested = tuple(item for item in observations if item.contested_truth)
    effective = _collapse_overlapping(contested)
    mean_excess = _mean_directional_excess(effective) if effective else 0.0
    hit_rate = _directional_hit_rate(effective) if effective else 0.0
    p_value, null_count = _circular_shift_p_value(effective)
    eras = _era_metrics(effective)
    verdict, reasons = _verdict(
        effective,
        mean_excess,
        hit_rate,
        p_value,
        eras,
        policy,
    )
    return {
        "verdict": verdict,
        "verdict_reasons": list(reasons),
        "raw_graded_samples": len(observations),
        "raw_contested_samples": len(contested),
        "effective_sample_size": len(effective),
        "overlap_collapse_ratio": (
            round(float(len(effective)) / float(len(contested)), 6)
            if contested
            else None
        ),
        "mean_directional_excess_over_horizon_adjusted_drift": round(
            mean_excess, 8
        ),
        "directional_hit_rate": round(hit_rate, 6) if effective else None,
        "circular_shift_null_p_value": (
            round(p_value, 6) if p_value is not None else None
        ),
        "circular_shift_null_samples": null_count,
        "representative_horizon_days": (
            int(round(fmean(item.horizon_days for item in observations)))
            if observations
            else None
        ),
        "eras": list(eras),
        "rank_ic": None,
        "rank_ic_status": "unavailable_no_point_in_time_continuous_score",
        "contested_truth_is_primary_evidence": True,
    }


def build_per_symbol_forecast_skill(
    settlement_load: SettlementLoad,
    source_hashes: Mapping[str, str],
    policy: TargetingPolicy,
) -> JsonObject:
    """Build an immutable, gate-blind per-symbol skill report."""

    grouped: dict[str, list[SettlementObservation]] = {}
    for observation in settlement_load.observations:
        grouped.setdefault(observation.symbol, []).append(observation)

    per_symbol: dict[str, JsonObject] = {}
    family_verdict_counts: Counter[str] = Counter()
    detector_verdict_counts: Counter[str] = Counter()
    for symbol, symbol_observations in sorted(grouped.items()):
        by_family: dict[str, list[SettlementObservation]] = {}
        by_detector: dict[str, list[SettlementObservation]] = {}
        for observation in symbol_observations:
            by_family.setdefault(observation.family, []).append(observation)
            by_detector.setdefault(observation.setup_id, []).append(observation)
        family_rows: dict[str, JsonObject] = {}
        for family, observations in sorted(by_family.items()):
            row = _family_skill(observations, policy)
            family_rows[family] = row
            family_verdict_counts[str(row["verdict"])] += 1
        detector_rows: dict[str, JsonObject] = {}
        for detector, observations in sorted(by_detector.items()):
            row = _family_skill(observations, policy)
            row["families"] = sorted({item.family for item in observations})
            detector_rows[detector] = row
            detector_verdict_counts[str(row["verdict"])] += 1
        per_symbol[symbol] = {
            "symbol": symbol,
            "per_family": family_rows,
            "family_count": len(family_rows),
            "per_detector": detector_rows,
            "detector_count": len(detector_rows),
        }

    report: JsonObject = {
        "artifact_type": "per_symbol_forecast_skill",
        "forecast_skill_version": FORECAST_SKILL_VERSION,
        "symbol_count_with_settlements": len(per_symbol),
        "graded_observation_count": len(settlement_load.observations),
        "duplicate_detection_count": settlement_load.duplicate_detection_count,
        "rejected_reason_counts": dict(settlement_load.rejected_reason_counts),
        "verdict_counts": dict(sorted(family_verdict_counts.items())),
        "family_verdict_counts": dict(sorted(family_verdict_counts.items())),
        "detector_verdict_counts": dict(
            sorted(detector_verdict_counts.items())
        ),
        "per_symbol": per_symbol,
        "policy": {
            "minimum_effective_samples": policy.minimum_effective_samples,
            "minimum_era_samples": policy.minimum_era_samples,
            "positive_excess_floor": policy.positive_excess_floor,
            "positive_hit_rate_floor": policy.positive_hit_rate_floor,
            "negative_hit_rate_ceiling": policy.negative_hit_rate_ceiling,
            "maximum_null_p_value": policy.maximum_null_p_value,
        },
        "source_hashes": dict(sorted(source_hashes.items())),
        "scanner_symbol_evidence_status": "unavailable_aggregate_only_not_smeared",
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    report["reproducibility_hash"] = canonical_hash(report)
    return report
