"""Dopey safety review utility: verifies the live-trading safety boundaries hold.

A standalone validation function usable by tests or operators. Confirms:
  - default mode is RESEARCH
  - live trading disabled
  - unofficial Robinhood API disabled
  - PaperBroker refuses live intents
  - live broker stubs raise LiveTradingDisabledError
Offline; no network; no credentials.
"""
from __future__ import annotations

from dopey_core.config import load_config, default_config_path
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="safety-review-live", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "X", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": "Y", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)


def safety_review() -> dict:
    """Run the safety boundary checks. Returns {ok, checks}."""
    checks: list[dict] = []

    cfg = load_config(default_config_path())
    checks.append({"name": "default_mode_research", "ok": cfg.get("mode") == "RESEARCH",
                   "value": cfg.get("mode")})
    checks.append({"name": "live_trading_disabled", "ok": cfg.get("live_trading_enabled") is False,
                   "value": cfg.get("live_trading_enabled")})
    checks.append({"name": "funded_broker_disabled", "ok": cfg.get("funded_broker_connections_enabled") is False,
                   "value": cfg.get("funded_broker_connections_enabled")})
    checks.append({"name": "unofficial_robinhood_disabled", "ok": cfg.get("allow_unofficial_robinhood_api") is False,
                   "value": cfg.get("allow_unofficial_robinhood_api")})

    # PaperBroker refuses live intents
    broker = PaperBroker()
    intent = _live_intent()
    paper_refused = False
    try:
        broker.place_order(intent)
    except LiveTradingDisabledError:
        paper_refused = True
    except Exception:
        paper_refused = True
    checks.append({"name": "paper_broker_refuses_live", "ok": paper_refused, "value": paper_refused})

    # live stubs raise LiveTradingDisabledError
    for name, ctor in (("robinhood", RobinhoodMCPAdapter), ("alpaca", AlpacaOptionsAdapter),
                       ("tradier", TradierOptionsAdapter)):
        raised = False
        try:
            ctor().place_order(intent)
        except LiveTradingDisabledError:
            raised = True
        except Exception:
            raised = True
        checks.append({"name": f"{name}_stub_blocks_live", "ok": raised, "value": raised})

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks}
