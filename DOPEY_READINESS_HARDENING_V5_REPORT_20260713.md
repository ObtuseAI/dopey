# DOPEY Readiness Hardening v5 - 2026-07-13

## Outcome

DOPEY remains `paper_only=true`, `live_blocked=true`, and `not_action_ready`. This pass hardened research reliability and operator truth without lowering evidence thresholds, enabling credentials, connecting to a broker, or exposing an order path.

The main corrected defect was scheduler state that treated a process exit code of zero as evidence success even when the produced news manifest was `partial_explicit_source_failures`. The v5 control plane now distinguishes cadence attempts from evidence-verified successes.

## Delivered Hardening

- Added typed evidence contracts for news and cross-asset intake manifests.
- Added `last_attempt_utc`, `last_verified_success_utc`, `minutes_since_attempt`, evidence verification, and lane status to schedule records.
- Migrated schedule state to `dopey-research-schedule-state-v5`.
- Reconciled the legacy false news-success timestamp into `degraded_evidence` while preserving its real attempt timestamp.
- Kept retry cadence based on attempts so degraded external sources do not create a hot retry loop.
- Kept dependent equity research blocked until both upstream manifests are evidence-complete.
- Added lane-level failed and degraded result records.
- Preserved independent due-lane execution after a lane command fails.
- Made actual command failures return a nonzero scheduler result while degraded evidence remains an explicit completed process state.
- Added v5 cycle result fields for attempted, executed, verified, degraded, and failed lanes.
- Moved execute-mode planning after locked state reconciliation so the saved plan and state agree in the same cycle.
- Bumped the MCP server identity to `0.2.0` for deployment verification.
- Corrected the GDELT query so `natural gas` is an exact phrase instead of two ungrouped terms.
- Disabled the redundant legacy `DOPEY_Intraday` Windows task after exact action-path verification.
- Added a fail-closed installer guard that disables the legacy task only when it has exactly one action and that action is this repo's `operator_tools\intraday.cmd`.
- Updated the README to describe v5 truth semantics and current evidence counts.

## Real Scheduler Proof

The existing `DOPEY_AccelerationCycle` task loaded the new code at 12:50 PM Central and returned `0`.

- state version: `dopey-research-schedule-state-v5`
- news lane status: `degraded_evidence`
- news last attempt: `2026-07-13T17:36:31.565751+00:00`
- news last verified success: absent
- news legacy false success removed: yes
- cycle version: `dopey-research-acceleration-cycle-v5`
- cycle status: `nothing_due`
- broker commands executed: `false`

Task readback after consolidation:

- `DOPEY_AccelerationCycle`: `Ready`
- `DOPEY_Intraday`: `Disabled`
- `DOPEY_DailyRitual`: `Ready`

## Validation

- Targeted acceleration and readiness suite: `7 passed`.
- Python compilation: passed for all changed Python modules and tests.
- PowerShell parser: passed for `operator_tools/install_acceleration_schedule.ps1`.
- `git diff --check`: passed; only Windows line-ending notices were emitted.
- CLI plan smoke: `schedule_version=dopey-research-schedule-v5`, news `last_run_status=degraded_evidence`, no false verified success.
- Repo-local MCP `_system_state()` smoke: v5 schedule policy, news degraded, equity swing blocked, no broker lanes.
- Broader equity/context validation: `21 passed, 1 failed`. The failure is intentionally preserved because the real news manifest is partial; it is not converted to a skip or pass.

## Protected Public Lake

- status: `public_lake_locked_clean`
- active public symbols: `160`
- active public rows: `1,292,545`
- active fixture symbols: `0`
- test-symbol residue: `0`
- restore required: `false`
- broker connection used: `false`
- live trading enabled: `false`

## Remaining Readiness Blockers

- point-in-time context days: `2 / 60`
- resolved context decisions: `0 / 200`
- forward closed paper trades: `4 / 100`
- forward wins: `0 / 4`
- closed net P&L: `-24.862` premium units
- discipline halt: active
- cohort edge, regime robustness, and statistical promotion: not cleared
- compounding multiplier: `0.0`
- news manifest: `partial_explicit_source_failures` because GDELT remains unavailable/rate-limited

These blockers are preserved literally. No synthetic evidence, lower threshold, fake champion, profitability claim, or live-readiness claim was introduced.

## Operator Note

The persistent in-app MCP transport had loaded v4 before this code changed. Its two repo-owned server processes were stopped cleanly, and the Codex host spawned a fresh launcher/worker pair from the updated repo at 12:55 PM. This turn's existing tool proxy remains bound to the closed old STDIO transport; a new Codex session/tool binding is required to call the fresh server through the UI. The repo-local venv path validates MCP server `0.2.0` and the complete v5 `_system_state()` output.

No git commit was created.
