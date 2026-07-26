"""Safely reclaim stale pytest isolation trees left by killed Windows runs.

The repository's per-session lake copy is a load-bearing isolation control.
This tool preserves that control and removes only direct ``pytest-N`` children
of the current user's pytest temp root when all of these are true:

* no active process command line contains ``pytest``;
* the directory is older than the policy floor;
* it is not among the newest retained sessions;
* it is neither a symlink nor a Windows reparse point; and
* its resolved parent is exactly the resolved pytest temp root.

Dry-run is the default CLI posture. Nightly automation calls the same audited
function with execution enabled before it launches new pytest workers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402

REPORT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "dopey"
    / "ops"
    / "stale_pytest_cleanup_latest.json"
)
PYTEST_SESSION_PATTERN = re.compile(r"^pytest-\d+$")


@dataclass(frozen=True)
class CleanupPolicy:
    keep_recent_count: int
    minimum_age_hours: float


@dataclass(frozen=True)
class CleanupCandidate:
    path: str
    last_modified_utc: str
    age_hours: float
    estimated_bytes: int


class ActivePytestProcessDetectedError(RuntimeError):
    """Raised when pytest appears after cleanup planning but before deletion."""


def default_cleanup_policy() -> CleanupPolicy:
    return CleanupPolicy(
        keep_recent_count=3,
        minimum_age_hours=12.0,
    )


def default_pytest_temp_root() -> Path:
    username = os.environ.get("USERNAME")
    if not username:
        raise RuntimeError("USERNAME is required to resolve the pytest temp root")
    return Path(tempfile.gettempdir()) / f"pytest-of-{username}"


def active_process_command_lines() -> tuple[str, ...]:
    """Read Windows command lines so cleanup never races an active test run."""

    if os.name != "nt":
        raise RuntimeError(
            "stale pytest cleanup currently supports Windows process identity only"
        )
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match 'python|pytest' } | "
        "Select-Object -ExpandProperty CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "failed to inspect active Python processes before pytest cleanup: "
            f"returncode={completed.returncode}, stderr={completed.stderr[-2000:]}"
        )
    payload = completed.stdout.strip()
    if not payload:
        return ()
    parsed = json.loads(payload)
    if isinstance(parsed, str):
        return (parsed,)
    if not isinstance(parsed, list) or not all(
        isinstance(value, str) for value in parsed
    ):
        raise TypeError(
            "Windows process command-line query returned an unexpected payload: "
            f"actual={type(parsed).__name__}"
        )
    return tuple(parsed)


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _directory_size(path: Path) -> int:
    total = 0
    for root, directories, files in os.walk(path, followlinks=False):
        root_path = Path(root)
        directories[:] = [
            name
            for name in directories
            if not (root_path / name).is_symlink()
            and not _is_reparse_point(root_path / name)
        ]
        for filename in files:
            file_path = root_path / filename
            if file_path.is_symlink() or _is_reparse_point(file_path):
                continue
            total += file_path.stat().st_size
    return total


def _clear_readonly_and_retry(
    function: Callable[[str], object],
    path: str,
    _error: tuple[type[BaseException], BaseException, object],
) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _active_pytest_commands(
    process_command_lines: Sequence[str],
) -> tuple[str, ...]:
    return tuple(
        command
        for command in process_command_lines
        if "pytest" in command.lower()
        and "operator_cleanup_stale_pytest_temp.py" not in command.lower()
    )


def _eligible_directories(base_path: Path) -> tuple[Path, ...]:
    if not base_path.exists():
        return ()
    if not base_path.is_dir() or base_path.is_symlink() or _is_reparse_point(base_path):
        raise ValueError(
            "pytest temp root must be a real directory: "
            f"path={base_path}"
        )
    resolved_base = base_path.resolve(strict=True)
    eligible: list[Path] = []
    for child in base_path.iterdir():
        if not PYTEST_SESSION_PATTERN.fullmatch(child.name):
            continue
        if not child.is_dir() or child.is_symlink() or _is_reparse_point(child):
            continue
        resolved_child = child.resolve(strict=True)
        if resolved_child.parent != resolved_base:
            raise ValueError(
                "pytest cleanup candidate escaped the intended root: "
                f"base={resolved_base}, candidate={resolved_child}"
            )
        eligible.append(resolved_child)
    return tuple(eligible)


def build_cleanup_candidates(
    base_path: Path,
    policy: CleanupPolicy,
    observed_at: datetime,
) -> tuple[CleanupCandidate, ...]:
    """Build a size-accounted plan while preserving the newest sessions."""

    if observed_at.tzinfo is None:
        raise ValueError("cleanup observed_at must be timezone-aware")
    if policy.keep_recent_count < 0:
        raise ValueError(
            "keep_recent_count must be non-negative: "
            f"value={policy.keep_recent_count}"
        )
    if policy.minimum_age_hours < 0.0:
        raise ValueError(
            "minimum_age_hours must be non-negative: "
            f"value={policy.minimum_age_hours}"
        )
    directories = sorted(
        _eligible_directories(base_path),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    protected = set(directories[: policy.keep_recent_count])
    candidates: list[CleanupCandidate] = []
    observed_utc = observed_at.astimezone(timezone.utc)
    for path in directories:
        if path in protected:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        age_hours = (observed_utc - modified).total_seconds() / 3600.0
        if age_hours < policy.minimum_age_hours:
            continue
        candidates.append(
            CleanupCandidate(
                path=str(path),
                last_modified_utc=modified.isoformat(),
                age_hours=round(age_hours, 3),
                estimated_bytes=_directory_size(path),
            )
        )
    return tuple(candidates)


def cleanup_stale_pytest_temp(
    base_path: Path,
    policy: CleanupPolicy,
    execute: bool,
    observed_at: datetime,
    process_command_lines: Sequence[str],
    process_command_line_reader: Callable[[], Sequence[str]],
) -> dict[str, object]:
    """Plan or execute bounded cleanup and return durable audit evidence."""

    active_pytest = _active_pytest_commands(process_command_lines)
    if active_pytest:
        return {
            "artifact_type": "stale_pytest_temp_cleanup",
            "cleanup_status": "blocked_active_pytest_process",
            "execute_requested": execute,
            "base_path": str(base_path),
            "base_path_status": (
                "present" if base_path.exists() else "missing_not_evaluated"
            ),
            "active_pytest_process_count": len(active_pytest),
            "candidate_count": 0,
            "removed_count": 0,
            "estimated_reclaimable_bytes": 0,
            "estimated_removed_bytes": 0,
            "removed_paths": [],
        }
    candidates = build_cleanup_candidates(base_path, policy, observed_at)
    removed_paths: list[str] = []
    estimated_removed_bytes = 0
    if execute and candidates:
        resolved_base = base_path.resolve(strict=True)
        for candidate in candidates:
            target = Path(candidate.path).resolve(strict=True)
            if target.parent != resolved_base:
                raise ValueError(
                    "cleanup target failed final containment check: "
                    f"base={resolved_base}, target={target}"
                )
            active_during_execution = _active_pytest_commands(
                process_command_line_reader()
            )
            if active_during_execution:
                raise ActivePytestProcessDetectedError(
                    "pytest appeared after cleanup planning; recursive deletion "
                    "was aborted before touching the candidate: "
                    f"target={target}, "
                    f"active_pytest_process_count={len(active_during_execution)}"
                )
            shutil.rmtree(target, onerror=_clear_readonly_and_retry)
            if target.exists():
                raise OSError(f"pytest cleanup target still exists: path={target}")
            removed_paths.append(str(target))
            estimated_removed_bytes += candidate.estimated_bytes
    return {
        "artifact_type": "stale_pytest_temp_cleanup",
        "cleanup_status": "cleanup_complete" if execute else "dry_run_complete",
        "execute_requested": execute,
        "base_path": str(base_path),
        "base_path_status": "present" if base_path.exists() else "missing_noop",
        "policy": asdict(policy),
        "active_pytest_process_count": 0,
        "candidate_count": len(candidates),
        "removed_count": len(removed_paths),
        "estimated_reclaimable_bytes": sum(
            candidate.estimated_bytes for candidate in candidates
        ),
        "estimated_removed_bytes": estimated_removed_bytes,
        "actual_free_space_delta_bytes": None,
        "byte_measurement_note": (
            "estimated_removed_bytes sums pre-delete file sizes; actual filesystem "
            "free-space change is not measured or claimed"
        ),
        "candidates": [asdict(candidate) for candidate in candidates],
        "removed_paths": removed_paths,
    }


def run_cleanup(execute: bool) -> dict[str, object]:
    report = cleanup_stale_pytest_temp(
        default_pytest_temp_root(),
        default_cleanup_policy(),
        execute,
        datetime.now(timezone.utc),
        active_process_command_lines(),
        active_process_command_lines,
    )
    write_json_atomic(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit and safely remove stale pytest isolation trees"
    )
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    report = run_cleanup(arguments.execute)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["cleanup_status"] != "blocked_active_pytest_process" else 2


if __name__ == "__main__":
    raise SystemExit(main())
