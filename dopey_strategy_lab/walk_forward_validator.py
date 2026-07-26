"""Dopey walk-forward validator: deterministic walk-forward consistency (research stub).

DOPEY-native stub. Computes a naive walk-forward consistency score from in-sample / out-of-sample
edge arrays. No live exec.
"""
from __future__ import annotations


def walk_forward_validate(is_edges: list[float], oos_edges: list[float]) -> dict:
    if not is_edges or not oos_edges:
        return {"consistency": 0.0, "oos_mean": 0.0, "is_mean": 0.0}
    is_mean = sum(is_edges) / len(is_edges)
    oos_mean = sum(oos_edges) / len(oos_edges)
    consistency = 0.0 if is_mean == 0 else max(0.0, min(1.0, oos_mean / is_mean))
    return {
        "consistency": round(consistency, 6),
        "oos_mean": round(oos_mean, 6),
        "is_mean": round(is_mean, 6),
    }
