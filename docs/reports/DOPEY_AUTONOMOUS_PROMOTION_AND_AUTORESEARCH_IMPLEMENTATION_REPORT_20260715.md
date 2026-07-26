# DOPEY Autonomous Promotion and Autoresearch Implementation Report

## Outcome

The next vNext operating slice is implemented. DOPEY now has autonomous, threshold-gated
research activation with zero human review for qualified evidence.

Positive research activation requires three independent protected decisions:

1. the symbol gate passes;
2. the strategy gate passes;
3. the symbol-strategy pair gate passes.

The candidate cannot grade itself, change the evaluator, change thresholds, or activate its
own mutation. Backtests alone cannot activate anything. Research activation has
`readiness_effect=none`, `execution_effect=none`, `paper_only=true`, and
`live_blocked=true`.

## Implemented surfaces

### Autonomous promotion

- `dopey/promotion/schema.py` defines the full research lifecycle and typed evidence.
- `dopey/promotion/thresholds.py` defines the protected threshold policy.
- `dopey/promotion/gates.py` evaluates symbol, strategy, and pair evidence independently.
- `dopey/promotion/runtime.py` constructs the mandatory three-gate matrix.
- `dopey/promotion/registry.py` records content-addressed decisions append-only.
- `dopey/promotion/cycle.py` consumes accumulated evidence and applies qualified activation.
- `dopey/promotion/run_promotion_cycle.py` exposes the scheduled local entrypoint.

### Recursive strategy research

- `dopey/autoresearch/taxonomy.py` defines 12 diverse research lineages.
- `dopey/autoresearch/invention.py` creates deterministic evidence-steered challengers.
- `dopey/autoresearch/task_suite.py` separates visible, private, and external evaluation.
- `dopey/autoresearch/runtime.py` writes the durable experiment ledger and inherits only
  protected `RESEARCH_APPROVED` champion strategies.
- `dopey/autoresearch/run_autoresearch_cycle.py` advances durable generations automatically.

The lineages cover technical momentum, structure, fundamental quality, fundamental
deterioration, volatility/options, macro, breadth, cross-asset, adversarial, calibration-first,
abstention-first, and execution-cost-aware research.

### Runtime integration

The acceleration schedule is version 7 and adds two local, network-disabled lanes:

- `autonomous_strategy_research`: every 240 minutes, 24 challengers, 30-minute ceiling;
- `autonomous_promotion_evaluation`: every 240 minutes, protected three-gate evaluation,
  10-minute ceiling.

The first real smoke cycle produced:

- generation: 1;
- candidates: 24;
- represented lineages: 12;
- status: `experiments_queued`;
- finding state: `missing_findings_exploration_only`;
- automatic research activations: 0;
- promotion status: `missing_promotion_evidence`;
- human review required: false;
- paper only: true;
- live blocked: true.

Those zero/missing states are correct. No forward promotion matrix exists yet, so the runtime
did not manufacture a champion.

### Existing vNext integration

- the constitution is version 2 and protects promotion thresholds and evaluator independence;
- evolution applies protected lifecycle transitions without human review but still requires the
  full promotion matrix for positive activation;
- safety retirement, quarantine, and parent rollback are automatic;
- agent-ablation validation and harmful-agent retirement transition automatically from forward
  protected evidence;
- the observatory reports research activations rather than requiring automatic promotion to
  remain zero;
- README and the vNext master implementation report now describe the autonomous boundary;
- the dedicated plan is `DOPEY_VNEXT_AUTONOMOUS_PROMOTION_AND_AUTORESEARCH_PLAN_20260715.md`.

## Threshold posture

The current protected policy requires, among other checks:

- symbol history of at least 504 rows;
- replay, private, external, and forward sample floors;
- at least three independent strategies for a symbol;
- strategy transfer across at least five symbols, three eras, and three regimes;
- pair evidence across at least two regimes and 20 forward outcomes;
- causal confidence of at least 0.65;
- calibration error no greater than 0.10;
- independence of at least 0.60;
- positive after-cost gain and confidence-interval lower bound;
- nonnegative contested-truth gain;
- bounded complexity, missingness, and abstention;
- deterministic replay and no leakage, revised-data contamination, or reward hacking.

## Validation

- focused autonomous promotion/evolution/schedule suite: `13 passed`;
- integrated vNext promotion, causal, metacognition, observatory, sovereign runtime, and
  acceleration suite: `21 passed`;
- broad observatory/sovereign/causal/readiness/broker slice: `125 passed`, with one legacy-key
  compatibility failure found and repaired; its affected causal/observatory scope then passed
  `3 passed`;
- Ruff over every changed Python surface: passed;
- `compileall` over `dopey` and `dopey_acceleration`: passed;
- autonomous strategy evidence contract: `verified_complete` with required status
  `experiments_queued`;
- protected `dopey_data/market_lake`: no tracked status or diff;
- no broker, order, credential, capital, or live path added;
- no commit created.

Repository-wide `git diff --check` still reports pre-existing whitespace in unrelated dirty
files. The scoped changed tracked files pass `git diff --check`.

## Honest current state

This slice makes promotion operationally autonomous; it does not make missing market evidence
appear. The existing external action-readiness state remains `not_action_ready`. Current vNext
predictions still require forward settlement. Backtests remain research evidence, never forward
proof.

The implemented loop can now continually invent and queue strategies, learn from governed
findings, inherit only approved champions, evaluate independent promotion dimensions, activate
qualified research without human review, and automatically degrade or roll back unsafe research
while remaining structurally unable to trade.
