"""Refresh the credential-free open-short and aggregate-margin research lanes."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from datetime import datetime, timezone
from pathlib import Path

from operator_tools.operator_fetch_macro_context import (
    IPO_LOOKBACK_MONTHS,
    MACRO_DIR,
    MACRO_MANIFEST_PATH,
    REPO,
    fetch_finra_margin_statistics,
    fetch_fundamentals,
    fetch_nasdaq_ipo_calendar,
    fetch_nasdaq_threshold_securities,
    fetch_short_crowding,
)


def pin_squeeze_context_files(
    short_rows: int,
    margin_rows: int,
    fundamental_rows: int,
    ipo_rows: int,
    threshold_rows: int,
    observed_date: date,
) -> dict[str, object]:
    """Extend the existing macro manifest without disturbing other pinned lanes."""

    if not MACRO_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"macro manifest is required before pinning squeeze context: path={MACRO_MANIFEST_PATH}"
        )
    try:
        payload = json.loads(MACRO_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"macro manifest is invalid JSON: path={MACRO_MANIFEST_PATH}, error={error}"
        ) from error
    if not isinstance(payload, dict):
        raise TypeError(
            f"macro manifest must be an object: path={MACRO_MANIFEST_PATH}"
        )
    file_hashes = dict(payload.get("file_hashes", {}))
    row_counts = dict(payload.get("row_counts", {}))
    sources = dict(payload.get("per_file_sources", {}))
    staged = (
        (
            MACRO_DIR / "short_crowding.csv",
            short_rows,
            "yahoo_finance_personal_research_actual_open_short_snapshot",
        ),
        (
            MACRO_DIR / "finra_margin_statistics.csv",
            margin_rows,
            "finra_rule_4521d_aggregate_internal_research",
        ),
        (
            MACRO_DIR / "fundamentals.csv",
            fundamental_rows,
            "yahoo_finance_personal_research",
        ),
        (
            MACRO_DIR / "ipo_calendar.csv",
            ipo_rows,
            "nasdaq_ipo_calendar_internal_research",
        ),
        (
            MACRO_DIR / "threshold_securities.csv",
            threshold_rows,
            "nasdaq_reg_sho_threshold_official",
        ),
    )
    for path, row_count, source in staged:
        if not path.exists() or row_count <= 0:
            raise FileNotFoundError(
                "squeeze context lane cannot be pinned without staged rows: "
                f"path={path}, row_count={row_count}"
            )
        relative = path.relative_to(REPO).as_posix()
        file_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        row_counts[relative] = row_count
        sources[relative] = source
    updated = {
        **payload,
        "manifest_id": f"macro-context-operator-{observed_date.isoformat()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_hashes": dict(sorted(file_hashes.items())),
        "row_counts": dict(sorted(row_counts.items())),
        "per_file_sources": dict(sorted(sources.items())),
        "local_file_paths": sorted(file_hashes),
    }
    temporary_path = Path(str(MACRO_MANIFEST_PATH) + ".tmp")
    temporary_path.write_text(
        json.dumps(updated, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, MACRO_MANIFEST_PATH)
    return {
        "manifest_path": str(MACRO_MANIFEST_PATH),
        "pinned_short_crowding_rows": short_rows,
        "pinned_margin_rows": margin_rows,
        "pinned_fundamental_rows": fundamental_rows,
        "pinned_ipo_rows": ipo_rows,
        "pinned_threshold_rows": threshold_rows,
    }


def main() -> int:
    observed_date = date.today()
    short_name, short_rows = fetch_short_crowding(observed_date)
    margin_name, margin_rows = fetch_finra_margin_statistics()
    fundamental_name, fundamental_rows = fetch_fundamentals(observed_date)
    ipo_name, ipo_rows = fetch_nasdaq_ipo_calendar(
        observed_date,
        IPO_LOOKBACK_MONTHS,
    )
    threshold_name, threshold_rows = fetch_nasdaq_threshold_securities(
        observed_date
    )
    manifest = pin_squeeze_context_files(
        short_rows,
        margin_rows,
        fundamental_rows,
        ipo_rows,
        threshold_rows,
        observed_date,
    )
    result = {
        "artifact_type": "squeeze_context_operator_fetch",
        "short_crowding_path": short_name,
        "short_crowding_rows": short_rows,
        "finra_margin_path": margin_name,
        "finra_margin_rows": margin_rows,
        "fundamentals_path": fundamental_name,
        "fundamentals_rows": fundamental_rows,
        "ipo_calendar_path": ipo_name,
        "ipo_calendar_rows": ipo_rows,
        "threshold_securities_path": threshold_name,
        "threshold_securities_rows": threshold_rows,
        "daily_short_volume_substituted": False,
        "borrow_fee_inferred": False,
        "borrow_utilization_inferred": False,
        "credential_count": 0,
        "manifest": manifest,
    }
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return (
        0
        if short_rows > 0
        and margin_rows > 0
        and fundamental_rows > 0
        and ipo_rows > 0
        and threshold_rows > 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
