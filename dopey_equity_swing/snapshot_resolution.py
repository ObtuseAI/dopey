"""Resolve current, hash-pinned swing-research snapshots without date constants."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from .contract_selector import validate_option_chain_file


class SnapshotResolutionError(RuntimeError):
    """Raised when a current research snapshot cannot be proven usable."""


class EarningsSnapshot(TypedDict):
    path: Path
    snapshot_date: str
    sha256: str
    symbol_count: int
    covered_symbols: tuple[str, ...]
    source_labels: tuple[str, ...]


class EarningsEvidence(TypedDict):
    snapshot_date: str
    snapshot_sha256: str
    snapshot_symbol_count: int
    symbol_covered: bool
    next_earnings_date: str
    source_labels: list[str]
    status: str
    live_candidate_event_gate_passed: bool


class OptionSnapshot(TypedDict):
    status: str
    path: Path | None
    snapshot_date: str
    manifest_created_at: str
    manifest_sha256: str
    manifest_chain_file_count: int
    manifest_chain_row_count: int
    chain_file_count: int
    chain_row_count: int
    combined_chain_sha256: str
    blocker: str


class _ValidatedChainFile(TypedDict):
    relative_path: str
    path: Path
    snapshot_date: date
    symbol: str
    sha256: str
    row_count: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dated_name(value: str, suffix: str) -> date | None:
    if not value.endswith(suffix):
        return None
    raw_date = value[: -len(suffix)]
    try:
        return date.fromisoformat(raw_date)
    except ValueError:
        return None


def resolve_earnings_snapshot(
    earnings_root: Path,
    market_as_of_date: date,
) -> EarningsSnapshot:
    """Require an earnings snapshot aligned with the validated price frontier."""
    candidates = [
        (snapshot_date, path)
        for path in earnings_root.glob("*_earnings.csv")
        if (snapshot_date := _dated_name(path.name, "_earnings.csv")) is not None
        and snapshot_date <= market_as_of_date
    ]
    if not candidates:
        raise SnapshotResolutionError(
            "equity swing research lacks a nonfuture earnings snapshot: "
            f"root={earnings_root}, market_as_of_date={market_as_of_date.isoformat()}"
        )
    snapshot_date, path = max(candidates, key=lambda candidate: candidate[0])
    if snapshot_date != market_as_of_date:
        raise SnapshotResolutionError(
            "equity swing earnings snapshot is not aligned with the price frontier: "
            f"path={path}, snapshot_date={snapshot_date.isoformat()}, "
            f"market_as_of_date={market_as_of_date.isoformat()}"
        )
    if path.stat().st_size <= 0:
        raise SnapshotResolutionError(f"equity swing earnings snapshot is empty: path={path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required_fields = {
                "snapshot_date",
                "symbol",
                "earnings_date",
                "source",
            }
            actual_fields = set(reader.fieldnames or ())
            if not required_fields.issubset(actual_fields):
                raise SnapshotResolutionError(
                    "equity swing earnings snapshot schema is incomplete: "
                    f"path={path}, required={sorted(required_fields)}, "
                    f"actual={sorted(actual_fields)}"
                )
            rows = list(reader)
    except OSError as error:
        raise SnapshotResolutionError(
            f"equity swing earnings snapshot is unreadable: path={path}, error={error}"
        ) from error
    if not rows:
        raise SnapshotResolutionError(
            f"equity swing earnings snapshot contains zero events: path={path}"
        )
    symbols: set[str] = set()
    source_labels: set[str] = set()
    observed_events: set[tuple[str, date]] = set()
    for line_number, row in enumerate(rows, start=2):
        row_snapshot_date = str(row.get("snapshot_date", "")).strip()
        symbol = str(row.get("symbol", "")).strip().upper()
        source = str(row.get("source", "")).strip()
        raw_earnings_date = str(row.get("earnings_date", "")).strip()
        try:
            event_date = date.fromisoformat(raw_earnings_date)
        except ValueError as error:
            raise SnapshotResolutionError(
                "equity swing earnings event date is invalid: "
                f"path={path}, line={line_number}, value={raw_earnings_date!r}"
            ) from error
        if row_snapshot_date != snapshot_date.isoformat():
            raise SnapshotResolutionError(
                "equity swing earnings row is not aligned with its snapshot: "
                f"path={path}, line={line_number}, row_snapshot_date={row_snapshot_date!r}, "
                f"expected={snapshot_date.isoformat()}"
            )
        if not symbol or not source:
            raise SnapshotResolutionError(
                "equity swing earnings row lacks symbol or source provenance: "
                f"path={path}, line={line_number}"
            )
        if event_date < snapshot_date:
            raise SnapshotResolutionError(
                "equity swing earnings snapshot contains a past event: "
                f"path={path}, line={line_number}, symbol={symbol}, "
                f"earnings_date={event_date.isoformat()}"
            )
        event_key = (symbol, event_date)
        if event_key in observed_events:
            raise SnapshotResolutionError(
                "equity swing earnings snapshot contains a duplicate event: "
                f"path={path}, line={line_number}, symbol={symbol}, "
                f"earnings_date={event_date.isoformat()}"
            )
        observed_events.add(event_key)
        symbols.add(symbol)
        source_labels.add(source)
    return {
        "path": path,
        "snapshot_date": snapshot_date.isoformat(),
        "sha256": _sha256(path),
        "symbol_count": len(symbols),
        "covered_symbols": tuple(sorted(symbols)),
        "source_labels": tuple(sorted(source_labels)),
    }


def build_earnings_evidence(
    snapshot: EarningsSnapshot,
    symbol: str,
    next_earnings_date: str | None,
) -> EarningsEvidence:
    """Describe symbol-level event coverage without treating absence as no event."""
    normalized_symbol = symbol.strip().upper()
    symbol_covered = normalized_symbol in snapshot["covered_symbols"]
    observed_date = "" if next_earnings_date is None else next_earnings_date
    complete = symbol_covered and bool(observed_date)
    return {
        "snapshot_date": snapshot["snapshot_date"],
        "snapshot_sha256": snapshot["sha256"],
        "snapshot_symbol_count": snapshot["symbol_count"],
        "symbol_covered": symbol_covered,
        "next_earnings_date": observed_date,
        "source_labels": list(snapshot["source_labels"]),
        "status": (
            "frontier_aligned_symbol_event_observed"
            if complete
            else "unresolved_symbol_absence"
        ),
        "live_candidate_event_gate_passed": complete,
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SnapshotResolutionError(f"options manifest is missing: path={path}")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotResolutionError(
            f"options manifest is unreadable: path={path}, error={error}"
        ) from error
    if not isinstance(payload, dict):
        raise SnapshotResolutionError(
            f"options manifest must be an object: path={path}"
        )
    return payload


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise SnapshotResolutionError(
                f"options manifest contains a duplicate JSON key: key={key!r}"
            )
        output[key] = value
    return output


def _manifest_created_at(value: Any, decision_time: datetime) -> str:
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")
    raw = str(value).strip()
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise SnapshotResolutionError(
            f"options manifest created_at is invalid: value={raw!r}"
        ) from error
    if observed.tzinfo is None:
        raise SnapshotResolutionError(
            f"options manifest created_at requires a timezone: value={raw!r}"
        )
    if observed.astimezone(timezone.utc) > decision_time.astimezone(timezone.utc):
        raise SnapshotResolutionError(
            "options manifest is from the future: "
            f"created_at={observed.isoformat()}, decision_time={decision_time.isoformat()}"
        )
    return observed.astimezone(timezone.utc).isoformat()


def _blocked_option_snapshot(
    manifest_path: Path,
    manifest_created_at: str,
    blocker: str,
) -> OptionSnapshot:
    return {
        "status": "blocked_no_current_hash_pinned_option_snapshot",
        "path": None,
        "snapshot_date": "",
        "manifest_created_at": manifest_created_at,
        "manifest_sha256": _readable_sha256(manifest_path),
        "manifest_chain_file_count": 0,
        "manifest_chain_row_count": 0,
        "chain_file_count": 0,
        "chain_row_count": 0,
        "combined_chain_sha256": "",
        "blocker": blocker,
    }


def resolve_option_snapshot(
    repository_root: Path,
    chain_root: Path,
    manifest_path: Path,
    market_as_of_date: date,
    decision_time: datetime,
) -> OptionSnapshot:
    """Return only an exact-frontier, manifest-hash-verified option snapshot.

    Option evidence is intentionally optional for the stock-direction lane. A
    missing or stale option snapshot returns an explicit blocked record so the
    equity engine can continue while contract selection remains unavailable.
    """
    manifest_created_at = ""
    try:
        manifest = _load_manifest(manifest_path)
        if (
            manifest.get("paper_only") is not True
            or manifest.get("live_blocked") is not True
            or manifest.get("not_live_data") is not True
        ):
            raise SnapshotResolutionError(
                "options manifest violates the research-only snapshot contract: "
                f"path={manifest_path}"
            )
        manifest_created_at = _manifest_created_at(
            manifest.get("created_at"), decision_time
        )
        advertised_dates = _advertised_snapshot_dates(
            manifest.get("snapshot_dates"),
            manifest_path,
        )
        decision_date = decision_time.astimezone(timezone.utc).date()
        future_dates = sorted(
            value.isoformat() for value in advertised_dates if value > decision_date
        )
        if future_dates:
            raise SnapshotResolutionError(
                "options manifest advertises future snapshot dates: "
                f"decision_date={decision_date.isoformat()}, future_dates={future_dates}"
            )
        raw_hashes = manifest.get("file_hashes")
        if not isinstance(raw_hashes, dict):
            raise SnapshotResolutionError(
                f"options manifest file_hashes must be an object: path={manifest_path}"
            )
        chain_entries = _validate_manifest_chain_files(
            repository_root,
            chain_root,
            raw_hashes,
            advertised_dates,
        )
    except SnapshotResolutionError as error:
        return _blocked_option_snapshot(
            manifest_path,
            manifest_created_at,
            str(error),
        )

    snapshot_date = market_as_of_date.isoformat()
    selected_entries = tuple(
        entry
        for entry in chain_entries
        if entry["snapshot_date"] == market_as_of_date
    )
    if not selected_entries:
        return _blocked_option_snapshot(
            manifest_path,
            manifest_created_at,
            f"manifest_missing_market_frontier_snapshot:{snapshot_date}",
        )
    snapshot_path = chain_root / snapshot_date
    combined_payload = "".join(
        f"{entry['relative_path']}:{entry['sha256']}\n"
        for entry in selected_entries
    )
    combined = hashlib.sha256(combined_payload.encode("utf-8")).hexdigest()
    return {
        "status": "current_hash_pinned_option_snapshot",
        "path": snapshot_path,
        "snapshot_date": snapshot_date,
        "manifest_created_at": manifest_created_at,
        "manifest_sha256": _sha256(manifest_path),
        "manifest_chain_file_count": len(chain_entries),
        "manifest_chain_row_count": sum(
            entry["row_count"] for entry in chain_entries
        ),
        "chain_file_count": len(selected_entries),
        "chain_row_count": sum(entry["row_count"] for entry in selected_entries),
        "combined_chain_sha256": combined,
        "blocker": "",
    }


def _readable_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return _sha256(path)
    except OSError:
        return ""


def _advertised_snapshot_dates(
    raw_dates: Any,
    manifest_path: Path,
) -> tuple[date, ...]:
    if not isinstance(raw_dates, list) or not raw_dates:
        raise SnapshotResolutionError(
            "options manifest snapshot_dates must be a nonempty list: "
            f"path={manifest_path}"
        )
    output: list[date] = []
    observed: set[date] = set()
    for value in raw_dates:
        raw_date = str(value).strip()
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError as error:
            raise SnapshotResolutionError(
                "options manifest contains an invalid snapshot date: "
                f"path={manifest_path}, value={raw_date!r}"
            ) from error
        if parsed in observed:
            raise SnapshotResolutionError(
                "options manifest contains a duplicate snapshot date: "
                f"path={manifest_path}, value={raw_date}"
            )
        observed.add(parsed)
        output.append(parsed)
    return tuple(sorted(output))


def _validate_manifest_chain_files(
    repository_root: Path,
    chain_root: Path,
    raw_hashes: dict[Any, Any],
    advertised_dates: tuple[date, ...],
) -> tuple[_ValidatedChainFile, ...]:
    if not chain_root.is_dir():
        raise SnapshotResolutionError(
            f"option-chain root is missing: path={chain_root}"
        )
    repository_root_resolved = repository_root.resolve()
    chain_root_resolved = chain_root.resolve()
    try:
        chain_root_resolved.relative_to(repository_root_resolved)
    except ValueError as error:
        raise SnapshotResolutionError(
            "option-chain root escapes the repository: "
            f"repository_root={repository_root}, chain_root={chain_root}"
        ) from error
    if not raw_hashes:
        raise SnapshotResolutionError(
            "options manifest advertises zero chain files"
        )

    advertised_date_set = set(advertised_dates)
    entry_dates: set[date] = set()
    expected_paths: set[str] = set()
    entries: list[_ValidatedChainFile] = []
    for raw_relative, raw_expected_hash in sorted(
        raw_hashes.items(), key=lambda item: str(item[0])
    ):
        relative = str(raw_relative).strip().replace("\\", "/")
        expected_hash = str(raw_expected_hash).strip().lower()
        if not relative or len(expected_hash) != 64 or any(
            character not in "0123456789abcdef" for character in expected_hash
        ):
            raise SnapshotResolutionError(
                "options manifest contains an invalid chain path or SHA-256: "
                f"relative_path={relative!r}, expected_hash={expected_hash!r}"
            )
        path = (repository_root_resolved / Path(relative)).resolve()
        try:
            canonical_relative = path.relative_to(repository_root_resolved).as_posix()
            path.relative_to(chain_root_resolved)
        except ValueError as error:
            raise SnapshotResolutionError(
                f"manifest chain path escapes the governed root: relative_path={relative}"
            ) from error
        if path.parent.parent != chain_root_resolved:
            raise SnapshotResolutionError(
                "manifest chain path violates the date/symbol directory contract: "
                f"path={canonical_relative}"
            )
        if canonical_relative != relative:
            raise SnapshotResolutionError(
                "manifest chain path is not canonical: "
                f"advertised={relative!r}, canonical={canonical_relative!r}"
            )
        if canonical_relative in expected_paths:
            raise SnapshotResolutionError(
                f"options manifest repeats a canonical chain path: path={canonical_relative}"
            )
        if not path.name.endswith("_chain.csv"):
            raise SnapshotResolutionError(
                f"options manifest advertises a non-chain file: path={canonical_relative}"
            )
        try:
            snapshot_date = date.fromisoformat(path.parent.name)
        except ValueError as error:
            raise SnapshotResolutionError(
                "manifest chain path lacks an ISO snapshot directory: "
                f"path={canonical_relative}"
            ) from error
        if snapshot_date not in advertised_date_set:
            raise SnapshotResolutionError(
                "manifest chain path belongs to an unadvertised snapshot date: "
                f"path={canonical_relative}, snapshot_date={snapshot_date.isoformat()}"
            )
        symbol = path.name[: -len("_chain.csv")].strip().upper()
        if not symbol:
            raise SnapshotResolutionError(
                f"manifest chain path has no underlying symbol: path={canonical_relative}"
            )
        if not path.is_file():
            raise SnapshotResolutionError(
                f"manifest_chain_file_missing:{canonical_relative}"
            )
        try:
            actual_hash = _sha256(path)
        except OSError as error:
            raise SnapshotResolutionError(
                "manifest chain file cannot be hashed: "
                f"path={canonical_relative}, error={error}"
            ) from error
        if actual_hash != expected_hash:
            raise SnapshotResolutionError(
                "chain_hash_mismatch:"
                f"{canonical_relative}:expected={expected_hash}:actual={actual_hash}"
            )
        try:
            row_count = validate_option_chain_file(path, snapshot_date, symbol)
        except ValueError as error:
            raise SnapshotResolutionError(
                "chain_row_contract_invalid:"
                f"{canonical_relative}:error={error}"
            ) from error
        expected_paths.add(canonical_relative)
        entry_dates.add(snapshot_date)
        entries.append(
            {
                "relative_path": canonical_relative,
                "path": path,
                "snapshot_date": snapshot_date,
                "symbol": symbol,
                "sha256": actual_hash,
                "row_count": row_count,
            }
        )

    if entry_dates != advertised_date_set:
        missing_dates = sorted(
            value.isoformat() for value in advertised_date_set - entry_dates
        )
        raise SnapshotResolutionError(
            "options manifest advertises snapshot dates without chain files: "
            f"missing_dates={missing_dates}"
        )
    actual_paths: set[str] = set()
    for path in chain_root.rglob("*_chain.csv"):
        resolved_path = path.resolve()
        try:
            actual_paths.add(
                resolved_path.relative_to(repository_root_resolved).as_posix()
            )
        except ValueError as error:
            raise SnapshotResolutionError(
                f"actual option-chain file escapes the repository: path={path}"
            ) from error
    unexpected_paths = sorted(actual_paths - expected_paths)
    if unexpected_paths:
        raise SnapshotResolutionError(
            "unexpected_chain_files_not_in_manifest:"
            f"paths={unexpected_paths}"
        )
    return tuple(entries)
