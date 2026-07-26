"""Write deterministic proof-weighted paper allocation artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .allocation_decision_models import PaperAllocationDecision
from .paper_allocation_models import PaperAllocationPlan
from .paper_risk_budget import PaperRiskBudget
from .proof_weighted_allocation_models import ProofWeightedOpportunity
from .proof_weighted_allocator import build_proof_weighted_allocation_bundle


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "allocation"
PROOF_WEIGHTED_OPPORTUNITIES_FIXTURE_PATH = FIXTURE_DIR / "proof_weighted_opportunities.json"
PAPER_ALLOCATION_POLICY_FIXTURE_PATH = FIXTURE_DIR / "paper_allocation_policy.json"
PAPER_RISK_BUDGET_FIXTURE_PATH = FIXTURE_DIR / "paper_risk_budget.json"
EXPECTED_ALLOCATION_DECISIONS_FIXTURE_PATH = FIXTURE_DIR / "expected_allocation_decisions.json"
EXPECTED_ALLOCATION_PLAN_FIXTURE_PATH = FIXTURE_DIR / "expected_allocation_plan.json"

ALLOCATION_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "allocation"
PROOF_WEIGHTED_OPPORTUNITIES_PATH = ALLOCATION_ARTIFACT_DIR / "proof_weighted_opportunities.jsonl"
PAPER_ALLOCATION_POLICY_PATH = ALLOCATION_ARTIFACT_DIR / "paper_allocation_policy.json"
PAPER_RISK_BUDGET_PATH = ALLOCATION_ARTIFACT_DIR / "paper_risk_budget.json"
PAPER_ALLOCATION_DECISIONS_PATH = ALLOCATION_ARTIFACT_DIR / "paper_allocation_decisions.jsonl"
PAPER_ALLOCATION_PLAN_PATH = ALLOCATION_ARTIFACT_DIR / "paper_allocation_plan.json"
ALLOCATION_REJECTIONS_PATH = ALLOCATION_ARTIFACT_DIR / "allocation_rejections.jsonl"
ALLOCATION_WATCHLIST_PATH = ALLOCATION_ARTIFACT_DIR / "allocation_watchlist.jsonl"
ALLOCATION_EXPOSURE_SUMMARY_PATH = ALLOCATION_ARTIFACT_DIR / "allocation_exposure_summary.json"
ALLOCATION_CONSTRAINT_SUMMARY_PATH = ALLOCATION_ARTIFACT_DIR / "allocation_constraint_summary.json"
ALLOCATION_PROOF_PATH = ALLOCATION_ARTIFACT_DIR / "allocation_proof.jsonl"
PORTFOLIO_ALLOCATOR_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "portfolio_replay" / "portfolio_allocator_feedback.jsonl"
CRISIS_ALLOCATOR_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "portfolio_stress_ladder" / "crisis_allocator_feedback.jsonl"
INCIDENT_ALLOCATOR_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "incident_response" / "incident_allocator_feedback.jsonl"
LIFECYCLE_ALLOCATOR_FEEDBACK_PATH = REPO_ROOT / "artifacts" / "dopey" / "lifecycle" / "lifecycle_feedback_allocator.jsonl"


def run_proof_weighted_allocator() -> dict[str, Any]:
    bundle = build_proof_weighted_allocation_bundle()
    opportunities: list[ProofWeightedOpportunity] = bundle["opportunities"]
    decisions: list[PaperAllocationDecision] = bundle["decisions"]
    plan: PaperAllocationPlan = bundle["plan"]
    budget: PaperRiskBudget = bundle["budget"]
    policy: dict[str, Any] = bundle["policy"]
    rejections: list[PaperAllocationDecision] = bundle["rejections"]
    watchlist: list[PaperAllocationDecision] = bundle["watchlist"]
    exposure_summary: dict[str, Any] = bundle["exposure_summary"]
    constraint_summary: dict[str, Any] = bundle["constraint_summary"]
    proof_records: list[dict[str, Any]] = bundle["proof_records"]
    write_allocation_fixture_files(bundle)
    ALLOCATION_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(PROOF_WEIGHTED_OPPORTUNITIES_PATH, [opportunity.to_dict() for opportunity in opportunities])
    _write_json(PAPER_ALLOCATION_POLICY_PATH, _with_artifact_type("paper_allocation_policy", policy))
    _write_json(PAPER_RISK_BUDGET_PATH, _with_artifact_type("paper_risk_budget", budget.to_dict()))
    _write_jsonl(PAPER_ALLOCATION_DECISIONS_PATH, [decision.to_dict() for decision in decisions])
    _write_json(PAPER_ALLOCATION_PLAN_PATH, plan.to_dict())
    _write_jsonl(ALLOCATION_REJECTIONS_PATH, [decision.to_dict() for decision in rejections])
    _write_jsonl(ALLOCATION_WATCHLIST_PATH, [decision.to_dict() for decision in watchlist])
    _write_json(ALLOCATION_EXPOSURE_SUMMARY_PATH, exposure_summary)
    _write_json(ALLOCATION_CONSTRAINT_SUMMARY_PATH, constraint_summary)
    _write_jsonl(ALLOCATION_PROOF_PATH, proof_records)
    result = {
        "proof_weighted_allocator_status": "ok",
        "summary": allocation_summary(plan, decisions, exposure_summary, constraint_summary),
        "artifact_paths": proof_weighted_allocator_artifact_paths(),
    }
    result["reproducibility_hash"] = reproducibility_hash(result)
    return result


def write_allocation_fixture_files(bundle: dict[str, Any]) -> dict[str, str]:
    opportunities: list[ProofWeightedOpportunity] = bundle["opportunities"]
    decisions: list[PaperAllocationDecision] = bundle["decisions"]
    plan: PaperAllocationPlan = bundle["plan"]
    budget: PaperRiskBudget = bundle["budget"]
    policy: dict[str, Any] = bundle["policy"]
    payloads = {
        PROOF_WEIGHTED_OPPORTUNITIES_FIXTURE_PATH: {"fixture_version": "dopey-proof-weighted-opportunities-v1", "opportunity_count": len(opportunities), "records": [opportunity.to_dict() for opportunity in opportunities], "paper_only": True, "live_blocked": True},
        PAPER_ALLOCATION_POLICY_FIXTURE_PATH: {"fixture_version": "dopey-paper-allocation-policy-v1", **policy},
        PAPER_RISK_BUDGET_FIXTURE_PATH: {"fixture_version": "dopey-paper-risk-budget-v1", **budget.to_dict()},
        EXPECTED_ALLOCATION_DECISIONS_FIXTURE_PATH: {"fixture_version": "dopey-expected-allocation-decisions-v1", "decision_count": len(decisions), "records": [decision.to_dict() for decision in decisions], "paper_only": True, "live_blocked": True},
        EXPECTED_ALLOCATION_PLAN_FIXTURE_PATH: {"fixture_version": "dopey-expected-allocation-plan-v1", "plan": plan.to_dict(), "paper_only": True, "live_blocked": True},
    }
    for path, payload in payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in payloads}


def load_proof_weighted_opportunities(path: Path | str) -> list[ProofWeightedOpportunity]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ProofWeightedOpportunity.from_dict(record) for record in payload.get("records", [])]


def load_expected_allocation_decisions(path: Path | str) -> list[PaperAllocationDecision]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [PaperAllocationDecision.from_dict(record) for record in payload.get("records", [])]


def load_expected_allocation_plan(path: Path | str) -> PaperAllocationPlan:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return PaperAllocationPlan.from_dict(payload["plan"])


def proof_weighted_allocator_artifact_paths() -> dict[str, str]:
    return {
        "proof_weighted_opportunities": str(PROOF_WEIGHTED_OPPORTUNITIES_PATH),
        "paper_allocation_policy": str(PAPER_ALLOCATION_POLICY_PATH),
        "paper_risk_budget": str(PAPER_RISK_BUDGET_PATH),
        "paper_allocation_decisions": str(PAPER_ALLOCATION_DECISIONS_PATH),
        "paper_allocation_plan": str(PAPER_ALLOCATION_PLAN_PATH),
        "allocation_rejections": str(ALLOCATION_REJECTIONS_PATH),
        "allocation_watchlist": str(ALLOCATION_WATCHLIST_PATH),
        "allocation_exposure_summary": str(ALLOCATION_EXPOSURE_SUMMARY_PATH),
        "allocation_constraint_summary": str(ALLOCATION_CONSTRAINT_SUMMARY_PATH),
        "allocation_proof": str(ALLOCATION_PROOF_PATH),
    }


def allocation_summary(
    plan: PaperAllocationPlan,
    decisions: list[PaperAllocationDecision],
    exposure_summary: dict[str, Any],
    constraint_summary: dict[str, Any],
) -> dict[str, Any]:
    decision_distribution: dict[str, int] = {}
    for decision in decisions:
        decision_distribution[decision.decision] = decision_distribution.get(decision.decision, 0) + 1
    summary = {
        "artifact_type": "proof_weighted_allocation_summary",
        "plan_id": plan.plan_id,
        "opportunity_count": plan.opportunity_count,
        "decision_distribution": dict(sorted(decision_distribution.items())),
        "allocated_count": plan.allocated_count,
        "throttled_count": plan.throttled_count,
        "shadow_only_count": plan.shadow_only_count,
        "delayed_rotation_count": plan.delayed_rotation_count,
        "watchlist_count": plan.watchlist_count,
        "rejected_count": plan.rejected_count,
        "total_paper_attention_weight": plan.total_paper_attention_weight,
        "total_paper_premium_risk_units": plan.total_paper_premium_risk_units,
        "allocation_by_strategy_type": plan.allocation_by_strategy_type,
        "allocation_by_underlying_family": plan.allocation_by_underlying_family,
        "allocation_by_regime_family": plan.allocation_by_regime_family,
        "allocation_by_option_type": plan.allocation_by_option_type,
        "zero_dte_vs_swing_allocation_split": {
            "zero_dte_paper_premium_risk_units": exposure_summary["zero_dte_paper_premium_risk_units"],
            "swing_paper_premium_risk_units": exposure_summary["swing_paper_premium_risk_units"],
            "zero_dte_exposure_share": exposure_summary["zero_dte_exposure_share"],
        },
        "constraint_summary": constraint_summary,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "artifact_paths": proof_weighted_allocator_artifact_paths(),
        "portfolio_feedback_summary": portfolio_replay_feedback_summary(),
        "crisis_feedback_summary": crisis_feedback_summary(),
        "incident_feedback_summary": incident_feedback_summary(),
        "lifecycle_feedback_summary": lifecycle_feedback_summary(),
    }
    summary["portfolio_feedback_loaded"] = bool(summary["portfolio_feedback_summary"].get("portfolio_feedback_loaded", False))
    summary["portfolio_feedback_actions"] = summary["portfolio_feedback_summary"].get("feedback_action_distribution", {})
    summary["crisis_feedback_loaded"] = bool(summary["crisis_feedback_summary"].get("crisis_feedback_loaded", False))
    summary["crisis_feedback_actions"] = summary["crisis_feedback_summary"].get("feedback_action_distribution", {})
    summary["incident_feedback_loaded"] = bool(summary["incident_feedback_summary"].get("incident_feedback_loaded", False))
    summary["incident_feedback_actions"] = summary["incident_feedback_summary"].get("feedback_action_distribution", {})
    summary["lifecycle_feedback_loaded"] = bool(summary["lifecycle_feedback_summary"].get("lifecycle_feedback_loaded", False))
    summary["lifecycle_feedback_actions"] = summary["lifecycle_feedback_summary"].get("feedback_action_distribution", {})
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def portfolio_replay_feedback_summary() -> dict[str, Any]:
    if not PORTFOLIO_ALLOCATOR_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "proof_weighted_allocator_portfolio_feedback",
            "portfolio_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_allocation_mutation_allowed": False,
        }
    records = _read_jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        action = str(record.get("feedback_action", record.get("feedback_type", "")))
        action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "proof_weighted_allocator_portfolio_feedback",
        "portfolio_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_allocation_mutation_allowed": False,
    }


def crisis_feedback_summary() -> dict[str, Any]:
    if not CRISIS_ALLOCATOR_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "proof_weighted_allocator_crisis_feedback",
            "crisis_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_allocation_mutation_allowed": False,
        }
    records = _read_jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        actions = record.get("feedback_actions", [])
        if not isinstance(actions, list):
            actions = [record.get("primary_feedback_action", "")]
        for action_value in actions:
            action = str(action_value)
            action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "proof_weighted_allocator_crisis_feedback",
        "crisis_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_allocation_mutation_allowed": False,
        "real_allocation_mutation_allowed": False,
    }


def incident_feedback_summary() -> dict[str, Any]:
    if not INCIDENT_ALLOCATOR_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "proof_weighted_allocator_incident_feedback",
            "incident_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_allocation_mutation_allowed": False,
            "real_allocation_mutation_allowed": False,
        }
    records = _read_jsonl(INCIDENT_ALLOCATOR_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        actions = record.get("feedback_actions", [])
        if not isinstance(actions, list):
            actions = []
        for action_value in actions:
            action = str(action_value)
            action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "proof_weighted_allocator_incident_feedback",
        "incident_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_allocation_mutation_allowed": False,
        "real_allocation_mutation_allowed": False,
    }


def lifecycle_feedback_summary() -> dict[str, Any]:
    if not LIFECYCLE_ALLOCATOR_FEEDBACK_PATH.exists():
        return {
            "artifact_type": "proof_weighted_allocator_lifecycle_feedback",
            "lifecycle_feedback_loaded": False,
            "feedback_records_loaded": 0,
            "feedback_action_distribution": {},
            "advisory_only": True,
            "paper_only": True,
            "live_blocked": True,
            "live_allocation_mutation_allowed": False,
            "real_allocation_mutation_allowed": False,
        }
    records = _read_jsonl(LIFECYCLE_ALLOCATOR_FEEDBACK_PATH)
    action_distribution: dict[str, int] = {}
    for record in records:
        action = str(record.get("feedback_action", record.get("feedback_type", "")))
        action_distribution[action] = action_distribution.get(action, 0) + 1
    return {
        "artifact_type": "proof_weighted_allocator_lifecycle_feedback",
        "lifecycle_feedback_loaded": True,
        "feedback_records_loaded": len(records),
        "feedback_action_distribution": dict(sorted(action_distribution.items())),
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_allocation_mutation_allowed": False,
        "real_allocation_mutation_allowed": False,
    }


def _with_artifact_type(artifact_type: str, record: dict[str, Any]) -> dict[str, Any]:
    return {"artifact_type": artifact_type, **record, "paper_only": True, "live_blocked": True}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
        output.append(payload)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output) + ("\n" if output else ""), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    result = run_proof_weighted_allocator()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["proof_weighted_allocator_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
