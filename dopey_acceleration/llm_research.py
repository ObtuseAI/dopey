"""State-change-triggered LLM research deliberation for paper-market evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from .common import read_optional_json, stable_hash, stamped, write_json_atomic
from .frontier import run_frontier_council
from .provider_control import (
    ACTIVE_HYBRID_ROUTE_ID,
    ProviderControl,
    active_model_roster,
    load_provider_control,
    routing_policy,
)


LLM_RESEARCH_VERSION = "dopey-llm-research-deliberation-v4"
MAX_MAPPING_ITEMS = 40
MAX_SEQUENCE_ITEMS = 8
MAX_STRING_CHARACTERS = 1_200
LLM_RESEARCH_PROMPT_STATE_VERSION = "dopey-llm-prompt-state-v1"
LLM_RESEARCH_PROMPT_STATE_MAX_BYTES = 11_000
MAX_PROMPT_STRING_CHARACTERS = 320


class SourceSpec(TypedDict):
    source_id: str
    relative_path: Path
    keys: tuple[str, ...]


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    {
        "source_id": "readiness",
        "relative_path": Path("artifacts/dopey/acceleration/readiness_acceleration_plan.json"),
        "keys": (
            "readiness_status",
            "active_symbol_count",
            "starting_active_universe_target",
            "actionable_shadow_thesis_count",
            "bottlenecks",
            "intake_health",
            "context_evidence_status",
        ),
    },
    {
        "source_id": "market_world_model",
        "relative_path": Path("artifacts/dopey/vnext/world_model.json"),
        "keys": (
            "as_of",
            "symbol_context",
            "regimes",
            "contradictions",
            "known_dimension_count",
            "unknown_dimension_count",
        ),
    },
    {
        "source_id": "forward_batch",
        "relative_path": Path("artifacts/dopey/vnext/cross_sectional_operational/latest_batch_summary.json"),
        "keys": (
            "batch_status",
            "market_time",
            "completed_symbol_count",
            "abstention_count",
            "settled_count_after",
            "calibration_sample_sufficient",
            "agent_ablation_status",
            "specialist_data_gap_count",
            "validated_positive_agent_count",
            "next_minimum_settlement_date",
        ),
    },
    {
        "source_id": "equity_swing",
        "relative_path": Path("artifacts/dopey/equity_swing/equity_first_swing_summary.json"),
        "keys": (
            "run_status",
            "as_of_date",
            "actionable_shadow_thesis_count",
            "actionable_symbols",
            "external_context_veto_count",
            "contract_blocker_counts",
            "context_evidence_gate",
            "limitations",
        ),
    },
    {
        "source_id": "market_extremes",
        "relative_path": Path("artifacts/dopey/playbook/market_extremes_report.json"),
        "keys": (
            "as_of_date",
            "biggest_mover_count",
            "top_gainers",
            "top_losers",
            "biggest_movers",
        ),
    },
    {
        "source_id": "option_extremes",
        "relative_path": Path("artifacts/dopey/playbook/option_extremes_report.json"),
        "keys": (
            "as_of_date",
            "top_winners",
            "top_losers",
            "limitations",
        ),
    },
    {
        "source_id": "strategy_invention",
        "relative_path": Path("artifacts/dopey/autoresearch/latest_cycle.json"),
        "keys": (
            "generation",
            "cycle_status",
            "finding_status",
            "candidate_count",
            "candidates",
            "evaluation_task_suite",
        ),
    },
    {
        "source_id": "strategy_engineering",
        "relative_path": Path("artifacts/dopey/strategy_engineering/latest_cycle.json"),
        "keys": (
            "cycle_status",
            "forward_candidate_count",
            "shadow_admitted_count",
            "forward_candidates",
            "gate_decisions",
            "reverse_report",
            "quality_diversity_archive",
        ),
    },
    {
        "source_id": "promotion",
        "relative_path": Path("artifacts/dopey/autoresearch/latest_promotion_cycle.json"),
        "keys": (
            "cycle_status",
            "evaluation_status",
            "activated_blueprint_count",
            "registry_appended_count",
            "matrix",
        ),
    },
    {
        "source_id": "cognitive_evidence",
        "relative_path": Path("artifacts/dopey/intelligence_research/latest_evidence_cycle.json"),
        "keys": (
            "cycle_status",
            "evidence_status",
            "visible_task_count",
            "independent_task_count",
            "missing_independent_partitions",
            "method_evidence",
            "evaluations",
            "activated_method_ids",
        ),
    },
    {
        "source_id": "coach_proposal_quarantine",
        "relative_path": Path("artifacts/dopey/two_coach/mutation_proposals/latest_batch.json"),
        "keys": (
            "batch_hash",
            "batch_status",
            "outcome_status",
            "proposal_count",
            "linked_proposal_count",
            "blocked_proposal_count",
            "orphan_experiment_count",
            "source_session_count",
            "evidence_weight",
            "mutation_targets_resolved",
            "next_gate",
            "automatic_apply_allowed",
            "strategy_mutation_allowed",
            "strategy_promotion_allowed",
        ),
    },
)


PROMPT_CONTENT_KEYS: dict[str, tuple[str, ...]] = {
    "readiness": (
        "readiness_status",
        "active_symbol_count",
        "starting_active_universe_target",
        "actionable_shadow_thesis_count",
        "bottlenecks",
        "intake_health",
        "context_evidence_status",
    ),
    "market_world_model": (
        "as_of",
        "symbol_context",
        "contradictions",
        "known_dimension_count",
        "unknown_dimension_count",
    ),
    "forward_batch": (
        "batch_status",
        "market_time",
        "completed_symbol_count",
        "abstention_count",
        "settled_count_after",
        "calibration_sample_sufficient",
        "agent_ablation_status",
        "specialist_data_gap_count",
        "validated_positive_agent_count",
        "next_minimum_settlement_date",
    ),
    "equity_swing": (
        "run_status",
        "as_of_date",
        "actionable_shadow_thesis_count",
        "external_context_veto_count",
        "contract_blocker_counts",
        "context_evidence_gate",
        "limitations",
    ),
    "market_extremes": (
        "as_of_date",
        "biggest_mover_count",
        "biggest_movers",
    ),
    "option_extremes": (
        "as_of_date",
        "top_winners",
        "top_losers",
        "limitations",
    ),
    "strategy_invention": (
        "generation",
        "cycle_status",
        "finding_status",
        "candidate_count",
    ),
    "strategy_engineering": (
        "cycle_status",
        "forward_candidate_count",
        "shadow_admitted_count",
        "gate_decisions",
        "reverse_report",
        "quality_diversity_archive",
    ),
    "promotion": (
        "cycle_status",
        "evaluation_status",
        "activated_blueprint_count",
        "registry_appended_count",
        "matrix",
    ),
    "cognitive_evidence": (
        "cycle_status",
        "evidence_status",
        "visible_task_count",
        "independent_task_count",
        "missing_independent_partitions",
        "method_evidence",
        "evaluations",
        "activated_method_ids",
    ),
    "coach_proposal_quarantine": (
        "batch_hash",
        "batch_status",
        "outcome_status",
        "proposal_count",
        "linked_proposal_count",
        "blocked_proposal_count",
        "orphan_experiment_count",
        "source_session_count",
        "evidence_weight",
        "mutation_targets_resolved",
        "next_gate",
        "automatic_apply_allowed",
        "strategy_mutation_allowed",
        "strategy_promotion_allowed",
    ),
}


PROMPT_MAPPING_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("readiness", "intake_health"): (
        "news_pipeline_status",
        "news_required_coverage_complete",
        "news_failed_source_ids",
    ),
    ("equity_swing", "contract_blocker_counts"): (
        "equity_thesis_not_actionable",
    ),
    ("equity_swing", "context_evidence_gate"): (
        "evidence_status",
        "context_decision_ledger_count",
        "context_outcome_ledger_count",
        "pending_context_decision_count",
        "minimum_resolved_decisions",
        "joint_snapshot_day_count",
        "minimum_snapshot_days",
        "minimum_walk_forward_eras",
        "required_next_evidence",
        "positive_context_promotion_allowed",
        "context_sizing_allowed",
    ),
    ("strategy_engineering", "reverse_report"): (
        "reverse_status",
        "hypothesis_count",
        "settled_case_count",
        "transferable_association_count",
        "uses_only_settled_point_in_time_cases",
        "automatic_promotion_allowed",
        "causal_claim_allowed",
    ),
    ("strategy_engineering", "quality_diversity_archive"): (
        "archive_version",
        "candidate_count",
        "occupied_cell_count",
        "promotion_allowed",
        "single_scalar_champion_selected",
    ),
    ("promotion", "matrix"): (
        "matrix_hash",
        "matrix_version",
        "automatic_research_activation_count",
        "backtest_only_activation_allowed",
        "candidate_self_activation_allowed",
        "execution_effect",
        "readiness_effect",
        "human_review_required",
    ),
}


PROMPT_SEQUENCE_ITEM_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("readiness", "bottlenecks"): (
        "bottleneck_id",
        "priority",
        "current",
        "required",
        "recorded_decisions",
        "remaining",
        "pending_maturity_or_settlement",
        "threshold_unchanged",
    ),
    ("market_extremes", "biggest_movers"): (
        "symbol",
        "direction",
        "latest_return_pct",
        "return_zscore",
        "is_trade_signal",
    ),
    ("option_extremes", "top_winners"): (
        "symbol",
        "contract_key",
        "entry_date",
        "exit_date",
        "roi_pct",
        "underlying_return_pct",
        "is_trade_signal",
        "research_role",
    ),
    ("option_extremes", "top_losers"): (
        "symbol",
        "contract_key",
        "entry_date",
        "exit_date",
        "roi_pct",
        "underlying_return_pct",
        "is_trade_signal",
        "research_role",
    ),
    ("strategy_engineering", "gate_decisions"): (
        "subject_id",
        "decision_hash",
        "decision",
        "passed",
        "failed_rules",
        "missing_metrics",
        "positive_promotion_allowed",
        "readiness_effect",
        "execution_effect",
    ),
    ("cognitive_evidence", "method_evidence"): (
        "method_id",
        "effect_size",
        "transfer_score",
        "visible_samples",
        "private_samples",
        "external_samples",
        "real_task_samples",
        "evaluator_independent",
        "reward_hacking_detected",
    ),
    ("cognitive_evidence", "evaluations"): (
        "method_id",
        "evaluation_hash",
        "promotion_state",
        "failed_thresholds",
        "automatic_cognitive_method_activation_allowed",
        "authority_effect",
    ),
}


PROMPT_SEQUENCE_SAMPLE_LIMITS: dict[tuple[str, str], int] = {
    ("readiness", "bottlenecks"): 3,
    ("market_world_model", "contradictions"): 2,
    ("equity_swing", "limitations"): 1,
    ("market_extremes", "biggest_movers"): 2,
    ("option_extremes", "top_winners"): 1,
    ("option_extremes", "top_losers"): 1,
    ("option_extremes", "limitations"): 2,
    ("strategy_engineering", "gate_decisions"): 0,
    ("cognitive_evidence", "missing_independent_partitions"): 3,
    ("cognitive_evidence", "method_evidence"): 0,
    ("cognitive_evidence", "evaluations"): 0,
}


def _bounded_value(value: Any, depth: int) -> Any:
    if depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return {"truncated_type": type(value).__name__, "item_count": len(value)}
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_STRING_CHARACTERS]
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda item: str(item[0]))[:MAX_MAPPING_ITEMS]
        return {str(key): _bounded_value(item, depth - 1) for key, item in items}
    if isinstance(value, (list, tuple)):
        return [_bounded_value(item, depth - 1) for item in value[:MAX_SEQUENCE_ITEMS]]
    raise TypeError(f"LLM research state contains an unsupported value type: {type(value).__name__}")


def _source_state(repo_root: Path, spec: SourceSpec) -> dict[str, Any]:
    path = repo_root / spec["relative_path"]
    source, availability = read_optional_json(path)
    if availability != "available":
        return {
            "source_id": spec["source_id"],
            "availability": availability,
            "relative_path": spec["relative_path"].as_posix(),
            "content": {},
        }
    selected = {key: source[key] for key in spec["keys"] if key in source}
    return {
        "source_id": spec["source_id"],
        "availability": availability,
        "relative_path": spec["relative_path"].as_posix(),
        "selected_content_hash": stable_hash(selected),
        "content": _bounded_value(selected, 5),
    }


def _provider_routes(control: ProviderControl) -> tuple[tuple[str, ...], tuple[str, ...]]:
    providers = control["providers"]
    if not providers["openrouter"] or not providers["openrouter_hybrid"]:
        raise RuntimeError(
            "the governed OpenRouter four-model hybrid is disabled; independent Claude and Codex routes are retired"
        )
    return (ACTIVE_HYBRID_ROUTE_ID,), ()


def build_llm_research_state(repo_root: Path, provider_control: ProviderControl) -> dict[str, Any]:
    resolved_root = repo_root.resolve()
    sources = [_source_state(resolved_root, spec) for spec in SOURCE_SPECS]
    return {
        "state_version": "dopey-llm-semantic-state-v4",
        "sources": sources,
        "operator_research_routing": {
            **provider_control,
            "active_model_roster": active_model_roster(),
            "routing_policy": routing_policy(),
        },
        "constitutional_constraints": {
            "paper_only": True,
            "live_blocked": True,
            "broker_access": False,
            "order_authority": False,
            "llm_output_is_unverified_hypothesis_only": True,
            "llm_cannot_promote_candidates": True,
            "settlement_and_held_out_evidence_remain_authoritative": True,
        },
    }


def _prompt_string(value: str) -> str:
    return value[:MAX_PROMPT_STRING_CHARACTERS]


def _prompt_value(source_id: str, key: str, value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _prompt_string(value)
    if isinstance(value, dict):
        selected_keys = PROMPT_MAPPING_KEYS.get((source_id, key), ())
        return {
            selected_key: _prompt_value(source_id, selected_key, value[selected_key])
            for selected_key in selected_keys
            if selected_key in value
        }
    if isinstance(value, (list, tuple)):
        sample_limit = PROMPT_SEQUENCE_SAMPLE_LIMITS.get((source_id, key), 1)
        item_keys = PROMPT_SEQUENCE_ITEM_KEYS.get((source_id, key), ())
        sample: list[Any] = []
        for item in value[:sample_limit]:
            if isinstance(item, dict):
                sample.append(
                    {
                        item_key: _prompt_value(source_id, item_key, item[item_key])
                        for item_key in item_keys
                        if item_key in item
                    }
                )
            elif item is None or isinstance(item, (bool, int, float)):
                sample.append(item)
            elif isinstance(item, str):
                sample.append(_prompt_string(item))
            else:
                raise TypeError(
                    "LLM research prompt sequence contains an unsupported value type: "
                    f"source_id={source_id}, key={key}, actual={type(item).__name__}"
                )
        return {
            "item_count": len(value),
            "content_hash": stable_hash({"items": list(value)}),
            "sample": sample,
        }
    raise TypeError(
        "LLM research prompt state contains an unsupported value type: "
        f"source_id={source_id}, key={key}, actual={type(value).__name__}"
    )


def _prompt_source(source: dict[str, Any]) -> dict[str, Any]:
    source_id = source.get("source_id")
    if not isinstance(source_id, str):
        raise TypeError("LLM research source_id must be a string")
    content = source.get("content")
    if not isinstance(content, dict):
        raise TypeError(f"LLM research source content must be an object: source_id={source_id}")
    keys = PROMPT_CONTENT_KEYS.get(source_id)
    if keys is None:
        raise ValueError(f"LLM research prompt projection lacks a source policy: source_id={source_id}")
    return {
        "source_id": source_id,
        "availability": source.get("availability"),
        "selected_content_hash": source.get("selected_content_hash", stable_hash(content)),
        "content": {
            key: _prompt_value(source_id, key, content[key])
            for key in keys
            if key in content
        },
    }


def _serialized_bytes(record: dict[str, Any]) -> int:
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return len(payload.encode("utf-8"))


def build_llm_research_prompt_state(
    semantic_state: dict[str, Any],
    semantic_state_hash: str,
) -> dict[str, Any]:
    raw_sources = semantic_state.get("sources")
    if not isinstance(raw_sources, list):
        raise TypeError("LLM research semantic sources must be an array")
    sources: list[dict[str, Any]] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            raise TypeError("LLM research semantic source must be an object")
        sources.append(_prompt_source(source))
    projection = {
        "prompt_state_version": LLM_RESEARCH_PROMPT_STATE_VERSION,
        "semantic_state_version": semantic_state.get("state_version"),
        "semantic_state_hash": semantic_state_hash,
        "source_count": len(sources),
        "sources": sources,
        "operator_research_routing": semantic_state.get("operator_research_routing"),
        "constitutional_constraints": semantic_state.get("constitutional_constraints"),
        "projection_policy": {
            "source_hashes_preserved": True,
            "readiness_and_blockers_preserved": True,
            "collection_samples_are_hash_backed": True,
            "raw_candidate_prose_included": False,
            "raw_coach_proposal_prose_included": False,
        },
    }
    projection_bytes = _serialized_bytes(projection)
    if projection_bytes > LLM_RESEARCH_PROMPT_STATE_MAX_BYTES:
        raise RuntimeError(
            "LLM research prompt projection exceeds its deterministic byte budget: "
            f"bytes={projection_bytes}, maximum={LLM_RESEARCH_PROMPT_STATE_MAX_BYTES}"
        )
    return projection


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        handle.flush()


def _council_evidence(council: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    raw_results = council.get("results", [])
    if not isinstance(raw_results, list):
        raise TypeError("frontier council results must be an array")
    for raw_record in raw_results:
        if not isinstance(raw_record, dict):
            raise TypeError("frontier council result must be an object")
        results.append(
            {
                key: value
                for key, value in raw_record.items()
                if key not in {"output", "stderr_tail"}
            }
        )
    return {
        key: value
        for key, value in {**council, "results": results}.items()
        if key not in {"repo_write_access"}
    }


def _successful_analyses(council: dict[str, Any]) -> list[dict[str, Any]]:
    analyses: list[dict[str, Any]] = []
    raw_results = council.get("results", [])
    if not isinstance(raw_results, list):
        raise TypeError("frontier council results must be an array")
    for record in raw_results:
        if not isinstance(record, dict):
            raise TypeError("frontier council result must be an object")
        component_analyses = record.get("component_analyses")
        if record.get("status") == "completed_analysis_only" and isinstance(component_analyses, list):
            for component in component_analyses:
                if not isinstance(component, dict) or not isinstance(component.get("analysis"), dict):
                    raise TypeError("hybrid component analysis must be a structured object")
                analyses.append(
                    {
                        "provider": str(component.get("provider", "unknown")),
                        "model": str(component.get("model", "unknown")),
                        "analysis": component["analysis"],
                    }
                )
        analysis = record.get("structured_analysis")
        if record.get("status") == "completed_analysis_only" and isinstance(analysis, dict):
            analyses.append(
                {
                    "provider": str(record.get("provider", "unknown")),
                    "model": str(record.get("model", "unknown")),
                    "analysis": analysis,
                }
            )
    if not analyses:
        raise RuntimeError("LLM discovery council produced no successful structured analyses")
    return analyses


def _hybrid_synthesis_evidence(discovery: dict[str, Any]) -> dict[str, Any]:
    discovery_evidence = _council_evidence(discovery)
    raw_results = discovery_evidence.get("results", [])
    if not isinstance(raw_results, list):
        raise TypeError("frontier council results must be an array")
    final_results = [
        record
        for record in raw_results
        if isinstance(record, dict)
        and record.get("provider") == ACTIVE_HYBRID_ROUTE_ID
        and record.get("status") == "completed_analysis_only"
        and isinstance(record.get("structured_analysis"), dict)
    ]
    if len(final_results) != 1:
        raise RuntimeError(
            "OpenRouter hybrid must produce one Claude-adjudicated structured result: "
            f"completed_final_result_count={len(final_results)}"
        )
    return {
        "council_id": discovery_evidence.get("council_id"),
        "status": "complete_reused_hybrid_final_adjudication",
        "providers": [ACTIVE_HYBRID_ROUTE_ID],
        "requested_provider_count": 1,
        "completed_provider_count": 1,
        "results": final_results,
        "synthesis_source": "discovery_hybrid_claude_final_adjudication",
        "reused_discovery_result_count": 1,
        "additional_frontier_call_count": 0,
        "additional_frontier_call_performed": False,
        "additional_reported_cost_usd": 0.0,
        "reused_discovery_cost_counted_again": False,
    }


def _reported_cost(councils: tuple[dict[str, Any], ...]) -> float:
    total = 0.0
    for council in councils:
        raw_results = council.get("results", [])
        if not isinstance(raw_results, list):
            continue
        for record in raw_results:
            if not isinstance(record, dict):
                continue
            usage = record.get("usage")
            if isinstance(usage, dict):
                cost = usage.get("cost")
                if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                    total += float(cost)
    return round(total, 8)


def _provider_models(councils: tuple[dict[str, Any], ...]) -> list[str]:
    models: list[str] = []
    for council in councils:
        raw_results = council.get("results", [])
        if not isinstance(raw_results, list):
            continue
        for record in raw_results:
            if not isinstance(record, dict) or record.get("status") != "completed_analysis_only":
                continue
            component_models = record.get("component_models")
            if isinstance(component_models, list):
                for component_model in component_models:
                    if isinstance(component_model, str) and component_model not in models:
                        models.append(component_model)
                if component_models:
                    continue
            model = record.get("model")
            if isinstance(model, str) and model not in models:
                models.append(model)
    return models


def run_llm_research_cycle(
    repo_root: Path,
    output_root: Path,
    timeout_seconds: int,
    force: bool,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("LLM research issued_at must be timezone-aware")
    if timeout_seconds < 30:
        raise ValueError(f"LLM research timeout must be at least 30 seconds: actual={timeout_seconds}")
    provider_control = load_provider_control()
    discovery_providers, synthesis_providers = _provider_routes(provider_control)
    state = build_llm_research_state(repo_root, provider_control)
    state_hash = stable_hash(state)
    prompt_state = build_llm_research_prompt_state(state, state_hash)
    prompt_state_hash = stable_hash(prompt_state)
    prompt_state_bytes = _serialized_bytes(prompt_state)
    latest_path = output_root / "latest_cycle.json"
    latest, availability = read_optional_json(latest_path)
    if (
        not force
        and availability == "available"
        and latest.get("cycle_status") == "complete_analysis_current"
        and latest.get("semantic_state_hash") == state_hash
    ):
        reuse_record = stamped(
            {
                "artifact_type": "llm_research_cycle_event",
                "cycle_version": LLM_RESEARCH_VERSION,
                "cycle_status": "complete_analysis_current",
                "analysis_action": "reused_unchanged_state",
                "issued_at": issued_at.astimezone(timezone.utc).isoformat(),
                "semantic_state_hash": state_hash,
                "latest_cycle_path": str(latest_path),
                "paper_only": True,
                "live_blocked": True,
                "readiness_effect": "none",
                "authority_effect": "none",
            }
        )
        _append_jsonl(output_root / "llm_research_ledger.jsonl", reuse_record)
        return {**latest, "runtime_event": reuse_record}

    discovery_objective = (
        "Interrogate the newest DOPEY evidence for stock and options research through the governed four-model "
        "OpenRouter hybrid: Gemini evidence mapping and Luna hypothesis scouting in parallel, GLM adversarial deep "
        "review, then Claude final adjudication. Identify falsifiable market-research hypotheses, hidden failure modes, "
        "missing evidence, and the highest-information paper-only experiments. Treat movers, patterns, indicators, "
        "backtests, and model-priced options as evidence inputs rather than answers. Prefer abstention when evidence is "
        "weak. The operator-selected paper-research expression is "
        f"{provider_control['instrument_mode']}."
    )
    discovery = run_frontier_council(
        discovery_objective,
        discovery_providers,
        prompt_state,
        timeout_seconds,
    )
    independent_analyses = _successful_analyses(discovery)
    completed_discovery_count = discovery.get("completed_provider_count")
    if completed_discovery_count != len(discovery_providers):
        completed_providers = [analysis["provider"] for analysis in independent_analyses]
        raise RuntimeError(
            "LLM discovery council is incomplete; the governed hybrid route is required: "
            f"completed={completed_providers}, required={list(discovery_providers)}"
        )
    discovery_evidence = _council_evidence(discovery)
    synthesis_evidence = _hybrid_synthesis_evidence(discovery)
    body = {
        "artifact_type": "state_change_triggered_llm_research_cycle",
        "cycle_version": LLM_RESEARCH_VERSION,
        "cycle_status": "complete_analysis_current",
        "analysis_action": (
            "generated_forced_refresh"
            if force
            else "generated_for_changed_state" if availability == "available" else "generated_initial_analysis"
        ),
        "issued_at": issued_at.astimezone(timezone.utc).isoformat(),
        "semantic_state_hash": state_hash,
        "source_state": state,
        "prompt_state": prompt_state,
        "prompt_state_hash": prompt_state_hash,
        "prompt_state_bytes": prompt_state_bytes,
        "prompt_state_max_bytes": LLM_RESEARCH_PROMPT_STATE_MAX_BYTES,
        "discovery_council": discovery_evidence,
        "synthesis_council": synthesis_evidence,
        "provider_models": _provider_models((discovery,)),
        "provider_control": state["operator_research_routing"],
        "discovery_provider_routes": list(discovery_providers),
        "synthesis_provider_routes": list(synthesis_providers),
        "additional_synthesis_frontier_call_performed": False,
        "instrument_mode": provider_control["instrument_mode"],
        "reported_openrouter_cost_usd": _reported_cost((discovery,)),
        "automatic_activation_count": 0,
        "automatic_promotion_count": 0,
        "candidate_self_evaluation_allowed": False,
        "llm_output_evidence_class": "unverified_research_hypothesis",
        "readiness_effect": "none",
        "authority_effect": "none",
        "permission_effect": "none",
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order_authority": True,
    }
    output = stamped(body)
    write_json_atomic(latest_path, output)
    _append_jsonl(
        output_root / "llm_research_ledger.jsonl",
        {
            "artifact_type": "llm_research_cycle_event",
            "cycle_version": LLM_RESEARCH_VERSION,
            "cycle_status": output["cycle_status"],
            "analysis_action": output["analysis_action"],
            "issued_at": output["issued_at"],
            "semantic_state_hash": state_hash,
            "reproducibility_hash": output["reproducibility_hash"],
            "provider_models": output["provider_models"],
            "reported_openrouter_cost_usd": output["reported_openrouter_cost_usd"],
            "paper_only": True,
            "live_blocked": True,
        },
    )
    return output
