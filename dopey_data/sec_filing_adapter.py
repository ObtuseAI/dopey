"""Dopey SEC filing adapter: research stub (no network/creds in first pass)."""
from __future__ import annotations

from .source_scorecard import SourceScorecard


class SECFilingAdapter:
    PLANNED_USE = "Fundamental / event research from SEC EDGAR"

    def __init__(self):
        self.scorecard = SourceScorecard(
            source_id="sec_filings",
            authority=0.9,
            freshness=0.7,
            license_class="PUBLIC_DOMAIN",
            research_only=True,
            credentialed=False,
            notes="EDGAR is public; no creds; no fetch in first pass",
        )

    def discover(self) -> dict:
        return {"source_id": "sec_filings", "planned_use": self.PLANNED_USE, "connected": False}

    def fetch(self, _ticker: str) -> dict:
        return {"ok": False, "reason": "no network in first pass; research stub"}
