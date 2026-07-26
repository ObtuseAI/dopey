"""CLI runner for provider package install repair."""
from __future__ import annotations

import json

from .provider_install_repair import run_provider_install_repair


def main() -> int:
    summary = run_provider_install_repair(90, 180, True)
    print(json.dumps({
        "active_python_status": summary["active_python_status"],
        "repo_venv_python": summary["repo_venv_python"],
        "yfinance_import_status": summary["yfinance_import_status"],
        "pandas_datareader_import_status": summary["pandas_datareader_import_status"],
        "yahooquery_import_status": summary["yahooquery_import_status"],
        "openbb_import_status": summary["openbb_import_status"],
        "install_timeout_count": summary["install_timeout_count"],
        "summary_path": summary["artifact_paths"]["provider_install_repair_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
