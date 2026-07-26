"""Elite archive: the screener's recursive-improvement loop, held-out-only.

Discipline (the part that keeps "recursively improving" from becoming the
V1-V7 disease wearing a new face):

* A weight set is scored ONLY on held-out eras (dates after TRAIN_END_DATE)
  using POINT-IN-TIME spine factors. Snapshot factor families (fundamentals /
  attention / flow / options overlay) cannot be back-cast without lookahead,
  so they are EXCLUDED from fitness and mutation - they ride the live screen
  as stamped research tilts until their accruing daily archives support true
  point-in-time evaluation.
* Direction-aware scoring: put archetypes are scored against NEGATIVE forward
  returns (a good put screen ranks the names that fall).
* Proposals mutate exactly one evaluable weight from a randomly chosen elite,
  seeded deterministically from the archive state (same inputs -> same
  proposals; no wall-clock, no unseeded RNG).
* The archive RECOMMENDS; a human commits screen_config.py. Nothing here
  writes the config, ever. The doofus external evolver gets the same fitness
  through operator_tools/operator_screen_fitness.py (measure-only contract).
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE

from .factor_engine import (
    FORWARD_RETURN_DAYS,
    load_adjusted_closes,
    point_in_time_factors,
    screenable_universe,
)
from .strategy_archetypes import build_archetypes

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENER_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "screener"
ELITE_ARCHIVE_PATH = SCREENER_ARTIFACT_DIR / "elite_archive.json"

TRAIN_END_DATE = "2021-12-31"      # same era boundary as the evolution fitness
HOLDOUT_DATE_STRIDE = 5            # evaluate every 5th trading day
MIN_HOLDOUT_DATES = 40
MIN_SYMBOLS_PER_DATE = 8
EVALUABLE_FAMILIES: tuple[str, ...] = ("momentum", "structure")
ELITE_CAPACITY = 8
RECOMMEND_MARGIN = 0.005           # mean-IC improvement required to recommend
PROPOSALS_PER_RUN = 4


def _config_id(weights_by_archetype: dict[str, dict[str, float]]) -> str:
    encoded = json.dumps(weights_by_archetype, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def current_weights() -> dict[str, dict[str, float]]:
    return {a.archetype_id: dict(a.weights) for a in build_archetypes()}


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Tie-averaged Spearman rank correlation (deterministic, dependency-free)."""
    n = len(xs)
    if n < 3:
        return 0.0

    def _ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx, ry = _ranks(xs), _ranks(ys)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / (var_x * var_y) ** 0.5


def _holdout_panel() -> dict[str, list[tuple[str, dict[str, float], float]]]:
    """Per symbol: [(date, pit_factors, forward_return)] on held-out dates.

    Deliberately pinned to the CORE floor (REQUIRED_HISTORY_UNIVERSE), not the
    registry-expanded active universe: fitness numbers must stay comparable
    across the trial ledger, and probation names entering/leaving would shift
    the evaluation panel under every previously-measured config."""
    panel: dict[str, list[tuple[str, dict[str, float], float]]] = {}
    for symbol in screenable_universe(REQUIRED_HISTORY_UNIVERSE):
        rows = load_adjusted_closes(symbol)
        dates = [d for d, _ in rows]
        closes = [c for _, c in rows]
        series: list[tuple[str, dict[str, float], float]] = []
        for index in range(0, len(rows) - FORWARD_RETURN_DAYS, HOLDOUT_DATE_STRIDE):
            date = dates[index]
            if date <= TRAIN_END_DATE:
                continue
            pit = point_in_time_factors(closes, index)
            if pit is None:
                continue
            base = closes[index]
            future = closes[index + FORWARD_RETURN_DAYS]
            if base <= 0:
                continue
            series.append((date, pit, future / base - 1.0))
        if series:
            panel[symbol] = series
    return panel


def evaluate_weight_set(
    weights_by_archetype: dict[str, dict[str, float]],
    panel: dict[str, list[tuple[str, dict[str, float], float]]] | None = None,
) -> dict:
    """Held-out mean rank-IC per archetype for the EVALUABLE families only."""
    panel = panel if panel is not None else _holdout_panel()
    by_date: dict[str, list[tuple[str, dict[str, float], float]]] = {}
    for symbol, series in panel.items():
        for date, pit, fwd in series:
            by_date.setdefault(date, []).append((symbol, pit, fwd))

    archetype_dir = {
        a.archetype_id: (-1.0 if a.executable_structure == "long_put" else 1.0)
        for a in build_archetypes()
    }
    per_archetype: dict[str, dict[str, float]] = {}
    for archetype_id, weights in weights_by_archetype.items():
        direction = archetype_dir.get(archetype_id, 1.0)
        ics: list[float] = []
        pair_count = 0
        for date in sorted(by_date):
            entries = by_date[date]
            if len(entries) < MIN_SYMBOLS_PER_DATE:
                continue
            scores = [
                sum(float(weights.get(f, 0.0)) * pit.get(f, 0.0) for f in EVALUABLE_FAMILIES)
                for _, pit, _ in entries
            ]
            forwards = [direction * fwd for _, _, fwd in entries]
            ics.append(_spearman(scores, forwards))
            pair_count += len(entries)
        mean_ic = sum(ics) / len(ics) if ics else 0.0
        per_archetype[archetype_id] = {
            "mean_holdout_rank_ic": round(mean_ic, 6),
            "holdout_dates": len(ics),
            "holdout_pairs": pair_count,
        }
    date_counts = [stats["holdout_dates"] for stats in per_archetype.values()]
    mean_over_archetypes = (
        sum(stats["mean_holdout_rank_ic"] for stats in per_archetype.values()) / len(per_archetype)
        if per_archetype else 0.0
    )
    return {
        "config_id": _config_id(weights_by_archetype),
        "weights_by_archetype": weights_by_archetype,
        "per_archetype": per_archetype,
        "mean_holdout_rank_ic": round(mean_over_archetypes, 6),
        "sample_sufficient": bool(date_counts and min(date_counts) >= MIN_HOLDOUT_DATES),
        "fitness_scope": "point_in_time_spine_factors_only",
        "excluded_from_fitness": ["value_rot", "attention", "flow", "quality", "structure_overlay"],
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }


def load_archive() -> dict:
    try:
        return json.loads(ELITE_ARCHIVE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"artifact_type": "screener_elite_archive", "entries": [], "active_config_id": "", "recommendation": None}


def _retain_elites(entries: list[dict], active_config_id: str) -> list[dict]:
    unique: dict[str, dict] = {}
    for entry in entries:
        unique[str(entry.get("config_id", ""))] = entry
    ranked = sorted(
        unique.values(),
        key=lambda e: (-float(e.get("mean_holdout_rank_ic", 0.0)), str(e.get("config_id", ""))),
    )
    kept = ranked[:ELITE_CAPACITY]
    if active_config_id and all(e.get("config_id") != active_config_id for e in kept):
        active_entry = unique.get(active_config_id)
        if active_entry:
            kept.append(active_entry)
    return kept


def propose_variants(archive: dict, count: int = PROPOSALS_PER_RUN) -> list[dict[str, dict[str, float]]]:
    """Deterministically seeded single-weight mutations of random elites,
    restricted to EVALUABLE families (mutating weights the fitness cannot see
    would be an unfalsifiable random walk)."""
    entries = archive.get("entries", [])
    if not entries:
        entries = [{"config_id": _config_id(current_weights()), "weights_by_archetype": current_weights()}]
    seed_material = json.dumps(
        [str(e.get("config_id", "")) for e in entries] + [str(archive.get("active_config_id", ""))],
        sort_keys=True,
    )
    rng = random.Random(hashlib.sha256(seed_material.encode("utf-8")).hexdigest())
    proposals: list[dict[str, dict[str, float]]] = []
    seen = {str(e.get("config_id", "")) for e in entries}
    attempts = 0
    while len(proposals) < count and attempts < count * 10:
        attempts += 1
        parent = rng.choice(entries)
        weights = {k: dict(v) for k, v in parent.get("weights_by_archetype", {}).items()}
        if not weights:
            continue
        archetype_id = rng.choice(sorted(weights))
        family = rng.choice(EVALUABLE_FAMILIES)
        base = float(weights[archetype_id].get(family, 0.0))
        step = rng.choice((-0.15, 0.15, -0.25 * abs(base) - 0.05, 0.25 * abs(base) + 0.05))
        weights[archetype_id][family] = round(max(-2.0, min(2.0, base + step)), 4)
        config_id = _config_id(weights)
        if config_id in seen:
            continue
        seen.add(config_id)
        proposals.append(weights)
    return proposals


def run_elite_archive_cycle() -> dict:
    """One measure-propose-measure cycle. Recommends; never applies."""
    SCREENER_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    panel = _holdout_panel()
    archive = load_archive()
    active = current_weights()
    active_eval = evaluate_weight_set(active, panel)
    entries = list(archive.get("entries", []))
    entries.append({**active_eval, "origin": "active_screen_config"})

    for weights in propose_variants({**archive, "entries": entries}):
        entries.append({**evaluate_weight_set(weights, panel), "origin": "seeded_elite_mutation"})

    kept = _retain_elites(entries, active_eval["config_id"])
    best = kept[0] if kept else active_eval
    recommendation = None
    improvement = float(best.get("mean_holdout_rank_ic", 0.0)) - float(active_eval["mean_holdout_rank_ic"])
    if (
        best.get("config_id") != active_eval["config_id"]
        and improvement >= RECOMMEND_MARGIN
        and best.get("sample_sufficient")
    ):
        recommendation = {
            "recommended_config_id": best["config_id"],
            "mean_holdout_rank_ic": best["mean_holdout_rank_ic"],
            "improvement_over_active": round(improvement, 6),
            "weights_by_archetype": best["weights_by_archetype"],
            "apply_instructions": "human edits dopey_screener/screen_config.py; nothing applies automatically",
        }

    record = {
        "artifact_type": "screener_elite_archive",
        "active_config_id": active_eval["config_id"],
        "active_mean_holdout_rank_ic": active_eval["mean_holdout_rank_ic"],
        "entries": kept,
        "recommendation": recommendation,
        "train_end_date": TRAIN_END_DATE,
        "evaluable_families": list(EVALUABLE_FAMILIES),
        "discipline": "held_out_only_measure_only_human_gated",
        "paper_only": True,
        "live_blocked": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
    ELITE_ARCHIVE_PATH.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
