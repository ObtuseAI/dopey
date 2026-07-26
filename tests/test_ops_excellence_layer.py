"""Ops-excellence layer: forecast card (Feynman), kaizen ledger (Toyota), SLO (SRE).

All three are measure-only readers; predictions are ex-ante and immutable once
scored; defect aggregation and error budgets recommend, never act.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

from dopey_acceleration.common import stable_hash
from dopey_ops import kaizen_ledger, pipeline_forecast_card, reliability_slo
from dopey_ops.pipeline_forecast_card import (
    deterministic_close_forecast,
    score_forecast,
)
from dopey_ops.reliability_slo import fetch_adherence, trailing_trading_days


# ---------- forecast card ----------


def test_deterministic_close_forecast_counts_due_exits() -> None:
    positions = [
        {"marking_sessions": 2, "expiry": "2026-12-18"},  # time stop due next mark
        {"marking_sessions": 0, "expiry": "2026-07-27"},  # force-close window (dte<=6)
        {"marking_sessions": 1, "expiry": "2026-12-18"},  # neither
        {
            "marking_sessions": 0,
            "expiry": "2026-12-18",
            "pending_exit_reason": "time_stop_deferred_unreliable_quote",
        },
    ]
    forecast = deterministic_close_forecast(positions, "2026-07-23")
    assert forecast["predicted_time_stop_closes"] == 1
    assert forecast["predicted_force_closes"] == 1
    assert forecast["predicted_pending_exit_closes"] == 1
    assert forecast["predicted_closes_point"] == 3
    assert forecast["predicted_closes_upper"] == 4


def test_score_forecast_flags_under_delivery() -> None:
    prediction = {"predicted_closes_point": 3, "predicted_closes_upper": 8}
    score = score_forecast(prediction, actual_closes=1)
    assert score["signed_error"] == -2
    assert score["under_delivered"] is True
    on_target = score_forecast(prediction, actual_closes=4)
    assert on_target["under_delivered"] is False


def test_forecast_card_scores_pending_then_repredicts(monkeypatch, tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    card_path = tmp_path / "card.json"
    monkeypatch.setattr(pipeline_forecast_card, "LEDGER_PATH", ledger_path)
    monkeypatch.setattr(pipeline_forecast_card, "CARD_PATH", card_path)
    # day 1: one position due for time stop
    ledger_path.write_text(
        json.dumps(
            {
                "last_marking_date": "2026-07-22",
                "open_positions": [{"marking_sessions": 2, "expiry": "2026-12-18"}],
                "closed_trades": [],
            }
        ),
        encoding="utf-8",
    )
    first = pipeline_forecast_card.run_pipeline_forecast_card()
    assert first["pending_forecast"]["predicted_closes_point"] == 1
    assert first["scored_count"] == 0
    # day 2: the marking happened, the position actually closed
    ledger_path.write_text(
        json.dumps(
            {
                "last_marking_date": "2026-07-23",
                "open_positions": [],
                "closed_trades": [{"exit_date": "2026-07-23"}],
            }
        ),
        encoding="utf-8",
    )
    second = pipeline_forecast_card.run_pipeline_forecast_card()
    assert second["scored_count"] == 1
    assert second["scored"][0]["absolute_error"] == 0
    assert second["pending_forecast"]["as_of_marking_date"] == "2026-07-23"
    assert second["never_a_gate_input"] is True


# ---------- kaizen ledger ----------


def test_kaizen_aggregates_and_prioritizes_defects(monkeypatch, tmp_path) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "adversarial_stress").mkdir(parents=True)
    (art / "forward_walk").mkdir(parents=True)
    (art / "research_supervisor").mkdir(parents=True)
    (art / "ops").mkdir(parents=True)
    (art / "adversarial_stress" / "adversarial_stress_repair_items.jsonl").write_text(
        "\n".join(
            json.dumps(
                {"reason": "single_name_concentration_breach", "detail": "NVDA 30%"}
            )
            for _ in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    (art / "forward_walk" / "forward_walk_ledger.json").write_text(
        json.dumps(
            {
                "open_positions": [
                    {
                        "symbol": "IONQ",
                        "last_quote_quality_status": "deferred_unreliable_quote",
                    }
                ],
                "censored_positions": [
                    {"censor_reason_codes": ["contract_quote_continuity_lost"]},
                    {"censor_reason_codes": ["contract_quote_continuity_lost"]},
                    {"censor_reason_codes": ["contract_quote_continuity_lost"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    (art / "research_supervisor" / "supervisor_run_journal.jsonl").write_text(
        json.dumps(
            {"stage_states": {"foundry": "failed_absorbed", "walk": "completed"}}
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kaizen_ledger, "ART", art)
    monkeypatch.setattr(
        kaizen_ledger, "KAIZEN_PATH", art / "ops" / "kaizen_ledger.json"
    )

    summary = kaizen_ledger.run_kaizen_ledger()

    assert summary["defect_class_count"] >= 3
    assert (
        summary["top_defects"][0]["defect_type"] == "contract_quote_continuity_lost"
    )  # highest count first
    assert summary["never_a_gate_input"] is True
    types = {d["defect_type"] for d in summary["top_defects"]}
    assert {
        "single_name_concentration_breach",
        "deferred_unreliable_quote",
        "failed_stages_latest_run",
    } <= types
    assert "missing_defect_source" not in types


# ---------- reliability SLO ----------


def test_trailing_trading_days_skips_weekends() -> None:
    days = trailing_trading_days(date(2026, 7, 20), 5)  # Monday
    assert days[-1] == "2026-07-20"
    assert "2026-07-19" not in days and "2026-07-18" not in days  # weekend skipped
    assert len(days) == 5


def test_fetch_adherence_counts_missed_days(monkeypatch, tmp_path) -> None:
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window[:10]:  # 10 of 14 present
        (chains / day).mkdir()
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    adherence = fetch_adherence(date(2026, 7, 22))
    assert adherence["missed_count"] == 4
    assert adherence["budget_exhausted"] is True


def test_fetch_adherence_one_miss_breaches_95pct_slo(monkeypatch, tmp_path) -> None:
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window[:-1]:
        (chains / day).mkdir()
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)

    adherence = fetch_adherence(date(2026, 7, 22))

    assert adherence["adherence"] == 0.9286
    assert adherence["error_budget_misses_allowed"] == 0
    assert adherence["budget_exhausted"] is True


def test_reliability_slo_breach_is_operational_cadence_guard_only(
    monkeypatch, tmp_path
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    chains = tmp_path / "chains"
    chains.mkdir()
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    monkeypatch.setattr(
        reliability_slo, "SLO_PATH", art / "ops" / "reliability_slo.json"
    )

    summary = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22), now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
    )

    assert summary["slo_status"] == "error_budget_breached"
    assert any("error budget" in b for b in summary["breaches"])
    assert "reliability work outranks research work" in summary["recommendation"]
    assert summary["operational_cadence_guard_allowed"] is True
    assert (
        summary["operational_cadence_guard_scope"]
        == "fail_closed_cadence_acceleration_only"
    )
    assert summary["edge_evidence_allowed"] is False
    assert summary["readiness_gate_input_allowed"] is False
    assert summary["trading_gate_input_allowed"] is False
    assert summary["not_edge_evidence"] is True
    assert summary["generated_at_utc"] == "2026-07-22T20:00:00+00:00"
    unhashed = dict(summary)
    claimed_hash = unhashed.pop("reproducibility_hash")
    assert stable_hash(unhashed) == claimed_hash


def test_reliability_slo_uses_research_supervisor_journal_run_timestamp(
    monkeypatch,
    tmp_path,
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    supervisor = art / "research_supervisor"
    supervisor.mkdir()
    supervisor.joinpath("supervisor_run_journal.jsonl").write_text(
        json.dumps({"run_utc": "2026-07-22T19:30:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window:
        (chains / day).mkdir()
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    monkeypatch.setattr(
        reliability_slo, "SLO_PATH", art / "ops" / "reliability_slo.json"
    )

    summary = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22),
        now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
        disk_free_gb=50.0,
    )

    assert summary["supervisor_journal_age_hours"] == 0.5
    assert not any("supervisor journal" in breach for breach in summary["breaches"])


def test_reliability_slo_classifies_stale_running_artifact_fail_closed(
    monkeypatch,
    tmp_path,
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    supervisor = art / "research_supervisor"
    supervisor.mkdir()
    supervisor.joinpath("supervisor_run_journal.jsonl").write_text(
        json.dumps({"run_utc": "2026-07-22T19:30:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    supervisor.joinpath("supervisor_active_run.json").write_text(
        json.dumps(
            {
                "run_status": "running",
                "heartbeat_at_utc": "2026-07-22T18:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window:
        (chains / day).mkdir()
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    monkeypatch.setattr(
        reliability_slo, "SLO_PATH", art / "ops" / "reliability_slo.json"
    )

    summary = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22),
        now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
        disk_free_gb=50.0,
    )

    assert summary["supervisor_active_run"] == {
        "status": "stale_running_artifact",
        "reported_run_status": "running",
        "heartbeat_age_hours": 2.0,
        "breach": True,
    }
    assert any(
        "active-run liveness is unverified" in breach for breach in summary["breaches"]
    )
    assert summary["slo_status"] == "error_budget_breached"


def test_reliability_slo_surfaces_lane_stalls_and_never_successful_lanes(
    monkeypatch,
    tmp_path,
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    schedule = art / "acceleration"
    schedule.mkdir(parents=True)
    schedule.joinpath("schedule_state.json").write_text(
        json.dumps(
            {
                "last_attempt_utc": {
                    "autonomous_strategy_research": (
                        "2026-07-22T17:00:00+00:00"
                    ),
                },
                "last_success_utc": {},
                "lane_statuses": {
                    "autonomous_strategy_research": {
                        "status": "degraded_evidence",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(
        reliability_slo,
        "LANES",
        (
            {
                "lane_id": "autonomous_strategy_research",
                "interval_minutes": 60,
                "window": "always",
                "timeout_seconds": 60,
                "retries": 0,
                "network": False,
                "description": "fixture",
            },
        ),
    )

    classified = reliability_slo.classify_lane_reliability(
        datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
    )

    assert classified["status"] == "lane_reliability_breached"
    assert classified["breached_lane_count"] == 1
    lane = classified["lanes"][0]
    assert lane["minutes_since_attempt"] == 180.0
    assert lane["minutes_since_verified_success"] is None
    assert lane["breach_reasons"] == [
        "attempt_stalled",
        "never_verified_success",
        "chronic_status:degraded_evidence",
    ]


def test_reliability_slo_breaches_on_aged_supervisor_repair_items(
    monkeypatch,
    tmp_path,
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    supervisor = art / "research_supervisor"
    supervisor.mkdir(parents=True)
    supervisor.joinpath(
        "resilient_research_supervisor_repair_queue.jsonl"
    ).write_text(
        json.dumps(
            {
                "artifact_type": "research_supervisor_repair_item",
                "stage": "fixture",
                "recorded_at_utc": "2026-07-18T20:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reliability_slo, "ART", art)

    classified = reliability_slo.classify_repair_queue(
        datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
    )

    assert classified["status"] == "repair_queue_age_breached"
    assert classified["open_item_count"] == 1
    assert classified["oldest_item_age_hours"] == 96.0
    assert classified["breach"] is True


def test_reliability_slo_missing_required_evidence_fails_closed(
    monkeypatch,
    tmp_path,
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window:
        (chains / day).mkdir()
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    monkeypatch.setattr(
        reliability_slo, "SLO_PATH", art / "ops" / "reliability_slo.json"
    )
    monkeypatch.setattr(reliability_slo, "_disk_free_gb", lambda: None)

    summary = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22),
        now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
    )

    assert summary["slo_status"] == "error_budget_breached"
    assert "forward-walk marking timestamp is missing or invalid" in summary["breaches"]
    assert "supervisor journal timestamp is missing or invalid" in summary["breaches"]
    assert "nightly summary timestamp is missing or invalid" in summary["breaches"]
    assert "disk headroom is unavailable" in summary["breaches"]


def test_reliability_slo_future_dated_evidence_fails_closed(
    monkeypatch,
    tmp_path,
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    (art / "forward_walk").mkdir()
    (art / "nightly").mkdir()
    supervisor = art / "research_supervisor"
    supervisor.mkdir()
    (art / "forward_walk" / "forward_walk_summary.json").write_text(
        json.dumps({"snapshot_date": "2026-07-23"}),
        encoding="utf-8",
    )
    (art / "nightly" / "nightly_latest.json").write_text(
        json.dumps({"finished_at_utc": "2026-07-22T21:00:00+00:00"}),
        encoding="utf-8",
    )
    supervisor.joinpath("supervisor_run_journal.jsonl").write_text(
        json.dumps({"run_utc": "2026-07-22T21:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window:
        (chains / day).mkdir()
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    monkeypatch.setattr(
        reliability_slo, "SLO_PATH", art / "ops" / "reliability_slo.json"
    )

    summary = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22),
        now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
        disk_free_gb=50.0,
    )

    assert summary["slo_status"] == "error_budget_breached"
    assert any(
        "forward-walk marking timestamp is future-dated" in b
        for b in summary["breaches"]
    )
    assert any(
        "supervisor journal timestamp is future-dated" in b for b in summary["breaches"]
    )
    assert any(
        "nightly summary timestamp is future-dated" in b for b in summary["breaches"]
    )


# ---------- fetch hardening (retries + carry-forward + health) ----------


def test_with_retries_recovers_from_transient_failures(monkeypatch) -> None:
    from operator_tools import operator_fetch_option_chains as fetch

    monkeypatch.setattr(fetch.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise KeyError("transient")
        return "ok"

    result, error = fetch._with_retries(flaky)
    assert result == "ok" and error is None and calls["n"] == 3

    def always_fails():
        raise KeyError("permanent")

    result, error = fetch._with_retries(always_fails)
    assert result is None and isinstance(error, KeyError)


def test_prior_calendar_rows_carry_only_future_dates(monkeypatch, tmp_path) -> None:
    from datetime import date as date_type

    from operator_tools import operator_fetch_option_chains as fetch

    monkeypatch.setattr(fetch, "EARNINGS_OUT", tmp_path)
    (tmp_path / "2026-07-22_earnings.csv").write_text(
        "snapshot_date,symbol,earnings_date,source\n"
        "2026-07-22,AAPL,2026-07-30,yahoo_finance_earnings\n"
        "2026-07-22,MSFT,2026-07-01,yahoo_finance_earnings\n"  # past: dropped
        "2026-07-22,ADP,2026-07-29,yahoo_finance_earnings\n",
        encoding="utf-8",
    )
    rows = fetch._prior_calendar_future_rows(date_type(2026, 7, 23))
    assert rows == {"AAPL": ["2026-07-30"], "ADP": ["2026-07-29"]}


def test_vol_term_merge_preserves_failed_or_regressed_index_history() -> None:
    from operator_tools.operator_fetch_macro_context import _merge_vol_term_rows

    prior = {
        "VIX": [
            ("2026-07-20", 17.0),
            ("2026-07-21", 18.0),
        ],
        "VIX3M": [
            ("2026-07-20", 20.0),
            ("2026-07-21", 21.0),
        ],
    }
    fetched = {
        "VIX": [
            ("2026-07-20", 17.0),
            ("2026-07-21", 18.0),
            ("2026-07-22", 19.0),
        ],
        "VIX3M": [("2026-07-20", 20.0)],
    }

    merged = _merge_vol_term_rows(prior, fetched)

    assert merged["VIX"] == fetched["VIX"]
    assert merged["VIX3M"] == prior["VIX3M"]


def test_stale_corrupt_operational_marker_is_archived_with_recovery_evidence(
    monkeypatch,
    tmp_path,
) -> None:
    from operator_tools import operational_run_marker

    marker_root = tmp_path / "operational_runs"
    marker_root.mkdir()
    marker = marker_root / "daily_ritual.json"
    marker.write_text("{", encoding="utf-8")
    now_utc = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
    stale_timestamp = (
        now_utc.timestamp()
        - operational_run_marker.CORRUPT_MARKER_STALE_SECONDS
        - 1
    )
    os.utime(marker, (stale_timestamp, stale_timestamp))
    monkeypatch.setattr(operational_run_marker, "MARKER_ROOT", marker_root)

    active = operational_run_marker.operational_run_active(
        "daily_ritual",
        now_utc,
    )

    assert active is False
    assert not marker.exists()
    assert len(tuple(marker_root.glob("daily_ritual.corrupt.*.json"))) == 1
    recovery = marker_root / "operational_marker_recovery.jsonl"
    assert "stale_corrupt_marker_archived" in recovery.read_text(encoding="utf-8")


def test_kaizen_counts_fetch_failures_that_survived_retries(
    monkeypatch, tmp_path
) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    manifests = tmp_path / "dopey_data" / "real" / "manifests"
    manifests.mkdir(parents=True)
    earnings = tmp_path / "dopey_data" / "real" / "raw" / "earnings_calendar"
    earnings.mkdir(parents=True)
    manifests.joinpath("options_data_manifest.json").write_text(
        json.dumps(
            {
                "fetch_health": {
                    "symbols_failed_after_retries": {
                        "IONQ": "KeyError: x",
                        "SOUN": "TimeoutError: y",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    earnings.joinpath("2026-07-23_earnings_fetch_health.json").write_text(
        json.dumps(
            {
                "symbols_failed_after_retries": {"ADP": "KeyError"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(kaizen_ledger, "ART", art)
    monkeypatch.setattr(kaizen_ledger, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        kaizen_ledger, "KAIZEN_PATH", art / "ops" / "kaizen_ledger.json"
    )

    summary = kaizen_ledger.run_kaizen_ledger()

    by_source = {d["source"]: d for d in summary["top_defects"]}
    assert by_source["chain_fetch"]["count"] == 2
    assert by_source["earnings_fetch"]["count"] == 1


def test_disk_headroom_breach_is_reported(monkeypatch, tmp_path) -> None:
    art = tmp_path / "artifacts" / "dopey"
    (art / "ops").mkdir(parents=True)
    chains = tmp_path / "chains"
    chains.mkdir()
    window = trailing_trading_days(date(2026, 7, 22), 14)
    for day in window:
        (chains / day).mkdir()  # fetch fully adherent: isolate the disk SLI
    monkeypatch.setattr(reliability_slo, "ART", art)
    monkeypatch.setattr(reliability_slo, "CHAIN_RAW_DIR", chains)
    monkeypatch.setattr(
        reliability_slo, "SLO_PATH", art / "ops" / "reliability_slo.json"
    )

    low = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22),
        now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
        disk_free_gb=0.5,
    )
    assert any("disk headroom" in b for b in low["breaches"])
    assert low["disk_free_gb"] == 0.5

    fine = reliability_slo.run_reliability_slo(
        as_of=date(2026, 7, 22),
        now=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
        disk_free_gb=50.0,
    )
    assert not any("disk headroom" in b for b in fine["breaches"])
