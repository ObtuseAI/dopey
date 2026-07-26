"""Research option model helpers V1."""
from __future__ import annotations

STRESS_PROFILES = (
    "normal",
    "high_slippage",
    "iv_crush",
    "iv_spike",
    "theta_accelerated",
    "worse_entry",
    "worse_exit",
)


def apply_stress_profile(signal: dict[str, object], profile: str) -> dict[str, object]:
    stressed = dict(signal)
    stressed["slippage_stress"] = "normal"
    stressed["theta_stress"] = "normal"
    stressed["iv_shock_stress"] = "normal"
    if profile == "high_slippage":
        stressed["slippage_stress"] = "high"
    elif profile == "iv_crush":
        stressed["iv_shock_stress"] = "crush"
    elif profile == "iv_spike":
        stressed["iv_shock_stress"] = "spike"
    elif profile == "theta_accelerated":
        stressed["theta_stress"] = "accelerated"
    elif profile == "worse_entry":
        stressed["slippage_stress"] = "high"
    elif profile == "worse_exit":
        stressed["exit_degradation"] = True
    return stressed
