from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_autonomy.run_real_public_market_wealth_engine_rerun import build_validation_summary
from dopey_chart_vision.run_chart_vision_engine import run_chart_vision_engine
from dopey_evolution.run_winner_loser_evolution_loop import run_winner_loser_evolution_loop
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_market_intake.local_cache_provider import CACHE_ROOT
from dopey_market_intake.market_data_cache_manager import run_market_data_cache_manager
from dopey_market_intake.market_data_tier_models import assign_data_tier
from dopey_market_intake.market_lake_public_promotion import run_market_lake_public_promotion
from dopey_market_intake.provider_health_diagnostics import run_provider_health_diagnostics
from dopey_market_intake.provider_ladder_v2 import run_public_ohlcv_provider_ladder_v2
from dopey_market_intake.public_ohlcv_provider_models import PUBLIC_OHLCV_FIELDS
from dopey_market_intake.stooq_ohlcv_provider_v2 import _parse_stooq_body
from dopey_market_intake.yahoo_direct_csv_provider import _empty as yahoo_empty
from dopey_options_engine.run_model_priced_trade_constructor import run_model_priced_trade_constructor
from dopey_runtime_bootstrap.active_python_resolver import REPO_VENV_PYTHON, preferred_repo_python, python_inventory
from dopey_runtime_bootstrap.provider_install_repair import run_provider_install_repair
from dopey_runtime_bootstrap.venv_package_import_audit import audit_imports_for_python
from dopey_scoreboard.public_vs_fixture_scoreboard_split import run_public_vs_fixture_scoreboard_split
from dopey_signal_engine.run_aggressive_signal_engine import run_aggressive_signal_engine
from dopey_tournament.run_paper_money_tournament_engine import run_paper_money_tournament_engine
from dopey_validation.full_suite_stabilizer import timeout_result
from dopey_wealth_engine.common import DATA_ROOT, REPO_ROOT, read_csv, read_jsonl, write_csv
from dopey_wealth_engine.fixtures import generate_fixture_ohlcv


@pytest.fixture
def simulated_public_symbol() -> Iterator[str]:
    symbol = "SIMV2"
    _remove_symbol_files(symbol)
    yield symbol
    _remove_symbol_files(symbol)


def test_market_data_provider_install_and_fallback_expansion_v2(
    simulated_public_symbol: str,
) -> None:
    inventory = python_inventory(2)
    assert any(record["source"] == "repo_venv" for record in inventory)
    assert preferred_repo_python() == REPO_VENV_PYTHON

    provider_install = run_provider_install_repair(1, 1, False)
    assert provider_install["repo_venv_exists"] is True
    assert provider_install["credentials_created"] is False
    assert provider_install["env_created"] is False
    assert provider_install["broker_connection_used"] is False

    audit = audit_imports_for_python(preferred_repo_python(), ["yfinance", "openbb"], 2)
    assert {record["package"] for record in audit} == {"yfinance", "openbb"}

    symbol = simulated_public_symbol
    public_rows = _public_rows(symbol, 620)
    write_csv(CACHE_ROOT / "simulated_public" / f"{symbol}.csv", public_rows, PUBLIC_OHLCV_FIELDS)
    ladder = run_public_ohlcv_provider_ladder_v2([symbol], False, 3)
    assert ladder["provider_ladder_status"] == "public_ohlcv_loaded_partial_universe"
    assert ladder["symbols_loaded"] == [symbol]
    assert ladder["used_fixture_fallback"] is False

    empty_rows, header_status = _parse_stooq_body(symbol, "", "")
    assert empty_rows == []
    assert header_status == "empty_csv"
    yahoo_failure = yahoo_empty(symbol, "https://query1.finance.yahoo.com/fail", "fetch_failed", "URLError: offline", None, 0, "missing")
    assert yahoo_failure["rows"] == []
    assert yahoo_failure["status"] == "fetch_failed"

    cache = run_market_data_cache_manager(36500)
    assert cache["cache_file_count"] >= 1
    assert cache["credentials_created"] is False

    fixture_rows = generate_fixture_ohlcv(symbol, 620)
    write_csv(DATA_ROOT / "market_lake" / "fixture_fallback" / "daily_ohlcv" / f"{symbol}.csv", fixture_rows, ["date", "open", "high", "low", "close", "volume"])
    promotion = run_market_lake_public_promotion(True)
    assert symbol in promotion["paper_trading_symbols"]
    assert promotion["active_symbols_public"] >= 1
    active_rows = read_csv(DATA_ROOT / "market_lake" / "active" / "daily_ohlcv" / f"{symbol}.csv")
    assert active_rows[0]["market_data_source_type"] == "public_cache"

    assert assign_data_tier(40, True, True, True, "public_no_key") == "market_vision"
    assert assign_data_tier(250, True, True, True, "public_no_key") == "research_sandbox"
    assert assign_data_tier(620, True, True, True, "public_no_key") == "paper_trading"

    diagnostics = run_provider_health_diagnostics([symbol], 3)
    assert "yfinance_diagnosis" in diagnostics
    assert "openbb_diagnosis" in diagnostics

    chart = run_chart_vision_engine()
    assert chart["chart_vision_status"] == "charts_generated"
    signals = run_aggressive_signal_engine()
    assert signals["signal_generation_status"] == "candidates_generated"
    signal_records = read_jsonl(Path(signals["artifact_paths"]["aggressive_signal_candidates"]))
    assert all("market_data_source_type" in record for record in signal_records)

    options = run_model_priced_trade_constructor()
    assert options["unsupported_structure_count"] == 0
    option_records = read_jsonl(Path(options["artifact_paths"]["model_priced_trade_candidates"]))
    assert all(record["trade_intent"] in {"long_call", "long_put", "no_trade"} for record in option_records)
    assert all("market_data_source_type" in record for record in option_records)

    tournament = run_paper_money_tournament_engine()
    assert tournament["paper_tournament_status"] == "complete"
    trade_records = read_jsonl(Path(tournament["artifact_paths"]["paper_tournament_trades"]))
    assert all("market_data_source_type" in record for record in trade_records)

    evolution = run_winner_loser_evolution_loop()
    assert "fixture_only_champion_count" in evolution
    assert "public_data_paper_champion_count" in evolution

    split = run_public_vs_fixture_scoreboard_split()
    assert split["scoreboard_split_status"] == "complete"
    assert split["merged_without_labels"] is False

    validation = build_validation_summary("simulated_public_provider_test_complete", [], [])
    assert validation["timeout_recorded_as_pass"] is False
    assert validation["validation_stabilizer_includes_shard"] is True

    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    assert "public_ohlcv_provider_ladder_v2_summary" in artifact_types
    assert "real_public_market_wealth_rerun_summary" in artifact_types
    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "public_ohlcv_provider_ladder_v2_summary" in export_ids
    assert "market_provider_expansion" in FINDING_CATEGORIES

    stabilizer_source = (REPO_ROOT / "dopey_validation" / "full_suite_stabilizer.py").read_text(encoding="utf-8")
    assert "tests/test_market_data_provider_install_and_fallback_expansion_v2.py" in stabilizer_source
    timeout = timeout_result(["python", "-m", "pytest"], 1)
    assert timeout["status"] == "inconclusive_timeout"
    assert timeout["timeout_recorded_as_pass"] is False

    assert not (REPO_ROOT / ".env").exists()


def _public_rows(symbol: str, count: int) -> list[dict]:
    rows = generate_fixture_ohlcv(symbol, count)
    business_dates = _recent_business_dates(count)
    output: list[dict] = []
    for index, row in enumerate(rows):
        output.append({
            **row,
            "date": business_dates[index],
            "adjusted_close": row["close"],
            "provider": "simulated_public",
            "source_url": "local-cache-simulated-public-provider",
            "fetch_timestamp": "2026-01-01T00:00:00+00:00",
            "adjustment_status": "adjusted_close_unavailable_close_used",
            "market_data_source_type": "public_cache",
        })
    return output


def _remove_symbol_files(symbol: str) -> None:
    paths = [
        DATA_ROOT / "market_lake" / "public" / "daily_ohlcv" / f"{symbol}.csv",
        DATA_ROOT / "market_lake" / "active" / "daily_ohlcv" / f"{symbol}.csv",
        DATA_ROOT / "market_lake" / "normalized" / "daily_ohlcv" / f"{symbol}.csv",
        DATA_ROOT / "market_lake" / "fixture_fallback" / "daily_ohlcv" / f"{symbol}.csv",
    ]
    paths.extend(CACHE_ROOT.glob(f"*/{symbol}.csv"))
    for path in paths:
        if path.exists():
            path.unlink()


def _recent_business_dates(count: int) -> list[str]:
    values: list[str] = []
    cursor = date.today()
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return list(reversed(values))
