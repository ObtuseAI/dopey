"""Network-free CLI for signed stock-mover discovery.

Ranks the biggest daily gainers and decliners independently, cross-references
both option-outcome tails, and emits competing continuation and mean-reversion
hypotheses as research flags, never trade signals.

    python -m dopey.strategy_engineering.run_swing_target_discovery \
        --history-root dopey_data/history/raw \
        --chains-root dopey_data/real/raw/options_chains
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .swing_target_discovery import discover_swing_targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Swing-target discovery (paper research; no edge claimed).")
    parser.add_argument("--history-root", default="dopey_data/history/raw")
    parser.add_argument("--chains-root", default="dopey_data/real/raw/options_chains")
    parser.add_argument("--biggest-mover-count", type=int, default=40)
    parser.add_argument("--max-targets", type=int, default=25)
    parser.add_argument("--no-option-cross-reference", action="store_true")
    args = parser.parse_args(argv)

    report = discover_swing_targets(
        Path(args.history_root),
        chains_root=None if args.no_option_cross_reference else Path(args.chains_root),
        biggest_mover_count=args.biggest_mover_count,
        max_targets=args.max_targets,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
