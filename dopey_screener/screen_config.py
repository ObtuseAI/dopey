"""Screen-weight configuration - the screener's ONLY evolvable surface.

Contract (same as dopey_backtest/exit_policy_config.py): every tunable is a
top-level ``NAME = <number>`` single-line assignment so the external evolver
(doofus) and the in-repo elite archive can perturb exactly one constant at a
time. Fitness for any change is HELD-OUT-ONLY (see
dopey_screener/elite_archive.py and operator_tools/operator_screen_fitness.py):
a weight set is judged by rank-IC on eras the search never trained on, never
by in-sample fit. Changes to this file are HUMAN-COMMITTED - the archive and
the evolver only ever RECOMMEND.

Factor families (inputs are normalized to roughly [-1, +1] before weighting):
  MOMENTUM   - spine 20d/60d price momentum (sign = direction of the move)
  VALUE_ROT  - fundamentals short-screen excess-flag count (0..5 scaled)
  ATTENTION  - Wikipedia crowd-attention z-score
  FLOW       - FINRA short-volume ratio (high = heavy short flow)
  STRUCTURE  - options-structure context (gamma regime / VRP / surface tear)
  QUALITY    - inverse rot (zero excess flags = highest quality)
"""

# --- long_call_momentum_breakout: ride confirmed strength ------------------
LCMB_MOMENTUM = 1.0
LCMB_VALUE_ROT = -0.4
LCMB_ATTENTION = 0.2
LCMB_FLOW = -0.3
LCMB_STRUCTURE = 0.3
LCMB_QUALITY = 0.4

# --- long_put_fundamental_rot: valuation excess + fundamental decay --------
LPFR_MOMENTUM = -0.5
LPFR_VALUE_ROT = 1.0
LPFR_ATTENTION = 0.3
LPFR_FLOW = 0.4
LPFR_STRUCTURE = 0.2
LPFR_QUALITY = -0.8

# --- long_put_crowded_fade: extreme attention into weakening tape ----------
LPCF_MOMENTUM = -0.3
LPCF_VALUE_ROT = 0.4
LPCF_ATTENTION = 1.0
LPCF_FLOW = 0.3
LPCF_STRUCTURE = 0.2
LPCF_QUALITY = -0.2

# --- long_call_quality_pullback: quality names on short-term weakness ------
LCQP_MOMENTUM = 0.5
LCQP_VALUE_ROT = -0.6
LCQP_ATTENTION = -0.2
LCQP_FLOW = -0.2
LCQP_STRUCTURE = 0.2
LCQP_QUALITY = 1.0

# --- long_premium_vol_expansion: compression coiling for a range break -----
LPVE_MOMENTUM = 0.2
LPVE_VALUE_ROT = 0.0
LPVE_ATTENTION = 0.2
LPVE_FLOW = 0.1
LPVE_STRUCTURE = 1.0
LPVE_QUALITY = 0.2
