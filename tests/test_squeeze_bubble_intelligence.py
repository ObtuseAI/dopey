"""Focused end-to-end proof for the daily squeeze/bubble research lane."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dopey_squeeze_bubble.intake import IntelligencePaths
from dopey_squeeze_bubble.models import default_policy
from dopey_squeeze_bubble.runtime import run_squeeze_bubble_intelligence


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _history_rows(
    symbol: str,
    closes: list[float],
    final_volume: float,
) -> list[dict[str, object]]:
    first_day = date(2025, 9, 28)
    rows: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        day = first_day + timedelta(days=index)
        volume = final_volume if index == len(closes) - 1 else 1_000_000.0
        rows.append(
            {
                "date": day.isoformat(),
                "symbol": symbol,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.98,
                "close": close,
                "adjusted_close": close,
                "volume": volume,
                "source": "integration_fixture",
            }
        )
    return rows


def test_daily_engine_separates_pressure_fragility_and_execution_boundaries(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "history"
    squeeze_closes = [20.0 * (1.008**index) for index in range(300)]
    bubble_closes = [30.0 * (1.006**index) for index in range(295)]
    bubble_closes.extend(
        [
            bubble_closes[-1] * 0.97,
            bubble_closes[-1] * 0.92,
            bubble_closes[-1] * 0.86,
            bubble_closes[-1] * 0.78,
            bubble_closes[-1] * 0.70,
        ]
    )
    history_fields = (
        "date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "source",
    )
    _write_csv(
        history_root / "SQUEEZE.csv",
        history_fields,
        _history_rows("SQUEEZE", squeeze_closes, 5_000_000.0),
    )
    _write_csv(
        history_root / "BUBBLE.csv",
        history_fields,
        _history_rows("BUBBLE", bubble_closes, 6_000_000.0),
    )

    macro = tmp_path / "macro"
    quant = tmp_path / "quant"
    short_fields = (
        "date",
        "symbol",
        "shares_short",
        "shares_short_prior_month",
        "short_percent_float",
        "short_ratio",
        "float_shares",
        "shares_outstanding",
        "held_percent_institutions",
        "held_percent_insiders",
        "average_volume",
        "market_cap",
        "source",
    )
    _write_csv(
        macro / "short_crowding.csv",
        short_fields,
        [
            {
                "date": "2026-07-24",
                "symbol": "SQUEEZE",
                "shares_short": 8_000_000,
                "shares_short_prior_month": 5_000_000,
                "short_percent_float": 0.40,
                "short_ratio": 12.0,
                "float_shares": 20_000_000,
                "shares_outstanding": 25_000_000,
                "held_percent_institutions": 0.60,
                "held_percent_insiders": 0.10,
                "average_volume": 800_000,
                "market_cap": 1_000_000_000,
                "source": "licensed_fixture",
            },
            {
                "date": "2026-07-24",
                "symbol": "BUBBLE",
                "shares_short": 1_000_000,
                "shares_short_prior_month": 1_000_000,
                "short_percent_float": 0.03,
                "short_ratio": 1.0,
                "float_shares": 90_000_000,
                "shares_outstanding": 100_000_000,
                "held_percent_institutions": 0.30,
                "held_percent_insiders": 0.05,
                "average_volume": 2_000_000,
                "market_cap": 2_000_000_000,
                "source": "licensed_fixture",
            },
        ],
    )
    _write_csv(
        macro / "finra_short_volume.csv",
        (
            "date",
            "symbol",
            "short_volume",
            "short_exempt_volume",
            "total_volume",
        ),
        [
            {
                "date": "2026-07-24",
                "symbol": "SQUEEZE",
                "short_volume": 800_000,
                "short_exempt_volume": 0,
                "total_volume": 1_000_000,
            },
            {
                "date": "2026-07-24",
                "symbol": "BUBBLE",
                "short_volume": 300_000,
                "short_exempt_volume": 0,
                "total_volume": 1_000_000,
            },
        ],
    )
    fundamental_fields = (
        "date",
        "symbol",
        "theme",
        "in_universe",
        "market_cap",
        "enterprise_value",
        "total_revenue",
        "trailing_pe",
        "forward_pe",
        "price_to_sales",
        "price_to_book",
        "profit_margin",
        "revenue_growth",
        "free_cashflow",
        "total_debt",
        "total_cash",
        "first_trade_date",
    )
    _write_csv(
        macro / "fundamentals.csv",
        fundamental_fields,
        [
            {
                "date": "2026-07-24",
                "symbol": "SQUEEZE",
                "theme": "industrial",
                "in_universe": 1,
                "market_cap": 1_000_000_000,
                "enterprise_value": 950_000_000,
                "total_revenue": 500_000_000,
                "trailing_pe": 20,
                "forward_pe": 18,
                "price_to_sales": 2,
                "price_to_book": 3,
                "profit_margin": 0.1,
                "revenue_growth": 0.1,
                "free_cashflow": 50_000_000,
                "total_debt": 100_000_000,
                "total_cash": 150_000_000,
                "first_trade_date": "2015-01-02",
            },
            {
                "date": "2026-07-24",
                "symbol": "BUBBLE",
                "theme": "ai",
                "in_universe": 1,
                "market_cap": 2_000_000_000,
                "enterprise_value": 4_900_000_000,
                "total_revenue": 100_000_000,
                "trailing_pe": 180,
                "forward_pe": 120,
                "price_to_sales": 40,
                "price_to_book": 30,
                "profit_margin": -0.5,
                "revenue_growth": 0.2,
                "free_cashflow": -500_000_000,
                "total_debt": 3_000_000_000,
                "total_cash": 100_000_000,
                "first_trade_date": "2025-09-28",
            },
        ],
    )
    _write_csv(
        macro / "ipo_calendar.csv",
        (
            "event_date",
            "symbol",
            "company_name",
            "exchange",
            "offer_price",
            "shares_offered",
            "offer_amount",
            "status",
            "source",
        ),
        [
            {
                "event_date": "2025-09-28",
                "symbol": "BUBBLE",
                "company_name": "Bubble Fixture",
                "exchange": "NASDAQ Global",
                "offer_price": 10,
                "shares_offered": 10_000_000,
                "offer_amount": 100_000_000,
                "status": "priced",
                "source": "nasdaq_fixture",
            }
        ],
    )
    _write_csv(
        macro / "borrow_context.csv",
        (
            "date",
            "symbol",
            "borrow_fee_percent",
            "utilization",
            "available_shares",
            "source",
        ),
        [
            {
                "date": "2026-07-24",
                "symbol": "SQUEEZE",
                "borrow_fee_percent": 65,
                "utilization": 0.99,
                "available_shares": 10_000,
                "source": "licensed_fixture",
            }
        ],
    )
    _write_csv(
        macro / "threshold_securities.csv",
        ("date", "symbol", "exchange", "source"),
        [
            {
                "date": "2026-07-24",
                "symbol": "SQUEEZE",
                "exchange": "XNYS",
                "source": "official_fixture",
            }
        ],
    )
    margin_rows: list[dict[str, object]] = []
    for index in range(13):
        month = date(2025, 7, 1) + timedelta(days=31 * index)
        normalized_month = month.replace(day=1)
        margin_rows.append(
            {
                "month": normalized_month.isoformat(),
                "debit_balances_millions": 900_000 + index * 55_000,
                "free_credit_cash_millions": 200_000,
                "free_credit_margin_millions": 190_000,
                "source": "finra_fixture",
            }
        )
    _write_csv(
        macro / "finra_margin_statistics.csv",
        (
            "month",
            "debit_balances_millions",
            "free_credit_cash_millions",
            "free_credit_margin_millions",
            "source",
        ),
        margin_rows,
    )

    ftd_rows = [
        {
            "settlement_date": f"202607{18 + index:02d}",
            "cusip": "000000000",
            "symbol": "SQUEEZE",
            "quantity_fails": 300_000,
            "description": "SQUEEZE FIXTURE",
            "price": 100,
            "archive_url": "https://sec.example/fixture.zip",
            "fetched_at": "2026-07-24T20:00:00+00:00",
        }
        for index in range(5)
    ]
    _write_csv(
        quant / "sec_fails_to_deliver.csv",
        (
            "settlement_date",
            "cusip",
            "symbol",
            "quantity_fails",
            "description",
            "price",
            "archive_url",
            "fetched_at",
        ),
        ftd_rows,
    )
    chain_path = tmp_path / "chain_metrics.jsonl"
    chain_records = (
        {
            "symbol": "SQUEEZE",
            "snapshot_date": "2026-07-24",
            "quote_derived": True,
            "contract_rows": 200,
            "call_open_interest": 500_000,
            "put_open_interest": 100_000,
            "call_volume": 80_000,
            "put_volume": 8_000,
            "put_call_oi_ratio": 0.2,
            "put_call_volume_ratio": 0.1,
            "total_gex_dollar_per_pct": -50_000_000,
            "gamma_flip_strike": 100,
            "atm_implied_vol": 0.9,
        },
        {
            "symbol": "BUBBLE",
            "snapshot_date": "2026-07-24",
            "quote_derived": True,
            "contract_rows": 200,
            "call_open_interest": 600_000,
            "put_open_interest": 120_000,
            "call_volume": 20_000,
            "put_volume": 60_000,
            "put_call_oi_ratio": 0.2,
            "put_call_volume_ratio": 3.0,
            "total_gex_dollar_per_pct": -80_000_000,
            "gamma_flip_strike": 200,
            "atm_implied_vol": 1.2,
        },
    )
    chain_path.write_text(
        "\n".join(json.dumps(record) for record in chain_records) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "artifacts"
    intelligence_paths = IntelligencePaths(
        repository_root=tmp_path,
        history_root=history_root,
        short_crowding_path=macro / "short_crowding.csv",
        short_flow_path=macro / "finra_short_volume.csv",
        fundamentals_path=macro / "fundamentals.csv",
        ftd_path=quant / "sec_fails_to_deliver.csv",
        borrow_path=macro / "borrow_context.csv",
        threshold_path=macro / "threshold_securities.csv",
        margin_path=macro / "finra_margin_statistics.csv",
        ipo_calendar_path=macro / "ipo_calendar.csv",
        chain_metrics_path=chain_path,
    )
    result = run_squeeze_bubble_intelligence(
        intelligence_paths,
        default_policy(),
        datetime(2026, 7, 25, 12, tzinfo=timezone.utc),
        output,
    )

    assert result["squeeze_candidate_count"] == 1
    assert result["bubble_unwind_candidate_count"] == 1
    assert result["order_construction_allowed"] is False
    assert result["paper_twin_required_for_any_live_review"] is True
    assessments = [
        json.loads(line)
        for line in (output / "symbol_assessments.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    by_symbol = {assessment["symbol"]: assessment for assessment in assessments}
    assert by_symbol["SQUEEZE"]["squeeze"]["daily_short_volume_is_short_interest"] is False
    assert (
        by_symbol["BUBBLE"]["bubble"]["preferred_expression"]
        == "long_put_or_bear_put_debit_spread_options_control_required"
    )
    assert by_symbol["BUBBLE"]["bubble"]["naked_short_or_undefined_loss_allowed"] is False
    assert by_symbol["BUBBLE"]["bubble"]["extreme_pe_score"] > 0.8
    assert by_symbol["BUBBLE"]["bubble"]["ipo_reflexivity_score"] > 0.5
    assert (
        by_symbol["BUBBLE"]["bubble"]["ipo_snapshot"]["first_trade_date"]
        == "2025-09-28"
    )
    rerun = run_squeeze_bubble_intelligence(
        intelligence_paths,
        default_policy(),
        datetime(2026, 7, 25, 13, tzinfo=timezone.utc),
        output,
    )
    assert rerun["forward_recording"]["candidate_signal_count"] == 2
    assert rerun["forward_recording"]["appended_signal_count"] == 0
    assert rerun["forward_recording"]["already_recorded_count"] == 2
