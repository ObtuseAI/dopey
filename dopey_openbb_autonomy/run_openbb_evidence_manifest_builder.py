"""CLI for OpenBB evidence manifest builder."""
from __future__ import annotations

import json

from .openbb_evidence_manifest_builder import run_openbb_evidence_manifest_builder


def main() -> int:
    result = run_openbb_evidence_manifest_builder()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
