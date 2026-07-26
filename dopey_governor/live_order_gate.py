"""Permanent live-order denial boundary for the DOPEY research repository.

No configuration, proof, capability, budget, or caller input can unlock live order
authority. A separately reviewed deployment repository would be required for any future
real-capital work.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GateConfig:
    mode: str = "RESEARCH"                       # RESEARCH | PAPER | MICRO_LIVE | ADAPTIVE_LIVE
    live_trading_enabled: bool = False
    funded_broker_connections_enabled: bool = False
    allow_unofficial_robinhood_api: bool = False
    paper_trading_enabled: bool = True
    default_structure_policy: str = "defined_risk_first"
    max_first_pass_order_mode: str = "none"     # none | paper | micro_live
    min_proof_strength: float = 0.6
    min_oos_edge: float = 0.05


class LiveOrderGate:
    def __init__(self, config: GateConfig | None = None):
        self.config = config or GateConfig()

    def evaluate(self, *, intent: dict, capability: dict, proof: dict,
                 budget_decision: dict) -> dict:
        """Deny a live-order request regardless of supplied state."""
        del intent, capability, proof, budget_decision
        return {
            "allowed": False,
            "reasons": ["execution_constitution_permanent_live_order_deny"],
            "config_mode": self.config.mode,
            "paper_only": True,
            "live_blocked": True,
        }

    @classmethod
    def from_config_dict(cls, cfg: dict) -> "LiveOrderGate":
        fields = {k: v for k, v in cfg.items() if k in GateConfig.__dataclass_fields__}
        return cls(GateConfig(**fields))
