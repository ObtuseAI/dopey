"""Deterministic normalization for a portable-reader scrollbar overflow defect."""

from __future__ import annotations

from pathlib import Path


PORTABLE_HEADER_WIDTH = (
    ".portable-page-header{position:sticky;top:0;z-index:60;display:flex;align-items:center;"
    "justify-content:space-between;width:100vw;height:48px;min-height:48px;"
    "margin-right:calc(50% - 50vw);margin-left:calc(50% - 50vw);"
)
NORMALIZED_HEADER_WIDTH = (
    ".portable-page-header{position:sticky;top:0;z-index:60;display:flex;align-items:center;"
    "justify-content:space-between;width:100%;height:48px;min-height:48px;"
    "margin-right:0;margin-left:0;"
)
HEAD_MARKER = "<head>"
READER_HEADER_OVERRIDE = (
    '<style data-dopey-portable-overflow-normalization="v1">'
    ".portable-page-header,.analytics-top-bar{"
    "width:100%!important;margin-right:0!important;margin-left:0!important"
    "}"
    "</style>"
)


def normalize_portable_header_width(html: str) -> str:
    occurrence_count = html.count(PORTABLE_HEADER_WIDTH)
    if occurrence_count != 1:
        raise ValueError(
            "portable header normalization requires exactly one known CSS signature: "
            f"occurrence_count={occurrence_count}"
        )
    if html.count(HEAD_MARKER) != 1:
        raise ValueError(
            "portable header normalization requires exactly one head marker: "
            f"occurrence_count={html.count(HEAD_MARKER)}"
        )
    if READER_HEADER_OVERRIDE in html:
        raise ValueError("portable header normalization rejects already-normalized HTML")
    fallback_normalized = html.replace(PORTABLE_HEADER_WIDTH, NORMALIZED_HEADER_WIDTH, 1)
    return fallback_normalized.replace(
        HEAD_MARKER,
        f"{HEAD_MARKER}\n{READER_HEADER_OVERRIDE}",
        1,
    )


def normalize_portable_html_file(source_path: Path, output_path: Path) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"portable HTML input is missing: path={source_path}")
    normalized = normalize_portable_header_width(source_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(normalized, encoding="utf-8")
