"""Evidence-gated analytical datasets for the native DOPEY desktop surface."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from collections.abc import Callable
from typing import Final, TypedDict, cast


MAX_EQUITY_POINTS: Final[int] = 180
MAX_OPTIONS_POINTS: Final[int] = 420
MAX_TELEMETRY_EVENTS: Final[int] = 240
TELEMETRY_CONTRACT_FIELDS: Final[tuple[str, ...]] = (
    "event_utc",
    "run_id",
    "agent_id",
    "phase",
    "status_transition",
    "input_artifact_hashes",
    "output_artifact_hashes",
    "duration_ms",
    "error",
)


class AnalyticsSource(TypedDict):
    """One bounded local source consumed by the analytics projection."""

    source_id: str
    relative_path: str
    status: str
    sha256: str | None
    detail: str


class AnalyticsError(RuntimeError):
    """Raised when an available analytics artifact violates its contract."""


def _inside_root(repository_root: Path, candidate: Path) -> Path:
    resolved_root = repository_root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise AnalyticsError(
            f"analytics source escapes repository root: root={resolved_root}, path={resolved}"
        )
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source(
    repository_root: Path,
    source_id: str,
    path: Path,
    status: str,
    detail: str,
) -> AnalyticsSource:
    resolved = _inside_root(repository_root, path)
    return AnalyticsSource(
        source_id=source_id,
        relative_path=resolved.relative_to(repository_root.resolve()).as_posix(),
        status=status,
        sha256=_sha256(resolved) if resolved.is_file() and status == "available" else None,
        detail=detail,
    )


def _json_object(path: Path) -> dict[str, object]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalyticsError(f"analytics JSON source is unreadable: path={path}, error={error}") from error
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise AnalyticsError(f"analytics JSON source must be an object: path={path}")
    return cast(dict[str, object], decoded)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error) as error:
        raise AnalyticsError(f"analytics CSV source is unreadable: path={path}, error={error}") from error


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _integer(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _require_paper_boundary(record: dict[str, object], context: str) -> None:
    if record.get("paper_only") is not True or record.get("live_blocked") is not True:
        raise AnalyticsError(
            f"analytics source violates paper-only boundary: context={context}, "
            f"paper_only={record.get('paper_only')}, live_blocked={record.get('live_blocked')}"
        )


def _downsample(rows: list[dict[str, str]], maximum: int) -> list[dict[str, str]]:
    if len(rows) <= maximum:
        return rows
    stride = (len(rows) - 1) / (maximum - 1)
    indexes = sorted({round(index * stride) for index in range(maximum)})
    return [rows[index] for index in indexes]


def _run_directory(repository_root: Path, dossier: dict[str, object]) -> Path:
    raw_path = _text(dossier.get("run_directory"))
    if raw_path is None:
        raise AnalyticsError("latest dossier does not report run_directory")
    candidate = Path(raw_path)
    resolved = _inside_root(repository_root, candidate if candidate.is_absolute() else repository_root / candidate)
    allowed_root = (repository_root / "artifacts" / "dopey" / "runs").resolve()
    if allowed_root not in resolved.parents:
        raise AnalyticsError(
            f"latest dossier run_directory is outside the governed run root: path={resolved}"
        )
    if not resolved.is_dir():
        raise AnalyticsError(f"latest dossier run_directory is missing: path={resolved}")
    return resolved


def _fold_metrics(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if _boolean(row.get("paper_only")) is not True or _boolean(row.get("live_blocked")) is not True:
            raise AnalyticsError(f"fold metric violates paper-only boundary: row={index}")
        output.append(
            {
                "candidate_id": row.get("cohort_id", ""),
                "family": row.get("signal_family", ""),
                "structure": row.get("candidate_strategy", ""),
                "era": row.get("era", ""),
                "sample_count": _integer(row.get("sample_count")),
                "expectancy_model_units": _number(row.get("average_pnl")),
                "net_model_units": _number(row.get("net_pnl")),
                "win_rate": _number(row.get("win_rate")),
                "profit_factor": _number(row.get("profit_factor")),
                "meets_minimum_sample": _boolean(row.get("meets_min_sample")),
            }
        )
    return output


def _robustness(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "candidate_id": row.get("scope", ""),
            "gate_id": row.get("test_id", ""),
            "status": row.get("status", "unknown"),
            "observed": row.get("observed", ""),
            "required": row.get("required", ""),
            "diagnostic_only": _boolean(row.get("diagnostic_only")) is True,
        }
        for row in rows
    ]


def _pareto(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "candidate_id": row.get("candidate_id", ""),
            "trade_count": _integer(row.get("trade_count")),
            "symbol_count": _integer(row.get("symbol_count")),
            "expectancy_model_units": _number(row.get("expectancy_model_units")),
            "stressed_expectancy_model_units": _number(
                row.get("stressed_cost_expectancy_model_units")
            ),
            "max_drawdown_model_units": _number(row.get("max_drawdown_model_units")),
            "tail_loss_p05_model_units": _number(row.get("tail_loss_p05_model_units")),
            "fold_stability": _number(row.get("fold_expectancy_dispersion")),
            "positive_fold_count": _integer(row.get("positive_fold_count")),
            "gate_failure_count": _integer(row.get("gate_failure_count")),
            "eligible": _boolean(row.get("eligible")),
            "evidence_class": row.get("evidence_class", "unknown"),
        }
        for row in rows
    ]


def _equity(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    sampled = _downsample(rows, MAX_EQUITY_POINTS)
    return [
        {
            "date": row.get("date", ""),
            "trade_count": _integer(row.get("trade_count")),
            "gross_model_units": _number(row.get("gross_model_unit_pnl")),
            "cost_model_units": _number(row.get("cost_model_units")),
            "net_model_units": _number(row.get("net_model_unit_pnl")),
            "cumulative_model_units": _number(row.get("cumulative_model_unit_pnl")),
            "drawdown_model_units": _number(row.get("drawdown_model_units")),
        }
        for row in sampled
    ]


def _failure_ranking(failure_modes: dict[str, object]) -> list[dict[str, object]]:
    raw = failure_modes.get("candidate_gate_failures")
    if not isinstance(raw, dict):
        return []
    failures: Counter[str] = Counter()
    for candidate_failures in raw.values():
        if isinstance(candidate_failures, list):
            failures.update(item for item in candidate_failures if isinstance(item, str))
    return [
        {"failure_id": failure_id, "candidate_count": count}
        for failure_id, count in failures.most_common()
    ]


def _evidence_lane(repository_root: Path, sources: list[AnalyticsSource]) -> dict[str, object]:
    dossier_path = repository_root / "artifacts" / "dopey" / "runs" / "latest_dossier.json"
    if not dossier_path.is_file():
        sources.append(_source(repository_root, "latest_dossier", dossier_path, "missing", "No latest dossier is available."))
        return {"status": "unavailable_missing_latest_dossier", "reason": "latest_dossier_missing"}
    dossier = _json_object(dossier_path)
    _require_paper_boundary(dossier, "latest_dossier")
    sources.append(_source(repository_root, "latest_dossier", dossier_path, "available", "Latest governed dossier."))
    run_directory = _run_directory(repository_root, dossier)
    required_files = {
        "fold_metrics": run_directory / "fold_metrics.csv",
        "robustness_tests": run_directory / "robustness_tests.csv",
        "pareto_frontier": run_directory / "pareto_frontier.csv",
        "equity_curve": run_directory / "equity_curve.csv",
        "failure_modes": run_directory / "failure_modes.json",
    }
    missing = [source_id for source_id, path in required_files.items() if not path.is_file()]
    if missing:
        for source_id, path in required_files.items():
            status = "missing" if source_id in missing else "available"
            sources.append(_source(repository_root, source_id, path, status, f"Dossier analytical source is {status}."))
        return {
            "status": "unavailable_incomplete_dossier",
            "reason": f"missing_sources={','.join(missing)}",
        }
    for source_id, path in required_files.items():
        sources.append(_source(repository_root, source_id, path, "available", "Governed dossier analytical source."))
    failure_modes = _json_object(required_files["failure_modes"])
    _require_paper_boundary(failure_modes, "failure_modes")
    selection_risk = dossier.get("selection_risk")
    return {
        "status": "available_diagnostic_only",
        "run_id": dossier.get("run_id"),
        "run_directory": run_directory.relative_to(repository_root.resolve()).as_posix(),
        "evidence_class": "real_underlying_history_model_priced_options_diagnostic_only",
        "paper_only": True,
        "live_blocked": True,
        "not_returns": True,
        "fold_metrics": _fold_metrics(_csv_rows(required_files["fold_metrics"])),
        "robustness_tests": _robustness(_csv_rows(required_files["robustness_tests"])),
        "pareto_frontier": _pareto(_csv_rows(required_files["pareto_frontier"])),
        "equity_curve": _equity(_csv_rows(required_files["equity_curve"])),
        "failure_ranking": _failure_ranking(failure_modes),
        "selection_pressure": {
            "candidate_count": dossier.get("candidate_count"),
            "eligible_candidate_count": dossier.get("eligible_candidate_count"),
            "diagnostic_frontier_count": dossier.get("diagnostic_frontier_count"),
            "trade_count": dossier.get("trade_count"),
            "effective_trials": selection_risk.get("effective_trials") if isinstance(selection_risk, dict) else None,
            "mutation_attempts": selection_risk.get("mutation_attempts_recorded") if isinstance(selection_risk, dict) else None,
            "deflated_sharpe_diagnostic": selection_risk.get("deflated_sharpe_ratio_diagnostic") if isinstance(selection_risk, dict) else None,
        },
    }


def _readiness_lane(repository_root: Path, sources: list[AnalyticsSource]) -> dict[str, object]:
    path = repository_root / "artifacts" / "dopey" / "acceleration" / "readiness_acceleration_plan.json"
    if not path.is_file():
        sources.append(_source(repository_root, "readiness_analytics", path, "missing", "No readiness acceleration plan is available."))
        return {"status": "unavailable_missing_readiness_acceleration_plan", "lanes": []}
    record = _json_object(path)
    _require_paper_boundary(record, "readiness_acceleration_plan")
    sources.append(_source(repository_root, "readiness_analytics", path, "available", "Readiness accrual and governance source."))
    raw_bottlenecks = record.get("bottlenecks")
    lanes: list[dict[str, object]] = []
    if isinstance(raw_bottlenecks, list):
        for index, raw_bottleneck in enumerate(raw_bottlenecks):
            if not isinstance(raw_bottleneck, dict):
                raise AnalyticsError(f"readiness bottleneck must be an object: index={index}")
            bottleneck = cast(dict[str, object], raw_bottleneck)
            eta = bottleneck.get("existing_eta")
            eta_record = cast(dict[str, object], eta) if isinstance(eta, dict) else {}
            lanes.append(
                {
                    "lane_id": bottleneck.get("bottleneck_id"),
                    "priority": bottleneck.get("priority"),
                    "current": bottleneck.get("current"),
                    "required": bottleneck.get("required"),
                    "remaining": bottleneck.get("remaining"),
                    "threshold_unchanged": bottleneck.get("threshold_unchanged") is True,
                    "acceleration": bottleneck.get("acceleration"),
                    "missing_checks": bottleneck.get("missing_checks") if isinstance(bottleneck.get("missing_checks"), list) else [],
                    "estimated_trading_days": eta_record.get("est_trading_days_to_sample_at_current_book"),
                    "estimate_only_not_a_promise": eta_record.get("estimate_only_not_a_promise") is True,
                    "maturity_lag_days": bottleneck.get("estimated_days_at_expanded_cross_section_before_maturity_lag"),
                }
            )
    return {
        "status": record.get("readiness_status"),
        "context_evidence_status": record.get("context_evidence_status"),
        "lanes": lanes,
        "governance": {
            "gate_policy_changed": record.get("gate_policy_changed") is True,
            "removed_gate_ids": record.get("removed_gate_ids") if isinstance(record.get("removed_gate_ids"), list) else [],
            "remaining_thresholds_lowered": record.get("remaining_evidence_thresholds_lowered") is True,
            "reproducibility_hash": record.get("reproducibility_hash"),
        },
        "intake_health": record.get("intake_health") if isinstance(record.get("intake_health"), dict) else {},
    }


def _position_age(as_of: date, raw_date: object) -> int | None:
    text = _text(raw_date)
    if text is None:
        return None
    try:
        return max((as_of - date.fromisoformat(text[:10])).days, 0)
    except ValueError:
        return None


def _iso_date(raw_date: object, *, source: str) -> date | None:
    text = _text(raw_date)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        raise AnalyticsError(f"invalid ISO date in {source}: value={text!r}") from error


def _paper_lane(repository_root: Path, sources: list[AnalyticsSource]) -> dict[str, object]:
    ledger_path = repository_root / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
    if not ledger_path.is_file():
        sources.append(_source(repository_root, "forward_walk_ledger", ledger_path, "missing", "No forward ledger is available."))
        return {"status": "unavailable_missing_forward_ledger", "positions": [], "exposures": []}
    ledger = _json_object(ledger_path)
    sources.append(_source(repository_root, "forward_walk_ledger", ledger_path, "available", "Quote-derived paper ledger."))
    open_positions = ledger.get("open_positions")
    closed_positions = ledger.get("closed_trades")
    if not isinstance(open_positions, list) or not isinstance(closed_positions, list):
        raise AnalyticsError("forward ledger positions must be arrays")
    all_records: list[tuple[str, dict[str, object]]] = []
    for lane, raw_records in (("open", open_positions), ("closed", closed_positions)):
        for index, raw_record in enumerate(raw_records):
            if not isinstance(raw_record, dict) or not all(isinstance(key, str) for key in raw_record):
                raise AnalyticsError(f"forward ledger row must be an object: lane={lane}, index={index}")
            record = cast(dict[str, object], raw_record)
            _require_paper_boundary(record, f"forward_ledger:{lane}:{index}")
            all_records.append((lane, record))
    observed_dates = [
        parsed
        for lane, record in all_records
        if (
            parsed := _iso_date(
                record.get("last_mark_date") or record.get("exit_date") or record.get("entry_date"),
                source=f"forward_ledger:{lane}",
            )
        )
        is not None
    ]
    ledger_as_of = _iso_date(ledger.get("last_marking_date") or ledger.get("last_entry_date"), source="forward_ledger")
    if not observed_dates and ledger_as_of is None:
        raise AnalyticsError("forward ledger has no observable as-of date")
    as_of = max(observed_dates) if observed_dates else cast(date, ledger_as_of)
    exposures: dict[str, dict[str, dict[str, float]]] = {
        "sector": defaultdict(lambda: {"count": 0.0, "entry_premium_units": 0.0}),
        "direction": defaultdict(lambda: {"count": 0.0, "entry_premium_units": 0.0}),
    }
    positions: list[dict[str, object]] = []
    for lane, record in all_records:
        option_type = _text(record.get("option_type")) or "unknown"
        direction = "bullish" if option_type == "call" else "bearish" if option_type == "put" else "unknown"
        sector = _text(record.get("entry_sector")) or "unclassified"
        entry_fill = _number(record.get("entry_fill"))
        if lane == "open":
            for axis, key in (("sector", sector), ("direction", direction)):
                exposures[axis][key]["count"] += 1
                exposures[axis][key]["entry_premium_units"] += entry_fill or 0.0
        positions.append(
            {
                "position_id": record.get("position_id"),
                "symbol": record.get("symbol"),
                "status": lane,
                "structure": record.get("candidate_strategy"),
                "direction": direction,
                "sector": sector,
                "entry_date": record.get("entry_date"),
                "last_mark_date": record.get("last_mark_date") or record.get("exit_date"),
                "age_days": _position_age(as_of, record.get("entry_date")),
                "quote_age_days": _position_age(as_of, record.get("last_mark_date") or record.get("exit_date")),
                "relative_spread": _number(record.get("entry_relative_spread")),
                "entry_fill": entry_fill,
                "last_mark_bid": _number(record.get("last_mark_bid")),
                "path_pnl": _number(record.get("path_pnl")),
                "pricing_source_tier": record.get("pricing_source_tier"),
                "quote_priced": record.get("quote_priced") is True,
            }
        )
    exposure_rows = [
        {
            "axis": axis,
            "key": key,
            "position_count": int(values["count"]),
            "entry_premium_units": round(values["entry_premium_units"], 6),
        }
        for axis, groups in exposures.items()
        for key, values in sorted(groups.items())
    ]
    return {
        "status": "available_quote_derived_paper_only",
        "as_of_date": as_of.isoformat(),
        "open_count": len(open_positions),
        "closed_count": len(closed_positions),
        "closed_required": 100,
        "positions": positions,
        "exposures": exposure_rows,
        "paper_only": True,
        "live_blocked": True,
        "not_real_capital": True,
    }


def _latest_options_directory(repository_root: Path) -> Path | None:
    root = repository_root / "dopey_data" / "real" / "raw" / "options_chains"
    if not root.is_dir():
        return None
    candidates = sorted(path for path in root.iterdir() if path.is_dir())
    return candidates[-1] if candidates else None


def _options_lane(repository_root: Path, sources: list[AnalyticsSource]) -> dict[str, object]:
    calibration_path = repository_root / "artifacts" / "dopey" / "chain_analytics" / "model_iv_calibration_summary.json"
    latest_directory = _latest_options_directory(repository_root)
    if not calibration_path.is_file() or latest_directory is None:
        if not calibration_path.is_file():
            sources.append(_source(repository_root, "iv_calibration", calibration_path, "missing", "IV calibration is missing."))
        return {"status": "unavailable_missing_quote_derived_options_evidence", "surface": []}
    calibration = _json_object(calibration_path)
    _require_paper_boundary(calibration, "iv_calibration")
    sources.append(_source(repository_root, "iv_calibration", calibration_path, "available", "Quote-derived IV calibration."))
    preferred_symbols = ("SPY", "QQQ", "AMD", "NVDA", "AAPL", "TSLA")
    selected_symbol = next(
        (symbol for symbol in preferred_symbols if (latest_directory / f"{symbol}_chain.csv").is_file()),
        None,
    )
    if selected_symbol is None:
        return {"status": "unavailable_no_supported_chain_snapshot", "surface": []}
    chain_path = latest_directory / f"{selected_symbol}_chain.csv"
    sources.append(_source(repository_root, "options_surface", chain_path, "available", "Latest quote-derived chain used for the desktop surface."))
    rows = _csv_rows(chain_path)
    surface: list[dict[str, object]] = []
    for row in rows:
        spot = _number(row.get("underlying_spot"))
        strike = _number(row.get("strike"))
        dte = _integer(row.get("dte_calendar"))
        if spot is None or strike is None or dte is None or dte > 120 or abs(strike / spot - 1.0) > 0.35:
            continue
        bid = _number(row.get("bid"))
        ask = _number(row.get("ask"))
        relative_spread = None
        if bid is not None and ask is not None and ask + bid > 0:
            relative_spread = (ask - bid) / ((ask + bid) / 2)
        surface.append(
            {
                "expiry": row.get("expiry"),
                "dte": dte,
                "option_type": row.get("option_type"),
                "strike": strike,
                "moneyness": strike / spot,
                "bid": bid,
                "ask": ask,
                "mid": _number(row.get("mid")),
                "implied_vol": _number(row.get("implied_vol")),
                "volume": _integer(row.get("volume")),
                "open_interest": _integer(row.get("open_interest")),
                "relative_spread": relative_spread,
            }
        )
        if len(surface) >= MAX_OPTIONS_POINTS:
            break
    multipliers = calibration.get("per_symbol_multipliers")
    multiplier_rows = []
    if isinstance(multipliers, dict):
        for symbol, raw in multipliers.items():
            if isinstance(symbol, str) and isinstance(raw, dict):
                multiplier_rows.append(
                    {
                        "symbol": symbol,
                        "contracts": _integer(raw.get("contracts")),
                        "multiplier": _number(raw.get("multiplier")),
                    }
                )
    multiplier_rows.sort(key=lambda row: cast(int, row["contracts"] or 0), reverse=True)
    return {
        "status": "available_quote_derived_not_edge_evidence",
        "snapshot_date": latest_directory.name,
        "symbol": selected_symbol,
        "available_symbols": [
            path.name.removesuffix("_chain.csv") for path in sorted(latest_directory.glob("*_chain.csv"))
        ],
        "surface": surface,
        "iv_calibration": {
            "status": calibration.get("calibration_status"),
            "current_multiplier": calibration.get("current_multiplier"),
            "recommended_multiplier": calibration.get("recommended_multiplier_median_iv_over_rv"),
            "iv_over_rv_p25": calibration.get("iv_over_rv_p25"),
            "iv_over_rv_p75": calibration.get("iv_over_rv_p75"),
            "premium_error_p25": calibration.get("model_premium_error_pct_p25"),
            "premium_error_median": calibration.get("model_premium_error_pct_median"),
            "premium_error_p75": calibration.get("model_premium_error_pct_p75"),
            "symbols_covered": len(calibration.get("symbols_covered", [])) if isinstance(calibration.get("symbols_covered"), list) else None,
            "multipliers": multiplier_rows[:40],
        },
        "quote_derived": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _gated_json_lane(
    repository_root: Path,
    sources: list[AnalyticsSource],
    source_id: str,
    relative_path: Path,
    missing_status: str,
) -> dict[str, object]:
    path = repository_root / relative_path
    if not path.is_file():
        sources.append(_source(repository_root, source_id, path, "missing", missing_status))
        return {"status": missing_status}
    record = _json_object(path)
    _require_paper_boundary(record, source_id)
    sources.append(_source(repository_root, source_id, path, "available", "Governed analytical capability source."))
    return record


def _ml_lane(repository_root: Path, sources: list[AnalyticsSource]) -> dict[str, object]:
    calibration = _gated_json_lane(
        repository_root,
        sources,
        "forward_calibration",
        Path("artifacts/dopey/vnext/cross_sectional_operational/calibration_summary.json"),
        "unavailable_missing_forward_calibration_contract",
    )
    signal_calibration = _gated_json_lane(
        repository_root,
        sources,
        "signal_calibration",
        Path("artifacts/dopey/signal_calibration/signal_calibration_summary.json"),
        "unavailable_missing_signal_calibration_contract",
    )
    agent_ablation = _gated_json_lane(
        repository_root,
        sources,
        "agent_ablation",
        Path("artifacts/dopey/vnext/cross_sectional_operational/latest_agent_ablation.json"),
        "unavailable_missing_agent_ablation_contract",
    )
    return {
        "calibration": calibration,
        "signal_calibration": signal_calibration,
        "agent_ablation": agent_ablation,
        "conformal": {
            "status": "unavailable_no_timestamped_prediction_target_coverage_contract",
            "required_evidence": [
                "timestamped_predictions",
                "independent_targets",
                "declared_coverage_level",
                "rolling_coverage_observations",
            ],
        },
        "shap": {
            "status": "unavailable_no_feature_model_contract",
            "reason": "No fitted feature model with a governed explainer contract is present.",
        },
        "embeddings": {
            "status": "unavailable_no_embedding_contract",
            "reason": "No governed embedding matrix or label/provenance contract is present.",
        },
        "training": {
            "status": "unavailable_no_iterative_training_telemetry_contract",
            "reason": "DOPEY currently exposes deterministic/statistical research artifacts, not a neural training loop.",
        },
    }


def _telemetry_lane(repository_root: Path, sources: list[AnalyticsSource]) -> dict[str, object]:
    path = repository_root / "artifacts" / "dopey" / "desktop" / "agent_activity_events.jsonl"
    if not path.is_file():
        sources.append(_source(repository_root, "agent_activity_events", path, "missing", "Observed agent event telemetry has not been emitted."))
        return {
            "status": "unavailable_declared_topology_only",
            "reason": "No append-only observed agent activity event stream exists yet.",
            "contract_fields": list(TELEMETRY_CONTRACT_FIELDS),
            "events": [],
            "observed_link_count": 0,
        }
    events: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AnalyticsError(f"agent activity event stream is unreadable: path={path}, error={error}") from error
    for line_index, line in enumerate(lines[-MAX_TELEMETRY_EVENTS:]):
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as error:
            raise AnalyticsError(
                f"agent activity event is invalid JSON: path={path}, line={line_index}, error={error}"
            ) from error
        if not isinstance(decoded, dict):
            raise AnalyticsError(f"agent activity event must be an object: line={line_index}")
        missing = [field for field in TELEMETRY_CONTRACT_FIELDS if field not in decoded]
        if missing:
            raise AnalyticsError(
                f"agent activity event is missing required fields: line={line_index}, fields={missing}"
            )
        events.append(cast(dict[str, object], decoded))
    sources.append(_source(repository_root, "agent_activity_events", path, "available", "Observed append-only agent event telemetry."))
    return {
        "status": "available_observed_events",
        "contract_fields": list(TELEMETRY_CONTRACT_FIELDS),
        "events": events,
        "observed_link_count": len(events),
    }


def _regime_lane(repository_root: Path) -> dict[str, object]:
    snapshot_roots = (
        repository_root / "dopey_data" / "real" / "raw" / "cross_asset" / "snapshots",
        repository_root / "dopey_data" / "real" / "raw" / "news" / "snapshots",
    )
    history: list[dict[str, object]] = []
    for root in snapshot_roots:
        if not root.is_dir():
            continue
        for path in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True)[:24]:
            history.append(
                {
                    "lane": root.parent.name,
                    "snapshot_id": path.name,
                    "file_count": sum(1 for item in path.iterdir() if item.is_file()),
                }
            )
    history.sort(key=lambda row: str(row["snapshot_id"]), reverse=True)
    return {
        "status": "available_provenance_history" if history else "unavailable_no_regime_history_index",
        "history": history[:40],
        "transition_model": {
            "status": "unavailable_no_transition_probability_model",
            "reason": "Snapshot history is provenance telemetry and does not establish a regime transition model.",
        },
        "distribution_drift": {
            "status": "unavailable_no_declared_reference_test_contract",
            "reason": "Freshness is observable; covariate drift requires a declared reference window and statistical test.",
        },
    }


def build_desktop_analytics(repository_root: Path) -> dict[str, object]:
    """Build one read-only analytics projection without inventing missing evidence."""

    resolved_root = repository_root.resolve()
    sources: list[AnalyticsSource] = []
    errors: list[str] = []

    def guarded(lane_id: str, builder: Callable[[], dict[str, object]]) -> dict[str, object]:
        try:
            result = builder()
        except AnalyticsError as error:
            errors.append(f"{lane_id}: {error}")
            return {"status": "unavailable_invalid_source", "reason": str(error)}
        if not isinstance(result, dict):
            raise TypeError(f"analytics lane builder returned a non-object: lane={lane_id}")
        return cast(dict[str, object], result)

    evidence = guarded("evidence", lambda: _evidence_lane(resolved_root, sources))
    readiness = guarded("readiness", lambda: _readiness_lane(resolved_root, sources))
    paper = guarded("paper", lambda: _paper_lane(resolved_root, sources))
    options = guarded("options", lambda: _options_lane(resolved_root, sources))
    machine_learning = guarded("machine_learning", lambda: _ml_lane(resolved_root, sources))
    telemetry = guarded("telemetry", lambda: _telemetry_lane(resolved_root, sources))
    return {
        "schema_version": "dopey-desktop-analytics-v1",
        "status": "available_with_explicit_gaps" if not errors else "available_with_invalid_optional_sources",
        "paper_only": True,
        "live_blocked": True,
        "evidence": evidence,
        "readiness": readiness,
        "paper": paper,
        "options": options,
        "machine_learning": machine_learning,
        "telemetry": telemetry,
        "regime": _regime_lane(resolved_root),
        "sources": sources,
        "errors": errors,
    }
