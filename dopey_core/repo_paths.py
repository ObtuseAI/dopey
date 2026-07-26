"""Canonical repository path constants.

Single source of truth for where DOPEY writes generated documents. Report,
ledger, commands, and session documents belong under ``docs/reports`` so the
repository root stays limited to genuine charters (README, LICENSE, SECURITY,
DATA_NOTICE, and the DOPEY_CANON / schema / policy governance documents).

Modules that emit generated markdown should build their output paths from
``REPORTS_DIR`` rather than joining report filenames straight onto the repo
root, which historically polluted the tree.
"""
from __future__ import annotations

from pathlib import Path

# dopey_core/ -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical home for generated reports / ledgers / commands / session docs.
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
