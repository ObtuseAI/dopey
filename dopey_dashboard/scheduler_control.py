"""Fail-closed Windows scheduler control for the paper-research desktop app."""

from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal, Protocol, TypedDict, cast


ACCELERATION_TASK_NAME: Final[str] = "DOPEY_AccelerationCycle"
DAILY_RITUAL_TASK_NAME: Final[str] = "DOPEY_DailyRitual"
CONTROL_CONFIRMATION: Final[str] = "paper_research_only"
ACCELERATION_COMMAND_RELATIVE_PATH: Final[Path] = Path("operator_tools") / "acceleration_cycle.cmd"
DAILY_RITUAL_COMMAND_RELATIVE_PATH: Final[Path] = Path("operator_tools") / "daily_ritual.cmd"
HIDDEN_LAUNCHER_RELATIVE_PATH: Final[Path] = (
    Path("operator_tools") / "run_scheduled_hidden.vbs"
)
HIDDEN_LAUNCHER_SHA256: Final[str] = (
    "1c07e2639690b34eb3e6954d09c15e1947abe90d07e41f205f76637780ed8348"
)
ACCELERATION_COMMAND_SHA256: Final[str] = (
    "bfea9f6754fd0fdd6f0d9cc1a8c498d3d47285f5df994c7b8b69f464e65a36a5"
)
DAILY_RITUAL_COMMAND_SHA256: Final[str] = (
    "53576811a9a7f934cb4254117100380c8a3f07c3a5eb4a80f94979de4f476dbd"
)
EXPECTED_TASK_PATH: Final[str] = "\\"
EXPECTED_LOGON_TYPE: Final[str] = "Interactive"
EXPECTED_RUN_LEVEL: Final[str] = "Limited"
ACCELERATION_LOCK_RELATIVE_PATH: Final[Path] = (
    Path("artifacts") / "dopey" / "acceleration" / "acceleration_cycle.lock"
)
CONTROL_AUDIT_RELATIVE_PATH: Final[Path] = (
    Path("artifacts") / "dopey" / "desktop" / "research_core_control_audit.jsonl"
)
CONSTITUTION_STATE_RELATIVE_PATH: Final[Path] = (
    Path("artifacts") / "dopey" / "vnext" / "operational" / "constitution_state.json"
)

CoreState = Literal["ON", "RUNNING", "DRAINING", "OFF", "FAULT"]


class SchedulerControlError(RuntimeError):
    """Base error for research scheduler inspection and control."""


class SchedulerCommandError(SchedulerControlError):
    """Raised when a Windows scheduler or process query fails."""


class SchedulerVerificationError(SchedulerControlError):
    """Raised when scheduler identity or a control postcondition is invalid."""


class ResearchCoreConfirmationError(SchedulerControlError):
    """Raised when the exact paper-research confirmation is absent."""


class TaskAction(TypedDict):
    execute: str
    arguments: str
    working_directory: str


class TaskTrigger(TypedDict):
    cim_class: str
    enabled: bool
    start_boundary: str
    repetition_interval: str


class ScheduledTaskSnapshot(TypedDict):
    task_name: str
    present: bool
    enabled: bool
    state: str
    task_path: str
    principal_user_id: str
    logon_type: str
    run_level: str
    actions: list[TaskAction]
    triggers: list[TaskTrigger]
    expected_execute: str
    expected_arguments: str
    command_sha256: str
    expected_command_sha256: str
    launcher_sha256: str
    expected_launcher_sha256: str
    action_verified: bool
    identity_verified: bool
    read_only: bool
    verification_issues: list[str]


class ProcessSnapshot(TypedDict):
    present: bool
    pid: int | None
    name: str
    executable_path: str
    command_line: str


class AccelerationLockSnapshot(TypedDict):
    path: str
    present: bool
    pid: int | None
    process_present: bool
    process_name: str
    executable_path: str
    command_line: str
    expected_command_line: str
    verified: bool
    verification_issues: list[str]


class SchedulerControlState(TypedDict):
    state: CoreState
    enabled: bool
    active_cycle_verified: bool
    active_automation_present: bool
    controlled_task_names: list[str]
    core_task: ScheduledTaskSnapshot
    acceleration_lock: AccelerationLockSnapshot
    auxiliary_tasks: list[ScheduledTaskSnapshot]
    issues: list[str]
    control_scope: str
    paper_only: bool
    live_blocked: bool


class SchedulerRunner(Protocol):
    """External-system interface used by production and deterministic tests."""

    def query_tasks(self) -> str:
        """Return the two allowlisted task snapshots as JSON."""

    def query_process(self, pid: int) -> str:
        """Return one process snapshot as JSON."""

    def enable_task(self, task_name: str) -> None:
        """Enable future starts for one exact allowlisted research task."""

    def disable_task(self, task_name: str) -> None:
        """Disable future starts for one exact allowlisted research task."""


def _powershell_task_query() -> str:
    return """
$ErrorActionPreference = 'Stop'
$rows = @()
foreach ($taskName in @('DOPEY_AccelerationCycle', 'DOPEY_DailyRitual')) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        $rows += [pscustomobject]@{
            TaskName = $taskName
            Present = $false
            Enabled = $false
            State = 'Missing'
            TaskPath = ''
            PrincipalUserId = ''
            LogonType = ''
            RunLevel = ''
            Actions = @()
            Triggers = @()
        }
        continue
    }
    $actions = @($task.Actions | ForEach-Object {
        [pscustomobject]@{
            Execute = [string]$_.Execute
            Arguments = [string]$_.Arguments
            WorkingDirectory = [string]$_.WorkingDirectory
        }
    })
    $triggers = @($task.Triggers | ForEach-Object {
        [pscustomobject]@{
            CimClass = [string]$_.CimClass.CimClassName
            Enabled = [bool]$_.Enabled
            StartBoundary = [string]$_.StartBoundary
            RepetitionInterval = [string]$_.Repetition.Interval
        }
    })
    $rows += [pscustomobject]@{
        TaskName = [string]$task.TaskName
        Present = $true
        Enabled = [bool]$task.Settings.Enabled
        State = [string]$task.State
        TaskPath = [string]$task.TaskPath
        PrincipalUserId = [string]$task.Principal.UserId
        LogonType = [string]$task.Principal.LogonType
        RunLevel = [string]$task.Principal.RunLevel
        Actions = $actions
        Triggers = $triggers
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 6 -Compress
""".strip()


def _powershell_process_query(pid: int) -> str:
    if pid <= 0:
        raise ValueError(f"process id must be positive: pid={pid}")
    return f"""
$ErrorActionPreference = 'Stop'
$process = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" -ErrorAction SilentlyContinue
if ($null -eq $process) {{
    [pscustomobject]@{{
        Present = $false
        Pid = {pid}
        Name = ''
        ExecutablePath = ''
        CommandLine = ''
    }} | ConvertTo-Json -Compress
}} else {{
    [pscustomobject]@{{
        Present = $true
        Pid = [int]$process.ProcessId
        Name = [string]$process.Name
        ExecutablePath = [string]$process.ExecutablePath
        CommandLine = [string]$process.CommandLine
    }} | ConvertTo-Json -Compress
}}
""".strip()


class WindowsSchedulerRunner:
    """PowerShell connector restricted to the two DOPEY research tasks."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        system_root = os.environ.get("SystemRoot")
        if not system_root:
            raise SchedulerCommandError("SystemRoot is required to resolve trusted Windows PowerShell")
        self._powershell_path = (
            Path(system_root)
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        ).resolve(strict=False)
        if not self._powershell_path.is_file():
            raise SchedulerCommandError(
                f"trusted Windows PowerShell executable is missing: path={self._powershell_path}"
            )

    def _run(self, script: str) -> str:
        try:
            completed = subprocess.run(
                (
                    str(self._powershell_path),
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ),
                cwd=self._repository_root,
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                encoding="utf-8",
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SchedulerCommandError(
                f"Windows scheduler command could not complete: repo={self._repository_root}, error={error}"
            ) from error
        if completed.returncode != 0:
            raise SchedulerCommandError(
                "Windows scheduler command failed: "
                f"repo={self._repository_root}, return_code={completed.returncode}, "
                f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
            )
        return completed.stdout.strip()

    def query_tasks(self) -> str:
        return self._run(_powershell_task_query())

    def query_process(self, pid: int) -> str:
        return self._run(_powershell_process_query(pid))

    def enable_task(self, task_name: str) -> None:
        _require_allowlisted_task_name(task_name)
        self._run(
            "$ErrorActionPreference='Stop'; "
            f"Enable-ScheduledTask -TaskPath '\\' -TaskName '{task_name}' -ErrorAction Stop | Out-Null"
        )

    def disable_task(self, task_name: str) -> None:
        _require_allowlisted_task_name(task_name)
        self._run(
            "$ErrorActionPreference='Stop'; "
            f"Disable-ScheduledTask -TaskPath '\\' -TaskName '{task_name}' -ErrorAction Stop | Out-Null"
        )


def _json_object(payload: str, context: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise SchedulerVerificationError(
            f"scheduler returned invalid JSON: context={context}, error={error}, payload={payload!r}"
        ) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SchedulerVerificationError(
            f"scheduler JSON must be an object: context={context}, actual={type(value).__name__}"
        )
    return cast(dict[str, object], value)


def _json_object_array(payload: str, context: str) -> list[dict[str, object]]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise SchedulerVerificationError(
            f"scheduler returned invalid JSON: context={context}, error={error}, payload={payload!r}"
        ) from error
    if not isinstance(value, list):
        raise SchedulerVerificationError(
            f"scheduler JSON must be an array: context={context}, actual={type(value).__name__}"
        )
    objects: list[dict[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            raise SchedulerVerificationError(
                f"scheduler array item must be an object: context={context}, index={index}"
            )
        objects.append(cast(dict[str, object], item))
    return objects


def _required_string(record: dict[str, object], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise SchedulerVerificationError(
            f"scheduler field must be a string: context={context}, key={key}, actual={type(value).__name__}"
        )
    return value


def _required_bool(record: dict[str, object], key: str, context: str) -> bool:
    value = record.get(key)
    if not isinstance(value, bool):
        raise SchedulerVerificationError(
            f"scheduler field must be a boolean: context={context}, key={key}, actual={type(value).__name__}"
        )
    return value


def _require_allowlisted_task_name(task_name: str) -> None:
    if task_name not in (ACCELERATION_TASK_NAME, DAILY_RITUAL_TASK_NAME):
        raise SchedulerVerificationError(
            f"scheduler mutation is restricted to allowlisted research tasks: task={task_name}"
        )


def _expected_principal_user() -> str:
    username = os.environ.get("USERNAME")
    if not username or not username.strip():
        raise SchedulerVerificationError(
            "USERNAME is required to verify the scheduled-task principal"
        )
    return username.strip()


def _normalized_path(path: Path) -> str:
    return str(path.resolve(strict=False)).replace("/", "\\").rstrip("\\").casefold()


def _trusted_wscript_path() -> Path:
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise SchedulerVerificationError(
            "SystemRoot is required to resolve trusted Windows Script Host"
        )
    path = (Path(system_root) / "System32" / "wscript.exe").resolve(strict=False)
    if not path.is_file():
        raise SchedulerVerificationError(
            f"trusted Windows Script Host executable is missing: path={path}"
        )
    return path


def _hidden_action_arguments(launcher_path: Path, command_key: str) -> str:
    return f'//B //NoLogo "{launcher_path}" {command_key}'


def _parse_actions(value: object, task_name: str) -> list[TaskAction]:
    if not isinstance(value, list):
        raise SchedulerVerificationError(
            f"scheduled task Actions must be an array: task={task_name}, actual={type(value).__name__}"
        )
    actions: list[TaskAction] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            raise SchedulerVerificationError(
                f"scheduled task action must be an object: task={task_name}, index={index}"
            )
        record = cast(dict[str, object], item)
        actions.append(
            {
                "execute": _required_string(record, "Execute", f"{task_name}.Actions[{index}]"),
                "arguments": _required_string(record, "Arguments", f"{task_name}.Actions[{index}]"),
                "working_directory": _required_string(
                    record,
                    "WorkingDirectory",
                    f"{task_name}.Actions[{index}]",
                ),
            }
        )
    return actions


def _parse_triggers(value: object, task_name: str) -> list[TaskTrigger]:
    if not isinstance(value, list):
        raise SchedulerVerificationError(
            f"scheduled task Triggers must be an array: task={task_name}, actual={type(value).__name__}"
        )
    triggers: list[TaskTrigger] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            raise SchedulerVerificationError(
                f"scheduled task trigger must be an object: task={task_name}, index={index}"
            )
        record = cast(dict[str, object], item)
        triggers.append(
            {
                "cim_class": _required_string(record, "CimClass", f"{task_name}.Triggers[{index}]"),
                "enabled": _required_bool(record, "Enabled", f"{task_name}.Triggers[{index}]"),
                "start_boundary": _required_string(
                    record,
                    "StartBoundary",
                    f"{task_name}.Triggers[{index}]",
                ),
                "repetition_interval": _required_string(
                    record,
                    "RepetitionInterval",
                    f"{task_name}.Triggers[{index}]",
                ),
            }
        )
    return triggers


def _file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise SchedulerVerificationError(
            f"scheduled-task command could not be hashed: path={path}, error={error}"
        ) from error


def _normalized_principal(value: str) -> str:
    return value.replace("/", "\\").rsplit("\\", maxsplit=1)[-1].casefold()


def _trigger_issues(task_name: str, triggers: Sequence[TaskTrigger]) -> list[str]:
    if task_name == DAILY_RITUAL_TASK_NAME:
        if len(triggers) != 1:
            return [
                "daily ritual must have exactly one weekly trigger: "
                f"task={task_name}, actual_count={len(triggers)}"
            ]
        weekly_trigger = triggers[0]
        issues: list[str] = []
        if weekly_trigger["cim_class"] != "MSFT_TaskWeeklyTrigger":
            issues.append(
                "scheduled task trigger class mismatch: "
                f"task={task_name}, expected=MSFT_TaskWeeklyTrigger, "
                f"actual={weekly_trigger['cim_class']}"
            )
        if not weekly_trigger["enabled"]:
            issues.append(f"scheduled task trigger must be enabled: task={task_name}")
        if not weekly_trigger["start_boundary"].strip():
            issues.append(f"scheduled task start boundary is missing: task={task_name}")
        return issues

    class_counts: dict[str, int] = {}
    for trigger in triggers:
        trigger_class = trigger["cim_class"]
        class_counts[trigger_class] = class_counts.get(trigger_class, 0) + 1
    allowed_classes = {"MSFT_TaskTimeTrigger", "MSFT_TaskLogonTrigger"}
    actual_classes = set(class_counts)
    issues = []
    if not 1 <= len(triggers) <= 2:
        issues.append(
            "acceleration task must have one time trigger and at most one logon trigger: "
            f"task={task_name}, actual_count={len(triggers)}"
        )
    unexpected_classes = sorted(actual_classes - allowed_classes)
    if unexpected_classes:
        issues.append(
            "acceleration task contains unapproved trigger classes: "
            f"task={task_name}, classes={unexpected_classes}"
        )
    if class_counts.get("MSFT_TaskTimeTrigger", 0) != 1:
        issues.append(
            "acceleration task must have exactly one time trigger: "
            f"task={task_name}, actual_count={class_counts.get('MSFT_TaskTimeTrigger', 0)}"
        )
    if class_counts.get("MSFT_TaskLogonTrigger", 0) > 1:
        issues.append(
            "acceleration task may have at most one logon trigger: "
            f"task={task_name}, actual_count={class_counts['MSFT_TaskLogonTrigger']}"
        )
    for trigger in triggers:
        if not trigger["enabled"]:
            issues.append(
                "scheduled task trigger must be enabled: "
                f"task={task_name}, class={trigger['cim_class']}"
            )
        if trigger["cim_class"] == "MSFT_TaskTimeTrigger":
            if trigger["repetition_interval"] != "PT15M":
                issues.append(
                    "acceleration task repetition mismatch: "
                    f"expected=PT15M, actual={trigger['repetition_interval']!r}"
                )
            if not trigger["start_boundary"].strip():
                issues.append(f"scheduled task start boundary is missing: task={task_name}")
    return issues


def _verify_task_identity(
    task_name: str,
    present: bool,
    task_path: str,
    principal_user_id: str,
    logon_type: str,
    run_level: str,
    actions: Sequence[TaskAction],
    triggers: Sequence[TaskTrigger],
    expected_execute: Path,
    expected_arguments: str,
    command_path: Path,
    expected_command_sha256: str,
    launcher_path: Path,
    expected_launcher_sha256: str,
) -> tuple[bool, str, str, list[str]]:
    issues: list[str] = []
    if not present:
        return False, "", "", [f"scheduled task is missing: task={task_name}"]
    if not command_path.is_file():
        issues.append(f"expected task command is missing: task={task_name}, path={command_path}")
        command_sha256 = ""
    else:
        command_sha256 = _file_sha256(command_path)
        if command_sha256 != expected_command_sha256:
            issues.append(
                "scheduled task command hash mismatch: "
                f"task={task_name}, expected={expected_command_sha256}, actual={command_sha256}"
            )
    if not launcher_path.is_file():
        issues.append(
            f"expected hidden launcher is missing: task={task_name}, path={launcher_path}"
        )
        launcher_sha256 = ""
    else:
        launcher_sha256 = _file_sha256(launcher_path)
        if launcher_sha256 != expected_launcher_sha256:
            issues.append(
                "scheduled task hidden-launcher hash mismatch: "
                f"task={task_name}, expected={expected_launcher_sha256}, actual={launcher_sha256}"
            )
    if not expected_execute.is_file():
        issues.append(
            f"trusted scheduled-task host is missing: task={task_name}, path={expected_execute}"
        )
    if task_path != EXPECTED_TASK_PATH:
        issues.append(
            f"scheduled task path mismatch: task={task_name}, expected={EXPECTED_TASK_PATH!r}, actual={task_path!r}"
        )
    if _normalized_principal(principal_user_id) != _normalized_principal(
        _expected_principal_user()
    ):
        issues.append(
            "scheduled task principal mismatch: "
            f"task={task_name}, expected={_expected_principal_user()!r}, actual={principal_user_id!r}"
        )
    if logon_type != EXPECTED_LOGON_TYPE:
        issues.append(
            f"scheduled task logon type mismatch: task={task_name}, expected={EXPECTED_LOGON_TYPE}, actual={logon_type}"
        )
    if run_level != EXPECTED_RUN_LEVEL:
        issues.append(
            f"scheduled task run level mismatch: task={task_name}, expected={EXPECTED_RUN_LEVEL}, actual={run_level}"
        )
    if len(actions) != 1:
        issues.append(
            f"scheduled task must have exactly one action: task={task_name}, actual_count={len(actions)}"
        )
    else:
        action = actions[0]
        if _normalized_path(Path(action["execute"])) != _normalized_path(expected_execute):
            issues.append(
                "scheduled task execute path mismatch: "
                f"task={task_name}, expected={expected_execute}, actual={action['execute']}"
            )
        if action["arguments"].strip().casefold() != expected_arguments.casefold():
            issues.append(
                "scheduled task hidden arguments mismatch: "
                f"task={task_name}, expected={expected_arguments!r}, actual={action['arguments']!r}"
            )
        if action["working_directory"].strip():
            issues.append(
                "scheduled task working directory must be empty: "
                f"task={task_name}, actual={action['working_directory']!r}"
            )
    issues.extend(_trigger_issues(task_name, triggers))
    return not issues, command_sha256, launcher_sha256, issues


def parse_scheduled_tasks(payload: str, repository_root: Path) -> list[ScheduledTaskSnapshot]:
    """Parse and verify only the two allowlisted Windows task definitions."""

    expected_names = (ACCELERATION_TASK_NAME, DAILY_RITUAL_TASK_NAME)
    records = _json_object_array(payload, "scheduled_tasks")
    by_name: dict[str, dict[str, object]] = {}
    for record in records:
        task_name = _required_string(record, "TaskName", "scheduled_tasks")
        if task_name not in expected_names:
            raise SchedulerVerificationError(
                f"unexpected scheduled task returned by allowlisted query: task={task_name}"
            )
        if task_name in by_name:
            raise SchedulerVerificationError(f"duplicate scheduled task returned: task={task_name}")
        by_name[task_name] = record

    snapshots: list[ScheduledTaskSnapshot] = []
    wscript_path = _trusted_wscript_path()
    launcher_path = (repository_root / HIDDEN_LAUNCHER_RELATIVE_PATH).resolve(strict=False)
    for task_name, relative_path, expected_command_sha256, command_key in (
        (
            ACCELERATION_TASK_NAME,
            ACCELERATION_COMMAND_RELATIVE_PATH,
            ACCELERATION_COMMAND_SHA256,
            "acceleration_cycle",
        ),
        (
            DAILY_RITUAL_TASK_NAME,
            DAILY_RITUAL_COMMAND_RELATIVE_PATH,
            DAILY_RITUAL_COMMAND_SHA256,
            "daily_ritual",
        ),
    ):
        if task_name not in by_name:
            raise SchedulerVerificationError(
                f"allowlisted scheduled-task query omitted required record: task={task_name}"
            )
        record = by_name[task_name]
        present = _required_bool(record, "Present", task_name)
        enabled = _required_bool(record, "Enabled", task_name)
        state = _required_string(record, "State", task_name)
        task_path = _required_string(record, "TaskPath", task_name)
        principal_user_id = _required_string(record, "PrincipalUserId", task_name)
        logon_type = _required_string(record, "LogonType", task_name)
        run_level = _required_string(record, "RunLevel", task_name)
        actions = _parse_actions(record.get("Actions"), task_name)
        triggers = _parse_triggers(record.get("Triggers"), task_name)
        command_path = (repository_root / relative_path).resolve(strict=False)
        expected_arguments = _hidden_action_arguments(launcher_path, command_key)
        identity_verified, command_sha256, launcher_sha256, issues = _verify_task_identity(
            task_name,
            present,
            task_path,
            principal_user_id,
            logon_type,
            run_level,
            actions,
            triggers,
            wscript_path,
            expected_arguments,
            command_path,
            expected_command_sha256,
            launcher_path,
            HIDDEN_LAUNCHER_SHA256,
        )
        snapshots.append(
            {
                "task_name": task_name,
                "present": present,
                "enabled": enabled,
                "state": state,
                "task_path": task_path,
                "principal_user_id": principal_user_id,
                "logon_type": logon_type,
                "run_level": run_level,
                "actions": actions,
                "triggers": triggers,
                "expected_execute": str(wscript_path),
                "expected_arguments": expected_arguments,
                "command_sha256": command_sha256,
                "expected_command_sha256": expected_command_sha256,
                "launcher_sha256": launcher_sha256,
                "expected_launcher_sha256": HIDDEN_LAUNCHER_SHA256,
                "action_verified": identity_verified,
                "identity_verified": identity_verified,
                "read_only": False,
                "verification_issues": issues,
            }
        )
    return snapshots


def parse_process_snapshot(payload: str, expected_pid: int) -> ProcessSnapshot:
    """Parse one Win32 process query without inferring missing process data."""

    record = _json_object(payload, "acceleration_process")
    present = _required_bool(record, "Present", "acceleration_process")
    raw_pid = record.get("Pid")
    if not isinstance(raw_pid, int) or isinstance(raw_pid, bool):
        raise SchedulerVerificationError(
            f"process Pid must be an integer: actual={type(raw_pid).__name__}"
        )
    if raw_pid != expected_pid:
        raise SchedulerVerificationError(
            f"process query returned a different pid: expected={expected_pid}, actual={raw_pid}"
        )
    return {
        "present": present,
        "pid": raw_pid,
        "name": _required_string(record, "Name", "acceleration_process"),
        "executable_path": _required_string(
            record,
            "ExecutablePath",
            "acceleration_process",
        ),
        "command_line": _required_string(record, "CommandLine", "acceleration_process"),
    }


def _normalized_command_line(command_line: str) -> str:
    unquoted = command_line.replace('"', "").replace("'", "")
    normalized_space = re.sub(r"\s+", " ", unquoted.strip())
    return normalized_space.replace("/", "\\").casefold()


def _expected_acceleration_command(repository_root: Path) -> str:
    python_path = (repository_root / ".venv" / "Scripts" / "python.exe").resolve(strict=False)
    return (
        f"{python_path} -m dopey_acceleration.run_acceleration_cycle --mode execute"
    )


def inspect_acceleration_lock(
    repository_root: Path,
    runner: SchedulerRunner,
) -> AccelerationLockSnapshot:
    """Verify that the lock owner is the exact paper-research cycle command."""

    lock_path = (repository_root / ACCELERATION_LOCK_RELATIVE_PATH).resolve(strict=False)
    expected_command = _expected_acceleration_command(repository_root)
    base: AccelerationLockSnapshot = {
        "path": str(lock_path),
        "present": False,
        "pid": None,
        "process_present": False,
        "process_name": "",
        "executable_path": "",
        "command_line": "",
        "expected_command_line": expected_command,
        "verified": True,
        "verification_issues": [],
    }
    if not lock_path.exists():
        return base
    if not lock_path.is_file():
        return {
            **base,
            "present": True,
            "verified": False,
            "verification_issues": [f"acceleration lock is not a file: path={lock_path}"],
        }
    try:
        raw_pid = lock_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as error:
        return {
            **base,
            "present": True,
            "verified": False,
            "verification_issues": [
                f"acceleration lock could not be read: path={lock_path}, error={error}"
            ],
        }
    try:
        pid = int(raw_pid)
    except ValueError:
        return {
            **base,
            "present": True,
            "verified": False,
            "verification_issues": [
                f"acceleration lock PID is invalid: path={lock_path}, value={raw_pid!r}"
            ],
        }
    if pid <= 0:
        return {
            **base,
            "present": True,
            "pid": pid,
            "verified": False,
            "verification_issues": [f"acceleration lock PID must be positive: pid={pid}"],
        }
    process = parse_process_snapshot(runner.query_process(pid), pid)
    issues: list[str] = []
    if not process["present"]:
        issues.append(f"acceleration lock owner process is absent: pid={pid}")
    elif _normalized_command_line(process["command_line"]) != _normalized_command_line(
        expected_command
    ):
        issues.append(
            "acceleration lock command mismatch: "
            f"pid={pid}, expected={expected_command!r}, actual={process['command_line']!r}"
        )
    return {
        "path": str(lock_path),
        "present": True,
        "pid": pid,
        "process_present": process["present"],
        "process_name": process["name"],
        "executable_path": process["executable_path"],
        "command_line": process["command_line"],
        "expected_command_line": expected_command,
        "verified": not issues,
        "verification_issues": issues,
    }


def derive_core_state(
    core_task: ScheduledTaskSnapshot,
    auxiliary_tasks: Sequence[ScheduledTaskSnapshot],
    acceleration_lock: AccelerationLockSnapshot,
) -> tuple[CoreState, list[str]]:
    """Derive the five-state control model from independently verified facts."""

    controlled_tasks = [core_task, *auxiliary_tasks]
    issues = [
        *(issue for task in controlled_tasks for issue in task["verification_issues"]),
        *acceleration_lock["verification_issues"],
    ]
    if any(not task["present"] or not task["identity_verified"] for task in controlled_tasks):
        return "FAULT", issues
    enabled_states = {task["enabled"] for task in controlled_tasks}
    if len(enabled_states) != 1:
        issues.append(
            "aggregate paper-research schedules have inconsistent enabled states: "
            + ", ".join(
                f"{task['task_name']}={task['enabled']}" for task in controlled_tasks
            )
        )
        return "FAULT", issues
    task_running = core_task["state"].casefold() == "running"
    if acceleration_lock["present"]:
        if not acceleration_lock["verified"]:
            return "FAULT", issues
        if not task_running:
            issues.append(
                "verified acceleration lock exists while the scheduled task is not Running: "
                f"task_state={core_task['state']}"
            )
            return "FAULT", issues
    elif task_running:
        issues.append("scheduled task reports Running without an acceleration lock")
        return "FAULT", issues

    active_automation = acceleration_lock["present"] or any(
        task["state"].casefold() == "running" for task in auxiliary_tasks
    )
    enabled = core_task["enabled"]
    if active_automation:
        return ("RUNNING" if enabled else "DRAINING"), issues
    return ("ON" if enabled else "OFF"), issues


def inspect_research_core(
    repository_root: Path,
    runner: SchedulerRunner,
) -> SchedulerControlState:
    """Inspect task identity, task state, and the acceleration lock owner."""

    tasks = parse_scheduled_tasks(runner.query_tasks(), repository_root)
    core_task = next(task for task in tasks if task["task_name"] == ACCELERATION_TASK_NAME)
    auxiliary_tasks = [task for task in tasks if task["task_name"] != ACCELERATION_TASK_NAME]
    acceleration_lock = inspect_acceleration_lock(repository_root, runner)
    state, core_issues = derive_core_state(core_task, auxiliary_tasks, acceleration_lock)
    active_automation_present = acceleration_lock["present"] or any(
        task["state"].casefold() == "running" for task in auxiliary_tasks
    )
    return {
        "state": state,
        "enabled": all(task["enabled"] for task in tasks),
        "active_cycle_verified": (
            acceleration_lock["present"] and acceleration_lock["verified"]
        ),
        "active_automation_present": active_automation_present,
        "controlled_task_names": [task["task_name"] for task in tasks],
        "core_task": core_task,
        "acceleration_lock": acceleration_lock,
        "auxiliary_tasks": auxiliary_tasks,
        "issues": core_issues,
        "control_scope": "aggregate_paper_research_automation_schedules_only",
        "paper_only": True,
        "live_blocked": True,
    }


def _append_audit(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise SchedulerControlError(
            f"research-core audit append failed: path={path}, error={error}"
        ) from error


def _audit_record(
    transaction_id: str,
    generated_utc: str,
    enabled: bool,
    outcome: str,
    before: SchedulerControlState | None,
    after: SchedulerControlState | None,
    schedule_mutated: bool,
    rollback_performed: bool,
    rollback_verified: bool,
    error: str,
) -> dict[str, object]:
    before_tasks = {} if before is None else {
        task["task_name"]: task["enabled"]
        for task in [before["core_task"], *before["auxiliary_tasks"]]
    }
    after_tasks = {} if after is None else {
        task["task_name"]: task["enabled"]
        for task in [after["core_task"], *after["auxiliary_tasks"]]
    }
    return {
        "artifact_type": "desktop_research_core_control_audit",
        "schema_version": "dopey-desktop-research-control-v2",
        "transaction_id": transaction_id,
        "generated_utc": generated_utc,
        "task_names": [ACCELERATION_TASK_NAME, DAILY_RITUAL_TASK_NAME],
        "requested_enabled": enabled,
        "action": (
            "enable_all_paper_automation_schedules"
            if enabled
            else "disable_all_future_paper_automation_starts"
        ),
        "outcome": outcome,
        "before_state": None if before is None else before["state"],
        "after_state": None if after is None else after["state"],
        "before_enabled": None if before is None else before["enabled"],
        "after_enabled": None if after is None else after["enabled"],
        "before_tasks": before_tasks,
        "after_tasks": after_tasks,
        "schedule_mutated": schedule_mutated,
        "rollback_performed": rollback_performed,
        "rollback_verified": rollback_verified,
        "active_process_terminated": False,
        "confirmation_valid": True,
        "error": error,
        "control_scope": "aggregate_paper_research_automation_schedules_only",
        "paper_only": True,
        "live_blocked": True,
    }


def _transaction_id(generated_utc: str, enabled: bool) -> str:
    payload = f"{generated_utc}|{enabled}|{ACCELERATION_TASK_NAME}|{DAILY_RITUAL_TASK_NAME}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _apply_task_enabled_state(runner: SchedulerRunner, enabled: bool) -> None:
    task_names = (
        (DAILY_RITUAL_TASK_NAME, ACCELERATION_TASK_NAME)
        if enabled
        else (ACCELERATION_TASK_NAME, DAILY_RITUAL_TASK_NAME)
    )
    for task_name in task_names:
        if enabled:
            runner.enable_task(task_name)
        else:
            runner.disable_task(task_name)


def _force_fail_closed_off(
    repository_root: Path,
    runner: SchedulerRunner,
) -> tuple[SchedulerControlState | None, bool, str]:
    errors: list[str] = []
    for task_name in (ACCELERATION_TASK_NAME, DAILY_RITUAL_TASK_NAME):
        try:
            runner.disable_task(task_name)
        except SchedulerControlError as error:
            errors.append(f"disable failed for {task_name}: {error}")
    after: SchedulerControlState | None = None
    try:
        after = inspect_research_core(repository_root, runner)
    except SchedulerControlError as error:
        errors.append(f"rollback inspection failed: {error}")
    rollback_verified = (
        after is not None
        and after["state"] in ("OFF", "DRAINING")
        and all(
            not task["enabled"]
            for task in [after["core_task"], *after["auxiliary_tasks"]]
        )
    )
    if not rollback_verified and after is not None:
        errors.append(
            "fail-closed rollback postcondition was not verified: "
            f"state={after['state']}, enabled={after['enabled']}"
        )
    return after, rollback_verified, "; ".join(errors)


def set_research_core_enabled_with_runner(
    repository_root: Path,
    enabled: bool,
    confirmation: str,
    runner: SchedulerRunner,
    audit_path: Path,
    generated_utc: str,
) -> dict[str, object]:
    """Enable/disable future paper cycles through an injected scheduler connector."""

    if confirmation != CONTROL_CONFIRMATION:
        transaction_id = _transaction_id(generated_utc, enabled)
        invalid_record = {
            **_audit_record(
                transaction_id,
                generated_utc,
                enabled,
                "rejected_invalid_confirmation",
                None,
                None,
                False,
                False,
                False,
                "exact confirmation paper_research_only is required",
            ),
            "confirmation_valid": False,
        }
        _append_audit(audit_path, invalid_record)
        raise ResearchCoreConfirmationError(
            "research-core control requires exact confirmation: paper_research_only"
        )

    transaction_id = _transaction_id(generated_utc, enabled)
    before = inspect_research_core(repository_root, runner)
    controlled_tasks = [before["core_task"], *before["auxiliary_tasks"]]
    if any(not task["present"] or not task["identity_verified"] for task in controlled_tasks):
        error = "paper-automation task set failed exact pre-control identity verification"
        _append_audit(
            audit_path,
            _audit_record(
                transaction_id,
                generated_utc,
                enabled,
                "rejected_precondition",
                before,
                None,
                False,
                False,
                False,
                error,
            ),
        )
        raise SchedulerVerificationError(error)
    if enabled and before["state"] == "FAULT":
        error = "research core cannot be enabled while scheduler or lock state is FAULT"
        _append_audit(
            audit_path,
            _audit_record(
                transaction_id,
                generated_utc,
                enabled,
                "rejected_precondition",
                before,
                None,
                False,
                False,
                False,
                error,
            ),
        )
        raise SchedulerVerificationError(error)

    schedule_mutated = any(task["enabled"] != enabled for task in controlled_tasks)
    if not schedule_mutated:
        audit = _audit_record(
            transaction_id,
            generated_utc,
            enabled,
            "no_change_required",
            before,
            before,
            False,
            False,
            False,
            "",
        )
        _append_audit(audit_path, audit)
        return {
            "before": before,
            "after": before,
            "audit": audit,
            "paper_only": True,
            "live_blocked": True,
        }

    intent = _audit_record(
        transaction_id,
        generated_utc,
        enabled,
        "mutation_intent_fsynced",
        before,
        None,
        False,
        False,
        False,
        "",
    )
    _append_audit(audit_path, intent)
    try:
        _apply_task_enabled_state(runner, enabled)
        after = inspect_research_core(repository_root, runner)
        postcondition_states = ("ON", "RUNNING") if enabled else ("OFF", "DRAINING")
        if (
            after["state"] not in postcondition_states
            or after["enabled"] != enabled
            or any(
                task["enabled"] != enabled or not task["identity_verified"]
                for task in [after["core_task"], *after["auxiliary_tasks"]]
            )
        ):
            raise SchedulerVerificationError(
                "research-core control postcondition failed: "
                f"requested_enabled={enabled}, observed_enabled={after['enabled']}, "
                f"observed_state={after['state']}"
            )
    except SchedulerControlError as error:
        rollback_after, rollback_verified, rollback_error = _force_fail_closed_off(
            repository_root,
            runner,
        )
        error_message = str(error)
        if rollback_error:
            error_message = f"{error_message}; {rollback_error}"
        _append_audit(
            audit_path,
            _audit_record(
                transaction_id,
                generated_utc,
                enabled,
                (
                    "failed_mutation_rolled_back_off"
                    if rollback_verified
                    else "failed_mutation_rollback_unverified"
                ),
                before,
                rollback_after,
                True,
                True,
                rollback_verified,
                error_message,
            ),
        )
        raise SchedulerVerificationError(error_message) from error

    audit = _audit_record(
        transaction_id,
        generated_utc,
        enabled,
        "changed",
        before,
        after,
        True,
        False,
        False,
        "",
    )
    try:
        _append_audit(audit_path, audit)
    except SchedulerControlError as error:
        rollback_after, rollback_verified, rollback_error = _force_fail_closed_off(
            repository_root,
            runner,
        )
        error_message = f"successful mutation could not be durably audited: {error}"
        if rollback_error:
            error_message = f"{error_message}; {rollback_error}"
        failure_audit = _audit_record(
            transaction_id,
            generated_utc,
            enabled,
            (
                "failed_audit_rolled_back_off"
                if rollback_verified
                else "failed_audit_rollback_unverified"
            ),
            before,
            rollback_after,
            True,
            True,
            rollback_verified,
            error_message,
        )
        try:
            _append_audit(audit_path, failure_audit)
        except SchedulerControlError as secondary_error:
            raise SchedulerVerificationError(
                f"{error_message}; rollback audit also failed: {secondary_error}"
            ) from secondary_error
        raise SchedulerVerificationError(error_message) from error
    return {
        "before": before,
        "after": after,
        "audit": audit,
        "paper_only": True,
        "live_blocked": True,
    }


def set_research_core_enabled(
    repository_root: Path,
    enabled: bool,
    confirmation: str,
) -> dict[str, object]:
    """Control future starts only after independently re-verifying the execution seal."""

    resolved_root = repository_root.resolve()
    audit_path = resolved_root / CONTROL_AUDIT_RELATIVE_PATH
    generated_utc = datetime.now(timezone.utc).isoformat()
    transaction_id = _transaction_id(generated_utc, enabled)
    constitution_path = resolved_root / CONSTITUTION_STATE_RELATIVE_PATH
    try:
        constitution = _json_object(
            constitution_path.read_text(encoding="utf-8"),
            "constitution_state",
        )
    except (OSError, UnicodeError, SchedulerVerificationError) as error:
        message = f"execution seal could not be verified: path={constitution_path}, error={error}"
        _append_audit(
            audit_path,
            _audit_record(
                transaction_id,
                generated_utc,
                enabled,
                "rejected_unverified_execution_seal",
                None,
                None,
                False,
                False,
                False,
                message,
            ),
        )
        raise SchedulerVerificationError(message) from error
    required_seal = {
        "paper_only": True,
        "live_blocked": True,
        "broker_authority": False,
        "order_authority": False,
        "order_construction_authority": False,
        "credential_access": False,
        "self_unlock_available": False,
    }
    mismatches = [
        key for key, expected in required_seal.items() if constitution.get(key) is not expected
    ]
    if mismatches:
        message = f"execution seal assertions failed: fields={mismatches}"
        _append_audit(
            audit_path,
            _audit_record(
                transaction_id,
                generated_utc,
                enabled,
                "rejected_unverified_execution_seal",
                None,
                None,
                False,
                False,
                False,
                message,
            ),
        )
        raise SchedulerVerificationError(message)
    return set_research_core_enabled_with_runner(
        resolved_root,
        enabled,
        confirmation,
        WindowsSchedulerRunner(resolved_root),
        audit_path,
        generated_utc,
    )
