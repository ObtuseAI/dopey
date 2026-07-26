"""CLI entry point for active policy integration map generation."""
from __future__ import annotations

import json
import sys

from .active_policy_integration_map import write_active_policy_integration_map


def main(argv: list[str] | None = None) -> int:
    result = write_active_policy_integration_map()
    print(json.dumps({
        "status": "ok",
        "policy_version": result["policy_version"],
        "enforcement_points": len(result["enforcement_points"]),
        "json_path": result["json_path"],
        "markdown_path": result["markdown_path"],
        "live_blocked": result["safety_state"]["live_blocked"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
