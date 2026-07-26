"""OPERATOR TOOL - intraday market-hours analyze/plan/evaluate routine.

Runs hourly during regular trading hours and produces a DECISION PACKET for a
human: how the open paper book sits against LIVE quotes right now, which
positions are approaching the pinned discipline's stop/target, the live book
P&L, standing research flags (crowding / fundamentals shorts / earnings), and
a put/call opportunity WATCH list. It plans; it does not act.

HARD BOUNDARIES (the point of this file):
- Places NO orders. Sets NO limit orders. There is no broker wiring here and
  none is added. Any "proposed limit" is a MODEL-ESTIMATED indicative number
  for a human to sanity-check, never an instruction sent anywhere.
- Enters NO paper positions. The forward walk owns entries/marks and does so
  ONCE per session at close - intraday entry would redefine the evidence
  semantics ("3 marking sessions" = 3 days, not 3 hours) and corrupt the very
  sample we accrue toward launch. This routine writes ONLY its own intraday
  artifact and never touches the forward-walk ledger or any evidence artifact.
- The readiness gate is the authority on whether ANY of this is actionable;
  it currently reports not_action_ready (no demonstrated edge). Every proposal
  is stamped with that verdict. Paper-only, live-blocked, read-only.

Usage:  .venv\\Scripts\\python operator_tools\\operator_intraday.py
Schedule (self-gates to RTH, so an hourly all-day trigger is fine):
  schtasks /create /tn DOPEY_Intraday /tr "C:\\Users\\CH\\dopey\\operator_tools\\intraday.cmd" /sc hourly /st 09:30 /f
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_core.market_calendar import is_trading_day  # noqa: E402
from dopey_options.risk_free_rate import resolve_risk_free_rate  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402
from dopey_risk_engine.exit_playbook import build_position_playbook  # noqa: E402
from dopey_core.repo_paths import REPORTS_DIR  # noqa: E402

LEDGER_PATH = REPO / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
MACRO_SUMMARY_PATH = REPO / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
CONTEXT_PATH = REPO / "artifacts" / "dopey" / "market_context" / "entry_context_fusion.jsonl"
INTRADAY_PATH = REPO / "artifacts" / "dopey" / "intraday" / "intraday_decision_packet.json"
INTRADAY_MD = REPORTS_DIR / "INTRADAY_WATCH.md"

APPROACH_PCT = 0.03           # within 3% of a trigger spot = "approaching"
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)


def _market_hours_now() -> tuple[bool, str]:
    """True only inside RTH on a trading day, evaluated in US/Eastern."""
    try:
        from zoneinfo import ZoneInfo

        now_et = datetime.now(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 - tz db absent: fall back to local wall clock
        now_et = datetime.now()
    if not is_trading_day(now_et.date()):
        return False, f"non_trading_day_{now_et.date().isoformat()}"
    if not (RTH_OPEN <= now_et.time() <= RTH_CLOSE):
        return False, f"outside_rth_{now_et.strftime('%H:%M')}_ET"
    return True, now_et.strftime("%Y-%m-%d %H:%M ET")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def fetch_live_spots(symbols: list[str]) -> dict[str, float]:
    """Current underlying prices (yfinance fast_info; personal research, no
    broker). A symbol that fails to fetch is simply omitted (position keeps its
    last known spot)."""
    import yfinance as yf

    spots: dict[str, float] = {}
    for symbol in symbols:
        try:
            price = float(yf.Ticker(symbol).fast_info["last_price"])
            if price > 0:
                spots[symbol] = price
        except Exception:  # noqa: BLE001 - operator lane: skip and continue
            continue
    return spots


def assess_position(position: dict, live_spot: float | None, risk_free: float) -> dict:
    spot = live_spot if live_spot and live_spot > 0 else float(
        position.get("current_spot") or position["entry_spot"]
    )
    live = dict(position)
    live["current_spot"] = spot
    book = build_position_playbook(live, risk_free)
    flat = next(s for s in book["scenarios"] if s["iv_scenario"] == "iv_flat_x1.0")
    current_cell = next(c for c in flat["grid"] if c["spot_move_pct"] == 0.0)
    stop_trig, tgt_trig = flat["stop_trigger_spot"], flat["target_trigger_spot"]
    status = "in_band"
    if stop_trig and abs(spot - stop_trig) / spot <= APPROACH_PCT:
        status = "approaching_stop"
    elif tgt_trig and abs(spot - tgt_trig) / spot <= APPROACH_PCT:
        status = "approaching_target"
    if current_cell["mark_return"] <= -0.5:
        status = "at_or_past_stop"
    elif current_cell["mark_return"] >= 1.0:
        status = "at_or_past_target"
    return {
        "position_id": position.get("position_id"),
        "symbol": position.get("symbol"),
        "candidate_strategy": position.get("candidate_strategy"),
        "live_spot": round(spot, 4),
        "spot_source": "live" if live_spot else "ledger_last_known",
        "current_mark_return": current_cell["mark_return"],
        "current_pnl_premium_units": current_cell["pnl_premium_units"],
        "stop_trigger_spot": stop_trig,
        "target_trigger_spot": tgt_trig,
        "sessions_until_time_stop": book["sessions_until_time_stop"],
        "intraday_status": status,
    }


def opportunity_watch(macro: dict) -> dict:
    """Standing put-side research flags surfaced for review. NOT entries and
    NOT orders - the daily post-close walk decides entries under the same
    signal+context gates, and the readiness gate governs whether any of it is
    actionable (currently: no)."""
    fundamentals = macro.get("fundamentals", {}) if isinstance(macro.get("fundamentals"), dict) else {}
    attention = macro.get("attention", {}) if isinstance(macro.get("attention"), dict) else {}
    congress = macro.get("congress", {}) if isinstance(macro.get("congress"), dict) else {}
    return {
        "put_side_fundamental_shorts_tradable": fundamentals.get("short_candidates_tradable_now", []),
        "put_side_fundamental_shorts_watchlist": fundamentals.get("short_candidates_watchlist_only", []),
        "crowded_attention_fade_flags": attention.get("crowded_attention_candidates", []),
        "congress_notable_selling": congress.get("notable_selling", []),
        "proposal_semantics": "research_flags_for_human_review_not_orders_not_paper_entries",
        "entries_decided_by": "daily_post_close_forward_walk_under_signal_and_context_gates",
    }


def main() -> int:
    open_now, when = _market_hours_now()
    INTRADAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    base = {
        "artifact_type": "intraday_decision_packet",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market_clock": when,
        "orders_placed": 0,
        "limit_orders_set": 0,
        "paper_entries_made": 0,
        "execution": "blocked_no_broker_wiring_human_places_any_order",
        "evidence_semantics_untouched": True,
        "read_only": True,
        "paper_only": True,
        "live_blocked": True,
    }
    if not open_now:
        base["intraday_status"] = f"market_closed_{when}_no_packet"
        write_json_atomic(INTRADAY_PATH, base)
        print(json.dumps({"status": base["intraday_status"]}))
        return 0

    ledger = _load(LEDGER_PATH)
    positions = ledger.get("open_positions", []) if isinstance(ledger, dict) else []
    macro = _load(MACRO_SUMMARY_PATH)
    gate = _load(REPO / "artifacts" / "dopey" / "broker_readiness" / "action_readiness_gate.json")
    risk_free, risk_free_source = resolve_risk_free_rate()

    symbols = sorted({str(p.get("symbol", "")) for p in positions if p.get("symbol")})
    spots = fetch_live_spots(symbols) if symbols else {}
    assessments = [assess_position(p, spots.get(str(p.get("symbol", ""))), risk_free) for p in positions]
    approaching = [a for a in assessments if a["intraday_status"] not in {"in_band"}]
    live_pnl = round(sum(a["current_pnl_premium_units"] for a in assessments), 4)

    packet = dict(base)
    packet.update({
        "intraday_status": "intraday_packet_ready",
        "risk_free_rate": risk_free,
        "risk_free_source": risk_free_source,
        "open_positions": len(positions),
        "live_spots_fetched": len(spots),
        "live_book_pnl_premium_units": live_pnl,
        "positions_needing_attention": [a["position_id"] for a in approaching],
        "assessments": assessments,
        "opportunity_watch": opportunity_watch(macro),
        "readiness_gate": gate.get("readiness_status", "unknown"),
        "gate_missing_requirements": gate.get("missing_requirements", []),
        "action_note": (
            "This is a plan, not an instruction. The gate is "
            f"{gate.get('readiness_status', 'unknown')}; no order is placed by this routine "
            "regardless of gate state - a human reviews and acts."
        ),
    })
    write_json_atomic(INTRADAY_PATH, packet)
    _write_md(packet)
    print(json.dumps({
        "status": "intraday_packet_ready",
        "market": when,
        "open_positions": len(positions),
        "attention": packet["positions_needing_attention"],
        "live_book_pnl": live_pnl,
        "gate": packet["readiness_gate"],
    }, indent=2))
    return 0


def _write_md(packet: dict) -> None:
    lines = [
        "# DOPEY Intraday Watch",
        "",
        f"{packet['market_clock']} — **{packet['open_positions']}** open, "
        f"live book P&L **{packet['live_book_pnl_premium_units']}** premium units. "
        f"Gate: **{packet['readiness_gate']}**.",
        "",
        "> Plan only. No orders placed, no limit orders set, no paper entries made. "
        "A human reviews and acts. Paper-only, live-blocked.",
        "",
        "## Positions needing attention",
        "",
    ]
    attn = [a for a in packet["assessments"] if a["intraday_status"] != "in_band"]
    if attn:
        for a in attn:
            lines.append(
                f"- `{a['symbol']}` {a['candidate_strategy']} — **{a['intraday_status']}** — "
                f"spot {a['live_spot']} ({a['spot_source']}), mark_return {a['current_mark_return']}, "
                f"stop@{a['stop_trigger_spot']} target@{a['target_trigger_spot']}, "
                f"{a['sessions_until_time_stop']} sessions to time-stop"
            )
    else:
        lines.append("- none — all open positions sit inside their discipline band")
    watch = packet["opportunity_watch"]
    lines += [
        "",
        "## Opportunity watch (research flags — not orders)",
        "",
        f"- Put-side fundamental shorts (tradable): {', '.join(watch['put_side_fundamental_shorts_tradable']) or 'none'}",
        f"- Crowded-attention fade flags: {', '.join(watch['crowded_attention_fade_flags']) or 'none'}",
        f"- Congress notable selling: {', '.join(watch['congress_notable_selling']) or 'none'}",
        "",
        f"Missing gate requirements: {', '.join(packet['gate_missing_requirements']) or 'none'}",
    ]
    INTRADAY_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
