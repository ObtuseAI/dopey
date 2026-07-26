"""Fixture expansion helpers for the 0DTE adversarial corpus."""
from __future__ import annotations

from .zero_dte_adversarial_fixture_builder import build_zero_dte_adversarial_fixture_cases
from .zero_dte_adversarial_path_builder import build_zero_dte_adversarial_intraday_paths


def build_zero_dte_fixture_expansion() -> dict:
    cases = build_zero_dte_adversarial_fixture_cases()
    paths = build_zero_dte_adversarial_intraday_paths(cases)
    return {
        "case_count": len(cases),
        "path_count": len(paths),
        "cases": [case.to_dict() for case in cases],
        "paths": paths,
        "paper_only": True,
        "live_blocked": True,
    }
