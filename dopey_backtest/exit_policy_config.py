"""Evolvable exit-policy constants — the ONLY external-evolution tunable surface.

Governance (DOPEY_CANON V22): these three constants are the whitelisted,
evidence-neutral tunables for the external evolution harness
(operator_tools/operator_evolve_fitness.py + the doofus hill-climber). They
parameterize the HISTORICAL research backtest's exit engine only:

- the forward paper walk pins its own exit constants (forward_paper_walk.py)
  and is NEVER moved by this module — live evidence semantics stay fixed;
- truth-layer, readiness-gate, leak-guard, sentinel, sizing, and cadence
  constants are NOT evolvable and must never move into this module;
- external perturbation of this file is measure-only recommendation:
  an operator reviews and applies any change through normal gated commit
  (self_modification = artifact_recommendation_only_operator_applies).

Each value must stay a top-level `NAME = <number>` single assignment on its
own line (the external evolver's AST perturber requires that exact shape).
"""

# Close when premium falls to this fraction of entry (long premium: max loss -100%).
PREMIUM_STOP_PCT = -0.5

# Close when premium reaches this multiple gain over entry.
PREMIUM_TARGET_PCT = 1.0

# Time stop: close after this many marking sessions if neither level hit.
MAX_HOLDING_STEPS = 3
