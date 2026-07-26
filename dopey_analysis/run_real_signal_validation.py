"""Compatibility CLI for real signal validation gate."""
from __future__ import annotations

import json
from typing import Any

from .run_real_signal_validation_gate import run_real_signal_validation_gate


def run_real_signal_validation() -> dict[str, Any]:
    return run_real_signal_validation_gate()


def main() -> int:
    result = run_real_signal_validation()
    print(json.dumps({
        "real_signal_validation_status": result["real_signal_validation_status"],
        "real_signal_evidence": result["real_signal_evidence"],
        "real_history_used": result["real_history_used"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
