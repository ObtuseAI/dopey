"""Run the free/public data provenance gate without fetching data."""
from __future__ import annotations

import json
from typing import Any

from .free_data_candidate_registry import write_free_data_candidate_registry
from .free_data_provenance_gate import write_free_data_provenance_gate


def run_free_data_provenance_gate() -> dict[str, Any]:
    registry = write_free_data_candidate_registry()
    gate = write_free_data_provenance_gate()
    return {
        **registry,
        **gate,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "paper_only": True,
        "live_blocked": True,
    }


def main() -> int:
    result = run_free_data_provenance_gate()
    print(json.dumps({
        "free_data_candidate_count": result["free_data_candidate_count"],
        "free_data_evidence_allowed_count": result["free_data_evidence_allowed_count"],
        "free_data_manual_review_required_count": result["free_data_manual_review_required_count"],
        "network_fetch_performed": result["network_fetch_performed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
