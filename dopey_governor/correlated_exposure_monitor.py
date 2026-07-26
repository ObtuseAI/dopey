"""Dopey correlated exposure monitor: naive correlation guard (research stub)."""
from __future__ import annotations


class CorrelatedExposureMonitor:
    def __init__(self, max_correlated_fraction: float = 0.30):
        self.max_correlated_fraction = max_correlated_fraction

    def check(self, exposures: dict[str, float], correlation_groups: dict[str, list[str]]) -> dict:
        """Return over-concentration flags by correlation group."""
        total = sum(exposures.values()) or 1.0
        flags = []
        for group, symbols in correlation_groups.items():
            gfrac = sum(exposures.get(s, 0.0) for s in symbols) / total
            if gfrac > self.max_correlated_fraction:
                flags.append({"group": group, "fraction": round(gfrac, 6),
                              "threshold": self.max_correlated_fraction})
        return {"over_concentrated": bool(flags), "flags": flags}
