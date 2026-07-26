"""Domain-independent scientific research over cognitive methods."""

from .creativity import CREATIVITY_OPERATORS, generate_cognitive_hypotheses
from .discovery import discover_research_questions
from .evaluator import COGNITIVE_METHOD_THRESHOLDS, evaluate_cognitive_method
from .evidence_cycle import run_cognitive_evidence_cycle, synthesize_cognitive_method_evidence
from .execution import execute_cognitive_experiments
from .runtime import run_intelligence_research_cycle
from .theory import build_theory_candidate

__all__ = [
    "COGNITIVE_METHOD_THRESHOLDS",
    "CREATIVITY_OPERATORS",
    "build_theory_candidate",
    "discover_research_questions",
    "evaluate_cognitive_method",
    "execute_cognitive_experiments",
    "generate_cognitive_hypotheses",
    "run_intelligence_research_cycle",
    "run_cognitive_evidence_cycle",
    "synthesize_cognitive_method_evidence",
]
