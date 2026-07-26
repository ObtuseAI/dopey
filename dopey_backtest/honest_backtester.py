"""Run DOPEY's honest offline backtester spine."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_research_pipeline.artifact_io import write_jsonl_atomic_streaming
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .backtest_models import (
    BACKTEST_ENGINE_VERSION,
    BacktestProofRecord,
    BacktestQualityFlag,
    BacktestRunResult,
    stable_backtest_hash,
)
from .model_priced_trade_simulator import (
    default_exit_config,
    load_model_repricing_paths,
    max_drawdown_model_units,
    model_unit_equity_curve,
    simulate_trade_intents,
)
from .signal_trade_mapper import load_directional_setup_signals, map_signal_records_to_trade_intents


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "backtest"
BACKTEST_FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "backtest"
SIGNAL_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "signals"
MODEL_REPRICING_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "model_repricing"
HISTORY_SPINE_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "history" / "history_spine_summary.json"
DIRECTIONAL_SETUP_SIGNALS_PATH = SIGNAL_ARTIFACT_DIR / "directional_setup_signals.jsonl"
MODEL_REPRICING_RESULTS_PATH = MODEL_REPRICING_ARTIFACT_DIR / "model_repricing_results.jsonl"
BACKTEST_SIGNAL_INPUTS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_signal_inputs.jsonl"
BACKTEST_TRADE_INTENTS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_intents.jsonl"
BACKTEST_ENTRY_DECISIONS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_entry_decisions.jsonl"
BACKTEST_EXIT_DECISIONS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_exit_decisions.jsonl"
BACKTEST_POSITION_STATES_PATH = BACKTEST_ARTIFACT_DIR / "backtest_position_states.jsonl"
BACKTEST_MARK_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_mark_records.jsonl"
BACKTEST_TRADE_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
BACKTEST_QUALITY_FLAGS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_quality_flags.jsonl"
BACKTEST_RUN_SUMMARY_PATH = BACKTEST_ARTIFACT_DIR / "backtest_run_summary.json"
BACKTEST_PROOF_PATH = BACKTEST_ARTIFACT_DIR / "backtest_proof.jsonl"
BACKTEST_EXPECTED_MATH_CASES_PATH = BACKTEST_FIXTURE_DIR / "backtest_expected_math_cases.json"
BACKTEST_POLICY_CASES_PATH = BACKTEST_FIXTURE_DIR / "backtest_policy_cases.json"
BACKTEST_EXIT_CASES_PATH = BACKTEST_FIXTURE_DIR / "backtest_exit_cases.json"
BACKTEST_REPORT_PATH = REPORTS_DIR / "DOPEY_HONEST_BACKTESTER_REPORT.md"
BACKTEST_LEDGER_PATH = REPORTS_DIR / "DOPEY_HONEST_BACKTESTER_ARTIFACT_LEDGER.md"


def run_honest_backtester() -> dict[str, Any]:
    ensure_upstream_artifacts()
    fixture_bundle = build_backtest_fixture_bundle()
    _write_fixture_files(fixture_bundle)
    history_summary = _load_json(HISTORY_SPINE_SUMMARY_PATH)
    history_dataset_status = str(history_summary.get("dataset_status", "missing_real_dataset"))
    backtest_status = _backtest_status(history_dataset_status)
    signal_records = load_directional_setup_signals(DIRECTIONAL_SETUP_SIGNALS_PATH)
    mapped = map_signal_records_to_trade_intents(signal_records)
    model_paths = load_model_repricing_paths(MODEL_REPRICING_RESULTS_PATH)
    simulated = simulate_trade_intents(
        mapped["trade_intents"],
        model_paths,
        history_dataset_status,
        default_exit_config(),
    )
    quality_flags = _run_quality_flags(history_dataset_status)
    quality_flags.extend(mapped["quality_flags"])
    quality_flags.extend(simulated["quality_flags"])
    trade_intents = mapped["trade_intents"]
    trade_records = simulated["trade_records"]
    pricing_distribution = _distribution(trade_intents, "pricing_source_tier")
    pricing_distribution.setdefault("fixture_only", 0)
    pricing_distribution.setdefault("model_priced", 0)
    pricing_distribution.setdefault("quote_priced", 0)
    data_distribution = _distribution(trade_intents, "data_source_tier")
    equity_curve = model_unit_equity_curve(trade_records)
    total_pnl = round(sum(float(record.get("path_pnl", 0.0)) for record in trade_records), 6)
    average_pnl = round(total_pnl / len(trade_records), 6) if trade_records else 0.0
    quality_reason_codes = sorted({str(flag.get("reason_code", "")) for flag in quality_flags if flag.get("reason_code")})
    summary_seed = BacktestRunResult(
        artifact_type="backtest_run_summary",
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        backtest_status=backtest_status,
        history_dataset_status=history_dataset_status,
        real_history_used=False,
        pricing_source_tier_distribution=pricing_distribution,
        data_source_tier_distribution=data_distribution,
        trade_intent_count=len(trade_intents),
        trade_record_count=len(trade_records),
        long_call_trade_count=sum(1 for record in trade_records if record["candidate_strategy"] == "long_call"),
        long_put_trade_count=sum(1 for record in trade_records if record["candidate_strategy"] == "long_put"),
        no_trade_count=sum(1 for record in trade_intents if record["candidate_strategy"] == "no_trade"),
        blocked_policy_violation_count=sum(1 for flag in quality_flags if flag.get("reason_code") == "blocked_policy_violation"),
        model_priced_trade_count=sum(1 for record in trade_records if record["model_priced"]),
        quote_priced_trade_count=sum(1 for record in trade_records if record["quote_priced"]),
        fixture_only_trade_count=sum(1 for record in trade_records if record["fixture_only"]),
        total_path_pnl_model_units=total_pnl,
        average_path_pnl_model_units=average_pnl,
        max_drawdown_model_units=max_drawdown_model_units(equity_curve),
        win_count=sum(1 for record in trade_records if str(record.get("win_loss_marker", "")).startswith("win_")),
        loss_count=sum(1 for record in trade_records if str(record.get("win_loss_marker", "")).startswith("loss_")),
        quality_flags=quality_reason_codes,
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        next_recommended_target="DOPEY_STATISTICAL_TRUTH_LAYER_V1",
        artifact_paths=backtest_artifact_paths(),
        run_hash="",
    )
    summary = summary_seed.to_dict()
    proof = _proof_record(summary)
    BACKTEST_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(BACKTEST_SIGNAL_INPUTS_PATH, mapped["signal_inputs"])
    _write_jsonl(BACKTEST_TRADE_INTENTS_PATH, trade_intents)
    _write_jsonl(BACKTEST_ENTRY_DECISIONS_PATH, simulated["entry_decisions"])
    _write_jsonl(BACKTEST_EXIT_DECISIONS_PATH, simulated["exit_decisions"])
    _write_jsonl(BACKTEST_POSITION_STATES_PATH, simulated["position_states"])
    _write_jsonl(BACKTEST_MARK_RECORDS_PATH, simulated["mark_records"])
    _write_jsonl(BACKTEST_TRADE_RECORDS_PATH, trade_records)
    _write_jsonl(BACKTEST_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(BACKTEST_RUN_SUMMARY_PATH, summary)
    _write_jsonl(BACKTEST_PROOF_PATH, [proof])
    _write_report(summary)
    _write_ledger(summary)
    return {
        "backtest_status": summary["backtest_status"],
        "history_dataset_status": summary["history_dataset_status"],
        "real_history_used": summary["real_history_used"],
        "pricing_source_tier_distribution": summary["pricing_source_tier_distribution"],
        "data_source_tier_distribution": summary["data_source_tier_distribution"],
        "trade_intent_count": summary["trade_intent_count"],
        "trade_record_count": summary["trade_record_count"],
        "long_call_trade_count": summary["long_call_trade_count"],
        "long_put_trade_count": summary["long_put_trade_count"],
        "no_trade_count": summary["no_trade_count"],
        "model_priced_trade_count": summary["model_priced_trade_count"],
        "quote_priced_trade_count": summary["quote_priced_trade_count"],
        "fixture_only_trade_count": summary["fixture_only_trade_count"],
        "total_path_pnl_model_units": summary["total_path_pnl_model_units"],
        "average_path_pnl_model_units": summary["average_path_pnl_model_units"],
        "max_drawdown_model_units": summary["max_drawdown_model_units"],
        "quality_flags": summary["quality_flags"],
        "not_real_backtest_evidence": summary["not_real_backtest_evidence"],
        "not_profitability_claim": summary["not_profitability_claim"],
        "not_live_ready": summary["not_live_ready"],
        "paper_only": summary["paper_only"],
        "live_blocked": summary["live_blocked"],
        "next_recommended_target": summary["next_recommended_target"],
        "artifact_paths": backtest_artifact_paths(),
    }


def ensure_upstream_artifacts() -> None:
    if not DIRECTIONAL_SETUP_SIGNALS_PATH.exists():
        from dopey_analysis.run_real_signal_engines import run_real_signal_engines

        run_real_signal_engines()
    if not MODEL_REPRICING_RESULTS_PATH.exists():
        from dopey_options.run_model_repricer import run_model_repricer

        run_model_repricer()


def backtest_artifact_paths() -> dict[str, str]:
    return {
        "backtest_signal_inputs": str(BACKTEST_SIGNAL_INPUTS_PATH),
        "backtest_trade_intents": str(BACKTEST_TRADE_INTENTS_PATH),
        "backtest_entry_decisions": str(BACKTEST_ENTRY_DECISIONS_PATH),
        "backtest_exit_decisions": str(BACKTEST_EXIT_DECISIONS_PATH),
        "backtest_position_states": str(BACKTEST_POSITION_STATES_PATH),
        "backtest_mark_records": str(BACKTEST_MARK_RECORDS_PATH),
        "backtest_trade_records": str(BACKTEST_TRADE_RECORDS_PATH),
        "backtest_quality_flags": str(BACKTEST_QUALITY_FLAGS_PATH),
        "backtest_run_summary": str(BACKTEST_RUN_SUMMARY_PATH),
        "backtest_proof": str(BACKTEST_PROOF_PATH),
        "backtest_expected_math_cases": str(BACKTEST_EXPECTED_MATH_CASES_PATH),
        "backtest_policy_cases": str(BACKTEST_POLICY_CASES_PATH),
        "backtest_exit_cases": str(BACKTEST_EXIT_CASES_PATH),
        "honest_backtester_report": str(BACKTEST_REPORT_PATH),
        "honest_backtester_artifact_ledger": str(BACKTEST_LEDGER_PATH),
    }


def build_backtest_fixture_bundle() -> dict[str, Any]:
    expected_cases = _expected_math_cases()
    policy_cases = _policy_cases()
    exit_cases = _exit_cases()
    expected_record = _fixture_record("backtest_expected_math_cases", expected_cases)
    policy_record = _fixture_record("backtest_policy_cases", policy_cases)
    exit_record = _fixture_record("backtest_exit_cases", exit_cases)
    return {
        "expected_math_cases": expected_record,
        "policy_cases": policy_record,
        "exit_cases": exit_record,
    }


def _expected_math_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(1, 9):
        cases.append(_fixture_case(f"long-call-entry-{index:03d}", "long_call_entry", "long_call", "long_call", "model_priced_premium_units"))
        cases.append(_fixture_case(f"long-put-entry-{index:03d}", "long_put_entry", "long_put", "long_put", "model_priced_premium_units"))
        cases.append(_fixture_case(f"model-pnl-{index:03d}", "model_priced_pnl", "long_call" if index % 2 else "long_put", "long_call" if index % 2 else "long_put", "path_pnl_is_exit_minus_entry"))
    return cases


def _policy_cases() -> list[dict[str, Any]]:
    templates = [
        ("no-trade", "no_trade", "no_trade", "none", "neutral_setup_no_trade"),
        ("spread-rejection", "spread_rejection", "long_call", "vertical_spread", "unsupported_option_structure"),
        ("short-vol-rejection", "short_vol_rejection", "long_call", "short_vol", "disallowed_short_vol_created"),
        ("naked-selling-rejection", "naked_selling_rejection", "long_put", "naked_short_put", "disallowed_naked_selling_created"),
        ("same-day-churn-rejection", "same_day_churn_rejection", "long_call", "long_call", "disallowed_same_day_churn_allowed"),
        ("broker-rejection", "broker_rejection", "long_call", "long_call", "disallowed_broker_required"),
        ("real-sizing-rejection", "real_sizing_rejection", "long_put", "long_put", "disallowed_real_sizing_used"),
    ]
    cases: list[dict[str, Any]] = []
    for offset in range(1, 5):
        for slug, family, strategy, structure, reason_code in templates:
            cases.append(_fixture_case(f"{slug}-{offset:03d}", family, strategy, structure, reason_code))
    return cases


def _exit_cases() -> list[dict[str, Any]]:
    templates = [
        ("premium-stop", "premium_stop", "long_call", "long_call", "premium_stop"),
        ("premium-target", "premium_target", "long_put", "long_put", "premium_target"),
        ("time-stop", "time_stop", "long_call", "long_call", "time_stop"),
        ("missing-real-history", "missing_real_history", "long_put", "long_put", "missing_real_history_fixture_validation_only"),
        ("missing-real-options-chain", "missing_real_options_chain", "long_call", "long_call", "missing_real_option_chain"),
    ]
    cases: list[dict[str, Any]] = []
    for offset in range(1, 4):
        for slug, family, strategy, structure, reason_code in templates:
            cases.append(_fixture_case(f"{slug}-{offset:03d}", family, strategy, structure, reason_code))
    return cases


def _fixture_record(artifact_type: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    record = {
        "artifact_type": artifact_type,
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "case_count": len(cases),
        "case_family_distribution": dict(sorted(Counter(case["case_family"] for case in cases).items())),
        "fixture_only": True,
        "model_priced": True,
        "quote_priced": False,
        "real_history_used": False,
        "real_option_chain_used": False,
        "not_real_backtest_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "cases": cases,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _fixture_case(case_id: str, case_family: str, candidate_strategy: str, option_structure: str, expected_reason_code: str) -> dict[str, Any]:
    record = {
        "case_id": case_id,
        "case_family": case_family,
        "candidate_strategy": candidate_strategy,
        "option_structure": option_structure,
        "expected_reason_code": expected_reason_code,
        "fixture_only": True,
        "model_priced": True,
        "quote_priced": False,
        "real_history_used": False,
        "real_option_chain_used": False,
        "not_real_backtest_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["case_hash"] = stable_backtest_hash(record)
    return record


def _run_quality_flags(history_dataset_status: str) -> list[dict[str, Any]]:
    flags = [
        _quality_flag_dict(
            "backtest-fixture-model-validation-only",
            "warning",
            "fixture_model_validation_only",
            "honest backtester is running fixture/model validation only",
            "fixture_only",
            False,
            "fixture_only",
        ),
        _quality_flag_dict(
            "backtest-no-real-evidence",
            "warning",
            "not_real_backtest_evidence",
            "real OHLCV and real options-chain validation are missing; no real backtest validity is claimed",
            "fixture_only",
            False,
            "fixture_only",
        ),
        _quality_flag_dict(
            "backtest-no-profitability-claim",
            "warning",
            "not_profitability_claim",
            "model-unit P&L is not a profitability claim",
            "model_priced",
            True,
            "fixture_only",
        ),
        _quality_flag_dict(
            "backtest-no-live-ready-claim",
            "warning",
            "not_live_ready",
            "offline fixture/model validation is not live readiness",
            "fixture_only",
            False,
            "fixture_only",
        ),
        _quality_flag_dict(
            "backtest-real-option-chain-absent",
            "warning",
            "missing_real_option_chain",
            "real options chain is absent; quote-priced records remain zero",
            "fixture_only",
            False,
            "fixture_only",
        ),
    ]
    if history_dataset_status != "valid_real_dataset":
        flags.extend([
            _quality_flag_dict(
                "backtest-real-history-absent",
                "warning",
                "missing_real_history",
                "history spine did not provide valid real OHLCV",
                "fixture_only",
                False,
                "missing_real_history",
            ),
            _quality_flag_dict(
                "backtest-validation-only",
                "warning",
                "missing_real_history_fixture_validation_only",
                "backtester outputs are fixture/model validation only while real history is missing",
                "fixture_only",
                False,
                "missing_real_history",
            ),
        ])
    return flags


def _quality_flag_dict(
    flag_id: str,
    severity: str,
    reason_code: str,
    message: str,
    pricing_source_tier: str,
    model_priced: bool,
    data_source_tier: str,
) -> dict[str, Any]:
    flag = BacktestQualityFlag(
        artifact_type="backtest_quality_flag",
        flag_id=flag_id,
        severity=severity,
        symbol="",
        signal_id="",
        reason_code=reason_code,
        message=message,
        pricing_source_tier=pricing_source_tier,
        data_source_tier=data_source_tier,
        real_history_used=False,
        real_option_chain_used=False,
        fixture_only=True,
        model_priced=model_priced,
        quote_priced=False,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        flag_hash="",
    )
    return flag.to_dict()


def _proof_record(summary: dict[str, Any]) -> dict[str, Any]:
    record = BacktestProofRecord(
        artifact_type="backtest_proof",
        proof_id="dopey-honest-backtester-v1-proof",
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        backtest_status=str(summary["backtest_status"]),
        history_dataset_status=str(summary["history_dataset_status"]),
        real_history_used=bool(summary["real_history_used"]),
        trade_intent_count=int(summary["trade_intent_count"]),
        trade_record_count=int(summary["trade_record_count"]),
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        no_broker=True,
        no_credentials=True,
        no_scheduler=True,
        no_real_sizing=True,
        no_orders=True,
        paper_only=True,
        live_blocked=True,
        next_recommended_target="DOPEY_STATISTICAL_TRUTH_LAYER_V1",
        proof_hash="",
    )
    return record.to_dict()


def _backtest_status(history_dataset_status: str) -> str:
    if history_dataset_status == "valid_real_dataset":
        return "valid_real_history_backtest_ready"
    return "missing_real_history_fixture_validation_only"


def _distribution(records: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        counter[str(record.get(field_name, "missing"))] += 1
    return dict(sorted(counter.items()))


def _write_fixture_files(fixture_bundle: dict[str, Any]) -> None:
    BACKTEST_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(BACKTEST_EXPECTED_MATH_CASES_PATH, fixture_bundle["expected_math_cases"])
    _write_json(BACKTEST_POLICY_CASES_PATH, fixture_bundle["policy_cases"])
    _write_json(BACKTEST_EXIT_CASES_PATH, fixture_bundle["exit_cases"])


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Honest Backtester Report",
        "",
        "## Objective",
        "Build a deterministic paper-only offline backtester spine that consumes computed signal outputs, model repricer marks, history-spine status, and long-call/long-put policy rules.",
        "",
        "## Data-Source Tier Policy",
        "- Fixture/sample/model validation records are labeled fixture_only=true and real_history_used=false.",
        "- local_real_history is not used unless the history spine reports valid_real_dataset.",
        f"- current history_dataset_status: `{summary['history_dataset_status']}`",
        "",
        "## Pricing-Source Tier Policy",
        "- long_call and long_put validation trades use model_priced marks only.",
        "- no_trade records use fixture_only pricing tier.",
        "- quote_priced remains zero because no real options chain is present.",
        "",
        "## Signal-To-Trade Mapping",
        "- bullish directional setup -> long call intent only.",
        "- bearish directional setup -> long put intent only.",
        "- neutral/no-edge setup -> no trade.",
        "",
        "## Long-Call / Long-Put Only Policy",
        "- No spreads, short-volatility structures, naked selling, undefined-risk positions, real sizing, broker dependency, orders, or scheduler loop are created.",
        "- Same-day churn is blocked; current fixture/model path requires at least one holding step.",
        "",
        "## Exit Logic",
        "- premium_stop_pct: `-0.50`",
        "- premium_target_pct: `1.00`",
        "- max_holding_steps: `3`",
        "- exits: premium_stop, premium_target, time_stop, terminal_path_mark, invalid_no_trade_block.",
        "",
        "## Model-Priced P&L Limitations",
        "- P&L is expressed only in abstract premium model units.",
        "- It is not account equity, buying power, real capital sizing, or a profitability claim.",
        "",
        "## Current Missing-Real-History Limitation",
        f"- backtest_status: `{summary['backtest_status']}`",
        f"- real_history_used: `{str(summary['real_history_used']).lower()}`",
        "- Current outputs are not real backtest evidence.",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- not_real_backtest_evidence: `true`",
        "- not_profitability_claim: `true`",
        "- not_live_ready: `true`",
        "- broker_connection: `none`",
        "- credentials: `none`",
        "- scheduler: `none`",
        "- real_sizing: `none`",
        "- live_orders: `false`",
        "",
        "## Validation Summary",
        f"- trade_intent_count: `{summary['trade_intent_count']}`",
        f"- trade_record_count: `{summary['trade_record_count']}`",
        f"- long_call_trade_count: `{summary['long_call_trade_count']}`",
        f"- long_put_trade_count: `{summary['long_put_trade_count']}`",
        f"- no_trade_count: `{summary['no_trade_count']}`",
        f"- pricing_source_tier_distribution: `{summary['pricing_source_tier_distribution']}`",
        f"- data_source_tier_distribution: `{summary['data_source_tier_distribution']}`",
        f"- total_path_pnl_model_units: `{summary['total_path_pnl_model_units']}`",
        f"- max_drawdown_model_units: `{summary['max_drawdown_model_units']}`",
        f"- quality_flags: `{summary['quality_flags']}`",
        "",
        "## Limitations",
        "- No real OHLCV or real options-chain evidence exists in the current run.",
        "- No real edge, backtest validity, profitability, or live readiness is claimed.",
        "- Fixture validation cases are deterministic math/policy checks only.",
        "",
        "## Next Target",
        "- `DOPEY_STATISTICAL_TRUTH_LAYER_V1`",
    ]
    BACKTEST_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledger(summary: dict[str, Any]) -> None:
    paths = backtest_artifact_paths()
    lines = [
        "# DOPEY Honest Backtester Artifact Ledger",
        "",
        "## Source Files",
        "- `dopey_backtest/backtest_models.py`",
        "- `dopey_backtest/signal_trade_mapper.py`",
        "- `dopey_backtest/model_priced_trade_simulator.py`",
        "- `dopey_backtest/honest_backtester.py`",
        "- `dopey_backtest/run_honest_backtester.py`",
        "- `tests/test_honest_backtester.py`",
        "",
        "## Fixture Files",
        f"- `{BACKTEST_EXPECTED_MATH_CASES_PATH}` records=`{_fixture_case_count(BACKTEST_EXPECTED_MATH_CASES_PATH)}` sha256=`{_file_sha256(BACKTEST_EXPECTED_MATH_CASES_PATH)}`",
        f"- `{BACKTEST_POLICY_CASES_PATH}` records=`{_fixture_case_count(BACKTEST_POLICY_CASES_PATH)}` sha256=`{_file_sha256(BACKTEST_POLICY_CASES_PATH)}`",
        f"- `{BACKTEST_EXIT_CASES_PATH}` records=`{_fixture_case_count(BACKTEST_EXIT_CASES_PATH)}` sha256=`{_file_sha256(BACKTEST_EXIT_CASES_PATH)}`",
        "",
        "## Artifact Files",
    ]
    for key in [
        "backtest_signal_inputs",
        "backtest_trade_intents",
        "backtest_entry_decisions",
        "backtest_exit_decisions",
        "backtest_position_states",
        "backtest_mark_records",
        "backtest_trade_records",
        "backtest_quality_flags",
        "backtest_run_summary",
        "backtest_proof",
    ]:
        path = Path(paths[key])
        lines.append(f"- `{path}` records=`{_record_count(path)}` sha256=`{_file_sha256(path)}`")
    lines.extend([
        "",
        "## Record Counts",
        f"- trade_intent_count: `{summary['trade_intent_count']}`",
        f"- trade_record_count: `{summary['trade_record_count']}`",
        f"- long_call_trade_count: `{summary['long_call_trade_count']}`",
        f"- long_put_trade_count: `{summary['long_put_trade_count']}`",
        f"- no_trade_count: `{summary['no_trade_count']}`",
        f"- model_priced_trade_count: `{summary['model_priced_trade_count']}`",
        f"- quote_priced_trade_count: `{summary['quote_priced_trade_count']}`",
        "",
        "## Hashes",
        f"- backtest_run_summary.run_hash: `{summary['run_hash']}`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- not_real_backtest_evidence: `true`",
        "- not_profitability_claim: `true`",
        "- not_live_ready: `true`",
        "- no broker, credentials, scheduler, real sizing, or orders created",
    ])
    BACKTEST_LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"dataset_status": "missing_real_dataset"}
    text = path.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {"dataset_status": "missing_real_dataset"}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    # Streaming + atomic (see real_history_honest_backtester._write_jsonl).
    write_jsonl_atomic_streaming(path, records)


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.suffix.lower() == ".json":
        return 1
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _fixture_case_count(path: Path) -> int:
    if not path.exists():
        return 0
    record = json.loads(path.read_text(encoding="utf-8"))
    return int(record.get("case_count", 0))
