"""Lane-context loader: feed macro/flow lane artifacts to the playbook scanner.

Maps the governed lane artifacts (macro context summary + chain positioning
ledger) into the typed lane states the scanner's lane-dependent detectors
expect. Everything is best-effort and honest: a missing or stale artifact
becomes a typed gap in the returned report — never a fabricated state.

States produced (when their lane artifact supports them):
- ``vix_term_structure_state``  <- vol_term_structure.term_structure_state
- ``liquidity_state``           <- liquidity_impulse.impulse_state
- ``cot_state``                 <- es_positioning.noncomm_net_z_52w extremes
- ``attention_state``           <- attention.crowded_attention_candidates
- ``short_interest_state``      <- actual open short interest + days-to-cover
- ``congress_state``            <- congress.notable_buying clusters
- ``fundamental_rot_state``     <- fundamentals.short_candidates
- ``gex_state``                 <- chain positioning total_gex_dollar_per_pct
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
DEFAULT_POSITIONING_PATH = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics" / "real_chain_positioning_metrics.jsonl"

COT_Z_EXTREME = 2.0
GEX_NEGATIVE_FLOOR = 0.0


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _read_jsonl_last_by_symbol(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return latest
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        symbol = str(record.get("symbol", "")).strip().upper()
        if symbol:
            latest[symbol] = record  # later lines win: last snapshot per symbol
    return latest


def load_lane_context(
    *,
    macro_summary_path: Path | None = None,
    positioning_path: Path | None = None,
) -> dict[str, Any]:
    """Build scanner lane states from governed lane artifacts.

    Returns ``{"states": {...}, "gaps": [...], ...}``; pass ``states`` as the
    scanner's ``lane_context``. Every unavailable lane is a named gap.
    """
    states: dict[str, Any] = {}
    gaps: list[str] = []

    macro = _read_json(macro_summary_path or DEFAULT_MACRO_SUMMARY_PATH)
    if macro is None:
        gaps.extend([
            "vix_term_structure_state", "liquidity_state", "cot_state",
            "attention_state", "short_interest_state", "congress_state",
            "fundamental_rot_state",
        ])
    else:
        vol = macro.get("vol_term_structure")
        if isinstance(vol, dict) and vol.get("term_structure_state"):
            state = str(vol["term_structure_state"])
            backwardation = "backwardation" in state
            states["vix_term_structure_state"] = {
                "detected": backwardation,  # the transition state is the signal
                "direction": "either",
                "strength": 0.7 if backwardation else 0.0,
                "term_structure_state": state,
                "term_slope_9d_3m": vol.get("term_slope_9d_3m"),
                "skew_percentile_252d": vol.get("skew_percentile_252d"),
            }
        else:
            gaps.append("vix_term_structure_state")

        liquidity = macro.get("liquidity_impulse")
        if isinstance(liquidity, dict) and liquidity.get("impulse_state"):
            impulse = str(liquidity["impulse_state"])
            states["liquidity_state"] = {
                "detected": impulse in ("flooding", "draining"),
                "direction": "long" if impulse == "flooding" else "short" if impulse == "draining" else "either",
                "strength": 0.6,
                "impulse_state": impulse,
                "impulse_4w_pct": liquidity.get("impulse_4w_pct"),
            }
        else:
            gaps.append("liquidity_state")

        cot = macro.get("es_positioning")
        if isinstance(cot, dict) and cot.get("noncomm_net_z_52w") is not None:
            try:
                z = float(cot["noncomm_net_z_52w"])
            except (TypeError, ValueError):
                z = 0.0
            states["cot_state"] = {
                "detected": abs(z) >= COT_Z_EXTREME,
                # fade the speculative extreme (documented framing)
                "direction": "long" if z <= -COT_Z_EXTREME else "short" if z >= COT_Z_EXTREME else "either",
                "strength": min(abs(z) / 4.0, 1.0),
                "noncomm_net_z_52w": z,
            }
        else:
            gaps.append("cot_state")

        attention = macro.get("attention")
        if isinstance(attention, dict) and isinstance(attention.get("crowded_attention_candidates"), list):
            crowded = sorted(
                {
                    str(symbol).strip().upper()
                    for symbol in attention["crowded_attention_candidates"]
                    if str(symbol).strip()
                }
            )
            raw_z_by_symbol = attention.get("attention_z_by_symbol")
            z_by_symbol = (
                {
                    str(symbol).strip().upper(): float(value)
                    for symbol, value in raw_z_by_symbol.items()
                    if str(symbol).strip()
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                }
                if isinstance(raw_z_by_symbol, dict)
                else {}
            )
            raw_threshold = attention.get("crowded_threshold_z")
            threshold = (
                float(raw_threshold)
                if isinstance(raw_threshold, (int, float))
                and not isinstance(raw_threshold, bool)
                and math.isfinite(float(raw_threshold))
                else COT_Z_EXTREME
            )
            states["attention_state"] = {
                "detected": bool(crowded),
                "direction": "either",
                "strength": 0.0,
                "crowded_symbols": crowded,
                "attention_z_by_symbol": z_by_symbol,
                "crowded_threshold_z": threshold,
                "research_priority_only": True,
                "directional_bias_allowed": False,
                "directional_confirmation_policy": (
                    "attention_z_plus_independent_price_extension_and_trend_regime"
                ),
            }
        else:
            gaps.append("attention_state")

        short_crowding = macro.get("short_crowding")
        observations = (
            short_crowding.get("by_symbol")
            if isinstance(short_crowding, dict)
            else None
        )
        if isinstance(observations, dict) and observations:
            crowded: dict[str, float] = {}
            for raw_symbol, raw_observation in observations.items():
                if not isinstance(raw_observation, dict):
                    continue
                raw_short_percent = raw_observation.get("short_percent_float")
                raw_days_to_cover = raw_observation.get("days_to_cover")
                if (
                    isinstance(raw_short_percent, (int, float))
                    and not isinstance(raw_short_percent, bool)
                    and isinstance(raw_days_to_cover, (int, float))
                    and not isinstance(raw_days_to_cover, bool)
                    and math.isfinite(float(raw_short_percent))
                    and math.isfinite(float(raw_days_to_cover))
                    and float(raw_short_percent) >= 0.10
                    and float(raw_days_to_cover) >= 3.0
                ):
                    crowded[str(raw_symbol).strip().upper()] = min(
                        1.0,
                        0.65 * min(float(raw_short_percent) / 0.35, 1.0)
                        + 0.35 * min(float(raw_days_to_cover) / 10.0, 1.0),
                    )
            states["short_interest_state"] = {
                "detected": bool(crowded),
                "direction": "either",
                "strength": max(crowded.values(), default=0.0),
                "crowded_short_symbols": sorted(crowded),
                "crowding_strength_by_symbol": dict(sorted(crowded.items())),
                "actual_open_short_interest_present": True,
                "daily_short_volume_substituted": False,
                "directional_bias_allowed": False,
                "direction_requires_independent_price_confirmation": True,
            }
        else:
            gaps.append("short_interest_state")

        congress = macro.get("congress")
        if isinstance(congress, dict) and isinstance(congress.get("notable_buying"), list):
            notable = [str(s) for s in congress["notable_buying"]]
            states["congress_state"] = {
                "detected": bool(notable),
                "direction": "long",
                "strength": min(0.2 + 0.1 * len(notable), 0.8),
                "notable_buying": notable,
                "honest_limits": congress.get("honest_limits"),
            }
        else:
            gaps.append("congress_state")

        fundamentals = macro.get("fundamentals")
        candidates = fundamentals.get("short_candidates_tradable_now") if isinstance(fundamentals, dict) else None
        if isinstance(candidates, list):
            names = [str(s) for s in candidates]
            states["fundamental_rot_state"] = {
                "detected": bool(names),
                "direction": "short",
                "strength": min(0.3 + 0.1 * len(names), 1.0),
                "short_candidates": names,
            }
        else:
            gaps.append("fundamental_rot_state")

    positioning = _read_jsonl_last_by_symbol(positioning_path or DEFAULT_POSITIONING_PATH)
    if positioning:
        negative_gex = {
            sym: rec.get("total_gex_dollar_per_pct")
            for sym, rec in positioning.items()
            if isinstance(rec.get("total_gex_dollar_per_pct"), (int, float))
            and float(rec["total_gex_dollar_per_pct"]) < GEX_NEGATIVE_FLOOR
        }
        states["gex_state"] = {
            "detected": bool(negative_gex),
            "direction": "either",
            "strength": min(0.3 + 0.05 * len(negative_gex), 1.0),
            "negative_gex_symbols": sorted(negative_gex),
            "directional_bias_allowed": False,
            "direction_requires_independent_price_confirmation": True,
        }
    else:
        gaps.append("gex_state")

    return {
        "artifact_type": "playbook_lane_context",
        "lane_context_version": "dopey-playbook-lane-context-v2",
        "states": states,
        "gaps": sorted(gaps),
        "loaded_state_count": len(states),
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
