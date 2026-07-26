"""dopey_execution — broker-agnostic execution layer (paper-first, live blocked by default).

DOPEY-native package. ExecutionIntent defaults live_allowed=false and defined_risk=true.
PaperBroker simulates paper fills; Robinhood/Alpaca/Tradier adapters are stubs. The
LiveOrderGate (in dopey_governor) blocks every live order unless ALL gates pass.
"""
from .errors import (  # noqa: F401
    DopeyExecutionError,
    LiveTradingDisabledError,
    UndefinedRiskBlockedError,
    BrokerCapabilityMissingError,
)
from .execution_intent import ExecutionIntent  # noqa: F401
from .broker_interface import BrokerInterface  # noqa: F401
from .paper_broker import PaperBroker  # noqa: F401
from .broker_capability_detector import BrokerCapabilityDetector  # noqa: F401
from .order_intent_validator import validate_intent  # noqa: F401
from .robinhood_mcp_adapter import RobinhoodMCPAdapter  # noqa: F401
from .alpaca_options_adapter import AlpacaOptionsAdapter  # noqa: F401
from .tradier_options_adapter import TradierOptionsAdapter  # noqa: F401
from .execution_quality_logger import ExecutionQualityLogger  # noqa: F401
