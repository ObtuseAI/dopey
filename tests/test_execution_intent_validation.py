"""Tests: execution-intent validation + PaperBroker preview (tests 5, 9)."""
from dopey_execution import ExecutionIntent, PaperBroker


def test_execution_intent_defaults_live_false():
    intent = ExecutionIntent(intent_id="x", symbol="SPY", structure="vertical",
                             legs=[{"side": "buy", "strike": 100}])
    assert intent.live_allowed is False
    assert intent.defined_risk is True
    assert intent.paper is True


def test_execution_intent_validation_surfaces_errors():
    bad = ExecutionIntent(intent_id="", symbol="", structure="vertical", legs=[],
                          quantity=0, defined_risk=False)
    assert bad.validate()


def test_paper_broker_preview_simulated_order():
    broker = PaperBroker()
    intent = ExecutionIntent(intent_id="t1", symbol="SPY", structure="vertical",
                             legs=[{"side": "buy", "strike": 100}, {"side": "sell", "strike": 105}])
    preview = broker.preview_order(intent)
    assert preview["preview"] is True
    assert preview["paper"] is True
    assert preview["valid"] is True
    placed = broker.place_order(intent)
    assert placed["ok"] is True
    assert placed["paper"] is True
