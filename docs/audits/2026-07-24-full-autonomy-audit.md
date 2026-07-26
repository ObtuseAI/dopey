# DOPEY Full-System Audit — Autonomy, Self-Improvement, Integrity, Reliability

**Date:** 2026-07-24 · **Repo:** `C:/Users/CH/dopey` @ `594018e` · **Scope:** read-only audit, no code changes
**Method:** 1 cartography pass + 5 parallel deep audits (live-execution safety, self-improvement loops, data integrity, bottlenecks/deadends, correctness sweep incl. lint + bounded tests). All findings verified against code with file:line evidence; runtime artifacts and logs inspected live.

---

## Executive verdict

Measured against the stated goals — *fully autonomous, recursively self-improving, no bottlenecks/bugs/failures/deadends/false data*:

| Goal | Verdict |
|---|---|
| Fully autonomous | **No.** The live trading branch is silently unscheduled; several loops require humans (repair queues, credentials, LLM budgets, quarantined placements); chronic failures never escalate. |
| Recursively self-improving | **No.** The autoresearch loop has never closed once (49 generations, zero evaluated candidates). Promotion is green *because it never promotes*. The only genuinely closed self-modification loop retunes scheduler intervals/timeouts — not strategy code, weights, or thresholds. |
| Intelligent / innovative | **Aspirational.** LLM-coach mutation proposals are quarantined into a landfill — no code path ever executes them. "Activated cognitive genomes" are written to files nobody reads. |
| No bottlenecks/deadends | **No.** Disk exhaustion is a near-term dead end (12 GB artifacts, ~4.8 GB/day churn, zero retention, telemetry-only gate). A corrupt lock file crash-loops the whole system until a human deletes it. A hung supervisor wedges everything with no upper bound. |
| No bugs/failures | **Failures are handled honestly, but several wedge states have no recovery path** (reservation crash, corrupt lock, stale ledger lock), CI lint is currently red, and one live stage has a quadratic blowup on production data. |
| No false data | **Mostly strong, with real gaps.** Hash pinning and synthetic-vs-realized labeling are genuinely solid. But dependency gates check status strings without age, provenance pins are stale/broken, an empty Yahoo response exits 0 ("success"), and mtime-based freshness is gameable. |

**What this system actually is:** an excellent *honest measurement and containment* machine — evidence contracts, hash chains, fail-closed gates, stage isolation — wrapped in *aspirational* self-improvement claims. The operational loop (run → measure → guard cadence) closes. The strategic loop (research → evaluate → promote → deploy → learn) is broken at every arrow that would make it recursive.

**It has traded real money:** one GOOGL round trip (bought 2026-07-20 under older, weaker code with +1.1% slippage; owner sold at a loss 2026-07-22). Current code makes that order impossible — the hardening is real.

---

## CRITICAL findings

### C1. The live trading branch is silently unscheduled — and nothing monitors it
`schtasks /Query /TN "DOPEY_LiveBranch"` → task does not exist. `artifacts/dopey/live_branch/latest_cycle.json` last written Jul 23 14:12; the scheduler log referenced by `operator_tools/live_branch.cmd:8-11` has never existed; the acceleration lane `live_branch` shows `inconclusive_timeout` since 2026-07-20. Neither the freshness sentinel (`dopey_data_ingestion/data_freshness_sentinel.py:40-46`) nor the SLO (`dopey_ops/reliability_slo.py`) has a live-branch lane. **The system can stop trading forever with zero detection.**
*Fix:* reinstall via `operator_tools/install_live_branch_schedule.ps1`; add a live-branch freshness lane (RTH-only, amber 1h / red 1 session) to the sentinel or SLO.

### C2. The "recursive self-improvement" core has never closed once
`dopey_acceleration/cycle.py:142-143` points the autoresearch lane at `artifacts/dopey/vnext/research_findings.json` — **no production writer exists anywhere** (grep: only readers). `blocked_cycle_ledger.jsonl` shows generations 38–49 all `blocked_missing_validated_research_findings` (through 07-24); generations 1–37 each queued 24 candidates that nothing ever evaluated. **49 generations, zero evidence-steered iterations, zero activations.** The lane's success contract (`dopey_acceleration/schedule.py:397-405`) is unreachable; it sits permanently at `degraded_evidence` with no `last_success_utc` ever.
*Fix:* wire a deterministic experiment runner that consumes `experiment_ledger.jsonl` and emits validated findings, or delete the lane and downgrade the "recursive" claims.

### C3. The promotion pipeline is green *because* it never promotes
`dopey/promotion/cycle.py:118-141` writes `latest_promotion_cycle.json`; only consumers are the dashboard display and an LLM prompt. `champion_strategies.json` is written only when activations > 0 — it has never been written. The killer detail: the lane's success criterion **requires** `synthesis_status == "complete_no_eligible_records"` (`schedule.py:452-460`). Both promotion lanes report fresh `completed`/`last_success`. Zero promotions since 07-15 is invisible.
*Fix:* success should be `complete` regardless of eligibility count; add a yield SLI alerting on N weeks of zero eligible records.

### C4. Disk exhaustion is a near-term dead end; the "disk SLI" gates nothing that writes
Disk C: 91% used, ~44 GB free; `artifacts/` = 12 GB; **~4.8 GB/day write churn**. Growth sources: snapshot manifests every ~60–90 min (191 in 12 days), 1.5 GB append-only signal ledgers, 1.1–1.5 GB full-ledger rewrites per supervisor run, `stage_results/` forever, `.tmp` orphans (a 527 MB one from 07-23 is still on disk). No retention/prune/rotation anywhere. `reliability_slo.py:49` floor (10 GB) only appends a breach string; its sole consumer (`reliability_guard.py:163-172`) merely blocks cadence *acceleration*. At current churn the floor is reached in ~1–2 months.
The 07-23 ENOSPC already proved the end state **and** exposed a containment hole: the supervisor died inside `_write_supervisor_progress` (`run_resilient_research_supervisor.py:736`, called at `:488`) — its own telemetry write, **outside** the per-stage try/except at `:465` — losing the whole run with no summary, no incident, and a stale `run_status: running` artifact now breaching the SLO.
*Fix:* retention/prune lane (snapshots, stage_results, `.tmp` sweep, ledger compaction); pre-flight disk check in supervisor `main()`; best-effort wrap on progress writes; make a disk breach actually pause write-heavy lanes (soft floor ~20 GB).

### C5. A partially-written supervisor lock crash-loops the entire system until a human deletes it
The lock write is non-atomic (`run_resilient_research_supervisor.py:766-770`). If truncated (disk full, power loss — exactly what ENOSPC produces): the supervisor blocks for the full 24h stale window (`:761-763`), and the acceleration cycle *raises* on the same corrupt lock (`dopey_acceleration/cycle.py:511-523`) — every 15-min invocation exits nonzero, forever. Task Scheduler restarts don't help; the failure is deterministic. Same class: an unreadable ritual marker makes `operational_run_marker.py:31` raise → ritual exits 2 daily.
*Fix:* write the lock via the existing `write_json_atomic`; treat an unreadable lock older than N minutes as stale (delete + log), not preserve-and-raise.

### C6. A hung-but-alive supervisor wedges the whole system with no upper bound
`install_research_supervisor_schedule.ps1:32` sets `ExecutionTimeLimit = PT0S` (unlimited). Liveness is PID-only (`run_resilient_research_supervisor.py:792-813`). Stage subprocesses have a 4h timeout, but a hang *between* stages (multi-GB ledger read, wedged `tasklist`) leaves a live PID holding the lock forever → acceleration defers every 15 min, ritual refuses daily, everything stops. **PID reuse** compounds it: `_pid_running` checks PID existence, not process identity — a recycled PID from an unrelated process holds the lock indefinitely and the 24h stale window does not apply when a PID is present (`:756-764`).
*Fix:* whole-run wall-clock cap (~10h) wired to a killer via the active-run heartbeat (SLO already computes it); record process start-time in the lock and verify against WMI.

### C7. Live stage has quadratic blowup on production data; its test hangs forever and burns CI
`tests/test_playbook_wiring.py:162-168` overrides only `history_root`, so `run_playbook_research_stage` falls through to the **production** chains root (36 MB / 1,443 files). `_transfer_consistency` (`dopey/strategy_engineering/reverse.py:117-128`) re-scans the full case list per group per feature — O(features × groups × cases). Tests killed at 250s incomplete; this file is in CI shard 3, so **CI fails by 30-min timeout on every run**, and the same path runs in the live supervisor `playbook_research` stage, stalling until the hard timeout kills it.
*Fix:* fixture `chains_root=tmp_path` in tests; rewrite `_transfer_consistency` as a single group-by pass; cap cases fed to `infer_reverse_hypotheses`.

---

## HIGH findings

### Live-execution safety

**H1. Missing control file fails OPEN.** `dopey_live/control.py:108-113` auto-creates the user-scoped control file with `live_branch_enabled=True, stock_execution_enabled=True` when absent; the `owner_authorization_id` is a repo-committed constant never validated (`control.py:40-54, 80-105`). A new machine / wiped profile / operator deleting the file believing it stops trading → live execution re-arms itself. (Corrupt files do fail closed.)
*Fix:* missing file must raise; explicit operator arming tool; machine-unique non-default authorization token, validated.

**H2. Crash between reservation and result permanently wedges the branch — including exits — with no recovery tool.** `ledger.py:144-187` (reserve latch) → `service.py:910-911` (unresolved-submission blocks the whole cycle, before exit processing) → broker call at `service.py:1270`. The 12-min Task Scheduler kill (`install_live_branch_schedule.ps1:37`) makes a mid-cycle death plausible (gateway up to ~9 min/intent; maturity gate recomputed twice per cycle). Every later cycle halts; stop-loss/target exits on open positions stop running indefinitely. Recovery requires hand-crafting a hash-chain-consistent ledger record; no tool exists.
*Fix:* operator reconciliation tool that appends the resolving record after manual broker verification; let exits proceed when only entries are unresolved; budget gateway time per cycle / recompute the gate once.

**H3. Unhandled exceptions leave a stale success-looking `latest_cycle.json`.** Only `Robinhood*`/`SettlementModelError` are handled; `LiveSignalError` from corrupt theses, `ValueError` in `_paper_twin_execution_payload` (after reservation latches), stale-lock `LiveBranchLedgerError` all propagate as bare tracebacks. No status is recorded; the dashboard renders the stale green artifact with no staleness check.
*Fix:* top-level handler writing a tombstone `latest_cycle.json` (`cycle_crashed_unhandled`) before re-raise; dashboard flags `generated_utc` older than one scheduler interval.

### Autonomy / operations

**H4. The 07-23 supervisor crash was never retried and left zero incident record.** `research_supervisor.log`: rc=1 at 19:28, no 19:43 restart despite RestartCount 1 / 15min. One transient failure = 23h research outage; the 30h journal-age SLO doesn't even breach. Whole-run crashes produce **no incident** — incidents/repair queue are only written at successful completion (`run_resilient_research_supervisor.py:527-529`).
*Fix:* investigate the VBS wrapper exit-code path (H6); add an acceleration-cycle watchdog that relaunches a dead same-day supervisor when the lock is free; write a crash tombstone incident from the `.cmd` wrapper.

**H5. Runtime-versus-cadence collisions starve lanes systematically.**
- Supervisor: 36 sequential stages × 4h timeout = 144h worst case (6× daily cadence); observed 6–6.7h runs occupy 18:30→~01:00, and the acceleration cycle defers while the supervisor lock is held — so `after_close` lanes (16:45–23:59 window) get only the 16:45–18:30 sliver. They last ran 07-23 ~20:30 *because the supervisor crashed*.
- Acceleration cycle: lane timeouts sum ≈13h baseline (20h+ with retries) vs its 8h task limit; lanes run in fixed order and a killed mid-lane attempt is never persisted — the next invocation restarts the same expensive early lanes; tail lanes can starve for days.
*Fix:* move the supervisor to ~01:00 or give acceleration exclusive 16:45–18:30; order due lanes by staleness/cost; persist `attempt_started` before execution; add lane-staleness SLIs (attempt age > 2× interval = breach).

**H6. The VBS hidden-launcher breaks exit-code and kill semantics.** `run_scheduled_hidden.vbs:39`: Task Scheduler's time-limit kill targets `wscript.exe`; the orphaned `cmd`/`python` grandchild is not guaranteed to die — a "12-minute" LiveBranch python can run past the bell and past market close, and `IgnoreNew` then no longer protects the next instance (the live path has no PID lock of its own). Consistent with H4's missing restart. If `wscript` is blocked by AV/policy, the task fails invisibly (all monitoring is artifact-based).
*Fix:* live-branch PID lock + market-hours guard inside `run_live_branch_cycle`; Monday-preflight check of scheduler last-run result codes; consider a native wrapper that propagates kill signals.

**H7. Repair queues and incidents are write-only, per-run, human-only.** Both JSONLs are rewritten each run (no accumulation, no resolution tracking); `suggested_action` addresses a human; grep confirms no reader. Chronic conditions never escalate — e.g. `agentic_account_reconciliation` reports `blocked_missing_account_snapshot` in journal after journal.
*Fix:* cumulative queue with age; SLO breach on items older than N days; or auto-dispatch idempotent repairs.

**H8. No stall/yield SLI anywhere — the system can spin green forever.** `reliability_slo.py:11-21` measures fetch adherence, freshness, disk — nothing about research yield. Cadence is driven by `last_attempt`, not `last_success` (`schedule.py:836-838`), so lanes that never succeed are never prioritized or alarmed. Current chronic spinners in `schedule_state.json`: `autonomous_strategy_research` (never succeeded), `coached_evolution_cycle` (degraded 2d), `governed_universe_growth` (never succeeded), `nightly_validation` (inconclusive 6.2d), `daily_close_stack` (no attempt 6.8d). Zero actionable theses for a month would only show as a counter in a summary JSON.
*Fix:* per-lane `minutes_since_success` SLIs (already computed at `schedule.py:831-835`, then dropped); zero-output streak detectors for producer lanes; treat chronic `degraded_evidence` like failures in the reliability guard.

### Self-improvement loop breaks

**H9. LLM-coach "innovation" is a dead end by construction.** `mutation_proposals/latest_batch.json`: 0 proposals, coach `abstained: true`; both orphan experiments `BLOCKED_MISSING_LINKED_HYPOTHESIS`; `coached_evolution/latest_run.json` = `blocked_daily_new_session_limit` (1/day paid cap). **No code path executes a quarantined experiment** — the advertised `next_gate: independent_experiment_then_purged_walk_forward` has no implementing lane. Quarantine = landfill.
*Fix:* build the deterministic experiment-dispatch lane already advertised in `schedule.py:194`, or stop claiming coached evolution improves anything.

**H10. "Intelligence research" terminates in files nobody reads.** `dopey/intelligence_research/evidence_cycle.py:1183` writes `activated_cognitive_genomes.json` — zero production readers (only tests). Current artifact: 0 activated genomes. The full loop is discover → benchmark → write file → (optionally) mention to an LLM.
*Fix:* discovery lane must actually load and apply activated methods, or mark the lane reporting-only.

**H11. Strategy engineering churns shadow candidates that are never evaluated.** `latest_cycle.json`: 32 forward candidates, 32 shadow-admitted, `complete_shadow_only` — and the lane contract *requires* shadow-only as the definition of done (`schedule.py:425-433`). Where a challenger needs forward validation, code records `shadow_challenger_forward_validation_required` (`dopey_evolution/sharpness_tuning.py:278`) — and no lane performs it.
*Fix:* shadow → forward-walk promotion path, or cap candidate generation until the backlog drains.

**H12. "Autonomous self-improvement" only retunes scheduler metadata.** `autonomous_improvement.py:26-28` — `SEALED_OVERRIDE_FIELDS = {interval_minutes, timeout_seconds, retries}`; anything else is rejected. The impressive `research_mutation_surface` list at `:254-260` is descriptive text in a coverage record, not code. The system cannot change a single strategy parameter, threshold, or weight. (Within its narrow scope this loop genuinely works — see Solid.)

### Data integrity

**H13. Dependency gate checks status strings only, never age; three intake lanes can be silently stale forever.** `schedule.py:541-570` compares only `artifact[status_key] == required_status`; the news/cross-asset/quant manifest contracts (`:342-376`) have no max-age on `created_at`. If an intake dies, its manifest says `"complete"` indefinitely and the equity-swing dependency gate passes on stale context. The freshness sentinel's lane list (`data_freshness_sentinel.py:35-42`) doesn't cover those three.
*Fix:* `max_age_hours` per evidence contract (timezone-aware `created_at`), or sentinel lanes keyed on data-as-of dates.

**H14. Provenance pins are broken and silently stale.** `ARTIFACT_PROVENANCE.json:9` and `DATA_MANIFEST.json` pin `options_data_manifest.json` at `6ddc39e5…`; the live file now hashes `f3629679…` (rebuilt 2026-07-23, 1,443 chain files — recomputed during audit). `DATA_QUALITY_REPORT.md` still describes "420 files, 85,608 rows, through 2026-07-16" — the corpus has grown ~3.4× past that. Nothing flags the drift.
*Fix:* label these as frozen evaluation-corpus records; CI/ritual check diffing pinned vs. actual hashes.

### Correctness / CI

**H15. Committed code fails the CI ruff gate.** 3 errors on the gated surface, committed in `742419f` (Jul 23): `cross_lane_convergence.py:27` (F401 `math`), `post_snap_read.py:25` (F401 `json`), `self_scout.py:122` (F841 `surfaces`). The lint job is red on any push of this tree.
*Fix:* `ruff check --fix`; delete or use `surfaces`.

**H16. Runtime state is tracked in git.** 2,807 tracked data files under `dopey_data/real`, 1,088 tracked snapshot paths, `operator_tools/research_supervisor.log` tracked and modified; ~60 untracked snapshot dirs not ignored. `.gitignore` covers almost none of it. Perpetual dirty tree, repo bloat, CI tree-pollution guard exposure.
*Fix:* `git rm -r --cached` snapshot/manifest/log paths; extend `.gitignore`.

---

## MEDIUM findings

### Live-execution safety
- **M1. Review-before-place ordering is never verified** — counts only (`robinhood_gateway.py:1276-1285`); a transcript placing before reviewing passes every check. *Fix:* require `calls.index(review) < calls.index(place)`, else quarantine.
- **M2. Equity exit orders (market, `limit_price=0.0`) risk systematic false quarantine** if the live MCP schema omits the limit field for market orders (`robinhood_gateway.py:1107-1123`); test fixtures always include it, so tests can't catch this. After a real placement this becomes the H2 wedge — **exits die**. *Fix:* accept absent-or-0 limit for market orders; validate once, attended, against the live tool schema before any exit is needed.
- **M3. Order-history "completeness" is an agent heuristic.** Complete = no cursor + no filters (`robinhood_gateway.py:669-713`), and the prompt is self-contradictory (`:1641-1665`). Silent server-side truncation would defeat the day-trade guard, overstate settled funds (GFV risk), and permanently block owner-liquidation settlement. *Fix:* explicit large `limit` + returned-count<limit as truncation proof; consistent prompt; history must cover the oldest open position's `market_date`.

### Data integrity
- **M4. Empty-frame OHLCV fetch exits 0.** `operator_fetch_daily_ohlcv.py:189-228, 934-964`: a Yahoo outage returning empty-but-parseable frames for every symbol prints "spine already current" and returns 0. Failed-fetch vs. genuinely-empty-day not distinguished. *Fix:* treat no-eligible-rows on a completed newer session as fetch failure for core symbols.
- **M5. Live ≤36h research freshness trusts mtime/producer timestamps, not data-as-of** (`dopey_live/signals.py:149-167`); rewriting stale content with a fresh mtime defeats the gate for champion/calibration/nightly artifacts (action/release artifacts are protected by in-process recompute). The equity quote ≤60s check *is* data-as-of and solid. *Fix:* bind freshness to embedded content hash or data-as-of date.
- **M6. Vol-term-structure wholesale rewrite erases partially-failed indices** (`operator_fetch_macro_context.py:143-160`): one rate-limited index loses its entire 2-year history; manifest re-pins so all hash checks pass; downstream quietly returns `None`. The Wikipedia lane right below does the correct per-symbol merge. *Fix:* per-symbol merge, or refuse to rewrite on staged-symbol regression.
- **M7. Earnings carry-forward eventually drops chronically-failing symbols from the blackout window** (`operator_fetch_option_chains.py:232-239`, max 2 carried dates); the health sidecar records it but no consumer machine-gates on it — the exact failure mode commit `e3d2791` set out to fix, delayed. *Fix:* fail closed — fresh-fetch failure beyond last carried date = "earnings unknown → blocked".
- **M8. Macro gate validates license/hash/schema but never recency; the treasury risk-free rate has no staleness check anywhere** (`macro_context_gate.py:64-96, 435`; `contract_selector.py:118-128`). On a treasury.gov outage a months-old rate flows into contract scoring indefinitely. *Fix:* per-lane max-age; recency bound in `load_short_rate`; extend sentinel to treasury/FINRA/CFTC files.
- **M9. Failed quant-context sources leave stale unpinned CSVs on disk** indistinguishable from fresh (`quant_context_intake.py:1173-1180`); pipeline status degrades correctly, but direct readers see stale data. *Fix:* carry prior pins with explicit `stale_carry_forward` status, or quarantine.

### Self-improvement / autonomy
- **M10. The celebrated feedback ledgers are measurement-only — none alter a decision.** Kaizen ledger: no production reader. Fitness decision: consumed by reporting only, never a gate. Veto shadow ledger: genuinely measures veto opportunity cost, read only by kaizen (report) and the advisory reclamation bench. Signal calibration: explicitly advisory. The "learns from its mistakes" layer produces beautiful reports; nothing feeds back into a threshold, weight, or gate.
- **M11. Human-in-the-loop behind the "fully autonomous" claim:** manual scheduled-task installation; the entire campaign layer (`run_public_signal_research_breakthrough_v1..v7`, champion hardening, finish-everything orchestrator) appears in neither STAGES nor LANES; all repair queues require humans; paid-LLM lanes are budget-capped (human refills); live trading is human-gated by design (`HUMAN_APPROVAL_CHECKLIST.md` — honest, but incompatible with the claim).
- **M12. Doc overclaims:** README's "designed to become more capable" loop has never completed one evidence-steered cycle; `DOPEY_CANON.md:624` lists alpha-layer recursive improvement that no running mechanism performs; `DOPEY_CANON.md:1026+` repeats ~15× "autonomous source/data admissibility now replaces manual review" for unscheduled one-shot orchestrators; `dopey_oss_miner/` has no runner (dead).
- **M13. Robinhood live path has human-only blocks that retry forever, silently** (`service.py:988-1008` consent/auth blocks with `operator_remediation` strings; order-history and position-ownership blockers hard-block every future cycle). Bounded retries are correct, but resolution is always a human and nothing surfaces the age of the block. *Fix:* dashboard/SLO surface blocked statuses with age.
- **M14. OpenRouter credential expiry is a human dead-end for LLM lanes** (`provider_control.py:363-402` DPAPI key); on expiry the lane degrades forever, retrying every 6h. *Fix:* credential-status check in Monday preflight + SLO lane.
- **M15. Yahoo/yfinance degradation has no circuit breaker; the error budget is permanently exhausted.** Fetch adherence 78.6% vs 95% SLO; budget remaining = −3 and nothing throttles, switches provider, or resets the 14-day accounting. *Fix:* backoff/jitter, degraded-provider path, budget-window reset.
- **M16. Ritual steps have no individual timeouts** — a hung `yfinance` call stalls the ritual up to the 8h task limit (`operator_fetch_daily_ohlcv.py:189`, `operator_fetch_cross_asset_context.py:63` have no explicit timeouts). Saving grace: a killed ritual writes no heartbeat, so the sentinel catches it. *Fix:* explicit timeouts on all network calls.
- **M17. Multi-GB ledger full-file reads/rewrites make stages slow and memory-heavy** (`real_history_signal_engine.py:591-599` parses 1.5 GB per run; `honest_backtester` rewrites 1.1–1.5 GB ledgers per run via `artifact_io.py:28-51`) — this is the ENOSPC mechanism. *Fix:* cursor/incremental processing; ledger compaction.

### Correctness
- **M18. Live-surface runtime deps only declared in `[dev]` extras** — `requests` imported at module level by 5 live modules, `yfinance` by 6 fetch lanes; main deps are just `cryptography` + `exchange-calendars` (`pyproject.toml:13-16, 31, 34`). `pip install -e .` without `[dev]` yields a broken operator surface.
- **M19. Test-gate quality holes:** ≥7 vacuous passes (`if not manifest.exists(): assert True`); 30 `pytest.skip` sites gating integrity checks on baselines absent in CI (the check evaporates instead of failing); 3 test files import dead packages, one of them **in the CI fast subset**; 25 hardcoded `C:/Users/CH` paths in tests.

---

## LOW findings (terse)

**Live safety**
- L1. Attestation ignores `extended_hours` and tolerates unexpected argument keys (`robinhood_gateway.py:1107-1123`) — prompt-injection hole in the last line of defense; currently mitigated by the regular-market gate + TIF `day`. *Fix:* attest absent-or-false; per-tool argument allowlist.
- L2. Stale ledger lock after crash halts all writes forever; dead-PID info recorded but never used (`ledger.py:82-111`). *Fix:* tombstone `latest_cycle.json` on lock failure; operator-confirmed break for dead-PID locks.
- L3. Fallback `market_date` uses ET calendar date, not session date — an owner 24h-market trade 20:00–24:00 ET could evade the day-trade guard (`robinhood_gateway.py:716-726, 778-781`). System itself never trades extended hours.
- L4. Orphaned-process overlap after scheduler kill: `reserve_intent` atomicity still prevents duplicate orders, but concurrent placements of different intents are undesigned territory.
- L5. Leveraged-ETF trade symbols not excluded from plain equity entries (`signals.py:1187-1195`) — could reach 20% single-name exposure vs the 10% cap.
- L6. Dead code (`ledger.py:190-206` `latest_open_date`, zero callers) and a self-fulfilling freshness check (`signals.py:321-325` — the cycle rewrites the artifacts it checks; the real control is recompute-equality, which is sound).

**Data integrity**
- L7. Option contract quotes have no age bound (`signals.py:1000-1007`) — structural; currently unreachable (all strategic option records blocked), but a days-old ask becomes the limit price when the lane opens. Capped by limit-order semantics.
- L8. Neutral defaults feed gates: missing fundamental sub-score defaults to 0.5, which *passes* the ≥0.48 gate (`dopey_equity_swing/thesis.py:107-121`); NaN volume fabricated as 0 in cross-asset (`operator_fetch_cross_asset_context.py:71-72`).
- L9. Sentinel uses naive local dates mixed with XNYS session arithmetic (`data_freshness_sentinel.py:88, 113`); heartbeat proves the wrapper ran, not that lanes succeeded — per-lane exit codes are written into the heartbeat JSON but nothing machine-checks them.
- L10. News event ledger is re-pinned wholesale each run, silently absorbing hand edits (`operator_fetch_news_context.py:264-298`); exposure limited (feeds record counts only; decision-relevant file is fully rewritten and hash-verified).

**Ops**
- L11. Nightly validation lane shows `inconclusive_timeout` since 07-18 — cosmetic state drift (externally owned), masks nightly health.
- L12. Supervisor journal-age SLO (30h) can miss a single crashed run — tighten to >26h.
- L13. Monday-preflight disk check (>5 GB) is weekly and report-only.
- L14. Supervisor-vs-ritual contention can skip the ritual on slow days (one-directional, no deadlock; sentinel catches it at 2 sessions).

**Correctness**
- L15. Python version skew: CI tests 3.11, production venv runs 3.13.13.
- L16. Two subprocess calls without timeout (`deploy_code_release.py:98, 114`).
- L17. Naive-datetime fallback in `operator_intraday.py:60-62` mislabels the RTH gate on non-ET machines without tzdata.
- L18. Portability litter: 21 hardcoded paths probing another user's machine (`C:/Users/chris/...`, `//FRANKENSTEIN/...`); 22 `sys.path.insert` idioms in operator_tools.
- L19. `yfinance==1.5.1` pinned unofficial API across 6 fetch lanes — breakage degrades silently to stale data (intended posture, but silent).

**Structural**
- L20. Dead islands confirmed: `dopey_research_autonomy/`, `dopey_paper_autonomy/`, `dopey_options_autonomy/`, `dopey_openbb_autonomy/`, `dopey_oss_miner/`, `dopey_open_source_vendor/`, `proof_ledger/` (README only), `_forked_*/`, `build/`. Sealed lab `dopey/ascendancy/promotion.py` (3,255 LOC signed L0–L5 promotion) has no scheduled caller; root registries are 1-line stubs. Decorative "cognitive architecture" (`dopey/metacognition|organisms|metabolism|homeostasis|shadows|observatory|world_model/...`) referenced only by tests and stale code backups. ~75 dated root-level report files; `docs/reports/` 222 files. This bulk inflates the apparent size/activity of the system and pollutes search — consider archiving.

---

## Verified SOLID (worth keeping and saying)

**Live-execution safety**
- Idempotency core: `reserve_intent` check-and-append inside a single O_EXCL lock hold; content-addressed intent IDs with no wall-clock — scheduler retries, restarts, and clock changes cannot mint duplicates. Ambiguous placements quarantine, never inferred, `attempt_limit=1`.
- Hash chain re-verified on *every* read, and every append re-reads first; mid-line truncation and clean trailing-record rollback both fail closed (broker cross-checks). Same guarantees on the paper-twin ledger.
- Transcript parser is draconian in the right ways: exactly-one-thread/turn, argument-mutation detection, duplicate-call detection, disallowed-tool rejection, per-call account binding, Decimal equality, credential redaction before serialization. Truncated transcripts and CLI schema drift fail closed.
- Day-trade guard is dual-layer (exits never built same-day + broker-history opposite-side check), broker-sourced, survives restarts; partial fills block conservatively.
- Capital: settled-spendable only, fails closed to zero; Decimal ROUND_DOWN sizing / ROUND_UP limits; per-cycle budget arithmetic verified across all three builders; 10% name / 50% gross / 0.5% risk caps hold.
- Quote hygiene: 60s staleness, future-skew, crossed-quote, 50bps spread, 2% drift, thesis-geometry re-validation at execution.

**Data integrity**
- OHLCV hash pinning spot-verified (8/8 pins match); validation covers content hashes, schema, per-row invariants, dupes, coverage; staged transaction with byte-level rollback; two-copy consistency checked before/after every publish.
- Synthetic-labeling law holds in production: thesis producer hardcodes `not_edge_evidence: True, strategy_promotion_allowed: False`; the only `True` occurrences repo-wide are in tests; all 24 live theses are `no_trade`. No synthetic/shadow result can currently reach execution.
- Option-chain snapshot resolution: exact-frontier match, per-file sha256 with path-escape checks, per-row contract validation, fail-visible blocked records.
- Quant intake point-in-time discipline (`available_at <= decision_at`, future rows quarantined, tz-awareness mandatory).
- News fetch: retries, ≥4-official-source floor else hard fail, zero-event feeds rejected, hash-pinned output verified by consumers.

**Autonomy / operations**
- Stage isolation: subprocess per stage, 4h hard timeout, process-tree kill, 15s heartbeat, atomic result publish.
- Absorb-record-continue, never-pass: failures → incidents, dependents `skipped_dependency`, degraded statuses never inflate the green count; regression/recovery diffing in the journal observed working (14 failed/skipped stages all recovered next run).
- Evidence contracts: lanes cannot claim success without artifact + exact status match; timeouts record `inconclusive_timeout`, not passes.
- **The one true closed self-improvement loop:** cadence self-tuning with fail-closed rollback — hash-chained policy history, sealed override ranges, and it fired for real on 07-24 (16 interval accelerations rolled back on error-budget breach). Narrow, but honest and functional.
- Reliability guard is fail-closed: SLO artifact must be hash-valid, fresh, schema-exact, correctly scoped before cadence acceleration is allowed.
- Atomic writes (temp+fsync+`os.replace`) with append-rollback across the artifact layer.
- Scheduler install hygiene: allowlisted actions and a limited principal. Credentials are never stored. Launcher hashes and postcondition assertions are verified independently.

**Correctness**
- Zero bare `except:`, zero TODO/FIXME, zero `assert`-as-validation, zero mutable defaults, zero `eval`/`exec`/`pickle.load` on the live surface.
- No tracked secrets; API keys DPAPI-at-rest with log redaction. `pip check` clean.
- 229/229 bounded tests passed; nightly harness has a genuine determinism check (fitness run twice, red on divergence); nightly shard runner has timeouts, checkpoints, honest inconclusive statuses.

---

## Priority fix list

**Before letting this run unattended again (this week):**
1. **C1** — reinstall + monitor the LiveBranch task (system isn't trading; nothing would notice).
2. **H1** — control file must fail closed when missing (currently self-arms live trading).
3. **H2 + H3 + M2** — the wedge trifecta: crash recovery tool for unresolved reservations, tombstone `latest_cycle.json` on unhandled exceptions, and attended validation of market-order exit attestation against the live MCP schema *before any exit is needed*.
4. **C5 + C6** — atomic lock writes + unreadable-lock stale handling + whole-run wall-clock cap + PID-reuse defense (one ENOSPC away from a permanent crash-loop).
5. **C4** — retention lane + disk floor that actually gates writers (~1–2 months to the next ENOSPC at current churn).

**To make "self-improving" true (or stop claiming it):**
6. **C2** — wire the experiment runner that produces `research_findings.json`, or delete the lane.
7. **C3** — fix the promotion success criterion; add yield SLIs (days since last eligible record / verified success per lane).
8. **H9 / H10 / H11** — build the deterministic evaluation paths for coach proposals, activated genomes, and shadow challengers — or mark all three reporting-only and correct the docs.
9. **M10** — pick ONE feedback ledger (veto shadow is the best candidate) and wire it into an actual gate/threshold to prove the feedback pattern end-to-end.

**To stop silent data rot:**
10. **H13** — max-age on lane evidence contracts + sentinel lanes for news/cross-asset/quant.
11. **M4 / M8** — empty-frame = fetch failure; recency bound on the treasury risk-free rate.
12. **H14** — re-issue or freeze-label the provenance manifests; add a pinned-vs-actual hash check.

**Housekeeping:**
13. **C7** — fix the playbook test hang + quadratic `_transfer_consistency` (CI is timing out).
14. **H15 / H16** — un-red the ruff gate; untrack runtime state from git.
15. **H5 / H7 / H8** — resolve supervisor-vs-after-close contention; make repair queues cumulative with age-based SLO breaches; add `minutes_since_success` SLIs.

---

## Audit coverage appendix

- **Surface mapped:** ~318,600 LOC first-party Python, 1,694 files, ~80 top-level packages; tests/ = 61k LOC, 3,868 test functions.
- **Actually-running production surface** (where audit depth was concentrated): `operator_tools/` scheduled entry points, `dopey_autonomy/run_resilient_research_supervisor.py` (36 stages), `dopey_acceleration/` (27 lanes), `dopey_live/`, `dopey_equity_swing/`, `dopey_data/`, and the `dopey.{autoresearch,intelligence_research,promotion,settlement,gates,runtime,strategy_engineering}` lane modules.
- **Commands executed on the live machine:** ruff CI passes, bounded pytest shard (229 tests), pip check, schtasks queries, df/du, sha256 re-verification of manifest pins, log/ledger/artifact inspection. No files modified; no broker, live, or MCP functionality invoked; no git mutations.
