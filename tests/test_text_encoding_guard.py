"""Tests: non-mutating text encoding guard."""
from __future__ import annotations

from pathlib import Path

from dopey_validation.text_encoding_guard import (
    ascii_safe_append,
    create_sanitized_preview,
    detect_invalid_utf8,
    original_file_hash,
    write_encoding_report,
)


def test_text_encoding_guard_detects_invalid_utf8(tmp_path: Path) -> None:
    target = tmp_path / "bad.md"
    target.write_bytes(b"ok\n\xffbad\n")
    diagnostic = detect_invalid_utf8(target)
    assert diagnostic.valid_utf8 is False
    assert diagnostic.invalid_offsets == [3]


def test_text_encoding_guard_writes_non_mutating_report(tmp_path: Path) -> None:
    target = tmp_path / "bad.md"
    report = tmp_path / "report.json"
    target.write_bytes(b"ok\n\xffbad\n")
    before = original_file_hash(target)
    record = write_encoding_report(target, report)
    assert report.exists()
    assert record["non_mutating"] is True
    assert original_file_hash(target) == before


def test_text_encoding_guard_creates_sanitized_preview(tmp_path: Path) -> None:
    target = tmp_path / "bad.md"
    preview = tmp_path / "preview.md"
    target.write_bytes(b"ok\n\xffbad\n")
    create_sanitized_preview(target, preview)
    assert preview.exists()
    assert "\ufffd" in preview.read_text(encoding="utf-8")


def test_text_encoding_guard_does_not_rewrite_original_by_default(tmp_path: Path) -> None:
    target = tmp_path / "bad.md"
    target.write_bytes(b"ok\n\xffbad\n")
    before = original_file_hash(target)
    write_encoding_report(target, tmp_path / "report.json", tmp_path / "preview.md")
    assert original_file_hash(target) == before


def test_ascii_safe_append_supported(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_text("base", encoding="ascii")
    ascii_safe_append(target, "append")
    assert target.read_text(encoding="ascii").endswith("append")
