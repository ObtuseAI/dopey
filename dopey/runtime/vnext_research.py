"""Accelerated operational vNext vertical slice for one symbol.

The runner reads validated local evidence, builds technical and world-model
evidence, runs a deterministic adversarial organism, evaluates metacognition,
and appends a shadow-only forward prediction. It never reads or writes an
execution command and never changes the protected readiness gate.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dopey.chronos.clocks import ClockDomain, ClockStamp, validate_clock_stamp
from dopey.chronos.stale_state import calibration_context_or_unavailable, validate_point_in_time_artifact
from dopey.constitution.authority import Authority
from dopey.constitution.execution_seal import assert_output_research_only, execution_seal_state
from dopey.constitution.readiness_law import assert_readiness_is_external
from dopey.derivatives.evidence import build_options_surface_evidence
from dopey.fundamentals.evidence import build_earnings_event_evidence, build_fundamental_evidence
from dopey.gates.evaluator import evaluate_gate
from dopey.gates.policy import policy_by_id
from dopey.governor.governor import govern_research_objective
from dopey.homeostasis.controller import evaluate_homeostasis
from dopey.metabolism.controller import plan_research_allocation
from dopey.metabolism.ledger import ResourceBudget, ResourceUsage, evaluate_resource_usage
from dopey.metacognition.control_loop import choose_closed_loop_control
from dopey.metacognition.evaluator import evaluate_metacognition
from dopey.memory.episodes import append_episode
from dopey.memory.observations import append_observation
from dopey.macro.credit import build_credit_proxy_evidence
from dopey.organisms.runtime import run_research_organism
from dopey.protocols.identity import canonical_hash
from dopey.settlement.predictions import append_prediction, build_forward_prediction
from dopey.shadows.shadow import run_shadow_controller
from dopey.technical.evidence import build_multi_timeframe_technical_evidence
from dopey.technical.history_adapter import load_default_validated_symbol_history
from dopey.world_model.enrichment import enrich_world_model
from dopey.world_model.state import build_world_model


@dataclass(frozen=True)
class VNextRunPaths:
    output_dir: Path
    cross_asset_context: Path
    news_context: Path
    calibration_summary: Path
    cross_section_context: Path
    macro_manifest: Path
    fundamental_file_reference: str
    options_manifest: Path
    earnings_directory: Path


def _load_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"vNext required input artifact is missing: path={path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"vNext input artifact must be a JSON object: path={path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _final_control(metacognitive_control: str, shadow_decision: str) -> str:
    downgrade_rank = {
        "NO_DOWNGRADE": 0,
        "ADD_ADVERSARY": 1,
        "EXPAND_EVIDENCE": 2,
        "ABSTAIN": 3,
        "TERMINATE": 4,
    }
    metacognitive_rank = downgrade_rank.get(metacognitive_control, 0)
    shadow_rank = downgrade_rank.get(shadow_decision, 0)
    return shadow_decision if shadow_rank > metacognitive_rank else metacognitive_control


def _resolve_research_conclusion(
    preliminary_control: str,
    closed_loop: dict[str, Any],
    metabolism: dict[str, Any],
) -> str:
    selected_control = str(closed_loop["selected_control"])
    low_yield_termination = bool(metabolism["automatic_low_yield_termination"])
    if (
        preliminary_control == "ABSTAIN"
        and selected_control == "TERMINATE"
        and low_yield_termination
    ):
        return "ABSTAIN"
    return _final_control(preliminary_control, selected_control)


def run_vnext_research(
    symbol: str,
    objective_type: str,
    event_time: str,
    market_time: str,
    paths: VNextRunPaths,
) -> dict[str, Any]:
    started = time.perf_counter()
    seal = execution_seal_state()
    symbol_history, history_proof = load_default_validated_symbol_history(symbol)
    clock = ClockStamp(
        domain=ClockDomain.DAILY,
        event_time=event_time,
        market_time=market_time,
        data_version=str(history_proof["actual_sha256"]),
        agent_version="dopey-fixed-organism-v1",
        policy_version="dopey-constitution-v1",
        model_version="deterministic-no-generative-model-v1",
        parent_event_id="",
        session_id=canonical_hash(
            {
                "symbol": symbol,
                "objective_type": objective_type,
                "event_time": event_time,
                "market_time": market_time,
            }
        )[:24],
    )
    validate_clock_stamp(clock)
    technical = build_multi_timeframe_technical_evidence(symbol, symbol_history, clock)
    cross_asset = _load_object(paths.cross_asset_context)
    news = _load_object(paths.news_context)
    raw_calibration = _load_object(paths.calibration_summary)
    input_time_proofs = {
        "cross_asset": validate_point_in_time_artifact(
            cross_asset,
            "cross_asset_context",
            event_time,
            ("decision_date", "as_of_date"),
            48.0,
        ),
        "news": validate_point_in_time_artifact(
            news,
            "news_context",
            event_time,
            ("decision_time",),
            72.0,
        ),
    }
    calibration, calibration_proof = calibration_context_or_unavailable(
        raw_calibration,
        event_time,
        24.0 * 35.0,
    )
    input_time_proofs["calibration"] = calibration_proof
    fundamental = build_fundamental_evidence(
        symbol,
        event_time,
        market_time,
        paths.macro_manifest,
        paths.fundamental_file_reference,
    )
    options_surface = build_options_surface_evidence(
        symbol,
        event_time,
        market_time,
        paths.options_manifest,
    )
    earnings_event = build_earnings_event_evidence(
        symbol,
        event_time,
        market_time,
        paths.earnings_directory,
    )
    credit_proxy = build_credit_proxy_evidence(event_time, market_time)
    for evidence_name, evidence in (
        ("fundamental", fundamental),
        ("options_surface", options_surface),
        ("earnings_event", earnings_event),
        ("credit_proxy", credit_proxy),
    ):
        input_time_proofs[evidence_name] = {
            "status": "point_in_time_valid",
            "evidence_id": evidence["evidence_id"],
            "evidence_status": evidence["evidence_status"],
            "observed_at": evidence["observed_at"],
        }
    world_model = build_world_model(technical, cross_asset, news, clock)
    cross_section = _load_object(paths.cross_section_context)
    input_time_proofs["cross_section"] = validate_point_in_time_artifact(
        cross_section,
        "cross_sectional_context",
        market_time,
        ("as_of",),
        8.0,
    )
    accepted_time_statuses = {
        "point_in_time_valid",
        "excluded_missing_point_in_time_timestamp",
    }
    point_in_time_complete = all(
        str(proof.get("status", "")) in accepted_time_statuses
        for proof in input_time_proofs.values()
    )
    if not point_in_time_complete:
        raise ValueError("vNext input point-in-time proof is incomplete")
    point_in_time_proof_id = f"vnext-input-time-proof:{canonical_hash(input_time_proofs)[:24]}"
    input_time_proofs = {
        "artifact_type": "vnext_input_time_proofs",
        "proof_version": "dopey-vnext-point-in-time-v1",
        "proof_id": point_in_time_proof_id,
        "point_in_time_complete": True,
        "inputs": input_time_proofs,
        "paper_only": True,
        "live_blocked": True,
    }
    world_model = enrich_world_model(world_model, cross_section, cross_asset, credit_proxy)
    evidence_profile = {
        "technical_measurement_count": technical["measurement_count"],
        "structure_pattern_evidence_count": technical["structure_pattern_evidence_count"],
        "known_world_dimension_count": world_model["known_dimension_count"],
        "unknown_world_dimension_count": world_model["unknown_dimension_count"],
        "world_model_contradiction_count": len(world_model["contradictions"]),
        "out_of_distribution": False,
    }
    governor, contracts = govern_research_objective(objective_type, symbol, 700, evidence_profile)
    available_evidence_types = (
        "technical_measurement",
        "technical_structure_pattern_evidence",
        "shared_market_world_model",
        "cross_sectional_market_context",
        "validated_credit_proxy",
        *(("validated_fundamental_evidence",) if fundamental["evidence_type"] == "validated_fundamental_evidence" else ()),
        *(("validated_options_surface",) if options_surface["evidence_type"] == "validated_options_surface" else ()),
        *(("validated_earnings_event",) if earnings_event["evidence_type"] == "validated_earnings_event" else ()),
        *(("calibration_summary",) if int(calibration.get("settled_total", 0) or 0) > 0 else ()),
    )
    specialist_evidence = {
        "technical_measurement": technical,
        "technical_structure_pattern_evidence": technical,
        "shared_market_world_model": world_model,
        "cross_sectional_market_context": cross_section,
        "validated_credit_proxy": credit_proxy,
        "validated_fundamental_evidence": fundamental,
        "validated_options_surface": options_surface,
        "validated_earnings_event": earnings_event,
        "calibration_summary": calibration,
    }
    organism, agent_results = run_research_organism(
        objective_type,
        symbol,
        contracts,
        technical,
        world_model,
        clock,
        available_evidence_types,
        specialist_evidence,
    )
    elapsed_before_control = time.perf_counter() - started
    usage = ResourceUsage(
        data_calls=len(symbol_history),
        provider_calls=0,
        tokens=0,
        cpu_seconds=elapsed_before_control,
        peak_memory_mb=0.0,
        simulation_count=0,
        backtest_count=0,
        option_chain_rows=int(options_surface.get("values", {}).get("row_count", 0) or 0),
        storage_bytes=0,
        wall_seconds=elapsed_before_control,
    )
    budget = ResourceBudget(
        maximum_data_calls=max(len(symbol_history) * 2, 1),
        maximum_provider_calls=0,
        maximum_tokens=0,
        maximum_cpu_seconds=30.0,
        maximum_peak_memory_mb=1024.0,
        maximum_simulations=0,
        maximum_backtests=0,
        maximum_option_chain_rows=max(int(options_surface.get("values", {}).get("row_count", 0) or 0) * 2, 1),
        maximum_storage_bytes=50_000_000,
        maximum_wall_seconds=30.0,
    )
    resource_ledger = evaluate_resource_usage(usage, budget)
    hypothesis_values = [float(value) for value in organism["hypotheses"].values()]
    metacognition = evaluate_metacognition(
        objective_type,
        Authority.RESEARCH,
        technical,
        world_model,
        agent_results,
        hypothesis_values,
        calibration,
        resource_ledger,
    )
    evidence_records = [
        *list(technical["measurements"]),
        *list(technical["structure_pattern_evidence"]),
        fundamental,
        options_surface,
        earnings_event,
        credit_proxy,
        world_model,
    ]
    shadow = run_shadow_controller(
        organism,
        agent_results,
        evidence_records,
        metacognition,
        resource_ledger,
        event_time,
        72.0,
    )
    metabolism = plan_research_allocation(
        contracts,
        agent_results,
        metacognition,
        resource_ledger,
        250,
    )
    known = int(world_model["known_dimension_count"])
    unknown = int(world_model["unknown_dimension_count"])
    total_dimensions = max(known + unknown, 1)
    lane_completion = float(
        cross_asset.get("context_status") == "complete"
        and news.get("pipeline_status") == "complete"
        and bool(cross_section.get("evidence_id"))
    )
    operational_metrics = {
        "lane_completion": lane_completion,
        "option_chain_continuity": float(options_surface["evidence_type"] == "validated_options_surface"),
        "universe_health": min(1.0, int(cross_section.get("validated_symbol_count", 0) or 0) / 55.0),
        "model_dependence": 0.0,
        "archive_diversity": min(1.0, len(agent_results) / 15.0),
        "research_backlog_pressure": unknown / total_dimensions,
        "phantom_signal_coverage": min(1.0, int(calibration.get("settled_total", 0) or 0) / 200.0),
    }
    homeostasis = evaluate_homeostasis(
        world_model,
        metacognition,
        resource_ledger,
        True,
        1.0,
        operational_metrics,
    )
    closed_loop = choose_closed_loop_control(
        metacognition,
        shadow,
        homeostasis,
        metabolism,
        0,
        3,
    )
    preliminary_control = _final_control(
        str(metacognition["primary_control"]),
        str(shadow["shadow_decision"]),
    )
    final_control = _resolve_research_conclusion(preliminary_control, closed_loop, metabolism)
    forward_control_gate = evaluate_gate(
        policy_by_id("forward_recording"),
        f"forward-control:{symbol}:{market_time}",
        {
            "point_in_time_complete": point_in_time_complete,
            "evidence_completeness": float(metacognition["confidence"]["evidence_completeness"]),
            "regime_familiarity": float(metacognition["confidence"]["regime_familiarity"]),
            "calibration_quality": float(metacognition["confidence"]["calibration_quality"]),
        },
        (point_in_time_proof_id,),
    )
    if not forward_control_gate["passed"]:
        final_control = str(forward_control_gate["decision"])
    evidence_ids = tuple(sorted(str(record["evidence_id"]) for record in evidence_records))
    prediction = build_forward_prediction(
        symbol,
        event_time,
        market_time,
        {str(key): float(value) for key, value in organism["hypotheses"].items()},
        float(metacognition["confidence"]["final_research_confidence"]),
        final_control,
        evidence_ids,
        point_in_time_proof_id,
        point_in_time_complete,
        10,
        {str(key): float(value) for key, value in organism["agent_contributions"].items()},
        {
            str(agent_id): {str(name): float(value) for name, value in hypotheses.items()}
            for agent_id, hypotheses in organism["agent_ablation_hypotheses"].items()
        },
    )
    prediction_append = append_prediction(paths.output_dir / "forward_predictions.jsonl", prediction)
    observation_memory = append_observation(
        paths.output_dir / "memory" / "observations.jsonl",
        {
            "symbol": symbol,
            "technical_evidence_id_count": technical["measurement_count"],
            "structure_pattern_evidence_id_count": technical["structure_pattern_evidence_count"],
            "world_model_evidence_id": world_model["evidence_id"],
            "technical_reproducibility_hash": technical["reproducibility_hash"],
            "world_model_content_hash": world_model["content_hash"],
        },
        event_time,
        clock.parent_event_id,
        evidence_ids,
    )
    episode_memory = append_episode(
        paths.output_dir / "memory" / "episodes.jsonl",
        {
            "symbol": symbol,
            "objective_type": objective_type,
            "organism_reproducibility_hash": organism["reproducibility_hash"],
            "dominant_hypothesis": organism["dominant_hypothesis"],
            "final_control": final_control,
            "prediction_id": prediction["prediction_id"],
        },
        event_time,
        clock.parent_event_id,
        evidence_ids,
    )
    summary_body: dict[str, Any] = {
        "artifact_type": "dopey_vnext_research_summary",
        "vnext_version": "dopey-vnext-dynamic-research-loop-v2",
        "run_status": "paper_research_complete_awaiting_forward_settlement",
        "symbol": symbol,
        "objective_type": objective_type,
        "event_time": event_time,
        "market_time": market_time,
        "constitution": seal,
        "technical_evidence_status": "complete",
        "technical_measurement_count": technical["measurement_count"],
        "world_model_known_dimensions": world_model["known_dimension_count"],
        "world_model_unknown_dimensions": world_model["unknown_dimension_count"],
        "fundamental_evidence_status": fundamental["evidence_status"],
        "options_surface_evidence_status": options_surface["evidence_status"],
        "earnings_event_evidence_status": earnings_event["evidence_status"],
        "credit_proxy_evidence_status": credit_proxy["evidence_status"],
        "organism_template_id": governor["template_id"],
        "agent_count": len(agent_results),
        "specialist_agent_count": organism["specialist_agent_count"],
        "specialist_data_gap_count": organism["specialist_data_gap_count"],
        "hypotheses": organism["hypotheses"],
        "dominant_hypothesis": organism["dominant_hypothesis"],
        "confidence": metacognition["confidence"],
        "knowledge_boundary": metacognition["knowledge_boundary"],
        "missing_evidence": organism["unresolved_uncertainty"],
        "metacognitive_control": metacognition["primary_control"],
        "shadow_decision": shadow["shadow_decision"],
        "closed_loop_control": closed_loop["selected_control"],
        "final_research_control": final_control,
        "autonomous_threshold_gate": forward_control_gate,
        "prediction_id": prediction["prediction_id"],
        "prediction_ledger_state": "recorded_or_identical",
        "settlement_status": prediction["prediction_status"],
        "calibration_input_status": str(
            calibration.get("input_status", calibration.get("calibration_status", "available_point_in_time"))
        ),
        "point_in_time_proof_id": point_in_time_proof_id,
        "point_in_time_complete": point_in_time_complete,
        "minimum_settlement_date": prediction["minimum_settlement_date"],
        "homeostasis_status": homeostasis["health_status"],
        "metabolism_termination": metabolism["automatic_low_yield_termination"],
        "readiness_effect": "none_protected_gate_not_read_or_written",
        "action_ready": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order_authority": True,
    }
    summary = {
        **summary_body,
        "prediction_append_status": prediction_append["append_status"],
        "observation_memory_status": observation_memory["append_status"],
        "episode_memory_status": episode_memory["append_status"],
        "reproducibility_hash": canonical_hash(summary_body),
    }
    assert_output_research_only(summary)
    assert_readiness_is_external(summary)
    outputs = {
        "constitution_state.json": seal,
        "validated_symbol_history_proof.json": history_proof,
        "input_time_proofs.json": input_time_proofs,
        "governor_plan.json": governor,
        "technical_evidence.json": technical,
        "world_model.json": world_model,
        "fundamental_evidence.json": fundamental,
        "options_surface_evidence.json": options_surface,
        "earnings_event_evidence.json": earnings_event,
        "credit_proxy_evidence.json": credit_proxy,
        "organism_episode.json": organism,
        "resource_ledger.json": resource_ledger,
        "metabolism_allocation.json": metabolism,
        "metacognition.json": metacognition,
        "shadow_controller.json": shadow,
        "homeostasis.json": homeostasis,
        "bounded_control_loop.json": closed_loop,
        "latest_prediction.json": prediction,
        "vnext_research_summary.json": summary,
    }
    for name, value in outputs.items():
        _write_object(paths.output_dir / name, value)
    return summary
