# DOPEY completion polish and operational synchronization report

Date: 2026-07-16

## Outcome

This release completes the feasible non-evidence engineering slice while preserving DOPEY's
paper-only constitution. It does not claim market edge, action readiness, calibration, causal
confidence, or promotion eligibility. Those states remain controlled by real forward outcomes.

## Implemented controls

- Kept the governed operating universe at 200 active validated symbols, with capacity for 250.
- Retained autonomous threshold gates as the default admission, continuation, abstention,
  quarantine, termination, and retirement vocabulary. Protected thresholds can tighten but
  cannot be loosened by research code.
- Added a version-pinned XNYS market calendar bounded from 1990 through 2100 and exposed it
  through the Chronos layer used by settlement. The narrow static fallback is explicitly
  dependency-contingent and fixture-tested through 2028.
- Added a state-preserving code release deployer. It inventories only governed code and
  configuration paths, refuses dirty sources and active leases, protects market/evidence state,
  creates content-addressed backups, copies atomically, verifies hashes, emits manifests, and
  rolls back a partial deployment.
- Made repository correctness checks blocking. CI now performs whole-tree syntax/undefined-name
  checks, strict lint for the governed runtime/operator surfaces, dependency consistency checks,
  and the four-shard operational pytest manifest on `master` and `public-release`.
- Corrected eight latent undefined-name defects found by the new whole-tree correctness gate.
- Added explicit package metadata and repository links and pinned the runtime market-calendar
  dependency.

## Validation

| Gate | Result |
| --- | --- |
| Dependency consistency | `pip check` clean |
| Python compilation | Governed runtime, acceleration control plane, and operator tools clean |
| Whole-tree correctness lint | Clean for `E9,F63,F7,F82` |
| Governed runtime/operator Ruff lint | Clean |
| Focused acceleration/threshold/strategy/research integration | 102 passed |
| Calendar, settlement, and deployment safety integration | 25 passed |
| State-preserving deployment integration | 3 passed, including forced mid-copy rollback |
| Operational CI manifest | 930 passed in 181.13 seconds |
| Full eight-shard suite | `complete_green`: 3,534 passed, 0 failed, 0 errors, 1 explicit skip; fingerprint `449bb3bc6ae8e41bacb5c67ffb656b81724a3a9d28832c583ba25346197acd15`; no checkpoint reuse |
| Shard membership audit | 118 expected files, 118 assigned entries, 118 unique files, 0 duplicates, 0 omissions; every shard's collect-only and executed counts matched |

## Operational synchronization contract

The live operational tree contains append-only evidence, provider artifacts, market-lake data,
schedule state, and operator journals. It must not be reset, cleaned, or replaced by a Git merge.
After the source release is committed and validated, synchronization uses:

```powershell
.venv\Scripts\python.exe -m operator_tools.deploy_code_release `
  --source-root C:\Users\CH\dopey-threshold-frontier `
  --target-root C:\Users\CH\dopey `
  --mode apply `
  --confirmation paper_research_code_only
```

The release manifest and backup root are written beneath the live tree's deployment-artifact
area. Any protected state path in an inventory or an active acceleration lease stops deployment.

## Honest remaining boundary

- 74 vNext predictions are pending; none may be graded before their valid settlement horizons.
- Context contribution remains blocked at 0 of 200 resolved decisions.
- The forward paper sample remains 21 of 100 closed trades; compounding remains disabled.
- Causal cohort and regime robustness have not passed matched, multiplicity-corrected gates.
- Defensible intraday depth and options dealer-state evidence remain data gaps where unavailable.
- Challengers remain experimental or shadow-only until private, external, held-out, and forward
  evidence clears the protected promotion rules and an operator approves positive promotion.

No engineering test can substitute for these evidence requirements.
