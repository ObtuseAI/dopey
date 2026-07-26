"""Fail-closed validation for every targeting evidence source."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import cast

from dopey.protocols.identity import canonical_hash
from dopey.strategy_engineering.playbook_scanner import PLAYBOOK_SCAN_VERSION
from dopey.strategy_engineering.playbook_settlement import (
    PLAYBOOK_TRUST_VERSION,
    is_rating_eligible_settlement,
)
from dopey.strategy_engineering.scanner_holdout_fitness import (
    DRIFT_BASELINE_POLICY_VERSION,
    EVENT_DEDUPLICATION_POLICY_VERSION,
    SCANNER_FITNESS_VERSION,
    SOURCE_HASH_POLICY_VERSION,
)
from dopey_core.market_calendar import trading_days_between
from dopey_data.history_models import history_manifest_hash
from dopey_data.history_validator import validate_history_dataset
from dopey_options.model_iv_calibration_contract import (
    MAX_MODEL_IV_CALIBRATION_AGE_SESSIONS,
    MODEL_IV_CALIBRATION_COMPLETE_STATUS,
    MODEL_IV_CALIBRATION_VERSION,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .per_symbol_forecast_skill import iter_jsonl

SOURCE_VALIDATION_VERSION = "dopey-targeting-source-validation-v1"
MAX_SCANNER_FITNESS_AGE_SESSIONS = 5
JsonObject = dict[str, object]
HistoryBars = dict[str, tuple[JsonObject, ...]]


@dataclass(frozen=True)
class ValidatedTargetingSources:
    """Immutable result of validating all evidence before targeting begins."""

    history: HistoryBars
    history_manifest_hash: str
    playbook_settlements: tuple[JsonObject, ...]
    playbook_detections: tuple[JsonObject, ...]
    scanner_fitness: JsonObject
    iv_calibration_summary: JsonObject
    iv_calibration_rows: tuple[JsonObject, ...]
    source_hashes: Mapping[str, str]
    validation_report: JsonObject
    blockers: tuple[JsonObject, ...]


def _blocker(source: str, reason_code: str, detail: str) -> JsonObject:
    return {
        "source": source,
        "reason_code": reason_code,
        "detail": detail,
    }


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> tuple[JsonObject, JsonObject | None]:
    if not path.is_file():
        return {}, _blocker(
            path.name,
            "required_artifact_missing",
            f"required JSON artifact is missing: path={path}",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {}, _blocker(
            path.name,
            "invalid_json_artifact",
            f"unable to parse JSON artifact: path={path}, error={error}",
        )
    if not isinstance(value, dict):
        return {}, _blocker(
            path.name,
            "json_artifact_not_object",
            f"JSON artifact must be an object: path={path}",
        )
    return cast(JsonObject, value), None


def _load_jsonl_rows(
    path: Path,
    source_name: str,
) -> tuple[tuple[JsonObject, ...], JsonObject | None]:
    if not path.is_file():
        return (), _blocker(
            source_name,
            "required_artifact_missing",
            f"required JSONL artifact is missing: path={path}",
        )
    try:
        rows = tuple(iter_jsonl(path))
    except (OSError, UnicodeDecodeError, TypeError, ValueError) as error:
        return (), _blocker(
            source_name,
            "invalid_jsonl_artifact",
            f"unable to parse JSONL artifact: path={path}, error={error}",
        )
    if not rows:
        return (), _blocker(
            source_name,
            "required_artifact_empty",
            f"required JSONL artifact contains no records: path={path}",
        )
    return rows, None


def _validate_history(
    manifest_path: Path,
    history_root: Path,
) -> tuple[HistoryBars, str, JsonObject, tuple[JsonObject, ...]]:
    blockers: list[JsonObject] = []
    raw_manifest, manifest_error = _load_json_object(manifest_path)
    if manifest_error is not None:
        blockers.append(
            _blocker(
                "history",
                str(manifest_error["reason_code"]),
                str(manifest_error["detail"]),
            )
        )
    supplied_hash = raw_manifest.get("manifest_reproducibility_hash")
    expected_hash = history_manifest_hash(raw_manifest) if raw_manifest else ""
    if (
        raw_manifest
        and (
            not isinstance(supplied_hash, str)
            or not supplied_hash
            or supplied_hash != expected_hash
        )
    ):
        blockers.append(
            _blocker(
                "history",
                "manifest_reproducibility_hash_mismatch",
                "history manifest content does not match its declared hash: "
                f"path={manifest_path}",
            )
        )

    try:
        validation = validate_history_dataset(
            manifest_path,
            history_root,
            False,
        )
    except (OSError, TypeError, ValueError) as error:
        blockers.append(
            _blocker(
                "history",
                "history_validator_failed",
                f"authoritative history validator failed: error={error}",
            )
        )
        validation = {
            "dataset_status": "invalid_real_dataset",
            "validation": {},
            "quality_flags": [],
            "bars_loaded": [],
        }

    dataset_status = str(validation.get("dataset_status", ""))
    if dataset_status != "valid_real_dataset":
        blockers.append(
            _blocker(
                "history",
                "history_dataset_not_valid_real_dataset",
                f"authoritative validator status={dataset_status or 'missing'}",
            )
        )
    validation_record = validation.get("validation")
    validation_object = (
        cast(JsonObject, validation_record)
        if isinstance(validation_record, dict)
        else {}
    )
    validated_manifest_hash = validation_object.get(
        "manifest_reproducibility_hash"
    )
    if (
        expected_hash
        and validated_manifest_hash != expected_hash
    ):
        blockers.append(
            _blocker(
                "history",
                "validator_manifest_hash_mismatch",
                "authoritative validator did not bind to the raw manifest hash",
            )
        )

    history: dict[str, list[JsonObject]] = defaultdict(list)
    raw_bars = validation.get("bars_loaded")
    if dataset_status == "valid_real_dataset" and isinstance(raw_bars, list):
        for raw_bar in raw_bars:
            if not isinstance(raw_bar, dict):
                blockers.append(
                    _blocker(
                        "history",
                        "validator_bar_not_object",
                        "authoritative validator returned a non-object bar",
                    )
                )
                break
            symbol = raw_bar.get("symbol")
            if not isinstance(symbol, str) or not symbol.strip():
                blockers.append(
                    _blocker(
                        "history",
                        "validator_bar_missing_symbol",
                        "authoritative validator returned a bar without symbol",
                    )
                )
                break
            history[symbol.upper()].append(cast(JsonObject, raw_bar))
    if dataset_status == "valid_real_dataset" and not history:
        blockers.append(
            _blocker(
                "history",
                "validated_history_empty",
                "authoritative validator returned no usable history bars",
            )
        )

    if blockers:
        history = defaultdict(list)
    immutable_history: HistoryBars = {
        symbol: tuple(
            sorted(rows, key=lambda row: str(row.get("date", "")))
        )
        for symbol, rows in sorted(history.items())
    }
    quality_flags = validation.get("quality_flags")
    reason_codes = sorted(
        {
            str(flag.get("reason_code", ""))
            for flag in quality_flags
            if isinstance(flag, dict) and flag.get("reason_code")
        }
        if isinstance(quality_flags, list)
        else set()
    )
    report: JsonObject = {
        "source_status": (
            "valid_hash_pinned_history"
            if not blockers
            else "blocked_invalid_history"
        ),
        "dataset_status": dataset_status,
        "manifest_reproducibility_hash": (
            expected_hash if not blockers else ""
        ),
        "validation_reproducibility_hash": str(
            validation_object.get("validation_reproducibility_hash", "")
        ),
        "bar_count": sum(len(rows) for rows in immutable_history.values()),
        "symbol_count": len(immutable_history),
        "quality_reason_codes": reason_codes,
    }
    return immutable_history, expected_hash, report, tuple(blockers)


def _settlement_contract_mismatches(record: Mapping[str, object]) -> list[str]:
    mismatches: list[str] = []
    expected_fields: tuple[tuple[str, object], ...] = (
        ("artifact_type", "playbook_settlement"),
        ("rating_policy_version", PLAYBOOK_TRUST_VERSION),
        ("source_playbook_scan_version", PLAYBOOK_SCAN_VERSION),
        ("not_trade_evidence", True),
        ("paper_only", True),
        ("live_blocked", True),
    )
    for key, expected in expected_fields:
        if record.get(key) != expected:
            mismatches.append(key)
    declared_eligible = record.get("rating_eligible")
    computed_eligible = is_rating_eligible_settlement(record)
    if (
        not isinstance(declared_eligible, bool)
        or declared_eligible != computed_eligible
    ):
        mismatches.append("rating_eligible")
    return mismatches


def _validate_playbook_settlements(
    path: Path,
) -> tuple[tuple[JsonObject, ...], JsonObject, tuple[JsonObject, ...]]:
    rows, load_error = _load_jsonl_rows(path, "playbook_settlements")
    blockers: list[JsonObject] = []
    if load_error is not None:
        blockers.append(load_error)
    current_rows: list[JsonObject] = []
    mismatch_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        mismatches = _settlement_contract_mismatches(row)
        if mismatches:
            for field in mismatches:
                mismatch_counts[field] += 1
            continue
        current_rows.append(row)
    if rows and not current_rows:
        blockers.append(
            _blocker(
                "playbook_settlements",
                "no_current_policy_settlements",
                "no settlement row satisfies the current trust, scan, and "
                "paper-only provenance contract",
            )
        )
    report: JsonObject = {
        "source_status": (
            "valid_current_policy_settlements"
            if current_rows and not mismatch_counts
            else (
                "valid_current_policy_with_legacy_rows_excluded"
                if current_rows
                else "blocked_no_current_policy_settlements"
            )
        ),
        "required_rating_policy_version": PLAYBOOK_TRUST_VERSION,
        "required_playbook_scan_version": PLAYBOOK_SCAN_VERSION,
        "total_record_count": len(rows),
        "current_policy_record_count": len(current_rows),
        "excluded_record_count": len(rows) - len(current_rows),
        "mismatched_field_counts": dict(sorted(mismatch_counts.items())),
    }
    return tuple(current_rows), report, tuple(blockers)


def _validate_playbook_detections(
    path: Path,
) -> tuple[tuple[JsonObject, ...], JsonObject]:
    if not path.is_file():
        return (), {
            "source_status": "unavailable_no_detection_ledger",
            "total_record_count": 0,
            "current_policy_record_count": 0,
            "excluded_record_count": 0,
        }
    try:
        rows = tuple(iter_jsonl(path))
    except (OSError, UnicodeDecodeError, TypeError, ValueError) as error:
        return (), {
            "source_status": "degraded_invalid_detection_ledger",
            "error": str(error),
            "total_record_count": 0,
            "current_policy_record_count": 0,
            "excluded_record_count": 0,
        }
    current_rows = tuple(
        row
        for row in rows
        if (
            row.get("source_playbook_scan_version") == PLAYBOOK_SCAN_VERSION
            and row.get("is_trade_signal") is False
            and row.get("paper_only") is True
            and row.get("live_blocked") is True
        )
    )
    return current_rows, {
        "source_status": (
            "valid_current_policy_detections"
            if len(current_rows) == len(rows)
            else "degraded_legacy_detections_excluded"
        ),
        "required_playbook_scan_version": PLAYBOOK_SCAN_VERSION,
        "total_record_count": len(rows),
        "current_policy_record_count": len(current_rows),
        "excluded_record_count": len(rows) - len(current_rows),
    }


def _scanner_contract_mismatches(record: Mapping[str, object]) -> list[str]:
    mismatches: list[str] = []
    expected_fields: tuple[tuple[str, object], ...] = (
        ("artifact_type", "scanner_fitness_evaluation"),
        ("scanner_fitness_version", SCANNER_FITNESS_VERSION),
        (
            "drift_baseline_policy_version",
            DRIFT_BASELINE_POLICY_VERSION,
        ),
        (
            "event_deduplication_policy_version",
            EVENT_DEDUPLICATION_POLICY_VERSION,
        ),
        ("source_hash_policy_version", SOURCE_HASH_POLICY_VERSION),
        ("detector_exception_count", 0),
        ("detector_exception_budget_status", "within_budget"),
        ("sample_sufficient", True),
        ("not_edge_evidence", True),
        ("promotion_allowed", False),
        ("paper_only", True),
        ("live_blocked", True),
    )
    for key, expected in expected_fields:
        if record.get(key) != expected:
            mismatches.append(key)

    exception_counts = record.get("detector_exception_counts")
    if (
        not isinstance(exception_counts, dict)
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in exception_counts.values()
        )
        or sum(
            int(value)
            for value in exception_counts.values()
            if isinstance(value, int) and not isinstance(value, bool)
        )
        != 0
    ):
        mismatches.append("detector_exception_counts")
    source_hash = record.get("source_universe_hash")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        mismatches.append("source_universe_hash")
    score = record.get("score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
        or not 0.0 <= float(score) <= 1.0
    ):
        mismatches.append("score")
    return sorted(set(mismatches))


def _validate_scanner_fitness(
    path: Path,
    observed_at: datetime,
) -> tuple[JsonObject, JsonObject, tuple[JsonObject, ...]]:
    record, load_error = _load_json_object(path)
    blockers: list[JsonObject] = []
    if load_error is not None:
        blockers.append(
            _blocker(
                "scanner_fitness",
                str(load_error["reason_code"]),
                str(load_error["detail"]),
            )
        )
    mismatches = _scanner_contract_mismatches(record) if record else []
    evaluated_at_value = record.get("evaluated_at_utc")
    evaluated_at: datetime | None = None
    if isinstance(evaluated_at_value, str):
        try:
            evaluated_at = datetime.fromisoformat(evaluated_at_value)
        except ValueError:
            mismatches.append("evaluated_at_utc")
    elif record:
        mismatches.append("evaluated_at_utc")
    scanner_age_sessions: int | None = None
    if evaluated_at is not None:
        if evaluated_at.tzinfo is None:
            mismatches.append("evaluated_at_utc_timezone")
        else:
            evaluated_date = evaluated_at.astimezone(timezone.utc).date()
            observed_date = observed_at.astimezone(timezone.utc).date()
            if evaluated_date > observed_date:
                mismatches.append("evaluated_at_utc_in_future")
            else:
                scanner_age_sessions = trading_days_between(
                    evaluated_date,
                    observed_date,
                )
                if scanner_age_sessions > MAX_SCANNER_FITNESS_AGE_SESSIONS:
                    mismatches.append("evaluated_at_utc_freshness")
    mismatches = sorted(set(mismatches))
    if mismatches:
        blockers.append(
            _blocker(
                "scanner_fitness",
                "scanner_contract_mismatch",
                "scanner fitness artifact failed required fields: "
                f"fields={','.join(mismatches)}",
            )
        )
    report: JsonObject = {
        "source_status": (
            "valid_current_scanner_fitness"
            if record and not blockers
            else "blocked_invalid_scanner_fitness"
        ),
        "required_scanner_fitness_version": SCANNER_FITNESS_VERSION,
        "observed_scanner_fitness_version": str(
            record.get("scanner_fitness_version", "")
        ),
        "contract_mismatches": mismatches,
        "detector_exception_count": record.get("detector_exception_count"),
        "detector_exception_budget_status": record.get(
            "detector_exception_budget_status"
        ),
        "sample_sufficient": record.get("sample_sufficient"),
        "evaluated_at_utc": str(evaluated_at_value or ""),
        "age_trading_sessions": scanner_age_sessions,
        "maximum_age_trading_sessions": (
            MAX_SCANNER_FITNESS_AGE_SESSIONS
        ),
    }
    return record if not blockers else {}, report, tuple(blockers)


def _iv_summary_hash_matches(summary: Mapping[str, object]) -> bool:
    supplied = summary.get("reproducibility_hash")
    if not isinstance(supplied, str) or not supplied:
        return False
    payload = {
        key: value
        for key, value in summary.items()
        if key != "reproducibility_hash"
    }
    return supplied == reproducibility_hash(payload)


def _validate_iv_calibration(
    summary_path: Path,
    rows_path: Path,
    observed_at: datetime,
) -> tuple[JsonObject, tuple[JsonObject, ...], JsonObject, tuple[JsonObject, ...]]:
    summary, summary_error = _load_json_object(summary_path)
    rows, rows_error = _load_jsonl_rows(rows_path, "iv_calibration_rows")
    blockers: list[JsonObject] = []
    if summary_error is not None:
        blockers.append(
            _blocker(
                "iv_calibration_summary",
                str(summary_error["reason_code"]),
                str(summary_error["detail"]),
            )
        )
    if rows_error is not None:
        blockers.append(rows_error)

    summary_mismatches: list[str] = []
    expected_fields: tuple[tuple[str, object], ...] = (
        ("artifact_type", "model_iv_calibration_summary"),
        ("model_iv_calibration_version", MODEL_IV_CALIBRATION_VERSION),
        ("calibration_status", MODEL_IV_CALIBRATION_COMPLETE_STATUS),
        ("quote_derived", True),
        ("not_edge_evidence", True),
        ("paper_only", True),
        ("live_blocked", True),
    )
    for key, expected in expected_fields:
        if summary and summary.get(key) != expected:
            summary_mismatches.append(key)
    if summary and not _iv_summary_hash_matches(summary):
        summary_mismatches.append("reproducibility_hash")

    snapshot_value = summary.get("snapshot_date")
    snapshot_date: date | None = None
    if isinstance(snapshot_value, str):
        try:
            snapshot_date = date.fromisoformat(snapshot_value)
        except ValueError:
            summary_mismatches.append("snapshot_date")
    elif summary:
        summary_mismatches.append("snapshot_date")

    observed_date = observed_at.astimezone(timezone.utc).date()
    age_sessions: int | None = None
    if snapshot_date is not None:
        if snapshot_date > observed_date:
            summary_mismatches.append("snapshot_date_in_future")
        else:
            age_sessions = trading_days_between(snapshot_date, observed_date)
            if age_sessions > MAX_MODEL_IV_CALIBRATION_AGE_SESSIONS:
                summary_mismatches.append("snapshot_freshness")

    row_mismatch_counts: dict[str, int] = defaultdict(int)
    row_symbols: set[str] = set()
    for row in rows:
        row_expected_fields: tuple[tuple[str, object], ...] = (
            ("artifact_type", "model_iv_calibration_row"),
            ("model_iv_calibration_version", MODEL_IV_CALIBRATION_VERSION),
            ("snapshot_date", snapshot_value),
            ("quote_derived", True),
            ("paper_only", True),
            ("live_blocked", True),
        )
        for key, expected in row_expected_fields:
            if row.get(key) != expected:
                row_mismatch_counts[key] += 1
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            row_mismatch_counts["symbol"] += 1
        else:
            row_symbols.add(symbol.upper())

    compared_count = summary.get("atm_contracts_compared")
    if (
        summary
        and (
            isinstance(compared_count, bool)
            or not isinstance(compared_count, int)
            or compared_count != len(rows)
        )
    ):
        summary_mismatches.append("atm_contracts_compared")
    covered_symbols = summary.get("symbols_covered")
    if (
        summary
        and (
            not isinstance(covered_symbols, list)
            or any(not isinstance(symbol, str) for symbol in covered_symbols)
            or {str(symbol).upper() for symbol in covered_symbols} != row_symbols
        )
    ):
        summary_mismatches.append("symbols_covered")

    if summary_mismatches:
        blockers.append(
            _blocker(
                "iv_calibration_summary",
                "iv_calibration_summary_contract_mismatch",
                "IV calibration summary failed required fields: "
                f"fields={','.join(sorted(set(summary_mismatches)))}",
            )
        )
    if row_mismatch_counts:
        blockers.append(
            _blocker(
                "iv_calibration_rows",
                "iv_calibration_row_contract_mismatch",
                "IV calibration rows failed required fields: "
                f"fields={','.join(sorted(row_mismatch_counts))}",
            )
        )
    report: JsonObject = {
        "source_status": (
            "valid_current_fresh_iv_calibration"
            if summary and rows and not blockers
            else "blocked_invalid_or_stale_iv_calibration"
        ),
        "required_model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
        "observed_model_iv_calibration_version": str(
            summary.get("model_iv_calibration_version", "")
        ),
        "calibration_status": str(summary.get("calibration_status", "")),
        "snapshot_date": str(snapshot_value or ""),
        "age_trading_sessions": age_sessions,
        "maximum_age_trading_sessions": (
            MAX_MODEL_IV_CALIBRATION_AGE_SESSIONS
        ),
        "row_count": len(rows),
        "summary_contract_mismatches": sorted(set(summary_mismatches)),
        "row_mismatched_field_counts": dict(
            sorted(row_mismatch_counts.items())
        ),
    }
    if blockers:
        return {}, (), report, tuple(blockers)
    return summary, rows, report, ()


def validate_targeting_sources(
    history_root: Path,
    history_manifest_path: Path,
    playbook_detection_path: Path,
    playbook_settlement_path: Path,
    scanner_fitness_path: Path,
    iv_calibration_rows_path: Path,
    iv_calibration_summary_path: Path,
    observed_at: datetime,
) -> ValidatedTargetingSources:
    """Validate and isolate current evidence without consuming stale aliases."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    history, manifest_hash, history_report, history_blockers = (
        _validate_history(history_manifest_path, history_root)
    )
    settlements, settlement_report, settlement_blockers = (
        _validate_playbook_settlements(playbook_settlement_path)
    )
    detections, detection_report = _validate_playbook_detections(
        playbook_detection_path
    )
    scanner, scanner_report, scanner_blockers = _validate_scanner_fitness(
        scanner_fitness_path,
        observed_at,
    )
    iv_summary, iv_rows, iv_report, iv_blockers = _validate_iv_calibration(
        iv_calibration_summary_path,
        iv_calibration_rows_path,
        observed_at,
    )
    blockers = (
        *history_blockers,
        *settlement_blockers,
        *scanner_blockers,
        *iv_blockers,
    )
    source_hashes = {
        "history_manifest": manifest_hash,
        "history_validation": str(
            history_report.get("validation_reproducibility_hash", "")
        ),
        "playbook_detections": _sha256(playbook_detection_path),
        "playbook_settlements": _sha256(playbook_settlement_path),
        "scanner_fitness": _sha256(scanner_fitness_path),
        "iv_calibration_rows": _sha256(iv_calibration_rows_path),
        "iv_calibration_summary": _sha256(iv_calibration_summary_path),
    }
    report: JsonObject = {
        "artifact_type": "targeting_source_validation",
        "source_validation_version": SOURCE_VALIDATION_VERSION,
        "source_validation_status": (
            "valid_current_evidence"
            if not blockers
            else "blocked_invalid_or_stale_upstream_evidence"
        ),
        "observed_at_utc": observed_at.astimezone(timezone.utc).isoformat(),
        "blocker_count": len(blockers),
        "blockers": list(blockers),
        "sources": {
            "history": history_report,
            "playbook_settlements": settlement_report,
            "playbook_detections": detection_report,
            "scanner_fitness": scanner_report,
            "iv_calibration": iv_report,
        },
        "source_hashes": dict(sorted(source_hashes.items())),
        "stale_or_mismatched_evidence_consumed": False,
        "paper_only": True,
        "live_blocked": True,
        "promotion_allowed": False,
    }
    report["reproducibility_hash"] = canonical_hash(report)
    if blockers:
        settlements = ()
        scanner = {}
        iv_summary = {}
        iv_rows = ()
    if history_blockers:
        history = {}
    return ValidatedTargetingSources(
        history=history,
        history_manifest_hash=manifest_hash,
        playbook_settlements=settlements,
        playbook_detections=detections if not blockers else (),
        scanner_fitness=scanner,
        iv_calibration_summary=iv_summary,
        iv_calibration_rows=iv_rows,
        source_hashes=source_hashes,
        validation_report=report,
        blockers=tuple(blockers),
    )
