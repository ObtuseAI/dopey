"""CLI for safe append long docs V5."""
from __future__ import annotations

import json

from dopey_validation.safe_append_canon_validation_docs_v5 import run_safe_append_canon_validation_docs_v5


def main() -> int:
    summary = run_safe_append_canon_validation_docs_v5()
    print(
        json.dumps(
            {
                "safe_append_docs_status": summary["safe_append_docs_status"],
                "canon_append_status": summary["canon_append_status"],
                "validation_report_append_status": summary["validation_report_append_status"],
                "invalid_utf8_detected": summary["invalid_utf8_detected"],
                "backup_count": summary["backup_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
