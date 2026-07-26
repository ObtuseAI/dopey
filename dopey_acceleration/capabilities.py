"""Discover local agent, skill, plugin, and MCP acceleration capabilities."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

from .capability_foundry import (
    CAPABILITY_FOUNDRY_ARTIFACT_TYPE,
    CAPABILITY_FOUNDRY_SNAPSHOT_FIELDS,
    CAPABILITY_FOUNDRY_STATUS,
    CAPABILITY_FOUNDRY_VERSION,
    CATALOG_PATH,
    compose_capability_foundry_snapshot,
    load_capability_catalog,
)
from .common import (
    ARTIFACT_ROOT,
    REPO_ROOT,
    read_optional_json,
    stable_hash,
    stamped,
    write_json_atomic,
)


CAPABILITY_PATH = ARTIFACT_ROOT / "capability_discovery.json"
CAPABILITY_FOUNDRY_PATH = ARTIFACT_ROOT / "capability_foundry" / "latest_snapshot.json"
COMMANDS: Final[tuple[str, ...]] = (
    "codex",
    "claude",
    "cursor-agent",
    "context7",
    "ollama",
    "lmstudio",
    "git",
    "gh",
    "node",
    "uv",
)
DOPEY_MCP_MODULE: Final[str] = "dopey_acceleration.mcp_server"


class AdditionSpec(TypedDict):
    capability: str
    purpose: str
    official_source: str
    priority: Literal["high", "medium"]
    command_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]


class ClientConfigSpec(TypedDict):
    client_id: Literal["codex", "claude-code", "cursor"]
    config_path: Path
    config_format: Literal["json", "toml"]
    server_key: str


ADDITION_SPECS: Final[tuple[AdditionSpec, ...]] = (
    {
        "capability": "OpenAI Docs MCP",
        "purpose": "current Codex/OpenAI integration guidance",
        "official_source": "https://developers.openai.com/learn/docs-mcp",
        "priority": "high",
        "command_ids": (),
        "skill_ids": ("openai-docs",),
    },
    {
        "capability": "Context7 MCP",
        "purpose": "current library and framework documentation for agent implementations",
        "official_source": "https://github.com/upstash/context7",
        "priority": "high",
        "command_ids": ("context7",),
        "skill_ids": ("context7",),
    },
    {
        "capability": "GitHub MCP",
        "purpose": "structured PR, issue, and repository operations beyond local git",
        "official_source": "https://github.com/github/github-mcp-server",
        "priority": "high",
        "command_ids": ("gh",),
        "skill_ids": ("github", "gh-address-comments", "gh-fix-ci", "yeet"),
    },
    {
        "capability": "Playwright or Chrome DevTools MCP",
        "purpose": "browser-based dashboard and data-pipeline verification",
        "official_source": "https://github.com/ChromeDevTools/chrome-devtools-mcp",
        "priority": "medium",
        "command_ids": (),
        "skill_ids": ("control-chrome", "control-in-app-browser"),
    },
    {
        "capability": "local Codex OSS provider",
        "purpose": "optional local Ollama or LM Studio frontier analysis instead of a cloud model",
        "official_source": "https://learn.chatgpt.com/docs/developer-commands",
        "priority": "medium",
        "command_ids": ("ollama", "lmstudio"),
        "skill_ids": (),
    },
)


def _skill_names(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted({path.parent.name for path in root.rglob("SKILL.md")})


def _command_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for name in COMMANDS:
        resolved = shutil.which(name)
        records.append(
            {
                "command": name,
                "available": resolved is not None,
                "path": resolved or "",
                "discovery_status": (
                    "path_detected_execution_unverified"
                    if resolved is not None
                    else "missing"
                ),
            }
        )
    return records


def _public_addition_record(spec: AdditionSpec) -> dict[str, str]:
    return {
        "capability": spec["capability"],
        "purpose": spec["purpose"],
        "official_source": spec["official_source"],
        "priority": spec["priority"],
    }


def _addition_matrix(
    available_commands: set[str],
    personal_skills: set[str],
    plugin_skills: set[str],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for spec in ADDITION_SPECS:
        detected_by = sorted(
            [
                *[
                    f"command:{command}"
                    for command in spec["command_ids"]
                    if command in available_commands
                ],
                *[
                    f"personal_skill:{skill}"
                    for skill in spec["skill_ids"]
                    if skill in personal_skills
                ],
                *[
                    f"plugin_skill_cache:{skill}"
                    for skill in spec["skill_ids"]
                    if skill in plugin_skills
                ],
            ]
        )
        records.append(
            {
                **_public_addition_record(spec),
                "satisfaction_status": (
                    "detected_unverified" if detected_by else "missing"
                ),
                "detected_by": detected_by,
                "observed_usable_by": [],
                "runtime_verification_required": bool(detected_by),
            }
        )
    return records


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return []
    return list(value)


def _read_client_config(
    path: Path, config_format: Literal["json", "toml"]
) -> tuple[dict[str, object], str]:
    if not path.exists():
        return {}, "missing"
    try:
        raw = path.read_text(encoding="utf-8")
        parsed: object = (
            json.loads(raw) if config_format == "json" else tomllib.loads(raw)
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
    ) as error:
        return {}, f"invalid_{type(error).__name__}"
    if not isinstance(parsed, dict):
        return {}, "invalid_root_type"
    return {str(key): value for key, value in parsed.items()}, "available"


def _gate_state(environment: Mapping[str, object], key: str) -> str:
    value = environment.get(key)
    if value == "0":
        return "disabled"
    if value == "1":
        return "enabled"
    if value is None:
        return "missing"
    return "invalid"


def _same_path(left: str, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).expanduser().resolve() == right.resolve()
    except OSError:
        return False


def _client_specs(repo_root: Path) -> tuple[ClientConfigSpec, ...]:
    return (
        {
            "client_id": "codex",
            "config_path": repo_root / ".codex" / "config.toml",
            "config_format": "toml",
            "server_key": "dopey_frontier_control",
        },
        {
            "client_id": "claude-code",
            "config_path": repo_root / ".mcp.json",
            "config_format": "json",
            "server_key": "dopey-frontier-control",
        },
        {
            "client_id": "cursor",
            "config_path": repo_root / ".cursor" / "mcp.json",
            "config_format": "json",
            "server_key": "dopey-frontier-control",
        },
    )


def _client_config_record(repo_root: Path, spec: ClientConfigSpec) -> dict[str, object]:
    parsed, file_status = _read_client_config(
        spec["config_path"], spec["config_format"]
    )
    server_root_key = "mcp_servers" if spec["config_format"] == "toml" else "mcpServers"
    servers = _object_mapping(parsed.get(server_root_key))
    server = _object_mapping(servers.get(spec["server_key"]))
    environment = _object_mapping(server.get("env"))
    command = server.get("command")
    command_text = command if isinstance(command, str) else ""
    args = _string_list(server.get("args"))
    server_configured = bool(server)
    enabled_value = server.get("enabled", True)
    enabled = server_configured and enabled_value is True
    expected_python = repo_root / ".venv" / "Scripts" / "python.exe"
    launch_target_match = _same_path(command_text, expected_python)
    launch_executable_exists = expected_python.is_file()
    module_target_match = args == ["-m", DOPEY_MCP_MODULE]
    configured_cwd = server.get("cwd")
    cwd_match = (
        True
        if configured_cwd is None
        else isinstance(configured_cwd, str) and _same_path(configured_cwd, repo_root)
    )
    execute_gate = _gate_state(environment, "DOPEY_MCP_ALLOW_EXECUTE")
    frontier_gate = _gate_state(environment, "DOPEY_MCP_ALLOW_FRONTIER")
    target_healthy = (
        file_status == "available"
        and server_configured
        and enabled
        and launch_target_match
        and launch_executable_exists
        and module_target_match
        and cwd_match
    )
    gates_valid = execute_gate in {"disabled", "enabled"} and frontier_gate in {
        "disabled",
        "enabled",
    }
    if not target_healthy or not gates_valid:
        configuration_status = "invalid_or_incomplete"
    elif execute_gate == "enabled":
        configuration_status = "unsafe_research_execution_enabled"
    elif frontier_gate == "enabled":
        configuration_status = (
            "configured_frontier_enabled_execute_blocked_runtime_unverified"
        )
    else:
        configuration_status = "configured_inspection_only_runtime_unverified"
    return {
        "client_id": spec["client_id"],
        "config_path": str(spec["config_path"]),
        "file_status": file_status,
        "server_configured": server_configured,
        "server_enabled": enabled,
        "launch_target_status": "matched" if launch_target_match else "mismatch",
        "launch_executable_status": (
            "present_execution_unverified" if launch_executable_exists else "missing"
        ),
        "module_target_status": "matched" if module_target_match else "mismatch",
        "cwd_status": "matched_or_project_inherited" if cwd_match else "mismatch",
        "research_execution_gate": execute_gate,
        "frontier_analysis_gate": frontier_gate,
        "configuration_status": configuration_status,
        "runtime_handshake_verified": False,
        "credential_values_reported": False,
    }


def _cross_client_mcp_health(repo_root: Path) -> dict[str, object]:
    clients = [
        _client_config_record(repo_root, spec) for spec in _client_specs(repo_root)
    ]
    configured_valid_count = sum(
        str(record["configuration_status"]).startswith("configured_")
        for record in clients
    )
    configured_count = sum(record["server_configured"] is True for record in clients)
    frontier_states = {
        str(record["frontier_analysis_gate"])
        for record in clients
        if record["frontier_analysis_gate"] in {"enabled", "disabled"}
    }
    execute_blocked_all = all(
        record["research_execution_gate"] == "disabled" for record in clients
    )
    if configured_valid_count != len(clients):
        status = "degraded"
    elif len(frontier_states) > 1:
        status = "configured_client_specific_frontier_policy_runtime_unverified"
    else:
        status = "configured_consistent_runtime_unverified"
    return {
        "status": status,
        "client_count": len(clients),
        "configured_client_count": configured_count,
        "configured_valid_client_count": configured_valid_count,
        "runtime_verified_client_count": 0,
        "runtime_verification_status": "not_performed",
        "research_execution_blocked_all_clients": execute_blocked_all,
        "frontier_gate_consistent": len(frontier_states) <= 1,
        "clients": clients,
        "credential_values_reported": False,
    }


def _probe_local_mcp(repo_root: Path) -> dict[str, object]:
    python = repo_root / ".venv" / "Scripts" / "python.exe"
    contract = {
        "capability_id": "dopey_frontier_control_mcp",
        "permissions": "inspection_only",
        "cost_class": "local_subprocess",
        "determinism": "protocol_and_tool_catalog_deterministic",
        "allowed_side_effects": [],
        "paper_only": True,
        "live_blocked": True,
    }
    if not python.is_file():
        return {
            **contract,
            "probe_status": "runtime_unverified_missing_python",
            "latency_ms": None,
            "tool_count": 0,
            "failure_type": "FileNotFoundError",
        }
    request_lines = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "dopey-capability-probe",
                        "version": "1",
                    },
                },
            },
            separators=(",", ":"),
        ),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            separators=(",", ":"),
        ),
    )
    environment = os.environ.copy()
    environment["DOPEY_MCP_ALLOW_EXECUTE"] = "0"
    environment["DOPEY_MCP_ALLOW_FRONTIER"] = "0"
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [str(python), "-m", DOPEY_MCP_MODULE],
            cwd=str(repo_root),
            env=environment,
            input="\n".join(request_lines) + "\n",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            **contract,
            "probe_status": "runtime_probe_timeout",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "tool_count": 0,
            "failure_type": "TimeoutExpired",
        }
    except OSError as error:
        return {
            **contract,
            "probe_status": "runtime_probe_launch_failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "tool_count": 0,
            "failure_type": type(error).__name__,
        }
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    if completed.returncode != 0:
        return {
            **contract,
            "probe_status": "runtime_probe_process_failed",
            "latency_ms": latency_ms,
            "tool_count": 0,
            "failure_type": f"returncode_{completed.returncode}",
        }
    try:
        responses = tuple(
            json.loads(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        )
    except json.JSONDecodeError:
        return {
            **contract,
            "probe_status": "runtime_probe_protocol_invalid",
            "latency_ms": latency_ms,
            "tool_count": 0,
            "failure_type": "JSONDecodeError",
        }
    by_id = {
        response.get("id"): response
        for response in responses
        if isinstance(response, dict)
    }
    initialize = by_id.get(1)
    tools_response = by_id.get(2)
    initialize_result = (
        initialize.get("result")
        if isinstance(initialize, dict)
        and isinstance(initialize.get("result"), dict)
        else {}
    )
    tools_result = (
        tools_response.get("result")
        if isinstance(tools_response, dict)
        and isinstance(tools_response.get("result"), dict)
        else {}
    )
    tools = tools_result.get("tools")
    if (
        initialize_result.get("protocolVersion") != "2025-11-25"
        or not isinstance(tools, list)
        or not any(
            isinstance(tool, dict)
            and tool.get("name") == "inspect_system_state"
            for tool in tools
        )
    ):
        return {
            **contract,
            "probe_status": "runtime_probe_contract_failed",
            "latency_ms": latency_ms,
            "tool_count": len(tools) if isinstance(tools, list) else 0,
            "failure_type": "ContractMismatch",
        }
    return {
        **contract,
        "probe_status": "runtime_verified_inspection_only",
        "latency_ms": latency_ms,
        "tool_count": len(tools),
        "failure_type": "",
    }


def _read_verified_stamped_artifact(path: Path) -> tuple[dict[str, Any], str]:
    artifact, status = read_optional_json(path)
    if status != "available":
        return artifact, status
    reproducibility_hash = artifact.get("reproducibility_hash")
    if not isinstance(reproducibility_hash, str) or not reproducibility_hash:
        raise ValueError(
            f"stamped artifact is missing its reproducibility hash: path={path}"
        )
    body = {
        str(key): value
        for key, value in artifact.items()
        if key != "reproducibility_hash"
    }
    expected_hash = stable_hash(body)
    if reproducibility_hash != expected_hash:
        raise ValueError(
            "stamped artifact reproducibility hash mismatch: "
            f"path={path}, expected={expected_hash}, observed={reproducibility_hash}"
        )
    return artifact, "available_integrity_verified"


def _read_compatible_foundry_artifact(
    path: Path,
    catalog_path: Path,
) -> tuple[dict[str, Any], str]:
    artifact, status = _read_verified_stamped_artifact(path)
    if status != "available_integrity_verified":
        return artifact, status
    if set(artifact) != CAPABILITY_FOUNDRY_SNAPSHOT_FIELDS:
        return {}, "stale_incompatible_schema"
    (
        expected_catalog_version,
        _observed_at,
        _remote_observation_status,
        _remote_verification_limitations,
        _sources,
        expected_catalog_hash,
    ) = load_capability_catalog(catalog_path)
    expected_fields = {
        "artifact_type": CAPABILITY_FOUNDRY_ARTIFACT_TYPE,
        "foundry_version": CAPABILITY_FOUNDRY_VERSION,
        "foundry_status": CAPABILITY_FOUNDRY_STATUS,
        "catalog_version": expected_catalog_version,
        "catalog_hash": expected_catalog_hash,
        "remote_provenance_verification_status": ("not_performed_by_offline_foundry"),
    }
    if any(
        artifact.get(field_name) != expected_value
        for field_name, expected_value in expected_fields.items()
    ):
        return {}, "stale_incompatible_version_or_catalog"
    expected_artifact = compose_capability_foundry_snapshot(catalog_path)
    if artifact != expected_artifact:
        return {}, "stale_incompatible_content"
    return artifact, status


def discover_capabilities(repo_root: Path) -> dict[str, Any]:
    if repo_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(
            f"repository root mismatch: expected={REPO_ROOT}, actual={repo_root}"
        )
    home = Path.home()
    command_records = _command_records()
    personal_skills = _skill_names(home / ".codex" / "skills")
    plugin_skills = _skill_names(home / ".codex" / "plugins" / "cache")
    available_commands = {
        str(record["command"])
        for record in command_records
        if record["available"] is True
    }
    addition_matrix = _addition_matrix(
        available_commands, set(personal_skills), set(plugin_skills)
    )
    recommendations = [
        {
            "capability": str(record["capability"]),
            "purpose": str(record["purpose"]),
            "official_source": str(record["official_source"]),
            "priority": str(record["priority"]),
        }
        for record in addition_matrix
        if record["satisfaction_status"] == "missing"
    ]
    satisfied_additions = [
        record
        for record in addition_matrix
        if record["satisfaction_status"] == "observed_usable"
    ]
    verification_required_additions = [
        record
        for record in addition_matrix
        if record["satisfaction_status"] == "detected_unverified"
    ]
    foundry, foundry_status = _read_compatible_foundry_artifact(
        CAPABILITY_FOUNDRY_PATH,
        CATALOG_PATH,
    )
    foundry_summary = {
        "artifact_status": foundry_status,
        "artifact_path": str(CAPABILITY_FOUNDRY_PATH),
        "foundry_status": str(foundry.get("foundry_status", "missing")),
        "foundry_version": str(foundry.get("foundry_version", "missing")),
        "remote_provenance_verification_status": str(
            foundry.get(
                "remote_provenance_verification_status",
                "missing",
            )
        ),
        "source_count": int(foundry.get("source_count", 0)),
        "internal_source_count": int(foundry.get("obtuseai_internal_source_count", 0)),
        "external_source_count": int(foundry.get("external_oss_source_count", 0)),
        "runtime_capabilities_proven_by_foundry": 0,
        "automatic_installation_allowed": False,
        "automatic_source_copy_allowed": False,
        "automatic_activation_allowed": False,
    }
    local_mcp_probe = _probe_local_mcp(repo_root)
    result = stamped(
        {
            "artifact_type": "agent_capability_discovery",
            "capability_version": "dopey-agent-capability-discovery-v8",
            "commands": command_records,
            "personal_skill_count": len(personal_skills),
            "personal_skills": personal_skills,
            "personal_skill_discovery_scope": "installed_skill_directory_presence",
            "plugin_skill_count": len(plugin_skills),
            "plugin_skills": plugin_skills,
            "plugin_skill_discovery_scope": "cache_presence_activation_unverified",
            "capability_addition_matrix": addition_matrix,
            "satisfied_additions": satisfied_additions,
            "verification_required_additions": verification_required_additions,
            "recommended_additions": recommendations,
            "repository_capability_foundry": foundry_summary,
            "cross_client_mcp_targets": ["codex", "claude-code", "cursor"],
            "cross_client_mcp_health": _cross_client_mcp_health(repo_root),
            "runtime_capability_contracts": [local_mcp_probe],
            "runtime_proven_capability_count": (
                1
                if local_mcp_probe["probe_status"]
                == "runtime_verified_inspection_only"
                else 0
            ),
            "frontier_modes": [
                "host_client_agent",
                "optional_cloud_council",
                "optional_codex_local_oss",
            ],
            "credentials_written": False,
            "credential_values_reported": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    write_json_atomic(CAPABILITY_PATH, result)
    return result
