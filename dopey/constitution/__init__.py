"""Non-evolvable DOPEY research constitution."""

from .authority import Authority, assert_research_authority
from .execution_seal import ExecutionSealViolation, execution_seal_state
from .invariants import CONSTITUTION_VERSION, PERMANENT_INVARIANTS
from .mutation_protection import assert_mutation_proposal_safe

__all__ = [
    "Authority",
    "CONSTITUTION_VERSION",
    "ExecutionSealViolation",
    "PERMANENT_INVARIANTS",
    "assert_mutation_proposal_safe",
    "assert_research_authority",
    "execution_seal_state",
]
