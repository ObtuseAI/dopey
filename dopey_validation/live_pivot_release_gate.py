"""Fail-closed evidence gate for the fully-live service label and options release."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Final

from dopey_live.ledger import (
    LiveBranchLedgerError,
    ledger_path,
    paper_twin_path,
    read_ledger,
)
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT: Final[Path] = REPO_ROOT / "artifacts" / "dopey"
FORWARD_INTEGRITY_PATH: Final[Path] = ARTIFACT_ROOT / "forward_walk" / "forward_evidence_integrity.json"
CHAMPION_HARDENING_PATH: Final[Path] = (
    ARTIFACT_ROOT / "champion_hardening" / "public_champion_hardening_gate_v1_summary.json"
)
NIGHTLY_PATH: Final[Path] = ARTIFACT_ROOT / "nightly" / "nightly_latest.json"
LIVE_LATEST_PATH: Final[Path] = ARTIFACT_ROOT / "live_branch" / "latest_cycle.json"
OUTPUT_PATH: Final[Path] = ARTIFACT_ROOT / "broker_readiness" / "live_pivot_release_gate.json"

RELEASE_GATE_VERSION: Final[str] = "dopey-live-pivot-release-gate-v1"
MIN_VALIDATED_FORWARD_TRADES: Final[int] = 100
MIN_VALIDATED_ENTRY_COHORTS: Final[int] = 10


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {"load_error": f"{type(error).__name__}: {error}"}, "invalid"
    if not isinstance(value, dict):
        return {"load_error": f"expected object, actual={type(value).__name__}"}, "invalid"
    return value, "available"


def _result_bearing_paper_execution(payload: dict[str, Any]) -> bool:
    if (
        payload.get("paper_twin_execution_status")
        != "independent_quote_observation_complete"
        or payload.get("result_bearing") is not True
        or payload.get("independent_of_live_result") is not True
        or payload.get("paper_only") is not True
        or not str(payload.get("market_observation_source", ""))
        or not str(payload.get("market_observed_at", ""))
    ):
        return False
    fill_status = payload.get("paper_fill_status")
    try:
        quantity = float(payload.get("paper_filled_quantity", 0.0))
    except (TypeError, ValueError):
        return False
    if not math.isfinite(quantity) or quantity < 0.0:
        return False
    if fill_status == "simulated_not_filled":
        return quantity == 0.0 and payload.get("paper_average_fill_price") is None
    if fill_status != "simulated_filled" or quantity <= 0.0:
        return False
    try:
        price = float(payload.get("paper_average_fill_price", 0.0))
    except (TypeError, ValueError):
        return False
    return math.isfinite(price) and price > 0.0


def _live_ledger_evidence(repository_root: Path) -> dict[str, Any]:
    try:
        live_records = read_ledger(ledger_path(repository_root))
        twin_records = read_ledger(paper_twin_path(repository_root))
    except LiveBranchLedgerError as error:
        return {
            "ledger_integrity_green": False,
            "paper_twin_linkage_green": False,
            "paper_twin_result_evidence_green": False,
            "placed_orders_reconciled": False,
            "placed_order_count": 0,
            "unreconciled_order_ids": [],
            "error": str(error),
        }
    staged_twin_hashes = {
        str(record.get("record_hash", ""))
        for record in twin_records
        if record.get("event_type") == "paper_twin_staged"
    }
    linked_live_hashes = {
        str(record["payload"].get("live_record_hash", ""))
        for record in twin_records
        if record.get("event_type") == "paper_twin_linked" and isinstance(record.get("payload"), dict)
    }
    result_bearing_twin_hashes = {
        str(record["payload"].get("paper_twin_record_hash", ""))
        for record in twin_records
        if record.get("event_type") == "paper_twin_execution_observed"
        and isinstance(record.get("payload"), dict)
        and _result_bearing_paper_execution(record["payload"])
    }
    # Legacy orders placed before execution-snapshot capture serialized no
    # review-time quote: an independent twin result is structurally impossible
    # for them, forever. They are reported separately (loudly) instead of
    # being counted as missing results - which would otherwise be a permanent
    # blocker whose only "fix" is placing more live orders. Post-capability
    # orders never legitimately carry this marker.
    terminally_unobservable_twin_hashes = {
        str(record["payload"].get("paper_twin_record_hash", ""))
        for record in twin_records
        if record.get("event_type") == "paper_twin_execution_observed"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("terminally_unobservable") is True
        and str(record["payload"].get("paper_twin_execution_status", ""))
        == "unobservable_legacy_order_predates_quote_snapshot"
    }
    observed_order_ids = {
        str(record["payload"].get("order_id", ""))
        for record in live_records
        if record.get("event_type") == "live_order_status_observed" and isinstance(record.get("payload"), dict)
    }
    placed_records = [
        record
        for record in live_records
        if record.get("event_type") == "live_order_result"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("placed") is True
    ]
    missing_twin_links: list[str] = []
    missing_twin_results: list[str] = []
    unobservable_legacy_twin_orders: list[str] = []
    unreconciled_order_ids: list[str] = []
    for record in placed_records:
        payload = record["payload"]
        order_id = str(payload.get("order_id", ""))
        twin_hash = str(payload.get("paper_twin_record_hash", ""))
        live_hash = str(record.get("record_hash", ""))
        if not twin_hash or twin_hash not in staged_twin_hashes or live_hash not in linked_live_hashes:
            missing_twin_links.append(order_id or live_hash)
        if not twin_hash or twin_hash not in result_bearing_twin_hashes:
            if twin_hash and twin_hash in terminally_unobservable_twin_hashes:
                unobservable_legacy_twin_orders.append(order_id or live_hash)
            else:
                missing_twin_results.append(order_id or live_hash)
        if not order_id or order_id not in observed_order_ids:
            unreconciled_order_ids.append(order_id or live_hash)
    return {
        "ledger_integrity_green": True,
        "paper_twin_linkage_green": not missing_twin_links,
        "paper_twin_result_evidence_green": not missing_twin_results,
        "placed_orders_reconciled": not unreconciled_order_ids,
        "placed_order_count": len(placed_records),
        "missing_twin_link_order_ids": sorted(missing_twin_links),
        "missing_twin_result_order_ids": sorted(missing_twin_results),
        "twin_result_unobservable_legacy_order_ids": sorted(
            unobservable_legacy_twin_orders
        ),
        "unreconciled_order_ids": sorted(unreconciled_order_ids),
        "live_ledger_record_count": len(live_records),
        "paper_twin_ledger_record_count": len(twin_records),
        "error": "",
    }


def build_live_pivot_release_gate(repository_root: Path) -> dict[str, Any]:
    if repository_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(f"repository root mismatch: expected={REPO_ROOT}, actual={repository_root}")
    integrity, integrity_status = _load_json(FORWARD_INTEGRITY_PATH)
    hardening, hardening_status = _load_json(CHAMPION_HARDENING_PATH)
    nightly, nightly_status = _load_json(NIGHTLY_PATH)
    live_latest, live_latest_status = _load_json(LIVE_LATEST_PATH)
    ledger_evidence = _live_ledger_evidence(repository_root)
    account = live_latest.get("account", {}) if isinstance(live_latest.get("account"), dict) else {}
    options_enabled = live_latest.get("options_execution_enabled") is True
    broker_history_complete = (
        account.get("authenticated") is True
        and account.get("equity_order_history_complete") is True
        and (not options_enabled or account.get("option_order_history_complete") is True)
    )
    stack_stability = nightly.get("stack_stability", {})
    if not isinstance(stack_stability, dict):
        stack_stability = {}
    fitness_determinism = nightly.get("fitness_determinism", {})
    if not isinstance(fitness_determinism, dict):
        fitness_determinism = {}
    checks = {
        "forward_integrity_artifact_current": integrity.get("integrity_version")
        == "dopey-forward-evidence-integrity-v1",
        "validated_forward_sample_sufficient": int(integrity.get("validated_closed_trade_count", 0))
        >= MIN_VALIDATED_FORWARD_TRADES,
        "validated_forward_multi_cohort": int(integrity.get("validated_entry_cohort_count", 0))
        >= MIN_VALIDATED_ENTRY_COHORTS,
        "validated_forward_net_positive": float(integrity.get("validated_net_pnl_premium_units", 0.0)) > 0.0,
        "hardened_champion_available": int(hardening.get("hardened_champion_count", 0)) > 0,
        "full_nightly_validation_green": (
            nightly.get("verdict") == "all_green"
            and nightly.get("suite_green") is True
            and stack_stability.get("green") is True
            and fitness_determinism.get("deterministic") is True
        ),
        "live_ledgers_hash_chain_green": ledger_evidence["ledger_integrity_green"] is True,
        "paper_twin_linkage_green": ledger_evidence["paper_twin_linkage_green"] is True,
        "paper_twin_result_evidence_green": ledger_evidence[
            "paper_twin_result_evidence_green"
        ]
        is True,
        "broker_order_history_complete": broker_history_complete,
        "placed_orders_reconciled": ledger_evidence["placed_orders_reconciled"] is True,
    }
    missing = sorted(name for name, passed in checks.items() if not passed)
    release_allowed = not missing
    summary = {
        "artifact_type": "live_pivot_release_gate",
        "release_gate_version": RELEASE_GATE_VERSION,
        "release_status": "release_ready" if release_allowed else "release_blocked",
        "fully_live_label_allowed": release_allowed,
        "options_research_release_allowed": release_allowed,
        "checks": checks,
        "missing_requirements": missing,
        "thresholds": {
            "minimum_validated_forward_trades": MIN_VALIDATED_FORWARD_TRADES,
            "minimum_validated_entry_cohorts": MIN_VALIDATED_ENTRY_COHORTS,
        },
        "forward_integrity": {
            "source_status": integrity_status,
            "validated_closed_trade_count": int(integrity.get("validated_closed_trade_count", 0)),
            "validated_entry_cohort_count": int(integrity.get("validated_entry_cohort_count", 0)),
            "censored_outcome_count": int(integrity.get("censored_outcome_count", 0)),
            "quarantined_outcome_count": int(integrity.get("quarantined_outcome_count", 0)),
        },
        "champion_hardening_source_status": hardening_status,
        "nightly_source_status": nightly_status,
        "live_latest_source_status": live_latest_status,
        "broker_and_twin_evidence": ledger_evidence,
        "broker_history_complete": broker_history_complete,
        "long_equity_live_owner_authority_changed": False,
        "options_execution_control_changed": False,
        "research_maturity_and_live_authority_remain_separate": True,
        "no_broker_call_performed": True,
        "paper_only_research_gate": True,
        "live_blocked": not release_allowed,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(OUTPUT_PATH, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(build_live_pivot_release_gate(REPO_ROOT), indent=2, sort_keys=True))
