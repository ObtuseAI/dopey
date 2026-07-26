# DOPEY OpenRouter Four-Model Hybrid Report

Date: 2026-07-22

## Outcome

DOPEY now has one governed OpenRouter research route, `openrouter_four_model_hybrid`. It runs four required models as a staged council and fails closed if any component is missing or invalid:

1. `parallel_discovery`
   - `google/gemini-3.6-flash` as `evidence_mapper`
   - `openai/gpt-5.6-luna` as `hypothesis_scout`
2. `deep_review`
   - `z-ai/glm-5.2` as `adversarial_auditor`
3. `synthesis`
   - `anthropic/claude-sonnet-5` as `final_adjudicator`

The hybrid policy is `four_model_role_routed_conservative_adjudication`. Gemini and Luna run in parallel. GLM receives their bounded structured records. Claude receives all three prior records. Claude owns the final summary, hypotheses, and experiments; code independently preserves a fair cross-model union of adversarial findings and uncertainties and forces final abstention when any component abstains.

## Intelligent routing

The council selects an explainable focus profile from objective signals while keeping all four required roles:

- `risk_and_execution_integrity`
- `market_hypothesis_and_forecast`
- `data_quality_and_evidence`
- `experiment_and_system_design`
- `general_evidence_ranked_research`

Every result records the selected route, matched signals, route scores, objective hash, exact model roster, ordered stages, role assignments, usage, paid-response count, and redacted response identity evidence.

## Governance and failure behavior

- Public council and MCP entry points accept exactly one canonical aggregate route.
- Individual component routes, duplicate routes, and independent CLI adapters cannot bypass the governed council.
- All four component responses must satisfy the bounded JSON contract.
- There is no fallback model and no partial-success completion.
- OpenRouter calls make at most two attempts per model. The normal worst-case critical path is 1,800 seconds, inside the 2,100-second scheduler envelope.
- Usage and cost from every successful HTTP response are retained, including a response rejected by the structured contract and costs incurred before a later stage fails.
- Eight-item risk and uncertainty caps use deterministic round-robin retention across GLM, Claude, Gemini, and Luna so one model cannot erase every other model's dissent.
- The LLM research cycle makes one hybrid call and reuses its Claude-adjudicated result. It does not make or bill a duplicate synthesis call.
- Model output remains an unverified research hypothesis. This route has no broker connector, order authority, credential readback, promotion authority, or ability to upgrade research readiness.

## Existing OpenRouter configuration and credential

The existing `dopey-provider-control-v1` configuration and Windows DPAPI user-scoped key were reused. Neither file was migrated or rewritten.

| Asset | SHA-256 before and after | Bytes | Last write UTC |
| --- | --- | ---: | --- |
| `provider_control.json` | `f7a79243cbe071194880eab8a6b7de46cd2ec9cec3ee10520c23a48580e9ded6` | 297 | `2026-07-21T07:17:28.8940678Z` |
| `openrouter_api_key.dpapi` | `ba11d296ad253862062807bf42272607e765731677b4e6bcf5ff108f2343c0f5` | 342 | `2026-07-19T02:20:14.2439216Z` |

Credential state now distinguishes `configured` from locally `usable`. Corrupt or undecryptable DPAPI data blocks the route and appears as `KEY UNUSABLE` in the desktop instead of being called ready. The current key separately passed a redacted authenticated OpenRouter key check with HTTP 200. An authenticated model-catalog check found all four exact required model IDs. No plaintext value was printed, logged, returned, or stored in the repository.

## Real governed transport smoke

One bounded paid request used the existing encrypted key and the production four-model route with synthetic non-market state. The prompt explicitly required analysis-only behavior, no market claim, and abstention.

| Proof | Result |
| --- | --- |
| Council status | `completed_all_providers` |
| Component / analysis count | `4 / 4` |
| Per-model attempts | `1, 1, 1, 1` |
| Selected focus | `market_hypothesis_and_forecast` |
| Final abstention | `true` |
| Paid response count | `4` |
| Prompt tokens | `5,427` |
| Completion tokens | `2,328` |
| Total tokens | `7,755` |
| Reported OpenRouter cost | `$0.02429896` |
| Wall time | `24 seconds` |
| Repository write access | `false` |
| LLM route broker/order authority | `false` |

Only redacted topology, count, usage, cost, and hashed response-ID metadata were printed. Model response text was not persisted as part of the smoke.

## Validation

- Ruff on affected Python and test files: passed.
- Python compilation for `dopey_acceleration`: passed.
- Focused merged Python suite: `51 passed`.
- Desktop strict TypeScript typecheck: passed.
- Desktop production Vite build and inline asset integrity check: passed.
- Native desktop smoke check: passed.
- Guarded Windows/PyInstaller release build and packaged executable smoke: passed.
- Scoped Git diff whitespace check: passed; only expected LF-to-CRLF notices were emitted.
- Independent adversarial audit: no unresolved code issue before the paid smoke.
- Existing provider configuration hash after validation: unchanged.
- Existing encrypted credential hash after validation: unchanged.

The rebuilt native release is `desktop/release/DOPEY Control Center.exe`, 44,339,492 bytes, SHA-256 `8cd51cf8958e2567e57eda5f7037bd8fb613c1492988868d8b868e13d14e23fc`. The release manifest records `packaged_smoke_passed=true`. Authenticode remains honestly reported as `NotSigned`, and the release manifest does not claim deployment authorization.

## Operator note

The repository MCP schema now exposes only `openrouter_four_model_hybrid`. A currently running MCP client can retain its old tool schema in process memory; reconnect or restart the DOPEY Frontier Control MCP before using the new canonical route through that client.

No Git commit was created.
