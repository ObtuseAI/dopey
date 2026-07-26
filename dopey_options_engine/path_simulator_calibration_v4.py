"""Path simulator calibration V4.

Produces calibration records that document the slippage/theta/IV-shock stress
grid applied to V4 path simulations. Pure metadata; no live pricing.
"""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file

from dopey_autonomy.signal_deepening_common import DEEPENING_ROOT


CALIBRATION_PATH = DEEPENING_ROOT / "path_simulator_calibration_v4.jsonl"

IV_REGIMES = ["realized_vol", "realized_vol_plus_10pct", "realized_vol_plus_25pct", "realized_vol_minus_10pct"]
SLIPPAGE_STRESSES = ["low", "normal", "high"]
THETA_STRESSES = ["low", "normal", "high"]
IV_SHOCK_STRESSES = ["normal", "low", "high"]


def build_calibration_grid_v4() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    index = 1
    for iv_regime in IV_REGIMES:
        for slippage in SLIPPAGE_STRESSES:
            for theta in THETA_STRESSES:
                for iv_shock in IV_SHOCK_STRESSES:
                    record = {
                        "artifact_type": "path_simulator_calibration_v4",
                        "calibration_id": f"calib-v4-{index:04d}",
                        "iv_proxy_regime": iv_regime,
                        "slippage_stress": slippage,
                        "theta_stress": theta,
                        "iv_shock_stress": iv_shock,
                        "slippage_multiplier": {"low": 0.015, "normal": 0.04, "high": 0.085}[slippage],
                        "theta_factor": {"low": 0.6, "normal": 1.0, "high": 1.4}[theta],
                        "iv_shock_multiplier": {"low": 0.85, "normal": 1.0, "high": 1.2}[iv_shock],
                        "model_priced": True,
                        "quote_priced": False,
                        "live_trading_enabled": False,
                    }
                    records.append(record_with_hash(record, "record_hash"))
                    index += 1
    write_jsonl_file(CALIBRATION_PATH, records)
    return records


def path_simulator_calibration_v4() -> dict[str, object]:
    grid = build_calibration_grid_v4()
    return {
        "artifact_type": "path_simulator_calibration_v4_summary",
        "calibration_count": len(grid),
        "iv_regimes": IV_REGIMES,
        "slippage_stresses": SLIPPAGE_STRESSES,
        "theta_stresses": THETA_STRESSES,
        "iv_shock_stresses": IV_SHOCK_STRESSES,
        "calibration_path": str(CALIBRATION_PATH),
        "live_trading_enabled": False,
    }
