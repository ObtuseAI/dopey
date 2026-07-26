from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from dopey_acceleration.cycle import _commands
from dopey_acceleration.schedule import LANES, LANE_EVIDENCE_CONTRACTS, SUBSUMED_BY_CLOSE
from dopey_data.quant_context_intake import (
    CFTC_MARKET_PATTERNS,
    Dataset,
    parse_bls_payload,
    parse_cboe_market_stats,
    parse_cftc_payload,
    parse_fred_series,
    parse_sec_ftd_archive,
    parse_treasury_debt_payload,
    validate_sec_user_agent,
    write_quant_context_outputs,
)


FETCHED_AT = "2026-07-20T00:00:00+00:00"


def test_sec_automated_access_identity_must_be_operator_declared() -> None:
    with pytest.raises(ValueError, match="DOPEY_SEC_USER_AGENT"):
        validate_sec_user_agent(None)
    with pytest.raises(ValueError, match="DOPEY_SEC_USER_AGENT"):
        validate_sec_user_agent("https://github.com/ObtuseAI/dopey")
    assert (
        validate_sec_user_agent("Obtuse AI markets@example.com")
        == "Obtuse AI markets@example.com"
    )


def test_quant_context_parsers_preserve_missing_and_semantic_fields() -> None:
    fred, future_count = parse_fred_series(
        (
            b"observation_date,DFF\n"
            b"2026-07-17,4.25\n"
            b"2026-07-18,.\n"
            b"2026-07-21,4.25\n"
        ),
        "DFF",
        "effective_federal_funds_rate",
        FETCHED_AT,
        date(2026, 7, 20),
    )
    assert fred == [
        (
            "2026-07-17",
            "DFF",
            "effective_federal_funds_rate",
            "4.25",
            FETCHED_AT,
            "latest_revised_snapshot",
        )
    ]
    assert future_count == 1

    bls_payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "LNS14000000",
                    "data": [
                        {
                            "year": "2026",
                            "period": "M06",
                            "periodName": "June",
                            "value": "4.1",
                            "footnotes": [{"text": "Preliminary."}],
                        },
                        {
                            "year": "2026",
                            "period": "M07",
                            "periodName": "July",
                            "value": "-",
                            "footnotes": [{}],
                        },
                    ],
                }
            ]
        },
    }
    bls = parse_bls_payload(
        json.dumps(bls_payload).encode("utf-8"),
        {"LNS14000000": "unemployment_rate"},
        FETCHED_AT,
    )
    assert len(bls) == 1
    assert bls[0][5] == "4.1"
    assert bls[0][6] == "Preliminary."

    treasury_payload = {
        "data": [
            {
                "record_date": "2026-07-16",
                "debt_held_public_amt": "30000000000000.00",
                "intragov_hold_amt": "7000000000000.00",
                "tot_pub_debt_out_amt": "37000000000000.00",
            }
        ]
    }
    treasury = parse_treasury_debt_payload(
        json.dumps(treasury_payload).encode("utf-8"),
        FETCHED_AT,
    )
    assert treasury[0][0] == "2026-07-16"
    assert treasury[0][-1] == FETCHED_AT

    cboe_html = " ".join(
        (
            "TOTAL PUT/CALL RATIO 0.97",
            "INDEX PUT/CALL RATIO 0.98",
            "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO 1.26",
            "EQUITY PUT/CALL RATIO 0.73",
            "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO 0.36",
            "SPX + SPXW PUT/CALL RATIO 1.18",
        )
    )
    cboe = parse_cboe_market_stats(f"<html><body>{cboe_html}</body></html>".encode(), FETCHED_AT)
    assert len(cboe) == 6
    assert cboe[0][1] == "0.97"


def test_cftc_parser_enforces_broad_multi_asset_coverage() -> None:
    records = []
    for index, (_alias, market_pattern) in enumerate(CFTC_MARKET_PATTERNS[:12], start=1):
        records.append(
            {
                "market_and_exchange_names": f"{market_pattern} - TEST EXCHANGE",
                "report_date_as_yyyy_mm_dd": "2026-07-14T00:00:00.000",
                "noncomm_positions_long_all": str(index * 100),
                "noncomm_positions_short_all": str(index * 75),
                "open_interest_all": str(index * 1000),
            }
        )
    rows = parse_cftc_payload(json.dumps(records).encode("utf-8"), FETCHED_AT)
    assert len(rows) == 12
    assert len({row[1] for row in rows}) == 12
    assert all(row[-1] == FETCHED_AT for row in rows)


def test_sec_ftd_parser_filters_universe_without_mislabeling_flow() -> None:
    content = (
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE\n"
        "20260715|037833100|AAPL|12345|APPLE INC|210.00\n"
        "20260715|594918104|MSFT|500|MICROSOFT CORP|500.00\n"
    )
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cnsfails202607a.txt", content)
    rows = parse_sec_ftd_archive(
        archive_buffer.getvalue(),
        "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202607a.zip",
        ("AAPL",),
        FETCHED_AT,
    )
    assert len(rows) == 1
    assert rows[0][2] == "AAPL"
    assert rows[0][3] == "12345"


def test_quant_context_writer_and_scheduler_are_hash_pinned_and_paper_only(tmp_path) -> None:
    dataset = Dataset(
        source_id="fred_macro_regime",
        filename="fred_macro_regime.csv",
        content=b"observation_date,series_id,value\n2026-07-17,DFF,4.25\n",
        row_count=1,
        newest_observation="2026-07-17",
        url="https://fred.stlouisfed.org/graph/fredgraph.csv",
        authority="federal_reserve_bank_of_st_louis",
        semantics="latest revised snapshot",
        redistribution_allowed=True,
        available_at=FETCHED_AT,
        future_observation_rows_quarantined=0,
    )
    statuses = [
        {
            "source_id": source_id,
            "authority": "official",
            "status": "staged",
            "required": True,
            "row_count": 1,
            "newest_observation": "2026-07-17",
            "url": "https://example.invalid/official",
            "error": "",
        }
        for source_id in (
            "fred_macro_regime",
            "bls_labor_inflation",
            "cftc_multi_asset_positioning",
            "treasury_debt_to_penny",
        )
    ]
    statuses.append(
        {
            "source_id": "sec_filing_events",
            "authority": "us_securities_and_exchange_commission",
            "status": "failed_after_retries_or_parse",
            "required": False,
            "row_count": 0,
            "newest_observation": "",
            "url": "https://data.sec.gov/submissions/",
            "error": "HTTP 403 Request Rate Threshold Exceeded",
        }
    )
    output_root = tmp_path / "raw"
    manifest_path = tmp_path / "quant_context_manifest.json"
    manifest = write_quant_context_outputs(
        [dataset],
        statuses,
        output_root,
        manifest_path,
        FETCHED_AT,
        FETCHED_AT,
        "20260720T000000Z",
        200,
    )
    latest = output_root / "fred_macro_regime.csv"
    snapshot = output_root / "snapshots" / "20260720T000000Z" / "fred_macro_regime.csv"
    assert latest.read_bytes() == snapshot.read_bytes()
    assert manifest["files"][0]["sha256"] == hashlib.sha256(latest.read_bytes()).hexdigest()
    assert manifest["pipeline_status"] == "complete"
    assert manifest["credential_count"] == 0
    assert manifest["broker_authority"] is False
    assert manifest["order_authority"] is False
    assert manifest["paper_only"] is True
    assert manifest["live_blocked"] is True
    assert manifest["source_statuses"][-1]["status"] == "failed_after_retries_or_parse"
    assert manifest["decision_at"] == FETCHED_AT
    assert manifest["files"][0]["available_at"] == FETCHED_AT
    assert manifest["files"][0]["future_observation_rows_quarantined"] == 0
    assert manifest["future_observation_rows_quarantined_total"] == 0

    future_dataset = replace(dataset, available_at="2026-07-20T00:00:01+00:00")
    with pytest.raises(ValueError, match="dataset is not available at decision"):
        write_quant_context_outputs(
            [future_dataset],
            statuses,
            tmp_path / "future_raw",
            tmp_path / "future_manifest.json",
            FETCHED_AT,
            FETCHED_AT,
            "20260720T000000Z",
            200,
        )
    assert not (tmp_path / "future_raw").exists()

    policy = next(lane for lane in LANES if lane["lane_id"] == "quant_context_intake")
    assert policy["network"] is True
    assert policy["window"] == "after_close"
    assert "quant_context_intake" in SUBSUMED_BY_CLOSE
    assert LANE_EVIDENCE_CONTRACTS["quant_context_intake"]["required_status"] == "complete"
    command = _commands(tmp_path)["quant_context_intake"]
    assert command[-2:] == ["--sec-symbol-limit", "250"]
    assert datetime.fromisoformat(FETCHED_AT).astimezone(timezone.utc).isoformat() == FETCHED_AT
