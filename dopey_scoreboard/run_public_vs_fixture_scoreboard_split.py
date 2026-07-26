"""CLI runner for public-vs-fixture scoreboard split."""
from __future__ import annotations

import json

from .public_vs_fixture_scoreboard_split import run_public_vs_fixture_scoreboard_split


def main() -> int:
    summary = run_public_vs_fixture_scoreboard_split()
    print(json.dumps({
        "scoreboard_split_status": summary["scoreboard_split_status"],
        "public_strategy_score_count": summary["public_strategy_score_count"],
        "fixture_strategy_score_count": summary["fixture_strategy_score_count"],
        "summary_path": summary["artifact_paths"]["public_vs_fixture_scoreboard_split"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
