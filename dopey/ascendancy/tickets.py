"""Paper-only decisions derived from frozen candidates, inputs, and protected gates."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Mapping, cast

import exchange_calendars

from dopey.constitution.execution_seal import (
    assert_no_forbidden_nested_payload,
    assert_output_research_only,
)

from .contracts import (
    CandidateGenome,
    DummyOpportunity,
    candidate_dummy_contract,
    candidate_genome_canonical_snapshot,
    candidate_option_legs,
    create_candidate_genome,
    create_dummy_opportunity,
    require_market_symbol,
    validate_candidate_genome,
    validate_dummy_opportunity,
    validate_exact_defined_risk_topology,
)
from .gates import (
    BehavioralState,
    CandidateExposure,
    PortfolioState,
    RiskLimits,
    evaluate_behavioral_gate,
    evaluate_risk_gate,
)
from .identity import (
    JsonValue,
    canonical_hash,
    canonical_json,
    parse_utc,
    require_sha256,
    require_utc_iso,
)
from .negative_controls import NegativeControlResult, evaluate_negative_controls
from .policy_ids import V1_REQUIRED_NEGATIVE_CONTROL_IDS
from .pricing import (
    PaperPriceDirection,
    PriceTriple,
    QuoteGateDecision,
    QuoteGatePolicy,
    QuoteSnapshot,
    build_price_triple,
    contract_identity_hash,
    evaluate_quote_gate,
    quote_contract_identity_hash,
    validate_quote_snapshot_identity,
)
from .v1_resources import (
    packaged_environment_contract,
    packaged_environment_freeze,
    packaged_universe_contract,
)


V1_PAPER_BANKROLL_USD = 100_000.0
V1_ENVIRONMENT_ID = "dopey-options-paper-v1"
V1_ENVIRONMENT_HASH = "811d348d94e151087cd77d496bd1f5135b24dd40ba107b5d860cde34b8475652"
V1_MAXIMUM_SYMBOLS = 200
V1_OPTIONS_COVERAGE_SYMBOLS = 199
V1_UNIVERSE_CONTRACT_HASH = (
    "842cb1afe8294d19a85a55979da69570dce41731707a9ecb9d5c0e61fed46163"
)
V1_UNIVERSE_CONTRACT_PATH = "data_contracts/universe_v1.json"
V1_EXCHANGE_CALENDARS_VERSION = "4.13.2"
V1_SESSION_SOURCE_URI = "python-package://exchange-calendars/4.13.2/XNYS"


@dataclass(frozen=True, slots=True)
class DecisionMarketContext:
    schema_version: Literal["dopey-decision-market-context-v1"]
    environment_id: str
    environment_hash: str
    manifest_id: str
    manifest_hash: str
    membership_mode: Literal["protected_initial_snapshot", "independent_point_in_time"]
    membership_schema_version: str
    membership_captured_at: str
    membership_attestation_id: str
    membership_attestation_hash: str
    symbols: tuple[str, ...]
    membership_effective_at: str
    membership_expires_at: str
    membership_source_uri: str
    membership_provenance_hash: str
    session_id: str
    calendar: Literal["XNYS"]
    session_open: str
    session_close: str
    session_source_uri: str
    session_source_hash: str
    synthetic: bool
    content_hash: str


@dataclass(frozen=True, slots=True)
class ProspectivePaperEvidence:
    schema_version: Literal["dopey-prospective-paper-evidence-v1"]
    opportunity_id: str
    opportunity_contract_hash: str
    candidate_id: str
    candidate_genome_hash: str
    environment_hash: str
    market_context_hash: str
    observed_at: str
    dummy_source_artifact_hash: str
    quote_source_artifact_hash: str
    exposure_model_artifact_hash: str
    complete_cost_model_artifact_hash: str
    fair_value_input_stack_artifact_hash: str
    corporate_actions_artifact_hash: str
    dividends_artifact_hash: str
    rates_artifact_hash: str
    borrow_artifact_hash: str
    synthetic: bool
    paper_only: bool
    live_blocked: bool
    content_hash: str


@dataclass(frozen=True, slots=True)
class PaperPriceRequest:
    quote: QuoteSnapshot
    model_fair_value: float
    price_direction: PaperPriceDirection
    slippage_basis_points: float
    commission_per_contract: float
    contract_multiplier: int


@dataclass(frozen=True, slots=True)
class DecisionControlInputs:
    environment_hash: str
    candidate_exposure: CandidateExposure
    portfolio_state: PortfolioState
    risk_limits: RiskLimits
    behavioral_state: BehavioralState
    negative_control_results: tuple[NegativeControlResult, ...]
    required_negative_control_ids: frozenset[str]
    candidate_author_id: str


@dataclass(frozen=True, slots=True)
class TicketLegTerms:
    content_hash: str
    contract_id: str
    side: Literal["buy", "sell"]
    underlying: str
    option_type: Literal["call", "put"]
    expiry: str
    strike: float
    quantity: int
    multiplier: int
    deliverable: str
    option_style: Literal["american", "european"]
    settlement_type: Literal["physical", "cash"]


@dataclass(frozen=True, slots=True)
class PaperExecutionTicket:
    ticket_id: str
    opportunity_id: str
    opportunity_contract_hash: str
    candidate_id: str
    candidate_genome_hash: str
    candidate_snapshot: str
    environment_hash: str
    decision_timestamp: str
    entry_earliest_time: str
    entry_latest_time: str
    cancellation_deadline: str
    structure_type: str
    leg_terms: tuple[TicketLegTerms, ...]
    contract_ids: tuple[str, ...]
    quantities: tuple[int, ...]
    price_triples: tuple[PriceTriple, ...]
    control_snapshot: str
    control_hash: str
    maximum_loss_usd: float
    maximum_loss_fraction: float
    invalidation_rule: str
    management_rule: str
    exit_rule: str
    paper_fill_status: Literal["pending_later_quote_witness"]
    evidence_class: Literal["synthetic_mechanics_only", "prospective_market_evidence"]
    opportunity_synthetic: bool
    exposure_model_certified: bool
    complete_cost_model_certified: bool
    fair_value_input_stack_certified: bool
    profitability_evidence_eligible: bool
    market_context_snapshot: str
    market_context_hash: str
    prospective_evidence_snapshot: str
    prospective_evidence_hash: str
    paper_only: bool
    live_blocked: bool


@dataclass(frozen=True, slots=True)
class AbstentionRecord:
    abstention_id: str
    opportunity_id: str
    opportunity_contract_hash: str
    opportunity_snapshot: str
    candidate_id: str
    candidate_genome_hash: str
    candidate_snapshot: str
    candidate_mode: Literal["options_expression", "abstention_policy"]
    environment_hash: str
    decision_timestamp: str
    reason_codes: tuple[str, ...]
    control_snapshot: str
    control_hash: str
    price_requests_snapshot: str
    price_requests_hash: str
    market_context_snapshot: str
    market_context_hash: str
    prospective_evidence_snapshot: str
    prospective_evidence_hash: str
    evidence_class: Literal["synthetic_mechanics_only", "prospective_market_evidence"]
    opportunity_synthetic: bool
    profitability_evidence_eligible: bool
    paper_only: bool
    live_blocked: bool


@dataclass(frozen=True, slots=True)
class PaperFillObservation:
    observation_id: str
    ticket_id: str
    witnessed_at: str
    contract_ids: tuple[str, ...]
    conservative_prices: tuple[float, ...]
    witness_hashes: tuple[str, ...]
    witness_quotes: tuple[QuoteSnapshot, ...]
    paper_fill_status: Literal["filled", "missed"]
    reason_codes: tuple[str, ...]
    evidence_class: Literal["synthetic_mechanics_only", "prospective_market_evidence"]
    profitability_evidence_eligible: bool
    realized_evidence: bool
    paper_only: bool
    live_blocked: bool


PaperDecision = PaperExecutionTicket | AbstentionRecord


def v1_quote_gate_policy() -> QuoteGatePolicy:
    return QuoteGatePolicy(15.0, 0.10, 0.05, 5, 25)


def v1_risk_limits() -> RiskLimits:
    return RiskLimits(
        0.01,
        0.02,
        0.03,
        0.001,
        0.02,
        0.10,
        0.10,
        0.02,
        0.005,
        0.05,
        0.02,
        0.02,
        0.02,
        0.03,
        0.05,
        0.05,
        0.05,
        0.03,
        False,
    )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _assert_finite_artifact(value: object, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"artifact contains a non-finite number: path={path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite_artifact(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite_artifact(item, f"{path}[{index}]")


def _assert_canonical_environment_v1() -> None:
    repository_root = _repository_root()
    environment_path = repository_root / "environments" / "environment_v1.json"
    freeze_path = repository_root / "ENVIRONMENT_V1_FREEZE.json"
    source_checkout = (repository_root / ".git").exists()
    if source_checkout:
        if not environment_path.is_file() or not freeze_path.is_file():
            raise ValueError(
                "source checkout is missing canonical environment_v1 artifacts"
            )
        environment_bytes = environment_path.read_bytes()
        if _sha256_bytes(environment_bytes) != V1_ENVIRONMENT_HASH:
            raise ValueError(
                "installed environment_v1 content differs from the canonical hash"
            )
        environment = json.loads(environment_bytes)
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    else:
        environment = packaged_environment_contract()
        freeze = packaged_environment_freeze()
    if not isinstance(environment, dict) or not isinstance(freeze, dict):
        raise ValueError("canonical environment artifacts must be mappings")
    expected_freeze = {
        "schema_version": "dopey-environment-freeze-v1",
        "environment_file": "environments/environment_v1.json",
        "environment_id": V1_ENVIRONMENT_ID,
        "file_sha256": V1_ENVIRONMENT_HASH,
        "mutation_policy": "new_version_required",
        "paper_only": True,
        "live_blocked": True,
    }
    if any(freeze.get(key) != value for key, value in expected_freeze.items()):
        raise ValueError("environment freeze does not bind canonical environment_v1")
    if (
        environment.get("environment_id") != V1_ENVIRONMENT_ID
        or environment.get("mode") != "paper_research_only"
        or environment.get("frozen") is not True
    ):
        raise ValueError("canonical environment_v1 authority is invalid")
    universe = environment.get("permitted_underlying_universe")
    if (
        not isinstance(universe, dict)
        or universe.get("maximum_symbols") != V1_MAXIMUM_SYMBOLS
    ):
        raise ValueError("canonical environment_v1 universe policy is invalid")
    if version("exchange-calendars") != V1_EXCHANGE_CALENDARS_VERSION:
        raise ValueError(
            "installed exchange-calendars version differs from environment v1"
        )


def _load_v1_universe_contract() -> dict[str, JsonValue]:
    path = _repository_root() / V1_UNIVERSE_CONTRACT_PATH
    packaged = packaged_universe_contract()
    source_checkout = (_repository_root() / ".git").exists()
    if source_checkout:
        if not path.is_file():
            raise ValueError("source checkout is missing protected universe_v1")
        raw = path.read_bytes()
        if _sha256_bytes(raw) != V1_UNIVERSE_CONTRACT_HASH:
            raise ValueError(
                "installed universe_v1 content differs from the protected hash"
            )
        decoded = json.loads(raw)
        if decoded != packaged:
            raise ValueError("source universe_v1 differs from its packaged contract")
    else:
        decoded = packaged
    if not isinstance(decoded, dict):
        raise ValueError("protected universe_v1 contract must be a mapping")
    expected_top_level = {
        "schema_version",
        "environment_id",
        "environment_hash",
        "authority_state",
        "watch_universe",
        "options_mechanics_coverage",
        "context_only_symbols",
        "paper_only",
        "live_blocked",
    }
    if set(decoded) != expected_top_level:
        raise ValueError("protected universe_v1 contract differs from its exact schema")
    if (
        decoded["schema_version"] != "dopey-universe-contract-v1"
        or decoded["environment_id"] != V1_ENVIRONMENT_ID
        or decoded["environment_hash"] != V1_ENVIRONMENT_HASH
        or decoded["authority_state"] != "development_mechanics_only"
        or decoded["paper_only"] is not True
        or decoded["live_blocked"] is not True
    ):
        raise ValueError("protected universe_v1 authority boundary is invalid")
    watch = _mapping(decoded["watch_universe"], "watch_universe")
    options = _mapping(
        decoded["options_mechanics_coverage"],
        "options_mechanics_coverage",
    )
    expected_watch_fields = {
        "manifest_id",
        "captured_at",
        "membership_effective_at",
        "membership_expires_at",
        "source_uri",
        "source_record_hash",
        "symbols",
    }
    expected_options_fields = {
        "manifest_id",
        "source_uri",
        "source_record_hash",
        "symbols",
    }
    if set(watch) != expected_watch_fields or set(options) != expected_options_fields:
        raise ValueError("protected universe manifests differ from the exact schema")
    watch_symbols = tuple(
        _string(symbol, "watch_universe.symbols[]")
        for symbol in _sequence(watch["symbols"], "watch_universe.symbols")
    )
    option_symbols = tuple(
        _string(symbol, "options_mechanics_coverage.symbols[]")
        for symbol in _sequence(
            options["symbols"], "options_mechanics_coverage.symbols"
        )
    )
    if (
        len(watch_symbols) != V1_MAXIMUM_SYMBOLS
        or watch_symbols != tuple(sorted(set(watch_symbols)))
        or len(option_symbols) != V1_OPTIONS_COVERAGE_SYMBOLS
        or option_symbols != tuple(sorted(set(option_symbols)))
        or not set(option_symbols).issubset(watch_symbols)
    ):
        raise ValueError(
            "protected universe coverage cardinality or identity is invalid"
        )
    context_only = tuple(
        _string(symbol, "context_only_symbols[]")
        for symbol in _sequence(decoded["context_only_symbols"], "context_only_symbols")
    )
    if context_only != ("VIX",) or set(watch_symbols).difference(option_symbols) != {
        "VIX"
    }:
        raise ValueError(
            "protected universe must preserve VIX as context-only coverage"
        )
    captured = parse_utc(_string(watch["captured_at"], "watch_universe.captured_at"))
    effective = parse_utc(
        _string(
            watch["membership_effective_at"], "watch_universe.membership_effective_at"
        )
    )
    expires = parse_utc(
        _string(watch["membership_expires_at"], "watch_universe.membership_expires_at")
    )
    if captured != effective or expires <= effective:
        raise ValueError("protected universe membership interval is invalid")
    for field_name, manifest in (
        ("watch_universe", watch),
        ("options_mechanics_coverage", options),
    ):
        _string(manifest["manifest_id"], f"{field_name}.manifest_id")
        _string(manifest["source_uri"], f"{field_name}.source_uri")
        require_sha256(
            _string(manifest["source_record_hash"], f"{field_name}.source_record_hash"),
            f"{field_name}.source_record_hash",
        )
    return cast(dict[str, JsonValue], decoded)


def v1_watch_universe() -> tuple[str, ...]:
    contract = _load_v1_universe_contract()
    watch = _mapping(contract["watch_universe"], "watch_universe")
    return tuple(
        _string(symbol, "watch_universe.symbols[]")
        for symbol in _sequence(watch["symbols"], "watch_universe.symbols")
    )


def v1_options_mechanics_coverage() -> tuple[str, ...]:
    contract = _load_v1_universe_contract()
    options = _mapping(
        contract["options_mechanics_coverage"], "options_mechanics_coverage"
    )
    return tuple(
        _string(symbol, "options_mechanics_coverage.symbols[]")
        for symbol in _sequence(
            options["symbols"], "options_mechanics_coverage.symbols"
        )
    )


def require_v1_environment_hash(environment_hash: str) -> None:
    require_sha256(environment_hash, "environment_hash")
    _assert_canonical_environment_v1()
    if environment_hash != V1_ENVIRONMENT_HASH:
        raise ValueError("artifact is not bound to canonical environment_v1")


def decision_market_context_body(
    context: DecisionMarketContext,
) -> dict[str, JsonValue]:
    return {
        "schema_version": context.schema_version,
        "environment_id": context.environment_id,
        "environment_hash": context.environment_hash,
        "manifest_id": context.manifest_id,
        "manifest_hash": context.manifest_hash,
        "membership_mode": context.membership_mode,
        "membership_schema_version": context.membership_schema_version,
        "membership_captured_at": context.membership_captured_at,
        "membership_attestation_id": context.membership_attestation_id,
        "membership_attestation_hash": context.membership_attestation_hash,
        "symbols": list(context.symbols),
        "membership_effective_at": context.membership_effective_at,
        "membership_expires_at": context.membership_expires_at,
        "membership_source_uri": context.membership_source_uri,
        "membership_provenance_hash": context.membership_provenance_hash,
        "session_id": context.session_id,
        "calendar": context.calendar,
        "session_open": context.session_open,
        "session_close": context.session_close,
        "session_source_uri": context.session_source_uri,
        "session_source_hash": context.session_source_hash,
        "synthetic": context.synthetic,
    }


def create_decision_market_context(
    session_id: str,
    synthetic: bool,
) -> DecisionMarketContext:
    if synthetic is not True:
        raise ValueError(
            "non-synthetic decisions require independent point-in-time membership evidence"
        )
    contract = _load_v1_universe_contract()
    watch = _mapping(contract["watch_universe"], "watch_universe")
    symbols = v1_watch_universe()
    calendar = exchange_calendars.get_calendar("XNYS")
    session_date = date.fromisoformat(session_id)
    if not calendar.is_session(session_date):
        raise ValueError("market context session_id is not an XNYS trading session")
    session_open = (
        calendar.session_open(session_date).isoformat().replace("+00:00", "Z")
    )
    session_close = (
        calendar.session_close(session_date).isoformat().replace("+00:00", "Z")
    )
    session_source_hash = canonical_hash(
        {
            "calendar": "XNYS",
            "session_id": session_id,
            "session_open": session_open,
            "session_close": session_close,
            "source_uri": V1_SESSION_SOURCE_URI,
        }
    )
    provisional = DecisionMarketContext(
        schema_version="dopey-decision-market-context-v1",
        environment_id=V1_ENVIRONMENT_ID,
        environment_hash=V1_ENVIRONMENT_HASH,
        manifest_id=_string(watch["manifest_id"], "watch_universe.manifest_id"),
        manifest_hash=V1_UNIVERSE_CONTRACT_HASH,
        membership_mode="protected_initial_snapshot",
        membership_schema_version="dopey-universe-contract-v1",
        membership_captured_at=_string(
            watch["captured_at"],
            "watch_universe.captured_at",
        ),
        membership_attestation_id="protected-universe-v1-local-hash",
        membership_attestation_hash=V1_UNIVERSE_CONTRACT_HASH,
        symbols=symbols,
        membership_effective_at=_string(
            watch["membership_effective_at"],
            "watch_universe.membership_effective_at",
        ),
        membership_expires_at=_string(
            watch["membership_expires_at"],
            "watch_universe.membership_expires_at",
        ),
        membership_source_uri=_string(watch["source_uri"], "watch_universe.source_uri"),
        membership_provenance_hash=_string(
            watch["source_record_hash"],
            "watch_universe.source_record_hash",
        ),
        session_id=session_id,
        calendar="XNYS",
        session_open=session_open,
        session_close=session_close,
        session_source_uri=V1_SESSION_SOURCE_URI,
        session_source_hash=session_source_hash,
        synthetic=synthetic,
        content_hash="0" * 64,
    )
    context = replace(
        provisional,
        content_hash=canonical_hash(decision_market_context_body(provisional)),
    )
    validate_decision_market_context(context)
    return context


def create_point_in_time_decision_market_context(
    manifest_id: str,
    manifest_hash: str,
    membership_schema_version: str,
    membership_captured_at: str,
    membership_effective_at: str,
    membership_expires_at: str,
    membership_source_uri: str,
    membership_provenance_hash: str,
    membership_attestation_id: str,
    membership_attestation_hash: str,
    symbols: tuple[str, ...],
    session_id: str,
) -> DecisionMarketContext:
    calendar = exchange_calendars.get_calendar("XNYS")
    session_date = date.fromisoformat(session_id)
    if not calendar.is_session(session_date):
        raise ValueError("market context session_id is not an XNYS trading session")
    session_open = (
        calendar.session_open(session_date).isoformat().replace("+00:00", "Z")
    )
    session_close = (
        calendar.session_close(session_date).isoformat().replace("+00:00", "Z")
    )
    session_source_hash = canonical_hash(
        {
            "calendar": "XNYS",
            "session_id": session_id,
            "session_open": session_open,
            "session_close": session_close,
            "source_uri": V1_SESSION_SOURCE_URI,
        }
    )
    provisional = DecisionMarketContext(
        schema_version="dopey-decision-market-context-v1",
        environment_id=V1_ENVIRONMENT_ID,
        environment_hash=V1_ENVIRONMENT_HASH,
        manifest_id=manifest_id,
        manifest_hash=manifest_hash,
        membership_mode="independent_point_in_time",
        membership_schema_version=membership_schema_version,
        membership_captured_at=membership_captured_at,
        membership_attestation_id=membership_attestation_id,
        membership_attestation_hash=membership_attestation_hash,
        symbols=symbols,
        membership_effective_at=membership_effective_at,
        membership_expires_at=membership_expires_at,
        membership_source_uri=membership_source_uri,
        membership_provenance_hash=membership_provenance_hash,
        session_id=session_id,
        calendar="XNYS",
        session_open=session_open,
        session_close=session_close,
        session_source_uri=V1_SESSION_SOURCE_URI,
        session_source_hash=session_source_hash,
        synthetic=False,
        content_hash="0" * 64,
    )
    context = replace(
        provisional,
        content_hash=canonical_hash(decision_market_context_body(provisional)),
    )
    validate_decision_market_context(context)
    return context


def validate_decision_market_context(context: DecisionMarketContext) -> None:
    if context.schema_version != "dopey-decision-market-context-v1":
        raise ValueError("market context schema version is unsupported")
    require_v1_environment_hash(context.environment_hash)
    if context.environment_id != V1_ENVIRONMENT_ID:
        raise ValueError("market context environment identity is unsupported")
    contract = _load_v1_universe_contract()
    watch = _mapping(contract["watch_universe"], "watch_universe")
    for field_name, value in (
        ("manifest_id", context.manifest_id),
        ("membership_schema_version", context.membership_schema_version),
        ("membership_attestation_id", context.membership_attestation_id),
        ("membership_source_uri", context.membership_source_uri),
        ("session_id", context.session_id),
        ("session_source_uri", context.session_source_uri),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"market context identity field is empty: field={field_name}"
            )
    for field_name, value in (
        ("manifest_hash", context.manifest_hash),
        ("membership_attestation_hash", context.membership_attestation_hash),
        ("membership_provenance_hash", context.membership_provenance_hash),
        ("session_source_hash", context.session_source_hash),
        ("content_hash", context.content_hash),
    ):
        require_sha256(value, f"market_context.{field_name}")
    require_utc_iso(context.membership_effective_at)
    require_utc_iso(context.membership_expires_at)
    require_utc_iso(context.membership_captured_at)
    captured = parse_utc(context.membership_captured_at)
    effective = parse_utc(context.membership_effective_at)
    expires = parse_utc(context.membership_expires_at)
    if effective < captured or expires <= effective:
        raise ValueError("market context membership interval is invalid")
    if not isinstance(context.synthetic, bool):
        raise ValueError("market context synthetic flag must be boolean")
    if context.membership_mode == "protected_initial_snapshot":
        if (
            context.synthetic is not True
            or context.manifest_id != watch["manifest_id"]
            or context.manifest_hash != V1_UNIVERSE_CONTRACT_HASH
            or context.membership_schema_version != "dopey-universe-contract-v1"
            or context.membership_captured_at != watch["captured_at"]
            or context.membership_attestation_id != "protected-universe-v1-local-hash"
            or context.membership_attestation_hash != V1_UNIVERSE_CONTRACT_HASH
            or context.membership_source_uri != watch["source_uri"]
            or context.membership_provenance_hash != watch["source_record_hash"]
            or context.membership_effective_at != watch["membership_effective_at"]
            or context.membership_expires_at != watch["membership_expires_at"]
            or context.symbols != v1_watch_universe()
        ):
            raise ValueError(
                "market context is not bound to the protected 200-symbol universe"
            )
    elif context.membership_mode == "independent_point_in_time":
        if context.synthetic is not False:
            raise ValueError(
                "dynamic point-in-time membership cannot claim synthetic status"
            )
        if context.membership_schema_version != "dopey-point-in-time-universe-v1":
            raise ValueError("dynamic membership schema version is unsupported")
        for symbol in context.symbols:
            require_market_symbol(symbol, "market_context.symbols[]")
        if (
            not context.symbols
            or len(context.symbols) > V1_MAXIMUM_SYMBOLS
            or context.symbols != tuple(sorted(set(context.symbols)))
        ):
            raise ValueError(
                "dynamic membership symbols must be sorted, unique, uppercase, and capped at 200"
            )
    else:
        raise ValueError("market context membership mode is unsupported")
    if context.calendar != "XNYS":
        raise ValueError("market context requires the XNYS calendar")
    session_date = date.fromisoformat(context.session_id)
    calendar = exchange_calendars.get_calendar("XNYS")
    if not calendar.is_session(session_date):
        raise ValueError("market context session is not an XNYS trading day")
    expected_open = (
        calendar.session_open(session_date).isoformat().replace("+00:00", "Z")
    )
    expected_close = (
        calendar.session_close(session_date).isoformat().replace("+00:00", "Z")
    )
    if context.session_open != expected_open or context.session_close != expected_close:
        raise ValueError("market context session bounds differ from XNYS")
    expected_session_hash = canonical_hash(
        {
            "calendar": "XNYS",
            "session_id": context.session_id,
            "session_open": expected_open,
            "session_close": expected_close,
            "source_uri": V1_SESSION_SOURCE_URI,
        }
    )
    if (
        context.session_source_uri != V1_SESSION_SOURCE_URI
        or context.session_source_hash != expected_session_hash
    ):
        raise ValueError("market context session provenance differs from XNYS")
    if context.content_hash != canonical_hash(decision_market_context_body(context)):
        raise ValueError(
            "market context content hash does not match its immutable fields"
        )


def prospective_paper_evidence_body(
    evidence: ProspectivePaperEvidence,
) -> dict[str, JsonValue]:
    return {
        "schema_version": evidence.schema_version,
        "opportunity_id": evidence.opportunity_id,
        "opportunity_contract_hash": evidence.opportunity_contract_hash,
        "candidate_id": evidence.candidate_id,
        "candidate_genome_hash": evidence.candidate_genome_hash,
        "environment_hash": evidence.environment_hash,
        "market_context_hash": evidence.market_context_hash,
        "observed_at": evidence.observed_at,
        "dummy_source_artifact_hash": evidence.dummy_source_artifact_hash,
        "quote_source_artifact_hash": evidence.quote_source_artifact_hash,
        "exposure_model_artifact_hash": evidence.exposure_model_artifact_hash,
        "complete_cost_model_artifact_hash": evidence.complete_cost_model_artifact_hash,
        "fair_value_input_stack_artifact_hash": evidence.fair_value_input_stack_artifact_hash,
        "corporate_actions_artifact_hash": evidence.corporate_actions_artifact_hash,
        "dividends_artifact_hash": evidence.dividends_artifact_hash,
        "rates_artifact_hash": evidence.rates_artifact_hash,
        "borrow_artifact_hash": evidence.borrow_artifact_hash,
        "synthetic": evidence.synthetic,
        "paper_only": evidence.paper_only,
        "live_blocked": evidence.live_blocked,
    }


def create_prospective_paper_evidence(
    opportunity: DummyOpportunity,
    candidate: CandidateGenome,
    market_context: DecisionMarketContext,
    observed_at: str,
    artifact_hashes: Mapping[str, str],
) -> ProspectivePaperEvidence:
    required_hash_fields = (
        "dummy_source_artifact_hash",
        "quote_source_artifact_hash",
        "exposure_model_artifact_hash",
        "complete_cost_model_artifact_hash",
        "fair_value_input_stack_artifact_hash",
        "corporate_actions_artifact_hash",
        "dividends_artifact_hash",
        "rates_artifact_hash",
        "borrow_artifact_hash",
    )
    if set(artifact_hashes) != set(required_hash_fields):
        raise ValueError(
            "prospective evidence artifact hashes differ from the exact schema"
        )
    provisional = ProspectivePaperEvidence(
        schema_version="dopey-prospective-paper-evidence-v1",
        opportunity_id=opportunity.opportunity_id,
        opportunity_contract_hash=opportunity.contract_hash,
        candidate_id=candidate.candidate_id,
        candidate_genome_hash=candidate.genome_hash,
        environment_hash=V1_ENVIRONMENT_HASH,
        market_context_hash=canonical_hash(
            cast(dict[str, JsonValue], asdict(market_context))
        ),
        observed_at=observed_at,
        dummy_source_artifact_hash=artifact_hashes["dummy_source_artifact_hash"],
        quote_source_artifact_hash=artifact_hashes["quote_source_artifact_hash"],
        exposure_model_artifact_hash=artifact_hashes["exposure_model_artifact_hash"],
        complete_cost_model_artifact_hash=artifact_hashes[
            "complete_cost_model_artifact_hash"
        ],
        fair_value_input_stack_artifact_hash=artifact_hashes[
            "fair_value_input_stack_artifact_hash"
        ],
        corporate_actions_artifact_hash=artifact_hashes[
            "corporate_actions_artifact_hash"
        ],
        dividends_artifact_hash=artifact_hashes["dividends_artifact_hash"],
        rates_artifact_hash=artifact_hashes["rates_artifact_hash"],
        borrow_artifact_hash=artifact_hashes["borrow_artifact_hash"],
        synthetic=False,
        paper_only=True,
        live_blocked=True,
        content_hash="0" * 64,
    )
    evidence = replace(
        provisional,
        content_hash=canonical_hash(prospective_paper_evidence_body(provisional)),
    )
    validate_prospective_paper_evidence(
        evidence, opportunity, candidate, market_context
    )
    return evidence


def validate_prospective_paper_evidence(
    evidence: ProspectivePaperEvidence,
    opportunity: DummyOpportunity,
    candidate: CandidateGenome,
    market_context: DecisionMarketContext,
) -> None:
    if evidence.schema_version != "dopey-prospective-paper-evidence-v1":
        raise ValueError("prospective evidence schema version is unsupported")
    if (
        evidence.paper_only is not True
        or evidence.live_blocked is not True
        or evidence.synthetic is not False
    ):
        raise ValueError(
            "prospective evidence weakened its paper-only real-market boundary"
        )
    require_v1_environment_hash(evidence.environment_hash)
    validate_decision_market_context(market_context)
    if market_context.membership_mode != "independent_point_in_time":
        raise ValueError(
            "prospective evidence requires dynamic point-in-time membership"
        )
    require_utc_iso(evidence.observed_at)
    observed_at = parse_utc(evidence.observed_at)
    if not (
        parse_utc(opportunity.creation_timestamp)
        <= observed_at
        < parse_utc(opportunity.expiration_timestamp)
    ):
        raise ValueError(
            "prospective evidence observation is outside the Dummy causal window"
        )
    if (
        evidence.opportunity_id != opportunity.opportunity_id
        or evidence.opportunity_contract_hash != opportunity.contract_hash
        or evidence.candidate_id != candidate.candidate_id
        or evidence.candidate_genome_hash != candidate.genome_hash
        or evidence.market_context_hash
        != canonical_hash(cast(dict[str, JsonValue], asdict(market_context)))
    ):
        raise ValueError(
            "prospective evidence is not bound to the frozen opportunity and candidate"
        )
    if opportunity.synthetic:
        raise ValueError(
            "prospective evidence requires a non-synthetic Dummy opportunity"
        )
    for field in fields(ProspectivePaperEvidence):
        if field.name.endswith("_artifact_hash"):
            require_sha256(
                cast(str, getattr(evidence, field.name)),
                f"prospective_evidence.{field.name}",
            )
    require_sha256(
        evidence.market_context_hash, "prospective_evidence.market_context_hash"
    )
    require_sha256(evidence.content_hash, "prospective_evidence.content_hash")
    if evidence.content_hash != canonical_hash(
        prospective_paper_evidence_body(evidence)
    ):
        raise ValueError(
            "prospective evidence content hash does not match its immutable fields"
        )


def _optional_artifact_snapshot(value: object | None) -> tuple[str, str]:
    snapshot = canonical_json(cast(JsonValue, value))
    return snapshot, canonical_hash(cast(JsonValue, value))


def _parse_optional_artifact_snapshot(
    snapshot: str,
    expected_hash: str,
    field_name: str,
) -> JsonValue:
    require_sha256(expected_hash, f"{field_name}_hash")
    try:
        decoded = json.loads(snapshot)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field_name} snapshot is not valid JSON") from error
    if canonical_json(cast(JsonValue, decoded)) != snapshot:
        raise ValueError(f"{field_name} snapshot is not canonical JSON")
    if canonical_hash(cast(JsonValue, decoded)) != expected_hash:
        raise ValueError(f"{field_name} snapshot hash mismatch")
    if decoded is None:
        return None
    return cast(JsonValue, decoded)


def candidate_lifecycle_rules(candidate: CandidateGenome) -> tuple[str, str, str]:
    validate_candidate_genome(candidate)
    management = _mapping(candidate.specification["management"], "management")
    risk = _mapping(candidate.specification["risk"], "risk")
    kill_conditions = _sequence(risk["kill_conditions"], "risk.kill_conditions")
    invalidation_rule = canonical_json(
        {
            "rule_type": "candidate_kill_conditions",
            "kill_conditions": sorted(
                _string(condition, "risk.kill_conditions[]")
                for condition in kill_conditions
            ),
        }
    )
    management_rule = canonical_json(
        {
            "monitor_frequency": cast(JsonValue, management["monitor_frequency"]),
            "hold_rule": cast(JsonValue, management["hold_rule"]),
            "trim_rule": cast(JsonValue, management["trim_rule"]),
            "hedge_rule": cast(JsonValue, management["hedge_rule"]),
            "roll_rule": cast(JsonValue, management["roll_rule"]),
        }
    )
    exit_rule = canonical_json(
        {
            "exit_rule": cast(JsonValue, management["exit_rule"]),
            "expiration_rule": cast(JsonValue, management["expiration_rule"]),
        }
    )
    return invalidation_rule, management_rule, exit_rule


def _candidate_limit_reasons(
    candidate: CandidateGenome,
    controls: DecisionControlInputs,
) -> tuple[str, ...]:
    sizing = _mapping(candidate.specification["sizing"], "sizing")
    risk = _mapping(candidate.specification["risk"], "risk")
    exposure = controls.candidate_exposure
    portfolio = controls.portfolio_state
    reasons: list[str] = []
    scalar_checks = (
        (
            exposure.maximum_loss_fraction > float(sizing["maximum_position_fraction"]),
            "candidate_position_limit",
        ),
        (
            exposure.maximum_loss_fraction
            > float(sizing["maximum_portfolio_contribution"]),
            "candidate_portfolio_contribution_limit",
        ),
        (
            exposure.margin_fraction > float(sizing["margin_limit"]),
            "candidate_margin_limit",
        ),
        (
            exposure.maximum_loss_fraction > float(risk["tail_limit"]),
            "candidate_tail_limit",
        ),
        (
            exposure.expected_shortfall_fraction
            > float(risk["expected_shortfall_limit"]),
            "candidate_expected_shortfall_limit",
        ),
        (
            exposure.ruin_probability > float(risk["ruin_probability_limit"]),
            "candidate_ruin_probability_limit",
        ),
        (
            portfolio.drawdown_fraction >= float(risk["drawdown_limit"]),
            "candidate_drawdown_limit",
        ),
    )
    reasons.extend(reason for failed, reason in scalar_checks if failed)
    greek_fields = (
        ("delta", "delta_limit"),
        ("gamma", "gamma_limit"),
        ("theta", "theta_limit"),
        ("vega", "vega_limit"),
        ("vanna", "vanna_limit"),
        ("charm", "charm_limit"),
        ("vomma", "vomma_limit"),
        ("skew", "skew_limit"),
        ("correlation", "correlation_limit"),
        ("event", "event_limit"),
        ("liquidity", "liquidity_limit"),
        ("gap", "gap_limit"),
    )
    for exposure_field, limit_field in greek_fields:
        combined = float(getattr(portfolio, exposure_field)) + float(
            getattr(exposure, exposure_field)
        )
        if abs(combined) > float(risk[limit_field]):
            reasons.append(f"candidate_{exposure_field}_limit")
    concentration = max(
        abs(portfolio.correlation + exposure.correlation),
        abs(portfolio.event + exposure.event),
        abs(portfolio.liquidity + exposure.liquidity),
        abs(portfolio.gap + exposure.gap),
    )
    if concentration > float(risk["concentration_limit"]):
        reasons.append("candidate_concentration_limit")
    return tuple(sorted(set(reasons)))


def _market_context_reasons(
    context: DecisionMarketContext | None,
    opportunity: DummyOpportunity,
    decision_timestamp: str,
    entry_earliest_time: str,
    cancellation_deadline: str,
    entry_latest_time: str,
) -> tuple[str, ...]:
    if context is None:
        return ("point_in_time_market_context_missing",)
    validate_decision_market_context(context)
    decision = parse_utc(decision_timestamp)
    earliest = parse_utc(entry_earliest_time)
    cancellation = parse_utc(cancellation_deadline)
    latest = parse_utc(entry_latest_time)
    session_open = parse_utc(context.session_open)
    session_close = parse_utc(context.session_close)
    effective = parse_utc(context.membership_effective_at)
    expires = parse_utc(context.membership_expires_at)
    reasons: list[str] = []
    if opportunity.underlying not in context.symbols:
        reasons.append("underlying_not_in_point_in_time_universe")
    if (
        context.membership_mode == "protected_initial_snapshot"
        and opportunity.underlying not in v1_options_mechanics_coverage()
    ):
        reasons.append("missing_option_chain_coverage")
    if decision < parse_utc(context.membership_captured_at):
        reasons.append("universe_membership_backdated_before_capture")
    if not effective <= decision < expires:
        reasons.append("universe_membership_not_effective_at_decision")
    if context.synthetic is not opportunity.synthetic:
        reasons.append("market_context_synthetic_class_mismatch")
    if (
        not session_open
        <= decision
        <= earliest
        < cancellation
        <= latest
        < session_close
    ):
        reasons.append("decision_or_entry_window_outside_xnys_session")
    return tuple(sorted(set(reasons)))


def _assert_research_boundary() -> None:
    assert_output_research_only(
        {
            "artifact_type": "paper_options_decision",
            "paper_only": True,
            "live_blocked": True,
            "action_ready": False,
        }
    )


def _controls_body(controls: DecisionControlInputs) -> dict[str, JsonValue]:
    return {
        "environment_hash": controls.environment_hash,
        "candidate_exposure": cast(
            dict[str, JsonValue], asdict(controls.candidate_exposure)
        ),
        "portfolio_state": cast(dict[str, JsonValue], asdict(controls.portfolio_state)),
        "risk_limits": cast(dict[str, JsonValue], asdict(controls.risk_limits)),
        "behavioral_state": cast(
            dict[str, JsonValue], asdict(controls.behavioral_state)
        ),
        "negative_control_results": [
            cast(dict[str, JsonValue], asdict(result))
            for result in sorted(
                controls.negative_control_results,
                key=lambda result: result.control_id,
            )
        ],
        "required_negative_control_ids": sorted(controls.required_negative_control_ids),
        "candidate_author_id": controls.candidate_author_id,
    }


def _ticket_control_body(
    controls: DecisionControlInputs,
    candidate: CandidateGenome,
    opportunity: DummyOpportunity,
    decision_timestamp: str,
) -> dict[str, JsonValue]:
    return {
        "schema_version": "dopey-paper-ticket-control-v1",
        "candidate_id": candidate.candidate_id,
        "candidate_genome_hash": candidate.genome_hash,
        "opportunity_id": opportunity.opportunity_id,
        "decision_timestamp": decision_timestamp,
        **_controls_body(controls),
        "paper_only": True,
        "live_blocked": True,
    }


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"candidate field must be a mapping: field={field_name}")
    return cast(Mapping[str, object], value)


def _exact_dataclass_mapping(
    value: object,
    dataclass_type: type[object],
    field_name: str,
) -> Mapping[str, object]:
    mapping = _mapping(value, field_name)
    expected_fields = {field.name for field in fields(dataclass_type)}
    observed_fields = set(mapping)
    if observed_fields != expected_fields:
        raise ValueError(
            "artifact mapping fields differ from the canonical schema: "
            f"field={field_name}, missing={sorted(expected_fields - observed_fields)}, "
            f"extra={sorted(observed_fields - expected_fields)}"
        )
    return mapping


def _sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"artifact field must be a sequence: field={field_name}")
    return tuple(value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"artifact field must be a string: field={field_name}")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"artifact field must be a boolean: field={field_name}")
    return value


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"artifact field must be an integer: field={field_name}")
    return value


def _number(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"artifact field must be numeric: field={field_name}")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"artifact numeric field must be finite: field={field_name}")
    return normalized


def _decision_market_context_from_mapping(value: object) -> DecisionMarketContext:
    mapping = _exact_dataclass_mapping(
        value, DecisionMarketContext, "decision_market_context"
    )
    raw_symbols = _sequence(mapping["symbols"], "market_context.symbols")
    context = DecisionMarketContext(
        schema_version=cast(
            Literal["dopey-decision-market-context-v1"],
            _string(mapping["schema_version"], "market_context.schema_version"),
        ),
        environment_id=_string(
            mapping["environment_id"], "market_context.environment_id"
        ),
        environment_hash=_string(
            mapping["environment_hash"], "market_context.environment_hash"
        ),
        manifest_id=_string(mapping["manifest_id"], "market_context.manifest_id"),
        manifest_hash=_string(mapping["manifest_hash"], "market_context.manifest_hash"),
        membership_mode=cast(
            Literal["protected_initial_snapshot", "independent_point_in_time"],
            _string(mapping["membership_mode"], "market_context.membership_mode"),
        ),
        membership_schema_version=_string(
            mapping["membership_schema_version"],
            "market_context.membership_schema_version",
        ),
        membership_captured_at=_string(
            mapping["membership_captured_at"],
            "market_context.membership_captured_at",
        ),
        membership_attestation_id=_string(
            mapping["membership_attestation_id"],
            "market_context.membership_attestation_id",
        ),
        membership_attestation_hash=_string(
            mapping["membership_attestation_hash"],
            "market_context.membership_attestation_hash",
        ),
        symbols=tuple(
            _string(symbol, "market_context.symbols[]") for symbol in raw_symbols
        ),
        membership_effective_at=_string(
            mapping["membership_effective_at"], "market_context.membership_effective_at"
        ),
        membership_expires_at=_string(
            mapping["membership_expires_at"], "market_context.membership_expires_at"
        ),
        membership_source_uri=_string(
            mapping["membership_source_uri"], "market_context.membership_source_uri"
        ),
        membership_provenance_hash=_string(
            mapping["membership_provenance_hash"],
            "market_context.membership_provenance_hash",
        ),
        session_id=_string(mapping["session_id"], "market_context.session_id"),
        calendar=cast(
            Literal["XNYS"], _string(mapping["calendar"], "market_context.calendar")
        ),
        session_open=_string(mapping["session_open"], "market_context.session_open"),
        session_close=_string(mapping["session_close"], "market_context.session_close"),
        session_source_uri=_string(
            mapping["session_source_uri"], "market_context.session_source_uri"
        ),
        session_source_hash=_string(
            mapping["session_source_hash"], "market_context.session_source_hash"
        ),
        synthetic=_boolean(mapping["synthetic"], "market_context.synthetic"),
        content_hash=_string(mapping["content_hash"], "market_context.content_hash"),
    )
    validate_decision_market_context(context)
    return context


def _prospective_paper_evidence_from_mapping(value: object) -> ProspectivePaperEvidence:
    mapping = _exact_dataclass_mapping(
        value, ProspectivePaperEvidence, "prospective_paper_evidence"
    )
    return ProspectivePaperEvidence(
        schema_version=cast(
            Literal["dopey-prospective-paper-evidence-v1"],
            _string(mapping["schema_version"], "prospective_evidence.schema_version"),
        ),
        opportunity_id=_string(
            mapping["opportunity_id"], "prospective_evidence.opportunity_id"
        ),
        opportunity_contract_hash=_string(
            mapping["opportunity_contract_hash"],
            "prospective_evidence.opportunity_contract_hash",
        ),
        candidate_id=_string(
            mapping["candidate_id"], "prospective_evidence.candidate_id"
        ),
        candidate_genome_hash=_string(
            mapping["candidate_genome_hash"],
            "prospective_evidence.candidate_genome_hash",
        ),
        environment_hash=_string(
            mapping["environment_hash"], "prospective_evidence.environment_hash"
        ),
        market_context_hash=_string(
            mapping["market_context_hash"],
            "prospective_evidence.market_context_hash",
        ),
        observed_at=_string(mapping["observed_at"], "prospective_evidence.observed_at"),
        dummy_source_artifact_hash=_string(
            mapping["dummy_source_artifact_hash"],
            "prospective_evidence.dummy_source_artifact_hash",
        ),
        quote_source_artifact_hash=_string(
            mapping["quote_source_artifact_hash"],
            "prospective_evidence.quote_source_artifact_hash",
        ),
        exposure_model_artifact_hash=_string(
            mapping["exposure_model_artifact_hash"],
            "prospective_evidence.exposure_model_artifact_hash",
        ),
        complete_cost_model_artifact_hash=_string(
            mapping["complete_cost_model_artifact_hash"],
            "prospective_evidence.complete_cost_model_artifact_hash",
        ),
        fair_value_input_stack_artifact_hash=_string(
            mapping["fair_value_input_stack_artifact_hash"],
            "prospective_evidence.fair_value_input_stack_artifact_hash",
        ),
        corporate_actions_artifact_hash=_string(
            mapping["corporate_actions_artifact_hash"],
            "prospective_evidence.corporate_actions_artifact_hash",
        ),
        dividends_artifact_hash=_string(
            mapping["dividends_artifact_hash"],
            "prospective_evidence.dividends_artifact_hash",
        ),
        rates_artifact_hash=_string(
            mapping["rates_artifact_hash"], "prospective_evidence.rates_artifact_hash"
        ),
        borrow_artifact_hash=_string(
            mapping["borrow_artifact_hash"], "prospective_evidence.borrow_artifact_hash"
        ),
        synthetic=_boolean(mapping["synthetic"], "prospective_evidence.synthetic"),
        paper_only=_boolean(mapping["paper_only"], "prospective_evidence.paper_only"),
        live_blocked=_boolean(
            mapping["live_blocked"], "prospective_evidence.live_blocked"
        ),
        content_hash=_string(
            mapping["content_hash"], "prospective_evidence.content_hash"
        ),
    )


def _candidate_exposure_from_mapping(value: object) -> CandidateExposure:
    mapping = _exact_dataclass_mapping(value, CandidateExposure, "candidate_exposure")
    return CandidateExposure(
        defined_risk=_boolean(
            mapping["defined_risk"], "candidate_exposure.defined_risk"
        ),
        days_to_expiration=_integer(
            mapping["days_to_expiration"],
            "candidate_exposure.days_to_expiration",
        ),
        maximum_loss_fraction=_number(
            mapping["maximum_loss_fraction"],
            "candidate_exposure.maximum_loss_fraction",
        ),
        margin_fraction=_number(
            mapping["margin_fraction"], "candidate_exposure.margin_fraction"
        ),
        expected_shortfall_fraction=_number(
            mapping["expected_shortfall_fraction"],
            "candidate_exposure.expected_shortfall_fraction",
        ),
        ruin_probability=_number(
            mapping["ruin_probability"],
            "candidate_exposure.ruin_probability",
        ),
        delta=_number(mapping["delta"], "candidate_exposure.delta"),
        gamma=_number(mapping["gamma"], "candidate_exposure.gamma"),
        theta=_number(mapping["theta"], "candidate_exposure.theta"),
        vega=_number(mapping["vega"], "candidate_exposure.vega"),
        vanna=_number(mapping["vanna"], "candidate_exposure.vanna"),
        charm=_number(mapping["charm"], "candidate_exposure.charm"),
        vomma=_number(mapping["vomma"], "candidate_exposure.vomma"),
        skew=_number(mapping["skew"], "candidate_exposure.skew"),
        correlation=_number(mapping["correlation"], "candidate_exposure.correlation"),
        event=_number(mapping["event"], "candidate_exposure.event"),
        liquidity=_number(mapping["liquidity"], "candidate_exposure.liquidity"),
        gap=_number(mapping["gap"], "candidate_exposure.gap"),
    )


def _portfolio_state_from_mapping(value: object) -> PortfolioState:
    mapping = _exact_dataclass_mapping(value, PortfolioState, "portfolio_state")
    return PortfolioState(
        daily_loss_fraction=_number(
            mapping["daily_loss_fraction"],
            "portfolio_state.daily_loss_fraction",
        ),
        drawdown_fraction=_number(
            mapping["drawdown_fraction"],
            "portfolio_state.drawdown_fraction",
        ),
        delta=_number(mapping["delta"], "portfolio_state.delta"),
        gamma=_number(mapping["gamma"], "portfolio_state.gamma"),
        theta=_number(mapping["theta"], "portfolio_state.theta"),
        vega=_number(mapping["vega"], "portfolio_state.vega"),
        vanna=_number(mapping["vanna"], "portfolio_state.vanna"),
        charm=_number(mapping["charm"], "portfolio_state.charm"),
        vomma=_number(mapping["vomma"], "portfolio_state.vomma"),
        skew=_number(mapping["skew"], "portfolio_state.skew"),
        correlation=_number(mapping["correlation"], "portfolio_state.correlation"),
        event=_number(mapping["event"], "portfolio_state.event"),
        liquidity=_number(mapping["liquidity"], "portfolio_state.liquidity"),
        gap=_number(mapping["gap"], "portfolio_state.gap"),
    )


def _risk_limits_from_mapping(value: object) -> RiskLimits:
    mapping = _exact_dataclass_mapping(value, RiskLimits, "risk_limits")
    return RiskLimits(
        maximum_position_loss_fraction=_number(
            mapping["maximum_position_loss_fraction"],
            "risk_limits.maximum_position_loss_fraction",
        ),
        maximum_margin_fraction=_number(
            mapping["maximum_margin_fraction"],
            "risk_limits.maximum_margin_fraction",
        ),
        maximum_expected_shortfall_fraction=_number(
            mapping["maximum_expected_shortfall_fraction"],
            "risk_limits.maximum_expected_shortfall_fraction",
        ),
        maximum_ruin_probability=_number(
            mapping["maximum_ruin_probability"],
            "risk_limits.maximum_ruin_probability",
        ),
        maximum_daily_loss_fraction=_number(
            mapping["maximum_daily_loss_fraction"],
            "risk_limits.maximum_daily_loss_fraction",
        ),
        maximum_drawdown_fraction=_number(
            mapping["maximum_drawdown_fraction"],
            "risk_limits.maximum_drawdown_fraction",
        ),
        maximum_absolute_delta=_number(
            mapping["maximum_absolute_delta"],
            "risk_limits.maximum_absolute_delta",
        ),
        maximum_absolute_gamma=_number(
            mapping["maximum_absolute_gamma"],
            "risk_limits.maximum_absolute_gamma",
        ),
        maximum_absolute_theta=_number(
            mapping["maximum_absolute_theta"],
            "risk_limits.maximum_absolute_theta",
        ),
        maximum_absolute_vega=_number(
            mapping["maximum_absolute_vega"],
            "risk_limits.maximum_absolute_vega",
        ),
        maximum_absolute_vanna=_number(
            mapping["maximum_absolute_vanna"],
            "risk_limits.maximum_absolute_vanna",
        ),
        maximum_absolute_charm=_number(
            mapping["maximum_absolute_charm"],
            "risk_limits.maximum_absolute_charm",
        ),
        maximum_absolute_vomma=_number(
            mapping["maximum_absolute_vomma"],
            "risk_limits.maximum_absolute_vomma",
        ),
        maximum_absolute_skew=_number(
            mapping["maximum_absolute_skew"],
            "risk_limits.maximum_absolute_skew",
        ),
        maximum_absolute_correlation=_number(
            mapping["maximum_absolute_correlation"],
            "risk_limits.maximum_absolute_correlation",
        ),
        maximum_absolute_event=_number(
            mapping["maximum_absolute_event"],
            "risk_limits.maximum_absolute_event",
        ),
        maximum_absolute_liquidity=_number(
            mapping["maximum_absolute_liquidity"],
            "risk_limits.maximum_absolute_liquidity",
        ),
        maximum_absolute_gap=_number(
            mapping["maximum_absolute_gap"],
            "risk_limits.maximum_absolute_gap",
        ),
        zero_dte_authorized_for_dedicated_research=_boolean(
            mapping["zero_dte_authorized_for_dedicated_research"],
            "risk_limits.zero_dte_authorized_for_dedicated_research",
        ),
    )


def _behavioral_state_from_mapping(value: object) -> BehavioralState:
    mapping = _exact_dataclass_mapping(value, BehavioralState, "behavioral_state")
    return BehavioralState(
        size_after_loss_ratio=_number(
            mapping["size_after_loss_ratio"],
            "behavioral_state.size_after_loss_ratio",
        ),
        frequency_after_loss_ratio=_number(
            mapping["frequency_after_loss_ratio"],
            "behavioral_state.frequency_after_loss_ratio",
        ),
        abstention_overrides=_integer(
            mapping["abstention_overrides"],
            "behavioral_state.abstention_overrides",
        ),
        fomo_entry=_boolean(mapping["fomo_entry"], "behavioral_state.fomo_entry"),
        loss_limit_changed=_boolean(
            mapping["loss_limit_changed"],
            "behavioral_state.loss_limit_changed",
        ),
        invalidated_position_held=_boolean(
            mapping["invalidated_position_held"],
            "behavioral_state.invalidated_position_held",
        ),
        cooldown_active=_boolean(
            mapping["cooldown_active"],
            "behavioral_state.cooldown_active",
        ),
    )


def _negative_control_result_from_mapping(value: object) -> NegativeControlResult:
    mapping = _exact_dataclass_mapping(
        value, NegativeControlResult, "negative_control_result"
    )
    explanation_value = mapping["explanation_evidence_id"]
    if explanation_value is not None and not isinstance(explanation_value, str):
        raise ValueError(
            "negative control explanation evidence ID must be a string or null"
        )
    return NegativeControlResult(
        control_id=_string(mapping["control_id"], "negative_control.control_id"),
        evaluator_id=_string(mapping["evaluator_id"], "negative_control.evaluator_id"),
        evidence_id=_string(mapping["evidence_id"], "negative_control.evidence_id"),
        observed_absolute_effect=_number(
            mapping["observed_absolute_effect"],
            "negative_control.observed_absolute_effect",
        ),
        maximum_expected_absolute_effect=_number(
            mapping["maximum_expected_absolute_effect"],
            "negative_control.maximum_expected_absolute_effect",
        ),
        completed=_boolean(mapping["completed"], "negative_control.completed"),
        explanation_evidence_id=cast(str | None, explanation_value),
    )


def _quote_snapshot_from_mapping(value: object) -> QuoteSnapshot:
    mapping = _exact_dataclass_mapping(value, QuoteSnapshot, "quote_snapshot")
    return QuoteSnapshot(
        contract_id=_string(mapping["contract_id"], "quote.contract_id"),
        chain_id=_string(mapping["chain_id"], "quote.chain_id"),
        observed_at=_string(mapping["observed_at"], "quote.observed_at"),
        received_at=_string(mapping["received_at"], "quote.received_at"),
        bid=_number(mapping["bid"], "quote.bid"),
        ask=_number(mapping["ask"], "quote.ask"),
        bid_size=_integer(mapping["bid_size"], "quote.bid_size"),
        ask_size=_integer(mapping["ask_size"], "quote.ask_size"),
        last=_number(mapping["last"], "quote.last"),
        volume=_integer(mapping["volume"], "quote.volume"),
        open_interest=_integer(mapping["open_interest"], "quote.open_interest"),
        source_uri=_string(mapping["source_uri"], "quote.source_uri"),
        source_record_hash=_string(
            mapping["source_record_hash"],
            "quote.source_record_hash",
        ),
        content_hash=_string(mapping["content_hash"], "quote.content_hash"),
        venue=_string(mapping["venue"], "quote.venue"),
        quote_condition=cast(
            Literal["regular", "fast", "halted", "nonfirm", "unknown"],
            _string(mapping["quote_condition"], "quote.quote_condition"),
        ),
        evidence_tier=cast(
            Literal[
                "public_snapshot_quote",
                "nbbo_quote",
                "broker_preview",
                "paper_executable_model",
                "realized_fill",
            ],
            _string(mapping["evidence_tier"], "quote.evidence_tier"),
        ),
        chain_complete=_boolean(mapping["chain_complete"], "quote.chain_complete"),
        option_style=cast(
            Literal["american", "european"],
            _string(mapping["option_style"], "quote.option_style"),
        ),
        settlement_type=cast(
            Literal["physical", "cash"],
            _string(mapping["settlement_type"], "quote.settlement_type"),
        ),
        contract_multiplier=_integer(
            mapping["contract_multiplier"],
            "quote.contract_multiplier",
        ),
        deliverable=_string(mapping["deliverable"], "quote.deliverable"),
        adjustment_required=_boolean(
            mapping["adjustment_required"],
            "quote.adjustment_required",
        ),
        adjustment_validated=_boolean(
            mapping["adjustment_validated"],
            "quote.adjustment_validated",
        ),
        underlying=_string(mapping["underlying"], "quote.underlying"),
        option_type=cast(
            Literal["call", "put"],
            _string(mapping["option_type"], "quote.option_type"),
        ),
        expiry=_string(mapping["expiry"], "quote.expiry"),
        strike=_number(mapping["strike"], "quote.strike"),
    )


def _paper_price_request_body(request: PaperPriceRequest) -> dict[str, JsonValue]:
    return {
        "quote": cast(dict[str, JsonValue], asdict(request.quote)),
        "model_fair_value": request.model_fair_value,
        "price_direction": request.price_direction,
        "slippage_basis_points": request.slippage_basis_points,
        "commission_per_contract": request.commission_per_contract,
        "contract_multiplier": request.contract_multiplier,
    }


def _paper_price_request_from_mapping(value: object) -> PaperPriceRequest:
    mapping = _exact_dataclass_mapping(value, PaperPriceRequest, "paper_price_request")
    return PaperPriceRequest(
        quote=_quote_snapshot_from_mapping(mapping["quote"]),
        model_fair_value=_number(
            mapping["model_fair_value"], "price_request.model_fair_value"
        ),
        price_direction=cast(
            PaperPriceDirection,
            _string(mapping["price_direction"], "price_request.price_direction"),
        ),
        slippage_basis_points=_number(
            mapping["slippage_basis_points"],
            "price_request.slippage_basis_points",
        ),
        commission_per_contract=_number(
            mapping["commission_per_contract"],
            "price_request.commission_per_contract",
        ),
        contract_multiplier=_integer(
            mapping["contract_multiplier"],
            "price_request.contract_multiplier",
        ),
    )


def _price_triple_from_mapping(value: object) -> PriceTriple:
    mapping = _exact_dataclass_mapping(value, PriceTriple, "price_triple")
    return PriceTriple(
        contract_id=_string(mapping["contract_id"], "price.contract_id"),
        contract_identity_hash=_string(
            mapping["contract_identity_hash"],
            "price.contract_identity_hash",
        ),
        quote_snapshot=_quote_snapshot_from_mapping(mapping["quote_snapshot"]),
        quote_source_hash=_string(
            mapping["quote_source_hash"], "price.quote_source_hash"
        ),
        quote_content_hash=_string(
            mapping["quote_content_hash"],
            "price.quote_content_hash",
        ),
        quote_gate_hash=_string(mapping["quote_gate_hash"], "price.quote_gate_hash"),
        decision_timestamp=_string(
            mapping["decision_timestamp"],
            "price.decision_timestamp",
        ),
        contract_multiplier=_integer(
            mapping["contract_multiplier"],
            "price.contract_multiplier",
        ),
        observed_midpoint=_number(
            mapping["observed_midpoint"], "price.observed_midpoint"
        ),
        model_fair_value=_number(mapping["model_fair_value"], "price.model_fair_value"),
        conservative_paper_executable=_number(
            mapping["conservative_paper_executable"],
            "price.conservative_paper_executable",
        ),
        price_direction=cast(
            PaperPriceDirection,
            _string(mapping["price_direction"], "price.price_direction"),
        ),
        slippage_basis_points=_number(
            mapping["slippage_basis_points"],
            "price.slippage_basis_points",
        ),
        commission_per_contract=_number(
            mapping["commission_per_contract"],
            "price.commission_per_contract",
        ),
        paper_executable_is_simulated=_boolean(
            mapping["paper_executable_is_simulated"],
            "price.paper_executable_is_simulated",
        ),
        profitability_evidence_eligible=_boolean(
            mapping["profitability_evidence_eligible"],
            "price.profitability_evidence_eligible",
        ),
    )


def _ticket_leg_from_mapping(value: object) -> TicketLegTerms:
    mapping = _exact_dataclass_mapping(value, TicketLegTerms, "ticket_leg")
    return TicketLegTerms(
        content_hash=_string(mapping["content_hash"], "ticket_leg.content_hash"),
        contract_id=_string(mapping["contract_id"], "ticket_leg.contract_id"),
        side=cast(
            Literal["buy", "sell"],
            _string(mapping["side"], "ticket_leg.side"),
        ),
        underlying=_string(mapping["underlying"], "ticket_leg.underlying"),
        option_type=cast(
            Literal["call", "put"],
            _string(mapping["option_type"], "ticket_leg.option_type"),
        ),
        expiry=_string(mapping["expiry"], "ticket_leg.expiry"),
        strike=_number(mapping["strike"], "ticket_leg.strike"),
        quantity=_integer(mapping["quantity"], "ticket_leg.quantity"),
        multiplier=_integer(mapping["multiplier"], "ticket_leg.multiplier"),
        deliverable=_string(mapping["deliverable"], "ticket_leg.deliverable"),
        option_style=cast(
            Literal["american", "european"],
            _string(mapping["option_style"], "ticket_leg.option_style"),
        ),
        settlement_type=cast(
            Literal["physical", "cash"],
            _string(mapping["settlement_type"], "ticket_leg.settlement_type"),
        ),
    )


def _ticket_leg_body(leg: TicketLegTerms) -> dict[str, JsonValue]:
    return {
        "contract_id": leg.contract_id,
        "side": leg.side,
        "underlying": leg.underlying,
        "option_type": leg.option_type,
        "expiry": leg.expiry,
        "strike": leg.strike,
        "quantity": leg.quantity,
        "multiplier": leg.multiplier,
        "deliverable": leg.deliverable,
        "option_style": leg.option_style,
        "settlement_type": leg.settlement_type,
    }


def ticket_leg_content_hash(leg: TicketLegTerms) -> str:
    return canonical_hash(_ticket_leg_body(leg))


def _freeze_ticket_leg(leg: Mapping[str, JsonValue]) -> TicketLegTerms:
    provisional = TicketLegTerms(
        content_hash="0" * 64,
        contract_id=str(leg["contract_id"]),
        side=cast(Literal["buy", "sell"], str(leg["side"])),
        underlying=str(leg["underlying"]),
        option_type=cast(Literal["call", "put"], str(leg["option_type"])),
        expiry=str(leg["expiry"]),
        strike=float(leg["strike"]),
        quantity=int(leg["quantity"]),
        multiplier=int(leg["multiplier"]),
        deliverable=str(leg["deliverable"]),
        option_style=cast(
            Literal["american", "european"],
            str(leg["option_style"]),
        ),
        settlement_type=cast(
            Literal["physical", "cash"],
            str(leg["settlement_type"]),
        ),
    )
    return replace(provisional, content_hash=ticket_leg_content_hash(provisional))


def _quote_leg_mismatch_reasons(
    quote: QuoteSnapshot,
    leg: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    comparisons = (
        ("identity", quote.contract_id, str(leg["contract_id"])),
        ("underlying", quote.underlying, str(leg["underlying"])),
        ("option_type", quote.option_type, str(leg["option_type"])),
        ("expiry", quote.expiry, str(leg["expiry"])),
        ("strike", quote.strike, leg["strike"]),
        ("multiplier", quote.contract_multiplier, int(leg["multiplier"])),
        ("deliverable", quote.deliverable, str(leg["deliverable"])),
        ("option_style", quote.option_style, str(leg["option_style"])),
        ("settlement_type", quote.settlement_type, str(leg["settlement_type"])),
    )
    return tuple(
        f"paper_ticket_contract_{field_name}_mismatch"
        for field_name, observed, expected in comparisons
        if observed != expected
    )


def _calculate_maximum_loss_usd(
    structure_type: str,
    legs: tuple[Mapping[str, JsonValue], ...],
    prices: tuple[PriceTriple, ...],
) -> float:
    net_debit = sum(
        price.conservative_paper_executable
        * int(leg["quantity"])
        * int(leg["multiplier"])
        * (1.0 if leg["side"] == "buy" else -1.0)
        for leg, price in zip(legs, prices, strict=True)
    )
    if all(leg["side"] == "buy" for leg in legs):
        maximum_loss = net_debit
    elif structure_type in {"bull_call_debit_spread", "bear_put_debit_spread"}:
        maximum_loss = net_debit
    elif structure_type in {"bear_call_credit_spread", "bull_put_credit_spread"}:
        width = abs(float(legs[0]["strike"]) - float(legs[1]["strike"]))
        quantity = int(legs[0]["quantity"])
        multiplier = int(legs[0]["multiplier"])
        maximum_loss = width * quantity * multiplier + net_debit
    else:
        raise ValueError(
            f"maximum-loss calculation does not support structure: {structure_type}"
        )
    if not math.isfinite(maximum_loss) or maximum_loss <= 0.0:
        raise ValueError("price-derived maximum loss must be positive and finite")
    return round(maximum_loss, 8)


def paper_execution_ticket_body(ticket: PaperExecutionTicket) -> dict[str, JsonValue]:
    return {
        "opportunity_id": ticket.opportunity_id,
        "opportunity_contract_hash": ticket.opportunity_contract_hash,
        "candidate_id": ticket.candidate_id,
        "candidate_genome_hash": ticket.candidate_genome_hash,
        "candidate_snapshot": ticket.candidate_snapshot,
        "environment_hash": ticket.environment_hash,
        "decision_timestamp": ticket.decision_timestamp,
        "entry_earliest_time": ticket.entry_earliest_time,
        "entry_latest_time": ticket.entry_latest_time,
        "cancellation_deadline": ticket.cancellation_deadline,
        "structure_type": ticket.structure_type,
        "leg_terms": [
            cast(dict[str, JsonValue], asdict(leg)) for leg in ticket.leg_terms
        ],
        "contract_ids": list(ticket.contract_ids),
        "quantities": list(ticket.quantities),
        "price_triples": [
            cast(dict[str, JsonValue], asdict(price)) for price in ticket.price_triples
        ],
        "control_snapshot": ticket.control_snapshot,
        "control_hash": ticket.control_hash,
        "maximum_loss_usd": ticket.maximum_loss_usd,
        "maximum_loss_fraction": ticket.maximum_loss_fraction,
        "invalidation_rule": ticket.invalidation_rule,
        "management_rule": ticket.management_rule,
        "exit_rule": ticket.exit_rule,
        "paper_fill_status": ticket.paper_fill_status,
        "evidence_class": ticket.evidence_class,
        "opportunity_synthetic": ticket.opportunity_synthetic,
        "exposure_model_certified": ticket.exposure_model_certified,
        "complete_cost_model_certified": ticket.complete_cost_model_certified,
        "fair_value_input_stack_certified": ticket.fair_value_input_stack_certified,
        "profitability_evidence_eligible": ticket.profitability_evidence_eligible,
        "market_context_snapshot": ticket.market_context_snapshot,
        "market_context_hash": ticket.market_context_hash,
        "prospective_evidence_snapshot": ticket.prospective_evidence_snapshot,
        "prospective_evidence_hash": ticket.prospective_evidence_hash,
        "paper_only": ticket.paper_only,
        "live_blocked": ticket.live_blocked,
    }


def paper_execution_ticket_id(ticket: PaperExecutionTicket) -> str:
    return f"paper-ticket-{canonical_hash(paper_execution_ticket_body(ticket))[:24]}"


def _require_positive_finite_number(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{field_name} must be positive and finite")
    return normalized


def _reconstruct_candidate_snapshot(
    ticket: PaperExecutionTicket,
) -> tuple[CandidateGenome, DummyOpportunity, tuple[TicketLegTerms, ...]]:
    if not isinstance(ticket.candidate_snapshot, str) or not ticket.candidate_snapshot:
        raise ValueError("paper execution ticket candidate snapshot cannot be empty")
    try:
        decoded = json.loads(ticket.candidate_snapshot)
    except json.JSONDecodeError as error:
        raise ValueError(
            "paper execution ticket candidate snapshot is not valid JSON"
        ) from error
    if not isinstance(decoded, dict):
        raise ValueError("paper execution ticket candidate snapshot must be a mapping")
    snapshot = cast(dict[str, JsonValue], decoded)
    if canonical_json(snapshot) != ticket.candidate_snapshot:
        raise ValueError(
            "paper execution ticket candidate snapshot is not canonical JSON"
        )
    if canonical_hash(snapshot) != ticket.candidate_genome_hash:
        raise ValueError(
            "paper execution ticket candidate snapshot differs from its genome hash"
        )
    if (
        snapshot.get("paper_only") is not True
        or snapshot.get("live_blocked") is not True
    ):
        raise ValueError(
            "paper execution ticket candidate snapshot weakened its authority"
        )
    specification = snapshot.get("specification")
    if not isinstance(specification, dict):
        raise ValueError(
            "paper execution ticket candidate snapshot lacks a specification"
        )
    candidate_id = snapshot.get("candidate_id")
    parent_ids = snapshot.get("parent_ids")
    research_family = snapshot.get("research_family")
    hypothesis = snapshot.get("hypothesis")
    falsification_condition = snapshot.get("falsification_condition")
    candidate_mode = snapshot.get("candidate_mode")
    if (
        not isinstance(candidate_id, str)
        or not isinstance(parent_ids, list)
        or any(not isinstance(parent_id, str) for parent_id in parent_ids)
        or not isinstance(research_family, str)
        or not isinstance(hypothesis, str)
        or not isinstance(falsification_condition, str)
        or candidate_mode not in {"options_expression", "abstention_policy"}
    ):
        raise ValueError(
            "paper execution ticket candidate snapshot identity is malformed"
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
    validate_candidate_genome(candidate)
    if candidate.candidate_id != ticket.candidate_id:
        raise ValueError("paper execution ticket candidate snapshot identity mismatch")
    if candidate.genome_hash != ticket.candidate_genome_hash:
        raise ValueError("paper execution ticket candidate hash is not reproducible")
    structure = _mapping(candidate.specification["structure"], "structure")
    dummy_contract = candidate_dummy_contract(candidate)
    reproducibility = _mapping(
        candidate.specification["reproducibility"], "reproducibility"
    )
    if structure.get("type") != ticket.structure_type:
        raise ValueError(
            "paper execution ticket structure differs from its candidate snapshot"
        )
    if reproducibility.get("environment_hash") != ticket.environment_hash:
        raise ValueError(
            "paper execution ticket environment differs from its candidate snapshot"
        )
    dummy = create_dummy_opportunity(
        str(dummy_contract["creation_timestamp"]),
        str(dummy_contract["underlying"]),
        str(dummy_contract["forecast"]),
        str(dummy_contract["intended_horizon"]),
        float(dummy_contract["confidence"]),
        float(dummy_contract["maximum_exposure_fraction"]),
        str(dummy_contract["expiration_timestamp"]),
        str(dummy_contract["upstream_version"]),
        str(dummy_contract["provenance_hash"]),
        cast(bool, dummy_contract["synthetic"]),
    )
    validate_dummy_opportunity(dummy)
    expected_dummy_contract = cast(dict[str, object], asdict(dummy))
    if dict(dummy_contract) != expected_dummy_contract:
        raise ValueError(
            "paper execution ticket embedded Dummy contract is not reproducible"
        )
    if (
        dummy.opportunity_id != ticket.opportunity_id
        or dummy.contract_hash != ticket.opportunity_contract_hash
        or ticket.opportunity_synthetic is not dummy.synthetic
    ):
        raise ValueError(
            "paper execution ticket opportunity differs from its candidate snapshot"
        )
    leg_terms = tuple(
        _freeze_ticket_leg(leg) for leg in candidate_option_legs(candidate)
    )
    return candidate, dummy, leg_terms


def _reconstruct_ticket_controls(
    ticket: PaperExecutionTicket | AbstentionRecord,
    require_passing_gates: bool,
) -> DecisionControlInputs:
    if not isinstance(ticket.control_snapshot, str) or not ticket.control_snapshot:
        raise ValueError("paper execution ticket control snapshot cannot be empty")
    try:
        decoded = json.loads(ticket.control_snapshot)
    except json.JSONDecodeError as error:
        raise ValueError(
            "paper execution ticket control snapshot is not valid JSON"
        ) from error
    if not isinstance(decoded, dict):
        raise ValueError("paper execution ticket control snapshot must be a mapping")
    snapshot = cast(dict[str, JsonValue], decoded)
    expected_fields = {
        "schema_version",
        "candidate_id",
        "candidate_genome_hash",
        "opportunity_id",
        "decision_timestamp",
        "environment_hash",
        "candidate_exposure",
        "portfolio_state",
        "risk_limits",
        "behavioral_state",
        "negative_control_results",
        "required_negative_control_ids",
        "candidate_author_id",
        "paper_only",
        "live_blocked",
    }
    if set(snapshot) != expected_fields:
        raise ValueError(
            "paper execution ticket control snapshot fields differ from its schema"
        )
    if canonical_json(snapshot) != ticket.control_snapshot:
        raise ValueError(
            "paper execution ticket control snapshot is not canonical JSON"
        )
    if canonical_hash(snapshot) != ticket.control_hash:
        raise ValueError("paper execution ticket control snapshot hash mismatch")
    expected_bindings: dict[str, JsonValue] = {
        "schema_version": "dopey-paper-ticket-control-v1",
        "candidate_id": ticket.candidate_id,
        "candidate_genome_hash": ticket.candidate_genome_hash,
        "opportunity_id": ticket.opportunity_id,
        "decision_timestamp": ticket.decision_timestamp,
        "environment_hash": ticket.environment_hash,
        "paper_only": True,
        "live_blocked": True,
    }
    if any(snapshot.get(key) != value for key, value in expected_bindings.items()):
        raise ValueError(
            "paper execution ticket control snapshot identity or authority mismatch"
        )
    raw_results = _sequence(
        snapshot["negative_control_results"],
        "control_snapshot.negative_control_results",
    )
    negative_control_results = tuple(
        _negative_control_result_from_mapping(result) for result in raw_results
    )
    observed_control_ids = tuple(
        result.control_id for result in negative_control_results
    )
    if observed_control_ids != tuple(sorted(observed_control_ids)):
        raise ValueError(
            "paper execution ticket negative controls must be sorted by control ID"
        )
    raw_required_ids = _sequence(
        snapshot["required_negative_control_ids"],
        "control_snapshot.required_negative_control_ids",
    )
    required_ids = tuple(
        _string(control_id, "control_snapshot.required_negative_control_ids[]")
        for control_id in raw_required_ids
    )
    if required_ids != tuple(sorted(set(required_ids))) or not required_ids:
        raise ValueError(
            "paper execution ticket required negative-control IDs must be nonempty, unique, and sorted"
        )
    controls = DecisionControlInputs(
        environment_hash=_string(
            snapshot["environment_hash"],
            "control_snapshot.environment_hash",
        ),
        candidate_exposure=_candidate_exposure_from_mapping(
            snapshot["candidate_exposure"],
        ),
        portfolio_state=_portfolio_state_from_mapping(snapshot["portfolio_state"]),
        risk_limits=_risk_limits_from_mapping(snapshot["risk_limits"]),
        behavioral_state=_behavioral_state_from_mapping(snapshot["behavioral_state"]),
        negative_control_results=negative_control_results,
        required_negative_control_ids=frozenset(required_ids),
        candidate_author_id=_string(
            snapshot["candidate_author_id"],
            "control_snapshot.candidate_author_id",
        ),
    )
    if controls.risk_limits != v1_risk_limits():
        raise ValueError(
            "paper execution ticket control snapshot weakened environment-v1 limits"
        )
    if controls.required_negative_control_ids != V1_REQUIRED_NEGATIVE_CONTROL_IDS:
        raise ValueError(
            "paper execution ticket controls weakened canonical negative controls"
        )
    require_v1_environment_hash(controls.environment_hash)
    risk_gate = evaluate_risk_gate(
        controls.candidate_exposure,
        controls.portfolio_state,
        controls.risk_limits,
    )
    if require_passing_gates and not risk_gate.passed:
        raise ValueError(
            "paper execution ticket control snapshot failed its frozen risk gate: "
            f"reasons={risk_gate.reason_codes}"
        )
    behavioral_gate = evaluate_behavioral_gate(controls.behavioral_state)
    if require_passing_gates and not behavioral_gate.passed:
        raise ValueError(
            "paper execution ticket control snapshot failed its behavioral firewall: "
            f"reasons={behavioral_gate.reason_codes}"
        )
    negative_control_gate = evaluate_negative_controls(
        controls.negative_control_results,
        controls.required_negative_control_ids,
        controls.candidate_author_id,
    )
    if require_passing_gates and not negative_control_gate.passed:
        raise ValueError(
            "paper execution ticket control snapshot failed negative controls: "
            f"reasons={negative_control_gate.reason_codes}"
        )
    return controls


def validate_paper_execution_ticket(ticket: PaperExecutionTicket) -> None:
    if ticket.paper_only is not True or ticket.live_blocked is not True:
        raise ValueError("paper execution ticket weakened its authority boundary")
    if ticket.paper_fill_status != "pending_later_quote_witness":
        raise ValueError("paper execution ticket has an invalid initial fill state")
    if ticket.evidence_class not in {
        "synthetic_mechanics_only",
        "prospective_market_evidence",
    }:
        raise ValueError("paper execution ticket has an unsupported evidence class")
    synthetic_ticket = ticket.evidence_class == "synthetic_mechanics_only"
    certification_state = (
        ticket.exposure_model_certified,
        ticket.complete_cost_model_certified,
        ticket.fair_value_input_stack_certified,
    )
    if synthetic_ticket and ticket.opportunity_synthetic is not True:
        raise ValueError(
            "synthetic mechanics ticket changed its opportunity evidence class"
        )
    if not synthetic_ticket and ticket.opportunity_synthetic is not False:
        raise ValueError(
            "prospective paper ticket changed its opportunity evidence class"
        )
    if any(certification_state) or ticket.profitability_evidence_eligible is not False:
        raise ValueError(
            "local paper ticket cannot self-certify inputs or profitability evidence"
        )
    if not ticket.opportunity_id or not ticket.candidate_id:
        raise ValueError("paper execution ticket identity fields cannot be empty")
    require_utc_iso(ticket.decision_timestamp)
    require_utc_iso(ticket.entry_earliest_time)
    require_utc_iso(ticket.entry_latest_time)
    require_utc_iso(ticket.cancellation_deadline)
    decision_time = parse_utc(ticket.decision_timestamp)
    entry_earliest = parse_utc(ticket.entry_earliest_time)
    entry_latest = parse_utc(ticket.entry_latest_time)
    cancellation_deadline = parse_utc(ticket.cancellation_deadline)
    if not decision_time <= entry_earliest < cancellation_deadline <= entry_latest:
        raise ValueError(
            "paper execution ticket timestamps violate the frozen causal order"
        )
    require_sha256(ticket.opportunity_contract_hash, "ticket.opportunity_contract_hash")
    require_sha256(ticket.candidate_genome_hash, "ticket.candidate_genome_hash")
    require_v1_environment_hash(ticket.environment_hash)
    require_sha256(ticket.control_hash, "ticket.control_hash")
    candidate, dummy, snapshot_leg_terms = _reconstruct_candidate_snapshot(ticket)
    if candidate.candidate_mode != "options_expression":
        raise ValueError("abstention-policy candidate cannot issue an options ticket")
    if (
        ticket.invalidation_rule,
        ticket.management_rule,
        ticket.exit_rule,
    ) != candidate_lifecycle_rules(candidate):
        raise ValueError(
            "paper execution ticket lifecycle differs from its frozen candidate"
        )
    raw_context = _parse_optional_artifact_snapshot(
        ticket.market_context_snapshot,
        ticket.market_context_hash,
        "market_context",
    )
    if raw_context is None:
        raise ValueError(
            "paper execution ticket requires a point-in-time market context"
        )
    market_context = _decision_market_context_from_mapping(raw_context)
    if market_context.synthetic is not dummy.synthetic:
        raise ValueError(
            "ticket market context synthetic class differs from its Dummy opportunity"
        )
    context_reasons = _market_context_reasons(
        market_context,
        dummy,
        ticket.decision_timestamp,
        ticket.entry_earliest_time,
        ticket.cancellation_deadline,
        ticket.entry_latest_time,
    )
    if context_reasons:
        raise ValueError(
            f"paper execution ticket failed market context: reasons={context_reasons}"
        )
    raw_prospective = _parse_optional_artifact_snapshot(
        ticket.prospective_evidence_snapshot,
        ticket.prospective_evidence_hash,
        "prospective_evidence",
    )
    if synthetic_ticket:
        if raw_prospective is not None:
            raise ValueError(
                "synthetic mechanics ticket cannot embed prospective evidence"
            )
    else:
        if raw_prospective is None:
            raise ValueError(
                "prospective paper ticket requires complete provenance evidence"
            )
        prospective_evidence = _prospective_paper_evidence_from_mapping(raw_prospective)
        validate_prospective_paper_evidence(
            prospective_evidence,
            dummy,
            candidate,
            market_context,
        )
        if parse_utc(prospective_evidence.observed_at) > parse_utc(
            ticket.decision_timestamp
        ):
            raise ValueError(
                "prospective evidence was not available at the paper decision"
            )
    if not ticket.structure_type:
        raise ValueError("paper execution ticket structure type cannot be empty")
    cardinalities = {
        len(ticket.leg_terms),
        len(ticket.contract_ids),
        len(ticket.quantities),
        len(ticket.price_triples),
    }
    if cardinalities != {len(ticket.contract_ids)} or not ticket.contract_ids:
        raise ValueError(
            "paper execution ticket leg collections must be nonempty and equal length"
        )
    if ticket.leg_terms != snapshot_leg_terms:
        raise ValueError(
            "paper execution ticket legs differ from its candidate snapshot"
        )
    if any(not contract_id for contract_id in ticket.contract_ids):
        raise ValueError("paper execution ticket contract IDs cannot be empty")
    if len(ticket.contract_ids) != len(set(ticket.contract_ids)):
        raise ValueError("paper execution ticket contract IDs must be unique")
    if any(
        not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0
        for quantity in ticket.quantities
    ):
        raise ValueError("paper execution ticket quantities must be positive integers")
    if (
        not ticket.invalidation_rule
        or not ticket.management_rule
        or not ticket.exit_rule
    ):
        raise ValueError("paper execution ticket requires explicit lifecycle rules")
    leg_mappings = tuple(_ticket_leg_body(leg) for leg in ticket.leg_terms)
    validate_exact_defined_risk_topology(
        ticket.structure_type,
        [dict(leg) for leg in leg_mappings],
    )
    for contract_id, quantity, leg, price in zip(
        ticket.contract_ids,
        ticket.quantities,
        ticket.leg_terms,
        ticket.price_triples,
        strict=True,
    ):
        require_sha256(leg.content_hash, "ticket.leg.content_hash")
        if leg.content_hash != ticket_leg_content_hash(leg):
            raise ValueError("paper execution ticket leg content hash is invalid")
        if contract_id != leg.contract_id or quantity != leg.quantity:
            raise ValueError("paper execution ticket redundant leg identities disagree")
        if price.contract_id != leg.contract_id:
            raise ValueError(
                "paper execution ticket price identity differs from its leg"
            )
        expected_contract_identity_hash = contract_identity_hash(
            leg.contract_id,
            leg.underlying,
            leg.option_type,
            leg.expiry,
            leg.strike,
            leg.multiplier,
            leg.deliverable,
            leg.option_style,
            leg.settlement_type,
        )
        if price.contract_identity_hash != expected_contract_identity_hash:
            raise ValueError(
                "paper execution ticket price semantic identity differs from its leg"
            )
        expected_direction = "debit" if leg.side == "buy" else "credit"
        if price.price_direction != expected_direction:
            raise ValueError(
                "paper execution ticket price direction differs from its leg side"
            )
        if price.contract_multiplier != leg.multiplier:
            raise ValueError(
                "paper execution ticket price multiplier differs from its leg"
            )
        if price.decision_timestamp != ticket.decision_timestamp:
            raise ValueError(
                "paper execution ticket contains a price from another decision time"
            )
        if price.slippage_basis_points != 25.0 or price.commission_per_contract != 0.65:
            raise ValueError(
                "paper execution ticket price costs differ from environment v1"
            )
        if price.paper_executable_is_simulated is not True:
            raise ValueError(
                "paper execution ticket price must remain explicitly simulated"
            )
        if price.profitability_evidence_eligible is not False:
            raise ValueError(
                "paper execution ticket price cannot be profitability evidence"
            )
        quote_observed = parse_utc(price.quote_snapshot.observed_at)
        quote_received = parse_utc(price.quote_snapshot.received_at)
        if not (
            parse_utc(market_context.session_open)
            <= quote_observed
            <= quote_received
            <= parse_utc(ticket.decision_timestamp)
            < parse_utc(market_context.session_close)
        ):
            raise ValueError(
                "paper execution ticket quote is outside its frozen XNYS session"
            )
        reconstructed_price = build_price_triple(
            price.quote_snapshot,
            ticket.decision_timestamp,
            v1_quote_gate_policy(),
            price.model_fair_value,
            price.price_direction,
            price.slippage_basis_points,
            price.commission_per_contract,
            price.contract_multiplier,
        )
        if reconstructed_price != price:
            raise ValueError(
                "paper execution ticket price triple is not mechanically reproducible"
            )
    maximum_loss_usd = _require_positive_finite_number(
        ticket.maximum_loss_usd,
        "ticket.maximum_loss_usd",
    )
    maximum_loss_fraction = _require_positive_finite_number(
        ticket.maximum_loss_fraction,
        "ticket.maximum_loss_fraction",
    )
    reconstructed_maximum_loss_usd = _calculate_maximum_loss_usd(
        ticket.structure_type,
        leg_mappings,
        ticket.price_triples,
    )
    if maximum_loss_usd != reconstructed_maximum_loss_usd:
        raise ValueError(
            "paper execution ticket maximum loss is not price-and-leg derived"
        )
    reconstructed_maximum_loss_fraction = round(
        reconstructed_maximum_loss_usd / V1_PAPER_BANKROLL_USD,
        12,
    )
    if maximum_loss_fraction != reconstructed_maximum_loss_fraction:
        raise ValueError("paper execution ticket maximum-loss fields are inconsistent")
    if maximum_loss_fraction > 1.0:
        raise ValueError(
            "paper execution ticket maximum-loss fraction cannot exceed one"
        )
    candidate_structure = _mapping(candidate.specification["structure"], "structure")
    declared_maximum_loss = _require_positive_finite_number(
        candidate_structure["maximum_loss"],
        "candidate.structure.maximum_loss",
    )
    if reconstructed_maximum_loss_usd > declared_maximum_loss:
        raise ValueError(
            "paper execution ticket maximum loss exceeds its candidate cap"
        )
    if reconstructed_maximum_loss_fraction > dummy.maximum_exposure_fraction:
        raise ValueError(
            "paper execution ticket maximum loss exceeds its Dummy exposure cap"
        )
    controls = _reconstruct_ticket_controls(ticket, True)
    candidate_limit_reasons = _candidate_limit_reasons(candidate, controls)
    if candidate_limit_reasons:
        raise ValueError(
            "paper execution ticket weakened frozen candidate limits: "
            f"reasons={candidate_limit_reasons}"
        )
    if not math.isclose(
        controls.candidate_exposure.maximum_loss_fraction,
        reconstructed_maximum_loss_fraction,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "paper execution ticket control exposure is not derived from its maximum loss"
        )
    if not math.isclose(
        controls.candidate_exposure.margin_fraction,
        reconstructed_maximum_loss_fraction,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "paper execution ticket control margin is not derived from its defined risk"
        )
    expected_dte = min(
        (
            date.fromisoformat(leg.expiry) - parse_utc(ticket.decision_timestamp).date()
        ).days
        for leg in ticket.leg_terms
    )
    if controls.candidate_exposure.days_to_expiration != expected_dte:
        raise ValueError(
            "paper execution ticket control DTE is not derived from its legs"
        )
    if ticket.ticket_id != paper_execution_ticket_id(ticket):
        raise ValueError(
            "paper execution ticket identity does not match its immutable content"
        )


def paper_execution_ticket_to_mapping(
    ticket: PaperExecutionTicket,
) -> dict[str, JsonValue]:
    validate_paper_execution_ticket(ticket)
    return cast(dict[str, JsonValue], asdict(ticket))


def paper_execution_ticket_from_mapping(
    value: Mapping[str, object],
) -> PaperExecutionTicket:
    mapping = _exact_dataclass_mapping(
        value, PaperExecutionTicket, "paper_execution_ticket"
    )
    raw_leg_terms = _sequence(mapping["leg_terms"], "ticket.leg_terms")
    raw_contract_ids = _sequence(mapping["contract_ids"], "ticket.contract_ids")
    raw_quantities = _sequence(mapping["quantities"], "ticket.quantities")
    raw_prices = _sequence(mapping["price_triples"], "ticket.price_triples")
    ticket = PaperExecutionTicket(
        ticket_id=_string(mapping["ticket_id"], "ticket.ticket_id"),
        opportunity_id=_string(mapping["opportunity_id"], "ticket.opportunity_id"),
        opportunity_contract_hash=_string(
            mapping["opportunity_contract_hash"],
            "ticket.opportunity_contract_hash",
        ),
        candidate_id=_string(mapping["candidate_id"], "ticket.candidate_id"),
        candidate_genome_hash=_string(
            mapping["candidate_genome_hash"],
            "ticket.candidate_genome_hash",
        ),
        candidate_snapshot=_string(
            mapping["candidate_snapshot"],
            "ticket.candidate_snapshot",
        ),
        environment_hash=_string(
            mapping["environment_hash"], "ticket.environment_hash"
        ),
        decision_timestamp=_string(
            mapping["decision_timestamp"],
            "ticket.decision_timestamp",
        ),
        entry_earliest_time=_string(
            mapping["entry_earliest_time"],
            "ticket.entry_earliest_time",
        ),
        entry_latest_time=_string(
            mapping["entry_latest_time"],
            "ticket.entry_latest_time",
        ),
        cancellation_deadline=_string(
            mapping["cancellation_deadline"],
            "ticket.cancellation_deadline",
        ),
        structure_type=_string(mapping["structure_type"], "ticket.structure_type"),
        leg_terms=tuple(_ticket_leg_from_mapping(leg) for leg in raw_leg_terms),
        contract_ids=tuple(
            _string(contract_id, "ticket.contract_ids[]")
            for contract_id in raw_contract_ids
        ),
        quantities=tuple(
            _integer(quantity, "ticket.quantities[]") for quantity in raw_quantities
        ),
        price_triples=tuple(_price_triple_from_mapping(price) for price in raw_prices),
        control_snapshot=_string(
            mapping["control_snapshot"],
            "ticket.control_snapshot",
        ),
        control_hash=_string(mapping["control_hash"], "ticket.control_hash"),
        maximum_loss_usd=_number(
            mapping["maximum_loss_usd"],
            "ticket.maximum_loss_usd",
        ),
        maximum_loss_fraction=_number(
            mapping["maximum_loss_fraction"],
            "ticket.maximum_loss_fraction",
        ),
        invalidation_rule=_string(
            mapping["invalidation_rule"],
            "ticket.invalidation_rule",
        ),
        management_rule=_string(mapping["management_rule"], "ticket.management_rule"),
        exit_rule=_string(mapping["exit_rule"], "ticket.exit_rule"),
        paper_fill_status=cast(
            Literal["pending_later_quote_witness"],
            _string(mapping["paper_fill_status"], "ticket.paper_fill_status"),
        ),
        evidence_class=cast(
            Literal["synthetic_mechanics_only", "prospective_market_evidence"],
            _string(mapping["evidence_class"], "ticket.evidence_class"),
        ),
        opportunity_synthetic=_boolean(
            mapping["opportunity_synthetic"],
            "ticket.opportunity_synthetic",
        ),
        exposure_model_certified=_boolean(
            mapping["exposure_model_certified"],
            "ticket.exposure_model_certified",
        ),
        complete_cost_model_certified=_boolean(
            mapping["complete_cost_model_certified"],
            "ticket.complete_cost_model_certified",
        ),
        fair_value_input_stack_certified=_boolean(
            mapping["fair_value_input_stack_certified"],
            "ticket.fair_value_input_stack_certified",
        ),
        profitability_evidence_eligible=_boolean(
            mapping["profitability_evidence_eligible"],
            "ticket.profitability_evidence_eligible",
        ),
        market_context_snapshot=_string(
            mapping["market_context_snapshot"],
            "ticket.market_context_snapshot",
        ),
        market_context_hash=_string(
            mapping["market_context_hash"],
            "ticket.market_context_hash",
        ),
        prospective_evidence_snapshot=_string(
            mapping["prospective_evidence_snapshot"],
            "ticket.prospective_evidence_snapshot",
        ),
        prospective_evidence_hash=_string(
            mapping["prospective_evidence_hash"],
            "ticket.prospective_evidence_hash",
        ),
        paper_only=_boolean(mapping["paper_only"], "ticket.paper_only"),
        live_blocked=_boolean(mapping["live_blocked"], "ticket.live_blocked"),
    )
    validate_paper_execution_ticket(ticket)
    return ticket


def paper_fill_observation_body(
    observation: PaperFillObservation,
) -> dict[str, JsonValue]:
    return {
        "ticket_id": observation.ticket_id,
        "witnessed_at": observation.witnessed_at,
        "contract_ids": list(observation.contract_ids),
        "conservative_prices": list(observation.conservative_prices),
        "witness_hashes": list(observation.witness_hashes),
        "witness_quotes": [
            cast(dict[str, JsonValue], asdict(quote))
            for quote in observation.witness_quotes
        ],
        "paper_fill_status": observation.paper_fill_status,
        "reason_codes": list(observation.reason_codes),
        "evidence_class": observation.evidence_class,
        "profitability_evidence_eligible": observation.profitability_evidence_eligible,
        "realized_evidence": observation.realized_evidence,
        "paper_only": observation.paper_only,
        "live_blocked": observation.live_blocked,
    }


def paper_fill_observation_id(observation: PaperFillObservation) -> str:
    return f"paper-fill-{canonical_hash(paper_fill_observation_body(observation))[:24]}"


def _paper_fill_outcome(
    ticket: PaperExecutionTicket,
    later_quotes: tuple[QuoteSnapshot, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    if not later_quotes:
        return (
            ("no_quote_witness_before_deadline",),
            (),
            ticket.cancellation_deadline,
        )
    raw_context = _parse_optional_artifact_snapshot(
        ticket.market_context_snapshot,
        ticket.market_context_hash,
        "market_context",
    )
    if raw_context is None:
        raise ValueError("paper fill ticket lacks its market context")
    market_context = _decision_market_context_from_mapping(raw_context)
    reasons: list[str] = []
    hashes: list[str] = []
    receipt_times: list[datetime] = []
    if len(later_quotes) != len(ticket.contract_ids):
        reasons.append("witness_leg_cardinality_mismatch")
    for index, quote in enumerate(later_quotes):
        validate_quote_snapshot_identity(quote)
        hashes.append(quote.content_hash)
        observed = parse_utc(quote.observed_at)
        received = parse_utc(quote.received_at)
        receipt_times.append(received)
        gate = evaluate_quote_gate(quote, quote.received_at, v1_quote_gate_policy())
        reasons.extend(f"witness_{reason}" for reason in gate.reason_codes)
        if index >= len(ticket.contract_ids):
            reasons.append("witness_unexpected_contract")
            continue
        contract_id = ticket.contract_ids[index]
        quantity = ticket.quantities[index]
        price = ticket.price_triples[index]
        if quote.contract_id != contract_id:
            reasons.append("witness_contract_identity_mismatch")
        if quote_contract_identity_hash(quote) != price.contract_identity_hash:
            reasons.append("witness_contract_terms_mismatch")
        if observed <= parse_utc(ticket.decision_timestamp):
            reasons.append("witness_not_after_decision")
        if not (
            parse_utc(ticket.entry_earliest_time)
            <= observed
            <= received
            <= parse_utc(ticket.cancellation_deadline)
            <= parse_utc(ticket.entry_latest_time)
        ):
            reasons.append("witness_outside_entry_or_cancel_window")
        if not (
            parse_utc(market_context.session_open)
            <= observed
            <= received
            < parse_utc(market_context.session_close)
        ):
            reasons.append("witness_outside_xnys_session")
        if price.price_direction == "debit":
            if quote.ask_size < quantity:
                reasons.append("witness_displayed_size_below_quantity")
            if quote.ask > price.conservative_paper_executable:
                reasons.append("witness_limit_not_crossed")
        else:
            if quote.bid_size < quantity:
                reasons.append("witness_displayed_size_below_quantity")
            if quote.bid < price.conservative_paper_executable:
                reasons.append("witness_limit_not_crossed")
    package_skew_seconds = (max(receipt_times) - min(receipt_times)).total_seconds()
    if package_skew_seconds > 1.0:
        reasons.append("witness_package_skew_above_limit")
    witnessed_at = max(
        later_quotes, key=lambda quote: parse_utc(quote.received_at)
    ).received_at
    return tuple(sorted(set(reasons))), tuple(hashes), witnessed_at


def validate_paper_fill_observation(
    observation: PaperFillObservation,
    ticket: PaperExecutionTicket,
) -> None:
    validate_paper_execution_ticket(ticket)
    if observation.ticket_id != ticket.ticket_id:
        raise ValueError("paper fill observation is not bound to the supplied ticket")
    if observation.paper_only is not True or observation.live_blocked is not True:
        raise ValueError("paper fill observation weakened its authority boundary")
    if observation.evidence_class != ticket.evidence_class:
        raise ValueError(
            "paper fill observation evidence class differs from its ticket"
        )
    if (
        observation.profitability_evidence_eligible
        is not ticket.profitability_evidence_eligible
    ):
        raise ValueError(
            "paper fill observation profitability eligibility differs from its ticket"
        )
    if observation.realized_evidence is not False:
        raise ValueError("paper fill observation cannot claim realized evidence")
    if observation.paper_fill_status not in {"filled", "missed"}:
        raise ValueError("paper fill observation has an invalid status")
    require_utc_iso(observation.witnessed_at)
    if observation.contract_ids != ticket.contract_ids:
        raise ValueError(
            "paper fill observation contract identities differ from the ticket"
        )
    expected_reasons, expected_hashes, expected_witnessed_at = _paper_fill_outcome(
        ticket,
        observation.witness_quotes,
    )
    if observation.witness_hashes != expected_hashes:
        raise ValueError("paper fill observation witness hashes are not quote-derived")
    if observation.witnessed_at != expected_witnessed_at:
        raise ValueError("paper fill observation time differs from its latest witness")
    if observation.reason_codes != expected_reasons:
        raise ValueError(
            "paper fill observation reason codes are not mechanically reproducible"
        )
    expected_status = "filled" if not expected_reasons else "missed"
    if observation.paper_fill_status != expected_status:
        raise ValueError(
            "paper fill observation status differs from later-witness mechanics"
        )
    expected_prices = tuple(
        price.conservative_paper_executable for price in ticket.price_triples
    )
    if expected_status == "filled":
        if observation.conservative_prices != expected_prices:
            raise ValueError(
                "filled paper observation prices differ from the frozen ticket"
            )
    elif observation.conservative_prices:
        raise ValueError("missed paper observation cannot contain executable prices")
    if observation.observation_id != paper_fill_observation_id(observation):
        raise ValueError(
            "paper fill observation identity does not match its immutable content"
        )


def paper_fill_observation_to_mapping(
    observation: PaperFillObservation,
    ticket: PaperExecutionTicket,
) -> dict[str, JsonValue]:
    validate_paper_fill_observation(observation, ticket)
    return cast(dict[str, JsonValue], asdict(observation))


def paper_fill_observation_from_mapping(
    value: Mapping[str, object],
    ticket: PaperExecutionTicket,
) -> PaperFillObservation:
    mapping = _exact_dataclass_mapping(
        value, PaperFillObservation, "paper_fill_observation"
    )
    observation = PaperFillObservation(
        observation_id=_string(mapping["observation_id"], "fill.observation_id"),
        ticket_id=_string(mapping["ticket_id"], "fill.ticket_id"),
        witnessed_at=_string(mapping["witnessed_at"], "fill.witnessed_at"),
        contract_ids=tuple(
            _string(contract_id, "fill.contract_ids[]")
            for contract_id in _sequence(mapping["contract_ids"], "fill.contract_ids")
        ),
        conservative_prices=tuple(
            _number(price, "fill.conservative_prices[]")
            for price in _sequence(
                mapping["conservative_prices"],
                "fill.conservative_prices",
            )
        ),
        witness_hashes=tuple(
            _string(witness_hash, "fill.witness_hashes[]")
            for witness_hash in _sequence(
                mapping["witness_hashes"], "fill.witness_hashes"
            )
        ),
        witness_quotes=tuple(
            _quote_snapshot_from_mapping(quote)
            for quote in _sequence(mapping["witness_quotes"], "fill.witness_quotes")
        ),
        paper_fill_status=cast(
            Literal["filled", "missed"],
            _string(mapping["paper_fill_status"], "fill.paper_fill_status"),
        ),
        reason_codes=tuple(
            _string(reason, "fill.reason_codes[]")
            for reason in _sequence(mapping["reason_codes"], "fill.reason_codes")
        ),
        evidence_class=cast(
            Literal["synthetic_mechanics_only", "prospective_market_evidence"],
            _string(mapping["evidence_class"], "fill.evidence_class"),
        ),
        profitability_evidence_eligible=_boolean(
            mapping["profitability_evidence_eligible"],
            "fill.profitability_evidence_eligible",
        ),
        realized_evidence=_boolean(
            mapping["realized_evidence"], "fill.realized_evidence"
        ),
        paper_only=_boolean(mapping["paper_only"], "fill.paper_only"),
        live_blocked=_boolean(mapping["live_blocked"], "fill.live_blocked"),
    )
    validate_paper_fill_observation(observation, ticket)
    return observation


def _reconstruct_abstention_candidate(
    record: AbstentionRecord,
) -> tuple[CandidateGenome, DummyOpportunity]:
    try:
        decoded_candidate = json.loads(record.candidate_snapshot)
        decoded_opportunity = json.loads(record.opportunity_snapshot)
    except json.JSONDecodeError as error:
        raise ValueError(
            "abstention candidate or opportunity snapshot is invalid JSON"
        ) from error
    if not isinstance(decoded_candidate, dict) or not isinstance(
        decoded_opportunity, dict
    ):
        raise ValueError(
            "abstention candidate and opportunity snapshots must be mappings"
        )
    candidate_mapping = cast(dict[str, object], decoded_candidate)
    if canonical_json(cast(JsonValue, decoded_candidate)) != record.candidate_snapshot:
        raise ValueError("abstention candidate snapshot is not canonical JSON")
    if (
        canonical_hash(cast(JsonValue, decoded_candidate))
        != record.candidate_genome_hash
    ):
        raise ValueError("abstention candidate snapshot differs from its genome hash")
    expected_candidate_fields = {
        "candidate_id",
        "parent_ids",
        "research_family",
        "hypothesis",
        "falsification_condition",
        "candidate_mode",
        "specification",
        "paper_only",
        "live_blocked",
    }
    if set(candidate_mapping) != expected_candidate_fields:
        raise ValueError("abstention candidate snapshot differs from its exact schema")
    parent_ids = _sequence(candidate_mapping["parent_ids"], "candidate.parent_ids")
    candidate_mode = _string(
        candidate_mapping["candidate_mode"], "candidate.candidate_mode"
    )
    if candidate_mode not in {"options_expression", "abstention_policy"}:
        raise ValueError("abstention candidate snapshot has an invalid candidate_mode")
    specification = _mapping(
        candidate_mapping["specification"], "candidate.specification"
    )
    candidate = create_candidate_genome(
        _string(candidate_mapping["candidate_id"], "candidate.candidate_id"),
        tuple(_string(parent_id, "candidate.parent_ids[]") for parent_id in parent_ids),
        _string(candidate_mapping["research_family"], "candidate.research_family"),
        _string(candidate_mapping["hypothesis"], "candidate.hypothesis"),
        _string(
            candidate_mapping["falsification_condition"],
            "candidate.falsification_condition",
        ),
        cast(Literal["options_expression", "abstention_policy"], candidate_mode),
        cast(dict[str, JsonValue], specification),
    )
    if (
        candidate.candidate_id != record.candidate_id
        or candidate.genome_hash != record.candidate_genome_hash
        or candidate.candidate_mode != record.candidate_mode
    ):
        raise ValueError("abstention candidate identity differs from its snapshot")
    opportunity_mapping = _exact_dataclass_mapping(
        decoded_opportunity,
        DummyOpportunity,
        "abstention.opportunity_snapshot",
    )
    opportunity = create_dummy_opportunity(
        _string(
            opportunity_mapping["creation_timestamp"], "opportunity.creation_timestamp"
        ),
        _string(opportunity_mapping["underlying"], "opportunity.underlying"),
        _string(opportunity_mapping["forecast"], "opportunity.forecast"),
        _string(
            opportunity_mapping["intended_horizon"], "opportunity.intended_horizon"
        ),
        _number(opportunity_mapping["confidence"], "opportunity.confidence"),
        _number(
            opportunity_mapping["maximum_exposure_fraction"],
            "opportunity.maximum_exposure_fraction",
        ),
        _string(
            opportunity_mapping["expiration_timestamp"],
            "opportunity.expiration_timestamp",
        ),
        _string(
            opportunity_mapping["upstream_version"], "opportunity.upstream_version"
        ),
        _string(opportunity_mapping["provenance_hash"], "opportunity.provenance_hash"),
        _boolean(opportunity_mapping["synthetic"], "opportunity.synthetic"),
    )
    if cast(dict[str, object], asdict(opportunity)) != opportunity_mapping:
        raise ValueError("abstention opportunity snapshot is not reproducible")
    embedded = candidate_dummy_contract(candidate)
    if (
        opportunity.opportunity_id != record.opportunity_id
        or opportunity.contract_hash != record.opportunity_contract_hash
        or embedded["opportunity_id"] != opportunity.opportunity_id
        or embedded["contract_hash"] != opportunity.contract_hash
        or record.opportunity_synthetic is not opportunity.synthetic
    ):
        raise ValueError(
            "abstention Dummy opportunity is not bound to its frozen candidate"
        )
    return candidate, opportunity


def _abstention_reason_codes(
    record: AbstentionRecord,
    candidate: CandidateGenome,
    opportunity: DummyOpportunity,
    controls: DecisionControlInputs,
    market_context: DecisionMarketContext | None,
    prospective_evidence: ProspectivePaperEvidence | None,
    price_requests: tuple[PaperPriceRequest, ...],
) -> tuple[str, ...]:
    legs = candidate_option_legs(candidate)
    entry = _mapping(candidate.specification["entry"], "entry")
    earliest = _string(entry["earliest_time"], "entry.earliest_time")
    latest = _string(entry["latest_time"], "entry.latest_time")
    cancellation_match = re.fullmatch(
        r"cancel_after_([1-9][0-9]*)_seconds",
        _string(entry["cancellation_rule"], "entry.cancellation_rule"),
    )
    if cancellation_match is None:
        raise ValueError("candidate cancellation rule must use cancel_after_N_seconds")
    cancellation = (
        min(
            parse_utc(earliest) + timedelta(seconds=int(cancellation_match.group(1))),
            parse_utc(latest),
        )
        .isoformat()
        .replace("+00:00", "Z")
    )
    reasons = list(
        _market_context_reasons(
            market_context,
            opportunity,
            record.decision_timestamp,
            earliest,
            cancellation,
            latest,
        )
    )
    if candidate.candidate_mode == "abstention_policy":
        reasons.append("candidate_mode_abstention_policy")
    if opportunity.synthetic:
        if prospective_evidence is not None:
            raise ValueError("synthetic abstention cannot contain prospective evidence")
    elif prospective_evidence is None:
        reasons.append("prospective_paper_evidence_missing")
    else:
        if market_context is None:
            raise ValueError("prospective evidence cannot exist without market context")
        validate_prospective_paper_evidence(
            prospective_evidence,
            opportunity,
            candidate,
            market_context,
        )
        if parse_utc(prospective_evidence.observed_at) > parse_utc(
            record.decision_timestamp
        ):
            reasons.append("prospective_paper_evidence_not_available_at_decision")
    if len(price_requests) != len(legs):
        reasons.append("paper_ticket_leg_cardinality_mismatch")
    if any(leg["side"] == "sell" for leg in legs):
        reasons.append("short_option_lifecycle_uncertified")
    risk_gate = evaluate_risk_gate(
        controls.candidate_exposure,
        controls.portfolio_state,
        controls.risk_limits,
    )
    behavioral_gate = evaluate_behavioral_gate(controls.behavioral_state)
    negative_control_gate = evaluate_negative_controls(
        controls.negative_control_results,
        controls.required_negative_control_ids,
        controls.candidate_author_id,
    )
    reasons.extend(risk_gate.reason_codes)
    reasons.extend(behavioral_gate.reason_codes)
    reasons.extend(negative_control_gate.reason_codes)
    reasons.extend(_candidate_limit_reasons(candidate, controls))
    for index, request in enumerate(price_requests):
        gate = evaluate_quote_gate(
            request.quote, record.decision_timestamp, v1_quote_gate_policy()
        )
        reasons.extend(gate.reason_codes)
        if index >= len(legs):
            continue
        leg = legs[index]
        reasons.extend(_quote_leg_mismatch_reasons(request.quote, leg))
        direction = "debit" if leg["side"] == "buy" else "credit"
        if request.price_direction != direction:
            reasons.append("paper_ticket_price_direction_mismatch")
        if request.contract_multiplier != leg["multiplier"]:
            reasons.append("paper_ticket_multiplier_mismatch")
        relevant_size = (
            request.quote.ask_size if direction == "debit" else request.quote.bid_size
        )
        if relevant_size < int(leg["quantity"]):
            reasons.append("paper_ticket_displayed_size_below_quantity")
        if (
            request.slippage_basis_points != 25.0
            or request.commission_per_contract != 0.65
        ):
            reasons.append("paper_ticket_cost_policy_not_environment_derived")
        if market_context is not None:
            observed = parse_utc(request.quote.observed_at)
            received = parse_utc(request.quote.received_at)
            if not (
                parse_utc(market_context.session_open)
                <= observed
                <= received
                <= parse_utc(record.decision_timestamp)
                < parse_utc(market_context.session_close)
            ):
                reasons.append("paper_ticket_quote_outside_xnys_session")
    return tuple(sorted(set(reasons or ["paper_price_unavailable"])))


def abstention_record_body(record: AbstentionRecord) -> dict[str, JsonValue]:
    return {
        "opportunity_id": record.opportunity_id,
        "opportunity_contract_hash": record.opportunity_contract_hash,
        "opportunity_snapshot": record.opportunity_snapshot,
        "candidate_id": record.candidate_id,
        "candidate_genome_hash": record.candidate_genome_hash,
        "candidate_snapshot": record.candidate_snapshot,
        "candidate_mode": record.candidate_mode,
        "environment_hash": record.environment_hash,
        "decision_timestamp": record.decision_timestamp,
        "reason_codes": list(record.reason_codes),
        "control_snapshot": record.control_snapshot,
        "control_hash": record.control_hash,
        "price_requests_snapshot": record.price_requests_snapshot,
        "price_requests_hash": record.price_requests_hash,
        "market_context_snapshot": record.market_context_snapshot,
        "market_context_hash": record.market_context_hash,
        "prospective_evidence_snapshot": record.prospective_evidence_snapshot,
        "prospective_evidence_hash": record.prospective_evidence_hash,
        "evidence_class": record.evidence_class,
        "opportunity_synthetic": record.opportunity_synthetic,
        "profitability_evidence_eligible": record.profitability_evidence_eligible,
        "paper_only": record.paper_only,
        "live_blocked": record.live_blocked,
    }


def abstention_record_id(record: AbstentionRecord) -> str:
    return f"abstain-{canonical_hash(abstention_record_body(record))[:24]}"


def validate_abstention_record(record: AbstentionRecord) -> None:
    if record.paper_only is not True or record.live_blocked is not True:
        raise ValueError("abstention record weakened its authority boundary")
    if not record.opportunity_id or not record.candidate_id:
        raise ValueError("abstention record identity fields cannot be empty")
    require_utc_iso(record.decision_timestamp)
    require_v1_environment_hash(record.environment_hash)
    for field_name, value in (
        ("opportunity_contract_hash", record.opportunity_contract_hash),
        ("candidate_genome_hash", record.candidate_genome_hash),
        ("control_hash", record.control_hash),
        ("price_requests_hash", record.price_requests_hash),
        ("market_context_hash", record.market_context_hash),
        ("prospective_evidence_hash", record.prospective_evidence_hash),
    ):
        require_sha256(value, f"abstention.{field_name}")
    if not record.reason_codes:
        raise ValueError("abstention record requires at least one reason code")
    if any(not reason_code for reason_code in record.reason_codes):
        raise ValueError("abstention record reason codes cannot be empty")
    if record.reason_codes != tuple(sorted(set(record.reason_codes))):
        raise ValueError("abstention record reason codes must be unique and sorted")
    candidate, opportunity = _reconstruct_abstention_candidate(record)
    if candidate.candidate_mode != record.candidate_mode:
        raise ValueError("abstention candidate_mode differs from its frozen candidate")
    if record.evidence_class not in {
        "synthetic_mechanics_only",
        "prospective_market_evidence",
    }:
        raise ValueError("abstention record evidence class is unsupported")
    if opportunity.synthetic:
        if (
            record.evidence_class != "synthetic_mechanics_only"
            or record.profitability_evidence_eligible is not False
        ):
            raise ValueError("synthetic abstention contains a real-evidence claim")
    elif record.evidence_class != "prospective_market_evidence":
        raise ValueError("real-market abstention has the wrong evidence class")
    controls = _reconstruct_ticket_controls(record, False)
    raw_price_requests = _parse_optional_artifact_snapshot(
        record.price_requests_snapshot,
        record.price_requests_hash,
        "price_requests",
    )
    if not isinstance(raw_price_requests, list):
        raise ValueError("abstention price request snapshot must be a list")
    price_requests = tuple(
        _paper_price_request_from_mapping(request) for request in raw_price_requests
    )
    raw_context = _parse_optional_artifact_snapshot(
        record.market_context_snapshot,
        record.market_context_hash,
        "market_context",
    )
    market_context = (
        _decision_market_context_from_mapping(raw_context)
        if raw_context is not None
        else None
    )
    raw_prospective = _parse_optional_artifact_snapshot(
        record.prospective_evidence_snapshot,
        record.prospective_evidence_hash,
        "prospective_evidence",
    )
    prospective_evidence = (
        _prospective_paper_evidence_from_mapping(raw_prospective)
        if raw_prospective is not None
        else None
    )
    expected_reasons = _abstention_reason_codes(
        record,
        candidate,
        opportunity,
        controls,
        market_context,
        prospective_evidence,
        price_requests,
    )
    if record.reason_codes != expected_reasons:
        raise ValueError(
            "abstention reasons are not reproducible from frozen controls: "
            f"expected={expected_reasons}, observed={record.reason_codes}"
        )
    if record.profitability_evidence_eligible is not False:
        raise ValueError("local abstention cannot self-certify profitability evidence")
    if record.abstention_id != abstention_record_id(record):
        raise ValueError(
            "abstention record identity does not match its immutable content"
        )


def abstention_record_to_mapping(record: AbstentionRecord) -> dict[str, JsonValue]:
    validate_abstention_record(record)
    return cast(dict[str, JsonValue], asdict(record))


def abstention_record_from_mapping(
    value: Mapping[str, object],
) -> AbstentionRecord:
    mapping = _exact_dataclass_mapping(value, AbstentionRecord, "abstention_record")
    raw_reason_codes = _sequence(mapping["reason_codes"], "abstention.reason_codes")
    record = AbstentionRecord(
        abstention_id=_string(mapping["abstention_id"], "abstention.abstention_id"),
        opportunity_id=_string(mapping["opportunity_id"], "abstention.opportunity_id"),
        opportunity_contract_hash=_string(
            mapping["opportunity_contract_hash"], "abstention.opportunity_contract_hash"
        ),
        opportunity_snapshot=_string(
            mapping["opportunity_snapshot"], "abstention.opportunity_snapshot"
        ),
        candidate_id=_string(mapping["candidate_id"], "abstention.candidate_id"),
        candidate_genome_hash=_string(
            mapping["candidate_genome_hash"], "abstention.candidate_genome_hash"
        ),
        candidate_snapshot=_string(
            mapping["candidate_snapshot"], "abstention.candidate_snapshot"
        ),
        candidate_mode=cast(
            Literal["options_expression", "abstention_policy"],
            _string(mapping["candidate_mode"], "abstention.candidate_mode"),
        ),
        environment_hash=_string(
            mapping["environment_hash"], "abstention.environment_hash"
        ),
        decision_timestamp=_string(
            mapping["decision_timestamp"],
            "abstention.decision_timestamp",
        ),
        reason_codes=tuple(
            _string(reason_code, "abstention.reason_codes[]")
            for reason_code in raw_reason_codes
        ),
        control_snapshot=_string(
            mapping["control_snapshot"], "abstention.control_snapshot"
        ),
        control_hash=_string(mapping["control_hash"], "abstention.control_hash"),
        price_requests_snapshot=_string(
            mapping["price_requests_snapshot"], "abstention.price_requests_snapshot"
        ),
        price_requests_hash=_string(
            mapping["price_requests_hash"], "abstention.price_requests_hash"
        ),
        market_context_snapshot=_string(
            mapping["market_context_snapshot"], "abstention.market_context_snapshot"
        ),
        market_context_hash=_string(
            mapping["market_context_hash"], "abstention.market_context_hash"
        ),
        prospective_evidence_snapshot=_string(
            mapping["prospective_evidence_snapshot"],
            "abstention.prospective_evidence_snapshot",
        ),
        prospective_evidence_hash=_string(
            mapping["prospective_evidence_hash"], "abstention.prospective_evidence_hash"
        ),
        evidence_class=cast(
            Literal["synthetic_mechanics_only", "prospective_market_evidence"],
            _string(mapping["evidence_class"], "abstention.evidence_class"),
        ),
        opportunity_synthetic=_boolean(
            mapping["opportunity_synthetic"], "abstention.opportunity_synthetic"
        ),
        profitability_evidence_eligible=_boolean(
            mapping["profitability_evidence_eligible"],
            "abstention.profitability_evidence_eligible",
        ),
        paper_only=_boolean(mapping["paper_only"], "abstention.paper_only"),
        live_blocked=_boolean(mapping["live_blocked"], "abstention.live_blocked"),
    )
    validate_abstention_record(record)
    return record


def paper_decision_body(decision: PaperDecision) -> dict[str, JsonValue]:
    if isinstance(decision, PaperExecutionTicket):
        return {
            "decision_type": "paper_execution_ticket",
            "artifact": paper_execution_ticket_to_mapping(decision),
        }
    return {
        "decision_type": "abstention_record",
        "artifact": abstention_record_to_mapping(decision),
    }


def build_paper_decision(
    opportunity: DummyOpportunity,
    candidate: CandidateGenome,
    decision_timestamp: str,
    price_requests: tuple[PaperPriceRequest, ...],
    quote_policy: QuoteGatePolicy,
    controls: DecisionControlInputs,
    market_context: DecisionMarketContext | None,
    prospective_evidence: ProspectivePaperEvidence | None,
) -> PaperDecision:
    _assert_research_boundary()
    require_utc_iso(decision_timestamp)
    validate_dummy_opportunity(opportunity)
    validate_candidate_genome(candidate)
    require_v1_environment_hash(controls.environment_hash)
    embedded_opportunity = candidate_dummy_contract(candidate)
    if (
        embedded_opportunity["opportunity_id"] != opportunity.opportunity_id
        or embedded_opportunity["contract_hash"] != opportunity.contract_hash
    ):
        raise ValueError(
            "candidate genome is not bound to the supplied Dummy opportunity"
        )
    if parse_utc(decision_timestamp) < parse_utc(opportunity.creation_timestamp):
        raise ValueError("paper decision cannot predate immutable Dummy opportunity")
    if parse_utc(decision_timestamp) >= parse_utc(opportunity.expiration_timestamp):
        raise ValueError("paper decision cannot use an expired Dummy opportunity")
    if quote_policy != v1_quote_gate_policy():
        raise ValueError(
            "paper decision quote policy must be derived from frozen environment v1"
        )
    if controls.risk_limits != v1_risk_limits():
        raise ValueError(
            "paper decision risk limits must be derived from frozen environment v1"
        )
    if controls.required_negative_control_ids != V1_REQUIRED_NEGATIVE_CONTROL_IDS:
        raise ValueError("paper decision requires the canonical v1 negative controls")
    reproducibility = _mapping(
        candidate.specification["reproducibility"], "reproducibility"
    )
    if (
        controls.environment_hash != reproducibility["environment_hash"]
        or controls.environment_hash != V1_ENVIRONMENT_HASH
    ):
        raise ValueError(
            "decision controls do not match the candidate environment identity"
        )

    legs = candidate_option_legs(candidate)
    structure = _mapping(candidate.specification["structure"], "structure")
    structure_type = str(structure["type"])
    entry = _mapping(candidate.specification["entry"], "entry")
    entry_earliest_time = str(entry["earliest_time"])
    entry_latest_time = str(entry["latest_time"])
    cancellation_match = re.fullmatch(
        r"cancel_after_([1-9][0-9]*)_seconds", str(entry["cancellation_rule"])
    )
    if cancellation_match is None:
        raise ValueError("candidate cancellation rule must use cancel_after_N_seconds")
    cancellation_seconds = int(cancellation_match.group(1))
    cancellation_from_entry = parse_utc(entry_earliest_time) + timedelta(
        seconds=cancellation_seconds
    )
    effective_deadline = min(cancellation_from_entry, parse_utc(entry_latest_time))
    cancellation_deadline = effective_deadline.isoformat().replace("+00:00", "Z")
    expected_contract_ids = tuple(str(leg["contract_id"]) for leg in legs)
    quantities = tuple(int(leg["quantity"]) for leg in legs)
    frozen_leg_terms = tuple(_freeze_ticket_leg(leg) for leg in legs)
    invalidation_rule, management_rule, exit_rule = candidate_lifecycle_rules(candidate)
    reasons: list[str] = []
    reasons.extend(
        _market_context_reasons(
            market_context,
            opportunity,
            decision_timestamp,
            entry_earliest_time,
            cancellation_deadline,
            entry_latest_time,
        )
    )
    if candidate.candidate_mode == "abstention_policy":
        reasons.append("candidate_mode_abstention_policy")
    if opportunity.synthetic:
        if prospective_evidence is not None:
            raise ValueError(
                "synthetic mechanics decision cannot contain prospective evidence"
            )
        evidence_class = "synthetic_mechanics_only"
    else:
        evidence_class = "prospective_market_evidence"
        if prospective_evidence is None:
            reasons.append("prospective_paper_evidence_missing")
        else:
            if market_context is None:
                raise ValueError(
                    "prospective evidence cannot exist without market context"
                )
            validate_prospective_paper_evidence(
                prospective_evidence,
                opportunity,
                candidate,
                market_context,
            )
            if parse_utc(prospective_evidence.observed_at) > parse_utc(
                decision_timestamp
            ):
                reasons.append("prospective_paper_evidence_not_available_at_decision")
    if len(price_requests) != len(legs):
        reasons.append("paper_ticket_leg_cardinality_mismatch")
    if any(leg["side"] == "sell" for leg in legs):
        reasons.append("short_option_lifecycle_uncertified")

    risk_gate = evaluate_risk_gate(
        controls.candidate_exposure,
        controls.portfolio_state,
        controls.risk_limits,
    )
    behavioral_gate = evaluate_behavioral_gate(controls.behavioral_state)
    negative_control_gate = evaluate_negative_controls(
        controls.negative_control_results,
        controls.required_negative_control_ids,
        controls.candidate_author_id,
    )
    reasons.extend(risk_gate.reason_codes)
    reasons.extend(behavioral_gate.reason_codes)
    reasons.extend(negative_control_gate.reason_codes)
    reasons.extend(_candidate_limit_reasons(candidate, controls))

    quote_gates: list[QuoteGateDecision] = []
    for index, request in enumerate(price_requests):
        gate = evaluate_quote_gate(request.quote, decision_timestamp, quote_policy)
        quote_gates.append(gate)
        reasons.extend(gate.reason_codes)
        if index >= len(legs):
            continue
        leg = legs[index]
        reasons.extend(_quote_leg_mismatch_reasons(request.quote, leg))
        expected_direction = "debit" if leg["side"] == "buy" else "credit"
        if request.price_direction != expected_direction:
            reasons.append("paper_ticket_price_direction_mismatch")
        if request.contract_multiplier != leg["multiplier"]:
            reasons.append("paper_ticket_multiplier_mismatch")
        relevant_size = (
            request.quote.ask_size
            if expected_direction == "debit"
            else request.quote.bid_size
        )
        if relevant_size < int(leg["quantity"]):
            reasons.append("paper_ticket_displayed_size_below_quantity")
        if (
            request.slippage_basis_points != 25.0
            or request.commission_per_contract != 0.65
        ):
            reasons.append("paper_ticket_cost_policy_not_environment_derived")
        if market_context is not None:
            quote_observed = parse_utc(request.quote.observed_at)
            quote_received = parse_utc(request.quote.received_at)
            if not (
                parse_utc(market_context.session_open)
                <= quote_observed
                <= quote_received
                <= parse_utc(decision_timestamp)
                < parse_utc(market_context.session_close)
            ):
                reasons.append("paper_ticket_quote_outside_xnys_session")

    price_triples: tuple[PriceTriple, ...] = ()
    if (
        len(price_requests) == len(legs)
        and all(gate.passed for gate in quote_gates)
        and not reasons
    ):
        price_triples = tuple(
            build_price_triple(
                request.quote,
                decision_timestamp,
                quote_policy,
                request.model_fair_value,
                request.price_direction,
                request.slippage_basis_points,
                request.commission_per_contract,
                request.contract_multiplier,
            )
            for request in price_requests
        )
    control_body = _ticket_control_body(
        controls,
        candidate,
        opportunity,
        decision_timestamp,
    )
    assert_no_forbidden_nested_payload(control_body, "paper_decision.controls")
    _assert_finite_artifact(control_body, "paper_decision.controls")
    control_snapshot = canonical_json(control_body)
    control_hash = canonical_hash(control_body)
    opportunity_body = cast(dict[str, JsonValue], asdict(opportunity))
    opportunity_snapshot = canonical_json(opportunity_body)
    candidate_snapshot = candidate_genome_canonical_snapshot(candidate)
    price_requests_body = [
        _paper_price_request_body(request) for request in price_requests
    ]
    price_requests_snapshot, price_requests_hash = _optional_artifact_snapshot(
        price_requests_body
    )
    context_body = (
        cast(dict[str, JsonValue], asdict(market_context))
        if market_context is not None
        else None
    )
    market_context_snapshot, market_context_hash = _optional_artifact_snapshot(
        context_body
    )
    prospective_body = (
        cast(dict[str, JsonValue], asdict(prospective_evidence))
        if prospective_evidence is not None
        else None
    )
    prospective_snapshot, prospective_hash = _optional_artifact_snapshot(
        prospective_body
    )
    if reasons or not price_triples:
        provisional_abstention = AbstentionRecord(
            abstention_id="pending",
            opportunity_id=opportunity.opportunity_id,
            opportunity_contract_hash=opportunity.contract_hash,
            opportunity_snapshot=opportunity_snapshot,
            candidate_id=candidate.candidate_id,
            candidate_genome_hash=candidate.genome_hash,
            candidate_snapshot=candidate_snapshot,
            candidate_mode=candidate.candidate_mode,
            environment_hash=controls.environment_hash,
            decision_timestamp=decision_timestamp,
            reason_codes=tuple(sorted(set(reasons or ["paper_price_unavailable"]))),
            control_snapshot=control_snapshot,
            control_hash=control_hash,
            price_requests_snapshot=price_requests_snapshot,
            price_requests_hash=price_requests_hash,
            market_context_snapshot=market_context_snapshot,
            market_context_hash=market_context_hash,
            prospective_evidence_snapshot=prospective_snapshot,
            prospective_evidence_hash=prospective_hash,
            evidence_class=cast(
                Literal["synthetic_mechanics_only", "prospective_market_evidence"],
                evidence_class,
            ),
            opportunity_synthetic=opportunity.synthetic,
            profitability_evidence_eligible=False,
            paper_only=True,
            live_blocked=True,
        )
        abstention = replace(
            provisional_abstention,
            abstention_id=abstention_record_id(provisional_abstention),
        )
        validate_abstention_record(abstention)
        return abstention

    maximum_loss_usd = _calculate_maximum_loss_usd(structure_type, legs, price_triples)
    declared_maximum_loss = float(structure["maximum_loss"])
    maximum_loss_fraction = round(maximum_loss_usd / V1_PAPER_BANKROLL_USD, 12)
    if maximum_loss_usd > declared_maximum_loss:
        raise ValueError("price-derived maximum loss exceeds the frozen candidate cap")
    if maximum_loss_fraction > opportunity.maximum_exposure_fraction:
        raise ValueError(
            "price-derived maximum loss exceeds the frozen upstream exposure envelope"
        )
    if not math.isclose(
        controls.candidate_exposure.maximum_loss_fraction,
        maximum_loss_fraction,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "candidate exposure maximum loss is not derived from frozen paper prices"
        )
    expected_dte = min(
        (
            date.fromisoformat(str(leg["expiry"]))
            - parse_utc(decision_timestamp).date()
        ).days
        for leg in legs
    )
    if controls.candidate_exposure.days_to_expiration != expected_dte:
        raise ValueError(
            "candidate exposure DTE is not derived from the frozen option legs"
        )

    provisional = PaperExecutionTicket(
        ticket_id="pending",
        opportunity_id=opportunity.opportunity_id,
        opportunity_contract_hash=opportunity.contract_hash,
        candidate_id=candidate.candidate_id,
        candidate_genome_hash=candidate.genome_hash,
        candidate_snapshot=candidate_snapshot,
        environment_hash=controls.environment_hash,
        decision_timestamp=decision_timestamp,
        entry_earliest_time=entry_earliest_time,
        entry_latest_time=entry_latest_time,
        cancellation_deadline=cancellation_deadline,
        structure_type=structure_type,
        leg_terms=frozen_leg_terms,
        contract_ids=expected_contract_ids,
        quantities=quantities,
        price_triples=price_triples,
        control_snapshot=control_snapshot,
        control_hash=control_hash,
        maximum_loss_usd=maximum_loss_usd,
        maximum_loss_fraction=maximum_loss_fraction,
        invalidation_rule=invalidation_rule,
        management_rule=management_rule,
        exit_rule=exit_rule,
        paper_fill_status="pending_later_quote_witness",
        evidence_class=cast(
            Literal["synthetic_mechanics_only", "prospective_market_evidence"],
            evidence_class,
        ),
        opportunity_synthetic=opportunity.synthetic,
        exposure_model_certified=False,
        complete_cost_model_certified=False,
        fair_value_input_stack_certified=False,
        profitability_evidence_eligible=False,
        market_context_snapshot=market_context_snapshot,
        market_context_hash=market_context_hash,
        prospective_evidence_snapshot=prospective_snapshot,
        prospective_evidence_hash=prospective_hash,
        paper_only=True,
        live_blocked=True,
    )
    ticket_id = paper_execution_ticket_id(provisional)
    ticket = replace(provisional, ticket_id=ticket_id)
    validate_paper_execution_ticket(ticket)
    return ticket


def build_paper_fill_observation(
    ticket: PaperExecutionTicket,
    later_quotes: tuple[QuoteSnapshot, ...],
    maximum_package_skew_seconds: float,
    quote_policy: QuoteGatePolicy,
) -> PaperFillObservation:
    validate_paper_execution_ticket(ticket)
    if quote_policy != v1_quote_gate_policy():
        raise ValueError(
            "paper fill quote policy must be derived from frozen environment v1"
        )
    if (
        not math.isfinite(maximum_package_skew_seconds)
        or maximum_package_skew_seconds < 0.0
    ):
        raise ValueError("maximum package skew must be finite and nonnegative")
    if maximum_package_skew_seconds != 1.0:
        raise ValueError(
            "paper fill package-skew policy must be derived from frozen environment v1"
        )
    reasons, hashes, witnessed_at = _paper_fill_outcome(ticket, later_quotes)
    filled = not reasons
    provisional = PaperFillObservation(
        observation_id="pending",
        ticket_id=ticket.ticket_id,
        witnessed_at=witnessed_at,
        contract_ids=ticket.contract_ids,
        conservative_prices=tuple(
            price.conservative_paper_executable for price in ticket.price_triples
        )
        if filled
        else (),
        witness_hashes=hashes,
        witness_quotes=later_quotes,
        paper_fill_status="filled" if filled else "missed",
        reason_codes=reasons,
        evidence_class=ticket.evidence_class,
        profitability_evidence_eligible=ticket.profitability_evidence_eligible,
        realized_evidence=False,
        paper_only=True,
        live_blocked=True,
    )
    observation = replace(
        provisional,
        observation_id=paper_fill_observation_id(provisional),
    )
    validate_paper_fill_observation(observation, ticket)
    return observation
