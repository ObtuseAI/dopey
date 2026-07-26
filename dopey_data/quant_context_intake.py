"""Governed public-source quant context intake for paper research.

The collector uses credential-free official endpoints and immutable snapshots. It
does not expose broker, order, account, credential, or live-sizing surfaces.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, TypedDict
from urllib.parse import urljoin

import requests

from dopey_universe.universe_registry import active_universe, load_registry


INTAKE_VERSION = "dopey-quant-context-intake-v3"
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SEC_USER_AGENT_ENVIRONMENT_VARIABLE = "DOPEY_SEC_USER_AGENT"
GENERAL_USER_AGENT = "DOPEY-PaperResearch/1.0 (+https://github.com/ObtuseAI/dopey)"
SEC_FILINGS_FORMS = frozenset(
    {
        "4",
        "8-K",
        "8-K/A",
        "10-K",
        "10-K/A",
        "10-Q",
        "10-Q/A",
        "13F-HR",
        "13F-HR/A",
        "144",
        "424B3",
        "424B5",
        "DEF 14A",
        "S-3",
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
    }
)
FRED_SERIES: tuple[tuple[str, str], ...] = (
    ("DFF", "effective_federal_funds_rate"),
    ("SOFR", "secured_overnight_financing_rate"),
    ("IORB", "interest_on_reserve_balances"),
    ("RRPONTSYD", "overnight_reverse_repo_awards"),
    ("WALCL", "federal_reserve_total_assets"),
    ("WTREGEN", "treasury_general_account"),
    ("DGS2", "treasury_two_year"),
    ("DGS10", "treasury_ten_year"),
    ("DGS30", "treasury_thirty_year"),
    ("T10Y2Y", "ten_year_two_year_spread"),
    ("T10Y3M", "ten_year_three_month_spread"),
    ("BAMLC0A0CM", "investment_grade_option_adjusted_spread"),
    ("BAMLH0A0HYM2", "high_yield_option_adjusted_spread"),
    ("NFCI", "chicago_fed_national_financial_conditions"),
    ("STLFSI4", "st_louis_fed_financial_stress"),
    ("UNRATE", "unemployment_rate"),
    ("PAYEMS", "total_nonfarm_payrolls"),
    ("CPIAUCSL", "consumer_price_index"),
    ("INDPRO", "industrial_production"),
    ("RSAFS", "retail_sales"),
    ("HOUST", "housing_starts"),
    ("ICSA", "initial_unemployment_claims"),
    ("M2SL", "m2_money_stock"),
)
BLS_SERIES: tuple[tuple[str, str], ...] = (
    ("CUUR0000SA0", "consumer_price_index_all_items"),
    ("CUUR0000SA0L1E", "consumer_price_index_core"),
    ("CES0000000001", "total_nonfarm_payrolls"),
    ("CES0500000003", "average_hourly_earnings_private"),
    ("LNS14000000", "unemployment_rate"),
    ("LNS11300000", "labor_force_participation_rate"),
    ("JTS000000000000000JOL", "job_openings"),
    ("WPUFD4", "producer_price_final_demand"),
)
CFTC_MARKET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ES", "E-MINI S&P 500"),
    ("NQ", "NASDAQ-100"),
    ("RTY", "RUSSELL"),
    ("VIX", "VIX"),
    ("ZN", "10-YEAR U.S. TREASURY"),
    ("ZB", "U.S. TREASURY BONDS"),
    ("DXY", "U.S. DOLLAR INDEX"),
    ("EURUSD", "EURO FX"),
    ("USDJPY", "JAPANESE YEN"),
    ("CL", "CRUDE OIL, LIGHT SWEET"),
    ("BZ", "BRENT"),
    ("NG", "NATURAL GAS"),
    ("GC", "GOLD"),
    ("SI", "SILVER"),
    ("HG", "COPPER"),
    ("BTC", "BITCOIN"),
    ("ETH", "ETHER"),
)
REQUIRED_SOURCE_IDS = frozenset(
    {
        "fred_macro_regime",
        "bls_labor_inflation",
        "cftc_multi_asset_positioning",
        "treasury_debt_to_penny",
    }
)
SUPPLEMENTAL_SOURCE_IDS = frozenset(
    {"sec_filing_events", "sec_fails_to_deliver", "cboe_options_market_stats"}
)


class HttpSourceError(RuntimeError):
    """Raised when an official source exhausts its bounded retry policy."""


class SourceStatus(TypedDict):
    source_id: str
    authority: str
    status: str
    required: bool
    row_count: int
    newest_observation: str
    url: str
    error: str


@dataclass(frozen=True)
class Dataset:
    source_id: str
    filename: str
    content: bytes
    row_count: int
    newest_observation: str
    url: str
    authority: str
    semantics: str
    redistribution_allowed: bool
    available_at: str
    future_observation_rows_quarantined: int


@dataclass(frozen=True)
class HttpPayload:
    url: str
    content: bytes
    retrieved_at: str


class HttpClient:
    """Rate-limited connector for public HTTP sources."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: int,
        maximum_attempts: int,
        minimum_interval_seconds: float,
    ) -> None:
        self._session = requests.Session()
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._maximum_attempts = maximum_attempts
        self._minimum_interval_seconds = minimum_interval_seconds
        self._last_request_monotonic = 0.0

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self._minimum_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get(self, url: str, params: dict[str, str] | None) -> HttpPayload:
        last_error: Exception | None = None
        for attempt in range(1, self._maximum_attempts + 1):
            self._pace()
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"},
                    timeout=self._timeout_seconds,
                )
                self._last_request_monotonic = time.monotonic()
                if response.status_code != 200:
                    body = response.text[:500].replace("\n", " ")
                    raise HttpSourceError(
                        f"HTTP GET failed: url={response.url} status={response.status_code} body={body}"
                    )
                if not response.content:
                    raise HttpSourceError(f"HTTP GET returned empty content: url={response.url}")
                return HttpPayload(
                    url=str(response.url),
                    content=response.content,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                )
            except (requests.RequestException, HttpSourceError) as error:
                last_error = error
                print(
                    json.dumps(
                        {
                            "warning": "quant_context_source_attempt_failed",
                            "method": "GET",
                            "url": url,
                            "attempt": attempt,
                            "maximum_attempts": self._maximum_attempts,
                            "error": str(error),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                if attempt < self._maximum_attempts:
                    time.sleep(float(attempt * 2))
        raise HttpSourceError(
            f"HTTP GET exhausted retries: url={url} attempts={self._maximum_attempts} error={last_error}"
        ) from last_error

    def post_json(self, url: str, payload: dict[str, Any]) -> HttpPayload:
        last_error: Exception | None = None
        for attempt in range(1, self._maximum_attempts + 1):
            self._pace()
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    headers={"User-Agent": self._user_agent, "Content-Type": "application/json"},
                    timeout=self._timeout_seconds,
                )
                self._last_request_monotonic = time.monotonic()
                if response.status_code != 200:
                    body = response.text[:500].replace("\n", " ")
                    raise HttpSourceError(
                        f"HTTP POST failed: url={response.url} status={response.status_code} body={body}"
                    )
                if not response.content:
                    raise HttpSourceError(f"HTTP POST returned empty content: url={response.url}")
                return HttpPayload(
                    url=str(response.url),
                    content=response.content,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                )
            except (requests.RequestException, HttpSourceError) as error:
                last_error = error
                print(
                    json.dumps(
                        {
                            "warning": "quant_context_source_attempt_failed",
                            "method": "POST",
                            "url": url,
                            "attempt": attempt,
                            "maximum_attempts": self._maximum_attempts,
                            "error": str(error),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                if attempt < self._maximum_attempts:
                    time.sleep(float(attempt * 2))
        raise HttpSourceError(
            f"HTTP POST exhausted retries: url={url} attempts={self._maximum_attempts} error={last_error}"
        ) from last_error


def validate_sec_user_agent(value: str | None) -> str:
    """Require the operator-declared organization and email expected by SEC."""
    normalized = "" if value is None else " ".join(value.split())
    if not normalized or "@" not in normalized or " " not in normalized:
        raise ValueError(
            "SEC automated access identity is missing or invalid: "
            f"set {SEC_USER_AGENT_ENVIRONMENT_VARIABLE} to "
            "'Organization Name contact@example.com'"
        )
    return normalized


def require_sec_client(client: HttpClient | None) -> HttpClient:
    """Stop SEC collection when the operator has not declared an identity."""
    if client is None:
        raise ValueError(
            "SEC collection is disabled until an authentic automated-access identity is configured: "
            f"environment_variable={SEC_USER_AGENT_ENVIRONMENT_VARIABLE}"
        )
    return client


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self.links.append(href)


class TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def _csv_bytes(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _json_object(content: bytes, source_id: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"source returned invalid JSON: source_id={source_id} error={error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"source JSON root must be an object: source_id={source_id}")
    return parsed


def _parse_float(value: Any, field: str, source_id: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"numeric field is invalid: source_id={source_id} field={field} value={value!r}"
        ) from error
    if not math.isfinite(parsed):
        raise ValueError(
            f"numeric field is non-finite: source_id={source_id} field={field} value={value!r}"
        )
    return parsed


def _parse_aware_timestamp(value: str, field: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"timestamp is invalid: field={field} value={value!r}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: field={field} value={value!r}")
    return parsed.astimezone(timezone.utc)


def validate_dataset_availability(datasets: list[Dataset], decision_at: str) -> None:
    """Reject a snapshot containing data retrieved after its decision boundary."""
    decision_time = _parse_aware_timestamp(decision_at, "decision_at")
    for dataset in datasets:
        available_time = _parse_aware_timestamp(
            dataset.available_at,
            f"datasets[{dataset.source_id}].available_at",
        )
        if available_time > decision_time:
            raise ValueError(
                "dataset is not available at decision: "
                f"source_id={dataset.source_id} available_at={dataset.available_at} "
                f"decision_at={decision_at}"
            )


def parse_fred_series(
    content: bytes,
    series_id: str,
    series_name: str,
    fetched_at: str,
    maximum_observation_date: date,
) -> tuple[list[tuple[str, ...]], int]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or len(reader.fieldnames) < 2:
        raise ValueError(f"FRED CSV schema is invalid: series_id={series_id} fields={reader.fieldnames}")
    date_field = reader.fieldnames[0]
    value_field = series_id if series_id in reader.fieldnames else reader.fieldnames[1]
    rows: list[tuple[str, ...]] = []
    future_observation_count = 0
    for record in reader:
        observation_date = str(record.get(date_field, "")).strip()
        value = str(record.get(value_field, "")).strip()
        if not observation_date or value in {"", "."}:
            continue
        try:
            parsed_observation_date = date.fromisoformat(observation_date)
        except ValueError as error:
            raise ValueError(
                "FRED observation date is invalid: "
                f"series_id={series_id} observation_date={observation_date!r}"
            ) from error
        if parsed_observation_date > maximum_observation_date:
            future_observation_count += 1
            continue
        _parse_float(value, value_field, "fred_macro_regime")
        rows.append((observation_date, series_id, series_name, value, fetched_at, "latest_revised_snapshot"))
    if not rows:
        raise ValueError(f"FRED CSV produced zero observations: series_id={series_id}")
    return rows, future_observation_count


def collect_fred_macro_regime(client: HttpClient, today: date) -> Dataset:
    rows: list[tuple[str, ...]] = []
    retrieved_at_values: list[str] = []
    future_observation_rows_quarantined = 0
    source_url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    history_start = today.replace(year=today.year - 20).isoformat()
    for series_id, series_name in FRED_SERIES:
        payload = client.get(source_url, {"id": series_id, "cosd": history_start})
        retrieved_at_values.append(payload.retrieved_at)
        series_rows, future_count = parse_fred_series(
            payload.content,
            series_id,
            series_name,
            payload.retrieved_at,
            today,
        )
        rows.extend(series_rows)
        future_observation_rows_quarantined += future_count
    rows.sort(key=lambda row: (row[0], row[1]))
    newest = max(row[0] for row in rows)
    return Dataset(
        source_id="fred_macro_regime",
        filename="fred_macro_regime.csv",
        content=_csv_bytes(
            ("observation_date", "series_id", "series_name", "value", "fetched_at", "revision_semantics"),
            rows,
        ),
        row_count=len(rows),
        newest_observation=newest,
        url=source_url,
        authority="federal_reserve_bank_of_st_louis",
        semantics=(
            "latest revised values; prospective snapshots prevent future look-ahead but are not ALFRED "
            "vintages; rows dated after the decision date are quarantined"
        ),
        redistribution_allowed=True,
        available_at=max(retrieved_at_values),
        future_observation_rows_quarantined=future_observation_rows_quarantined,
    )


def parse_bls_payload(content: bytes, series_names: dict[str, str], fetched_at: str) -> list[tuple[str, ...]]:
    payload = _json_object(content, "bls_labor_inflation")
    status = str(payload.get("status", ""))
    if status != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS request failed: status={status} message={payload.get('message')}")
    results = payload.get("Results")
    series_records = results.get("series") if isinstance(results, dict) else None
    if not isinstance(series_records, list):
        raise ValueError("BLS response is missing Results.series")
    rows: list[tuple[str, ...]] = []
    returned_ids: set[str] = set()
    for series_record in series_records:
        if not isinstance(series_record, dict):
            continue
        series_id = str(series_record.get("seriesID", ""))
        if series_id not in series_names:
            continue
        returned_ids.add(series_id)
        observations = series_record.get("data")
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            period = str(observation.get("period", ""))
            if period == "M13":
                continue
            value = str(observation.get("value", "")).strip()
            if value in {"", ".", "-"}:
                continue
            _parse_float(value, "value", "bls_labor_inflation")
            footnotes = observation.get("footnotes")
            footnote_text = " | ".join(
                str(item.get("text", ""))
                for item in footnotes
                if isinstance(item, dict) and item.get("text")
            ) if isinstance(footnotes, list) else ""
            rows.append(
                (
                    series_id,
                    series_names[series_id],
                    str(observation.get("year", "")),
                    period,
                    str(observation.get("periodName", "")),
                    value,
                    footnote_text,
                    fetched_at,
                    "published_snapshot",
                )
            )
    missing = sorted(set(series_names) - returned_ids)
    if missing:
        raise ValueError(f"BLS response omitted required series: missing={missing}")
    if not rows:
        raise ValueError("BLS response produced zero observations")
    return rows


def collect_bls_labor_inflation(client: HttpClient, today: date) -> Dataset:
    source_url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    series_names = dict(BLS_SERIES)
    request = {
        "seriesid": list(series_names),
        "startyear": str(today.year - 3),
        "endyear": str(today.year),
    }
    payload = client.post_json(source_url, request)
    rows = parse_bls_payload(payload.content, series_names, payload.retrieved_at)
    rows.sort(key=lambda row: (row[0], row[2], row[3]))
    newest = max(f"{row[2]}-{row[3]}" for row in rows)
    return Dataset(
        source_id="bls_labor_inflation",
        filename="bls_labor_inflation.csv",
        content=_csv_bytes(
            (
                "series_id",
                "series_name",
                "year",
                "period",
                "period_name",
                "value",
                "footnotes",
                "fetched_at",
                "vintage_semantics",
            ),
            rows,
        ),
        row_count=len(rows),
        newest_observation=newest,
        url=payload.url,
        authority="us_bureau_of_labor_statistics",
        semantics="published BLS observations snapshotted at fetch time; not a reconstructed release-vintage history",
        redistribution_allowed=True,
        available_at=payload.retrieved_at,
        future_observation_rows_quarantined=0,
    )


def _cftc_alias(market_name: str) -> str:
    upper_name = market_name.upper()
    for alias, pattern in CFTC_MARKET_PATTERNS:
        if pattern in upper_name:
            return alias
    return ""


def parse_cftc_payload(content: bytes, fetched_at: str) -> list[tuple[str, ...]]:
    try:
        parsed = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"CFTC response is invalid JSON: error={error}") from error
    if not isinstance(parsed, list):
        raise ValueError("CFTC response root must be an array")
    rows: list[tuple[str, ...]] = []
    for record in parsed:
        if not isinstance(record, dict):
            continue
        market_name = str(record.get("market_and_exchange_names", ""))
        alias = _cftc_alias(market_name)
        if not alias:
            continue
        long_positions = _parse_float(
            record.get("noncomm_positions_long_all"),
            "noncomm_positions_long_all",
            "cftc_multi_asset_positioning",
        )
        short_positions = _parse_float(
            record.get("noncomm_positions_short_all"),
            "noncomm_positions_short_all",
            "cftc_multi_asset_positioning",
        )
        open_interest = _parse_float(
            record.get("open_interest_all"),
            "open_interest_all",
            "cftc_multi_asset_positioning",
        )
        report_date = str(record.get("report_date_as_yyyy_mm_dd", ""))[:10]
        if not report_date:
            continue
        rows.append(
            (
                report_date,
                alias,
                market_name,
                f"{long_positions:.0f}",
                f"{short_positions:.0f}",
                f"{long_positions - short_positions:.0f}",
                f"{open_interest:.0f}",
                fetched_at,
            )
        )
    represented_aliases = {row[1] for row in rows}
    coverage_floor = 12
    if len(represented_aliases) < coverage_floor:
        raise ValueError(
            "CFTC multi-asset coverage floor failed: "
            f"represented={sorted(represented_aliases)} required_count={coverage_floor}"
        )
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return rows


def collect_cftc_multi_asset_positioning(client: HttpClient, today: date) -> Dataset:
    source_url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    earliest = (today - timedelta(days=800)).isoformat()
    params = {
        "$limit": "50000",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$where": f"report_date_as_yyyy_mm_dd >= '{earliest}T00:00:00.000'",
    }
    payload = client.get(source_url, params)
    rows = parse_cftc_payload(payload.content, payload.retrieved_at)
    return Dataset(
        source_id="cftc_multi_asset_positioning",
        filename="cftc_multi_asset_positioning.csv",
        content=_csv_bytes(
            (
                "report_date",
                "asset_alias",
                "market_and_exchange",
                "noncommercial_long",
                "noncommercial_short",
                "noncommercial_net",
                "open_interest",
                "fetched_at",
            ),
            rows,
        ),
        row_count=len(rows),
        newest_observation=max(row[0] for row in rows),
        url=payload.url,
        authority="us_commodity_futures_trading_commission",
        semantics="weekly reportable-position snapshot; not full market positioning and not a trade signal",
        redistribution_allowed=True,
        available_at=payload.retrieved_at,
        future_observation_rows_quarantined=0,
    )


def parse_treasury_debt_payload(content: bytes, fetched_at: str) -> list[tuple[str, ...]]:
    payload = _json_object(content, "treasury_debt_to_penny")
    records = payload.get("data")
    if not isinstance(records, list):
        raise ValueError("Treasury FiscalData response is missing data array")
    rows: list[tuple[str, ...]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        record_date = str(record.get("record_date", ""))
        public = str(record.get("debt_held_public_amt", ""))
        intragovernmental = str(record.get("intragov_hold_amt", ""))
        total = str(record.get("tot_pub_debt_out_amt", ""))
        if not record_date:
            continue
        _parse_float(public, "debt_held_public_amt", "treasury_debt_to_penny")
        _parse_float(intragovernmental, "intragov_hold_amt", "treasury_debt_to_penny")
        _parse_float(total, "tot_pub_debt_out_amt", "treasury_debt_to_penny")
        rows.append((record_date, public, intragovernmental, total, fetched_at))
    if not rows:
        raise ValueError("Treasury FiscalData response produced zero rows")
    rows.sort(key=lambda row: row[0])
    return rows


def collect_treasury_debt_to_penny(client: HttpClient) -> Dataset:
    source_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
    payload = client.get(source_url, {"sort": "-record_date", "page[size]": "400"})
    rows = parse_treasury_debt_payload(payload.content, payload.retrieved_at)
    return Dataset(
        source_id="treasury_debt_to_penny",
        filename="treasury_debt_to_penny.csv",
        content=_csv_bytes(
            (
                "record_date",
                "debt_held_by_public",
                "intragovernmental_holdings",
                "total_public_debt",
                "fetched_at",
            ),
            rows,
        ),
        row_count=len(rows),
        newest_observation=max(row[0] for row in rows),
        url=payload.url,
        authority="us_treasury_bureau_of_the_fiscal_service",
        semantics="daily fiscal stock measure; contextual liquidity/fiscal input, not causal edge evidence",
        redistribution_allowed=True,
        available_at=payload.retrieved_at,
        future_observation_rows_quarantined=0,
    )


def parse_sec_company_tickers(content: bytes, active_symbols: tuple[str, ...]) -> list[tuple[str, str, str]]:
    payload = _json_object(content, "sec_filing_events")
    active = {symbol.upper() for symbol in active_symbols}
    matches: dict[str, tuple[str, str, str]] = {}
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        ticker = str(record.get("ticker", "")).upper()
        cik_raw = record.get("cik_str")
        if ticker not in active or not isinstance(cik_raw, int):
            continue
        matches[ticker] = (ticker, f"{cik_raw:010d}", str(record.get("title", "")))
    return [matches[symbol] for symbol in sorted(matches)]


def parse_sec_submissions(
    content: bytes,
    ticker: str,
    cik: str,
    fetched_at: str,
    earliest_filing_date: date,
) -> list[tuple[str, ...]]:
    payload = _json_object(content, "sec_filing_events")
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        raise ValueError(f"SEC submissions response is missing filings.recent: ticker={ticker} cik={cik}")
    required_columns = ("accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "primaryDocument")
    columns: dict[str, list[Any]] = {}
    for column in required_columns:
        values = recent.get(column)
        if not isinstance(values, list):
            raise ValueError(f"SEC submissions column is missing: ticker={ticker} column={column}")
        columns[column] = values
    row_count = min(len(values) for values in columns.values())
    rows: list[tuple[str, ...]] = []
    for index in range(row_count):
        filing_date = str(columns["filingDate"][index])
        form = str(columns["form"][index])
        if filing_date < earliest_filing_date.isoformat() or form not in SEC_FILINGS_FORMS:
            continue
        accession = str(columns["accessionNumber"][index])
        primary_document = str(columns["primaryDocument"][index])
        accession_compact = accession.replace("-", "")
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_compact}/{primary_document}"
        )
        rows.append(
            (
                filing_date,
                str(columns["acceptanceDateTime"][index]),
                str(columns["reportDate"][index]),
                ticker,
                cik,
                form,
                accession,
                primary_document,
                filing_url,
                fetched_at,
            )
        )
    return rows


def collect_sec_filing_events(
    client: HttpClient,
    today: date,
    active_symbols: tuple[str, ...],
    symbol_limit: int,
) -> Dataset:
    if symbol_limit <= 0:
        raise ValueError(f"SEC symbol limit must be positive: actual={symbol_limit}")
    tickers_url = "https://www.sec.gov/files/company_tickers.json"
    tickers_payload = client.get(tickers_url, None)
    companies = parse_sec_company_tickers(tickers_payload.content, active_symbols)
    selected = companies[:symbol_limit]
    if not selected:
        raise ValueError("SEC ticker mapping matched zero active-universe symbols")
    earliest = today - timedelta(days=730)
    rows: list[tuple[str, ...]] = []
    retrieved_at_values = [tickers_payload.retrieved_at]
    for ticker, cik, _title in selected:
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        payload = client.get(submissions_url, None)
        retrieved_at_values.append(payload.retrieved_at)
        rows.extend(parse_sec_submissions(payload.content, ticker, cik, payload.retrieved_at, earliest))
    if not rows:
        raise ValueError(
            f"SEC submissions produced zero selected filing events: selected_symbol_count={len(selected)}"
        )
    unique_rows = sorted(set(rows), key=lambda row: (row[0], row[3], row[6]))
    return Dataset(
        source_id="sec_filing_events",
        filename="sec_filing_events.csv",
        content=_csv_bytes(
            (
                "filing_date",
                "accepted_at",
                "report_date",
                "ticker",
                "cik",
                "form",
                "accession_number",
                "primary_document",
                "filing_url",
                "fetched_at",
            ),
            unique_rows,
        ),
        row_count=len(unique_rows),
        newest_observation=max(row[0] for row in unique_rows),
        url=tickers_url,
        authority="us_securities_and_exchange_commission",
        semantics=(
            f"official filing metadata for {len(selected)} mapped active symbols; forms are event context, "
            "accepted_at is an EDGAR event timestamp rather than proof of public availability; "
            "fetched_at is the response-completion availability proof"
        ),
        redistribution_allowed=True,
        available_at=max(retrieved_at_values),
        future_observation_rows_quarantined=0,
    )


def parse_sec_ftd_archive(content: bytes, archive_url: str, active_symbols: tuple[str, ...], fetched_at: str) -> list[tuple[str, ...]]:
    active = {symbol.upper() for symbol in active_symbols}
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise ValueError(f"SEC FTD archive is invalid: url={archive_url}") from error
    names = [name for name in archive.namelist() if not name.endswith("/")]
    if len(names) != 1:
        raise ValueError(f"SEC FTD archive must contain one data file: url={archive_url} names={names}")
    text = archive.read(names[0]).decode("latin-1")
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    rows: list[tuple[str, ...]] = []
    for record in reader:
        symbol = str(record.get("SYMBOL", "")).upper().strip()
        if symbol not in active:
            continue
        quantity = str(record.get("QUANTITY (FAILS)", "")).strip()
        if not quantity.isdigit():
            raise ValueError(f"SEC FTD quantity is invalid: symbol={symbol} value={quantity!r}")
        rows.append(
            (
                str(record.get("SETTLEMENT DATE", "")).strip(),
                str(record.get("CUSIP", "")).strip(),
                symbol,
                quantity,
                str(record.get("DESCRIPTION", "")).strip(),
                str(record.get("PRICE", "")).strip(),
                archive_url,
                fetched_at,
            )
        )
    return rows


def collect_sec_fails_to_deliver(
    client: HttpClient,
    active_symbols: tuple[str, ...],
) -> Dataset:
    source_url = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
    page = client.get(source_url, None)
    parser = LinkCollector()
    parser.feed(page.content.decode("utf-8", errors="strict"))
    archive_urls = sorted(
        {
            urljoin(source_url, link)
            for link in parser.links
            if re.search(r"cnsfails\d{6}[ab]\.zip$", link, re.IGNORECASE)
        },
        reverse=True,
    )[:2]
    if not archive_urls:
        raise ValueError("SEC FTD index exposed zero current archive links")
    rows: list[tuple[str, ...]] = []
    retrieved_at_values = [page.retrieved_at]
    for archive_url in archive_urls:
        archive_payload = client.get(archive_url, None)
        retrieved_at_values.append(archive_payload.retrieved_at)
        rows.extend(
            parse_sec_ftd_archive(
                archive_payload.content,
                archive_url,
                active_symbols,
                archive_payload.retrieved_at,
            )
        )
    if not rows:
        raise ValueError("SEC FTD archives contained zero active-universe rows")
    unique_rows = sorted(set(rows), key=lambda row: (row[0], row[2], row[1]))
    return Dataset(
        source_id="sec_fails_to_deliver",
        filename="sec_fails_to_deliver.csv",
        content=_csv_bytes(
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
            unique_rows,
        ),
        row_count=len(unique_rows),
        newest_observation=max(row[0] for row in unique_rows),
        url=source_url,
        authority="us_securities_and_exchange_commission",
        semantics=(
            "aggregate settlement-date balance; includes long-sale and short-sale fails, is not daily flow, "
            "and is not evidence of abusive or naked short selling"
        ),
        redistribution_allowed=True,
        available_at=max(retrieved_at_values),
        future_observation_rows_quarantined=0,
    )


def parse_cboe_market_stats(content: bytes, fetched_at: str) -> list[tuple[str, ...]]:
    parser = TextCollector()
    parser.feed(content.decode("utf-8", errors="strict"))
    text = " ".join(parser.parts)
    labels = (
        "TOTAL PUT/CALL RATIO",
        "INDEX PUT/CALL RATIO",
        "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO",
        "EQUITY PUT/CALL RATIO",
        "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO",
        "SPX + SPXW PUT/CALL RATIO",
    )
    rows: list[tuple[str, ...]] = []
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s+([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        if match is None:
            raise ValueError(f"Cboe daily statistics omitted required metric: metric={label}")
        value = match.group(1)
        _parse_float(value, label, "cboe_options_market_stats")
        rows.append((label.lower().replace(" ", "_").replace("/", "_"), value, fetched_at, "current_page_at_fetch"))
    return rows


def collect_cboe_options_market_stats(client: HttpClient) -> Dataset:
    source_url = "https://www.cboe.com/markets/us/options/market-statistics/daily"
    payload = client.get(source_url, None)
    rows = parse_cboe_market_stats(payload.content, payload.retrieved_at)
    return Dataset(
        source_id="cboe_options_market_stats",
        filename="cboe_options_market_stats.csv",
        content=_csv_bytes(("metric", "value", "fetched_at", "observation_semantics"), rows),
        row_count=len(rows),
        newest_observation=payload.retrieved_at,
        url=source_url,
        authority="cboe_exchange",
        semantics="aggregate exchange statistics, not consolidated customer flow or dealer gamma exposure",
        redistribution_allowed=False,
        available_at=payload.retrieved_at,
        future_observation_rows_quarantined=0,
    )


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _manifest_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _source_status(dataset: Dataset, required: bool) -> SourceStatus:
    return {
        "source_id": dataset.source_id,
        "authority": dataset.authority,
        "status": "staged",
        "required": required,
        "row_count": dataset.row_count,
        "newest_observation": dataset.newest_observation,
        "url": dataset.url,
        "error": "",
    }


def _failed_status(source_id: str, required: bool, url: str, error: Exception) -> SourceStatus:
    return {
        "source_id": source_id,
        "authority": "official_or_exchange_public_source",
        "status": "failed_after_retries_or_parse",
        "required": required,
        "row_count": 0,
        "newest_observation": "",
        "url": url,
        "error": str(error),
    }


def _manifest_status(statuses: list[SourceStatus]) -> str:
    staged_required = {
        status["source_id"]
        for status in statuses
        if status["required"] and status["status"] == "staged"
    }
    if staged_required == REQUIRED_SOURCE_IDS:
        return "complete"
    return "partial_explicit_source_failures"


def write_quant_context_outputs(
    datasets: list[Dataset],
    statuses: list[SourceStatus],
    output_root: Path,
    manifest_path: Path,
    fetched_at: str,
    decision_at: str,
    run_stamp: str,
    active_symbol_count: int,
) -> dict[str, Any]:
    validate_dataset_availability(datasets, decision_at)
    snapshot_root = output_root / "snapshots" / run_stamp
    files: list[dict[str, Any]] = []
    for dataset in datasets:
        latest_path = output_root / dataset.filename
        snapshot_path = snapshot_root / dataset.filename
        _write_atomic(latest_path, dataset.content)
        _write_atomic(snapshot_path, dataset.content)
        files.append(
            {
                "source_id": dataset.source_id,
                "latest_path": _manifest_path(latest_path),
                "snapshot_path": _manifest_path(snapshot_path),
                "sha256": hashlib.sha256(dataset.content).hexdigest(),
                "row_count": dataset.row_count,
                "newest_observation": dataset.newest_observation,
                "available_at": dataset.available_at,
                "future_observation_rows_quarantined": dataset.future_observation_rows_quarantined,
                "semantics": dataset.semantics,
                "redistribution_allowed": dataset.redistribution_allowed,
            }
        )
    pipeline_status = _manifest_status(statuses)
    manifest: dict[str, Any] = {
        "artifact_type": "quant_context_intake_manifest",
        "intake_version": INTAKE_VERSION,
        "created_at": fetched_at,
        "decision_at": decision_at,
        "pipeline_status": pipeline_status,
        "required_source_ids": sorted(REQUIRED_SOURCE_IDS),
        "supplemental_source_ids": sorted(SUPPLEMENTAL_SOURCE_IDS),
        "source_statuses": statuses,
        "files": files,
        "future_observation_rows_quarantined_total": sum(
            dataset.future_observation_rows_quarantined for dataset in datasets
        ),
        "active_symbol_count": active_symbol_count,
        "credential_count": 0,
        "broker_authority": False,
        "order_authority": False,
        "paper_only": True,
        "live_blocked": True,
        "point_in_time_notice": (
            "Every file is an immutable prospective fetch snapshot. available_at is the official-source HTTP "
            "response completion time, and every dataset is rejected unless available_at <= decision_at. SEC "
            "accepted_at is not treated as public availability because SEC documents may disseminate later. "
            "Rows whose observation date is after the decision date are quarantined rather than treated as "
            "current features. "
            "Historical FRED and BLS observations may contain revisions and must not be represented as "
            "reconstructed release vintages."
        ),
        "license_notice": (
            "Government-source records retain source provenance. Cboe summary statistics are internal research "
            "only and are not redistribution-cleared."
        ),
        "completion_semantics": (
            "complete means every credential-free required government source staged. Supplemental SEC and "
            "exchange failures remain explicit and never become synthetic or carried-forward fresh data."
        ),
    }
    manifest_content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_atomic(manifest_path, manifest_content)
    _write_atomic(snapshot_root / "quant_context_manifest.json", manifest_content)
    return manifest


def run_quant_context_intake(
    output_root: Path,
    manifest_path: Path,
    sec_symbol_limit: int,
    now_utc: datetime,
    sec_user_agent: str | None,
) -> dict[str, Any]:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    fetched_at = now_utc.astimezone(timezone.utc).isoformat()
    run_stamp = now_utc.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    today = now_utc.astimezone(timezone.utc).date()
    symbols = active_universe(load_registry())
    general_client = HttpClient(GENERAL_USER_AGENT, 45, 3, 0.2)
    try:
        validated_sec_user_agent = validate_sec_user_agent(sec_user_agent)
    except ValueError:
        sec_client = None
    else:
        sec_client = HttpClient(validated_sec_user_agent, 45, 3, 0.15)
    collectors: tuple[tuple[str, str, bool, Callable[[], Dataset]], ...] = (
        (
            "fred_macro_regime",
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            True,
            lambda: collect_fred_macro_regime(general_client, today),
        ),
        (
            "bls_labor_inflation",
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            True,
            lambda: collect_bls_labor_inflation(general_client, today),
        ),
        (
            "cftc_multi_asset_positioning",
            "https://publicreporting.cftc.gov/resource/6dca-aqww.json",
            True,
            lambda: collect_cftc_multi_asset_positioning(general_client, today),
        ),
        (
            "treasury_debt_to_penny",
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
            True,
            lambda: collect_treasury_debt_to_penny(general_client),
        ),
        (
            "sec_filing_events",
            "https://data.sec.gov/submissions/",
            False,
            lambda: collect_sec_filing_events(
                require_sec_client(sec_client),
                today,
                symbols,
                sec_symbol_limit,
            ),
        ),
        (
            "sec_fails_to_deliver",
            "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data",
            False,
            lambda: collect_sec_fails_to_deliver(require_sec_client(sec_client), symbols),
        ),
        (
            "cboe_options_market_stats",
            "https://www.cboe.com/markets/us/options/market-statistics/daily",
            False,
            lambda: collect_cboe_options_market_stats(general_client),
        ),
    )
    datasets: list[Dataset] = []
    statuses: list[SourceStatus] = []
    for source_id, url, required, collector in collectors:
        try:
            dataset = collector()
        except (HttpSourceError, ValueError, zipfile.BadZipFile) as error:
            statuses.append(_failed_status(source_id, required, url, error))
            continue
        datasets.append(dataset)
        statuses.append(_source_status(dataset, required))
    decision_at = datetime.now(timezone.utc).isoformat()
    manifest = write_quant_context_outputs(
        datasets,
        statuses,
        output_root,
        manifest_path,
        fetched_at,
        decision_at,
        run_stamp,
        len(symbols),
    )
    return manifest
