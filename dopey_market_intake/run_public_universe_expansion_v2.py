"""CLI runner for public universe expansion V2."""
from __future__ import annotations

import json

from .public_universe_expansion_v2 import run_public_universe_expansion_v2


def main() -> int:
    summary = run_public_universe_expansion_v2()
    print(json.dumps({
        "public_universe_expansion_status": summary["public_universe_expansion_status"],
        "candidate_symbol_count": summary["candidate_symbol_count"],
        "active_public_symbol_count": summary["active_public_symbol_count"],
        "new_symbols_added": summary["new_symbols_added"],
        "summary_path": summary["artifact_paths"]["public_universe_expansion_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
