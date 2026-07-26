# Agent C CI and Epistemic Ledger Hardening

Date: 2026-07-26  
Scope: CI determinism, cross-platform regression containment, and research-mutation evidence  
Authority: research measurement only; no execution, promotion, broker, or protected-root mutation

## Root causes and controls

| Surface | Root cause | Production control |
|---|---|---|
| CI shard membership | Line-index assignment moved many tests when the manifest was reordered or edited. | Canonical path validation plus `SHA-256(path) mod shard_count`; an added path does not move existing paths. |
| CI coverage proof | A single aggregate collection floor did not prove every shard received every assigned file exactly once. | Per-shard collection, exact assigned-file versus collected-file comparison, cross-shard node-ID uniqueness, non-empty shard enforcement, and the existing 800-test floor. |
| Worktree isolation | `shard_files.txt` was written inside the checkout and then explicitly excluded from the pollution gate. | Shard selections are written under `RUNNER_TEMP`; clean-state checks run before pytest and exact porcelain plus `git diff --check` run afterward with no scratch-file exception. |
| Cross-platform pytest stability | A prior test patched the shared `os.name` module attribute, which made Linux pytest instantiate `WindowsPath` and crash internally. | The current production seam `_runtime_platform_name()` remains process-local; a dedicated regression proves the seam cannot mutate global `os.name`. |
| Mutation self-deception | No dedicated contained ledger converted a measured fitness drop into immutable rollback evidence. | Every record is hash-chained, sequence-bound, content-addressed, head-anchored, research-only, operator-gated, and semantically re-evaluated during verification. Any fitness drop records `rollback_required`. |
| Ledger corruption | A valid-prefix truncation can preserve an internally valid hash prefix unless the expected head is pinned separately. | A content-addressed head anchor pins record count and head hash. Entry tampering, sequence drift, duplicate IDs, malformed JSON, boundary drift, missing anchors, and truncation fail closed. |
| Interrupted anchor persistence | Appending a record can succeed before atomic anchor replacement fails. | The append raises explicitly; subsequent audits report `head_anchor_missing`, every later append is blocked, and history is never silently rebuilt or rewritten. |

## Mutation decision contract

| Measurement | Decision | Rollback required | Authority |
|---|---|---:|---|
| Candidate fitness below baseline | `rollback_required` | yes | none |
| Candidate fitness equals baseline | `retain_baseline_no_improvement` | no | none |
| Candidate fitness above baseline | `eligible_for_operator_review` | no | none |
| Ledger or anchor corruption | `rollback_required` | yes | none |

Every record preserves candidate evidence, forbids history rewrite, and carries
`research_only=true`, `execution_authority=none`, `promotion_authority=none`, and
`operator_gate_required=true`.

## Verification

| Check | Result |
|---|---:|
| Focused CI, process-tree, and nightly-shard tests | 28 passed |
| Deterministic CI manifest | 67 files |
| Shard 1 collection | 20 files / 320 tests |
| Shard 2 collection | 18 files / 272 tests |
| Shard 3 collection | 17 files / 305 tests |
| Shard 4 collection | 12 files / 329 tests |
| Aggregate collection | 1,226 unique node IDs / 0 duplicates |
| CI shard plan SHA-256 | `f1d4ee23e857e2a8129ee36f73289fefcbd8e8e708cfb2456418b92eda669574` |
| Ruff | passed |
| Python compile | passed |
| Workflow YAML parse | passed |
| Bash syntax and live validator | passed |
| `git diff --check` | passed |

## Residual constraints

- The 1,226-node curated CI gate was collected, while the full heavy suite was not executed in this bounded pass.
- Modulo assignment intentionally favors stable membership over equal file counts; the validator rejects any empty shard and reports the exact immutable plan hash.
- The ledger API is ready for mutation producers, but legacy producers must call it before the architecture can claim universal mutation coverage.
- The local head anchor detects accidental or partial corruption. A privileged writer able to rewrite both ledger and anchor can reforge hashes; independently anchored or WORM storage is required for stronger adversarial immutability.
- An interrupted record/anchor transaction remains blocked until an explicit, evidence-preserving operator reconciliation is implemented. The verifier never silently repairs that state.
