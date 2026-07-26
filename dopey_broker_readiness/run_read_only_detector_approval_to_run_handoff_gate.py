"""CLI entrypoint for the offline approval-to-run handoff gate."""
from __future__ import annotations

import json

from .approval_to_run_handoff_gate import validate_read_only_detector_approval_to_run_handoff_gate


def main() -> None:
    result = validate_read_only_detector_approval_to_run_handoff_gate()
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
