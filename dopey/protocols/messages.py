"""Restricted semantic vocabulary for material agent communication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from .identity import CausalIdentity


class MessageType(StrEnum):
    OBSERVATION = "OBSERVATION"
    MEASUREMENT = "MEASUREMENT"
    HYPOTHESIS = "HYPOTHESIS"
    COUNTEREVIDENCE = "COUNTEREVIDENCE"
    UNCERTAINTY = "UNCERTAINTY"
    DATA_GAP = "DATA_GAP"
    CONTROL_REQUEST = "CONTROL_REQUEST"
    VETO = "VETO"
    CALIBRATION_UPDATE = "CALIBRATION_UPDATE"
    SETTLEMENT = "SETTLEMENT"
    HEALTH_ALERT = "HEALTH_ALERT"
    MUTATION_PROPOSAL = "MUTATION_PROPOSAL"


@dataclass(frozen=True)
class ResearchMessage:
    message_id: str
    sender: str
    target: str
    semantic_type: MessageType
    content: dict[str, Any]
    evidence_ids: tuple[str, ...]
    confidence: float
    provenance: str
    causal_identity: CausalIdentity

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["semantic_type"] = self.semantic_type.value
        return record


def validate_message(message: ResearchMessage) -> None:
    if not message.sender or not message.target:
        raise ValueError(
            "research message requires sender and target: "
            f"message_id={message.message_id}"
        )
    if not 0.0 <= message.confidence <= 1.0:
        raise ValueError(
            "research message confidence must be within [0, 1]: "
            f"message_id={message.message_id}, confidence={message.confidence}"
        )
    if message.semantic_type in {
        MessageType.MEASUREMENT,
        MessageType.HYPOTHESIS,
        MessageType.COUNTEREVIDENCE,
        MessageType.SETTLEMENT,
    } and not message.evidence_ids:
        raise ValueError(
            "material message requires evidence references: "
            f"message_id={message.message_id}, semantic_type={message.semantic_type.value}"
        )
