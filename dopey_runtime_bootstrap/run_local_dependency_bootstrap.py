"""CLI runner for DOPEY local dependency bootstrap."""
from __future__ import annotations

import json

from .local_dependency_bootstrap import run_local_dependency_bootstrap


def main() -> int:
    summary = run_local_dependency_bootstrap(5)
    print(json.dumps({
        "bootstrap_status": summary["bootstrap_status"],
        "installed_count": summary["installed_count"],
        "fallback_package_count": summary["fallback_package_count"],
        "summary_path": summary["artifact_paths"]["local_dependency_bootstrap_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
