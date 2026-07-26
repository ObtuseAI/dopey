"""CLI runner for public signal mutation factory V3."""
from __future__ import annotations

import json

from .public_signal_mutation_factory_v3 import run_public_signal_mutation_factory_v3


def main() -> int:
    summary = run_public_signal_mutation_factory_v3()
    print(json.dumps({
        "public_signal_mutation_status": summary["public_signal_mutation_status"],
        "signal_variant_count": summary["signal_variant_count"],
        "family_count": summary["family_count"],
        "summary_path": summary["artifact_paths"]["public_signal_mutation_factory_v3_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
