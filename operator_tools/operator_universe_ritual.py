"""OPERATOR TOOL - universe staging ritual (the governor's NETWORK lane).

Consumes the governor's staging queue: probes each candidate for market-cap
and dollar-volume floors, records listed-options availability separately,
and for those that pass stages FULL history through the exact
governed path every prior expansion used - both staged copies written,
truncated to the current core frontier (uniform-advance preserved), history
manifest data_files entry appended, both manifests re-pinned with the repo's
canonical hash, spine re-validated. After the validator answers
valid_real_dataset, the registry records a staged standby candidate. Existing
standby history is never rewritten during metadata requalification. Active
membership is selected separately by the offline evolving-universe policy.

Bounded (MAX_ADDS_PER_RUN) and reversible. Also runs mechanical-death
quarantine: a probation name whose fetch fails or whose frontier lags the
core by QUARANTINE_FRONTIER_LAG_SESSIONS is quarantined (excluded from the
active universe and from uniform-advance) so a dead ticker can never freeze
the spine. Core names are exempt from all of this by construction.

Usage:  .venv\\Scripts\\python operator_tools\\operator_universe_ritual.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_data.history_models import history_manifest_hash  # noqa: E402
from dopey_data.run_history_dataset_validation import run_history_dataset_validation  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402
from dopey_universe.universe_registry import (  # noqa: E402
    QUARANTINE_FRONTIER_LAG_SESSIONS,
    load_registry,
    probation_symbols,
    quarantine,
    record_staging_proof,
    save_registry,
)

REAL_DIR = REPO / "dopey_data" / "real" / "raw" / "daily_ohlcv"
HISTORY_DIR = REPO / "dopey_data" / "history" / "raw"
PUBLIC_LAKE_DIR = REPO / "dopey_data" / "market_lake" / "public" / "daily_ohlcv"
HISTORY_MANIFEST_PATH = REPO / "dopey_data" / "history" / "history_dataset_manifest.json"
REAL_MANIFEST_PATH = REPO / "dopey_data" / "real" / "manifests" / "real_data_manifest.json"
STAGING_QUEUE_PATH = REPO / "artifacts" / "dopey" / "universe" / "staging_queue.json"
RITUAL_LOG_PATH = REPO / "artifacts" / "dopey" / "universe" / "universe_ritual_log.jsonl"
RITUAL_SUMMARY_PATH = REPO / "artifacts" / "dopey" / "universe" / "universe_ritual_summary.json"

MAX_ADDS_PER_RUN = 5
MARKET_CAP_FLOOR = 1_000_000_000
ETF_ASSET_FLOOR = 250_000_000
ADV_FLOOR_USD = 5_000_000
MIN_HISTORY_ROWS = 120  # a name must bring enough history to be researchable
CSV_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source"


def _log(record: dict) -> None:
    RITUAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"logged_utc": datetime.now(timezone.utc).isoformat(), **record}
    with RITUAL_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def core_frontier() -> str:
    """Newest last-date across CORE spine files = the uniform-advance frontier
    any new name must be truncated to."""
    from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE

    dates = []
    for symbol in REQUIRED_HISTORY_UNIVERSE:
        path = HISTORY_DIR / f"{symbol}.csv"
        try:
            last = path.read_text(encoding="utf-8").splitlines()[-1].split(",", 1)[0]
            if last and last != "date":
                dates.append(last)
        except OSError:
            continue
    return max(dates) if dates else ""


def probe_candidate(symbol: str) -> dict:
    """Network probe for equity quality; options availability is metadata.

    Missing listed options never blocks stock technical/fundamental research.
    It only prevents downstream contract selection for that symbol.
    """
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    result = {
        "symbol": symbol,
        "instrument_type": "",
        "research_tradable": False,
        "options_available": False,
        "market_cap": 0.0,
        "fund_assets": 0.0,
        "capitalization_kind": "",
        "capitalization_value": 0.0,
        "adv_usd": 0.0,
        "probe_observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "probe_ok": False,
        "reasons": [],
    }
    try:
        options = list(ticker.options or [])
        result["options_available"] = len(options) > 0
    except Exception as error:  # noqa: BLE001 - operator lane
        result["options_probe_warning"] = f"options_probe_failed_{type(error).__name__}"
    try:
        info = ticker.info or {}
        instrument_type = str(info.get("quoteType") or info.get("typeDisp") or "").upper()
        result["instrument_type"] = instrument_type
        result["research_tradable"] = instrument_type in {"EQUITY", "ETF"}
        if result["research_tradable"] is not True:
            result["reasons"].append("unsupported_or_missing_research_instrument_type")
        cap = float(info.get("marketCap") or 0.0)
        fund_assets = float(info.get("totalAssets") or info.get("netAssets") or 0.0)
        result["market_cap"] = cap
        result["fund_assets"] = fund_assets
        if instrument_type == "ETF":
            result["capitalization_kind"] = "fund_assets"
            result["capitalization_value"] = fund_assets
            if fund_assets < ETF_ASSET_FLOOR:
                result["reasons"].append("below_etf_asset_floor")
        else:
            result["capitalization_kind"] = "market_cap"
            result["capitalization_value"] = cap
        if instrument_type == "EQUITY" and cap < MARKET_CAP_FLOOR:
            result["reasons"].append("below_market_cap_floor")
    except Exception as error:  # noqa: BLE001
        result["reasons"].append(f"info_probe_failed_{type(error).__name__}")
    try:
        frame = ticker.history(period="1mo", auto_adjust=False)
        if len(frame) >= 5:
            adv = float((frame["Close"] * frame["Volume"]).tail(20).mean())
            result["adv_usd"] = round(adv, 2)
            if adv < ADV_FLOOR_USD:
                result["reasons"].append("below_dollar_volume_floor")
        else:
            result["reasons"].append("insufficient_recent_history")
    except Exception as error:  # noqa: BLE001
        result["reasons"].append(f"history_probe_failed_{type(error).__name__}")
    result["probe_ok"] = not result["reasons"]
    return result


def _persist_staged_history(symbol: str, frontier: str, lines: list[str], source: str) -> dict:
    if len(lines) - 1 < MIN_HISTORY_ROWS:
        return {"staged": False, "reason": f"only_{len(lines) - 1}_rows_below_min_{MIN_HISTORY_ROWS}"}
    body = "\n".join(lines) + "\n"
    for target_dir in (HISTORY_DIR, REAL_DIR):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{symbol}.csv").write_text(body, encoding="utf-8")

    history_file = HISTORY_DIR / f"{symbol}.csv"
    digest = hashlib.sha256(history_file.read_bytes()).hexdigest()
    manifest = json.loads(HISTORY_MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = [e for e in manifest.get("data_files", []) if e.get("path") != f"raw/{symbol}.csv"]
    entries.append({
        "format": "csv",
        "path": f"raw/{symbol}.csv",
        "row_count": len(lines) - 1,
        "sha256": digest,
        "source": source,
        "symbols": [symbol],
    })
    manifest["data_files"] = sorted(entries, key=lambda e: e["path"])
    manifest["manifest_reproducibility_hash"] = ""
    manifest["manifest_reproducibility_hash"] = history_manifest_hash(manifest)
    HISTORY_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    real = json.loads(REAL_MANIFEST_PATH.read_text(encoding="utf-8"))
    relative = (REAL_DIR / f"{symbol}.csv").relative_to(REPO).as_posix()
    real.setdefault("file_hashes", {})[relative] = hashlib.sha256((REAL_DIR / f"{symbol}.csv").read_bytes()).hexdigest()
    real["last_operator_ohlcv_update_utc"] = datetime.now(timezone.utc).isoformat()
    REAL_MANIFEST_PATH.write_text(json.dumps(real, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"staged": True, "rows": len(lines) - 1, "frontier": frontier, "sha256": digest, "source": source}


def stage_local_public_history(symbol: str, frontier: str) -> dict:
    """Stage existing real public OHLCV without another provider request."""
    source_path = PUBLIC_LAKE_DIR / f"{symbol}.csv"
    if not source_path.exists():
        return {"staged": False, "reason": "local_public_history_missing"}
    lines = [CSV_HEADER]
    with source_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            day = str(row.get("date", ""))[:10]
            if not day or (frontier and day > frontier):
                continue
            try:
                open_price = float(row["open"])
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
                adjusted = float(row.get("adjusted_close") or close)
                volume = int(float(row.get("volume") or 0))
            except (KeyError, TypeError, ValueError):
                continue
            if min(open_price, high, low, close, adjusted) <= 0:
                continue
            provider = str(row.get("provider") or row.get("source") or "public_lake")
            lines.append(f"{day},{symbol},{open_price},{high},{low},{close},{adjusted},{volume},{provider}")
    return _persist_staged_history(symbol, frontier, lines, "protected_public_lake")


def reuse_validated_standby_history(symbol: str, frontier: str) -> dict:
    """Reuse a current standby spine file for metadata-only requalification.

    This path never rewrites or truncates history. A stale or malformed standby
    is refused so it can only return through a separately governed transactional
    data refresh.
    """

    path = HISTORY_DIR / f"{symbol}.csv"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return {
            "staged": False,
            "reason": f"standby_history_unavailable_{type(error).__name__}",
        }
    if not lines or lines[0].strip() != CSV_HEADER:
        return {"staged": False, "reason": "standby_history_header_invalid"}
    rows = len(lines) - 1
    if rows < MIN_HISTORY_ROWS:
        return {
            "staged": False,
            "reason": f"standby_history_rows_{rows}_below_min_{MIN_HISTORY_ROWS}",
        }
    last_date = lines[-1].split(",", 1)[0]
    if frontier and last_date < frontier:
        return {
            "staged": False,
            "reason": f"standby_history_stale_{last_date}_behind_{frontier}",
        }
    return {
        "staged": True,
        "rows": rows,
        "frontier": last_date,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source": "existing_governed_standby_history",
        "metadata_only_requalification": True,
    }


def stage_full_history(symbol: str, frontier: str) -> dict:
    """Fetch max history only when a protected local public file is absent."""
    import yfinance as yf

    frame = yf.Ticker(symbol).history(period="max", auto_adjust=False)
    lines = [CSV_HEADER]
    for index, row in frame.iterrows():
        day = index.date().isoformat()
        if frontier and day > frontier:
            continue
        try:
            open_price, high, low, close = (float(row[name]) for name in ("Open", "High", "Low", "Close"))
            adjusted = float(row.get("Adj Close", close))
            volume = int(row["Volume"]) if row["Volume"] == row["Volume"] else 0
        except (KeyError, TypeError, ValueError):
            continue
        if min(open_price, high, low, close) <= 0 or adjusted != adjusted or adjusted <= 0:
            continue
        lines.append(f"{day},{symbol},{open_price},{high},{low},{close},{adjusted},{volume},yahoo_finance")
    return _persist_staged_history(symbol, frontier, lines, "yahoo_finance")


def remove_staged_history(symbol: str) -> None:
    """Rollback files and both manifest references after validator rejection."""
    for target_dir in (HISTORY_DIR, REAL_DIR):
        (target_dir / f"{symbol}.csv").unlink(missing_ok=True)
    history = json.loads(HISTORY_MANIFEST_PATH.read_text(encoding="utf-8"))
    history["data_files"] = [
        entry for entry in history.get("data_files", []) if entry.get("path") != f"raw/{symbol}.csv"
    ]
    history["manifest_reproducibility_hash"] = ""
    history["manifest_reproducibility_hash"] = history_manifest_hash(history)
    HISTORY_MANIFEST_PATH.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    real = json.loads(REAL_MANIFEST_PATH.read_text(encoding="utf-8"))
    relative = (REAL_DIR / f"{symbol}.csv").relative_to(REPO).as_posix()
    if isinstance(real.get("file_hashes"), dict):
        real["file_hashes"].pop(relative, None)
    REAL_MANIFEST_PATH.write_text(json.dumps(real, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_quarantine_sweep(registry: dict, frontier: str) -> tuple[dict, list[str]]:
    """Mechanical death only: probation names lagging the core frontier."""
    quarantined: list[str] = []
    for symbol in probation_symbols(registry):
        path = HISTORY_DIR / f"{symbol}.csv"
        try:
            last = path.read_text(encoding="utf-8").splitlines()[-1].split(",", 1)[0]
        except OSError:
            registry = quarantine(registry, symbol, "spine_file_unreadable")
            quarantined.append(symbol)
            continue
        if frontier and last < frontier:
            from dopey_core.market_calendar import is_trading_day  # noqa: PLC0415
            from datetime import date, timedelta

            lag_sessions = 0
            cursor = date.fromisoformat(frontier)
            floor_date = date.fromisoformat(last)
            while cursor > floor_date and lag_sessions <= QUARANTINE_FRONTIER_LAG_SESSIONS:
                if is_trading_day(cursor):
                    lag_sessions += 1
                cursor -= timedelta(days=1)
            if lag_sessions > QUARANTINE_FRONTIER_LAG_SESSIONS:
                registry = quarantine(registry, symbol, f"frontier_lag_{lag_sessions}_sessions")
                quarantined.append(symbol)
    return registry, quarantined


def main() -> int:
    registry = load_registry()
    frontier = core_frontier()
    try:
        queue = json.loads(STAGING_QUEUE_PATH.read_text(encoding="utf-8")).get("queue", [])
    except (OSError, json.JSONDecodeError):
        queue = []

    registry, quarantined = run_quarantine_sweep(registry, frontier)
    save_registry(registry)
    staged_batch: list[dict] = []
    for entry in queue:
        if len(staged_batch) >= MAX_ADDS_PER_RUN:
            break
        symbol = str(entry.get("symbol", "")).upper()
        tier = registry.get("symbols", {}).get(symbol, {}).get("tier")
        if not symbol or tier not in {"candidate", "standby", "quarantined"}:
            continue
        probe = probe_candidate(symbol)
        _log({"event": "probe", **probe})
        if not probe["probe_ok"]:
            registry["symbols"][symbol].setdefault("notes", []).append(
                f"probe_failed_{'+'.join(probe['reasons'])}"
            )
            save_registry(registry)
            continue
        time.sleep(0.5)
        if tier == "standby":
            staging = reuse_validated_standby_history(symbol, frontier)
        else:
            staging = stage_local_public_history(symbol, frontier)
            if not staging.get("staged") and staging.get("reason") == "local_public_history_missing":
                staging = stage_full_history(symbol, frontier)
        _log({"event": "stage", "symbol": symbol, **staging})
        if not staging.get("staged"):
            registry["symbols"][symbol].setdefault("notes", []).append(f"staging_failed_{staging.get('reason', '')}")
            save_registry(registry)
            continue
        staged_batch.append({"symbol": symbol, "probe": probe, "staging": staging})

    staged_for_evolution: list[str] = []
    validator_status = "not_run_no_staged_candidates"
    if staged_batch:
        validation = run_history_dataset_validation()
        validator_status = str(validation.get("dataset_status", ""))
        _log({
            "event": "validate_batch",
            "symbols": [str(item["symbol"]) for item in staged_batch],
            "dataset_status": validator_status,
        })
    if staged_batch and validator_status != "valid_real_dataset":
        for item in staged_batch:
            symbol = str(item["symbol"])
            metadata_only = item["staging"].get("metadata_only_requalification") is True
            if not metadata_only:
                remove_staged_history(symbol)
            registry["symbols"][symbol].setdefault("notes", []).append(f"rolled_back_validator_{validator_status}")
            _log({
                "event": "rollback" if not metadata_only else "metadata_requalification_refused",
                "symbol": symbol,
                "reason": validator_status,
                "history_mutated": False if metadata_only else True,
            })
    elif staged_batch:
        for item in staged_batch:
            symbol = str(item["symbol"])
            probe = item["probe"]
            staging = item["staging"]
            staging_proof = {
                "staged_rows": staging["rows"],
                "staged_frontier": staging["frontier"],
                "options_available": probe["options_available"],
                "market_cap": probe["market_cap"],
                "fund_assets": probe["fund_assets"],
                "capitalization_kind": probe["capitalization_kind"],
                "capitalization_value": probe["capitalization_value"],
                "adv_usd": probe["adv_usd"],
                "instrument_type": probe["instrument_type"],
                "research_tradable": probe["research_tradable"],
                "probe_observed_at_utc": probe["probe_observed_at_utc"],
                "validator_status": validator_status,
            }
            registry = record_staging_proof(registry, symbol, staging_proof)
            if registry["symbols"][symbol].get("tier") == "standby":
                staged_for_evolution.append(symbol)
            save_registry(registry)

    save_registry(registry)
    summary = {
        "artifact_type": "governed_universe_growth_summary",
        "universe_ritual_status": "ok",
        "staged_and_promoted": [],
        "staged_for_evolution": staged_for_evolution,
        "membership_selection": "offline_evolving_universe_policy",
        "quarantined": quarantined,
        "queue_length": len(queue),
        "core_frontier": frontier,
        "validator_status": validator_status,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(RITUAL_SUMMARY_PATH, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
