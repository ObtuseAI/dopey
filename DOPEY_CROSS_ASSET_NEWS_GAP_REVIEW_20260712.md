# DOPEY Cross-Asset and News Gap Review

Date: 2026-07-12  
Scope: `dopey_equity_swing`, cross-asset operator intake, news operator intake, staged data, tests, and current v2 artifacts  
Review posture: evidence-only; no trading behavior changed

## Verdict

The v2 layer is a useful, safety-gated research context system, but it is not yet an elite or production-grade cross-asset/news intelligence engine. The most important weaknesses are temporal correctness, non-archival snapshots, continuous-futures roll contamination, stale/partial data being re-labeled complete, weak news-source independence, and a lack of historical validation for every context weight and veto threshold.

Live trading, broker access, sizing, and order authority remain blocked.

## Priority findings

### P1 - Future-dated news leaks into replay decisions

`classify_news_events` clamps negative age to zero. An event published after a supplied decision time is labeled `fresh_24h` and enters the recent-event set. A direct probe with a 2026-07-13 event and a 2026-07-12 decision returned age `0.0` and `fresh_7d_event_count=1`.

Required correction: exclude `published_at > decision_time`, record `future_event_rejected`, and add a replay test.

### P1 - News and cross-asset inputs are overwritten instead of archived

Both operator stages atomically replace one canonical data file and one manifest. The current GDELT lane only requests seven days, so repeated runs cannot reconstruct what the engine knew at a prior decision time. The reverse-engineering lane therefore cannot test whether news or cross-asset context improved missed-trade selection.

Required correction: immutable timestamped raw snapshots, append-only normalized ledgers, ingestion timestamps, raw-response hashes, and an as-of loader.

### P1 - Continuous futures are not roll-aware

The intake stores only provider symbol, date, close, and volume for generic front-month symbols such as `CL=F` and `NG=F`. There is no contract month, roll date, adjustment factor, open interest, or OHLC. Observed one-day absolute moves include NG `47.48%`, SI `31.35%`, HG `22.25%`, and CL `16.41%`; the engine cannot distinguish market shocks from roll/stitch artifacts.

Required correction: contract-level histories, explicit roll calendar, back-adjusted and unadjusted series, roll flags, OHLC/open interest, and shock calculations that exclude or separately model roll transitions.

### P1 - Freshness and completeness do not propagate honestly

Cross-asset `as_of_date` is the maximum date across all series, which was 2026-07-12 because crypto trades on weekends while futures and FX ended 2026-07-10. There is no per-market calendar or maximum-age gate. Partial manifests are accepted by loaders, while the derived news and cross-asset artifacts declare `complete` without carrying the source failure state forward.

Required correction: per-series expected calendars, source-specific freshness SLAs, common decision cutoff, stale-series exclusion, and exact manifest status propagation.

### P1 - Context rules have no walk-forward evidence

Risk, inflation, growth, theme weights, `-0.70` contradiction veto, `0.65` stress gate, three-source news threshold, and keyword severities are hand-set. Current reverse engineering uses price features only. No ablation proves that cross-asset or news context improves precision, drawdown, timing, or calibration out of sample.

Required correction: point-in-time context archive, purged walk-forward joins, threshold ablations, regime and era splits, and shadow-only promotion gates.

### P2 - News corroboration counts domains, not information independence

GDELT supplied 250 of 339 events (`73.75%`). Any three domains can satisfy independence even when they repeat the same wire story, syndicate one source, or are low-quality outlets. Conversely, semantically identical reports with different titles can miss the Jaccard threshold. The staged set contained 23 events across 10 exactly duplicated titles.

Required correction: source-quality tiers, wire/syndication lineage, canonical event/entity extraction, semantic clustering, geography, and corroboration that weights primary/official evidence above domain count.

### P2 - News is not mapped to the affected asset or company

Categories are produced, but thesis integration consumes one global risk-tone scalar. Energy disruption, semiconductor export controls, bank regulation, crypto enforcement, and company-specific events are not mapped to sector, theme, ticker, commodity, currency, or maturity exposures.

Required correction: typed event-to-exposure graph with direction uncertainty, impacted symbols/themes/assets, effective time, expected horizon, and explicit contradiction handling.

### P2 - Important primary information lanes are missing

The pipeline has Fed, SEC, CFTC, EIA, and GDELT coverage, but no point-in-time economic calendar or surprise data for CPI/PPI/PCE, payrolls, GDP, PMIs, Treasury auctions/refunding, FOMC schedule, USDA crops, NOAA weather, OFAC sanctions, State/Defense geopolitical releases, exchange outages, EDGAR company filings, or earnings-call revisions.

Required correction: add official event calendars and releases before expanding secondary media volume.

### P2 - Asset-specific depth is shallow

- Treasury: no real yields, breakevens, SOFR/repo, auction tails, term premium, or funding stress.
- Commodities: no futures curve, inventories, COT by commodity, seasonality, freight, or weather.
- Crypto: no perpetual funding, open interest, liquidations, stablecoin flows, ETF flows, basis, or on-chain activity.
- FX: no carry/rate differential, positioning, intervention calendar, or central-bank divergence.

### P2 - Operational tracking is manual

The fetchers are not registered with a scheduler, freshness monitor, alert ledger, or last-known-good quarantine workflow. A user must run both operator commands and the engine manually.

Required correction: paper-only scheduled intake with immutable snapshots, source health metrics, stale alerts, and a fail-closed decision gate. This must not broaden into broker or live-order automation.

### P2 - Failure and test coverage gaps

The cross-asset retry handler does not catch general network request exceptions emitted below `yfinance`, so some transient failures can bypass its retry loop. Tests cover pure trend and synthetic corroboration behavior but not future-event rejection, partial manifests, stale series, roll jumps, source-quality tiers, append-only replay, or a full staged-data integration run.

## Current evidence snapshot

- Cross-asset: 20 series, 10,527 rows, no duplicate symbol/date rows.
- Calendar mismatch: BTC/ETH through 2026-07-12; futures/most FX through 2026-07-10.
- News: 339 events, seven sources, six official feeds, 250 GDELT events.
- News concentration: GDELT share `73.75%`.
- Exact-title duplication: 10 duplicated titles covering 23 events.
- Current context: risk appetite `0.287922`, systemic stress `0.278019`, zero corroborated alerts.
- Current thesis effect: AMD context confirmation `0.166054`; LCID context contradiction `-0.334233`, below the veto threshold.
- Validation: 28 targeted tests passed, but the missing tests above prevent an elite-readiness claim.

## Recommended remediation order

1. Fix time leakage, freshness/status propagation, network retry coverage, and partial-data fail-closed behavior.
2. Make all source data immutable and replayable as of a decision timestamp.
3. Replace generic continuous futures with roll-aware contract data and per-market calendars.
4. Add official economic/geopolitical calendars plus source-tiered event/entity/exposure mapping.
5. Run purged walk-forward context ablations; promote only rules that improve multiple eras without weakening drawdown or calibration.

## Honest terminal state

`research_context_functional_not_elite_context_evidence_incomplete`

No current cross-asset or news heuristic should be promoted into sizing or live execution.
