"""Command-line entrypoint for the multi-daily universe membership refresh."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .evolving_universe import refresh_evolving_universe_membership


def main() -> int:
    summary = refresh_evolving_universe_membership(datetime.now(timezone.utc))
    print(
        json.dumps(
            {
                "status": summary["status"],
                "active_after": summary["active_after"],
                "maximum_active_universe_size": summary[
                    "maximum_active_universe_size"
                ],
                "promoted_symbols": summary["promoted_symbols"],
                "demoted_symbols": summary["demoted_symbols"],
                "registry_persisted": summary["registry_persisted"],
                "reproducibility_hash": summary["reproducibility_hash"],
                "paper_only": summary["paper_only"],
                "live_blocked": summary["live_blocked"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
