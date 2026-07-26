"""Dopey OpenBB adapter: research stub (no network/creds in first pass).

DOPEY-native stub. Exposes a planned-use interface only; no live fetch.
"""
from __future__ import annotations

from .source_scorecard import SourceScorecard


class OpenBBAdapter:
    PLANNED_USE = "Terminal aggregation of market data for research"

    def __init__(self):
        self.scorecard = SourceScorecard(
            source_id="openbb",
            authority=0.8,
            freshness=0.7,
            license_class="UNKNOWN",
            research_only=True,
            credentialed=False,
            notes="stub; no network in first pass",
        )

    def discover(self) -> dict:
        return {"source_id": "openbb", "planned_use": self.PLANNED_USE, "connected": False}

    def fetch(self, *_args, **_kwargs) -> dict:
        return {"ok": False, "reason": "no network in first pass; research-only stub"}
