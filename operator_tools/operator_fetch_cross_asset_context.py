"""Stage a real, local cross-asset history snapshot for paper research."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from curl_cffi.requests.exceptions import RequestException as CurlRequestException
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from requests.exceptions import RequestException
import yfinance as yf
from yfinance.exceptions import YFException


class AssetSpec(TypedDict):
    provider_symbol: str
    symbol: str
    name: str
    asset_class: str
    subclass: str


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "cross_asset"
OUTPUT_PATH = OUTPUT_DIR / "cross_asset_daily.csv"
MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "cross_asset_context_manifest.json"
SNAPSHOT_ROOT = OUTPUT_DIR / "snapshots"
MANIFEST_SNAPSHOT_ROOT = REPO_ROOT / "dopey_data" / "real" / "manifests" / "cross_asset_snapshots"
SOURCE_NAME = "yahoo_finance_personal_research"
MAX_ATTEMPTS = 3

ASSETS: tuple[AssetSpec, ...] = (
    {"provider_symbol": "ES=F", "symbol": "ES", "name": "E-mini S&P 500", "asset_class": "futures", "subclass": "equity_index"},
    {"provider_symbol": "NQ=F", "symbol": "NQ", "name": "E-mini Nasdaq 100", "asset_class": "futures", "subclass": "equity_index"},
    {"provider_symbol": "YM=F", "symbol": "YM", "name": "E-mini Dow", "asset_class": "futures", "subclass": "equity_index"},
    {"provider_symbol": "RTY=F", "symbol": "RTY", "name": "E-mini Russell 2000", "asset_class": "futures", "subclass": "equity_index"},
    {"provider_symbol": "ZN=F", "symbol": "ZN", "name": "10-Year Treasury Note", "asset_class": "futures", "subclass": "treasury"},
    {"provider_symbol": "ZB=F", "symbol": "ZB", "name": "30-Year Treasury Bond", "asset_class": "futures", "subclass": "treasury"},
    {"provider_symbol": "CL=F", "symbol": "CL", "name": "WTI Crude Oil", "asset_class": "commodity", "subclass": "energy"},
    {"provider_symbol": "BZ=F", "symbol": "BZ", "name": "Brent Crude Oil", "asset_class": "commodity", "subclass": "energy"},
    {"provider_symbol": "NG=F", "symbol": "NG", "name": "Natural Gas", "asset_class": "commodity", "subclass": "energy"},
    {"provider_symbol": "GC=F", "symbol": "GC", "name": "Gold", "asset_class": "commodity", "subclass": "precious_metal"},
    {"provider_symbol": "SI=F", "symbol": "SI", "name": "Silver", "asset_class": "commodity", "subclass": "precious_metal"},
    {"provider_symbol": "HG=F", "symbol": "HG", "name": "Copper", "asset_class": "commodity", "subclass": "industrial_metal"},
    {"provider_symbol": "ZC=F", "symbol": "ZC", "name": "Corn", "asset_class": "commodity", "subclass": "agriculture"},
    {"provider_symbol": "ZW=F", "symbol": "ZW", "name": "Wheat", "asset_class": "commodity", "subclass": "agriculture"},
    {"provider_symbol": "ZS=F", "symbol": "ZS", "name": "Soybeans", "asset_class": "commodity", "subclass": "agriculture"},
    {"provider_symbol": "DX-Y.NYB", "symbol": "DXY", "name": "U.S. Dollar Index", "asset_class": "currency", "subclass": "dollar_index"},
    {"provider_symbol": "EURUSD=X", "symbol": "EURUSD", "name": "Euro/U.S. Dollar", "asset_class": "currency", "subclass": "major_fx"},
    {"provider_symbol": "JPY=X", "symbol": "USDJPY", "name": "U.S. Dollar/Japanese Yen", "asset_class": "currency", "subclass": "major_fx"},
    {"provider_symbol": "BTC-USD", "symbol": "BTC", "name": "Bitcoin", "asset_class": "crypto", "subclass": "digital_asset"},
    {"provider_symbol": "ETH-USD", "symbol": "ETH", "name": "Ethereum", "asset_class": "crypto", "subclass": "digital_asset"},
)


def fetch_asset_rows(spec: AssetSpec) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            history = yf.Ticker(spec["provider_symbol"]).history(period="2y", auto_adjust=False, actions=False)
            if history.empty:
                raise ValueError(f"provider returned empty history: provider_symbol={spec['provider_symbol']}")
            rows: list[dict[str, Any]] = []
            for index, row in history.iterrows():
                close = float(row["Close"])
                if close <= 0.0:
                    continue
                volume_value = row.get("Volume", 0)
                volume = int(volume_value) if volume_value == volume_value else 0
                rows.append(
                    {
                        "date": index.date().isoformat(),
                        "symbol": spec["symbol"],
                        "provider_symbol": spec["provider_symbol"],
                        "name": spec["name"],
                        "asset_class": spec["asset_class"],
                        "subclass": spec["subclass"],
                        "close": round(close, 8),
                        "volume": volume,
                        "source": SOURCE_NAME,
                        "series_type": _series_type(spec),
                        "contract_metadata_status": _contract_metadata_status(spec),
                    }
                )
            if not rows:
                raise ValueError(f"provider history contained no positive closes: provider_symbol={spec['provider_symbol']}")
            return rows
        except (CurlRequestException, KeyError, RequestException, RuntimeError, TypeError, ValueError, YFException) as error:
            last_error = error
            print(
                f"WARNING cross-asset fetch attempt failed: symbol={spec['symbol']} "
                f"provider_symbol={spec['provider_symbol']} attempt={attempt}/{MAX_ATTEMPTS} error={error}",
                flush=True,
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(float(attempt * 2))
    raise RuntimeError(
        f"cross-asset fetch exhausted retries: symbol={spec['symbol']} provider_symbol={spec['provider_symbol']} "
        f"last_error={last_error}"
    ) from last_error


def write_cross_asset_snapshot(rows: list[dict[str, Any]], run_stamp: str) -> Path:
    if not rows:
        raise ValueError("cross-asset snapshot cannot be written without rows")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = (
        "date", "symbol", "provider_symbol", "name", "asset_class", "subclass",
        "close", "volume", "source", "series_type", "contract_metadata_status",
    )
    temp = OUTPUT_PATH.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (str(row["symbol"]), str(row["date"]))))
    temp.replace(OUTPUT_PATH)
    snapshot_dir = SNAPSHOT_ROOT / run_stamp
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = snapshot_dir / OUTPUT_PATH.name
    snapshot_path.write_bytes(OUTPUT_PATH.read_bytes())
    return snapshot_path


def write_manifest(
    rows: list[dict[str, Any]],
    source_statuses: list[dict[str, str]],
    snapshot_path: Path,
    run_stamp: str,
) -> dict[str, Any]:
    symbols = sorted({str(row["symbol"]) for row in rows})
    status = "complete" if len(symbols) == len(ASSETS) else "partial_explicit_source_failures"
    manifest: dict[str, Any] = {
        "manifest_id": f"cross-asset-context-{datetime.now(timezone.utc).date().isoformat()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_family": "cross_asset_daily_context",
        "dataset_status": status,
        "provider_name": SOURCE_NAME,
        "provider_terms_reviewed": True,
        "license_status": "reviewed_allowed_internal_research",
        "redistribution_allowed": False,
        "local_file_path": OUTPUT_PATH.relative_to(REPO_ROOT).as_posix(),
        "file_sha256": hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest(),
        "immutable_snapshot_path": snapshot_path.relative_to(REPO_ROOT).as_posix(),
        "immutable_snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "symbols_requested": [spec["symbol"] for spec in ASSETS],
        "symbols_staged": symbols,
        "source_statuses": source_statuses,
        "paper_only": True,
        "live_blocked": True,
        "not_broker_data": True,
        "not_credentials": True,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = MANIFEST_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(MANIFEST_PATH)
    (snapshot_path.parent / "cross_asset_context_manifest.json").write_bytes(MANIFEST_PATH.read_bytes())
    MANIFEST_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_snapshot = MANIFEST_SNAPSHOT_ROOT / f"cross_asset_context_manifest_{run_stamp}.json"
    manifest_snapshot.write_bytes(MANIFEST_PATH.read_bytes())
    return manifest


def _series_type(spec: AssetSpec) -> str:
    if spec["provider_symbol"].endswith("=F"):
        return "continuous_futures_proxy"
    if spec["asset_class"] == "crypto":
        return "spot_crypto_proxy"
    if spec["subclass"] == "dollar_index":
        return "currency_index_proxy"
    return "spot_fx_proxy"


def _contract_metadata_status(spec: AssetSpec) -> str:
    return "unavailable_provider_continuous_symbol" if spec["provider_symbol"].endswith("=F") else "not_applicable"


def main() -> int:
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rows: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    for spec in ASSETS:
        try:
            fetched = fetch_asset_rows(spec)
        except RuntimeError as error:
            statuses.append({"symbol": spec["symbol"], "status": "failed_after_retries", "error": str(error)})
            continue
        rows.extend(fetched)
        statuses.append({"symbol": spec["symbol"], "status": "staged", "error": ""})
        time.sleep(0.25)
    staged_symbols = {str(row["symbol"]) for row in rows}
    required_classes = {"futures", "commodity", "currency", "crypto"}
    staged_classes = {str(row["asset_class"]) for row in rows}
    if len(staged_symbols) < 12 or not required_classes.issubset(staged_classes):
        raise RuntimeError(
            f"cross-asset coverage floor failed: symbols={len(staged_symbols)}, classes={sorted(staged_classes)}, "
            f"required_classes={sorted(required_classes)}"
        )
    snapshot_path = write_cross_asset_snapshot(rows, run_stamp)
    manifest = write_manifest(rows, statuses, snapshot_path, run_stamp)
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
