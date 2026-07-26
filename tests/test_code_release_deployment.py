"""Integration tests for the state-preserving DOPEY code release deployer."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from operator_tools.deploy_code_release import CONFIRMATION, apply_release_plan, build_release_plan


def _initialize_source(source_root: Path) -> None:
    (source_root / "dopey" / "gates").mkdir(parents=True)
    (source_root / "dopey" / "gates" / "policy.py").write_text("PAPER_ONLY = True\n", encoding="utf-8")
    (source_root / "operator_tools").mkdir()
    (source_root / "operator_tools" / "run.py").write_text("print('paper')\n", encoding="utf-8")
    (source_root / "pyproject.toml").write_text("[project]\nname = 'dopey'\nversion = '0.1.0'\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=source_root, check=True)
    subprocess.run(["git", "config", "user.email", "dopey-test@example.invalid"], cwd=source_root, check=True)
    subprocess.run(["git", "config", "user.name", "DOPEY Test"], cwd=source_root, check=True)
    subprocess.run(["git", "add", "."], cwd=source_root, check=True)
    subprocess.run(["git", "commit", "-qm", "test release"], cwd=source_root, check=True)


def test_code_release_preserves_state_and_backs_up_overwritten_code(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    _initialize_source(source_root)
    target_code = target_root / "dopey" / "gates" / "policy.py"
    target_code.parent.mkdir(parents=True)
    target_code.write_text("PAPER_ONLY = 'old'\n", encoding="utf-8")
    state_path = target_root / "artifacts" / "dopey" / "vnext" / "ledger.jsonl"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"settlement":"immutable"}\n', encoding="utf-8")

    plan = build_release_plan(source_root, target_root)
    manifest = apply_release_plan(plan, CONFIRMATION)

    assert manifest["deployment_status"] == "complete_verified"
    assert target_code.read_text(encoding="utf-8") == "PAPER_ONLY = True\n"
    assert state_path.read_text(encoding="utf-8") == '{"settlement":"immutable"}\n'
    backup_path = Path(next(item["backup_path"] for item in manifest["files"] if item["relative_path"] == "dopey/gates/policy.py"))
    assert backup_path.read_text(encoding="utf-8") == "PAPER_ONLY = 'old'\n"
    latest = json.loads(
        (target_root / "artifacts" / "dopey" / "deployment" / "latest_code_release.json").read_text(encoding="utf-8")
    )
    assert latest["verification_hash"] == manifest["verification_hash"]


def test_code_release_refuses_dirty_source_wrong_confirmation_and_active_lock(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    _initialize_source(source_root)
    clean_plan = build_release_plan(source_root, target_root)
    with pytest.raises(PermissionError, match="paper_research_code_only"):
        apply_release_plan(clean_plan, "wrong")

    lock_path = target_root / "artifacts" / "dopey" / "acceleration" / "acceleration_cycle.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("123", encoding="ascii")
    with pytest.raises(RuntimeError, match="acceleration cycle lock"):
        apply_release_plan(clean_plan, CONFIRMATION)
    lock_path.unlink()

    (source_root / "dopey" / "gates" / "policy.py").write_text("PAPER_ONLY = False\n", encoding="utf-8")
    dirty_plan = build_release_plan(source_root, target_root)
    with pytest.raises(RuntimeError, match="dirty source"):
        apply_release_plan(dirty_plan, CONFIRMATION)


def test_code_release_rolls_back_prior_updates_after_atomic_copy_failure(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    _initialize_source(source_root)
    target_code = target_root / "dopey" / "gates" / "policy.py"
    target_code.parent.mkdir(parents=True)
    target_code.write_text("PAPER_ONLY = 'old'\n", encoding="utf-8")
    plan = build_release_plan(source_root, target_root)
    blocked_target = target_root / "operator_tools" / "run.py"
    blocked_target.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="rollback was attempted"):
        apply_release_plan(plan, CONFIRMATION)

    assert target_code.read_text(encoding="utf-8") == "PAPER_ONLY = 'old'\n"
    failed = json.loads(
        (target_root / "artifacts" / "dopey" / "deployment" / "latest_code_release.json").read_text(encoding="utf-8")
    )
    assert failed["deployment_status"] == "failed_rolled_back"
    assert failed["rollback_complete"] is True
    assert not tuple(target_root.rglob(".*.tmp"))
