"""Veto Shadow Ledger: opinion vetoes get phantom-measured, capacity vetoes don't.

Phantom outcomes must be unmistakably phantom (integrity class overridden,
excluded from forward statistics) and must never touch the real forward ledger.
"""
from __future__ import annotations

import json

from dopey_backtest import forward_paper_walk as walk
from dopey_backtest import veto_shadow


def _isolate(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(veto_shadow, "SHADOW_LEDGER_PATH", tmp_path / "shadow_ledger.json")
    monkeypatch.setattr(veto_shadow, "SHADOW_CLOSED_PATH", tmp_path / "shadow_closed.jsonl")
    monkeypatch.setattr(veto_shadow, "SHADOW_SUMMARY_PATH", tmp_path / "shadow_summary.json")


def _snapshot_rows(symbol: str, side: str, bid: float, ask: float) -> dict[str, list[dict]]:
    return {symbol: [{
        "symbol": symbol,
        "expiry": "2026-08-07",
        "dte_calendar": 29,
        "option_type": side,
        "strike": 100.0,
        "bid": bid,
        "ask": ask,
        "volume": 20,
        "open_interest": 100,
        "implied_vol": 0.2,
        "underlying_spot": 100.0,
    }]}


def _signal(symbol: str, strategy: str) -> dict:
    return {
        "signal_id": f"sig-{symbol}-{strategy}",
        "symbol": symbol,
        "candidate_strategy": strategy,
        "signal_date": "2026-07-08",
        "source_signal_family": "test",
    }


def test_opinion_veto_classification() -> None:
    assert veto_shadow.is_opinion_veto(("entry_context_unfavorable",))
    assert veto_shadow.is_opinion_veto(("vrp_rich_premium_expensive", "dealer_short_gamma_amplifying"))
    assert veto_shadow.is_opinion_veto((
        "adversarial_entry_verdict_would_reduce_but_one_contract_cannot_be_reduced",
        "crowded_attention",
        "vol_surface_tear",
    ))
    # any capacity/liquidity/book-state code disqualifies the whole bundle
    assert not veto_shadow.is_opinion_veto(("portfolio_sector_cap_reached",))
    assert not veto_shadow.is_opinion_veto(("entry_context_unfavorable", "stale_existing_book_stress_evidence"))
    assert not veto_shadow.is_opinion_veto(("adversarial_entry_verdict_would_refuse", "projected_symbol_premium_share_exceeds_25pct"))
    assert not veto_shadow.is_opinion_veto(())


def test_shadow_opens_only_opinion_vetoes_with_priceable_contracts(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)
    rows = _snapshot_rows("SPY", "call", 4.0, 4.2)
    candidates = [
        (_signal("SPY", "long_call"), ("entry_context_unfavorable",)),          # opinion + priceable -> phantom
        (_signal("AAPL", "long_call"), ("portfolio_sector_cap_reached",)),      # capacity -> never
        (_signal("MSFT", "long_call"), ("vrp_rich_premium_expensive",)),        # opinion but no contract rows -> skip
    ]
    result = veto_shadow.open_shadow_positions(
        candidates, rows, "2026-07-09",
        select_contract=walk._select_entry_contract,
        commission_premium_units=walk.COMMISSION_PREMIUM_UNITS,
    )
    assert result["shadow_opened"] == 1
    ledger = veto_shadow.load_shadow_ledger()
    assert len(ledger["open_positions"]) == 1
    phantom = ledger["open_positions"][0]
    assert phantom["symbol"] == "SPY"
    assert phantom["phantom"] is True
    assert phantom["primary_veto_class"] == "entry_context_unfavorable"
    assert phantom["entry_fill"] == round(4.2 + walk.COMMISSION_PREMIUM_UNITS, 6)
    assert phantom["included_in_forward_performance_statistics"] is False

    # same signal never shadowed twice (fresh date so the idempotence guard passes)
    again = veto_shadow.open_shadow_positions(
        [(_signal("SPY", "long_call"), ("entry_context_unfavorable",))], rows, "2026-07-10",
        select_contract=walk._select_entry_contract,
        commission_premium_units=walk.COMMISSION_PREMIUM_UNITS,
    )
    assert again["shadow_opened"] == 0


def test_shadow_close_is_stamped_phantom_and_summarized(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)
    rows = _snapshot_rows("SPY", "call", 2.0, 2.1)
    veto_shadow.open_shadow_positions(
        [(_signal("SPY", "long_call"), ("entry_context_unfavorable",))], rows, "2026-07-09",
        select_contract=walk._select_entry_contract,
        commission_premium_units=walk.COMMISSION_PREMIUM_UNITS,
    )
    # next session the bid doubles -> premium_target close via the walk's OWN policy
    exit_rows = {("SPY", "2026-08-07", "call", 100.0): _snapshot_rows("SPY", "call", 4.5, 4.7)["SPY"][0]}
    summary = veto_shadow.mark_shadow_positions(exit_rows, "2026-07-10", mark_position=walk._mark_position)

    assert summary["closed_phantom_count"] == 1
    assert summary["open_phantom_count"] == 0
    stats = summary["per_veto_class"]["entry_context_unfavorable"]
    assert stats["n"] == 1 and stats["win_rate"] == 1.0
    assert summary["never_a_gate_input"] is True

    ledger = veto_shadow.load_shadow_ledger()
    closed = ledger["closed_trades"][0]
    assert closed["artifact_type"] == "veto_shadow_closed_trade"
    assert closed["outcome_integrity_class"] == veto_shadow.PHANTOM_OUTCOME_CLASS
    assert closed["included_in_forward_performance_statistics"] is False
    assert closed["exit_reason"] == "premium_target"
    assert closed["phantom"] is True


def test_walk_entry_loop_feeds_shadow_and_real_ledger_stays_clean(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)
    signals_path = tmp_path / "signals.jsonl"
    context_path = tmp_path / "entry_context.jsonl"
    monkeypatch.setattr(walk, "DIRECTIONAL_SETUP_SIGNALS_PATH", signals_path)
    monkeypatch.setattr(walk, "FRESH_DIRECTIONAL_SETUP_SIGNALS_PATH", tmp_path / "absent.jsonl")
    monkeypatch.setattr(walk, "ENTRY_CONTEXT_PATH", context_path)
    signal = {**_signal("SPY", "long_call"), "data_source_tier": "local_real_history", "confidence_proxy": 0.9}
    signals_path.write_text(json.dumps(signal) + "\n", encoding="utf-8")
    context_path.write_text(
        json.dumps({
            "symbol": "SPY",
            "snapshot_date": "2026-07-09",
            "external_context_status": "complete",
            "long_call_entry_bias": "unfavorable",
            "long_put_entry_bias": "neutral",
            "long_call_veto_reasons": ["vrp_rich_premium_expensive"],
            "long_put_veto_reasons": [],
        }) + "\n",
        encoding="utf-8",
    )
    snapshot = {"rows": _snapshot_rows("SPY", "call", 4.0, 4.2)["SPY"]}
    ledger = {"open_positions": [], "closed_trades": [], "last_marking_date": ""}

    opened = walk._open_new_positions(ledger, snapshot, "2026-07-09")

    assert opened == []
    assert ledger["last_entry_rejections"][0]["reason_codes"] == ["vrp_rich_premium_expensive"]
    assert ledger["last_veto_shadow_open_result"]["shadow_opened"] == 1
    # the phantom lives in the shadow file, never in the forward ledger
    assert ledger["closed_trades"] == [] and ledger["open_positions"] == []
    shadow = veto_shadow.load_shadow_ledger()
    assert shadow["open_positions"][0]["primary_veto_class"] == "vrp_rich_premium_expensive"
