"""CLI runner for public lake final-state lock V2."""
from __future__ import annotations

import json

from .public_lake_final_state_lock_v2 import run_public_lake_final_state_lock_v2


def main() -> int:
    summary = run_public_lake_final_state_lock_v2()
    print(json.dumps({
        "public_lake_final_state_status": summary["public_lake_final_state_status"],
        "active_public_symbol_count": summary["active_public_symbol_count"],
        "active_fixture_symbol_count": summary["active_fixture_symbol_count"],
        "public_rows_active": summary["public_rows_active"],
        "summary_path": summary["artifact_paths"]["public_lake_final_state_lock_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
