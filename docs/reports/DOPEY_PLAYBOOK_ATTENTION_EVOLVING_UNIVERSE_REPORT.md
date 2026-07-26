# DOPEY Playbook, Attention, and Evolving Universe

## Current operating state

DOPEY now publishes a multi-daily, research-only Playbook for bullish and bearish stock predictions. The Playbook is visible in the desktop UI, refreshes through the acceleration scheduler every 240 minutes, and cannot construct or promote orders. Bearish entries are prediction research, not short-sale instructions.

The current verified artifact was generated at `2026-07-22T08:26:10.211053+00:00` from market data through `2026-07-21`.

- Playbook status: `complete_research_rankings`
- Refresh interval: 240 minutes
- Active universe: 195 of 500 maximum
- Eligible single stocks: 181
- Attention: 224 rank-eligible partial observations, 1 abstention, 0 fully complete observations
- Paper-only research: true
- Live execution allowed: false
- Order construction allowed: false
- Trade promotion allowed: false
- Rank score is a research-priority score, not a probability or expected-return estimate

Final content identities:

- Attention snapshot: `f2f46f23bbeb5eef603fd56292771160fb73f31b397c3f35d7a939357acc39b3`
- Evolving-universe reproducibility hash: `7c2faf836781899c0f22b00b205c64cab87a140f2a3f4bf20e546abcc1bbb27a`
- Playbook content/reproducibility hash: `8603398fdc1aa97d42464f83bbacef9cafe7c2a1c03898083fc1c5789753ab2a`

## Current prediction research

These are ranked hypotheses requiring forward validation. They are not profit guarantees or individualized investment advice.

| List | Current symbols in rank order |
|---|---|
| Top 5 overall | AMD bullish, CVS bearish, INTC bearish, HPE bullish, RIOT bearish |
| Short-term bullish | AMD, HPE, COIN, ISRG, MARA, NOC, IONQ, DHR, MSTR, WMT |
| Short-term bearish | CVS, INTC, RIOT, HAL, PYPL, LCID, AMAT, DHR, XOM, MDB |
| Long-term bullish | INTC, AMD, MS, MU, TXN, AMAT, DDOG, GS, MPC, VLO |
| Long-term bearish | MSTR, BSX, ACN, NOW, ZS, ADBE, LCID, PYPL, SMCI, CRM |

The top-five research scores are AMD 66.42, CVS 65.19, INTC 65.18, HPE 63.79, and RIOT 63.72. Scores are cross-sectional priority measures and must not be interpreted as win probabilities.

## Playbook contract

The ranking engine publishes exactly four directional lists of up to 10 names plus an overall list of up to 5 unique symbols. It does not pad a list when the evidence is insufficient.

Each clickable UI entry exposes:

- thesis summary and independent setup-family agreement;
- why the symbol is timely;
- catalysts, risks, competing evidence, first rejection, and kill conditions;
- technical, fundamental, trust, attention, tradability, and universe evidence;
- missing evidence and freshness/provenance hashes;
- what additional evidence would make the hypothesis investable.

Directional bias comes only from independently detected market setups. Attention is direction-neutral and may only increase or decrease research priority. The ranker requires the attention snapshot and directional scan to share the same market-data frontier and fails closed on detector errors, malformed evidence, or an ineligible universe.

The desktop Playbook has no execution controls. The desktop state loader rejects malformed lists, invalid hashes, boundary violations, wrong list sizes, invalid ranks, duplicate identifiers, and any bearish record that could synthesize a short-stock order.

## Attention engine

Attention combines four independently attributable components:

- market activity;
- price and volatility discontinuity;
- news-event intensity;
- options activity.

Missing components remain explicit instead of becoming numeric zeroes. On the current frontier, 224 symbols are usable for ranking but partial because at least one optional component is absent; one symbol abstains. Attention is explicitly marked `research_priority_only`, `not_return_or_edge_evidence`, and non-directional.

Public context inputs follow the documented limits of their sources. FINRA states that published short-sale volume is not the same as short interest, and consolidated totals can be misleading without accounting for reporting scope. Wikimedia pageviews measure attention, not sentiment or price direction. SEC EDGAR submissions and XBRL facts are issuer-disclosure evidence, not trading signals. Source documentation: [FINRA short-sale volume](https://www.finra.org/finra-data/browse-catalog/short-sale-volume), [FINRA explanatory notice](https://www.finra.org/rules-guidance/notices/information-notice-051019), [Wikimedia Analytics API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/), and [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

## Evolving universe

The fixed-size universe assumption is replaced by a governed membership engine capped at 500 active symbols. It ranks the complete active set using attention, liquidity, capitalization, tradability, and evidence quality, while retaining membership history.

Current composition:

- 37 immutable core symbols;
- 158 active probation symbols;
- 30 standby symbols;
- 124 candidates;
- 305 unused active slots.

Promotion and demotion are transactional and fail closed. Thirty legacy ETF/fund records are currently in standby because truthful instrument-type/AUM evidence was absent. They can requalify from fresh metadata without rewriting OHLCV history. This is an evidence gap, not a negative price prediction.

## Scheduling and live host proof

The `playbook_refresh` lane runs through `dopey_acceleration` with:

- interval: 240 minutes;
- window: always;
- network required by lane: false;
- timeout: 900 seconds;
- evidence status required: `complete_research_rankings`.

The host task `DOPEY_AccelerationCycle` is installed and completed the new lane successfully during final verification. The lane is selected by the existing recurring acceleration cycle and its artifact evidence verifies complete. The final corrected direct end-to-end refresh completed in 318.8 seconds and rebuilt attention, evolved membership, scanned/settled directional hypotheses, and published the Playbook.

## Verification

- 98 focused Python tests passed across ranking, attention, universe evolution, scheduler/control-plane, desktop state, scanner wiring, and universe-governor suites.
- All 612 eligible directional detections share the exact `2026-07-21` frontier; mixed-frontier input fails closed.
- All seven Playbook source SHA-256 pins match their current files, and both internal Playbook hashes verify.
- Ruff passed on the changed Python surface.
- Desktop TypeScript typecheck passed.
- Desktop production build passed (38 modules transformed and inlined).
- Native desktop smoke check passed with schema v7 and the Playbook/attention/evolving-universe sources present.
- Desktop source health reports `attention_snapshot`, `evolving_universe`, and `playbook_rankings` as available with no relevant issues.
- Visual-QA fixtures generated successfully with read-only state and no mutation authority.
- Automated screenshot inspection could not be completed because the in-app browser rejected the local `file://` visual-QA URL under its navigation policy. No policy bypass was attempted.

## Remaining evidence gaps

- The current long-term list is a horizon-labeled research view; it does not yet have an independently matured long-horizon outcome ledger. Long-horizon confidence therefore remains provisional.
- Most attention records lack at least one optional source component, principally complete symbol-level news identity coverage.
- ETF/fund requalification needs trustworthy type and AUM metadata for the 30 standby records.
- The already-running Frontier Control MCP processes may continue to display the cached legacy 200/250 universe contract until those processes are reloaded. The filesystem, desktop state, and new runners use the 500 cap.
- No forward profitability claim is established by generating the rankings. Promotion toward capital use must depend on matured out-of-sample outcomes, calibration, transaction-cost evidence, risk controls, and the repo's independent live gates.

## Canonical files

- `dopey/strategy_engineering/playbook_rankings.py`
- `dopey/strategy_engineering/run_playbook_refresh.py`
- `dopey_attention/engine.py`
- `dopey_universe/evolving_universe.py`
- `desktop/src/views/PlaybookView.tsx`
- `artifacts/dopey/playbook/playbook_rankings.json`
- `artifacts/dopey/attention/attention_snapshot.json`
- `artifacts/dopey/universe/evolving_universe_summary.json`
