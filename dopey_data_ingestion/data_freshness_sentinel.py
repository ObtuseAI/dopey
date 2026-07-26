"""Data-freshness sentinel: the stage that notices when the machine goes stale.

Every evidence lane in DOPEY assumes the daily ritual keeps running. If the
scheduled task dies, the chain archive stops growing, the forward walk stops
marking, and every downstream number quietly ages - with nothing to say so.
This stage measures, in TRADING SESSIONS (weekends/holidays excluded), how far
behind each artifact is, classifies each lane green/amber/red, and fails red
so the supervisor records the outage as an incident.

Lanes: OHLCV history spine, options-chain archive, earnings calendar, forward
walk marks, and the ritual heartbeat file the wrapper writes. Thresholds are
deliberately tolerant of a single missed session (providers lag; holidays
happen) and unforgiving of a silent week.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from dopey_core.market_calendar import trading_days_between
from dopey_options.chain_snapshot_loader import list_chain_snapshot_dates
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_RAW_DIR = REPO_ROOT / "dopey_data" / "history" / "raw"
EARNINGS_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "earnings_calendar"
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
HEARTBEAT_PATH = REPO_ROOT / "artifacts" / "dopey" / "observability" / "ritual_heartbeat.json"
FRESHNESS_PATH = REPO_ROOT / "artifacts" / "dopey" / "observability" / "data_freshness.json"

# sessions-behind thresholds: (amber_at, red_at)
THRESHOLDS = {
    "ohlcv_spine": (3, 6),
    "chain_archive": (2, 5),
    "earnings_calendar": (4, 8),
    "forward_walk_marks": (2, 5),
    "ritual_heartbeat": (2, 5),
    "macro_context": (4, 8),
}
MACRO_VOL_PATH = REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context" / "vol_term_structure.csv"


def classify_lag(lane: str, sessions_behind: int | None) -> str:
    if sessions_behind is None:
        return "red_missing"
    amber_at, red_at = THRESHOLDS[lane]
    if sessions_behind >= red_at:
        return "red_stale"
    if sessions_behind >= amber_at:
        return "amber"
    return "green"


def latest_ohlcv_spine_date() -> str | None:
    """Max bar date present across staged history CSVs (cheap tail read per file)."""
    if not HISTORY_RAW_DIR.exists():
        return None
    latest: str | None = None
    for path in HISTORY_RAW_DIR.glob("*.csv"):
        try:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(size - 4096, 0))
                tail = handle.read().decode("utf-8", errors="replace")
        except OSError:
            continue
        for line in reversed(tail.splitlines()):
            token = line.split(",", 1)[0].strip()
            if len(token) == 10 and token[4] == "-" and token[7] == "-":
                if latest is None or token > latest:
                    latest = token
                break
    return latest


def latest_earnings_date() -> str | None:
    if not EARNINGS_DIR.exists():
        return None
    stems = sorted(path.name.split("_")[0] for path in EARNINGS_DIR.glob("*_earnings.csv"))
    return stems[-1] if stems else None


def run_data_freshness_sentinel(as_of: date | None = None) -> dict[str, Any]:
    today = as_of or date.today()
    observed: dict[str, str | None] = {
        "ohlcv_spine": latest_ohlcv_spine_date(),
        "chain_archive": (list_chain_snapshot_dates() or [None])[-1],
        "earnings_calendar": latest_earnings_date(),
        "forward_walk_marks": None,
        "ritual_heartbeat": None,
        "macro_context": None,
    }
    if MACRO_VOL_PATH.exists():
        latest_macro = ""
        for line in MACRO_VOL_PATH.read_text(encoding="utf-8").splitlines()[1:]:
            token = line.split(",", 1)[0].strip()
            if len(token) == 10 and token > latest_macro:
                latest_macro = token
        observed["macro_context"] = latest_macro or None
    if LEDGER_PATH.exists():
        try:
            ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
            observed["forward_walk_marks"] = str(ledger.get("last_marking_date")) or None
        except (json.JSONDecodeError, OSError):
            observed["forward_walk_marks"] = None
    if HEARTBEAT_PATH.exists():
        # The cmd wrapper writes a locale-formatted timestamp; the file's mtime is
        # the reliable machine-readable signal.
        observed["ritual_heartbeat"] = date.fromtimestamp(HEARTBEAT_PATH.stat().st_mtime).isoformat()

    lanes: dict[str, dict[str, Any]] = {}
    for lane, latest in observed.items():
        sessions_behind: int | None = None
        if latest:
            try:
                sessions_behind = trading_days_between(date.fromisoformat(latest), today)
            except ValueError:
                sessions_behind = None
        lanes[lane] = {
            "latest_observed_date": latest,
            "sessions_behind": sessions_behind,
            "state": classify_lag(lane, sessions_behind),
        }
    # The heartbeat lane only goes red once the ritual has EVER run; before the
    # first scheduled firing, its absence is expected and reported as amber.
    if lanes["ritual_heartbeat"]["state"] == "red_missing":
        lanes["ritual_heartbeat"]["state"] = "amber_never_ran"

    states = [str(lane_record["state"]) for lane_record in lanes.values()]
    overall = "red" if any(state.startswith("red") for state in states) else ("amber" if any(state.startswith("amber") for state in states) else "green")
    summary: dict[str, Any] = {
        "artifact_type": "data_freshness_summary",
        "freshness_status": f"data_freshness_{overall}",
        "as_of": today.isoformat(),
        "lanes": lanes,
        "thresholds_sessions_behind": {lane: {"amber_at": pair[0], "red_at": pair[1]} for lane, pair in THRESHOLDS.items()},
        "unit": "trading_sessions_behind (weekends + fixed US holiday list excluded)",
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(FRESHNESS_PATH, summary)
    if overall == "red":
        raise RuntimeError(f"data_freshness_red:{[lane for lane, record in lanes.items() if str(record['state']).startswith('red')]}")
    return summary
