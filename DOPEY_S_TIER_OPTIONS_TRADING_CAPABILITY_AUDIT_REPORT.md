# DOPEY S-TIER OPTIONS TRADING CAPABILITY AUDIT REPORT

- audit_id: `dopey-s-tier-options-audit-2026-07-05`
- auditor: external audit agent (Claude Code), read-only + report-only session
- repo: `C:\Users\CH\dopey`
- scope: capability audit across trading edge, fundamentals, technicals, options intelligence, backtesting, execution modeling, risk, and recursive improvement
- machine-readable roadmap: `artifacts/dopey/s_tier_audit/s_tier_options_audit_roadmap.json`
- safety state during audit: unchanged. No live trading, no broker connection, no credentials, no `.env`, no scheduler, no order placement, no commits, no safety-gate modification.

---

## 1. Executive verdict

DOPEY is a **well-governed simulation shell with no trading intelligence inside it yet**. The safety
architecture is real and multi-layered. Almost everything that looks like market analysis, edge
discovery, backtesting evidence, or broker readiness is deterministic fixture math scoring itself
against hand-authored assumptions. The system is honest about this in places
(`DOPEY_CANON.md:120-121` — "deterministic offline fixture interfaces, not real market-data
integrations"), but the volume of reports, ledgers, scores, champions, and "proof" language builds
an impression of validated capability that the code cannot support.

The single most important structural fact: **the same hands that author the fixtures author the
expected outcomes.** Walk-forward windows carry `expected_outcome.next_underlying_price`,
`days_to_exit`, and `exit_reason` inside the fixture itself (`dopey_walk_forward/replay_engine.py:190`
reads `expected.get("days_to_exit")`). A backtest whose exits and terminal prices are pre-scripted
by the fixture designer cannot produce edge evidence, no matter how many consistency splits,
tournaments, and ledgers are layered on top.

### Grades by layer

| Layer | Grade | One-line justification |
|---|---|---|
| Trading intelligence | **D** | No signal is computed from any price/volume/IV series. `dopey_edge/signal_discovery.py:22-38` reads `oos_edge` out of a hand-built proof-bundle dict. 454 total lines in `dopey_edge`. |
| Options intelligence | **C-** | Black-Scholes Greeks engine is real and mathematically correct (`dopey_options/greeks_engine.py:22-56`). No IV solver, fake IV rank (hardcoded linear scale, `iv_surface_fixture.py:128`), trivial skew/term structure, assignment prob = \|delta\|. |
| Backtesting realism | **D** | 56 synthetic windows, one snapshot each, pre-scripted outcomes, zero commissions, no mark-to-market path, no benchmarks, no statistics. Structure (leak-free splits, holdout tagging) is decent; content is fiction. |
| Paper-trading architecture | **C** | Policy enforcement (no-day-trade, long-premium-only, 0DTE lifecycle) is genuinely wired into `PaperBroker` and `account_ledger`. But `PaperBroker` fills have **no price**: orders return `simulated_paper_filled` with no fill-price computation, and the 281-line `SlippageModel` is never invoked by it. |
| Broker-readiness | **D-** | The detector's 884 capability records are 13 hardcoded fixture capability types × 68 fixture runs (`dopey_broker_readiness/read_only_capability_provider.py:81-138`). No real broker API surface has ever been observed. Adapters return `"alpaca-paper-stub"` order ids. |
| Execution readiness | **F (correctly)** | No order types, no limit prices, no partial fills, no rejections, no quote freshness, no reconciliation between order log and position ledger. F is the *intended* state — noted here so nobody mistakes detector artifacts for progress. |
| Risk governance | **C-** | Incident FSM, lifecycle FSM, exposure caps, and thesis-required allocation are real, testable policy machines. Correlation is label-based, stress "scenarios" are tags not shocked Greeks, drawdown monitor has no equity curve to watch, zero calibration (no Brier scores). |
| Recursive improvement | **D+** | Deterministic, reproducible, safety-capped — and a closed Goodhart loop. Fitness = weighted proxy scores computed from the same fixtures the candidates were tuned on (`dopey_tournament/runner.py:85-124`; `REGIME_FAMILY_HINTS` hardcoded priors in `dopey_walk_forward/family_outcome.py:57-77`). Mutation "improvements" of +0.014 to +0.039 fixture points are meaningless. |
| Live readiness | **F (by design, correct)** | Live blocking is enforced at intent validation, PaperBroker, genome defaults, and config. This F is a passing grade for the current phase. |

**Overall: not S-tier, and not close — but the chassis is unusually well-suited to *becoming*
credible, because everything is deterministic, replayable, and policy-gated.** The missing
ingredient is not more governance; it is real data, real computation, and an outcome-based fitness
function.

---

## 2. What is real

These components genuinely work and are worth keeping:

1. **Live-order blocking, defense in depth.** `ExecutionIntent.validate()` rejects
   `live_allowed=true` (`dopey_execution/execution_intent.py:64-65`); `PaperBroker.place_order`
   raises `LiveTradingDisabledError` on live intents; `StrategyGenome.live_allowed` defaults False
   (`dopey_strategy_lab/strategy_genome.py:21`); the walk-forward replay engine refuses live intents
   outright (`dopey_walk_forward/replay_engine.py:84-85`); config defaults are research-only. This
   is real enforcement, not documentation.
2. **No-day-trade enforcement.** Same-day round trips are actually blocked in
   `dopey_execution/account_ledger.py` (open/close lifecycle with trading-calendar eligibility) and
   independently re-checked in `PaperBroker` active-policy validation (`paper_broker.py:91-112`).
   0DTE requires explicit lifecycle state + risk-model approval to same-day close.
3. **Black-Scholes Greeks engine.** `dopey_options/greeks_engine.py:22-56` — d1/d2, delta, gamma,
   theta (per-day), vega (per-1%), rho are all correct closed-form implementations. This is a real
   quant primitive the repricing engine of a future honest backtester can be built on.
4. **Policy/lifecycle/incident state machines.** `dopey_lifecycle` (signal→…→paper_closed states),
   `dopey_incident/incident_response_policy.py:14-31` (7-rank kill-switch FSM with per-state blocked
   action sets), and the active long-premium policy kernel (`dopey_governor/active_trading_policy.py`)
   are clean, deterministic, well-tested governance machinery.
5. **Reproducibility discipline.** Append-only ProofLedger, content hashes on records, a
   self-audit harness (`dopey_audit`) that actually recomputes hashes and cross-checks layers, and
   deterministic fixtures make every claim replayable. Rare and valuable.
6. **Leak-free split scaffolding.** The stronger walk-forward layer builds rolling/blocked/anchored/
   regime-holdout splits with a holdout-absence invariant. The *structure* is right; it is currently
   pointed at synthetic content.
7. **Test discipline.** 2,733 collected tests, no-network by construction, targeted shards pass
   quickly (37 tournament/walk-forward/pipeline tests pass in ~9s). The suite tests what the code
   claims — the problem is what the code claims is mostly governance, not intelligence.

---

## 3. What is theater or incomplete

Ranked by how much false confidence each generates:

1. **Backtest results, walk-forward scores, tournament rankings, champions.** Every P&L-like number
   is `fit_nudge + base_pnl * regime_factor + iv_component + pattern_boost - penalty`
   (`dopey_walk_forward/family_outcome.py:142-200`) where `regime_factor` comes from hardcoded
   `REGIME_FAMILY_HINTS` (directional_convexity = 0.80 in bullish_breakout, by fiat). The champion
   `genome-directional-convexity-spy-fixture-v1` is the strategy that best matches the fixture
   author's priors. Not evidence of anything.
2. **The five "S-tier analysis layers" (macro/micro/technical/fundamental/pattern).** All read
   pre-scored values from fixture JSON (e.g., `risk_on_score: 0.82` in
   `window_001_train_analysis.json`). `AnalysisFusionScore` is a weighted average of placeholders.
   The canon admits this; the tournament reports mostly don't re-admit it per-number.
3. **Broker-readiness record counts.** 884 capability records = 13 fixture capability families × 68
   completed fixture runs. 476/408/68 splits are combinatorial artifacts of the same multiplication.
   Zero real broker surface observed. The detector framework is a decent *harness*, but its outputs
   are currently self-referential and should never be cited as readiness evidence.
4. **PaperBroker "fills."** Orders are recorded `simulated_paper_filled` with **no fill price, no
   spread crossing, no slippage** (`dopey_execution/paper_broker.py:180,197`). The slippage model
   exists (`dopey_execution/slippage_model.py`, 281 lines) and is not called from the fill path.
   Replay-layer fill quality scores come from a different, fixture-fed path. Any "paper fill
   quality" metric upstream of promotion is therefore synthetic twice over.
5. **Mutation/feedback/threshold "optimization."** Score deltas like 0.577118 → 0.602118
   (`DOPEY_CANON.md:268-269`) are movements on the same fixture metric the mutation was designed
   against — a textbook Goodhart loop. "Failure-mode reduction estimate: -0.04" is a design-intent
   estimate, not a measurement.
6. **IV rank/percentile.** `(avg_iv - 0.10) / 0.25` clamped to [0,1] (`iv_surface_fixture.py:128`)
   is not IV rank; there is no IV history anywhere. Skew = mean(put IV) − mean(call IV); term
   structure = nearest-strike lookup. No solver exists to extract IV from prices.
7. **Correlation/stress/portfolio risk.** `CorrelatedExposureMonitor` is a labeled-group fraction
   check (self-described "research stub"). Stress ladder levels are case tags; no portfolio Greeks
   are recomputed under shocks. Drawdown slope math is real but has no real equity curve to consume.
8. **LiveOrderGate.** Correctly written (`dopey_governor/live_order_gate.py:34-72`) and **never
   called in any order path**. Current safety holds because of intent validation and PaperBroker
   checks, not because of the gate. Either wire it in or stop counting it as a boundary.
9. **The report corpus itself.** 98 root-level `.md` reports, 75 export bundles, 9,264 artifact
   files, 1.9 GB — for a system with 5 git commits and **332 untracked files** including entire
   packages (`dopey_audit/`, `dopey_broker_readiness/`, `dopey_allocation/`…). Reporting throughput
   has vastly outrun both engineering hygiene and capability growth. This is the Blunder disease
   signature: activity metrics compounding while capability stays flat.
10. **"Full validation."** Full pytest is `inconclusive_timeout` (308s, ~7% progress at kill;
    honestly recorded as not-a-pass — good). But a suite that cannot complete is a standing
    integrity hole: no state of the repo has ever been verified end-to-end.

---

## 4. Critical gaps to S-tier

### P0 — blocks any credible edge proof (paper or live)

- **G1. Zero real market data.** 0 real tickers, 0 OHLCV bars, 0 real option chains, 0 real IV
  history, 0 earnings dates. Fixture chains have 3 strikes and 3–12 price points. Nothing built on
  this can be validated, promoted, or trusted.
- **G2. Pre-scripted outcomes.** Fixture windows embed their own exit day, exit reason, and terminal
  price. The evaluator cannot disagree with the fixture author. This must be replaced by
  model-based repricing along price paths the strategy cannot see in advance.
- **G3. Proxy fitness / Goodhart promotion loop.** `_combined_score` weights ten fixture-derived
  component scores; promotion thresholds (proof strength ≥ 0.65 etc.) gate on those same synthetic
  numbers. Nothing in promotion measures held-out outcome quality.
- **G4. No fill economics.** PaperBroker fills have no price; commissions are zero everywhere;
  slippage model unwired. All downstream "P&L" is unpriced.

### P1 — needed for strong paper edge validation

- **G5. No computed signals.** Momentum, breakout, pullback, vol expansion, relative strength,
  regime — none are computed from series. The entire `dopey_edge` doctrine operates on metadata.
- **G6. No options market realism.** No IV solver, no IV history/rank, no surface interpolation, no
  theta/gamma path P&L during holds, no dividend/exercise modeling beyond intrinsic-at-expiry.
- **G7. No statistics.** No benchmark baselines (buy-and-hold, always-long-ATM-calls, random-entry),
  no bootstrap/confidence intervals, no deflated Sharpe/reality-check, N=24–56 synthetic trades.
- **G8. No real exit logic.** Stops, targets, time stops, and thesis invalidation are labels, not
  rules evaluated against a path; no max-loss auto-exit exists in replay.

### P2 — needed for live-pilot readiness (later, human-gated)

- **G9. Execution model gaps.** No order-type model (limit/market), no partial fills/rejections, no
  quote freshness, no order-vs-ledger reconciliation, LiveOrderGate unwired, kill-switch triggers
  fixture-injected only.
- **G10. Broker-readiness evidence is self-referential.** A real read-only proof requires observing
  a real broker surface (read-only, human-approved, per the existing approval-packet framework) —
  the current fixture detector cannot substitute.
- **G11. Repo/process integrity.** 332 untracked files, 39 modified files (~6.8k uncommitted lines
  including an in-flight tournament bundle), full pytest never completes. Rollback and provenance
  claims are hollow while the working tree itself is unversioned.

### P3 — elite/frontier upgrades

- **G12.** Event-driven catalyst engine (earnings/macro calendars with real dates), post-earnings
  drift and IV-crush modeling from history.
- **G13.** Cross-sectional relative-strength rotation across a 30–50 name universe; correlation
  from actual return series; portfolio Greeks under shocks.
- **G14.** Calibration layer: Brier scores/calibration curves for every confidence number the
  system emits; live-vs-paper deviation tracking once a real paper mirror exists.
- **G15.** Intraday (minute-bar) 0DTE modeling to replace 3-snapshot lifecycle fixtures.

---

## 5. Concrete upgrade roadmap

Bundles are ordered; each is sized to one focused work session and each has a hard safety boundary:
**no broker, no credentials, no live orders, no scheduler, no real capital.** Machine-readable copy
in `artifacts/dopey/s_tier_audit/s_tier_options_audit_roadmap.json`.

### B1 — REAL-DATA-BACKTEST-SPINE-V1 *(recommended first — see §10)*
- **Objective:** Replace hand-authored price fixtures with real historical daily OHLCV for ~30
  liquid optionable underlyings (SPY, QQQ, IWM, megacaps, sector ETFs), 3–5 years,
  dividend-adjusted, stored as offline files; add VIX daily history; derive realized vol series.
  Data is fetched once, by the human operator, offline-cached into `dopey_data/history/` — the
  runtime stays no-network.
- **Files/modules:** new `dopey_data/history_store.py`, loader schema, corpus registry; extend
  `build_corpus.py` to slice real windows instead of authoring synthetic ones.
- **Validation:** integrity tests (monotone dates, split/dividend adjustment spot checks, no-NaN),
  hash-pinned datasets, license note per source.
- **Proof artifacts:** dataset manifest with SHA256s, coverage report (symbols × days).
- **Safety:** market data only; no account or broker endpoints; runtime never fetches.
- **Impact:** unblocks G1; every later bundle depends on it.

### B2 — MODEL-REPRICER-V1
- **Objective:** Honest option mark-to-market along real underlying paths: IV solver
  (Newton + bisection fallback) added to `greeks_engine`, a minimal surface model (per-expiry ATM
  vol + skew parameterization calibrated to whatever chain data exists; model-generated chains
  where none does), daily repricing of held long calls/puts (theta/gamma/vega path P&L).
- **Files:** `dopey_options/iv_solver.py`, `dopey_options/surface_model.py`, rewrite of
  `family_outcome.py` to compute outcomes instead of reading `expected_outcome`.
- **Validation:** put-call parity checks, IV round-trip tests (price→IV→price), Greek finite-difference
  cross-checks against the closed-form engine.
- **Proof artifacts:** repricer test report; before/after comparison showing fixture-scripted vs
  model-computed outcomes on identical windows.
- **Safety:** pure math; no network.
- **Impact:** kills G2/G6-core; converts the replay engine from fiction to model-based simulation.

### B3 — REAL-SIGNAL-ENGINES-V1
- **Objective:** Compute the first real signals from B1 series: momentum (multi-horizon returns),
  breakout (N-day high/low with volume confirmation), pullback-in-trend (MA structure), volatility
  expansion/compression (realized-vol ratio, band width), relative strength vs sector/SPY. Regime
  classifier from realized vol + trend slope + drawdown state — computed, not labeled.
- **Files:** `dopey_analysis/technical_engine.py` (real), `dopey_strategy_lab/regime_classifier.py`
  (replace stub), `dopey_edge/signal_discovery.py` (compute instead of read).
- **Validation:** unit tests on known series; signal distribution sanity reports.
- **Proof artifacts:** signal coverage report over the B1 universe; regime timeline vs VIX overlay.
- **Safety:** offline computation only.
- **Impact:** kills G5; gives the tournament something real to rank.

### B4 — HONEST-BACKTESTER-V1
- **Objective:** Event-driven daily backtest loop: signals (B3) → contract selection (existing
  ranker, upgraded to delta/DTE targets) → entry at ask-side model price + commission ($0.65/contract
  default) → daily repricing (B2) → exits by rule (stop %, target %, time stop, thesis invalidation)
  under the existing no-day-trade policy → trade log with full P&L accounting.
- **Files:** new `dopey_backtest/` package; reuse PaperBroker policy checks as order-path gates.
- **Validation:** conservation tests (cash + positions), deterministic seed replay, golden trade-log
  fixtures.
- **Proof artifacts:** per-strategy trade logs, equity curves, cost attribution (spread, commission,
  slippage separated).
- **Safety:** paper only; real sizing stays abstract (risk units), no dollar account.
- **Impact:** kills G4/G8; produces the first outcome data worth scoring.

### B5 — STATISTICAL-TRUTH-LAYER-V1
- **Objective:** Benchmarks (always-long-ATM-call-30DTE, random-entry matched-holding, underlying
  buy-and-hold), block-bootstrap confidence intervals on expectancy and Sharpe, deflated Sharpe /
  multiple-testing correction across the candidate population, regime-separated result tables,
  minimum-N gates (no verdict below ~80–100 trades).
- **Files:** `dopey_validation/statistics.py`, walk-forward runner integration with true
  time-ordered expanding windows + embargo on real data.
- **Validation:** statistical unit tests against known distributions.
- **Proof artifacts:** per-family evidence cards: expectancy ± CI, max DD, benchmark delta, N.
- **Safety:** none needed beyond offline.
- **Impact:** kills G7; makes "proof" mean something.

### B6 — FITNESS-FUNCTION-REPLACEMENT-V1
- **Objective:** Promotion gates re-based on held-out outcomes: fitness = held-out expectancy after
  costs, penalized by max drawdown and CI width; proxy component scores (greek fit, fusion,
  pattern) demoted to diagnostics that can *veto* but never *promote*. Mutation loop re-pointed at
  B4 outcomes with train/holdout separation in time; retire fixture-score deltas from all champion
  language.
- **Files:** `dopey_tournament/runner.py` (`_combined_score` replacement),
  `dopey_governor/meta_governor.py`, `DOPEY_PROOF_WEIGHTED_PROMOTION_POLICY.md` rewrite.
- **Validation:** regression test proving a metric-gaming candidate (high proxy scores, bad held-out
  P&L) is rejected.
- **Proof artifacts:** promotion decision records citing held-out outcome stats only.
- **Safety:** promotion ceiling remains paper tiers.
- **Impact:** kills G3; ends the Goodhart loop.

### B7 — PAPERBROKER-FILL-REALISM-V1
- **Objective:** Wire `SlippageModel` into `PaperBroker.place_order`; fills = model price ± spread
  crossing with liquidity-scaled slippage; limit-order semantics with marketable/non-marketable
  outcomes; probabilistic partial fills and rejections (deterministic seed); quote-timestamp
  freshness field with staleness rejection; order-log ↔ account-ledger reconciliation check; wire
  `LiveOrderGate.evaluate()` into the order path as the final pre-fill gate (it will always deny
  live — that is the point).
- **Files:** `dopey_execution/paper_broker.py`, `slippage_model.py`, `account_ledger.py`,
  `dopey_governor/live_order_gate.py` call sites.
- **Validation:** existing safety tests must stay green; new fill-distribution tests.
- **Proof artifacts:** fill-quality report from replayed B4 runs; reconciliation zero-drift proof.
- **Safety:** paper-only unchanged; gate wiring strengthens, never weakens, boundaries.
- **Impact:** kills G4-execution-half and half of G9.

### B8 — EXIT-DISCIPLINE-ENGINE-V1
- **Objective:** Real long-premium exit logic evaluated per-day against B2 marks: premium stop
  (e.g., −50%), target (e.g., +100%), time stop (DTE floor), delta/thesis invalidation (underlying
  crosses invalidation level), max-loss auto-exit enforced in replay, all under no-day-trade rules
  with 0DTE special-lifecycle carve-out.
- **Files:** `dopey_lifecycle` (economic triggers added to FSM), `dopey_backtest` exit module.
- **Validation:** scenario tests (gap-through-stop behavior, expiry-day handling).
- **Proof artifacts:** exit-reason distribution reports; loss-clipping evidence vs no-discipline
  baseline.
- **Impact:** kills G8; makes risk discipline mechanical rather than aspirational.

### B9 — 0DTE-EMPIRICAL-LIFECYCLE-V2
- **Objective:** Replace 3-snapshot 0DTE fixtures with minute-bar-driven paths (model-generated
  from realistic intraday vol profiles first; real minute data later if licensed), gamma/theta path
  accounting, time-of-day boundaries, pin-risk and auto-exercise handling at expiry.
- **Files:** `dopey_options/zero_dte_*` modules.
- **Validation:** adversarial corpus re-run on the new engine; loophole tests stay red.
- **Impact:** makes the 0DTE sleeve's special-lifecycle proof mean something (G15).

### B10 — REPO-INTEGRITY-AND-VALIDATION-STABILIZER-V1
- **Objective:** (a) Commit the working tree in reviewed logical bundles (human-approved; this
  audit creates none); (b) archive/prune the 75 export bundles (1.9 GB) out of the working repo;
  (c) shard pytest into tagged lanes (fast/policy/replay/export) with per-lane timeouts and a CI
  script so a *complete* green run exists; (d) de-duplicate the repeated canon sections
  (`DOPEY_CANON.md` has 6 identical POST_RUN_EVIDENCE blocks and encoding damage — see
  `DOPEY_TEXT_ENCODING_GUARD_REPORT.md`).
- **Validation:** full-suite green run recorded with wall-clock; repo size delta.
- **Impact:** kills G11; makes every other bundle's evidence trustworthy.

### B11 — CATALYST-AND-FUNDAMENTAL-DATA-V1 *(P3, after B1–B6)*
- **Objective:** Real earnings-date calendar and macro-event dates (historical, offline-cached);
  post-earnings-drift and pre/post-event IV behavior measured from history; sector relative-strength
  rotation across the B1 universe; fundamental scenario scores replaced by real coarse factors
  (revenue growth, margin trend from filings) where licensable.
- **Safety:** documents and calendars only; SEC/EDGAR is public; no broker data.

### B12 — BROKER-READ-ONLY-PROOF-V1 *(P2, human-gated, last)*
- **Objective:** Execute the already-designed approval-packet path against a real broker in strictly
  read-only mode (see §8). Not before B1–B8 exist — read-only broker proof without an edge to
  deploy is ceremony.

---

## 6. Trading strategy expansion plan

**Consistency finding first:** the declared trade universe is long calls and long puts only, but the
current tournament families build verticals (short leg), iron condors (short-vol credit structure),
and butterflies (`DOPEY_CANON.md:140-144`, `dopey_walk_forward/family_structures.py:78-134`). The
iron-condor family directly contradicts the active policy's "no short-vol premium-selling
structures" rule (`DOPEY_CANON.md:619-620`). Before expansion, **reconcile the family set with the
canon**: either the universe is single-leg long premium (then retire/quarantine the
condor/vertical families from the tournament) or net-debit multi-leg is explicitly in scope (then
amend the mission statement). This audit assumes single-leg long calls/puts per the operator's
current instruction.

Strategy families to build on B1–B5 foundations, all long-single-leg, all no-day-trade compliant:

| Family | Entry (computed, not labeled) | Contract | Exit | Regime gate |
|---|---|---|---|---|
| **Momentum breakout** | N-day high break + volume ≥ 1.5× 20d avg + RS vs SPY positive | Call, 30–45 DTE, 0.55–0.65Δ | +100% target / −50% stop / 21-DTE time stop | trend or expansion regimes only |
| **Failed breakout / fakeout** | Break of N-day level that closes back inside within 1–2 days | Put (failed upside break), 21–35 DTE, ~0.50Δ | +80% / −50% / 14-DTE | chop→reversal transitions |
| **Trend pullback continuation** | Uptrend (20>50 MA, positive slope) + pullback to 20MA holding | Call, 30–45 DTE, 0.60Δ | trend-break invalidation (close < swing low) | trending regimes |
| **Volatility expansion** | Realized-vol compression percentile < 20 + range contraction, direction from RS | Call or put, 30–60 DTE, 0.45–0.55Δ; require IV percentile < 40 to avoid overpaying | vol-expansion realized or 50% premium stop | compression regimes |
| **Post-earnings drift** | Earnings gap > +4% with above-average volume, buy day-after | Call, 30 DTE, 0.55Δ | 10-trading-day time exit / −50% stop | needs B11 calendar |
| **Sector RS rotation** | Sector ETF 20d RS rank top-2 and improving | Call on sector ETF, 45 DTE, 0.60Δ | RS rank decay below median | risk-on regimes |
| **Macro/rates-sensitive directional** | Rate-shock day (2y yield move > 2σ) → puts on rate-sensitive sectors, calls on beneficiaries | 30–45 DTE, 0.50Δ | 5–10 day time exit | event windows (B11) |
| **Event/catalyst swing** | Pre-scheduled catalysts with historical drift edge, entered T-5 to T-2 | Direction from B3 signals; skip if IV percentile > 70 (crush risk) | exit before event unless drift-hold rule proven | needs B11 |
| **0DTE special lifecycle** | Only after B9; index/mega-ETF only, catalyst-day, first/last-hour boundaries, existing lifecycle proof machinery | 0DTE call/put, strict spread/liquidity caps | intraday special-lifecycle rules; never a churn loophole | gated exactly as current canon |

Every family enters the tournament only with: ≥100 held-out trades, benchmark deltas, and cost-full
P&L (B5 gates). Families that can't reach N=100 in available history (macro-shock) carry an
explicit "insufficient-N, research-only" tag rather than a score.

---

## 7. Data and backtesting plan

Nothing is fetched now. Classification of future needs:

| Class | Contents | Status/boundary |
|---|---|---|
| **Offline fixture data (current)** | 138 fixture JSONs, ~12 MB, synthetic | Keep for policy/regression tests only. Never cite as market evidence again. |
| **Historical market data (B1)** | Daily OHLCV 30–50 optionable names + sector ETFs + SPY/QQQ/IWM, 3–5y, dividend/split adjusted; VIX/VVIX daily | Human fetches once (yfinance/Stooq/Polygon free tier acceptable for daily), cached offline, hash-pinned. Runtime stays no-network. |
| **Historical options chain/quote data (B2+/B9)** | EOD chains with NBBO bid/ask, OI, volume, IV per contract (e.g., CBOE DataShop, ORATS, HistoricalOptionData ~$50–100 one-off per slice); minute bars for 0DTE later | Deferred purchase decision; until then B2's surface model generates chains calibrated to realized vol + VIX so the backtester is at least model-honest. Flag every result "model-priced, not quote-priced". |
| **Fundamental data (B11)** | Earnings dates + surprise history; coarse quarterly fundamentals from EDGAR (public) | Public filings acceptable offline; analyst estimates need licensing — defer. |
| **News/catalyst data (B11)** | Macro calendar (FOMC/CPI historical dates are public), earnings calendar | Public, offline-cacheable. |
| **Broker/account data** | Quotes-with-entitlements, account state, fills | **Forbidden until explicit human approval**, per existing approval-packet canon. Not needed for B1–B8. |

Backtesting rules that must hold from B4 onward: point-in-time universe lists (avoid survivorship
— fix the universe by liquidity as-of each year-start), no same-bar entry/exit on signal bar
(enter next open), embargo gaps between train and test, every result labeled with its pricing
source tier (fixture < model-priced < quote-priced).

---

## 8. Execution-readiness plan

Path from the current read-only fixture detector to a tiny human-approved live pilot. Each step is
a separate human-approved bundle; none is started by this audit.

1. **Post-run evidence hardening (done in fixture form).** Keep the evidence-contract machinery,
   but re-label all fixture-derived records `fixture_only=true` in summaries so counts (884/476/408)
   can never be quoted as broker evidence.
2. **Simulated quote/order-review mirror (B7 output).** PaperBroker with priced fills, limit
   semantics, rejections, and reconciliation — a broker-shaped surface with broker-like responses,
   still 100% offline.
3. **Paper mirror with broker-like responses.** Replay the mirror against recorded (not live)
   broker response schemas — error codes, order-state transitions from public API docs — so
   reconciliation and kill-switch paths exercise realistic failure shapes (timeouts, partial
   fills, rejects).
4. **Reconciliation simulator.** Inject drift (missing fill, duplicate order, stale position) and
   prove detection + incident-FSM escalation, closing the current two-truth-sources gap.
5. **Read-only real broker proof (human-approved, first network step).** The existing intake
   validator/handoff gate/pre-run scanner framework runs against a real read-only surface
   (quotes/chains/hours only; no account writes, ideally no account at all first). Output: real
   capability records replacing the fixture multiplication.
6. **Order-review-only proof.** Broker order *preview* endpoints only (no submission), verifying
   the request-construction path against real validation errors, with the LiveOrderGate wired and
   denying submission.
7. **Tiny human-approved live pilot packet.** Only after B5/B6 evidence exists: one underlying, one
   contract, 1-lot, defined premium cap, human approves each order individually, kill-switch and
   reconciliation active, full audit trail. Not a DOPEY decision — a human one, using DOPEY's packet.

Explicitly *not* on this path: schedulers/daemons, credential storage in-repo, autonomous sizing.

---

## 9. Anti-Goodhart requirements

**Metrics to retire from all promotion/verdict language** (may survive as diagnostics only):

- capability/read-only/blocked **record counts** (884/476/408/68) — fixture multiplication
- `completeness_score: 100`, coverage %, artifact counts, ledger lengths, report counts
- fixture score deltas (0.577→0.602 "improvements"), `combined_score` and all ten component scores
  as promotion inputs, `proof_strength` as currently computed (average of synthetic scores)
- "S-tier" as a self-applied label anywhere in canon or reports until §5 B5-gated evidence exists
- pass/fail verdicts from windows whose outcomes are fixture-scripted
- test-count and shard-pass counts as capability claims (they verify governance, which is fine —
  say "governance verified", not "trading validated")

**Replacement outcome metrics (the only promotion currency):**

- held-out expectancy per trade **after costs**, with block-bootstrap CI, N ≥ 100
- hit rate × payoff ratio decomposition; max drawdown; ulcer index
- delta vs three benchmarks (buy-and-hold underlying, always-long-ATM-call, random-entry matched)
- deflated Sharpe / multiple-testing-corrected significance across the whole candidate population
  (the tournament tests dozens of variants — correct for it)
- regime-sliced expectancy with per-slice N disclosed
- calibration: Brier score of every confidence/probability the system emits vs realized outcomes
- later: paper-vs-model deviation (fill quality, mark error) once a real mirror exists

**Structural rules:** (1) any metric that appears in a promotion gate must be computed on data the
candidate never touched during fit — enforced by time-split registry, not convention; (2) the
fixture corpus is quarantined to policy-regression duty; (3) every report that cites a number must
carry its pricing-source tier; (4) one metric owner: `dopey_validation` computes outcome stats,
nothing else may.

---

## 10. Final recommendation

**Single best next bundle: B1 — REAL-DATA-BACKTEST-SPINE-V1** (with B2 as its immediate successor
in the same arc).

Reasoning: every other improvement — signals, honest backtesting, statistics, fitness replacement,
even meaningful 0DTE work — is blocked behind the absence of a single byte of real market history.
B1 is cheap (daily bars for ~30–50 names + VIX, one-time offline fetch by the operator), zero
safety risk (no broker, no credentials, runtime stays no-network), and it immediately converts the
strongest existing assets (deterministic replay harness, split builder, Greeks engine, policy
gates) from theater props into working instruments. The moment real series exist, the pre-scripted
`expected_outcome` pattern becomes deletable (B2), and DOPEY's enormous governance investment
finally has something real to govern.

Do not build more governance, reporting, detector, export, or approval layers until B1–B5 exist.
That machinery is already several stories taller than the building.

---

## Appendix A — Audit verification log

Commands run (all read-only/inspection; no broker/live/network commands):

- `git status` / `git log --oneline` / `git diff --stat` — 5 commits; 227 tracked files, 332
  untracked, 39 modified (~6,820 uncommitted inserted lines incl. `dopey_tournament/runner.py` +1,002)
- `python -m pytest --collect-only -q` — **2,733 tests collected in 1.14s**
- `python -m pytest tests/test_tournament.py tests/test_walk_forward.py tests/test_pipeline.py -q`
  — **37 passed in 9.21s** (covers the in-flight uncommitted bundle's areas)
- `python -m pytest -q -p no:cacheprovider --durations=25` (600s cap) — timed out without
  completing, consistent with the recorded `inconclusive_timeout` at 308s/7%; full-suite completion
  remains unproven (see B10)
- Package/LOC census, artifact census (98 root reports, 75 export bundles, 9,264 artifact files,
  1.9 GB), fixture sampling, and seven domain-focused source reviews with file:line evidence
  (strategy/edge, options intelligence, backtesting, execution/broker, risk/portfolio, data layer,
  recursive improvement)

Not verified (could not, within this session): full-suite green state (timeout); exact behavior of
every one of the 63 `dopey_options` files (sampled the load-bearing ones); the `_forked_blunder`
provenance trees (out of scope, read-only preserved); any claim about real broker behavior (no
network access permitted or attempted).

No commit was created. No file outside this report and the roadmap JSON was modified.
