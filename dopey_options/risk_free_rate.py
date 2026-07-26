"""Risk-free rate resolver: real Treasury curve when staged, honest fallback otherwise.

Every pricing engine used to hardcode 4%. The macro-context gate now distills
the ~30d par yield from the operator-staged US Treasury curve; engines resolve
through here and record the provenance string in their artifacts, so a reader
always knows whether a number was priced off the real curve or the fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
FALLBACK_RATE = 0.04


def resolve_risk_free_rate(default: float = FALLBACK_RATE) -> tuple[float, str]:
    """(annualized decimal rate, provenance). Sanity band keeps a corrupt artifact
    from poisoning pricing."""
    if MACRO_SUMMARY_PATH.exists():
        try:
            summary = json.loads(MACRO_SUMMARY_PATH.read_text(encoding="utf-8"))
            pct = summary.get("risk_free_rate_30d_pct")
            if pct is not None and 0.0 <= float(pct) <= 20.0:
                return float(pct) / 100.0, "us_treasury_par_yield_curve_30d"
        except (json.JSONDecodeError, ValueError, TypeError, OSError):
            pass
    return default, "fallback_constant_no_treasury_staged"
