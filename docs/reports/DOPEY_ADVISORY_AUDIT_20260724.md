# DOPEY Advisory Audit — Strategies, Intelligence, Execution, Tooling

Date: 2026-07-24
Scope: code-grounded audit of `C:\Users\CH\dopey` @ `594018e` (branch `agent/dopey-vnext-operational-readiness`)
Nature: **advisory report. No code changed, no gates touched, no evidence claimed.** Recommendations in §7 respect the constitution; §8 lists ideas that would require constitutional change, clearly separated.

Method: serial self-audit — core docs (README, CAPABILITY_CARD, NO_EDGE_CERTIFICATE, META_CAPABILITY_FOUNDRY_REVIEW_20260724, EQUITY_FIRST swing report, INTRADAY_WATCH), then targeted reads of `dopey_analysis`, `dopey_signal_research`, `dopey_backtest`, `dopey/evolution|autoresearch|intelligence_research|world_model|memory`, `dopey_strategy_lab`, `dopey_execution`, `dopey_live`, `dopey_autonomy`, `operator_tools`, `dopey_ops`. Test collection verified green under `.venv` (~4,206 tests); **full suite not run** (CI/nightly shards own that).

---

## 1. Executive summary

DOPEY has built **world-class honesty infrastructure on top of a search space too small to contain an edge**. The imbalance is the finding.

The honest scoreboard says: 9,333 real-history trades net negative after costs, 0/10 cohorts beat random baselines, 0/144 TA composites promoted, one measured skill — **loss avoidance** (+1,065 units by *not* trading). Meanwhile the last two weeks of commits went overwhelmingly into integrity hardening (semantic RNG, replay manifests, contamination detection, memory graphs) — protecting the evaluation of candidates that have no predictive content. The meta-foundry review's own verdict agrees: "not another model or strategy library" was the gap *it* chose to close. This audit's read is the mirror image: the integrity substrate is now so far ahead of the predictive substrate that further integrity work has near-zero marginal value until there is something worth being honest about.

The five highest-leverage moves, in order:

1. **Pivot research mass from entry discovery to exits, avoidance, and sizing** — the only skill the system has ever measured lives there, yet the entire research estate (7 signal families, 144-composite foundry, V1–V7 breakthrough campaigns) is entry-obsessed, and the exit policy is one fixed rule (`-50% / +100% / 3 sessions`) applied to everything.
2. **Fix the horizon mismatch**: the indicator foundry optimizes 5-day-forward IC (`indicator_foundry.py: FORWARD_HORIZON = 5`) while the forward walk pins a 3-marking-session max hold (`forward_paper_walk.py: MAX_MARKING_SESSIONS = 3`). The promotion lane cannot even express the horizon the discovery lane optimizes for.
3. **Make the evolutionary machinery actually adaptive.** The "mutation policy" is a fixed hand-written list of ~12 mutations with hardcoded values (`dopey_strategy_lab/mutation_policy.py`); genome fitness is weakest-dimension-capped over dimensions that are all ~0 because there are no settled samples. This is instrumentation of evolution, not evolution.
4. **Attack costs, not just signals.** Every entry is modeled as a taker fill at the ask. On retail long-option spreads, a patient-fill (mid/limit) lane is often the whole difference between PF<1 and PF>1. A shadow patient-fill lane is cheap to build and measures a real, actionable number.
5. **Consolidate the V1–V7 proliferation.** Seven generations of `research_mutation_queue`, `research_holdout`, `research_breakthrough_gate`, plus 14 live-gate status modules — old versions are referenced only by the artifact loader (historical archaeology). Keep them as frozen artifacts, not as 20k LOC in the active package.

Bottom line: DOPEY is an excellent *referee* with a weak *team*. Fund the team.

---

## 2. Strategies & indicators

### What exists

- **7 directional signal families** on daily OHLCV (`dopey_analysis/technical_signal_engine.py`): momentum, breakout, fakeout, market regime, trend pullback, relative strength, volatility regime. Leak-free by construction (bars-through-date enforced).
- **Indicator foundry** (`dopey_analysis/indicator_foundry.py`): 12 classic indicators + grammar-composed composites, rank-IC evaluated train (2015–2021) vs validation (2022–2026) with a multiple-testing bar that rises with candidate count and a circular-shift null. Result: **0/144 promoted**. This is good statistics producing an honest null.
- **Equity-first multi-timeframe swing engine**: 24 names, 78% technical / 22% fundamental weighting, point-in-time fundamental snapshots. Latest run: **0 actionable theses**, 0 tracked contracts.
- **V1–V7 public signal research campaigns** (`dopey_signal_research/`, 183 files / ~20k LOC): candidate generators, mutation queues, holdouts, breakthrough gates. Each generation responded to zero results by adding more gate criteria — V7 has ~20 conjunctive criteria. Result across all generations: **0 promotions**.

### Weaknesses (file-level)

- **The search space is univariate threshold rules on daily bars.** There is no cross-sectional model anywhere (rank 200 symbols against each other), no regularized regression, no gradient boosting, no learned ensemble — `ensemble_allocator.py` allocates among rule families, it doesn't learn. Daily-bar threshold rules are the single most picked-over search space in retail quant; the honest nulls are exactly what prior literature predicts.
- **Horizon mismatch (see §1.2).** A foundry candidate with genuine 5-day IC gets force-closed at session 3 by the only exit policy that exists. Some fraction of the "0/144" null may be measurement artifact, not absence of signal. This is testable for free: re-run the foundry's promoted-nowhere candidates under a 5-session-hold honest backtest and compare.
- **Gate ratcheting is not research progress.** V1→V7 mostly made rejection more elaborate. The value of a campaign is its *candidate generation*; DOPEY's generations kept the same generator family and hardened the filter. Stricter filters on the same candidates cannot produce a promotion.
- **Fundamental lane is thin.** Fundamental confirmation exists (22% weight, fixtures, sector peers) but there is no fundamental *signal family* with its own walk-forward lane — no earnings drift, no revision momentum, no accruals/quality screens, despite staged news/event fixtures already existing.

### New hypotheses worth testing (constitution-respecting)

Each listed as: hypothesis → data already in-house? → falsification test.

1. **Cross-sectional relative momentum/volatility ranking** across the 200-symbol universe (long the top decile vs skip-the-bottom-decile avoidance overlay). Data: existing OHLCV spine. Falsify: era-split rank-IC of the *cross-sectional rank* (not per-symbol thresholds) vs the existing circular-shift null.
2. **Post-earnings announcement drift (PEAD)** using the staged news/event fixtures as earnings calendar. The strongest documented equity anomaly; absent from DOPEY entirely. Falsify: event-window forward returns vs matched non-event cohorts, cost-stacked.
3. **Earnings IV-crush avoidance overlay** — formalizes the one measured skill (VRP blackout) into a per-symbol calendar rule. Falsify: veto shadow ledger A/B — the infrastructure to measure this *already exists*.
4. **Sector-relative strength** using `sector_peer_context.py` fixtures: symbol signal valid only when sector rank agrees. Falsify: cohort split on sector agreement; measure veto opportunity cost via shadow ledger.
5. **Congress-trade fade / attention flags** — already emitted as "research flags" in INTRADAY_WATCH (`NFLX, MSFT, BAC` selling; put-side fundamental shorts list). Promote from dashboard text to a registered cohort with forward tracking. Falsify: matched forward cohort vs baseline.

None of these require new data vendors, new holding periods, or constitutional change. All fit the existing forward-evidence lanes.

---

## 3. Intelligence / algorithms

### What exists

- Integrity substrate (best-in-class, keep it): collision-safe semantic RNG, content-addressed evaluation specs, fixed common-random-number seed panels, replay manifests capped at SHADOW_ONLY, cognitive contamination detection, content-hash-verified canonical memory, rebuildable causal memory graph, SQLite projection over the 321k-trade ledger.
- Recursive evolution kernel (`dopey/evolution/`): population → constitutionally filtered mutation → isolated replay → weakest-dimension fitness → promotion *proposal* (never persisted).
- Autoresearch (`dopey/autoresearch/`): seed strategy taxonomy → evidence-steered invention → task suites.
- Cognitive layer (`dopey/intelligence_research/`): creativity operators (ANALOGY, INVERSION, MORPHOLOGICAL_SEARCH...), theory candidates, evidence cycles.
- Capability foundry (`dopey_acceleration/`): 32 pinned external candidates, quarantined, zero adopted.

### Weaknesses (file-level)

- **The mutation policy is not search.** `dopey_strategy_lab/mutation_policy.py: build_mutation_instructions()` returns a fixed ordered list: `mut-delta-01 → 0.58`, `mut-dte-01 → "21_35"`, etc. Twelve hand-picked constants, evaluated once, forever. There is no population dynamics, no fitness-proportional selection, no novelty search, no restarts. Calling this "evolution" overstates it; it is a dozen manual what-ifs with excellent receipts.
- **Genome fitness is structurally pinned at zero.** `dopey/genome/fitness.py` takes the *minimum* of {causal_confidence, transfer, calibration_quality, settlement_sample_quality, efficiency}. With 4/100 forward closes, `settlement_sample_quality ≈ 0.13` caps every genome forever — by design. The design is honest, but it means the evolutionary loop has **no gradient**: every candidate scores ~0, selection is uniform noise, nothing is learned between cycles.
- **The creativity/theory layers have no input signal.** `theory.py` requires `automatic_cognitive_method_activation_allowed is True`, which nothing can set; the creativity operators are string templates. This is scaffolding for a machine whose engine isn't connected.
- **No calibrated uncertainty anywhere.** The capability survey lists MAPIE (conformal prediction) and ruptures (changepoint detection) as reviewed-but-not-adopted. These are precisely the tools that would convert the one measured skill (avoidance) from heuristic vetoes into *calibrated* abstention with measurable coverage.

### Recommendations

1. **Adopt MAP-Elites or a simple evolutionary strategy over a typed parameter DSL** (the meta-review already flagged doofus's MIT MAP-Elites as a direct-adaptation candidate). Niching dimensions: regime, mechanism family, turnover/cost, failure mode. This turns "12 fixed mutations" into actual search with diversity pressure — the single highest-value algorithmic upgrade available.
2. **Give evolution a real gradient without dishonesty**: keep the weakest-dimension cap for *promotion*, but add a separate, explicitly-labeled **shadow fitness** for *selection* (e.g., replay + walk-forward composite, SHADOW_ONLY evidence class). Selection can be speculative; promotion must not be. The current design conflates the two and gets a flat landscape.
3. **Adopt MAPIE conformal intervals on the context/veto engine.** Output: "avoid this entry with 90% coverage" instead of threshold vetoes. Directly measurable against the veto shadow ledger — and it upgrades the one thing the system is provably good at.
4. **Adopt ruptures for regime segmentation** replacing/validating the hand regime rules in the market-regime family. Cheap, deterministic, offline.
5. **Freeze the cognitive meta-layers** (theory, creativity, evidence cycles beyond maintenance) until a genome produces a non-zero shadow fitness. Meta-cognition about an empty discovery process is organizational debt.
6. Their own P0/P1 items — signed evaluator trust root, point-in-time truth kernel, differential oracle mesh — are correctly prioritized. **The PIT truth kernel also unlocks strategies** (PEAD, fundamentals) that are currently untestable; treat it as a strategy enabler, not just integrity.

---

## 4. Execution

### What exists (strong, keep)

- Forward paper walk: fill at **real ask + commission**, mark at **real bid**, entry/exit relative-spread caps, OI/volume floors — a genuinely conservative retail cost model.
- T+1 settled-funds model, good-faith-violation guard, zero day-trade enforcement, PDT-safe policy, fail-closed paper broker with account ledger.
- `dopey_live/` Robinhood gateway: attestation-heavy, read-only reconciliation live, execution sealed behind evidence + owner authorization. This is correct and should not move.

### Weaknesses (file-level)

- **Always-taker fills.** `forward_paper_walk.py` enters at the ask, exits at the bid. For the spreads DOPEY's long-premium book trades, the spread *is* the strategy's biggest cost — bigger than any signal. There is no lane that asks: "what would a patient limit order have done?"
- **One exit policy for everything** (`-50% / +100% / 3 sessions`, pinned in two places — `exit_policy_config.py` for the historical lane, constants in `forward_paper_walk.py` for the forward lane). The 27-cell exit walk-forward correctly refused its best-train candidate as overfit — and then exit research apparently stopped. One refused search is not an exhausted surface.
- **Live-gate status proliferation**: `dopey_live_gate/` has 14 modules (v1–v7, champion, hardening v3, repair v1, deepening v2) re-implementing the same status pattern. Same disease as the signal-research v1–v7 stack.
- **Model-priced backtest lane** (`model_priced_trade_simulator.py`) is the workhorse for 9,333-trade history, but its pricing fidelity vs real spreads is unvalidated — that's what the meta-review's differential oracle mesh (QuantLib) is for. Until that mesh exists, treat *magnitudes* from the model-priced lane as soft evidence; signs and refusals stand.
- **No execution-quality measurement possible**: zero live fills, so the CLV analogue and execution-quality logger are starved. Expected, but worth stating: execution intelligence cannot improve until fills exist, and fills are (correctly) gated behind the forward evidence that is accruing at 4/100 closes.

### Recommendations

1. **Patient-fill shadow lane** (highest value): alongside every taker-modeled paper entry/exit, record a phantom mid/limit fill with a conservative fill rule (count filled only if the subsequent market traded through the limit price). Output: measured $ value of patience, per family. If patience is worth more than the median signal's gross expectancy, execution research outranks signal research — currently nobody knows.
2. **Exit-policy research program, not a search**: instead of one 27-cell grid, test 3–4 *structurally different* exit families (time-scaled targets, ATR-trailed, thesis-invalidation, premium-decay-aware) with the walk-forward discipline already built. The exit surface is already the whitelisted evolvable surface — use it.
3. **Consolidate `dopey_live_gate/` to one parameterized status module** with per-campaign config, same as the signal-research consolidation.
4. **Do not touch the live branch.** The seal is the product.

---

## 5. Scripts / tooling / ops

### What exists (mostly strong)

- 36-stage resilient supervisor: absorb-record-continue, structured incidents, repair queue, dependency-aware skipping. Last completed run: 24,071s (~6.7h), 0 incidents, 14 stage recoveries vs previous run, 0 regressions.
- Ops layer: Feynman forecast card, kaizen ledger (currently nearly empty: 2 defects — MU 44.3% book concentration breach, one deferred quote), reliability SLO with disk-headroom SLI.
- Nightly test shards: content-addressed, checkpoint-resumable, parallel. Test collection under `.venv`: ~4,206 tests, zero collection errors. CI: manifest + 4 shards + ruff + mutation guard.
- Windows scheduling via Task Scheduler `.cmd`/`.ps1` installers; 33 operator tools.

### Weaknesses

- **Scheduling sprawl**: six separate `install_*.ps1` schedulers (acceleration, durable research, hidden launchers, live branch, operational cadence, research supervisor). The 2026-07-23 commit notes the "first unjammed cycle" — contention was real and only just fixed. Consolidate to **one scheduler manifest** that owns all cadences and detects its own overlaps.
- **12 GB `artifacts/` in-repo.** Working as designed (evidence accumulates), but add a retention/tiering policy: hot (current generation) vs cold (compressed, content-addressed archive). The 115 MB trade-memory JSONL already needed a SQLite projection; the next scaling wall is the artifact tree itself.
- **One-off hype-named orchestrators** in `dopey_autonomy/`: `run_finish_literally_everything_orchestrator`, `run_wealth_engine_full_completion`, `run_remaining_gap_eliminator`, `run_real_public_market_wealth_engine_rerun`. Campaign one-shots. Archive them out of the active package (like the v1–v6 lanes) or delete; they cost reader attention on every audit.
- **Validation sprawl outside the repo**: ~20 `DOPEY_VALIDATION_*` directories + runner scripts in the home dir. Centralize under one `validation/` root with an index; several captured failing runs (e.g., slice miner returning 0 slices) that deserve linked kaizen entries.
- **6.7-hour supervisor run**: most stages finish in <2s, so a few dominate (real_signals, forward walk, memory rebuild). A stage-duration profile + parallelizing independent stages would cut wall time materially; the dependency graph already exists for skip logic.
- **Minor**: bare-interpreter pytest collection dies with 24 `zoneinfo` errors; only `.venv` works. Document in README quick start (it says to use `.venv`, but the failure mode is cryptic) or add `tzdata` to dev deps for Windows robustness.

---

## 6. Cross-cutting observation: version archaeology

The same pattern repeats in four packages: `research_mutation_queue_v1..v7`, `research_holdout_v1..v7`, `research_breakthrough_gate_v1..v7`, 14 live-gate modules, `signal_research_v2..v7_common`. Verified: versions ≤v6 are imported **only** by `dopey_audit/artifact_loader.py` (which needs them to read historical artifacts) — they are frozen archaeology living in the active package. Recommendation: move superseded versions to a `legacy/` package imported only by the artifact loader, or replace the loader's code-imports with schema-only parsing. ~15–20k LOC of active-tree weight, one mechanical change, zero behavioral risk (tests cover the loader).

---

## 7. Prioritized recommendations (constitution-respecting)

| # | Action | Area | Impact | Effort | Evidence risk |
|---|---|---|---|---|---|
| 1 | Patient-fill shadow lane in forward walk | Execution | High — measures the largest known cost | Medium | None (shadow class) |
| 2 | Exit-family research program (4 structural families, walk-forward) | Execution/Strategy | High — only measured skill is exit-side | Medium | None (existing discipline) |
| 3 | Horizon-mismatch experiment: foundry candidates under 5-session holds | Strategy | High — could reclassify part of the 0/144 null | Low | None (backtest lane) |
| 4 | MAP-Elites over typed parameter DSL + separate shadow fitness for selection | Intelligence | High — converts fake evolution into search | Medium-High | None (shadow-only) |
| 5 | PEAD event-study lane from staged earnings/news fixtures | Strategy | Medium-High — strongest known anomaly, absent | Medium | None |
| 6 | MAPIE conformal abstention on veto engine | Intelligence | Medium — upgrades the one proven skill | Medium | None |
| 7 | Cross-sectional rank signals (200-symbol universe) | Strategy | Medium | Low-Medium | None |
| 8 | Point-in-time truth kernel (their P1) — framed as strategy enabler | Intelligence/Data | Medium-High — unlocks 5 & fundamentals | High | None |
| 9 | Consolidate v1–v7 archaeology into `legacy/` + one live-gate module | Tooling | Medium — audit/velocity | Low-Medium | Low (tests exist) |
| 10 | Single scheduler manifest + artifact tiering | Tooling | Medium | Low | None |
| 11 | Supervisor stage profiling + parallel independent stages | Tooling | Medium | Low-Medium | None |
| 12 | Differential oracle mesh (QuantLib) for model-priced lane validation | Execution | Medium — calibrates 9,333-trade magnitudes | Medium | None |

Explicit non-recommendations: more breakthrough-gate generations (V8), more integrity hardening beyond the meta-review's P0/P1, more cognitive meta-layers, any live-branch change.

## 8. Appendix — ideas that require constitutional change (clearly separated)

These violate current law (DOPEY_CONSTITUTION / AGENTS.md). Listed for completeness with what each would require — **none are recommended now**.

1. **Intraday bars + intraday holding periods.** The largest single expansion of the opportunity set: time-of-day effects, opening-range, intraday mean reversion, real 0DTE-adjacent research. Requires: amending the same-session round-trip prohibition, PDT-rule handling for the account size, intraday data vendor, new execution semantics. The 0DTE prohibition is well-founded (fixture-only daily assumptions cannot price intraday gamma risk) and should survive any such amendment.
2. **Enable the options execution lane.** Currently owner-disabled; the unlock gate correctly demands 100 validated forward closes (at 4/100, realistically 6+ months out at current accrual). Requires: evidence + explicit owner re-authorization. Not a code problem.
3. **Purchased point-in-time options NBBO history** (CBOE DataShop / Polygon / ORATS). Doesn't violate the constitution per se, but breaks the "public data only" constraint the V1–V7 campaigns were built under, and the CAPABILITY_CARD states current date-only Yahoo snapshots don't qualify for quote validation. This is the **binding constraint on ever finding an options edge from history** — the NO_EDGE_CERTIFICATE itself says the current dataset "is not eligible to answer whether an options edge exists." If any rule-breaking item is worth its cost, it's this one.
4. **Live limit-order (patient) fills.** Follows naturally from §7.1 *if* the shadow lane proves value, but requires live execution — sealed until the evidence gate opens.
5. **Additional brokers** (dormant Alpaca/Tradier adapters exist). Broker boundary change, banned by AGENTS.md; low value — the Robinhood MCP lane works. Not worth the constitutional surface area.

## 9. Suggested 30 / 60 / 90-day sequence

**Days 1–30 (measure the unknowns, cheap):**
- §7.1 patient-fill shadow lane; §7.3 horizon-mismatch experiment; §7.9 legacy consolidation; §7.10 scheduler manifest. All low-effort, all produce numbers the project currently lacks.

**Days 31–60 (convert measurement into research direction):**
- §7.2 exit-family program (informed by §7.1/§7.3 results); §7.5 PEAD lane; §7.7 cross-sectional ranks; §7.11 supervisor profiling. Decision point: if patient-fill value > median gross expectancy, execution outranks signals for the next quarter.

**Days 61–90 (upgrade the discovery engine):**
- §7.4 MAP-Elites + shadow fitness; §7.6 conformal abstention; start §7.8 PIT truth kernel (multi-quarter, do in slices). Re-run the full honest pipeline end-to-end and diff the scoreboard against today's.

The through-line: DOPEY's honesty stack already knows how to grade any answer. The work now is generating answers worth grading.
