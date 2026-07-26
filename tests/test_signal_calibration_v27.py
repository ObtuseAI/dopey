"""Tests: V27 phantom signal settlement + contested-truth calibration
(adapted from the dummy repo's calibration disciplines).

The properties: no early grading (horizon must fully elapse on real data),
grading is deterministic and lookahead-free, contested means disagreeing with
drift, trust is earned on the contested record and stays advisory, and every
artifact is stamped not-trade-evidence with the gate never reading the lane.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_calibration.signal_settlement import (
    CALIBRATION_SUMMARY_PATH,
    FLAT_RETURN_EPSILON,
    HORIZON_TRADING_DAYS,
    MIN_SETTLEMENTS_FOR_TRUST,
    PHANTOM_LEDGER_PATH,
    _trust_from_record,
    calibration_context,
    family_trust_for,
    run_signal_calibration,
    settle_signal,
)
from dopey_risk_engine.adversarial_signal_panel import build_panel_record

REPO_ROOT = Path(__file__).resolve().parent.parent


def _panel_position(family: str = "relative_strength") -> dict:
    return {
        "position_id": "p1",
        "symbol": "AAPL",
        "candidate_strategy": "long_call",
        "entry_date": "2025-01-15",
        "signal_date": "2025-01-10",
        "signal_family": family,
    }


def _dates(count: int) -> list[str]:
    return [f"2025-01-{day:02d}" for day in range(1, count + 1)]


def _signal(direction: str = "bullish", signal_date: str = "2025-01-05") -> dict:
    return {
        "signal_id": "sig-1",
        "signal_family": "momentum",
        "symbol": "TEST",
        "direction": direction,
        "signal_date": signal_date,
    }


# ---------------------------------------------------------------------------
# Grading mechanics
# ---------------------------------------------------------------------------

def test_no_early_grading_before_horizon_elapses() -> None:
    dates = _dates(12)
    closes = [100.0] * 12
    # signal at index 4, horizon 10 -> needs index 14 which does not exist
    assert settle_signal(_signal(signal_date=dates[4]), dates, closes) is None


def test_bullish_hit_and_miss_grade_correctly() -> None:
    dates = _dates(25)
    up = [100.0 + i for i in range(25)]
    down = [100.0 - i * 0.5 for i in range(25)]
    hit = settle_signal(_signal("bullish", dates[5]), dates, up)
    miss = settle_signal(_signal("bullish", dates[5]), dates, down)
    assert hit is not None and hit["hit"] is True and hit["realized_direction"] == "bullish"
    assert miss is not None and miss["hit"] is False and miss["realized_direction"] == "bearish"
    assert hit["settle_date"] == dates[5 + HORIZON_TRADING_DAYS]


def test_flat_forward_return_is_a_miss_for_both_directions() -> None:
    dates = _dates(25)
    flat = [100.0] * 25
    for direction in ("bullish", "bearish"):
        graded = settle_signal(_signal(direction, dates[5]), dates, flat)
        assert graded is not None
        assert graded["realized_direction"] == "flat"
        assert graded["hit"] is False
    assert FLAT_RETURN_EPSILON > 0


def test_grading_never_reads_rows_before_signal_for_outcome() -> None:
    """Outcome depends only on [signal_date, settle_date] closes - a crash
    BEFORE the signal must not change the grade (drift changes, hit cannot)."""
    dates = _dates(40)
    base = [100.0] * 40
    for i in range(25, 40):
        base[i] = 100.0 + (i - 24)
    crashed_history = list(base)
    for i in range(0, 20):
        crashed_history[i] = 500.0 - i * 10
    a = settle_signal(_signal("bullish", dates[25]), dates, base)
    b = settle_signal(_signal("bullish", dates[25]), dates, crashed_history)
    assert a is not None and b is not None
    assert a["hit"] == b["hit"] is True
    assert a["forward_return"] == b["forward_return"]


def test_contested_means_disagreeing_with_drift() -> None:
    dates = _dates(60)
    rising = [100.0 + i for i in range(60)]
    bearish_into_uptrend = settle_signal(_signal("bearish", dates[30]), dates, rising)
    bullish_with_uptrend = settle_signal(_signal("bullish", dates[30]), dates, rising)
    assert bearish_into_uptrend is not None and bearish_into_uptrend["contested"] is True
    assert bullish_with_uptrend is not None and bullish_with_uptrend["contested"] is False


def test_unknown_direction_or_date_never_grades() -> None:
    dates = _dates(30)
    closes = [100.0] * 30
    assert settle_signal(_signal("sideways", dates[5]), dates, closes) is None
    assert settle_signal(_signal("bullish", "1999-01-01"), dates, closes) is None


# ---------------------------------------------------------------------------
# Contested-truth trust discipline
# ---------------------------------------------------------------------------

def test_trust_is_unrated_below_contested_sample_floor() -> None:
    trust = _trust_from_record(hits=90, count=100, contested_hits=5, contested_count=6)
    assert trust["trust"] == 1.0
    assert trust["trust_rating"] == "unrated_insufficient_contested_sample"
    assert trust["advisory_only"] is True
    assert trust["enforcement"] == "never"


def test_trust_earned_only_on_contested_record() -> None:
    floor = MIN_SETTLEMENTS_FOR_TRUST
    good = _trust_from_record(hits=50, count=100, contested_hits=int(floor * 0.7), contested_count=floor)
    bad = _trust_from_record(hits=90, count=100, contested_hits=int(floor * 0.3), contested_count=floor)
    assert good["trust"] > 1.0        # beat the flip where it disagreed with drift
    assert bad["trust"] < 1.0         # 90% overall means NOTHING - contested record was bad
    assert 0.25 <= bad["trust"] and good["trust"] <= 2.0


# ---------------------------------------------------------------------------
# Runner artifacts + semantics
# ---------------------------------------------------------------------------

def test_runner_writes_ledger_and_summary_with_stamps() -> None:
    summary = run_signal_calibration()
    assert CALIBRATION_SUMMARY_PATH.exists()
    assert summary["semantics"] == "signal_calibration_not_trade_evidence"
    assert summary["gate_visibility"] == "the readiness gate never reads this lane"
    assert summary["not_edge_evidence"] is True
    assert summary["promotion_allowed"] is False
    assert summary["trust_enforcement"].startswith("advisory")
    if summary["settled_total"]:
        first = json.loads(PHANTOM_LEDGER_PATH.read_text(encoding="utf-8").splitlines()[0])
        assert first["semantics"] == "signal_calibration_not_trade_evidence"
        assert first["traded"] is False
        assert first["promotion_allowed"] is False


def test_runner_is_deterministic() -> None:
    first = run_signal_calibration()
    second = run_signal_calibration()
    assert first["settled_total"] == second["settled_total"]
    assert first["overall_hit_rate"] == second["overall_hit_rate"]
    assert first["contested_hit_rate"] == second["contested_hit_rate"]


def test_readiness_gate_source_never_reads_calibration_lane() -> None:
    text = (REPO_ROOT / "dopey_broker_readiness" / "action_readiness_gate.py").read_text(encoding="utf-8")
    assert "signal_calibration" not in text
    assert "phantom" not in text.lower()


def test_calibration_module_is_offline_and_orderless() -> None:
    text = (REPO_ROOT / "dopey_calibration" / "signal_settlement.py").read_text(encoding="utf-8").lower()
    for forbidden in ("requests", "yfinance", "urllib", "place_order", "broker", "websocket"):
        assert forbidden not in text


def test_supervisor_includes_signal_calibration_stage() -> None:
    from dopey_autonomy.run_resilient_research_supervisor import STAGES

    names = [name for name, _, _ in STAGES]
    assert "signal_calibration" in names
    assert names.index("signal_calibration") > names.index("real_signals")
    assert len(names) == len(set(names))
    assert names[-1] == "action_readiness_gate"


def test_calibration_runs_before_the_panel_it_feeds() -> None:
    """The panel reads the contested-truth base rate as an advisory lens, so
    calibration must be settled earlier in the same pass (the reorder)."""
    from dopey_autonomy.run_resilient_research_supervisor import STAGES

    names = [name for name, _, _ in STAGES]
    assert names.index("signal_calibration") < names.index("adversarial_signal_panel")


# ---------------------------------------------------------------------------
# Read-side accessors: the contested-truth trust that feeds the panel
# ---------------------------------------------------------------------------

def test_family_trust_for_unknown_family_is_explicit_unrated_never_a_pass() -> None:
    # explicit empty summary -> no disk read; an uncalibrated family must be
    # stamped unrated, never silently treated as trusted or blocked
    trust = family_trust_for("NO_SUCH_FAMILY_XYZ", {})
    assert trust["trust_rating"] == "unrated_no_calibration_for_family"
    assert trust["advisory_only"] is True
    assert trust["enforcement"] == "never"
    assert trust["family"] == "NO_SUCH_FAMILY_XYZ"


def test_family_trust_for_reads_summary_and_stays_advisory() -> None:
    synthetic = {"family_trust": {"momentum": {
        "trust": 1.4, "trust_rating": "rated_on_contested_record",
        "contested_hit_rate": 0.7, "contested_settlements": 40,
    }}}
    trust = family_trust_for("momentum", synthetic)
    assert trust["trust"] == 1.4
    assert trust["family"] == "momentum"
    assert trust["advisory_only"] is True and trust["enforcement"] == "never"


def test_calibration_context_is_advisory_and_gate_blind() -> None:
    synthetic = {
        "signal_calibration_status": "phantom_settlements_graded",
        "settled_total": 78209, "overall_hit_rate": 0.4964,
        "contested_total": 20000, "contested_hit_rate": 0.4647,
    }
    context = calibration_context(synthetic)
    assert context["advisory_only"] is True
    assert context["enforcement"] == "never"
    assert context["semantics"] == "signal_calibration_not_trade_evidence"
    assert context["contested_hit_rate"] == 0.4647


def test_calibration_context_missing_summary_is_honest() -> None:
    context = calibration_context({})
    assert context["status"] == "no_calibration_yet"
    assert context["advisory_only"] is True
    assert context["enforcement"] == "never"


# ---------------------------------------------------------------------------
# Panel wiring: contested-truth is recorded, and never moves the verdict
# ---------------------------------------------------------------------------

def test_panel_record_carries_advisory_calibration_lens() -> None:
    record = build_panel_record(_panel_position(), {}, {}, {}, {})
    lens = record["calibration_lens"]
    assert lens["lens_role"] == "contested_truth_advisory_recorded_never_enforced"
    assert lens["does_not_affect_verdict"] is True
    assert lens["enforcement"] == "never"
    # an uncalibrated forward-walk family degrades honestly, never to a pass
    assert lens["trust_rating"] == "unrated_no_calibration_for_family"


def test_calibration_lens_never_changes_the_verdict() -> None:
    """A gate must be EARNED. A wildly trusted vs distrusted family must yield
    the SAME recorded verdict - the lens colors the record, nothing else."""
    trusted = {"family_trust": {"relative_strength": {
        "trust": 2.0, "trust_rating": "rated_on_contested_record", "contested_hit_rate": 0.95}}}
    distrusted = {"family_trust": {"relative_strength": {
        "trust": 0.25, "trust_rating": "rated_on_contested_record", "contested_hit_rate": 0.05}}}
    a = build_panel_record(_panel_position(), {}, {}, {}, trusted)
    b = build_panel_record(_panel_position(), {}, {}, {}, distrusted)
    assert a["panel_verdict_recorded_not_enforced"] == b["panel_verdict_recorded_not_enforced"]
    # the advisory difference IS recorded, it just doesn't act
    assert a["calibration_lens"]["trust"] != b["calibration_lens"]["trust"]


def test_panel_runner_attaches_calibration_context_when_recording() -> None:
    from dopey_risk_engine.adversarial_signal_panel import run_adversarial_signal_panel

    summary = run_adversarial_signal_panel()
    if summary.get("panel_status") == "adversarial_panel_recorded":
        assert "calibration_context" in summary
        assert summary["calibration_context"]["advisory_only"] is True
        assert summary["calibration_context"]["enforcement"] == "never"
