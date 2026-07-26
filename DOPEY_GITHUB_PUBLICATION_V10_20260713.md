# DOPEY GitHub Publication V10

Date: 2026-07-13
Repository: `ObtuseAI/dopey` (private)
Publication branch: `codex/elite-action-hardening-v9`
Review base: `master`

## Published scope

This publication preserves the full authorized private working state produced by the readiness, loss-analysis, strategy-calibration, and V9 execution-hardening sessions. It includes governed real-data snapshots because the target repository is private. The stripped `public-release` branch is intentionally unchanged.

The README now presents the current control contract first, removes the obsolete 60-day creator-context gate, distinguishes current evidence from the representative dashboard image, documents V9 liquidity and portfolio controls, and states the private/public data boundary precisely.

The GitHub repository description is set to:

> DOPEY — fail-closed, equity-first market intelligence and paper-research control plane with multi-timeframe structure, cross-asset/news context, liquidity-aware options selection, matched-cohort validation, and evidence-gated autonomy. No live order path.

## V9 control highlights

- Paper entries reject options with bid below `$0.05`, open interest below `25`, volume below `5`, or bid/ask spread above `10%`.
- Paper exits defer discretionary execution when the observed spread exceeds `25%` and preserve an auditable retry state.
- Forward paper exposure is capped at `12` open positions, `8` units total premium risk, `3` units per sector, `8` options positions, and one open position per symbol.
- Energy shorts are vetoed when active geopolitical evidence can materially tighten supply or raise risk premium.
- Baseline arbitration uses matched policy-eligible cohorts, monthly clusters, and family-wise significance control.
- Action-readiness evidence records versioned entry, exit, portfolio, context, and baseline policies.

## Publication validation

- Focused integration and control-plane suite: `115 passed`.
- Protected public-lake read-only audit: `public_lake_locked_clean`.
- Public lake: `160` symbols, `1,292,545` rows, `0` fixture symbols, `0` test-symbol residue, `0` quality flags.
- Patch whitespace validation: clean when CRLF is treated as the repository's valid end-of-line convention.
- Credential scan: no credential material found in the publication scope; the only credential-like match was documentation for a disabled broker-boundary flag.

## Safety and readiness statement

This is a paper-market research publication. It does not add broker credentials, broker connections, order submission, real-money sizing, or a live execution path. The current evidence state remains fail-closed: `not_action_ready`, promotion blocked, and live trading blocked.

No claim of profitability, production readiness, or guaranteed trading performance is made.
