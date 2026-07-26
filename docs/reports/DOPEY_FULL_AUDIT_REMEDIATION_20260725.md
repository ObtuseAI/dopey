# DOPEY Full Audit Remediation

**Date:** 2026-07-25
**Source audit:** `docs/audits/2026-07-24-full-autonomy-audit.md`
**Scope:** code, tests, evidence contracts, operator tooling, runtime safety,
data integrity, and documentation
**Safety boundary:** no broker call, order placement, credential mutation,
live arming, or Task Scheduler mutation was performed

## Outcome

The audit has been addressed as an engineering remediation rather than a
claim-cleanup exercise. The critical false-green paths, missing research
evaluator, lock wedges, unbounded supervisor run, live control fail-open,
unresolved-order deadlock, stale artifact trust, data recency gaps, CI lint
failures, and quadratic playbook path were fixed and covered by executable
tests.

DOPEY is materially safer and more autonomous as a **paper-market research
system**. It is not represented as an autonomous live trader. Live execution
remains separately operator-armed and fail-closed. A missing
`DOPEY_LiveBranch` scheduled task, attended broker/MCP schema verification, and
several larger architectural migrations remain explicit blockers rather than
being hidden behind green status.

## Validation evidence

| Check | Result |
|---|---|
| Default-branch release suite | **314 passed in 29.43s** |
| Protected-boundary/release suite | **21 passed in 9.17s** |
| CI syntax/error lint gate | **passed** |
| CI first-party lint gate | **passed** |
| Installed dependency consistency | **passed; no broken requirements** |
| Protected manifest verification | **passed** |
| Free space on `C:` | **29.38 GiB** |
| New write-heavy supervisor floor | **20 GiB; fail-closed below floor** |
| Live/broker calls | **none** |
| Scheduler mutations | **none** |

The exact lint gates were:

```text
python -m ruff check . --select E9,F63,F7,F82
python -m ruff check dopey dopey_acceleration dopey_execution \
  dopey_governor dopey_signal_research operator_tools
```

A separate full-repository `ruff check .` still reports 468 issues in old
tests, dead islands, and out-of-scope forked code. The production/CI-gated
surface is clean; the broad archive is not represented as lint-clean.

## Critical findings

| Finding | Disposition | Evidence |
|---|---|---|
| C1 live branch silently unscheduled | **Contained; external action remains** | Dashboard timestamps now age and fault, and live execution has its own process lock and crash tombstone. The `DOPEY_LiveBranch` task is still absent and was not installed without live/scheduler authority. |
| C2 recursive loop never closes | **Fixed for two lineages** | Added deterministic experiment evaluation for `technical_momentum` and `structural_trend`, pinned-history verification, 60/20/20 partitions, after-cost scoring, aggregate-only private selection, external qualification, findings emission, append-only ledger, and cycle-hash idempotency. |
| C3 promotion green on zero yield | **Fixed** | Completion is independent of eligibility; zero eligible records remain an explicit yield state. Scheduler evidence now requires synthesis completion, and reliability evaluates verified success. |
| C4 disk exhaustion gates nothing | **Contained; retention migration remains** | Write-heavy supervisor runs fail closed below 20 GiB. Progress writes are best-effort and whole-run crashes create evidence. Destructive automatic pruning was not added against the active public lake. |
| C5 corrupt lock crash-loop | **Fixed** | Supervisor locks carry UUID, PID, process-start identity, atomic durability, bounded corruption age, recovery journal evidence, and exact-owner release. Ritual marker corruption has the same bounded recovery posture. |
| C6 hung supervisor unbounded | **Fixed in process** | Whole run is capped at 10 hours; each stage receives the remaining budget; later stages become `skipped_run_budget`; PID identity is checked rather than PID existence alone. |
| C7 quadratic production path | **Fixed** | Transfer consistency now groups cases in one pass, and the playbook test supplies its temporary chains root instead of reading the production corpus. |

## High findings

| Finding | Disposition | Evidence |
|---|---|---|
| H1 missing live control fails open | **Fixed** | Missing control now fails closed. Arming is explicit and bound to machine, user, authorization, and path; rearming clears execution options. |
| H2 unresolved reservation blocks exits | **Fixed** | Entries remain blocked, protective exits may proceed, gateway work has a cycle timeout, and an operator reconciliation tool appends a hash-chain-valid broker-verified resolution. |
| H3 unhandled live crash looks green | **Fixed** | The live wrapper writes a `cycle_crashed_unhandled` tombstone before re-raising; dashboard state rejects invalid, future, and stale timestamps. |
| H4 supervisor crash has no incident/retry | **Partially fixed** | Top-level crashes now append incident and repair evidence plus a crash tombstone. Scheduler/VBS restart behavior remains an external operational item. |
| H5 cadence collisions starve tail lanes | **Partially fixed** | Attempts persist before execution; never-successful and stalest lanes are prioritized; whole-cycle budgets bound tail loss; per-lane age SLOs detect starvation. The installed schedule was not moved. |
| H6 hidden VBS breaks kill semantics | **Contained** | Live branch now has an in-process identity lock and crash recovery, preventing wrapper-orphan overlap. Replacing the installed wrapper remains external. |
| H7 repair queues are write-only | **Fixed for persistence/aging** | Incidents and repairs append with run IDs and timestamps; reliability breaches on unresolved items older than 72 hours. Automatic repair execution remains intentionally absent. |
| H8 no stall/yield SLI | **Fixed** | Reliability evaluates attempt and verified-success age at two times lane cadence and treats chronic degraded/timeout states as breaches. |
| H9 coach quarantine is a dead end | **Explicitly bounded** | The deterministic evaluator closes the experiment path for two supported lineages. Coach outputs without an executable lineage remain quarantined and are now documented as reporting-only. |
| H10 activated intelligence files unused | **Architectural backlog** | The docs no longer claim these artifacts alter runtime behavior. No unsafe generic code-activation mechanism was added. |
| H11 shadow candidates never evaluated | **Architectural backlog** | Shadow-only candidates remain non-promotable and are documented as reporting-only until a bounded forward evaluator is implemented. |
| H12 self-improvement only tunes metadata | **Narrow loop preserved** | Cadence tuning remains sealed. Strategy research now has one separate deterministic evidence feedback loop; arbitrary self-editing is not enabled. |
| H13 evidence contracts ignore age | **Fixed** | News and cross-asset evidence expire after 3 hours; quant context expires after 36 hours; dependency state exposes timestamp, age, and freshness. |
| H14 provenance silently stale | **Fixed semantically** | Provenance and data manifests are labeled frozen evaluation-corpus snapshots. The verifier reports source-manifest drift and binding status instead of implying current operational truth. |
| H15 CI ruff gate red | **Fixed** | Removed the three first-party unused import/variable violations; both exact CI lint commands pass. |
| H16 runtime state tracked | **Partially fixed** | Future public-lake runtime state and operator logs are ignored. Removing thousands of already-tracked active-lake files is a controlled repository migration and was not mixed into this dirty production tree. |

## Medium findings

| Finding | Disposition | Evidence |
|---|---|---|
| M1 review-before-place not verified | **Fixed** | Transcript validation requires the exact review call to precede the placement call. |
| M2 market exits falsely quarantined | **Source fixed; attended proof remains** | Market orders accept absent-or-zero limit fields. Live MCP schema validation was not invoked. |
| M3 order-history completeness heuristic | **Strengthened; attended proof remains** | History requires exact `limit=1000`, no filters/cursor, fewer than 1,000 results, and consistent prompts. Broker behavior still requires attended validation. |
| M4 empty OHLCV exits success | **Fixed** | A completed newer session with no eligible provider rows raises rather than reporting current. |
| M5 freshness trusts mtime | **Fixed** | Champion, calibration, and nightly artifacts carry and validate canonical hashes and source-artifact bindings; option/equity quotes remain data-time checked. |
| M6 volatility rewrite erases indices | **Fixed** | Per-index merge preserves failed-index history and refuses material staged regressions. |
| M7 earnings carry-forward expires unsafe | **Verified fail-closed** | Missing or unresolved earnings evidence remains a no-trade condition rather than being treated as clear. |
| M8 macro/risk-free rate never expires | **Fixed** | Macro lanes have recency policies; the short rate rejects future data and data older than seven days. |
| M9 stale quant CSVs remain direct-readable | **Architectural backlog** | Evidence-contract consumers now reject stale manifests, but direct-reader quarantine/carry-forward metadata still needs a storage migration. |
| M10 feedback ledgers never affect decisions | **Fixed for one bounded loop** | Qualified experiment findings now feed the next autoresearch generation. Other advisory ledgers remain advisory. |
| M11 humans behind autonomy claim | **Corrected boundary** | README and canon now say paper-research autonomy and identify live/operator gates; human authority is retained for capital-affecting actions. |
| M12 documentation overclaims | **Fixed** | Current operational truth identifies the two executable lineages and labels coach/genome/shadow paths reporting-only. |
| M13 live blocks retry without age | **Partially fixed** | Dashboard staleness and lane SLOs expose chronic failure. A dedicated per-remediation age panel remains backlog. |
| M14 credential expiry dead end | **Backlog** | No credential mutation or validation was performed; a preflight credential-status probe remains needed. |
| M15 provider has no circuit breaker | **Backlog** | Provider failures remain explicit and stale data is rejected, but automatic provider switching/backoff accounting is not yet a closed circuit breaker. |
| M16 ritual network calls unbounded | **Partially contained** | Supervisor and operator-stage subprocesses are time bounded; some provider-library calls rely on their finite internal timeout rather than a full per-symbol deadline. |
| M17 multi-GB full ledger processing | **Architectural backlog** | Run/disk caps prevent silent machine exhaustion. Cursor processing and compaction remain necessary. |
| M18 runtime dependencies only in dev | **Fixed** | `requests`, `tzdata`, and `yfinance` are declared runtime dependencies; `pip check` passes. |
| M19 weak/vacuous test gates | **Backlog** | New remediation coverage uses real integration fixtures and production-root isolation. Historical vacuous/skipped tests still require a dedicated cleanup. |

## Low findings

| Finding | Disposition | Evidence |
|---|---|---|
| L1 extended-hours/unexpected args | **Fixed** | Per-tool argument allowlists and absent-or-false `extended_hours` validation are enforced. |
| L2 stale live ledger lock | **Fixed** | Operator-confirmed recovery requires the exact path, valid chain, dead PID, and at least 15-minute age; recovery is archived and ledgered. |
| L3 fallback market date | **Verified** | Timestamp conversion uses Eastern market date; extended-hours placement remains forbidden. |
| L4 orphan overlap | **Fixed** | Live operator wrapper uses a UUID/PID/process-start lock with stale recovery. |
| L5 leveraged ETFs use equity caps | **Fixed** | Leveraged ETF symbols are excluded from the plain-equity execution route. |
| L6 dead/self-fulfilling freshness code | **Partially fixed** | Source hashes now bind maturity inputs. Unused helpers remain archive cleanup. |
| L7 option quote has no age bound | **Fixed** | Option quotes must be timezone-aware and belong to the current execution market session. |
| L8 neutral defaults enter gates | **Partially fixed** | Missing/invalid fundamental support is zero and a no-trade reason. Cross-asset NaN normalization remains cleanup work. |
| L9 heartbeat does not prove lane success | **Partially fixed** | Per-lane attempt, verified success, and chronic status now drive SLO breaches. Sentinel calendar normalization remains separate cleanup. |
| L10 news ledger repins hand edits | **Backlog** | Hash verification remains intact; append provenance or immutable source segmentation is still preferable. |
| L11 stale nightly status | **Contained** | Chronic timeout and success-age SLOs now make it visible rather than cosmetic green. |
| L12 30-hour supervisor SLO too loose | **Fixed** | Supervisor freshness is 26 hours. |
| L13 weekly 5-GB disk report only | **Fixed** | Every production supervisor run enforces a 20-GiB write floor. |
| L14 supervisor/ritual contention | **Contained** | Lane success-age SLO catches skipped work; installed schedule coordination remains external. |
| L15 Python version skew | **Backlog** | Runtime and CI version alignment requires pipeline/environment ownership. |
| L16 subprocesses lack timeout | **Fixed** | Git inspection subprocesses in code release are capped at 30 seconds. |
| L17 non-ET fallback | **Fixed by dependency** | `tzdata` is now a runtime dependency; market-session gates use timezone-aware data. |
| L18 hardcoded paths/import shims | **Backlog** | Requires a portability migration outside the safety-critical remediation. |
| L19 yfinance fragility | **Backlog** | Outages fail visibly and freshness gates prevent trust, but provider diversity remains needed. |
| L20 dead islands and report bulk | **Backlog** | Dead surfaces are not represented as active capability; archival/deletion requires a separately reviewed migration. |

## Important implementation surfaces

- `dopey/autoresearch/experiment_runner.py`
- `dopey/autoresearch/run_experiment_evaluation.py`
- `dopey_acceleration/schedule.py`
- `dopey_acceleration/cycle.py`
- `dopey_autonomy/run_resilient_research_supervisor.py`
- `dopey_ops/reliability_slo.py`
- `dopey_live/control.py`
- `dopey_live/service.py`
- `dopey_live/ledger.py`
- `dopey_live/robinhood_gateway.py`
- `operator_tools/operator_live_branch.py`
- `operator_tools/operator_reconcile_live_submission.py`
- `operator_tools/operator_recover_live_ledger_lock.py`
- `operator_tools/operator_fetch_daily_ohlcv.py`
- `operator_tools/operator_fetch_macro_context.py`
- `README.md`
- `DOPEY_CANON.md`

## Current external and architectural blockers

1. `DOPEY_LiveBranch` does not exist in Task Scheduler. Installing it changes
   live operational state and requires explicit operator/live authority.
2. The market-order and order-history MCP transcript contracts need an attended
   broker-schema validation before relying on live exits or account history.
3. Existing tracked runtime data requires a deliberate Git history/index
   migration; `.gitignore` only prevents new untracked churn.
4. Snapshot retention, ledger compaction, and cursor-based processing are still
   required for long-run storage scalability.
5. Fourteen autoresearch lineages, coach dispatch, activated genomes, and
   shadow-to-forward promotion still need individually bounded evaluators.
6. Credential preflight, a provider circuit breaker/diversity layer, and broad
   dead-island/test cleanup remain open.

These are not treated as passing conditions. Until they are completed, the
correct capability statement is: **autonomous bounded paper research with
fail-closed, explicitly governed live execution**.

## Observed scheduler state

The scheduler was inspected read-only:

| Task | State | Last result |
|---|---|---|
| `DOPEY_AccelerationCycle` | Ready | 0 |
| `DOPEY_DailyRitual` | Ready | 0 |
| `DOPEY_Nightly` | Ready | 2 |
| `DOPEY_ResearchSupervisor` | Ready | 0 |
| `DOPEY_WeekendSoak` | Ready | 2 |
| `DOPEY_MondayPreflight` | Ready | not mutated |
| `DOPEY_Intraday` | Disabled | not mutated |
| `DOPEY_LiveBranch` | **Missing** | external blocker |

The nonzero nightly/weekend results and missing live task remain operational
facts; they were not rewritten as success.

## Handoff state

The remediation remains uncommitted for review. The working tree already
contained extensive active-market data and generated-report changes; none were
discarded or reset. No claim is made that every dirty runtime file belongs to
this remediation.
