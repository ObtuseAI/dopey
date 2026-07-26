"""Evidence gap planner + next-proof priority planner for the audit harness."""
from __future__ import annotations

from .evidence_models import (
    ALLOWED_NEXT_BUILD_TARGETS,
    AuditRecommendedBuildTarget,
    CrossLayerConsistencyReport,
    EvidenceGap,
    EvidenceInventory,
    NextProofPriority,
    ReplayAuditResult,
)


# Gap category -> default severity.
GAP_CATEGORIES = {
    "insufficient_walk_forward_consistency": "warning",
    "small_regime_corpus": "info",
    "missing_source_backed_data": "info",
    "deterministic_fixture_only_limitation": "info",
    "weak_cross_family_evidence": "warning",
    "high_overfit_family": "warning",
    "low_liquidity_robustness": "warning",
    "iv_surface_trap_exposure": "warning",
    "macro_contradiction_pressure": "warning",
    "insufficient_holdout_windows": "warning",
    "missing_audit_hash": "error",
    "stale_artifact": "warning",
    "schema_drift": "warning",
    "missing_proof_ledger_record": "error",
    "missing_safety_proof": "error",
    "weak_stronger_consistency_evidence": "warning",
    "consistency_evidence_missing": "warning",
    "weak_regime_holdout_corpus_v2_evidence": "warning",
    "regime_holdout_corpus_v2_missing": "warning",
    "weak_sector_peer_fundamental_evidence": "warning",
    "sector_peer_fundamental_missing": "warning",
}


def _gap(gap_id: str, category: str, message: str, families=None) -> EvidenceGap:
    return EvidenceGap(
        gap_id=gap_id,
        category=category,
        severity=GAP_CATEGORIES.get(category, "warning"),
        message=message,
        affected_families=families or [],
    )


def build_evidence_gaps(inventory: EvidenceInventory, replay: ReplayAuditResult,
                        consistency: CrossLayerConsistencyReport,
                        mg_registry: dict, ensemble_registry: dict,
                        stronger_consistency_registry: dict | None = None,
                        regime_holdout_v2_registry: dict | None = None,
                        fundamental_registry: dict | None = None) -> list[EvidenceGap]:
    gaps: list[EvidenceGap] = []

    # Stale / schema / missing artifacts
    for artifact in inventory.artifacts:
        if artifact.status == "stale":
            gaps.append(_gap(f"gap-stale-{artifact.artifact_type}", "stale_artifact",
                             f"{artifact.artifact_type} missing required fields: {artifact.missing_required_fields}"))
        if artifact.status == "missing" and artifact.artifact_type.endswith("_ledger"):
            gaps.append(_gap(f"gap-missing-ledger-{artifact.artifact_type}", "missing_proof_ledger_record",
                             f"proof ledger missing: {artifact.artifact_type}"))
    for sf in replay.schema_findings:
        gaps.append(_gap(f"gap-schema-{sf.artifact_type}", "schema_drift",
                         f"schema drift in {sf.artifact_type}: {sf.missing_fields}"))

    # Deterministic fixture-only limitation is always noted.
    gaps.append(_gap("gap-fixture-only", "deterministic_fixture_only_limitation",
                     "all evidence is deterministic fixture math, not live performance evidence"))

    # Missing source-backed data (offline sources only).
    gaps.append(_gap("gap-source-data", "missing_source_backed_data",
                     "network/credential data sources remain deferred; only offline internal sources active"))

    # Walk-forward consistency priority from meta-governor missing-evidence priorities.
    mg_missing = mg_registry.get("missing_evidence_priorities", []) if mg_registry else []
    if any("walk_forward" in m for m in mg_missing):
        gaps.append(_gap("gap-wf-consistency", "insufficient_walk_forward_consistency",
                         "non-directional families need stronger walk-forward consistency"))
    if any("holdout" in m.lower() for m in mg_missing) or any("coverage" in m for m in mg_missing):
        gaps.append(_gap("gap-holdout-corpus", "insufficient_holdout_windows",
                         "broader regime/holdout coverage required for cross-family promotion"))

    # Stronger walk-forward consistency: if the registry is missing, log an evidence gap;
    # if present, summarize its top holdout failures and overfit warnings as warnings.
    if not stronger_consistency_registry:
        gaps.append(_gap("gap-stronger-consistency-missing", "consistency_evidence_missing",
                         "stronger walk-forward consistency registry is missing"))
    else:
        holdout_failures = int(stronger_consistency_registry.get("holdout_failures", 0))
        overfit_warnings = int(stronger_consistency_registry.get("overfit_warnings", 0))
        if holdout_failures > 0 or overfit_warnings > 0:
            gaps.append(_gap("gap-stronger-consistency-weak", "weak_stronger_consistency_evidence",
                             f"stronger walk-forward consistency: {holdout_failures} holdout failures, {overfit_warnings} overfit warnings"))

    # Regime/holdout corpus v2: if the registry is missing, log an evidence gap; if
    # present, summarize its top holdout failures and overfit warnings.
    if not regime_holdout_v2_registry:
        gaps.append(_gap("gap-regime-holdout-v2-missing", "regime_holdout_corpus_v2_missing",
                         "regime/holdout corpus v2 registry is missing"))
    else:
        v2_holdout_failures = int(regime_holdout_v2_registry.get("holdout_failures", 0))
        v2_overfit_warnings = int(regime_holdout_v2_registry.get("overfit_warnings", 0))
        v2_total = int(regime_holdout_v2_registry.get("total_windows", 0))
        if v2_holdout_failures > 0 or v2_overfit_warnings > 0:
            gaps.append(_gap("gap-regime-holdout-v2-weak", "weak_regime_holdout_corpus_v2_evidence",
                             f"regime/holdout corpus v2: {v2_holdout_failures} holdout failures, {v2_overfit_warnings} overfit warnings"))
        if v2_total < 16:
            gaps.append(_gap("gap-regime-holdout-v2-thin", "regime_holdout_corpus_v2_missing",
                             f"regime/holdout corpus v2 has only {v2_total} windows; expand further"))

    # Sector/peer/fundamental coverage gap
    if not fundamental_registry:
        gaps.append(_gap("gap-fundamental-missing", "sector_peer_fundamental_missing",
                         "sector/peer/fundamental fixture registry is missing"))
    else:
        coverage_categories = dict(fundamental_registry.get("coverage", {}).get("categories", {}) or {})
        missing_categories = list(fundamental_registry.get("coverage", {}).get("missing_categories", []) or [])
        if missing_categories:
            gaps.append(_gap("gap-fundamental-weak", "weak_sector_peer_fundamental_evidence",
                             f"sector/peer/fundamental coverage missing: {missing_categories}"))
        low_categories = [category for category, score in coverage_categories.items() if float(score) < 0.50]
        if low_categories:
            gaps.append(_gap("gap-fundamental-low-coverage", "weak_sector_peer_fundamental_evidence",
                             f"sector/peer/fundamental coverage low: {low_categories}"))

    # Overfit + family pressure from meta-governor family trust profiles.
    family_profiles = mg_registry.get("family_trust_profiles", []) if mg_registry else []
    high_overfit_fams = [p["strategy_family"] for p in family_profiles if float(p.get("overfit_pressure", 0)) >= 0.9]
    if high_overfit_fams:
        gaps.append(_gap("gap-high-overfit", "high_overfit_family",
                         "high overfit pressure in families blocks promotion", high_overfit_fams))
    low_liq_fams = [p["strategy_family"] for p in family_profiles if float(p.get("liquidity_pressure", 0)) >= 0.6]
    if low_liq_fams:
        gaps.append(_gap("gap-low-liquidity", "low_liquidity_robustness",
                         "low liquidity robustness pressures families", low_liq_fams))
    macro_pressure_fams = [p["strategy_family"] for p in family_profiles if float(p.get("macro_pressure", 0)) >= 0.6]
    if macro_pressure_fams:
        gaps.append(_gap("gap-macro-pressure", "macro_contradiction_pressure",
                         "macro contradiction pressure affects families", macro_pressure_fams))

    # Weak cross-family evidence if only one family carries ensemble weight.
    family_weights = ensemble_registry.get("family_weights", {}) if ensemble_registry else {}
    weighted_families = [f for f, w in family_weights.items() if float(w) > 0.0]
    if len(weighted_families) <= 1:
        gaps.append(_gap("gap-cross-family", "weak_cross_family_evidence",
                         "ensemble concentrates on a single family; cross-family evidence weak", weighted_families))

    # Deduplicate by gap_id (keep first).
    seen: set[str] = set()
    deduped: list[EvidenceGap] = []
    for g in gaps:
        if g.gap_id in seen:
            continue
        seen.add(g.gap_id)
        deduped.append(g)
    # Sort by severity rank then category.
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    deduped.sort(key=lambda g: (severity_rank.get(g.severity, 3), g.category, g.gap_id))
    return deduped


# Category -> recommended next build target (must be in ALLOWED_NEXT_BUILD_TARGETS).
_CATEGORY_TARGET = {
    "insufficient_walk_forward_consistency": "stronger_walk_forward_consistency_expansion",
    "insufficient_holdout_windows": "larger_regime_holdout_corpus",
    "small_regime_corpus": "larger_regime_holdout_corpus",
    "weak_cross_family_evidence": "tournament_performance_reporting_dashboard_artifacts",
    "high_overfit_family": "stronger_walk_forward_consistency_expansion",
    "low_liquidity_robustness": "deterministic_sector_peer_fundamental_fixture_expansion",
    "schema_drift": "artifact_compaction_export_verifier",
    "stale_artifact": "artifact_compaction_export_verifier",
    "missing_audit_hash": "artifact_compaction_export_verifier",
    "weak_sector_peer_fundamental_evidence": "deterministic_sector_peer_fundamental_fixture_expansion",
    "sector_peer_fundamental_missing": "deterministic_sector_peer_fundamental_fixture_expansion",
}


def build_next_proof_priorities(gaps: list[EvidenceGap]) -> list[NextProofPriority]:
    """Rank next-proof priorities; walk-forward consistency is always prioritized first."""
    priorities: list[NextProofPriority] = []
    rank = 1
    # Always rank walk-forward consistency first when present.
    wf = [g for g in gaps if g.category == "insufficient_walk_forward_consistency"]
    ordered = wf + [g for g in gaps if g.category != "insufficient_walk_forward_consistency" and g.severity in {"error", "warning"}]
    seen_cat: set[str] = set()
    for gap in ordered:
        if gap.category in seen_cat:
            continue
        seen_cat.add(gap.category)
        priorities.append(NextProofPriority(
            priority_id=f"priority-{rank:02d}-{gap.category}",
            gap_category=gap.category,
            rank=rank,
            message=gap.message,
        ))
        rank += 1
    return priorities


def recommend_build_target(priorities: list[NextProofPriority]) -> AuditRecommendedBuildTarget:
    for priority in priorities:
        target = _CATEGORY_TARGET.get(priority.gap_category)
        if target and target in ALLOWED_NEXT_BUILD_TARGETS:
            return AuditRecommendedBuildTarget(target=target, rationale=f"addresses top gap: {priority.gap_category}")
    return AuditRecommendedBuildTarget(
        target=ALLOWED_NEXT_BUILD_TARGETS[0],
        rationale="default next build target",
    )
