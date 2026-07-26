"""Non-readiness policy field exposed to organism construction."""

from __future__ import annotations


def research_policy_field() -> dict[str, bool | str]:
    return {
        "policy_version": "dopey-sovereign-research-governor-v1",
        "consensus_is_proof": False,
        "may_mark_action_ready": False,
        "may_bypass_evidence_gates": False,
        "may_modify_protected_rules": False,
        "may_create_broker_authority": False,
        "paper_only": True,
        "live_blocked": True,
    }
