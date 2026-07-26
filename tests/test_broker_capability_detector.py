"""Tests: broker capability detector (test 7)."""
from dopey_execution import BrokerCapabilityDetector


def test_robinhood_options_disabled_unknown_default():
    det = BrokerCapabilityDetector()
    cap = det.detect(
        {"broker": "robinhood_mcp", "options_exec_supported": False,
         "options_exec_known": False, "supported_structures": [], "live": False},
        requested_structure="vertical",
        allow_live=False,
    )
    assert cap["options_exec_supported"] is False
    assert cap["options_exec_known"] is False
    assert cap["supports_structure"] is False
    assert cap["live_allowed"] is False


def test_paper_broker_capability_supported():
    det = BrokerCapabilityDetector()
    from dopey_execution import PaperBroker
    pb = PaperBroker()
    cap = det.detect(pb.get_capabilities(), requested_structure="vertical", allow_live=False)
    assert cap["options_exec_supported"] is True
    assert cap["supports_structure"] is True
