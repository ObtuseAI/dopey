"""CLI for the DOPEY evidence artifact contract registry and bundle audit."""

from __future__ import annotations

import json
from pathlib import Path

from .artifact_contracts import audit_evidence_artifact_bundle


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    result = audit_evidence_artifact_bundle(
        repository_root,
        repository_root / "artifacts" / "dopey" / "contracts" / "latest_bundle_audit.json",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
