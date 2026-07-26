"""Stable hashing helpers for portfolio replay records."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_portfolio_hash(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

