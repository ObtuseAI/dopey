"""Autonomous open historical options data gap plan."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, safety_state, stable_hash, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "options_autonomy"
CANDIDATE_PATH = ARTIFACT_DIR / "open_options_data_candidate_registry.jsonl"
RESULTS_PATH = ARTIFACT_DIR / "open_options_data_admissibility_results.jsonl"
GAP_REPORT_PATH = ARTIFACT_DIR / "open_options_data_gap_report.json"
SUMMARY_PATH = ARTIFACT_DIR / "open_options_data_autonomy_summary.json"
PROOF_PATH = ARTIFACT_DIR / "open_options_data_autonomy_proof.jsonl"


def run_open_options_data_autonomy_plan() -> dict[str, Any]:
    candidates = _candidates()
    results = [_result(record) for record in candidates]
    accepted_quotes = [record for record in results if record["outcome"] == "accepted_open_options_quotes_available"]
    accepted_chains = [record for record in results if record["outcome"] == "accepted_open_options_chain_available"]
    status = "accepted_open_options_quotes_available" if accepted_quotes else ("accepted_open_options_chain_available" if accepted_chains else "no_machine_admissible_open_options_data")
    gap = {
        "artifact_type": "open_options_data_gap_report",
        "options_data_status": status,
        "quote_priced_backtest_allowed": bool(accepted_quotes),
        "real_options_evidence_blocked": not bool(accepted_quotes or accepted_chains),
        "model_priced_options_research_allowed": True,
        "synthetic_scenario_testing_allowed": True,
        "synthetic_scenario_testing_label": "synthetic_only",
        "blocked_reasons": ["no_machine_admissible_credential_free_historical_options_quotes"] if not accepted_quotes else [],
        "paper_only": True,
        "live_blocked": True,
    }
    gap["gap_report_hash"] = stable_hash(gap)
    summary = {
        "artifact_type": "open_options_data_autonomy_summary",
        "options_autonomy_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "options_data_status": status,
        "candidate_count": len(candidates),
        "accepted_quote_source_count": len(accepted_quotes),
        "accepted_chain_source_count": len(accepted_chains),
        "quote_priced_backtest_allowed": bool(accepted_quotes),
        "model_priced_research_allowed": True,
        "real_options_evidence": bool(accepted_quotes or accepted_chains),
        "alpha_vantage_excluded": True,
        "network_fetch_performed": False,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(CANDIDATE_PATH, candidates)
    write_jsonl(RESULTS_PATH, results)
    write_json(GAP_REPORT_PATH, gap)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("open-options-data-autonomy-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "open_options_data_candidate_registry": str(CANDIDATE_PATH),
        "open_options_data_admissibility_results": str(RESULTS_PATH),
        "open_options_data_gap_report": str(GAP_REPORT_PATH),
        "open_options_data_autonomy_summary": str(SUMMARY_PATH),
        "open_options_data_autonomy_proof": str(PROOF_PATH),
    }


def _candidates() -> list[dict[str, Any]]:
    raw = [
        ("options-paid-archive", "paid historical quote archive", "MIT", True, False, False),
        ("options-broker-chain", "broker chain endpoint", "MIT", False, True, False),
        ("options-web-scrape", "scraped chain pages", "MIT", False, False, True),
        ("options-unknown-license", "unknown options dataset", "", False, False, False),
        ("options-fixture", "sample options fixture", "CC0-1.0", False, False, False),
    ]
    records: list[dict[str, Any]] = []
    for source_id, name, license_id, paid, broker, scrape in raw:
        record = {
            "artifact_type": "open_options_data_candidate_registry",
            "source_id": source_id,
            "source_name": name,
            "license_id": license_id,
            "paid_or_proprietary": paid,
            "broker_or_live_source": broker,
            "scrape_only": scrape,
            "credentials_required": broker,
            "sample_or_fixture": source_id == "options-fixture",
            "paper_only": True,
            "live_blocked": True,
        }
        record["candidate_hash"] = stable_hash(record)
        records.append(record)
    return records


def _result(candidate: dict[str, Any]) -> dict[str, Any]:
    if not candidate["license_id"]:
        outcome = "options_data_rejected_unknown_license"
    elif candidate["credentials_required"]:
        outcome = "options_data_rejected_credentials_required"
    elif candidate["scrape_only"]:
        outcome = "options_data_rejected_scrape_only"
    elif candidate["paid_or_proprietary"] or candidate["sample_or_fixture"]:
        outcome = "no_machine_admissible_open_options_data"
    else:
        outcome = "no_machine_admissible_open_options_data"
    record = {
        "artifact_type": "open_options_data_admissibility_results",
        "source_id": candidate["source_id"],
        "outcome": outcome,
        "quote_priced_backtest_allowed": False,
        "model_priced_research_allowed": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["result_hash"] = stable_hash(record)
    return record

