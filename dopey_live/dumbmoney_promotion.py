"""Authenticated DumbMoney promotion lineage for Robinhood entry intents.

An entry strategy hash is not authority.  The only accepted lineage is an
AlphaPassportV1 signed by a sealed research key and a PromotionCertificateV1
signed by a disjoint sealed promoter key.  Their canonical body digests must
also be the one singleton tuple named by the active CapitalEnvelopeV1.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Final, Mapping, Protocol

from .dumbmoney_authority import (
    DOPEY_VENUE,
    EQUITY_INSTRUMENT_ID_PATTERN,
    IDENTIFIER_PATTERN,
    OPTION_INSTRUMENT_ID_PATTERN,
    DumbMoneyAuthorityError,
    VerifiedCapitalAuthority,
    _decode_public_key,
    _exact_fields,
    _hash_array,
    _identifier_array,
    _positive_int,
    _sha256_text,
    _utc_timestamp,
    _verify_signed_wrapper,
    intent_authorized_instrument_id,
    intent_incremental_risk_cents,
)
from .models import LiveExecutionIntent


ALPHA_PASSPORT_SCHEMA: Final[str] = "dumbmoney.alpha_passport.v1"
PROMOTION_CERTIFICATE_SCHEMA: Final[str] = "dumbmoney.promotion-certificate.v1"
LIVE_PROMOTION_STAGES: Final[frozenset[str]] = frozenset(
    {"EXPLORATORY_LIVE", "AGGRESSIVE_BOUNDED"}
)
EVIDENCE_CLASSES: Final[frozenset[str]] = frozenset(
    {"SYNTHETIC", "REPLAY", "BACKTEST", "PAPER", "FORWARD", "REALIZED"}
)
PROMOTION_STAGES: Final[frozenset[str]] = frozenset(
    {
        "IDEA",
        "REPLAY",
        "POINT_IN_TIME_BACKTEST",
        "FORWARD_SHADOW",
        "PAPER",
        *LIVE_PROMOTION_STAGES,
    }
)
ALPHA_PASSPORT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "passport_id",
        "strategy_lineage_id",
        "venue",
        "strategy_hash",
        "artifact_hashes",
        "evidence_verdict_hashes",
        "intended_instruments",
        "maximum_loss_cents",
        "evidence_class",
        "created_at",
        "expires_at",
    }
)
PROMOTION_CERTIFICATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "certificate_id",
        "passport_digest",
        "verdict_digests",
        "stage",
        "venue",
        "instruments",
        "maximum_loss_cents",
        "rollback_triggers",
        "policy_epoch",
        "not_before",
        "expires_at",
    }
)


class DumbMoneyPromotionError(DumbMoneyAuthorityError):
    """Raised when signed research-to-live lineage cannot be proven."""


@dataclass(frozen=True)
class AlphaPassportV1:
    passport_id: str
    strategy_lineage_id: str
    venue: str
    strategy_hash: str
    artifact_hashes: tuple[str, ...]
    evidence_verdict_hashes: tuple[str, ...]
    intended_instruments: tuple[str, ...]
    maximum_loss_cents: int
    evidence_class: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class PromotionCertificateV1:
    certificate_id: str
    passport_digest: str
    verdict_digests: tuple[str, ...]
    stage: str
    venue: str
    instruments: tuple[str, ...]
    maximum_loss_cents: int
    rollback_triggers: tuple[str, ...]
    policy_epoch: int
    not_before: str
    expires_at: str


@dataclass(frozen=True)
class VerifiedAlphaPassport:
    passport: AlphaPassportV1
    event_id: str
    body_digest: str
    signer_key_id: str
    wrapper_expires_at: str


@dataclass(frozen=True)
class VerifiedPromotionCertificate:
    certificate: PromotionCertificateV1
    event_id: str
    body_digest: str
    signer_key_id: str
    wrapper_expires_at: str


@dataclass(frozen=True)
class VerifiedPromotionBinding:
    """Exact signed lineage pinned to one active capital fence."""

    strategy_hash: str
    passport_hash: str
    promotion_hash: str
    instrument_id: str
    maximum_loss_cents: int
    policy_epoch: int
    capital_envelope_id: str
    capital_event_id: str
    capital_body_digest: str
    capital_fencing_generation: int
    passport_event_id: str
    promotion_event_id: str
    passport_signer_key_id: str
    promotion_signer_key_id: str
    expires_at: str

    def evidence(self) -> dict[str, Any]:
        return {
            "strategy_hash": self.strategy_hash,
            "passport_hash": self.passport_hash,
            "promotion_hash": self.promotion_hash,
            "instrument_id": self.instrument_id,
            "maximum_loss_cents": self.maximum_loss_cents,
            "policy_epoch": self.policy_epoch,
            "capital_envelope_id": self.capital_envelope_id,
            "capital_event_id": self.capital_event_id,
            "capital_body_digest": self.capital_body_digest,
            "capital_fencing_generation": self.capital_fencing_generation,
            "passport_event_id": self.passport_event_id,
            "promotion_event_id": self.promotion_event_id,
            "passport_signer_key_id": self.passport_signer_key_id,
            "promotion_signer_key_id": self.promotion_signer_key_id,
            "expires_at": self.expires_at,
        }


class PromotionAuthorityResolver(Protocol):
    """Resolve and authenticate the lineage immediately before use."""

    def bind_intent(
        self,
        authority: VerifiedCapitalAuthority,
        intent: LiveExecutionIntent,
        now_utc: datetime,
        *,
        expected_binding: VerifiedPromotionBinding | None = None,
    ) -> tuple[LiveExecutionIntent, VerifiedPromotionBinding]: ...


def _identifier(value: Any, label: str) -> str:
    text = str(value)
    if not IDENTIFIER_PATTERN.fullmatch(text):
        raise DumbMoneyPromotionError(f"{label} is not a canonical identifier")
    return text


def _instrument_array(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    values = _identifier_array(payload, field)
    unsupported = tuple(
        value
        for value in values
        if not (
            EQUITY_INSTRUMENT_ID_PATTERN.fullmatch(value)
            or OPTION_INSTRUMENT_ID_PATTERN.fullmatch(value)
        )
    )
    if unsupported:
        raise DumbMoneyPromotionError(
            f"{field} contains noncanonical Dopey instrument IDs: {unsupported}"
        )
    return values


def _possibly_empty_hash_array(
    payload: dict[str, Any],
    field: str,
) -> tuple[str, ...]:
    values = payload.get(field)
    if not isinstance(values, list):
        raise DumbMoneyPromotionError(f"{field} must be an array")
    normalized = tuple(_sha256_text(value, field) for value in values)
    if normalized != tuple(sorted(set(normalized))):
        raise DumbMoneyPromotionError(f"{field} must be sorted and duplicate-free")
    return normalized


def _sealed_role_keyring(
    keys: Mapping[str, bytes],
    role: str,
) -> dict[str, bytes]:
    if not isinstance(keys, Mapping) or not 1 <= len(keys) <= 16:
        raise DumbMoneyPromotionError(
            f"sealed {role} public-key set must contain 1 to 16 keys"
        )
    verified: dict[str, bytes] = {}
    for raw_key_id, raw_key in keys.items():
        key_id = _sha256_text(raw_key_id, f"{role} key ID")
        try:
            public_key = _decode_public_key(raw_key)
        except DumbMoneyAuthorityError as error:
            raise DumbMoneyPromotionError(
                f"sealed {role} public key is invalid: key_id={key_id}"
            ) from error
        if hashlib.sha256(public_key).hexdigest() != key_id:
            raise DumbMoneyPromotionError(
                f"sealed {role} key ID does not bind its key: key_id={key_id}"
            )
        verified[key_id] = public_key
    return verified


def validated_role_keyrings(
    promoter_public_keys: Mapping[str, bytes],
    research_public_keys: Mapping[str, bytes],
    *,
    core_public_key: bytes | None = None,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    promoter = _sealed_role_keyring(promoter_public_keys, "promoter")
    research = _sealed_role_keyring(research_public_keys, "research")
    overlap = set(promoter) & set(research)
    if overlap:
        raise DumbMoneyPromotionError(
            "sealed promoter and research public-key sets must be disjoint"
        )
    if core_public_key is not None:
        try:
            core_key_id = hashlib.sha256(
                _decode_public_key(core_public_key)
            ).hexdigest()
        except DumbMoneyAuthorityError as error:
            raise DumbMoneyPromotionError(
                "pinned Core public key is invalid"
            ) from error
        if core_key_id in promoter or core_key_id in research:
            raise DumbMoneyPromotionError(
                "Core, promoter, and research signing roles must be disjoint"
            )
    return promoter, research


def _alpha_passport(
    payload: dict[str, Any],
    now_utc: datetime,
) -> AlphaPassportV1:
    _exact_fields(payload, ALPHA_PASSPORT_FIELDS, "AlphaPassportV1")
    if payload.get("schema") != ALPHA_PASSPORT_SCHEMA:
        raise DumbMoneyPromotionError("AlphaPassportV1 schema is unsupported")
    if payload.get("venue") != DOPEY_VENUE:
        raise DumbMoneyPromotionError("AlphaPassportV1 is not for dopey_robinhood")
    evidence_class = str(payload.get("evidence_class", ""))
    if evidence_class not in EVIDENCE_CLASSES:
        raise DumbMoneyPromotionError("AlphaPassportV1 evidence_class is unsupported")
    created_at = str(payload.get("created_at", ""))
    expires_at = str(payload.get("expires_at", ""))
    created = _utc_timestamp(created_at, "passport.created_at")
    expires = _utc_timestamp(expires_at, "passport.expires_at")
    if expires <= created:
        raise DumbMoneyPromotionError("AlphaPassportV1 validity interval is empty")
    now = now_utc.astimezone(timezone.utc)
    if not created <= now < expires:
        raise DumbMoneyPromotionError("AlphaPassportV1 is not currently valid")
    return AlphaPassportV1(
        passport_id=_identifier(payload.get("passport_id"), "passport_id"),
        strategy_lineage_id=_identifier(
            payload.get("strategy_lineage_id"),
            "strategy_lineage_id",
        ),
        venue=DOPEY_VENUE,
        strategy_hash=_sha256_text(
            payload.get("strategy_hash"),
            "passport.strategy_hash",
        ),
        artifact_hashes=_hash_array(payload, "artifact_hashes"),
        evidence_verdict_hashes=_possibly_empty_hash_array(
            payload,
            "evidence_verdict_hashes",
        ),
        intended_instruments=_instrument_array(payload, "intended_instruments"),
        maximum_loss_cents=_positive_int(payload, "maximum_loss_cents"),
        evidence_class=evidence_class,
        created_at=created_at,
        expires_at=expires_at,
    )


def _promotion_certificate(
    payload: dict[str, Any],
    now_utc: datetime,
) -> PromotionCertificateV1:
    _exact_fields(
        payload,
        PROMOTION_CERTIFICATE_FIELDS,
        "PromotionCertificateV1",
    )
    if payload.get("schema") != PROMOTION_CERTIFICATE_SCHEMA:
        raise DumbMoneyPromotionError("PromotionCertificateV1 schema is unsupported")
    if payload.get("venue") != DOPEY_VENUE:
        raise DumbMoneyPromotionError(
            "PromotionCertificateV1 is not for dopey_robinhood"
        )
    stage = str(payload.get("stage", ""))
    if stage not in PROMOTION_STAGES:
        raise DumbMoneyPromotionError("PromotionCertificateV1 stage is unsupported")
    not_before = str(payload.get("not_before", ""))
    expires_at = str(payload.get("expires_at", ""))
    starts = _utc_timestamp(not_before, "promotion.not_before")
    expires = _utc_timestamp(expires_at, "promotion.expires_at")
    if expires <= starts:
        raise DumbMoneyPromotionError(
            "PromotionCertificateV1 validity interval is empty"
        )
    now = now_utc.astimezone(timezone.utc)
    if not starts <= now < expires:
        raise DumbMoneyPromotionError("PromotionCertificateV1 is not currently valid")
    rollback_triggers = _identifier_array(payload, "rollback_triggers")
    return PromotionCertificateV1(
        certificate_id=_identifier(
            payload.get("certificate_id"),
            "certificate_id",
        ),
        passport_digest=_sha256_text(
            payload.get("passport_digest"),
            "promotion.passport_digest",
        ),
        verdict_digests=_hash_array(payload, "verdict_digests"),
        stage=stage,
        venue=DOPEY_VENUE,
        instruments=_instrument_array(payload, "instruments"),
        maximum_loss_cents=_positive_int(payload, "maximum_loss_cents"),
        rollback_triggers=rollback_triggers,
        policy_epoch=_positive_int(payload, "policy_epoch"),
        not_before=not_before,
        expires_at=expires_at,
    )


def verify_alpha_passport_envelope(
    envelope: dict[str, Any],
    research_public_keys: Mapping[str, bytes],
    now_utc: datetime,
) -> VerifiedAlphaPassport:
    """Authenticate and parse one current research-signed passport."""

    research = _sealed_role_keyring(research_public_keys, "research")
    signer_key_id = _sha256_text(
        envelope.get("signer_key_id"),
        "passport signer_key_id",
    )
    public_key = research.get(signer_key_id)
    if public_key is None:
        raise DumbMoneyPromotionError(
            "AlphaPassportV1 signer is outside the sealed research key set"
        )
    wrapper = _verify_signed_wrapper(
        envelope,
        public_key,
        now_utc,
        enforce_current_window=True,
    )
    if wrapper.body_schema != ALPHA_PASSPORT_SCHEMA:
        raise DumbMoneyPromotionError("resolved envelope is not AlphaPassportV1")
    passport = _alpha_passport(wrapper.body, now_utc)
    return VerifiedAlphaPassport(
        passport=passport,
        event_id=wrapper.event_id,
        body_digest=wrapper.body_digest,
        signer_key_id=wrapper.signer_key_id,
        wrapper_expires_at=wrapper.expires_at,
    )


def verify_promotion_certificate_envelope(
    envelope: dict[str, Any],
    promoter_public_keys: Mapping[str, bytes],
    now_utc: datetime,
) -> VerifiedPromotionCertificate:
    """Authenticate and parse one current promoter-signed certificate."""

    promoter = _sealed_role_keyring(promoter_public_keys, "promoter")
    signer_key_id = _sha256_text(
        envelope.get("signer_key_id"),
        "promotion signer_key_id",
    )
    public_key = promoter.get(signer_key_id)
    if public_key is None:
        raise DumbMoneyPromotionError(
            "PromotionCertificateV1 signer is outside the sealed promoter key set"
        )
    wrapper = _verify_signed_wrapper(
        envelope,
        public_key,
        now_utc,
        enforce_current_window=True,
    )
    if wrapper.body_schema != PROMOTION_CERTIFICATE_SCHEMA:
        raise DumbMoneyPromotionError("resolved envelope is not PromotionCertificateV1")
    promotion = _promotion_certificate(wrapper.body, now_utc)
    return VerifiedPromotionCertificate(
        certificate=promotion,
        event_id=wrapper.event_id,
        body_digest=wrapper.body_digest,
        signer_key_id=wrapper.signer_key_id,
        wrapper_expires_at=wrapper.expires_at,
    )


def bind_verified_promotion(
    authority: VerifiedCapitalAuthority,
    intent: LiveExecutionIntent,
    passport: VerifiedAlphaPassport,
    promotion: VerifiedPromotionCertificate,
    now_utc: datetime,
    *,
    expected_binding: VerifiedPromotionBinding | None = None,
) -> tuple[LiveExecutionIntent, VerifiedPromotionBinding]:
    """Bind one locally generated intent to an authenticated singleton chain."""

    if intent.side != "buy":
        raise DumbMoneyPromotionError(
            "promotion lineage may only be attached to new-risk buy intents"
        )
    if now_utc.tzinfo is None:
        raise DumbMoneyPromotionError("promotion binding requires an aware UTC clock")
    if expected_binding is None:
        if intent.passport_hash or intent.promotion_hash:
            raise DumbMoneyPromotionError(
                "local intent supplied its own passport or promotion digest"
            )
    else:
        if (
            intent.passport_hash != expected_binding.passport_hash
            or intent.promotion_hash != expected_binding.promotion_hash
        ):
            raise DumbMoneyPromotionError(
                "revalidated intent lineage differs from its authenticated binding"
            )

    if (
        len(authority.envelope.strategy_hashes) != 1
        or len(authority.envelope.passport_hashes) != 1
        or len(authority.envelope.promotion_hashes) != 1
    ):
        raise DumbMoneyPromotionError(
            "active capital authority is not a singleton lineage tuple"
        )
    strategy_hash = authority.envelope.strategy_hashes[0]
    passport_hash = authority.envelope.passport_hashes[0]
    promotion_hash = authority.envelope.promotion_hashes[0]
    if passport.body_digest != passport_hash:
        raise DumbMoneyPromotionError(
            "resolved passport digest differs from active capital authority"
        )
    if promotion.body_digest != promotion_hash:
        raise DumbMoneyPromotionError(
            "resolved promotion digest differs from active capital authority"
        )
    if promotion.certificate.passport_digest != passport.body_digest:
        raise DumbMoneyPromotionError(
            "PromotionCertificateV1 does not bind the resolved AlphaPassportV1"
        )
    if passport.passport.strategy_hash != strategy_hash:
        raise DumbMoneyPromotionError(
            "AlphaPassportV1 strategy differs from active capital authority"
        )
    if intent.source_hash != strategy_hash:
        raise DumbMoneyPromotionError(
            "local intent strategy differs from authenticated singleton lineage"
        )
    if promotion.certificate.stage not in LIVE_PROMOTION_STAGES:
        raise DumbMoneyPromotionError(
            "PromotionCertificateV1 stage is not live-authorizing"
        )
    if promotion.certificate.policy_epoch != authority.envelope.policy_epoch:
        raise DumbMoneyPromotionError("promotion and capital policy epochs differ")

    instrument_id = intent_authorized_instrument_id(intent)
    if (
        instrument_id not in authority.envelope.authorized_instruments
        or instrument_id not in passport.passport.intended_instruments
        or instrument_id not in promotion.certificate.instruments
    ):
        raise DumbMoneyPromotionError(
            "intent instrument is not jointly authorized by capital, "
            "passport, and promotion"
        )
    risk_cents = intent_incremental_risk_cents(intent)
    lineage_maximum_loss = min(
        passport.passport.maximum_loss_cents,
        promotion.certificate.maximum_loss_cents,
    )
    if risk_cents > lineage_maximum_loss:
        raise DumbMoneyPromotionError(
            "intent worst-case loss exceeds authenticated promotion lineage"
        )
    expiry_candidates = (
        authority.envelope.expires_at,
        passport.wrapper_expires_at,
        passport.passport.expires_at,
        promotion.wrapper_expires_at,
        promotion.certificate.expires_at,
    )
    expires_at = min(
        expiry_candidates,
        key=lambda value: _utc_timestamp(value, "lineage expiry"),
    )
    if now_utc.astimezone(timezone.utc) >= _utc_timestamp(
        expires_at,
        "lineage expiry",
    ):
        raise DumbMoneyPromotionError(
            "authenticated promotion binding is already expired"
        )
    binding = VerifiedPromotionBinding(
        strategy_hash=strategy_hash,
        passport_hash=passport_hash,
        promotion_hash=promotion_hash,
        instrument_id=instrument_id,
        maximum_loss_cents=lineage_maximum_loss,
        policy_epoch=authority.envelope.policy_epoch,
        capital_envelope_id=authority.envelope.envelope_id,
        capital_event_id=authority.event_id,
        capital_body_digest=authority.body_digest,
        capital_fencing_generation=authority.envelope.fencing_generation,
        passport_event_id=passport.event_id,
        promotion_event_id=promotion.event_id,
        passport_signer_key_id=passport.signer_key_id,
        promotion_signer_key_id=promotion.signer_key_id,
        expires_at=expires_at,
    )
    if expected_binding is not None and binding != expected_binding:
        raise DumbMoneyPromotionError(
            "promotion lineage or capital fence changed during execution"
        )
    return (
        replace(
            intent,
            passport_hash=passport_hash,
            promotion_hash=promotion_hash,
        ),
        binding,
    )
