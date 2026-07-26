"""Live gate constants."""
from __future__ import annotations


LIVE_GATE_VERSION = "dopey-live-gate-separated-disabled-v1"
LIVE_GATE_STATUS = {
    "live_trading_enabled": False,
    "broker_connection_enabled": False,
    "real_order_enabled": False,
    "credentials_present": False,
    "human_live_approval_required": True,
    "paper_champions_required": True,
    "capital_risk_review_required": True,
    "separate_future_bundle_required": True,
}

