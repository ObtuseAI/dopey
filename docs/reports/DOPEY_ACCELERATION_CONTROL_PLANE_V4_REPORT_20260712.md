# DOPEY Acceleration Control Plane v4 — Session Report

## Outcome

DOPEY now has a paper-only acceleration and agent-control plane spanning governed scheduling, readiness bottleneck ranking, public-lake universe expansion, evidence-gated geometric compounding, local capability discovery, and a client-neutral MCP for Codex, Claude Code, and Cursor.

The implementation raises evidence velocity without lowering readiness, sample, freshness, walk-forward, stress, or context thresholds. It adds no broker connection, credential path, order tool, or live-trading authority.

## Delivered surfaces

- Nine calendar-aware research lanes, woken every 15 minutes by `DOPEY_AccelerationCycle` and self-gated by cadence and market window.
- Locking with live-PID detection, stale-lock recovery, and Task Scheduler `IgnoreNew` overlap protection.
- Dependency-aware swing scheduling: incomplete news or cross-asset provenance blocks downstream swing work before expensive computation.
- A protected-public-lake bridge that discovers locally available stock/ETF history, seeds governed candidates, stages bounded batches, validates once per batch, and promotes only after `valid_real_dataset`.
- A six-symbol governed expansion: VTI, VOO, RSP, MDY, EFA, and EEM moved from candidate to probation after real-history validation.
- A 100-active-symbol ceiling (37 immutable core plus up to 63 probation names), while expansion remains bounded and reviewable.
- Options availability changed from an equity-research prerequisite to contract-selection metadata.
- Geometric compounding research based only on realized forward-paper returns, with quarter-Kelly capped at 5% and disabled until 100 trades plus positive geometric growth.
- Capability discovery across Codex, Claude, Cursor Agent, Ollama, LM Studio, Git, GitHub CLI, Node, uv, installed skills, plugins, and high-value MCP additions.
- Stable MCP `2025-11-25` STDIO server with nine typed tools and default-off execution/frontier gates.
- Cross-client project configuration for Codex (`.codex/config.toml`), Claude Code (`.mcp.json`), and Cursor (`.cursor/mcp.json`).
- Optional isolated frontier-analysis council for Codex, Claude, Cursor Agent, and Codex OSS via Ollama/LM Studio. The council receives evidence state but no repo write authority.
- Installed personal Codex plugin `dopey-frontier-control@personal` with the `operate-dopey` skill and current operator-console screenshot.

## Current truth state

- Action readiness: `not_action_ready`.
- Context evidence: 1/60 complete joint market days and 0/200 resolved decisions.
- Forward sample: 4/100 closed paper trades.
- Compounding: `blocked_insufficient_or_nonpositive_forward_evidence`.
- Observed geometric mean trade return: -0.89928016 across four observations.
- Observed maximum drawdown: 0.99989709.
- Allowed fractional compounding multiplier: 0.0.
- Weekly sharpness: `complete_paper_only`; zero survivors, zero promoted indicators, and zero increased sizing.
- News provenance: `partial_explicit_source_failures`; the swing lane is explicitly blocked until the manifest is complete.
- Protected public lake: `public_lake_locked_clean`, 160 public symbols, 0 active fixture symbols, 1,292,545 active public rows.
- Governed history spine: 43 symbols after six validated probation promotions.
- Additional local public candidates available: 108; the next proposed batch begins AVGO, SMCI, INTC, MU, QCOM, and TXN.

## Scheduler evidence

- Windows task: `\DOPEY_AccelerationCycle`.
- Wake cadence: every 15 minutes.
- Multiple-instance policy: `IgnoreNew`.
- Execution limit: eight hours.
- First task run exposed and preserved an import-path failure in outcome settlement.
- Root repair: all Python operator lanes now run as modules.
- Formerly failing outcome lane then completed with `no_matured_decisions`.
- Weekly sharpness completed successfully and stayed paper-only.
- Subsequent real Task Scheduler wake-up returned `Last Result: 0`.

## Validation

- `23 passed in 2.09s` for focused acceleration-control-plane, universe-governor, and action-readiness tests.
- MCP smoke passed protocol negotiation, tool listing, inspection, and default-off execution denial.
- Real isolated Codex frontier council completed in 22.4 seconds with `completed_analysis_only` and `repo_write_access: false`; its recommendation respected the incomplete-news blocker and unchanged gates.
- `compileall_passed` for acceleration, universe, market-intake, operator, and integration-test code.
- Codex discovered the installed plugin MCP server with both mutation gates set to `0`.
- Claude Code discovered the project MCP and reported pending interactive approval.
- Cursor Agent is not installed; `.cursor/mcp.json` passed static JSON validation.
- Official plugin validator: passed.
- Official skill validator: passed.
- `git diff --check`: passed after line-ending normalization.
- Broad `pytest -q -m "not slow"`: `inconclusive_timeout` at the 600-second cap with no terminal summary. Surviving pytest wrapper/child processes were explicitly contained. This is not counted as a pass.

## Capability expansion recommendations

High-value additions identified but not silently installed are Context7 MCP for current library documentation, GitHub MCP for structured repository operations, and Chrome DevTools/Playwright MCP for UI and pipeline verification. Codex and Claude are available locally. Cursor Agent, Ollama, and LM Studio are currently absent; installing one of the local model runtimes would activate the optional cloud-independent `codex_local` frontier lane.

## Boundaries preserved

- Paper research only; live trading remains blocked.
- No broker or order tools exist in the MCP.
- No credentials were written.
- No synthetic evidence was used to satisfy readiness.
- No threshold was reduced.
- Publication was authorized in the follow-up: the full implementation is committed and pushed on `codex/acceleration-control-plane-v4`, with draft PR #3 targeting `master`; the data-stripped landing README and cache-busting screenshot were committed separately to `public-release`.
