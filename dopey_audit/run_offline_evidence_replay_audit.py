"""CLI entry point for the offline evidence replay audit harness.

Usage:
    python -m dopey_audit.run_offline_evidence_replay_audit

The harness is deterministic, offline, fixture-only, and paper-only. It never enables live
 trading, connects to brokers, or uses network access.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .audit_runner import run_offline_evidence_replay_audit


def main(argv: list[str] | None = None) -> int:
    summary = run_offline_evidence_replay_audit()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary.get("verdict") in {
        "fail_safety",
        "fail_reproducibility",
        "fail_schema",
        "fail_missing_evidence",
    }:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
