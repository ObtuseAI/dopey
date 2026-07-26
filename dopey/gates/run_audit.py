"""CLI for the structural autonomous-threshold audit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .audit import audit_threshold_fabric, write_threshold_audit
from .policy import AUTONOMOUS_GATE_POLICIES


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit DOPEY autonomous threshold policies")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    audit = audit_threshold_fabric(AUTONOMOUS_GATE_POLICIES, datetime.now(timezone.utc))
    write_threshold_audit(arguments.output, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    if audit["audit_status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
