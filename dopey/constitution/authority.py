"""Typed authority domains with a research-only root."""

from __future__ import annotations

from enum import StrEnum


class Authority(StrEnum):
    OBSERVE = "OBSERVE"
    RESEARCH = "RESEARCH"
    ADVERSARIAL_REVIEW = "ADVERSARIAL_REVIEW"
    SETTLEMENT = "SETTLEMENT"
    SHADOW_CONTROL = "SHADOW_CONTROL"


class AuthorityViolation(PermissionError):
    """Raised when a component requests authority outside research scope."""


def assert_research_authority(authority: Authority) -> None:
    if authority not in frozenset(Authority):
        raise AuthorityViolation(f"unsupported DOPEY authority: authority={authority!s}")


def assert_no_authority_escalation(current: Authority, requested: Authority) -> None:
    allowed_transitions: dict[Authority, frozenset[Authority]] = {
        Authority.OBSERVE: frozenset({Authority.OBSERVE}),
        Authority.RESEARCH: frozenset({Authority.OBSERVE, Authority.RESEARCH}),
        Authority.ADVERSARIAL_REVIEW: frozenset({Authority.OBSERVE, Authority.ADVERSARIAL_REVIEW}),
        Authority.SETTLEMENT: frozenset({Authority.OBSERVE, Authority.SETTLEMENT}),
        Authority.SHADOW_CONTROL: frozenset({Authority.OBSERVE, Authority.SHADOW_CONTROL}),
    }
    if requested not in allowed_transitions[current]:
        raise AuthorityViolation(
            "agent authority escalation denied: "
            f"current={current.value}, requested={requested.value}"
        )
