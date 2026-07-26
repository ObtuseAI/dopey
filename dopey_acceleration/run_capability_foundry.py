"""Build the governed, execution-free repository capability snapshot."""

from __future__ import annotations

import json

from .capability_foundry import (
    CAPABILITY_FOUNDRY_PATH,
    CATALOG_PATH,
    build_capability_foundry_snapshot,
)


def main() -> None:
    result = build_capability_foundry_snapshot(
        CATALOG_PATH,
        CAPABILITY_FOUNDRY_PATH,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
