"""dopey_analysis — S-tier multi-layer market analysis stack (deterministic, offline, fixture-based).

Implements the analysis architecture for macro, microstructure, technical, fundamental, and
pattern-recognition intelligence as first-class parts of DOPEY's recursive edge engine. In this
pass these are deterministic offline fixture interfaces — NOT real market-data integrations.
No single analysis layer is final authority; AnalysisFusionScore combines and penalizes
contradictions. No network, no credentials, no live path.
"""
from .models import (  # noqa: F401
    MacroContext,
    MicrostructureContext,
    TechnicalContext,
    FundamentalContext,
    PatternSignal,
    AnalysisFusionScore,
)
from .macro_analysis import score_macro
from .microstructure_analysis import score_microstructure
from .technical_analysis import score_technical
from .fundamental_analysis import score_fundamental
from .pattern_recognition import score_patterns
from .analysis_fusion import fuse_analysis
from .enrichment import load_window_analysis, WINDOW_ANALYSIS_DIR
