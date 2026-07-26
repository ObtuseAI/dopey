"""Streaming atomic JSONL writer: bounded memory, replace-only visibility.

The honest backtester's trade ledger exceeds 500MB at the full universe. The
writer must stream records (no whole-payload string) and expose either the old
file or the complete new file - never a torn intermediate (the 2026-07-21
ledger-corruption incident class).
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_research_pipeline.artifact_io import write_jsonl_atomic_streaming


def test_writes_records_as_json_lines(tmp_path: Path) -> None:
    target = tmp_path / "ledger.jsonl"
    records = [{"trade_id": index, "pnl": index * 0.5} for index in range(5)]
    written = write_jsonl_atomic_streaming(target, records)
    assert written == 5
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["trade_id"] for line in lines] == [0, 1, 2, 3, 4]
    assert not target.with_name(target.name + ".tmp").exists()


def test_replaces_existing_file_atomically(tmp_path: Path) -> None:
    target = tmp_path / "ledger.jsonl"
    target.write_text('{"old": true}\n', encoding="utf-8")
    write_jsonl_atomic_streaming(target, [{"new": True}])
    assert json.loads(target.read_text(encoding="utf-8"))["new"] is True


def test_empty_iterable_writes_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "ledger.jsonl"
    assert write_jsonl_atomic_streaming(target, []) == 0
    assert target.read_text(encoding="utf-8") == ""


def test_generator_input_is_consumed_once_lazily(tmp_path: Path) -> None:
    target = tmp_path / "ledger.jsonl"
    consumed: list[int] = []

    def generate():
        for index in range(3):
            consumed.append(index)
            yield {"index": index}

    assert write_jsonl_atomic_streaming(target, generate()) == 3
    assert consumed == [0, 1, 2]


def test_failing_record_leaves_prior_file_intact(tmp_path: Path) -> None:
    target = tmp_path / "ledger.jsonl"
    target.write_text('{"old": true}\n', encoding="utf-8")

    def explode():
        yield {"fine": 1}
        raise RuntimeError("mid-write failure")

    try:
        write_jsonl_atomic_streaming(target, explode())
    except RuntimeError:
        pass
    assert json.loads(target.read_text(encoding="utf-8"))["old"] is True


def test_keep_backup_preserves_previous_generation(tmp_path: Path) -> None:
    target = tmp_path / "ledger.jsonl"
    target.write_text('{"old": true}\n', encoding="utf-8")
    write_jsonl_atomic_streaming(target, [{"new": True}], keep_backup=True)
    backup = target.with_name(target.name + ".bak")
    assert json.loads(backup.read_text(encoding="utf-8"))["old"] is True
    assert json.loads(target.read_text(encoding="utf-8"))["new"] is True
