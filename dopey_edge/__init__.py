"""Dopey edge — signal discovery + Dummy aggressive-adaptive-edge doctrine (research stubs).

DOPEY-native package. Borrows the Dummy doctrine: proof-weighted aggression, weak-signal
starving, capital redeployment, fast invalidation, recursive data expansion. All modules are
recommend-only / research-only; none place live trades or connect a funded broker.
"""
from .signal_discovery import discover_signals  # noqa: F401
from .asymmetric_opportunity_ranker import rank_opportunities  # noqa: F401
from .weak_signal_starver import starve_weak_signals  # noqa: F401
from .proof_weighted_aggression_gate import (  # noqa: F401
    AggressionEvaluation,
    AggressionScore,
    ExecutionEligibility,
    PromotionDecision,
    ProofWeightedAggressionGate,
)
from .capital_redeployment_engine import redeploy_capital  # noqa: F401
from .fast_invalidation_engine import detect_invalidation  # noqa: F401
from .recursive_data_expander import expand_data_candidates  # noqa: F401
