"""Client-neutral STDIO MCP server for DOPEY research operations.

Compatible with the stable MCP 2025-11-25 initialization lifecycle used by
Codex, Claude Code, and Cursor. Standard output is reserved for JSON-RPC.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from .capabilities import discover_capabilities
from .common import REPO_ROOT
from .compounding import build_compounding_plan
from .cycle import run_acceleration_cycle
from .frontier import run_frontier_council
from .readiness import build_readiness_acceleration_plan
from .schedule import build_schedule_plan
from .system_snapshot import build_system_snapshot
from .universe import build_universe_expansion_plan, seed_universe_candidates


SERVER_NAME = "dopey-frontier-control"
SERVER_VERSION = "0.6.0"
LATEST_STABLE_PROTOCOL = "2025-11-25"
SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
SERVER_INSTRUCTIONS = (
    "DOPEY is paper-only and live-blocked. Use tools to inspect readiness, schedule research, expand governed equity coverage, "
    "and analyze evidence. Never request credentials, connect to a broker, place/cancel orders, or treat paper/backtest output "
    "as proven ROI. Research execution and frontier delegation are disabled unless the operator explicitly enables their environment "
    "gates and supplies the exact confirmation phrase. Do not alter creator-governed evidence policy without an explicit creator directive."
)


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    read_only: bool,
    idempotent: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": False,
            "idempotentHint": idempotent,
            "openWorldHint": False,
        },
    }


TOOLS = [
    _tool(
        "inspect_system_state",
        "Build the current readiness, schedule, universe, compounding, and capability state. Writes only reproducible derived artifacts.",
        {},
        [],
        False,
        True,
    ),
    _tool(
        "inspect_readiness_acceleration",
        "Rank readiness bottlenecks and safe acceleration actions under the current creator-governed evidence policy.",
        {},
        [],
        False,
        True,
    ),
    _tool(
        "inspect_schedule",
        "Show which research lanes are due under the calendar-aware acceleration policy.",
        {
            "lane_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional allowlist of lane IDs; use an empty list for all lanes.",
            }
        },
        ["lane_ids"],
        False,
        True,
    ),
    _tool(
        "inspect_universe_expansion",
        "Find real public-lake symbols that can enter governed equity-research candidacy.",
        {"batch_size": {"type": "integer", "minimum": 1, "maximum": 50}},
        ["batch_size"],
        False,
        True,
    ),
    _tool(
        "inspect_compounding_research",
        "Calculate geometric paper-return evidence and keep compounding disabled until sample and edge gates clear.",
        {},
        [],
        False,
        True,
    ),
    _tool(
        "discover_agent_capabilities",
        "Discover local Codex, Claude, Cursor, OSS-model, MCP, plugin, and skill capabilities and recommend high-value additions.",
        {},
        [],
        False,
        True,
    ),
    _tool(
        "seed_governed_universe_candidates",
        "Register a bounded batch of locally available public-lake symbols as candidates only. Does not promote, trade, or mutate core.",
        {
            "batch_size": {"type": "integer", "minimum": 1, "maximum": 50},
            "confirmation": {"type": "string", "const": "paper_research_only"},
        },
        ["batch_size", "confirmation"],
        False,
        True,
    ),
    _tool(
        "run_research_cycle",
        "Execute due allowlisted paper-research lanes. No broker or order command exists.",
        {
            "lane_ids": {"type": "array", "items": {"type": "string"}},
            "confirmation": {"type": "string", "const": "paper_research_only"},
        },
        ["lane_ids", "confirmation"],
        False,
        False,
    ),
    _tool(
        "run_frontier_analysis_council",
        "Ask the governed OpenRouter four-model role-routed hybrid for analysis-only research. Component routes are internal and cannot be independently selected.",
        {
            "objective": {"type": "string", "minLength": 1, "maxLength": 4000},
            "providers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {
                    "type": "string",
                    "enum": ["openrouter_four_model_hybrid"],
                },
            },
            "timeout_seconds": {"type": "integer", "minimum": 30, "maximum": 900},
            "confirmation": {"type": "string", "const": "analysis_only_no_repo_writes"},
        },
        ["objective", "providers", "timeout_seconds", "confirmation"],
        False,
        False,
    ),
]


def _require_execute_enabled(arguments: dict[str, Any]) -> None:
    if os.environ.get("DOPEY_MCP_ALLOW_EXECUTE", "0") != "1":
        raise PermissionError("research execution is disabled; set DOPEY_MCP_ALLOW_EXECUTE=1 in the MCP client environment")
    if arguments.get("confirmation") != "paper_research_only":
        raise PermissionError("confirmation must be paper_research_only")


def _require_frontier_enabled(arguments: dict[str, Any]) -> None:
    if os.environ.get("DOPEY_MCP_ALLOW_FRONTIER", "0") != "1":
        raise PermissionError("frontier delegation is disabled; set DOPEY_MCP_ALLOW_FRONTIER=1 in the MCP client environment")
    if arguments.get("confirmation") != "analysis_only_no_repo_writes":
        raise PermissionError("confirmation must be analysis_only_no_repo_writes")


def _system_state() -> dict[str, Any]:
    return build_system_snapshot(REPO_ROOT, datetime.now(timezone.utc))


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "inspect_system_state":
        return _system_state()
    if name == "inspect_readiness_acceleration":
        return build_readiness_acceleration_plan(REPO_ROOT)
    if name == "inspect_schedule":
        return build_schedule_plan(
            REPO_ROOT,
            datetime.now(timezone.utc),
            tuple(str(value) for value in arguments.get("lane_ids", [])),
        )
    if name == "inspect_universe_expansion":
        return build_universe_expansion_plan(REPO_ROOT, int(arguments["batch_size"]))
    if name == "inspect_compounding_research":
        return build_compounding_plan(REPO_ROOT)
    if name == "discover_agent_capabilities":
        return discover_capabilities(REPO_ROOT)
    if name == "seed_governed_universe_candidates":
        _require_execute_enabled(arguments)
        return seed_universe_candidates(REPO_ROOT, int(arguments["batch_size"]))
    if name == "run_research_cycle":
        _require_execute_enabled(arguments)
        return run_acceleration_cycle(
            REPO_ROOT,
            "execute",
            tuple(str(value) for value in arguments["lane_ids"]),
            datetime.now(timezone.utc),
        )
    if name == "run_frontier_analysis_council":
        _require_frontier_enabled(arguments)
        return run_frontier_council(
            str(arguments["objective"]),
            tuple(str(value) for value in arguments["providers"]),
            _system_state(),
            int(arguments["timeout_seconds"]),
        )
    raise KeyError(f"unknown MCP tool: {name}")


def _success(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        params = request.get("params", {})
        requested = str(params.get("protocolVersion", ""))
        protocol = requested if requested in SUPPORTED_PROTOCOLS else LATEST_STABLE_PROTOCOL
        return _success(
            request_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": SERVER_INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = request.get("params", {})
        name = str(params.get("name", ""))
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "tools/call arguments must be an object")
        try:
            output = _call_tool(name, arguments)
        except Exception as error:  # MCP must return a structured tool error and remain available
            return _success(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps({"error_type": type(error).__name__, "message": str(error)})}],
                    "isError": True,
                },
            )
        return _success(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False)}],
                "structuredContent": output,
                "isError": False,
            },
        )
    if request_id is None:
        return None
    return _error(request_id, -32601, f"method not found: {method}")


def _handle_message(parsed: object) -> object | None:
    if isinstance(parsed, list):
        responses = [_handle_request(item) for item in parsed if isinstance(item, dict)]
        return [response for response in responses if response is not None]
    if not isinstance(parsed, dict):
        return _error(None, -32600, "request must be a JSON object")
    return _handle_request(parsed)


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            response = _handle_message(parsed)
        except json.JSONDecodeError as error:
            response = _error(None, -32700, f"parse error: {error}")
        except Exception as error:
            response = _error(None, -32603, f"internal error: {type(error).__name__}: {error}")
        if response is not None and response != []:
            sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
