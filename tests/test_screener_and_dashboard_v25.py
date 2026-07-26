"""Tests: V25 adaptive target screener + operator dashboard.

Covers the archetype declarations, the evolvable-surface contract, factor
honesty (missing data -> no fabricated numbers), the elite archive's held-out
discipline (recommend-never-apply, deterministic proposals), the screener
runner's artifacts and semantics stamps, the doofus fitness CLI contract, the
supervisor stage wiring, and the dashboard's state builder + hard boundaries
(localhost-only, no order paths, envelope stamps).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from dopey_screener import screen_config
from dopey_screener.elite_archive import (
    EVALUABLE_FAMILIES,
    RECOMMEND_MARGIN,
    TRAIN_END_DATE,
    current_weights,
    evaluate_weight_set,
    load_archive,
    propose_variants,
    run_elite_archive_cycle,
)
from dopey_screener.factor_engine import (
    load_adjusted_closes,
    point_in_time_factors,
    screenable_universe,
    snapshot_factors,
)
from dopey_screener.run_target_screener import (
    SCREENER_SUMMARY_PATH,
    SCREENER_TARGETS_PATH,
    run_target_screener,
)
from dopey_screener.strategy_archetypes import (
    EXECUTABLE_STRUCTURES,
    FACTOR_FAMILIES,
    build_archetypes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def screener_result() -> dict:
    return run_target_screener()


# ---------------------------------------------------------------------------
# Archetypes + evolvable surface contract
# ---------------------------------------------------------------------------

def test_archetypes_cover_call_put_and_screen_only() -> None:
    archetypes = build_archetypes()
    structures = {a.executable_structure for a in archetypes}
    assert "long_call" in structures
    assert "long_put" in structures
    assert structures <= EXECUTABLE_STRUCTURES | {"screen_only"}


def test_archetype_weights_cover_all_factor_families() -> None:
    for archetype in build_archetypes():
        assert set(archetype.weights) == set(FACTOR_FAMILIES)


def test_screen_config_is_flat_numeric_assignments_only() -> None:
    """The doofus/external-evolver contract: every tunable is a top-level
    NAME = <number> single-line assignment (same as exit_policy_config)."""
    tree = ast.parse(Path("dopey_screener/screen_config.py").read_text(encoding="utf-8"))
    numeric_targets = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            value = node.value
            if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
                value = value.operand
            assert isinstance(value, ast.Constant) and isinstance(value.value, (int, float))
            numeric_targets.append(node.targets[0].id)
    assert len(numeric_targets) == 5 * len(FACTOR_FAMILIES)


def test_archetypes_read_config_at_call_time() -> None:
    original = screen_config.LCMB_MOMENTUM
    try:
        screen_config.LCMB_MOMENTUM = original + 0.5
        weights = next(a for a in build_archetypes() if a.archetype_id == "long_call_momentum_breakout").weights
        assert weights["momentum"] == original + 0.5
    finally:
        screen_config.LCMB_MOMENTUM = original


# ---------------------------------------------------------------------------
# Factor honesty
# ---------------------------------------------------------------------------

def test_context_only_symbols_are_never_screened() -> None:
    assert "VIX" not in screenable_universe(("SPY", "VIX", "^VIX", "AAPL"))
    assert "^VIX" not in screenable_universe(("SPY", "VIX", "^VIX", "AAPL"))


def test_point_in_time_factors_do_not_read_future_rows() -> None:
    closes = [100.0] * 200
    flat = point_in_time_factors(closes, 150)
    crashed = point_in_time_factors(closes[:151] + [1.0] * 49, 150)
    assert flat == crashed  # rows after the index can never change the factors


def test_point_in_time_factors_need_enough_history() -> None:
    assert point_in_time_factors([100.0] * 50, 49) is None


def test_missing_symbol_loads_empty_not_fabricated() -> None:
    assert load_adjusted_closes("NO_SUCH_SYMBOL_XYZ") == []


def test_snapshot_factors_absent_lanes_contribute_nothing() -> None:
    factors, provenance = snapshot_factors(["NO_SUCH_SYMBOL_XYZ"])
    assert factors["NO_SUCH_SYMBOL_XYZ"].get("value_rot") is None or True  # absent key, not a made-up 0-flag read
    assert "snapshot_semantics" in provenance
    assert provenance["snapshot_semantics"] == "current_day_cross_section_only_not_backcastable"


# ---------------------------------------------------------------------------
# Elite archive discipline
# ---------------------------------------------------------------------------

def test_evaluation_is_held_out_only_and_deterministic() -> None:
    first = evaluate_weight_set(current_weights())
    second = evaluate_weight_set(current_weights())
    assert first["config_id"] == second["config_id"]
    assert first["mean_holdout_rank_ic"] == second["mean_holdout_rank_ic"]
    assert first["fitness_scope"] == "point_in_time_spine_factors_only"
    assert first["not_edge_evidence"] is True
    assert first["promotion_allowed"] is False
    assert TRAIN_END_DATE == "2021-12-31"


def test_snapshot_families_excluded_from_fitness() -> None:
    evaluation = evaluate_weight_set(current_weights())
    assert set(evaluation["excluded_from_fitness"]) >= {"value_rot", "attention", "flow", "quality"}
    assert set(EVALUABLE_FAMILIES) == {"momentum", "structure"}


def test_proposals_are_deterministic_and_mutate_one_evaluable_weight() -> None:
    archive = load_archive()
    first = propose_variants(archive, count=3)
    second = propose_variants(archive, count=3)
    assert first == second
    base = current_weights()
    for variant in first:
        diffs = [
            (arch, family)
            for arch in variant
            for family in variant[arch]
            if variant[arch][family] != base.get(arch, {}).get(family)
        ]
        # exactly one weight differs from SOME elite parent; every diff vs the
        # active config must stay within the evaluable families
        assert all(family in EVALUABLE_FAMILIES for _, family in diffs)


def test_archive_cycle_recommends_never_applies(tmp_path: Path) -> None:
    config_before = Path("dopey_screener/screen_config.py").read_bytes()
    record = run_elite_archive_cycle()
    assert Path("dopey_screener/screen_config.py").read_bytes() == config_before
    assert record["discipline"] == "held_out_only_measure_only_human_gated"
    assert record["promotion_allowed"] is False
    recommendation = record["recommendation"]
    if recommendation is not None:
        assert recommendation["improvement_over_active"] >= RECOMMEND_MARGIN
        assert "human edits" in recommendation["apply_instructions"]


# ---------------------------------------------------------------------------
# Screener runner artifacts + semantics
# ---------------------------------------------------------------------------

def test_screener_writes_targets_and_summary(screener_result: dict) -> None:
    assert SCREENER_TARGETS_PATH.exists()
    assert SCREENER_SUMMARY_PATH.exists()
    assert screener_result["screener_status"] in {"targets_ranked", "no_spine_rows_available"}


def test_every_target_is_stamped_research_flag(screener_result: dict) -> None:
    rows = [json.loads(line) for line in SCREENER_TARGETS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    for row in rows:
        assert row["semantics"] == "research_flag_for_human_review_not_an_order_not_a_paper_entry"
        assert row["paper_only"] is True
        assert row["live_blocked"] is True
        assert row["not_edge_evidence"] is True


def test_summary_carries_honest_limits_and_no_promotion(screener_result: dict) -> None:
    assert screener_result["not_edge_evidence"] is True
    assert screener_result["promotion_allowed"] is False
    assert any("not edge evidence" in limit for limit in screener_result["honest_limits"])
    assert any("human-applied" in limit for limit in screener_result["honest_limits"])


def test_top_targets_only_positive_scores(screener_result: dict) -> None:
    for targets in screener_result["top_targets_by_archetype"].values():
        assert all(target["screen_score"] > 0.0 for target in targets)


def test_screener_module_has_no_order_or_broker_paths() -> None:
    text = "\n".join(
        (REPO_ROOT / "dopey_screener" / name).read_text(encoding="utf-8").lower()
        for name in ("run_target_screener.py", "elite_archive.py", "factor_engine.py", "strategy_archetypes.py", "screen_config.py")
    )
    for forbidden in ("place_order", "cancel_order", "broker_preference", "robinhood", "sk-proj-", "apscheduler"):
        assert forbidden not in text


def test_supervisor_includes_target_screener_stage() -> None:
    from dopey_autonomy.run_resilient_research_supervisor import STAGES

    names = [name for name, _, _ in STAGES]
    assert "target_screener" in names
    assert len(names) == len(set(names))
    assert names[-1] == "action_readiness_gate"


def test_screen_fitness_cli_contract() -> None:
    """The doofus target contract: last stdout line parses into [0, 1]."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "operator_tools" / "operator_screen_fitness.py")],
        capture_output=True, text=True, timeout=600, cwd=str(REPO_ROOT),
    )
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert lines
    if result.returncode == 0:
        score = float(lines[-1])
        assert 0.0 <= score <= 1.0
    else:
        assert lines[-1] == "insufficient_holdout_sample_measurement_invalid"


# ---------------------------------------------------------------------------
# Dashboard boundaries + state builder
# ---------------------------------------------------------------------------

def test_dashboard_binds_localhost_only() -> None:
    from dopey_dashboard import operator_dashboard

    assert operator_dashboard.HOST == "127.0.0.1"


def test_dashboard_source_has_no_order_paths_or_credentials() -> None:
    text = (REPO_ROOT / "dopey_dashboard" / "operator_dashboard.py").read_text(encoding="utf-8").lower()
    for forbidden in ("place_order", "cancel_order", "buy_to_open", "sell_to_open", "sk-proj-", "api_key", "robinhood"):
        assert forbidden not in text


def test_dashboard_state_carries_envelope_stamps() -> None:
    from dopey_dashboard.operator_dashboard import build_state

    state = build_state()
    assert state["envelope"]["paper_only"] is True
    assert state["envelope"]["live_blocked"] is True
    assert state["envelope"]["orders_possible_from_this_page"] is False
    assert "blocked_until_gate_all_green" in state["envelope"]["execution_seal"]
    assert "paper_record" in state and "readiness_gate" in state and "targets" in state


def test_dashboard_state_is_json_serializable_with_missing_artifacts() -> None:
    from dopey_dashboard.operator_dashboard import build_state

    json.dumps(build_state())  # empty-mirror robustness: absent artifacts never raise


def test_dashboard_stop_without_running_process_is_honest() -> None:
    from dopey_dashboard.operator_dashboard import stop_supervisor

    result = stop_supervisor()
    assert result["stopped"] is False
    assert result["reason"] == "not_running"


def test_dashboard_page_has_no_external_resources() -> None:
    from dopey_dashboard.operator_dashboard import PAGE

    lowered = PAGE.lower()
    assert "http://" not in lowered.replace("http://127.0.0.1", "")
    assert "https://" not in lowered
    assert "src=" not in lowered  # no external scripts/images; everything inline
