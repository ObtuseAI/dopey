"""Refresh valuation and IPO context without repeating short-interest calls."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from operator_tools.operator_fetch_macro_context import (
    IPO_LOOKBACK_MONTHS,
    MACRO_DIR,
    fetch_fundamentals,
    fetch_nasdaq_ipo_calendar,
)
from operator_tools.operator_fetch_squeeze_context import (
    pin_squeeze_context_files,
)


def _csv_row_count(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(
            f"required squeeze context lane is missing: path={path}"
        )
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _row in csv.DictReader(handle))


def main() -> int:
    observed_date = date.today()
    fundamental_name, fundamental_rows = fetch_fundamentals(observed_date)
    ipo_name, ipo_rows = fetch_nasdaq_ipo_calendar(
        observed_date,
        IPO_LOOKBACK_MONTHS,
    )
    short_rows = _csv_row_count(MACRO_DIR / "short_crowding.csv")
    margin_rows = _csv_row_count(MACRO_DIR / "finra_margin_statistics.csv")
    threshold_rows = _csv_row_count(MACRO_DIR / "threshold_securities.csv")
    manifest = pin_squeeze_context_files(
        short_rows,
        margin_rows,
        fundamental_rows,
        ipo_rows,
        threshold_rows,
        observed_date,
    )
    result = {
        "artifact_type": "bubble_context_operator_fetch",
        "fundamentals_path": fundamental_name,
        "fundamentals_rows": fundamental_rows,
        "ipo_calendar_path": ipo_name,
        "ipo_calendar_rows": ipo_rows,
        "credential_count": 0,
        "manifest": manifest,
    }
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0 if fundamental_rows > 0 and ipo_rows > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
