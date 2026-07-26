"""Dopey strategy lab — strategy genome + walk-forward validation + overfit detection.

DOPEY-native package. Stdlib dataclasses only — no pydantic. Research-only.
"""
from .strategy_genome import StrategyGenome  # noqa: F401
from .mutation_tournament import run_mutation_tournament  # noqa: F401
from .walk_forward_validator import walk_forward_validate  # noqa: F401
from .overfit_detector import detect_overfit  # noqa: F401
from .regime_classifier import classify_regime  # noqa: F401
from .champion_registry import ChampionRegistry  # noqa: F401
