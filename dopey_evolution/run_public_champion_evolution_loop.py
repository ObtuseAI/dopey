"""CLI runner for public champion evolution loop."""
from __future__ import annotations

import json

from .public_champion_evolution_loop import run_public_champion_evolution_loop


def main() -> int:
    summary = run_public_champion_evolution_loop()
    print(json.dumps({
        "public_champion_evolution_status": summary["public_champion_evolution_status"],
        "generation_count": summary["generation_count"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "mutations_generated": summary["mutations_generated"],
        "summary_path": summary["artifact_paths"]["public_champion_evolution_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
