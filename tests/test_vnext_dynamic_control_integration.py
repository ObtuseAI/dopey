"""Integration coverage for dynamic morphology and bounded closed-loop control."""

from __future__ import annotations

from dopey.governor.morphology import select_organism_template
from dopey.metacognition.control_loop import choose_closed_loop_control
from dopey.organisms.templates import OBJECTIVE_SPECIALISTS


def test_all_governed_objectives_build_dynamic_research_only_organisms() -> None:
    for objective in OBJECTIVE_SPECIALISTS:
        template_id, contracts = select_organism_template(
            objective,
            {"unknown_world_dimension_count": 2, "out_of_distribution": False},
        )
        assert template_id.startswith(objective)
        assert len(contracts) >= 12
        assert any(contract.agent_id == "knowledge_boundary_agent" for contract in contracts)
        assert all("place_order" not in contract.capabilities for contract in contracts)
        assert all(contract.failure_policy == "ABSTAIN" for contract in contracts)


def test_closed_loop_can_abstain_but_never_promote_or_change_readiness() -> None:
    control = choose_closed_loop_control(
        {"primary_control": "ABSTAIN", "secondary_controls": ["EXPAND_EVIDENCE"]},
        {"shadow_decision": "EXPAND_EVIDENCE"},
        {"interventions": ["expand_missing_world_model_evidence"]},
        {"automatic_low_yield_termination": False},
        0,
        3,
    )

    assert control["selected_control"] == "ABSTAIN"
    assert control["may_change_readiness"] is False
    assert control["may_promote"] is False
    assert control["may_expand_authority"] is False
    assert "execution_seal" in control["protected_surfaces"]
