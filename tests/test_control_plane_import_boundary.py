"""Structural guard: research/evolvable surfaces may not reach the control plane.

DOPEY's constitution whitelists what the external evolver and research code may
touch: NEVER the truth layer, readiness/release gates, sizing/portfolio policy,
sentinels, or the live-execution package. Until now that boundary was enforced
by hand-curation plus the runtime envelope sentinel. This makes it a build-time
structural invariant, the way evo-trader (r/algotrading) fails its build if a
strategy file imports the risk-limits module directly: an AST scan of the
research surfaces that fails if any imports a control-plane module AT IMPORT
TIME. Lazy imports inside function bodies remain the deliberate escape hatch
(a research stage runner may pull an engine lazily); it is IMPORT-TIME reach
into the control plane - the thing that makes tampering structurally easy -
that is forbidden.

This is "code literally cannot reach it at import time," complementing the
process-level isolation the external evolver already provides (it perturbs
source files from its own process/venv, with no shared in-memory reference).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Pure research + doofus-perturbed evolvable surfaces. These generate signals
# and thresholds; they must never depend on how outcomes are judged or sized.
RESEARCH_SURFACE_MODULES = (
    "dopey_backtest/exit_policy_config.py",
    "dopey_screener/screen_config.py",
    "dopey/strategy_engineering/scanner_evolvable_config.py",
    "dopey/strategy_engineering/playbook.py",
    "dopey/strategy_engineering/playbook_scanner.py",
    "dopey/strategy_engineering/scanner_holdout_fitness.py",
    "dopey/strategy_engineering/compression_expansion_study.py",
    "dopey/strategy_engineering/swing_target_discovery.py",
    "dopey/strategy_engineering/option_roi_discovery.py",
    "dopey/strategy_engineering/cross_lane_convergence.py",
    "dopey/strategy_engineering/trade_memory.py",
    "dopey/strategy_engineering/option_expression_cost.py",
    "dopey/strategy_engineering/situational_scorecard.py",
    "dopey/strategy_engineering/self_scout.py",
    "dopey/strategy_engineering/pre_snap_read.py",
    "dopey/strategy_engineering/expression_selector.py",
    "dopey/strategy_engineering/post_snap_read.py",
    "dopey/strategy_engineering/reclamation_bench.py",
    "dopey_backtest/veto_shadow.py",
    "dopey_ops/pipeline_forecast_card.py",
    "dopey_ops/kaizen_ledger.py",
    "dopey_ops/reliability_slo.py",
)

# The control plane: judging edge, gating readiness/release, sizing, sentinels,
# and live execution. A research surface importing any of these at import time
# is a boundary violation.
FORBIDDEN_CONTROL_MODULES = (
    "dopey_broker_readiness.action_readiness_gate",
    "dopey_validation.live_pivot_release_gate",
    "dopey_risk_engine.forward_portfolio_policy",
    "dopey_risk_engine.forward_entry_guard",
    "dopey_stats.run_statistical_truth_layer",
    "dopey_fitness.truth_gated_fitness_engine",
    "dopey_audit.envelope_integrity_sentinel",
    "dopey_data_ingestion.data_freshness_sentinel",
    "dopey_live",  # the whole live-execution package
)


def _import_time_imports(tree: ast.Module) -> list[ast.stmt]:
    """Import/ImportFrom reachable at import time - NOT inside function bodies.

    Descends into module-level if/try/with/for so a guarded top-level import is
    still caught, but never into a def/async def/lambda (lazy imports there are
    the sanctioned escape hatch).
    """
    found: list[ast.stmt] = []

    def visit(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                found.append(node)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                visit(node.body)
                visit(getattr(node, "orelse", []))
                visit(getattr(node, "finalbody", []))
                for handler in getattr(node, "handlers", []):
                    visit(handler.body)
            # def / async def / class bodies are intentionally NOT descended

    visit(tree.body)
    return found


def _imported_modules(stmt: ast.stmt) -> list[str]:
    if isinstance(stmt, ast.ImportFrom):
        if stmt.level:  # relative import stays inside the research package
            return []
        return [stmt.module] if stmt.module else []
    if isinstance(stmt, ast.Import):
        return [alias.name for alias in stmt.names]
    return []


def _violates(module: str) -> str | None:
    for forbidden in FORBIDDEN_CONTROL_MODULES:
        if module == forbidden or module.startswith(forbidden + "."):
            return forbidden
    return None


def test_research_surfaces_exist() -> None:
    missing = [rel for rel in RESEARCH_SURFACE_MODULES if not (REPO_ROOT / rel).is_file()]
    assert not missing, f"guarded research modules are missing (rename?): {missing}"


def test_research_surfaces_do_not_import_control_plane() -> None:
    violations: list[str] = []
    for rel in RESEARCH_SURFACE_MODULES:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for stmt in _import_time_imports(tree):
            for module in _imported_modules(stmt):
                forbidden = _violates(module)
                if forbidden is not None:
                    violations.append(f"{rel}:{stmt.lineno} imports control-plane module {module!r} (matches {forbidden!r})")
    assert not violations, (
        "research/evolvable surfaces must not reach the control plane at import "
        "time (lazy imports inside functions are allowed):\n  " + "\n  ".join(violations)
    )


def test_evolvable_config_modules_are_pure_constants() -> None:
    # The doofus-perturbed surfaces must import NOTHING at module level except,
    # at most, their own sibling config assembler - a stray import is where a
    # control-plane dependency would first creep in.
    evolvable = (
        "dopey_backtest/exit_policy_config.py",
        "dopey_screener/screen_config.py",
        "dopey/strategy_engineering/scanner_evolvable_config.py",
    )
    offenders: list[str] = []
    for rel in evolvable:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for stmt in _import_time_imports(tree):
            for module in _imported_modules(stmt):
                offenders.append(f"{rel} imports {module}")
    assert not offenders, (
        "doofus-perturbed evolvable configs must stay pure numeric constants "
        "with no import-time dependencies:\n  " + "\n  ".join(offenders)
    )


def test_guard_detects_a_planted_violation() -> None:
    # Prove the AST check would actually fire: a synthetic module that imports
    # the readiness gate at top level must be flagged.
    planted = ast.parse(
        "from dopey_broker_readiness.action_readiness_gate import run_action_readiness_gate\n"
        "X = 1\n"
    )
    hits = [
        module
        for stmt in _import_time_imports(planted)
        for module in _imported_modules(stmt)
        if _violates(module)
    ]
    assert hits == ["dopey_broker_readiness.action_readiness_gate"]


def test_lazy_import_inside_function_is_allowed() -> None:
    # A control-plane import INSIDE a function body must NOT be flagged - that
    # is the sanctioned escape hatch for stage runners.
    lazy = ast.parse(
        "def run():\n"
        "    from dopey_live.service import run_live_branch_cycle\n"
        "    return run_live_branch_cycle\n"
    )
    hits = [
        module
        for stmt in _import_time_imports(lazy)
        for module in _imported_modules(stmt)
        if _violates(module)
    ]
    assert hits == []
