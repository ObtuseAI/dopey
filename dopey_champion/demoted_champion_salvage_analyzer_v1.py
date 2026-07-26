"""Demoted champion salvage analyzer V1."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import HARDENING_ROOT, load_public_trades, stress_metrics, trades_for_champion, live_safety_fields
from dopey_autonomy.champion_repair_common import REPAIR_ROOT, demoted_champion_names, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file


RECORDS_PATH = REPAIR_ROOT / "demoted_champion_salvage_records_v1.jsonl"
CANDIDATES_PATH = REPAIR_ROOT / "demoted_champion_salvage_candidates_v1.jsonl"
KILLS_PATH = REPAIR_ROOT / "demoted_champion_kill_confirmations_v1.jsonl"
SUMMARY_PATH = REPAIR_ROOT / "demoted_champion_salvage_analyzer_v1_summary.json"
PROOF_PATH = REPAIR_ROOT / "demoted_champion_salvage_analyzer_v1_proof.jsonl"
STRESS_RESULTS_PATH = HARDENING_ROOT / "public_champion_deep_stress_results_v1.jsonl"


def run_demoted_champion_salvage_analyzer_v1() -> dict[str, object]:
    demoted = demoted_champion_names()
    trades = load_public_trades()
    stress_results = read_jsonl_file(STRESS_RESULTS_PATH)
    records: list[dict[str, object]] = []
    salvage_candidates: list[dict[str, object]] = []
    kills: list[dict[str, object]] = []

    for champion in demoted:
        cohort_trades = trades_for_champion({"cohort_level": "variant_id", "cohort_id": champion}, trades)
        if not cohort_trades and "volatility_squeeze" in champion:
            cohort_trades = trades_for_champion({"cohort_level": "family_cohort_id", "cohort_id": "volatility_squeeze_breakout"}, trades)
        metrics = stress_metrics(cohort_trades)
        failures = [r for r in stress_results if r.get("champion_name") == champion and not r.get("survival_flag")]
        systemic = len(failures) >= 20 or safe_float(metrics.get("profit_factor", 0.0)) <= 1.05
        status = classify_demoted(champion, metrics, systemic)
        record = record_with_hash({
            "artifact_type": "demoted_champion_salvage_record_v1",
            "champion_name": champion,
            "salvage_status": status,
            "failure_count": len(failures),
            "systemic_failure": systemic,
            "sample_count": metrics.get("sample_count", 0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            **live_safety_fields(),
        }, "record_hash")
        records.append(record)
        if status == "salvage_candidate":
            salvage_candidates.append(record)
        elif status in {"permanent_demotion", "kill_confirmed"}:
            kills.append(record)

    summary = {
        "artifact_type": "demoted_champion_salvage_analyzer_v1_summary",
        "demoted_champion_salvage_analyzer_version": "dopey-public-champion-salvage-analyzer-v1",
        "demoted_champion_salvage_status": "demoted_salvage_analysis_complete",
        "demoted_champion_count": len(demoted),
        "salvage_candidate_count": len(salvage_candidates),
        "kill_confirmed_count": len(kills),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RECORDS_PATH, records)
    write_jsonl_file(CANDIDATES_PATH, salvage_candidates)
    write_jsonl_file(KILLS_PATH, kills)
    write_stage_proof(PROOF_PATH, "demoted-champion-salvage-analyzer-v1", str(summary["demoted_champion_salvage_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def classify_demoted(champion: str, metrics: dict[str, object], systemic: bool) -> str:
    if "volatility_squeeze" in champion and systemic:
        return "kill_confirmed"
    if systemic:
        return "permanent_demotion"
    if safe_float(metrics.get("profit_factor", 0.0)) > 1.12 and int(metrics.get("sample_count", 0)) >= 30:
        return "salvage_candidate"
    if safe_float(metrics.get("net_pnl", 0.0)) > 0.0:
        return "watchlist_only"
    return "permanent_demotion"


def artifact_paths() -> dict[str, str]:
    return {"demoted_champion_salvage_analyzer_v1_summary": str(SUMMARY_PATH)}
