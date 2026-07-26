"""CLI runner for public signal mutation factory V4."""
from __future__ import annotations

import json

from .public_signal_mutation_factory_v4 import run_public_signal_mutation_factory_v4


def main() -> int:
    summary = run_public_signal_mutation_factory_v4()
    print(json.dumps({
        "public_signal_mutation_status": summary["public_signal_mutation_status"],
        "signal_variant_count": summary["signal_variant_count"],
        "near_champion_expansion_count": summary["near_champion_expansion_count"],
        "family_count": summary["family_count"],
        "unique_micro_cohort_count": summary["unique_micro_cohort_count"],
        "unique_setup_cohort_count": summary["unique_setup_cohort_count"],
        "public_data_only": summary["public_data_only"],
        "fixture_signal_count": summary["fixture_signal_count"],
        "summary_path": summary["artifact_paths"]["public_signal_mutation_factory_v4_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
