"""CLI runner for retune hardening gate."""
from __future__ import annotations

import json

from dopey_champion.conditional_champion_retune_hardening_gate_v1 import run_conditional_champion_retune_hardening_gate_v1


def main() -> int:
    summary = run_conditional_champion_retune_hardening_gate_v1()
    print(json.dumps({
        "conditional_champion_retune_hardening_status": summary["conditional_champion_retune_hardening_status"],
        "retuned_hardened_count": summary["retuned_hardened_count"],
        "retuned_conditional_count": summary["retuned_conditional_count"],
        "summary_path": summary["artifact_paths"]["conditional_champion_retune_hardening_gate_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
