"""Integration coverage for resumable content-addressed nightly test shards."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from operator_tools.nightly_shards import build_test_shards, run_sharded_suite


def test_nightly_shards_execute_and_reuse_green_checkpoints(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tests_dir / "conftest.py").write_text("", encoding="utf-8")
    (tests_dir / "test_alpha.py").write_text("def test_alpha():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    (tests_dir / "test_beta.py").write_text("def test_beta():\n    assert 'dopey'.upper() == 'DOPEY'\n", encoding="utf-8")
    nightly_dir = repo_root / "artifacts" / "nightly"

    first = run_sharded_suite(sys.executable, repo_root, tests_dir, nightly_dir, 2, 2, 30)
    timeout_checkpoint = nightly_dir / "shard_checkpoints" / "prior-timeout" / "shard-999.json"
    timeout_checkpoint.parent.mkdir(parents=True)
    timeout_checkpoint.write_text(
        json.dumps(
            {
                "status": "inconclusive_timeout",
                "junit": str(timeout_checkpoint.with_suffix(".xml")),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    second = run_sharded_suite(sys.executable, repo_root, tests_dir, nightly_dir, 2, 2, 30)

    assert first["suite_status"] == "complete_green"
    assert first["passed"] == 2
    assert first["reused_checkpoint_count"] == 0
    assert second["suite_status"] == "complete_green"
    assert second["reused_checkpoint_count"] == 2
    assert second["suite_fingerprint"] == first["suite_fingerprint"]


def test_nightly_shards_keep_ordered_integration_chains_together(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)
    ordered_names = (
        "test_public_signal_research_breakthrough_v2.py",
        "test_public_signal_research_breakthrough_v3.py",
        "test_public_signal_research_breakthrough_v4.py",
        "test_public_signal_research_breakthrough_v5.py",
        "test_public_signal_research_breakthrough_v6.py",
        "test_public_signal_research_breakthrough_v7.py",
    )
    for name in (*ordered_names, "test_unrelated.py"):
        (tests_dir / name).write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    shards = build_test_shards(tests_dir, 3, {})
    containing = next(shard for shard in shards if any(path.name == ordered_names[0] for path in shard))
    positions = [tuple(path.name for path in containing).index(name) for name in ordered_names]

    assert positions == sorted(positions)
    assert all(name in {path.name for path in containing} for name in ordered_names)


def test_nightly_shards_invalidate_checkpoints_when_production_source_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (repo_root / "production.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests_dir / "conftest.py").write_text("", encoding="utf-8")
    (tests_dir / "test_alpha.py").write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
    nightly_dir = repo_root / "artifacts" / "nightly"

    first = run_sharded_suite(sys.executable, repo_root, tests_dir, nightly_dir, 1, 1, 30)
    (repo_root / "production.py").write_text("VALUE = 2\n", encoding="utf-8")
    second = run_sharded_suite(sys.executable, repo_root, tests_dir, nightly_dir, 1, 1, 30)

    assert first["suite_status"] == "complete_green"
    assert second["suite_status"] == "complete_green"
    assert second["suite_fingerprint"] != first["suite_fingerprint"]
    assert second["reused_checkpoint_count"] == 0
    assert second["duration_hint_file_count"] == 1


def test_nightly_shards_reuse_failed_junit_only_for_duration_balancing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tests_dir / "conftest.py").write_text("", encoding="utf-8")
    test_file = tests_dir / "test_alpha.py"
    test_file.write_text("def test_alpha():\n    assert False\n", encoding="utf-8")
    nightly_dir = repo_root / "artifacts" / "nightly"

    failed = run_sharded_suite(sys.executable, repo_root, tests_dir, nightly_dir, 1, 1, 30)
    test_file.write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
    repaired = run_sharded_suite(sys.executable, repo_root, tests_dir, nightly_dir, 1, 1, 30)

    assert failed["suite_status"] == "complete_failures"
    assert repaired["suite_status"] == "complete_green"
    assert repaired["duration_hint_file_count"] == 1
    assert repaired["reused_checkpoint_count"] == 0


def test_nightly_shard_timeout_terminates_process_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n",
        encoding="utf-8",
    )
    (tests_dir / "conftest.py").write_text("", encoding="utf-8")
    (tests_dir / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n",
        encoding="utf-8",
    )
    nightly_dir = repo_root / "artifacts" / "nightly"

    result = run_sharded_suite(
        sys.executable,
        repo_root,
        tests_dir,
        nightly_dir,
        1,
        1,
        1,
    )

    assert result["suite_status"] == "inconclusive_timeout"
    assert result["shards"][0]["process_tree_terminated"] is True
    assert result["shards"][0]["status"] == "inconclusive_timeout"
