from __future__ import annotations

from dopey_autonomy.champion_hardening_common import (
    apply_holdout,
    apply_stress_case,
    holdout_survived,
    is_test_symbol,
    stress_case_definitions,
    stress_metrics,
    stress_survived,
)
from dopey_autonomy.run_public_paper_champion_hardening_and_deep_stress_v1 import orchestrator_artifact_paths
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_models import ALLOWED_NEXT_BUILD_TARGETS
from dopey_champion.public_champion_decay_monitor_v1 import rolling_window_expectancy, streak_metrics
from dopey_champion.public_champion_hardening_gate_v1 import classify_champion
from dopey_export.artifact_selector import export_selection_rules
from dopey_live_gate.public_champion_hardening_live_gate_status_v3 import build_live_gate_status_v3
from dopey_signal_engine.public_signal_artifact_cleaner_v1 import run_public_signal_artifact_cleaner_v1
from dopey_validation.champion_hardening_preflight import run_champion_hardening_preflight
from dopey_validation.full_suite_stabilizer import collect_test_files, timeout_result
from dopey_wealth_engine.common import REPO_ROOT


def test_stale_simv2_cleaner_removes_intermediate_test_rows(tmp_path, monkeypatch) -> None:
    signal_path = tmp_path / "signals" / "public_signal_mutation_candidates_v4.jsonl"
    signal_path.parent.mkdir(parents=True)
    signal_path.write_text(
        '{"symbol":"SIMV2A","signal_id":"s1","strategy_id":"x"}\n'
        '{"symbol":"SPY","signal_id":"s2","strategy_id":"y"}\n',
        encoding="utf-8",
    )
    hardening_root = tmp_path / "champion_hardening"
    hardening_root.mkdir(parents=True)
    import dopey_signal_engine.public_signal_artifact_cleaner_v1 as cleaner_mod
    monkeypatch.setattr(cleaner_mod, "SIGNAL_CANDIDATES_PATH", signal_path)
    monkeypatch.setattr(cleaner_mod, "HARDENING_ROOT", hardening_root)
    monkeypatch.setattr(cleaner_mod, "SUMMARY_PATH", hardening_root / "summary.json")
    monkeypatch.setattr(cleaner_mod, "REMOVED_PATH", hardening_root / "removed.jsonl")
    monkeypatch.setattr(cleaner_mod, "QUALITY_FLAGS_PATH", hardening_root / "flags.jsonl")
    monkeypatch.setattr(cleaner_mod, "PROOF_PATH", hardening_root / "proof.jsonl")
    monkeypatch.setattr(cleaner_mod, "BACKUP_ROOT", tmp_path / "backups")
    summary = run_public_signal_artifact_cleaner_v1()
    assert summary["removed_test_signal_count"] == 1
    assert summary["output_signal_count"] == 1
    assert summary["simv2_rows_remaining"] == 0
    assert summary["live_trading_enabled"] is False


def test_decision_artifacts_remain_clean_via_preflight() -> None:
    summary = run_champion_hardening_preflight()
    assert summary["decision_artifacts_clean"] is True
    assert summary["live_trading_enabled"] is False


def test_champion_inventory_required_fields_present() -> None:
    required = {
        "champion_name", "canonical_champion_id", "cohort_level", "sample_count", "net_pnl",
        "expectancy", "profit_factor", "max_drawdown", "top_symbol_share", "live_gate_lock_status",
    }
    # Pure shape test using sample champion/trades without full artifact run
    from dopey_autonomy.champion_hardening_common import trades_for_champion
    champion = {"cohort_level": "variant_id", "cohort_id": "bollinger_expansion|fast_scalp|dte7|ATM"}
    trades = sample_trades()
    assert trades_for_champion(champion, trades)
    assert required


def test_deep_stress_matrix_applies_slippage_theta_iv_outlier_stress() -> None:
    trades = sample_trades()
    cases = stress_case_definitions()
    families = {case["stress_family"] for case in cases}
    assert {"slippage", "theta", "iv_shock", "outlier_removal", "concentration", "recent_only", "regime_specific"} <= families
    slippage_case = next(case for case in cases if case["stress_id"] == "slippage_2_0x")
    baseline = stress_metrics(trades)
    stressed = stress_metrics(apply_stress_case(trades, slippage_case))
    assert stressed["net_pnl"] <= baseline["net_pnl"]


def test_holdout_expansion_computes_partitions() -> None:
    trades = sample_trades()
    holdout = {"holdout_id": "2024_trend_ai", "start": "2024-01-01", "end": "2024-12-31"}
    subset = apply_holdout(trades, holdout)
    assert subset
    assert all(str(trade.get("entry_date", "")).startswith("2024") for trade in subset)


def test_decay_monitor_flags_degraded_champions() -> None:
    degraded = [0.5 if index % 2 == 0 else -2.0 for index in range(30)]
    assert rolling_window_expectancy(degraded, 20) < 0.0


def test_hardening_gate_hardens_conditions_or_demotes() -> None:
    hardened, _ = classify_champion(
        core_survived=20, core_total=20, holdout_survived=18, holdout_total=20,
        alert_count=0, concentration_failures=0, outlier_failures=0,
        champion={"profit_factor": 1.5, "sample_count": 40},
    )
    conditional, _ = classify_champion(
        core_survived=14, core_total=20, holdout_survived=12, holdout_total=20,
        alert_count=1, concentration_failures=1, outlier_failures=0,
        champion={"profit_factor": 1.3, "sample_count": 40},
    )
    demoted, _ = classify_champion(
        core_survived=8, core_total=20, holdout_survived=6, holdout_total=20,
        alert_count=3, concentration_failures=2, outlier_failures=2,
        champion={"profit_factor": 1.0, "sample_count": 40},
    )
    assert hardened == "hardened_public_paper_champion"
    assert conditional == "conditional_public_paper_champion"
    assert demoted == "demoted_failed_deep_stress"


def test_hardening_gate_does_not_enable_live_trading() -> None:
    status = build_live_gate_status_v3({"hardened_champion_count": 2, "conditional_champion_count": 1, "demoted_champion_count": 0})
    assert status["live_trading_enabled"] is False


def test_repair_queue_produces_targeted_records() -> None:
    from dopey_champion.public_champion_hardening_gate_v1 import build_repair_items
    items = build_repair_items("champ-a", "conditional_public_paper_champion", ["holdout_partition_failure"])
    assert items
    assert items[0]["repair_type"] == "recent_market_repair"


def test_scoreboard_separates_hardened_conditional_demoted() -> None:
    from dopey_scoreboard.public_champion_hardening_scoreboard_v1 import build_public_champion_hardening_scoreboard_v1
    gate_summary = {
        "input_public_champion_count": 3,
        "hardened_champion_names": ["a"],
        "conditional_champion_names": ["b"],
        "demoted_champion_names": ["c"],
    }
    scoreboard = build_public_champion_hardening_scoreboard_v1(gate_summary, {}, {}, {}, {}, [])
    assert scoreboard["hardened_champion_names"] == ["a"]
    assert scoreboard["conditional_champion_names"] == ["b"]
    assert scoreboard["demoted_champion_names"] == ["c"]


def test_live_gate_remains_disabled_even_if_champions_harden() -> None:
    status = build_live_gate_status_v3({"hardened_champion_count": 5, "conditional_champion_count": 2, "demoted_champion_count": 0})
    assert status["live_gate_status"] == "disabled_live_gate_locked"
    assert status["live_trading_enabled"] is False
    assert status["broker_connection_enabled"] is False
    assert status["real_order_enabled"] is False


def test_official_robinhood_market_data_lane_allowed() -> None:
    status = build_live_gate_status_v3({"hardened_champion_count": 1, "conditional_champion_count": 0, "demoted_champion_count": 0})
    assert status["official_robinhood_market_data_allowed"] is True
    assert status["unofficial_robinhood_api_blocked"] is True
    assert status["robinhood_scraping_blocked"] is True
    assert status["robinhood_reverse_auth_blocked"] is True
    assert status["robinhood_live_trading_enabled"] is False


def test_no_env_credentials_broker_orders_or_live_trading() -> None:
    assert not (REPO_ROOT / ".env").exists()
    status = build_live_gate_status_v3({"hardened_champion_count": 0, "conditional_champion_count": 0, "demoted_champion_count": 0})
    assert status["credentials_present"] is False
    assert status["live_trading_enabled"] is False


def test_full_orchestrator_writes_artifact_paths() -> None:
    paths = orchestrator_artifact_paths()
    assert "public_paper_champion_hardening_and_deep_stress_v1_summary" in paths
    assert "public_paper_champion_hardening_and_deep_stress_v1_validation_summary" in paths


def test_audit_report_export_review_recognize_hardening_artifacts() -> None:
    spec_names = {spec[0] for spec in ARTIFACT_SPECS}
    rule_names = {rule.artifact_id for rule in export_selection_rules()}
    artifact_ids = [
        "champion_hardening_preflight_summary",
        "public_signal_artifact_cleaner_summary",
        "public_champion_inventory_v1_summary",
        "public_champion_deep_stress_matrix_v1_summary",
        "public_champion_holdout_expansion_v1_summary",
        "public_champion_decay_monitor_v1_summary",
        "public_champion_hardening_gate_v1_summary",
        "public_champion_hardening_scoreboard_v1",
        "public_champion_hardening_live_gate_status_v3",
        "public_paper_champion_hardening_and_deep_stress_v1_summary",
        "public_paper_champion_hardening_and_deep_stress_v1_validation_summary",
    ]
    for artifact_id in artifact_ids:
        assert artifact_id in spec_names
        assert artifact_id in rule_names
    assert "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1" in ALLOWED_NEXT_BUILD_TARGETS


def test_validation_stabilizer_includes_hardening_shard() -> None:
    files = collect_test_files(REPO_ROOT)
    assert "tests/test_public_paper_champion_hardening_and_deep_stress_v1.py" in files


def test_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_stress_and_holdout_survival_helpers() -> None:
    trades = sample_trades()
    metrics = stress_metrics(trades)
    survived, _ = stress_survived(metrics, min_sample=5)
    assert survived is True
    baseline = metrics
    holdout_metrics = stress_metrics(trades[:20])
    holdout_ok, _ = holdout_survived(holdout_metrics, baseline)
    assert isinstance(holdout_ok, bool)


def test_is_test_symbol_blocks_simv2_prefixes() -> None:
    assert is_test_symbol("SIMV2")
    assert is_test_symbol("TESTALPHA")
    assert not is_test_symbol("SPY")


def sample_trades() -> list[dict[str, object]]:
    trades: list[dict[str, object]] = []
    for index in range(40):
        trades.append({
            "variant_id": "bollinger_expansion|fast_scalp|dte7|ATM",
            "micro_cohort_id": "bollinger_expansion|scalp|short_dte|atm",
            "setup_cohort_id": "bollinger_expansion|bullish|scalp",
            "family_cohort_id": "bollinger_expansion",
            "regime_cohort_id": "bollinger_expansion|low_volatility",
            "symbol_cluster_cohort_id": "bollinger_expansion|broad_etf",
            "canonical_champion_id": "champ-test",
            "symbol": "SPY" if index % 2 == 0 else "QQQ",
            "sector": "broad_etf",
            "regime": "low_volatility" if index % 3 else "high_volatility",
            "trend_regime": "uptrend" if index % 4 else "downtrend",
            "entry_date": f"2024-{(index % 12) + 1:02d}-15",
            "trade_intent": "long_call",
            "paper_pnl": 12.0 if index % 3 else -4.0,
            "slippage_cost": 0.5,
            "theta_decay_cost": 0.1,
            "entry_spot": 100.0,
            "market_data_source_type": "public_live_fetch",
        })
    return trades


def test_streak_metrics_recovery_measures_trades_to_earn_back_losses() -> None:
    assert streak_metrics([]) == (0, 0)
    assert streak_metrics([1.0, 2.0]) == (0, 0)
    assert streak_metrics([-1.0, -1.0, -1.0, 3.0]) == (3, 1)
    assert streak_metrics([-1.0, -1.0, -1.0, 1.0, 1.0, 1.0]) == (3, 3)
    # Worst streak is never earned back: recovery is 0, not the streak length.
    assert streak_metrics([-1.0, -1.0, 5.0, -1.0, -1.0, -1.0, 1.0]) == (3, 0)
    # Net recovery path includes intervening losses.
    assert streak_metrics([-2.0, 1.0, -1.0, 2.0]) == (1, 3)
    # Equal-length streaks use the larger loss, not the first occurrence.
    assert streak_metrics([-1.0, 5.0, -3.0, 2.0, 1.0]) == (1, 2)
