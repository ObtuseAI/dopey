"""Tests for the strategy playbook and the autonomous playbook scanner."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from dopey.strategy_engineering.playbook import (
    PLAYBOOK,
    computable_setups,
    data_gapped_setups,
    playbook_by_family,
    playbook_summary,
)
from dopey.strategy_engineering.playbook_scanner import (
    DETECTORS,
    SCANNER_EVOLVABLE_PARAMETERS,
    detect_big_mover_dual,
    detect_channel_breakout,
    detect_gap_continuation,
    detect_quality_pullback,
    scan_playbook,
)

_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source"


def _bar(date: str, o: float, h: float, low: float, c: float, v: float = 1e6) -> dict[str, float]:
    return {"date": date, "open": o, "high": h, "low": low, "close": c, "volume": v}


def _trend_bars(n: int, start: float = 100.0, drift: float = 1.01) -> list[dict[str, float]]:
    bars = []
    price = start
    for i in range(n):
        day = f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        nxt = price * drift
        bars.append(_bar(day, price, max(price, nxt) * 1.005, min(price, nxt) * 0.995, nxt))
        price = nxt
    return bars


def _write_history(root: Path, symbol: str, closes: list[float], volumes: list[float] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [_HEADER]
    for i, close in enumerate(closes):
        vol = volumes[i] if volumes else 1_000_000
        day = f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        lines.append(f"{day},{symbol},{close},{close * 1.01},{close * 0.99},{close},{close},{vol},test")
    (root / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ #
# Playbook catalog integrity
# ------------------------------------------------------------------ #

def test_playbook_is_comprehensive_and_honest():
    summary = playbook_summary()
    assert summary["setup_count"] >= 45, "the canon must stay comprehensive"
    assert len(summary["family_counts"]) >= 6
    assert summary["all_entries_unvalidated"] is True
    assert summary["profit_or_edge_claimed"] is False
    for setup in PLAYBOOK:
        assert setup["evidence_status"] == "unvalidated_hypothesis"
        assert setup["paper_only"] is True and setup["live_blocked"] is True
        assert setup["lineage"], f"{setup['setup_id']} must cite its lineage"
        assert setup["economic_rationale"], f"{setup['setup_id']} must state WHY it could work"
        assert setup["failure_modes"], f"{setup['setup_id']} must name how it fails"


def test_setup_ids_unique_and_detectors_resolve():
    ids = [s["setup_id"] for s in PLAYBOOK]
    assert len(ids) == len(set(ids))
    for setup in computable_setups():
        assert setup["computable_detector"] in DETECTORS, (
            f"{setup['setup_id']} names detector {setup['computable_detector']} which is not implemented"
        )


def test_data_gapped_setups_are_typed_not_hidden():
    gapped = data_gapped_setups()
    assert gapped, "honest gaps must be registered, not dropped"
    for setup in gapped:
        assert setup["required_data"], f"{setup['setup_id']} must name the missing data"


def test_families_cover_the_canon():
    families = set(playbook_by_family())
    for required in ("momentum_trend", "mean_reversion", "value_quality",
                     "volatility", "flow_positioning", "macro_regime", "event_driven"):
        assert required in families


# ------------------------------------------------------------------ #
# Individual detectors
# ------------------------------------------------------------------ #

def test_channel_breakout_detects_new_high():
    bars = _trend_bars(80, drift=1.0)          # flat channel
    bars.append(_bar("2026-03-27", 100, 112, 100, 111))  # decisive break
    hit = detect_channel_breakout(bars, {})
    assert hit is not None and hit["direction"] == "long"


def test_gap_continuation_requires_hold():
    bars = _trend_bars(40, drift=1.0)
    prev_close = bars[-1]["close"]
    # Gap up 5% that HOLDS (closes near high)
    bars.append(_bar("2026-03-01", prev_close * 1.05, prev_close * 1.08, prev_close * 1.045, prev_close * 1.075))
    hit = detect_gap_continuation(bars, {})
    assert hit is not None and hit["direction"] == "long"
    # Gap up that FAILS (closes back inside) -> no detection
    bars[-1] = _bar("2026-03-01", prev_close * 1.05, prev_close * 1.055, prev_close * 0.99, prev_close * 0.995)
    assert detect_gap_continuation(bars, {}) is None


def test_quality_pullback_needs_uptrend_and_oversold():
    up = _trend_bars(220, drift=1.005)
    # Sharp 6-day pullback that stays above the 200d
    for i in range(6):
        prev = up[-1]["close"]
        up.append(_bar(f"2026-09-{i + 1:02d}", prev, prev * 1.001, prev * 0.96, prev * 0.965))
    hit = detect_quality_pullback(up, {})
    assert hit is not None and hit["direction"] == "long"


def test_big_mover_dual_emits_competing_hypotheses():
    bars = _trend_bars(40, drift=1.01)
    prev = bars[-1]["close"]
    # +6% mover, strong close, huge volume, trend aligned -> continuation favored
    bars.append(_bar("2026-03-05", prev, prev * 1.065, prev * 0.999, prev * 1.06, v=5e6))
    hit = detect_big_mover_dual(bars, {"mover_return_floor": 0.04})
    assert hit is not None
    assert hit["details"]["competing_hypotheses"] is True
    assert hit["details"]["favored_framing"] == "momentum_continuation"
    assert hit["details"]["continuation_score"] > hit["details"]["reversion_score"]
    assert hit["selected_setup_id"] == "big_mover_momentum"
    assert hit["details"]["hypotheses_recorded"] == 1


def test_big_mover_scan_records_only_independently_selected_setup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hist"
    closes = [100.0 * (1.001 ** index) for index in range(299)]
    closes.append(closes[-1] * 1.06)
    volumes = [1_000_000.0] * 299 + [5_000_000.0]
    _write_history(root, "MOVER", closes, volumes)

    report = scan_playbook(root)

    big_movers = [
        detection
        for detection in report["detections"]
        if detection["setup_id"]
        in {"big_mover_fade", "big_mover_momentum"}
    ]
    assert len(big_movers) == 1
    assert big_movers[0]["setup_id"] == "big_mover_momentum"
    assert big_movers[0]["independently_selected_setup"] is True


# ------------------------------------------------------------------ #
# Full scan
# ------------------------------------------------------------------ #

def test_scan_reports_gaps_and_claims_nothing(tmp_path: Path):
    rep = scan_playbook(tmp_path / "empty")
    assert rep["status"] == "no_ohlcv_history"
    assert rep["profit_or_edge_claimed"] is False


def test_scan_detects_across_families(tmp_path: Path):
    root = tmp_path / "hist"
    _write_history(root, "TREND", [100.0 * (1.02 ** i) for i in range(300)])
    _write_history(root, "CRASH", [100.0 * (0.985 ** i) for i in range(300)])
    _write_history(root, "FLAT", [100.0 + math.sin(i / 3.0) for i in range(300)])
    rep = scan_playbook(root)
    assert rep["status"] == "complete"
    assert rep["detection_count"] > 0
    assert rep["setups_data_gapped"], "typed gaps must be visible in the report"
    families = set(rep["detections_per_family"])
    assert "momentum_trend" in families
    for d in rep["detections"]:
        assert d["is_trade_signal"] is False
        assert d["paper_only"] is True and d["live_blocked"] is True
        assert d["evidence_status"] == "unvalidated_hypothesis"
        assert d["lineage"], "every detection carries its lineage"


def test_lane_context_setups_fire_only_with_state(tmp_path: Path):
    root = tmp_path / "hist"
    _write_history(root, "TREND", [100.0 * (1.01 ** i) for i in range(300)])
    without = scan_playbook(root)
    assert "gamma_squeeze_flow" not in without["detections_per_setup"]
    with_lane = scan_playbook(root, lane_context={
        "gex_state": {"detected": True, "direction": "long", "strength": 0.9, "gex": -7.4e7}
    })
    assert with_lane["detections_per_setup"].get("gamma_squeeze_flow", 0) >= 1


def test_attention_fade_requires_independent_price_and_regime_confirmation(
    tmp_path: Path,
):
    root = tmp_path / "hist"
    _write_history(root, "EXTENDED", [100.0 * (1.006 ** i) for i in range(300)])
    _write_history(root, "FLAT", [100.0 + math.sin(i / 3.0) for i in range(300)])

    attention_without_z = {
        "attention_state": {
            "detected": True,
            "direction": "either",
            "crowded_symbols": ["EXTENDED"],
            "research_priority_only": True,
            "directional_bias_allowed": False,
        }
    }
    unconfirmed = scan_playbook(root, lane_context=attention_without_z)
    assert unconfirmed["detections_per_setup"].get("crowded_attention_fade", 0) == 0

    attention_with_independent_checks = {
        "attention_state": {
            "detected": True,
            "direction": "either",
            "crowded_symbols": ["EXTENDED", "FLAT"],
            "attention_z_by_symbol": {"EXTENDED": 3.2, "FLAT": 3.2},
            "crowded_threshold_z": 2.0,
            "research_priority_only": True,
            "directional_bias_allowed": False,
        }
    }
    confirmed = scan_playbook(root, lane_context=attention_with_independent_checks)
    fades = [
        detection
        for detection in confirmed["detections"]
        if detection["setup_id"] == "crowded_attention_fade"
    ]
    assert len(fades) == 1
    assert fades[0]["symbol"] == "EXTENDED"
    assert fades[0]["direction"] == "short"
    assert fades[0]["details"]["price_extension_confirmed"] is True
    assert fades[0]["details"]["trend_regime_confirmed"] is True
    assert fades[0]["details"]["attention_alone_directional"] is False


def test_lane_states_do_not_flood_the_universe(tmp_path: Path):
    """A market-wide lane state fires ONCE (market proxy); a symbol-listed
    state fires only for its implicated symbols — never once per symbol."""
    root = tmp_path / "hist"
    for symbol in ("AAA", "BBB", "CCC", "SPY"):
        _write_history(root, symbol, [100.0 * (1.01 ** i) for i in range(300)])
    rep = scan_playbook(root, lane_context={
        # market-wide (no symbol list): must fire exactly once, on SPY
        "liquidity_state": {"detected": True, "direction": "long", "strength": 0.6},
        # symbol-listed: must fire ONLY for BBB
        "fundamental_rot_state": {"detected": True, "direction": "short",
                                  "strength": 0.9, "short_candidates": ["BBB"]},
    })
    liq = [d for d in rep["detections"] if d["setup_id"] == "liquidity_impulse_risk"]
    rot = [d for d in rep["detections"] if d["setup_id"] == "fundamental_rot_short"]
    assert len(liq) == 1 and liq[0]["symbol"] == "SPY"
    assert len(rot) == 1 and rot[0]["symbol"] == "BBB"


def test_evolvable_surface_is_declared():
    rep_keys = set(SCANNER_EVOLVABLE_PARAMETERS)
    assert {"CHANNEL_BREAKOUT_WINDOW", "GAP_MIN_PCT", "PULLBACK_RSI"} <= rep_keys
    assert all(isinstance(v, float) for v in SCANNER_EVOLVABLE_PARAMETERS.values())


def test_real_spine_scan_if_present():
    root = Path(__file__).resolve().parents[1] / "dopey_data" / "history" / "raw"
    if not root.is_dir() or len(list(root.glob("*.csv"))) < 3:
        pytest.skip("insufficient staged OHLCV history")
    rep = scan_playbook(root)
    assert rep["status"] == "complete"
    assert rep["detection_count"] > 0
    assert rep["profit_or_edge_claimed"] is False
    assert rep["live_blocked"] is True
