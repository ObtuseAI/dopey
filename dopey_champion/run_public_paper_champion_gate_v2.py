"""CLI runner for public paper champion gate V2."""
from __future__ import annotations

import json

from .public_paper_champion_gate_v2 import run_public_paper_champion_gate_v2


def main() -> int:
    summary = run_public_paper_champion_gate_v2()
    print(json.dumps({
        "public_paper_champion_gate_status": summary["public_paper_champion_gate_status"],
        "candidate_count": summary["candidate_count"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "champion_names": summary["champion_names"],
        "near_champion_count": summary["near_champion_count"],
        "sample_repair_candidate_count": summary["sample_repair_candidate_count"],
        "walk_forward_repair_candidate_count": summary["walk_forward_repair_candidate_count"],
        "rejection_count": summary["rejection_count"],
        "top_rejection_reasons": summary["top_rejection_reasons"],
        "thresholds_lowered": summary["thresholds_lowered"],
        "summary_path": summary["artifact_paths"]["public_paper_champion_gate_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
