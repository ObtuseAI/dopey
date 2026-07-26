"""Dopey execution errors: safety exception types.

DOPEY-native. LiveTradingDisabledError is raised whenever any code path attempts a live order
while live trading is not explicitly enabled.
"""
from __future__ import annotations


class DopeyExecutionError(Exception):
    """Base error for the Dopey execution layer."""


class LiveTradingDisabledError(DopeyExecutionError):
    """Raised when a live order is attempted while live trading is disabled (default)."""


class UndefinedRiskBlockedError(DopeyExecutionError):
    """Raised when an undefined-risk structure is attempted (defined-risk default)."""


class BrokerCapabilityMissingError(DopeyExecutionError):
    """Raised when the broker does not support the requested structure."""
