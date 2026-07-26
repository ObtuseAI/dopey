# DOPEY Full Audit + Per-Symbol Candidate/Targeting Program — Design Spec

- **Date:** 2026-07-26
- **Branch:** `agent/dopey-audit-targeting-2026w30` (off `agent/dopey-vnext-operational-readiness`)
- **Status:** Approved design (user sign-off 2026-07-26), pre-implementation
- **Posture invariant:** L0/no-edge honesty is load-bearing. Nothing in this program weakens a gate, sentinel, evidence floor, honesty stamp, or the live-book whitelist. All new strategy machinery ships `unvalidated_hypothesis`, earns trust only via forward settlement, and runs shadow-first. "Positive edges across the board" is pursued honestly: fix corrupted measurement, then concentrate attention on symbol×strategy pairs whose per-symbol evidence clears the bar — never by declaring edge.

## Method

Seven parallel read-only audit lanes over the whole repo, every finding required file:line or command-output evidence; prior-memory "fixed" claims were re-verified before being re-reported. Lanes: (1) backtest/forward-walk, (2) signals/foundry/screener/convergence, (3) supervisor/scheduling/ops, (4) data lanes/spine, (5) strategy layer + effectiveness inventory, (6) dopey_live/LLM/security kernel, (7) test health/repo hygiene/bloat.

Current system state anchors (live artifacts): action-readiness gate `not_action_ready` 9/18; forward book 16 open / 33 raw closed (13 validated, 17 stale-censored legacy, 3 quarantined); MU premium share ≈28.6% > 25% cap; supervisor 37 stages in working tree (36 committed); nightly 07-25 exit 2 (2/8 shard timeouts); SLO `error_budget_breached`; disk C: 96% full (23GB free).

---

# PART 1 — CONSOLIDATED AUDIT FINDINGS

Severity: **C**ritical (1), **H**igh (16), **M**edium (33), **L**ow (25+). IDs: L1–L7 = audit lane, n = finding number in lane.

## Critical

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| L3-1 | `kaizen_ledger` stage can never run — placed before its dependency `adversarial_stress` in STAGES; `skipped_dependency` every production run since deployment (b4b26ec) | `run_resilient_research_supervisor.py:326` vs `:330`; live journal 07-25 shows skip; tests check registration, never topology | Move entry after `adversarial_stress`; add topological-order unit test over STAGES |

## High

| ID | Finding | Evidence | Fix |
|---|---|---|---|
| L1-1 | Discipline-halt re-arm anchored to raw closed count (33) but sliced on validated closes (13) — next halt latch silently blinds loss-streak/drawdown protection for ~20 closes | `forward_paper_walk.py:334` vs `:159-166`; legacy-repair path `:173-178` already computes the correct validated anchor | Store validated anchor (`_closed_trade_count_at_halt`) at latch time |
| L3-2 | Weekend soak hard-kills supervisor mid-run by design: 2h timeout vs ≈6.6h real run; observed live 07-25 (orphaned lock, stale "running" artifact, orphaned stage grandchild writing after parent death) | `operator_weekend_soak.py:28` `SUPERVISOR_TIMEOUT_SECONDS=7200`; `artifacts/.supervisor.lock` pid 19304 dead; grandchild result mtime after kill | Timeout ≥11h or reuse <24h completed journal; tree-kill via `taskkill /T`; tombstone on timeout |
| L3-3 | STATUS_KEYS out of sync — 6 stage return keys unlisted (`forecast_card_status`, `kaizen_status`, `slo_status`, `book_quality_status`, `probe_status`, `playbook_stage_status`) → permanently `completed_degraded`; `all_stages_completed` unreachable | `run_resilient_research_supervisor.py:358-391,1153`; producer files e.g. `pipeline_forecast_card.py:126`, `reliability_slo.py:462` | Add the six keys (or per-stage key map); keep `missing_status_field` fallback |
| L4-1 | adjusted_close dividend-seam basis drift: Yahoo restates Adj Close retroactively at each ex-date; spine updater only appends → spurious ≈−yield returns at every seam; 207 adjusted_close consumers incl. foundry | `operator_fetch_daily_ohlcv.py:166-235` (append-only); `indicator_foundry.py:330,378-439` | Re-fetch overlap window (90d) per refresh; flag/restage symbols whose staged adj diverges beyond rounding |
| L4-2 | Interior gaps cement: 10-day fetch window + warning-only `missing_weekdays` → dataset stays `valid_real_dataset` with 37 open gap warnings live | `operator_fetch_daily_ohlcv.py:189`; `history_validator.py:283,306` | Calendar-aware interior-gap error for required symbols; widen refetch window when staged tail lags |
| L4-3 | market_lake stores the same 651MB three times (public/normalized/active byte-identical) + 651MB yfinance HTTP cache inside the governed tree; ≈1.3–1.9GB reclaimable | `cmp` SPY.csv all three equal; `market_lake_public_promotion.py:65-66`; two consumers read different lanes | Collapse to one canonical lane + manifest indirection; exclude/prune HTTP cache |
| L4-4 | Full history validation = 86.1s (sha256 225 files/197MB + parse 1,808,325 rows) paid at 36 call sites — every consumer process re-validates before working | measured; call sites e.g. `history_signal_adapter.py:92`, `real_history_honest_backtester.py:456` | Cache verdict keyed on manifest hash + file hashes; env flag to force full revalidation |
| L2-1 | Scanner fitness drift baseline has look-ahead: at detection day i, trailing drift entries for j∈{i-4..i-1} use closes up to i+4 — docstring's PIT invariant is false; bias is conservative (suppresses real positives) | `scanner_holdout_fitness.py:114-139` vs docstring `:20-21` | Lag the accumulator by FORWARD_HORIZON (accumulate forward of day `index-5`) |
| L2-2 | Incremental signal mode diverges from full recompute when a symbol leaves the spine: removed symbols stay frozen in all 7 family JSONLs and keep trading in backtests; no test covers it | `real_history_signal_engine.py:188-202,210`; consumer `real_history_honest_backtester.py:168-172` | Fail closed to full recompute on `set(sidecar) - set(spine) - CONTEXT_ONLY ≠ ∅`; add test |
| L2-3 | Spine-load census: 8 validated full-spine loads + ≥4 raw re-reads per supervisor cycle (stages are isolated subprocesses, nothing shared) ≈1.6GB hashing + ~4.3M bar validations + ~4.3M bar hashes, then double/triple re-hashing in the signal adapter | loaders at `history_signal_adapter.py:92`, `market_structure_engine.py:60`, `real_history_honest_backtester.py:456`, `market_context_fusion.py:102`, `real_structure_chart_renderer.py:35`, `indicator_foundry.py:476`, `market_simulation_engine.py:193`; raw re-reads `factor_engine.py:59`, `elite_archive.py:101`, `swing_target_discovery.py:60`, `signal_settlement.py:47` | Cache one validated hashed spine artifact per `reproducibility_hash`; all stages consume it; `history_validation` stays sole validator |
| L2-4 | 1.53GB `directional_setup_signals.jsonl` slurped whole by ≥3 stages/cycle (~1.5GB transient RAM each, ~4.3M record parses); incremental appends forever, no rotation | `signal_trade_mapper.py:39` `read_text().splitlines()`; callers `real_history_honest_backtester.py:168-170`, `exit_policy_walkforward_search.py:31`, `signal_settlement.py:141` | Stream-parse; date/symbol-filtered readers for calibration/exit-search; governed compaction preserving provenance |
| L5-1 | Trade-memory outcome stats use premium-dollar PnL interpreted as fractional returns — "catastrophic ≤−0.9" flags a $5 option losing $1; all AVOID grades, the 20/23 scorecard, and 10/10 pre-snap audibles inherit the scale bias | `real_history_honest_backtester.py:140` (`path_pnl` premium units) vs `trade_memory.py:138`, `situational_scorecard.py:52-57,103`, `pre_snap_read.py:116`; fractional field `trade_return_model_units` exists at `:142` unused | Key `_outcome_stats` on `trade_return_model_units`; re-derive thresholds in return space |
| L5-2 | Trade-memory corpus split-corrupted (87,225/321,416 rows = 27% have `path_pnl < −1.0` — impossible for long premium; min −2679 on VIXY reverse-split; 570 rows < −50) and multi-counted (321,416 rows = 186,440 unique economic trades × avg 1.72 family fanout) | streaming scan of `trade_memory_index.jsonl` | Quarantine `|path_pnl| > entry_premium` rows as corrupt; report unique-trade counts beside row counts |
| L5-3 | big_mover dual-framing "arbitration" is vacuous: both setups map to one detector emitting only the favored direction; per-setup trust rows byte-identical (29 pairs, 0 direction mismatches); both families' trust polluted with non-independent duplicates | `playbook.py:283-298`, `playbook_scanner.py:372`; verified on `playbook_settlement_ledger.jsonl` | Emit two opposing-direction records per detection, or record only under favored setup_id |
| L5-4 | Settlement hit-rate samples near-perfectly autocorrelated: 291/291 consecutive same-setup+symbol pairs ≤7 calendar days apart (5-day overlapping windows, daily re-fires); quoted contested n's (240/353) far from independent | ledger scan; `detection_id` includes `as_of_date` by design | Report effective sample size / cluster by symbol×window beside every contested n before "rated" is quoted |
| L7-1 | ~15GB stale pytest basetemp dirs in %TEMP% (21 dirs × ~743MB) — direct ENOSPC contributor; pytest keep-last-3 reaping not working under killed runs/Windows locks; each test session copytrees the 665MB lake | `ls %TEMP%/pytest-of-CH`; `tests/conftest.py:520`; C: 96% full | Delete stale dirs now; add cleanup helper + doc note (isolation copy itself is load-bearing, keep) |
| L7-2 | `artifacts/` = 12GB on disk (gitignored) — largest reclaimable area; no retention policy anywhere | `du -sh artifacts` | Explicit retention policy (this spec, Phase 2) |

## Medium (33, grouped)

**Evidence/measurement integrity**
- L1-2 Censor channel is survivor-tilted (17 censored mean −13% vs validated −8.1%; structural: wide/stale quotes are likeliest deep-loss). Fix: publish censored-at-last-bid sensitivity floor annotation (never gate input).
- L2-5 Fixture lane and real lane write the SAME signal artifact paths; `ensure_upstream_artifacts` backfills fixture content into real paths; `_reusable_summary` checks existence only. Fix: separate fixture filenames or content-sentinel reuse check.
- L2-8 Foundry derived lanes (quote/macro/attention) clear on pooled era-unsplit analytic bar only, weaker than the meta layer they feed; `vix_level` IC 0.30 "cleared". Fix: era-split + shift-null when n allows; label clears "analytic-bar only" until then.
- L2-9 Attention lane clears against the wrong sign (`abs(ic) >= bar`; hypothesis is negative; live artifact clears at +0.055). Fix: signed directional clear.
- L2-10 Elite archive re-selects on same fixed holdout every cycle (best-of-N on one panel, margin ≈1 SE, no multiple-testing control; `HOLDOUT_DATE_STRIDE=5 < FORWARD_RETURN_DAYS=10` overlap). Fix: stride ≥ horizon; trials-count-scaled margin or shift-null.
- L2-11 Scanner fitness silently censors crashing detectors (`except Exception: continue`) — biases fitness upward invisibly. Fix: count exceptions per detector; error budget.
- L5-5 Convergence "corroborated" rests on screener lanes of n=1–2 archetypes; the largest forward sample (flow_positioning n=353) is unmapped in `PLAYBOOK_FAMILY`. Fix: weight/report lane sample sizes; map flow_positioning or state exclusion.
- L5-6 Lane-context hard-codes direction for non-directional states: negative-GEX → `long`, crowded-short → `long` — manufactures the two biggest "anti-predictive" families (gamma_squeeze 40.8% n=240; flow_positioning 42.5% n=353) without ever testing direction as a hypothesis. Fix: emit `either`; let settlement grade the squeeze thesis separately.
- L5-7 Trust `rated` computed on raw settled count, not contested (momentum_trend "rated" with contested=23<30) — contradicts the module's own doctrine. Fix: `rated = contested_settled >= RATED_FLOOR`.
- L6-2 `classify_operational_status("within_error_budget")` → FAILED (healthy-set entry unreachable behind substring pass). Latent today, inverts healthy→failure for any future caller. Fix: exact-match healthy set before token scans.
- L6-3 Resolved readiness bottlenecks reported at severity 1.0 ("remains unresolved") in the cognitive world model (`0 or required → required`). Fix: drop `or required`.

**Ops/reliability**
- L3-4 Acceleration-cycle lock stores bare PID (no start-identity, no age expiry) → PID-reuse permanent jam; unlink races. Fix: port supervisor lock payload.
- L3-5 Soak records previous run's supervisor_status after a kill (stale journal read). Fix: attach only on passed + run_id match.
- L3-6 Repair-queue SLI structurally ungreenable (append-only, no resolution path, 72h age limit → permanent budget breach). Fix: add closed/acknowledged resolution semantics.
- L3-7 `pipeline_forecast_card` `within_band` collapses to `actual >= point` (upper bound dead). Fix: `point <= actual <= upper`.
- L4-5 Validator holiday false-positives bury real gaps (SPY 308 "missing weekdays" = market holidays; all 37 symbols carry permanent warnings). Fix: use `market_calendar.is_trading_day`.
- L4-6 Fabricated quality flags in active-lake builder (`continuity_pass: True` etc. hardcoded without reading a row). Fix: run real `_quality` or stamp `not_evaluated`.
- L4-7 Macro fetcher ~15 non-atomic `write_text` calls; a torn write becomes permanent lane failure. Fix: one `_atomic_write_text` helper.
- L4-8 The 07-23 retry/backoff never reached the spine updater — one transient Yahoo error holds the whole spine for the day. Fix: wrap `collect_new_rows` in `_with_retries`.
- L4-9 Spine-updater stale-lock deadlock (lock has pid/created_at, nothing reads them). Fix: refuse only if fresh + pid alive; else loud takeover.
- L6-1 The 07-25 "closed learning loop" is wired dead at both ends: `active_policy` never carries `research_overrides`, and nothing produces `research_mutation_evidence.json`; the test fabricates the key. Headline feature inert; activation counters overstate. Fix: add key to payload + round-trip test.
- L6-6 Claim compiler drops the API-key redaction (`str(error)` verbatim into committed artifact) used everywhere else in the LLM lane. Fix: route through `_redacted_error_text`.

**Perf/bloat**
- L1-3 Backtest artifact dir 4.8GB (78% no-trade placeholder intents; ~50-key honesty stamps × 4.4M records). Fix: gzip-at-rest for cold ledgers (readers already stream); do NOT drop records/stamps.
- L1-5 Backtest compute fully materializes ~7M records (multi-GB RSS spike); write path is streamed but read/mapping is not. Fix: stream-parse signals, drop raw after mapping, flush per-trade groups.
- L1-6 Ledger hash verification runs 4 full passes/nightly (543MB × 4). Fix: memoize resolution per process.
- L2-6 `_bars_through_date` re-sorts full series per family per eval date (~1.5M sorts/full recompute — the 97-min driver). Fix: sort once per symbol + bisect.
- L2-7 Foundry primitives are O(window) Python loops per eval point (~660M ops MACD alone; EMA restarts per index). Fix: causal O(n) rolling/EMA passes per symbol, same warmup rule.
- L4-10 cross_asset immutable snapshots never pruned (210 runs = 338MB, +1.6MB/day). Fix: retention (last ~10 + monthlies).
- L5-8 `option_extremes_report.json` = 80MB, 67.5MB of it hypothesis case-id strings nothing reads. Fix: count+hash, IDs stay in the ledger.
- L5-9 `expression_selector.py` built and tested but never run by any stage (built ≠ cohesive). Fix: wire into reclamation trigger or mark operator-only.
- L7-3 2807 tracked files under `dopey_data/real/` despite gitignore (the sanctioned index migration never done). Fix: `git rm -r --cached` in a dedicated reviewed commit.
- L7-4 Root sprawl: 80 tracked root files (72 ALLCAPS reports/registries, 21 dated) + duplicate `reports/` (38) vs `docs/reports/` (224). Fix: consolidate.
- L7-5 19 git worktrees, 7 detached `dopey-vnext-clean-*` leftovers. Fix: prune after confirming clean (user decision per worktree policy).

## Low (selected; full detail in lane reports)

L1-7 readiness gate checks halt latch not conditions; L1-8/9 aux ledgers (veto shadow, straddle probe) unguarded JSON reads + silent track-record restart; L1-10 straddle probe no same-day idempotency; L1-11 drawdown computed on non-chronological order; L1-12 pricing constants bind at import (stale mid-process); L1-13 no censor path for persistently unreliable quotes (zombie slot); L2-12 scanner fitness tunes on alphabetical first-40 symbols (A–M selection bias); L2-13 pooled excess double-counts co-fired events; L2-14 screener/playbook/settlement read raw CSVs with no hash check; L2-16 deterministic fixtures rewritten every run + quarantine rescans 13 trees; L2-17 cache adoption relabels provenance gated only by mtime; L2-18 convergence drops `long_put_fundamental_rot`; L3-8 subprocess timeouts not tree-kills in cycle/nightly; L3-9 supervisor early returns invisible in journal; L3-10 dead `_write_json`/`_write_jsonl` + non-fsync `write_json_atomic`; L3-11 unbounded small-artifact accumulation (shard_checkpoints 18 dirs, stage_results 213 files); L3-12 stage-count drift 36 docs vs 37 tree; L3-13 `_is_degraded` marker holes (no live producer); L4-11 spine single-provider (acknowledged; keep anchor check); L4-12 mixed CRLF/LF in spine CSVs (one-time governed normalization); L4-13 lake normalization admits NaN/inf, no OHLC-consistency gate; L4-14 signals/backups 3×75MB same-op backups; L4-15 universe doc drift + empty scaffold dirs + stray manifest drafts; L4-16 manifest path resolution accepts absolute/`..`; L4-17 redundant cross-lane fetches (^VIX, BTC/ETH); L5-11 "either"/"guard" detections accrue forever ungraded (volatility family permanently unrated); L5-12 directional imbalance 643 long vs 44 short graded; L5-13 reclamation bench artifact stale vs code; playbook refresh used day-old spine; L5-14 archetype count drift (53 registered/35 computable/18 data-gapped; docs say 52); L6-7 experiment-runner reuse path doesn't hash-bind findings file; L6-8 `unsupported_lineage_count` mislabels fully-filtered lineages; L6-9 `use_full_available_balance` dead misleading field in sealed schema; L6-10 memory-ledger torn-tail repair drops bytes without evidence trail; L6-11 `dopey_live_gate` 13 versioned gate scripts unmarked active/archival; L6-12 `_execute_policy` treats unknown operation as EMPHASIZE; L6-13 double-write of `latest_cycle.json`; L7-6 `_forked_blunder*` live production deps with staging names at root; L7-7 append-only generated-doc churn keeps tree perpetually dirty (DOPEY_CANON +16/commit); L7-8 package-layout split-brain (~55 flat `dopey_*` vs `dopey/` 29 subpackages); L7-9 tracked tool-config dirs + odd `EXPERIMENT_REGISTRY.jsonl.head.json`.

## Verified healthy (do not "fix")

PnL identity exact (7,143 sampled trades); Black-Scholes core correct; `write_jsonl_atomic_streaming` on the 543MB ledger; 100-close gate counts validated-only, phantom/straddle lanes separate; test isolation (mirror + import hook + closure test) genuinely load-bearing; 4,234 tests collect in 3.54s with zero errors; both known standalone-failure classes already fixed; no look-ahead in signal computation or entry timing; foundry era discipline real (0/144 promoted honestly); screener PIT/snapshot separation clean; promotion gate fails closed; incremental sidecar fails closed on grid drift; transactional spine publish with rollback proof; uniform-advance invariant working; OHLC-consistency gate double-applied; scheduled tasks match install scripts exactly; `inconclusive_timeout` honest end-to-end; supervisor lock recovery handles the live orphaned lock correctly; reliability_guard is a model fail-closed verifier; dopey_live order path fail-closed end-to-end (armed=false defaults, ≤5-min gate freshness, settled-cash sizing, day-trade guard, 1 intent/cycle); codex MCP gateway sandboxing real (per-op allowlists + transcript audit); OpenRouter credential hygiene clean; cognitive-method auto-activation honestly inert; option-cost honesty holds (`corroborated_and_survives_option_costs: []`); settlement ledger append-only idempotent; composite forward-evidence ledger refuses duplicate snapshots.

---

# PART 2 — STRATEGY-EFFECTIVENESS INVENTORY (current measured verdicts)

All numbers carry the Part-1 measurement caveats (esp. L5-1/2/3/4/6, L2-1) until Phase 1 fixes land and lanes re-run.

**Scanner holdout fitness** (`scanner_fitness_last_eval.json`, 11,478 events, overall mean excess −0.0011, deflated score 0.478):
short_term_reversal +0.0094 (944) · capitulation +0.0091 (11) · band_snapback +0.0040 (613) · vcp +0.0033 (190) · box_breakout +0.0017 (64) · quality_pullback +0.0012 (354) · ts_momentum −0.0016 (7,522) · bb_squeeze −0.0039 (119) · week52_high −0.0059 (834) · gap_continuation −0.0077 (141) · channel_breakout −0.0101 (686).

**Screener per-archetype held-out IC** (overall +0.0066 ≈ zero): quality_pullback +0.0186 · momentum_breakout +0.0120 · crowded_fade +0.0077 · fundamental_rot +0.0022 · vol_expansion −0.0076.

**Playbook contested-settlement trust** (687 graded; autocorrelation caveat L5-4): flow_positioning 42.5% (n=353) and gamma_squeeze_flow 40.8% (n=240) and momentum_trend 30.4% (n=23, mis-rated L5-7) anti-predictive; short_squeeze_mechanics 46.0% (n=113) negative; mean_reversion 51.5% (n=33) coin flip; volatility n=2 unrated; small-n: bollinger_snapback 75% (4), short_term_reversal 58.8% (17), gap_go 27.3% (11).

**Cross-lane convergence**: mean_reversion corroborated-positive (scanner +0.0062 n=1922; screener n=2) but **fails option costs**; volatility_compression corroborated-negative; momentum_continuation contested. `corroborated_and_survives_option_costs: []` — no family survives long-option expression portfolio-wide (ATM 30DTE breakeven +1.01%/5d @ IV 0.30; best release angle 0.75% still misses).

**Trade memory** (unit caveat L5-1): stretched_above is the worst entry context for all 5 rated families.

**Key insight for targeting:** costs and edge are both per-symbol (IV calibration AAPL 0.73× vs BAC 1.23×; per-name vol/liquidity). Portfolio-level "no edge" can coexist with per-symbol pockets that clear the bar. That is the honest path to "positive edges across the board": a book where every symbol×strategy pair present earned its place — and everything negative is avoid-graded out.

---

# PART 3 — THE 5-PHASE PROGRAM

## Phase 0 — Branch + disk triage (no repo-logic changes)
1. Branch `agent/dopey-audit-targeting-2026w30` (created).
2. Delete 21 stale `%TEMP%/pytest-of-CH/pytest-*` dirs (~15GB reclaim); add basetemp hygiene note to test docs.
3. Prune 7 detached `dopey-vnext-clean-*` worktrees **only after confirming no uncommitted work** (per standing policy, user confirms each).
4. Artifacts retention policy doc (cold-ledger gzip list, snapshot retention numbers) — policy only; deletion steps executed in Phase 2 with verification.

## Phase 1 — Measurement integrity (~25 fixes; every fix with regression test)
Grouped commits, each with tests:
- **1a Trade-memory truth:** key `_outcome_stats` on `trade_return_model_units`; corruption guard (`|path_pnl| > entry_premium` quarantine, VIXY-class); unique-trade counts beside row counts; re-derive AVOID/catastrophic thresholds in return space; rebuild index; scorecard/pre-snap consume corrected stats. (L5-1, L5-2)
- **1b Settlement/trust truth:** big-mover records once (favored setup_id) or true dual records (L5-3); effective-sample-size (symbol×window clustering) reported beside every contested n and required before `rated` (L5-4); `rated = contested_settled >= RATED_FLOOR` (L5-7); lane_context emits `either` for GEX/crowded states; squeeze thesis graded as a hypothesis, not baked direction (L5-6).
- **1c Scanner/foundry statistics:** drift-baseline horizon lag (L2-1); detector exception counting + error budget (L2-11); stratified/hash-spread symbol cap replacing alphabetical-40 (L2-12, L5-10); event-deduped pooled excess alongside (L2-13); foundry derived-lane signed clears (L2-9) + "analytic-bar only" labeling pending era-split/shift-null (L2-8); elite-archive stride ≥ horizon + trials-scaled margin (L2-10); map flow_positioning + lane sample sizes in convergence headline (L5-5, L2-18).
- **1d Walk/gate correctness:** validated halt-anchor (L1-1); gate evaluates halt conditions or reads conditions-clear stamp (L1-7); guarded reads for aux ledgers (L1-8, L1-9); straddle same-day idempotency (L1-10); chronological drawdown (L1-11); pricing constants resolved at call time (L1-12); censored-at-last-bid sensitivity floor annotation (L1-2); unreliable-quote censor threshold (L1-13).
- **1e Supervisor/ops correctness:** kaizen ordering + topological test (L3-1); STATUS_KEYS + 6 keys (L3-3); soak timeout ≥11h / fresh-journal reuse + tree-kill + journal-status gating (L3-2, L3-5); repair-queue resolution semantics (L3-6); forecast `within_band` (L3-7); cycle-lock port of supervisor payload (L3-4); journal entries on early returns (L3-9); degraded-marker exact-match blocklist (L3-13).
- **1f Data integrity:** dividend-seam overlap re-fetch + divergence flag/restage (L4-1); calendar-aware interior-gap error + adaptive refetch window (L4-2, L4-5); real quality evaluation or `not_evaluated` stamp in lake builder (L4-6); atomic macro writes (L4-7); spine-updater retries (L4-8); stale-lock takeover (L4-9); lake NaN/OHLC gates (L4-13); manifest path containment (L4-16); one-time governed LF normalization of spine CSVs (L4-12); redundant-fetch dedup (L4-17).
- **1g Autonomy/security:** wire `research_overrides` into active_policy + producer for `research_mutation_evidence.json` + round-trip test (L6-1); healthy-exact-match before token scans (L6-2); drop `or required` (L6-3); envelope sentinel: scan `dopey/` kernel + fail-closed `manifest_missing` (L6-4, L6-5); claim-compiler redaction (L6-6); findings hash-binding on reuse path (L6-7); unknown-policy-operation raise (L6-12); single-write `latest_cycle.json` (L6-13); torn-tail repair evidence sidecar (L6-10).
- **1h Signal-lane provenance:** incremental fail-closed on symbol removal + test (L2-2); fixture/real artifact-path separation or content-sentinel reuse (L2-5); spine-hash gate on raw CSV readers (L2-14); cache-adoption content-equality guard (L2-17).
- **Re-baseline:** after 1a–1h, re-run the affected measurement lanes (scanner fitness, screener fitness, convergence, trade memory, playbook trust re-derivation from existing settlement ledger — no gate thresholds touched) so Part-2 numbers are re-stated on corrected measurement. Verdicts may move either way; whatever they say is the new honest baseline.

## Phase 2 — Performance & bloat (behavior-identical, benchmarked)
1. **Shared validated-spine cache** keyed by `reproducibility_hash`: one compact validated artifact (arrays), all 8 validated loaders consume it; `history_validation` stays sole validator; fail-closed on hash miss. Target: ≥50% cycle-time cut on the 86s×8 validation overhead + parse. (L2-3, L4-4)
2. **Stream the big JSONLs:** `load_directional_setup_signals` line-iterator; date/symbol-filtered readers for calibration/exit-search; backtest compute path streams + drops raw after mapping. (L2-4, L1-5)
3. **Signal engine:** sort-once + bisect; benchmark prefix cache. (L2-6)
4. **Foundry:** causal O(n) primitive passes (same warmup/start rule; numerically identical assertion on a sample). (L2-7)
5. **Ledger verify memoization** per process. (L1-6)
6. **Cold-storage:** gzip-at-rest for cold ledgers (intents/inputs/decisions/baseline — readers gain transparent `.gz` support); the 543MB recovery mirror is gzip-at-rest ONLY, never deleted (L1-4 verified its recovery branch unreachable by sha mismatch; L4-14 notes it stays referenced by `trade_records_recovery.py` — compress, keep, keep its manifest); delete 2 of 3 same-op signal backups (L4-14); cross_asset/news snapshot retention (L4-10); option_extremes case-ids → count+hash (L5-8).
7. **market_lake dedupe** to one canonical lane + manifest indirection; HTTP cache excluded/pruned. (L4-3)
8. **Repo hygiene:** reports consolidation (`reports/` → `docs/reports/`); sanctioned `git rm -r --cached dopey_data/real` index migration (dedicated commit); shard-checkpoint/stage-results retention caps; dead-helper deletion (L3-10); doc drift fixes (L4-15, L5-14, L3-12); `dopey_live_gate` active/archival README (L6-11); `_forked_blunder*` README or vendor rename (L7-6); `.head.json` resolution (L7-9).
9. **Wire `expression_selector` into the reclamation trigger** that cites it (or mark operator-only). (L5-9)

## Phase 3 — Per-symbol candidates + forecasting-skill targeting (shadow-first; the headline build)
New package `dopey_targeting/` (new code, no changes to existing selection paths):
1. **`per_symbol_forecast_skill.py`** — for every symbol × {family, detector} point-in-time held-out skill: excess-over-drift, hit rate, rank IC vs forward returns; era-split; block/circular-shift null per symbol; **effective sample size** mandatory (L5-4 discipline); verdicts: `positive_verified | flat | negative_verified | insufficient_evidence`. Data inputs: corrected trade-memory index, scanner fitness per-detector events, playbook settlement ledger, spine. All point-in-time, no look-ahead (reuses the corrected drift discipline from Phase 1).
2. **`symbol_candidate_registry.py`** — every symbol its own candidate: per-symbol profile = {per-family skill verdicts, per-symbol option-cost survival (uses existing per-symbol IV calibration multipliers + `option_expression_cost` cost stack at that symbol's current IV/DTE), liquidity/capacity annotation, data-quality flags}. Targeting score = f(skill verdict, effective-n, cost survival, liquidity) with deadbands; symbols with `negative_verified` on all families → `avoid_graded`.
3. **`shadow_targeting_ledger.py`** — veto-shadow pattern: targeting-ranked candidates open phantom positions via the walk's own injected selection/marking/exit policy; per-symbol targeting classes settle; closes stamped phantom; gate never sees them. Reclamation-bench-style tripwires: a targeting class at effective-n ≥ 30 with positive verified record becomes eligible for human review (recommend-only, never auto-applied).
4. **Supervisor stage `symbol_targeting`** (after `playbook_research`; dep-safe) + advisory soft-read into playbook stage alongside the existing 6 advisory contexts. Artifacts stamped `signal_calibration_not_trade_evidence`-class: `targeting_research_only`, `promotion_allowed: false`, gate-blind (test-asserted).
5. **Forecast-quality feedback:** the better dopey forecasts a symbol (per-symbol skill improving across eras), the higher its targeting weight — implemented as a monotone weight curve with per-symbol deadband and a hard floor at `insufficient_evidence`; targeting concentration caps mirror book caps (sector/direction) so the shadow book stays realistic.

## Phase 4 — Strategy fine-tuning (measure-only, recommend-only)
1. Re-run all three doofus evolvable surfaces (exit trio, screen weights, scanner params) against the corrected measurement baselines; per-symbol conditioning replaces the alphabetical-40 cross-section (Phase 1c). `auto_apply=false` unchanged; evolver recommends, human applies; whitelist discipline (evidence-neutral hyperparams only) unchanged.
2. Per-family parameter studies only where Phase 3 shows per-symbol pockets (e.g. mean-reversion detectors on low-IV symbols that clear costs) — as research artifacts, never promotions.
3. Foundry derived-lane era-split/shift-null upgrade once sample sizes allow (L2-8 follow-through).
4. Update `operator_evolution_status.py` pane with the per-symbol layer.

## Phase 5 — Verification & report
1. Full test suite, PYTEST_EXIT captured directly (pipe-mask lesson); new tests per phase (topological stage order, halt-anchor, unit-space stats, corruption guard, incremental symbol-removal, targeting gate-blindness, shadow/gate isolation, null-discipline in skill scoring).
2. Behavior-identity proofs for perf changes (prefix+tail == full for signal engine; sampled numeric equality for foundry primitives; record-for-record for spine cache).
3. Final consolidated report: audit-fix ledger (finding → commit → verification), re-baselined Part-2 numbers, targeting system first read, remaining risks.

## Constraints & non-goals
- No gate/sentinel/threshold weakening; no live-book changes; no order-path changes; dopey_live stays sealed (its 2 hygiene findings are doc/schema notes for the next sealed-manifest regen, not edits).
- No deletion of other sessions' worktrees/changes without per-item user confirmation; the dirty tree (desktop/, docs/reports/, dopey_squeeze_bubble/, 2 operator_tools fetchers) belongs to another session — left untouched, and Phase commits must not sweep it in.
- No fabricated evidence; no synthetic stand-ins; no promotion claims from shadow lanes; "positive edges" means measured per-symbol verified pockets + avoid-grading the rest.
- `.gitattributes -text` discipline for any sealed/pinned files touched; PROTECTED_MANIFEST regen only if a sealed root changes (none planned).
