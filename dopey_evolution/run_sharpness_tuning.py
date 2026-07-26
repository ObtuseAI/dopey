"""Run DOPEY's evidence-gated paper-only sharpness tuning bundle."""
from __future__ import annotations

import json

from .sharpness_tuning import run_sharpness_tuning


def main() -> int:
    result = run_sharpness_tuning()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["sharpness_status"] == "complete_paper_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
