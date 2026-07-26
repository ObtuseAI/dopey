# DOPEY Evidence Intelligence Ascendancy Report

## Commander summary

DOPEY now has one cohesive, paper-only evidence-intelligence system spanning settlement,
strategy evaluation, mutation search, options-pricing validation, autonomous scheduling, and
the native control center. The system converts existing research output into auditable evidence
without elevating model-priced options results into realized or executable proof.

The current scientific result is deliberately negative: 12 strategy cohorts produced no
eligible candidate. Five nondominated candidates remain visible as a diagnostic Pareto frontier,
but promotion is blocked because all 285,301 option observations are model-priced and none are
quote-priced. Fitness remains `hold_no_promotion`; truth remains
`insufficient_real_evidence`; live execution remains sealed.

## Implemented system

### Strategy Evidence Dossier

`dopey_reporting.strategy_evidence_dossier` streams the full trade ledger and emits a
content-addressed run under `artifacts/dopey/runs/<run_id>/`. Every run contains a manifest,
summary, fold metrics, compact trades, equity curve, drawdowns, exposures, robustness tests,
failure modes, scorecards, a Pareto frontier, and a standalone HTML report.

Hard gates precede ranking. The scorecard tracks the full mutation search volume, family and
matched baselines, cost stress, fold dispersion, drawdown, confidence bounds, and source hashes.
Annualized return and Calmar are intentionally unavailable because model-unit P&L has no valid
capital denominator.

Latest verified run:

- run ID: `dossier-98655fd13b9a23d5ba28`
- cohorts: 12
- eligible candidates: 0
- diagnostic frontier candidates: 5
- model-priced trade observations: 285,301
- recorded mutation attempts: 2,988 across 88 registry generations
- gross model-unit P&L: -2,832.440376
- modeled costs: 158,589.276727
- net model-unit P&L: -161,421.717103

These values are diagnostics, not returns, expected profit, or deployable edge.

### Mutation Genealogy Explorer

`dopey_evolution.mutation_genealogy` converts the immutable mutation registry into a typed
parent-child graph with node status, mutation mechanism, rejection reason, behavior signature,
duplicate groups, family budget allocation, and the dossier's diagnostic frontier. The current
graph has 40 nodes and 36 edges while preserving all 2,988 historical attempts.

The search is described accurately as a deterministic, budgeted mutation graph. It does not
claim A* guarantees because the noisy strategy landscape has no defensible admissible
distance-to-optimum heuristic.

### Binomial Options Oracle

`dopey_options.binomial_oracle` implements the Cox-Ross-Rubinstein model for European and
American calls and puts, continuous yield, bounded exact discrete cash dividends, early-exercise
nodes, delta, gamma, theta, no-arbitrage bounds, and defined-risk vertical payoff limits.

The latest oracle validation passed 10 of 10 invariants, including Black-Scholes convergence,
put-call parity, American exercise relationships, strike and volatility monotonicity, dividend
early exercise, and capped vertical loss. Its contract is explicit:

- theoretical pricer: implemented;
- historical market replay: not substituted;
- execution/fill simulator: not substituted;
- source tier: `model_priced_oracle`;
- promotion allowed: false.

### Resumable Selective Settlement

`dopey_equity_swing.context_settlement` verifies the frozen dataset manifest and loads only the
hash-pinned symbol files needed by a bounded rotating decision batch. It preserves the immutable
decision ledger and append-only outcome truth while preventing early pending rows from starving
later decisions.

The latest run selected all four pending decisions, hash-validated three symbol files, loaded
18,653 real history rows, and completed with no synthetic outcomes. No decision had matured by
the 2026-07-17 evidence frontier, so the correct result remains four unresolved decisions.

### Autonomous and desktop integration

The `evidence_intelligence` acceleration lane runs the dossier, genealogy, and oracle as one
four-hour paper-research cycle. Schedule state v15 makes the new lane durable in the existing
15-minute Windows wake-up control plane.

The native control center now has nine surfaces. Evidence displays hard gates, source truth,
economic decomposition, the diagnostic frontier, settlement, and pricing-oracle validation.
Evolution provides an interactive SVG genealogy, node inspector, rejection reasons, and family
budget ledger. The bridge reads only local governed artifacts and continues to expose no broker,
order, shell, credential-readback, or live-execution method.

## Verification

Executed from `C:\Users\CH\dopey`:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests\test_context_settlement_resumability.py `
  tests\test_strategy_evidence_dossier_integration.py `
  tests\test_mutation_genealogy_explorer.py `
  tests\test_binomial_oracle_integration.py `
  tests\test_desktop_control_center.py `
  tests\test_acceleration_control_plane.py -q
```

Result: **28 passed**.

```powershell
.\desktop\build_desktop.ps1
```

Result: deterministic frontend build, source smoke, packaged smoke, and release manifest passed.
The executable is 14,790,553 bytes with SHA-256
`691b308b6adac4350feccbdabb4b604f3129789396ea6f8e19d56842591e3ce8`.
It is an unsigned local research build. The packaged runtime contract records
`server_started=false`, `live_execution_enabled=false`, `paper_only=true`, and
`live_blocked=true`.

## Reproduction

```powershell
cd C:\Users\CH\dopey
.venv\Scripts\python.exe -m operator_tools.update_context_decision_outcomes
.venv\Scripts\python.exe -m dopey_reporting.run_evidence_intelligence_cycle
.venv\Scripts\python.exe -m dopey_dashboard.control_center_state
.\desktop\build_desktop.ps1
```

Primary artifacts:

- `artifacts/dopey/runs/latest_dossier.json`
- `artifacts/dopey/evolution/mutation_genealogy.json`
- `artifacts/dopey/options_oracle/binomial_oracle_validation.json`
- `artifacts/dopey/equity_swing/latest_context_settlement.json`
- `artifacts/dopey/evidence_intelligence/latest_cycle.json`
- `desktop/release/DOPEY_Control_Center_RELEASE_MANIFEST.json`

## Remaining evidence frontier

Architecture is no longer the blocker. DOPEY must accrue immutable, timestamped, executable
option-chain observations and forward settlements, then survive matched baselines, realistic
fills and costs, selection-aware statistics, adversarial stress, clean-room reproduction,
sealed evaluation, and prospective shadow operation. Until then, the correct operational state
is research-active, paper-only, live-blocked, and not action-ready.
