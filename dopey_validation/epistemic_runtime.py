"""Runtime adapter from market-research artifacts to epistemic supervision.

The runtime is downgrade-only. It reads existing research artifacts, maps only
fields that are actually present, and atomically writes one summary artifact.
It has no execution imports or promotion authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from .epistemic_adversary import (
    CandidateClaim,
    EpistemicPolicy,
    EvidenceLayer,
    EvidencePoint,
    RegimeEffect,
    canonical_epistemic_hash,
    evaluate_epistemic_claim,
)

EPISTEMIC_RUNTIME_VERSION = "dopey-epistemic-runtime-v1"
JsonObject = dict[str, object]


@dataclass(frozen=True)
class EpistemicRuntimePaths:
    """Repository-contained inputs and the single output artifact."""

    repository_root: Path
    squeeze_assessments_path: Path
    squeeze_rankings_path: Path
    squeeze_summary_path: Path
    targeting_registry_path: Path
    targeting_forecast_path: Path
    targeting_summary_path: Path
    output_path: Path


@dataclass(frozen=True)
class AdaptedClaim:
    """A source-artifact claim projected into the adversarial contract."""

    claim: CandidateClaim
    evidence: tuple[EvidencePoint, ...]
    regime_effects: tuple[RegimeEffect, ...]
    source_artifact: str
    source_queue: str
    adapter_findings: tuple[str, ...]


def default_epistemic_runtime_paths(
    repository_root: Path,
) -> EpistemicRuntimePaths:
    """Return the repository-local production research paths."""

    root = repository_root.resolve()
    squeeze_root = root / "artifacts" / "dopey" / "squeeze_bubble"
    targeting_root = root / "artifacts" / "dopey" / "targeting"
    epistemic_root = root / "artifacts" / "dopey" / "epistemic_supervision"
    return EpistemicRuntimePaths(
        repository_root=root,
        squeeze_assessments_path=(squeeze_root / "symbol_assessments.jsonl"),
        squeeze_rankings_path=squeeze_root / "candidate_rankings.json",
        squeeze_summary_path=squeeze_root / "squeeze_bubble_summary.json",
        targeting_registry_path=(targeting_root / "symbol_candidate_registry.json"),
        targeting_forecast_path=(targeting_root / "per_symbol_forecast_skill.json"),
        targeting_summary_path=targeting_root / "targeting_summary.json",
        output_path=epistemic_root / "epistemic_supervision_summary.json",
    )


def _ensure_contained(
    repository_root: Path,
    path: Path,
    field_name: str,
) -> Path:
    root = repository_root.resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(
            "epistemic runtime path escapes repository root: "
            f"field={field_name}, root={root}, path={resolved}"
        )
    return resolved


def _resolved_paths(paths: EpistemicRuntimePaths) -> EpistemicRuntimePaths:
    root = paths.repository_root.resolve()
    return EpistemicRuntimePaths(
        repository_root=root,
        squeeze_assessments_path=_ensure_contained(
            root,
            paths.squeeze_assessments_path,
            "squeeze_assessments_path",
        ),
        squeeze_rankings_path=_ensure_contained(
            root,
            paths.squeeze_rankings_path,
            "squeeze_rankings_path",
        ),
        squeeze_summary_path=_ensure_contained(
            root,
            paths.squeeze_summary_path,
            "squeeze_summary_path",
        ),
        targeting_registry_path=_ensure_contained(
            root,
            paths.targeting_registry_path,
            "targeting_registry_path",
        ),
        targeting_forecast_path=_ensure_contained(
            root,
            paths.targeting_forecast_path,
            "targeting_forecast_path",
        ),
        targeting_summary_path=_ensure_contained(
            root,
            paths.targeting_summary_path,
            "targeting_summary_path",
        ),
        output_path=_ensure_contained(
            root,
            paths.output_path,
            "output_path",
        ),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_blocker(
    source: str,
    reason_code: str,
    detail: str,
) -> JsonObject:
    return {
        "source": source,
        "reason_code": reason_code,
        "detail": detail,
    }


def _load_json(
    path: Path,
    source: str,
) -> tuple[JsonObject | None, JsonObject | None]:
    if not path.is_file():
        return None, _input_blocker(
            source,
            "required_artifact_missing",
            f"required JSON artifact is missing: path={path}",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, _input_blocker(
            source,
            "invalid_json_artifact",
            f"unable to parse JSON artifact: path={path}, error={error}",
        )
    if not isinstance(raw, dict):
        return None, _input_blocker(
            source,
            "json_artifact_not_object",
            f"JSON artifact must be an object: path={path}",
        )
    return cast(JsonObject, raw), None


def _load_jsonl(
    path: Path,
    source: str,
) -> tuple[tuple[JsonObject, ...] | None, JsonObject | None]:
    if not path.is_file():
        return None, _input_blocker(
            source,
            "required_artifact_missing",
            f"required JSONL artifact is missing: path={path}",
        )
    rows: list[JsonObject] = []
    try:
        with path.open("r", encoding="utf-8", errors="strict") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    return None, _input_blocker(
                        source,
                        "jsonl_row_not_object",
                        (
                            "JSONL row must be an object: "
                            f"path={path}, line={line_number}"
                        ),
                    )
                rows.append(cast(JsonObject, raw))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, _input_blocker(
            source,
            "invalid_jsonl_artifact",
            f"unable to parse JSONL artifact: path={path}, error={error}",
        )
    if not rows:
        return None, _input_blocker(
            source,
            "required_artifact_empty",
            f"required JSONL artifact contains no rows: path={path}",
        )
    return tuple(rows), None


def _write_json_atomic(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(
                record,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, dict) else None


def _sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, (list, tuple)):
        return value
    return None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_artifact_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _pairs_to_integer_map(value: object) -> dict[str, int]:
    rows = _sequence(value)
    if rows is None:
        return {}
    result: dict[str, int] = {}
    for row in rows:
        pair = _sequence(row)
        if pair is None or len(pair) != 2:
            continue
        key = _text(pair[0])
        number = _integer(pair[1])
        if key and number is not None:
            result[key] = number
    return result


def _declared_content_hash_status(
    artifact: Mapping[str, object],
    hash_key: str,
) -> tuple[str, str]:
    declared = _text(artifact.get(hash_key))
    if not declared:
        return "", "missing_declared_content_hash"
    body = {key: value for key, value in artifact.items() if key != hash_key}
    expected = canonical_epistemic_hash(body)
    if declared != expected:
        return declared, (
            f"declared_content_hash_mismatch:declared={declared},expected={expected}"
        )
    return declared, "verified"


def _timestamp_blockers(
    source: str,
    timestamp: str,
    evaluated_at: datetime,
    policy: EpistemicPolicy,
) -> tuple[JsonObject, ...]:
    parsed = _parse_artifact_timestamp(timestamp)
    if parsed is None:
        return (
            _input_blocker(
                source,
                "artifact_timestamp_missing_or_invalid",
                f"artifact timestamp is missing or invalid: value={timestamp!r}",
            ),
        )
    evaluated_utc = evaluated_at.astimezone(timezone.utc)
    future_seconds = (parsed - evaluated_utc).total_seconds()
    age_seconds = (evaluated_utc - parsed).total_seconds()
    blockers: list[JsonObject] = []
    if future_seconds > policy.maximum_future_skew_seconds:
        blockers.append(
            _input_blocker(
                source,
                "artifact_timestamp_future_dated",
                (
                    "artifact timestamp exceeds future-skew policy: "
                    f"future_seconds={future_seconds:.6f}"
                ),
            )
        )
    if age_seconds > policy.maximum_evidence_age_seconds:
        blockers.append(
            _input_blocker(
                source,
                "artifact_timestamp_stale",
                (
                    "artifact timestamp exceeds freshness policy: "
                    f"age_seconds={age_seconds:.6f}, "
                    f"maximum={policy.maximum_evidence_age_seconds}"
                ),
            )
        )
    return tuple(blockers)


def _normalized_timestamp(value: str) -> str:
    parsed = _parse_artifact_timestamp(value)
    return parsed.isoformat() if parsed is not None else ""


def _cycle_coherence_blockers(
    assessments: Sequence[Mapping[str, object]],
    rankings: Mapping[str, object],
    squeeze_summary: Mapping[str, object],
    targeting_registry: Mapping[str, object],
    targeting_forecast: Mapping[str, object],
    targeting_summary: Mapping[str, object],
    policy: EpistemicPolicy,
    evaluated_at: datetime,
) -> tuple[JsonObject, ...]:
    blockers: list[JsonObject] = []
    assessment_timestamps = tuple(
        _text(assessment.get("decision_at_utc")) for assessment in assessments
    )
    for index, timestamp in enumerate(assessment_timestamps):
        blockers.extend(
            _timestamp_blockers(
                f"squeeze_assessment[{index}]",
                timestamp,
                evaluated_at,
                policy,
            )
        )
    ranking_timestamp = _text(rankings.get("decision_at_utc"))
    squeeze_summary_timestamp = _text(squeeze_summary.get("decision_at_utc"))
    targeting_timestamp = _text(targeting_summary.get("observed_at_utc"))
    blockers.extend(
        _timestamp_blockers(
            "squeeze_rankings",
            ranking_timestamp,
            evaluated_at,
            policy,
        )
    )
    blockers.extend(
        _timestamp_blockers(
            "squeeze_summary",
            squeeze_summary_timestamp,
            evaluated_at,
            policy,
        )
    )
    blockers.extend(
        _timestamp_blockers(
            "targeting_summary",
            targeting_timestamp,
            evaluated_at,
            policy,
        )
    )

    normalized_assessment_times = {
        _normalized_timestamp(timestamp)
        for timestamp in assessment_timestamps
        if _normalized_timestamp(timestamp)
    }
    normalized_ranking_time = _normalized_timestamp(ranking_timestamp)
    normalized_squeeze_summary_time = _normalized_timestamp(squeeze_summary_timestamp)
    if (
        len(normalized_assessment_times) != 1
        or normalized_ranking_time not in normalized_assessment_times
        or normalized_squeeze_summary_time not in normalized_assessment_times
    ):
        blockers.append(
            _input_blocker(
                "squeeze_cycle",
                "squeeze_cycle_timestamp_mismatch",
                (
                    "assessments, rankings, and producer summary must share "
                    "one decision timestamp"
                ),
            )
        )

    squeeze_status = _text(squeeze_summary.get("squeeze_bubble_status"))
    if not squeeze_status.startswith("complete_research_only"):
        blockers.append(
            _input_blocker(
                "squeeze_summary",
                "squeeze_producer_not_complete",
                f"producer status is not complete research: status={squeeze_status}",
            )
        )
    if (
        rankings.get("paper_only") is not True
        or rankings.get("live_blocked") is not True
        or rankings.get("order_construction_allowed") is not False
    ):
        blockers.append(
            _input_blocker(
                "squeeze_rankings",
                "squeeze_ranking_boundary_invalid",
                "rankings must remain paper-only, live-blocked, and order-free",
            )
        )

    targeting_status = _text(targeting_summary.get("targeting_status"))
    if not (
        targeting_status.startswith("complete_shadow_research_")
        or targeting_status == "blocked_invalid_or_stale_upstream_evidence"
    ):
        blockers.append(
            _input_blocker(
                "targeting_summary",
                "targeting_producer_status_invalid",
                f"unsupported targeting producer status: status={targeting_status}",
            )
        )

    registry_hash, registry_hash_status = _declared_content_hash_status(
        targeting_registry,
        "reproducibility_hash",
    )
    forecast_hash, forecast_hash_status = _declared_content_hash_status(
        targeting_forecast,
        "reproducibility_hash",
    )
    registry_sources = _mapping(targeting_registry.get("source_hashes")) or {}
    if (
        forecast_hash_status != "verified"
        or _text(registry_sources.get("forecast_skill")) != forecast_hash
    ):
        blockers.append(
            _input_blocker(
                "targeting_cycle",
                "targeting_forecast_registry_hash_mismatch",
                (
                    "candidate registry must bind the current forecast "
                    "reproducibility hash"
                ),
            )
        )
    generation_path = _text(targeting_summary.get("candidate_registry_generation_path"))
    generation_hash = Path(generation_path).stem if generation_path else ""
    if (
        registry_hash_status != "verified"
        or not generation_hash
        or generation_hash != registry_hash
    ):
        blockers.append(
            _input_blocker(
                "targeting_cycle",
                "targeting_summary_registry_generation_mismatch",
                (
                    "targeting summary must bind the current content-addressed "
                    "registry generation"
                ),
            )
        )
    return tuple(blockers)


def _ranking_membership(
    rankings: Mapping[str, object],
    assessment_ids: set[str],
) -> tuple[dict[tuple[str, str], str], tuple[JsonObject, ...]]:
    blockers: list[JsonObject] = []
    queues = _mapping(rankings.get("queues"))
    if queues is None:
        return {}, (
            _input_blocker(
                "squeeze_rankings",
                "rankings_queues_missing",
                "candidate rankings lacks a queues object",
            ),
        )
    membership: dict[tuple[str, str], str] = {}
    lane_by_queue = {
        "squeeze_candidates": "squeeze",
        "squeeze_watch": "squeeze",
        "bubble_unwind_candidates": "bubble",
        "bubble_fragility_monitors": "bubble",
        "bubble_watch": "bubble",
    }
    for queue_name, lane in lane_by_queue.items():
        raw_ids = _sequence(queues.get(queue_name))
        if raw_ids is None:
            blockers.append(
                _input_blocker(
                    "squeeze_rankings",
                    "ranking_queue_missing_or_invalid",
                    f"ranking queue must be a sequence: queue={queue_name}",
                )
            )
            continue
        seen_ids: set[str] = set()
        for raw_identifier in raw_ids:
            identifier = _text(raw_identifier)
            if not identifier:
                blockers.append(
                    _input_blocker(
                        "squeeze_rankings",
                        "ranking_identifier_missing",
                        f"ranking queue contains an empty ID: queue={queue_name}",
                    )
                )
                continue
            if identifier not in assessment_ids:
                blockers.append(
                    _input_blocker(
                        "squeeze_rankings",
                        "ranking_references_unknown_assessment",
                        (
                            "ranking queue references an unknown assessment: "
                            f"queue={queue_name}, assessment_id={identifier}"
                        ),
                    )
                )
                continue
            if identifier in seen_ids:
                blockers.append(
                    _input_blocker(
                        "squeeze_rankings",
                        "duplicate_ranking_identifier",
                        (
                            "ranking queue repeats an assessment: "
                            f"queue={queue_name}, assessment_id={identifier}"
                        ),
                    )
                )
            seen_ids.add(identifier)
            membership[(identifier, lane)] = queue_name
    return membership, tuple(blockers)


def _source_id_values(value: object) -> tuple[str, ...]:
    rows = _sequence(value)
    if rows is None:
        return ()
    return tuple(text for row in rows if (text := _text(row)))


def _source_identity(source_id: str) -> tuple[str, str]:
    marker = ":sha256:"
    if marker not in source_id:
        return source_id, ""
    prefix, content_hash = source_id.rsplit(marker, maxsplit=1)
    if not prefix or not content_hash:
        return source_id, ""
    return source_id, content_hash


def _first_source_id(record: Mapping[str, object]) -> str:
    values = _source_id_values(record.get("source_ids"))
    return values[0] if values else ""


def _squeeze_evidence_points(
    assessment: Mapping[str, object],
    lane_name: str,
    lane: Mapping[str, object],
) -> tuple[EvidencePoint, ...]:
    assessment_id = _text(assessment.get("assessment_id"))
    decision_at = _text(assessment.get("decision_at_utc"))
    raw_evidence = _mapping(assessment.get("evidence")) or {}
    integrity = _mapping(raw_evidence.get("integrity")) or {}
    short_crowding = _mapping(raw_evidence.get("short_crowding")) or {}
    fundamentals = _mapping(raw_evidence.get("fundamentals")) or {}
    observed_at = _text(integrity.get("observed_at_utc")) or decision_at
    counts = _pairs_to_integer_map(integrity.get("lane_observation_counts"))
    robustness = _mapping(lane.get("robustness")) or {}
    point_in_time = (
        integrity.get("path_containment_verified") is True
        and not (_sequence(integrity.get("stale_lanes")) or ())
        and not (_sequence(integrity.get("future_dated_lanes")) or ())
    )
    origin_layer: EvidenceLayer = (
        "research"
        if assessment.get("order_construction_allowed") is False
        and assessment.get("paper_only") is True
        and assessment.get("live_blocked") is True
        else "simulated_execution"
    )
    independent_sources = _integer(robustness.get("independent_source_count"))
    technical_count = counts.get("technical")
    technical_source = _text(integrity.get("technical_source_id"))
    short_source = _first_source_id(short_crowding)
    fundamental_source = _first_source_id(fundamentals)
    derived_source = (
        f"derived:squeeze_assessment:{assessment_id}:sha256:"
        f"{canonical_epistemic_hash(assessment)}"
    )
    specifications: tuple[
        tuple[str, str, object, int | None, bool, str],
        ...,
    ]
    if lane_name == "squeeze":
        liquidity = _mapping(lane.get("observed_liquidity_stress")) or {}
        specifications = (
            (
                "pressure_score",
                "short_interest",
                lane.get("pressure_score"),
                counts.get("short_crowding"),
                False,
                short_source,
            ),
            (
                "ignition_score",
                "price",
                lane.get("ignition_score"),
                technical_count,
                False,
                technical_source,
            ),
            (
                "persistence_score",
                "crowding",
                lane.get("persistence_score"),
                None,
                False,
                derived_source,
            ),
            (
                "robustness_score",
                "data_quality",
                robustness.get("robustness_score"),
                independent_sources,
                False,
                derived_source,
            ),
            (
                "observed_liquidity_stress",
                "liquidity",
                liquidity.get("score"),
                technical_count,
                False,
                technical_source,
            ),
        )
    else:
        liquidity = _mapping(lane.get("observed_liquidity_air_pocket")) or {}
        specifications = (
            (
                "fragility_score",
                "valuation",
                lane.get("fragility_score"),
                counts.get("fundamentals"),
                False,
                fundamental_source,
            ),
            (
                "unwind_trigger_score",
                "unwind",
                lane.get("unwind_trigger_score"),
                technical_count,
                False,
                technical_source,
            ),
            (
                "extreme_pe_score",
                "valuation",
                lane.get("extreme_pe_score"),
                counts.get("fundamentals"),
                False,
                fundamental_source,
            ),
            (
                "revenue_valuation_excess_score",
                "valuation",
                lane.get("revenue_valuation_excess_score"),
                counts.get("fundamentals"),
                False,
                fundamental_source,
            ),
            (
                "ipo_reflexivity_score",
                "ipo",
                lane.get("ipo_reflexivity_score"),
                counts.get("fundamentals"),
                False,
                fundamental_source,
            ),
            (
                "persistence_score",
                "fundamental",
                lane.get("persistence_score"),
                None,
                False,
                derived_source,
            ),
            (
                "robustness_score",
                "data_quality",
                robustness.get("robustness_score"),
                independent_sources,
                False,
                derived_source,
            ),
            (
                "observed_liquidity_air_pocket",
                "liquidity",
                liquidity.get("score"),
                technical_count,
                False,
                technical_source,
            ),
        )
    points: list[EvidencePoint] = []
    for (
        feature_name,
        feature_family,
        raw_value,
        denominator,
        requires_denominator,
        raw_source_id,
    ) in specifications:
        value = _finite_float(raw_value)
        if value is None:
            continue
        source_id, source_hash = _source_identity(raw_source_id)
        points.append(
            EvidencePoint(
                evidence_id=(f"{assessment_id}:{lane_name}:{feature_name}"),
                source_id=source_id,
                source_hash=source_hash,
                observed_at_utc=observed_at,
                available_at_utc=decision_at,
                feature_name=feature_name,
                feature_family=feature_family,
                value=value,
                direction="supports",
                denominator=denominator,
                requires_denominator=requires_denominator,
                weight=1.0,
                regime="unavailable",
                cohort=lane_name,
                catalyst_id=None,
                point_in_time=point_in_time,
                origin_layer=origin_layer,
            )
        )
    return tuple(points)


def _adapt_squeeze_claims(
    assessments: Sequence[Mapping[str, object]],
    rankings: Mapping[str, object],
    assessments_hash: str,
) -> tuple[
    tuple[AdaptedClaim, ...],
    tuple[JsonObject, ...],
]:
    blockers: list[JsonObject] = []
    assessment_ids = {
        _text(assessment.get("assessment_id"))
        for assessment in assessments
        if _text(assessment.get("assessment_id"))
    }
    membership, ranking_blockers = _ranking_membership(
        rankings,
        assessment_ids,
    )
    blockers.extend(ranking_blockers)
    adapted: list[AdaptedClaim] = []
    for assessment in assessments:
        assessment_id = _text(assessment.get("assessment_id"))
        symbol = _text(assessment.get("symbol"))
        decision_at = _text(assessment.get("decision_at_utc"))
        raw_evidence = _mapping(assessment.get("evidence"))
        if not assessment_id or not symbol or not decision_at or raw_evidence is None:
            blockers.append(
                _input_blocker(
                    "squeeze_assessments",
                    "assessment_contract_incomplete",
                    (
                        "assessment requires assessment_id, symbol, "
                        "decision_at_utc, and evidence"
                    ),
                )
            )
            continue
        fundamentals = _mapping(raw_evidence.get("fundamentals")) or {}
        issuer_sector = _text(fundamentals.get("theme")) or None
        days_since_ipo = _integer(fundamentals.get("days_since_first_trade"))
        for lane_name in ("squeeze", "bubble"):
            lane = _mapping(assessment.get(lane_name))
            if lane is None:
                blockers.append(
                    _input_blocker(
                        "squeeze_assessments",
                        "assessment_lane_missing",
                        (
                            "assessment lacks a lane object: "
                            f"assessment_id={assessment_id}, lane={lane_name}"
                        ),
                    )
                )
                continue
            status = _text(lane.get("status"))
            direction = _text(lane.get("direction"))
            score = _finite_float(lane.get("score"))
            if not status or not direction or score is None:
                blockers.append(
                    _input_blocker(
                        "squeeze_assessments",
                        "assessment_lane_contract_incomplete",
                        (
                            "lane requires status, direction, and finite score: "
                            f"assessment_id={assessment_id}, lane={lane_name}"
                        ),
                    )
                )
                continue
            points = _squeeze_evidence_points(
                assessment,
                lane_name,
                lane,
            )
            adapter_findings = [
                "regime_effects_missing",
                (
                    "independent_catalyst_identity_missing"
                    if lane_name == "squeeze"
                    else "valuation_peer_sector_missing"
                ),
            ]
            if any(not point.source_hash for point in points):
                adapter_findings.append("underlying_source_content_hashes_missing")
            adapted.append(
                AdaptedClaim(
                    claim=CandidateClaim(
                        claim_id=f"{assessment_id}:{lane_name}",
                        symbol=symbol,
                        lane=lane_name,
                        upstream_status=status,
                        as_of_utc=decision_at,
                        direction=direction,
                        score=score,
                        aggregate_effect=None,
                        issuer_sector=issuer_sector,
                        valuation_peer_sector=None,
                        days_since_ipo=days_since_ipo,
                        catalyst_ids=(),
                        promotion_requested=False,
                        fitness_delta=None,
                        training_evidence_ids=(),
                        evaluation_evidence_ids=tuple(
                            point.evidence_id for point in points
                        ),
                        hidden_holdout_passed=False,
                        external_holdout_passed=False,
                        prior_artifact_hash=assessments_hash,
                        order_capability_present=(
                            assessment.get("order_construction_allowed") is True
                        ),
                    ),
                    evidence=points,
                    regime_effects=(),
                    source_artifact="squeeze_assessments",
                    source_queue=membership.get(
                        (assessment_id, lane_name),
                        "unranked",
                    ),
                    adapter_findings=tuple(sorted(adapter_findings)),
                )
            )
    return tuple(adapted), tuple(blockers)


def _targeting_family_rows(
    candidate: Mapping[str, object],
) -> Mapping[str, object]:
    rows = _mapping(candidate.get("per_family_skill"))
    return rows or {}


def _targeting_family_scores(
    candidate: Mapping[str, object],
) -> Mapping[str, object]:
    rows = _mapping(candidate.get("per_family_targeting_score"))
    return rows or {}


def _selected_targeting_family(
    family_rows: Mapping[str, object],
    family_scores: Mapping[str, object],
) -> str:
    candidates: list[tuple[float, str]] = []
    for family, row in family_rows.items():
        if not isinstance(family, str) or not isinstance(row, dict):
            continue
        score = _finite_float(family_scores.get(family))
        candidates.append((score if score is not None else 0.0, family))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]


def _targeting_evidence_points(
    symbol: str,
    observed_at: str,
    forecast_hash: str,
    family_rows: Mapping[str, object],
    family_scores: Mapping[str, object],
    origin_layer: EvidenceLayer,
) -> tuple[EvidencePoint, ...]:
    points: list[EvidencePoint] = []
    for family, raw_row in sorted(family_rows.items()):
        row = _mapping(raw_row)
        if not isinstance(family, str) or row is None:
            continue
        value = _finite_float(
            row.get("mean_directional_excess_over_horizon_adjusted_drift")
        )
        denominator = _integer(row.get("effective_sample_size"))
        verdict = _text(row.get("verdict"))
        direction = (
            "supports"
            if verdict == "positive_verified"
            else ("opposes" if verdict == "negative_verified" else "neutral")
        )
        score = _finite_float(family_scores.get(family))
        if value is None:
            continue
        points.append(
            EvidencePoint(
                evidence_id=f"targeting:{symbol}:{family}",
                source_id=f"per_symbol_forecast_skill:{forecast_hash}",
                source_hash=forecast_hash,
                observed_at_utc=observed_at,
                available_at_utc=observed_at,
                feature_name=("mean_directional_excess_over_horizon_adjusted_drift"),
                feature_family="targeting_skill",
                value=value,
                direction=direction,
                denominator=denominator,
                requires_denominator=True,
                weight=score if score is not None else 0.0,
                regime="aggregate",
                cohort=family,
                catalyst_id=None,
                point_in_time=False,
                origin_layer=origin_layer,
            )
        )
    return tuple(points)


def _targeting_regime_effects(
    family_rows: Mapping[str, object],
) -> tuple[RegimeEffect, ...]:
    effects: list[RegimeEffect] = []
    for family, raw_row in sorted(family_rows.items()):
        row = _mapping(raw_row)
        if not isinstance(family, str) or row is None:
            continue
        eras = _sequence(row.get("eras"))
        if eras is None:
            continue
        for raw_era in eras:
            era = _mapping(raw_era)
            if era is None:
                continue
            regime_id = _text(era.get("era"))
            effect = _finite_float(era.get("mean_directional_excess"))
            denominator = _integer(era.get("effective_samples"))
            if not regime_id or effect is None or denominator is None:
                continue
            effects.append(
                RegimeEffect(
                    regime_id=regime_id,
                    cohort_id=family,
                    effect=effect,
                    denominator=denominator,
                )
            )
    return tuple(effects)


def _adapt_targeting_claims(
    registry: Mapping[str, object],
    forecast: Mapping[str, object],
    summary: Mapping[str, object],
    registry_file_hash: str,
    forecast_file_hash: str,
) -> tuple[
    tuple[AdaptedClaim, ...],
    tuple[JsonObject, ...],
]:
    blockers: list[JsonObject] = []
    declared_registry_hash, registry_hash_status = _declared_content_hash_status(
        registry, "reproducibility_hash"
    )
    declared_forecast_hash, forecast_hash_status = _declared_content_hash_status(
        forecast, "reproducibility_hash"
    )
    if registry_hash_status != "verified":
        blockers.append(
            _input_blocker(
                "targeting_registry",
                "registry_content_hash_invalid",
                registry_hash_status,
            )
        )
    if forecast_hash_status != "verified":
        blockers.append(
            _input_blocker(
                "targeting_forecast",
                "forecast_content_hash_invalid",
                forecast_hash_status,
            )
        )
    observed_at = _text(summary.get("observed_at_utc"))
    if not observed_at:
        blockers.append(
            _input_blocker(
                "targeting_summary",
                "targeting_cycle_timestamp_missing",
                "targeting summary lacks observed_at_utc",
            )
        )
        return (), tuple(blockers)
    candidates = _sequence(registry.get("candidates"))
    if candidates is None:
        blockers.append(
            _input_blocker(
                "targeting_registry",
                "targeting_candidates_missing",
                "targeting registry lacks a candidates sequence",
            )
        )
        return (), tuple(blockers)

    research_boundary_intact = (
        registry.get("targeting_research_only") is True
        and registry.get("order_capability_present") is False
        and registry.get("paper_only") is True
        and registry.get("live_blocked") is True
        and summary.get("targeting_research_only") is True
        and summary.get("order_capability_present") is False
        and summary.get("paper_only") is True
        and summary.get("live_blocked") is True
    )
    origin_layer: EvidenceLayer = (
        "research" if research_boundary_intact else "simulated_execution"
    )
    adapted: list[AdaptedClaim] = []
    for raw_candidate in candidates:
        candidate = _mapping(raw_candidate)
        if candidate is None:
            blockers.append(
                _input_blocker(
                    "targeting_registry",
                    "targeting_candidate_not_object",
                    "targeting candidate row must be an object",
                )
            )
            continue
        symbol = _text(candidate.get("symbol"))
        status = _text(candidate.get("candidate_status"))
        score = _finite_float(candidate.get("targeting_score"))
        if not symbol or not status or score is None:
            blockers.append(
                _input_blocker(
                    "targeting_registry",
                    "targeting_candidate_contract_incomplete",
                    "targeting candidate requires symbol, status, and score",
                )
            )
            continue
        family_rows = _targeting_family_rows(candidate)
        family_scores = _targeting_family_scores(candidate)
        selected_family = _selected_targeting_family(
            family_rows,
            family_scores,
        )
        selected_row = _mapping(family_rows.get(selected_family)) or {}
        aggregate_effect = _finite_float(
            selected_row.get("mean_directional_excess_over_horizon_adjusted_drift")
        )
        source_hash = (
            declared_forecast_hash
            if forecast_hash_status == "verified"
            else forecast_file_hash
        )
        points = _targeting_evidence_points(
            symbol,
            observed_at,
            source_hash,
            family_rows,
            family_scores,
            origin_layer,
        )
        regime_effects = _targeting_regime_effects(family_rows)
        parent_hash = (
            declared_registry_hash
            if registry_hash_status == "verified"
            else registry_file_hash
        )
        adapted.append(
            AdaptedClaim(
                claim=CandidateClaim(
                    claim_id=f"targeting:{parent_hash[:24]}:{symbol}",
                    symbol=symbol,
                    lane="targeting",
                    upstream_status=status,
                    as_of_utc=observed_at,
                    direction="unknown",
                    score=score,
                    aggregate_effect=aggregate_effect,
                    issuer_sector=None,
                    valuation_peer_sector=None,
                    days_since_ipo=None,
                    catalyst_ids=(),
                    promotion_requested=False,
                    fitness_delta=None,
                    training_evidence_ids=(),
                    evaluation_evidence_ids=tuple(
                        point.evidence_id for point in points
                    ),
                    hidden_holdout_passed=False,
                    external_holdout_passed=False,
                    prior_artifact_hash=parent_hash,
                    order_capability_present=(
                        candidate.get("order_capability_present") is True
                        or not research_boundary_intact
                    ),
                ),
                evidence=points,
                regime_effects=regime_effects,
                source_artifact="targeting_registry",
                source_queue=status,
                adapter_findings=(
                    "underlying_observation_timestamps_missing",
                    "claim_direction_not_available_in_registry",
                ),
            )
        )
    return tuple(adapted), tuple(blockers)


def _claim_envelope(
    adapted: AdaptedClaim,
    policy: EpistemicPolicy,
) -> JsonObject:
    verdict = evaluate_epistemic_claim(
        adapted.claim,
        adapted.evidence,
        adapted.regime_effects,
        policy,
    )
    body: JsonObject = {
        "claim_id": adapted.claim.claim_id,
        "symbol": adapted.claim.symbol,
        "lane": adapted.claim.lane,
        "source_artifact": adapted.source_artifact,
        "source_queue": adapted.source_queue,
        "adapter_findings": adapted.adapter_findings,
        "verdict": verdict,
    }
    return {
        **body,
        "envelope_hash": canonical_epistemic_hash(body),
    }


def _epistemic_status(
    blockers: Sequence[Mapping[str, object]],
    claim_envelopes: Sequence[Mapping[str, object]],
) -> str:
    if blockers:
        return "blocked_missing_or_invalid_epistemic_inputs"
    verdicts = tuple(
        _mapping(envelope.get("verdict")) or {} for envelope in claim_envelopes
    )
    if any(int(verdict.get("blocking_finding_count", 0)) > 0 for verdict in verdicts):
        return "blocked_epistemic_claims_present"
    if any(
        _text(verdict.get("supervision_status")).startswith("inconclusive")
        or int(verdict.get("inconclusive_finding_count", 0)) > 0
        for verdict in verdicts
    ):
        return "inconclusive_epistemic_claims_present"
    if not verdicts:
        return "blocked_missing_or_invalid_epistemic_inputs"
    return "complete_claims_require_existing_research_gates"


def run_epistemic_supervision(
    paths: EpistemicRuntimePaths,
    policy: EpistemicPolicy,
    evaluated_at: datetime,
) -> JsonObject:
    """Adapt real research artifacts and atomically persist one verdict summary."""

    if evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    resolved = _resolved_paths(paths)
    input_paths = {
        "squeeze_assessments": resolved.squeeze_assessments_path,
        "squeeze_rankings": resolved.squeeze_rankings_path,
        "squeeze_summary": resolved.squeeze_summary_path,
        "targeting_registry": resolved.targeting_registry_path,
        "targeting_forecast": resolved.targeting_forecast_path,
        "targeting_summary": resolved.targeting_summary_path,
    }
    input_hashes = {
        key: _sha256(path) if path.is_file() else ""
        for key, path in sorted(input_paths.items())
    }
    blockers: list[JsonObject] = []
    adapted_claims: list[AdaptedClaim] = []

    assessments, assessments_blocker = _load_jsonl(
        resolved.squeeze_assessments_path,
        "squeeze_assessments",
    )
    rankings, rankings_blocker = _load_json(
        resolved.squeeze_rankings_path,
        "squeeze_rankings",
    )
    squeeze_summary, squeeze_summary_blocker = _load_json(
        resolved.squeeze_summary_path,
        "squeeze_summary",
    )
    for blocker in (
        assessments_blocker,
        rankings_blocker,
        squeeze_summary_blocker,
    ):
        if blocker is not None:
            blockers.append(blocker)
    if assessments is not None and rankings is not None and squeeze_summary is not None:
        squeeze_claims, squeeze_blockers = _adapt_squeeze_claims(
            assessments,
            rankings,
            input_hashes["squeeze_assessments"],
        )
        adapted_claims.extend(squeeze_claims)
        blockers.extend(squeeze_blockers)

    registry, registry_blocker = _load_json(
        resolved.targeting_registry_path,
        "targeting_registry",
    )
    forecast, forecast_blocker = _load_json(
        resolved.targeting_forecast_path,
        "targeting_forecast",
    )
    targeting_summary, summary_blocker = _load_json(
        resolved.targeting_summary_path,
        "targeting_summary",
    )
    for blocker in (
        registry_blocker,
        forecast_blocker,
        summary_blocker,
    ):
        if blocker is not None:
            blockers.append(blocker)
    if registry is not None and forecast is not None and targeting_summary is not None:
        targeting_claims, targeting_blockers = _adapt_targeting_claims(
            registry,
            forecast,
            targeting_summary,
            input_hashes["targeting_registry"],
            input_hashes["targeting_forecast"],
        )
        adapted_claims.extend(targeting_claims)
        blockers.extend(targeting_blockers)
    if (
        assessments is not None
        and rankings is not None
        and squeeze_summary is not None
        and registry is not None
        and forecast is not None
        and targeting_summary is not None
    ):
        blockers.extend(
            _cycle_coherence_blockers(
                assessments,
                rankings,
                squeeze_summary,
                registry,
                forecast,
                targeting_summary,
                policy,
                evaluated_at,
            )
        )

    claim_envelopes = tuple(
        sorted(
            (_claim_envelope(adapted, policy) for adapted in adapted_claims),
            key=lambda envelope: (
                _text(envelope.get("claim_id")),
                _text(envelope.get("lane")),
            ),
        )
    )
    verdict_status_counts: Counter[str] = Counter()
    source_claim_counts: Counter[str] = Counter()
    for envelope in claim_envelopes:
        verdict = _mapping(envelope.get("verdict")) or {}
        verdict_status_counts[
            _text(verdict.get("supervision_status")) or "missing_status"
        ] += 1
        source_claim_counts[_text(envelope.get("source_artifact"))] += 1

    body: JsonObject = {
        "artifact_type": "epistemic_supervision_runtime_summary",
        "runtime_version": EPISTEMIC_RUNTIME_VERSION,
        "evaluated_at_utc": evaluated_at.astimezone(timezone.utc).isoformat(),
        "epistemic_status": _epistemic_status(
            blockers,
            claim_envelopes,
        ),
        "input_content_hashes": input_hashes,
        "input_paths": {key: str(path) for key, path in sorted(input_paths.items())},
        "input_blocker_count": len(blockers),
        "input_blockers": tuple(
            sorted(
                blockers,
                key=lambda blocker: (
                    _text(blocker.get("source")),
                    _text(blocker.get("reason_code")),
                    _text(blocker.get("detail")),
                ),
            )
        ),
        "claim_count": len(claim_envelopes),
        "source_claim_counts": dict(sorted(source_claim_counts.items())),
        "verdict_status_counts": dict(sorted(verdict_status_counts.items())),
        "claim_verdicts": claim_envelopes,
        "source_artifacts_mutated": False,
        "existing_research_gates_still_required": True,
        "research_only": True,
        "simulated_execution_separated": True,
        "promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    summary: JsonObject = {
        **body,
        "summary_hash": canonical_epistemic_hash(body),
    }
    _write_json_atomic(resolved.output_path, summary)
    return summary
