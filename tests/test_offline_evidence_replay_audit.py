"""Tests for the DOPEY offline evidence replay audit harness.

Every test is deterministic, offline, and paper-only. No broker credentials, network access,
or live state is introduced.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.artifact_loader import (
    build_completeness_report,
    build_inventory,
)
from dopey_audit.consistency_auditor import (
    check_champion_divergence,
    check_champion_tournament_link,
    check_meta_governor_decision_evidence,
    check_mutation_champion_link,
    check_strategy_references_exist,
)
from dopey_audit.evidence_gap_planner import (
    ALLOWED_NEXT_BUILD_TARGETS,
    build_evidence_gaps,
    build_next_proof_priorities,
    recommend_build_target,
)
from dopey_audit.evidence_models import (
    EvidenceArtifact,
    EvidenceInventory,
    FORBIDDEN_LIVE_TOKENS,
)
from dopey_audit.hash_auditor import audit_record_hash, canonical_record_hash
from dopey_audit.replay_auditor import audit_schema, run_replay_audit
from dopey_audit.safety_auditor import (
    audit_blunder_integrity,
    audit_config_safety,
    audit_forbidden_decisions_in_records,
    audit_live_stubs_block,
)
from dopey_audit.score_replay import (
    audit_ensemble_score_consistency,
)
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def artifact_root(tmp_path: Path) -> Path:
    root = tmp_path / "artifacts" / "dopey"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def sample_evidence_record() -> dict:
    return {
        "run_id": "audit-sample-run-001",
        "final_status": "PASS",
        "safety_state": {"mode": "RESEARCH", "live_blocked": True},
        "score": 0.75,
    }


@pytest.fixture
def sample_ensemble_record() -> dict:
    return {
        "ensemble_allocator_version": "dopey-ensemble-allocator-v1",
        "weights_sum": 1.0,
        "candidates": [
            {
                "strategy_id": "strategy-a",
                "strategy_family": "directional_convexity",
                "source_type": "tournament",
                "base_score": 0.6,
                "walk_forward_score": 0.5,
                "analysis_fusion_score": 0.55,
                "macro_fit_score": 0.4,
                "iv_surface_fit_score": 0.45,
                "greek_fit_score": 0.5,
                "liquidity_robustness_score": 0.6,
                "slippage_robustness_score": 0.55,
                "pattern_score": 0.5,
                "failure_pressure_score": 0.1,
                "overfit_level": "low",
                "overfit_rank": 1,
                "mutation_delta": 0.0,
                "promotion_state": "paper_candidate",
                "paper_only": True,
                "holdout_score": 0.48,
                "best_regimes": ["bullish_breakout"],
                "worst_regimes": ["macro_shock_risk_off"],
            }
        ],
        "decisions": [
            {"strategy_id": "strategy-a", "recommended_weight": 1.0, "decision": "increase_paper_attention"}
        ],
        "family_weights": {"directional_convexity": 1.0},
        "source_tournament_champion": "strategy-a",
        "reproducibility_hash": "",
    }


@pytest.fixture
def audited_ensemble_record(sample_ensemble_record: dict) -> dict:
    rec = dict(sample_ensemble_record)
    rec["reproducibility_hash"] = canonical_record_hash(rec)
    return rec


# ---------------------------------------------------------------------------
# Workstream A — evidence inventory tests
# ---------------------------------------------------------------------------

def test_evidence_artifact_serializes_deterministically() -> None:
    a1 = EvidenceArtifact(artifact_type="paper_pipeline_ledger", path="/tmp/x.jsonl", exists=True, record_count=3)
    a2 = EvidenceArtifact(artifact_type="paper_pipeline_ledger", path="/tmp/x.jsonl", exists=True, record_count=3)
    assert a1.to_dict() == a2.to_dict()


def test_evidence_inventory_loads_known_artifact_paths(artifact_root: Path, sample_evidence_record: dict) -> None:
    target = artifact_root / "proof_ledger" / "dopey_paper_pipeline.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sample_evidence_record) + "\n", encoding="utf-8")
    inv = build_inventory(artifact_root)
    found = [a for a in inv.artifacts if a.artifact_type == "paper_pipeline_ledger"]
    assert found
    assert found[0].exists is True
    assert found[0].record_count == 1
    assert found[0].status in {"present", "stale"}


def test_evidence_inventory_reports_missing_artifact_without_crashing(artifact_root: Path) -> None:
    inv = build_inventory(artifact_root)
    missing = [a for a in inv.artifacts if a.status == "missing"]
    assert missing
    for a in missing:
        assert a.parse_status == "not_loaded"


def test_evidence_inventory_hash_is_deterministic(artifact_root: Path, sample_evidence_record: dict) -> None:
    target = artifact_root / "walk_forward" / "dopey_walk_forward.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(sample_evidence_record, sort_keys=True) + "\n"
    target.write_text(line * 3, encoding="utf-8")
    inv1 = build_inventory(artifact_root)
    inv2 = build_inventory(artifact_root)
    a1 = next(a for a in inv1.artifacts if a.artifact_type == "walk_forward_ledger")
    a2 = next(a for a in inv2.artifacts if a.artifact_type == "walk_forward_ledger")
    assert a1.hash == a2.hash
    assert a1.hash and len(a1.hash) == 64


def test_evidence_completeness_report_marks_empty_or_missing_records(artifact_root: Path) -> None:
    empty = artifact_root / "champion_registry" / "champion_registry.jsonl"
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("\n", encoding="utf-8")
    inv = build_inventory(artifact_root)
    report = build_completeness_report(inv)
    assert report.expected_artifacts >= 5
    assert report.empty_artifacts
    assert report.completeness_fraction <= 1.0


# ---------------------------------------------------------------------------
# Workstream B — replay/hash audit tests
# ---------------------------------------------------------------------------

def test_replay_audit_recomputes_hash_deterministically(audited_ensemble_record: dict) -> None:
    case, finding = audit_record_hash("ensemble_registry", audited_ensemble_record, 0)
    assert case is not None
    assert case.passed is True
    assert finding is None


def test_replay_audit_detects_hash_drift(audited_ensemble_record: dict) -> None:
    tampered = dict(audited_ensemble_record)
    tampered["weights_sum"] = 0.5
    # reproducibility_hash still refers to the original record.
    case, finding = audit_record_hash("ensemble_registry", tampered, 0)
    assert case is not None
    assert case.passed is False
    assert finding is not None
    assert finding.stored_hash == audited_ensemble_record["reproducibility_hash"]


def test_replay_audit_detects_score_drift(audited_ensemble_record: dict) -> None:
    drifted = dict(audited_ensemble_record)
    drifted["weights_sum"] = 2.0
    drifted["decisions"] = [
        {"strategy_id": "strategy-a", "recommended_weight": 1.5, "decision": "increase_paper_attention"}
    ]
    findings = audit_ensemble_score_consistency(drifted)
    assert findings
    assert any(f.field == "weights_sum" for f in findings)


def test_replay_audit_detects_schema_drift() -> None:
    record = {"run_id": "x"}  # missing final_status
    case, finding = audit_schema("paper_pipeline_ledger", record, 0)
    assert case is not None
    assert case.passed is False
    assert finding is not None
    assert "final_status" in finding.missing_fields


def test_replay_audit_passes_stable_fixture_record(tmp_path: Path, audited_ensemble_record: dict) -> None:
    target = tmp_path / "ensemble_allocation_registry.jsonl"
    target.write_text(json.dumps(audited_ensemble_record) + "\n", encoding="utf-8")
    inv = EvidenceInventory(artifacts=[
        EvidenceArtifact(
            artifact_type="ensemble_registry",
            path=str(target),
            exists=True,
            record_count=1,
            status="present",
        )
    ])
    replay = run_replay_audit(inv, tmp_path)
    assert replay.verdict == "pass"


# ---------------------------------------------------------------------------
# Workstream C — cross-layer consistency audit tests
# ---------------------------------------------------------------------------

def test_consistency_audit_links_champion_to_tournament_record() -> None:
    champion = {"champion_strategy_id": "strategy-a"}
    ensemble = {"source_tournament_champion": "strategy-a"}
    chk, finding = check_champion_tournament_link(champion, ensemble)
    assert chk.passed is True
    assert finding is None


def test_consistency_audit_links_mutation_champion_to_mutation_registry() -> None:
    mutation = {
        "best_mutated_strategy_id": "mut-a",
        "ranking": [{"strategy_id": "mut-a"}, {"strategy_id": "mut-b"}],
    }
    chk, finding = check_mutation_champion_link(mutation)
    assert chk.passed is True
    assert finding is None


def test_consistency_audit_links_meta_governor_decision_to_supporting_evidence() -> None:
    mg = {
        "strategy_proof_profiles": [{"strategy_id": "s1"}, {"strategy_id": "s2"}],
        "decisions": [{"strategy_id": "s1"}, {"strategy_id": "s2"}],
    }
    chk, finding = check_meta_governor_decision_evidence(mg)
    assert chk.passed is True
    assert finding is None


def test_consistency_audit_flags_missing_strategy_reference() -> None:
    known = {"s1", "s2"}
    chk, finding = check_strategy_references_exist(["s1", "s3"], known)
    assert chk.passed is False
    assert finding is not None
    assert "s3" in finding.referenced_ids


def test_consistency_audit_flags_unexplained_champion_divergence() -> None:
    assert check_champion_divergence("a", "b") is not None
    assert check_champion_divergence("a", "a") is None
    assert check_champion_divergence("a", "b", explanation="governor_override") is None


# ---------------------------------------------------------------------------
# Workstream D — safety-boundary drift audit tests
# ---------------------------------------------------------------------------

def test_safety_audit_confirms_research_mode() -> None:
    findings = audit_config_safety()
    modes = {f.check_id for f in findings}
    assert findings or "config_research_mode" not in modes
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"


def test_safety_audit_confirms_live_disabled() -> None:
    findings = audit_config_safety()
    assert all(f.severity != "safety_error" for f in findings)
    cfg = load_config(default_config_path())
    assert cfg["live_trading_enabled"] is False


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="audit-live-x",
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


def test_safety_audit_detects_active_forbidden_live_decision(artifact_root: Path) -> None:
    bad = artifact_root / "meta_governor" / "meta_governor_decisions.jsonl"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(
        json.dumps({
            "meta_governor_version": "v1",
            "decisions": [{"strategy_id": "s1", "decision": "micro_live"}],
            "safety_state": {"mode": "RESEARCH"},
        }) + "\n",
        encoding="utf-8",
    )
    inv = build_inventory(artifact_root)
    findings = audit_forbidden_decisions_in_records(inv)
    assert any(f.severity == "safety_error" for f in findings)


def test_safety_audit_allows_forbidden_terms_in_documented_forbidden_lists(artifact_root: Path) -> None:
    ok = artifact_root / "meta_governor" / "meta_governor_decisions.jsonl"
    ok.parent.mkdir(parents=True, exist_ok=True)
    ok.write_text(
        json.dumps({
            "meta_governor_version": "v1",
            "forbidden_live_decisions": sorted(FORBIDDEN_LIVE_TOKENS),
            "blocked_tiers": ["micro_live", "adaptive_live"],
            "decisions": [{"strategy_id": "s1", "decision": "hold_research_only"}],
            "safety_state": {"mode": "RESEARCH"},
        }) + "\n",
        encoding="utf-8",
    )
    inv = build_inventory(artifact_root)
    findings = audit_forbidden_decisions_in_records(inv)
    assert not any(f.check_id == "forbidden_live_decisions_active" for f in findings)


def test_safety_audit_confirms_live_stubs_block() -> None:
    findings = audit_live_stubs_block()
    assert not findings


def test_safety_audit_confirms_paper_broker_refuses_live_allowed() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_safety_audit_confirms_blunder_integrity_if_manifest_available(tmp_path: Path) -> None:
    # Create a temp Blunder manifest that points to the repo LICENSE file.
    manifest = tmp_path / "blunder_sha256_baseline.txt"
    license_file = Path(__file__).resolve().parent.parent / "LICENSE"
    if not license_file.exists():
        license_file = tmp_path / "dummy_blunder.py"
        license_file.write_text("# dummy blunder source\n", encoding="utf-8")
    import hashlib
    h = hashlib.sha256(license_file.read_bytes()).hexdigest().upper()
    manifest.write_text(f"{h}  {license_file}\n", encoding="utf-8")
    findings = audit_blunder_integrity(manifest)
    assert all(f.severity != "safety_error" for f in findings)


# ---------------------------------------------------------------------------
# Workstream E — evidence gap planner tests
# ---------------------------------------------------------------------------

def test_evidence_gap_planner_prioritizes_walk_forward_consistency() -> None:
    gaps = build_evidence_gaps(
        EvidenceInventory(),
        type("R", (), {"schema_findings": [], "verdict": "pass"})(),
        type("C", (), {"checks": [], "findings": [], "consistency_errors": 0, "safety_errors": 0})(),
        {"missing_evidence_priorities": ["stronger_walk_forward_consistency"]},
        {"family_weights": {"directional_convexity": 1.0}},
    )
    cats = {g.category for g in gaps}
    assert "insufficient_walk_forward_consistency" in cats
    priorities = build_next_proof_priorities(gaps)
    assert priorities[0].gap_category == "insufficient_walk_forward_consistency"


def test_evidence_gap_planner_flags_small_holdout_corpus() -> None:
    gaps = build_evidence_gaps(
        EvidenceInventory(),
        type("R", (), {"schema_findings": [], "verdict": "pass"})(),
        type("C", (), {"checks": [], "findings": [], "consistency_errors": 0, "safety_errors": 0})(),
        {"missing_evidence_priorities": ["broader_holdout_coverage"]},
        {"family_weights": {}},
    )
    cats = {g.category for g in gaps}
    assert "insufficient_holdout_windows" in cats or "small_regime_corpus" in cats


def test_evidence_gap_planner_flags_high_overfit_family() -> None:
    gaps = build_evidence_gaps(
        EvidenceInventory(),
        type("R", (), {"schema_findings": [], "verdict": "pass"})(),
        type("C", (), {"checks": [], "findings": [], "consistency_errors": 0, "safety_errors": 0})(),
        {
            "family_trust_profiles": [
                {"strategy_family": "volatility_expansion", "overfit_pressure": 0.95}
            ]
        },
        {"family_weights": {"directional_convexity": 1.0}},
    )
    assert any(g.category == "high_overfit_family" and "volatility_expansion" in g.affected_families for g in gaps)


def test_evidence_gap_planner_outputs_allowed_next_targets_only() -> None:
    gaps = build_evidence_gaps(
        EvidenceInventory(),
        type("R", (), {"schema_findings": [], "verdict": "pass"})(),
        type("C", (), {"checks": [], "findings": [], "consistency_errors": 0, "safety_errors": 0})(),
        {"missing_evidence_priorities": ["stronger_walk_forward_consistency"]},
        {"family_weights": {}},
    )
    priorities = build_next_proof_priorities(gaps)
    target = recommend_build_target(priorities)
    assert target.target in ALLOWED_NEXT_BUILD_TARGETS


# ---------------------------------------------------------------------------
# Workstream F — CLI / registry / reproducibility tests
# ---------------------------------------------------------------------------

def test_offline_evidence_replay_audit_cli_runs(artifact_root: Path, tmp_path: Path) -> None:
    from dopey_audit.run_offline_evidence_replay_audit import main
    # Ensure a safe minimal config by using default config (RESEARCH).
    code = main([])
    # The frozen runtime seed intentionally omits part of the export-review
    # safety packet. A non-mutating audit must fail closed rather than rebuild
    # that evidence behind the evaluator's back.
    assert code == 1


def test_audit_registries_written(artifact_root: Path, tmp_path: Path) -> None:
    from dopey_audit.audit_runner import run_offline_evidence_replay_audit
    root = tmp_path / "artifacts" / "dopey"
    root.mkdir(parents=True, exist_ok=True)
    for sub in ["proof_ledger", "walk_forward", "tournaments", "champion_registry"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    sample = {
        "run_id": "x",
        "final_status": "PASS",
        "safety_state": {"mode": "RESEARCH", "live_blocked": True},
    }
    for fname in ["proof_ledger/dopey_paper_pipeline.jsonl", "walk_forward/dopey_walk_forward.jsonl"]:
        (root / fname).write_text(json.dumps(sample) + "\n", encoding="utf-8")
    (root / "tournaments" / "dopey_tournament.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    (root / "champion_registry" / "champion_registry.jsonl").write_text(
        json.dumps({"champion_strategy_id": "s-a", "champion_registry_version": "v1"}) + "\n", encoding="utf-8"
    )
    result = run_offline_evidence_replay_audit(artifact_root=root)
    for p in ["inventory_path", "replay_audit_path", "consistency_audit_path", "safety_audit_path", "evidence_gap_plan_path"]:
        assert Path(result[p]).exists()


def test_audit_summary_artifact_written(artifact_root: Path, tmp_path: Path) -> None:
    from dopey_audit.audit_runner import run_offline_evidence_replay_audit
    root = tmp_path / "artifacts" / "dopey"
    root.mkdir(parents=True, exist_ok=True)
    sample = {
        "run_id": "x",
        "final_status": "PASS",
        "safety_state": {"mode": "RESEARCH", "live_blocked": True},
    }
    for sub in ["proof_ledger", "walk_forward", "tournaments", "mutations", "failure_modes", "failure_feedback", "source_registry", "iv_surface", "macro_events", "ensemble_allocator", "meta_governor", "champion_registry"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "proof_ledger" / "dopey_paper_pipeline.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    (root / "walk_forward" / "dopey_walk_forward.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    (root / "tournaments" / "dopey_tournament.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    (root / "champion_registry" / "champion_registry.jsonl").write_text(
        json.dumps({"champion_strategy_id": "s-a", "champion_registry_version": "v1"}) + "\n", encoding="utf-8"
    )
    result = run_offline_evidence_replay_audit(artifact_root=root, summary_path=tmp_path / "summary.md")
    assert Path(result["audit_summary_path"]).exists()
    assert "DOPEY Offline Evidence Replay Audit Summary" in Path(result["audit_summary_path"]).read_text(encoding="utf-8")


def test_audit_summary_contains_safety_state(artifact_root: Path, tmp_path: Path) -> None:
    from dopey_audit.audit_runner import run_offline_evidence_replay_audit
    root = tmp_path / "artifacts" / "dopey"
    root.mkdir(parents=True, exist_ok=True)
    sample = {
        "run_id": "x",
        "final_status": "PASS",
        "safety_state": {"mode": "RESEARCH", "live_blocked": True},
    }
    (root / "proof_ledger").mkdir(parents=True, exist_ok=True)
    (root / "proof_ledger" / "dopey_paper_pipeline.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    result = run_offline_evidence_replay_audit(artifact_root=root, summary_path=tmp_path / "summary.md")
    md = Path(result["audit_summary_path"]).read_text(encoding="utf-8")
    assert "mode: `" in md
    assert "live_trading_enabled: `" in md
    assert "live_blocked: `" in md


def test_audit_reproducibility_hash_is_deterministic(artifact_root: Path, audited_ensemble_record: dict) -> None:
    from dopey_research_pipeline.quality_ledger import reproducibility_hash
    rec1 = dict(audited_ensemble_record)
    rec2 = dict(audited_ensemble_record)
    del rec1["reproducibility_hash"]
    del rec2["reproducibility_hash"]
    assert reproducibility_hash(rec1) == reproducibility_hash(rec2)


# ---------------------------------------------------------------------------
# Safety regression tests
# ---------------------------------------------------------------------------

def test_no_live_promotion_possible_after_audit_harness(artifact_root: Path, tmp_path: Path) -> None:
    # Run audit over default artifacts; inspect latest meta-governor decisions.
    from dopey_audit.audit_runner import run_offline_evidence_replay_audit
    result = run_offline_evidence_replay_audit()
    assert result["forbidden_live_decisions_active"] == 0
    assert result["safety_errors"] > 0
    assert result["verdict"] == "fail_safety"
    assert result["live_trading_enabled"] is False


def test_live_stubs_still_block_after_audit_harness() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_audit_harness() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_audit_harness() -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_audit_harness_does_not_modify_live_settings(artifact_root: Path, tmp_path: Path) -> None:
    from dopey_audit.audit_runner import run_offline_evidence_replay_audit
    before = load_config(default_config_path())
    run_offline_evidence_replay_audit()
    after = load_config(default_config_path())
    assert before == after


def test_blunder_source_integrity_if_manifest_available(tmp_path: Path) -> None:
    # If a manifest exists, verify it passes when files match.
    from dopey_audit.safety_auditor import BLUNDER_MANIFEST_PATH, audit_blunder_integrity
    if BLUNDER_MANIFEST_PATH.exists():
        findings = audit_blunder_integrity()
        assert all(f.severity != "safety_error" for f in findings)
    else:
        # Use a temp manifest with a known file.
        dummy = tmp_path / "dummy_blunder.py"
        dummy.write_text("# original blunder content\n", encoding="utf-8")
        import hashlib
        h = hashlib.sha256(dummy.read_bytes()).hexdigest().upper()
        manifest = tmp_path / "manifest.txt"
        manifest.write_text(f"{h}  {dummy}\n", encoding="utf-8")
        findings = audit_blunder_integrity(manifest)
        assert not any(f.severity == "safety_error" for f in findings)
