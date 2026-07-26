from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from dopey_acceleration import llm_research
from dopey_acceleration.common import stable_hash
from dopey_acceleration.frontier import (
    OPENROUTER_HYBRID_COMPONENTS,
    OPENROUTER_MAX_COMPONENT_PROMPT_BYTES,
    _component_prompt,
    _council_prompt,
    _select_openrouter_route,
)
from dopey_acceleration.provider_control import ProviderControl


def _provider_control() -> ProviderControl:
    return {
        "schema_version": "dopey-provider-control-v1",
        "updated_utc": "2026-07-22T12:00:00+00:00",
        "instrument_mode": "both",
        "providers": {
            "openrouter": True,
            "openrouter_hybrid": True,
            "claude": False,
            "codex": False,
        },
        "paper_only": True,
        "live_blocked": True,
    }


def _oversized_payload() -> dict[str, Any]:
    large_records = [
        {
            **{f"field_{field_index:02d}": "x" * 1_200 for field_index in range(40)},
            "bottleneck_id": f"blocker-{record_index}",
            "current": record_index,
            "required": 200,
            "remaining": 200 - record_index,
            "threshold_unchanged": True,
        }
        for record_index in range(12)
    ]
    return {
        "readiness_status": "not_action_ready",
        "active_symbol_count": 225,
        "starting_active_universe_target": 500,
        "actionable_shadow_thesis_count": 0,
        "bottlenecks": large_records,
        "intake_health": {"news_pipeline_status": "complete"},
        "context_evidence_status": "blocked_insufficient_resolved_context_decisions",
        "as_of": "2026-07-22T12:00:00+00:00",
        "symbol_context": "SPY",
        "contradictions": ["unknown breadth", "mixed evidence"],
        "known_dimension_count": 11,
        "unknown_dimension_count": 6,
        "batch_status": "complete_awaiting_forward_settlement",
        "market_time": "2026-07-22T12:00:00+00:00",
        "completed_symbol_count": 37,
        "abstention_count": 37,
        "settled_count_after": 0,
        "calibration_sample_sufficient": False,
        "agent_ablation_status": "insufficient_forward_settlements",
        "specialist_data_gap_count": 52,
        "validated_positive_agent_count": 0,
        "next_minimum_settlement_date": "2026-07-28",
        "run_status": "paper_research_complete",
        "as_of_date": "2026-07-22",
        "external_context_veto_count": 0,
        "contract_blocker_counts": {"equity_thesis_not_actionable": 225},
        "context_evidence_gate": {"evidence_status": "blocked", "minimum_resolved_decisions": 200},
        "limitations": ["paper only", "no settled evidence"],
        "biggest_mover_count": 40,
        "biggest_movers": large_records,
        "top_gainers": large_records,
        "top_losers": large_records,
        "top_winners": large_records,
        "generation": 38,
        "cycle_status": "complete_shadow_only",
        "finding_status": "blocked_missing_validated_research_findings",
        "candidate_count": 32,
        "candidates": large_records,
        "evaluation_task_suite": large_records,
        "forward_candidate_count": 32,
        "shadow_admitted_count": 32,
        "forward_candidates": large_records,
        "gate_decisions": large_records,
        "reverse_report": {"reverse_status": "blocked", "settled_case_count": 0},
        "quality_diversity_archive": {"candidate_count": 32, "promotion_allowed": False},
        "evaluation_status": "complete",
        "activated_blueprint_count": 0,
        "registry_appended_count": 0,
        "matrix": {"matrix_hash": "a" * 64, "candidate_self_activation_allowed": False},
        "evidence_status": "evaluation_complete",
        "visible_task_count": 384,
        "independent_task_count": 0,
        "missing_independent_partitions": ["private", "external", "real"],
        "method_evidence": large_records,
        "evaluations": large_records,
        "activated_method_ids": [],
        "batch_hash": "b" * 64,
        "outcome_status": "complete_quarantined_proposals",
        "proposal_count": 3,
        "linked_proposal_count": 2,
        "blocked_proposal_count": 1,
        "orphan_experiment_count": 0,
        "source_session_count": 1,
        "evidence_weight": 0.0,
        "mutation_targets_resolved": 0,
        "next_gate": "independent_experiment_then_purged_walk_forward_and_held_out_validation",
        "automatic_apply_allowed": False,
        "strategy_mutation_allowed": False,
        "strategy_promotion_allowed": False,
        "sessions": [{"raw_proposal_prose": "MUST_NOT_REACH_PROMPT"}],
    }


def _write_sources(repo_root: Path, payload: dict[str, Any]) -> None:
    for spec in llm_research.SOURCE_SPECS:
        path = repo_root / spec["relative_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_prompt_projection_is_deterministic_hash_backed_and_under_prepaid_cap(tmp_path: Path) -> None:
    _write_sources(tmp_path, _oversized_payload())
    semantic_state = llm_research.build_llm_research_state(tmp_path, _provider_control())
    semantic_hash = stable_hash(semantic_state)
    prompt_state = llm_research.build_llm_research_prompt_state(semantic_state, semantic_hash)

    assert llm_research._serialized_bytes(semantic_state) > OPENROUTER_MAX_COMPONENT_PROMPT_BYTES
    assert llm_research._serialized_bytes(prompt_state) <= llm_research.LLM_RESEARCH_PROMPT_STATE_MAX_BYTES
    assert prompt_state == llm_research.build_llm_research_prompt_state(semantic_state, semantic_hash)
    assert prompt_state["semantic_state_hash"] == semantic_hash
    readiness = next(source for source in prompt_state["sources"] if source["source_id"] == "readiness")
    assert readiness["content"]["readiness_status"] == "not_action_ready"
    assert readiness["content"]["context_evidence_status"] == "blocked_insufficient_resolved_context_decisions"
    coach = next(source for source in prompt_state["sources"] if source["source_id"] == "coach_proposal_quarantine")
    assert coach["content"]["proposal_count"] == 3
    assert coach["content"]["evidence_weight"] == 0.0
    assert "MUST_NOT_REACH_PROMPT" not in json.dumps(prompt_state)

    council_prompt = _council_prompt("Find the safest paper-only next experiment.", prompt_state)
    route = _select_openrouter_route(council_prompt)
    for provider in OPENROUTER_HYBRID_COMPONENTS[:2]:
        component_prompt = _component_prompt(provider, council_prompt, route, ())
        assert len(component_prompt.encode("utf-8")) < OPENROUTER_MAX_COMPONENT_PROMPT_BYTES


def test_cycle_passes_projection_not_full_state_to_frontier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_sources(tmp_path, _oversized_payload())
    captured: dict[str, Any] = {}

    class ProjectionCaptured(RuntimeError):
        pass

    def capture_council(
        objective: str,
        providers: tuple[str, ...],
        state: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        captured.update(state)
        raise ProjectionCaptured

    monkeypatch.setattr(llm_research, "load_provider_control", _provider_control)
    monkeypatch.setattr(llm_research, "run_frontier_council", capture_council)

    with pytest.raises(ProjectionCaptured):
        llm_research.run_llm_research_cycle(
            tmp_path,
            tmp_path / "output",
            90,
            True,
            datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        )

    assert captured["prompt_state_version"] == llm_research.LLM_RESEARCH_PROMPT_STATE_VERSION
    assert "state_version" not in captured
    assert llm_research._serialized_bytes(captured) <= llm_research.LLM_RESEARCH_PROMPT_STATE_MAX_BYTES
