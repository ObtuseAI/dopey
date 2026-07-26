"""Focused coverage for effective DOPEY capability discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_acceleration.capabilities import (
    _addition_matrix,
    _cross_client_mcp_health,
    _probe_local_mcp,
    _read_compatible_foundry_artifact,
    _read_verified_stamped_artifact,
)
from dopey_acceleration.capability_foundry import (
    CATALOG_PATH,
    build_capability_foundry_snapshot,
)
from dopey_acceleration.common import stable_hash


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_detected_capabilities_remain_runtime_unverified() -> None:
    matrix = _addition_matrix(
        {"gh"},
        {"openai-docs"},
        {"github", "control-chrome"},
    )
    status_by_capability = {
        str(record["capability"]): str(record["satisfaction_status"])
        for record in matrix
    }

    assert status_by_capability["OpenAI Docs MCP"] == "detected_unverified"
    assert status_by_capability["GitHub MCP"] == "detected_unverified"
    assert (
        status_by_capability["Playwright or Chrome DevTools MCP"]
        == "detected_unverified"
    )
    assert status_by_capability["Context7 MCP"] == "missing"
    assert status_by_capability["local Codex OSS provider"] == "missing"


def test_local_mcp_capability_probe_verifies_only_inspection_contract() -> None:
    probe = _probe_local_mcp(REPO_ROOT)

    assert probe["probe_status"] == "runtime_verified_inspection_only"
    assert int(probe["tool_count"]) >= 1
    assert probe["permissions"] == "inspection_only"
    assert probe["allowed_side_effects"] == []
    assert probe["live_blocked"] is True


def test_cross_client_health_reports_only_safe_effective_fields(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "dopey"
    expected_python = repo_root / ".venv" / "Scripts" / "python.exe"
    expected_python.parent.mkdir(parents=True)
    expected_python.write_text("", encoding="utf-8")
    codex_config = repo_root / ".codex" / "config.toml"
    claude_config = repo_root / ".mcp.json"
    cursor_config = repo_root / ".cursor" / "mcp.json"
    codex_config.parent.mkdir(parents=True)
    cursor_config.parent.mkdir(parents=True)
    codex_config.write_text(
        "\n".join(
            [
                "[mcp_servers.dopey_frontier_control]",
                f"command = '{expected_python.as_posix()}'",
                'args = ["-m", "dopey_acceleration.mcp_server"]',
                f"cwd = '{repo_root.as_posix()}'",
                "enabled = true",
                "",
                "[mcp_servers.dopey_frontier_control.env]",
                'DOPEY_MCP_ALLOW_EXECUTE = "0"',
                'DOPEY_MCP_ALLOW_FRONTIER = "1"',
                'OPENROUTER_API_KEY = "sentinel-secret-never-report"',
            ]
        ),
        encoding="utf-8",
    )
    json_config = {
        "mcpServers": {
            "dopey-frontier-control": {
                "command": str(expected_python),
                "args": ["-m", "dopey_acceleration.mcp_server"],
                "env": {
                    "DOPEY_MCP_ALLOW_EXECUTE": "0",
                    "DOPEY_MCP_ALLOW_FRONTIER": "0",
                    "OPENROUTER_API_KEY": "sentinel-secret-never-report",
                },
            }
        }
    }
    claude_config.parent.mkdir(parents=True, exist_ok=True)
    claude_config.write_text(json.dumps(json_config), encoding="utf-8")
    cursor_config.write_text(json.dumps(json_config), encoding="utf-8")

    health = _cross_client_mcp_health(repo_root)
    serialized = json.dumps(health, sort_keys=True)

    assert (
        health["status"]
        == "configured_client_specific_frontier_policy_runtime_unverified"
    )
    assert health["configured_client_count"] == 3
    assert health["configured_valid_client_count"] == 3
    assert health["runtime_verified_client_count"] == 0
    assert health["runtime_verification_status"] == "not_performed"
    assert health["research_execution_blocked_all_clients"] is True
    assert health["frontier_gate_consistent"] is False
    assert "sentinel-secret-never-report" not in serialized
    assert "OPENROUTER_API_KEY" not in serialized


def test_foundry_consumer_rejects_tampered_stamped_artifact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "foundry.json"
    body = {
        "artifact_type": "governed_repository_capability_foundry_snapshot",
        "foundry_status": "complete_quarantined_unverified_provenance_candidates",
        "source_count": 1,
    }
    path.write_text(
        json.dumps({**body, "reproducibility_hash": stable_hash(body)}),
        encoding="utf-8",
    )

    artifact, status = _read_verified_stamped_artifact(path)

    assert status == "available_integrity_verified"
    assert artifact["source_count"] == 1

    path.write_text(
        json.dumps(
            {
                **artifact,
                "source_count": 999,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="reproducibility hash mismatch"):
        _read_verified_stamped_artifact(path)


def test_foundry_consumer_rejects_self_consistent_incompatible_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "foundry.json"
    artifact = build_capability_foundry_snapshot(CATALOG_PATH, path)
    incompatible_body = {
        **{
            key: value
            for key, value in artifact.items()
            if key != "reproducibility_hash"
        },
        "foundry_version": "dopey-capability-foundry-stale",
    }
    path.write_text(
        json.dumps(
            {
                **incompatible_body,
                "reproducibility_hash": stable_hash(incompatible_body),
            }
        ),
        encoding="utf-8",
    )

    loaded, status = _read_compatible_foundry_artifact(path, CATALOG_PATH)

    assert loaded == {}
    assert status == "stale_incompatible_version_or_catalog"


def test_foundry_consumer_rejects_self_consistent_malformed_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "foundry.json"
    artifact = build_capability_foundry_snapshot(CATALOG_PATH, path)
    malformed_body = {
        **{
            key: value
            for key, value in artifact.items()
            if key != "reproducibility_hash"
        },
        "source_count": -9,
        "ranked_candidates": "not-a-candidate-array",
        "automatic_activation_allowed": True,
    }
    path.write_text(
        json.dumps(
            {
                **malformed_body,
                "reproducibility_hash": stable_hash(malformed_body),
            }
        ),
        encoding="utf-8",
    )

    loaded, status = _read_compatible_foundry_artifact(path, CATALOG_PATH)

    assert loaded == {}
    assert status == "stale_incompatible_content"
