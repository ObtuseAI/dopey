"""DOPEY vNext governed market-intelligence architecture.

The vNext package wraps existing research engines with immutable authority,
evidence, metacognitive, and settlement contracts. It has no execution API.
"""

from .constitution.execution_seal import execution_seal_state

VNEXT_VERSION = "dopey-vnext-vertical-slice-v1"

__all__ = ["VNEXT_VERSION", "execution_seal_state"]
