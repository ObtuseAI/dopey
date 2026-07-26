"""OPERATOR TOOL - cross-lane convergence (measure-only intelligence layer).

Reads DOPEY's independent held-out / forward measurement lanes and reports
where they CORROBORATE a directional sign vs where they CONFLICT. Corroboration
across genuinely independent methods raises confidence in a research
hypothesis; it never becomes an edge claim and never promotes. Forward
settlement remains the sole arbiter of trust.

Run after the fitness lanes refresh (scanner + screener fitness, compression
study, playbook settlement) so it reads current numbers.

Usage:  .venv\\Scripts\\python operator_tools\\operator_cross_lane_convergence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.cross_lane_convergence import (  # noqa: E402
    run_cross_lane_convergence,
)


def main() -> int:
    report = run_cross_lane_convergence()
    print(
        json.dumps(
            {
                "headline": report["headline"],
                "corroborated_findings": report["corroborated_findings"],
                "contested_findings": report["contested_findings"],
                "system_contested_base_rate": report["system_contested_base_rate"],
                "not_edge_evidence": report["not_edge_evidence"],
                "promotion_allowed": report["promotion_allowed"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
