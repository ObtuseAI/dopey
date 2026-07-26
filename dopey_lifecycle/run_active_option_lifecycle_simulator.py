"""CLI runner for the active long-call/long-put lifecycle simulator."""
from __future__ import annotations

import json
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .lifecycle_policy import default_lifecycle_policy
from .lifecycle_simulator import build_lifecycle_cases, lifecycle_artifact_paths, simulate_lifecycle_cases, write_lifecycle_outputs


def run_active_option_lifecycle_simulator() -> dict[str, Any]:
    policy = default_lifecycle_policy()
    cases = build_lifecycle_cases()
    bundle = simulate_lifecycle_cases(policy, cases)
    artifact_paths = write_lifecycle_outputs(policy, bundle)
    result = {
        "active_option_lifecycle_simulator_status": "ok",
        "summary": bundle["summary"],
        "artifact_paths": artifact_paths,
        "fixture_only": True,
        "paper_only": True,
        "live_blocked": True,
    }
    result["reproducibility_hash"] = reproducibility_hash(result)
    return result


def main() -> int:
    result = run_active_option_lifecycle_simulator()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["active_option_lifecycle_simulator_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
