"""Write deterministic offline 0DTE special lifecycle risk artifacts."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .zero_dte_decision_engine import evaluate_zero_dte_candidate
from .zero_dte_risk_model import ZERO_DTE_RISK_MODEL_VERSION, ZeroDTERiskInput
from .zero_dte_risk_thresholds import (
    ZERO_DTE_RISK_THRESHOLDS_FIXTURE_PATH,
    ZeroDTERiskThresholds,
    load_default_zero_dte_risk_thresholds,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy" / "zero_dte_risk_cases.json"
ZERO_DTE_RISK_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "zero_dte_risk"
ZERO_DTE_RISK_DECISIONS_PATH = ZERO_DTE_RISK_ARTIFACT_DIR / "zero_dte_risk_decisions.jsonl"
ZERO_DTE_RISK_THRESHOLDS_PATH = ZERO_DTE_RISK_ARTIFACT_DIR / "zero_dte_risk_thresholds.json"
ZERO_DTE_RISK_SUMMARY_PATH = ZERO_DTE_RISK_ARTIFACT_DIR / "zero_dte_risk_summary.json"
ZERO_DTE_RISK_PROOF_PATH = ZERO_DTE_RISK_ARTIFACT_DIR / "zero_dte_risk_proof.jsonl"
ZERO_DTE_BLOCKED_CANDIDATES_PATH = ZERO_DTE_RISK_ARTIFACT_DIR / "zero_dte_blocked_candidates.jsonl"
ZERO_DTE_APPROVED_CANDIDATES_PATH = ZERO_DTE_RISK_ARTIFACT_DIR / "zero_dte_approved_candidates.jsonl"


def load_zero_dte_risk_cases(path: Path | str = FIXTURE_PATH) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults = payload.get("case_defaults", {})
    if not isinstance(defaults, dict):
        raise TypeError("zero_dte_risk_cases case_defaults must be object")
    cases: list[dict[str, Any]] = []
    raw_cases = payload.get("cases", [])
    if not isinstance(raw_cases, list):
        raise TypeError("zero_dte_risk_cases cases must be list")
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise TypeError("zero_dte_risk case must be object")
        overrides = raw_case.get("input", {})
        if not isinstance(overrides, dict):
            raise TypeError("zero_dte_risk case input must be object")
        merged_input = {**defaults, **overrides}
        cases.append({
            "case_id": str(raw_case["case_id"]),
            "input": merged_input,
            "expected_decision": str(raw_case["expected_decision"]),
            "expected_reason_codes": list(raw_case.get("expected_reason_codes", [])),
        })
    return cases


def evaluate_zero_dte_fixture_cases(
    cases: list[dict[str, Any]],
    thresholds: ZeroDTERiskThresholds,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in cases:
        candidate = ZeroDTERiskInput.from_dict(case["input"])
        decision = evaluate_zero_dte_candidate(candidate, thresholds)
        decision_record = decision.to_dict()
        records.append({
            "case_id": case["case_id"],
            "expected_decision": case["expected_decision"],
            "expected_reason_codes": case["expected_reason_codes"],
            "decision": decision_record,
            "expectation_matched": (
                decision.decision == case["expected_decision"]
                and set(case["expected_reason_codes"]).issubset(set(decision.reason_codes))
            ),
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
        })
    return records


def run_zero_dte_risk_model() -> dict[str, Any]:
    thresholds = load_default_zero_dte_risk_thresholds()
    cases = load_zero_dte_risk_cases(FIXTURE_PATH)
    evaluated = evaluate_zero_dte_fixture_cases(cases, thresholds)
    decisions = [record["decision"] for record in evaluated]
    blocked = [
        decision for decision in decisions
        if str(decision["approval_status"]) == "blocked" or str(decision["decision"]).startswith("blocked")
    ]
    approved = [
        decision for decision in decisions
        if decision["decision"] in {"approved_for_paper_open", "approved_with_throttle"}
    ]
    throttled = [decision for decision in decisions if decision["decision"] == "approved_with_throttle"]
    expiry_only = [decision for decision in decisions if decision["decision"] == "expiry_managed_only"]
    alternatives = [decision for decision in decisions if decision["decision"] == "prefer_non_zero_dte_alternative"]
    top_block_reasons = Counter(
        reason
        for decision in blocked
        for reason in decision.get("reason_codes", [])
    )
    risk_tiers = Counter(str(decision["risk_tier"]) for decision in decisions)
    summary = {
        "zero_dte_risk_model_version": ZERO_DTE_RISK_MODEL_VERSION,
        "threshold_version": thresholds.threshold_version,
        "fixture_case_count": len(cases),
        "decision_count": len(decisions),
        "approved_count": len(approved),
        "blocked_count": len(blocked),
        "throttled_count": len(throttled),
        "expiry_managed_only_count": len(expiry_only),
        "non_zero_dte_alternative_recommendations": len(alternatives),
        "top_block_reasons": dict(top_block_reasons.most_common(8)),
        "risk_tier_distribution": dict(sorted(risk_tiers.items())),
        "all_expectations_matched": all(record["expectation_matched"] for record in evaluated),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    ZERO_DTE_RISK_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(ZERO_DTE_RISK_THRESHOLDS_PATH, {
        "artifact_type": "zero_dte_risk_thresholds",
        "thresholds": thresholds.to_dict(),
        "source_fixture": str(ZERO_DTE_RISK_THRESHOLDS_FIXTURE_PATH),
        "paper_only": True,
        "live_blocked": True,
    })
    _write_jsonl(ZERO_DTE_RISK_DECISIONS_PATH, decisions)
    _write_json(ZERO_DTE_RISK_SUMMARY_PATH, summary)
    _write_jsonl(ZERO_DTE_BLOCKED_CANDIDATES_PATH, blocked)
    _write_jsonl(ZERO_DTE_APPROVED_CANDIDATES_PATH, approved)
    proof_records = [
        {
            "artifact_type": "zero_dte_risk_proof",
            "candidate_id": decision["candidate_id"],
            "decision": decision["decision"],
            "risk_tier": decision["risk_tier"],
            "score_components": decision["score_components"],
            "reason_codes": decision["reason_codes"],
            "threshold_version": decision["threshold_version"],
            "decision_hash": decision["decision_hash"],
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
        }
        for decision in decisions
    ]
    for proof in proof_records:
        proof["reproducibility_hash"] = reproducibility_hash(proof)
    _write_jsonl(ZERO_DTE_RISK_PROOF_PATH, proof_records)
    return {
        "zero_dte_risk_model_status": "ok" if summary["all_expectations_matched"] else "fixture_expectation_mismatch",
        "summary": summary,
        "artifact_paths": zero_dte_risk_artifact_paths(),
    }


def zero_dte_risk_artifact_paths() -> dict[str, str]:
    return {
        "zero_dte_risk_decisions": str(ZERO_DTE_RISK_DECISIONS_PATH),
        "zero_dte_risk_thresholds": str(ZERO_DTE_RISK_THRESHOLDS_PATH),
        "zero_dte_risk_summary": str(ZERO_DTE_RISK_SUMMARY_PATH),
        "zero_dte_risk_proof": str(ZERO_DTE_RISK_PROOF_PATH),
        "zero_dte_blocked_candidates": str(ZERO_DTE_BLOCKED_CANDIDATES_PATH),
        "zero_dte_approved_candidates": str(ZERO_DTE_APPROVED_CANDIDATES_PATH),
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash(payload)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_zero_dte_risk_model()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["zero_dte_risk_model_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
