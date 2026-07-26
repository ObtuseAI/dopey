"""Canonical identities used by immutable contracts and append-only ledgers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_hash(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_sha256(value: str, field_name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(
            "content identity must be a lowercase hexadecimal SHA-256: "
            f"field_name={field_name}, value={value!r}"
        )
    return value


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include an offset: value={value!r}")
    return parsed.astimezone(timezone.utc)


def require_utc_iso(value: str) -> str:
    parsed = parse_utc(value)
    canonical = parsed.isoformat().replace("+00:00", "Z")
    if value != canonical:
        raise ValueError(
            "timestamp must be canonical UTC ISO-8601: "
            f"value={value!r}, expected={canonical!r}"
        )
    return value
