"""Failed champion family quarantine V1."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import HARDENING_ROOT, live_safety_fields
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    conditional_champion_names,
    demoted_champion_names,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_common import (
    QUARANTINE_PATH,
    QUARANTINE_SIGNATURES,
    RESEARCH_ROOT,
    is_quarantined_signature,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file


LESSONS_PATH = RESEARCH_ROOT / "failed_family_lessons_ledger_v1.jsonl"
NEGATIVE_CONTROLS_PATH = RESEARCH_ROOT / "failed_family_negative_controls_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "failed_champion_family_quarantine_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "failed_champion_family_quarantine_v1_proof.jsonl"
STRESS_PATH = HARDENING_ROOT / "public_champion_deep_stress_results_v1.jsonl"
SALVAGE_PATH = REPAIR_ROOT / "demoted_champion_salvage_records_v1.jsonl"


def run_failed_champion_family_quarantine_v1() -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    stress = read_jsonl_file(STRESS_PATH)
    salvage = read_jsonl_file(SALVAGE_PATH)
    quarantine_records: list[dict[str, object]] = []
    lessons: list[dict[str, object]] = []
    negative_controls: list[dict[str, object]] = []
    future_allowed = 0

    families = build_quarantine_families()
    for family in families:
        family_id = str(family["family_id"])
        failures = [row for row in stress if family_id in str(row.get("champion_name", "")) and not row.get("survival_flag")]
        salvage_row = next((row for row in salvage if str(row.get("champion_name", "")) == family_id), {})
        overlap_risk = is_quarantined_signature(family_id)
        negative_control = "volatility_squeeze" in family_id or family_id in conditional_champion_names()
        future_eligible = not negative_control and salvage_row.get("salvage_status") == "watchlist_only"
        if future_eligible:
            future_allowed += 1
        record = record_with_hash({
            "artifact_type": "failed_champion_family_quarantine_v1",
            "family_id": family_id,
            "quarantine_reason": family.get("quarantine_reason", ""),
            "stress_failure_count": len(failures),
            "holdout_failure_profile": family.get("holdout_failure_profile", ""),
            "sample_concentration_problem": family.get("sample_concentration_problem", False),
            "negative_control": negative_control,
            "failed_family_overlap_risk": overlap_risk,
            "future_research_allowed_after_redesign": future_eligible,
            **live_safety_fields(),
        }, "record_hash")
        quarantine_records.append(record)
        lessons.append(record_with_hash({
            "artifact_type": "failed_family_lessons_ledger_v1",
            "family_id": family_id,
            "failure_reason": family.get("failure_reason", ""),
            "stress_failure_profile": family.get("stress_failure_profile", ""),
            "holdout_failure_profile": family.get("holdout_failure_profile", ""),
            "concentration_problem": family.get("sample_concentration_problem", False),
            "negative_control": negative_control,
            **live_safety_fields(),
        }, "record_hash"))
        if negative_control:
            negative_controls.append(record)

    summary = {
        "artifact_type": "failed_champion_family_quarantine_v1_summary",
        "failed_champion_family_quarantine_version": "dopey-public-failed-family-quarantine-v1",
        "failed_family_quarantine_status": "failed_family_quarantine_complete",
        "quarantined_family_count": len(quarantine_records),
        "negative_control_count": len(negative_controls),
        "future_research_allowed_count": future_allowed,
        "quarantine_signatures": list(QUARANTINE_SIGNATURES),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(QUARANTINE_PATH, quarantine_records)
    write_jsonl_file(LESSONS_PATH, lessons)
    write_jsonl_file(NEGATIVE_CONTROLS_PATH, negative_controls)
    write_stage_proof(PROOF_PATH, "failed-champion-family-quarantine-v1", str(summary["failed_family_quarantine_status"]), summary)
    return {**summary, "artifact_paths": {"failed_champion_family_quarantine_v1_summary": str(SUMMARY_PATH)}}


def build_quarantine_families() -> list[dict[str, object]]:
    families: list[dict[str, object]] = []
    for champion in demoted_champion_names() + conditional_champion_names():
        families.append({
            "family_id": champion,
            "quarantine_reason": "prior_demotion_or_failed_retune",
            "failure_reason": "systemic_stress_failure_under_model_priced_paths",
            "stress_failure_profile": "net_pnl_not_positive|profit_factor_below_core_threshold|sample_count_inadequate",
            "holdout_failure_profile": "holdout_survival_failed",
            "sample_concentration_problem": "volatility_squeeze" in champion,
        })
    families.append({
        "family_id": "volatility_squeeze_breakout",
        "quarantine_reason": "shared_trade_concentration_cohort",
        "failure_reason": "systemic_negative_expectancy_under_hardening_stress",
        "stress_failure_profile": "net_pnl_not_positive",
        "holdout_failure_profile": "holdout_survival_failed",
        "sample_concentration_problem": True,
    })
    return families


def load_quarantine_ids() -> set[str]:
    return {str(row.get("family_id", "")) for row in read_jsonl_file(QUARANTINE_PATH) if row.get("family_id")}
