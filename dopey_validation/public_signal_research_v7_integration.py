"""V7 integration touch points validator.

Verifies that audit, reporting, export, export-review, and validation
infrastructure recognizes the V7 signal-research-breakthrough artifact
family. Writes a summary + proof JSONL.

This module never enables live trading and never lowers MIN_BREAKTHROUGH_PF.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V7_ROOT,
    RESEARCH_V7_VERSION,
    research_v7_proof_record,
)


INTEGRATION_SUMMARY_PATH = RESEARCH_V7_ROOT / "v7_integration_touch_points_summary.json"
INTEGRATION_PROOF_PATH = RESEARCH_V7_ROOT / "v7_integration_touch_points_proof.jsonl"

_V7_ARTIFACT_TYPES = {
    "public_signal_research_v7_preflight_summary",
    "public_signal_research_v7_baseline_freeze_summary",
    "no_trade_contribution_audit_v7_summary",
    "v6_watchlist_diagnosis_v7_summary",
    "research_mutation_queue_executor_v7_summary",
    "trade_active_repair_policy_v7_summary",
    "research_candidate_generator_v7_summary",
    "profit_holdout_split_scorer_v7_summary",
    "research_path_simulator_v7_summary",
    "research_tournament_v7_summary",
    "research_breakthrough_gate_v7_summary",
    "research_mutation_queue_v7_summary",
    "public_signal_research_scoreboard_v7",
    "public_signal_research_live_gate_status_v7",
    "public_signal_research_breakthrough_v7_summary",
    "public_signal_research_breakthrough_v7_validation_summary",
}

_V7_EVIDENCE_KEYS = {
    "public_signal_research_v7_preflight_summary",
    "public_signal_research_v7_baseline_freeze_summary",
    "no_trade_contribution_audit_v7_summary",
    "v6_watchlist_diagnosis_v7_summary",
    "research_mutation_queue_executor_v7_summary",
    "trade_active_repair_policy_v7_summary",
    "research_candidate_generator_v7_summary",
    "profit_holdout_split_scorer_v7_summary",
    "research_path_simulator_v7_summary",
    "research_tournament_v7_summary",
    "research_breakthrough_gate_v7_summary",
    "research_mutation_queue_v7_summary",
    "public_signal_research_breakthrough_v7_summary",
    "public_signal_research_breakthrough_v7_validation_summary",
    "public_signal_research_scoreboard_v7",
    "public_signal_research_live_gate_status_v7",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_artifact_loader() -> dict[str, object]:
    from dopey_audit.artifact_loader import ARTIFACT_SPECS

    recognized = {spec[0] for spec in ARTIFACT_SPECS}
    missing = sorted(_V7_ARTIFACT_TYPES - recognized)
    v7_count = sum(1 for name in recognized if "v7" in name)
    return {
        "name": "artifact_loader_v7_specs",
        "passed": not missing,
        "missing": missing,
        "recognized_count": v7_count,
    }


def _check_data_loader() -> dict[str, object]:
    from dopey_reporting.data_loader import EVIDENCE_PATHS

    missing = sorted(_V7_EVIDENCE_KEYS - set(EVIDENCE_PATHS))
    v7_count = sum(1 for name in EVIDENCE_PATHS if "v7" in name)
    return {
        "name": "reporting_data_loader_v7_paths",
        "passed": not missing,
        "missing": missing,
        "recognized_count": v7_count,
    }


def _check_artifact_selector() -> dict[str, object]:
    from dopey_export.artifact_selector import export_selection_rules

    rules = export_selection_rules()
    recognized = {r.artifact_id for r in rules}
    missing = sorted(_V7_ARTIFACT_TYPES - recognized)
    v7_count = sum(1 for name in recognized if "v7" in name)
    return {
        "name": "export_artifact_selector_v7_rules",
        "passed": not missing,
        "missing": missing,
        "recognized_count": v7_count,
    }


def _check_review_models() -> dict[str, object]:
    from dopey_export_review.review_models import FINDING_CATEGORIES

    passed = "public_signal_research_breakthrough_v7" in FINDING_CATEGORIES
    return {
        "name": "export_review_models_v7_category",
        "passed": passed,
        "missing": [] if passed else ["public_signal_research_breakthrough_v7"],
    }


def _check_review_packet() -> dict[str, object]:
    import dopey_export_review.review_packet as rp

    passed = hasattr(rp, "_render_public_signal_research_v7_section")
    return {
        "name": "export_review_packet_v7_section",
        "passed": passed,
        "missing": [] if passed else ["_render_public_signal_research_v7_section"],
    }


def _check_evidence_models() -> dict[str, object]:
    from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS

    passed = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7" in ALLOWED_NEXT_BUILD_TARGETS
    return {
        "name": "audit_evidence_models_v7_target",
        "passed": passed,
        "missing": [] if passed else ["DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7"],
    }


def _check_full_suite_stabilizer() -> dict[str, object]:
    import dopey_validation.full_suite_stabilizer as fss

    src = Path(fss.__file__).read_text(encoding="utf-8")
    passed = "test_public_signal_research_breakthrough_v7.py" in src
    return {
        "name": "full_suite_stabilizer_v7_tests",
        "passed": passed,
        "missing": [] if passed else ["tests/test_public_signal_research_breakthrough_v7.py"],
    }


def _check_canon_doc() -> dict[str, object]:
    path = Path(__file__).resolve().parent.parent / "DOPEY_CANON.md"
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7" in text
    return {
        "name": "DOPEY_CANON_v7_section",
        "passed": passed,
        "missing": [] if passed else ["DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7"],
    }


def _check_validation_report() -> dict[str, object]:
    path = Path(__file__).resolve().parent.parent / "DOPEY_VALIDATION_REPORT.md"
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7" in text
    return {
        "name": "DOPEY_VALIDATION_REPORT_v7_section",
        "passed": passed,
        "missing": [] if passed else ["DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7"],
    }


def run_v7_integration_touch_points() -> dict[str, object]:
    checks = [
        _check_artifact_loader(),
        _check_data_loader(),
        _check_artifact_selector(),
        _check_review_models(),
        _check_review_packet(),
        _check_evidence_models(),
        _check_full_suite_stabilizer(),
        _check_canon_doc(),
        _check_validation_report(),
    ]
    failed = [c for c in checks if not c["passed"]]
    summary: dict[str, object] = {
        "artifact_type": "public_signal_research_v7_integration_touch_points_summary",
        "integration_status": "pass" if not failed else "fail",
        "bundle_version": RESEARCH_V7_VERSION,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "live_trading_enabled": False,
        "no_trade_only_blocked": True,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": [c["name"] for c in failed],
        "timestamp": _utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    summary["summary_path"] = str(INTEGRATION_SUMMARY_PATH)
    summary["proof_path"] = str(INTEGRATION_PROOF_PATH)
    summary = write_summary_with_hash(INTEGRATION_SUMMARY_PATH, summary)
    proof_payload = {
        "integration_status": summary["integration_status"],
        "check_count": summary["check_count"],
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
        "failed_checks": summary["failed_checks"],
    }
    write_jsonl_file(
        INTEGRATION_PROOF_PATH,
        [research_v7_proof_record("v7_integration_touch_points", str(summary["integration_status"]), proof_payload)],
    )
    return summary


if __name__ == "__main__":
    result = run_v7_integration_touch_points()
    print(
        json.dumps(
            {
                "integration_status": result["integration_status"],
                "check_count": result["check_count"],
                "passed_count": result["passed_count"],
                "failed_count": result["failed_count"],
                "failed_checks": result["failed_checks"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    raise SystemExit(0 if result["integration_status"] == "pass" else 1)
