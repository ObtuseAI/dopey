# DOPEY GitHub Presentation Release

Date: 2026-07-12  
Branch: `codex/elite-equity-intelligence-v3`  
Scope: complete safe worktree publication

## Outcome

DOPEY's public presentation now accurately leads with the equity-first v3 architecture:
multi-timeframe market structure and stock fundamentals establish direction, cross-asset
and news evidence supply context and defensive vetoes, and options chains select the
strategically tracked strike and expiry only after the equity thesis exists.

The presentation deliberately does not claim profitability, live readiness, or proven
context edge. Paper-only and live-blocked boundaries remain visible in the README, UI,
package description, and GitHub description.

## Presentation surfaces

- Rebuilt the console hero around multi-timeframe structure, evidence, and reproducibility.
- Added live v3 counters for 23 equities, 23 complete structures, 20/20 usable cross-asset
  series, 339 news events, AMD/LCID shadow setups, and the AMD tracked contract.
- Exposed the context evidence gate at 1/60 snapshot days and 0/200 resolved decisions.
- Reframed the README around equity-first authority, global context, news intelligence,
  strategy archaeology, and explicit evidence requirements.
- Updated the package and GitHub descriptions to match the actual system.
- Captured the real localhost console through the in-app browser and replaced
  `docs/images/operator_console.png`.

Screenshot SHA-256:
`bbd2c142acbc8730b0c14b9da6f2b6f174b80c8225e94a0456c55ec1af92b9df`

## Validation

Command:

`.venv\Scripts\python.exe -m pytest tests\test_screener_and_dashboard_v25.py tests\test_equity_first_swing_engine.py tests\test_sharpness_tuning.py tests\test_proof_weighted_aggression_gate.py tests\test_live_trading_disabled_by_default.py tests\test_no_live_artifact_bindings.py -q`

Result: `60 passed in 17.64s`.

Browser verification found no console warnings or errors.

## Safety and truth state

- Credential-named changed files: 0.
- Suspected credential assignments in changed text files: 0.
- Changed files over 10 MB: 0.
- Broker execution: blocked.
- Real orders: unavailable.
- Positive external-context promotion: blocked pending forward evidence.
- Context sizing: blocked pending forward evidence.

## Honest terminal state

`presentation_release_ready_paper_only_live_blocked_context_edge_not_yet_earned`
