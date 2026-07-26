"""Tests for DOPEY artifact compaction/export verifier."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS, build_inventory, load_latest_record
from dopey_audit.hash_auditor import audit_record_hash
from dopey_audit.audit_runner import run_offline_evidence_replay_audit
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_compactor import build_ledger_compaction_summary, compact_jsonl_artifact
from dopey_export.artifact_selector import (
    EXPORT_COPY_PROOF_PATH,
    EXPORT_MANIFEST_REGISTRY_PATH,
    EXPORT_PROOF_LEDGER_PATH,
    EXPORT_REGISTRY_PATH,
    EXPORT_SAFETY_SCAN_PATH,
    default_export_profile,
    export_selection_rules,
    is_excluded_path,
    safety_state,
    select_export_artifacts,
)
from dopey_export.copy_verifier import verify_copied_bundle
from dopey_export.export_manifest import canonical_export_hash, build_export_manifest
from dopey_export.export_models import (
    DEFAULT_EXPORT_PROFILE,
    CopyProof,
    ExportArtifact,
)
from dopey_export.export_safety_scanner import (
    scan_artifact_path,
    scan_export_artifacts,
    scan_text_for_sensitive_content,
)
from dopey_export.export_verifier import run_artifact_compaction_export_verifier


@pytest.fixture(scope="module")
def export_result() -> dict:
    return run_artifact_compaction_export_verifier(DEFAULT_EXPORT_PROFILE)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sample_export_artifact(path: Path) -> ExportArtifact:
    data = path.read_bytes()
    return ExportArtifact(
        artifact_id="sample",
        artifact_type="sample_jsonl",
        source_path=str(path),
        relative_export_path="artifacts/sample.jsonl",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        record_count=2,
        parse_status="ok",
        required=True,
        safety_scan_status="not_scanned",
        notes=[],
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="export-live-x",
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


def test_export_artifact_serializes_deterministically(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    artifact = _sample_export_artifact(path)
    assert json.dumps(artifact.to_dict(), sort_keys=True) == json.dumps(artifact.to_dict(), sort_keys=True)


def test_export_manifest_hash_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    artifact = _sample_export_artifact(path)
    first = build_export_manifest("m1", "b1", DEFAULT_EXPORT_PROFILE, [artifact], {"live_blocked": True})
    second = build_export_manifest("m1", "b1", DEFAULT_EXPORT_PROFILE, [artifact], {"live_blocked": True})
    assert first.reproducibility_hash == second.reproducibility_hash


def test_export_profile_defaults_to_handoff_shared_folder() -> None:
    profile = default_export_profile()
    assert profile.profile_name == "handoff_shared_folder"


def test_export_bundle_plan_records_required_and_optional_artifacts() -> None:
    plan = select_export_artifacts(DEFAULT_EXPORT_PROFILE, safety_state())
    assert plan.required_artifacts
    assert isinstance(plan.optional_artifacts, list)
    assert plan.profile == DEFAULT_EXPORT_PROFILE


def test_artifact_selector_includes_required_reports_and_registries() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "report-dopey_validation_report" in ids
    assert "reporting_dashboard_index" in ids
    assert "audit_summary" in ids
    assert "meta_governor_registry" in ids


def test_artifact_selector_excludes_env_git_cache_and_pycache() -> None:
    assert is_excluded_path(".env")
    assert is_excluded_path(".git/config")
    assert is_excluded_path("pkg/__pycache__/x.pyc")
    assert is_excluded_path(".pytest_cache/v/cache")


def test_artifact_selector_excludes_original_blunder_source_tree() -> None:
    assert is_excluded_path("_forked_blunder/engine.py")
    assert is_excluded_path("_forked_blunder_tests/test_engine.py")


def test_artifact_selector_handles_missing_optional_artifact() -> None:
    plan = select_export_artifacts(DEFAULT_EXPORT_PROFILE, safety_state())
    assert "optional_operator_export_notes" in plan.missing_optional_artifacts


def test_jsonl_compactor_records_count_first_last_hash(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"strategy_id": "s1", "mode": "RESEARCH"}\n{"strategy_id": "s2", "live_blocked": true}\n', encoding="utf-8")
    summary = build_ledger_compaction_summary(path)
    assert summary.record_count == 2
    assert summary.first_record_hash
    assert summary.last_record_hash


def test_compaction_summary_preserves_source_hash(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"strategy_id": "s1"}\n{"strategy_id": "s2"}\n', encoding="utf-8")
    artifact = _sample_export_artifact(path)
    compacted = compact_jsonl_artifact(artifact, tmp_path / "out")
    assert compacted.source_sha256 == artifact.sha256


def test_compactor_does_not_modify_original_artifact(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    original = '{"strategy_id": "s1"}\n{"strategy_id": "s2"}\n'
    path.write_text(original, encoding="utf-8")
    compact_jsonl_artifact(_sample_export_artifact(path), tmp_path / "out")
    assert path.read_text(encoding="utf-8") == original


def test_compaction_output_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"strategy_id": "s1"}\n{"strategy_id": "s2"}\n', encoding="utf-8")
    first = compact_jsonl_artifact(_sample_export_artifact(path), tmp_path / "out1")
    second = compact_jsonl_artifact(_sample_export_artifact(path), tmp_path / "out2")
    assert first.reproducibility_hash == second.reproducibility_hash


def test_export_safety_scanner_detects_active_forbidden_live_decision(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"decision": "live_candidate"}', encoding="utf-8")
    findings = scan_artifact_path(path)
    assert any(finding.token == "live_candidate" for finding in findings)


def test_export_safety_scanner_allows_forbidden_terms_in_blocked_documentation(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("Forbidden live decisions include live_candidate and micro_live; they remain blocked.", encoding="utf-8")
    findings = scan_text_for_sensitive_content(path, path.read_text(encoding="utf-8"))
    assert not findings


def test_export_safety_scanner_detects_api_key_like_string(tmp_path: Path) -> None:
    path = tmp_path / "secret.txt"
    path.write_text("OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz", encoding="utf-8")
    findings = scan_text_for_sensitive_content(path, path.read_text(encoding="utf-8"))
    assert any("credential" in finding.reason or "API-key" in finding.reason for finding in findings)


def test_export_safety_scanner_detects_env_file_export_attempt(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("BROKER_TOKEN=redacted-test-value", encoding="utf-8")
    findings = scan_text_for_sensitive_content(path, path.read_text(encoding="utf-8"))
    assert any("env" in finding.reason.lower() for finding in findings)


def test_export_safety_scan_result_blocks_verified_export_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"decision": "live_candidate"}', encoding="utf-8")
    result = scan_export_artifacts("bad-bundle", [_sample_export_artifact(path)])
    assert result.verification_blocked is True


def test_export_verifier_builds_local_bundle(export_result: dict) -> None:
    assert Path(export_result["local_export_path"]).exists()


def test_export_verifier_writes_manifest(export_result: dict) -> None:
    assert Path(export_result["local_export_path"], "EXPORT_MANIFEST.json").exists()
    assert EXPORT_MANIFEST_REGISTRY_PATH.exists()


def test_export_verifier_verifies_file_hashes(export_result: dict) -> None:
    assert export_result["hash_mismatches"] == 0
    assert export_result["files_verified"] > 0


def test_copy_verifier_detects_missing_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "a.txt").write_text("a", encoding="utf-8")
    proof = verify_copied_bundle("b", source, target)
    assert proof.missing_files == ["a.txt"]


def test_copy_verifier_detects_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "a.txt").write_text("a", encoding="utf-8")
    (target / "a.txt").write_text("b", encoding="utf-8")
    proof = verify_copied_bundle("b", source, target)
    assert proof.hash_mismatches == ["a.txt"]


def test_copy_proof_serializes_deterministically(tmp_path: Path) -> None:
    proof = CopyProof("cp", "b", "s", "t", 1, 1, 1, 1, 1, [], [], [], "verified", "")
    assert canonical_export_hash(proof.to_dict()) == canonical_export_hash(proof.to_dict())


def test_shared_folder_unavailable_is_reported_not_fatal(monkeypatch) -> None:
    from dopey_export import export_verifier
    monkeypatch.setattr(export_verifier, "first_available_shared_target", lambda bundle_id: None)
    result = run_artifact_compaction_export_verifier("minimal_proof")
    assert result["export_status"] in {"ok", "fail_missing_required_artifacts"}
    assert result["copy_status"] == "skipped_unavailable"
    if result["export_status"] == "fail_missing_required_artifacts":
        assert _jsonl(EXPORT_REGISTRY_PATH)[-1]["missing_required_artifacts"]


def test_artifact_compaction_export_verifier_cli_runs_offline(export_result: dict) -> None:
    assert export_result["mode"] == "RESEARCH"
    assert export_result["live_trading_enabled"] is False
    assert export_result["live_blocked"] is True


def test_export_registry_written(export_result: dict) -> None:
    assert EXPORT_REGISTRY_PATH.exists()
    assert any(record["bundle_id"] == export_result["bundle_id"] for record in _jsonl(EXPORT_REGISTRY_PATH))


def test_export_manifest_written(export_result: dict) -> None:
    assert EXPORT_MANIFEST_REGISTRY_PATH.exists()
    assert any(record["bundle_id"] == export_result["bundle_id"] for record in _jsonl(EXPORT_MANIFEST_REGISTRY_PATH))


def test_export_safety_scan_written(export_result: dict) -> None:
    assert EXPORT_SAFETY_SCAN_PATH.exists()
    assert _jsonl(EXPORT_SAFETY_SCAN_PATH)[-1]["active_forbidden_live_decisions"] == 0


def test_export_proof_record_written(export_result: dict) -> None:
    assert EXPORT_PROOF_LEDGER_PATH.exists()
    assert export_result["export_status"] in {"ok", "fail_missing_required_artifacts"}
    expected_status = "PASS" if export_result["export_status"] == "ok" else "FAIL"
    assert _jsonl(EXPORT_PROOF_LEDGER_PATH)[-1]["final_status"] == expected_status


def test_export_reproducibility_hash_is_deterministic(export_result: dict) -> None:
    manifest = _jsonl(EXPORT_MANIFEST_REGISTRY_PATH)[-1]
    assert canonical_export_hash(manifest) == manifest["reproducibility_hash"]


def test_evidence_audit_recognizes_export_artifacts(export_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    assert {"export_registry", "export_manifest", "export_verification", "export_safety_scan", "export_copy_proof", "export_compaction_summary"}.issubset(names)
    inventory = build_inventory()
    assert any(artifact.artifact_type == "export_manifest" and artifact.status == "present" for artifact in inventory.artifacts)


def test_evidence_audit_hashes_export_manifest(export_result: dict) -> None:
    manifest = _jsonl(EXPORT_MANIFEST_REGISTRY_PATH)[-1]
    case, finding = audit_record_hash("export_manifest", manifest, 0)
    assert case is not None
    assert case.passed is True
    assert finding is None


def test_evidence_audit_reads_copy_proof(export_result: dict) -> None:
    proof = load_latest_record(EXPORT_COPY_PROOF_PATH)
    assert proof["verification_status"] in {"verified", "skipped_unavailable"}


def test_evidence_audit_export_summary_records_counts(export_result: dict) -> None:
    audit = run_offline_evidence_replay_audit()
    summary = audit["recommended_build_target"]
    assert summary["target"]
    expected_verdict = "pass" if export_result["export_status"] == "ok" else "fail_safety"
    assert audit["verdict"] == expected_verdict
    assert audit["inventory"]["artifact_count"] >= 43


def test_no_live_promotion_possible_after_export_verifier(export_result: dict) -> None:
    assert export_result["active_forbidden_live_decisions"] == 0


def test_live_stubs_still_block_after_export_verifier(export_result: dict) -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_export_verifier(export_result: dict) -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_export_verifier(export_result: dict) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_export_verifier_does_not_modify_live_settings(export_result: dict) -> None:
    state = safety_state()
    assert state["mode"] == "RESEARCH"
    assert state["live_trading_enabled"] is False
    assert state["funded_broker_connections_enabled"] is False
    assert state["allow_unofficial_robinhood_api"] is False


def test_export_bundle_contains_no_active_live_decisions(export_result: dict) -> None:
    active = 0
    for path in Path(export_result["local_export_path"]).rglob("*"):
        if path.is_file():
            active += sum(1 for finding in scan_artifact_path(path) if "forbidden live decision" in finding.reason)
    assert active == 0


def test_export_bundle_contains_no_credentials(export_result: dict) -> None:
    credential_findings = 0
    for path in Path(export_result["local_export_path"]).rglob("*"):
        if path.is_file():
            credential_findings += sum(1 for finding in scan_artifact_path(path) if "credential" in finding.reason or "API-key" in finding.reason)
    assert credential_findings == 0


def test_blunder_source_integrity_if_manifest_available(export_result: dict) -> None:
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
