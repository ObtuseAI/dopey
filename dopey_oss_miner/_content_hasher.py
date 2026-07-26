"""Dopey content hasher: SHA256 over bytes/text/files.

Forked verbatim from Blunder inflow content_hasher (Z:\\BFORK-20260630-020500\\blunder\\inflow\\
content_hasher.py). Renamed module only; logic unchanged.

DOPEY lineage: Blunder inflow/content_hasher.py -> dopey_oss_miner._content_hasher
"""
from __future__ import annotations

from pathlib import Path
import hashlib


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8", errors="replace"))


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())
