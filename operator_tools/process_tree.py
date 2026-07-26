"""Cross-platform captured subprocess execution with bounded tree termination."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict


class ProcessTreeTerminationError(RuntimeError):
    """Raised when a timed-out subprocess tree cannot be proven terminated."""


class CapturedProcessResult(TypedDict):
    return_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    timeout_seconds: int
    process_tree_terminated: bool


def _runtime_platform_name() -> str:
    return os.name


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if _runtime_platform_name() == "nt":
        system_root = os.environ.get("SystemRoot", "")
        if not system_root:
            raise ProcessTreeTerminationError(
                "SystemRoot is required to terminate a timed-out Windows process tree"
            )
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        try:
            completed = subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProcessTreeTerminationError(
                "could not invoke Windows process-tree termination: "
                f"pid={process.pid}, taskkill={taskkill}, error={error}"
            ) from error
        if completed.returncode != 0:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired as error:
                raise ProcessTreeTerminationError(
                    "failed to terminate timed-out Windows process tree: "
                    f"pid={process.pid}, return_code={completed.returncode}, "
                    f"stderr={completed.stderr[-2_000:]}"
                ) from error
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as error:
            raise ProcessTreeTerminationError(
                "could not terminate POSIX process group: "
                f"pid={process.pid}, error={error}"
            ) from error
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired as error:
        raise ProcessTreeTerminationError(
            f"timed-out process tree did not exit after termination: pid={process.pid}"
        ) from error


def run_captured_process_tree(
    command: list[str],
    cwd: Path,
    environment: Mapping[str, str] | None,
    timeout_seconds: int,
) -> CapturedProcessResult:
    if timeout_seconds <= 0:
        raise ValueError(
            "process-tree timeout must be positive: "
            f"timeout_seconds={timeout_seconds}, command={command}"
        )
    platform_name = _runtime_platform_name()
    creation_flags = (
        int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if platform_name == "nt"
        else 0
    )
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=platform_name != "nt",
        creationflags=creation_flags,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        partial_stdout = (
            error.stdout.decode("utf-8", errors="replace")
            if isinstance(error.stdout, bytes)
            else str(error.stdout or "")
        )
        partial_stderr = (
            error.stderr.decode("utf-8", errors="replace")
            if isinstance(error.stderr, bytes)
            else str(error.stderr or "")
        )
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        return {
            "return_code": None,
            "stdout": stdout or partial_stdout,
            "stderr": stderr or partial_stderr,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "process_tree_terminated": True,
        }
    return {
        "return_code": process.returncode,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "process_tree_terminated": False,
    }
