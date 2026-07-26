"""Tests for DOPEY export bundle review assistant artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS, build_inventory, load_records
from dopey_audit.audit_runner import run_offline_evidence_replay_audit
from dopey_audit.hash_auditor import audit_record_hash
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.export_models import DEFAULT_EXPORT_PROFILE
from dopey_export.export_safety_scanner import scan_artifact_path
from dopey_export.export_verifier import run_artifact_compaction_export_verifier
from dopey_export_review.evidence_map import build_evidence_map
from dopey_export_review.review_checklist import build_review_checklist
from dopey_export_review.review_data import load_review_context
from dopey_export_review.review_models import (
    ExportReviewBundle,
    ExportReviewFinding,
)
from dopey_export_review.review_paths import (
    EXPORT_REVIEW_FINDINGS_PATH,
    EXPORT_REVIEW_PROOF_PATH,
    EXPORT_REVIEW_REGISTRY_PATH,
    EXPORT_REVIEW_ROOT,
    LATEST_CHECKLIST_PATH,
    LATEST_EVIDENCE_MAP_PATH,
    LATEST_EXECUTIVE_SUMMARY_PATH,
    LATEST_NEXT_STEPS_PATH,
    LATEST_PRIORITY_QUEUE_PATH,
    LATEST_SAFETY_SUMMARY_PATH,
)
from dopey_export_review.review_priority import build_review_priorities
from dopey_export_review.review_runner import run_export_bundle_review_assistant


@pytest.fixture(scope="module")
def review_result() -> dict:
    run_artifact_compaction_export_verifier(DEFAULT_EXPORT_PROFILE)
    return run_export_bundle_review_assistant()


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="review-live-x",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
            {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5},
        ],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )


def test_export_review_bundle_serializes_deterministically() -> None:
    bundle = ExportReviewBundle(
        review_id="r",
        source_bundle_id="b",
        source_export_path="s",
        manifest_path="m",
        copy_proof_path="c",
        artifact_count=1,
        total_size_bytes=2,
        hash_status="pass",
        copy_status="verified",
        safety_status="pass",
        credential_scan_status="pass",
        active_forbidden_live_decisions=0,
        review_artifact_paths=["a"],
        recommended_review_order=["manifest"],
        known_gaps=["gap"],
        next_build_target="export_review_comparison_diff_artifacts",
        paper_only=True,
        live_blocked=True,
        reproducibility_hash="h",
    )
    assert json.dumps(bundle.to_dict(), sort_keys=True) == json.dumps(bundle.to_dict(), sort_keys=True)


def test_export_review_finding_serializes_deterministically() -> None:
    finding = ExportReviewFinding("f", "info", "manifest", "p", "summary", {"a": 1}, "act", True, False)
    assert json.dumps(finding.to_dict(), sort_keys=True) == json.dumps(finding.to_dict(), sort_keys=True)


def test_export_review_checklist_hash_is_deterministic(review_result: dict) -> None:
    ctx = load_review_context()
    first = build_review_checklist(ctx, "pass", "verified")
    second = build_review_checklist(ctx, "pass", "verified")
    assert first.reproducibility_hash == second.reproducibility_hash


def test_export_review_run_result_records_source_bundle(review_result: dict) -> None:
    assert review_result["source_bundle_id"].startswith("dopey-export-")


def test_review_checklist_includes_bundle_identity(review_result: dict) -> None:
    text = LATEST_CHECKLIST_PATH.read_text(encoding="utf-8")
    assert "Bundle identity" in text
    assert review_result["source_bundle_id"] in text


def test_review_checklist_includes_completeness_section(review_result: dict) -> None:
    assert "Completeness" in LATEST_CHECKLIST_PATH.read_text(encoding="utf-8")


def test_review_checklist_includes_safety_section(review_result: dict) -> None:
    text = LATEST_CHECKLIST_PATH.read_text(encoding="utf-8")
    assert "Safety" in text
    assert "mode=RESEARCH" in text
    assert "live_trading_enabled=false" in text


def test_review_checklist_includes_evidence_quality_section(review_result: dict) -> None:
    assert "Evidence quality" in LATEST_CHECKLIST_PATH.read_text(encoding="utf-8")


def test_review_checklist_includes_strategy_family_summary(review_result: dict) -> None:
    assert "Strategy/family summary" in LATEST_CHECKLIST_PATH.read_text(encoding="utf-8")


def test_review_checklist_includes_reviewer_priorities(review_result: dict) -> None:
    assert "Reviewer priorities" in LATEST_CHECKLIST_PATH.read_text(encoding="utf-8")


def test_executive_summary_written(review_result: dict) -> None:
    assert LATEST_EXECUTIVE_SUMMARY_PATH.exists()
    assert "DOPEY Export Review Executive Summary" in LATEST_EXECUTIVE_SUMMARY_PATH.read_text(encoding="utf-8")


def test_review_safety_summary_written(review_result: dict) -> None:
    assert LATEST_SAFETY_SUMMARY_PATH.exists()
    assert "offline_only" in LATEST_SAFETY_SUMMARY_PATH.read_text(encoding="utf-8")


def test_review_priority_queue_written(review_result: dict) -> None:
    assert LATEST_PRIORITY_QUEUE_PATH.exists()
    assert "Priority Queue" in LATEST_PRIORITY_QUEUE_PATH.read_text(encoding="utf-8")


def test_review_next_steps_written(review_result: dict) -> None:
    assert LATEST_NEXT_STEPS_PATH.exists()
    assert "export_review_comparison_diff_artifacts" in LATEST_NEXT_STEPS_PATH.read_text(encoding="utf-8")


def test_review_packet_states_fixture_paper_only(review_result: dict) -> None:
    combined = LATEST_EXECUTIVE_SUMMARY_PATH.read_text(encoding="utf-8") + LATEST_SAFETY_SUMMARY_PATH.read_text(encoding="utf-8")
    assert "fixture_only" in combined
    assert "paper_only" in combined
    assert "live_path_enabled: `false`" in combined


def test_evidence_map_links_reports_to_source_artifacts(review_result: dict) -> None:
    evidence_map = json.loads(LATEST_EVIDENCE_MAP_PATH.read_text(encoding="utf-8"))
    assert evidence_map["report_to_source_artifacts"]


def test_evidence_map_links_manifest_to_exported_files(review_result: dict) -> None:
    evidence_map = json.loads(LATEST_EVIDENCE_MAP_PATH.read_text(encoding="utf-8"))
    assert len(evidence_map["manifest_to_exported_files"]) == review_result["artifact_count"]


def test_evidence_map_links_copy_proof_to_target_files(review_result: dict) -> None:
    evidence_map = json.loads(LATEST_EVIDENCE_MAP_PATH.read_text(encoding="utf-8"))
    ctx = load_review_context()
    copy_status = str(ctx.export_copy_proof.get("verification_status", "missing"))
    if copy_status == "skipped_unavailable":
        assert evidence_map["copy_proof_to_target_files"] == []
        assert not ctx.export_copy_proof.get("target_dir")
    else:
        assert evidence_map["copy_proof_to_target_files"]


def test_evidence_map_references_existing_paths_or_marks_missing(review_result: dict) -> None:
    evidence_map = json.loads(LATEST_EVIDENCE_MAP_PATH.read_text(encoding="utf-8"))
    assert all("exists" in item for item in evidence_map["manifest_to_exported_files"])


def test_evidence_map_is_deterministic(review_result: dict) -> None:
    ctx = load_review_context()
    assert build_evidence_map(ctx).reproducibility_hash == build_evidence_map(ctx).reproducibility_hash


def test_review_priority_orders_safety_before_gaps(review_result: dict) -> None:
    ctx = load_review_context()
    safety = ExportReviewFinding("s", "safety_error", "safety", "p", "safety issue", {}, "fix", True, True)
    gap = ExportReviewFinding("g", "warning", "gap", "p", "gap", {}, "review", True, False)
    priorities = build_review_priorities(ctx, [gap, safety], "pass", "verified")
    assert priorities[0].severity == "safety_error"


def test_review_priority_includes_manifest_and_copy_proof(review_result: dict) -> None:
    text = LATEST_PRIORITY_QUEUE_PATH.read_text(encoding="utf-8")
    assert "manifest" in text
    assert "copy_proof" in text


def test_review_priority_includes_top_evidence_gaps(review_result: dict) -> None:
    assert "evidence gaps" in LATEST_PRIORITY_QUEUE_PATH.read_text(encoding="utf-8").lower()


def test_review_priority_queue_is_deterministic(review_result: dict) -> None:
    ctx = load_review_context()
    first = [item.to_dict() for item in build_review_priorities(ctx, [], "pass", "verified")]
    second = [item.to_dict() for item in build_review_priorities(ctx, [], "pass", "verified")]
    assert first == second


def test_export_bundle_review_assistant_cli_runs_offline(review_result: dict) -> None:
    assert review_result["review_status"] == "ok"
    assert review_result["mode"] == "RESEARCH"
    assert review_result["live_trading_enabled"] is False


def test_export_review_registry_written(review_result: dict) -> None:
    assert EXPORT_REVIEW_REGISTRY_PATH.exists()
    assert _jsonl(EXPORT_REVIEW_REGISTRY_PATH)[-1]["source_bundle_id"] == review_result["source_bundle_id"]


def test_export_review_findings_written(review_result: dict) -> None:
    assert EXPORT_REVIEW_FINDINGS_PATH.exists()
    assert _jsonl(EXPORT_REVIEW_FINDINGS_PATH)


def test_export_review_proof_record_written(review_result: dict) -> None:
    assert EXPORT_REVIEW_PROOF_PATH.exists()
    assert _jsonl(EXPORT_REVIEW_PROOF_PATH)[-1]["final_status"] == "PASS"


def test_export_review_reproducibility_hash_is_deterministic(review_result: dict) -> None:
    second = run_export_bundle_review_assistant()
    assert second["reproducibility_hash"] == review_result["reproducibility_hash"]


def test_evidence_audit_recognizes_export_review_artifacts(review_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    expected = {
        "export_review_registry",
        "export_review_findings",
        "export_review_proof",
        "export_review_checklist",
        "export_review_executive_summary",
        "export_review_evidence_map",
        "export_review_priority_queue",
        "export_review_safety_summary",
    }
    assert expected.issubset(names)
    assert any(artifact.artifact_type == "export_review_registry" and artifact.status == "present" for artifact in build_inventory().artifacts)


def test_evidence_audit_hashes_export_review_checklist(review_result: dict) -> None:
    record = load_records(LATEST_CHECKLIST_PATH)[-1]
    case, finding = audit_record_hash("export_review_checklist", record, 0)
    assert case is not None
    assert case.passed is True
    assert finding is None


def test_evidence_audit_validates_export_review_evidence_map(review_result: dict) -> None:
    audit = run_offline_evidence_replay_audit()
    checks = {check["check_id"]: check["passed"] for check in audit["consistency_audit"]["checks"]}
    assert checks["export_review_evidence_map_valid"] is True


def test_evidence_audit_records_export_review_summary(review_result: dict) -> None:
    audit = run_offline_evidence_replay_audit()
    source_bundle_id = audit["export_review_summary"]["source_bundle_id"]
    assert review_result["source_bundle_id"]
    assert source_bundle_id
    assert source_bundle_id == audit["export_summary"]["bundle_id"]


def test_no_live_promotion_possible_after_export_review_assistant(review_result: dict) -> None:
    assert review_result["active_forbidden_live_decisions"] == 0


def test_live_stubs_still_block_after_export_review_assistant(review_result: dict) -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_export_review_assistant(review_result: dict) -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_export_review_assistant(review_result: dict) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_export_review_assistant_does_not_modify_live_settings(review_result: dict) -> None:
    assert review_result["live_blocked"] is True
    assert review_result["live_trading_enabled"] is False


def test_export_review_artifacts_contain_no_active_live_decisions(review_result: dict) -> None:
    active = 0
    for path in EXPORT_REVIEW_ROOT.rglob("*"):
        if path.is_file():
            active += sum(1 for finding in scan_artifact_path(path) if "forbidden live decision" in finding.reason)
    assert active == 0


def test_export_review_artifacts_contain_no_credentials(review_result: dict) -> None:
    credentials = 0
    for path in EXPORT_REVIEW_ROOT.rglob("*"):
        if path.is_file():
            credentials += sum(1 for finding in scan_artifact_path(path) if "credential" in finding.reason or "API-key" in finding.reason)
    assert credentials == 0


def test_export_review_assistant_does_not_create_chat_agent_or_server(review_result: dict) -> None:
    package_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("dopey_export_review").glob("*.py"))
    assert "http.server" not in package_text
    assert "uvicorn" not in package_text
    assert "chat_agent" not in package_text


def test_blunder_source_integrity_if_manifest_available(review_result: dict) -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available")
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        expected, file_path = parts
        candidate = Path(file_path)
        if not candidate.exists():
            continue
        assert hashlib.sha256(candidate.read_bytes()).hexdigest().upper() == expected.upper()
        checked += 1
    assert checked > 0
