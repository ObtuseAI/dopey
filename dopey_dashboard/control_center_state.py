"""Source-backed state assembly for the native DOPEY control center."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, cast

from dopey_acceleration.provider_control import provider_control_state
from dopey.protocols.identity import canonical_hash
from dopey.strategy_engineering.playbook_settlement import (
    PLAYBOOK_TRUST_VERSION,
)

from .desktop_analytics import build_desktop_analytics
from .live_branch_state import build_live_branch_state
from .scheduler_control import (
    SchedulerRunner,
    WindowsSchedulerRunner,
    inspect_research_core,
)


SOURCE_SPECS: Final[tuple[tuple[str, Path, bool], ...]] = (
    (
        "readiness",
        Path("artifacts")
        / "dopey"
        / "acceleration"
        / "readiness_acceleration_plan.json",
        True,
    ),
    (
        "trade_readiness_frontier",
        Path("artifacts") / "dopey" / "readiness" / "trade_readiness_frontier.json",
        True,
    ),
    (
        "schedule",
        Path("artifacts") / "dopey" / "acceleration" / "schedule_plan.json",
        True,
    ),
    (
        "universe_expansion_plan",
        Path("artifacts") / "dopey" / "acceleration" / "universe_expansion_plan.json",
        True,
    ),
    (
        "evolving_universe",
        Path("artifacts") / "dopey" / "universe" / "evolving_universe_summary.json",
        True,
    ),
    (
        "attention_snapshot",
        Path("artifacts") / "dopey" / "attention" / "attention_snapshot.json",
        True,
    ),
    (
        "playbook_rankings",
        Path("artifacts") / "dopey" / "playbook" / "playbook_rankings.json",
        True,
    ),
    (
        "history_manifest",
        Path("dopey_data") / "history" / "history_dataset_manifest.json",
        True,
    ),
    (
        "world_model",
        Path("artifacts") / "dopey" / "vnext" / "operational" / "world_model.json",
        True,
    ),
    (
        "metacognition",
        Path("artifacts") / "dopey" / "vnext" / "operational" / "metacognition.json",
        True,
    ),
    (
        "homeostasis",
        Path("artifacts") / "dopey" / "vnext" / "operational" / "homeostasis.json",
        True,
    ),
    (
        "observatory",
        Path("artifacts")
        / "dopey"
        / "vnext"
        / "operational"
        / "observatory_artifact.json",
        False,
    ),
    (
        "paper_record",
        Path("artifacts") / "dopey" / "forward_walk" / "forward_walk_summary.json",
        True,
    ),
    (
        "paper_ledger",
        Path("artifacts") / "dopey" / "forward_walk" / "forward_walk_ledger.json",
        False,
    ),
    (
        "option_extremes",
        Path("artifacts") / "dopey" / "playbook" / "option_extremes_report.json",
        True,
    ),
    (
        "market_extremes",
        Path("artifacts") / "dopey" / "playbook" / "market_extremes_report.json",
        True,
    ),
    (
        "llm_research",
        Path("artifacts") / "dopey" / "llm_research" / "latest_cycle.json",
        True,
    ),
    (
        "strategy_dossier",
        Path("artifacts") / "dopey" / "runs" / "latest_dossier.json",
        True,
    ),
    (
        "capital_exposure",
        Path("artifacts") / "dopey" / "runs" / "latest_capital_exposure.json",
        True,
    ),
    (
        "mutation_genealogy",
        Path("artifacts") / "dopey" / "evolution" / "mutation_genealogy.json",
        True,
    ),
    (
        "binomial_oracle",
        Path("artifacts")
        / "dopey"
        / "options_oracle"
        / "binomial_oracle_validation.json",
        True,
    ),
    (
        "context_settlement",
        Path("artifacts") / "dopey" / "equity_swing" / "latest_context_settlement.json",
        True,
    ),
    (
        "evidence_contract_audit",
        Path("artifacts") / "dopey" / "contracts" / "latest_bundle_audit.json",
        True,
    ),
    (
        "evidence_cycle",
        Path("artifacts") / "dopey" / "evidence_intelligence" / "latest_cycle.json",
        True,
    ),
    (
        "constitution",
        Path("artifacts")
        / "dopey"
        / "vnext"
        / "operational"
        / "constitution_state.json",
        True,
    ),
)


def _json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(
            f"control-center source artifact is missing: path={path}"
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"control-center source artifact is not a file: path={path}"
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(
            f"control-center source artifact must be a JSON object: path={path}, actual={type(value).__name__}"
        )
    return cast(dict[str, object], value)


def _issue(
    issue_id: str,
    severity: str,
    source_id: str,
    message: str,
) -> dict[str, object]:
    return {
        "issue_id": issue_id,
        "severity": severity,
        "source_id": source_id,
        "message": message,
    }


def _file_modified_utc(path: Path) -> str:
    try:
        modified = path.stat().st_mtime
    except OSError as error:
        raise OSError(
            f"control-center source timestamp is unreadable: path={path}, error={error}"
        ) from error
    return datetime.fromtimestamp(modified, timezone.utc).isoformat()


def _record_observed_utc(record: dict[str, object]) -> str | None:
    for key in ("observed_utc", "generated_utc", "as_of", "generatedAt"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    snapshot = record.get("snapshot")
    if isinstance(snapshot, dict):
        for key in ("generatedAt", "generated_utc", "as_of", "observed_at"):
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _load_sources(
    repository_root: Path,
) -> tuple[
    dict[str, dict[str, object] | None],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    sources: dict[str, dict[str, object] | None] = {}
    health: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    for source_id, relative_path, requires_boundary in SOURCE_SPECS:
        path = (repository_root / relative_path).resolve(strict=False)
        try:
            record = _json_object(path)
        except FileNotFoundError as error:
            sources[source_id] = None
            health.append(
                {
                    "source_id": source_id,
                    "path": str(relative_path).replace("\\", "/"),
                    "status": "missing",
                    "issue": str(error),
                }
            )
            issues.append(
                _issue(f"source_missing:{source_id}", "fault", source_id, str(error))
            )
            continue
        except json.JSONDecodeError as error:
            sources[source_id] = None
            message = f"control-center source artifact contains invalid JSON: path={path}, error={error}"
            health.append(
                {
                    "source_id": source_id,
                    "path": str(relative_path).replace("\\", "/"),
                    "status": "invalid_json",
                    "issue": message,
                }
            )
            issues.append(
                _issue(f"source_invalid_json:{source_id}", "fault", source_id, message)
            )
            continue
        except (OSError, UnicodeError, TypeError) as error:
            sources[source_id] = None
            message = f"control-center source artifact is unreadable: path={path}, error={error}"
            health.append(
                {
                    "source_id": source_id,
                    "path": str(relative_path).replace("\\", "/"),
                    "status": "unreadable",
                    "issue": message,
                }
            )
            issues.append(
                _issue(f"source_unreadable:{source_id}", "fault", source_id, message)
            )
            continue

        boundary_valid = not requires_boundary or (
            record.get("paper_only") is True and record.get("live_blocked") is True
        )
        status = "available" if boundary_valid else "invalid_safety_boundary"
        message = (
            ""
            if boundary_valid
            else ("source does not assert paper_only=true and live_blocked=true")
        )
        observed_utc = _record_observed_utc(record)
        try:
            file_modified_utc = _file_modified_utc(path)
        except OSError as error:
            sources[source_id] = None
            message = str(error)
            health.append(
                {
                    "source_id": source_id,
                    "path": str(relative_path).replace("\\", "/"),
                    "status": "unreadable",
                    "observed_utc": observed_utc,
                    "file_modified_utc": None,
                    "issue": message,
                }
            )
            issues.append(
                _issue(f"source_unreadable:{source_id}", "fault", source_id, message)
            )
            continue
        sources[source_id] = record if boundary_valid else None
        health.append(
            {
                "source_id": source_id,
                "path": str(relative_path).replace("\\", "/"),
                "status": status,
                "observed_utc": observed_utc,
                "file_modified_utc": file_modified_utc,
                "issue": message,
            }
        )
        if not boundary_valid:
            issues.append(
                _issue(
                    f"source_boundary_invalid:{source_id}",
                    "fault",
                    source_id,
                    message,
                )
            )
    return sources, health, issues


def _object_field(
    record: dict[str, object],
    key: str,
    source_id: str,
) -> dict[str, object]:
    value = record.get(key)
    if not isinstance(value, dict) or not all(
        isinstance(item_key, str) for item_key in value
    ):
        raise TypeError(
            f"control-center source field must be an object: source={source_id}, key={key}, actual={type(value).__name__}"
        )
    return cast(dict[str, object], value)


def _object_list_field(
    record: dict[str, object],
    key: str,
    source_id: str,
) -> list[dict[str, object]]:
    value = record.get(key)
    if not isinstance(value, list):
        raise TypeError(
            f"control-center source field must be an array: source={source_id}, key={key}, actual={type(value).__name__}"
        )
    output: list[dict[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not all(
            isinstance(item_key, str) for item_key in item
        ):
            raise TypeError(
                "control-center source array item must be an object: "
                f"source={source_id}, key={key}, index={index}"
            )
        output.append(cast(dict[str, object], item))
    return output


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


PLAYBOOK_LIST_SPECS: Final[dict[str, tuple[str, str, int]]] = {
    "short_term_bullish": ("short_term", "bullish", 10),
    "short_term_bearish": ("short_term", "bearish", 10),
    "long_term_bullish": ("long_term", "bullish", 10),
    "long_term_bearish": ("long_term", "bearish", 10),
    "overall": ("", "", 5),
}


def _playbook_rankings_state(
    playbook: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> dict[str, object] | None:
    if playbook is None:
        return None
    try:
        if playbook.get("artifact_type") != "ranked_equity_prediction_playbook":
            raise ValueError(
                "playbook artifact_type is not ranked_equity_prediction_playbook"
            )
        if playbook.get("schema_version") != "dopey-playbook-rankings-v2":
            raise ValueError(
                "playbook schema_version is unsupported: "
                f"actual={playbook.get('schema_version')!r}"
            )
        if (
            playbook.get("source_playbook_trust_version")
            != PLAYBOOK_TRUST_VERSION
        ):
            raise ValueError(
                "playbook trust semantics are unsupported: "
                f"expected={PLAYBOOK_TRUST_VERSION}, "
                "actual="
                f"{playbook.get('source_playbook_trust_version')!r}"
            )
        if playbook.get("playbook_status") not in {
            "complete_research_rankings",
            "partial_insufficient_eligible_candidates",
        }:
            raise ValueError(
                f"playbook status is not renderable: actual={playbook.get('playbook_status')!r}"
            )
        required_false = (
            "order_construction_allowed",
            "trade_promotion_allowed",
            "live_execution_allowed",
            "broker_authority",
        )
        invalid_false = [
            key for key in required_false if playbook.get(key) is not False
        ]
        if invalid_false:
            raise ValueError(
                f"playbook non-execution assertions failed: fields={invalid_false}"
            )
        if (
            playbook.get("paper_only") is not True
            or playbook.get("live_blocked") is not True
        ):
            raise ValueError(
                "playbook must assert paper_only=true and live_blocked=true"
            )
        if playbook.get("rank_score_is_not_probability") is not True:
            raise ValueError("playbook must assert rank_score_is_not_probability=true")

        lists = _object_field(playbook, "lists", "playbook_rankings")
        if set(lists) != set(PLAYBOOK_LIST_SPECS):
            raise ValueError(
                "playbook list set is incomplete: "
                f"expected={sorted(PLAYBOOK_LIST_SPECS)}, actual={sorted(lists)}"
            )
        recommendations = _object_field(
            playbook,
            "recommendations",
            "playbook_rankings",
        )
        validated_recommendations: dict[str, dict[str, object]] = {}
        for recommendation_id, raw_recommendation in recommendations.items():
            if not isinstance(raw_recommendation, dict) or not all(
                isinstance(key, str) for key in raw_recommendation
            ):
                raise TypeError(
                    "playbook recommendation must be an object: "
                    f"recommendation_id={recommendation_id}"
                )
            recommendation = cast(dict[str, object], raw_recommendation)
            if recommendation.get("recommendation_id") != recommendation_id:
                raise ValueError(
                    "playbook recommendation key does not match recommendation_id: "
                    f"key={recommendation_id}, field={recommendation.get('recommendation_id')!r}"
                )
            score = recommendation.get("research_priority_score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise TypeError(
                    "playbook research_priority_score must be numeric: "
                    f"recommendation_id={recommendation_id}"
                )
            numeric_score = float(score)
            if (
                not math.isfinite(numeric_score)
                or numeric_score < 0.0
                or numeric_score > 100.0
            ):
                raise ValueError(
                    "playbook research_priority_score must be finite and in [0, 100]: "
                    f"recommendation_id={recommendation_id}, value={score!r}"
                )
            if recommendation.get("rank_score_is_not_probability") is not True:
                raise ValueError(
                    "playbook recommendation treats rank score as a probability: "
                    f"recommendation_id={recommendation_id}"
                )
            if recommendation.get("order_construction_allowed") is not False:
                raise ValueError(
                    "playbook recommendation permits order construction: "
                    f"recommendation_id={recommendation_id}"
                )
            if recommendation.get("trade_promotion_allowed") is not False:
                raise ValueError(
                    "playbook recommendation permits trade promotion: "
                    f"recommendation_id={recommendation_id}"
                )
            if (
                recommendation.get("execution_state")
                != "research_ranked_not_execution_instruction"
            ):
                raise ValueError(
                    "playbook recommendation execution boundary is invalid: "
                    f"recommendation_id={recommendation_id}"
                )
            valuation_context = _object_field(
                recommendation,
                "valuation_context",
                f"playbook recommendation {recommendation_id}",
            )
            if valuation_context.get("valuation_gate") not in {
                "passed_current_point_in_time_valuation",
                "blocked_missing_current_valuation",
                "blocked_insufficient_valuation_evidence",
                "blocked_valuation_contradiction",
            }:
                raise ValueError(
                    "playbook recommendation valuation gate is invalid: "
                    f"recommendation_id={recommendation_id}, "
                    f"gate={valuation_context.get('valuation_gate')!r}"
                )
            valuation_fit = valuation_context.get("valuation_fit_score")
            if (
                isinstance(valuation_fit, bool)
                or not isinstance(valuation_fit, (int, float))
                or not math.isfinite(float(valuation_fit))
                or not 0.0 <= float(valuation_fit) <= 1.0
            ):
                raise ValueError(
                    "playbook recommendation valuation fit must be finite in [0, 1]: "
                    f"recommendation_id={recommendation_id}, value={valuation_fit!r}"
                )
            validated_recommendations[recommendation_id] = recommendation

        referenced_ids: set[str] = set()
        for list_id, (
            expected_horizon,
            expected_bias,
            limit,
        ) in PLAYBOOK_LIST_SPECS.items():
            raw_ids = lists[list_id]
            if not isinstance(raw_ids, list) or not all(
                isinstance(value, str) for value in raw_ids
            ):
                raise TypeError(
                    f"playbook list must be a string array: list_id={list_id}"
                )
            recommendation_ids = cast(list[str], raw_ids)
            if len(recommendation_ids) > limit:
                raise ValueError(
                    f"playbook list exceeds its governed limit: list_id={list_id}, limit={limit}"
                )
            if len(recommendation_ids) != len(set(recommendation_ids)):
                raise ValueError(
                    f"playbook list contains duplicate IDs: list_id={list_id}"
                )
            if list_id == "overall":
                symbols: list[str] = []
                for recommendation_id in recommendation_ids:
                    recommendation = validated_recommendations.get(recommendation_id)
                    if recommendation is None:
                        raise ValueError(
                            "playbook list references an unknown recommendation: "
                            f"list_id={list_id}, recommendation_id={recommendation_id}"
                        )
                    symbols.append(str(recommendation.get("symbol", "")))
                if len(symbols) != len(set(symbols)):
                    raise ValueError("playbook overall list contains duplicate symbols")
                continue
            for rank, recommendation_id in enumerate(recommendation_ids, start=1):
                recommendation = validated_recommendations.get(recommendation_id)
                if recommendation is None:
                    raise ValueError(
                        "playbook list references an unknown recommendation: "
                        f"list_id={list_id}, recommendation_id={recommendation_id}"
                    )
                if recommendation.get("category") != list_id:
                    raise ValueError(
                        "playbook recommendation category mismatch: "
                        f"list_id={list_id}, recommendation_id={recommendation_id}"
                    )
                if recommendation.get("horizon") != expected_horizon:
                    raise ValueError(
                        "playbook recommendation horizon mismatch: "
                        f"list_id={list_id}, recommendation_id={recommendation_id}"
                    )
                if recommendation.get("directional_bias") != expected_bias:
                    raise ValueError(
                        "playbook recommendation directional bias mismatch: "
                        f"list_id={list_id}, recommendation_id={recommendation_id}"
                    )
                if expected_horizon == "long_term":
                    valuation_context = _object_field(
                        recommendation,
                        "valuation_context",
                        f"playbook recommendation {recommendation_id}",
                    )
                    if valuation_context.get("valuation_gate") != (
                        "passed_current_point_in_time_valuation"
                    ):
                        raise ValueError(
                            "long-term playbook recommendation lacks a passed valuation gate: "
                            f"recommendation_id={recommendation_id}"
                        )
                if recommendation.get("rank") != rank:
                    raise ValueError(
                        "playbook recommendation rank is not ordered: "
                        f"list_id={list_id}, recommendation_id={recommendation_id}, rank={rank}"
                    )
                if expected_bias == "bearish" and not str(
                    recommendation.get("bearish_expression_policy", "")
                ).startswith("directional_research_only; no short-stock order;"):
                    raise ValueError(
                        "bearish playbook recommendation lacks the no-short-stock boundary: "
                        f"recommendation_id={recommendation_id}"
                    )
                referenced_ids.add(recommendation_id)
        if referenced_ids != set(validated_recommendations):
            raise ValueError(
                "playbook recommendations contain unlisted category records"
            )

        source_artifacts = _object_list_field(
            playbook,
            "source_artifacts",
            "playbook_rankings",
        )
        if not source_artifacts:
            raise ValueError("playbook source_artifacts cannot be empty")
        for index, source in enumerate(source_artifacts):
            source_path = source.get("path")
            source_hash = source.get("sha256")
            if not isinstance(source_path, str) or not source_path:
                raise ValueError(f"playbook source path is missing: index={index}")
            if not isinstance(source_hash, str) or len(source_hash) != 64:
                raise ValueError(f"playbook source hash is invalid: index={index}")

        content_hash = playbook.get("content_hash")
        if not isinstance(content_hash, str) or len(content_hash) != 64:
            raise ValueError("playbook content_hash must be a SHA-256 identity")
        if playbook.get("reproducibility_hash") != content_hash:
            raise ValueError(
                "playbook reproducibility_hash does not match content_hash"
            )
        hash_body = {
            key: value
            for key, value in playbook.items()
            if key not in {"content_hash", "reproducibility_hash"}
        }
        if canonical_hash(hash_body) != content_hash:
            raise ValueError("playbook content hash verification failed")
    except (TypeError, ValueError) as error:
        issues.append(
            _issue(
                "playbook_rankings_invalid",
                "fault",
                "playbook_rankings",
                str(error),
            )
        )
        return None
    return dict(playbook)


def _readiness_progress(
    readiness: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> list[dict[str, object]]:
    if readiness is None:
        return []
    try:
        bottlenecks = _object_list_field(readiness, "bottlenecks", "readiness")
    except TypeError as error:
        issues.append(
            _issue("readiness_bottlenecks_invalid", "fault", "readiness", str(error))
        )
        return []
    progress: list[dict[str, object]] = []
    for index, bottleneck in enumerate(bottlenecks):
        bottleneck_id = bottleneck.get("bottleneck_id")
        if not isinstance(bottleneck_id, str):
            issues.append(
                _issue(
                    f"readiness_bottleneck_id_invalid:{index}",
                    "fault",
                    "readiness",
                    f"bottleneck_id must be a string: index={index}",
                )
            )
            continue
        current = _number(bottleneck.get("current"))
        required = _number(bottleneck.get("required"))
        ratio = (
            None
            if current is None or required is None or required <= 0
            else min(current / required, 1.0)
        )
        progress.append(
            {
                "bottleneck_id": bottleneck_id,
                "priority": bottleneck.get("priority"),
                "current": current,
                "required": required,
                "remaining": _number(bottleneck.get("remaining")),
                "progress_ratio": ratio,
                "threshold_unchanged": bottleneck.get("threshold_unchanged") is True,
                "acceleration": bottleneck.get("acceleration"),
                "missing_checks": bottleneck.get("missing_checks"),
            }
        )
    return progress


def _schedule_lanes(
    schedule: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> list[dict[str, object]]:
    if schedule is None:
        return []
    try:
        return _object_list_field(schedule, "lanes", "schedule")
    except TypeError as error:
        issues.append(_issue("schedule_lanes_invalid", "fault", "schedule", str(error)))
        return []


def _operator_headline(
    core_state: str,
    readiness: dict[str, object] | None,
    schedule_lanes: list[dict[str, object]],
    execution_seal_state: str,
) -> str:
    core_phrases: dict[str, str] = {
        "RUNNING": "Paper research cycle running",
        "ON": "Paper research scheduler armed",
        "DRAINING": "Paper research cycle draining",
        "OFF": "Paper research scheduler offline",
        "FAULT": "Paper research control fault",
    }
    headline_parts = [core_phrases.get(core_state, "Paper research state unknown")]
    headline_parts.append(
        "execution sealed"
        if execution_seal_state == "SEALED"
        else "execution-seal fault"
    )

    due_lane_ids = [
        lane_id.replace("_", " ")
        for lane in schedule_lanes
        if lane.get("due") is True and isinstance((lane_id := lane.get("lane_id")), str)
    ]
    if due_lane_ids:
        headline_parts.append(f"{', '.join(due_lane_ids)} due")

    readiness_status = None if readiness is None else readiness.get("readiness_status")
    if isinstance(readiness_status, str):
        headline_parts.append(readiness_status.replace("_", " "))
    return "; ".join(headline_parts) + "."


def _history_symbols(
    history_manifest: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> list[str]:
    if history_manifest is None:
        return []
    try:
        files = _object_list_field(history_manifest, "data_files", "history_manifest")
    except TypeError as error:
        issues.append(
            _issue(
                "history_manifest_files_invalid",
                "fault",
                "history_manifest",
                str(error),
            )
        )
        return []
    symbols: set[str] = set()
    for index, record in enumerate(files):
        raw_symbols = record.get("symbols")
        if not isinstance(raw_symbols, list) or not all(
            isinstance(symbol, str) for symbol in raw_symbols
        ):
            issues.append(
                _issue(
                    f"history_manifest_symbols_invalid:{index}",
                    "fault",
                    "history_manifest",
                    f"data_files symbols must be a string array: index={index}",
                )
            )
            continue
        symbols.update(cast(list[str], raw_symbols))
    return sorted(symbols)


def _universe_state(
    evolving_universe: dict[str, object] | None,
    expansion_plan: dict[str, object] | None,
    history_manifest: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> dict[str, object]:
    public_lake_symbols = _history_symbols(history_manifest, issues)
    if evolving_universe is None:
        return {
            "summary": None,
            "historical_expansion_plan": expansion_plan,
            "active_symbol_count": None,
            "target_count": 500,
            "maximum_count": 500,
            "public_lake_count": len(public_lake_symbols),
            "capacity_policy": "evolving_ranked_cap",
            "symbols": [],
            "tier_counts": {},
        }
    status = evolving_universe.get("status")
    if status != "evolved":
        issues.append(
            _issue(
                "evolving_universe_not_current",
                "fault",
                "evolving_universe",
                f"evolving universe status is not evolved: actual={status!r}",
            )
        )
    maximum = evolving_universe.get("maximum_active_universe_size")
    if maximum != 500:
        issues.append(
            _issue(
                "evolving_universe_cap_invalid",
                "fault",
                "evolving_universe",
                f"evolving universe cap must be 500: actual={maximum!r}",
            )
        )
    try:
        ranked_members = _object_list_field(
            evolving_universe,
            "ranked_members",
            "evolving_universe",
        )
    except TypeError as error:
        issues.append(
            _issue(
                "evolving_universe_ranked_members_invalid",
                "fault",
                "evolving_universe",
                str(error),
            )
        )
        ranked_members = []
    symbols: list[str] = []
    tier_counts: dict[str, int] = {}
    for index, member in enumerate(ranked_members):
        symbol = member.get("symbol")
        tier = member.get("resulting_tier")
        if not isinstance(symbol, str) or not symbol:
            issues.append(
                _issue(
                    f"evolving_universe_symbol_invalid:{index}",
                    "fault",
                    "evolving_universe",
                    f"ranked member symbol must be a non-empty string: index={index}",
                )
            )
            continue
        if tier not in {"core", "probation"}:
            continue
        symbols.append(symbol)
        tier_key = str(tier)
        tier_counts[tier_key] = tier_counts.get(tier_key, 0) + 1
    if len(symbols) != len(set(symbols)):
        issues.append(
            _issue(
                "evolving_universe_duplicate_active_symbol",
                "fault",
                "evolving_universe",
                "evolving universe ranked members contain duplicate active symbols",
            )
        )
        symbols = list(dict.fromkeys(symbols))
    active_count = evolving_universe.get("active_after")
    if isinstance(active_count, bool) or not isinstance(active_count, int):
        issues.append(
            _issue(
                "evolving_universe_active_count_invalid",
                "fault",
                "evolving_universe",
                f"active_after must be an integer: actual={active_count!r}",
            )
        )
        active_count = None
    elif active_count != len(symbols):
        issues.append(
            _issue(
                "evolving_universe_active_count_mismatch",
                "fault",
                "evolving_universe",
                f"active_after does not match ranked active members: active_after={active_count}, members={len(symbols)}",
            )
        )
    if isinstance(active_count, int) and active_count > 500:
        issues.append(
            _issue(
                "evolving_universe_above_cap",
                "fault",
                "evolving_universe",
                f"active universe exceeds governed cap: active_after={active_count}, cap=500",
            )
        )
    return {
        "summary": evolving_universe,
        "historical_expansion_plan": expansion_plan,
        "active_symbol_count": active_count,
        "target_count": 500,
        "maximum_count": 500,
        "public_lake_count": len(public_lake_symbols),
        "capacity_policy": evolving_universe.get("capacity_policy"),
        "available_active_slots": evolving_universe.get("available_active_slots"),
        "promoted_symbols": evolving_universe.get("promoted_symbols"),
        "demoted_symbols": evolving_universe.get("demoted_symbols"),
        "tier_counts": tier_counts,
        "symbols": symbols,
    }


def _observatory_state(
    observatory: dict[str, object] | None,
    health: list[dict[str, object]],
    issues: list[dict[str, object]],
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    if observatory is None:
        return None, []
    try:
        snapshot = _object_field(observatory, "snapshot", "observatory")
        datasets = _object_field(snapshot, "datasets", "observatory.snapshot")
    except TypeError as error:
        issues.append(
            _issue("observatory_snapshot_invalid", "fault", "observatory", str(error))
        )
        return None, []

    source_rows: list[dict[str, object]] = []
    raw_source_rows = datasets.get("source_health")
    if not isinstance(raw_source_rows, list):
        issues.append(
            _issue(
                "observatory_source_health_invalid",
                "fault",
                "observatory",
                "observatory source_health dataset must be an array",
            )
        )
    else:
        for index, item in enumerate(raw_source_rows):
            if not isinstance(item, dict):
                issues.append(
                    _issue(
                        f"observatory_source_health_row_invalid:{index}",
                        "fault",
                        "observatory",
                        f"observatory source_health row must be an object: index={index}",
                    )
                )
                continue
            row = cast(dict[str, object], item)
            source = str(row.get("source", f"row-{index}"))
            status = str(row.get("status", "unknown"))
            normalized = {
                "source_id": f"observatory:{source}",
                "path": str(row.get("path", "")),
                "status": status,
                "observed_utc": row.get("observed_at"),
                "file_modified_utc": row.get("file_modified_utc"),
                "issue": ""
                if status == "available"
                else f"observatory source status is {status}",
            }
            source_rows.append(normalized)
            health.append(normalized)
            if status != "available":
                issues.append(
                    _issue(
                        f"observatory_source_unavailable:{source}",
                        "warning",
                        "observatory",
                        f"observatory source is not available: source={source}, status={status}",
                    )
                )

    access_issues = snapshot.get("accessIssues")
    if not isinstance(access_issues, list):
        issues.append(
            _issue(
                "observatory_access_issues_invalid",
                "fault",
                "observatory",
                "observatory accessIssues must be an array",
            )
        )
    else:
        for index, item in enumerate(access_issues):
            issues.append(
                _issue(
                    f"observatory_access_issue:{index}",
                    "warning",
                    "observatory",
                    str(item),
                )
            )
    return datasets, source_rows


def _execution_seal_state(
    constitution: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> str:
    if constitution is None:
        return "FAULT"
    required_values: dict[str, object] = {
        "paper_only": True,
        "live_blocked": True,
        "broker_authority": False,
        "order_authority": False,
        "order_construction_authority": False,
        "credential_access": False,
        "self_unlock_available": False,
    }
    mismatches = [
        key
        for key, expected in required_values.items()
        if constitution.get(key) is not expected
    ]
    if mismatches:
        issues.append(
            _issue(
                "constitution_execution_seal_invalid",
                "fault",
                "constitution",
                f"execution-seal assertions failed: fields={mismatches}",
            )
        )
        return "FAULT"
    return "SEALED"


def _paper_book_state(
    summary: dict[str, object] | None,
    ledger: dict[str, object] | None,
    issues: list[dict[str, object]],
) -> dict[str, object] | None:
    if summary is None:
        return None
    paper_book = dict(summary)
    if ledger is None:
        return paper_book
    for ledger_key, output_key in (
        ("open_positions", "open_positions"),
        ("closed_trades", "closed_positions"),
    ):
        value = ledger.get(ledger_key)
        if not isinstance(value, list):
            issues.append(
                _issue(
                    f"paper_ledger_{ledger_key}_invalid",
                    "fault",
                    "paper_ledger",
                    f"paper ledger field must be an array: key={ledger_key}",
                )
            )
            paper_book[output_key] = []
            continue
        validated: list[dict[str, object]] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict) or not all(
                isinstance(key, str) for key in item
            ):
                issues.append(
                    _issue(
                        f"paper_ledger_{ledger_key}_row_invalid:{index}",
                        "fault",
                        "paper_ledger",
                        f"paper ledger row must be an object: key={ledger_key}, index={index}",
                    )
                )
                continue
            record = cast(dict[str, object], item)
            if (
                record.get("paper_only") is not True
                or record.get("live_blocked") is not True
            ):
                issues.append(
                    _issue(
                        f"paper_ledger_{ledger_key}_boundary_invalid:{index}",
                        "fault",
                        "paper_ledger",
                        "paper ledger row does not assert paper_only=true and live_blocked=true: "
                        f"key={ledger_key}, index={index}",
                    )
                )
                continue
            validated.append(dict(record))
        paper_book[output_key] = validated
    return paper_book


def build_control_center_state_with_runner(
    repository_root: Path,
    runner: SchedulerRunner,
    generated_utc: str,
) -> dict[str, object]:
    """Build one explicit, source-attributed desktop snapshot."""

    resolved_root = repository_root.resolve()
    sources, source_health, issues = _load_sources(resolved_root)
    scheduler = inspect_research_core(resolved_root, runner)
    for index, message in enumerate(scheduler["issues"]):
        issues.append(
            _issue(
                f"scheduler_issue:{index}",
                "fault" if scheduler["state"] == "FAULT" else "warning",
                "windows_scheduler",
                message,
            )
        )

    readiness = sources["readiness"]
    schedule = sources["schedule"]
    universe_expansion_plan = sources["universe_expansion_plan"]
    evolving_universe = sources["evolving_universe"]
    history_manifest = sources["history_manifest"]
    observatory = sources["observatory"]
    readiness_progress = _readiness_progress(readiness, issues)
    schedule_lanes = _schedule_lanes(schedule, issues)
    universe = _universe_state(
        evolving_universe,
        universe_expansion_plan,
        history_manifest,
        issues,
    )
    playbook_rankings = _playbook_rankings_state(
        sources["playbook_rankings"],
        issues,
    )
    observatory_datasets, observatory_source_health = _observatory_state(
        observatory,
        source_health,
        issues,
    )
    constitution = sources["constitution"]
    execution_seal_state = _execution_seal_state(constitution, issues)
    paper_book = _paper_book_state(
        sources["paper_record"],
        sources["paper_ledger"],
        issues,
    )
    headline = _operator_headline(
        scheduler["state"],
        readiness,
        schedule_lanes,
        execution_seal_state,
    )
    llm_provider_control = provider_control_state()
    analytics = build_desktop_analytics(resolved_root)
    live_branch = build_live_branch_state(resolved_root)

    return {
        "artifact_type": "dopey_desktop_control_center_state",
        "schema_version": "dopey-desktop-control-center-v7",
        "generated_utc": generated_utc,
        "repository_root": str(resolved_root),
        "headline": headline,
        "research_core": scheduler,
        "auxiliary_schedules": scheduler["auxiliary_tasks"],
        "source_health": source_health,
        "observatory_source_health": observatory_source_health,
        "issues": issues,
        "readiness": readiness,
        "trade_readiness_frontier": sources["trade_readiness_frontier"],
        "readiness_progress": readiness_progress,
        "schedule": schedule,
        "schedule_lanes": schedule_lanes,
        "universe": universe,
        "evolving_universe": evolving_universe,
        "attention_snapshot": sources["attention_snapshot"],
        "playbook_rankings": playbook_rankings,
        "world_model": sources["world_model"],
        "metacognition": sources["metacognition"],
        "homeostasis": sources["homeostasis"],
        "observatory": observatory,
        "observatory_datasets": observatory_datasets,
        "paper_record": paper_book,
        "option_extremes": sources["option_extremes"],
        "market_extremes": sources["market_extremes"],
        "llm_research": sources["llm_research"],
        "strategy_dossier": sources["strategy_dossier"],
        "capital_exposure": sources["capital_exposure"],
        "mutation_genealogy": sources["mutation_genealogy"],
        "binomial_oracle": sources["binomial_oracle"],
        "context_settlement": sources["context_settlement"],
        "evidence_contract_audit": sources["evidence_contract_audit"],
        "evidence_cycle": sources["evidence_cycle"],
        "analytics": analytics,
        "live_branch": live_branch,
        "llm_provider_control": llm_provider_control,
        "constitution": {
            "execution_seal_state": execution_seal_state,
            "state": constitution,
        },
        "host_capabilities": {
            "control_authority": "research_routing_and_live_branch_options_gate",
            "local_compiled_ui_only": True,
            "filesystem_api_exposed": False,
            "process_api_exposed": False,
            "broker_api_exposed": False,
            "credential_api_exposed": True,
            "credential_api_scope": "write_only_openrouter_key_to_windows_dpapi_user_scope",
            "credential_value_readback_available": False,
            "research_agent_credential_access": False,
            "order_api_exposed": False,
            "live_execution_capability_present": True,
            "live_execution_transport": "official_robinhood_agentic_mcp",
            "account_identifiers_redacted": True,
        },
        "paper_only": False,
        "live_blocked": False,
        "research_branch_paper_only": True
        if execution_seal_state == "SEALED"
        else None,
    }


def build_control_center_state(repository_root: Path) -> dict[str, object]:
    """Build current desktop state using the restricted Windows connector."""

    resolved_root = repository_root.resolve()
    return build_control_center_state_with_runner(
        resolved_root,
        WindowsSchedulerRunner(resolved_root),
        datetime.now(timezone.utc).isoformat(),
    )
