"""CLI for static DOPEY export bundle review assistant artifacts.

Usage:
    python -m dopey_export_review.run_export_bundle_review_assistant
"""
from __future__ import annotations

import json
import sys

from .review_runner import run_export_bundle_review_assistant


def main() -> int:
    summary = run_export_bundle_review_assistant()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["review_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
