"""Forward paper walk: ex-ante, quote-priced paper positions.

The strongest honest evidence lane DOPEY has. Each run against a fresh
operator-staged chain snapshot:

1. Marks open paper positions at an executable REAL bid (conservative long
   exit side). Dislocated quotes are preserved as observations but cannot
   trigger an exit; time/expiry exits defer until the next executable quote.
2. Opens new paper positions from FRESH real-history directional setups only
   (signal within FRESH_SIGNAL_MAX_AGE_DAYS of the snapshot), filled at the
   REAL ask plus commission - the price a retail taker actually pays.
3. Accumulates a closed-trade track record. Because entries are decided before
   the future exists, this lane has zero lookahead and zero backtest bias; the
   cost is that evidence accrues at the speed of reality.

Positions are quote-priced paper records: no broker, no orders, no sizing
beyond 1 contract in premium units. Paper-only, live-blocked, promotion still
gated by the statistical truth layer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_autonomy.public_champion_common import sector_for_symbol
from dopey_backtest.forward_evidence_integrity import (
    CENSORED_OUTCOME,
    INTEGRITY_VERSION,
    POLICY_REPLAY_PATH,
    VALIDATED_OUTCOME,
    build_integrity_summary,
    write_integrity_artifacts,
)
from dopey_options.chain_snapshot_loader import load_latest_chain_snapshot
from dopey_options.liquidity_engine import (
    ENTRY_POLICY_VERSION,
    EXIT_POLICY_VERSION,
    FORWARD_ENTRY_MAX_RELATIVE_SPREAD,
    FORWARD_ENTRY_MIN_OPEN_INTEREST,
    FORWARD_ENTRY_MIN_VOLUME,
    FORWARD_EXIT_MAX_RELATIVE_SPREAD,
    forward_entry_liquidity_rejection_reasons,
    forward_exit_quote_rejection_reasons,
    quote_relative_spread,
)
from dopey_research_pipeline.artifact_io import read_json_guarded, write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_risk_engine.forward_portfolio_policy import (
    MAX_NEW_POSITIONS_PER_RUN,
    MAX_OPEN_POSITIONS,
    MAX_POSITIONS_PER_DIRECTION,
    MAX_POSITIONS_PER_SECTOR,
    PORTFOLIO_POLICY_VERSION,
    portfolio_counts as _portfolio_counts,
    strategy_direction as _strategy_direction,
)
from dopey_backtest import veto_shadow
from dopey_risk_engine.adversarial_stress_engine import compute_book_stress
from dopey_risk_engine.forward_entry_guard import (
    ENTRY_GUARD_VERSION,
    MAX_SYMBOL_PREMIUM_SHARE,
    adversarial_rejection_reasons,
    concentration_rejection_reasons,
    existing_book_stress_rejection_reasons,
)
from dopey_core.repo_paths import REPORTS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
FORWARD_WALK_DIR = REPO_ROOT / "artifacts" / "dopey" / "forward_walk"
LEDGER_PATH = FORWARD_WALK_DIR / "forward_walk_ledger.json"
CLOSED_TRADES_PATH = FORWARD_WALK_DIR / "forward_walk_closed_trades.jsonl"
SUMMARY_PATH = FORWARD_WALK_DIR / "forward_walk_summary.json"
DIRECTIONAL_SETUP_SIGNALS_PATH = REPO_ROOT / "artifacts" / "dopey" / "signals" / "directional_setup_signals.jsonl"
FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH = REPO_ROOT / "artifacts" / "dopey" / "signals" / "directional_setup_signals_fresh.jsonl"
FORWARD_WALK_REPORT_PATH = REPORTS_DIR / "DOPEY_FORWARD_PAPER_WALK_REPORT.md"

PREMIUM_STOP_PCT = -0.50
PREMIUM_TARGET_PCT = 1.00
MAX_MARKING_SESSIONS = 3
FORCE_CLOSE_DTE = 5
FRESH_SIGNAL_MAX_AGE_DAYS = 7
COMMISSION_PREMIUM_UNITS = 0.0065
ENTRY_CONTEXT_PATH = REPO_ROOT / "artifacts" / "dopey" / "market_context" / "entry_context_fusion.jsonl"
MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
DISCIPLINE_LOSS_STREAK_HALT = 5
DISCIPLINE_DRAWDOWN_HALT_PCT = 0.30
DISCIPLINE_HALT_COOLDOWN_SESSIONS = 5
DISCIPLINE_HALT_POLICY_VERSION = "dopey-forward-discipline-halt-v2"
TARGET_ENTRY_DTE = 30
ENTRY_DTE_BAND = (21, 45)
MISSING_QUOTE_CENSOR_AFTER_OBSERVATIONS = 3


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"forward-walk dependency is unreadable: path={path}, error={error}") from error
    if not isinstance(value, dict):
        raise TypeError(f"forward-walk dependency must be an object: path={path}")
    return value


def _integrity_state(ledger: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    policy_replay = _load_optional_json(POLICY_REPLAY_PATH)
    summary, outcomes = build_integrity_summary(ledger, policy_replay)
    return summary, outcomes


def _validated_closed_trades(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    _summary, outcomes = _integrity_state(ledger)
    return outcomes["validated"]


def _entry_context_by_symbol() -> dict[str, dict[str, Any]]:
    if not ENTRY_CONTEXT_PATH.exists():
        return {}
    contexts: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(ENTRY_CONTEXT_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or not str(record.get("symbol", "")):
            raise ValueError(f"entry context row is invalid: path={ENTRY_CONTEXT_PATH}, line={line_number}")
        symbol = str(record.get("symbol", ""))
        contexts[symbol] = record
    return contexts


def _discipline_halt(ledger: dict[str, Any]) -> str | None:
    """Tilt protection: halt new entries on a loss streak or deep ledger drawdown.

    A tripped halt LATCHES for DISCIPLINE_HALT_COOLDOWN_SESSIONS marking
    sessions (the trailing-window conditions alone would silently un-halt as
    soon as one closing run shifted the window).
    """
    latched = ledger.get("last_discipline_halt")
    if isinstance(latched, dict) and int(latched.get("cooldown_sessions_remaining", 0)) > 0:
        return f"latched_{latched.get('reason', 'halt')}"
    closed = _closed_trades_since_completed_halt(ledger)
    if len(closed) >= DISCIPLINE_LOSS_STREAK_HALT:
        recent = closed[-DISCIPLINE_LOSS_STREAK_HALT:]
        if all(float(trade.get("path_pnl", 0.0)) < 0.0 for trade in recent):
            return f"loss_streak_halt_{DISCIPLINE_LOSS_STREAK_HALT}_consecutive"
    cumulative = 0.0
    peak = 0.0
    premium_spent = sum(float(trade.get("entry_fill", 0.0)) for trade in closed)
    for trade in closed:
        cumulative += float(trade.get("path_pnl", 0.0))
        peak = max(peak, cumulative)
    if premium_spent > 0 and (peak - cumulative) / premium_spent > DISCIPLINE_DRAWDOWN_HALT_PCT:
        return "drawdown_halt_exceeds_30pct_of_premium_spent"
    return None


def _closed_trades_since_completed_halt(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    closed = _validated_closed_trades(ledger)
    latched = ledger.get("last_discipline_halt")
    if not isinstance(latched, dict) or int(latched.get("cooldown_sessions_remaining", 0)) > 0:
        return closed
    count_at_halt = latched.get("closed_trade_count_at_halt")
    if isinstance(count_at_halt, int):
        return closed[max(min(count_at_halt, len(closed)), 0) :]
    halt_date = str(latched.get("date", ""))
    if not halt_date:
        raise ValueError("completed discipline halt is missing date and closed-trade anchor")
    return [trade for trade in closed if str(trade.get("exit_date", "")) > halt_date]


def _closed_trade_count_at_halt(ledger: dict[str, Any], halt_date: str) -> int:
    return sum(
        1
        for trade in _validated_closed_trades(ledger)
        if str(trade.get("exit_date", "")) <= halt_date
    )


def _new_discipline_halt(
    ledger: dict[str, Any],
    snapshot_date: str,
    halt_reason: str,
) -> dict[str, Any]:
    """Latch against the same validated evidence domain used for re-arming."""

    return {
        "date": snapshot_date,
        "reason": halt_reason,
        "cooldown_sessions_remaining": DISCIPLINE_HALT_COOLDOWN_SESSIONS,
        "closed_trade_count_at_halt": len(_validated_closed_trades(ledger)),
        "halt_policy_version": DISCIPLINE_HALT_POLICY_VERSION,
        "rearm_policy": "new_closed_trade_evidence_after_cooldown_only",
    }


def run_forward_paper_walk() -> dict[str, Any]:
    snapshot = load_latest_chain_snapshot()
    if snapshot["chain_snapshot_status"] != "real_chain_snapshot_validated":
        ledger = _load_ledger()
        integrity_summary, outcomes = _integrity_state(ledger)
        write_integrity_artifacts(integrity_summary, outcomes)
        summary = _summary_base(snapshot["chain_snapshot_status"], ledger, integrity_summary)
        _write_json(SUMMARY_PATH, summary)
        return summary
    ledger = _load_ledger()
    snapshot_date = str(snapshot["snapshot_date"])
    rows_by_contract = {
        (row["symbol"], row["expiry"], row["option_type"], float(row["strike"])): row
        for row in snapshot["rows"]
    }
    newly_closed: list[dict[str, Any]] = []
    newly_censored: list[dict[str, Any]] = []
    if ledger["last_marking_date"] != snapshot_date:
        latched = ledger.get("last_discipline_halt")
        if isinstance(latched, dict) and int(latched.get("cooldown_sessions_remaining", 0)) > 0:
            latched.setdefault("halt_policy_version", DISCIPLINE_HALT_POLICY_VERSION)
            latched.setdefault(
                "closed_trade_count_at_halt",
                _closed_trade_count_at_halt(ledger, str(latched.get("date", ""))),
            )
            latched["cooldown_sessions_remaining"] = int(latched["cooldown_sessions_remaining"]) - 1
        still_open: list[dict[str, Any]] = []
        for position in ledger["open_positions"]:
            key = (position["symbol"], position["expiry"], position["option_type"], float(position["strike"]))
            row = rows_by_contract.get(key)
            if row is None:
                observed = dict(position)
                observed["observation_sessions"] = int(observed.get("observation_sessions", 0)) + 1
                if snapshot_date >= str(position["expiry"]):
                    newly_censored.append(
                        _censor_missing_quote_continuity(
                            observed,
                            snapshot_date,
                            (
                                "contract_expired_without_exact_contract_quote",
                                "quote_continuity_lost_before_observed_exit",
                                "no_exit_fill_observed",
                            ),
                        )
                    )
                    continue
                observed["missed_marks"] = int(observed.get("missed_marks", 0)) + 1
                observed["quote_continuity_status"] = "pending_missing_quote_continuity"
                missing_dates = list(observed.get("missing_quote_dates", []))
                missing_dates.append(snapshot_date)
                observed["missing_quote_dates"] = list(dict.fromkeys(str(value) for value in missing_dates))
                if observed["missed_marks"] >= MISSING_QUOTE_CENSOR_AFTER_OBSERVATIONS:
                    newly_censored.append(
                        _censor_missing_quote_continuity(
                            observed,
                            snapshot_date,
                            ("contract_quote_continuity_lost", "no_exit_fill_observed"),
                        )
                    )
                else:
                    still_open.append(observed)
                continue
            marked_position, closed_position = _mark_position(position, row, snapshot_date)
            if closed_position is not None:
                newly_closed.append(closed_position)
                continue
            if marked_position is None:
                raise RuntimeError(f"forward mark produced no state: position_id={position.get('position_id', '')}")
            still_open.append(marked_position)
        ledger["open_positions"] = still_open
        ledger["closed_trades"].extend(newly_closed)
        ledger["censored_positions"].extend(newly_censored)
        ledger["last_marking_date"] = snapshot_date
    shadow_summary = veto_shadow.mark_shadow_positions(
        rows_by_contract, snapshot_date, mark_position=_mark_position
    )
    new_positions = _open_new_positions(ledger, snapshot, snapshot_date)
    ledger["open_positions"].extend(new_positions)
    write_json_atomic(LEDGER_PATH, ledger, keep_backup=True)
    _write_jsonl(CLOSED_TRADES_PATH, ledger["closed_trades"])
    integrity_summary, outcomes = _integrity_state(ledger)
    write_integrity_artifacts(integrity_summary, outcomes)
    summary = _summary_base("forward_walk_marked", ledger, integrity_summary)
    summary.update(
        {
            "snapshot_date": snapshot_date,
            "newly_closed_count": len(newly_closed),
            "newly_censored_count": len(newly_censored),
            "newly_opened_count": len(new_positions),
            "veto_shadow": {
                "open_phantom_count": shadow_summary["open_phantom_count"],
                "closed_phantom_count": shadow_summary["closed_phantom_count"],
                "shadow_open_result": ledger.get("last_veto_shadow_open_result", {}),
                "never_a_gate_input": True,
            },
        }
    )
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write_json(SUMMARY_PATH, summary)
    _write_report(summary, ledger)
    return summary


def _open_new_positions(
    ledger: dict[str, Any],
    snapshot: dict[str, Any],
    snapshot_date: str,
) -> list[dict[str, Any]]:
    if not DIRECTIONAL_SETUP_SIGNALS_PATH.exists():
        ledger["last_entry_rejections"] = [{"reason_codes": ["missing_directional_setup_signals"]}]
        return []
    if ledger.get("last_entry_date") == snapshot_date:
        return []  # idempotent: one entry pass per snapshot date, however many runs happen
    signal_path = (
        FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH
        if FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH.exists()
        else DIRECTIONAL_SETUP_SIGNALS_PATH
    )
    signals: list[dict[str, Any]] = []
    with signal_path.open("r", encoding="utf-8") as signal_file:
        for line_number, line in enumerate(signal_file, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(
                    f"directional signal row must be an object: path={signal_path}, line={line_number}"
                )
            signal_date = str(value.get("signal_date", "1970-01-01"))
            if 0 <= _age_days(signal_date, snapshot_date) <= FRESH_SIGNAL_MAX_AGE_DAYS:
                signals.append(value)
    used_signal_ids = {str(position.get("signal_id", "")) for position in ledger["open_positions"]}
    used_signal_ids |= {str(trade.get("signal_id", "")) for trade in ledger["closed_trades"]}
    censored_positions = ledger.get("censored_positions", [])
    if not isinstance(censored_positions, list):
        raise TypeError("forward ledger censored_positions must be an array")
    used_signal_ids |= {str(position.get("signal_id", "")) for position in censored_positions}
    eligible = [
        record
        for record in signals
        if record.get("data_source_tier") == "local_real_history"
        and record.get("candidate_strategy") in {"long_call", "long_put"}
        and 0 <= _age_days(str(record.get("signal_date", "1970-01-01")), snapshot_date) <= FRESH_SIGNAL_MAX_AGE_DAYS
        and str(record.get("signal_id", "")) not in used_signal_ids  # one shot per signal, no re-entry churn
    ]
    halt_reason = _discipline_halt(ledger)
    if halt_reason is not None:
        existing = ledger.get("last_discipline_halt")
        if not (isinstance(existing, dict) and int(existing.get("cooldown_sessions_remaining", 0)) > 0):
            ledger["last_discipline_halt"] = _new_discipline_halt(
                ledger,
                snapshot_date,
                halt_reason,
            )
        ledger["last_entry_rejections"] = [{"reason_codes": [halt_reason]}]
        return []
    context_by_symbol = _entry_context_by_symbol()
    macro_summary = _load_optional_json(MACRO_SUMMARY_PATH)
    # Stress evidence is computed in-process on the CURRENT post-exit book, never
    # read from yesterday's artifact: a stale artifact whose position count
    # mismatched today's book rejected every candidate (the book self-jammed on
    # any day an exit or entry changed its size).
    stress_summary = compute_book_stress(ledger["open_positions"])
    existing_stress_rejections = existing_book_stress_rejection_reasons(
        ledger["open_positions"], stress_summary
    )
    eligible.sort(key=lambda record: float(record.get("confidence_proxy", 0.0)), reverse=True)
    open_symbols, sector_counts, direction_counts = _portfolio_counts(ledger["open_positions"])
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in snapshot["rows"]:
        rows_by_symbol.setdefault(str(row["symbol"]), []).append(row)
    opened: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    shadow_candidates: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for record in eligible:
        if len(opened) >= MAX_NEW_POSITIONS_PER_RUN:
            break
        symbol = str(record["symbol"])
        strategy = str(record["candidate_strategy"])
        if symbol in open_symbols:
            rejections.append(_entry_rejection(record, ("symbol_already_open",)))
            continue
        if len(ledger["open_positions"]) + len(opened) >= MAX_OPEN_POSITIONS:
            rejections.append(_entry_rejection(record, ("portfolio_open_position_cap_reached",)))
            continue
        sector = sector_for_symbol(symbol)
        direction = _strategy_direction(strategy)
        if sector_counts[sector] >= MAX_POSITIONS_PER_SECTOR:
            rejections.append(_entry_rejection(record, ("portfolio_sector_cap_reached",)))
            continue
        if direction_counts[direction] >= MAX_POSITIONS_PER_DIRECTION:
            rejections.append(_entry_rejection(record, ("portfolio_direction_cap_reached",)))
            continue
        context = context_by_symbol.get(symbol)
        if context is None:
            rejections.append(_entry_rejection(record, ("missing_entry_context",)))
            continue
        if str(context.get("snapshot_date", "")) != snapshot_date:
            rejections.append(_entry_rejection(record, ("entry_context_not_aligned_to_chain_snapshot",)))
            continue
        entry_bias = str(context.get(f"{strategy}_entry_bias", ""))
        if entry_bias not in {"favorable", "neutral", "unfavorable"}:
            raise ValueError(f"invalid entry bias: symbol={symbol}, strategy={strategy}, bias={entry_bias}")
        if entry_bias == "unfavorable":
            veto_reasons = tuple(str(value) for value in context.get(f"{strategy}_veto_reasons", []))
            veto_reasons = veto_reasons or ("entry_context_unfavorable",)
            rejections.append(_entry_rejection(record, veto_reasons))
            shadow_candidates.append((record, veto_reasons))
            continue
        side = "call" if strategy == "long_call" else "put"
        atm, selection_reasons = _select_entry_contract(rows_by_symbol, symbol, side)
        if atm is None:
            rejections.append(_entry_rejection(record, selection_reasons))
            continue
        ask = float(atm["ask"])
        spot = float(atm["underlying_spot"])
        entry_fill = round(ask + COMMISSION_PREMIUM_UNITS, 6)
        projected_positions = [*ledger["open_positions"], *opened]
        risk_rejections = tuple(
            dict.fromkeys(
                (
                    *existing_stress_rejections,
                    *concentration_rejection_reasons(projected_positions, symbol, entry_fill),
                    *adversarial_rejection_reasons(symbol, strategy, context, macro_summary),
                )
            )
        )
        if risk_rejections:
            rejections.append(_entry_rejection(record, risk_rejections))
            shadow_candidates.append((record, risk_rejections))
            continue
        ledger["position_counter"] = int(ledger.get("position_counter", 0)) + 1
        opened.append(
            {
                "position_id": f"fw-{symbol}-{strategy}-{snapshot_date}-{int(ledger['position_counter']):05d}",
                "symbol": symbol,
                "candidate_strategy": strategy,
                "option_type": side,
                "signal_id": str(record.get("signal_id", "")),
                "signal_family": str(record.get("source_signal_family", "")),
                "signal_date": str(record.get("signal_date", "")),
                "entry_date": snapshot_date,
                "expiry": str(atm["expiry"]),
                "strike": float(atm["strike"]),
                "entry_bid": float(atm["bid"]),
                "entry_ask": ask,
                "entry_fill": entry_fill,
                "entry_spot": spot,
                "entry_iv": float(atm["implied_vol"]),
                "entry_volume": int(atm["volume"]),
                "entry_open_interest": int(atm["open_interest"]),
                "entry_relative_spread": round(quote_relative_spread(float(atm["bid"]), ask), 6),
                "entry_policy_version": ENTRY_POLICY_VERSION,
                "entry_context_snapshot_date": str(context["snapshot_date"]),
                "entry_context_external_status": str(context.get("external_context_status", "unknown")),
                "entry_context_veto_reasons": list(context.get(f"{strategy}_veto_reasons", [])),
                "entry_sector": sector,
                "signal_confidence_proxy": float(record.get("confidence_proxy", 0.0)),
                "signal_reason_codes": list(record.get("reason_codes", [])),
                "signal_record_hash": str(record.get("record_hash", "")),
                "marking_sessions": 0,
                "observation_sessions": 0,
                "missed_marks": 0,
                "last_mark_bid": float(atm["bid"]),
                "last_mark_date": snapshot_date,
                "last_executable_bid": float(atm["bid"]),
                "last_executable_ask": ask,
                "last_executable_date": snapshot_date,
                "last_quote_quality_status": "executable_entry_quote",
                "unreliable_quote_count": 0,
                "quote_continuity_status": "continuous_at_entry",
                "entry_risk_guard_version": ENTRY_GUARD_VERSION,
                "quote_priced": True,
                "pricing_source_tier": "quote_derived_snapshot",
                "ex_ante": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
        open_symbols.add(symbol)
        sector_counts[sector] += 1
        direction_counts[direction] += 1
    ledger["last_entry_rejections"] = rejections
    ledger["last_entry_risk_guard_version"] = ENTRY_GUARD_VERSION
    ledger["last_entry_date"] = snapshot_date
    ledger["last_veto_shadow_open_result"] = veto_shadow.open_shadow_positions(
        shadow_candidates,
        rows_by_symbol,
        snapshot_date,
        select_contract=_select_entry_contract,
        commission_premium_units=COMMISSION_PREMIUM_UNITS,
    )
    return opened


def _select_entry_contract(
    rows_by_symbol: dict[str, list[dict[str, Any]]],
    symbol: str,
    side: str,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Pick the entry contract for a symbol/side, or the rejection reasons.

    Shared by real entries and the veto-shadow lane so a phantom holds exactly
    the contract the real entry would have held.
    """
    candidates = [row for row in rows_by_symbol.get(symbol, []) if row["option_type"] == side]
    if not candidates:
        return None, ("no_contract_for_symbol_and_side",)
    liquid_candidates = [
        row
        for row in candidates
        if not forward_entry_liquidity_rejection_reasons(
            float(row["bid"]),
            float(row["ask"]),
            int(row["volume"]),
            int(row["open_interest"]),
        )
    ]
    if not liquid_candidates:
        liquidity_reasons = sorted({
            reason
            for row in candidates
            for reason in forward_entry_liquidity_rejection_reasons(
                float(row["bid"]),
                float(row["ask"]),
                int(row["volume"]),
                int(row["open_interest"]),
            )
        })
        return None, tuple(liquidity_reasons)
    spot = float(liquid_candidates[0]["underlying_spot"])
    # Tenor policy: multi-expiry snapshots stage a 14/30/60 DTE surface; pin the
    # entry to the ~30 DTE tenor first, then nearest-ATM, with deterministic ties.
    in_band = [row for row in liquid_candidates if ENTRY_DTE_BAND[0] <= int(row["dte_calendar"]) <= ENTRY_DTE_BAND[1]]
    pool = in_band or liquid_candidates
    atm = min(
        pool,
        key=lambda row: (
            abs(int(row["dte_calendar"]) - TARGET_ENTRY_DTE),
            abs(float(row["strike"]) - spot),
            quote_relative_spread(float(row["bid"]), float(row["ask"])),
            -int(row["open_interest"]),
            -int(row["volume"]),
            float(row["strike"]),
            str(row["expiry"]),
        ),
    )
    if float(atm["ask"]) <= 0:
        return None, ("entry_ask_not_positive",)
    return atm, ()


def _entry_rejection(record: dict[str, Any], reason_codes: tuple[str, ...]) -> dict[str, Any]:
    return {
        "signal_id": str(record.get("signal_id", "")),
        "symbol": str(record.get("symbol", "")),
        "candidate_strategy": str(record.get("candidate_strategy", "")),
        "reason_codes": list(reason_codes),
        "paper_only": True,
        "live_blocked": True,
    }


def _mark_position(
    position: dict[str, Any],
    row: dict[str, Any],
    snapshot_date: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    marked = dict(position)
    bid = float(row["bid"])
    ask = float(row["ask"])
    spread = quote_relative_spread(bid, ask)
    marked["observation_sessions"] = int(marked.get("observation_sessions", 0)) + 1
    marked["marking_sessions"] = int(marked.get("marking_sessions", 0)) + 1
    marked["last_observed_bid"] = bid
    marked["last_observed_ask"] = ask
    marked["last_observed_date"] = snapshot_date
    marked["last_observed_relative_spread"] = round(spread, 6)
    quote_rejections = forward_exit_quote_rejection_reasons(bid, ask)
    if quote_rejections:
        marked["unreliable_quote_count"] = int(marked.get("unreliable_quote_count", 0)) + 1
        marked["last_quote_quality_status"] = "deferred_unreliable_quote"
        marked["last_quote_rejection_reasons"] = list(quote_rejections)
        if not str(marked.get("pending_exit_reason", "")):
            if int(marked["marking_sessions"]) >= MAX_MARKING_SESSIONS:
                marked["pending_exit_reason"] = "time_stop_deferred_unreliable_quote"
            elif int(row["dte_calendar"]) <= FORCE_CLOSE_DTE:
                marked["pending_exit_reason"] = "expiry_proximity_forced_close_deferred_unreliable_quote"
        return marked, None

    marked["missed_marks"] = 0
    marked["missing_quote_dates"] = []
    marked["quote_continuity_status"] = "continuous"
    marked["last_mark_bid"] = bid
    marked["last_mark_date"] = snapshot_date
    marked["last_executable_bid"] = bid
    marked["last_executable_ask"] = ask
    marked["last_executable_date"] = snapshot_date
    marked["last_quote_quality_status"] = "executable_quote"
    marked["last_quote_rejection_reasons"] = []
    pending_exit_reason = str(marked.pop("pending_exit_reason", ""))
    if pending_exit_reason:
        return None, _close_with_quote(marked, row, snapshot_date, pending_exit_reason)

    entry_fill = float(marked["entry_fill"])
    mark_return = (bid - COMMISSION_PREMIUM_UNITS) / entry_fill - 1.0 if entry_fill > 0 else 0.0
    if mark_return <= PREMIUM_STOP_PCT:
        return None, _close_with_quote(marked, row, snapshot_date, "premium_stop")
    if mark_return >= PREMIUM_TARGET_PCT:
        return None, _close_with_quote(marked, row, snapshot_date, "premium_target")
    if int(marked["marking_sessions"]) >= MAX_MARKING_SESSIONS:
        return None, _close_with_quote(marked, row, snapshot_date, "time_stop")
    if int(row["dte_calendar"]) <= FORCE_CLOSE_DTE:
        return None, _close_with_quote(marked, row, snapshot_date, "expiry_proximity_forced_close")
    return marked, None


def _close(position: dict[str, Any], bid: float, close_date: str, reason: str) -> dict[str, Any]:
    exit_fill = round(max(bid - COMMISSION_PREMIUM_UNITS, 0.0), 6)
    entry_fill = float(position["entry_fill"])
    pnl = round(exit_fill - entry_fill, 6)
    return {
        **{key: value for key, value in position.items() if key not in {"marking_sessions", "missed_marks"}},
        "artifact_type": "forward_walk_closed_trade",
        "exit_date": close_date,
        "exit_fill": exit_fill,
        "exit_reason": reason,
        "holding_sessions": int(position.get("observation_sessions", position["marking_sessions"])),
        "executable_marking_sessions": int(position["marking_sessions"]),
        "path_pnl": pnl,
        "trade_return": round(pnl / entry_fill, 6) if entry_fill > 0 else 0.0,
        "win_loss_marker": "win_forward_walk" if pnl > 0 else ("loss_forward_walk" if pnl < 0 else "flat_forward_walk"),
        "outcome_integrity_version": INTEGRITY_VERSION,
        "outcome_integrity_class": VALIDATED_OUTCOME,
        "outcome_integrity_reason_codes": ["observed_current_policy_close"],
        "included_in_forward_performance_statistics": True,
        "quote_priced": True,
        "ex_ante": True,
        "not_profitability_claim": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _close_with_quote(
    position: dict[str, Any],
    row: dict[str, Any],
    close_date: str,
    reason: str,
) -> dict[str, Any]:
    bid = float(row["bid"])
    ask = float(row["ask"])
    rejection_reasons = forward_exit_quote_rejection_reasons(bid, ask)
    if rejection_reasons:
        raise ValueError(
            f"refusing close on non-executable quote: position_id={position.get('position_id', '')}, "
            f"bid={bid}, ask={ask}, reasons={list(rejection_reasons)}"
        )
    closed = _close(position, bid, close_date, reason)
    spread = quote_relative_spread(bid, ask)
    return {
        **closed,
        "exit_bid": bid,
        "exit_ask": ask,
        "exit_relative_spread": round(spread, 6),
        "exit_volume": int(row["volume"]),
        "exit_open_interest": int(row["open_interest"]),
        "exit_underlying_spot": float(row["underlying_spot"]),
        "exit_quote_quality_status": "executable_quote",
        "exit_policy_version": EXIT_POLICY_VERSION,
    }


def _censor_missing_quote_continuity(
    position: dict[str, Any],
    censor_date: str,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        **position,
        "artifact_type": "forward_walk_censored_position",
        "censor_date": censor_date,
        "censor_reason": CENSORED_OUTCOME,
        "quote_continuity_status": CENSORED_OUTCOME,
        "outcome_integrity_version": INTEGRITY_VERSION,
        "outcome_integrity_class": CENSORED_OUTCOME,
        "outcome_integrity_reason_codes": list(reason_codes),
        "included_in_forward_performance_statistics": False,
        "exit_fill_observed": False,
        "win_loss_marker": "not_applicable_censored",
        "not_profitability_claim": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _turnover_annotation(
    ledger: dict[str, Any],
    integrity_summary: dict[str, Any],
) -> dict[str, Any]:
    """How fast the paper book cycles - a scale/capacity descriptor, not edge.

    closes-per-session over the observed window, plus the implied number of
    sessions to turn the whole current book over. Needs no historical
    book-size series (which the ledger does not keep): it reads only the
    entry-date span and the validated closed count.
    """
    from datetime import date

    from dopey_core.market_calendar import trading_days_between

    entry_dates = [
        str(trade.get("entry_date", ""))
        for trade in ledger.get("closed_trades", [])
        if str(trade.get("entry_date", ""))
    ] + [
        str(position.get("entry_date", ""))
        for position in ledger.get("open_positions", [])
        if str(position.get("entry_date", ""))
    ]
    last_marking = str(ledger.get("last_marking_date", ""))
    closed = int(integrity_summary["validated_closed_trade_count"])
    open_count = len(ledger.get("open_positions", []))
    if not entry_dates or len(last_marking) != 10:
        return {
            "turnover_status": "insufficient_history",
            "capacity_annotation_not_a_promotion_input": True,
        }
    try:
        span_sessions = trading_days_between(
            date.fromisoformat(min(entry_dates)), date.fromisoformat(last_marking)
        )
    except ValueError:
        return {
            "turnover_status": "unparseable_dates",
            "capacity_annotation_not_a_promotion_input": True,
        }
    closes_per_session = closed / span_sessions if span_sessions > 0 else 0.0
    sessions_to_cycle_book = (
        open_count / closes_per_session if closes_per_session > 0 else None
    )
    return {
        "turnover_status": "computed",
        "observed_span_trading_sessions": span_sessions,
        "validated_closes_in_window": closed,
        "closes_per_trading_session": round(closes_per_session, 4),
        "implied_sessions_to_cycle_current_book": (
            round(sessions_to_cycle_book, 2) if sessions_to_cycle_book is not None else None
        ),
        "capacity_annotation_not_a_promotion_input": True,
    }


def _summary_base(
    status: str,
    ledger: dict[str, Any],
    integrity_summary: dict[str, Any],
) -> dict[str, Any]:
    rejection_counts: dict[str, int] = {}
    for rejection in ledger.get("last_entry_rejections", []):
        for reason in rejection.get("reason_codes", []):
            key = str(reason)
            rejection_counts[key] = rejection_counts.get(key, 0) + 1
    open_symbols, sector_counts, direction_counts = _portfolio_counts(ledger["open_positions"])
    pending_exit_count = sum(
        1 for position in ledger["open_positions"] if str(position.get("pending_exit_reason", ""))
    )
    return {
        "artifact_type": "forward_walk_summary",
        "forward_walk_status": status,
        "open_position_count": len(ledger["open_positions"]),
        "closed_trade_count": int(integrity_summary["validated_closed_trade_count"]),
        "closed_net_pnl_premium_units": float(integrity_summary["validated_net_pnl_premium_units"]),
        "closed_win_count": int(integrity_summary["validated_win_count"]),
        "closed_loss_count": int(integrity_summary["validated_loss_count"]),
        "raw_closed_record_count": int(integrity_summary["raw_closed_record_count"]),
        "censored_outcome_count": int(integrity_summary["censored_outcome_count"]),
        "quarantined_outcome_count": int(integrity_summary["quarantined_outcome_count"]),
        "validated_entry_cohort_count": int(integrity_summary["validated_entry_cohort_count"]),
        "statistics_exclude_censored_and_quarantined_outcomes": True,
        "last_marking_date": ledger["last_marking_date"],
        "entry_policy": (
            f"{ENTRY_POLICY_VERSION}: fresh real signals; context snapshot aligned; "
            f"OI>={FORWARD_ENTRY_MIN_OPEN_INTEREST}; volume>={FORWARD_ENTRY_MIN_VOLUME}; "
            f"relative spread<={FORWARD_ENTRY_MAX_RELATIVE_SPREAD:.0%}; fill at ask plus commission"
        ),
        "portfolio_policy": (
            f"{PORTFOLIO_POLICY_VERSION}: open<={MAX_OPEN_POSITIONS}; new/run<={MAX_NEW_POSITIONS_PER_RUN}; "
            f"sector<={MAX_POSITIONS_PER_SECTOR}; direction<={MAX_POSITIONS_PER_DIRECTION}; "
            f"symbol premium share<={MAX_SYMBOL_PREMIUM_SHARE:.0%} or concentration-repair-only; one position/symbol"
        ),
        "portfolio_open_cap_breached_by_legacy_book": len(ledger["open_positions"]) > MAX_OPEN_POSITIONS,
        "portfolio_duplicate_symbol_position_count": len(ledger["open_positions"]) - len(open_symbols),
        "portfolio_sector_counts": dict(sorted(sector_counts.items())),
        "portfolio_direction_counts": dict(sorted(direction_counts.items())),
        "last_entry_rejection_count": len(ledger.get("last_entry_rejections", [])),
        "last_entry_rejection_reason_counts": dict(sorted(rejection_counts.items())),
        "exit_policy": (
            f"{EXIT_POLICY_VERSION}: executable relative spread<={FORWARD_EXIT_MAX_RELATIVE_SPREAD:.0%}; "
            f"stop {PREMIUM_STOP_PCT:+.0%} / target {PREMIUM_TARGET_PCT:+.0%} / "
            f"time {MAX_MARKING_SESSIONS} sessions / force-close dte<={FORCE_CLOSE_DTE}; "
            "dislocated quotes defer exits"
        ),
        "missing_quote_policy": (
            f"after {MISSING_QUOTE_CENSOR_AFTER_OBSERVATIONS} consecutive missing exact-contract observations, "
            "archive as censored_missing_quote_continuity with no exit fill and no win/loss"
        ),
        "open_pending_exit_count": pending_exit_count,
        "open_unreliable_quote_observation_count": sum(
            int(position.get("unreliable_quote_count", 0)) for position in ledger["open_positions"]
        ),
        "turnover_annotation": _turnover_annotation(ledger, integrity_summary),
        "evidence_class": "ex_ante_quote_priced_paper",
        "not_profitability_claim": True,
        "not_live_ready": True,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _age_days(earlier: str, later: str) -> int:
    from datetime import date

    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except ValueError:
        return 10_000


def _load_ledger() -> dict[str, Any]:
    # Guarded read: fall back to the .bak on a torn primary; raise (stage fails
    # loudly) only when both are corrupt. Never silently restart the track record.
    parsed, _source = read_json_guarded(LEDGER_PATH)
    if parsed is None:
        parsed = {}
    parsed.setdefault("open_positions", [])
    parsed.setdefault("closed_trades", [])
    parsed.setdefault("censored_positions", [])
    parsed.setdefault("last_marking_date", "")
    parsed.setdefault("last_entry_rejections", [])
    return parsed


def _write_report(summary: dict[str, Any], ledger: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Forward Paper Walk Report",
        "",
        "## Evidence Class",
        "Ex-ante, quote-priced paper trading: entries at the real ask on fresh signals, marks at",
        "an executable real bid on later snapshots. Dislocated quotes defer exits. Zero lookahead is structurally possible. Evidence",
        "accrues at the speed of reality - this is the honest track record lane.",
        "",
        f"- status: `{summary['forward_walk_status']}` | last marking date: `{summary['last_marking_date']}`",
        f"- open positions: `{summary['open_position_count']}`",
        f"- closed trades: `{summary['closed_trade_count']}` "
        f"(W `{summary['closed_win_count']}` / L `{summary['closed_loss_count']}`)",
        f"- raw closed records preserved: `{summary['raw_closed_record_count']}` | "
        f"censored `{summary['censored_outcome_count']}` | quarantined `{summary['quarantined_outcome_count']}`",
        f"- closed net P&L (premium units): `{summary['closed_net_pnl_premium_units']}`",
        f"- entry policy: `{summary['entry_policy']}`",
        f"- portfolio policy: `{summary['portfolio_policy']}`",
        f"- exit policy: `{summary['exit_policy']}`",
        f"- missing quote policy: `{summary['missing_quote_policy']}`",
        f"- pending exits awaiting executable quotes: `{summary['open_pending_exit_count']}`",
        "",
        "## Open Positions",
    ]
    for position in ledger["open_positions"]:
        lines.append(
            f"- `{position['position_id']}` {position['symbol']} {position['candidate_strategy']} "
            f"K={position['strike']} exp={position['expiry']} entry_fill={position['entry_fill']} "
            f"last_bid={position['last_mark_bid']}"
        )
    lines.extend(
        [
            "",
            "## Honest Limits",
            "- Paper fills at ask/bid assume full size at quote; real fills can be worse.",
            "- Sample accrues slowly by design; no claims until the truth layer's thresholds are met.",
            "- paper_only: `true`; live_blocked: `true`; promotion blocked upstream.",
        ]
    )
    FORWARD_WALK_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
