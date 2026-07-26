"""Inventory manually staged local OHLCV files without importing them."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .local_ohlcv_import_models import (
    LOCAL_OHLCV_IMPORT_VERSION,
    LocalOhlcvFileInventoryRecord,
    stable_local_ohlcv_hash,
)
from .local_staging_contract import REPO_ROOT


DAILY_OHLCV_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "daily_ohlcv"
MARKET_CONTEXT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "market_context"
CORPORATE_ACTIONS_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "corporate_actions"
MANIFEST_DIR = REPO_ROOT / "dopey_data" / "real" / "manifests"
REAL_DATA_MANIFEST_PATH = MANIFEST_DIR / "real_data_manifest.json"
REAL_DATA_MANIFEST_TEMPLATE_PATH = MANIFEST_DIR / "real_data_manifest.template.json"
ACCEPTED_FILE_EXTENSIONS: frozenset[str] = frozenset({".csv", ".jsonl"})
SCAN_DIRS: tuple[Path, ...] = (DAILY_OHLCV_DIR, MARKET_CONTEXT_DIR, CORPORATE_ACTIONS_DIR)
TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"access[_-]?token", re.IGNORECASE),
    re.compile(r"secret[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE),
)
FORBIDDEN_LIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbroker\b", re.IGNORECASE),
    re.compile(r"\blive[_ -]?trading\b", re.IGNORECASE),
    re.compile(r"\border[_ -]?(id|route|submit|cancel|place)\b", re.IGNORECASE),
    re.compile(r"\bscheduler\b|\bdaemon\b", re.IGNORECASE),
    re.compile(r"\breal[_ -]?(capital|sizing|buying[_ -]?power|account[_ -]?balance)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class LocalOhlcvParsedFile:
    path: Path
    dataset_family: str
    rows: list[dict[str, str]]
    header_columns: list[str]
    malformed_rows: int
    text: str


def inventory_local_ohlcv_files() -> list[dict[str, Any]]:
    manifest = load_manifest_record(REAL_DATA_MANIFEST_PATH)
    return [record.to_dict() for record in build_inventory_records(manifest)]


def build_inventory_records(manifest: dict[str, Any]) -> list[LocalOhlcvFileInventoryRecord]:
    return [_inventory_record(parsed, manifest) for parsed in read_staged_local_ohlcv_files()]


def read_staged_local_ohlcv_files() -> list[LocalOhlcvParsedFile]:
    files = list_staged_local_ohlcv_paths()
    return [read_local_ohlcv_file(path, dataset_family_for_path(path)) for path in files]


def list_staged_local_ohlcv_paths() -> list[Path]:
    paths: list[Path] = []
    for folder in SCAN_DIRS:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            resolved = path.resolve()
            if not _is_inside_repo(resolved):
                continue
            if path.suffix.lower() in ACCEPTED_FILE_EXTENSIONS:
                paths.append(path)
    return sorted(paths)


def read_local_ohlcv_file(path: Path, dataset_family: str) -> LocalOhlcvParsedFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".jsonl":
        rows, headers, malformed = _read_jsonl_rows(text)
    else:
        rows, headers, malformed = _read_csv_rows(text)
    return LocalOhlcvParsedFile(path=path, dataset_family=dataset_family, rows=rows, header_columns=headers, malformed_rows=malformed, text=text)


def load_manifest_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"manifest_parse_error": True}
    return parsed if isinstance(parsed, dict) else {"manifest_parse_error": True}


def dataset_family_for_path(path: Path) -> str:
    if MARKET_CONTEXT_DIR in path.parents:
        return "market_context"
    if CORPORATE_ACTIONS_DIR in path.parents:
        return "corporate_actions"
    return "daily_ohlcv"


def repo_relative_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_row_is_blocked(row: dict[str, str]) -> bool:
    return (
        _truthy(row.get("sample_only", ""))
        or _truthy(row.get("not_real_data", ""))
        or row.get("symbol", "").strip().upper() == "SAMPLE_ONLY"
        or row.get("underlying_symbol", "").strip().upper() == "SAMPLE_ONLY"
    )


def credential_token_found(text: str) -> bool:
    return any(pattern.search(text) for pattern in TOKEN_PATTERNS)


def forbidden_live_marker_found(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_LIVE_PATTERNS)


def parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def manifest_local_file_paths(manifest: dict[str, Any]) -> set[str]:
    raw = manifest.get("local_file_paths", [])
    if not isinstance(raw, list):
        return set()
    return {str(path).replace("\\", "/") for path in raw}


def manifest_file_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    raw = manifest.get("file_hashes", {})
    if not isinstance(raw, dict):
        return {}
    return {str(key).replace("\\", "/"): str(value) for key, value in raw.items()}


def _inventory_record(parsed: LocalOhlcvParsedFile, manifest: dict[str, Any]) -> LocalOhlcvFileInventoryRecord:
    relative = repo_relative_path(parsed.path)
    manifest_paths = manifest_local_file_paths(manifest)
    manifest_hashes = manifest_file_hashes(manifest)
    sources_present = any("source" in row and row.get("source", "").strip() for row in parsed.rows)
    license_present = bool(manifest.get("license_status") and manifest.get("license_status") not in {"unknown", "missing", "unreviewed", "template_only"})
    future = any((parse_date(row.get("date", "")) or date.min) > date.today() for row in parsed.rows)
    seed = {"path": relative, "sha256": sha256_file(parsed.path)}
    return LocalOhlcvFileInventoryRecord(
        artifact_type="local_ohlcv_file_inventory",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        file_id=f"inventory-{stable_local_ohlcv_hash(seed)[:12]}",
        dataset_family=parsed.dataset_family,
        local_file_path=relative,
        file_extension=parsed.path.suffix.lower(),
        byte_size=parsed.path.stat().st_size,
        sha256=sha256_file(parsed.path),
        row_count=len(parsed.rows),
        header_columns=parsed.header_columns,
        sample_only_detected=any(sample_row_is_blocked(row) for row in parsed.rows),
        fake_symbol_detected=any(row.get("symbol", "").strip().upper() == "SAMPLE_ONLY" for row in parsed.rows),
        credential_token_pattern_detected=credential_token_found(parsed.text),
        future_date_candidate_detected=future,
        manifest_referenced=relative in manifest_paths or relative in manifest_hashes,
        source_provenance_fields_present=sources_present or bool(manifest.get("provider_name")),
        license_fields_present=license_present,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        file_hash="",
    )


def _read_csv_rows(text: str) -> tuple[list[dict[str, str]], list[str], int]:
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


def _read_jsonl_rows(text: str) -> tuple[list[dict[str, str]], list[str], int]:
    rows: list[dict[str, str]] = []
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


def _is_inside_repo(path: Path) -> bool:
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}
