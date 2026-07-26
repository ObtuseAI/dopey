"""Dopey drawdown slope monitor: detect drawdown acceleration (research stub)."""
from __future__ import annotations


class DrawdownSlopeMonitor:
    def __init__(self, accel_threshold: float = 0.05):
        self.accel_threshold = accel_threshold

    def slope(self, equity_curve: list[float]) -> dict:
        if len(equity_curve) < 3:
            return {"slope": 0.0, "acceleration": 0.0, "accelerating": False}
        n = len(equity_curve)
        xs = list(range(n))
        # linear slope
        xmean, ymean = sum(xs) / n, sum(equity_curve) / n
        num = sum((xs[i] - xmean) * (equity_curve[i] - ymean) for i in range(n))
        den = sum((x - xmean) ** 2 for x in xs) or 1.0
        slope = num / den
        # acceleration = second difference of last three
        a, b, c = equity_curve[-3], equity_curve[-2], equity_curve[-1]
        accel = (c - b) - (b - a)
        return {
            "slope": round(slope, 6),
            "acceleration": round(accel, 6),
            "accelerating": bool(accel < -self.accel_threshold),
        }
