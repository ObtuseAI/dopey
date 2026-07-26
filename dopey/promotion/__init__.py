"""Protected autonomous research-activation gates."""

from .gates import (
    evaluate_strategy_promotion,
    evaluate_symbol_promotion,
    evaluate_symbol_strategy_promotion,
)
from .runtime import build_autonomous_promotion_matrix
from .schema import ResearchActivationState
from .thresholds import AUTONOMOUS_PROMOTION_THRESHOLDS

__all__ = [
    "AUTONOMOUS_PROMOTION_THRESHOLDS",
    "ResearchActivationState",
    "build_autonomous_promotion_matrix",
    "evaluate_strategy_promotion",
    "evaluate_symbol_promotion",
    "evaluate_symbol_strategy_promotion",
]
