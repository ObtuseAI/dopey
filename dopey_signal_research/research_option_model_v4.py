"""V4 research option model.

V4 reuses V3 stress profiles. The V3 model already exports
``STRESS_PROFILES`` and ``apply_stress_profile`` which are imported
here as the canonical V4 stress machinery.
"""
from __future__ import annotations

from dopey_signal_research.research_option_model_v3 import STRESS_PROFILES, apply_stress_profile  # noqa: F401

__all__ = ["STRESS_PROFILES", "apply_stress_profile"]
