# DOPEY LLM Frontier Utilization Report

## Outcome

DOPEY now uses its existing user-scoped OpenRouter configuration as a durable,
state-change-triggered research council. The live provider routes are:

- `minimax/minimax-m3` at `high` reasoning;
- `z-ai/glm-5.2` at `xhigh` reasoning;
- `gpt-5.6-sol` at `xhigh` reasoning as the adjudicator.

The OpenRouter key remains outside the repository. This work verified only that
`OPENROUTER_API_KEY` is present at process and user scope; the value was never
printed, copied, written to an artifact, or added to configuration.

Current OpenRouter model identifiers were independently verified from the
[MiniMax M3 model page](https://openrouter.ai/minimax/minimax-m3) and the
[GLM 5.2 model page](https://openrouter.ai/z-ai/glm-5.2).

## Runtime Architecture

The `llm_frontier_research` schedule lane runs every six hours when due.
It reads a bounded semantic snapshot of current DOPEY evidence, including:

- readiness and the 200-symbol active-universe state;
- the shared market world model;
- pending forward predictions and settlement state;
- equity and options extremes, including gainers and losers;
- swing-engine evidence;
- strategy invention, reverse engineering, and promotion evidence;
- cognitive-method evaluation evidence.

MiniMax M3 and GLM 5.2 analyze that state independently. Both reviews are
mandatory. Codex then receives only their structured reviews and constitutional
constraints and adjudicates disagreements, unsupported novelty, uncertainty,
and proposed experiments. A partial one-review council cannot publish a new
complete artifact.

The lane hashes semantic state. Identical state reuses the last complete result
without another provider call. The verified unchanged-state path completed in
`0.103` seconds.

## Latest Complete Deliberation

Artifact:
`artifacts/dopey/llm_research/latest_cycle.json`

- cycle status: `complete_analysis_current`
- analysis action: `generated_forced_refresh`
- discovery providers completed: `2 / 2`
- synthesis providers completed: `1 / 1`
- MiniMax attempt: `1`
- MiniMax usage: `39,209` prompt, `5,758` completion, `44,967` total tokens
- GLM attempt: `2` (attempt 1 was rejected for violating the bounded-array contract)
- GLM usage: `39,620` prompt, `3,546` completion, `43,166` total tokens
- latest completed OpenRouter cost reported by the API: `$0.02412042`
- synthesis experiment count: `4`
- paper only: `true`
- live blocked: `true`
- automatic activation count: `0`
- automatic promotion count: `0`

The adjudicated conclusion was that no strategy or trading experiment is
justified from current evidence. The highest-information safe task is a
point-in-time breadth audit, followed by settlement reconciliation and passive
forward accrual under unchanged gates.

The reported cost is for the latest completed artifact only. Earlier provider
probes, rejected outputs, and failed refresh attempts may have incurred charges
that are not represented in that artifact.

## Governed Intelligence Handoff

The current synthesis was ingested into the deterministic intelligence research
engine as unverified hypotheses:

- LLM-derived knowledge signals: `8`
- total knowledge signals: `13`
- discovery questions selected: `8`
- cognitive hypotheses produced: `16`
- governed paper-only experiments queued: `16`
- automatic cognitive-method activations: `0`

The LLM cannot grade itself, promote a candidate, relax a threshold, change
readiness, expand permissions, construct an order, or access a broker. Settlement,
held-out evaluation, provenance, and constitutional gates remain authoritative.

## Control Center

The desktop Control Center now exposes:

- council status and analysis action;
- the three contributing model routes;
- the adjudicated summary;
- proposed experiment count;
- abstention state;
- reported OpenRouter cost.

The native package was rebuilt and smoke-verified:

- executable: `desktop/release/DOPEY Control Center.exe`
- SHA-256: `172267eeb867ffce98c6c9608361ba81d3d9fd4366f75c74b40f383ed63e5206`
- packaged smoke: `pass`
- live execution enabled: `false`
- desktop shortcut: `C:\Users\CH\OneDrive\Desktop\DOPEY Control Center.lnk`
- shortcut launcher: hidden PowerShell invocation of `desktop/launch_desktop.ps1`

The updated application was reopened after packaging.

## Resilience Corrections

- OpenRouter responses are validated against a strict JSON contract.
- Malformed or overlong results are retried and never silently accepted.
- Provider errors include model, attempt, status, and redacted response context.
- Codex subprocess input and output are explicitly UTF-8 on Windows.
- The Windows acceleration-lock liveness check now uses `tasklist.exe`; a live
  scheduler PID reports an active cycle instead of raising `WinError 87`.
- The scheduled lane is evidence-verified from
  `cycle_status=complete_analysis_current`.
- Research execution remains disabled in MCP configuration while analysis-only
  frontier delegation is enabled.

## Validation

- Ruff on all changed Python surfaces: `pass`
- Python compileall: `pass`
- acceleration, intelligence, and desktop integration suite: `23 passed`
- desktop TypeScript and Vite production build: `pass`
- source desktop smoke: `pass`
- packaged desktop smoke: `pass`
- scheduled `llm_frontier_research` lane: `completed`, evidence `verified_complete`
- control-center source boundary: `paper_only=true`, `live_blocked=true`
- git diff whitespace check: `pass`

## Files

Core implementation:

- `dopey_acceleration/frontier.py`
- `dopey_acceleration/llm_research.py`
- `dopey_acceleration/run_llm_research.py`
- `dopey_acceleration/schedule.py`
- `dopey_acceleration/cycle.py`
- `dopey_acceleration/mcp_server.py`
- `dopey/intelligence_research/dopey_adapter.py`
- `dopey/intelligence_research/run_intelligence_cycle.py`

Operator surface:

- `dopey_dashboard/control_center_state.py`
- `desktop/src/types.ts`
- `desktop/src/state.ts`
- `desktop/src/views/CommandView.tsx`
- `desktop/src/styles.css`
- `.codex/config.toml`
- `README.md`

Focused validation:

- `tests/test_acceleration_control_plane.py`
- `tests/test_intelligence_research_engine.py`
- `tests/test_desktop_control_center.py`

## Shared Handoff

The reviewed source snapshot, latest complete LLM artifact, report, manifest,
tests, and rebuilt desktop executable were copied to both available shared
destinations:

- `C:\Users\CH\Desktop\Shared Folder\DOPEY_LLM_FRONTIER_20260718-210125`
- `\\FRANKENSTEIN\Shared Folder\DOPEY_LLM_FRONTIER_20260718-210125`

Each packet contains `22` files. The copied executable at both destinations
matches SHA-256
`172267eeb867ffce98c6c9608361ba81d3d9fd4366f75c74b40f383ed63e5206`.

## Boundary

DOPEY remains `not_action_ready`, paper-only, and structurally live-blocked. LLM
utilization improves research generation, adversarial review, uncertainty
identification, and experiment ranking. It does not create evidence or trading
authority.
