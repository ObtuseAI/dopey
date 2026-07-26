"""CLI for OpenBB provider registry generation."""
from __future__ import annotations

import json

from .openbb_provider_registry import run_openbb_provider_registry


def main() -> int:
    result = run_openbb_provider_registry()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
