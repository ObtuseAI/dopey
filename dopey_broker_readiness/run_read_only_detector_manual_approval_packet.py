"""Run the offline manual-approval packet builder for a future read-only detector."""
from __future__ import annotations

import json
import sys

from .manual_approval_packet_builder import build_manual_approval_packet_outputs


def main(argv: list[str] | None = None) -> int:
    result = build_manual_approval_packet_outputs()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["manual_approval_packet_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
