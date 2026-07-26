"""Fail closed when tracked files violate the public-source release boundary."""

from __future__ import annotations

import json
import subprocess
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import NoReturn


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SOURCE_MANIFEST_PATH = REPOSITORY_ROOT / "PUBLIC_SOURCE_MANIFEST.json"
TEST_ARTIFACT_SEED_MANIFEST_PATH = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "runtime_artifact_seed_v1_manifest.json"
)
FALSE_BOUNDARY_FIELDS = (
    "real_market_data_included",
    "broker_credentials_included",
    "broker_account_history_included",
    "private_runtime_history_included",
    "historical_private_session_reports_included",
    "operator_agent_configuration_included",
)
FORBIDDEN_EXACT_PATHS = frozenset(
    {
        ".mcp.json",
        "AGENTS.md",
        "reports/DOPEY_ROBINHOOD_READ_ONLY_RECONCILIATION_20260723.md",
        "reports/FULL_SHARDED_SUITE_RESULT.json",
    }
)
FORBIDDEN_PREFIXES = (
    ".codex/",
    ".cursor/",
    "dopey_data/history/",
    "dopey_data/market_lake/",
)
FORBIDDEN_ARTIFACT_NAME_PATTERNS = (
    "DOPEY_*_COPY_PROOF*",
    "DOPEY_*_COPY_MANIFEST*",
    "DOPEY_*_HANDOFF_MANIFEST*",
    "DOPEY_*_HANDOFF_PROOF*",
    "DOPEY_*_HANDOFF_20*",
    "DOPEY_*_SESSION_REPORT*",
    "DOPEY_*_SESSION_20*",
)
ALLOWED_REAL_DATA_PATTERNS = (
    "dopey_data/real/manifests/*.template.json",
    "dopey_data/real/templates/**",
)


class PublicSourceBoundaryError(RuntimeError):
    """Raised when the tracked public snapshot crosses a declared boundary."""


def _fail(message: str) -> NoReturn:
    raise PublicSourceBoundaryError(message)


def _load_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _fail(f"public source manifest must be a JSON object: path={path}")
    return value


def _tracked_paths(repository_root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return tuple(
        path
        for path in result.stdout.decode("utf-8").split("\0")
        if path
    )


def _is_allowed_real_data_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in ALLOWED_REAL_DATA_PATTERNS)


def _validate_manifest_flags(manifest: dict[str, object]) -> None:
    mismatches = {
        field: manifest.get(field)
        for field in FALSE_BOUNDARY_FIELDS
        if manifest.get(field) is not False
    }
    if mismatches:
        _fail(f"public source manifest boundary flags must be false: mismatches={mismatches}")


def _validate_test_artifact_seed_boundary(path: Path) -> None:
    manifest = _load_manifest(path)
    expected = {
        "derived_historical_public_market_test_fixture": True,
        "raw_provider_market_data_included": False,
        "broker_account_or_order_history_included": False,
        "operational_runtime_state": False,
        "paper_only": True,
        "live_blocked": True,
    }
    mismatches = {
        field: {"expected": expected_value, "actual": manifest.get(field)}
        for field, expected_value in expected.items()
        if manifest.get(field) is not expected_value
    }
    if mismatches:
        _fail(f"test artifact seed boundary metadata is invalid: mismatches={mismatches}")


def _validate_tracked_paths(
    tracked_paths: tuple[str, ...],
    allowed_top_level_reports: frozenset[str],
) -> None:
    violations: list[str] = []
    for path in tracked_paths:
        file_name = PurePosixPath(path).name
        if path in FORBIDDEN_EXACT_PATHS:
            violations.append(path)
            continue
        if any(fnmatch(file_name, pattern) for pattern in FORBIDDEN_ARTIFACT_NAME_PATTERNS):
            violations.append(path)
            continue
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            violations.append(path)
            continue
        if path.startswith("dopey_data/real/") and not _is_allowed_real_data_path(path):
            violations.append(path)
            continue
        if path.startswith("reports/") and path not in allowed_top_level_reports:
            violations.append(path)
    if violations:
        _fail(
            "tracked files violate the public source boundary: "
            f"violations={sorted(violations)}"
        )


def verify_public_source_boundary(repository_root: Path) -> dict[str, object]:
    manifest_path = repository_root / PUBLIC_SOURCE_MANIFEST_PATH.name
    manifest = _load_manifest(manifest_path)
    _validate_manifest_flags(manifest)
    _validate_test_artifact_seed_boundary(
        repository_root / TEST_ARTIFACT_SEED_MANIFEST_PATH.relative_to(REPOSITORY_ROOT)
    )

    raw_allowed_reports = manifest.get("allowed_top_level_reports")
    if not isinstance(raw_allowed_reports, list) or not all(
        isinstance(path, str) for path in raw_allowed_reports
    ):
        _fail("allowed_top_level_reports must be a list of strings")

    tracked_paths = _tracked_paths(repository_root)
    _validate_tracked_paths(tracked_paths, frozenset(raw_allowed_reports))

    source_inventory = manifest.get("source_inventory")
    if not isinstance(source_inventory, dict):
        _fail("source_inventory must be a JSON object")
    declared_file_count = source_inventory.get("public_file_count")
    if declared_file_count != len(tracked_paths):
        _fail(
            "public file count does not match tracked snapshot: "
            f"declared={declared_file_count}, actual={len(tracked_paths)}"
        )

    return {
        "status": "public_source_boundary_verified",
        "tracked_file_count": len(tracked_paths),
        "allowed_top_level_report_count": len(raw_allowed_reports),
    }


def main() -> None:
    result = verify_public_source_boundary(REPOSITORY_ROOT)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
