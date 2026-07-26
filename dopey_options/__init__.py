"""dopey_options — options ontology, greeks, surfaces, liquidity, ranking, spreads.

DOPEY-native package. Stdlib dataclasses only — no pydantic. Research-only: no order
placement, no live pricing, no undefined-risk structures.
"""
from .ontology import Underlying, OptionContract, OptionChain  # noqa: F401
from .greeks_engine import bs_greeks, enrich_contract  # noqa: F401
from .iv_surface_engine import iv_grid, moneyness_rank  # noqa: F401
from .skew_engine import skew_slope  # noqa: F401
from .term_structure_engine import atm_term_structure  # noqa: F401
from .liquidity_engine import liquidity_score  # noqa: F401
from .contract_ranker import rank_contracts  # noqa: F401
from .spread_builder import vertical_spread, pick_vertical  # noqa: F401
from .assignment_exercise_engine import assignment_risk  # noqa: F401
