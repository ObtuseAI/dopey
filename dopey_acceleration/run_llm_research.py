"""CLI for the state-change-triggered DOPEY LLM research lane."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .llm_research import run_llm_research_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded multi-model analysis over changed DOPEY evidence")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    output = run_llm_research_cycle(
        arguments.repo_root,
        arguments.output_root,
        arguments.timeout_seconds,
        bool(arguments.force),
        datetime.now(timezone.utc),
    )
    print(json.dumps(output, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
