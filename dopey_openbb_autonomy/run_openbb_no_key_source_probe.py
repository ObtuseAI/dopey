"""CLI for OpenBB no-key source probe."""
from __future__ import annotations

import json

from .openbb_no_key_source_probe import run_openbb_no_key_source_probe


def main() -> int:
    result = run_openbb_no_key_source_probe()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
