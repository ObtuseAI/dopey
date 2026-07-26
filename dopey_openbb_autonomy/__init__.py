"""OpenBB adapter autonomy for DOPEY research-only data discovery."""
from __future__ import annotations

from .openbb_runtime_detector import detect_openbb_runtime
from .openbb_provider_registry import run_openbb_provider_registry

__all__ = ["detect_openbb_runtime", "run_openbb_provider_registry"]
