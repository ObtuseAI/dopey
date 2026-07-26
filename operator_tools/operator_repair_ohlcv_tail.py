"""OPERATOR TOOL - repair OHLC-inconsistent tail rows in the governed spine.

2026-07-16/17 incident: the upstream provider returned rows whose high sat
below open/close (or low above them) for 10 symbols. The staging gate of the
time only rejected non-positive prices, so the rows staged; append-only
semantics then made them unrepairable by re-fetch, and the whole-dataset
validator correctly failed closed (invalid_real_dataset), blocking dependent
lanes.

This tool performs the governed repair:
1. refuses to run while the supervisor or acceleration lock exists;
2. scans the last TAIL_WINDOW rows of every spine symbol for OHLC-inconsistent
   rows;
3. builds an in-memory candidate truncated to the last clean row while leaving
   both live copies untouched;
4. re-fetches through the hardened finite/invariant gate and requires every
   removed evidence date to be restored;
5. transactionally publishes both candidates and manifests with exact rollback,
   then requires full-history validation before reporting success.

Idempotent; touches only rows proven inconsistent; never fabricates a bar.

Usage:  .venv\\Scripts\\python operator_tools\\operator_repair_ohlcv_tail.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from operator_tools.operator_fetch_daily_ohlcv import (  # noqa: E402
    HISTORY_DIR,
    REAL_DIR,
    OhlcvDataValidationError,
    collect_new_rows_after_date,
    latest_completed_market_session,
    publish_refresh_transaction,
    publish_tail_repair_transaction,
)

TAIL_WINDOW = 10
SUPERVISOR_LOCK = REPO / "artifacts" / ".supervisor.lock"
ACCELERATION_LOCK = REPO / "artifacts" / "dopey" / "acceleration" / "acceleration_cycle.lock"


class OhlcvTailRepairError(RuntimeError):
    """Raised when a bounded tail repair cannot preserve source evidence."""


def _row_inconsistent(line: str) -> bool:
    parts = line.split(",")
    if len(parts) < 8:
        return False
    try:
        open_price, high, low, close = (float(parts[i]) for i in (2, 3, 4, 5))
    except ValueError:
        return False
    if not all(math.isfinite(value) for value in (open_price, high, low, close)):
        return True
    return high < max(open_price, close, low) or low > min(open_price, close, high)


def _partition_tail(lines: list[str], bad_dates: frozenset[str]) -> tuple[list[str], list[str]]:
    """Return immutable kept/removed partitions from the earliest bad date."""
    if len(lines) < 2 or not bad_dates:
        return list(lines), []
    earliest = min(bad_dates)
    kept = [lines[0]] + [line for line in lines[1:] if line.split(",", 1)[0] < earliest]
    removed = [line for line in lines[1:] if line.split(",", 1)[0] >= earliest]
    return kept, removed


def _repair_candidate(
    symbol: str,
    source_bytes: bytes,
    bad_dates: frozenset[str],
    fetched_rows: list[tuple[str, str]],
) -> tuple[bytes, int]:
    try:
        lines = source_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise OhlcvTailRepairError(
            f"OHLCV tail source is not UTF-8: symbol={symbol}, error={error}"
        ) from error
    kept, removed = _partition_tail(lines, bad_dates)
    if not removed:
        raise OhlcvTailRepairError(
            f"repair finding did not map to removable tail rows: symbol={symbol}, bad_dates={sorted(bad_dates)}"
        )
    fetched_by_date: dict[str, str] = {}
    for day, row in fetched_rows:
        if day in fetched_by_date:
            raise OhlcvDataValidationError(
                f"duplicate refetched repair date: symbol={symbol}, date={day}"
            )
        fetched_by_date[day] = row
    removed_dates = {line.split(",", 1)[0] for line in removed}
    missing_dates = sorted(removed_dates - set(fetched_by_date))
    if missing_dates:
        raise OhlcvTailRepairError(
            f"provider did not restore every removed evidence row: symbol={symbol}, missing_dates={missing_dates}"
        )
    candidate_lines = kept + [fetched_by_date[day] for day in sorted(fetched_by_date)]
    return ("\n".join(candidate_lines) + "\n").encode("utf-8"), len(removed)


def main() -> int:
    for lock in (SUPERVISOR_LOCK, ACCELERATION_LOCK):
        if lock.exists():
            print(json.dumps({"repair_status": "refused_active_lock", "lock": str(lock)}))
            return 1

    now_utc = datetime.now(timezone.utc)
    completed_session = latest_completed_market_session(now_utc)
    findings: dict[str, list[str]] = {}
    source_bytes_by_symbol: dict[str, bytes] = {}
    baseline_hashes: dict[str, str] = {}
    for csv_path in sorted(HISTORY_DIR.glob("*.csv")):
        source_bytes = csv_path.read_bytes()
        try:
            lines = source_bytes.decode("utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise OhlcvTailRepairError(
                f"history OHLCV file is not UTF-8: path={csv_path}, error={error}"
            ) from error
        bad = [line.split(",", 1)[0] for line in lines[-TAIL_WINDOW:] if _row_inconsistent(line)]
        if bad:
            symbol = csv_path.stem
            real_path = REAL_DIR / f"{symbol}.csv"
            if not real_path.is_file():
                raise OhlcvTailRepairError(
                    f"repair requires matching real-data copy: symbol={symbol}, path={real_path}"
                )
            real_bytes = real_path.read_bytes()
            if source_bytes != real_bytes:
                raise OhlcvTailRepairError(
                    f"history and real-data copies differ before repair: symbol={symbol}"
                )
            findings[symbol] = bad
            source_bytes_by_symbol[symbol] = source_bytes
            baseline_hashes[symbol] = hashlib.sha256(source_bytes).hexdigest()

    removed: dict[str, int] = {}
    refetched: dict[str, int] = {}
    candidates: dict[str, bytes] = {}
    for symbol, bad_date_list in sorted(findings.items()):
        bad_dates = frozenset(bad_date_list)
        lines = source_bytes_by_symbol[symbol].decode("utf-8").splitlines()
        kept, _ = _partition_tail(lines, bad_dates)
        last_retained_date = kept[-1].split(",", 1)[0] if len(kept) > 1 else "1900-01-01"
        rows = collect_new_rows_after_date(
            symbol,
            last_retained_date,
            completed_session,
        )
        candidate, removed_count = _repair_candidate(
            symbol,
            source_bytes_by_symbol[symbol],
            bad_dates,
            rows,
        )
        candidates[symbol] = candidate
        removed[f"history/{symbol}"] = removed_count
        removed[f"real/{symbol}"] = removed_count
        refetched[symbol] = len(rows)

    if candidates:
        validation = publish_tail_repair_transaction(
            candidates,
            baseline_hashes,
            now_utc,
        )
    else:
        validation = publish_refresh_transaction(
            {},
            completed_session,
            now_utc,
        )
    result = {
        "artifact_type": "ohlcv_tail_repair_report",
        "repair_status": "complete" if findings else "nothing_to_repair",
        "symbols_affected": sorted(findings),
        "bad_dates": {symbol: sorted(set(dates)) for symbol, dates in findings.items()},
        "rows_removed": removed,
        "rows_refetched": refetched,
        "post_repair_dataset_status": validation.get("dataset_status"),
        "paper_only": True,
        "live_blocked": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if validation.get("dataset_status") == "valid_real_dataset" else 2


if __name__ == "__main__":
    raise SystemExit(main())
