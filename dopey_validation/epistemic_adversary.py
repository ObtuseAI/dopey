"""Deterministic downgrade-only adversary for market-research claims.

The module accepts immutable value records and returns content-addressed audit
artifacts. It never writes artifacts, changes gates, promotes candidates, or
imports execution packages.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal

EPISTEMIC_ADVERSARY_VERSION = "dopey-epistemic-adversary-v1"
SUPERVISOR_TOPOLOGY_AUDIT_VERSION = "dopey-supervisor-topology-audit-v1"

FindingSeverity = Literal["block", "inconclusive"]
EvidenceDirection = Literal["supports", "opposes", "neutral"]
EvidenceLayer = Literal[
    "research",
    "simulated_execution",
    "live_execution",
    "broker",
]

PRESERVED_STATUS_MARKERS = (
    "blocked",
    "inconclusive",
    "insufficient",
    "invalid",
    "missing",
    "timed_out",
    "timeout",
)
SQUEEZE_CROWDING_FAMILIES = frozenset(
    {
        "borrow",
        "crowding",
        "options_crowding",
        "settlement_failure",
        "short_interest",
    }
)
BUBBLE_INDEPENDENT_FAMILIES = frozenset(
    {
        "balance_sheet",
        "cash_flow",
        "fundamental",
        "liquidity",
        "unwind",
        "valuation",
    }
)
BUBBLE_MECHANICAL_FAMILIES = frozenset(
    {
        "attention",
        "ipo",
        "price",
        "volume",
    }
)


@dataclass(frozen=True)
class EpistemicPolicy:
    """Explicit thresholds for adversarial evidence supervision."""

    maximum_evidence_age_seconds: int
    maximum_future_skew_seconds: int
    maximum_duplicate_fraction: float
    minimum_denominator: int
    maximum_single_observation_weight: float
    maximum_single_contribution_fraction: float
    minimum_regime_denominator: int
    minimum_independent_regimes: int
    maximum_recent_ipo_days: int
    minimum_evidence_points: int


@dataclass(frozen=True)
class EvidencePoint:
    """One point-in-time feature contribution to a research claim."""

    evidence_id: str
    source_id: str
    source_hash: str
    observed_at_utc: str
    available_at_utc: str
    feature_name: str
    feature_family: str
    value: float
    direction: EvidenceDirection
    denominator: int | None
    requires_denominator: bool
    weight: float
    regime: str
    cohort: str
    catalyst_id: str | None
    point_in_time: bool
    origin_layer: EvidenceLayer


@dataclass(frozen=True)
class RegimeEffect:
    """A denominator-bearing effect estimate for one regime and cohort."""

    regime_id: str
    cohort_id: str
    effect: float
    denominator: int


@dataclass(frozen=True)
class CandidateClaim:
    """A research claim presented to the downgrade-only adversary."""

    claim_id: str
    symbol: str
    lane: str
    upstream_status: str
    as_of_utc: str
    direction: str
    score: float
    aggregate_effect: float | None
    issuer_sector: str | None
    valuation_peer_sector: str | None
    days_since_ipo: int | None
    catalyst_ids: tuple[str, ...]
    promotion_requested: bool
    fitness_delta: float | None
    training_evidence_ids: tuple[str, ...]
    evaluation_evidence_ids: tuple[str, ...]
    hidden_holdout_passed: bool
    external_holdout_passed: bool
    prior_artifact_hash: str
    order_capability_present: bool


@dataclass(frozen=True)
class StageContract:
    """Import-free projection of one supervisor stage."""

    name: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class EpistemicFinding:
    """Deterministic adversarial finding record."""

    attack_id: str
    severity: FindingSeverity
    reason_code: str
    evidence_ids: tuple[str, ...]
    detail: str

    def as_record(self) -> dict[str, object]:
        return asdict(self)


def default_epistemic_policy() -> EpistemicPolicy:
    """Return the explicit fail-closed baseline policy."""

    return EpistemicPolicy(
        maximum_evidence_age_seconds=3 * 24 * 60 * 60,
        maximum_future_skew_seconds=60,
        maximum_duplicate_fraction=0.0,
        minimum_denominator=20,
        maximum_single_observation_weight=0.35,
        maximum_single_contribution_fraction=0.50,
        minimum_regime_denominator=20,
        minimum_independent_regimes=3,
        maximum_recent_ipo_days=90,
        minimum_evidence_points=4,
    )


def _canonical_hash(record: Mapping[str, object]) -> str:
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_epistemic_hash(record: Mapping[str, object]) -> str:
    """Return the canonical hash used by epistemic artifacts."""

    return _canonical_hash(record)


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be ISO-8601: value={value!r}") from error
    if parsed.tzinfo is None:
        raise ValueError(
            f"{field_name} must include a timezone offset: value={value!r}"
        )
    return parsed.astimezone(timezone.utc)


def _validate_policy(policy: EpistemicPolicy) -> None:
    if policy.maximum_evidence_age_seconds <= 0:
        raise ValueError("maximum_evidence_age_seconds must be positive")
    if policy.maximum_future_skew_seconds < 0:
        raise ValueError("maximum_future_skew_seconds cannot be negative")
    for field_name, value in (
        ("maximum_duplicate_fraction", policy.maximum_duplicate_fraction),
        (
            "maximum_single_observation_weight",
            policy.maximum_single_observation_weight,
        ),
        (
            "maximum_single_contribution_fraction",
            policy.maximum_single_contribution_fraction,
        ),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{field_name} must be within [0, 1]: value={value}")
    for field_name, value in (
        ("minimum_denominator", policy.minimum_denominator),
        ("minimum_regime_denominator", policy.minimum_regime_denominator),
        ("minimum_independent_regimes", policy.minimum_independent_regimes),
        ("maximum_recent_ipo_days", policy.maximum_recent_ipo_days),
        ("minimum_evidence_points", policy.minimum_evidence_points),
    ):
        if value <= 0:
            raise ValueError(f"{field_name} must be positive: value={value}")


def _validate_claim(claim: CandidateClaim) -> None:
    for field_name, value in (
        ("claim_id", claim.claim_id),
        ("symbol", claim.symbol),
        ("lane", claim.lane),
        ("upstream_status", claim.upstream_status),
        ("direction", claim.direction),
    ):
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
    _parse_utc(claim.as_of_utc, "claim.as_of_utc")


def _finding(
    attack_id: str,
    severity: FindingSeverity,
    reason_code: str,
    evidence_ids: Sequence[str],
    detail: str,
) -> EpistemicFinding:
    return EpistemicFinding(
        attack_id=attack_id,
        severity=severity,
        reason_code=reason_code,
        evidence_ids=tuple(sorted(set(evidence_ids))),
        detail=detail,
    )


def _deduplicate_findings(
    findings: Sequence[EpistemicFinding],
) -> tuple[EpistemicFinding, ...]:
    unique = {
        (
            finding.attack_id,
            finding.severity,
            finding.reason_code,
            finding.evidence_ids,
            finding.detail,
        ): finding
        for finding in findings
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda finding: (
                0 if finding.severity == "block" else 1,
                finding.attack_id,
                finding.reason_code,
                finding.evidence_ids,
            ),
        )
    )


def _status_must_be_preserved(status: str) -> bool:
    normalized = status.strip().lower()
    return any(marker in normalized for marker in PRESERVED_STATUS_MARKERS)


def _temporal_findings(
    claim: CandidateClaim,
    evidence: Sequence[EvidencePoint],
    policy: EpistemicPolicy,
) -> tuple[EpistemicFinding, ...]:
    claim_at = _parse_utc(claim.as_of_utc, "claim.as_of_utc")
    findings: list[EpistemicFinding] = []
    for point in evidence:
        observed_at = _parse_utc(
            point.observed_at_utc,
            f"evidence[{point.evidence_id}].observed_at_utc",
        )
        available_at = _parse_utc(
            point.available_at_utc,
            f"evidence[{point.evidence_id}].available_at_utc",
        )
        future_observation_seconds = (observed_at - claim_at).total_seconds()
        future_availability_seconds = (available_at - claim_at).total_seconds()
        impossible_availability_seconds = (observed_at - available_at).total_seconds()
        age_seconds = (claim_at - available_at).total_seconds()
        if future_observation_seconds > policy.maximum_future_skew_seconds:
            findings.append(
                _finding(
                    "temporal_integrity",
                    "block",
                    "future_observation_after_claim",
                    (point.evidence_id,),
                    "observation timestamp occurs after the claim cutoff",
                )
            )
        if future_availability_seconds > policy.maximum_future_skew_seconds:
            findings.append(
                _finding(
                    "temporal_integrity",
                    "block",
                    "future_evidence_available_after_claim",
                    (point.evidence_id,),
                    "evidence was not available at the claim cutoff",
                )
            )
        if impossible_availability_seconds > policy.maximum_future_skew_seconds:
            findings.append(
                _finding(
                    "temporal_integrity",
                    "block",
                    "observation_time_after_availability",
                    (point.evidence_id,),
                    "evidence availability predates its observation",
                )
            )
        if age_seconds > policy.maximum_evidence_age_seconds:
            findings.append(
                _finding(
                    "temporal_integrity",
                    "block",
                    "stale_evidence",
                    (point.evidence_id,),
                    "evidence exceeds the configured point-in-time age limit",
                )
            )
        if point.point_in_time is False:
            findings.append(
                _finding(
                    "temporal_integrity",
                    "block",
                    "non_point_in_time_evidence",
                    (point.evidence_id,),
                    "source does not prove point-in-time availability",
                )
            )
    return tuple(findings)


def _evidence_fingerprint(point: EvidencePoint) -> str:
    record: dict[str, object] = {
        "source_id": point.source_id,
        "source_hash": point.source_hash,
        "observed_at_utc": point.observed_at_utc,
        "available_at_utc": point.available_at_utc,
        "feature_name": point.feature_name,
        "feature_family": point.feature_family,
        "value": point.value,
        "direction": point.direction,
        "denominator": point.denominator,
        "requires_denominator": point.requires_denominator,
        "regime": point.regime,
        "cohort": point.cohort,
        "catalyst_id": point.catalyst_id,
        "point_in_time": point.point_in_time,
        "origin_layer": point.origin_layer,
    }
    return _canonical_hash(record)


def _identity_findings(
    evidence: Sequence[EvidencePoint],
    policy: EpistemicPolicy,
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    missing_identity = tuple(
        point.evidence_id or "<missing>"
        for point in evidence
        if not point.evidence_id.strip()
        or not point.source_id.strip()
        or not point.source_hash.strip()
    )
    if missing_identity:
        findings.append(
            _finding(
                "evidence_identity",
                "block",
                "missing_evidence_source_identity",
                missing_identity,
                "evidence ID, source ID, and source hash are mandatory",
            )
        )

    evidence_id_counts = Counter(point.evidence_id for point in evidence)
    duplicate_ids = tuple(
        evidence_id
        for evidence_id, count in evidence_id_counts.items()
        if evidence_id and count > 1
    )
    if duplicate_ids:
        findings.append(
            _finding(
                "duplicate_evidence",
                "block",
                "duplicate_evidence_id",
                duplicate_ids,
                "one evidence ID appears more than once",
            )
        )

    fingerprints = tuple(_evidence_fingerprint(point) for point in evidence)
    fingerprint_counts = Counter(fingerprints)
    duplicate_instances = sum(
        count - 1 for count in fingerprint_counts.values() if count > 1
    )
    duplicate_fraction = duplicate_instances / len(evidence) if evidence else 0.0
    if duplicate_fraction > policy.maximum_duplicate_fraction:
        duplicate_fingerprints = {
            fingerprint
            for fingerprint, count in fingerprint_counts.items()
            if count > 1
        }
        duplicate_points = tuple(
            point.evidence_id
            for point, fingerprint in zip(
                evidence,
                fingerprints,
                strict=True,
            )
            if fingerprint in duplicate_fingerprints
        )
        findings.append(
            _finding(
                "duplicate_evidence",
                "block",
                "duplicated_evidence_contribution",
                duplicate_points,
                (
                    "duplicate contribution fraction exceeds policy: "
                    f"actual={duplicate_fraction:.6f}, "
                    f"maximum={policy.maximum_duplicate_fraction:.6f}"
                ),
            )
        )

    source_ids_by_hash: dict[str, set[str]] = defaultdict(set)
    evidence_ids_by_hash: dict[str, list[str]] = defaultdict(list)
    for point in evidence:
        if point.source_hash:
            source_ids_by_hash[point.source_hash].add(point.source_id)
            evidence_ids_by_hash[point.source_hash].append(point.evidence_id)
    relabeled_ids = tuple(
        evidence_id
        for source_hash, source_ids in source_ids_by_hash.items()
        if len(source_ids) > 1
        for evidence_id in evidence_ids_by_hash[source_hash]
    )
    if relabeled_ids:
        findings.append(
            _finding(
                "duplicate_evidence",
                "block",
                "source_hash_relabeling",
                relabeled_ids,
                "identical source content is presented under multiple source IDs",
            )
        )
    return tuple(findings)


def _contradiction_findings(
    claim: CandidateClaim,
    evidence: Sequence[EvidencePoint],
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    by_family: dict[str, list[EvidencePoint]] = defaultdict(list)
    invalid_directions: list[str] = []
    for point in evidence:
        by_family[point.feature_family].append(point)
        if point.direction not in {"supports", "opposes", "neutral"}:
            invalid_directions.append(point.evidence_id)
    if invalid_directions:
        findings.append(
            _finding(
                "contradictory_features",
                "block",
                "invalid_evidence_direction",
                invalid_directions,
                "evidence direction is outside the supported typed vocabulary",
            )
        )
    for family, points in sorted(by_family.items()):
        directions = {point.direction for point in points}
        if "supports" in directions and "opposes" in directions:
            findings.append(
                _finding(
                    "contradictory_features",
                    "block",
                    "contradictory_feature_direction",
                    tuple(point.evidence_id for point in points),
                    f"feature family contains unresolved opposition: family={family}",
                )
            )

    if claim.aggregate_effect is not None and claim.aggregate_effect != 0.0:
        aggregate_direction = "bullish" if claim.aggregate_effect > 0.0 else "bearish"
        normalized_direction = claim.direction.strip().lower()
        if normalized_direction in {"bullish", "bearish"}:
            if normalized_direction != aggregate_direction:
                findings.append(
                    _finding(
                        "contradictory_features",
                        "block",
                        "claim_direction_aggregate_effect_conflict",
                        (),
                        "claim direction conflicts with its aggregate effect sign",
                    )
                )
    return tuple(findings)


def _denominator_findings(
    evidence: Sequence[EvidencePoint],
    policy: EpistemicPolicy,
) -> tuple[EpistemicFinding, ...]:
    invalid = tuple(
        point.evidence_id
        for point in evidence
        if point.requires_denominator
        and (
            point.denominator is None or point.denominator < policy.minimum_denominator
        )
    )
    if not invalid:
        return ()
    return (
        _finding(
            "missing_denominators",
            "block",
            "missing_or_insufficient_denominator",
            invalid,
            (
                "rate, ratio, or effect evidence lacks the minimum denominator: "
                f"required={policy.minimum_denominator}"
            ),
        ),
    )


def _outlier_findings(
    evidence: Sequence[EvidencePoint],
    policy: EpistemicPolicy,
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    invalid_weights = tuple(
        point.evidence_id
        for point in evidence
        if not math.isfinite(point.weight) or point.weight < 0.0
    )
    invalid_values = tuple(
        point.evidence_id for point in evidence if not math.isfinite(point.value)
    )
    if invalid_weights:
        findings.append(
            _finding(
                "outlier_domination",
                "block",
                "invalid_evidence_weight",
                invalid_weights,
                "evidence weights must be finite and non-negative",
            )
        )
    if invalid_values:
        findings.append(
            _finding(
                "outlier_domination",
                "block",
                "invalid_evidence_value",
                invalid_values,
                "evidence values must be finite",
            )
        )
    valid = tuple(
        point
        for point in evidence
        if math.isfinite(point.weight)
        and point.weight >= 0.0
        and math.isfinite(point.value)
    )
    total_weight = sum(point.weight for point in valid)
    if valid and total_weight <= 0.0:
        findings.append(
            _finding(
                "outlier_domination",
                "inconclusive",
                "nonpositive_total_evidence_weight",
                tuple(point.evidence_id for point in valid),
                "evidence has no positive contribution weight",
            )
        )
        return tuple(findings)
    if total_weight > 0.0:
        dominant_weight = max(valid, key=lambda point: point.weight)
        dominant_weight_fraction = dominant_weight.weight / total_weight
        if dominant_weight_fraction > policy.maximum_single_observation_weight:
            findings.append(
                _finding(
                    "outlier_domination",
                    "block",
                    "single_observation_weight_domination",
                    (dominant_weight.evidence_id,),
                    (
                        "single evidence weight exceeds policy fraction: "
                        f"actual={dominant_weight_fraction:.6f}, "
                        f"maximum={policy.maximum_single_observation_weight:.6f}"
                    ),
                )
            )

    contributions = tuple((point, point.weight * abs(point.value)) for point in valid)
    total_contribution = sum(value for _, value in contributions)
    if total_contribution > 0.0:
        dominant_point, dominant_contribution = max(
            contributions,
            key=lambda row: row[1],
        )
        contribution_fraction = dominant_contribution / total_contribution
        if contribution_fraction > policy.maximum_single_contribution_fraction:
            findings.append(
                _finding(
                    "outlier_domination",
                    "block",
                    "single_observation_contribution_domination",
                    (dominant_point.evidence_id,),
                    (
                        "single evidence contribution exceeds policy fraction: "
                        f"actual={contribution_fraction:.6f}, "
                        "maximum="
                        f"{policy.maximum_single_contribution_fraction:.6f}"
                    ),
                )
            )
    return tuple(findings)


def _regime_findings(
    claim: CandidateClaim,
    regime_effects: Sequence[RegimeEffect],
    policy: EpistemicPolicy,
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    regime_keys = tuple(
        (effect.cohort_id, effect.regime_id) for effect in regime_effects
    )
    duplicate_keys = tuple(
        f"{cohort_id}:{regime_id}"
        for (cohort_id, regime_id), count in Counter(regime_keys).items()
        if count > 1
    )
    if duplicate_keys:
        findings.append(
            _finding(
                "simpson_regime_inversion",
                "block",
                "duplicate_regime_effect",
                duplicate_keys,
                "one cohort-regime cell appears more than once",
            )
        )

    invalid_denominators = tuple(
        f"{effect.cohort_id}:{effect.regime_id}"
        for effect in regime_effects
        if effect.denominator < policy.minimum_regime_denominator
    )
    if invalid_denominators:
        findings.append(
            _finding(
                "simpson_regime_inversion",
                "inconclusive",
                "missing_or_insufficient_regime_denominator",
                invalid_denominators,
                (
                    "regime effect lacks the minimum denominator: "
                    f"required={policy.minimum_regime_denominator}"
                ),
            )
        )

    qualified = tuple(
        effect
        for effect in regime_effects
        if effect.denominator >= policy.minimum_regime_denominator
        and math.isfinite(effect.effect)
    )
    independent_regimes = {effect.regime_id for effect in qualified}
    if len(independent_regimes) < policy.minimum_independent_regimes:
        findings.append(
            _finding(
                "simpson_regime_inversion",
                "inconclusive",
                "insufficient_independent_regimes",
                tuple(sorted(independent_regimes)),
                (
                    "claim lacks the required independent regime count: "
                    f"actual={len(independent_regimes)}, "
                    f"required={policy.minimum_independent_regimes}"
                ),
            )
        )

    aggregate_effect = claim.aggregate_effect
    if aggregate_effect is None or aggregate_effect == 0.0 or not qualified:
        return tuple(findings)
    aggregate_sign = 1 if aggregate_effect > 0.0 else -1
    supporting_denominator = sum(
        effect.denominator
        for effect in qualified
        if effect.effect * aggregate_sign > 0.0
    )
    opposing_denominator = sum(
        effect.denominator
        for effect in qualified
        if effect.effect * aggregate_sign < 0.0
    )
    if opposing_denominator > supporting_denominator:
        findings.append(
            _finding(
                "simpson_regime_inversion",
                "block",
                "simpson_or_regime_direction_inversion",
                tuple(
                    f"{effect.cohort_id}:{effect.regime_id}"
                    for effect in qualified
                    if effect.effect * aggregate_sign < 0.0
                ),
                "denominator-weighted regime effects oppose the aggregate claim",
            )
        )
    if supporting_denominator > 0 and opposing_denominator > 0:
        findings.append(
            _finding(
                "simpson_regime_inversion",
                "block",
                "regime_direction_instability",
                tuple(f"{effect.cohort_id}:{effect.regime_id}" for effect in qualified),
                "claim direction changes across sufficiently sampled regimes",
            )
        )
    return tuple(findings)


def _lane_semantic_findings(
    claim: CandidateClaim,
    evidence: Sequence[EvidencePoint],
    policy: EpistemicPolicy,
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    lane = claim.lane.strip().lower()
    supporting = tuple(point for point in evidence if point.direction == "supports")
    supporting_families = {point.feature_family.strip().lower() for point in supporting}
    point_catalysts = {
        point.catalyst_id
        for point in evidence
        if point.catalyst_id
        and point.feature_family.strip().lower() not in SQUEEZE_CROWDING_FAMILIES
    }
    independent_catalysts = {
        catalyst_id
        for catalyst_id in (*claim.catalyst_ids, *point_catalysts)
        if catalyst_id
    }
    if (
        lane == "squeeze"
        and supporting_families & SQUEEZE_CROWDING_FAMILIES
        and not independent_catalysts
    ):
        findings.append(
            _finding(
                "crowding_without_catalyst",
                "block",
                "crowding_without_independent_catalyst",
                tuple(
                    point.evidence_id
                    for point in supporting
                    if point.feature_family.strip().lower() in SQUEEZE_CROWDING_FAMILIES
                ),
                "crowding alone cannot establish durable squeeze ignition",
            )
        )

    if lane == "bubble":
        valuation_points = tuple(
            point
            for point in supporting
            if point.feature_family.strip().lower() == "valuation"
        )
        if valuation_points:
            issuer_sector = (claim.issuer_sector or "").strip().lower()
            peer_sector = (claim.valuation_peer_sector or "").strip().lower()
            if not issuer_sector or not peer_sector:
                findings.append(
                    _finding(
                        "valuation_sector_alignment",
                        "block",
                        "valuation_peer_sector_missing",
                        tuple(point.evidence_id for point in valuation_points),
                        "valuation evidence lacks an explicit issuer/peer sector",
                    )
                )
            elif issuer_sector != peer_sector:
                findings.append(
                    _finding(
                        "valuation_sector_alignment",
                        "block",
                        "valuation_sector_mismatch",
                        tuple(point.evidence_id for point in valuation_points),
                        (
                            "valuation comparison crosses sectors: "
                            f"issuer={issuer_sector}, peer={peer_sector}"
                        ),
                    )
                )

        if (
            claim.days_since_ipo is not None
            and claim.days_since_ipo <= policy.maximum_recent_ipo_days
        ):
            independent_families = supporting_families & BUBBLE_INDEPENDENT_FAMILIES
            unwind_confirmed = "unwind" in independent_families
            nonmechanical_confirmed = bool(independent_families - {"unwind"})
            if not unwind_confirmed or not nonmechanical_confirmed:
                mechanical_ids = tuple(
                    point.evidence_id
                    for point in supporting
                    if point.feature_family.strip().lower()
                    in BUBBLE_MECHANICAL_FAMILIES
                )
                findings.append(
                    _finding(
                        "mechanical_post_ipo",
                        "block",
                        "mechanical_post_ipo_effect_not_excluded",
                        mechanical_ids,
                        (
                            "recent IPO claim lacks both nonmechanical evidence "
                            "and an independently confirmed unwind"
                        ),
                    )
                )
    return tuple(findings)


def _execution_separation_findings(
    claim: CandidateClaim,
    evidence: Sequence[EvidencePoint],
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    contaminated = tuple(
        point.evidence_id for point in evidence if point.origin_layer != "research"
    )
    if contaminated:
        findings.append(
            _finding(
                "execution_layer_contamination",
                "block",
                "execution_layer_evidence_contamination",
                contaminated,
                "research claim includes simulated, live, or broker evidence",
            )
        )
    if claim.order_capability_present:
        findings.append(
            _finding(
                "execution_layer_contamination",
                "block",
                "order_capability_present_in_research_claim",
                (),
                "research artifact exposes order capability",
            )
        )
    return tuple(findings)


def _promotion_findings(
    claim: CandidateClaim,
    evidence: Sequence[EvidencePoint],
) -> tuple[EpistemicFinding, ...]:
    findings: list[EpistemicFinding] = []
    training_ids = set(claim.training_evidence_ids)
    evaluation_ids = set(claim.evaluation_evidence_ids)
    available_ids = {point.evidence_id for point in evidence}
    overlap = tuple(sorted(training_ids & evaluation_ids))
    missing_evaluation_ids = tuple(sorted(evaluation_ids - available_ids))

    if claim.fitness_delta is not None and claim.fitness_delta < 0.0:
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "fitness_drop_requires_rollback",
                (),
                f"candidate fitness delta is negative: value={claim.fitness_delta}",
            )
        )
    if not claim.promotion_requested:
        return tuple(findings)
    if _status_must_be_preserved(claim.upstream_status):
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "promotion_attempt_from_blocked_or_inconclusive_upstream",
                (),
                "promotion was requested from a preserved upstream state",
            )
        )
    if not claim.hidden_holdout_passed:
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "hidden_holdout_not_passed",
                tuple(sorted(evaluation_ids)),
                "promotion lacks a passed hidden holdout",
            )
        )
    if not claim.external_holdout_passed:
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "external_holdout_not_passed",
                tuple(sorted(evaluation_ids)),
                "promotion lacks a passed external holdout",
            )
        )
    if claim.fitness_delta is None or claim.fitness_delta <= 0.0:
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "positive_fitness_delta_not_proven",
                (),
                "promotion lacks a strictly positive measured fitness delta",
            )
        )
    if overlap:
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "training_evaluation_evidence_reuse",
                overlap,
                "training evidence was reused as independent evaluation evidence",
            )
        )
    if missing_evaluation_ids:
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "unbound_evaluation_evidence",
                missing_evaluation_ids,
                "promotion references evaluation evidence absent from this audit",
            )
        )
    if not claim.prior_artifact_hash.strip():
        findings.append(
            _finding(
                "fitness_promotion_laundering",
                "block",
                "promotion_missing_parent_artifact_hash",
                (),
                "promotion claim is not linked to an immutable parent artifact",
            )
        )
    return tuple(findings)


def evaluate_epistemic_claim(
    claim: CandidateClaim,
    evidence: Sequence[EvidencePoint],
    regime_effects: Sequence[RegimeEffect],
    policy: EpistemicPolicy,
) -> dict[str, object]:
    """Attack one claim and return a deterministic downgrade-only artifact."""

    _validate_policy(policy)
    _validate_claim(claim)
    findings = _deduplicate_findings(
        (
            *_temporal_findings(claim, evidence, policy),
            *_identity_findings(evidence, policy),
            *_contradiction_findings(claim, evidence),
            *_denominator_findings(evidence, policy),
            *_outlier_findings(evidence, policy),
            *_regime_findings(claim, regime_effects, policy),
            *_lane_semantic_findings(claim, evidence, policy),
            *_execution_separation_findings(claim, evidence),
            *_promotion_findings(claim, evidence),
        )
    )
    preserved_upstream_status = _status_must_be_preserved(claim.upstream_status)
    block_count = sum(1 for finding in findings if finding.severity == "block")
    inconclusive_count = sum(
        1 for finding in findings if finding.severity == "inconclusive"
    )
    if preserved_upstream_status:
        supervision_status = claim.upstream_status
    elif block_count > 0:
        supervision_status = "blocked_epistemic_adversarial_failure"
    elif inconclusive_count > 0 or len(evidence) < policy.minimum_evidence_points:
        supervision_status = "inconclusive_epistemic_evidence"
    else:
        supervision_status = "eligible_for_existing_research_gates"

    rollback_required = claim.fitness_delta is not None and claim.fitness_delta < 0.0
    body: dict[str, object] = {
        "artifact_type": "epistemic_adversarial_supervision",
        "adversary_version": EPISTEMIC_ADVERSARY_VERSION,
        "claim": asdict(claim),
        "policy": asdict(policy),
        "supervision_status": supervision_status,
        "upstream_status": claim.upstream_status,
        "upstream_status_preserved_exactly": preserved_upstream_status,
        "finding_count": len(findings),
        "blocking_finding_count": block_count,
        "inconclusive_finding_count": inconclusive_count,
        "finding_reason_codes": tuple(finding.reason_code for finding in findings),
        "findings": tuple(finding.as_record() for finding in findings),
        "evidence_point_count": len(evidence),
        "unique_evidence_id_count": len({point.evidence_id for point in evidence}),
        "unique_source_hash_count": len(
            {point.source_hash for point in evidence if point.source_hash}
        ),
        "regime_effect_count": len(regime_effects),
        "parent_artifact_hash": claim.prior_artifact_hash,
        "automatic_rollback_required": rollback_required,
        "mutation_retention_allowed": not rollback_required,
        "existing_research_gates_still_required": True,
        "research_only": True,
        "simulated_execution_separated": True,
        "promotion_allowed": False,
        "order_construction_allowed": False,
        "live_execution_allowed": False,
        "profit_or_edge_claimed": False,
    }
    return {
        **body,
        "content_hash": _canonical_hash(body),
    }


def _stage_map(
    stages: Sequence[StageContract],
) -> dict[str, StageContract]:
    return {stage.name: stage for stage in stages}


def audit_supervisor_topology(
    stages: Sequence[StageContract],
    expected_stage_count: int,
) -> dict[str, object]:
    """Audit stage truth and the missing adversarial lineage without imports."""

    if expected_stage_count <= 0:
        raise ValueError(
            f"expected_stage_count must be positive: value={expected_stage_count}"
        )
    names = tuple(stage.name for stage in stages)
    name_counts = Counter(names)
    duplicate_names = tuple(
        sorted(name for name, count in name_counts.items() if count > 1)
    )
    known_names = set(names)
    unknown_dependencies = tuple(
        sorted(
            {
                dependency
                for stage in stages
                for dependency in stage.dependencies
                if dependency not in known_names
            }
        )
    )
    seen: set[str] = set()
    out_of_order: list[str] = []
    for stage in stages:
        missing_before_stage = set(stage.dependencies) - seen
        if missing_before_stage:
            out_of_order.append(stage.name)
        seen.add(stage.name)

    by_name = _stage_map(stages)
    squeeze_dependencies = by_name.get(
        "squeeze_bubble_intelligence",
        StageContract("", ()),
    ).dependencies
    targeting_dependencies = by_name.get(
        "symbol_targeting",
        StageContract("", ()),
    ).dependencies
    panel_dependencies = by_name.get(
        "adversarial_signal_panel",
        StageContract("", ()),
    ).dependencies
    epistemic_dependencies = by_name.get(
        "epistemic_supervision",
        StageContract("", ()),
    ).dependencies
    readiness_dependencies = by_name.get(
        "action_readiness_gate",
        StageContract("", ()),
    ).dependencies
    reconciliation_dependencies = by_name.get(
        "agentic_account_reconciliation",
        StageContract("", ()),
    ).dependencies

    gaps: list[dict[str, object]] = []
    required_epistemic_dependencies = {
        "symbol_targeting",
        "squeeze_bubble_intelligence",
    }
    if "epistemic_supervision" not in known_names:
        gaps.append(
            {
                "reason_code": (
                    "epistemic_supervision_not_wired_after_targeting_and_squeeze"
                ),
                "severity": "high",
                "affected_stages": (
                    "symbol_targeting",
                    "squeeze_bubble_intelligence",
                ),
            }
        )
    elif not required_epistemic_dependencies.issubset(set(epistemic_dependencies)):
        gaps.append(
            {
                "reason_code": "epistemic_supervision_lineage_incomplete",
                "severity": "high",
                "affected_stages": ("epistemic_supervision",),
            }
        )

    structural_validity = (
        len(stages) == expected_stage_count
        and not duplicate_names
        and not unknown_dependencies
        and not out_of_order
    )
    body: dict[str, object] = {
        "artifact_type": "supervisor_topology_epistemic_audit",
        "audit_version": SUPERVISOR_TOPOLOGY_AUDIT_VERSION,
        "current_stage_count": len(stages),
        "expected_stage_count": expected_stage_count,
        "stage_count_status": (
            f"verified_current_{len(stages)}_stage_truth"
            if len(stages) == expected_stage_count
            else "stage_count_mismatch"
        ),
        "stage_names": names,
        "duplicate_stage_names": duplicate_names,
        "unknown_dependencies": unknown_dependencies,
        "out_of_order_stages": tuple(out_of_order),
        "topologically_ordered": not out_of_order,
        "structural_validity": structural_validity,
        "critical_lineage": {
            "symbol_targeting_dependencies": targeting_dependencies,
            "squeeze_bubble_dependencies": squeeze_dependencies,
            "epistemic_supervision_dependencies": epistemic_dependencies,
            "adversarial_signal_panel_dependencies": panel_dependencies,
            "action_readiness_dependencies": readiness_dependencies,
            "account_reconciliation_dependencies": (reconciliation_dependencies),
        },
        "intentional_separations": {
            "action_readiness_is_independent_root": not readiness_dependencies,
            "account_reconciliation_is_independent_root": (
                not reconciliation_dependencies
            ),
            "research_epistemic_stage_has_execution_dependencies": bool(
                {
                    "action_readiness_gate",
                    "agentic_account_reconciliation",
                }.intersection(epistemic_dependencies)
            ),
        },
        "research_execution_separation_preserved": not {
            "action_readiness_gate",
            "agentic_account_reconciliation",
        }.intersection(epistemic_dependencies),
        "gap_count": len(gaps),
        "gaps": tuple(sorted(gaps, key=lambda gap: str(gap["reason_code"]))),
        "audit_status": (
            "structurally_valid_epistemic_lineage_gaps_found"
            if structural_validity and gaps
            else (
                "structurally_valid_no_epistemic_lineage_gaps"
                if structural_validity
                else "invalid_supervisor_topology"
            )
        ),
        "research_only": True,
        "mutation_performed": False,
        "promotion_allowed": False,
        "order_capability_present": False,
    }
    return {
        **body,
        "content_hash": _canonical_hash(body),
    }
