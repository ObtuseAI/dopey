"""Tests: live trading disabled by default + Robinhood cannot place live orders (tests 3, 4, 6, 8)."""
import pytest
from dopey.constitution.execution_seal import (
    ExecutionSealViolation,
    assert_output_research_only,
)
from dopey_core.config import load_config, default_config_path
from dopey_execution import RobinhoodMCPAdapter, ExecutionIntent, LiveTradingDisabledError
from dopey_governor import LiveOrderGate, GateConfig


def test_live_trading_disabled_by_default():
    cfg = load_config(default_config_path())
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["paper_trading_enabled"] is True


def test_no_unofficial_robinhood_api():
    cfg = load_config(default_config_path())
    assert cfg["allow_unofficial_robinhood_api"] is False
    with pytest.raises(ValueError):
        RobinhoodMCPAdapter(allow_unofficial_api=True)


def test_robinhood_cannot_place_live_orders():
    rh = RobinhoodMCPAdapter()
    intent = ExecutionIntent(intent_id="rh1", symbol="SPY", structure="vertical",
                             legs=[{"side": "buy", "strike": 100}], live_allowed=False)
    assert rh.preview_order(intent)["preview"] is True
    intent_live = ExecutionIntent(intent_id="rh2", symbol="SPY", structure="vertical",
                                  legs=[{"side": "buy", "strike": 100}], live_allowed=True)
    with pytest.raises(LiveTradingDisabledError):
        rh.place_order(intent_live)


def test_live_order_gate_blocks_default():
    gate = LiveOrderGate(GateConfig())
    verdict = gate.evaluate(
        intent={"live_allowed": True, "defined_risk": True, "paper": False},
        capability={"supports_structure": True, "options_exec_supported": True},
        proof={"proof_strength": 0.9, "oos_edge": 0.2},
        budget_decision={"approved": True},
    )
    assert verdict["allowed"] is False
    assert verdict["reasons"]


def test_live_order_gate_cannot_be_enabled_by_configuration():
    gate = LiveOrderGate(
        GateConfig(
            mode="ADAPTIVE_LIVE",
            live_trading_enabled=True,
            funded_broker_connections_enabled=True,
            max_first_pass_order_mode="micro_live",
            min_proof_strength=0.0,
            min_oos_edge=0.0,
        )
    )
    verdict = gate.evaluate(
        intent={"live_allowed": True, "defined_risk": True, "paper": False},
        capability={"supports_structure": True, "options_exec_supported": True},
        proof={"proof_strength": 1.0, "oos_edge": 1.0},
        budget_decision={"approved": True},
    )
    assert verdict == {
        "allowed": False,
        "reasons": ["execution_constitution_permanent_live_order_deny"],
        "config_mode": "ADAPTIVE_LIVE",
        "paper_only": True,
        "live_blocked": True,
    }


def test_broker_adapters_reject_live_enablement():
    from dopey_execution import AlpacaOptionsAdapter, TradierOptionsAdapter

    with pytest.raises(ValueError, match="live_enabled cannot be true"):
        RobinhoodMCPAdapter(live_enabled=True)
    with pytest.raises(ValueError, match="live_enabled cannot be true"):
        AlpacaOptionsAdapter(live_enabled=True)
    with pytest.raises(ValueError, match="live_enabled cannot be true"):
        TradierOptionsAdapter(live_enabled=True)


def test_execution_seal_accepts_only_literal_false_for_denied_capability_keys():
    assert_output_research_only(
        {
            "paper_only": True,
            "live_blocked": True,
            "action_ready": False,
            "constitution": {
                "credential_access": False,
                "live_order_authority": False,
            },
        }
    )
    with pytest.raises(ExecutionSealViolation, match="forbidden nested key"):
        assert_output_research_only(
            {
                "paper_only": True,
                "live_blocked": True,
                "action_ready": False,
                "constitution": {"credential_access": "false"},
            }
        )
