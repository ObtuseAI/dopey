"""Fetch credential-free quant context into the governed paper-research lake."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dopey_data.quant_context_intake import (
    SEC_USER_AGENT_ENVIRONMENT_VARIABLE,
    run_quant_context_intake,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPOSITORY_ROOT / "dopey_data" / "real" / "raw" / "quant_context",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=REPOSITORY_ROOT / "dopey_data" / "real" / "manifests" / "quant_context_manifest.json",
    )
    parser.add_argument("--sec-symbol-limit", type=int, default=250)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = run_quant_context_intake(
        arguments.output_root.resolve(),
        arguments.manifest_path.resolve(),
        int(arguments.sec_symbol_limit),
        datetime.now(timezone.utc),
        os.environ.get(SEC_USER_AGENT_ENVIRONMENT_VARIABLE),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)
    return 0 if manifest["pipeline_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
