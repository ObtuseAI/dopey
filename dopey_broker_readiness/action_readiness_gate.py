"""Action-readiness gate: 'ready for action' as a measurable, machine-checked state.

Evaluates every condition the system itself requires before ANY broker
connection could be justified, from live artifacts - and publishes the exact
missing list. Also codifies the Robinhood MCP boundary contract:

ALLOWED (if/when an OFFICIAL Robinhood MCP exists and the operator connects it):
  read-only account snapshot, positions, balances - for paper-mirroring and
  reconciliation only. Auth lives in the MCP client, never in this repo.

BLOCKED PERMANENTLY BY THIS PROJECT'S ENVELOPE:
  unofficial Robinhood APIs / reverse-auth / session-cookie access (all
  community "Robinhood MCP" servers use these), credentials or .env in-repo,
  and ANY order/execution endpoint wiring. An OFFICIAL lane exists as of
  2026-07-09 (Robinhood Agentic Trading MCP, agent.robinhood.com/mcp/trading);
  only its read-only account mirroring is allowed, with auth in the operator's
  MCP client. This boundary is documentation - no network code backs it here.

The gate is NECESSARY, NOT SUFFICIENT: even at all-green, live trading stays
blocked pending explicit human operator review. This module contains no
network, broker, or credential code - it only reads local artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_analysis.forward_book_quality import run_forward_book_quality_audit
from dopey_backtest.baseline_arbitration import BASELINE_POLICY_VERSION
from dopey_backtest.era_walk_forward import ERA_POLICY_VERSION
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR
from dopey_risk_engine.adversarial_stress_engine import (
    build_current_quote_snapshot_binding,
    build_forward_book_binding,
    build_stress_policy_binding,
    stress_summary_has_complete_quotes,
    stress_summary_integrity_valid,
    stress_summary_matches_forward_book,
)
from dopey_validation.live_pivot_release_gate import build_live_pivot_release_gate

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / "artifacts" / "dopey"
FORWARD_SUMMARY_PATH = ARTIFACTS / "forward_walk" / "forward_walk_summary.json"
FORWARD_LEDGER_PATH = ARTIFACTS / "forward_walk" / "forward_walk_ledger.json"
FORWARD_INTEGRITY_PATH = ARTIFACTS / "forward_walk" / "forward_evidence_integrity.json"
BASELINE_SUMMARY_PATH = ARTIFACTS / "backtest" / "baseline_arbitration_summary.json"
ERA_SUMMARY_PATH = ARTIFACTS / "backtest" / "era_walk_forward_summary.json"
TRUTH_SUMMARY_PATH = ARTIFACTS / "stats" / "statistical_truth_summary.json"
STRESS_SUMMARY_PATH = (
    ARTIFACTS / "adversarial_stress" / "adversarial_stress_summary.json"
)
CALIBRATION_SUMMARY_PATH = (
    ARTIFACTS / "chain_analytics" / "model_iv_calibration_summary.json"
)
FRESHNESS_SUMMARY_PATH = ARTIFACTS / "observability" / "data_freshness.json"
READINESS_ARTIFACT_DIR = ARTIFACTS / "broker_readiness"
READINESS_SUMMARY_PATH = READINESS_ARTIFACT_DIR / "action_readiness_gate.json"
READINESS_REPORT_PATH = REPORTS_DIR / "DOPEY_ACTION_READINESS_GATE_REPORT.md"

MIN_FORWARD_CLOSED_TRADES = 100
MAX_CALIBRATION_ABS_MEDIAN_ERROR = 0.10


def stress_book_snapshot_matches_forward_book(
    stress: dict[str, Any],
    open_positions: list[dict[str, Any]],
) -> bool:
    """Return whether stress evidence binds to the exact current forward book."""
    return stress_summary_matches_forward_book(stress, open_positions)


def stress_evidence_integrity_valid(stress: dict[str, Any]) -> bool:
    """Verify stress evidence integrity and its fail-closed safety boundary."""
    return stress_summary_integrity_valid(stress)


def stress_valuation_inputs_match_current(
    stress: dict[str, Any],
    open_positions: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    """Compare policy, rates, and quote evidence with current governed inputs."""
    current_inputs = {
        **build_stress_policy_binding(),
        **build_current_quote_snapshot_binding(open_positions),
    }
    all_inputs_match = all(
        stress.get(key) == value for key, value in current_inputs.items()
    )
    quotes_usable = stress_summary_has_complete_quotes(
        current_inputs,
        open_positions,
    )
    return all_inputs_match and quotes_usable, current_inputs


def run_action_readiness_gate() -> dict[str, Any]:
    integrity = _load(FORWARD_INTEGRITY_PATH)
    baseline = _load(BASELINE_SUMMARY_PATH)
    era = _load(ERA_SUMMARY_PATH)
    truth = _load(TRUTH_SUMMARY_PATH)
    stress = _load(STRESS_SUMMARY_PATH)
    calibration = _load(CALIBRATION_SUMMARY_PATH)
    ledger = _load(FORWARD_LEDGER_PATH)
    freshness = _load(FRESHNESS_SUMMARY_PATH)
    book_quality = run_forward_book_quality_audit()
    live_pivot_release = build_live_pivot_release_gate(REPO_ROOT)

    raw_open_positions = ledger.get("open_positions")
    forward_book_structure_valid = isinstance(raw_open_positions, list) and all(
        isinstance(position, dict) for position in raw_open_positions
    )
    open_positions = (
        [dict(position) for position in raw_open_positions]
        if forward_book_structure_valid
        else []
    )
    current_forward_book_binding = build_forward_book_binding(open_positions)
    stress_book_snapshot_current = (
        forward_book_structure_valid
        and stress_book_snapshot_matches_forward_book(stress, open_positions)
    )
    stress_integrity_valid = stress_evidence_integrity_valid(stress)
    stress_valuation_inputs_current, current_stress_inputs = (
        stress_valuation_inputs_match_current(stress, open_positions)
        if forward_book_structure_valid
        else (False, {})
    )
    closed = int(integrity.get("validated_closed_trade_count", 0))
    validated_net_pnl = float(integrity.get("validated_net_pnl_premium_units", 0.0))
    halt = (
        ledger.get("last_discipline_halt")
        if isinstance(ledger.get("last_discipline_halt"), dict)
        else {}
    )
    checks = {
        "forward_track_sample_sufficient": closed >= MIN_FORWARD_CLOSED_TRADES,
        "forward_track_net_positive": validated_net_pnl > 0.0 and closed > 0,
        "forward_evidence_integrity_current": integrity.get("integrity_version")
        == "dopey-forward-evidence-integrity-v1",
        "validated_multi_cohort_forward_sample": (
            int(integrity.get("validated_entry_cohort_count", 0))
            >= int(live_pivot_release["thresholds"]["minimum_validated_entry_cohorts"])
        ),
        "cohort_baseline_policy_current": baseline.get("baseline_policy_version")
        == BASELINE_POLICY_VERSION,
        "any_cohort_beats_matched_baseline_familywise": (
            baseline.get("baseline_policy_version") == BASELINE_POLICY_VERSION
            and int(baseline.get("cohorts_beating_baseline", 0)) > 0
        ),
        "cohort_era_policy_current": era.get("era_policy_version")
        == ERA_POLICY_VERSION,
        "any_cohort_regime_robust": int(era.get("regime_robust_count", 0)) > 0,
        "statistical_truth_promotion_allowed": truth.get("promotion_allowed") is True,
        "stress_evidence_integrity_valid": stress_integrity_valid,
        "stress_book_snapshot_current": stress_book_snapshot_current,
        "stress_valuation_inputs_current": stress_valuation_inputs_current,
        "stress_book_survives_all_scenarios": (
            stress_integrity_valid
            and stress_book_snapshot_current
            and stress_valuation_inputs_current
            and stress.get("scenario_stress_green") is True
        ),
        # fail CLOSED: no ledger at all means the forward lane has never run,
        # which is not a passing state for a readiness check.
        "no_active_discipline_halt": bool(ledger)
        and int(halt.get("cooldown_sessions_remaining", 0)) <= 0,
        "pricing_model_calibrated": abs(
            float(calibration.get("model_premium_error_pct_median", 1.0))
        )
        <= MAX_CALIBRATION_ABS_MEDIAN_ERROR,
        "data_freshness_green": str(freshness.get("freshness_status", ""))
        == "data_freshness_green",
        "open_book_entry_quality_green": book_quality.get(
            "open_book_entry_quality_green"
        )
        is True,
        "open_book_concentration_green": book_quality.get(
            "open_book_concentration_green"
        )
        is True,
        "hardened_champion_available": live_pivot_release["checks"][
            "hardened_champion_available"
        ]
        is True,
        "full_nightly_validation_green": live_pivot_release["checks"][
            "full_nightly_validation_green"
        ]
        is True,
        "paper_twin_broker_reconciliation_green": (
            live_pivot_release["checks"]["paper_twin_linkage_green"] is True
            and live_pivot_release["checks"]["broker_order_history_complete"] is True
            and live_pivot_release["checks"]["placed_orders_reconciled"] is True
        ),
    }
    missing = sorted(name for name, passed in checks.items() if not passed)
    action_ready = not missing
    # Evidence ETA (estimate only, never a promise): closed trades accrue from
    # open positions aging into stops/targets/time-stops plus new entries. With
    # a 3-session max hold, open book roughly turns over every ~3 sessions and
    # refills at up to MAX_NEW_POSITIONS_PER_RUN; the dominant unknown is how
    # many entries the context gates admit each session.
    open_count = len(open_positions)
    remaining = max(MIN_FORWARD_CLOSED_TRADES - closed, 0)
    closes_per_session_optimistic = max(open_count / 3.0, 1.0)
    evidence_eta = {
        "estimate_only_not_a_promise": True,
        "closed_so_far": closed,
        "closed_required": MIN_FORWARD_CLOSED_TRADES,
        "open_positions_aging": open_count,
        "est_trading_days_to_sample_at_current_book": round(
            remaining / closes_per_session_optimistic, 1
        ),
        "assumption": "open book turns over ~every 3 sessions and refills; context gates set the true pace",
        "evidence_semantics_unchanged": "sample accrues only from real marked sessions; nothing accelerates it but the market",
    }
    summary = {
        "artifact_type": "action_readiness_gate",
        "readiness_status": "action_ready_pending_human_review"
        if action_ready
        else "not_action_ready",
        "action_ready": action_ready,
        "checks": checks,
        "missing_requirements": missing,
        "forward_closed_trades": closed,
        "forward_closed_trades_required": MIN_FORWARD_CLOSED_TRADES,
        "forward_raw_closed_records": int(integrity.get("raw_closed_record_count", 0)),
        "forward_censored_outcomes": int(integrity.get("censored_outcome_count", 0)),
        "forward_quarantined_outcomes": int(
            integrity.get("quarantined_outcome_count", 0)
        ),
        "forward_validated_entry_cohort_count": int(
            integrity.get("validated_entry_cohort_count", 0)
        ),
        "live_pivot_release_gate": live_pivot_release,
        "evidence_eta": evidence_eta,
        "forward_book_entry_quality": {
            "book_quality_status": book_quality["book_quality_status"],
            "open_position_count": book_quality["open_position_count"],
            "nonconforming_open_position_count": book_quality[
                "nonconforming_open_position_count"
            ],
            "unavailable_entry_evidence_count": book_quality[
                "unavailable_entry_evidence_count"
            ],
            "entry_policy_version": book_quality["entry_policy_version"],
            "open_book_concentration_green": book_quality[
                "open_book_concentration_green"
            ],
            "portfolio_concentration": book_quality["portfolio_concentration"],
        },
        "stress_book_snapshot_binding": {
            "binding_status": (
                "current_forward_book_bound"
                if stress_book_snapshot_current
                else "blocked_stale_or_unbound_stress_evidence"
            ),
            "current_forward_book": current_forward_book_binding,
            "stress_evidence": {
                key: stress.get(key) for key in current_forward_book_binding
            },
            "integrity_valid": stress_integrity_valid,
            "valuation_inputs_status": (
                "current_governed_inputs"
                if stress_valuation_inputs_current
                else "blocked_stale_or_unverified_valuation_inputs"
            ),
            "current_valuation_inputs": current_stress_inputs,
            "stress_valuation_inputs": {
                key: stress.get(key) for key in current_stress_inputs
            },
        },
        "gate_semantics": "necessary_not_sufficient_human_operator_review_always_required",
        "robinhood_mcp_boundary": {
            "official_mcp_available": True,
            "official_mcp_endpoint": "https://agent.robinhood.com/mcp/trading",
            "official_program": "Robinhood Agentic Trading (dedicated agentic account, MCP standard)",
            "verified_date": "2026-07-09",
            "allowed_now": [
                "read_only_account_snapshot_via_official_mcp",
                "positions_and_balances_for_paper_mirroring_and_reconciliation",
                "auth_lives_in_mcp_client_config_never_in_repo",
            ],
            "blocked_always": [
                "unofficial_api_or_reverse_auth_or_session_cookies",
                "credentials_or_env_in_repo",
            ],
            "execution_policy": {
                "status": "blocked_until_gate_all_green_plus_explicit_human_approval",
                "designated_path_if_ever_unlocked": "official_mcp_dedicated_agentic_account_only_minimum_sizing_human_reviewed",
                "operator_responsibility_note": "Robinhood terms place full responsibility for agent-executed trades on the account holder; the truth layer currently reports NO demonstrated edge",
            },
            "data_note": "market data needs are already met credential-free (governed OHLCV + chain snapshots); the official MCP adds account state now and execution only if ever earned",
        },
        "live_trading_enabled": False,
        "live_trading_enabled_field_scope": "protected_research_promotion_gate_only",
        "owner_authorized_live_branch_evaluated_separately": True,
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    READINESS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(READINESS_SUMMARY_PATH, summary)
    _write_report(summary)
    return summary


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Action Readiness Gate Report",
        "",
        "'Ready for action' is a checkable state, not a feeling. This gate evaluates every",
        "condition the system requires before a broker connection could even be discussed.",
        "",
        f"- readiness_status: `{summary['readiness_status']}`",
        f"- forward closed trades: `{summary['forward_closed_trades']}` / `{summary['forward_closed_trades_required']}` required",
        "",
        "## Checklist",
    ]
    for name, passed in summary["checks"].items():
        lines.append(f"- [{'x' if passed else ' '}] `{name}`")
    lines.extend(
        [
            "",
            "## Robinhood MCP Boundary (updated 2026-07-09)",
            "- OFFICIAL Robinhood Agentic Trading MCP exists: agent.robinhood.com/mcp/trading",
            "  (dedicated agentic account, MCP standard, Claude Code supported).",
            "- Allowed now: read-only account state via the official MCP for paper-mirroring and",
            "  reconciliation; auth lives in the operator's MCP client, never in this repo.",
            "- Unofficial credential lanes remain permanently blocked.",
            "- EXECUTION remains blocked until this gate is all-green AND a human explicitly",
            "  approves; if ever unlocked, the designated path is the official MCP into the",
            "  dedicated agentic account at minimum sizing. Robinhood's terms place full",
            "  responsibility for agent trades on the account holder - and the truth layer",
            "  currently reports no demonstrated edge.",
            "",
            "## Invariants",
            "- live_trading_enabled: `false`; paper_only: `true`; live_blocked: `true`.",
            "- All-green here is necessary, NOT sufficient. A human operator decision is always",
            "  the final gate.",
        ]
    )
    READINESS_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
