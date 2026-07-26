"""CLI runner for the public lake freeze guard."""
from __future__ import annotations

import json

from .public_lake_freeze_guard import run_public_lake_freeze_guard


def main() -> int:
    summary = run_public_lake_freeze_guard()
    print(json.dumps({
        "public_lake_guard_status": summary["public_lake_guard_status"],
        "active_public_symbol_count": summary["active_public_symbol_count"],
        "active_fixture_symbol_count": summary["active_fixture_symbol_count"],
        "public_lake_restored": summary["public_lake_restored"],
        "summary_path": summary["artifact_paths"]["public_lake_freeze_guard_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
