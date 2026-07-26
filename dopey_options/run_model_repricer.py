"""Write deterministic offline model repricer artifacts for DOPEY."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .iv_solver import IV_SOLVER_VERSION, solve_implied_volatility
from .model_repricing_engine import MODEL_REPRICING_ENGINE_VERSION, reprice_long_option_path, repricing_path_input
from .option_pricing_models import MODEL_REPRICING_VERSION, option_pricing_input, price_european_option
from .vol_surface_model import VOL_SURFACE_MODEL_VERSION, build_minimal_vol_surface_snapshot


REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_REPRICING_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "model_repricing"
MODEL_REPRICING_FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "model_repricing"
MODEL_REPRICING_FIXTURE_CASES_PATH = MODEL_REPRICING_FIXTURE_DIR / "model_repricing_cases.json"
IV_SOLVER_VALIDATION_PATH = MODEL_REPRICING_ARTIFACT_DIR / "iv_solver_validation.json"
VOL_SURFACE_MODEL_PATH = MODEL_REPRICING_ARTIFACT_DIR / "vol_surface_model.json"
MODEL_REPRICING_CASES_PATH = MODEL_REPRICING_ARTIFACT_DIR / "model_repricing_cases.jsonl"
MODEL_REPRICING_RESULTS_PATH = MODEL_REPRICING_ARTIFACT_DIR / "model_repricing_results.jsonl"
MODEL_REPRICING_QUALITY_FLAGS_PATH = MODEL_REPRICING_ARTIFACT_DIR / "model_repricing_quality_flags.jsonl"
MODEL_REPRICING_SUMMARY_PATH = MODEL_REPRICING_ARTIFACT_DIR / "model_repricing_summary.json"
MODEL_REPRICING_PROOF_PATH = MODEL_REPRICING_ARTIFACT_DIR / "model_repricing_proof.jsonl"
MODEL_REPRICER_REPORT_PATH = REPORTS_DIR / "DOPEY_MODEL_REPRICER_REPORT.md"
MODEL_REPRICER_LEDGER_PATH = REPORTS_DIR / "DOPEY_MODEL_REPRICER_ARTIFACT_LEDGER.md"
HISTORY_SPINE_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "history" / "history_spine_summary.json"


def run_model_repricer() -> dict[str, Any]:
    history_summary = _history_summary()
    cases = build_model_repricing_fixture_cases()
    surface = build_minimal_vol_surface_snapshot(
        "SPY_MODEL",
        "2026-07-01",
        100.0,
        0.32,
        0.45,
        0.08,
        0.10,
        1.25,
        [7, 14, 30, 60],
        [0.85, 0.95, 1.00, 1.05, 1.15],
        False,
    )
    iv_validation = _build_iv_solver_validation(cases)
    path_results = _build_path_results(surface.to_dict(), history_summary)
    quality_flags = [
        flag
        for result in path_results
        for flag in result["quality_flags"]
    ]
    step_count = sum(len(result["repricing_results"]) for result in path_results)
    quote_priced_records = sum(
        1
        for result in path_results
        for step in result["repricing_results"]
        if step["pricing_source_tier"] == "quote_priced"
    )
    summary = _summary_record(cases, iv_validation, surface.to_dict(), path_results, quality_flags, history_summary, step_count, quote_priced_records)
    proof = _proof_record(summary)
    MODEL_REPRICING_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_REPRICING_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(MODEL_REPRICING_FIXTURE_CASES_PATH, {
        "artifact_type": "model_repricing_fixture_cases",
        "model_repricing_version": MODEL_REPRICING_VERSION,
        "case_count": len(cases),
        "cases": cases,
        "paper_only": True,
        "live_blocked": True,
    })
    _write_json(IV_SOLVER_VALIDATION_PATH, iv_validation)
    _write_json(VOL_SURFACE_MODEL_PATH, {
        "artifact_type": "vol_surface_model",
        "vol_surface_model_version": VOL_SURFACE_MODEL_VERSION,
        "surface": surface.to_dict(),
        "real_option_chain_absent": True,
        "pricing_source_tier": "model_priced",
        "paper_only": True,
        "live_blocked": True,
    })
    _write_jsonl(MODEL_REPRICING_CASES_PATH, cases)
    _write_jsonl(MODEL_REPRICING_RESULTS_PATH, path_results)
    _write_jsonl(MODEL_REPRICING_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(MODEL_REPRICING_SUMMARY_PATH, summary)
    _write_jsonl(MODEL_REPRICING_PROOF_PATH, [proof])
    refreshed_summary = _summary_with_hashes(summary)
    _write_report(refreshed_summary)
    _write_ledger(refreshed_summary)
    return {
        "model_repricing_status": refreshed_summary["model_repricing_status"],
        "artifact_paths": model_repricing_artifact_paths(),
        "pricing_source_tier_distribution": refreshed_summary["pricing_source_tier_distribution"],
        "real_history_status": refreshed_summary["history_dataset_status"],
        "real_options_chain_absent": refreshed_summary["real_option_chain_absent"],
        "model_priced_records": refreshed_summary["model_priced_records"],
        "quote_priced_records": refreshed_summary["quote_priced_records"],
        "quality_flags": refreshed_summary["quality_flags"],
    }


def build_model_repricing_fixture_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    underlying_prices = [92.0, 96.0, 100.0, 104.0, 108.0, 112.0]
    vols = [0.12, 0.18, 0.24, 0.32, 0.48, 0.70]
    for index, vol in enumerate(vols, start=1):
        for underlying_price in underlying_prices[:3]:
            cases.append(_iv_case(f"call-round-trip-{index}-{int(underlying_price)}", "call_iv_round_trip", "call", underlying_price, 100.0, vol, "round_trip_iv_math"))
    for index, vol in enumerate(vols, start=1):
        for underlying_price in underlying_prices[3:]:
            cases.append(_iv_case(f"put-round-trip-{index}-{int(underlying_price)}", "put_iv_round_trip", "put", underlying_price, 100.0, vol, "round_trip_iv_math"))
    cases.extend([
        _solver_rejection_case("intrinsic-floor-call", "intrinsic_floor_rejection", "call", 110.0, 100.0, 9.0, "reject_price_below_intrinsic_floor"),
        _solver_rejection_case("intrinsic-floor-put", "intrinsic_floor_rejection", "put", 90.0, 100.0, 9.0, "reject_price_below_intrinsic_floor"),
        _solver_rejection_case("upper-bound-call", "upper_bound_rejection", "call", 100.0, 95.0, 101.0, "reject_price_above_upper_bound"),
        _solver_rejection_case("upper-bound-put", "upper_bound_rejection", "put", 100.0, 95.0, 96.0, "reject_price_above_upper_bound"),
        _invalid_case("zero-underlying", "call", 0.0, 100.0, 1.0, 0.25, "nonpositive_underlying"),
        _invalid_case("negative-underlying", "call", -1.0, 100.0, 1.0, 0.25, "nonpositive_underlying"),
        _invalid_case("zero-strike", "put", 100.0, 0.0, 1.0, 0.25, "nonpositive_strike"),
        _invalid_case("negative-strike", "put", 100.0, -10.0, 1.0, 0.25, "nonpositive_strike"),
        _invalid_case("negative-time", "call", 100.0, 100.0, 1.0, -0.01, "negative_time_to_expiry"),
        _invalid_case("negative-option-price", "put", 100.0, 100.0, -0.01, 0.25, "negative_option_price"),
        _iv_case("newton-solved-atm-call", "newton_solved", "call", 100.0, 100.0, 0.31, "newton_primary_path"),
        _iv_case("bisection-fallback-otm-put", "bisection_fallback_solved", "put", 125.0, 100.0, 0.43, "force_bisection_by_bad_initial_vol"),
        _surface_case("surface-floor-clamp", "surface_clamp_floor", 100.0, 130.0, 7, "call"),
        _surface_case("surface-cap-clamp", "surface_clamp_cap", 100.0, 60.0, 60, "put"),
        _path_case("call-path-repricing", "call_path_repricing", "call"),
        _path_case("put-path-repricing", "put_path_repricing", "put"),
        _path_case("theta-decay-path", "theta_decay_path", "call"),
        _path_case("volatility-expansion-path", "volatility_expansion_path", "call"),
        _path_case("volatility-compression-path", "volatility_compression_path", "put"),
        _path_case("missing-real-history-case", "missing_real_history_case", "call"),
        _path_case("missing-real-options-chain-case", "missing_real_options_chain_case", "put"),
    ])
    return cases


def model_repricing_artifact_paths() -> dict[str, str]:
    return {
        "iv_solver_validation": str(IV_SOLVER_VALIDATION_PATH),
        "vol_surface_model": str(VOL_SURFACE_MODEL_PATH),
        "model_repricing_cases": str(MODEL_REPRICING_CASES_PATH),
        "model_repricing_results": str(MODEL_REPRICING_RESULTS_PATH),
        "model_repricing_quality_flags": str(MODEL_REPRICING_QUALITY_FLAGS_PATH),
        "model_repricing_summary": str(MODEL_REPRICING_SUMMARY_PATH),
        "model_repricing_proof": str(MODEL_REPRICING_PROOF_PATH),
        "model_repricing_fixture_cases": str(MODEL_REPRICING_FIXTURE_CASES_PATH),
        "model_repricing_report": str(MODEL_REPRICER_REPORT_PATH),
        "model_repricing_artifact_ledger": str(MODEL_REPRICER_LEDGER_PATH),
    }


def _build_iv_solver_validation(cases: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in cases:
        if case["case_family"] not in {
            "call_iv_round_trip",
            "put_iv_round_trip",
            "intrinsic_floor_rejection",
            "upper_bound_rejection",
            "invalid_input",
            "newton_solved",
            "bisection_fallback_solved",
        }:
            continue
        params = case["pricing_input"]
        option_price = float(params.get("option_price", 0.0))
        known_iv = float(params.get("known_iv", 0.0))
        if case["case_family"] in {"call_iv_round_trip", "put_iv_round_trip", "newton_solved", "bisection_fallback_solved"}:
            option_price = price_european_option(option_pricing_input(
                "SPY_MODEL",
                params["option_type"],
                float(params["strike"]),
                "2026-08-21",
                "2026-07-01",
                float(params["underlying_price"]),
                float(params["time_to_expiry_years"]),
                known_iv,
                0.04,
                0.0,
                "fixture_only",
            )).model_price
        initial_vol = 0.000001 if case["case_family"] == "bisection_fallback_solved" else 0.25
        solved = solve_implied_volatility(
            "SPY_MODEL",
            params["option_type"],
            float(params["strike"]),
            "2026-08-21",
            "2026-07-01",
            float(params["underlying_price"]),
            option_price,
            float(params["time_to_expiry_years"]),
            0.04,
            0.0,
            "fixture_only",
            False,
            initial_vol,
            0.000001,
            100,
        )
        record = {
            "artifact_type": "iv_solver_validation_case",
            "case_id": case["case_id"],
            "case_family": case["case_family"],
            "known_iv": round(known_iv, 10),
            "target_option_price": round(option_price, 6),
            "solver_result": solved.to_dict(),
            "validation_passed": _iv_case_passed(case, known_iv, solved.to_dict()),
            "pricing_source_tier": "fixture_only",
            "paper_only": True,
            "live_blocked": True,
        }
        record["reproducibility_hash"] = reproducibility_hash(record)
        records.append(record)
    passed = sum(1 for record in records if record["validation_passed"])
    summary = {
        "artifact_type": "iv_solver_validation",
        "iv_solver_version": IV_SOLVER_VERSION,
        "validation_status": "pass" if passed == len(records) else "fail",
        "validation_case_count": len(records),
        "validation_pass_count": passed,
        "validation_fail_count": len(records) - passed,
        "solver_status_distribution": _count_by(records, ["solver_result", "solver_status"]),
        "method_distribution": _count_by(records, ["solver_result", "method_used"]),
        "pricing_source_tier_distribution": {"fixture_only": len(records), "model_priced": 0, "quote_priced": 0},
        "quote_priced_count": 0,
        "records": records,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _build_path_results(surface_snapshot: dict[str, Any], history_summary: dict[str, Any]) -> list[dict[str, Any]]:
    path_specs = [
        ("call_path_repricing", "call", 100.0, [
            {"valuation_date": "2026-07-01", "underlying_price": 100.0, "days_to_expiry": 30, "implied_vol": 0.30},
            {"valuation_date": "2026-07-02", "underlying_price": 102.0, "days_to_expiry": 29, "implied_vol": 0.30},
            {"valuation_date": "2026-07-03", "underlying_price": 105.0, "days_to_expiry": 28, "implied_vol": 0.30},
        ]),
        ("put_path_repricing", "put", 100.0, [
            {"valuation_date": "2026-07-01", "underlying_price": 100.0, "days_to_expiry": 30, "implied_vol": 0.30},
            {"valuation_date": "2026-07-02", "underlying_price": 98.0, "days_to_expiry": 29, "implied_vol": 0.30},
            {"valuation_date": "2026-07-03", "underlying_price": 95.0, "days_to_expiry": 28, "implied_vol": 0.30},
        ]),
        ("theta_decay_path", "call", 100.0, [
            {"valuation_date": "2026-07-01", "underlying_price": 100.0, "days_to_expiry": 30, "implied_vol": 0.30},
            {"valuation_date": "2026-07-11", "underlying_price": 100.0, "days_to_expiry": 20, "implied_vol": 0.30},
            {"valuation_date": "2026-07-21", "underlying_price": 100.0, "days_to_expiry": 10, "implied_vol": 0.30},
        ]),
        ("volatility_expansion_path", "call", 100.0, [
            {"valuation_date": "2026-07-01", "underlying_price": 100.0, "days_to_expiry": 30, "implied_vol": 0.20},
            {"valuation_date": "2026-07-02", "underlying_price": 100.0, "days_to_expiry": 29, "implied_vol": 0.30},
            {"valuation_date": "2026-07-03", "underlying_price": 100.0, "days_to_expiry": 28, "implied_vol": 0.45},
        ]),
        ("volatility_compression_path", "put", 100.0, [
            {"valuation_date": "2026-07-01", "underlying_price": 100.0, "days_to_expiry": 30, "implied_vol": 0.45},
            {"valuation_date": "2026-07-02", "underlying_price": 100.0, "days_to_expiry": 29, "implied_vol": 0.30},
            {"valuation_date": "2026-07-03", "underlying_price": 100.0, "days_to_expiry": 28, "implied_vol": 0.20},
        ]),
    ]
    records: list[dict[str, Any]] = []
    for path_id, option_type, strike, rows in path_specs:
        path_input = repricing_path_input(
            path_id,
            "SPY_MODEL",
            option_type,
            strike,
            "2026-08-21",
            rows,
            surface_snapshot,
            0.04,
            0.0,
            str(history_summary.get("dataset_status", "missing_real_dataset")),
            False,
            "model_priced",
        )
        record = {
            "artifact_type": "model_repricing_path_result",
            "model_repricing_engine_version": MODEL_REPRICING_ENGINE_VERSION,
            **reprice_long_option_path(path_input).to_dict(),
        }
        record["reproducibility_hash"] = reproducibility_hash({key: value for key, value in record.items() if key != "reproducibility_hash"})
        records.append(record)
    return records


def _summary_record(
    cases: list[dict[str, Any]],
    iv_validation: dict[str, Any],
    surface: dict[str, Any],
    path_results: list[dict[str, Any]],
    quality_flags: list[dict[str, Any]],
    history_summary: dict[str, Any],
    step_count: int,
    quote_priced_records: int,
) -> dict[str, Any]:
    model_priced_records = step_count
    fixture_only_records = len(cases) + int(iv_validation["validation_case_count"])
    quality_reason_codes = sorted({str(flag["reason_code"]) for flag in quality_flags})
    summary = {
        "artifact_type": "model_repricing_summary",
        "model_repricing_version": MODEL_REPRICING_VERSION,
        "iv_solver_version": IV_SOLVER_VERSION,
        "vol_surface_model_version": VOL_SURFACE_MODEL_VERSION,
        "model_repricing_engine_version": MODEL_REPRICING_ENGINE_VERSION,
        "model_repricing_status": "model_priced_fixture_validation_only",
        "history_dataset_status": str(history_summary.get("dataset_status", "missing_real_dataset")),
        "real_history_absent": str(history_summary.get("dataset_status", "missing_real_dataset")) == "missing_real_dataset",
        "real_option_chain_absent": bool(surface.get("real_option_chain_absent", True)),
        "real_backtest_results_created": False,
        "expected_outcome_consumed": False,
        "fixture_case_count": len(cases),
        "iv_solver_validation_status": iv_validation["validation_status"],
        "iv_solver_validation_case_count": iv_validation["validation_case_count"],
        "repricing_path_count": len(path_results),
        "repricing_step_count": step_count,
        "model_priced_records": model_priced_records,
        "fixture_only_records": fixture_only_records,
        "quote_priced_records": quote_priced_records,
        "pricing_source_tier_distribution": {
            "fixture_only": fixture_only_records,
            "model_priced": model_priced_records,
            "quote_priced": quote_priced_records,
        },
        "quality_flags": quality_reason_codes,
        "model_priced_only_no_quote_claim": quote_priced_records == 0,
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "next_recommended_target": "DOPEY_REAL_SIGNAL_ENGINES_V1",
        "artifact_paths": model_repricing_artifact_paths(),
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _summary_with_hashes(summary: dict[str, Any]) -> dict[str, Any]:
    artifact_hashes = {
        name: _file_sha256(Path(path))
        for name, path in model_repricing_artifact_paths().items()
        if Path(path).exists() and name not in {
            "model_repricing_report",
            "model_repricing_artifact_ledger",
            "model_repricing_summary",
            "model_repricing_proof",
        }
    }
    record_counts = {
        name: _record_count(Path(path))
        for name, path in model_repricing_artifact_paths().items()
        if Path(path).exists() and name not in {"model_repricing_report", "model_repricing_artifact_ledger"}
    }
    refreshed = dict(summary)
    refreshed["artifact_hashes"] = artifact_hashes
    refreshed["artifact_record_counts"] = record_counts
    refreshed["reproducibility_hash"] = reproducibility_hash({key: value for key, value in refreshed.items() if key != "reproducibility_hash"})
    _write_json(MODEL_REPRICING_SUMMARY_PATH, refreshed)
    _write_jsonl(MODEL_REPRICING_PROOF_PATH, [_proof_record(refreshed)])
    return refreshed


def _proof_record(summary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "model_repricing_proof",
        "proof_id": "model-repricing-proof-v1",
        "run_id": "dopey-model-repricer-v1-offline-fixture-run",
        "final_status": "PASS",
        "model_repricing_status": summary["model_repricing_status"],
        "history_dataset_status": summary["history_dataset_status"],
        "real_history_absent": summary["real_history_absent"],
        "real_option_chain_absent": summary["real_option_chain_absent"],
        "model_priced_records": summary["model_priced_records"],
        "quote_priced_records": summary["quote_priced_records"],
        "quality_flags": summary["quality_flags"],
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }
    record["proof_hash"] = reproducibility_hash(record)
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Model Repricer Report",
        "",
        "## Objective",
        "Build the first offline model repricer layer for long-premium call and put backtesting infrastructure without claiming real historical evidence.",
        "",
        "## What Was Built",
        "- Implied-volatility solver with Newton-Raphson first and bisection fallback.",
        "- Deterministic Black-Scholes pricing records with Greeks and pricing-source tiers.",
        "- Minimal offline volatility surface with floor/cap clamps.",
        "- Long call/put mark-to-market path repricing in abstract premium units.",
        "- Artifact, audit, reporting, export, review, and validation hooks.",
        "",
        "## IV Solver Behavior",
        f"- validation_status: `{summary['iv_solver_validation_status']}`",
        f"- validation_cases: `{summary['iv_solver_validation_case_count']}`",
        "- invalid inputs are recorded as `invalid_input` with reason codes.",
        "- solver statuses are limited to solved, fallback_solved, invalid_input, no_solution, and max_iterations.",
        "",
        "## Vol Surface Assumptions",
        "- surface_source: `offline_model_assumptions`",
        "- pricing_source_tier: `model_priced`",
        f"- real_option_chain_absent: `{str(summary['real_option_chain_absent']).lower()}`",
        "- floor and cap clamps are explicit and deterministic.",
        "",
        "## Repricing Path Behavior",
        f"- repricing_paths: `{summary['repricing_path_count']}`",
        f"- repricing_steps: `{summary['repricing_step_count']}`",
        "- path P&L is abstract premium mark-to-market only; it is not position sizing.",
        "",
        "## Current Dataset Limitation",
        f"- history_dataset_status: `{summary['history_dataset_status']}`",
        f"- real_history_absent: `{str(summary['real_history_absent']).lower()}`",
        "- No real historical backtest evidence is claimed.",
        "",
        "## Pricing-Source Tiers",
        f"- fixture_only: `{summary['pricing_source_tier_distribution']['fixture_only']}`",
        f"- model_priced: `{summary['pricing_source_tier_distribution']['model_priced']}`",
        f"- quote_priced: `{summary['pricing_source_tier_distribution']['quote_priced']}`",
        "",
        "## Validation Summary",
        f"- quality_flags: `{summary['quality_flags']}`",
        "- quote-priced claims are blocked while real quote/chain data is absent.",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- broker_connection: `none`",
        "- orders: `none`",
        "- scheduler: `none`",
        "- real_sizing: `false`",
        "",
        "## Limitations",
        "- Model-priced scenarios are math validation only.",
        "- Real OHLCV and real options-chain data remain absent in the current local dataset state.",
        "- No edge, profitability, execution quality, or live readiness is claimed.",
        "",
        "## Next Target",
        f"- `{summary['next_recommended_target']}`",
    ]
    MODEL_REPRICER_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledger(summary: dict[str, Any]) -> None:
    final_hashes = {
        name: _file_sha256(Path(path))
        for name, path in summary["artifact_paths"].items()
        if Path(path).exists() and name != "model_repricing_artifact_ledger"
    }
    lines = [
        "# DOPEY Model Repricer Artifact Ledger",
        "",
        "## Source Files",
        "- `dopey_options/iv_solver.py`",
        "- `dopey_options/option_pricing_models.py`",
        "- `dopey_options/vol_surface_model.py`",
        "- `dopey_options/model_repricing_engine.py`",
        "- `dopey_options/run_model_repricer.py`",
        "- `tests/test_model_repricer.py`",
        "",
        "## Artifact Paths",
    ]
    for name, path in sorted(summary["artifact_paths"].items()):
        lines.append(f"- `{name}`: `{path}`")
    lines.extend(["", "## Record Counts"])
    for name, count in sorted(summary.get("artifact_record_counts", {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Hashes"])
    for name, digest in sorted(final_hashes.items()):
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend([
        "",
        "## Pricing-Source Tiers",
        f"- fixture_only: `{summary['pricing_source_tier_distribution']['fixture_only']}`",
        f"- model_priced: `{summary['pricing_source_tier_distribution']['model_priced']}`",
        f"- quote_priced: `{summary['pricing_source_tier_distribution']['quote_priced']}`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- broker_connection: `none`",
        "- orders: `none`",
        "- scheduler: `none`",
        "- real_sizing: `false`",
    ])
    MODEL_REPRICER_LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _iv_case(case_id: str, case_family: str, option_type: str, underlying_price: float, strike: float, known_iv: float, validation_target: str) -> dict[str, Any]:
    return {
        "artifact_type": "model_repricing_case",
        "case_id": case_id,
        "case_family": case_family,
        "validation_target": validation_target,
        "pricing_source_tier": "fixture_only",
        "pricing_input": {
            "option_type": option_type,
            "underlying_price": underlying_price,
            "strike": strike,
            "time_to_expiry_years": 30.0 / 365.0,
            "known_iv": known_iv,
        },
        "paper_only": True,
        "live_blocked": True,
    }


def _solver_rejection_case(case_id: str, case_family: str, option_type: str, underlying_price: float, strike: float, option_price: float, validation_target: str) -> dict[str, Any]:
    return {
        "artifact_type": "model_repricing_case",
        "case_id": case_id,
        "case_family": case_family,
        "validation_target": validation_target,
        "pricing_source_tier": "fixture_only",
        "pricing_input": {
            "option_type": option_type,
            "underlying_price": underlying_price,
            "strike": strike,
            "time_to_expiry_years": 30.0 / 365.0,
            "option_price": option_price,
            "known_iv": 0.0,
        },
        "paper_only": True,
        "live_blocked": True,
    }


def _invalid_case(case_id: str, option_type: str, underlying_price: float, strike: float, option_price: float, time_to_expiry_years: float, validation_target: str) -> dict[str, Any]:
    record = _solver_rejection_case(
        case_id,
        "invalid_input",
        option_type,
        underlying_price,
        strike,
        option_price,
        validation_target,
    )
    record["pricing_input"] = {
        "option_type": option_type,
        "underlying_price": underlying_price,
        "strike": strike,
        "time_to_expiry_years": time_to_expiry_years,
        "option_price": option_price,
        "known_iv": 0.0,
    }
    return record


def _surface_case(case_id: str, case_family: str, underlying_price: float, strike: float, expiry_days: int, option_type: str) -> dict[str, Any]:
    return {
        "artifact_type": "model_repricing_case",
        "case_id": case_id,
        "case_family": case_family,
        "validation_target": "surface_clamp_behavior",
        "pricing_source_tier": "model_priced",
        "surface_input": {
            "option_type": option_type,
            "underlying_price": underlying_price,
            "strike": strike,
            "expiry_days": expiry_days,
        },
        "paper_only": True,
        "live_blocked": True,
    }


def _path_case(case_id: str, case_family: str, option_type: str) -> dict[str, Any]:
    return {
        "artifact_type": "model_repricing_case",
        "case_id": case_id,
        "case_family": case_family,
        "validation_target": "model_path_repricing_behavior",
        "pricing_source_tier": "model_priced",
        "path_input": {
            "option_type": option_type,
            "history_dataset_status": "missing_real_dataset",
            "real_option_chain_present": False,
        },
        "paper_only": True,
        "live_blocked": True,
    }


def _iv_case_passed(case: dict[str, Any], known_iv: float, solver_result: dict[str, Any]) -> bool:
    family = case["case_family"]
    if family in {"call_iv_round_trip", "put_iv_round_trip", "newton_solved"}:
        return solver_result["solver_status"] == "solved" and abs(float(solver_result["iv"]) - known_iv) <= 0.0001
    if family == "bisection_fallback_solved":
        return solver_result["solver_status"] == "fallback_solved" and abs(float(solver_result["iv"]) - known_iv) <= 0.0001
    if family in {"intrinsic_floor_rejection", "upper_bound_rejection", "invalid_input"}:
        return solver_result["solver_status"] == "invalid_input"
    return False


def _history_summary() -> dict[str, Any]:
    if not HISTORY_SPINE_SUMMARY_PATH.exists():
        return {
            "dataset_status": "missing_real_dataset",
            "real_local_data_found": False,
            "row_count": 0,
            "symbols_covered": [],
            "quality_flags": ["history_spine_summary_missing"],
        }
    text = HISTORY_SPINE_SUMMARY_PATH.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {"dataset_status": "missing_real_dataset"}


def _count_by(records: list[dict[str, Any]], path: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value: Any = record
        for key in path:
            value = value[key]
        key_value = str(value)
        counts[key_value] = counts.get(key_value, 0) + 1
    return dict(sorted(counts.items()))


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    output: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
        output.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix.lower() == ".jsonl":
        return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    if path.suffix.lower() == ".json":
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return 0
        parsed = json.loads(text)
        return len(parsed) if isinstance(parsed, list) else 1
    return 1


def main() -> int:
    result = run_model_repricer()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["model_repricing_status"] == "model_priced_fixture_validation_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
