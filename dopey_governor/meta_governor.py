"""Deterministic offline meta-governor orchestrator for DOPEY.

Consumes all current DOPEY evidence layers and produces deterministic paper-only governance
decisions: proof profiles, family/regime trust maps, and promotion/demotion/quarantine
decisions. This is NOT live approval, NOT broker execution, and NOT real performance
evidence. Live promotion remains impossible.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .family_trust_map import (
    FAMILY_TRUST_MAP_VERSION,
    build_family_trust_profiles,
    build_regime_trust_profiles,
)
from .meta_governor_models import (
    ALLOWED_TIERS,
    FORBIDDEN_LIVE_TIERS,
    META_GOVERNOR_VERSION,
    MetaGovernorDecision,
    MetaGovernorRunResult,
)
from .proof_evidence_loader import EVIDENCE_PATHS, EvidenceBundle, load_evidence_bundle
from .proof_quality import (
    PROOF_QUALITY_VERSION,
    build_strategy_proof_profiles,
    score_evidence_layers,
    score_proof_quality,
)
from .promotion_policy import (
    PROMOTION_POLICY_VERSION,
    decide_meta_governor,
    forbidden_decisions_emitted,
)


META_GOVERNOR_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "meta_governor"
META_GOVERNOR_REGISTRY_PATH = META_GOVERNOR_ARTIFACT_DIR / "meta_governor_registry.jsonl"
META_GOVERNOR_DECISIONS_PATH = META_GOVERNOR_ARTIFACT_DIR / "meta_governor_decisions.jsonl"
META_GOVERNOR_LEDGER_PATH = META_GOVERNOR_ARTIFACT_DIR / "meta_governor_proof.jsonl"
META_GOVERNOR_SUMMARY_PATH = META_GOVERNOR_ARTIFACT_DIR / "meta_governor_summary.md"


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_governor": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_meta_governor_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"meta-governor requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("meta-governor requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("meta-governor requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("meta-governor requires allow_unofficial_robinhood_api=false")


def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _role_flags(evidence: EvidenceBundle, profiles) -> tuple[str, set[str], set[str], set[str]]:
    """Return (champion_id, top_strategy_ids, ensemble_member_ids, mutation_champion_ids)."""
    champion_id = str(evidence.champion.get("champion_strategy_id", ""))
    ensemble_members = {str(d.get("strategy_id", "")) for d in evidence.ensemble.get("decisions", []) if float(d.get("recommended_weight", 0.0)) > 0.0}
    mutation_champ = str(evidence.mutation.get("best_mutated_strategy_id", ""))
    fb_champ = str(evidence.feedback.get("best_candidate", {}).get("candidate_strategy_id", ""))
    mutation_champions = {s for s in (mutation_champ, fb_champ) if s}
    return champion_id, ensemble_members, ensemble_members, mutation_champions


def _build_summary_markdown(result: MetaGovernorRunResult, decisions: list[MetaGovernorDecision],
                            family_profiles, regime_profiles, layer_scores,
                            missing_evidence: list[str]) -> str:
    lines: list[str] = []
    lines.append("# DOPEY Offline Meta-Governor Summary")
    lines.append("")
    lines.append(f"- meta_governor_version: `{META_GOVERNOR_VERSION}`")
    lines.append(f"- mode: `{result.mode}`")
    lines.append(f"- live_trading_enabled: `{result.live_trading_enabled}`")
    lines.append(f"- live_blocked: `{result.live_blocked}`")
    lines.append(f"- strategies_evaluated: `{result.strategies_evaluated}`")
    lines.append(f"- families_evaluated: `{result.families_evaluated}`")
    lines.append(f"- forbidden_live_decisions_emitted: `{result.forbidden_live_decisions_emitted}`")
    lines.append("")
    lines.append("## Top strategy proof profile")
    if decisions:
        top = sorted(decisions, key=lambda d: (-d.proof_strength, d.strategy_id))[0]
        lines.append(f"- strategy_id: `{top.strategy_id}`")
        lines.append(f"- family: `{top.strategy_family}`")
        lines.append(f"- decision: `{top.decision}`")
        lines.append(f"- eligible_tier: `{top.eligible_tier}`")
        lines.append(f"- proof_strength: `{round(top.proof_strength, 6)}`")
        lines.append(f"- risk_pressure: `{round(top.risk_pressure, 6)}`")
        lines.append(f"- paper_only: `{top.paper_only}` / live_allowed: `{top.live_allowed}`")
    lines.append("")
    lines.append("## Family trust ranking")
    for fp in family_profiles:
        lines.append(
            f"- `{fp.strategy_family}` trust={round(fp.trust_score, 3)} attention=`{fp.recommended_attention}` "
            f"mutation_intensity=`{fp.allowed_mutation_intensity}` ensemble_weight={round(fp.ensemble_weight, 3)}"
        )
    lines.append("")
    lines.append("## Best / worst regimes by family")
    for fp in family_profiles:
        lines.append(f"- `{fp.strategy_family}` best={fp.best_regimes} worst={fp.worst_regimes}")
    lines.append("")
    lines.append("## Regime trust map")
    for rp in regime_profiles:
        lines.append(
            f"- `{rp.regime_tag}` ({rp.regime_class}) trust={round(rp.trust_score, 3)} "
            f"preferred={rp.preferred_families} penalized={rp.penalized_families} "
            f"dominant_failures={rp.dominant_failure_modes}"
        )
    lines.append("")
    lines.append("## Promotion / demotion decisions")
    for d in decisions:
        lines.append(f"- `{d.strategy_id}` -> `{d.decision}` (tier `{d.eligible_tier}`, proof {round(d.proof_strength, 3)})")
    lines.append("")
    lines.append("## Missing evidence priorities")
    for m in missing_evidence:
        lines.append(f"- {m}")
    lines.append("")
    lines.append("## Evidence layer scores")
    for layer in layer_scores:
        lines.append(f"- `{layer.layer_name}` status=`{layer.status}` score={round(layer.score, 3)} coverage={round(layer.coverage, 3)}")
    lines.append("")
    lines.append("## Safety state")
    lines.append("- PaperBroker refuses `live_allowed=true`; Robinhood/Alpaca/Tradier raise `LiveTradingDisabledError`.")
    lines.append("- No broker connection, credentials, network market data, live trades, live promotion, or scheduled run.")
    lines.append("- Live migration requires: human approval, explicit live_trading enablement by an operator, MICRO_LIVE/ADAPTIVE_LIVE mode, broker capability confirmation, LiveOrderGate approval, and additional OOS evidence. NOT enabled in this pass.")
    return "\n".join(lines) + "\n"


def _aggregate_missing_evidence(decisions: list[MetaGovernorDecision]) -> list[str]:
    counts: dict[str, int] = {}
    for d in decisions:
        for m in d.required_missing_evidence:
            counts[m] = counts.get(m, 0) + 1
    return [m for m, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _build_proof_entry(result: MetaGovernorRunResult, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=META_GOVERNOR_VERSION,
        task_id="offline-meta-governor-proof-weighted-promotion",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"governor_version": META_GOVERNOR_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "governor_result": result.to_dict(),
            "registry_record": registry_record,
            "safety_state": result.safety_state,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[result.registry_path, result.decisions_path, result.summary_path],
        diffs=[],
        test_results={
            "meta_governor_status": result.meta_governor_status,
            "strategies_evaluated": result.strategies_evaluated,
            "families_evaluated": result.families_evaluated,
            "forbidden_live_decisions_emitted": result.forbidden_live_decisions_emitted,
            "forbidden_live_tiers_emitted": sorted(set(d.get("eligible_tier", "") for d in registry_record.get("decisions", [])).intersection(FORBIDDEN_LIVE_TIERS)),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic paper-only proof governance; no live execution",
            "governance decisions are research/paper only, not live promotion",
            "no broker connection, credentials, network market data, schedule, or live migration",
        ],
    )


def run_offline_meta_governor(
    *,
    evidence_paths: dict[str, Path] | None = None,
    registry_path: Path | str | None = None,
    decisions_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
    summary_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_meta_governor_safety_state(safety)

    evidence = load_evidence_bundle(evidence_paths or EVIDENCE_PATHS)
    layer_scores = score_evidence_layers(evidence)
    profiles = build_strategy_proof_profiles(evidence)
    if not profiles:
        raise ValueError("meta-governor requires at least one strategy proof profile (tournament evidence missing)")

    family_profiles = build_family_trust_profiles(evidence, profiles)
    regime_profiles = build_regime_trust_profiles(evidence)

    champion_id, ensemble_members, _, mutation_champions = _role_flags(evidence, profiles)
    top_strategy_ids = set()
    if profiles:
        top_strategy_ids = {sorted(profiles, key=lambda p: (-p.current_score, p.strategy_id))[0].strategy_id}
    if champion_id:
        top_strategy_ids.add(champion_id)

    decisions: list[MetaGovernorDecision] = []
    for profile in profiles:
        quality = score_proof_quality(profile, layer_scores, evidence)
        decision = decide_meta_governor(
            profile, quality,
            is_top_strategy=profile.strategy_id in top_strategy_ids,
            is_ensemble_member=profile.strategy_id in ensemble_members,
            is_mutation_champion=profile.strategy_id in mutation_champions,
        )
        decisions.append(decision)

    forbidden = forbidden_decisions_emitted(decisions)
    if forbidden:
        raise ValueError(f"forbidden live meta-governor decisions emitted: {forbidden}")
    forbidden_tiers = sorted({d.eligible_tier for d in decisions}.intersection(FORBIDDEN_LIVE_TIERS))
    if forbidden_tiers:
        raise ValueError(f"forbidden live tiers emitted: {forbidden_tiers}")

    paper_champions = [d.strategy_id for d in decisions if d.decision == "promote_to_paper_champion"]
    ensemble_members_out = [d.strategy_id for d in decisions if d.decision == "mark_offline_ensemble_member"]
    mutation_champions_out = [d.strategy_id for d in decisions if d.decision == "mark_offline_mutation_champion"]
    quarantined = [d.strategy_id for d in decisions if d.decision == "quarantine_overfit"]
    starved = [d.strategy_id for d in decisions if d.decision == "starve_weak_signal"]
    research_only = [d.strategy_id for d in decisions if d.decision in {"hold_research_only", "request_more_fixture_evidence"}]
    rejected = [d.strategy_id for d in decisions if d.decision == "reject_unsafe"]
    missing_evidence = _aggregate_missing_evidence(decisions)

    result = MetaGovernorRunResult(
        meta_governor_status="ok",
        mode=safety["mode"],
        live_trading_enabled=safety["live_trading_enabled"],
        strategies_evaluated=len(profiles),
        families_evaluated=len(family_profiles),
        paper_champions=paper_champions,
        offline_ensemble_members=ensemble_members_out,
        offline_mutation_champions=mutation_champions_out,
        quarantined=quarantined,
        starved=starved,
        research_only=research_only,
        rejected=rejected,
        forbidden_live_decisions_emitted=[],
        live_blocked=True,
        safety_state=safety,
    )

    registry_record = {
        "meta_governor_version": META_GOVERNOR_VERSION,
        "proof_quality_version": PROOF_QUALITY_VERSION,
        "promotion_policy_version": PROMOTION_POLICY_VERSION,
        "family_trust_map_version": FAMILY_TRUST_MAP_VERSION,
        "evidence_layers_present": evidence.layers_present(),
        "evidence_layer_scores": [layer.to_dict() for layer in layer_scores],
        "strategy_proof_profiles": [p.to_dict() for p in profiles],
        "family_trust_profiles": [p.to_dict() for p in family_profiles],
        "regime_trust_profiles": [p.to_dict() for p in regime_profiles],
        "decisions": [d.to_dict() for d in decisions],
        "missing_evidence_priorities": missing_evidence,
        "allowed_tiers": ALLOWED_TIERS,
        "safety_state": safety,
    }
    repro = reproducibility_hash(registry_record)
    registry_record["reproducibility_hash"] = repro
    result.reproducibility_hash = repro

    reg_target = _write_jsonl(registry_record, registry_path or META_GOVERNOR_REGISTRY_PATH)
    decisions_record = {
        "meta_governor_version": META_GOVERNOR_VERSION,
        "decisions": [d.to_dict() for d in decisions],
        "decision_counts": {
            "paper_champions": len(paper_champions),
            "offline_ensemble_members": len(ensemble_members_out),
            "offline_mutation_champions": len(mutation_champions_out),
            "quarantined": len(quarantined),
            "starved": len(starved),
            "research_only": len(research_only),
            "rejected": len(rejected),
        },
        "safety_state": safety,
    }
    dec_repro = reproducibility_hash(decisions_record)
    decisions_record["reproducibility_hash"] = dec_repro
    dec_target = _write_jsonl(decisions_record, decisions_path or META_GOVERNOR_DECISIONS_PATH)
    result.registry_path = str(reg_target)
    result.decisions_path = str(dec_target)

    proof_target = Path(proof_ledger_path) if proof_ledger_path else META_GOVERNOR_LEDGER_PATH
    result.proof_record_path = str(proof_target)

    summary_md = _build_summary_markdown(result, decisions, family_profiles, regime_profiles, layer_scores, missing_evidence)
    summary_target = Path(summary_path) if summary_path else META_GOVERNOR_SUMMARY_PATH
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.write_text(summary_md, encoding="utf-8")
    result.summary_path = str(summary_target)

    ProofLedger(proof_target).append(_build_proof_entry(result, registry_record))

    summary = result.to_dict()
    summary["evidence_layer_scores"] = [layer.to_dict() for layer in layer_scores]
    summary["strategy_proof_profiles"] = [p.to_dict() for p in profiles]
    summary["family_trust_profiles"] = [p.to_dict() for p in family_profiles]
    summary["regime_trust_profiles"] = [p.to_dict() for p in regime_profiles]
    summary["decisions"] = [d.to_dict() for d in decisions]
    summary["missing_evidence_priorities"] = missing_evidence
    return summary
