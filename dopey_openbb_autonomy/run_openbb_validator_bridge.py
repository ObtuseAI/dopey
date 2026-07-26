"""CLI for OpenBB validator bridge."""
from __future__ import annotations

import json

from .openbb_validator_bridge import run_openbb_validator_bridge


def main() -> int:
    result = run_openbb_validator_bridge()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
