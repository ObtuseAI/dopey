"""Research holdout V4 (re-exports V1 split logic with V4 subfamily-friendly docstring)."""
from __future__ import annotations

from dopey_signal_research.research_holdout_v1 import holdout_split_pass_rate, holdout_survival

__all__ = ["holdout_split_pass_rate", "holdout_survival"]
