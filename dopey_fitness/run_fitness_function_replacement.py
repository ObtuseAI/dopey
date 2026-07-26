"""CLI entrypoint for DOPEY's truth-gated fitness replacement."""
from __future__ import annotations

import json

from .truth_gated_fitness_engine import run_fitness_function_replacement


def main() -> int:
    result = run_fitness_function_replacement()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

