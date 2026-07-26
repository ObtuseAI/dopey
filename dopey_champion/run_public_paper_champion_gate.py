"""CLI runner for public paper champion gate."""
from __future__ import annotations

import json

from .public_paper_champion_gate import run_public_paper_champion_gate


def main() -> int:
    summary = run_public_paper_champion_gate()
    print(json.dumps({
        "public_paper_champion_gate_status": summary["public_paper_champion_gate_status"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "champion_names": summary["champion_names"],
        "summary_path": summary["artifact_paths"]["public_paper_champion_gate_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
