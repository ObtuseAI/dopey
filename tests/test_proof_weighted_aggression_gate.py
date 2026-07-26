"""Tests: proof-weighted aggression gate demote/promote (test 10)."""
from dopey_edge import ProofWeightedAggressionGate


def test_weak_proof_demotes():
    gate = ProofWeightedAggressionGate()
    cap = {"options_exec_supported": True}
    weak = {"overfit_flag": True, "proof_strength": 0.2, "oos_edge": 0.0,
            "signal_decay": 0.6, "drawdown_slope": 0.08, "slippage_bps": 20}
    dec = gate.decide({"genome_id": "g1", "family": "f", "preferred_regime": "neutral"},
                      weak, liquidity=0.1, regime="neutral", broker_capability=cap)
    assert dec.decision == "demote"


def test_strong_proof_promotes():
    gate = ProofWeightedAggressionGate()
    cap = {"options_exec_supported": True}
    strong = {"overfit_flag": False, "proof_strength": 0.9, "oos_edge": 0.3,
              "walk_forward_consistency": 0.8, "paper_fill_quality": 0.9,
              "regime_alignment": True, "capital_efficiency": 0.8, "family_proof": True,
              "signal_decay": 0.0, "drawdown_slope": 0.0, "slippage_bps": 1}
    dec = gate.decide({"genome_id": "g2", "family": "f", "preferred_regime": "neutral"},
                      strong, liquidity=0.9, regime="neutral", broker_capability=cap)
    assert dec.decision == "promote"


def test_gate_is_deterministic():
    gate = ProofWeightedAggressionGate()
    cap = {"options_exec_supported": True}
    strong = {"overfit_flag": False, "proof_strength": 0.9, "oos_edge": 0.3,
              "walk_forward_consistency": 0.8, "paper_fill_quality": 0.9,
              "regime_alignment": True, "capital_efficiency": 0.8, "family_proof": True,
              "signal_decay": 0.0, "drawdown_slope": 0.0, "slippage_bps": 1}
    a = gate.score({"genome_id": "g2", "family": "f"}, strong, 0.9, "neutral", cap).score
    b = gate.score({"genome_id": "g2", "family": "f"}, strong, 0.9, "neutral", cap).score
    assert a == b


def test_broker_capability_cannot_change_edge_conviction() -> None:
    gate = ProofWeightedAggressionGate()
    proof = {"proof_strength": 0.9, "oos_edge": 0.3, "walk_forward_consistency": 0.8}
    genome = {"genome_id": "g3", "family": "f"}
    supported = gate.decide(genome, proof, 0.9, "neutral", {"options_exec_supported": True})
    unsupported = gate.decide(genome, proof, 0.9, "neutral", {"options_exec_supported": False})
    assert supported.to_dict() == unsupported.to_dict()


def test_execution_eligibility_is_independent_and_fail_closed() -> None:
    gate = ProofWeightedAggressionGate()
    proof = {"proof_strength": 0.9, "oos_edge": 0.3, "walk_forward_consistency": 0.8}
    evaluation = gate.evaluate(
        {"genome_id": "g4", "family": "f"},
        proof,
        0.9,
        "neutral",
        {"options_exec_supported": True, "live_trading_enabled": False, "human_approval_present": False},
    )
    assert evaluation.edge_decision.decision == "promote"
    assert evaluation.execution_eligibility.status == "execution_blocked"
    assert evaluation.execution_eligibility.reason_codes == ["live_trading_disabled", "human_approval_missing"]
