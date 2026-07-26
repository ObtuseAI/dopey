"""OPERATOR TOOL - self-scout report (watch film of our own tendencies).

Adversarial self-examination: directional over-concentration, duplicate-name
risk, corroboration leaning on shared machinery, search breadth without
improvement. Reports tells ranked by severity; fixes and promotes nothing.

Usage:  .venv\\Scripts\\python operator_tools\\operator_self_scout.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.self_scout import run_self_scout  # noqa: E402


def main() -> int:
    report = run_self_scout()
    print(
        json.dumps(
            {
                "headline": report["headline"],
                "severity_counts": report["severity_counts"],
                "findings": [{"severity": f["severity"], "tell": f["tell"], "detail": f["detail"]} for f in report["findings"]],
            },
            indent=2,
        ),
        flush=True,
    )
    # Non-zero only on a critical tell so a scheduler can alert on it.
    return 1 if report["severity_counts"]["critical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
