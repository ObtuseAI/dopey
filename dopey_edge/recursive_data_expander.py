"""Dopey recursive data expander: discover+score candidate data sources (no network calls).

DOPEY-native stub. Borrows the Dummy "recursive data expansion" doctrine. Returns candidate
data-source entries with planned use. NO network calls in the first pass; OpenBB, Alpaca
options, Tradier options, SEC filings, yfinance research-only, Robinhood MCP account/tool
discovery, CBOE/OPRA-style licensed placeholder, earnings calendar, macro calendar, VIX/VVIX,
realized vol, and unusual options activity are recorded as ledger stubs only.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class DataCandidate:
    source_id: str
    kind: str
    planned_use: str
    licensed: bool
    research_only: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


_CANDIDATES = [
    ("openbb", "Data", "Terminal aggregation of market data for research", True),
    ("alpaca_options", "Data", "Options chain + paper/sandbox fills", False),
    ("tradier_options", "Data", "Options chain + paper/sandbox fills", False),
    ("sec_filings", "Data", "Fundamental / event research from SEC EDGAR", False),
    ("yfinance_research", "Data", "Research-only price/option snapshots (rate-limited, no exec)", False),
    ("robinhood_mcp", "MCP/tooling", "Account + tool discovery only; no order placement in first pass", False),
    ("cboe_opra_placeholder", "Data", "Licensed options OPRA feed placeholder (requires license)", True),
    ("earnings_calendar", "Data", "Earnings event timing for event-driven research", False),
    ("macro_calendar", "Data", "Macro event timing for regime classification", False),
    ("vix_vvix", "Data", "Volatility-regime indicators for research", False),
    ("realized_vol", "Data", "Realized vol series for IV premium / edge research", False),
    ("unusual_options_activity", "Data", "Unusual options activity signals (if legally/licensed available)", True),
]


def expand_data_candidates() -> list[DataCandidate]:
    """Return the planned candidate data-source ledger. No network calls."""
    return [DataCandidate(sid, kind, use, lic, True) for sid, kind, use, lic in _CANDIDATES]
