"""Nonce-bound Core resolver for Dopey promotion and passport contracts."""

from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Final, Mapping
from urllib.parse import urlencode

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .dumbmoney_authority import (
    DOPEY_VENUE,
    DumbMoneyAuthorityError,
    VerifiedCapitalAuthority,
    _decode_public_key,
    _sha256_text,
    _utc_timestamp,
    _urlsafe_b64decode,
    canonical_json_bytes,
)
from .dumbmoney_command_feed import (
    CHECKPOINT_SIGNATURE_FIELDS,
    MAXIMUM_RESPONSE_BYTES,
    CommandFeedHttpRequest,
    CommandFeedHttpResponse,
    CommandFeedTransport,
    DumbMoneyCommandFeedError,
    _cell_bearer,
    _exact_fields,
    _loads_strict_json,
    _response_content_type,
    _validated_ledger_proof,
    _validated_loopback_origin,
)
from .dumbmoney_promotion import (
    ALPHA_PASSPORT_SCHEMA,
    LIVE_PROMOTION_STAGES,
    PROMOTION_CERTIFICATE_SCHEMA,
    DumbMoneyPromotionError,
    PromotionAuthorityResolver,
    VerifiedAlphaPassport,
    VerifiedPromotionBinding,
    VerifiedPromotionCertificate,
    bind_verified_promotion,
    validated_role_keyrings,
    verify_alpha_passport_envelope,
    verify_promotion_certificate_envelope,
)
from .models import LiveExecutionIntent


CONTRACT_RESOLUTION_SCHEMA: Final[str] = "dumbmoney.cell-contract-resolution.v1"
CONTRACT_RESOLUTION_CHECKPOINT_SCHEMA: Final[str] = (
    "dumbmoney.cell-contract-resolution-checkpoint.v1"
)
CONTRACT_RESOLUTION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "request_nonce",
        "requested_body_digest",
        "capital_envelope_digest",
        "fencing_generation",
        "observed_at",
        "contract_schema",
        "transport_window_current",
        "body_window_current",
        "eligible_live_input",
        "authority_state",
        "ledger_proof",
        "envelope",
        "checkpoint",
        "checkpoint_signature",
    }
)
CONTRACT_RESOLUTION_CHECKPOINT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "request_nonce",
        "requested_body_digest",
        "capital_envelope_digest",
        "fencing_generation",
        "observed_at",
        "contract_schema",
        "transport_window_current",
        "body_window_current",
        "eligible_live_input",
        "authority_state",
        "ledger_proof",
        "envelope",
    }
)
CONTRACT_SCHEMAS: Final[frozenset[str]] = frozenset(
    {ALPHA_PASSPORT_SCHEMA, PROMOTION_CERTIFICATE_SCHEMA}
)
MAXIMUM_RESOLUTION_CLOCK_SKEW: Final[timedelta] = timedelta(seconds=60)
AUTHORITY_STATE_SCHEMA: Final[str] = "dumbmoney.cell-authority-state.v1"
AUTHORITY_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "evaluated_at",
        "authority_valid_until",
        "policy_epoch",
        "mandate_id",
        "mandate_event_digest",
        "kill_clear",
        "kill_generation",
        "kill_event_digest",
        "desired_mode",
        "desired_mode_revision",
        "desired_mode_event_digest",
        "capital_envelope_digest",
        "capital_event_digest",
        "fencing_generation",
        "strategy_hash",
        "passport_digest",
        "passport_event_digest",
        "promotion_digest",
        "promotion_event_digest",
        "verdicts",
        "ledger_head_sequence",
        "ledger_head_digest",
    }
)
AUTHORITY_VERDICT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "verdict_digest",
        "verdict_event_digest",
        "verdict_id",
        "court",
        "decision",
        "signer_key_id",
        "evaluated_at",
        "expires_at",
        "transport_expires_at",
    }
)
VERDICT_COURTS: Final[frozenset[str]] = frozenset(
    {"integrity", "statistics", "economics", "adversarial_operations"}
)


@dataclass(frozen=True)
class _ResolvedContract:
    contract_schema: str
    body_digest: str
    envelope: dict[str, Any]
    verified: VerifiedAlphaPassport | VerifiedPromotionCertificate
    authority_state: dict[str, Any]


def _validated_evaluator_keyring(
    values: Mapping[str, bytes],
    *,
    disjoint_key_ids: frozenset[str],
) -> dict[str, bytes]:
    if not isinstance(values, Mapping) or not 1 <= len(values) <= 32:
        raise DumbMoneyPromotionError(
            "sealed evaluator keyring must contain 1 to 32 keys"
        )
    resolved: dict[str, bytes] = {}
    for raw_key_id, raw_key in values.items():
        key_id = _sha256_text(raw_key_id, "evaluator signer key ID")
        try:
            public_key = _decode_public_key(raw_key)
        except DumbMoneyAuthorityError as error:
            raise DumbMoneyPromotionError(
                "sealed evaluator public key is invalid"
            ) from error
        if hashlib.sha256(public_key).hexdigest() != key_id:
            raise DumbMoneyPromotionError(
                "evaluator signer key ID does not bind its public key"
            )
        if key_id in disjoint_key_ids:
            raise DumbMoneyPromotionError(
                "evaluator signer role overlaps a control or research role"
            )
        resolved[key_id] = public_key
    return resolved


@dataclass(frozen=True)
class DumbMoneyContractResolverClient(PromotionAuthorityResolver):
    """Fetch and authenticate the exact singleton lineage named by capital."""

    base_url: str
    cell_bearer_provider: Callable[[], str]
    trusted_core_public_key: bytes
    trusted_promoter_public_keys: Mapping[str, bytes]
    trusted_research_public_keys: Mapping[str, bytes]
    trusted_evaluator_public_keys: Mapping[str, bytes]
    transport: CommandFeedTransport
    timeout_seconds: float = 5.0

    def bind_intent(
        self,
        authority: VerifiedCapitalAuthority,
        intent: LiveExecutionIntent,
        now_utc: datetime,
        *,
        expected_binding: VerifiedPromotionBinding | None = None,
    ) -> tuple[LiveExecutionIntent, VerifiedPromotionBinding]:
        if now_utc.tzinfo is None:
            raise DumbMoneyPromotionError(
                "contract resolution requires an aware UTC clock"
            )
        if (
            len(authority.envelope.passport_hashes) != 1
            or len(authority.envelope.promotion_hashes) != 1
        ):
            raise DumbMoneyPromotionError(
                "contract resolver requires singleton capital lineage"
            )
        try:
            core_key = _decode_public_key(self.trusted_core_public_key)
        except DumbMoneyAuthorityError as error:
            raise DumbMoneyPromotionError(
                "pinned Core public key is invalid"
            ) from error
        promoter_keys, research_keys = validated_role_keyrings(
            self.trusted_promoter_public_keys,
            self.trusted_research_public_keys,
            core_public_key=core_key,
        )
        evaluator_keys = _validated_evaluator_keyring(
            self.trusted_evaluator_public_keys,
            disjoint_key_ids=frozenset(
                {
                    hashlib.sha256(core_key).hexdigest(),
                    *promoter_keys,
                    *research_keys,
                }
            ),
        )
        promotion_resolution = self._resolve(
            authority.envelope.promotion_hashes[0],
            PROMOTION_CERTIFICATE_SCHEMA,
            authority.body_digest,
            authority.envelope.fencing_generation,
            now_utc,
            core_key,
            promoter_keys,
            research_keys,
            evaluator_keys,
            authority,
        )
        if not isinstance(
            promotion_resolution.verified,
            VerifiedPromotionCertificate,
        ):
            raise DumbMoneyPromotionError(
                "Core promotion resolution returned the wrong contract type"
            )
        passport_digest = promotion_resolution.verified.certificate.passport_digest
        if passport_digest != authority.envelope.passport_hashes[0]:
            raise DumbMoneyPromotionError(
                "resolved promotion points outside the singleton capital passport"
            )
        passport_resolution = self._resolve(
            passport_digest,
            ALPHA_PASSPORT_SCHEMA,
            authority.body_digest,
            authority.envelope.fencing_generation,
            now_utc,
            core_key,
            promoter_keys,
            research_keys,
            evaluator_keys,
            authority,
        )
        if not isinstance(
            passport_resolution.verified,
            VerifiedAlphaPassport,
        ):
            raise DumbMoneyPromotionError(
                "Core passport resolution returned the wrong contract type"
            )
        promotion_state = {
            key: value
            for key, value in promotion_resolution.authority_state.items()
            if key != "evaluated_at"
        }
        passport_state = {
            key: value
            for key, value in passport_resolution.authority_state.items()
            if key != "evaluated_at"
        }
        if promotion_state != passport_state:
            raise DumbMoneyPromotionError(
                "promotion and passport were not resolved from one authority state"
            )
        return bind_verified_promotion(
            authority,
            intent,
            passport_resolution.verified,
            promotion_resolution.verified,
            now_utc,
            expected_binding=expected_binding,
        )

    def _resolve(
        self,
        body_digest: str,
        expected_schema: str,
        capital_envelope_digest: str,
        fencing_generation: int,
        now_utc: datetime,
        core_public_key: bytes,
        promoter_public_keys: Mapping[str, bytes],
        research_public_keys: Mapping[str, bytes],
        evaluator_public_keys: Mapping[str, bytes],
        authority: VerifiedCapitalAuthority,
    ) -> _ResolvedContract:
        try:
            origin = _validated_loopback_origin(self.base_url)
            digest = _sha256_text(body_digest, "requested contract digest")
            capital_digest = _sha256_text(
                capital_envelope_digest,
                "active capital envelope digest",
            )
            if (
                isinstance(fencing_generation, bool)
                or not isinstance(fencing_generation, int)
                or fencing_generation <= 0
            ):
                raise DumbMoneyPromotionError(
                    "active capital fencing generation must be positive"
                )
            if expected_schema not in CONTRACT_SCHEMAS:
                raise DumbMoneyPromotionError(
                    "requested contract schema is unsupported"
                )
            if (
                isinstance(self.timeout_seconds, bool)
                or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(float(self.timeout_seconds))
                or not 0.1 <= float(self.timeout_seconds) <= 30.0
            ):
                raise DumbMoneyPromotionError(
                    "contract transport timeout must be between 0.1 and 30 seconds"
                )
            token = _cell_bearer(self.cell_bearer_provider)
            try:
                request_nonce = _sha256_text(
                    secrets.token_hex(32),
                    "contract request_nonce",
                )
            except Exception as error:
                raise DumbMoneyPromotionError(
                    "cryptographic contract nonce generation failed"
                ) from error
        except (DumbMoneyAuthorityError, DumbMoneyCommandFeedError) as error:
            raise DumbMoneyPromotionError(
                f"contract resolver configuration is invalid: {error}"
            ) from error
        query = urlencode(
            {
                "request_nonce": request_nonce,
                "capital_envelope_digest": capital_digest,
            }
        )
        request = CommandFeedHttpRequest(
            method="GET",
            url=(f"{origin}/v1/cells/{DOPEY_VENUE}/contracts/{digest}?{query}"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout_seconds=float(self.timeout_seconds),
        )
        try:
            response = self.transport(request)
        except Exception as error:
            raise DumbMoneyPromotionError(
                f"contract transport failed closed: {type(error).__name__}"
            ) from error
        if not isinstance(response, CommandFeedHttpResponse):
            raise DumbMoneyPromotionError(
                "contract transport returned an unsupported response"
            )
        if isinstance(response.status, bool) or not isinstance(response.status, int):
            raise DumbMoneyPromotionError("contract HTTP status is invalid")
        if response.status in {401, 403}:
            raise DumbMoneyPromotionError(
                "contract resolution authentication or scope was denied"
            )
        if response.status != 200:
            raise DumbMoneyPromotionError(
                f"contract resolver returned HTTP {response.status}"
            )
        if not isinstance(response.body, bytes):
            raise DumbMoneyPromotionError("contract response body is not bytes")
        if len(response.body) > MAXIMUM_RESPONSE_BYTES:
            raise DumbMoneyPromotionError("contract response exceeds size limit")
        if not _response_content_type(response.headers).startswith("application/json"):
            raise DumbMoneyPromotionError("contract response content type is invalid")
        try:
            payload = _loads_strict_json(response.body, "contract resolution")
            return _validated_resolution(
                payload,
                digest,
                expected_schema,
                capital_digest,
                fencing_generation,
                request_nonce,
                now_utc,
                core_public_key,
                promoter_public_keys,
                research_public_keys,
                evaluator_public_keys,
                authority,
            )
        except (
            DumbMoneyAuthorityError,
            DumbMoneyCommandFeedError,
            DumbMoneyPromotionError,
        ) as error:
            raise DumbMoneyPromotionError(
                f"contract resolution was rejected: {error}"
            ) from error


def _verify_resolution_checkpoint(
    checkpoint: Mapping[str, Any],
    signature_payload: Mapping[str, Any],
    core_public_key: bytes,
) -> None:
    _exact_fields(
        checkpoint,
        CONTRACT_RESOLUTION_CHECKPOINT_FIELDS,
        "contract resolution checkpoint",
    )
    _exact_fields(
        signature_payload,
        CHECKPOINT_SIGNATURE_FIELDS,
        "contract resolution checkpoint signature",
    )
    if checkpoint.get("schema") != CONTRACT_RESOLUTION_CHECKPOINT_SCHEMA:
        raise DumbMoneyPromotionError(
            "contract resolution checkpoint schema is unsupported"
        )
    if signature_payload.get("algorithm") != "Ed25519":
        raise DumbMoneyPromotionError(
            "contract resolution checkpoint algorithm is unsupported"
        )
    expected_key_id = hashlib.sha256(core_public_key).hexdigest()
    if signature_payload.get("signer_key_id") != expected_key_id:
        raise DumbMoneyPromotionError(
            "contract resolution checkpoint signer is not pinned Core"
        )
    try:
        signature = _urlsafe_b64decode(str(signature_payload.get("signature", "")))
        if len(signature) != 64:
            raise ValueError("Ed25519 signature must be 64 bytes")
        Ed25519PublicKey.from_public_bytes(core_public_key).verify(
            signature,
            canonical_json_bytes(dict(checkpoint)),
        )
    except (InvalidSignature, ValueError) as error:
        raise DumbMoneyPromotionError(
            "contract resolution checkpoint signature is invalid"
        ) from error


def _positive_sequence(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DumbMoneyPromotionError(f"{label} must be a positive integer")
    return value


def _validated_authority_state(
    raw_state: Any,
    *,
    authority: VerifiedCapitalAuthority,
    now_utc: datetime,
    evaluator_public_keys: Mapping[str, bytes],
) -> dict[str, Any]:
    if not isinstance(raw_state, dict):
        raise DumbMoneyPromotionError("contract authority_state must be an object")
    _exact_fields(raw_state, AUTHORITY_STATE_FIELDS, "contract authority_state")
    if raw_state.get("schema") != AUTHORITY_STATE_SCHEMA:
        raise DumbMoneyPromotionError("contract authority_state schema is unsupported")
    now = now_utc.astimezone(timezone.utc)
    evaluated_at = _utc_timestamp(
        raw_state.get("evaluated_at"),
        "authority_state.evaluated_at",
    )
    valid_until = _utc_timestamp(
        raw_state.get("authority_valid_until"),
        "authority_state.authority_valid_until",
    )
    if (
        abs(now - evaluated_at) > MAXIMUM_RESOLUTION_CLOCK_SKEW
        or not evaluated_at < valid_until
        or not now < valid_until
        or valid_until
        > _utc_timestamp(
            authority.envelope.expires_at,
            "active capital envelope expires_at",
        )
    ):
        raise DumbMoneyPromotionError(
            "contract authority_state is stale, future-dated, or expired"
        )
    expected_values = {
        "policy_epoch": authority.envelope.policy_epoch,
        "mandate_id": authority.envelope.mandate_id,
        "kill_clear": True,
        "desired_mode": "LIVE",
        "capital_envelope_digest": authority.body_digest,
        "fencing_generation": authority.envelope.fencing_generation,
        "strategy_hash": authority.envelope.strategy_hashes[0],
        "passport_digest": authority.envelope.passport_hashes[0],
        "promotion_digest": authority.envelope.promotion_hashes[0],
    }
    for field, expected in expected_values.items():
        if raw_state.get(field) != expected:
            raise DumbMoneyPromotionError(
                f"contract authority_state {field} does not match active authority"
            )
    for field in (
        "kill_generation",
        "desired_mode_revision",
        "ledger_head_sequence",
    ):
        _positive_sequence(raw_state.get(field), f"authority_state.{field}")
    for field in (
        "mandate_event_digest",
        "kill_event_digest",
        "desired_mode_event_digest",
        "capital_event_digest",
        "passport_event_digest",
        "promotion_event_digest",
        "ledger_head_digest",
    ):
        _sha256_text(raw_state.get(field), f"authority_state.{field}")
    verdicts = raw_state.get("verdicts")
    if not isinstance(verdicts, list) or len(verdicts) < 2:
        raise DumbMoneyPromotionError(
            "contract authority_state requires at least two PASS verdicts"
        )
    verdict_facts: set[tuple[str, str, str, str]] = set()
    courts: set[str] = set()
    for index, verdict in enumerate(verdicts):
        if not isinstance(verdict, dict):
            raise DumbMoneyPromotionError(
                f"authority_state.verdicts[{index}] must be an object"
            )
        _exact_fields(
            verdict,
            AUTHORITY_VERDICT_FIELDS,
            f"authority_state.verdicts[{index}]",
        )
        digest = _sha256_text(
            verdict.get("verdict_digest"),
            f"authority_state.verdicts[{index}].verdict_digest",
        )
        event_digest = _sha256_text(
            verdict.get("verdict_event_digest"),
            f"authority_state.verdicts[{index}].verdict_event_digest",
        )
        verdict_id = str(verdict.get("verdict_id", ""))
        if not verdict_id or len(verdict_id) > 128:
            raise DumbMoneyPromotionError("authority verdict ID is invalid")
        court = str(verdict.get("court", ""))
        if court not in VERDICT_COURTS or verdict.get("decision") != "PASS":
            raise DumbMoneyPromotionError(
                "contract authority verdict is not a recognized PASS"
            )
        signer_key_id = _sha256_text(
            verdict.get("signer_key_id"),
            f"authority_state.verdicts[{index}].signer_key_id",
        )
        if signer_key_id not in evaluator_public_keys:
            raise DumbMoneyPromotionError(
                "contract authority verdict signer is not sealed"
            )
        verdict_evaluated_at = _utc_timestamp(
            verdict.get("evaluated_at"),
            f"authority_state.verdicts[{index}].evaluated_at",
        )
        verdict_expires_at = _utc_timestamp(
            verdict.get("expires_at"),
            f"authority_state.verdicts[{index}].expires_at",
        )
        transport_expires_at = _utc_timestamp(
            verdict.get("transport_expires_at"),
            f"authority_state.verdicts[{index}].transport_expires_at",
        )
        if (
            verdict_evaluated_at > now + MAXIMUM_RESOLUTION_CLOCK_SKEW
            or not verdict_evaluated_at < verdict_expires_at
            or not now < verdict_expires_at
            or not now < transport_expires_at
            or valid_until > min(verdict_expires_at, transport_expires_at)
        ):
            raise DumbMoneyPromotionError(
                "contract authority verdict is stale, future-dated, or expired"
            )
        verdict_facts.add((digest, event_digest, verdict_id, court))
        courts.add(court)
    if len(verdict_facts) != len(verdicts) or len(courts) < 2:
        raise DumbMoneyPromotionError(
            "contract authority verdict facts or courts are not unique"
        )
    return dict(raw_state)


def _validated_resolution(
    payload: dict[str, Any],
    expected_digest: str,
    expected_schema: str,
    expected_capital_digest: str,
    expected_fencing_generation: int,
    expected_nonce: str,
    now_utc: datetime,
    core_public_key: bytes,
    promoter_public_keys: Mapping[str, bytes],
    research_public_keys: Mapping[str, bytes],
    evaluator_public_keys: Mapping[str, bytes],
    authority: VerifiedCapitalAuthority,
) -> _ResolvedContract:
    _exact_fields(payload, CONTRACT_RESOLUTION_FIELDS, "contract resolution")
    if payload.get("schema") != CONTRACT_RESOLUTION_SCHEMA:
        raise DumbMoneyPromotionError("contract resolution schema is unsupported")
    checkpoint = payload.get("checkpoint")
    checkpoint_signature = payload.get("checkpoint_signature")
    if not isinstance(checkpoint, dict) or not isinstance(
        checkpoint_signature,
        dict,
    ):
        raise DumbMoneyPromotionError(
            "contract resolution checkpoint and signature must be objects"
        )
    _verify_resolution_checkpoint(
        checkpoint,
        checkpoint_signature,
        core_public_key,
    )
    expected_checkpoint = {
        key: value
        for key, value in payload.items()
        if key not in {"schema", "checkpoint", "checkpoint_signature"}
    }
    expected_checkpoint["schema"] = CONTRACT_RESOLUTION_CHECKPOINT_SCHEMA
    if checkpoint != expected_checkpoint:
        raise DumbMoneyPromotionError(
            "signed checkpoint does not bind the full contract resolution"
        )
    if payload.get("cell_id") != DOPEY_VENUE:
        raise DumbMoneyPromotionError("contract resolution targets another venue cell")
    request_nonce = _sha256_text(
        payload.get("request_nonce"),
        "contract response request_nonce",
    )
    if request_nonce != expected_nonce:
        raise DumbMoneyPromotionError(
            "contract response nonce does not match this request"
        )
    requested_digest = _sha256_text(
        payload.get("requested_body_digest"),
        "contract response requested_body_digest",
    )
    if requested_digest != expected_digest:
        raise DumbMoneyPromotionError(
            "contract response digest does not match this request"
        )
    capital_digest = _sha256_text(
        payload.get("capital_envelope_digest"),
        "contract response capital_envelope_digest",
    )
    if capital_digest != expected_capital_digest:
        raise DumbMoneyPromotionError(
            "contract response is not bound to the active capital envelope"
        )
    fencing_generation = payload.get("fencing_generation")
    if (
        isinstance(fencing_generation, bool)
        or not isinstance(fencing_generation, int)
        or fencing_generation != expected_fencing_generation
    ):
        raise DumbMoneyPromotionError(
            "contract response is not bound to the active capital fence"
        )
    contract_schema = str(payload.get("contract_schema", ""))
    if contract_schema != expected_schema:
        raise DumbMoneyPromotionError(
            "contract response schema does not match this request"
        )
    for field in (
        "transport_window_current",
        "body_window_current",
        "eligible_live_input",
    ):
        if not isinstance(payload.get(field), bool):
            raise DumbMoneyPromotionError(
                f"contract response {field} must be a boolean"
            )
    observed_at = _utc_timestamp(
        payload.get("observed_at"),
        "contract response observed_at",
    )
    now = now_utc.astimezone(timezone.utc)
    if abs(now - observed_at) > MAXIMUM_RESOLUTION_CLOCK_SKEW:
        raise DumbMoneyPromotionError(
            "contract response observed_at is stale or future-dated"
        )
    envelope = payload.get("envelope")
    if not isinstance(envelope, dict):
        raise DumbMoneyPromotionError("contract response envelope must be an object")
    if envelope.get("body_digest") != expected_digest:
        raise DumbMoneyPromotionError(
            "contract envelope body digest does not match the requested digest"
        )
    if envelope.get("body_schema") != expected_schema:
        raise DumbMoneyPromotionError(
            "contract envelope schema does not match the requested schema"
        )
    authority_state = _validated_authority_state(
        payload.get("authority_state"),
        authority=authority,
        now_utc=now_utc,
        evaluator_public_keys=evaluator_public_keys,
    )
    if (
        _utc_timestamp(
            authority_state["evaluated_at"],
            "authority_state.evaluated_at",
        )
        != observed_at
    ):
        raise DumbMoneyPromotionError(
            "contract authority_state evaluated_at does not mirror observed_at"
        )
    raw_proof = payload.get("ledger_proof")
    if not isinstance(raw_proof, dict):
        raise DumbMoneyPromotionError("contract ledger proof must be an object")
    proof_command = {
        "global_sequence": raw_proof.get("global_sequence"),
        "event_id": raw_proof.get("event_id"),
        "event_digest": raw_proof.get("event_digest"),
        "body_schema": expected_schema,
    }
    proof = _validated_ledger_proof(
        raw_proof,
        proof_command,
        envelope,
    )
    if (
        proof["payload_digest"] != expected_digest
        or proof["event_schema"] != expected_schema
    ):
        raise DumbMoneyPromotionError(
            "contract ledger proof does not bind the requested contract"
        )
    expected_authority_event_digest = authority_state[
        (
            "promotion_event_digest"
            if expected_schema == PROMOTION_CERTIFICATE_SCHEMA
            else "passport_event_digest"
        )
    ]
    if proof["event_digest"] != expected_authority_event_digest:
        raise DumbMoneyPromotionError(
            "contract proof event digest does not match current authority_state"
        )
    ledger_head_sequence = int(authority_state["ledger_head_sequence"])
    proof_sequence = int(proof["global_sequence"])
    if proof_sequence > ledger_head_sequence or (
        proof_sequence == ledger_head_sequence
        and proof["event_digest"] != authority_state["ledger_head_digest"]
    ):
        raise DumbMoneyPromotionError(
            "contract proof is not continuous with the authority ledger head"
        )
    if expected_schema == PROMOTION_CERTIFICATE_SCHEMA:
        promotion_verified = verify_promotion_certificate_envelope(
            envelope,
            promoter_public_keys,
            now_utc,
        )
        verified: VerifiedAlphaPassport | VerifiedPromotionCertificate = (
            promotion_verified
        )
        body_not_before = _utc_timestamp(
            promotion_verified.certificate.not_before,
            "promotion.not_before",
        )
        body_expires = _utc_timestamp(
            promotion_verified.certificate.expires_at,
            "promotion.expires_at",
        )
        eligible = (
            body_not_before <= observed_at < body_expires
            and promotion_verified.certificate.stage in LIVE_PROMOTION_STAGES
        )
    else:
        passport_verified = verify_alpha_passport_envelope(
            envelope,
            research_public_keys,
            now_utc,
        )
        verified = passport_verified
        body_not_before = _utc_timestamp(
            passport_verified.passport.created_at,
            "passport.created_at",
        )
        body_expires = _utc_timestamp(
            passport_verified.passport.expires_at,
            "passport.expires_at",
        )
        eligible = body_not_before <= observed_at < body_expires
    wrapper_not_before = _utc_timestamp(
        envelope.get("not_before"),
        "contract envelope not_before",
    )
    wrapper_expires = _utc_timestamp(
        envelope.get("expires_at"),
        "contract envelope expires_at",
    )
    transport_current = wrapper_not_before <= observed_at < wrapper_expires
    body_current = body_not_before <= observed_at < body_expires
    eligible = transport_current and eligible
    if payload["transport_window_current"] is not transport_current:
        raise DumbMoneyPromotionError("contract transport-window projection mismatch")
    if payload["body_window_current"] is not body_current:
        raise DumbMoneyPromotionError("contract body-window projection mismatch")
    if payload["eligible_live_input"] is not eligible:
        raise DumbMoneyPromotionError("contract live-eligibility projection mismatch")
    if not eligible:
        raise DumbMoneyPromotionError(
            "resolved contract is not an eligible current live input"
        )
    return _ResolvedContract(
        contract_schema=contract_schema,
        body_digest=expected_digest,
        envelope=dict(envelope),
        verified=verified,
        authority_state=authority_state,
    )
