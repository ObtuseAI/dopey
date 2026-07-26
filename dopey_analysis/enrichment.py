"""Dopey analysis fixture enrichment: per-window deterministic analysis contexts.

Adds a separate analysis-context fixture file per walk-forward window (kept alongside the window
fixtures) so the tournament can compute AnalysisFusionScore per window without real data.
Deterministic; no network. Place-holder notes mark where future real data would feed in.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import (
    MacroContext, MicrostructureContext, TechnicalContext, FundamentalContext, PatternSignal,
)

WINDOW_ANALYSIS_DIR = Path(__file__).resolve().parent.parent / "dopey_data" / "fixtures" / "walk_forward"


def _analysis_path(window_id: str, directory: Path | None = None) -> Path:
    d = directory or WINDOW_ANALYSIS_DIR
    return d / f"{window_id}_analysis.json"


def load_window_analysis(window_id: str, directory: Path | None = None) -> dict:
    """Load the analysis-context fixture for a window. Returns a dict of contexts + patterns."""
    p = _analysis_path(window_id, directory)
    if not p.exists():
        # graceful: return neutral defaults if no analysis fixture present
        return {
            "macro": MacroContext(regime_tag=window_id).to_dict(),
            "microstructure": MicrostructureContext().to_dict(),
            "technical": TechnicalContext().to_dict(),
            "fundamental": FundamentalContext().to_dict(),
            "patterns": [],
        }
    return json.loads(p.read_text(encoding="utf-8"))


def parse_window_analysis(data: dict) -> dict:
    """Parse a raw analysis dict into typed context objects."""
    return {
        "macro": MacroContext.from_dict(data.get("macro", {})),
        "microstructure": MicrostructureContext.from_dict(data.get("microstructure", {})),
        "technical": TechnicalContext.from_dict(data.get("technical", {})),
        "fundamental": FundamentalContext.from_dict(data.get("fundamental", {})),
        "patterns": [PatternSignal.from_dict(p) for p in data.get("patterns", [])],
    }
