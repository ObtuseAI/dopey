"""CLI for the quote-priced options unlock gate."""
from __future__ import annotations

import json

from .quote_priced_options_unlock_gate import run_quote_priced_options_unlock_gate


def main() -> int:
    summary = run_quote_priced_options_unlock_gate()
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
