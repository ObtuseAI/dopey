"""Fail-closed validation for the frozen Ascendancy paper environment."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast

from .protected_manifest import file_sha256


REQUIRED_ENVIRONMENT_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "frozen",
        "mode",
        "authority",
        "permitted_underlying_universe",
        "trading_hours",
        "data_sources",
        "quote_granularity",
        "option_chain_coverage",
        "decision_timestamps",
        "maximum_permitted_latency",
        "allowed_option_structures",
        "commissions_and_fees",
        "spread_model",
        "slippage_model",
        "fill_model",
        "market_impact_assumptions",
        "dividend_treatment",
        "rates",
        "borrow_treatment",
        "exercise_rules",
        "assignment_rules",
        "settlement_type",
        "capital",
        "margin_model",
        "maximum_position_size",
        "maximum_portfolio_greek_exposure",
        "concentration_limits",
        "loss_limits",
        "allowed_holding_periods",
        "benchmark_policies",
        "temporal_partitions",
        "sealed_holdout_policy",
        "compute_budget",
        "candidate_expiration_policy",
        "liquidity_floors",
        "forward_evidence",
        "zero_dte",
        "assumption_status",
    }
)
EXPECTED_BASELINE_IDS = frozenset(
    {
        "no_trade",
        "underlying_only_risk_matched",
        "fixed_defined_risk_option",
        "delta_targeted_long_option",
        "fixed_vertical",
        "naive_immediate_paper_price",
        "naive_limit_paper_price",
        "fixed_fraction_allocation",
        "volatility_matched_allocation",
        "market_implied_distribution",
    }
)


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"environment field must be a mapping: field={field_name}")
    return cast(dict[str, object], value)


def _finite_fraction(value: object, field_name: str, allow_zero: bool) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"environment risk field must be numeric: field={field_name}")
    number = float(value)
    lower_bound_satisfied = number >= 0.0 if allow_zero else number > 0.0
    if not math.isfinite(number) or not lower_bound_satisfied or number > 1.0:
        raise ValueError(f"environment risk field is outside its fraction domain: field={field_name}")
    return number


def load_environment(environment_path: Path) -> dict[str, object]:
    decoded = json.loads(environment_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("environment must be a JSON mapping")
    environment = cast(dict[str, object], decoded)
    validate_environment(environment)
    return environment


def validate_environment(environment: dict[str, object]) -> None:
    missing = sorted(REQUIRED_ENVIRONMENT_FIELDS.difference(environment))
    if missing:
        raise ValueError(f"environment is incomplete: missing={missing}")
    if environment["schema_version"] != "dopey-options-environment-v1":
        raise ValueError("environment schema version is unsupported")
    if environment["environment_id"] != "dopey-options-paper-v1":
        raise ValueError("environment identity is unsupported")
    if environment["frozen"] is not True or environment["mode"] != "paper_research_only":
        raise ValueError("environment must be frozen in paper-research-only mode")

    authority = _mapping(environment["authority"], "authority")
    prohibited_authorities = (
        "real_capital_authority",
        "broker_credentials_allowed",
        "order_construction_allowed",
        "order_transmission_allowed",
    )
    if any(authority.get(field) is not False for field in prohibited_authorities):
        raise ValueError("environment grants prohibited brokerage or real-capital authority")
    if authority.get("maximum_autonomous_evidence_level") != "L5":
        raise ValueError("environment autonomous ceiling must remain L5 paper shadow")

    universe = _mapping(environment["permitted_underlying_universe"], "permitted_underlying_universe")
    if universe.get("maximum_symbols") != 200:
        raise ValueError("Ascendancy v1 requires the frozen 200-symbol starting universe")
    coverage = _mapping(environment["option_chain_coverage"], "option_chain_coverage")
    observed_symbols = coverage.get("available_unique_symbols")
    if not isinstance(observed_symbols, int) or isinstance(observed_symbols, bool):
        raise ValueError("option coverage symbol count must be an integer")
    if observed_symbols < 0 or observed_symbols > 200:
        raise ValueError("option coverage exceeds the frozen universe")

    structures = environment["allowed_option_structures"]
    if not isinstance(structures, list) or not structures:
        raise ValueError("environment requires an explicit non-empty structure allowlist")
    prohibited_fragments = ("naked", "undefined", "ratio", "uncovered")
    if any(
        not isinstance(structure, str)
        or any(fragment in structure.lower() for fragment in prohibited_fragments)
        for structure in structures
    ):
        raise ValueError("environment structure allowlist contains an uncapped-loss form")

    sealed = _mapping(environment["sealed_holdout_policy"], "sealed_holdout_policy")
    if (
        sealed.get("raw_observation_access") is not False
        or sealed.get("aggregate_feedback_only") is not True
        or sealed.get("maximum_submissions_per_frozen_candidate") != 1
    ):
        raise ValueError("environment sealed holdout must be aggregate-only and one-shot")
    zero_dte = _mapping(environment["zero_dte"], "zero_dte")
    if zero_dte.get("enabled") is not False or zero_dte.get("daily_bar_evidence_allowed") is not False:
        raise ValueError("zero-DTE must remain disabled in environment v1")

    loss_limits = _mapping(environment["loss_limits"], "loss_limits")
    for field_name in (
        "maximum_daily_loss_fraction",
        "maximum_drawdown_fraction",
        "maximum_expected_shortfall_fraction",
        "maximum_probability_of_ruin",
    ):
        _finite_fraction(loss_limits.get(field_name), f"loss_limits.{field_name}", allow_zero=False)
    position = _mapping(environment["maximum_position_size"], "maximum_position_size")
    _finite_fraction(
        position.get("maximum_loss_fraction_of_paper_bankroll"),
        "maximum_position_size.maximum_loss_fraction_of_paper_bankroll",
        allow_zero=False,
    )
    _finite_fraction(
        position.get("maximum_margin_fraction_of_paper_bankroll"),
        "maximum_position_size.maximum_margin_fraction_of_paper_bankroll",
        allow_zero=False,
    )
    benchmarks = environment["benchmark_policies"]
    if not isinstance(benchmarks, list) or frozenset(benchmarks) != EXPECTED_BASELINE_IDS:
        raise ValueError("environment baseline vocabulary differs from the canonical v1 IDs")


def verify_environment_freeze(environment_path: Path, freeze_path: Path) -> None:
    environment = load_environment(environment_path)
    decoded = json.loads(freeze_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("environment freeze must be a JSON mapping")
    freeze = cast(dict[str, object], decoded)
    declared_path = Path(str(freeze.get("environment_file")))
    resolved_declared_path = (
        declared_path.resolve(strict=True)
        if declared_path.is_absolute()
        else (freeze_path.parent / declared_path).resolve(strict=True)
    )
    if resolved_declared_path != environment_path.resolve(strict=True):
        raise ValueError("environment freeze points to a different environment file")
    if freeze.get("environment_id") != environment["environment_id"]:
        raise ValueError("environment freeze identity mismatch")
    if freeze.get("file_sha256") != file_sha256(environment_path):
        raise ValueError("environment freeze content hash mismatch")
    if freeze.get("mutation_policy") != "new_version_required":
        raise ValueError("environment freeze mutation policy is not fail-closed")
    if freeze.get("paper_only") is not True or freeze.get("live_blocked") is not True:
        raise ValueError("environment freeze weakened the paper-only boundary")
