"""CLI for model-priced options research expansion V2."""
from __future__ import annotations

import json

from .model_priced_options_research_expansion_v2 import run_model_priced_options_research_expansion_v2


def main() -> int:
    result = run_model_priced_options_research_expansion_v2()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
