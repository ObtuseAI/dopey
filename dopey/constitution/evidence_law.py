"""Evidence identity and provenance law."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class EvidenceLawViolation(ValueError):
    """Raised when evidence is missing constitutional identity fields."""


REQUIRED_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "content_hash",
        "observed_at",
        "source_uri",
        "schema_version",
        "provenance",
    }
)


def validate_evidence_record(record: Mapping[str, Any]) -> None:
    missing = sorted(field for field in REQUIRED_EVIDENCE_FIELDS if not record.get(field))
    if missing:
        raise EvidenceLawViolation(
            "evidence record violates identity law: "
            f"missing_fields={missing}, evidence_id={record.get('evidence_id', '')}"
        )


def validate_evidence_records(records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        raise EvidenceLawViolation("material research requires at least one evidence record")
    for record in records:
        validate_evidence_record(record)
