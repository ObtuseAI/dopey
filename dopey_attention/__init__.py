"""Governed, research-only market attention detection."""

from .engine import (
    ATTENTION_ENGINE_VERSION,
    ATTENTION_SCHEMA_VERSION,
    AttentionDataError,
    build_attention_snapshot,
    default_attention_policy,
    write_attention_snapshot,
)

__all__ = [
    "ATTENTION_ENGINE_VERSION",
    "ATTENTION_SCHEMA_VERSION",
    "AttentionDataError",
    "build_attention_snapshot",
    "default_attention_policy",
    "write_attention_snapshot",
]
