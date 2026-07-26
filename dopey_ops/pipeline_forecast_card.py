"""Pipeline Forecast Card: predict before you look (Feynman).

"The first principle is that you must not fool yourself - and you are the
easiest person to fool." The cheapest defense Feynman practiced: state the
expected result BEFORE running the experiment, then grade the miss. DOPEY
predicts markets all day but never predicts ITSELF. This card makes the
pipeline state, ex ante, what its own machinery should produce at the next
marking session - how many positions must close under the deterministic exit
policy - and then scores every prediction against what actually happened.

The value is the ERROR, not the forecast: a systematic over-prediction of
closes means quote quality or continuity is silently eating throughput (time
stops deferring on unreliable quotes); an under-prediction means stops and
targets fire more than the time-policy intuition suggests. Both are pipeline
self-knowledge no single marking run surfaces.

Measure-only, never a gate input. Predictions are made from the ledger alone
(no quotes, no lookahead) and are immutable once scored.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from dopey_research_pipeline.artifact_io import write_json_atomic

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
CARD_PATH = REPO_ROOT / "artifacts" / "dopey" / "ops" / "pipeline_forecast_card.json"

CARD_VERSION = "dopey-pipeline-forecast-card-v1"
MAX_SCORED_HISTORY = 120
# Mirrors the forward walk's exit policy without importing it (predictions must
# never share mutable state with the thing they predict).
TIME_STOP_SESSIONS = 3
FORCE_CLOSE_DTE = 5


def _load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def deterministic_close_forecast(open_positions: list[dict[str, Any]], as_of: str) -> dict[str, Any]:
    """Positions the exit policy MUST close at the next executable mark."""
    time_stop_due = 0
    force_close_due = 0
    pending_exit = 0
    for position in open_positions:
        if str(position.get("pending_exit_reason", "")):
            pending_exit += 1
            continue
        if int(position.get("marking_sessions", 0)) >= TIME_STOP_SESSIONS - 1:
            time_stop_due += 1
            continue
        try:
            dte = (date.fromisoformat(str(position["expiry"])) - date.fromisoformat(as_of)).days
        except (KeyError, ValueError):
            continue
        if dte <= FORCE_CLOSE_DTE + 1:
            force_close_due += 1
    point = time_stop_due + force_close_due + pending_exit
    return {
        "predicted_time_stop_closes": time_stop_due,
        "predicted_force_closes": force_close_due,
        "predicted_pending_exit_closes": pending_exit,
        "predicted_closes_point": point,
        "predicted_closes_upper": len(open_positions),  # stops/targets can close anything
        "open_position_count": len(open_positions),
    }


def score_forecast(prediction: dict[str, Any], actual_closes: int) -> dict[str, Any]:
    point = int(prediction.get("predicted_closes_point", 0))
    upper = int(prediction.get("predicted_closes_upper", 0))
    return {
        "actual_closes": actual_closes,
        "signed_error": actual_closes - point,
        "absolute_error": abs(actual_closes - point),
        "within_band": point <= actual_closes <= upper,
        "under_delivered": actual_closes < point,
    }


def run_pipeline_forecast_card() -> dict[str, Any]:
    ledger = _load_json(LEDGER_PATH)
    card = _load_json(CARD_PATH)
    scored: list[dict[str, Any]] = list(card.get("scored", []))
    pending = card.get("pending_forecast")
    last_marking = str(ledger.get("last_marking_date", ""))

    # Score the pending forecast once a NEWER marking session has happened.
    if isinstance(pending, dict) and last_marking > str(pending.get("as_of_marking_date", "")):
        actual = sum(
            1
            for trade in ledger.get("closed_trades", [])
            if str(trade.get("exit_date", "")) == last_marking
        )
        scored.append(
            {
                "forecast_made_after_marking": pending.get("as_of_marking_date"),
                "scored_at_marking": last_marking,
                **{k: pending[k] for k in pending if k.startswith("predicted_")},
                **score_forecast(pending, actual),
            }
        )
        scored = scored[-MAX_SCORED_HISTORY:]
        pending = None

    if pending is None and last_marking:
        pending = {
            "as_of_marking_date": last_marking,
            **deterministic_close_forecast(ledger.get("open_positions", []), last_marking),
        }

    recent = scored[-20:]
    n = len(recent)
    summary = {
        "artifact_type": "pipeline_forecast_card",
        "card_version": CARD_VERSION,
        "forecast_card_status": "forecast_card_current" if last_marking else "blocked_no_forward_ledger",
        "pending_forecast": pending,
        "scored": scored,
        "scored_count": len(scored),
        "rolling_mean_absolute_error": round(sum(s["absolute_error"] for s in recent) / n, 4) if n else None,
        "rolling_mean_signed_error": round(sum(s["signed_error"] for s in recent) / n, 4) if n else None,
        "under_delivery_rate": round(sum(1 for s in recent if s["under_delivered"]) / n, 4) if n else None,
        "reading": (
            "persistent negative signed error (under-delivery) = quote quality/continuity is "
            "silently eating throughput; positive = stops and targets dominate the time policy"
        ),
        "never_a_gate_input": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(CARD_PATH, summary)
    return summary
