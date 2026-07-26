"""Evolvable scanner thresholds - the third external-evolution tunable surface.

Governance (mirrors dopey_backtest/exit_policy_config.py): these are the
whitelisted, evidence-neutral scanner thresholds the external evolver may
perturb. They change WHICH price patterns a detector fires on - never how an
outcome is judged. Truth-layer, gate, leak-guard, sentinel, sizing, and
cadence constants are NOT here and must never move here.

The doofus AST perturber requires each tunable to be a top-level
`NAME = <number>` single assignment on its own line, so they live here as
module constants; playbook_scanner assembles SCANNER_EVOLVABLE_PARAMETERS from
them. External perturbation is measure-only recommendation scored by
operator_tools/operator_scanner_fitness.py (held-out directional edge); an
operator reviews and applies any change through normal gated commit.
"""

# --- trend / momentum ---
TS_MOMENTUM_LOOKBACK = 252.0
TS_MOMENTUM_SKIP = 21.0
CHANNEL_BREAKOUT_WINDOW = 55.0
GAP_MIN_PCT = 0.03
W52_HIGH_PROXIMITY = 0.02
BOX_WINDOW = 15.0
BOX_MAX_RANGE_PCT = 0.08
VCP_CONTRACTION_STEPS = 3.0

# --- mean reversion ---
REVERSAL_WEEK_RETURN = 0.08
PULLBACK_RSI = 32.0
SNAPBACK_SIGMA = 2.0
MOVER_TOP_N = 40.0
CAPITULATION_VOL_PCT = 0.90

# --- volatility / compression ---
COIL_RANGE_PCT = 0.10
LOW_VOL_QUINTILE = 0.20
BB_SQUEEZE_WINDOW = 20.0
BB_SQUEEZE_BAND_K = 2.0
BB_SQUEEZE_PCTL = 0.10
BB_SQUEEZE_LOOKBACK = 120.0
BB_SQUEEZE_VOLUME_Z_MIN = 0.5


def evolvable_parameters() -> dict[str, float]:
    """The whitelisted evolvable thresholds as a name->value mapping.

    Ordering is preserved for artifact stability. Any name added here must be
    a top-level numeric constant above (the perturber addresses it by name).
    """
    return {
        "TS_MOMENTUM_LOOKBACK": TS_MOMENTUM_LOOKBACK,
        "TS_MOMENTUM_SKIP": TS_MOMENTUM_SKIP,
        "CHANNEL_BREAKOUT_WINDOW": CHANNEL_BREAKOUT_WINDOW,
        "GAP_MIN_PCT": GAP_MIN_PCT,
        "W52_HIGH_PROXIMITY": W52_HIGH_PROXIMITY,
        "BOX_WINDOW": BOX_WINDOW,
        "BOX_MAX_RANGE_PCT": BOX_MAX_RANGE_PCT,
        "VCP_CONTRACTION_STEPS": VCP_CONTRACTION_STEPS,
        "REVERSAL_WEEK_RETURN": REVERSAL_WEEK_RETURN,
        "PULLBACK_RSI": PULLBACK_RSI,
        "SNAPBACK_SIGMA": SNAPBACK_SIGMA,
        "MOVER_TOP_N": MOVER_TOP_N,
        "CAPITULATION_VOL_PCT": CAPITULATION_VOL_PCT,
        "COIL_RANGE_PCT": COIL_RANGE_PCT,
        "LOW_VOL_QUINTILE": LOW_VOL_QUINTILE,
        "BB_SQUEEZE_WINDOW": BB_SQUEEZE_WINDOW,
        "BB_SQUEEZE_BAND_K": BB_SQUEEZE_BAND_K,
        "BB_SQUEEZE_PCTL": BB_SQUEEZE_PCTL,
        "BB_SQUEEZE_LOOKBACK": BB_SQUEEZE_LOOKBACK,
        "BB_SQUEEZE_VOLUME_Z_MIN": BB_SQUEEZE_VOLUME_Z_MIN,
    }
