"""Append-only phantom evidence for per-symbol targeting decisions."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean

from dopey.protocols.identity import canonical_hash

from .per_symbol_forecast_skill import iter_jsonl

SHADOW_LEDGER_VERSION = "dopey-shadow-targeting-ledger-v1"
JsonObject = dict[str, object]


def _append_jsonl_durable(
    path: Path,
    records: Sequence[Mapping[str, object]],
) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            )
        handle.flush()
        os.fsync(handle.fileno())


def _eligible_family_pairs(
    candidate_registry: Mapping[str, object],
) -> dict[tuple[str, str], JsonObject]:
    candidate_rows = candidate_registry.get("candidates")
    if not isinstance(candidate_rows, list):
        raise TypeError("candidate registry candidates must be a list")
    capacity_policy = candidate_registry.get("capacity_policy")
    if not isinstance(capacity_policy, dict):
        raise TypeError("candidate registry capacity_policy must be an object")
    maximum_candidates = capacity_policy.get("maximum_shadow_candidates")
    if (
        isinstance(maximum_candidates, bool)
        or not isinstance(maximum_candidates, int)
        or maximum_candidates <= 0
    ):
        raise ValueError(
            "candidate registry maximum_shadow_candidates must be positive"
        )
    pairs: dict[tuple[str, str], JsonObject] = {}
    selected_symbols: set[str] = set()
    for candidate in candidate_rows:
        if not isinstance(candidate, dict):
            continue
        if (
            candidate.get("candidate_status")
            != "targeting_shadow_eligible_for_forward_validation"
        ):
            continue
        symbol = candidate.get("symbol")
        family_scores = candidate.get("per_family_targeting_score")
        attention_weight = candidate.get("shadow_attention_weight")
        if (
            isinstance(attention_weight, bool)
            or not isinstance(attention_weight, (int, float))
            or not math.isfinite(float(attention_weight))
            or float(attention_weight) <= 0.0
        ):
            continue
        if not isinstance(symbol, str) or not isinstance(family_scores, dict):
            continue
        selected_symbols.add(symbol.upper())
        for family, score in family_scores.items():
            if (
                isinstance(family, str)
                and not isinstance(score, bool)
                and isinstance(score, (int, float))
                and math.isfinite(float(score))
                and float(score) > 0.0
            ):
                pairs[(symbol.upper(), family)] = {
                    "candidate_status": str(candidate["candidate_status"]),
                    "shadow_attention_weight": float(attention_weight),
                    "family_targeting_score": float(score),
                    "targeting_score": float(candidate.get("targeting_score", score)),
                }
    if len(selected_symbols) > maximum_candidates:
        raise ValueError(
            "candidate registry exceeds its shadow capacity: "
            f"selected_symbol_count={len(selected_symbols)}, "
            f"maximum_shadow_candidates={maximum_candidates}"
        )
    return pairs


def _horizon(detection: Mapping[str, object]) -> int:
    raw_horizons = detection.get("horizon_days")
    if not isinstance(raw_horizons, list):
        return 5
    horizons = [
        int(value)
        for value in raw_horizons
        if isinstance(value, int) and value > 0
    ]
    return min(horizons) if horizons else 5


def _signal_record(
    detection: Mapping[str, object],
    candidate_registry: Mapping[str, object],
    candidate_evidence: Mapping[str, object],
) -> JsonObject:
    direction = detection.get("direction")
    if direction not in {"long", "short"}:
        raise ValueError(
            "targeting shadow signal requires long or short research direction: "
            f"detection_id={detection.get('detection_id')}, direction={direction}"
        )
    body: JsonObject = {
        "artifact_type": "targeting_shadow_signal",
        "shadow_ledger_version": SHADOW_LEDGER_VERSION,
        "source_detection_id": str(detection["detection_id"]),
        "source_candidate_registry_hash": str(
            candidate_registry["reproducibility_hash"]
        ),
        "source_candidate_registry_version": str(
            candidate_registry.get("candidate_registry_version", "")
        ),
        "source_candidate_status": str(candidate_evidence["candidate_status"]),
        "source_shadow_attention_weight": float(
            candidate_evidence["shadow_attention_weight"]
        ),
        "source_family_targeting_score": float(
            candidate_evidence["family_targeting_score"]
        ),
        "source_targeting_score": float(candidate_evidence["targeting_score"]),
        "symbol": str(detection["symbol"]).upper(),
        "family": str(detection["family"]),
        "setup_id": str(detection.get("setup_id", "")),
        "as_of_date": str(detection["as_of_date"]),
        "direction": direction,
        "horizon_days": _horizon(detection),
        "source_strength": detection.get("strength"),
        "phantom_position": True,
        "not_realized_trade_pnl": True,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
    }
    immutable_identity = {
        "shadow_ledger_version": SHADOW_LEDGER_VERSION,
        "source_detection_id": body["source_detection_id"],
    }
    body["signal_id"] = (
        f"targeting-shadow:{canonical_hash(immutable_identity)[:24]}"
    )
    return body


def _required_capacity(
    candidate_registry: Mapping[str, object],
    key: str,
) -> int:
    capacity_policy = candidate_registry.get("capacity_policy")
    if not isinstance(capacity_policy, dict):
        raise TypeError("candidate registry capacity_policy must be an object")
    raw_value = capacity_policy.get(key)
    if (
        isinstance(raw_value, bool)
        or not isinstance(raw_value, int)
        or raw_value <= 0
    ):
        raise ValueError(f"candidate registry capacity must be positive: key={key}")
    return raw_value


def _source_strength(signal: Mapping[str, object]) -> float:
    value = signal.get("source_strength")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    return number if math.isfinite(number) else 0.0


def _apply_signal_capacity(
    signals: Sequence[JsonObject],
    maximum_candidates: int,
    maximum_per_direction: int,
) -> list[JsonObject]:
    ordered = sorted(
        signals,
        key=lambda row: (
            -float(row["source_shadow_attention_weight"]),
            -float(row["source_family_targeting_score"]),
            -_source_strength(row),
            str(row["symbol"]),
            str(row["family"]),
            str(row["source_detection_id"]),
        ),
    )
    selected: list[JsonObject] = []
    selected_symbols: set[str] = set()
    direction_counts: Counter[str] = Counter()
    for row in ordered:
        symbol = str(row["symbol"])
        direction = str(row["direction"])
        if symbol in selected_symbols:
            continue
        if len(selected) >= maximum_candidates:
            continue
        if direction_counts[direction] >= maximum_per_direction:
            continue
        selected.append(row)
        selected_symbols.add(symbol)
        direction_counts[direction] += 1
    return selected


def append_current_shadow_signals(
    detections: Sequence[Mapping[str, object]],
    settled_detection_ids: set[str],
    candidate_registry: Mapping[str, object],
    signal_ledger_path: Path,
) -> JsonObject:
    """Append only latest unresolved detections selected by verified skill."""

    existing_source_detection_ids = {
        str(row.get("source_detection_id", ""))
        for row in iter_jsonl(signal_ledger_path)
        if isinstance(row.get("source_detection_id"), str)
    }
    eligible_pairs = _eligible_family_pairs(candidate_registry)
    maximum_candidates = _required_capacity(
        candidate_registry,
        "maximum_shadow_candidates",
    )
    maximum_per_direction = _required_capacity(
        candidate_registry,
        "maximum_shadow_candidates_per_direction",
    )
    unresolved = [
        detection
        for detection in detections
        if str(detection.get("detection_id", "")) not in settled_detection_ids
        and isinstance(detection.get("as_of_date"), str)
    ]
    latest_date = max(
        (str(row["as_of_date"]) for row in unresolved),
        default=None,
    )
    candidates_by_detection_id: dict[str, JsonObject] = {}
    for detection in unresolved:
        pair = (
            str(detection.get("symbol", "")).upper(),
            str(detection.get("family", "")),
        )
        if pair not in eligible_pairs:
            continue
        if str(detection["as_of_date"]) != latest_date:
            continue
        source_detection_id = str(detection.get("detection_id", ""))
        if not source_detection_id:
            raise ValueError("eligible targeting detection lacks detection_id")
        proposed = _signal_record(
            detection,
            candidate_registry,
            eligible_pairs[pair],
        )
        prior = candidates_by_detection_id.get(source_detection_id)
        if prior is not None and canonical_hash(prior) != canonical_hash(proposed):
            raise ValueError(
                "conflicting targeting detections share a detection_id: "
                f"source_detection_id={source_detection_id}"
            )
        candidates_by_detection_id[source_detection_id] = proposed
    pre_capacity_signals = list(candidates_by_detection_id.values())
    candidate_signals = _apply_signal_capacity(
        pre_capacity_signals,
        maximum_candidates,
        maximum_per_direction,
    )
    fresh = [
        row
        for row in candidate_signals
        if str(row["source_detection_id"]) not in existing_source_detection_ids
    ]
    _append_jsonl_durable(signal_ledger_path, fresh)
    return {
        "artifact_type": "targeting_shadow_signal_recording",
        "latest_unresolved_detection_date": latest_date,
        "eligible_symbol_family_count": len(eligible_pairs),
        "candidate_signal_count": len(candidate_signals),
        "pre_capacity_candidate_signal_count": len(pre_capacity_signals),
        "capacity_dropped_count": (
            len(pre_capacity_signals) - len(candidate_signals)
        ),
        "selected_symbol_count": len(
            {str(row["symbol"]) for row in candidate_signals}
        ),
        "appended_signal_count": len(fresh),
        "already_recorded_count": len(candidate_signals) - len(fresh),
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _settle_signal(
    signal: Mapping[str, object],
    bars: Sequence[Mapping[str, object]],
) -> JsonObject | None:
    as_of_date = str(signal["as_of_date"])
    entry_index = next(
        (
            index
            for index, bar in enumerate(bars)
            if str(bar.get("date", "")) > as_of_date
        ),
        None,
    )
    if entry_index is None:
        return None
    horizon_days = int(signal["horizon_days"])
    exit_index = entry_index + horizon_days
    if exit_index >= len(bars):
        return None
    entry_close = float(bars[entry_index]["close"])
    exit_close = float(bars[exit_index]["close"])
    if entry_close <= 0.0 or exit_close <= 0.0:
        raise ValueError(
            "shadow targeting settlement requires positive closes: "
            f"signal_id={signal['signal_id']}, entry={entry_close}, exit={exit_close}"
        )
    raw_return = exit_close / entry_close - 1.0
    direction = str(signal["direction"])
    directional_return = raw_return if direction == "long" else -raw_return
    path_returns = [
        float(bar["close"]) / entry_close - 1.0
        for bar in bars[entry_index : exit_index + 1]
    ]
    directional_path = (
        path_returns if direction == "long" else [-value for value in path_returns]
    )
    body: JsonObject = {
        "artifact_type": "targeting_shadow_settlement",
        "shadow_ledger_version": SHADOW_LEDGER_VERSION,
        "signal_id": str(signal["signal_id"]),
        "source_detection_id": str(signal["source_detection_id"]),
        "source_candidate_registry_hash": str(
            signal["source_candidate_registry_hash"]
        ),
        "symbol": str(signal["symbol"]),
        "family": str(signal["family"]),
        "direction": direction,
        "entry_date": str(bars[entry_index]["date"]),
        "settle_date": str(bars[exit_index]["date"]),
        "horizon_days": horizon_days,
        "entry_close": entry_close,
        "exit_close": exit_close,
        "raw_underlying_return": round(raw_return, 8),
        "directional_return": round(directional_return, 8),
        "maximum_favorable_excursion": round(max(directional_path), 8),
        "maximum_adverse_excursion": round(min(directional_path), 8),
        "hit": directional_return > 0.0,
        "phantom_position": True,
        "not_realized_trade_pnl": True,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    body["settlement_id"] = (
        f"targeting-shadow-settlement:{canonical_hash(body)[:24]}"
    )
    return body


def settle_shadow_signals(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    signal_ledger_path: Path,
    settlement_ledger_path: Path,
) -> JsonObject:
    """Settle each phantom signal once against next-session close marks."""

    signals = list(iter_jsonl(signal_ledger_path))
    existing = list(iter_jsonl(settlement_ledger_path))
    settled_signal_ids = {str(row.get("signal_id", "")) for row in existing}
    fresh: list[JsonObject] = []
    pending = 0
    for signal in signals:
        if str(signal.get("signal_id", "")) in settled_signal_ids:
            continue
        symbol = str(signal.get("symbol", ""))
        bars = bars_by_symbol.get(symbol)
        if bars is None:
            pending += 1
            continue
        settlement = _settle_signal(signal, bars)
        if settlement is None:
            pending += 1
            continue
        fresh.append(settlement)
    _append_jsonl_durable(settlement_ledger_path, fresh)
    return {
        "artifact_type": "targeting_shadow_settlement_run",
        "new_settlement_count": len(fresh),
        "total_settlement_count": len(existing) + len(fresh),
        "pending_signal_count": pending,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def build_shadow_evidence_report(
    settlement_ledger_path: Path,
    minimum_effective_samples: int,
) -> JsonObject:
    """Summarize phantom outcomes without converting them into promotion."""

    settlements = list(iter_jsonl(settlement_ledger_path))
    grouped: dict[tuple[str, str], list[JsonObject]] = {}
    for row in settlements:
        grouped.setdefault(
            (str(row.get("symbol", "")), str(row.get("family", ""))),
            [],
        ).append(row)
    per_symbol_family: dict[str, JsonObject] = {}
    overlap_review_required = 0
    for (symbol, family), rows in sorted(grouped.items()):
        directional_returns = [float(row["directional_return"]) for row in rows]
        hit_rate = sum(1 for row in rows if row.get("hit") is True) / len(rows)
        mean_return = fmean(directional_returns)
        enough = len(rows) >= minimum_effective_samples
        raw_positive = enough and hit_rate >= 0.52 and mean_return > 0.0
        if raw_positive:
            overlap_review_required += 1
        per_symbol_family[f"{symbol}:{family}"] = {
            "symbol": symbol,
            "family": family,
            "settled_observations": len(rows),
            "directional_hit_rate": round(hit_rate, 6),
            "mean_directional_return": round(mean_return, 8),
            "research_review_state": (
                "requires_overlap_and_null_corrected_skill_verification"
                if raw_positive
                else "unrated_or_not_positive"
            ),
            "automatic_promotion_allowed": False,
        }
    report: JsonObject = {
        "artifact_type": "targeting_shadow_evidence_report",
        "shadow_ledger_version": SHADOW_LEDGER_VERSION,
        "settlement_count": len(settlements),
        "symbol_family_count": len(grouped),
        "human_research_review_eligible_count": 0,
        "raw_positive_buckets_requiring_overlap_review": overlap_review_required,
        "per_symbol_family": per_symbol_family,
        "effective_sample_warning": (
            "daily signals can overlap; eligibility remains human-review-only "
            "until the forecast-skill overlap/null discipline is re-applied"
        ),
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    report["reproducibility_hash"] = canonical_hash(report)
    return report
