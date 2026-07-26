"""Calendar-aware research scheduling with explicit lane subsumption."""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from zoneinfo import ZoneInfo

from .common import (
    ARTIFACT_ROOT,
    REPO_ROOT,
    read_optional_json,
    stable_hash,
    stamped,
    write_json_atomic,
)
from .reliability_guard import evaluate_reliability_guard
from .storage_pressure import (
    measure_storage_pressure,
    storage_blocker_for_lane,
)


class LanePolicy(TypedDict):
    lane_id: str
    interval_minutes: int
    window: str
    timeout_seconds: int
    retries: int
    network: bool
    description: str


class LaneEvidenceContract(TypedDict):
    artifact_path: Path
    status_key: str
    required_status: str
    timestamp_key: NotRequired[str]
    max_age_hours: NotRequired[float]


class LaneEvidenceStatus(TypedDict):
    verification_required: bool
    verification_status: str
    artifact_path: str
    artifact_availability: str
    status_key: str
    actual_status: str
    required_status: str
    timestamp_key: NotRequired[str]
    observed_timestamp: NotRequired[str]
    age_hours: NotRequired[float | None]
    max_age_hours: NotRequired[float | None]
    freshness_status: NotRequired[str]
    verified_complete: bool


SCHEDULE_STATE_PATH = ARTIFACT_ROOT / "schedule_state.json"
SCHEDULE_PLAN_PATH = ARTIFACT_ROOT / "schedule_plan.json"
ACTIVE_IMPROVEMENT_POLICY_PATH = (
    ARTIFACT_ROOT / "autonomous_improvement" / "active_policy.json"
)
AUTONOMOUS_IMPROVEMENT_POLICY_VERSION = "dopey-autonomous-improvement-v2"
SCHEDULE_STATE_VERSION = "dopey-research-schedule-state-v23"
NEW_YORK = ZoneInfo("America/New_York")
EXTERNAL_LANE_OWNERS: dict[str, str] = {
    "daily_close_stack": "windows_task_scheduler:DOPEY_DailyRitual",
    "nightly_validation": "windows_task_scheduler:DOPEY_Nightly",
}
LANES: tuple[LanePolicy, ...] = (
    {
        "lane_id": "news_intake",
        "interval_minutes": 60,
        "window": "always",
        "timeout_seconds": 420,
        "retries": 2,
        "network": True,
        "description": "immutable official/geopolitical/financial news snapshot",
    },
    {
        "lane_id": "cross_asset_intake",
        "interval_minutes": 60,
        "window": "always",
        "timeout_seconds": 420,
        "retries": 2,
        "network": True,
        "description": "futures, commodities, crypto, currency, Treasury and volatility context",
    },
    {
        "lane_id": "quant_context_intake",
        "interval_minutes": 1440,
        "window": "after_close",
        "timeout_seconds": 1800,
        "retries": 2,
        "network": True,
        "description": "official macro, positioning, filing, settlement-fail and options-flow context",
    },
    {
        "lane_id": "context_outcome_settlement",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 180,
        "retries": 1,
        "network": False,
        "description": "append matured forward outcomes without rewriting decisions",
    },
    {
        "lane_id": "equity_swing_engine",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 600,
        "retries": 1,
        "network": False,
        "description": "equity-first multi-timeframe thesis, context and contract selection",
    },
    {
        "lane_id": "playbook_refresh",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 900,
        "retries": 1,
        "network": False,
        "description": "refresh direction-neutral attention, evolving membership, and ranked bullish/bearish prediction research",
    },
    {
        "lane_id": "symbol_intelligence_lab",
        "interval_minutes": 1440,
        "window": "after_close",
        "timeout_seconds": 7200,
        "retries": 1,
        "network": False,
        "description": "refresh per-symbol strategy experiments, market geometry, meta-plans, and option value surfaces",
    },
    {
        "lane_id": "intraday_watch",
        "interval_minutes": 30,
        "window": "rth",
        "timeout_seconds": 240,
        "retries": 1,
        "network": True,
        "description": "read-only market-hours risk and thesis watch",
    },
    {
        "lane_id": "daily_close_stack",
        "interval_minutes": 1440,
        "window": "after_close",
        "timeout_seconds": 3600,
        "retries": 1,
        "network": True,
        "description": "bounded close ritual for market data, context, swing and settlement",
    },
    {
        "lane_id": "universe_candidate_seed",
        "interval_minutes": 1440,
        "window": "after_close",
        "timeout_seconds": 180,
        "retries": 1,
        "network": False,
        "description": "seed locally available public-lake symbols into governed candidacy",
    },
    {
        "lane_id": "governed_universe_growth",
        "interval_minutes": 10080,
        "window": "weekend",
        "timeout_seconds": 14400,
        "retries": 1,
        "network": True,
        "description": "stage up to five governed universe candidates with full validation and rollback",
    },
    {
        "lane_id": "nightly_validation",
        "interval_minutes": 1440,
        "window": "overnight",
        "timeout_seconds": 21600,
        "retries": 1,
        "network": False,
        "description": "regression, stack stability and determinism evidence",
    },
    {
        "lane_id": "vnext_forward_research",
        "interval_minutes": 1440,
        "window": "after_close",
        "timeout_seconds": 10800,
        "retries": 1,
        "network": False,
        "description": "resumable cross-sectional vNext predictions, pre/post settlement and calibration",
    },
    {
        "lane_id": "autonomous_experiment_evaluation",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 1800,
        "retries": 1,
        "network": False,
        "description": "compile supported queued challengers and independently evaluate hidden and external historical partitions",
    },
    {
        "lane_id": "autonomous_strategy_research",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 1800,
        "retries": 1,
        "network": False,
        "description": "invent diverse strategy challengers for protected hidden and forward evaluation",
    },
    {
        "lane_id": "coached_evolution_cycle",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 2100,
        "retries": 1,
        "network": True,
        "description": "state-change-gated Claude-headed coaching, quarantine, and deterministic experiment dispatch",
    },
    {
        "lane_id": "coach_proposal_quarantine",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 120,
        "retries": 1,
        "network": False,
        "description": "validate grounded Claude or Codex coaching and quarantine zero-weight experiment proposals",
    },
    {
        "lane_id": "autonomous_threshold_audit",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 300,
        "retries": 1,
        "network": False,
        "description": "verify sealed tighten-only autonomous threshold policies and authority boundaries",
    },
    {
        "lane_id": "strategy_engineering_research",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 1800,
        "retries": 1,
        "network": False,
        "description": "reverse settled research and construct interpretable forward challengers in shadow mode",
    },
    {
        "lane_id": "evidence_intelligence",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 600,
        "retries": 1,
        "network": False,
        "description": "content-addressed strategy dossier, mutation genealogy, and options pricing invariants",
    },
    {
        "lane_id": "autonomous_promotion_evidence_synthesis",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 600,
        "retries": 1,
        "network": False,
        "description": "synthesize only independently supported symbol and strategy promotion evidence",
    },
    {
        "lane_id": "autonomous_promotion_evaluation",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 600,
        "retries": 1,
        "network": False,
        "description": "apply protected symbol, strategy, and pair research-activation thresholds",
    },
    {
        "lane_id": "autonomous_self_improvement",
        "interval_minutes": 360,
        "window": "always",
        "timeout_seconds": 300,
        "retries": 1,
        "network": False,
        "description": "threshold-gated cadence, resilience, and research-method improvement for every paper lane",
    },
    {
        "lane_id": "llm_frontier_research",
        "interval_minutes": 360,
        "window": "always",
        "timeout_seconds": 2100,
        "retries": 1,
        "network": True,
        "description": "state-change-triggered OpenRouter four-model role-routed conservative adjudication",
    },
    {
        "lane_id": "intelligence_discovery_research",
        "interval_minutes": 360,
        "window": "always",
        "timeout_seconds": 900,
        "retries": 1,
        "network": False,
        "description": "discover and test better domain-independent methods of discovery and reasoning",
    },
    {
        "lane_id": "intelligence_evidence_evaluation",
        "interval_minutes": 360,
        "window": "always",
        "timeout_seconds": 1800,
        "retries": 1,
        "network": False,
        "description": "run matched cross-domain cognitive benchmarks and protected activation gates",
    },
    {
        "lane_id": "vnext_forward_settlement",
        "interval_minutes": 240,
        "window": "always",
        "timeout_seconds": 1800,
        "retries": 1,
        "network": False,
        "description": "settlement-only accrual for matured vNext predictions without new research",
    },
    {
        "lane_id": "weekly_sharpness_research",
        "interval_minutes": 10080,
        "window": "weekend",
        "timeout_seconds": 3600,
        "retries": 1,
        "network": False,
        "description": "held-out sharpness and strategy archaeology research",
    },
)
SUBSUMED_BY_CLOSE = {
    "news_intake",
    "cross_asset_intake",
    "quant_context_intake",
    "context_outcome_settlement",
    "equity_swing_engine",
}
SUBSUMED_BY_VNEXT_RESEARCH = {"vnext_forward_settlement"}
LANE_EVIDENCE_CONTRACTS: dict[str, LaneEvidenceContract] = {
    "coached_evolution_cycle": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "coached_evolution"
        / "latest_run.json",
        "status_key": "run_status",
        "required_status": "complete",
    },
    "playbook_refresh": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "playbook"
        / "playbook_refresh_result.json",
        "status_key": "refresh_status",
        "required_status": "complete",
    },
    "context_outcome_settlement": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "latest_context_settlement.json",
        "status_key": "operation_status",
        "required_status": "complete",
    },
    "news_intake": {
        "artifact_path": REPO_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "news_context_manifest.json",
        "status_key": "pipeline_status",
        "required_status": "complete",
        "timestamp_key": "created_at",
        "max_age_hours": 3.0,
    },
    "cross_asset_intake": {
        "artifact_path": REPO_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "cross_asset_context_manifest.json",
        "status_key": "dataset_status",
        "required_status": "complete",
        "timestamp_key": "created_at",
        "max_age_hours": 3.0,
    },
    "governed_universe_growth": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "universe"
        / "universe_ritual_summary.json",
        "status_key": "universe_ritual_status",
        "required_status": "ok",
    },
    "quant_context_intake": {
        "artifact_path": REPO_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "quant_context_manifest.json",
        "status_key": "pipeline_status",
        "required_status": "complete",
        "timestamp_key": "created_at",
        "max_age_hours": 36.0,
    },
    "vnext_forward_research": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "vnext"
        / "cross_sectional_operational"
        / "latest_batch_summary.json",
        "status_key": "batch_status",
        "required_status": "complete_awaiting_forward_settlement",
    },
    "vnext_forward_settlement": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "vnext"
        / "cross_sectional_operational"
        / "latest_settlement_operation.json",
        "status_key": "operation_status",
        "required_status": "complete",
    },
    "autonomous_experiment_evaluation": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "autoresearch"
        / "latest_experiment_evaluation.json",
        "status_key": "evaluation_status",
        "required_status": "complete",
        "timestamp_key": "last_verified_at",
        "max_age_hours": 8.0,
    },
    "autonomous_strategy_research": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "autoresearch"
        / "latest_cycle.json",
        "status_key": "cycle_status",
        "required_status": "experiments_queued",
    },
    "coach_proposal_quarantine": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "two_coach"
        / "mutation_proposals"
        / "latest_batch.json",
        "status_key": "batch_status",
        "required_status": "complete",
    },
    "autonomous_threshold_audit": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "threshold_fabric"
        / "latest_audit.json",
        "status_key": "audit_status",
        "required_status": "complete",
    },
    "strategy_engineering_research": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "strategy_engineering"
        / "latest_cycle.json",
        "status_key": "cycle_status",
        "required_status": "complete_shadow_only",
    },
    "evidence_intelligence": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "evidence_intelligence"
        / "latest_cycle.json",
        "status_key": "cycle_status",
        "required_status": "complete",
    },
    "symbol_intelligence_lab": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "symbol_lab"
        / "latest_batch_summary.json",
        "status_key": "batch_status",
        "required_status": "complete",
    },
    "autonomous_promotion_evidence_synthesis": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "autoresearch"
        / "promotion_evidence.json",
        "status_key": "synthesis_status",
        "required_status": "complete",
    },
    "autonomous_promotion_evaluation": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "autoresearch"
        / "latest_promotion_cycle.json",
        "status_key": "evaluation_status",
        "required_status": "complete",
    },
    "autonomous_self_improvement": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "acceleration"
        / "autonomous_improvement"
        / "latest_cycle.json",
        "status_key": "cycle_status",
        "required_status": "complete",
    },
    "intelligence_discovery_research": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "intelligence_research"
        / "latest_cycle.json",
        "status_key": "cycle_status",
        "required_status": "cognitive_experiments_queued",
    },
    "llm_frontier_research": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "llm_research"
        / "latest_cycle.json",
        "status_key": "cycle_status",
        "required_status": "complete_analysis_current",
    },
    "intelligence_evidence_evaluation": {
        "artifact_path": REPO_ROOT
        / "artifacts"
        / "dopey"
        / "intelligence_research"
        / "latest_evidence_cycle.json",
        "status_key": "evidence_status",
        "required_status": "evaluation_complete",
    },
}
LANE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "equity_swing_engine": ("news_intake", "cross_asset_intake"),
    "autonomous_strategy_research": ("autonomous_experiment_evaluation",),
}


def _window_open(window: str, now_et: datetime) -> bool:
    weekday = now_et.weekday()
    local_time = now_et.time()
    if window == "always":
        return True
    if window == "rth":
        return weekday < 5 and time(9, 30) <= local_time <= time(16, 0)
    if window == "after_close":
        return weekday < 5 and time(16, 45) <= local_time <= time(23, 59, 59)
    if window == "overnight":
        return time(1, 30) <= local_time <= time(5, 0)
    if window == "weekend":
        return weekday >= 5
    raise ValueError(f"unknown schedule window: {window}")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _object_mapping(record: dict[str, Any], key: str) -> dict[str, object]:
    value = record.get(key)
    if not isinstance(value, dict):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _lane_evidence_freshness(
    artifact: dict[str, Any],
    contract: LaneEvidenceContract,
    now_utc: datetime,
) -> tuple[str, str, float | None, float | None, str]:
    timestamp_key = str(contract.get("timestamp_key", ""))
    max_age_hours = contract.get("max_age_hours")
    if not timestamp_key or max_age_hours is None:
        return "", "", None, None, "not_required"
    raw_timestamp = artifact.get(timestamp_key)
    observed_timestamp = str(raw_timestamp) if raw_timestamp is not None else ""
    parsed_timestamp = _parse_timestamp(raw_timestamp)
    if parsed_timestamp is None:
        return (
            timestamp_key,
            observed_timestamp,
            None,
            float(max_age_hours),
            "missing_or_invalid_timestamp",
        )
    age_hours = (
        now_utc.astimezone(timezone.utc) - parsed_timestamp.astimezone(timezone.utc)
    ).total_seconds() / 3600.0
    if age_hours < -(5.0 / 60.0):
        freshness_status = "future_timestamp"
    elif age_hours > float(max_age_hours):
        freshness_status = "stale"
    else:
        freshness_status = "fresh"
    return (
        timestamp_key,
        parsed_timestamp.isoformat(),
        round(age_hours, 4),
        float(max_age_hours),
        freshness_status,
    )


def evaluate_lane_evidence_at(
    lane_id: str,
    now_utc: datetime,
) -> LaneEvidenceStatus:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    contract = LANE_EVIDENCE_CONTRACTS.get(lane_id)
    if contract is None:
        return {
            "verification_required": False,
            "verification_status": "not_required",
            "artifact_path": "",
            "artifact_availability": "not_applicable",
            "status_key": "",
            "actual_status": "not_applicable",
            "required_status": "not_applicable",
            "timestamp_key": "",
            "observed_timestamp": "",
            "age_hours": None,
            "max_age_hours": None,
            "freshness_status": "not_required",
            "verified_complete": True,
        }
    artifact, availability = read_optional_json(contract["artifact_path"])
    actual_status = str(artifact.get(contract["status_key"], availability))
    (
        timestamp_key,
        observed_timestamp,
        age_hours,
        max_age_hours,
        freshness_status,
    ) = _lane_evidence_freshness(artifact, contract, now_utc)
    verified_complete = (
        availability == "available"
        and actual_status == contract["required_status"]
        and freshness_status in {"fresh", "not_required"}
    )
    return {
        "verification_required": True,
        "verification_status": "verified_complete"
        if verified_complete
        else "degraded_evidence",
        "artifact_path": str(contract["artifact_path"]),
        "artifact_availability": availability,
        "status_key": contract["status_key"],
        "actual_status": actual_status,
        "required_status": contract["required_status"],
        "timestamp_key": timestamp_key,
        "observed_timestamp": observed_timestamp,
        "age_hours": age_hours,
        "max_age_hours": max_age_hours,
        "freshness_status": freshness_status,
        "verified_complete": verified_complete,
    }


def evaluate_lane_evidence(lane_id: str) -> LaneEvidenceStatus:
    return evaluate_lane_evidence_at(lane_id, datetime.now(timezone.utc))


def _dependency_blocker(lane_id: str, now_utc: datetime) -> str | None:
    dependency_lane_ids = LANE_DEPENDENCIES.get(lane_id)
    if dependency_lane_ids is None:
        return None
    for dependency_lane_id in dependency_lane_ids:
        evidence = evaluate_lane_evidence_at(dependency_lane_id, now_utc)
        if not evidence["verified_complete"]:
            artifact_name = Path(evidence["artifact_path"]).name
            return (
                f"{artifact_name}:{evidence['status_key']}={evidence['actual_status']}:"
                f"required={evidence['required_status']}:"
                f"freshness={evidence['freshness_status']}:"
                f"age_hours={evidence['age_hours']}:"
                f"max_age_hours={evidence['max_age_hours']}"
            )
    return None


def _due_priority(record: dict[str, Any]) -> tuple[int, float, int, str]:
    minutes_since_success = record.get("minutes_since_success")
    if minutes_since_success is None:
        return (
            0,
            0.0,
            int(record["timeout_seconds"]),
            str(record["lane_id"]),
        )
    return (
        1,
        -float(minutes_since_success),
        int(record["timeout_seconds"]),
        str(record["lane_id"]),
    )


def _policy_activation_evidence_committed(policy: dict[str, Any]) -> bool:
    history_path_text = policy.get("policy_history_path")
    if not isinstance(history_path_text, str) or not history_path_text:
        return False
    history_path = Path(history_path_text)
    expected_history_root = (
        ACTIVE_IMPROVEMENT_POLICY_PATH.parent / "history"
    ).resolve()
    try:
        resolved_history_path = history_path.resolve()
        if resolved_history_path.parent != expected_history_root:
            return False
        history, availability = read_optional_json(resolved_history_path)
    except (OSError, TypeError, ValueError):
        return False
    if availability != "available":
        return False
    history_hash = history.get("reproducibility_hash")
    unhashed_history = dict(history)
    unhashed_history.pop("reproducibility_hash", None)
    transition = history.get("policy_transition")
    cycle_result = history.get("cycle_result")
    active_policy = history.get("active_policy")
    if (
        history.get("immutable_history") is not True
        or not isinstance(history_hash, str)
        or stable_hash(unhashed_history) != history_hash
        or not isinstance(transition, dict)
        or not isinstance(cycle_result, dict)
        or active_policy != policy
    ):
        return False
    transition_hash = transition.get("reproducibility_hash")
    unhashed_transition = dict(transition)
    unhashed_transition.pop("reproducibility_hash", None)
    cycle_hash = cycle_result.get("reproducibility_hash")
    unhashed_cycle = dict(cycle_result)
    unhashed_cycle.pop("reproducibility_hash", None)
    prepared_evidence_valid = (
        transition.get("active_policy_hash") == policy.get("reproducibility_hash")
        and isinstance(transition_hash, str)
        and stable_hash(unhashed_transition) == transition_hash
        and cycle_result.get("active_policy_hash") == policy.get("reproducibility_hash")
        and isinstance(cycle_hash, str)
        and stable_hash(unhashed_cycle) == cycle_hash
    )
    if not prepared_evidence_valid:
        return False
    commit_marker_path_text = policy.get("activation_commit_marker_path")
    if not isinstance(commit_marker_path_text, str) or not commit_marker_path_text:
        return False
    commit_marker_path = Path(commit_marker_path_text)
    try:
        resolved_commit_marker_path = commit_marker_path.resolve()
        if (
            resolved_commit_marker_path.parent
            != ACTIVE_IMPROVEMENT_POLICY_PATH.parent.resolve()
        ):
            return False
        marker, marker_availability = read_optional_json(resolved_commit_marker_path)
    except (OSError, TypeError, ValueError):
        return False
    if marker_availability != "available":
        return False
    marker_hash = marker.get("reproducibility_hash")
    unhashed_marker = dict(marker)
    unhashed_marker.pop("reproducibility_hash", None)
    return (
        marker.get("artifact_type") == "autonomous_improvement_activation_commit"
        and marker.get("active_policy_hash") == policy.get("reproducibility_hash")
        and marker.get("history_hash") == history_hash
        and marker.get("transition_hash") == transition_hash
        and marker.get("prepared_cycle_result_hash") == cycle_hash
        and marker.get("paper_only") is True
        and marker.get("live_blocked") is True
        and isinstance(marker_hash, str)
        and stable_hash(unhashed_marker) == marker_hash
    )


def _effective_lanes(
    now_utc: datetime,
) -> tuple[tuple[LanePolicy, ...], str]:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    policy, availability = read_optional_json(ACTIVE_IMPROVEMENT_POLICY_PATH)
    if availability != "available":
        return LANES, "baseline_no_active_policy"
    claimed_hash = policy.get("reproducibility_hash")
    unhashed_policy = dict(policy)
    unhashed_policy.pop("reproducibility_hash", None)
    if (
        not isinstance(claimed_hash, str)
        or not claimed_hash
        or stable_hash(unhashed_policy) != claimed_hash
    ):
        raise ValueError(
            "autonomous improvement policy failed reproducibility hash validation: "
            f"path={ACTIVE_IMPROVEMENT_POLICY_PATH}"
        )
    if (
        policy.get("policy_status") != "active_threshold_gated"
        or policy.get("paper_only") is not True
        or policy.get("live_blocked") is not True
        or policy.get("evidence_thresholds_lowered") is not False
    ):
        raise ValueError(
            "autonomous improvement policy violates its activation boundary: "
            f"path={ACTIVE_IMPROVEMENT_POLICY_PATH}"
        )
    if (
        policy.get("policy_version") == AUTONOMOUS_IMPROVEMENT_POLICY_VERSION
        and not _policy_activation_evidence_committed(policy)
    ):
        return LANES, "baseline_uncommitted_active_policy"
    embedded_guard = policy.get("reliability_guard")
    current_guard = evaluate_reliability_guard(
        REPO_ROOT,
        now_utc,
    )
    cadence_acceleration_allowed = (
        policy.get("policy_version") == AUTONOMOUS_IMPROVEMENT_POLICY_VERSION
        and isinstance(embedded_guard, dict)
        and embedded_guard.get("guard_status") == "within_error_budget"
        and embedded_guard.get("cadence_acceleration_allowed") is True
        and current_guard.get("guard_status") == "within_error_budget"
        and current_guard.get("cadence_acceleration_allowed") is True
    )
    raw_overrides = policy.get("lane_overrides")
    if not isinstance(raw_overrides, dict):
        raise TypeError("autonomous improvement lane_overrides must be an object")
    known_ids = {lane["lane_id"] for lane in LANES}
    unknown_ids = sorted(
        str(lane_id) for lane_id in raw_overrides if str(lane_id) not in known_ids
    )
    if unknown_ids:
        raise ValueError(
            f"autonomous improvement policy contains unknown lanes: {unknown_ids}"
        )
    effective: list[LanePolicy] = []
    for lane in LANES:
        lane_id = lane["lane_id"]
        raw_override = raw_overrides.get(lane_id, {})
        if not isinstance(raw_override, dict):
            raise TypeError(
                f"autonomous lane override must be an object: lane_id={lane_id}"
            )
        effective_override = {
            str(field): value
            for field, value in raw_override.items()
            if field != "interval_minutes" or cadence_acceleration_allowed
        }
        unknown_fields = sorted(
            set(raw_override) - {"interval_minutes", "timeout_seconds", "retries"}
        )
        if unknown_fields:
            raise ValueError(
                f"autonomous lane override contains protected fields: lane_id={lane_id}, fields={unknown_fields}"
            )
        values = {
            key: effective_override.get(key, lane[key])
            for key in ("interval_minutes", "timeout_seconds", "retries")
        }
        if not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in values.values()
        ):
            raise TypeError(
                f"autonomous lane override values must be integers: lane_id={lane_id}"
            )
        interval_minutes = int(values["interval_minutes"])
        timeout_seconds = int(values["timeout_seconds"])
        retries = int(values["retries"])
        if not 15 <= interval_minutes <= int(lane["interval_minutes"]):
            raise ValueError(
                f"autonomous interval override is outside its sealed range: lane_id={lane_id}"
            )
        if (
            not int(lane["timeout_seconds"])
            <= timeout_seconds
            <= int(lane["timeout_seconds"]) * 2
        ):
            raise ValueError(
                f"autonomous timeout override is outside its sealed range: lane_id={lane_id}"
            )
        if not int(lane["retries"]) <= retries <= 3:
            raise ValueError(
                f"autonomous retry override is outside its sealed range: lane_id={lane_id}"
            )
        effective.append(
            {
                **lane,
                "interval_minutes": interval_minutes,
                "timeout_seconds": timeout_seconds,
                "retries": retries,
            }
        )
    policy_status = (
        "active_threshold_gated"
        if cadence_acceleration_allowed
        else "active_recovery_only_cadence_baseline"
    )
    return tuple(effective), policy_status


def build_schedule_plan(
    repo_root: Path, now_utc: datetime, requested_lane_ids: tuple[str, ...]
) -> dict[str, Any]:
    if repo_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(
            f"repository root mismatch: expected={REPO_ROOT}, actual={repo_root}"
        )
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    effective_lanes, improvement_policy_status = _effective_lanes(now_utc)
    known_ids = {lane["lane_id"] for lane in effective_lanes}
    unknown = sorted(set(requested_lane_ids) - known_ids)
    if unknown:
        raise ValueError(f"unknown schedule lane ids: {unknown}")
    state, state_status = read_optional_json(SCHEDULE_STATE_PATH)
    completions = _object_mapping(state, "last_success_utc")
    attempts = _object_mapping(state, "last_attempt_utc")
    lane_statuses = _object_mapping(state, "lane_statuses")
    verified_state_semantics = (
        str(state.get("schedule_state_version", "")) == SCHEDULE_STATE_VERSION
    )
    now = now_utc.astimezone(timezone.utc)
    now_et = now.astimezone(NEW_YORK)
    storage_pressure = measure_storage_pressure(repo_root, False)
    records: list[dict[str, Any]] = []
    for lane in effective_lanes:
        lane_id = lane["lane_id"]
        evidence = evaluate_lane_evidence_at(lane_id, now)
        last_attempt = _parse_timestamp(attempts.get(lane_id, completions.get(lane_id)))
        verified_success_value = (
            completions.get(lane_id)
            if verified_state_semantics or evidence["verified_complete"]
            else None
        )
        last_success = _parse_timestamp(verified_success_value)
        attempt_elapsed = (
            None
            if last_attempt is None
            else (now - last_attempt.astimezone(timezone.utc)).total_seconds() / 60.0
        )
        success_elapsed = (
            None
            if last_success is None
            else (now - last_success.astimezone(timezone.utc)).total_seconds() / 60.0
        )
        interval_due = last_attempt is None or float(attempt_elapsed) >= float(
            lane["interval_minutes"]
        )
        window_open = _window_open(lane["window"], now_et)
        selected = not requested_lane_ids or lane_id in requested_lane_ids
        dependency_blocker = _dependency_blocker(lane_id, now)
        storage_blocker = storage_blocker_for_lane(
            lane_id,
            storage_pressure,
        )
        operational_blocker = dependency_blocker or storage_blocker
        last_status_record = lane_statuses.get(lane_id)
        last_run_status = (
            str(last_status_record.get("status", "unknown"))
            if isinstance(last_status_record, dict)
            else "unknown"
        )
        calendar_due = (
            selected
            and window_open
            and interval_due
            and operational_blocker is None
        )
        execution_owner = EXTERNAL_LANE_OWNERS.get(lane_id, "dopey_acceleration_cycle")
        records.append(
            {
                **lane,
                "selected": selected,
                "window_open": window_open,
                "interval_due": interval_due,
                "last_attempt_utc": last_attempt.isoformat()
                if last_attempt is not None
                else None,
                "last_verified_success_utc": last_success.isoformat()
                if last_success is not None
                else None,
                "minutes_since_attempt": round(attempt_elapsed, 2)
                if attempt_elapsed is not None
                else None,
                "minutes_since_success": round(success_elapsed, 2)
                if success_elapsed is not None
                else None,
                "last_run_status": last_run_status,
                "evidence_verification": evidence,
                "calendar_due": calendar_due,
                "due": calendar_due and lane_id not in EXTERNAL_LANE_OWNERS,
                "execution_owner": execution_owner,
                "subsumed_by": execution_owner
                if lane_id in EXTERNAL_LANE_OWNERS
                else None,
                "blocked_by": operational_blocker,
                "storage_blocked": storage_blocker is not None,
            }
        )
    close_due = any(
        record["lane_id"] == "daily_close_stack" and record["due"] for record in records
    )
    if close_due:
        for record in records:
            if record["lane_id"] in SUBSUMED_BY_CLOSE and record["due"]:
                record["due"] = False
                record["subsumed_by"] = "daily_close_stack"
    vnext_research_due = any(
        record["lane_id"] == "vnext_forward_research" and record["due"]
        for record in records
    )
    if vnext_research_due:
        for record in records:
            if record["lane_id"] in SUBSUMED_BY_VNEXT_RESEARCH and record["due"]:
                record["due"] = False
                record["subsumed_by"] = "vnext_forward_research"
    due_records = sorted(
        (record for record in records if record["due"]),
        key=_due_priority,
    )
    plan = stamped(
        {
            "artifact_type": "research_acceleration_schedule_plan",
            "schedule_version": "dopey-research-schedule-v22",
            "generated_utc": now.isoformat(),
            "generated_et": now_et.isoformat(),
            "state_status": state_status,
            "lanes": records,
            "due_lane_ids": [record["lane_id"] for record in due_records],
            "policy": "cadence from persisted attempts; readiness from status-and-freshness verified evidence; due work is prioritized by never-successful then stalest-successful lane; standalone daily and nightly owners cannot be duplicated by the acceleration cycle",
            "autonomous_improvement_policy_status": improvement_policy_status,
            "autonomous_improvement_policy_path": str(ACTIVE_IMPROVEMENT_POLICY_PATH),
            "storage_pressure": storage_pressure,
            "paper_only": True,
            "live_blocked": True,
            "broker_lanes_present": False,
        }
    )
    write_json_atomic(SCHEDULE_PLAN_PATH, plan)
    return plan
