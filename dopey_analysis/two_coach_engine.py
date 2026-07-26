"""Two-coach chart research: deterministic evidence plus Claude or Codex review."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Final

from dopey.protocols.identity import canonical_hash
from dopey_acceleration.frontier import (
    HEAD_COACH_IDS,
    OpenRouterPaidFailure,
    head_coach_availability,
    run_research_head_coach,
)
from dopey_analysis.trade_loss_coach import classify_closed_trade
from dopey_dashboard.chart_state import build_chart_state
from dopey_research_pipeline.artifact_io import write_json_atomic


TWO_COACH_VERSION: Final[str] = "dopey-two-coach-chart-replay-v1"
EVIDENCE_COACH_ID: Final[str] = "deterministic_structure_replay_coach_v1"
DEFAULT_HEAD_COACH_ID: Final[str] = "claude"
MAX_PRIOR_LESSONS: Final[int] = 6
MAX_HEAD_COACH_MODEL_INPUT_BYTES: Final[int] = 24_000
VALIDATED_OUTCOMES_RELATIVE_PATH: Final[Path] = (
    Path("artifacts")
    / "dopey"
    / "forward_walk"
    / "forward_walk_validated_closed_trades.jsonl"
)
ARTIFACT_RELATIVE_ROOT: Final[Path] = Path("artifacts") / "dopey" / "two_coach"
REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\[\[((?:level|structure|lesson):[A-Za-z0-9:_\-]+)\]\]"
)
NUMERIC_LITERAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])(?:[$€£]\s*)?[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?(?:%|bps?)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


class TwoCoachContractError(RuntimeError):
    """Raised when either coach violates the bounded research contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_validated_outcomes(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "validated prior-trade source contains malformed JSON: "
                    f"path={path}, line={line_number}, error={error}"
                ) from error
            if not isinstance(value, dict):
                raise TypeError(
                    "validated prior-trade record must be an object: "
                    f"path={path}, line={line_number}"
                )
            if (
                value.get("outcome_integrity_class") != "validated_forward_outcome"
                or value.get("included_in_forward_performance_statistics") is not True
                or value.get("historical_record_preserved") is not True
            ):
                raise ValueError(
                    "validated prior-trade source contains an unvalidated outcome: "
                    f"path={path}, line={line_number}, position_id={value.get('position_id')}"
                )
            records.append(value)
    return records


def _parsed_date(value: object, label: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"prior-trade date is missing: field={label}, value={value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"prior-trade date is invalid: field={label}, value={value!r}") from error


def _outcome_bucket(record: Mapping[str, Any]) -> str:
    pnl = float(record.get("path_pnl", 0.0))
    return "winner" if pnl > 0.0 else "loser" if pnl < 0.0 else "flat"


def _similarity_score(record: Mapping[str, Any], symbol: str, strategy: str) -> int:
    score = 0
    if str(record.get("symbol", "")).upper() == symbol:
        score += 4
    if strategy and str(record.get("candidate_strategy", "")) == strategy:
        score += 2
    if record.get("ex_ante") is True:
        score += 1
    return score


def _match_scope(record: Mapping[str, Any], symbol: str, strategy: str) -> str:
    symbol_match = str(record.get("symbol", "")).upper() == symbol
    strategy_match = bool(strategy) and str(record.get("candidate_strategy", "")) == strategy
    if symbol_match and strategy_match:
        return "exact_symbol_and_strategy"
    if symbol_match:
        return "exact_symbol"
    if strategy_match:
        return "cross_symbol_same_strategy"
    return "cross_symbol_context_only"


def retrieve_prior_trade_lessons(
    validated_records: Sequence[dict[str, Any]],
    symbol: str,
    strategy: str,
    cutoff: str,
    source_sha256: str | None,
) -> dict[str, Any]:
    """Retrieve balanced, point-in-time lessons without ranking on PnL magnitude."""

    normalized_symbol = symbol.strip().upper()
    cutoff_date = _parsed_date(cutoff, "cutoff")
    eligible: list[tuple[int, int, str, dict[str, Any]]] = []
    for record in validated_records:
        exit_date = _parsed_date(record.get("exit_date"), "exit_date")
        if exit_date > cutoff_date:
            continue
        record_hash = canonical_hash(record)
        eligible.append(
            (
                _similarity_score(record, normalized_symbol, strategy),
                exit_date.toordinal(),
                record_hash,
                record,
            )
        )
    ordered = sorted(
        eligible,
        key=lambda item: (-item[0], -item[1], item[2]),
    )
    winners = [item for item in ordered if _outcome_bucket(item[3]) == "winner"]
    losers = [item for item in ordered if _outcome_bucket(item[3]) == "loser"]
    flats = [item for item in ordered if _outcome_bucket(item[3]) == "flat"]
    selected = [*winners[:3], *losers[:3]]
    if len(selected) < MAX_PRIOR_LESSONS:
        selected_hashes = {item[2] for item in selected}
        for item in [*ordered, *flats]:
            if item[2] in selected_hashes:
                continue
            selected.append(item)
            selected_hashes.add(item[2])
            if len(selected) >= MAX_PRIOR_LESSONS:
                break
    selected = sorted(
        selected[:MAX_PRIOR_LESSONS],
        key=lambda item: (-item[0], -item[1], item[2]),
    )
    lessons: list[dict[str, Any]] = []
    for rank, (similarity, _ordinal, record_hash, record) in enumerate(selected, start=1):
        lesson_body = {
            "source_position_id": str(record.get("position_id", "")),
            "source_record_hash": record_hash,
            "outcome_observed_at": str(record["exit_date"]),
            "symbol": str(record.get("symbol", "")),
            "strategy": str(record.get("candidate_strategy", "")),
            "signal_family": str(record.get("signal_family", "unknown")),
            "lesson_code": classify_closed_trade(record),
            "outcome_bucket": _outcome_bucket(record),
            "match_scope": _match_scope(record, normalized_symbol, strategy),
            "similarity_score": similarity,
            "rank": rank,
        }
        lessons.append(
            {
                "lesson_id": f"lesson:{canonical_hash(lesson_body)[:24]}",
                **lesson_body,
            }
        )
    status = (
        "complete_lessons_retrieved"
        if lessons
        else "complete_no_eligible_prior_trades"
    )
    body: dict[str, Any] = {
        "artifact_type": "validated_prior_trade_lesson_retrieval",
        "schema_version": "dopey-prior-trade-retrieval-v1",
        "retrieval_status": status,
        "replay_cutoff": cutoff,
        "required_outcome_class": "validated_forward_outcome",
        "source_sha256": source_sha256,
        "eligible_record_count": len(eligible),
        "lesson_count": len(lessons),
        "ranking_inputs": [
            "exact_symbol",
            "candidate_strategy",
            "ex_ante_marker",
            "outcome_observed_at_recency",
            "source_record_hash_tiebreak",
        ],
        "pnl_magnitude_used_for_ranking": False,
        "winner_and_loser_balance_requested": True,
        "censored_included": False,
        "quarantined_included": False,
        "post_cutoff_outcomes_included": False,
        "lessons": lessons,
        "paper_only": True,
        "live_blocked": True,
        "not_edge_evidence": True,
    }
    return {**body, "retrieval_hash": canonical_hash(body)}


def _directional_strategy(structures: Sequence[Mapping[str, Any]]) -> str:
    bullish = sum(record.get("directional_bias") == "bullish" for record in structures)
    bearish = sum(record.get("directional_bias") == "bearish" for record in structures)
    if bullish > bearish:
        return "long_call"
    if bearish > bullish:
        return "long_put"
    return ""


def build_evidence_coach_packet(
    repository_root: Path,
    symbol: str,
    timeframe: str,
    head_coach_id: str,
) -> dict[str, Any]:
    """Build the first coach's immutable, raw-OHLC and replay-grounded packet."""

    normalized_head_coach = head_coach_id.strip().casefold()
    if normalized_head_coach not in HEAD_COACH_IDS:
        raise ValueError(
            "two-coach head coach is unsupported: "
            f"actual={head_coach_id!r}, allowed={HEAD_COACH_IDS}"
        )
    chart = build_chart_state(repository_root, symbol, timeframe)
    grounded = chart.get("grounded_structure_evidence")
    replay = chart.get("blind_replay_evidence")
    if not isinstance(grounded, dict) or not isinstance(replay, dict):
        raise TwoCoachContractError("chart state lacks grounded structure or replay evidence")
    if (
        grounded.get("viewport_is_detector_input") is not False
        or grounded.get("image_pixels_are_detector_input") is not False
        or grounded.get("raw_ohlcv_is_detector_input") is not True
    ):
        raise TwoCoachContractError("grounded structure detector input boundary is invalid")
    structures = grounded.get("structures")
    numeric_facts = grounded.get("numeric_facts")
    if not isinstance(structures, list) or not isinstance(numeric_facts, list):
        raise TwoCoachContractError("grounded structure registry is malformed")
    strategy = _directional_strategy(
        [record for record in structures if isinstance(record, dict)]
    )
    outcomes_path = repository_root / VALIDATED_OUTCOMES_RELATIVE_PATH
    validated_records = _load_validated_outcomes(outcomes_path)
    source_sha256 = _sha256(outcomes_path) if outcomes_path.exists() else None
    lessons = retrieve_prior_trade_lessons(
        validated_records,
        str(chart["symbol"]),
        strategy,
        str(chart["as_of"]),
        source_sha256,
    )
    topology = {
        "coach_count": 2,
        "evidence_coach_id": EVIDENCE_COACH_ID,
        "head_coach_id": normalized_head_coach,
        "head_coach_availability": head_coach_availability()[normalized_head_coach],
        "runtime_fallback_allowed": False,
    }
    authority = {
        "research_only": True,
        "paper_only": True,
        "live_blocked": True,
        "broker_access": False,
        "order_authority": False,
        "strategy_promotion_allowed": False,
        "parameter_mutation_allowed": False,
    }
    body: dict[str, Any] = {
        "artifact_type": "two_coach_evidence_packet",
        "schema_version": TWO_COACH_VERSION,
        "mode": "paper_research_only",
        "topology": topology,
        "instrument": {
            "symbol": chart["symbol"],
            "asset_class": "equity_underlying",
            "timeframe": chart["timeframe"],
            "as_of": chart["as_of"],
        },
        "data_snapshot": {
            "chart_content_hash": chart["content_hash"],
            "grounded_evidence_hash": grounded.get("evidence_hash"),
            "visible_ohlcv_hash": grounded.get("visible_ohlcv_hash"),
            "visible_start_date": grounded.get("visible_start_date"),
            "visible_end_date": grounded.get("visible_end_date"),
            "future_data_visible_during_detection": False,
            "viewport_is_detector_input": False,
            "image_pixels_are_detector_input": False,
        },
        "evidence_coach": {
            "coach_id": EVIDENCE_COACH_ID,
            "structure_registry": structures,
            "numeric_fact_registry": numeric_facts,
            "blind_replay": replay,
            "prior_trade_lessons": lessons,
            "selected_directional_strategy_for_similarity_only": strategy or "neutral",
            "structure_count": len(structures),
            "numeric_fact_count": len(numeric_facts),
            "lesson_count": lessons["lesson_count"],
        },
        "option_claim_boundary": {
            "status": "blocked_missing_point_in_time_entry_and_exit_option_evidence",
            "underlying_ohlcv_cannot_validate_option_pnl": True,
            "zero_dte_weekly_option_outcome_claim_allowed": False,
        },
        "mutation_boundary": {
            "coach_suggestions_quarantined": True,
            "purged_walk_forward_required": True,
            "held_out_validation_required": True,
            "automatic_activation_allowed": False,
        },
        "authority": authority,
    }
    packet_hash = canonical_hash(body)
    return {
        **body,
        "packet_hash": packet_hash,
        "session_id": f"two-coach:{packet_hash[:24]}",
    }


def _validated_registry_text(record: Mapping[str, Any], key: str, registry_name: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TwoCoachContractError(
            f"{registry_name} record lacks required text: key={key!r}, record={record!r}"
        )
    return value


def _ordered_model_structures(structures: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    validated: list[Mapping[str, Any]] = []
    for record in structures:
        _validated_registry_text(record, "structure_id", "structure")
        _validated_registry_text(record, "structure_type", "structure")
        _validated_registry_text(record, "available_at_date", "structure")
        validated.append(record)
    return sorted(
        validated,
        key=lambda record: (
            str(record["available_at_date"]),
            str(record["structure_id"]),
        ),
        reverse=True,
    )


def build_head_coach_model_state(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Project the full local packet into a bounded, no-reveal model input."""

    evidence = packet.get("evidence_coach")
    topology = packet.get("topology")
    instrument = packet.get("instrument")
    data_snapshot = packet.get("data_snapshot")
    authority = packet.get("authority")
    if not all(
        isinstance(value, dict)
        for value in (evidence, topology, instrument, data_snapshot, authority)
    ):
        raise TwoCoachContractError("two-coach packet lacks required model-input records")
    assert isinstance(evidence, dict)
    structures_value = evidence.get("structure_registry")
    facts_value = evidence.get("numeric_fact_registry")
    lessons_value = evidence.get("prior_trade_lessons")
    if not isinstance(structures_value, list) or not isinstance(facts_value, list):
        raise TwoCoachContractError("two-coach packet registries are malformed")
    if not isinstance(lessons_value, dict) or not isinstance(lessons_value.get("lessons"), list):
        raise TwoCoachContractError("two-coach prior-trade lessons are malformed")
    structures = [
        record
        for record in structures_value
        if isinstance(record, Mapping)
    ]
    facts = [
        record
        for record in facts_value
        if isinstance(record, Mapping)
    ]
    if len(structures) != len(structures_value) or len(facts) != len(facts_value):
        raise TwoCoachContractError("two-coach registries contain non-object records")
    selected_structures = _ordered_model_structures(structures)
    fact_by_ref: dict[str, Mapping[str, Any]] = {}
    for record in facts:
        level_ref = _validated_registry_text(record, "level_ref", "numeric fact")
        if level_ref in fact_by_ref:
            raise TwoCoachContractError(
                f"numeric fact registry contains a duplicate reference: level_ref={level_ref}"
            )
        fact_by_ref[level_ref] = record
    prioritized_fact_refs: list[str] = []
    seen_fact_refs: set[str] = set()
    latest_facts = sorted(
        (
            record
            for record in facts
            if str(record.get("label", "")).startswith("latest_")
        ),
        key=lambda record: (
            str(record.get("label", "")),
            str(record.get("level_ref", "")),
        ),
    )
    for record in latest_facts:
        level_ref = str(record["level_ref"])
        prioritized_fact_refs.append(level_ref)
        seen_fact_refs.add(level_ref)
    for structure in selected_structures:
        level_refs = structure.get("level_refs")
        if not isinstance(level_refs, list) or not all(isinstance(value, str) for value in level_refs):
            raise TwoCoachContractError(
                "structure registry contains invalid level references: "
                f"structure_id={structure.get('structure_id')!r}"
            )
        for level_ref in level_refs:
            if level_ref not in fact_by_ref:
                raise TwoCoachContractError(
                    "structure references an unknown numeric fact: "
                    f"structure_id={structure.get('structure_id')!r}, level_ref={level_ref!r}"
                )
            if level_ref not in seen_fact_refs:
                prioritized_fact_refs.append(level_ref)
                seen_fact_refs.add(level_ref)
    selected_fact_refs = prioritized_fact_refs
    selected_fact_ref_set = set(selected_fact_refs)
    compact_structures = [
        {
            "structure_id": str(record["structure_id"]),
            "structure_type": str(record["structure_type"]),
            "directional_bias": str(record.get("directional_bias", "neutral")),
            "available_at_date": str(record["available_at_date"]),
            "level_refs": [
                str(level_ref)
                for level_ref in record.get("level_refs", [])
                if str(level_ref) in selected_fact_ref_set
            ],
            "candidate_not_truth": bool(record.get("candidate_not_truth", True)),
            **(
                {
                    "trend_direction": str(record.get("trend_direction", "unknown")),
                    "containment_state": str(record.get("containment_state", "unknown")),
                }
                if record.get("structure_type") == "trend_channel"
                else {}
            ),
        }
        for record in selected_structures
    ]
    for source, compact in zip(selected_structures, compact_structures, strict=True):
        if compact["level_refs"] != source.get("level_refs"):
            raise TwoCoachContractError(
                "blocked_partial_structure_projection: "
                f"structure_id={source.get('structure_id')!r}"
            )
    compact_facts = [
        {
            "level_ref": level_ref,
            "label": _validated_registry_text(fact_by_ref[level_ref], "label", "numeric fact"),
            "canonical_display": _validated_registry_text(
                fact_by_ref[level_ref],
                "canonical_display",
                "numeric fact",
            ),
            "unit": _validated_registry_text(fact_by_ref[level_ref], "unit", "numeric fact"),
        }
        for level_ref in selected_fact_refs
    ]
    compact_lessons: list[dict[str, str]] = []
    raw_lessons = lessons_value["lessons"]
    for record in raw_lessons:
        if not isinstance(record, Mapping):
            raise TwoCoachContractError("prior-trade lesson registry contains a non-object record")
        compact_lessons.append(
            {
                "lesson_id": _validated_registry_text(record, "lesson_id", "lesson"),
                "lesson_code": _validated_registry_text(record, "lesson_code", "lesson"),
                "outcome_bucket": _validated_registry_text(record, "outcome_bucket", "lesson"),
                "match_scope": _validated_registry_text(record, "match_scope", "lesson"),
            }
        )
    model_body: dict[str, Any] = {
        "artifact_type": "two_coach_head_coach_model_input",
        "schema_version": TWO_COACH_VERSION,
        "source_packet_hash": packet.get("packet_hash"),
        "session_id": packet.get("session_id"),
        "mode": packet.get("mode"),
        "topology": {
            "coach_count": topology.get("coach_count"),
            "evidence_coach_id": topology.get("evidence_coach_id"),
            "head_coach_id": topology.get("head_coach_id"),
            "runtime_fallback_allowed": False,
        },
        "instrument": instrument,
        "data_snapshot": data_snapshot,
        "evidence_coach": {
            "coach_id": evidence.get("coach_id"),
            "structures": compact_structures,
            "numeric_facts": compact_facts,
            "prior_trade_lessons": compact_lessons,
            "full_structure_count": len(structures),
            "represented_structure_count": len(compact_structures),
            "full_numeric_fact_count": len(facts),
            "represented_numeric_fact_count": len(compact_facts),
            "full_lesson_count": len(raw_lessons),
            "represented_lesson_count": len(compact_lessons),
            "model_projection_is_not_full_audit_packet": True,
            "all_references_resolve_against_source_packet": True,
            "not_edge_evidence": True,
        },
        "replay_input_boundary": {
            "reveal_values_visible_to_head_coach": False,
            "future_bars_visible_to_head_coach": False,
            "replay_evaluation_occurs_after_coaching": True,
        },
        "option_claim_boundary": packet.get("option_claim_boundary"),
        "mutation_boundary": packet.get("mutation_boundary"),
        "authority": authority,
    }
    model_input_hash = canonical_hash(model_body)
    model_state = {
        **model_body,
        "model_input_hash": model_input_hash,
        "model_input_bytes": 0,
    }
    for _iteration in range(4):
        model_input_bytes = len(
            json.dumps(model_state, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        if model_state["model_input_bytes"] == model_input_bytes:
            break
        model_state["model_input_bytes"] = model_input_bytes
    else:
        raise TwoCoachContractError("head-coach model-input byte telemetry did not converge")
    if model_input_bytes > MAX_HEAD_COACH_MODEL_INPUT_BYTES:
        raise TwoCoachContractError(
            "blocked_head_coach_model_input_budget_exceeded: "
            f"bytes={model_input_bytes}, maximum={MAX_HEAD_COACH_MODEL_INPUT_BYTES}"
        )
    return model_state


def _all_strings(value: Any, path: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        return [
            item
            for key, child in value.items()
            for item in _all_strings(child, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in _all_strings(child, f"{path}[{index}]")
        ]
    return []


def _reference_registry(packet: Mapping[str, Any]) -> dict[str, str]:
    evidence = packet.get("evidence_coach")
    if not isinstance(evidence, dict):
        raise TwoCoachContractError("evidence coach packet is missing")
    registry: dict[str, str] = {}
    structures = evidence.get("structure_registry")
    facts = evidence.get("numeric_fact_registry")
    lessons_record = evidence.get("prior_trade_lessons")
    if not isinstance(structures, list) or not isinstance(facts, list) or not isinstance(lessons_record, dict):
        raise TwoCoachContractError("evidence coach registries are malformed")
    lessons = lessons_record.get("lessons")
    if not isinstance(lessons, list):
        raise TwoCoachContractError("prior trade lesson registry is malformed")
    for record in structures:
        if not isinstance(record, dict) or not isinstance(record.get("structure_id"), str):
            raise TwoCoachContractError("structure registry contains an invalid record")
        reference = str(record["structure_id"])
        channel_context = (
            f" / trend {record.get('trend_direction', 'unknown')}"
            f" / containment {record.get('containment_state', 'unknown')}"
            if record.get("structure_type") == "trend_channel"
            else ""
        )
        registry[reference] = (
            f"{record.get('structure_type', 'structure')} / "
            f"{record.get('directional_bias', 'neutral')} / "
            f"available {record.get('available_at_date', 'unknown')}"
            f"{channel_context}"
        )
    for record in facts:
        if not isinstance(record, dict) or not isinstance(record.get("level_ref"), str):
            raise TwoCoachContractError("numeric fact registry contains an invalid record")
        reference = str(record["level_ref"])
        registry[reference] = (
            f"{record.get('label', 'level')} "
            f"{record.get('canonical_display', '?')} {record.get('unit', '')}".strip()
        )
    for record in lessons:
        if not isinstance(record, dict) or not isinstance(record.get("lesson_id"), str):
            raise TwoCoachContractError("prior trade lesson registry contains an invalid record")
        reference = str(record["lesson_id"])
        registry[reference] = (
            f"{record.get('lesson_code', 'lesson')} / "
            f"{record.get('outcome_bucket', 'unknown')} / "
            f"{record.get('match_scope', 'context')}"
        )
    return registry


def _model_reference_allowlist(model_state: Mapping[str, Any]) -> set[str]:
    evidence = model_state.get("evidence_coach")
    if not isinstance(evidence, Mapping):
        raise TwoCoachContractError("head-coach model input lacks its evidence registry")
    allowed: set[str] = set()
    field_specs = (
        ("structures", "structure_id"),
        ("numeric_facts", "level_ref"),
        ("prior_trade_lessons", "lesson_id"),
    )
    for field, reference_key in field_specs:
        records = evidence.get(field)
        if not isinstance(records, list):
            raise TwoCoachContractError(
                f"head-coach model input registry is malformed: field={field}"
            )
        for record in records:
            if not isinstance(record, Mapping):
                raise TwoCoachContractError(
                    f"head-coach model input registry contains a non-object: field={field}"
                )
            reference = _validated_registry_text(record, reference_key, field)
            if reference in allowed:
                raise TwoCoachContractError(
                    f"head-coach model input contains a duplicate reference: reference={reference}"
                )
            allowed.add(reference)
    return allowed


def validate_head_coach_analysis(
    analysis: dict[str, Any],
    packet: Mapping[str, Any],
    model_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject free numeric literals and unresolved evidence references."""

    registry = _reference_registry(packet)
    allowed_references = _model_reference_allowlist(model_state)
    projection_unknown = sorted(allowed_references - set(registry))
    if projection_unknown:
        raise TwoCoachContractError(
            "blocked_model_projection_reference_mismatch: "
            f"references={projection_unknown}"
        )
    references: list[str] = []
    numeric_findings: list[dict[str, str]] = []
    for path, text in _all_strings(analysis, "analysis"):
        found = REFERENCE_PATTERN.findall(text)
        references.extend(found)
        without_references = REFERENCE_PATTERN.sub("", text)
        numeric_match = NUMERIC_LITERAL_PATTERN.search(without_references)
        if numeric_match is not None:
            numeric_findings.append(
                {
                    "path": path,
                    "literal": numeric_match.group(0),
                }
            )
    unknown = sorted(set(references) - allowed_references)
    if unknown:
        raise TwoCoachContractError(
            "blocked_unknown_evidence_reference: "
            f"references={unknown}"
        )
    if numeric_findings:
        raise TwoCoachContractError(
            "blocked_hallucinated_numeric_literal: "
            f"findings={numeric_findings}"
        )
    if analysis.get("abstain") is not True and not references:
        raise TwoCoachContractError(
            "blocked_missing_evidence_reference: non-abstaining analysis cited no registered evidence"
        )
    return {
        "numeric_grounding_status": "verified_no_free_numeric_literals",
        "all_references_resolved": True,
        "reference_count": len(references),
        "unique_reference_count": len(set(references)),
        "referenced_ids": sorted(set(references)),
        "direct_model_authored_levels_allowed": False,
    }


def _render_text(text: str, registry: Mapping[str, str]) -> str:
    return REFERENCE_PATTERN.sub(
        lambda match: registry[str(match.group(1))],
        text,
    )


def _render_analysis(value: Any, registry: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _render_text(value, registry)
    if isinstance(value, dict):
        return {key: _render_analysis(child, registry) for key, child in value.items()}
    if isinstance(value, list):
        return [_render_analysis(child, registry) for child in value]
    return value


def _head_coach_objective(head_coach_id: str) -> str:
    return "\n".join(
        [
            f"Act as the explicitly selected {head_coach_id} head coach over DOPEY's deterministic Evidence and Replay Coach.",
            "Interpret the frozen raw-OHLC structures, blind replay, and validated prior-trade lessons without creating any level.",
            "Every chart structure claim must cite a token exactly like [[structure:registered_id]].",
            "Every price or other numeric fact must be expressed only as a token exactly like [[level:registered_id]].",
            "Every historical lesson claim must cite a token exactly like [[lesson:registered_id]].",
            "Do not write standalone digits, prices, dates, percentages, ratios, counts, or rounded values anywhere in the response.",
            "Give a thesis, counterthesis, invalidation logic, unknowns, and abstention conditions as research coaching only.",
            "Do not give buy, sell, quantity, limit-price, broker, order, sizing, or execution instructions.",
            "Underlying OHLC cannot substantiate option PnL; preserve the explicit option-evidence blocker.",
            "Treat all structures as versioned candidate definitions, not smart-money truth or proven edge.",
            "Return at most three hypotheses, three adversarial findings, three uncertainties, and two experiments.",
            "Keep every string under forty words; never copy hashes, dates, counts, or identifiers except registered reference tokens.",
        ]
    )


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False))
        handle.write("\n")


def _failure_audit(
    repository_root: Path,
    symbol: str,
    timeframe: str,
    head_coach_id: str,
    error: Exception,
) -> None:
    paid_usage: dict[str, Any] = {}
    paid_response_count = 0
    paid_response_ids: list[str] = []
    if isinstance(error, OpenRouterPaidFailure):
        paid_usage = dict(error.usage)
        paid_response_count = error.paid_response_count
        paid_response_ids = list(error.paid_response_ids)
    record = {
        "artifact_type": "two_coach_session_failure",
        "schema_version": TWO_COACH_VERSION,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol.strip().upper(),
        "timeframe": timeframe.strip().lower(),
        "requested_head_coach_id": head_coach_id.strip().casefold(),
        "status": "blocked_two_coach_session_failure",
        "error_type": type(error).__name__,
        "error": str(error)[:2000],
        "usage": paid_usage,
        "paid_response_count": paid_response_count,
        "paid_response_ids": paid_response_ids,
        "runtime_fallback_used": False,
        "research_only": True,
        "paper_only": True,
        "live_blocked": True,
        "broker_access": False,
        "order_authority": False,
        "strategy_promotion_allowed": False,
    }
    _append_jsonl(repository_root / ARTIFACT_RELATIVE_ROOT / "session_ledger.jsonl", record)


def run_two_coach_review(
    repository_root: Path,
    symbol: str,
    timeframe: str,
    head_coach_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run deterministic coach one and exactly one selected LLM head coach."""

    normalized_root = repository_root.resolve()
    try:
        packet = build_evidence_coach_packet(
            normalized_root,
            symbol,
            timeframe,
            head_coach_id,
        )
        model_state = build_head_coach_model_state(packet)
        head_coach = run_research_head_coach(
            _head_coach_objective(head_coach_id.strip().casefold()),
            head_coach_id,
            model_state,
            timeout_seconds,
        )
        analysis = head_coach.get("structured_analysis")
        if not isinstance(analysis, dict):
            raise TwoCoachContractError("head coach returned no structured analysis")
        grounding = validate_head_coach_analysis(analysis, packet, model_state)
        registry = _reference_registry(packet)
        rendered_analysis = _render_analysis(analysis, registry)
        if analysis.get("abstain") is True:
            status = "complete_research_coaching_abstained"
            verdict = "abstain"
        elif packet["evidence_coach"]["prior_trade_lessons"]["lesson_count"] == 0:
            status = "complete_research_coaching_no_prior_lessons"
            verdict = "revise" if analysis.get("adversarial_findings") else "research_review"
        else:
            status = "complete_research_coaching"
            verdict = "revise" if analysis.get("adversarial_findings") else "research_review"
        body: dict[str, Any] = {
            "artifact_type": "two_coach_chart_research_session",
            "schema_version": TWO_COACH_VERSION,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": packet["session_id"],
            "status": status,
            "verdict": verdict,
            "topology": packet["topology"],
            "evidence_coach": {
                "coach_id": EVIDENCE_COACH_ID,
                "packet_hash": packet["packet_hash"],
                "structure_count": packet["evidence_coach"]["structure_count"],
                "numeric_fact_count": packet["evidence_coach"]["numeric_fact_count"],
                "lesson_count": packet["evidence_coach"]["lesson_count"],
                "structure_registry": packet["evidence_coach"]["structure_registry"],
                "numeric_fact_registry": packet["evidence_coach"]["numeric_fact_registry"],
                "prior_trade_lessons": packet["evidence_coach"]["prior_trade_lessons"],
                "blind_replay": packet["evidence_coach"]["blind_replay"],
            },
            "head_coach": {
                **head_coach,
                "model_input_hash": model_state["model_input_hash"],
                "model_input_bytes": model_state["model_input_bytes"],
                "model_input_reveal_values_visible": False,
                "structured_analysis": analysis,
                "rendered_analysis": rendered_analysis,
                "grounding": grounding,
            },
            "option_claim_boundary": packet["option_claim_boundary"],
            "mutation_boundary": packet["mutation_boundary"],
            "authority": packet["authority"],
        }
        session_hash = canonical_hash(body)
        output = {**body, "session_hash": session_hash}
        artifact_root = normalized_root / ARTIFACT_RELATIVE_ROOT
        write_json_atomic(
            artifact_root
            / "latest"
            / f"{str(packet['instrument']['symbol']).lower()}_{str(packet['instrument']['timeframe']).lower()}.json",
            output,
        )
        _append_jsonl(artifact_root / "session_ledger.jsonl", output)
        return output
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        _failure_audit(
            normalized_root,
            symbol,
            timeframe,
            head_coach_id,
            error,
        )
        if isinstance(error, TwoCoachContractError):
            raise
        raise TwoCoachContractError(
            "two-coach review failed closed: "
            f"head_coach_id={head_coach_id!r}, symbol={symbol!r}, timeframe={timeframe!r}, error={error}"
        ) from error
