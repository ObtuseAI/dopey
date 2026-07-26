"""Strategy archetype declarations for the target screener.

Each archetype is a declarative factor-weight profile over the shared factor
families. The screener can RANK for any archetype ("any type of trading
strategy" as a research lens); the ENVELOPE stays long-premium-only, so every
archetype maps to an executable structure of long_call / long_put (or is
stamped screen_only). Weights live in screen_config.py (the evolvable
surface) - this module only declares shape and semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import screen_config as cfg

FACTOR_FAMILIES: tuple[str, ...] = (
    "momentum",
    "value_rot",
    "attention",
    "flow",
    "structure",
    "quality",
)

EXECUTABLE_STRUCTURES: frozenset[str] = frozenset({"long_call", "long_put"})


@dataclass(frozen=True)
class StrategyArchetype:
    archetype_id: str
    display_name: str
    thesis: str
    executable_structure: str          # long_call | long_put | screen_only
    weights: dict[str, float] = field(default_factory=dict)
    honest_limits: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "archetype_id": self.archetype_id,
            "display_name": self.display_name,
            "thesis": self.thesis,
            "executable_structure": self.executable_structure,
            "weights": dict(self.weights),
            "honest_limits": list(self.honest_limits),
            "executable_under_envelope": self.executable_structure in EXECUTABLE_STRUCTURES,
        }


def _weights(prefix: str) -> dict[str, float]:
    return {
        "momentum": float(getattr(cfg, f"{prefix}_MOMENTUM")),
        "value_rot": float(getattr(cfg, f"{prefix}_VALUE_ROT")),
        "attention": float(getattr(cfg, f"{prefix}_ATTENTION")),
        "flow": float(getattr(cfg, f"{prefix}_FLOW")),
        "structure": float(getattr(cfg, f"{prefix}_STRUCTURE")),
        "quality": float(getattr(cfg, f"{prefix}_QUALITY")),
    }


def build_archetypes() -> list[StrategyArchetype]:
    """Archetype set, weights read from screen_config AT CALL TIME so an
    evolver-perturbed config is picked up without re-import gymnastics."""
    return [
        StrategyArchetype(
            "long_call_momentum_breakout",
            "Momentum breakout (calls)",
            "confirmed price strength with supportive structure carries",
            "long_call",
            _weights("LCMB"),
            ("bull-drift confound until baseline arbitration passes",),
        ),
        StrategyArchetype(
            "long_put_fundamental_rot",
            "Fundamental rot (puts)",
            "valuation excess + fundamental decay eventually reprices",
            "long_put",
            _weights("LPFR"),
            (
                "expensive-to-borrow names carry expensive puts",
                "no unearned bias: flags are research input, not edge",
            ),
        ),
        StrategyArchetype(
            "long_put_crowded_fade",
            "Crowded-attention fade (puts)",
            "extreme retail attention into weakening tape mean-reverts",
            "long_put",
            _weights("LPCF"),
            ("attention IC is weak-negative and unpromoted (foundry)",),
        ),
        StrategyArchetype(
            "long_call_quality_pullback",
            "Quality pullback (calls)",
            "clean-fundamental names on short-term weakness recover",
            "long_call",
            _weights("LCQP"),
            (),
        ),
        StrategyArchetype(
            "long_premium_vol_expansion",
            "Vol-expansion coil (direction by momentum sign)",
            "realized-vol compression + structure stress precedes range break",
            "screen_only",
            _weights("LPVE"),
            (
                "direction chosen by momentum sign at review time",
                "long-premium execution only; no straddles/strangles live",
            ),
        ),
    ]


def archetype_ids() -> list[str]:
    return [archetype.archetype_id for archetype in build_archetypes()]
