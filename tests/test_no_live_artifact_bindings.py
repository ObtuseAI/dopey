"""Closure guard: no test-visible module may bind a writable live-tree path.

Runner modules bind absolute artifact paths at import time (``REPO_ROOT /
"artifacts" / ...``); one unswept binding is enough for a test run to stomp
live pipeline evidence (observed: fixture-tier records overwriting
artifacts/dopey/signals/directional_setup_signals.jsonl and zeroing the honest
backtest). conftest's redirect_artifact_bindings() + import hook sweep loaded
modules; this test proves the sweep reaches closure over the ENTIRE package
tree: it imports every dopey/operator module, re-runs the sweep, and fails if
any live artifact binding, repo-root report binding, or registered dopey_data
write-target binding survives.

Pattern reference: doofus tests/test_no_live_db_bindings.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import conftest

# Vendored third-party trees and PowerShell-only dirs: nothing to import.
_WALK_EXCLUDED_TOP_LEVEL = {"dopey_open_source_vendor"}


def _iter_module_names() -> list[str]:
    names: list[str] = []
    for package_dir in sorted(conftest.REPO_ROOT.iterdir()):
        name = package_dir.name
        if not package_dir.is_dir() or name in _WALK_EXCLUDED_TOP_LEVEL:
            continue
        if not (name.startswith("dopey") or name == "operator_tools"):
            continue
        for py_file in sorted(package_dir.rglob("*.py")):
            relative = py_file.relative_to(conftest.REPO_ROOT)
            if "__pycache__" in relative.parts:
                continue
            parts = list(relative.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if parts:
                names.append(".".join(parts))
    return names


def test_redirect_artifact_bindings_reaches_closure() -> None:
    imported = 0
    for module_name in _iter_module_names():
        try:
            importlib.import_module(module_name)
            imported += 1
        except Exception:  # noqa: BLE001 - optional deps may be absent
            continue
    assert imported > 100, f"package walk looks broken: only {imported} modules imported"

    conftest.redirect_artifact_bindings()
    leftovers = conftest.find_live_bindings()
    assert not leftovers, (
        "live tree bindings survived redirect_artifact_bindings(): " + ", ".join(sorted(leftovers))
    )


def test_hot_write_paths_are_redirected_and_spine_reads_stay_real() -> None:
    """Spot-check the exact paths whose pollution triggered this layer, and
    prove the real read-only data spine was NOT redirected."""
    signal_engine = importlib.import_module("dopey_analysis.real_history_signal_engine")
    backtester = importlib.import_module("dopey_backtest.real_history_honest_backtester")
    supervisor = importlib.import_module("dopey_autonomy.run_resilient_research_supervisor")
    history_store = importlib.import_module("dopey_data.history_store")

    conftest.redirect_artifact_bindings()

    live_artifacts = str(conftest.LIVE_ARTIFACTS_ROOT)
    for module, attr in (
        (signal_engine, "SIGNAL_ARTIFACT_DIR"),
        (backtester, "BACKTEST_ARTIFACT_DIR" if hasattr(backtester, "BACKTEST_ARTIFACT_DIR") else "ARTIFACT_DIR"),
        (supervisor, "SUPERVISOR_ARTIFACT_DIR"),
        (supervisor, "SUPERVISOR_RUN_JOURNAL_PATH"),
        (supervisor, "SUPERVISOR_LOCK_PATH"),
    ):
        bound = getattr(module, attr)
        assert isinstance(bound, Path)
        assert not conftest._is_under(bound, conftest.LIVE_ARTIFACTS_ROOT), (
            f"{module.__name__}.{attr} still points into the live tree: {bound}"
        )

    for module_name, attr in (
        ("dopey_allocation.run_proof_weighted_allocator", "EXPECTED_ALLOCATION_PLAN_FIXTURE_PATH"),
        ("dopey_incident.run_incident_response_rehearsal", "EXPECTED_INCIDENT_SUMMARY_FIXTURE_PATH"),
        ("dopey_lifecycle.lifecycle_simulator", "LIFECYCLE_EXPECTED_PROOFS_FIXTURE_PATH"),
        ("dopey_portfolio.run_portfolio_replay", "EXPECTED_PORTFOLIO_REPLAY_SUMMARY_FIXTURE_PATH"),
        ("dopey_portfolio.run_portfolio_stress_ladder", "EXPECTED_STRESS_LADDER_SUMMARY_FIXTURE_PATH"),
        ("dopey_portfolio.run_portfolio_stress_ladder", "STRESS_LADDER_REPLAY_CASES_FIXTURE_PATH"),
    ):
        module = importlib.import_module(module_name)
        conftest.redirect_artifact_bindings()
        bound = getattr(module, attr)
        assert isinstance(bound, Path)
        assert not conftest._is_under(bound, conftest.LIVE_DATA_ROOT), (
            f"{module_name}.{attr} still points into the live data tree: {bound}"
        )

    # The supervisor's repo-root report must not target the tracked file.
    assert supervisor.SUPERVISOR_REPORT_PATH.parent != conftest.REPO_ROOT

    # Read-only real data spine stays REAL: tests exercise real staged data.
    assert history_store.HISTORY_ROOT == conftest.REPO_ROOT / "dopey_data" / "history"
    assert history_store.HISTORY_MANIFEST_PATH.exists(), "real history manifest must remain visible"
    assert live_artifacts  # silence unused warning-style lints


def test_no_module_binds_repo_root_dynamic_state_paths() -> None:
    """redirect_target() maps repo-root files only for ``.md`` outputs; the
    governed root ledgers/registries (``PROOF_LEDGER.jsonl`` and friends) are
    written solely through runtime ``repository_root`` arguments, never module
    constants. This guard makes that convention loud: any future module-level
    binding to a governed dynamic-state file fails here instead of silently
    escaping both the sweep and the closure test above.
    """
    from verifier.protected_manifest import ASCENDANCY_DYNAMIC_STATE_PATHS

    for module_name in _iter_module_names():
        try:
            importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - optional deps may be absent
            continue

    governed = {
        (conftest.REPO_ROOT / relative).resolve() for relative in ASCENDANCY_DYNAMIC_STATE_PATHS
    }
    offenders: list[str] = []
    for module_name, module in list(sys.modules.items()):
        top = module_name.split(".")[0]
        if not (top.startswith("dopey") or top == "operator_tools"):
            continue
        for attr, value in list(vars(module).items()):
            if isinstance(value, Path) and value.resolve() in governed:
                offenders.append(f"{module_name}.{attr} -> {value}")
    assert not offenders, (
        "module-level bindings to governed root dynamic-state files (write "
        "through a runtime repository_root argument instead): "
        + ", ".join(sorted(offenders))
    )


def test_import_hook_sweeps_lazy_imports() -> None:
    """A module imported mid-test (the supervisor stage pattern) must come out
    of the import machinery already redirected."""
    victim = "dopey_data.run_history_dataset_validation"
    saved = {
        name: sys.modules.pop(name)
        for name in [victim]
        if name in sys.modules
    }
    try:
        module = importlib.import_module(victim)
        bound = module.HISTORY_ARTIFACT_DIR
        assert not conftest._is_under(bound, conftest.LIVE_ARTIFACTS_ROOT), (
            f"lazy import escaped isolation: {bound}"
        )
    finally:
        sys.modules.update(saved)
        conftest.redirect_artifact_bindings()
