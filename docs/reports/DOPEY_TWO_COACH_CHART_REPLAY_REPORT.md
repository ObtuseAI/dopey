# DOPEY Two-Coach Chart Replay Report

Date: 2026-07-22

## Outcome

DOPEY now has a research-only two-coach chart workflow. Claude is the default head coach through the existing fixed OpenRouter four-model hybrid. Codex is an explicit selectable alternative. The system never silently falls back between them.

The deterministic Evidence/Replay Coach owns every chart structure, numeric fact, replay boundary, and eligible prior-trade lesson. The selected head coach may interpret those registered facts but cannot invent price levels. Every referenced structure, level, and lesson is resolved and validated before the result is accepted.

## Reddit Review

Adopted from the reviewed Reddit workflow:

- raw OHLC rather than screenshot geometry as the source of numeric truth;
- deterministic chart-structure detection;
- point-in-time retrieval of prior completed trades;
- blind replay with future bars separated from the coach input;
- viewport, zoom, and device-pixel-ratio invariance testing;
- validation of every model-produced numeric statement against detector output.

Not adopted as evidence:

- unsupported claims of extreme accuracy;
- image-derived or model-authored price levels;
- treating coach agreement as independent market evidence;
- inferring option returns from underlying-only OHLC;
- granting order, broker, strategy-promotion, or live-execution authority.

Source: https://www.reddit.com/r/ai_trading/comments/1v2lhkp/i_integrated_claude_into_my_trading_setup_to/

## Implementation

- `dopey_chart_vision/grounded_structure_engine.py`: hash-addressed swings, market structure, fair-value-gap candidates, sweep candidates, order-block candidates, Fibonacci levels, trend channels, and blind replay evidence.
- `dopey_analysis/two_coach_engine.py`: point-in-time lesson retrieval, evidence packets, strict references, numeric-literal rejection, append-only session auditing, and two-coach execution.
- `dopey_acceleration/frontier.py`: explicit `claude` and `codex` head-coach selection. Claude retains the exact canonical four-model OpenRouter topology; Codex uses the existing read-only CLI adapter.
- `dopey_dashboard/chart_state.py` and `dopey_dashboard/desktop_app.py`: chart evidence and desktop API wiring.
- `desktop/src/views/ChartView.tsx`: coach selector, grounded structure registry, proof strip, analysis panels, and research-only authority disclosure.
- Supporting typed bridge, normalization, styles, release-manifest, and focused integration tests.

## Verified

- Focused chart/frontier/desktop Python suite: `57 passed in 18.71s`.
- Broader acceleration/playbook integration suite: `37 passed in 237.99s`.
- Ruff on the changed Python surfaces: passed.
- Python compile validation: passed.
- Desktop TypeScript typecheck: passed.
- Vite production build and inline local-document build: passed.
- Native source smoke: passed with `get_chart_coach` in the exact narrow API surface.
- Isolated PyInstaller build and packaged smoke: passed.
- Packaged executable: `desktop/release/DOPEY Control Center.exe`, 45,013,595 bytes,
  SHA-256 `8013bac5835b7af48e4a3eefdefc9541f15dd94cd7a32b60d619b393df075d85`.
- Release manifest records `packaged_smoke_passed=true`, `server_started=false`, and
  Authenticode status `NotSigned`.
- OpenRouter provider-control SHA-256 remained `f7a79243cbe071194880eab8a6b7de46cd2ec9cec3ee10520c23a48580e9ded6`.
- Encrypted OpenRouter key-file SHA-256 remained `ba11d296ad253862062807bf42272607e765731677b4e6bcf5ff108f2343c0f5`.

The focused suite includes twenty viewport/zoom/DPR invariance cases, look-ahead separation, confirmation-lag checks, point-in-time balanced lesson retrieval, unknown-reference rejection, numeric-literal rejection, explicit no-fallback behavior, and exact Claude hybrid identity.

## Real Head-Coach Smoke

The first real run failed closed in the parallel discovery stage. The original
model input duplicated current and frozen registries and produced an approximately
83.9 KB first-stage prompt. Gemini returned malformed/truncated JSON twice. The
failure ledger preserved three paid response IDs, 136,161 tokens, and cost
`$0.29914075`; no coach result was accepted.

The root fix keeps the complete local audit packet while transmitting a compact,
no-reveal projection. The verified SPY daily projection includes all 31 structures,
all 59 registered numeric facts, and the one eligible validated prior-trade lesson
in 18,780 bytes. Every component prompt is capped at 48,000 bytes before a paid
request. Replay reveal values are absent, and accepted citations must be present in
both the projection and the authoritative local registry.

The second real run completed the exact required route:

- Gemini 3.6 Flash evidence mapper;
- Luna 5.6 hypothesis scout;
- GLM 5.2 adversarial auditor;
- Claude Sonnet 5 final adjudicator.

It completed in 619.1 seconds with one audited Gemini contract retry, five paid
responses, 81,430 tokens, and cost `$0.26906345`. The accepted state was
`complete_research_coaching` with verdict `revise`, 46 reference occurrences,
16 unique registered references, `verified_no_free_numeric_literals`, no runtime
fallback, and the option evidence blocker preserved. Total spend across the failed
and successful smoke attempts was `$0.56820420`.

Claude is therefore the live-smoked default head coach. The installed Codex
read-only adapter, explicit selection, exact model identity, and no-fallback path
are covered by local contract tests; a separate full Codex model call was not made.

## Authority and Claims

The repository's overall desktop runtime truthfully remains in its separately
authorized `LIVE` operating mode. This chart-coaching subsystem is still strictly
research-only: it has no broker access, order authority, sizing authority,
parameter mutation, or automatic strategy promotion, and it does not import or
modify `dopey_live`.

No market-accuracy, option-P&L accuracy, edge, wealth-compounding, or live-readiness
claim is made from these tests or model opinions. Underlying-only OHLC remains
insufficient evidence for 0DTE or weekly option outcome claims. The implementation
is left uncommitted for review.

## Shared Handoff

The review packet was copied to
`\\FRANKENSTEIN\Shared Folder\DOPEY_TWO_COACH_CHART_REPLAY_20260722_055442`.
It contains 25 source, test, evidence, report, and release payloads plus
`SESSION_COPY_MANIFEST.json` and its SHA-256 sidecar. Every copied payload was
rehashed at the destination and matched its source.
