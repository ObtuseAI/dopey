"""Offline local history dataset loader for daily OHLCV files."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .history_models import (
    ALLOWED_HISTORY_FORMATS,
    HistoryBar,
    HistoryDataFile,
    HistoryDatasetManifest,
)


class HistoryDatasetError(ValueError):
    """Raised when a local history dataset cannot be loaded safely."""


REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_ROOT = REPO_ROOT / "dopey_data" / "history"
HISTORY_RAW_DIR = HISTORY_ROOT / "raw"
HISTORY_MANIFEST_PATH = HISTORY_ROOT / "history_dataset_manifest.json"


def file_sha256(path: Path | str) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_history_manifest(path: Path | str) -> HistoryDatasetManifest:
    target = Path(path)
    text = target.read_text(encoding="utf-8").strip()
    if not text:
        raise HistoryDatasetError(f"history dataset manifest is empty: {target}")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise HistoryDatasetError(f"history dataset manifest must be a JSON object: {target}")
    return HistoryDatasetManifest.from_dict(parsed)


def resolve_history_data_file_path(
    manifest_path: Path | str,
    manifest: HistoryDatasetManifest,
    file_ref: HistoryDataFile,
) -> Path:
    candidate = Path(file_ref.path)
    if candidate.is_absolute():
        raise HistoryDatasetError(
            "history manifest data-file path must be relative: "
            f"manifest={manifest_path}, path={file_ref.path!r}"
        )
    if any(part == ".." for part in candidate.parts):
        raise HistoryDatasetError(
            "history manifest data-file path contains parent traversal: "
            f"manifest={manifest_path}, path={file_ref.path!r}"
        )
    manifest_parent = Path(manifest_path).resolve(strict=False).parent
    raw_dir = Path(manifest.raw_data_directory)
    if raw_dir.is_absolute():
        raw_root = raw_dir.resolve(strict=False)
        _require_path_within(
            raw_root,
            manifest_parent,
            "absolute raw-data directory must remain under the manifest directory",
        )
    else:
        if any(part == ".." for part in raw_dir.parts):
            raise HistoryDatasetError(
                "history manifest raw-data directory contains parent traversal: "
                f"manifest={manifest_path}, raw_data_directory={manifest.raw_data_directory!r}"
            )
        raw_parts = [part.lower() for part in raw_dir.parts]
        raw_root = (
            REPO_ROOT / raw_dir
            if raw_parts and raw_parts[0] == "dopey_data"
            else manifest_parent / raw_dir
        ).resolve(strict=False)
    relative_candidate = (
        Path(*candidate.parts[1:])
        if candidate.parts
        and candidate.parts[0].lower() == raw_root.name.lower()
        else candidate
    )
    resolved = (raw_root / relative_candidate).resolve(strict=False)
    _require_path_within(
        resolved,
        raw_root,
        "history data-file path escaped the declared raw-data directory",
    )
    return resolved


def _require_path_within(candidate: Path, root: Path, message: str) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise HistoryDatasetError(
            f"{message}: candidate={candidate}, root={root}"
        ) from error


def load_raw_history_records(file_path: Path | str, file_format: str) -> list[dict[str, Any]]:
    normalized_format = file_format.lower()
    if normalized_format not in ALLOWED_HISTORY_FORMATS:
        raise HistoryDatasetError(f"unsupported history file format: {normalized_format}")
    target = Path(file_path)
    if normalized_format == "csv":
        return _load_csv_records(target)
    if normalized_format == "jsonl":
        return _load_jsonl_records(target)
    raise HistoryDatasetError(f"unsupported history file format: {normalized_format}")


def load_history_bars_from_file(file_path: Path | str, file_format: str) -> list[HistoryBar]:
    records = load_raw_history_records(file_path, file_format)
    return [HistoryBar.from_dict(record) for record in records]


def load_manifest_history_bars(manifest_path: Path | str, manifest: HistoryDatasetManifest) -> list[HistoryBar]:
    bars: list[HistoryBar] = []
    for file_ref in manifest.data_files:
        path = resolve_history_data_file_path(manifest_path, manifest, file_ref)
        bars.extend(load_history_bars_from_file(path, file_ref.format))
    return bars


def _load_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise HistoryDatasetError(f"jsonl row must be object: {path}:{line_number}")
        records.append(parsed)
    return records
