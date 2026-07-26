"""OPERATOR TOOL - compile an external strategy claim into a falsifiable spec.

Reads claim text (a file path or literal), runs it through the Strategy Claim
Compiler (gemini-3.6-flash for interpretation; deterministic validation and
honesty stamps), and writes the compiled spec. The spec is a hypothesis to
prosecute with the existing machinery - never evidence, never authority.

Usage:
  .venv\\Scripts\\python operator_tools\\operator_compile_strategy_claim.py --text "buy calls when momentum turns bullish" --kind reddit --ref <url>
  .venv\\Scripts\\python operator_tools\\operator_compile_strategy_claim.py --file claim.txt --kind youtube
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_acceleration.strategy_claim_compiler import compile_claim  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402

CLAIMS_DIR = REPO / "artifacts" / "dopey" / "compiled_claims"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a strategy claim into a falsifiable spec")
    parser.add_argument("--text", help="claim text literal")
    parser.add_argument("--file", help="path to a file holding the claim text")
    parser.add_argument("--kind", default="unknown", help="reddit|youtube|repo|article|unknown")
    parser.add_argument("--ref", default="", help="source url or reference")
    arguments = parser.parse_args()

    if arguments.file:
        raw_claim = Path(arguments.file).read_text(encoding="utf-8")
    elif arguments.text:
        raw_claim = arguments.text
    else:
        parser.error("provide --text or --file")

    spec = compile_claim(raw_claim, {"kind": arguments.kind, "ref": arguments.ref})
    CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = CLAIMS_DIR / f"compiled_claim_{stamp}.json"
    write_json_atomic(out_path, spec)
    print(
        json.dumps(
            {
                "compile_status": spec.get("compile_status"),
                "thesis_direction": spec.get("extracted", {}).get("thesis_direction"),
                "missing_or_ambiguous": spec.get("extracted", {}).get("missing_or_ambiguous"),
                "evidence_status": spec.get("evidence_status"),
                "artifact": str(out_path),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
