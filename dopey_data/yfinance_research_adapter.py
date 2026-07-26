"""Dopey yfinance research adapter: research-only stub (no network/creds, no exec)."""
from __future__ import annotations

from .source_scorecard import SourceScorecard


class YFinanceResearchAdapter:
    PLANNED_USE = "Research-only price/option snapshots (rate-limited, no exec)"

    def __init__(self):
        self.scorecard = SourceScorecard(
            source_id="yfinance_research",
            authority=0.6,
            freshness=0.75,
            license_class="UNKNOWN",
            research_only=True,
            credentialed=False,
            notes="research-only; rate-limited; never used for execution",
        )

    def discover(self) -> dict:
        return {"source_id": "yfinance_research", "planned_use": self.PLANNED_USE, "connected": False}

    def fetch(self, _symbol: str) -> dict:
        return {"ok": False, "reason": "no network in first pass; research-only stub"}
