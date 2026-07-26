"""Orchestrate the paper-only equity-first multi-timeframe swing research lane."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dopey_backtest.trade_records_recovery import (
    VerifiedLedgerResolution,
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)
from dopey_core.repo_paths import REPORTS_DIR
from dopey_data.history_validator import validate_default_history_dataset
from dopey_market_intake.macro_context_gate import (
    load_macro_lanes,
    run_macro_context_gate,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .contract_selector import (
    load_option_chain_snapshot,
    load_short_rate,
    select_strategic_contracts,
)
from .context_evidence import (
    append_context_decision_records,
    build_context_decision_records,
    build_context_decision_velocity,
    build_context_evidence_gate,
    repair_context_decision_ledger,
)
from .context_outcomes import (
    append_outcome_records,
    build_matured_context_outcomes,
    load_jsonl_records,
)
from .cross_asset import build_cross_asset_regime, load_cross_asset_snapshot
from .fundamentals import (
    FundamentalSnapshot,
    load_earnings_dates,
    resolve_fundamental_snapshot,
    score_fundamental_snapshot,
)
from .leveraged_etf import (
    build_leveraged_etf_swing_plans,
    preferred_leveraged_etf_plans,
)
from .market_structure import analyze_multi_timeframe_structure, group_history_bars
from .news_context import (
    apply_external_context,
    build_news_intelligence,
    load_news_snapshot,
)
from .reverse_engineering import (
    build_trade_evidence,
    build_retrospective_events,
    mine_strategy_candidates,
    missed_trade_events,
)
from .snapshot_resolution import (
    EarningsSnapshot,
    OptionSnapshot,
    build_earnings_evidence,
    resolve_earnings_snapshot,
    resolve_option_snapshot,
)
from .thesis import (
    SECTOR_ETF_BY_THEME,
    build_equity_swing_thesis,
    technical_confirmation,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey" / "equity_swing"
FUNDAMENTALS_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context" / "fundamentals.csv"
)
EARNINGS_ROOT = REPO_ROOT / "dopey_data" / "real" / "raw" / "earnings_calendar"
CHAIN_ROOT = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
OPTIONS_MANIFEST_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"
)
TREASURY_PATH = (
    REPO_ROOT
    / "dopey_data"
    / "real"
    / "raw"
    / "macro_context"
    / "treasury_yield_curve.csv"
)
CROSS_ASSET_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "raw" / "cross_asset" / "cross_asset_daily.csv"
)
CROSS_ASSET_MANIFEST_PATH = (
    REPO_ROOT
    / "dopey_data"
    / "real"
    / "manifests"
    / "cross_asset_context_manifest.json"
)
NEWS_EVENTS_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "raw" / "news" / "news_events.jsonl"
)
NEWS_MANIFEST_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "manifests" / "news_context_manifest.json"
)
CROSS_ASSET_SNAPSHOT_ROOT = (
    REPO_ROOT / "dopey_data" / "real" / "raw" / "cross_asset" / "snapshots"
)
NEWS_SNAPSHOT_ROOT = REPO_ROOT / "dopey_data" / "real" / "raw" / "news" / "snapshots"
NEWS_EVENT_LEDGER_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "raw" / "news" / "news_event_ledger.jsonl"
)

STRUCTURE_PATH = ARTIFACT_ROOT / "multi_timeframe_structure.jsonl"
FUNDAMENTAL_PATH = ARTIFACT_ROOT / "equity_fundamental_confirmation.jsonl"
THESIS_PATH = ARTIFACT_ROOT / "equity_swing_theses.jsonl"
LEVERAGED_ETF_PLAN_PATH = ARTIFACT_ROOT / "leveraged_etf_swing_plans.jsonl"
CONTRACT_PATH = ARTIFACT_ROOT / "strategic_option_contracts.jsonl"
MISSED_TRADE_PATH = ARTIFACT_ROOT / "missed_trade_events.jsonl"
STRATEGY_CANDIDATE_PATH = ARTIFACT_ROOT / "reverse_engineered_strategy_candidates.jsonl"
FINGERPRINT_PATH = ARTIFACT_ROOT / "past_trade_strategy_fingerprints.jsonl"
CROSS_ASSET_REGIME_PATH = ARTIFACT_ROOT / "cross_asset_regime.json"
NEWS_INTELLIGENCE_PATH = ARTIFACT_ROOT / "news_intelligence.json"
CONTEXT_EVIDENCE_GATE_PATH = ARTIFACT_ROOT / "context_evidence_gate.json"
CONTEXT_DECISION_LEDGER_PATH = ARTIFACT_ROOT / "context_decision_ledger.jsonl"
CONTEXT_OUTCOME_LEDGER_PATH = ARTIFACT_ROOT / "context_outcome_ledger.jsonl"
SUMMARY_PATH = ARTIFACT_ROOT / "equity_first_swing_summary.json"
REPORT_PATH = REPORTS_DIR / "DOPEY_EQUITY_FIRST_MULTI_TIMEFRAME_SWING_REPORT.md"


def run_equity_first_swing_engine() -> dict[str, Any]:
    decision_time = datetime.now(timezone.utc)
    decision_ledger_repair = repair_context_decision_ledger(
        CONTEXT_DECISION_LEDGER_PATH
    )
    context_evidence_gate = build_context_evidence_gate(
        CROSS_ASSET_SNAPSHOT_ROOT,
        NEWS_SNAPSHOT_ROOT,
        NEWS_EVENT_LEDGER_PATH,
        CONTEXT_DECISION_LEDGER_PATH,
        CONTEXT_OUTCOME_LEDGER_PATH,
    )
    _write_json(CONTEXT_EVIDENCE_GATE_PATH, context_evidence_gate)
    history_result = validate_default_history_dataset()
    dataset_status = str(history_result["dataset_status"])
    if dataset_status != "valid_real_dataset":
        raise ValueError(
            f"equity-first swing engine requires valid real history: dataset_status={dataset_status}"
        )
    histories = group_history_bars(list(history_result["bars_loaded"]))
    if "SPY" not in histories:
        raise ValueError(
            "equity-first swing engine requires SPY history for relative-strength confirmation"
        )

    market_as_of_date = date.fromisoformat(str(histories["SPY"][-1]["date"]))
    earnings_snapshot = resolve_earnings_snapshot(
        EARNINGS_ROOT,
        market_as_of_date,
    )
    option_snapshot = resolve_option_snapshot(
        REPO_ROOT,
        CHAIN_ROOT,
        OPTIONS_MANIFEST_PATH,
        market_as_of_date,
        decision_time,
    )

    fundamental_snapshot = resolve_fundamental_snapshot(
        FUNDAMENTALS_PATH,
        market_as_of_date,
    )
    fundamentals = score_fundamental_snapshot(
        fundamental_snapshot["rows"],
        market_as_of_date,
    )
    earnings = load_earnings_dates(earnings_snapshot["path"])
    chains = (
        load_option_chain_snapshot(option_snapshot["path"], market_as_of_date)
        if option_snapshot["path"] is not None
        else {}
    )
    short_rate = load_short_rate(TREASURY_PATH, decision_time.date())
    backtest_trade_evidence = resolve_default_backtest_trade_ledger()
    emitted_signals, fingerprints = build_trade_evidence(
        iter_verified_trade_records(backtest_trade_evidence)
    )
    cross_asset_rows, cross_asset_manifest = load_cross_asset_snapshot(
        CROSS_ASSET_PATH, CROSS_ASSET_MANIFEST_PATH
    )
    news_events, news_manifest = load_news_snapshot(
        NEWS_EVENTS_PATH, NEWS_MANIFEST_PATH
    )
    macro_summary = run_macro_context_gate()
    if macro_summary.get("macro_status") != "macro_context_computed":
        raise ValueError(
            f"validated macro context is required: macro_status={macro_summary.get('macro_status')}"
        )
    validated_macro = load_macro_lanes()
    if validated_macro.get("macro_status") != "macro_lanes_validated":
        raise ValueError(
            f"validated macro lanes are required: macro_status={validated_macro.get('macro_status')}"
        )
    treasury_rows = list(validated_macro["lanes"].get("treasury_yield_curve.csv", []))
    cross_asset_regime = build_cross_asset_regime(
        cross_asset_rows, macro_summary, treasury_rows, decision_time.date()
    )
    news_intelligence = build_news_intelligence(news_events, decision_time)
    symbols = sorted(symbol for symbol in fundamentals if symbol in histories)
    structures: list[dict[str, Any]] = []
    theses: list[dict[str, Any]] = []
    contracts: list[dict[str, Any]] = []
    for symbol in symbols:
        structure = analyze_multi_timeframe_structure(symbol, histories[symbol])
        structures.append(structure)
        theme = str(fundamentals[symbol]["theme"])
        sector_symbol = SECTOR_ETF_BY_THEME.get(theme)
        sector_rows = histories.get(sector_symbol) if sector_symbol else None
        technical = technical_confirmation(
            histories[symbol], histories["SPY"], sector_rows, structure
        )
        earnings_date = earnings.get(symbol)
        equity_thesis = {
            **build_equity_swing_thesis(
                symbol,
                histories[symbol],
                structure,
                technical,
                fundamentals[symbol],
                earnings_date,
            ),
            "earnings_evidence": build_earnings_evidence(
                earnings_snapshot,
                symbol,
                earnings_date,
            ),
        }
        thesis = apply_external_context(
            equity_thesis,
            theme,
            cross_asset_regime,
            news_intelligence,
            context_evidence_gate,
        )
        theses.append(thesis)
        contracts.append(
            select_strategic_contracts(thesis, chains.get(symbol, []), short_rate)
        )

    leveraged_etf_plans = build_leveraged_etf_swing_plans(theses, histories)

    retrospective = build_retrospective_events(
        {symbol: histories[symbol] for symbol in symbols},
        emitted_signals,
        5,
        10,
    )
    missed = missed_trade_events(retrospective)
    candidates = mine_strategy_candidates(retrospective, "2021-12-31")

    _write_jsonl(STRUCTURE_PATH, structures)
    _write_jsonl(FUNDAMENTAL_PATH, [fundamentals[symbol] for symbol in symbols])
    _write_jsonl(THESIS_PATH, theses)
    _write_jsonl(LEVERAGED_ETF_PLAN_PATH, leveraged_etf_plans)
    _write_jsonl(CONTRACT_PATH, contracts)
    _write_jsonl(MISSED_TRADE_PATH, missed)
    _write_jsonl(STRATEGY_CANDIDATE_PATH, candidates)
    _write_jsonl(FINGERPRINT_PATH, fingerprints)
    _write_json(CROSS_ASSET_REGIME_PATH, cross_asset_regime)
    _write_json(NEWS_INTELLIGENCE_PATH, news_intelligence)
    decision_records = build_context_decision_records(
        theses,
        cross_asset_regime,
        news_intelligence,
        context_evidence_gate,
        decision_time.isoformat(),
    )
    appended_decision_count = append_context_decision_records(
        CONTEXT_DECISION_LEDGER_PATH, decision_records
    )
    all_decisions = load_jsonl_records(CONTEXT_DECISION_LEDGER_PATH, "decision_id")
    existing_outcomes = load_jsonl_records(CONTEXT_OUTCOME_LEDGER_PATH, "decision_id")
    matured_outcomes = build_matured_context_outcomes(
        all_decisions,
        histories,
        {str(record["decision_id"]) for record in existing_outcomes},
        max(row["date"] for rows in histories.values() for row in rows),
    )
    appended_outcome_count = append_outcome_records(
        CONTEXT_OUTCOME_LEDGER_PATH, matured_outcomes
    )
    context_evidence_gate = {
        **context_evidence_gate,
        "context_decision_ledger_count": int(
            context_evidence_gate["context_decision_ledger_count"]
        )
        + appended_decision_count,
        "context_outcome_ledger_count": int(
            context_evidence_gate["context_outcome_ledger_count"]
        )
        + appended_outcome_count,
    }
    _write_json(CONTEXT_EVIDENCE_GATE_PATH, context_evidence_gate)

    summary = build_summary(
        history_result,
        structures,
        theses,
        leveraged_etf_plans,
        contracts,
        retrospective,
        missed,
        candidates,
        fingerprints,
        short_rate,
        cross_asset_regime,
        news_intelligence,
        cross_asset_manifest,
        news_manifest,
        context_evidence_gate,
        decision_ledger_repair,
        appended_decision_count,
        appended_outcome_count,
        fundamental_snapshot,
        earnings_snapshot,
        option_snapshot,
        backtest_trade_evidence,
    )
    _write_json(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        render_report(summary, theses, leveraged_etf_plans, contracts, candidates),
        encoding="utf-8",
    )
    return summary


def build_summary(
    history_result: dict[str, Any],
    structures: list[dict[str, Any]],
    theses: list[dict[str, Any]],
    leveraged_etf_plans: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    retrospective: list[dict[str, Any]],
    missed: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    fingerprints: list[dict[str, Any]],
    short_rate: float,
    cross_asset_regime: dict[str, Any],
    news_intelligence: dict[str, Any],
    cross_asset_manifest: dict[str, Any],
    news_manifest: dict[str, Any],
    context_evidence_gate: dict[str, Any],
    decision_ledger_repair: dict[str, int],
    appended_decision_count: int,
    appended_outcome_count: int,
    fundamental_snapshot: FundamentalSnapshot,
    earnings_snapshot: EarningsSnapshot,
    option_snapshot: OptionSnapshot,
    backtest_trade_evidence: VerifiedLedgerResolution,
) -> dict[str, Any]:
    actionable = [thesis for thesis in theses if thesis["trade_intent"] != "no_trade"]
    selected = [
        contract
        for contract in contracts
        if contract["selection_status"] == "tracked_contracts_selected"
    ]
    leveraged_actionable = [
        plan
        for plan in leveraged_etf_plans
        if plan.get("plan_status") == "actionable_shadow_leveraged_etf_plan"
    ]
    leveraged_preferred = preferred_leveraged_etf_plans(leveraged_actionable)
    cleared = [
        candidate
        for candidate in candidates
        if candidate["candidate_status"] == "shadow_candidate_cleared_two_era_screen"
    ]
    blocker_counts: dict[str, int] = {}
    for contract in contracts:
        reason = str(contract.get("block_reason", ""))
        if reason:
            blocker_counts[reason] = blocker_counts.get(reason, 0) + 1
    input_fingerprint = {
        "history_reproducibility_hash": history_result["summary"][
            "reproducibility_hash"
        ],
        "fundamentals_sha256": fundamental_snapshot["sha256"],
        "fundamentals_snapshot_date": fundamental_snapshot["snapshot_date"],
        "fundamentals_snapshot_row_count": fundamental_snapshot[
            "snapshot_row_count"
        ],
        "fundamentals_future_row_count_excluded": fundamental_snapshot[
            "future_row_count_excluded"
        ],
        "earnings_snapshot_date": earnings_snapshot["snapshot_date"],
        "earnings_sha256": earnings_snapshot["sha256"],
        "earnings_symbol_count": earnings_snapshot["symbol_count"],
        "earnings_source_labels": list(earnings_snapshot["source_labels"]),
        "treasury_sha256": _file_sha256(TREASURY_PATH),
        "backtest_trades_sha256": backtest_trade_evidence["resolved_sha256"],
        "backtest_trades_source_sha256": backtest_trade_evidence["source_sha256"],
        "backtest_trades_resolved_sha256": backtest_trade_evidence[
            "resolved_sha256"
        ],
        "backtest_trades_recovery_manifest_sha256": backtest_trade_evidence.get(
            "recovery_manifest_sha256", ""
        ),
        "backtest_trades_resolution_status": backtest_trade_evidence["status"],
        "backtest_trades_incident_recovery_used": backtest_trade_evidence[
            "incident_recovery_used"
        ],
        "backtest_trades_verified_record_count": backtest_trade_evidence[
            "verified_record_hash_count"
        ],
        "cross_asset_sha256": _file_sha256(CROSS_ASSET_PATH),
        "news_events_sha256": _file_sha256(NEWS_EVENTS_PATH),
        "option_snapshot_status": option_snapshot["status"],
        "option_snapshot_date": option_snapshot["snapshot_date"],
        "options_manifest_sha256": option_snapshot["manifest_sha256"],
        "combined_chain_sha256": option_snapshot["combined_chain_sha256"],
        "manifest_chain_file_count": option_snapshot["manifest_chain_file_count"],
        "manifest_chain_row_count": option_snapshot["manifest_chain_row_count"],
        "chain_file_count": option_snapshot["chain_file_count"],
        "chain_row_count": option_snapshot["chain_row_count"],
    }
    summary: dict[str, Any] = {
        "artifact_type": "equity_first_multi_timeframe_swing_summary",
        "engine_version": "equity_first_mtf_cross_asset_news_swing_v4",
        "run_status": "paper_research_complete",
        "as_of_date": max(str(thesis["as_of_date"]) for thesis in theses)
        if theses
        else "",
        "dataset_status": history_result["dataset_status"],
        "equity_symbol_count": len(theses),
        "complete_structure_count": sum(
            structure["structure_status"] == "complete" for structure in structures
        ),
        "confirmed_daily_channel_count": _channel_count(structures, "daily"),
        "confirmed_weekly_channel_count": _channel_count(structures, "weekly"),
        "confirmed_monthly_channel_count": _channel_count(structures, "monthly"),
        "actionable_shadow_thesis_count": len(actionable),
        "actionable_symbols": [str(thesis["symbol"]) for thesis in actionable],
        "leveraged_etf_swing": {
            "supported_pair_count": len(
                {str(plan["pair_id"]) for plan in leveraged_etf_plans}
            ),
            "supported_product_count": len(leveraged_etf_plans),
            "actionable_plan_count": len(leveraged_actionable),
            "actionable_trade_symbols": [
                str(plan["trade_symbol"]) for plan in leveraged_actionable
            ],
            "preferred_actionable_plan_count": len(leveraged_preferred),
            "preferred_actionable_trade_symbols": [
                str(plan["trade_symbol"]) for plan in leveraged_preferred
            ],
            "analysis_symbols": sorted(
                {str(plan["analysis_symbol"]) for plan in leveraged_etf_plans}
            ),
            "product_categories": sorted(
                {str(plan["product_category"]) for plan in leveraged_etf_plans}
            ),
            "chart_authority_policy": "underlying_or_declared_benchmark_proxy_only",
            "bearish_construction": "long_inverse_etf_shares_no_direct_short_sale",
            "maximum_holding_sessions": 5,
            "paper_twin_required": True,
        },
        "strategic_contract_selection_count": len(selected),
        "selected_contract_symbols": [str(contract["symbol"]) for contract in selected],
        "contract_blocker_counts": blocker_counts,
        "fundamental_snapshot_evidence": {
            "status": fundamental_snapshot["point_in_time_status"],
            "snapshot_date": fundamental_snapshot["snapshot_date"],
            "source_row_count": fundamental_snapshot["source_row_count"],
            "snapshot_row_count": fundamental_snapshot["snapshot_row_count"],
            "in_universe_symbol_count": fundamental_snapshot[
                "in_universe_symbol_count"
            ],
            "historical_row_count_excluded": fundamental_snapshot[
                "historical_row_count_excluded"
            ],
            "future_row_count_excluded": fundamental_snapshot[
                "future_row_count_excluded"
            ],
            "maximum_staleness_calendar_days": fundamental_snapshot[
                "maximum_staleness_calendar_days"
            ],
            "future_observation_consumed": False,
        },
        "earnings_snapshot_evidence": {
            "snapshot_date": earnings_snapshot["snapshot_date"],
            "snapshot_symbol_count": earnings_snapshot["symbol_count"],
            "source_labels": list(earnings_snapshot["source_labels"]),
            "covered_thesis_count": sum(
                thesis.get("earnings_evidence", {}).get("symbol_covered") is True
                for thesis in theses
            ),
            "unresolved_thesis_count": sum(
                thesis.get("earnings_evidence", {}).get("symbol_covered") is not True
                for thesis in theses
            ),
            "missing_symbol_is_no_event_claimed": False,
        },
        "option_snapshot_evidence": {
            "status": option_snapshot["status"],
            "snapshot_date": option_snapshot["snapshot_date"],
            "manifest_created_at": option_snapshot["manifest_created_at"],
            "manifest_chain_file_count": option_snapshot[
                "manifest_chain_file_count"
            ],
            "manifest_chain_row_count": option_snapshot[
                "manifest_chain_row_count"
            ],
            "chain_file_count": option_snapshot["chain_file_count"],
            "chain_row_count": option_snapshot["chain_row_count"],
            "blocker": option_snapshot["blocker"],
            "equity_direction_dependency": False,
            "contract_selection_dependency": True,
        },
        "retrospective_observation_count": len(retrospective),
        "qualified_missed_trade_count": len(missed),
        "reverse_engineered_candidate_count": len(candidates),
        "two_era_shadow_candidate_count": len(cleared),
        "two_era_shadow_candidate_ids": [
            str(candidate["candidate_id"]) for candidate in cleared
        ],
        "past_trade_strategy_fingerprint_count": len(fingerprints),
        "backtest_trade_evidence": {
            "status": backtest_trade_evidence["status"],
            "integrity_policy_version": backtest_trade_evidence[
                "integrity_policy_version"
            ],
            "source_sha256": backtest_trade_evidence["source_sha256"],
            "resolved_sha256": backtest_trade_evidence["resolved_sha256"],
            "incident_recovery_used": backtest_trade_evidence[
                "incident_recovery_used"
            ],
            "record_count": backtest_trade_evidence["record_count"],
            "verified_record_hash_count": backtest_trade_evidence[
                "verified_record_hash_count"
            ],
            "authoritative_evidence": backtest_trade_evidence[
                "authoritative_evidence"
            ],
        },
        "cross_asset_context": {
            "dataset_status": cross_asset_manifest["dataset_status"],
            "series_count": cross_asset_regime["series_count"],
            "asset_classes": cross_asset_regime["asset_classes"],
            "risk_appetite_score": cross_asset_regime["risk_appetite_score"],
            "inflation_pressure_score": cross_asset_regime["inflation_pressure_score"],
            "growth_impulse_score": cross_asset_regime["growth_impulse_score"],
            "systemic_stress_score": cross_asset_regime["systemic_stress_score"],
            "series_quality": cross_asset_regime["series_quality"],
            "treasury_curve_state": cross_asset_regime["treasury_curve"]["curve_state"],
            "treasury_spread_2s10s_pct": cross_asset_regime["treasury_curve"][
                "spread_2s10s_pct"
            ],
        },
        "news_context": {
            "pipeline_status": news_manifest["pipeline_status"],
            "source_count_staged": news_manifest["source_count_staged"],
            "official_source_count_staged": news_manifest[
                "official_source_count_staged"
            ],
            "event_count": news_intelligence["event_count"],
            "fresh_7d_event_count": news_intelligence["fresh_7d_event_count"],
            "corroborated_alert_count": news_intelligence["corroborated_alert_count"],
            "news_risk_tone_score": news_intelligence["news_risk_tone_score"],
            "future_event_rejected_count": news_intelligence[
                "future_event_rejected_count"
            ],
            "theme_risk_tone_scores": news_intelligence["theme_risk_tone_scores"],
        },
        "external_context_veto_count": sum(
            thesis["thesis_status"] == "no_trade_external_context_veto"
            for thesis in theses
        ),
        "context_evidence_gate": context_evidence_gate,
        "context_decision_ledger": {
            "path": str(CONTEXT_DECISION_LEDGER_PATH),
            "records_appended_this_run": appended_decision_count,
            "outcome_status": "pending_forward_outcome",
            "repair": decision_ledger_repair,
            "outcomes_appended_this_run": appended_outcome_count,
            "velocity": build_context_decision_velocity(theses),
        },
        "direction_authority": {
            "stock_technicals_weight": 0.78,
            "stock_fundamentals_weight": 0.22,
            "options_data_weight": 0.0,
            "options_role": "strike_expiry_and_contract_quality_selection_after_equity_direction",
        },
        "timeframe_policy": {
            "daily": 0.45,
            "weekly": 0.35,
            "monthly": 0.20,
            "intraday": "unavailable_no_local_intraday_history_not_synthesized",
        },
        "risk_free_rate": round(short_rate, 8),
        "reverse_engineering_policy": "retrospective labels_fixed_interpretable_rules_train_validation_split_shadow_only",
        "input_fingerprint": input_fingerprint,
        "limitations": [
            "Daily OHLCV is resampled to weekly and monthly; no local intraday bars are available.",
            "Fundamentals and option chains are point-in-time snapshots, not survivorship-bias-free historical panels.",
            "Cross-asset futures are continuous provider series and may contain roll discontinuities.",
            "Continuous-futures discontinuities are flagged and latest suspect moves are excluded, but contract-level roll data remains unavailable.",
            "News classification uses headline metadata and deterministic rules; it is not a verified causal or sentiment model.",
            "Past backtest fingerprints are model-priced and are not real option-chain profitability evidence.",
            "Reverse-engineered rules are hypotheses and cannot self-promote into allocation or execution.",
        ],
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order_authority": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def render_report(
    summary: dict[str, Any],
    theses: list[dict[str, Any]],
    leveraged_etf_plans: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> str:
    actionable = [thesis for thesis in theses if thesis["trade_intent"] != "no_trade"]
    selected = [
        contract
        for contract in contracts
        if contract["selection_status"] == "tracked_contracts_selected"
    ]
    leveraged_actionable = [
        plan
        for plan in leveraged_etf_plans
        if plan.get("plan_status") == "actionable_shadow_leveraged_etf_plan"
    ]
    cleared = [
        candidate
        for candidate in candidates
        if candidate["candidate_status"] == "shadow_candidate_cleared_two_era_screen"
    ]
    thesis_lines = [
        f"- {record['symbol']}: {record['trade_intent']}; setup={record['setup_type']}; "
        f"R/R={record['reward_risk_ratio']}; target={record['target_price']}; invalidation={record['invalidation_price']}"
        for record in actionable
    ] or [
        "- No symbol cleared every technical, fundamental, structure, and reward/risk gate."
    ]
    contract_lines = [
        f"- {record['symbol']}: {record['primary_contract']['expiry']} {record['primary_contract']['option_type']} "
        f"{record['primary_contract']['strike']}; delta={record['primary_contract']['delta']}; "
        f"score={record['primary_contract']['contract_score']}"
        for record in selected
    ] or [
        "- No strategic contract cleared the earnings, DTE, quote, liquidity, and payoff gates."
    ]
    leveraged_lines = [
        f"- {record['trade_symbol']} via {record['analysis_symbol']} charts: "
        f"direction={record['exposure_direction']}; daily target={record['daily_leverage_multiple']}x; "
        f"max hold={record['expected_hold_trading_days']} sessions"
        for record in leveraged_actionable
    ] or ["- No leveraged or inverse ETF plan cleared its underlying-chart gates."]
    candidate_lines = [
        f"- {record['candidate_id']}: train lift={record['train_precision_lift']}; "
        f"validation lift={record['validation_precision_lift']}; shadow only"
        for record in cleared
    ] or ["- No reverse-engineered rule cleared the minimum two-era shadow screen."]
    return "\n".join(
        [
            "# DOPEY Equity-First Multi-Timeframe Swing Engine",
            "",
            f"Status: `{summary['run_status']}`  ",
            f"As of: `{summary['as_of_date']}`  ",
            f"Reproducibility hash: `{summary['reproducibility_hash']}`",
            "",
            "## Result",
            "",
            f"The engine analyzed {summary['equity_symbol_count']} stocks with daily/weekly/monthly structure, "
            f"produced {summary['actionable_shadow_thesis_count']} actionable shadow theses, and selected "
            f"{summary['strategic_contract_selection_count']} strategically tracked option contract(s).",
            "",
            "Direction is now stock-first: 78% technical confirmation, 22% fundamental confirmation, and 0% option data. "
            "Options can select strike/expiry/contract quality only after the equity direction is fixed.",
            "Leveraged ETF direction is analysis-symbol-first: the ETF price is never the thesis, and bearish "
            "exposure uses long inverse shares instead of a direct short sale.",
            "Cross-asset and news context can confirm, contradict, or jointly veto a setup but receive zero primary direction weight.",
            "",
            "## Point-in-time snapshot integrity",
            "",
            f"- Fundamentals: {summary['fundamental_snapshot_evidence']['status']} on "
            f"{summary['fundamental_snapshot_evidence']['snapshot_date']}; "
            f"selected rows={summary['fundamental_snapshot_evidence']['snapshot_row_count']}; "
            f"future rows excluded={summary['fundamental_snapshot_evidence']['future_row_count_excluded']}; "
            "maximum staleness=0 calendar days.",
            f"- Options: {summary['option_snapshot_evidence']['status']}; manifest files verified="
            f"{summary['option_snapshot_evidence']['manifest_chain_file_count']}; "
            f"manifest rows verified={summary['option_snapshot_evidence']['manifest_chain_row_count']}; "
            f"frontier files={summary['option_snapshot_evidence']['chain_file_count']}; "
            f"frontier rows={summary['option_snapshot_evidence']['chain_row_count']}.",
            "- Option evidence has zero stock-direction weight and remains strategic tracking only with no order authority.",
            "",
            "## Cross-asset and news coverage",
            "",
            f"- Cross-asset series: {summary['cross_asset_context']['series_count']} across "
            f"{', '.join(summary['cross_asset_context']['asset_classes'])}.",
            f"- Risk appetite={summary['cross_asset_context']['risk_appetite_score']}; "
            f"inflation pressure={summary['cross_asset_context']['inflation_pressure_score']}; "
            f"systemic stress={summary['cross_asset_context']['systemic_stress_score']}.",
            f"- Cross-asset quality: usable={summary['cross_asset_context']['series_quality']['usable_count']}; "
            f"blocked={summary['cross_asset_context']['series_quality']['blocked_count']}; "
            f"historical discontinuities flagged={summary['cross_asset_context']['series_quality']['historical_discontinuity_count']}.",
            "- Treasury context includes the current 3m/2y/5y/10y/30y curve, 2s10s/3m10y/5s30s slopes, "
            "daily yield changes, and ZN/ZB momentum.",
            f"- News events={summary['news_context']['event_count']} from "
            f"{summary['news_context']['source_count_staged']} staged sources "
            f"({summary['news_context']['official_source_count_staged']} official).",
            f"- Fresh 7-day events={summary['news_context']['fresh_7d_event_count']}; "
            f"corroborated risk alerts={summary['news_context']['corroborated_alert_count']}; "
            f"context vetoes={summary['external_context_veto_count']}.",
            f"- Future headlines rejected at decision time: {summary['news_context']['future_event_rejected_count']}.",
            f"- Context evidence gate: {summary['context_evidence_gate']['evidence_status']}; "
            f"joint snapshot days={summary['context_evidence_gate']['joint_snapshot_day_count']}; "
            "snapshot history is telemetry rather than a duration gate; positive promotion and sizing remain disabled.",
            f"- Forward context decisions appended this run: {summary['context_decision_ledger']['records_appended_this_run']}; "
            "outcomes remain pending until their holding windows mature.",
            "- News sources: Federal Reserve, SEC, CFTC, EIA official RSS feeds and GDELT DOC 2 global coverage.",
            "",
            "## Actionable shadow theses",
            "",
            *thesis_lines,
            "",
            "## Strategically tracked contracts",
            "",
            *contract_lines,
            "",
            "## Leveraged and inverse ETF swing plans",
            "",
            f"Supported pairs: {summary['leveraged_etf_swing']['supported_pair_count']}; "
            f"products: {summary['leveraged_etf_swing']['supported_product_count']}; "
            f"analysis symbols: {len(summary['leveraged_etf_swing']['analysis_symbols'])}.",
            *leveraged_lines,
            "",
            "## Reverse-engineered rule screen",
            "",
            f"Retrospective observations: {summary['retrospective_observation_count']}; "
            f"qualified missed swings: {summary['qualified_missed_trade_count']}.",
            *candidate_lines,
            "",
            "## Guardrails and limitations",
            "",
            "- All output is paper research. Live trading, broker connectivity, sizing, and orders remain blocked.",
            "- Pivots are usable only after confirmation; weekly and monthly bars are resampled from validated daily history.",
            "- Intraday structure remains honestly unavailable because no local intraday dataset was supplied.",
            "- Reverse-engineered rules are shadow hypotheses, not promoted strategies or edge claims.",
            "- Past option backtest fingerprints remain model-priced, not quote-priced real option-chain evidence.",
            "",
            "## Artifact paths",
            "",
            f"- `{STRUCTURE_PATH}`",
            f"- `{FUNDAMENTAL_PATH}`",
            f"- `{THESIS_PATH}`",
            f"- `{LEVERAGED_ETF_PLAN_PATH}`",
            f"- `{CONTRACT_PATH}`",
            f"- `{MISSED_TRADE_PATH}`",
            f"- `{STRATEGY_CANDIDATE_PATH}`",
            f"- `{FINGERPRINT_PATH}`",
            f"- `{CROSS_ASSET_REGIME_PATH}`",
            f"- `{NEWS_INTELLIGENCE_PATH}`",
            f"- `{CONTEXT_EVIDENCE_GATE_PATH}`",
            f"- `{CONTEXT_DECISION_LEDGER_PATH}`",
            f"- `{CONTEXT_OUTCOME_LEDGER_PATH}`",
            f"- `{SUMMARY_PATH}`",
            "",
        ]
    )


def _channel_count(structures: list[dict[str, Any]], timeframe: str) -> int:
    return sum(
        record.get("channel", {}).get("channel_status") == "confirmed"
        for structure in structures
        for record in structure.get("timeframes", [])
        if record.get("timeframe") == timeframe
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records
    )
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
