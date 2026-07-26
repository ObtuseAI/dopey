"""Immutable Dummy opportunity contracts and frozen candidate genomes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Literal, Mapping, cast

from dopey.constitution.execution_seal import assert_no_forbidden_nested_payload

from .baselines import BASELINE_IDS
from .identity import (
    JsonValue,
    canonical_hash,
    canonical_json,
    parse_utc,
    require_sha256,
    require_utc_iso,
)
from .policy_ids import V1_REQUIRED_NEGATIVE_CONTROL_IDS
from .stress import v1_required_stress_requirements


PROHIBITED_DISCRETIONARY_PHRASES = (
    "use judgment",
    "when conditions look good",
    "if appropriate",
    "when sentiment changes",
    "based on market feel",
)

REQUIRED_CANDIDATE_SECTIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "dummy_input_contract": frozenset(
            {
                "opportunity_id",
                "creation_timestamp",
                "underlying",
                "forecast",
                "intended_horizon",
                "confidence",
                "maximum_exposure_fraction",
                "expiration_timestamp",
                "upstream_version",
                "provenance_hash",
                "synthetic",
                "contract_hash",
            }
        ),
        "market_state": frozenset(
            {
                "available_features",
                "timestamp_rules",
                "liquidity_state",
                "volatility_state",
            }
        ),
        "instrument_choice": frozenset(
            {"use_options", "underlying_alternative", "reason"}
        ),
        "structure": frozenset(
            {"type", "legs", "maximum_loss", "assignment_profile", "exercise_profile"}
        ),
        "entry": frozenset(
            {
                "earliest_time",
                "latest_time",
                "limit_price_rule",
                "cancellation_rule",
                "venue_rule",
                "legging_rule",
                "fill_model_version",
            }
        ),
        "sizing": frozenset(
            {
                "method",
                "uncertainty_haircut",
                "maximum_position_fraction",
                "maximum_portfolio_contribution",
                "margin_limit",
            }
        ),
        "management": frozenset(
            {
                "monitor_frequency",
                "hold_rule",
                "trim_rule",
                "hedge_rule",
                "roll_rule",
                "exit_rule",
                "expiration_rule",
            }
        ),
        "risk": frozenset(
            {
                "delta_limit",
                "gamma_limit",
                "theta_limit",
                "vega_limit",
                "vanna_limit",
                "charm_limit",
                "vomma_limit",
                "skew_limit",
                "correlation_limit",
                "event_limit",
                "liquidity_limit",
                "gap_limit",
                "tail_limit",
                "concentration_limit",
                "drawdown_limit",
                "expected_shortfall_limit",
                "ruin_probability_limit",
                "kill_conditions",
            }
        ),
        "economics": frozenset(
            {
                "commission_model",
                "spread_model",
                "slippage_model",
                "impact_model",
                "funding_model",
                "borrow_model",
            }
        ),
        "evaluation": frozenset(
            {
                "benchmarks",
                "primary_metrics",
                "secondary_metrics",
                "negative_controls",
                "stress_tests",
            }
        ),
        "reproducibility": frozenset(
            {
                "data_snapshot_hash",
                "code_commit",
                "environment_hash",
                "evaluator_version",
                "random_seeds",
            }
        ),
    }
)
MAPPING_PROXY_TYPE = type(MappingProxyType({}))
V1_ENVIRONMENT_HASH = "811d348d94e151087cd77d496bd1f5135b24dd40ba107b5d860cde34b8475652"
MARKET_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")


@dataclass(frozen=True, slots=True)
class DummyOpportunity:
    opportunity_id: str
    creation_timestamp: str
    underlying: str
    forecast: str
    intended_horizon: str
    confidence: float
    maximum_exposure_fraction: float
    expiration_timestamp: str
    upstream_version: str
    provenance_hash: str
    synthetic: bool
    contract_hash: str


@dataclass(frozen=True, slots=True)
class CandidateGenome:
    candidate_id: str
    parent_ids: tuple[str, ...]
    research_family: str
    hypothesis: str
    falsification_condition: str
    candidate_mode: Literal["options_expression", "abstention_policy"]
    specification: Mapping[str, JsonValue]
    paper_only: bool
    live_blocked: bool
    genome_hash: str


def _deep_freeze(value: JsonValue) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return cast(JsonValue, value)


def _is_deeply_frozen(value: object) -> bool:
    if isinstance(value, MAPPING_PROXY_TYPE):
        return all(_is_deeply_frozen(item) for item in value.values())
    if isinstance(value, tuple):
        return all(_is_deeply_frozen(item) for item in value)
    return not isinstance(value, (dict, list, set))


def _validate_finite_json(value: object, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            f"candidate specification contains non-finite number: path={path}"
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_finite_json(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_finite_json(item, f"{path}[{index}]")


def create_candidate_genome(
    candidate_id: str,
    parent_ids: tuple[str, ...],
    research_family: str,
    hypothesis: str,
    falsification_condition: str,
    candidate_mode: Literal["options_expression", "abstention_policy"],
    specification: dict[str, JsonValue],
) -> CandidateGenome:
    if candidate_mode not in {"options_expression", "abstention_policy"}:
        raise ValueError("candidate genome has an unsupported candidate_mode")
    identity_fields = {
        "candidate_id": candidate_id,
        "research_family": research_family,
        "hypothesis": hypothesis,
        "falsification_condition": falsification_condition,
    }
    if any(
        not isinstance(value, str) or not value.strip()
        for value in identity_fields.values()
    ):
        raise ValueError("candidate genome identity fields must be non-empty strings")
    if (
        not isinstance(parent_ids, tuple)
        or any(
            not isinstance(parent_id, str) or not parent_id.strip()
            for parent_id in parent_ids
        )
        or len(parent_ids) != len(set(parent_ids))
    ):
        raise ValueError("candidate parent_ids must be unique non-empty strings")
    if not isinstance(specification, dict):
        raise ValueError("candidate specification must be a mapping")
    assert_no_forbidden_nested_payload(specification, "candidate.specification")
    _validate_finite_json(specification, "specification")
    body: dict[str, JsonValue] = {
        "candidate_id": candidate_id,
        "parent_ids": list(parent_ids),
        "research_family": research_family,
        "hypothesis": hypothesis,
        "falsification_condition": falsification_condition,
        "candidate_mode": candidate_mode,
        "specification": specification,
        "paper_only": True,
        "live_blocked": True,
    }
    frozen = cast(Mapping[str, JsonValue], _deep_freeze(specification))
    candidate = CandidateGenome(
        candidate_id=candidate_id,
        parent_ids=parent_ids,
        research_family=research_family,
        hypothesis=hypothesis,
        falsification_condition=falsification_condition,
        candidate_mode=candidate_mode,
        specification=frozen,
        paper_only=True,
        live_blocked=True,
        genome_hash=canonical_hash(body),
    )
    validate_candidate_genome(candidate)
    return candidate


def create_dummy_opportunity(
    creation_timestamp: str,
    underlying: str,
    forecast: str,
    intended_horizon: str,
    confidence: float,
    maximum_exposure_fraction: float,
    expiration_timestamp: str,
    upstream_version: str,
    provenance_hash: str,
    synthetic: bool,
) -> DummyOpportunity:
    normalized_confidence = _require_probability(
        confidence, "confidence", allow_zero=True
    )
    normalized_exposure = _require_probability(
        maximum_exposure_fraction,
        "maximum_exposure_fraction",
        allow_zero=False,
    )
    body: dict[str, JsonValue] = {
        "creation_timestamp": creation_timestamp,
        "underlying": underlying,
        "forecast": forecast,
        "intended_horizon": intended_horizon,
        "confidence": normalized_confidence,
        "maximum_exposure_fraction": normalized_exposure,
        "expiration_timestamp": expiration_timestamp,
        "upstream_version": upstream_version,
        "provenance_hash": provenance_hash,
        "synthetic": synthetic,
    }
    contract_hash = canonical_hash(body)
    opportunity = DummyOpportunity(
        opportunity_id=f"dummy-{contract_hash[:24]}",
        creation_timestamp=creation_timestamp,
        underlying=underlying,
        forecast=forecast,
        intended_horizon=intended_horizon,
        confidence=normalized_confidence,
        maximum_exposure_fraction=normalized_exposure,
        expiration_timestamp=expiration_timestamp,
        upstream_version=upstream_version,
        provenance_hash=provenance_hash,
        synthetic=synthetic,
        contract_hash=contract_hash,
    )
    validate_dummy_opportunity(opportunity)
    return opportunity


def _require_probability(value: float, field_name: str, allow_zero: bool) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"Dummy opportunity probability field must be numeric: field={field_name}"
        )
    normalized = float(value)
    lower_bound_satisfied = normalized >= 0.0 if allow_zero else normalized > 0.0
    if not math.isfinite(normalized) or not lower_bound_satisfied or normalized > 1.0:
        lower_bound = "[0, 1]" if allow_zero else "(0, 1]"
        raise ValueError(
            f"Dummy opportunity field must be within {lower_bound}: "
            f"field={field_name}, value={value}"
        )
    return normalized


def _dummy_opportunity_body(opportunity: DummyOpportunity) -> dict[str, JsonValue]:
    return {
        "creation_timestamp": opportunity.creation_timestamp,
        "underlying": opportunity.underlying,
        "forecast": opportunity.forecast,
        "intended_horizon": opportunity.intended_horizon,
        "confidence": opportunity.confidence,
        "maximum_exposure_fraction": opportunity.maximum_exposure_fraction,
        "expiration_timestamp": opportunity.expiration_timestamp,
        "upstream_version": opportunity.upstream_version,
        "provenance_hash": opportunity.provenance_hash,
        "synthetic": opportunity.synthetic,
    }


def require_market_symbol(value: str, field_name: str) -> str:
    if not isinstance(value, str) or MARKET_SYMBOL_PATTERN.fullmatch(value) is None:
        raise ValueError(
            "market symbol must match ^[A-Z][A-Z0-9.-]{0,14}$: "
            f"field={field_name}, value={value!r}"
        )
    return value


def validate_dummy_opportunity(opportunity: DummyOpportunity) -> None:
    require_utc_iso(opportunity.creation_timestamp)
    require_utc_iso(opportunity.expiration_timestamp)
    if parse_utc(opportunity.expiration_timestamp) <= parse_utc(
        opportunity.creation_timestamp
    ):
        raise ValueError("Dummy opportunity expiration must follow its creation time")
    if not all(
        (
            opportunity.underlying,
            opportunity.forecast,
            opportunity.intended_horizon,
            opportunity.upstream_version,
        )
    ):
        raise ValueError(
            "Dummy opportunity requires non-empty semantic identity fields"
        )
    require_market_symbol(opportunity.underlying, "underlying")
    _require_probability(opportunity.confidence, "confidence", allow_zero=True)
    _require_probability(
        opportunity.maximum_exposure_fraction,
        "maximum_exposure_fraction",
        allow_zero=False,
    )
    require_sha256(opportunity.provenance_hash, "provenance_hash")
    if not isinstance(opportunity.synthetic, bool):
        raise ValueError("Dummy opportunity synthetic flag must be boolean")
    expected_hash = canonical_hash(_dummy_opportunity_body(opportunity))
    require_sha256(opportunity.contract_hash, "contract_hash")
    if opportunity.contract_hash != expected_hash:
        raise ValueError(
            "Dummy opportunity contract hash does not match its immutable content"
        )
    if opportunity.opportunity_id != f"dummy-{expected_hash[:24]}":
        raise ValueError("Dummy opportunity ID does not match its immutable content")


def _collect_text(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(text for item in value for text in _collect_text(item))
    if isinstance(value, Mapping):
        return tuple(text for item in value.values() for text in _collect_text(item))
    return ()


def validate_candidate_genome(candidate: CandidateGenome) -> None:
    if candidate.paper_only is not True or candidate.live_blocked is not True:
        raise ValueError(
            "candidate genome must remain paper_only=true and live_blocked=true"
        )
    identity_fields = (
        candidate.candidate_id,
        candidate.research_family,
        candidate.hypothesis,
        candidate.falsification_condition,
    )
    if any(
        not isinstance(value, str) or not value.strip() for value in identity_fields
    ):
        raise ValueError("candidate genome identity fields must be non-empty strings")
    if (
        not isinstance(candidate.parent_ids, tuple)
        or any(
            not isinstance(parent_id, str) or not parent_id.strip()
            for parent_id in candidate.parent_ids
        )
        or len(candidate.parent_ids) != len(set(candidate.parent_ids))
    ):
        raise ValueError("candidate parent_ids must be unique non-empty strings")
    if candidate.candidate_mode not in {"options_expression", "abstention_policy"}:
        raise ValueError("candidate genome has an unsupported candidate_mode")
    if not _is_deeply_frozen(candidate.specification):
        raise ValueError("candidate specification must be deeply immutable")
    specification_value = _deep_thaw(candidate.specification)
    if not isinstance(specification_value, dict):
        raise ValueError("candidate specification must be a deeply immutable mapping")
    specification = specification_value
    assert_no_forbidden_nested_payload(specification, "candidate.specification")
    _validate_finite_json(specification, "specification")
    if set(specification) != set(REQUIRED_CANDIDATE_SECTIONS):
        raise ValueError(
            "candidate specification sections differ from the exact schema"
        )
    for section, required_fields in REQUIRED_CANDIDATE_SECTIONS.items():
        value = specification.get(section)
        if not isinstance(value, dict):
            raise ValueError(f"candidate section must be a mapping: section={section}")
        missing = sorted(required_fields.difference(value))
        if missing:
            raise ValueError(
                f"candidate section is incomplete: section={section}, missing={missing}"
            )
        extras = sorted(set(value).difference(required_fields))
        if extras:
            raise ValueError(
                f"candidate section contains unsupported fields: section={section}, extras={extras}"
            )
    dummy_contract = specification["dummy_input_contract"]
    assert isinstance(dummy_contract, dict)
    _validate_embedded_dummy_contract(dummy_contract)
    structure = specification["structure"]
    assert isinstance(structure, dict)
    legs_value = structure["legs"]
    if not isinstance(legs_value, list) or not all(
        isinstance(leg, dict) for leg in legs_value
    ):
        raise ValueError("candidate structure legs must be a list of mappings")
    maximum_loss = structure["maximum_loss"]
    if not isinstance(maximum_loss, (int, float)) or isinstance(maximum_loss, bool):
        raise ValueError("candidate maximum_loss must be numeric")
    if candidate.candidate_mode == "options_expression":
        validate_exact_defined_risk_topology(
            str(structure["type"]),
            [dict(leg) for leg in legs_value],
        )
        if any(leg["underlying"] != dummy_contract["underlying"] for leg in legs_value):
            raise ValueError(
                "candidate option leg underlying must match the frozen Dummy opportunity"
            )
        contract_ids = [str(leg["contract_id"]) for leg in legs_value]
        if len(contract_ids) != len(set(contract_ids)):
            raise ValueError("candidate option leg contract IDs must be unique")
        if float(maximum_loss) <= 0.0:
            raise ValueError(
                "options candidate maximum_loss must be a positive finite amount"
            )
    elif (
        structure["type"] != "no_position"
        or legs_value
        or float(maximum_loss) != 0.0
        or structure["assignment_profile"] != "no_assignment"
        or structure["exercise_profile"] != "no_exercise"
    ):
        raise ValueError(
            "abstention candidate must encode the exact no-position topology"
        )
    _validate_candidate_semantics(
        specification,
        dummy_contract,
        legs_value,
        candidate.candidate_mode,
    )
    use_options = specification["instrument_choice"]["use_options"]
    expected_use_options = candidate.candidate_mode == "options_expression"
    if use_options is not expected_use_options:
        raise ValueError("candidate_mode disagrees with instrument_choice.use_options")
    found = [
        phrase
        for text in _collect_text(specification)
        for phrase in PROHIBITED_DISCRETIONARY_PHRASES
        if phrase in text.lower()
    ]
    if found:
        raise ValueError(
            f"candidate contains undefined discretion: phrases={sorted(set(found))}"
        )
    expected_hash = canonical_hash(
        {
            "candidate_id": candidate.candidate_id,
            "parent_ids": list(candidate.parent_ids),
            "research_family": candidate.research_family,
            "hypothesis": candidate.hypothesis,
            "falsification_condition": candidate.falsification_condition,
            "candidate_mode": candidate.candidate_mode,
            "specification": specification,
            "paper_only": candidate.paper_only,
            "live_blocked": candidate.live_blocked,
        }
    )
    if candidate.genome_hash != expected_hash:
        raise ValueError(
            "candidate genome hash mismatch: "
            f"candidate_id={candidate.candidate_id}, expected={expected_hash}, observed={candidate.genome_hash}"
        )


def candidate_genome_canonical_snapshot(candidate: CandidateGenome) -> str:
    validate_candidate_genome(candidate)
    specification = _deep_thaw(candidate.specification)
    if not isinstance(specification, dict):
        raise ValueError("candidate specification snapshot must be a mapping")
    return canonical_json(
        {
            "candidate_id": candidate.candidate_id,
            "parent_ids": list(candidate.parent_ids),
            "research_family": candidate.research_family,
            "hypothesis": candidate.hypothesis,
            "falsification_condition": candidate.falsification_condition,
            "candidate_mode": candidate.candidate_mode,
            "specification": specification,
            "paper_only": candidate.paper_only,
            "live_blocked": candidate.live_blocked,
        }
    )


def candidate_genome_to_mapping(candidate: CandidateGenome) -> dict[str, JsonValue]:
    validate_candidate_genome(candidate)
    specification = _deep_thaw(candidate.specification)
    if not isinstance(specification, dict):
        raise ValueError("candidate specification snapshot must be a mapping")
    return {
        "candidate_id": candidate.candidate_id,
        "parent_ids": list(candidate.parent_ids),
        "research_family": candidate.research_family,
        "hypothesis": candidate.hypothesis,
        "falsification_condition": candidate.falsification_condition,
        "candidate_mode": candidate.candidate_mode,
        "specification": specification,
        "paper_only": candidate.paper_only,
        "live_blocked": candidate.live_blocked,
        "genome_hash": candidate.genome_hash,
    }


def candidate_genome_from_mapping(value: Mapping[str, object]) -> CandidateGenome:
    expected_fields = {
        "candidate_id",
        "parent_ids",
        "research_family",
        "hypothesis",
        "falsification_condition",
        "candidate_mode",
        "specification",
        "paper_only",
        "live_blocked",
        "genome_hash",
    }
    if set(value) != expected_fields:
        raise ValueError(
            "candidate genome mapping differs from the exact canonical schema"
        )
    candidate_id = value["candidate_id"]
    parent_ids = value["parent_ids"]
    research_family = value["research_family"]
    hypothesis = value["hypothesis"]
    falsification_condition = value["falsification_condition"]
    candidate_mode = value["candidate_mode"]
    specification = value["specification"]
    genome_hash = value["genome_hash"]
    if (
        not isinstance(candidate_id, str)
        or not isinstance(parent_ids, list)
        or any(not isinstance(parent_id, str) for parent_id in parent_ids)
        or not isinstance(research_family, str)
        or not isinstance(hypothesis, str)
        or not isinstance(falsification_condition, str)
        or candidate_mode not in {"options_expression", "abstention_policy"}
        or not isinstance(specification, dict)
        or value["paper_only"] is not True
        or value["live_blocked"] is not True
        or not isinstance(genome_hash, str)
    ):
        raise ValueError(
            "candidate genome mapping contains malformed identity or authority fields"
        )
    candidate = create_candidate_genome(
        candidate_id,
        tuple(parent_ids),
        research_family,
        hypothesis,
        falsification_condition,
        cast(Literal["options_expression", "abstention_policy"], candidate_mode),
        cast(dict[str, JsonValue], specification),
    )
    require_sha256(genome_hash, "candidate.genome_hash")
    if candidate.genome_hash != genome_hash:
        raise ValueError(
            "candidate genome mapping hash does not match its validated content"
        )
    return candidate


def _validate_leg_identity(leg: Mapping[str, JsonValue]) -> None:
    required = {
        "contract_id",
        "side",
        "underlying",
        "option_type",
        "expiry",
        "strike",
        "quantity",
        "multiplier",
        "deliverable",
        "option_style",
        "settlement_type",
    }
    missing = sorted(required.difference(leg))
    if missing:
        raise ValueError(f"option leg identity is incomplete: missing={missing}")
    extras = sorted(set(leg).difference(required))
    if extras:
        raise ValueError(
            f"option leg identity contains unsupported fields: extras={extras}"
        )
    if leg["side"] not in {"buy", "sell"}:
        raise ValueError(f"unsupported option leg side: side={leg['side']!r}")
    if leg["option_type"] not in {"call", "put"}:
        raise ValueError(f"unsupported option type: option_type={leg['option_type']!r}")
    if not isinstance(leg["contract_id"], str) or not leg["contract_id"]:
        raise ValueError("option contract_id must be a non-empty string")
    if not isinstance(leg["underlying"], str) or not leg["underlying"]:
        raise ValueError("option underlying must be a non-empty string")
    require_market_symbol(str(leg["underlying"]), "structure.legs[].underlying")
    if not isinstance(leg["deliverable"], str) or not leg["deliverable"]:
        raise ValueError("option deliverable must be a non-empty string")
    if leg["option_style"] not in {"american", "european"}:
        raise ValueError(
            f"unsupported option style: option_style={leg['option_style']!r}"
        )
    if leg["settlement_type"] not in {"physical", "cash"}:
        raise ValueError(
            f"unsupported option settlement type: settlement_type={leg['settlement_type']!r}"
        )
    if not isinstance(leg["expiry"], str) or not leg["expiry"]:
        raise ValueError("option expiry must be a non-empty string")
    try:
        date.fromisoformat(leg["expiry"])
    except ValueError as error:
        raise ValueError(
            f"option expiry must be an ISO date: expiry={leg['expiry']!r}"
        ) from error
    if (
        not isinstance(leg["quantity"], int)
        or isinstance(leg["quantity"], bool)
        or leg["quantity"] <= 0
    ):
        raise ValueError("option quantity must be a positive integer")
    if (
        not isinstance(leg["multiplier"], int)
        or isinstance(leg["multiplier"], bool)
        or leg["multiplier"] <= 0
    ):
        raise ValueError("option multiplier must be a positive integer")
    if (
        not isinstance(leg["strike"], (int, float))
        or isinstance(leg["strike"], bool)
        or leg["strike"] <= 0
    ):
        raise ValueError("option strike must be positive")


def _leg_signature(leg: Mapping[str, JsonValue]) -> tuple[object, ...]:
    return (
        leg["underlying"],
        leg["option_type"],
        leg["expiry"],
        leg["multiplier"],
        leg["deliverable"],
        leg["option_style"],
        leg["settlement_type"],
    )


def validate_exact_defined_risk_topology(
    structure_type: str,
    legs: list[dict[str, JsonValue]],
) -> None:
    if not legs:
        raise ValueError("candidate requires at least one option leg")
    for leg in legs:
        _validate_leg_identity(leg)
    short_legs = [leg for leg in legs if leg["side"] == "sell"]
    long_legs = [leg for leg in legs if leg["side"] == "buy"]
    long_only_types = {"long_call", "long_put", "long_straddle", "long_strangle"}
    vertical_rules: Mapping[str, tuple[str, str, str]] = {
        "bull_call_debit_spread": ("call", "long_lower", "short_higher"),
        "bear_call_credit_spread": ("call", "short_lower", "long_higher"),
        "bear_put_debit_spread": ("put", "short_lower", "long_higher"),
        "bull_put_credit_spread": ("put", "long_lower", "short_higher"),
    }
    if not short_legs:
        if structure_type not in long_only_types:
            raise ValueError(
                f"unsupported long-only structure type: structure_type={structure_type!r}"
            )
        expected_counts = {
            "long_call": (1, {"call"}),
            "long_put": (1, {"put"}),
            "long_straddle": (2, {"call", "put"}),
            "long_strangle": (2, {"call", "put"}),
        }
        expected_count, expected_types = expected_counts[structure_type]
        observed_types = {str(leg["option_type"]) for leg in long_legs}
        if len(long_legs) != expected_count or observed_types != expected_types:
            raise ValueError(
                "long-only leg topology does not match declared structure: "
                f"structure_type={structure_type}"
            )
        signatures = {
            (
                leg["underlying"],
                leg["expiry"],
                leg["multiplier"],
                leg["quantity"],
                leg["deliverable"],
                leg["option_style"],
                leg["settlement_type"],
            )
            for leg in long_legs
        }
        if len(signatures) != 1:
            raise ValueError(
                "multi-leg long-only structure requires matched contract identity"
            )
        if (
            structure_type == "long_straddle"
            and len({leg["strike"] for leg in long_legs}) != 1
        ):
            raise ValueError("long straddle requires a common strike")
        if (
            structure_type == "long_strangle"
            and len({leg["strike"] for leg in long_legs}) != 2
        ):
            raise ValueError("long strangle requires distinct strikes")
        return
    if structure_type not in vertical_rules:
        raise ValueError(
            "sell-bearing structure is not in the exact bounded-loss allowlist: "
            f"structure_type={structure_type!r}"
        )
    if len(short_legs) != 1 or len(long_legs) != 1 or len(legs) != 2:
        raise ValueError(
            "v1 vertical structures require exactly one long and one short leg"
        )
    short_leg = short_legs[0]
    long_leg = long_legs[0]
    option_type, lower_role, higher_role = vertical_rules[structure_type]
    if _leg_signature(short_leg) != _leg_signature(long_leg):
        raise ValueError(
            "protective leg must match underlying, option type, expiry, multiplier, "
            "deliverable, option style, and settlement type"
        )
    if short_leg["option_type"] != option_type:
        raise ValueError(
            "option type does not match structure topology: "
            f"structure_type={structure_type}, option_type={short_leg['option_type']}"
        )
    if long_leg["quantity"] != short_leg["quantity"]:
        raise ValueError(
            "v1 vertical protective quantity must exactly match short quantity"
        )
    long_strike = float(long_leg["strike"])
    short_strike = float(short_leg["strike"])
    if long_strike == short_strike:
        raise ValueError("vertical strikes must differ")
    actual_lower_role = "long_lower" if long_strike < short_strike else "short_lower"
    actual_higher_role = "short_higher" if short_strike > long_strike else "long_higher"
    if (actual_lower_role, actual_higher_role) != (lower_role, higher_role):
        raise ValueError(
            "protective strike direction does not match declared structure: "
            f"structure_type={structure_type}, long_strike={long_strike}, short_strike={short_strike}"
        )


def _validate_embedded_dummy_contract(contract: Mapping[str, JsonValue]) -> None:
    text_fields = (
        "opportunity_id",
        "creation_timestamp",
        "underlying",
        "forecast",
        "intended_horizon",
        "expiration_timestamp",
        "upstream_version",
        "provenance_hash",
        "contract_hash",
    )
    if any(
        not isinstance(contract[field], str) or not contract[field]
        for field in text_fields
    ):
        raise ValueError("embedded Dummy contract contains an empty identity field")
    require_market_symbol(
        str(contract["underlying"]), "dummy_input_contract.underlying"
    )
    creation = require_utc_iso(str(contract["creation_timestamp"]))
    expiration = require_utc_iso(str(contract["expiration_timestamp"]))
    if parse_utc(expiration) <= parse_utc(creation):
        raise ValueError("embedded Dummy contract expiration must follow creation")
    require_sha256(
        str(contract["provenance_hash"]), "dummy_input_contract.provenance_hash"
    )
    require_sha256(str(contract["contract_hash"]), "dummy_input_contract.contract_hash")
    confidence = contract["confidence"]
    exposure = contract["maximum_exposure_fraction"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise ValueError("embedded Dummy confidence must be within [0, 1]")
    if (
        not isinstance(exposure, (int, float))
        or isinstance(exposure, bool)
        or not 0.0 < float(exposure) <= 1.0
    ):
        raise ValueError("embedded Dummy maximum exposure must be within (0, 1]")
    if not isinstance(contract["synthetic"], bool):
        raise ValueError("embedded Dummy synthetic flag must be boolean")
    body: dict[str, JsonValue] = {
        "creation_timestamp": str(contract["creation_timestamp"]),
        "underlying": str(contract["underlying"]),
        "forecast": str(contract["forecast"]),
        "intended_horizon": str(contract["intended_horizon"]),
        "confidence": float(confidence),
        "maximum_exposure_fraction": float(exposure),
        "expiration_timestamp": str(contract["expiration_timestamp"]),
        "upstream_version": str(contract["upstream_version"]),
        "provenance_hash": str(contract["provenance_hash"]),
        "synthetic": bool(contract["synthetic"]),
    }
    expected_hash = canonical_hash(body)
    if contract["contract_hash"] != expected_hash:
        raise ValueError(
            "embedded Dummy contract hash does not match its immutable content"
        )
    if contract["opportunity_id"] != f"dummy-{expected_hash[:24]}":
        raise ValueError(
            "embedded Dummy opportunity ID does not match its immutable content"
        )


def candidate_dummy_contract(candidate: CandidateGenome) -> Mapping[str, JsonValue]:
    validate_candidate_genome(candidate)
    value = candidate.specification["dummy_input_contract"]
    if not isinstance(value, Mapping):
        raise ValueError("candidate Dummy contract is not a mapping")
    return value


def candidate_option_legs(
    candidate: CandidateGenome,
) -> tuple[Mapping[str, JsonValue], ...]:
    validate_candidate_genome(candidate)
    structure = candidate.specification["structure"]
    if not isinstance(structure, Mapping):
        raise ValueError("candidate structure is not a mapping")
    legs = structure["legs"]
    if not isinstance(legs, tuple) or not all(isinstance(leg, Mapping) for leg in legs):
        raise ValueError("candidate option legs are not deeply frozen mappings")
    return tuple(cast(Mapping[str, JsonValue], leg) for leg in legs)


def _require_fraction_field(
    section: Mapping[str, JsonValue],
    field_name: str,
    allow_zero: bool,
) -> float:
    value = section[field_name]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"candidate fraction field must be numeric: field={field_name}"
        )
    number = float(value)
    lower_bound_satisfied = number >= 0.0 if allow_zero else number > 0.0
    if not math.isfinite(number) or not lower_bound_satisfied or number > 1.0:
        raise ValueError(
            f"candidate fraction field is outside its domain: field={field_name}"
        )
    return number


def _require_positive_number(
    section: Mapping[str, JsonValue], field_name: str
) -> float:
    value = section[field_name]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"candidate risk limit must be numeric: field={field_name}")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(
            f"candidate risk limit must be positive and finite: field={field_name}"
        )
    return number


def _require_nonempty_string_list(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError(
            f"candidate field requires a non-empty string list: field={field_name}"
        )
    return tuple(value)


def _require_nonempty_string(
    section: Mapping[str, JsonValue],
    field_name: str,
) -> str:
    value = section[field_name.rsplit(".", maxsplit=1)[-1]]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"candidate field requires a non-empty string: field={field_name}"
        )
    return value


def _validate_candidate_semantics(
    specification: dict[str, JsonValue],
    dummy_contract: dict[str, JsonValue],
    legs: list[dict[str, JsonValue]],
    candidate_mode: Literal["options_expression", "abstention_policy"],
) -> None:
    market_state = cast(dict[str, JsonValue], specification["market_state"])
    _require_nonempty_string_list(
        market_state["available_features"],
        "market_state.available_features",
    )
    for field_name in ("timestamp_rules", "liquidity_state", "volatility_state"):
        _require_nonempty_string(market_state, f"market_state.{field_name}")

    instrument_choice = cast(dict[str, JsonValue], specification["instrument_choice"])
    if not isinstance(instrument_choice["use_options"], bool):
        raise ValueError("candidate instrument_choice.use_options must be boolean")
    for field_name in ("underlying_alternative", "reason"):
        _require_nonempty_string(instrument_choice, f"instrument_choice.{field_name}")

    structure = cast(dict[str, JsonValue], specification["structure"])
    for field_name in ("type", "assignment_profile", "exercise_profile"):
        _require_nonempty_string(structure, f"structure.{field_name}")

    entry = cast(dict[str, JsonValue], specification["entry"])
    earliest = require_utc_iso(str(entry["earliest_time"]))
    latest = require_utc_iso(str(entry["latest_time"]))
    if parse_utc(earliest) < parse_utc(str(dummy_contract["creation_timestamp"])):
        raise ValueError(
            "candidate entry window cannot predate the frozen Dummy opportunity"
        )
    if parse_utc(latest) <= parse_utc(earliest):
        raise ValueError("candidate entry latest_time must follow earliest_time")
    if parse_utc(latest) >= parse_utc(str(dummy_contract["expiration_timestamp"])):
        raise ValueError(
            "candidate entry window must close before Dummy opportunity expiration"
        )
    latest_date = parse_utc(latest).date()
    if any(date.fromisoformat(str(leg["expiry"])) < latest_date for leg in legs):
        raise ValueError("candidate option expiry cannot predate the entry window")
    for field_name in (
        "limit_price_rule",
        "cancellation_rule",
        "venue_rule",
        "legging_rule",
        "fill_model_version",
    ):
        _require_nonempty_string(entry, f"entry.{field_name}")

    sizing = cast(dict[str, JsonValue], specification["sizing"])
    _require_nonempty_string(sizing, "sizing.method")
    uncertainty_haircut = _require_fraction_field(
        sizing, "uncertainty_haircut", allow_zero=True
    )
    allow_zero = candidate_mode == "abstention_policy"
    maximum_position = _require_fraction_field(
        sizing,
        "maximum_position_fraction",
        allow_zero=allow_zero,
    )
    maximum_contribution = _require_fraction_field(
        sizing,
        "maximum_portfolio_contribution",
        allow_zero=allow_zero,
    )
    margin_limit = _require_fraction_field(
        sizing, "margin_limit", allow_zero=allow_zero
    )
    if candidate_mode == "abstention_policy" and any(
        value != 0.0
        for value in (
            uncertainty_haircut,
            maximum_position,
            maximum_contribution,
            margin_limit,
        )
    ):
        raise ValueError(
            "abstention candidate sizing and margin fields must all be zero"
        )
    if maximum_position > float(dummy_contract["maximum_exposure_fraction"]):
        raise ValueError(
            "candidate position fraction exceeds the frozen Dummy exposure envelope"
        )
    if maximum_contribution < maximum_position:
        raise ValueError(
            "candidate portfolio contribution cap cannot be below its position cap"
        )

    risk = cast(dict[str, JsonValue], specification["risk"])
    exposure_limit_fields = (
        "delta_limit",
        "gamma_limit",
        "theta_limit",
        "vega_limit",
        "vanna_limit",
        "charm_limit",
        "vomma_limit",
        "skew_limit",
        "correlation_limit",
        "event_limit",
        "liquidity_limit",
        "gap_limit",
    )
    fraction_limit_fields = (
        "tail_limit",
        "concentration_limit",
        "drawdown_limit",
        "expected_shortfall_limit",
        "ruin_probability_limit",
    )
    if candidate_mode == "options_expression":
        for field_name in exposure_limit_fields:
            _require_positive_number(risk, field_name)
        for field_name in fraction_limit_fields:
            _require_fraction_field(risk, field_name, allow_zero=False)
    else:
        for field_name in exposure_limit_fields + fraction_limit_fields:
            if _require_fraction_field(risk, field_name, allow_zero=True) != 0.0:
                raise ValueError("abstention candidate risk limits must all be zero")
    _require_nonempty_string_list(risk["kill_conditions"], "risk.kill_conditions")

    management = cast(dict[str, JsonValue], specification["management"])
    for field_name in (
        "monitor_frequency",
        "hold_rule",
        "trim_rule",
        "hedge_rule",
        "roll_rule",
        "exit_rule",
        "expiration_rule",
    ):
        _require_nonempty_string(management, f"management.{field_name}")

    economics = cast(dict[str, JsonValue], specification["economics"])
    for field_name in (
        "commission_model",
        "spread_model",
        "slippage_model",
        "impact_model",
        "funding_model",
        "borrow_model",
    ):
        _require_nonempty_string(economics, f"economics.{field_name}")

    evaluation = cast(dict[str, JsonValue], specification["evaluation"])
    benchmarks = _require_nonempty_string_list(
        evaluation["benchmarks"], "evaluation.benchmarks"
    )
    unknown_baselines = sorted(set(benchmarks).difference(BASELINE_IDS))
    if unknown_baselines:
        raise ValueError(
            f"candidate declares unknown baseline IDs: ids={unknown_baselines}"
        )
    for field_name in (
        "primary_metrics",
        "secondary_metrics",
        "negative_controls",
        "stress_tests",
    ):
        _require_nonempty_string_list(
            evaluation[field_name], f"evaluation.{field_name}"
        )
    declared_negative_controls = tuple(cast(list[str], evaluation["negative_controls"]))
    expected_negative_controls = tuple(sorted(V1_REQUIRED_NEGATIVE_CONTROL_IDS))
    if declared_negative_controls != expected_negative_controls:
        raise ValueError(
            "candidate negative_controls must equal the canonical v1 required set"
        )
    declared_stress_tests = tuple(cast(list[str], evaluation["stress_tests"]))
    expected_stress_tests = tuple(
        sorted(scenario_id for _, scenario_id in v1_required_stress_requirements())
    )
    if declared_stress_tests != expected_stress_tests:
        raise ValueError(
            "candidate stress_tests must equal the canonical v1 required set"
        )

    reproducibility = cast(dict[str, JsonValue], specification["reproducibility"])
    require_sha256(str(reproducibility["data_snapshot_hash"]), "data_snapshot_hash")
    require_sha256(str(reproducibility["environment_hash"]), "environment_hash")
    if reproducibility["environment_hash"] != V1_ENVIRONMENT_HASH:
        raise ValueError(
            "candidate reproducibility environment_hash is not canonical environment_v1"
        )
    _require_nonempty_string(reproducibility, "reproducibility.code_commit")
    _require_nonempty_string(reproducibility, "reproducibility.evaluator_version")
    seeds = reproducibility["random_seeds"]
    if (
        not isinstance(seeds, list)
        or not seeds
        or any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds)
        or len(seeds) != len(set(seeds))
    ):
        raise ValueError("candidate random seeds must be unique integers")
