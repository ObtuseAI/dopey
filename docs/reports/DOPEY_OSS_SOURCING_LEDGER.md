# DOPEY OSS Sourcing Ledger

Vetted open-source material (GitHub sweep 2026-07-10). Verdicts are envelope-bound:
MIT-compatible licenses only for imports, no broker/execution wiring, no
credentialed lanes, no unreviewable data, hand-rolled preferred where the math is
small enough to own.

## Adopted
| Project | License | Use |
|---|---|---|
| exchange_calendars | Apache-2.0 | authoritative XNYS sessions in `dopey_core/market_calendar.py`; reviewed static holiday list retained as fallback (zero-dep degrade) |
| yfinance / requests / pandas / matplotlib / openbb | Apache/MIT/BSD | pre-existing operator-lane + rendering dependencies |

## Adopt-later (earmarked, not yet needed)
| Project | License | Trigger |
|---|---|---|
| QuantLib-Python | BSD-mod | American-exercise pricing cross-check if early-exercise premium ever matters to the honest lane (long premium exits in <=3 sessions today) |
| arch | NCSA | GARCH(1,1) realized-vol forecast to upgrade the VRP proxy once the macro lane earns a role |
| hypothesis | MPL-2.0 | property-based fuzzing of the pricing/IV engines in the weekend soak harness |
| duckdb | MIT | chain-archive analytics when the CSV archive outgrows linear scans (~months away) |
| Microsoft qlib | MIT | ML research platform; only relevant if the foundry graduates past rank-IC screens |

## Reference-only (read the ideas, do not import)
| Project | Why not import |
|---|---|
| awesome-quant / awesome-systematic-trading | curated indexes - sourcing maps, not code |
| py_vollib (+ lets_be_rational) | MIT but redundant: house `implied_vol_bisection` is 30 dependency-free lines against our own pricer |
| SVI / arbitrage-free surface repos (XanderRobbins etc.) | good math references for a future vol-surface upgrade; hobby-grade code stays out of the truth path |
| hftbacktest, nautilus_trader, StockSharp | HFT/execution engines - wrong asset horizon, and execution wiring is envelope-refused regardless |

## Refused (do not adopt)
| Source | Reason |
|---|---|
| FinancePy, backtrader | GPL-3: importing contaminates the MIT release lane |
| DoltHub community options DBs | data provenance/license unreviewable (recorded in macro manifest) |
| unofficial Robinhood APIs / reverse-auth MCP servers | permanently blocked by envelope |
| X/Twitter scrapers | ToS-violating collection |
| Stooq bulk endpoints | requires circumventing an anti-bot proof-of-work |

Every future adoption goes through this ledger: license first, envelope second,
"can we own the math ourselves" third.
