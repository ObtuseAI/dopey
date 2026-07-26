"""Protected/evolvable surface firewall for mutation proposals."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .invariants import EVOLVABLE_SURFACES, PROTECTED_SURFACES


class MutationProtectionViolation(PermissionError):
    """Raised when a proposal targets a constitutional surface."""


def assert_mutation_proposal_safe(proposal: Mapping[str, Any]) -> None:
    surface = str(proposal.get("surface", "")).strip()
    if not surface:
        raise MutationProtectionViolation("mutation proposal requires an explicit surface")
    if surface in PROTECTED_SURFACES:
        raise MutationProtectionViolation(
            "mutation proposal targets a protected surface: "
            f"surface={surface}"
        )
    if surface not in EVOLVABLE_SURFACES:
        raise MutationProtectionViolation(
            "mutation proposal targets an unrecognized surface: "
            f"surface={surface}"
        )
    if proposal.get("auto_apply") is not False:
        raise MutationProtectionViolation("mutation proposals must set auto_apply=false")
    if proposal.get("promotion_state") not in {"EXPERIMENTAL", "SHADOW_ONLY"}:
        raise MutationProtectionViolation(
            "mutation proposal must remain EXPERIMENTAL or SHADOW_ONLY: "
            f"promotion_state={proposal.get('promotion_state')}"
        )
