"""Dopey overfit detector: deterministic overfit flag (research stub).

DOPEY-native stub. Flags overfit when OOS edge collapses relative to IS edge.
"""
from __future__ import annotations


def detect_overfit(is_mean: float, oos_mean: float, ratio_threshold: float = 0.5) -> dict:
    overfit = is_mean > 0 and (oos_mean / is_mean) < ratio_threshold
    return {"overfit_flag": bool(overfit), "is_mean": round(is_mean, 6), "oos_mean": round(oos_mean, 6)}
