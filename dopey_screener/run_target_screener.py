"""Target screener runner: today's ranked targets per strategy archetype.

Combines point-in-time spine factors (momentum, RV compression) with today's
snapshot factors (fundamental rot, attention, short flow, quality, options
overlay) under the archetype weights in screen_config.py, ranks the governed
universe per archetype, and runs one elite-archive improvement cycle
(measure-only; recommendations are human-gated).

Outputs are RESEARCH FLAGS for a human: no orders, no paper entries, no
evidence-artifact writes. The forward walk keeps sole authority over entries.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_universe.universe_registry import active_universe

from .elite_archive import run_elite_archive_cycle
from .factor_engine import (
    load_adjusted_closes,
    point_in_time_factors,
    screenable_universe,
    snapshot_factors,
)
from .strategy_archetypes import build_archetypes

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENER_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "screener"
SCREENER_TARGETS_PATH = SCREENER_ARTIFACT_DIR / "screener_targets.jsonl"
SCREENER_SUMMARY_PATH = SCREENER_ARTIFACT_DIR / "screener_summary.json"

TOP_TARGETS_PER_ARCHETYPE = 5
# Live structure factor = pit compression blended with today's options overlay.
# The elite fitness only ever sees the pit component (see elite_archive).
STRUCTURE_PIT_WEIGHT = 0.6
STRUCTURE_OVERLAY_WEIGHT = 0.4


def _today_factor_rows() -> tuple[dict[str, dict[str, float]], dict]:
    # registry-aware: core floor plus staged probation names; quarantined and
    # retired names drop out here automatically
    symbols = screenable_universe(active_universe())
    snapshot, provenance = snapshot_factors(symbols)
    rows: dict[str, dict[str, float]] = {}
    spine_dates: list[str] = []
    for symbol in symbols:
        closes_rows = load_adjusted_closes(symbol)
        if not closes_rows:
            continue
        closes = [c for _, c in closes_rows]
        pit = point_in_time_factors(closes, len(closes) - 1)
        if pit is None:
            continue
        spine_dates.append(closes_rows[-1][0])
        snap = snapshot.get(symbol, {})
        structure = (
            STRUCTURE_PIT_WEIGHT * pit["structure"]
            + STRUCTURE_OVERLAY_WEIGHT * snap.get("structure_overlay", 0.0)
        )
        rows[symbol] = {
            "momentum": pit["momentum"],
            "structure": round(structure, 6),
            "value_rot": snap.get("value_rot", 0.0),
            "attention": snap.get("attention", 0.0),
            "flow": snap.get("flow", 0.0),
            "quality": snap.get("quality", 0.0),
        }
    provenance["spine_frontier"] = max(spine_dates) if spine_dates else ""
    provenance["symbols_scored"] = len(rows)
    return rows, provenance


def run_target_screener() -> dict:
    SCREENER_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    factor_rows, provenance = _today_factor_rows()
    archetypes = build_archetypes()
    generated_at = datetime.now(timezone.utc).isoformat()

    target_records: list[dict] = []
    top_by_archetype: dict[str, list[dict]] = {}
    for archetype in archetypes:
        scored: list[dict] = []
        for symbol, factors in factor_rows.items():
            contributions = {
                family: round(weight * factors.get(family, 0.0), 6)
                for family, weight in archetype.weights.items()
            }
            score = round(sum(contributions.values()), 6)
            scored.append({
                "artifact_type": "screener_target",
                "generated_at_utc": generated_at,
                "archetype_id": archetype.archetype_id,
                "executable_structure": archetype.executable_structure,
                "symbol": symbol,
                "screen_score": score,
                "factor_contributions": contributions,
                "factors": {k: round(v, 6) for k, v in factors.items()},
                "semantics": "research_flag_for_human_review_not_an_order_not_a_paper_entry",
                "paper_only": True,
                "live_blocked": True,
                "not_edge_evidence": True,
            })
        scored.sort(key=lambda row: (-row["screen_score"], row["symbol"]))
        for rank, row in enumerate(scored, start=1):
            row["rank"] = rank
        target_records.extend(scored)
        top_by_archetype[archetype.archetype_id] = [
            {
                "symbol": row["symbol"],
                "screen_score": row["screen_score"],
                "rank": row["rank"],
                "executable_structure": archetype.executable_structure,
            }
            for row in scored[:TOP_TARGETS_PER_ARCHETYPE]
            if row["screen_score"] > 0.0
        ]

    archive_record = run_elite_archive_cycle()

    with SCREENER_TARGETS_PATH.open("w", encoding="utf-8") as handle:
        for record in target_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "artifact_type": "screener_summary",
        "generated_at_utc": generated_at,
        "screener_status": "targets_ranked" if factor_rows else "no_spine_rows_available",
        "symbols_scored": provenance.get("symbols_scored", 0),
        "spine_frontier": provenance.get("spine_frontier", ""),
        "archetypes": [archetype.to_dict() for archetype in archetypes],
        "top_targets_by_archetype": top_by_archetype,
        "snapshot_provenance": provenance,
        "elite_archive": {
            "active_config_id": archive_record.get("active_config_id", ""),
            "active_mean_holdout_rank_ic": archive_record.get("active_mean_holdout_rank_ic", 0.0),
            "entry_count": len(archive_record.get("entries", [])),
            "recommendation_pending": archive_record.get("recommendation") is not None,
        },
        "honest_limits": [
            "screen scores are research ranking, not edge evidence",
            "snapshot factor families are today-only tilts (not backcastable); fitness never scores them",
            "entries remain owned by the daily post-close forward walk under its gates",
            "recommendations from the elite archive are human-applied, never automatic",
        ],
        "paper_only": True,
        "live_blocked": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
    SCREENER_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run_target_screener()
    print(json.dumps({
        "screener_status": result["screener_status"],
        "symbols_scored": result["symbols_scored"],
        "recommendation_pending": result["elite_archive"]["recommendation_pending"],
    }, indent=2))
