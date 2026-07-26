"""Rank evidence bottlenecks under the current creator-governed policy."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from dopey_equity_swing.context_evidence import (
    CALENDAR_DURATION_GATE_AUTHORITY,
    CALENDAR_DURATION_GATE_ENABLED,
    SNAPSHOT_HISTORY_ROLE,
)
from dopey_universe.universe_registry import (
    MAX_ACTIVE_UNIVERSE_SIZE,
    UNIVERSE_CAPACITY_POLICY,
    active_universe,
    load_registry,
)

from .common import ARTIFACT_ROOT, REPO_ROOT, read_optional_json, stamped, write_json_atomic


ACTION_GATE_PATH = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness" / "action_readiness_gate.json"
CONTEXT_GATE_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "context_evidence_gate.json"
SWING_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "equity_first_swing_summary.json"
UNIVERSE_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "universe" / "universe_summary.json"
NEWS_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "news_context_manifest.json"
PLAN_PATH = ARTIFACT_ROOT / "readiness_acceleration_plan.json"


def build_readiness_acceleration_plan(repo_root: Path) -> dict[str, Any]:
    if repo_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(f"repository root mismatch: expected={REPO_ROOT}, actual={repo_root}")
    action, action_status = read_optional_json(ACTION_GATE_PATH)
    context, context_status = read_optional_json(CONTEXT_GATE_PATH)
    swing, swing_status = read_optional_json(SWING_SUMMARY_PATH)
    universe, universe_status = read_optional_json(UNIVERSE_SUMMARY_PATH)
    news_manifest, news_manifest_status = read_optional_json(NEWS_MANIFEST_PATH)

    closed = int(action.get("forward_closed_trades", 0))
    closed_required = int(action.get("forward_closed_trades_required", 100))
    snapshot_days = int(context.get("joint_snapshot_day_count", 0))
    resolved = int(context.get("context_outcome_ledger_count", 0))
    resolved_required = int(context.get("minimum_resolved_decisions", 200))
    decisions = int(context.get("context_decision_ledger_count", 0))
    pending_decisions = int(context.get("pending_context_decision_count", max(decisions - resolved, 0)))
    actionable = int(swing.get("actionable_shadow_thesis_count", 0))
    universe_summary_active_symbols = int(
        universe.get("active_universe_size", 0)
    )
    universe_registry_active_symbols = len(active_universe(load_registry()))
    active_symbols = universe_registry_active_symbols

    resolved_remaining = max(resolved_required - resolved, 0)
    closed_remaining = max(closed_required - closed, 0)
    observed_decision_rate = max(decisions // max(snapshot_days, 1), 1)
    expanded_decision_rate = max(actionable, min(max(active_symbols // 5, 1), 20))

    bottlenecks = [
        {
            "bottleneck_id": "resolved_context_decisions",
            "priority": 1,
            "current": resolved,
            "required": resolved_required,
            "remaining": resolved_remaining,
            "recorded_decisions": decisions,
            "pending_maturity_or_settlement": pending_decisions,
            "observed_decisions_per_joint_snapshot_day": observed_decision_rate,
            "estimated_days_at_observed_cross_section": math.ceil(resolved_remaining / observed_decision_rate),
            "estimated_days_at_expanded_cross_section_before_maturity_lag": math.ceil(resolved_remaining / expanded_decision_rate),
            "acceleration": "expand equity coverage, append one semantic decision per symbol/day, and settle matured outcomes daily",
            "threshold_unchanged": True,
        },
        {
            "bottleneck_id": "forward_closed_trade_sample",
            "priority": 2,
            "current": closed,
            "required": closed_required,
            "remaining": closed_remaining,
            "existing_eta": action.get("evidence_eta", {}),
            "acceleration": "increase independent eligible paper setups under existing portfolio and stress caps; never trade merely to satisfy a count",
            "threshold_unchanged": True,
        },
        {
            "bottleneck_id": "cohort_edge_and_regime_robustness",
            "priority": 3,
            "missing_checks": [
                name
                for name in (
                    "cohort_baseline_policy_current",
                    "any_cohort_beats_matched_baseline_familywise",
                    "cohort_era_policy_current",
                    "any_cohort_regime_robust",
                    "statistical_truth_promotion_allowed",
                )
                if action.get("checks", {}).get(name) is not True
            ],
            "acceleration": "rerun one-to-one matched cohort controls and month-cluster inference, then expand eras and symbols while preserving child-level attribution",
            "threshold_unchanged": True,
        },
    ]
    plan = stamped(
        {
            "artifact_type": "readiness_acceleration_plan",
            "acceleration_version": "dopey-readiness-acceleration-v6",
            "source_status": {
                "action_gate": action_status,
                "context_gate": context_status,
                "swing_summary": swing_status,
                "universe_summary": universe_status,
                "news_manifest": news_manifest_status,
            },
            "readiness_status": action.get("readiness_status", "missing_action_gate"),
            "context_evidence_status": context.get("evidence_status", "missing_context_gate"),
            "context_snapshot_telemetry": {
                "observed_joint_snapshot_days": snapshot_days,
                "calendar_duration_gate_enabled": CALENDAR_DURATION_GATE_ENABLED,
                "calendar_duration_gate_authority": CALENDAR_DURATION_GATE_AUTHORITY,
                "snapshot_history_role": SNAPSHOT_HISTORY_ROLE,
            },
            "intake_health": {
                "news_pipeline_status": str(news_manifest.get("pipeline_status", "missing")),
                "news_required_coverage_complete": news_manifest.get("source_coverage", {}).get(
                    "required_coverage_complete"
                )
                is True,
                "news_failed_source_ids": sorted(
                    str(status.get("source_id", ""))
                    for status in news_manifest.get("source_statuses", [])
                    if status.get("status") != "staged"
                ),
            },
            "active_symbol_count": active_symbols,
            "active_symbol_count_authority": "governed_universe_registry",
            "universe_summary_active_symbol_count": (
                universe_summary_active_symbols
            ),
            "universe_registry_active_symbol_count": (
                universe_registry_active_symbols
            ),
            "universe_symbol_count_consistent": (
                universe_summary_active_symbols
                == universe_registry_active_symbols
            ),
            "universe_capacity_policy": UNIVERSE_CAPACITY_POLICY,
            "maximum_active_universe_size": MAX_ACTIVE_UNIVERSE_SIZE,
            "available_active_slots": max(MAX_ACTIVE_UNIVERSE_SIZE - active_symbols, 0),
            "actionable_shadow_thesis_count": actionable,
            "bottlenecks": bottlenecks,
            "highest_value_next_actions": [
                "restore complete required news coverage while preserving explicit supplemental source failures",
                "run the equity-first engine after both context lanes complete",
                "settle context outcomes every session",
                "bridge locally available public-lake symbols into governed equity research probation",
                "consolidate evidence by canonical cohort before creating additional micro variants",
            ],
            "gate_policy_changed": True,
            "removed_gate_ids": ["point_in_time_context_days"],
            "remaining_evidence_thresholds_lowered": False,
            "synthetic_evidence_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    write_json_atomic(PLAN_PATH, plan)
    return plan
