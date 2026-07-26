"""CLI for model-priced options research expansion."""
from __future__ import annotations

import json

from .model_priced_options_research_expansion import run_model_priced_options_research_expansion


def main() -> int:
    summary = run_model_priced_options_research_expansion()
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
