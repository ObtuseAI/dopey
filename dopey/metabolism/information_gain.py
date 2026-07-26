"""Estimate normalized research information gain."""

from __future__ import annotations


def estimate_information_gain(
    prior_uncertainty: float,
    posterior_uncertainty: float,
    reusable_evidence_fraction: float,
) -> float:
    for name, value in {
        "prior_uncertainty": prior_uncertainty,
        "posterior_uncertainty": posterior_uncertainty,
        "reusable_evidence_fraction": reusable_evidence_fraction,
    }.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"information-gain input must be within [0, 1]: field={name}, value={value}")
    reduction = max(0.0, prior_uncertainty - posterior_uncertainty)
    return round(min(1.0, reduction + 0.25 * reusable_evidence_fraction), 6)
