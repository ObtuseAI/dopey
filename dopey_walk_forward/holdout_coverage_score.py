"""Wrapper module: re-exports the v2 coverage scoring API under a project-consistent name.

This file exists so the audit / runner can import from a stable module path. The
implementation lives in `corpus_coverage.py`.
"""
from .corpus_coverage import (
    CorpusCoverageScore,
    FamilyChallengeCoverageScore,
    REQUIRED_CROSS_FAMILY_CHALLENGES,
    REQUIRED_IV_TRANSITIONS,
    REQUIRED_LIQUIDITY_STRESSES,
    REQUIRED_MACRO_SHOCKS,
    REQUIRED_REGIME_TAGS,
    REQUIRED_SECTORS_V2,
    RegimeCoverageScore,
    SectorCoverageScore,
    StressCoverageScore,
    score_corpus_coverage,
    score_family_challenge_coverage,
    score_regime_coverage,
    score_sector_coverage,
    score_stress_coverage,
    score_v2_category_coverage,
)


__all__ = [
    "CorpusCoverageScore",
    "FamilyChallengeCoverageScore",
    "RegimeCoverageScore",
    "SectorCoverageScore",
    "StressCoverageScore",
    "REQUIRED_REGIME_TAGS",
    "REQUIRED_SECTORS_V2",
    "REQUIRED_MACRO_SHOCKS",
    "REQUIRED_IV_TRANSITIONS",
    "REQUIRED_LIQUIDITY_STRESSES",
    "REQUIRED_CROSS_FAMILY_CHALLENGES",
    "score_corpus_coverage",
    "score_family_challenge_coverage",
    "score_regime_coverage",
    "score_sector_coverage",
    "score_stress_coverage",
    "score_v2_category_coverage",
]
