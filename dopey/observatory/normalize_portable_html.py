"""CLI for the portable-reader header overflow normalization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .portable_html import normalize_portable_html_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize the generated portable observatory header width")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    normalize_portable_html_file(arguments.input, arguments.output)
    print(json.dumps({
        "input": str(arguments.input),
        "output": str(arguments.output),
        "normalization": "portable_header_width_100vw_to_100_percent",
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
