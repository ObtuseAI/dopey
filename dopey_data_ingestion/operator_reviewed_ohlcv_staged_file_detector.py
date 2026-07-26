"""Detect operator-staged reviewed OHLCV files without importing them."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvStagedFileInventory,
    stable_operator_stage_hash,
)


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
STAGED_FILE_STATUS_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_staged_file_status.json"
STAGED_FILE_INVENTORY_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_staged_file_inventory.jsonl"
DAILY_OHLCV_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "daily_ohlcv"
MARKET_CONTEXT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "market_context"
CORPORATE_ACTIONS_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "corporate_actions"
SCAN_DIRS: tuple[Path, ...] = (DAILY_OHLCV_DIR, MARKET_CONTEXT_DIR, CORPORATE_ACTIONS_DIR)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".jsonl"})
TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"access[_-]?token", re.IGNORECASE),
    re.compile(r"secret[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE),
)
LIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbroker\b", re.IGNORECASE),
    re.compile(r"\blive[_ -]?trading\b", re.IGNORECASE),
    re.compile(r"\border[_ -]?(id|route|submit|cancel|place|record)\b", re.IGNORECASE),
    re.compile(r"\bscheduler\b|\bdaemon\b", re.IGNORECASE),
    re.compile(r"\baccount[_ -]?balance\b", re.IGNORECASE),
    re.compile(r"\bbuying[_ -]?power\b", re.IGNORECASE),
    re.compile(r"\breal[_ -]?(capital|sizing)\b", re.IGNORECASE),
)


def detect_operator_reviewed_staged_files() -> dict[str, Any]:
    inventory = build_staged_file_inventory()
    status = build_staged_file_status(inventory)
    _write_json(STAGED_FILE_STATUS_PATH, status)
    _write_jsonl(STAGED_FILE_INVENTORY_PATH, inventory)
    return {**status, "inventory": inventory, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "operator_reviewed_ohlcv_staged_file_status": str(STAGED_FILE_STATUS_PATH),
        "operator_reviewed_ohlcv_staged_file_inventory": str(STAGED_FILE_INVENTORY_PATH),
    }


def build_staged_file_inventory() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _all_scan_files():
        records.append(_inventory_record(path))
    return sorted(records, key=lambda record: record["local_file_path"])


def build_staged_file_status(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [record for record in inventory if record["file_extension"] in ALLOWED_EXTENSIONS and not record["symlink_or_outside_repo_attempt"]]
    terminal = any(
        record["credential_token_pattern_detected"]
        or record["broker_live_order_scheduler_real_sizing_pattern_detected"]
        or record["symlink_or_outside_repo_attempt"]
        for record in inventory
    )
    manual_repair = any(
        record["unsupported_file_type"]
        or not record["header"]
        or record["template_sample_contamination"]
        or not record["source_column_present"]
        for record in inventory
    )
    status = "operator_files_missing" if not inventory else "staged_files_detected"
    if terminal:
        status = "terminal_block"
    record = {
        "artifact_type": "operator_reviewed_ohlcv_staged_file_status",
        "stage_version": OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        "status": status,
        "staged_file_count": len(accepted),
        "scanned_file_count": len(inventory),
        "real_data_files_present": len(accepted) > 0,
        "operator_files_missing": len(accepted) == 0,
        "manual_repair_required": manual_repair,
        "terminal_block": terminal,
        "unsupported_file_count": sum(1 for record in inventory if record["unsupported_file_type"]),
        "sample_contamination_count": sum(1 for record in inventory if record["template_sample_contamination"]),
        "credential_or_token_count": sum(1 for record in inventory if record["credential_token_pattern_detected"]),
        "broker_live_order_scheduler_real_sizing_count": sum(1 for record in inventory if record["broker_live_order_scheduler_real_sizing_pattern_detected"]),
        "symlink_or_outside_repo_count": sum(1 for record in inventory if record["symlink_or_outside_repo_attempt"]),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["status_hash"] = stable_operator_stage_hash(record)
    return record


def _all_scan_files() -> list[Path]:
    paths: list[Path] = []
    for folder in SCAN_DIRS:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file() or path.is_symlink():
                paths.append(path)
    return sorted(paths)


def _inventory_record(path: Path) -> dict[str, Any]:
    symlink_escape = _symlink_or_outside_repo(path)
    text = "" if symlink_escape else _safe_read_text(path)
    rows, header, malformed_rows = _read_rows(path, text)
    symbols = sorted({str(row.get("symbol", "")).strip().upper() for row in rows if str(row.get("symbol", "")).strip()})
    dates = sorted(_date_values(rows))
    extension = path.suffix.lower()
    unsupported = extension not in ALLOWED_EXTENSIONS
    sample_symbol = any(symbol == "SAMPLE_ONLY" for symbol in symbols)
    sample_row = any(_truthy(str(row.get("sample_only", ""))) for row in rows)
    not_real_row = any(_truthy(str(row.get("not_real_data", ""))) for row in rows)
    token = _pattern_found(TOKEN_PATTERNS, text)
    live = _pattern_found(LIVE_PATTERNS, text)
    relative = _repo_relative(path)
    sha = "" if symlink_escape or not path.is_file() else hashlib.sha256(path.read_bytes()).hexdigest()
    return OperatorReviewedOhlcvStagedFileInventory(
        artifact_type="operator_reviewed_ohlcv_staged_file_inventory",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        inventory_id=f"operator-stage-inventory-{stable_operator_stage_hash({'path': relative, 'sha256': sha})[:12]}",
        local_file_path=relative,
        dataset_family=_dataset_family(path),
        file_extension=extension,
        byte_size=0 if symlink_escape or not path.exists() else path.stat().st_size,
        sha256=sha,
        row_count=len(rows),
        header=header,
        source_column_present="source" in header,
        symbol_count_candidate=len(symbols),
        date_range_candidate={"start": dates[0], "end": dates[-1]} if dates else {},
        template_sample_contamination=sample_symbol or sample_row or not_real_row,
        sample_only_symbol_detected=sample_symbol,
        sample_only_row_detected=sample_row,
        not_real_data_row_detected=not_real_row,
        credential_token_pattern_detected=token,
        broker_live_order_scheduler_real_sizing_pattern_detected=live,
        unsupported_file_type=unsupported,
        symlink_or_outside_repo_attempt=symlink_escape,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        strategy_promotion_allowed=False,
        not_options_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        inventory_hash="",
    ).to_dict() | {"malformed_row_count": malformed_rows}


def _read_rows(path: Path, text: str) -> tuple[list[dict[str, str]], list[str], int]:
    if path.suffix.lower() == ".csv":
        reader = csv.DictReader(text.splitlines())
        headers = [str(item) for item in (reader.fieldnames or [])]
        rows: list[dict[str, str]] = []
        malformed = 0
        for row in reader:
            if None in row:
                malformed += 1
                continue
            rows.append({str(key): str(value if value is not None else "") for key, value in row.items()})
        return rows, headers, malformed
    if path.suffix.lower() == ".jsonl":
        rows = []
        headers: set[str] = set()
        malformed = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(parsed, dict):
                malformed += 1
                continue
            row = {str(key): str(value) for key, value in parsed.items()}
            headers.update(row)
            rows.append(row)
        return rows, sorted(headers), malformed
    return [], [], 0


def _date_values(rows: list[dict[str, str]]) -> list[str]:
    dates: list[str] = []
    for row in rows:
        value = str(row.get("date", "")).strip()
        try:
            dates.append(datetime.strptime(value, "%Y-%m-%d").date().isoformat())
        except ValueError:
            continue
    return dates


def _dataset_family(path: Path) -> str:
    if MARKET_CONTEXT_DIR in path.parents:
        return "market_context"
    if CORPORATE_ACTIONS_DIR in path.parents:
        return "corporate_actions"
    return "daily_ohlcv"


def _safe_read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _pattern_found(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _symlink_or_outside_repo(path: Path) -> bool:
    if path.is_symlink():
        try:
            path.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            return True
        return True
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return True
    return False


def _repo_relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
