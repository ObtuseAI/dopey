"""Content-addressed evidence and causal identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    content_hash: str
    observed_at: str
    source_uri: str
    schema_version: str
    provenance: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CausalIdentity:
    event_id: str
    parent_event_id: str
    session_id: str
    event_time: str
    market_time: str
    data_version: str
    agent_version: str
    policy_version: str
    model_version: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def build_causal_identity(
    parent_event_id: str,
    session_id: str,
    event_time: str,
    market_time: str,
    data_version: str,
    agent_version: str,
    policy_version: str,
    model_version: str,
) -> CausalIdentity:
    payload = {
        "parent_event_id": parent_event_id,
        "session_id": session_id,
        "event_time": event_time,
        "market_time": market_time,
        "data_version": data_version,
        "agent_version": agent_version,
        "policy_version": policy_version,
        "model_version": model_version,
    }
    return CausalIdentity(event_id=canonical_hash(payload), **payload)
