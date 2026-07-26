"""Separated visible, private, and external strategy evaluation partitions."""

from __future__ import annotations

from .schema import EvaluationTask


def build_evaluation_task_suite() -> tuple[EvaluationTask, ...]:
    visible: EvaluationTask = {
        "partition": "VISIBLE_DEVELOPMENT",
        "purpose": "debug candidate behavior on disclosed historical tasks",
        "item_level_feedback_visible": True,
        "selection_authority": False,
        "required_checks": ("determinism", "schema", "leakage_audit", "random_entry", "circular_shift"),
    }
    private: EvaluationTask = {
        "partition": "PRIVATE_SELECTION",
        "purpose": "select mutations on hidden dates, symbols, regimes, sectors, and traps",
        "item_level_feedback_visible": False,
        "selection_authority": True,
        "required_checks": (
            "future_data_trap",
            "revised_fundamental_trap",
            "duplicate_family_trap",
            "survivorship_trap",
            "easy_symbol_trap",
            "over_abstention_trap",
            "simulation_as_truth_trap",
            "cluster_independence_trap",
            "market_drift_trap",
            "complexity_camouflage_trap",
        ),
    }
    external: EvaluationTask = {
        "partition": "EXTERNAL_GENERALIZATION",
        "purpose": "confirm transfer on untouched and later forward-paper evidence",
        "item_level_feedback_visible": False,
        "selection_authority": False,
        "required_checks": ("cross_symbol_transfer", "cross_era_transfer", "new_regime", "forward_settlement"),
    }
    return visible, private, external
