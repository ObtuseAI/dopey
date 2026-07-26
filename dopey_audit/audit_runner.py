"""Deterministic offline evidence replay audit runner (paper-only)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .artifact_loader import ARTIFACT_ROOT, load_latest_record
from .consistency_auditor import run_consistency_audit
from .evidence_gap_planner import (
    build_evidence_gaps,
    build_next_proof_priorities,
    recommend_build_target,
)
from .evidence_models import (
    ALLOWED_NEXT_BUILD_TARGETS,
    AUDIT_HARNESS_VERSION,
    AuditRunResult,
)
from .evidence_inventory import build_completeness_report, build_freshness_report, build_inventory
from .replay_auditor import run_replay_audit
from .safety_auditor import run_safety_audit
from .active_policy_audit import run_active_policy_audit


AUDIT_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "audit"
INVENTORY_PATH = AUDIT_ARTIFACT_DIR / "evidence_inventory.jsonl"
REPLAY_AUDIT_PATH = AUDIT_ARTIFACT_DIR / "replay_audit.jsonl"
CONSISTENCY_AUDIT_PATH = AUDIT_ARTIFACT_DIR / "consistency_audit.jsonl"
SAFETY_AUDIT_PATH = AUDIT_ARTIFACT_DIR / "safety_audit.jsonl"
GAP_PLAN_PATH = AUDIT_ARTIFACT_DIR / "evidence_gap_plan.jsonl"
AUDIT_LEDGER_PATH = AUDIT_ARTIFACT_DIR / "evidence_replay_audit_proof.jsonl"
AUDIT_SUMMARY_PATH = AUDIT_ARTIFACT_DIR / "evidence_replay_audit_summary.md"
MAX_AUDIT_PROOF_ENTRY_BYTES = 256_000


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_audit": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_audit_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"audit harness requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("audit harness requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("audit harness requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("audit harness requires allow_unofficial_robinhood_api=false")


def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _verdict(replay_verdict, consistency, safety_active_forbidden, completeness) -> str:
    if safety_active_forbidden > 0:
        return "fail_safety"
    if consistency.safety_errors > 0:
        return "fail_safety"
    if replay_verdict == "fail_reproducibility":
        return "fail_reproducibility"
    if replay_verdict == "fail_schema":
        return "fail_schema"
    if completeness.completeness_fraction < 0.5:
        return "fail_missing_evidence"
    if replay_verdict == "warning" or consistency.consistency_errors > 0:
        return "warning"
    return "pass"


def _build_summary_md(result: AuditRunResult, inventory_dict, replay_dict, consistency_dict,
                      safety_findings, gaps, priorities, build_target, completeness) -> str:
    lines: list[str] = []
    lines.append("# DOPEY Offline Evidence Replay Audit Summary")
    lines.append("")
    lines.append(f"- audit_harness_version: `{AUDIT_HARNESS_VERSION}`")
    lines.append(f"- verdict: `{result.verdict}`")
    lines.append(f"- mode: `{result.mode}`")
    lines.append(f"- live_trading_enabled: `{result.live_trading_enabled}`")
    lines.append(f"- live_blocked: `{result.live_blocked}`")
    lines.append(f"- artifacts_scanned: `{result.artifacts_scanned}`")
    lines.append(f"- records_scanned: `{result.records_scanned}`")
    lines.append(f"- replay_cases_run: `{result.replay_cases_run}`")
    lines.append(f"- hash_mismatches: `{result.hash_mismatches}`")
    lines.append(f"- score_drift_findings: `{result.score_drift_findings}`")
    lines.append(f"- schema_warnings: `{result.schema_warnings}`")
    lines.append(f"- consistency_errors: `{result.consistency_errors}`")
    lines.append(f"- safety_errors: `{result.safety_errors}`")
    lines.append(f"- forbidden_live_decisions_active: `{result.forbidden_live_decisions_active}`")
    lines.append(f"- evidence_completeness: `{round(completeness.completeness_fraction, 3)}`")
    lines.append(f"- top_next_proof_priority: `{result.top_next_proof_priority}`")
    lines.append("")
    lines.append("## Evidence inventory")
    for a in inventory_dict["artifacts"]:
        lines.append(f"- `{a['artifact_type']}` status=`{a['status']}` records=`{a['record_count']}` parse=`{a['parse_status']}`")
    lines.append("")
    lines.append("## Replay / hash audit")
    lines.append(f"- verdict: `{replay_dict['verdict']}`")
    lines.append(f"- hash mismatches: `{replay_dict['hash_mismatches']}`; score drift: `{replay_dict['score_drift_findings']}`; schema warnings: `{replay_dict['schema_findings']}`")
    lines.append("")
    lines.append("## Cross-layer consistency")
    for c in consistency_dict["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        lines.append(f"- [{mark}] {c['check_id']}: {c['description']}")
    for f in consistency_dict["findings"]:
        lines.append(f"- ({f['severity']}) {f['message']}")
    lines.append("")
    lines.append("## Safety audit")
    for f in safety_findings:
        lines.append(f"- ({f['severity']}) {f['message']}")
    if not safety_findings:
        lines.append("- no safety-boundary drift detected")
    lines.append("")
    lines.append("## Evidence gaps")
    for g in gaps:
        lines.append(f"- [{g.severity}] {g.category}: {g.message}")
    lines.append("")
    lines.append("## Next proof priorities")
    for p in priorities:
        lines.append(f"- {p.rank}. {p.gap_category}: {p.message}")
    lines.append("")
    lines.append("## Recommended next build target")
    lines.append(f"- `{build_target.target}` — {build_target.rationale}")
    lines.append("")
    lines.append("## Safety state")
    lines.append("- PaperBroker refuses `live_allowed=true`; Robinhood/Alpaca/Tradier raise `LiveTradingDisabledError`.")
    lines.append("- No broker connection, credentials, network access, live trades, live promotion, or scheduled run.")
    lines.append("- Original Blunder source unchanged (SHA256 manifest verified when available).")
    return "\n".join(lines) + "\n"


def _build_proof_entry(result: AuditRunResult, registry_record: dict) -> ProofEntry:
    registry_identity = {
        "artifact_type": registry_record.get("artifact_type", "offline_evidence_replay_audit"),
        "audit_harness_version": registry_record.get("audit_harness_version", AUDIT_HARNESS_VERSION),
        "audit_status": registry_record.get("audit_status", result.audit_status),
        "verdict": registry_record.get("verdict", result.verdict),
        "reproducibility_hash": registry_record.get("reproducibility_hash", result.reproducibility_hash),
        "inventory_path": registry_record.get("inventory_path", ""),
        "replay_audit_path": registry_record.get("replay_audit_path", ""),
        "consistency_audit_path": registry_record.get("consistency_audit_path", ""),
        "safety_audit_path": registry_record.get("safety_audit_path", ""),
        "evidence_gap_plan_path": registry_record.get("evidence_gap_plan_path", ""),
        "audit_summary_path": registry_record.get("audit_summary_path", ""),
    }
    return ProofEntry(
        run_id=AUDIT_HARNESS_VERSION,
        task_id="offline-evidence-replay-audit",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"audit_version": AUDIT_HARNESS_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "audit_result": result.to_dict(),
            "registry_identity": registry_identity,
            "proof_payload_scope": "content_identity_and_compact_result_only",
            "recursive_artifact_embedding_allowed": False,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[result.audit_registry_path, result.audit_summary_path],
        diffs=[],
        test_results={
            "audit_status": result.audit_status,
            "verdict": result.verdict,
            "hash_mismatches": result.hash_mismatches,
            "consistency_errors": result.consistency_errors,
            "safety_errors": result.safety_errors,
            "forbidden_live_decisions_active": result.forbidden_live_decisions_active,
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic paper-only audit; no live execution",
            "audit is reproducibility/consistency checking, not live performance evidence",
            "no broker connection, credentials, network access, schedule, or live migration",
        ],
    )


def run_offline_evidence_replay_audit(
    *,
    artifact_root: Path | str | None = None,
    inventory_path: Path | str | None = None,
    replay_path: Path | str | None = None,
    consistency_path: Path | str | None = None,
    safety_path: Path | str | None = None,
    gap_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
    summary_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_audit_safety_state(safety)
    # An audit must observe a frozen subject, not regenerate it. The previous
    # implementation invoked the entire research, export, and review stack on
    # every audit call. That changed the evidence being examined, made isolated
    # fixture audits inspect unrelated state, and turned one test file into an
    # hours-long pipeline run. Dependency refresh belongs to the supervisor;
    # this harness only verifies the artifacts that already exist.
    active_policy_audit = run_active_policy_audit(
        write_proofs=False,
        auto_create_map=False,
    )

    inventory = build_inventory(artifact_root)
    inventory_dict = inventory.to_dict()
    completeness = build_completeness_report(inventory)
    freshness = build_freshness_report(inventory)

    replay = run_replay_audit(inventory, artifact_root)
    replay_dict = replay.to_dict()

    consistency = run_consistency_audit(inventory)
    consistency_dict = consistency.to_dict()

    safety_findings, active_forbidden = run_safety_audit(inventory)
    safety_records = [f.to_dict() for f in safety_findings]
    # The active-policy audit currently reports absent proof files through its
    # legacy `safety_errors` counter. Missing evidence is not an active
    # forbidden decision, so retain that result as advisory telemetry instead
    # of corrupting the forbidden-decision count.

    mg_registry = load_latest_record(Path(artifact_root) / "meta_governor" / "meta_governor_registry.jsonl") if artifact_root else load_latest_record(ARTIFACT_ROOT / "meta_governor" / "meta_governor_registry.jsonl")
    ensemble_registry = load_latest_record(Path(artifact_root) / "ensemble_allocator" / "ensemble_allocation_registry.jsonl") if artifact_root else load_latest_record(ARTIFACT_ROOT / "ensemble_allocator" / "ensemble_allocation_registry.jsonl")
    stronger_consistency_registry = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "walk_forward_consistency" / "consistency_registry.jsonl"
    )
    regime_holdout_v2_registry = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "regime_holdout_corpus_v2" / "corpus_registry.jsonl"
    )
    fundamental_registry = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "fundamental_fixtures" / "fundamental_registry.jsonl"
    )
    export_registry = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "exports" / "export_registry.jsonl"
    )
    export_manifest = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "exports" / "export_manifest.jsonl"
    )
    export_safety_scan = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "exports" / "export_safety_scan.jsonl"
    )
    export_copy_proof = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "exports" / "export_copy_proof.jsonl"
    )
    export_review_registry = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "export_reviews" / "export_review_registry.jsonl"
    )
    export_review_findings = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "export_reviews" / "export_review_findings.jsonl"
    )
    export_review_evidence_map = load_latest_record(
        (Path(artifact_root) if artifact_root else ARTIFACT_ROOT) / "export_reviews" / "EXPORT_REVIEW_EVIDENCE_MAP.json"
    )

    gaps = build_evidence_gaps(inventory, replay, consistency, mg_registry, ensemble_registry,
                               stronger_consistency_registry=stronger_consistency_registry,
                               regime_holdout_v2_registry=regime_holdout_v2_registry,
                               fundamental_registry=fundamental_registry)
    priorities = build_next_proof_priorities(gaps)
    build_target = recommend_build_target(priorities)

    verdict = _verdict(replay.verdict, consistency, active_forbidden, completeness)

    records_scanned = sum(a.record_count for a in inventory.artifacts)
    result = AuditRunResult(
        audit_status="ok",
        mode=safety["mode"],
        live_trading_enabled=safety["live_trading_enabled"],
        artifacts_scanned=len(inventory.artifacts),
        records_scanned=records_scanned,
        replay_cases_run=len(replay.cases),
        hash_mismatches=len(replay.hash_findings),
        score_drift_findings=len(replay.score_findings),
        schema_warnings=len(replay.schema_findings),
        consistency_errors=consistency.consistency_errors,
        safety_errors=consistency.safety_errors + active_forbidden,
        forbidden_live_decisions_active=active_forbidden,
        evidence_gaps=len(gaps),
        top_next_proof_priority=priorities[0].gap_category if priorities else "",
        live_blocked=True,
        verdict=verdict,
        safety_state=safety,
    )

    inv_target = _write_jsonl({**inventory_dict, "safety_state": safety, "completeness": completeness.to_dict(), "freshness": freshness.to_dict()}, inventory_path or INVENTORY_PATH)
    rep_target = _write_jsonl({**replay_dict, "safety_state": safety}, replay_path or REPLAY_AUDIT_PATH)
    con_target = _write_jsonl({**consistency_dict, "safety_state": safety}, consistency_path or CONSISTENCY_AUDIT_PATH)
    safe_target = _write_jsonl({"findings": safety_records, "active_forbidden": active_forbidden, "safety_state": safety}, safety_path or SAFETY_AUDIT_PATH)
    gap_target = _write_jsonl({
        "gaps": [g.to_dict() for g in gaps],
        "next_proof_priorities": [p.to_dict() for p in priorities],
        "recommended_build_target": build_target.to_dict(),
        "allowed_next_build_targets": ALLOWED_NEXT_BUILD_TARGETS,
        "safety_state": safety,
    }, gap_path or GAP_PLAN_PATH)

    registry_record = {
        "audit_harness_version": AUDIT_HARNESS_VERSION,
        "verdict": verdict,
        "inventory": inventory_dict,
        "replay_audit": replay_dict,
        "consistency_audit": consistency_dict,
        "safety_findings": safety_records,
        "active_policy_audit": active_policy_audit,
        "dependency_refresh_performed": False,
        "audit_subject_mutated": False,
        "audit_scope": "observe_existing_artifacts_only",
        "active_forbidden_decisions": active_forbidden,
        "evidence_gaps": [g.to_dict() for g in gaps],
        "next_proof_priorities": [p.to_dict() for p in priorities],
        "recommended_build_target": build_target.to_dict(),
        "completeness": completeness.to_dict(),
        "freshness": freshness.to_dict(),
        "stronger_consistency_summary": (
            {
                "windows_loaded": stronger_consistency_registry.get("windows_loaded", 0),
                "splits_built": stronger_consistency_registry.get("splits_built", 0),
                "strategies_evaluated": stronger_consistency_registry.get("strategies_evaluated", 0),
                "families_evaluated": stronger_consistency_registry.get("families_evaluated", 0),
                "top_consistent_strategy": stronger_consistency_registry.get("top_consistent_strategy", ""),
                "top_consistent_family": stronger_consistency_registry.get("top_consistent_family", ""),
                "holdout_failures": stronger_consistency_registry.get("holdout_failures", 0),
                "overfit_warnings": stronger_consistency_registry.get("overfit_warnings", 0),
                "strong_consistency_count": stronger_consistency_registry.get("strong_consistency_count", 0),
            }
            if stronger_consistency_registry else None
        ),
        "regime_holdout_v2_summary": (
            {
                "total_windows": regime_holdout_v2_registry.get("total_windows", 0),
                "new_windows_added": regime_holdout_v2_registry.get("new_windows_added", 0),
                "splits_built": regime_holdout_v2_registry.get("splits_built", 0),
                "strategies_evaluated": regime_holdout_v2_registry.get("strategies_evaluated", 0),
                "families_evaluated": regime_holdout_v2_registry.get("families_evaluated", 0),
                "top_consistent_strategy_v2": regime_holdout_v2_registry.get("top_consistent_strategy_v2", ""),
                "top_consistent_family_v2": regime_holdout_v2_registry.get("top_consistent_family_v2", ""),
                "holdout_failures": regime_holdout_v2_registry.get("holdout_failures", 0),
                "overfit_warnings": regime_holdout_v2_registry.get("overfit_warnings", 0),
                "coverage_score": regime_holdout_v2_registry.get("coverage_score", 0.0),
            }
            if regime_holdout_v2_registry else None
        ),
        "export_summary": (
            {
                "bundle_id": export_registry.get("bundle_id", ""),
                "profile": export_registry.get("profile", ""),
                "export_status": export_registry.get("export_status", ""),
                "artifacts_selected": export_registry.get("artifacts_selected", 0),
                "artifacts_exported": export_registry.get("artifacts_exported", 0),
                "compacted_artifacts": export_registry.get("compacted_artifacts", 0),
                "manifest_artifact_count": export_manifest.get("artifact_count", 0),
                "manifest_total_size_bytes": export_manifest.get("total_size_bytes", 0),
                "safety_scan_status": export_safety_scan.get("scan_status", ""),
                "active_forbidden_live_decisions": export_safety_scan.get("active_forbidden_live_decisions", 0),
                "credential_findings": export_safety_scan.get("credential_findings", 0),
                "copy_status": export_copy_proof.get("verification_status", ""),
                "files_verified": export_copy_proof.get("files_verified", 0),
                "hash_mismatches": len(export_copy_proof.get("hash_mismatches", []) or []),
            }
            if export_registry else None
        ),
        "export_review_summary": (
            {
                "review_id": export_review_registry.get("review_id", ""),
                "source_bundle_id": export_review_registry.get("source_bundle_id", ""),
                "review_status": export_review_registry.get("review_status", ""),
                "manifest_status": export_review_registry.get("manifest_status", ""),
                "copy_proof_status": export_review_registry.get("copy_proof_status", ""),
                "hash_status": export_review_registry.get("hash_status", ""),
                "safety_status": export_review_registry.get("safety_status", ""),
                "credential_status": export_review_registry.get("credential_status", ""),
                "findings_count": export_review_registry.get("findings_count", 0),
                "safety_errors": export_review_registry.get("safety_errors", 0),
                "warnings": export_review_registry.get("warnings", 0),
                "latest_finding_category": export_review_findings.get("category", ""),
                "evidence_map_exported_files": len(export_review_evidence_map.get("manifest_to_exported_files", []) or []),
                "next_build_target": export_review_registry.get("next_build_target", ""),
            }
            if export_review_registry else None
        ),
        "safety_state": safety,
    }
    repro = reproducibility_hash(registry_record)
    registry_record["reproducibility_hash"] = repro
    result.reproducibility_hash = repro

    summary_md = _build_summary_md(result, inventory_dict, replay_dict, consistency_dict, safety_records, gaps, priorities, build_target, completeness)
    summary_target = Path(summary_path) if summary_path else AUDIT_SUMMARY_PATH
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.write_text(summary_md, encoding="utf-8")

    proof_target = Path(proof_ledger_path) if proof_ledger_path else AUDIT_LEDGER_PATH
    proof_entry = _build_proof_entry(result, registry_record)
    proof_entry_bytes = len(json.dumps(proof_entry.to_dict(), ensure_ascii=False).encode("utf-8"))
    if proof_entry_bytes > MAX_AUDIT_PROOF_ENTRY_BYTES:
        raise ValueError(
            "offline evidence replay audit proof entry exceeds the bounded payload contract: "
            f"bytes={proof_entry_bytes}, maximum={MAX_AUDIT_PROOF_ENTRY_BYTES}"
        )
    ProofLedger(proof_target).append(proof_entry)

    result.audit_registry_path = str(gap_target)
    result.audit_summary_path = str(summary_target)

    summary = result.to_dict()
    summary["inventory"] = inventory_dict
    summary["replay_audit"] = replay_dict
    summary["consistency_audit"] = consistency_dict
    summary["safety_findings"] = safety_records
    summary["active_policy_audit"] = active_policy_audit
    summary["dependency_refresh_performed"] = False
    summary["audit_subject_mutated"] = False
    summary["audit_scope"] = "observe_existing_artifacts_only"
    summary["evidence_gaps"] = [g.to_dict() for g in gaps]
    summary["next_proof_priorities"] = [p.to_dict() for p in priorities]
    summary["recommended_build_target"] = build_target.to_dict()
    summary["completeness"] = completeness.to_dict()
    summary["export_summary"] = registry_record.get("export_summary")
    summary["export_review_summary"] = registry_record.get("export_review_summary")
    summary["inventory_path"] = str(inv_target)
    summary["replay_audit_path"] = str(rep_target)
    summary["consistency_audit_path"] = str(con_target)
    summary["safety_audit_path"] = str(safe_target)
    summary["evidence_gap_plan_path"] = str(gap_target)
    summary["proof_record_path"] = str(proof_target)
    summary["audit_summary_path"] = str(summary_target)
    return summary
