"""CLI for the state-change-gated autonomous coached-evolution lane."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .coached_evolution_cycle import run_coached_evolution_cycle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded coach, quarantine, and deterministic experiment phases"
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--head-coach", choices=("claude", "codex"), required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--daily-new-session-limit", type=int, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--coach-root", type=Path, required=True)
    parser.add_argument("--proposal-root", type=Path, required=True)
    parser.add_argument("--history-manifest", type=Path, required=True)
    parser.add_argument("--experiment-root", type=Path, required=True)
    arguments = parser.parse_args()
    result = run_coached_evolution_cycle(
        arguments.repo_root,
        str(arguments.symbol),
        str(arguments.timeframe),
        str(arguments.head_coach),
        int(arguments.timeout_seconds),
        int(arguments.daily_new_session_limit),
        arguments.output_root,
        arguments.coach_root,
        arguments.proposal_root,
        arguments.history_manifest,
        arguments.experiment_root,
        datetime.now(timezone.utc),
    )
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
