"""Build the content-addressed DOPEY Strategy Evidence Dossier."""
from __future__ import annotations

import json
from pathlib import Path

from .strategy_evidence_dossier import build_strategy_evidence_dossier, default_dossier_source_paths


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    summary = build_strategy_evidence_dossier(
        REPOSITORY_ROOT,
        default_dossier_source_paths(REPOSITORY_ROOT),
        REPOSITORY_ROOT / "artifacts" / "dopey" / "runs",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "runs" / "latest_dossier.json",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if str(summary["dossier_status"]).startswith("complete_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
