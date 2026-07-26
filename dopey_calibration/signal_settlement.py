"""Phantom signal settlement ledger + contested-truth calibration.

The dummy repo's two disciplines, translated to dopey's directional signals:

PHANTOM GRADING - the forward walk trades a handful of positions, but the
signal engine emits gated directional setups across the whole universe every
session. Every one of those signals gets SETTLED at its horizon against the
real spine (did the direction realize over the next HORIZON trading days?)
whether or not it was traded. Signal-quality evidence accrues at signal
velocity instead of position velocity.

CONTESTED TRUTH - a signal that agrees with the prevailing drift and comes
true proves nothing. A phantom is CONTESTED when its direction OPPOSES the
trailing 20d drift sign; calibration is reported overall AND contested-only,
and per-family trust is earned on the contested record.

HARD SEMANTICS (stamped on every artifact):
- signal_calibration_not_trade_evidence: no fills, no premium, no costs -
  this is direction-realization bookkeeping on real closes.
- The readiness gate NEVER reads this lane. It cannot move any gate check.
- Trust scores are advisory research weights (adversarial-panel visibility);
  they enforce nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGNALS_PATH = REPO_ROOT / "artifacts" / "dopey" / "signals" / "directional_setup_signals.jsonl"
HISTORY_RAW_DIR = REPO_ROOT / "dopey_data" / "history" / "raw"
CALIBRATION_DIR = REPO_ROOT / "artifacts" / "dopey" / "signal_calibration"
PHANTOM_LEDGER_PATH = CALIBRATION_DIR / "phantom_settlements.jsonl"
CALIBRATION_SUMMARY_PATH = CALIBRATION_DIR / "signal_calibration_summary.json"

HORIZON_TRADING_DAYS = 10          # matches the research horizon everywhere else
DRIFT_WINDOW_DAYS = 20             # contested = direction opposes this drift
MIN_SETTLEMENTS_FOR_TRUST = 30     # below this a family's trust is "unrated"
FLAT_RETURN_EPSILON = 0.002        # |fwd| below this = flat, graded as a miss for both directions


def _load_closes(symbol: str) -> tuple[list[str], list[float]]:
    path = HISTORY_RAW_DIR / f"{symbol}.csv"
    dates: list[str] = []
    closes: list[float] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split(",")
            if len(parts) >= 7:
                try:
                    close = float(parts[6])
                except ValueError:
                    continue
                if close > 0:
                    dates.append(parts[0])
                    closes.append(close)
    except OSError:
        pass
    return dates, closes


def settle_signal(signal: dict, dates: list[str], closes: list[float]) -> dict | None:
    """Grade one signal against the real spine. None = not yet settleable
    (horizon has not fully elapsed on real data - NEVER graded early)."""
    signal_date = str(signal.get("signal_date", ""))
    direction = str(signal.get("direction", ""))
    if not signal_date or direction not in {"bullish", "bearish"}:
        return None
    try:
        index = dates.index(signal_date)
    except ValueError:
        return None
    if index + HORIZON_TRADING_DAYS >= len(dates):
        return None  # horizon not elapsed: no early grading, ever
    base = closes[index]
    settle_close = closes[index + HORIZON_TRADING_DAYS]
    if base <= 0:
        return None
    forward_return = settle_close / base - 1.0
    realized_direction = (
        "flat" if abs(forward_return) < FLAT_RETURN_EPSILON
        else ("bullish" if forward_return > 0 else "bearish")
    )
    hit = realized_direction == direction
    drift = 0.0
    if index >= DRIFT_WINDOW_DAYS and closes[index - DRIFT_WINDOW_DAYS] > 0:
        drift = base / closes[index - DRIFT_WINDOW_DAYS] - 1.0
    contested = (direction == "bullish" and drift < 0) or (direction == "bearish" and drift > 0)
    return {
        "artifact_type": "phantom_signal_settlement",
        "signal_id": str(signal.get("signal_id", "")),
        "signal_family": str(signal.get("signal_family", "")),
        "symbol": str(signal.get("symbol", "")),
        "direction": direction,
        "signal_date": signal_date,
        "settle_date": dates[index + HORIZON_TRADING_DAYS],
        "horizon_trading_days": HORIZON_TRADING_DAYS,
        "forward_return": round(forward_return, 6),
        "realized_direction": realized_direction,
        "hit": hit,
        "trailing_drift_20d": round(drift, 6),
        "contested": contested,
        "semantics": "signal_calibration_not_trade_evidence",
        "traded": False,
        "paper_only": True,
        "live_blocked": True,
        "promotion_allowed": False,
    }


def _trust_from_record(hits: int, count: int, contested_hits: int, contested_count: int) -> dict:
    """Advisory trust per the contested-truth discipline: rated on the
    contested record when it has sample, else explicitly unrated."""
    overall = hits / count if count else 0.0
    contested_rate = contested_hits / contested_count if contested_count else 0.0
    if contested_count >= MIN_SETTLEMENTS_FOR_TRUST:
        # 0.5 = coin-flip on the contested record -> trust 1.0 (neutral);
        # earned strictly by beating the flip where it disagreed with drift
        trust = round(max(0.25, min(2.0, 1.0 + 2.0 * (contested_rate - 0.5))), 4)
        rating = "rated_on_contested_record"
    else:
        trust = 1.0
        rating = "unrated_insufficient_contested_sample"
    return {
        "settlements": count,
        "hit_rate": round(overall, 4),
        "contested_settlements": contested_count,
        "contested_hit_rate": round(contested_rate, 4),
        "trust": trust,
        "trust_rating": rating,
        "advisory_only": True,
        "enforcement": "never",
    }


def run_signal_calibration() -> dict:
    """Settle every settleable gated signal; aggregate calibration + trust."""
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    signals: list[dict] = []
    try:
        for line in SIGNALS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    signals.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    closes_cache: dict[str, tuple[list[str], list[float]]] = {}
    settlements: list[dict] = []
    pending = 0
    for signal in signals:
        symbol = str(signal.get("symbol", ""))
        if not symbol:
            continue
        if symbol not in closes_cache:
            closes_cache[symbol] = _load_closes(symbol)
        graded = settle_signal(signal, *closes_cache[symbol])
        if graded is None:
            pending += 1
            continue
        settlements.append(graded)

    with PHANTOM_LEDGER_PATH.open("w", encoding="utf-8") as handle:
        for record in settlements:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    by_family: dict[str, dict[str, int]] = {}
    for record in settlements:
        family = record["signal_family"] or "unknown"
        stats = by_family.setdefault(family, {"hits": 0, "count": 0, "contested_hits": 0, "contested_count": 0})
        stats["count"] += 1
        stats["hits"] += int(record["hit"])
        if record["contested"]:
            stats["contested_count"] += 1
            stats["contested_hits"] += int(record["hit"])

    family_trust = {
        family: _trust_from_record(s["hits"], s["count"], s["contested_hits"], s["contested_count"])
        for family, s in sorted(by_family.items())
    }
    total = len(settlements)
    total_hits = sum(int(r["hit"]) for r in settlements)
    contested = [r for r in settlements if r["contested"]]
    summary = {
        "artifact_type": "signal_calibration_summary",
        "signal_calibration_status": "phantom_settlements_graded" if settlements else "no_settleable_signals",
        "settled_total": total,
        "pending_horizon_not_elapsed": pending,
        "overall_hit_rate": round(total_hits / total, 4) if total else 0.0,
        "contested_total": len(contested),
        "contested_hit_rate": round(sum(int(r["hit"]) for r in contested) / len(contested), 4) if contested else 0.0,
        "family_trust": family_trust,
        "horizon_trading_days": HORIZON_TRADING_DAYS,
        "disciplines": {
            "phantom_grading": "every gated signal settles at horizon, traded or not (dummy repo adaptation)",
            "contested_truth": "trust earned only where the signal DISAGREED with 20d drift - agreeing and being right proves nothing",
        },
        "semantics": "signal_calibration_not_trade_evidence",
        "gate_visibility": "the readiness gate never reads this lane",
        "trust_enforcement": "advisory research weights only - recorded, never enforced",
        "paper_only": True,
        "live_blocked": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
    CALIBRATION_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def load_calibration_summary() -> dict:
    """Read the last-written calibration summary (empty dict if never run)."""
    try:
        return json.loads(CALIBRATION_SUMMARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def family_trust_for(family: str, summary: dict | None = None) -> dict:
    """Advisory contested-truth trust for a signal family, for consumers that
    want visibility (the adversarial panel). ALWAYS returns a record: an
    uncalibrated family is stamped 'unrated' so a caller can never read a
    missing family as a pass, a block, or edge. Enforcement is never; pass
    summary=None to read the artifact, or an explicit dict to stay offline."""
    summary = load_calibration_summary() if summary is None else summary
    trust = (summary.get("family_trust") or {}).get(str(family))
    if not isinstance(trust, dict):
        return {
            "family": str(family),
            "trust": 1.0,
            "trust_rating": "unrated_no_calibration_for_family",
            "contested_settlements": 0,
            "contested_hit_rate": None,
            "advisory_only": True,
            "enforcement": "never",
            "semantics": "signal_calibration_not_trade_evidence",
        }
    record = dict(trust)
    record["family"] = str(family)
    record["advisory_only"] = True
    record["enforcement"] = "never"
    record["semantics"] = "signal_calibration_not_trade_evidence"
    return record


def calibration_context(summary: dict | None = None) -> dict:
    """System-wide directional-signal base rate for advisory visibility. NOT a
    per-family claim, NOT trade evidence; the readiness gate never reads it.
    This is the contested-truth reality check the bull case must beat."""
    summary = load_calibration_summary() if summary is None else summary
    if not summary:
        return {
            "status": "no_calibration_yet",
            "settled_total": 0,
            "overall_hit_rate": None,
            "contested_hit_rate": None,
            "note": "no phantom calibration has been produced yet",
            "advisory_only": True,
            "enforcement": "never",
            "semantics": "signal_calibration_not_trade_evidence",
        }
    return {
        "status": summary.get("signal_calibration_status", "unknown"),
        "settled_total": summary.get("settled_total", 0),
        "overall_hit_rate": summary.get("overall_hit_rate"),
        "contested_total": summary.get("contested_total", 0),
        "contested_hit_rate": summary.get("contested_hit_rate"),
        "note": (
            "system-wide directional-signal base rate - a signal that only "
            "agrees with the prevailing drift and comes true proves nothing; "
            "advisory context for the bull lens, never enforced, gate-blind"
        ),
        "advisory_only": True,
        "enforcement": "never",
        "semantics": "signal_calibration_not_trade_evidence",
    }


if __name__ == "__main__":
    result = run_signal_calibration()
    print(json.dumps({
        "signal_calibration_status": result["signal_calibration_status"],
        "settled": result["settled_total"],
        "pending": result["pending_horizon_not_elapsed"],
        "overall_hit_rate": result["overall_hit_rate"],
        "contested_hit_rate": result["contested_hit_rate"],
        "families": list(result["family_trust"]),
    }, indent=2))
