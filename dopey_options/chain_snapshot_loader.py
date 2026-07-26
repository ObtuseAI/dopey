"""Load and validate operator-staged options-chain snapshots.

Gates before any row is trusted: manifest finalized (license reviewed, not
template), per-file sha256 pins match, schema exact, quality rules (positive
strikes, ask >= bid >= 0, sane IV, no future snapshot dates, no credential or
live-trading markers). Rows that pass are labeled quote-derived snapshot data.
Never fabricates rows; missing or invalid staging returns a blocked status.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CHAIN_RAW_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
OPTIONS_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"

REQUIRED_COLUMNS = (
    "snapshot_date", "symbol", "expiry", "dte_calendar", "option_type", "strike",
    "bid", "ask", "mid", "last", "volume", "open_interest", "implied_vol",
    "underlying_spot", "source",
)
VALID_LICENSE_STATUSES = {
    "reviewed_allowed_internal_research",
    "reviewed_restricted_internal_research",
    "reviewed_public_domain",
    "reviewed_open_data_internal_research",
}
FORBIDDEN_PATTERNS = (
    re.compile(r"api[_-]?key|access[_-]?token|secret[_-]?key|password|bearer\s", re.IGNORECASE),
    re.compile(r"\bbroker\b|\blive[_ -]?trading\b|\border[_ -]?(id|submit|place)\b|\bscheduler\b", re.IGNORECASE),
)


def list_chain_snapshot_dates() -> list[str]:
    """Sorted staged snapshot-directory names (ISO dates) that contain at least one
    CSV - an empty dir from a failed fetch day must never become "latest".
    Listing only; rows still gate per-load."""
    if not CHAIN_RAW_DIR.exists():
        return []
    return sorted(path.name for path in CHAIN_RAW_DIR.iterdir() if path.is_dir() and any(path.glob("*.csv")))


def load_latest_chain_snapshot() -> dict[str, Any]:
    dates = list_chain_snapshot_dates()
    return load_chain_snapshot(dates[-1] if dates else "")


def load_chain_snapshot(snapshot_date: str) -> dict[str, Any]:
    """Load one staged snapshot by date through the full gate stack (manifest, pins, schema, quality)."""
    manifest = _load_manifest()
    if not manifest:
        return _blocked("blocked_missing_options_manifest")
    if manifest.get("template_only") is True or str(manifest.get("manifest_id", "")).startswith("OPTIONS_TEMPLATE"):
        return _blocked("blocked_options_manifest_template_only")
    if str(manifest.get("license_status", "unknown")).lower() not in VALID_LICENSE_STATUSES:
        return _blocked("blocked_options_license_not_reviewed")
    if manifest.get("provider_terms_reviewed") is not True:
        return _blocked("blocked_options_terms_not_reviewed")
    latest = CHAIN_RAW_DIR / snapshot_date
    if not snapshot_date or not latest.is_dir():
        return _blocked("blocked_no_real_chain_data_staged")
    manifest_hashes = {str(k).replace("\\", "/"): str(v) for k, v in manifest.get("file_hashes", {}).items()}
    rows: list[dict[str, Any]] = []
    reason_codes: list[str] = []
    files_loaded = 0
    for path in sorted(latest.glob("*.csv")):
        relative = _manifest_relative_path(path)
        recorded = manifest_hashes.get(relative)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if recorded is None:
            reason_codes.append(f"missing_manifest_hash:{relative}")
            continue
        if recorded != actual:
            reason_codes.append(f"hash_mismatch:{relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS):
            reason_codes.append(f"forbidden_marker:{relative}")
            continue
        file_rows, file_reasons = _parse_file(text, relative)
        rows.extend(file_rows)
        reason_codes.extend(file_reasons)
        files_loaded += 1
    if not rows:
        return _blocked("blocked_no_valid_chain_rows", reason_codes)
    return {
        "chain_snapshot_status": "real_chain_snapshot_validated",
        "snapshot_date": latest.name,
        "files_loaded": files_loaded,
        "row_count": len(rows),
        "symbols": sorted({row["symbol"] for row in rows}),
        "reason_codes": sorted(set(reason_codes)),
        "rows": rows,
        "quote_derived": True,
        "data_source_tier": "public_chain_snapshot",
        "paper_only": True,
        "live_blocked": True,
    }


def _manifest_relative_path(path: Path) -> str:
    """Return the canonical manifest key for live or isolated data roots."""
    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    real_data_root = CHAIN_RAW_DIR.parents[1]
    if not path.is_relative_to(real_data_root):
        raise ValueError(f"Options-chain path is outside the governed data root: {path}")
    data_relative = path.relative_to(real_data_root)
    return (Path("dopey_data") / "real" / data_relative).as_posix()


def _parse_file(text: str, relative: str) -> tuple[list[dict[str, Any]], list[str]]:
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
        return [], [f"schema_mismatch:{relative}"]
    today = date.today()
    rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    for raw in reader:
        try:
            snapshot_date = date.fromisoformat(raw["snapshot_date"])
            strike = float(raw["strike"])
            bid = float(raw["bid"])
            ask = float(raw["ask"])
            implied_vol = float(raw["implied_vol"])
            spot = float(raw["underlying_spot"])
            dte = int(raw["dte_calendar"])
            mid = float(raw["mid"])
            last = float(raw["last"])
            volume = int(float(raw["volume"]))
            open_interest = int(float(raw["open_interest"]))
        except (KeyError, ValueError, TypeError):
            reasons.append(f"row_parse_error:{relative}")
            continue
        if snapshot_date > today:
            reasons.append(f"future_snapshot_date:{relative}")
            continue
        if strike <= 0 or spot <= 0 or bid < 0 or ask < bid or not (0.005 <= implied_vol <= 5.0) or dte <= 0:
            reasons.append(f"quality_reject:{relative}")
            continue
        if raw["option_type"] not in {"call", "put"}:
            reasons.append(f"bad_option_type:{relative}")
            continue
        rows.append(
            {
                "snapshot_date": raw["snapshot_date"],
                "symbol": raw["symbol"].strip().upper(),
                "expiry": raw["expiry"],
                "dte_calendar": dte,
                "option_type": raw["option_type"],
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": last,
                "volume": volume,
                "open_interest": open_interest,
                "implied_vol": implied_vol,
                "underlying_spot": spot,
                "source": raw["source"],
                "quote_derived": True,
            }
        )
    return rows, reasons


def _load_manifest() -> dict[str, Any]:
    if not OPTIONS_MANIFEST_PATH.exists():
        return {}
    try:
        parsed = json.loads(OPTIONS_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _blocked(status: str, reason_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "chain_snapshot_status": status,
        "snapshot_date": "",
        "files_loaded": 0,
        "row_count": 0,
        "symbols": [],
        "reason_codes": reason_codes or [],
        "rows": [],
        "quote_derived": False,
        "paper_only": True,
        "live_blocked": True,
    }
