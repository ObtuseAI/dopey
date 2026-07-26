"""Cross-layer consistency audit for the offline evidence replay harness."""
from __future__ import annotations

from pathlib import Path

from .artifact_loader import load_latest_record, load_records
from .evidence_models import (
    CrossLayerConsistencyReport,
    ConsistencyCheck,
    ConsistencyFinding,
    EvidenceInventory,
)


def _check(check_id: str, description: str, passed: bool) -> ConsistencyCheck:
    return ConsistencyCheck(check_id=check_id, description=description, passed=passed)


def check_champion_tournament_link(champion_record: dict, ensemble_record: dict) -> tuple[ConsistencyCheck, ConsistencyFinding | None]:
    champ = str(champion_record.get("champion_strategy_id", ""))
    tournament_champ = str(ensemble_record.get("source_tournament_champion", ""))
    passed = bool(champ) and bool(tournament_champ) and champ == tournament_champ
    finding = None
    if not passed:
        finding = ConsistencyFinding(
            check_id="champion_tournament_link",
            severity="warning" if (champ or tournament_champ) else "error",
            message=f"champion registry champion '{champ}' diverges from ensemble/tournament champion '{tournament_champ}'",
            referenced_ids=[champ, tournament_champ],
        )
    return _check("champion_tournament_link", "champion registry champion matches tournament champion", passed), finding


def check_champion_divergence(champion_id: str, expected_id: str, explanation: str = "") -> ConsistencyFinding | None:
    """Flag an unexplained champion divergence. Returns a finding if divergence is unexplained."""
    if not champion_id or not expected_id:
        return None
    if champion_id == expected_id:
        return None
    if explanation:
        return None  # explained divergence is allowed
    return ConsistencyFinding(
        check_id="champion_tournament_link",
        severity="warning",
        message=f"unexplained champion divergence: '{champion_id}' vs expected '{expected_id}'",
        referenced_ids=[champion_id, expected_id],
    )


def check_mutation_champion_link(mutation_record: dict) -> tuple[ConsistencyCheck, ConsistencyFinding | None]:
    best = str(mutation_record.get("best_mutated_strategy_id", ""))
    ranking_ids = {str(row.get("strategy_id", "")) for row in mutation_record.get("ranking", [])}
    passed = bool(best) and best in ranking_ids
    finding = None if passed else ConsistencyFinding(
        check_id="mutation_champion_link",
        severity="error",
        message=f"mutation champion '{best}' not found in mutation ranking",
        referenced_ids=[best],
    )
    return _check("mutation_champion_link", "mutation champion appears in mutation registry ranking", passed), finding


def check_meta_governor_decision_evidence(mg_record: dict) -> tuple[ConsistencyCheck, ConsistencyFinding | None]:
    decisions = mg_record.get("decisions", [])
    profiles = {str(p.get("strategy_id", "")) for p in mg_record.get("strategy_proof_profiles", [])}
    missing = [str(d.get("strategy_id", "")) for d in decisions if str(d.get("strategy_id", "")) not in profiles]
    passed = not missing
    finding = None if passed else ConsistencyFinding(
        check_id="meta_governor_decision_evidence",
        severity="error",
        message="meta-governor decisions reference strategies without proof profiles",
        referenced_ids=missing,
    )
    return _check("meta_governor_decision_evidence", "meta-governor decisions have supporting proof profiles", passed), finding


def check_strategy_references_exist(referenced_ids: list[str], known_ids: set[str]) -> tuple[ConsistencyCheck, ConsistencyFinding | None]:
    known = {str(k) for k in known_ids}
    missing = [rid for rid in referenced_ids if rid and rid not in known]
    passed = not missing
    finding = None if passed else ConsistencyFinding(
        check_id="strategy_references_exist",
        severity="error",
        message="referenced strategy ids not found in known genome/mutation records",
        referenced_ids=missing,
    )
    return _check("strategy_references_exist", "all referenced strategy ids exist in known records", passed), finding


def check_forbidden_live_decisions_absent(records_by_type: dict[str, list[dict]]) -> tuple[ConsistencyCheck, list[ConsistencyFinding]]:
    from .evidence_models import FORBIDDEN_LIVE_TOKENS
    findings: list[ConsistencyFinding] = []
    for artifact_type, records in records_by_type.items():
        for record in records:
            decisions = record.get("decisions", [])
            if not isinstance(decisions, list):
                continue
            for decision in decisions:
                token = str(decision.get("decision", "")) if isinstance(decision, dict) else ""
                if token in FORBIDDEN_LIVE_TOKENS:
                    findings.append(ConsistencyFinding(
                        check_id="forbidden_live_decisions_absent",
                        severity="safety_error",
                        message=f"forbidden live decision '{token}' in {artifact_type}",
                        referenced_ids=[],
                    ))
    passed = not findings
    return _check("forbidden_live_decisions_absent", "no forbidden live decisions appear as active decisions", passed), findings


def run_consistency_audit(inventory: EvidenceInventory) -> CrossLayerConsistencyReport:
    """Run all cross-layer consistency checks over latest records."""
    checks: list[ConsistencyCheck] = []
    findings: list[ConsistencyFinding] = []

    def latest(artifact_type: str) -> dict:
        artifact = next((a for a in inventory.artifacts if a.artifact_type == artifact_type), None)
        return load_latest_record(artifact.path) if artifact and artifact.status in {"present", "stale"} else {}

    champion = latest("champion_registry")
    ensemble = latest("ensemble_registry")
    mutation = latest("mutation_registry")
    mg = latest("meta_governor_registry")

    chk, f = check_champion_tournament_link(champion, ensemble)
    checks.append(chk)
    if f:
        findings.append(f)

    chk, f = check_mutation_champion_link(mutation)
    checks.append(chk)
    if f:
        findings.append(f)

    chk, f = check_meta_governor_decision_evidence(mg)
    checks.append(chk)
    if f:
        findings.append(f)

    # known strategy id set: champion family ranking + mutation ranking + ensemble candidates + mg profiles
    known: set[str] = set()
    for row in champion.get("family_ranking", []):
        known.add(str(row.get("strategy_id", "")))
    for row in mutation.get("ranking", []):
        known.add(str(row.get("strategy_id", "")))
    for row in ensemble.get("candidates", []):
        known.add(str(row.get("strategy_id", "")))
    known.add(str(champion.get("champion_strategy_id", "")))
    known.add(str(champion.get("runner_up_strategy_id", "")))
    known.discard("")

    referenced: list[str] = []
    for d in mg.get("decisions", []):
        referenced.append(str(d.get("strategy_id", "")))
    reporting_cards = []
    reporting_artifact = next((a for a in inventory.artifacts if a.artifact_type == "strategy_report_cards"), None)
    if reporting_artifact and reporting_artifact.status in {"present", "stale"}:
        reporting_cards = load_records(reporting_artifact.path)
        for card in reporting_cards:
            referenced.append(str(card.get("strategy_id", "")))
    chk, f = check_strategy_references_exist(referenced, known)
    checks.append(chk)
    if f:
        findings.append(f)

    reporting_safe = True
    unsafe_reporting: list[str] = []
    for card in reporting_cards:
        if card.get("paper_only") is not True or card.get("live_allowed") is not False:
            reporting_safe = False
            unsafe_reporting.append(str(card.get("strategy_id", "")))
    checks.append(_check("reporting_artifacts_paper_only", "reporting strategy cards are paper-only and live-blocked", reporting_safe))
    if not reporting_safe:
        findings.append(ConsistencyFinding(
            check_id="reporting_artifacts_paper_only",
            severity="safety_error",
            message="reporting strategy cards contain non-paper or live-allowed state",
            referenced_ids=unsafe_reporting,
        ))

    export_registry = latest("export_registry")
    export_manifest = latest("export_manifest")
    export_safety_scan = latest("export_safety_scan")
    export_copy_proof = latest("export_copy_proof")
    export_manifest_safe = bool(export_manifest.get("bundle_id")) and export_manifest.get("safety_state", {}).get("live_blocked") is True
    checks.append(_check("export_manifest_parses", "export manifest parses and records live-blocked safety state", export_manifest_safe))
    if not export_manifest_safe:
        findings.append(ConsistencyFinding(
            check_id="export_manifest_parses",
            severity="error",
            message="export manifest missing bundle id or live-blocked safety state",
            referenced_ids=[str(export_manifest.get("bundle_id", ""))],
        ))

    export_scan_safe = int(export_safety_scan.get("active_forbidden_live_decisions", 0)) == 0 and export_safety_scan.get("verification_blocked") is not True
    checks.append(_check("export_safety_scan_passes", "export safety scan has no active forbidden live decisions", export_scan_safe))
    if not export_scan_safe:
        findings.append(ConsistencyFinding(
            check_id="export_safety_scan_passes",
            severity="safety_error",
            message="export safety scan reports active forbidden content or blocked verification",
            referenced_ids=[str(export_safety_scan.get("bundle_id", ""))],
        ))

    copy_status = str(export_copy_proof.get("verification_status", ""))
    copy_proof_ok = copy_status in {"verified", "skipped_unavailable"}
    checks.append(_check("export_copy_proof_valid", "export copy proof is verified or cleanly skipped", copy_proof_ok))
    if not copy_proof_ok:
        findings.append(ConsistencyFinding(
            check_id="export_copy_proof_valid",
            severity="error",
            message=f"export copy proof status is {copy_status}",
            referenced_ids=[str(export_copy_proof.get("bundle_id", ""))],
        ))

    registry_links_manifest = bool(export_registry.get("bundle_id")) and export_registry.get("bundle_id") == export_manifest.get("bundle_id")
    checks.append(_check("export_registry_links_manifest", "export registry bundle id matches manifest bundle id", registry_links_manifest))
    if not registry_links_manifest:
        findings.append(ConsistencyFinding(
            check_id="export_registry_links_manifest",
            severity="error",
            message="export registry and manifest bundle ids diverge",
            referenced_ids=[str(export_registry.get("bundle_id", "")), str(export_manifest.get("bundle_id", ""))],
        ))

    export_review_registry = latest("export_review_registry")
    export_review_proof = latest("export_review_proof")
    export_review_evidence_map = latest("export_review_evidence_map")
    export_review_findings_artifact = next((a for a in inventory.artifacts if a.artifact_type == "export_review_findings"), None)
    export_review_findings = (
        load_records(export_review_findings_artifact.path)
        if export_review_findings_artifact and export_review_findings_artifact.status in {"present", "stale"}
        else []
    )
    review_checklist_artifact = next((a for a in inventory.artifacts if a.artifact_type == "export_review_checklist"), None)

    review_artifacts_present = bool(export_review_registry or export_review_evidence_map or export_review_proof)
    if review_artifacts_present:
        review_source = str(export_review_registry.get("source_bundle_id", ""))
        latest_bundle = str(export_manifest.get("bundle_id", ""))
        review_registry_ok = bool(review_source) and review_source == latest_bundle
        checks.append(_check("export_review_registry_links_source_bundle", "export review registry references the latest source bundle", review_registry_ok))
        if not review_registry_ok:
            registry_severity = "warning" if review_source and latest_bundle else "error"
            findings.append(ConsistencyFinding(
                check_id="export_review_registry_links_source_bundle",
                severity=registry_severity,
                message="export review registry is stale relative to the latest export bundle",
                referenced_ids=[review_source, latest_bundle],
            ))

        checklist_safe = False
        if review_checklist_artifact and Path(review_checklist_artifact.path).exists():
            checklist_text = Path(review_checklist_artifact.path).read_text(encoding="utf-8", errors="replace")
            checklist_safe = "mode=RESEARCH" in checklist_text and "live_trading_enabled=false" in checklist_text and "live_blocked" in checklist_text
        checks.append(_check("export_review_checklist_includes_safety_state", "export review checklist includes research/live-blocked safety state", checklist_safe))
        if not checklist_safe:
            findings.append(ConsistencyFinding(
                check_id="export_review_checklist_includes_safety_state",
                severity="safety_error",
                message="export review checklist is missing required safety state text",
                referenced_ids=[],
            ))

        evidence_map_ok = bool(export_review_evidence_map.get("source_bundle_id")) and isinstance(export_review_evidence_map.get("manifest_to_exported_files"), list)
        evidence_map_marked = all("exists" in item for item in export_review_evidence_map.get("manifest_to_exported_files", []) or [])
        checks.append(_check("export_review_evidence_map_valid", "export review evidence map parses and marks artifact references", evidence_map_ok and evidence_map_marked))
        if not (evidence_map_ok and evidence_map_marked):
            findings.append(ConsistencyFinding(
                check_id="export_review_evidence_map_valid",
                severity="error",
                message="export review evidence map is missing source bundle id or reference existence markers",
                referenced_ids=[str(export_review_evidence_map.get("source_bundle_id", ""))],
            ))

        review_findings_safe = all(str(record.get("severity", "")) != "safety_error" for record in export_review_findings)
        checks.append(_check("export_review_findings_have_no_safety_errors", "export review findings include no active safety errors", review_findings_safe))
        if not review_findings_safe:
            findings.append(ConsistencyFinding(
                check_id="export_review_findings_have_no_safety_errors",
                severity="safety_error",
                message="export review findings contain a safety_error record",
                referenced_ids=[],
            ))

        proof_source = export_review_proof.get("execution_result", {}).get("source_bundle_id", "") if isinstance(export_review_proof.get("execution_result"), dict) else ""
        review_proof_ok = bool(proof_source) and proof_source == latest_bundle
        checks.append(_check("export_review_proof_references_source_bundle", "export review proof references source bundle id", review_proof_ok))
        if not review_proof_ok:
            proof_severity = "warning" if proof_source and latest_bundle else "error"
            findings.append(ConsistencyFinding(
                check_id="export_review_proof_references_source_bundle",
                severity=proof_severity,
                message="export review proof is stale relative to the latest export bundle",
                referenced_ids=[str(proof_source), latest_bundle],
            ))

    # forbidden live decisions across all present registries/ledgers
    records_by_type: dict[str, list[dict]] = {}
    for artifact in inventory.artifacts:
        if artifact.status in {"present", "stale"}:
            records_by_type[artifact.artifact_type] = load_records(artifact.path)
    chk, flist = check_forbidden_live_decisions_absent(records_by_type)
    checks.append(chk)
    findings.extend(flist)

    consistency_errors = sum(1 for f in findings if f.severity == "error")
    safety_errors = sum(1 for f in findings if f.severity == "safety_error")
    return CrossLayerConsistencyReport(checks=checks, findings=findings, consistency_errors=consistency_errors, safety_errors=safety_errors)
