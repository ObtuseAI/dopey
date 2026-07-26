"""CLI for DOPEY artifact compaction/export verifier.

Usage:
    python -m dopey_export.run_artifact_compaction_export_verifier
"""
from __future__ import annotations

import json
import sys

from .export_models import DEFAULT_EXPORT_PROFILE
from .export_verifier import run_artifact_compaction_export_verifier


def main() -> int:
    profile = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXPORT_PROFILE
    summary = run_artifact_compaction_export_verifier(profile)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["export_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
