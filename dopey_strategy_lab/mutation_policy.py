"""Deterministic offline mutation policy for StrategyGenome variants."""
from __future__ import annotations

from .genome_mutation import MutationInstruction


MUTATION_POLICY_VERSION = "dopey-mutation-policy-v1"

MUTATION_TYPES: tuple[str, ...] = (
    "adjust_delta_preference",
    "adjust_dte_bucket",
    "adjust_liquidity_threshold",
    "adjust_slippage_tolerance",
    "adjust_iv_regime_preference",
    "adjust_pattern_preference",
    "adjust_invalidation_sensitivity",
    "adjust_regime_filter",
    "adjust_spread_structure_proxy",
    "adjust_theta_tolerance",
    "adjust_vega_tolerance",
    "adjust_overfit_penalty",
)


def build_mutation_instructions(seed: str = "dopey-offline-edge-v1") -> list[MutationInstruction]:
    """Return a fixed, ordered mutation policy. The seed is recorded for reproducibility."""
    return [
        MutationInstruction("mut-delta-01", "adjust_delta_preference", "parameters.delta_preference",
                            None, 0.58, "prefer cleaner directional delta without live authority"),
        MutationInstruction("mut-dte-01", "adjust_dte_bucket", "parameters.dte_bucket",
                            None, "21_35", "test a longer short-duration buffer offline"),
        MutationInstruction("mut-liquidity-01", "adjust_liquidity_threshold",
                            "parameters.liquidity_threshold", None, 0.45,
                            "reward candidates that fit current fixture liquidity"),
        MutationInstruction("mut-slippage-01", "adjust_slippage_tolerance",
                            "parameters.slippage_tolerance", None, 0.065,
                            "test tolerance to modeled fixture slippage"),
        MutationInstruction("mut-iv-01", "adjust_iv_regime_preference",
                            "parameters.iv_regime_preference", None, "normal_or_expansion",
                            "align with deterministic IV fixture context"),
        MutationInstruction("mut-pattern-01", "adjust_pattern_preference",
                            "parameters.pattern_preference", None, "trend_vol_continuation",
                            "favor current pattern fixture continuation context"),
        MutationInstruction("mut-invalidation-01", "adjust_invalidation_sensitivity",
                            "parameters.invalidation_sensitivity", None, 0.72,
                            "raise paper-only invalidation responsiveness"),
        MutationInstruction("mut-regime-01", "adjust_regime_filter", "parameters.regime_filter",
                            None, "trend_vol_expansion_or_breakout",
                            "favor best-fit deterministic regimes"),
        MutationInstruction("mut-structure-01", "adjust_spread_structure_proxy",
                            "parameters.spread_structure_proxy", None, "narrow_defined_risk_vertical",
                            "test defined-risk structure preference only"),
        MutationInstruction("mut-theta-01", "adjust_theta_tolerance", "parameters.theta_tolerance",
                            None, 0.40, "limit theta decay exposure in fixture scoring"),
        MutationInstruction("mut-vega-01", "adjust_vega_tolerance", "parameters.vega_tolerance",
                            None, 0.55, "bound vega noise in IV-crush contexts"),
        MutationInstruction("mut-overfit-01", "adjust_overfit_penalty", "parameters.overfit_penalty",
                            None, 0.12, "penalize high-overfit mutated candidates"),
    ]
