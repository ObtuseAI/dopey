# DOPEY OSS IMPORT LEDGER

This ledger records candidate external/OSS sources and their **planned use** in DOPEY. In the
first pass **nothing is vendored**; these are research-discovery candidates only. Each entry is
evaluated through the `dopey_oss_miner` quarantine/license/trust pipeline before any future use.

| Candidate | Category | Planned use | Status |
|---|---|---|---|
| OpenBB | Data | Terminal aggregation of market data for research | not vendored |
| Alpaca options SDK | Execution/broker | Paper/sandbox options fills + chain | not vendored |
| Tradier options API | Execution/broker | Paper/sandbox options fills + chain | not vendored |
| yfinance | Data | Research-only price/option snapshots (rate-limited, no exec) | not vendored |
| SEC EDGAR tools | Data | Fundamental / event research from SEC filings | not vendored |
| Robinhood MCP | MCP/tooling | Account + tool discovery only; no order placement | not vendored |
| CBOE/OPRA-style feeds | Data | Licensed options OPRA feed placeholder (requires license) | not vendored |
| earnings-calendars libs | Data | Earnings event timing for event-driven research | not vendored |
| macro-calendar libs | Data | Macro event timing for regime classification | not vendored |
| VIX/VVIX data | Data | Volatility-regime indicators for research | not vendored |
| realized-vol tools | Data | Realized vol series for IV premium / edge research | not vendored |
| unusual-options-activity | Data | Unusual options activity signals (if legally/licensed available) | not vendored |
| backtesting.py / vectorbt | Trading/backtesting | Walk-forward / tournament backtest substrate | not vendored |
| QuantLib / py_vollib | Options math/research | Greeks / IV / model calibration research | not vendored |
| pyfolio / empyrical | Portfolio/risk | Performance + risk analytics for paper | not vendored |
| robin-stocks (private API) | Execution/broker | **REJECTED** — unofficial private API, forbidden | rejected |

## Promotion criteria (none auto-vendored)
Any future vendoring requires: license compatibility (`dopey_oss_miner.license_scanner`), zero
risk flags (`_secret_sentinel`), non-duplicate content hash, a replay fixture, and a passing
`promotion_recommender` verdict. No source promotes directly; all pass through quarantine.
