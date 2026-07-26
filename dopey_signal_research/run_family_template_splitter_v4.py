"""CLI runner for V4 family template splitter."""
from __future__ import annotations

import json

from dopey_signal_research.family_template_splitter_v4 import run_family_template_splitter_v4


def main() -> int:
    summary = run_family_template_splitter_v4()
    print(
        json.dumps(
            {
                "family_template_splitter_status": summary["family_template_splitter_status"],
                "continuation_subfamily_count": summary["continuation_subfamily_count"],
                "volume_subfamily_count": summary["volume_subfamily_count"],
                "volume_rescue_status": summary.get("volume_rescue_status", ""),
                "summary_path": summary["artifact_paths"]["family_template_splitter_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
