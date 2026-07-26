# DOPEY vNext Autonomous Promotion and Autoresearch Plan

## Operating decision

Research activation is autonomous. A qualified symbol, strategy, or symbol-strategy pair does
not wait for human review. The protected evaluator applies deterministic thresholds and records
the transition in an append-only registry.

This autonomy is confined to market research. It grants no broker, credential, order,
capital-allocation, action-readiness, or live-execution authority.

DOPEY autoresearch is now also an experimental domain beneath the domain-independent
Intelligence Research Engine. The market layer invents and evaluates strategies; the higher
layer studies which methods of discovery, reasoning, creativity, planning, and evaluation make
that research process improve. The higher layer never imports market concepts and cannot alter
truth, verification, authority, permissions, readiness, or execution. Its complete architecture
is defined in `DOPEY_INTELLIGENCE_RESEARCH_ENGINE_PLAN_20260715.md`.

## Promotion architecture

Every active research path must pass three independent gates:

```text
Symbol evidence gate
        +
Strategy evidence gate
        +
Symbol x strategy forward gate
        |
        v
Automatic research activation
        |
        +-- readiness effect: none
        +-- execution effect: none
```

The three-gate rule prevents a strong strategy from hiding a weak symbol history, a strong
symbol from hiding a fragile strategy, or aggregate performance from hiding a failing pair.

### Symbol gate

The symbol gate measures whether a name is safe and informative enough for an activated
research path. It requires:

- sufficient clean point-in-time history;
- deterministic replay;
- private and external samples;
- forward-paper settlements;
- several independent strategy families;
- calibrated, cost-positive, contested-truth evidence;
- no leakage, revised-data contamination, or reward-hacking finding.

Symbols are evaluated independently. Failure can leave a symbol experimental, forward-paper,
degraded, retired, or quarantined without affecting unrelated names.

### Strategy gate

The strategy gate is global to one immutable strategy identity and lineage. It requires:

- replay/backtest scale, with backtests explicitly insufficient for activation;
- hidden private improvement;
- untouched external generalization;
- later forward-paper settlement;
- cross-symbol, cross-era, and cross-regime transfer;
- causal confidence and calibrated probabilities;
- positive after-cost and lower-confidence-bound evidence;
- nonnegative contested-truth performance;
- independent evaluation;
- bounded complexity and abstention;
- no reward-hacking, leakage, or revised-data violation.

### Symbol-strategy pair gate

The pair gate activates only after both parents are approved. It independently requires enough
forward samples and regimes, pair-level causal confidence, calibration, independence,
after-cost gain, contested performance, and a positive confidence-interval lower bound.

This gate is the activation authority. A candidate never grades or activates itself.

## Lifecycle

```text
EXPERIMENTAL
QUARANTINED
SHADOW_ONLY
REPLAY_VALIDATED
PRIVATE_VALIDATED
EXTERNAL_VALIDATED
FORWARD_PAPER
CONTESTED_VALIDATED
RESEARCH_APPROVED
DEGRADED
RETIRED
```

Protected lifecycle transitions, safety demotions, quarantine, and parent rollback are
automatic. `RESEARCH_APPROVED` requires the complete three-gate matrix. Historical replay can
advance validation state but can never substitute for forward proof.

## Recursive strategy ecology

The autonomous research lane continuously maintains twelve distinct lineages:

1. technical momentum;
2. structural trend;
3. fundamental quality;
4. fundamental deterioration;
5. volatility and options;
6. macro regime;
7. breadth and participation;
8. cross-asset;
9. adversarial;
10. calibration-first;
11. abstention-first;
12. execution-cost-aware research.

Each lineage owns an objective, seed genes, and bounded mutation operators. Failure memory,
settlement evidence, calibration errors, backtest findings, and new research steer later
mutations. When no governed finding exists, the cycle labels the work
`missing_findings_exploration_only`; it does not invent a success claim.

Allowed recursive improvements include:

- indicator parameters and normalized composites;
- strategy definitions and regime conditions;
- evidence ordering and budgets;
- organism composition and adversarial sequence;
- stopping, abstention, and calibration policy;
- lineage allocation and mutation operators;
- metacognitive strategy selection.

Protected and non-evolvable surfaces include:

- truth and settlement;
- point-in-time provenance;
- execution seal and credential restrictions;
- readiness law;
- promotion thresholds;
- evaluator independence and private partitions;
- candidate self-activation prohibition.

## Evaluation separation

### Visible development

Provides detailed debugging feedback for determinism, schema correctness, leakage audits,
random-entry baselines, and circular-shift nulls. It has no selection authority.

### Private selection

Selects mutations using hidden dates, symbols, regimes, sectors, event clusters, execution
conditions, and contested cases. The researcher receives aggregate scores, never item-level
answers. Private traps cover future data, revised fundamentals, duplicate families,
survivorship, easy-symbol selection, over-abstention, simulation-as-truth, false independence,
market drift, and complexity camouflage.

### External generalization

Confirms untouched cross-symbol and cross-era transfer, new regimes, later market structure,
and forward-paper settlement. It is never used to choose mutations.

## Autonomous cadence

The `autonomous_strategy_research` lane runs locally every four hours with:

- no network requirement;
- a fixed 30-minute execution ceiling;
- one explicit attempt;
- a 24-candidate budget;
- an append-only experiment ledger;
- a canonical `latest_cycle.json` evidence contract;
- exact `experiments_queued` status;
- zero activation claims until protected evaluation evidence exists.

The lane invents candidates; the protected evaluator selects and promotes them. These are
separate authorities.

## Metacognitive recursion

The next integrated slices connect settlement and failure memory to lineage allocation:

1. score expected information gain before each experiment;
2. allocate trials with a contextual lineage bandit;
3. fork stalled lineages from the best transferable genome;
4. measure agent independence and duplicate-family consensus;
5. distill winning candidates and rerun private evaluation;
6. apply the three-gate matrix after each new settlement batch;
7. automatically degrade or roll back research paths when calibration drifts;
8. run fixed-budget improved-improver ignition tests.

The meta-level objective is not raw candidate count. It is net-positive improvement under
fixed compute with lower calibration error, lower reward-hacking rate, better transfer, and
less complexity.

## Current implementation status

Implemented in this slice:

- sealed autonomous promotion thresholds;
- typed symbol, strategy, and pair evidence contracts;
- deterministic three-gate evaluator and content-addressed decisions;
- append-only activation registry;
- automatic research lifecycle transitions and safety rollback;
- twelve-lineage seed taxonomy;
- evidence-steered deterministic candidate invention;
- visible/private/external task-suite separation and private traps;
- scheduled four-hour autonomous research lane;
- observatory and README semantics for autonomous research activation;
- integration coverage proving no-human activation and zero readiness/execution effect.

Evidence-dependent rather than code-dependent:

- no current pair is claimed `RESEARCH_APPROVED` without enough forward settlement;
- existing action readiness remains `not_action_ready`;
- backtests and simulation remain non-forward evidence;
- live execution remains unavailable by constitution.

## Success tests

The complete capability is demonstrated only when all of the following are observed:

- qualifying symbol evidence activates its symbol gate automatically;
- a transferable, calibrated strategy activates its strategy gate automatically;
- a forward-proven pair activates without human review;
- the same strategy remains blocked on symbols whose pair evidence fails;
- leakage or reward-hacking findings quarantine automatically;
- calibration drift degrades or rolls back an active research path automatically;
- later strategy generations outperform parents on hidden and external tasks under fixed cost;
- no activation changes action readiness, order authority, or the execution seal.

That is the intended autonomous boundary: constant invention, independent grading, automatic
research activation, automatic safety demotion, and immutable separation from trading power.
