"""dopey_governor — account budget + circuit breakers + the LiveOrderGate (safety kernel).

DOPEY-native package. The LiveOrderGate is the hard boundary: it blocks ALL live orders in the
default (research-only) configuration. No live order may pass unless ALL gates are satisfied.
"""
from .account_budget_policy import AccountBudgetPolicy  # noqa: F401
from .adaptive_circuit_breaker import AdaptiveCircuitBreaker  # noqa: F401
from .live_order_gate import LiveOrderGate, GateConfig  # noqa: F401
from .drawdown_slope_monitor import DrawdownSlopeMonitor  # noqa: F401
from .correlated_exposure_monitor import CorrelatedExposureMonitor  # noqa: F401
from .trade_permission_kernel import TradePermissionKernel  # noqa: F401
