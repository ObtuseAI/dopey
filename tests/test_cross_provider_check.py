"""Cross-provider spot check: verification-only, deterministic, fail-soft.

Two lanes: the keyless FRED SP500 return anchor (always on) and the optional
Alpha Vantage per-symbol lane (soft-unconfigured without a key). Secondary
rows are compared and discarded - the artifact must say so - and a material
divergence in either lane flips the verdict while volume differences stay
informational.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from operator_tools import operator_cross_provider_check as check

_CLEAN_ANCHOR = {
    "anchor_status": "compared",
    "shared_return_days": 9,
    "worst_abs_return_diff": 0.0002,
    "issues": [],
}


def _write_spine(history: Path, symbol: str, rows: list[tuple[str, float, float]]) -> None:
    lines = ["date,symbol,open,high,low,close,adjusted_close,volume,source"]
    for day, close, volume in rows:
        lines.append(f"{day},{symbol},{close},{close},{close},{close},{close},{int(volume)},yahoo_finance")
    (history / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_weekly_rotation_is_deterministic_and_rotates() -> None:
    symbols = [f"S{index:03d}" for index in range(50)]
    week1 = check.weekly_rotation(symbols, date(2026, 7, 20), 20)
    week1_again = check.weekly_rotation(symbols, date(2026, 7, 22), 20)  # same ISO week
    week2 = check.weekly_rotation(symbols, date(2026, 7, 27), 20)
    assert week1 == week1_again
    assert len(week1) == 20
    assert week1 != week2  # the sample moves week over week


def test_compare_flags_material_and_minor_close_divergence() -> None:
    spine = {"2026-07-21": (100.0, 1_000_000.0), "2026-07-22": (100.0, 1_000_000.0)}
    secondary = {"2026-07-21": (101.0, 1_000_000.0), "2026-07-22": (104.0, 1_000_000.0)}
    result = check.compare_symbol("TEST", spine, secondary)
    severities = sorted(issue["severity"] for issue in result["issues"])
    assert severities == ["material", "minor"]
    assert result["shared_days_compared"] == 2


def test_volume_divergence_is_informational_only() -> None:
    spine = {"2026-07-22": (100.0, 1_000_000.0)}
    secondary = {"2026-07-22": (100.0, 400_000.0)}
    result = check.compare_symbol("TEST", spine, secondary)
    assert [issue["severity"] for issue in result["issues"]] == ["informational"]


def test_anchor_compares_returns_not_levels(tmp_path, monkeypatch) -> None:
    history = tmp_path / "raw"
    history.mkdir()
    # SPY at ~1/10 of the index level: identical RETURNS must be consistent.
    _write_spine(
        history,
        "SPY",
        [("2026-07-20", 500.0, 1e6), ("2026-07-21", 505.0, 1e6), ("2026-07-22", 500.0, 1e6)],
    )
    monkeypatch.setattr(check, "HISTORY_DIR", history)
    monkeypatch.setattr(
        check,
        "fetch_fred_sp500_closes",
        lambda: {"2026-07-20": 5000.0, "2026-07-21": 5050.0, "2026-07-22": 4951.0},
    )
    anchor = check.sp500_anchor_check("2026-07-19")
    assert anchor["anchor_status"] == "compared"
    # 07-21: both +1.0% -> clean. 07-22: spine -0.99% vs fred -1.96% -> material.
    assert [issue["severity"] for issue in anchor["issues"]] == ["material"]


def test_run_discards_secondary_and_verdicts_material(tmp_path, monkeypatch) -> None:
    history = tmp_path / "raw"
    history.mkdir()
    _write_spine(history, "AAA", [("2026-07-21", 100.0, 1e6), ("2026-07-22", 101.0, 1e6)])
    monkeypatch.setattr(check, "HISTORY_DIR", history)
    monkeypatch.setattr(check, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(check, "SAMPLE_SYMBOLS", 1)
    monkeypatch.setattr(check, "sp500_anchor_check", lambda day_floor: dict(_CLEAN_ANCHOR))
    monkeypatch.setattr(
        check,
        "fetch_secondary_rows",
        lambda symbol, start, end: {"2026-07-22": (110.0, 1_000_000.0)},
    )
    report = check.run_cross_provider_check(today=date(2026, 7, 23))
    assert report["verdict"] == "material_divergence_detected"
    assert report["secondary_rows_discarded_not_persisted"] is True
    assert report["material_close_divergences"] == 1
    assert (tmp_path / "report.json").exists()


def test_unconfigured_key_is_a_soft_anchor_only_state(tmp_path, monkeypatch) -> None:
    history = tmp_path / "raw"
    history.mkdir()
    _write_spine(history, "AAA", [("2026-07-22", 101.0, 1e6)])
    monkeypatch.setattr(check, "HISTORY_DIR", history)
    monkeypatch.setattr(check, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(check, "SAMPLE_SYMBOLS", 1)
    monkeypatch.setattr(check, "sp500_anchor_check", lambda day_floor: dict(_CLEAN_ANCHOR))
    monkeypatch.delenv(check.ALPHAVANTAGE_KEY_ENV, raising=False)
    report = check.run_cross_provider_check(today=date(2026, 7, 23))
    assert report["verdict"] == "anchor_consistent_per_symbol_lane_unconfigured"
    assert report["secondary_configured"] is False
    assert report["fetch_failures"] == []


def test_run_fails_soft_on_fetch_errors(tmp_path, monkeypatch) -> None:
    history = tmp_path / "raw"
    history.mkdir()
    _write_spine(history, "AAA", [("2026-07-22", 101.0, 1e6)])
    monkeypatch.setattr(check, "HISTORY_DIR", history)
    monkeypatch.setattr(check, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(check, "SAMPLE_SYMBOLS", 1)
    monkeypatch.setattr(check, "sp500_anchor_check", lambda day_floor: dict(_CLEAN_ANCHOR))

    def explode(symbol, start, end):
        raise OSError("provider down")

    monkeypatch.setattr(check, "fetch_secondary_rows", explode)
    report = check.run_cross_provider_check(today=date(2026, 7, 23))
    assert report["verdict"] == "anchor_consistent_per_symbol_lane_unavailable"
    assert report["fetch_failures"][0]["reason"].startswith("secondary_fetch_failed")
