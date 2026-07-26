"""CLI runner for machine license/terms verifier."""
from __future__ import annotations

import json

from .machine_license_terms_verifier import run_machine_license_terms_verifier


def main() -> int:
    result = run_machine_license_terms_verifier()
    print(json.dumps({
        "candidate_count": result["candidate_count"],
        "accepted_license_terms_count": result["accepted_license_terms_count"],
        "rejected_license_terms_count": result["rejected_license_terms_count"],
        "summary_path": result["artifact_paths"]["machine_license_terms_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

