"""Dopey Tradier options data adapter: research/paper stub (no network/creds in first pass)."""
from __future__ import annotations

from .source_scorecard import SourceScorecard


class TradierOptionsDataAdapter:
    PLANNED_USE = "Options chain + paper/sandbox fills"

    def __init__(self):
        self.scorecard = SourceScorecard(
            source_id="tradier_options",
            authority=0.8,
            freshness=0.85,
            license_class="UNKNOWN",
            research_only=True,
            credentialed=False,
            notes="paper/sandbox-ready placeholder; no creds in first pass",
        )

    def discover(self) -> dict:
        return {"source_id": "tradier_options", "planned_use": self.PLANNED_USE, "connected": False}

    def fetch_chain(self, _symbol: str) -> dict:
        return {"ok": False, "reason": "no network in first pass; paper/sandbox stub"}
