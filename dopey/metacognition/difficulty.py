"""Estimate task difficulty from missing evidence and contradiction."""

from __future__ import annotations


def estimate_difficulty(
    evidence_completeness: float,
    regime_familiarity: float,
    disagreement: float,
    contradiction_count: int,
) -> dict[str, float | str]:
    if contradiction_count < 0:
        raise ValueError(f"contradiction count cannot be negative: count={contradiction_count}")
    score = (
        0.35 * (1.0 - evidence_completeness)
        + 0.30 * (1.0 - regime_familiarity)
        + 0.25 * disagreement
        + 0.10 * min(1.0, contradiction_count / 3.0)
    )
    level = "HIGH" if score >= 0.65 else "MEDIUM" if score >= 0.35 else "LOW"
    return {"score": round(score, 6), "level": level}
