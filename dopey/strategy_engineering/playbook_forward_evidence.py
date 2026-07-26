"""Append-only forward evidence for composite Playbook research rankings."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean
from typing import Final, Literal, cast

from dopey.protocols.identity import canonical_hash
from dopey_acceleration.common import write_json_atomic


FORWARD_EVIDENCE_VERSION: Final[str] = "dopey-playbook-forward-evidence-v3"
SHORT_TERM_EVALUATION_HORIZON: Final[int] = 5
LONG_TERM_EVALUATION_HORIZON: Final[int] = 20
MINIMUM_RANK_IC_COHORT_SIZE: Final[int] = 10
MINIMUM_RANK_IC_COHORTS: Final[int] = 5
MINIMUM_SETTLED_RECOMMENDATIONS: Final[int] = 100
SNAPSHOT_EVIDENCE_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "market_data_as_of",
    "symbol",
    "category",
    "evaluation_horizon_trading_days",
)

HorizonBucket = Literal["short_term", "long_term"]
DirectionalBias = Literal["bullish", "bearish"]
SnapshotEvidenceIdentity = tuple[str, str, str, int]


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(
            f"playbook forward evidence field must be a nonempty string: field={field}, value={value!r}"
        )
    return value.strip()


def _required_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"playbook forward evidence field must be numeric: field={field}, value={value!r}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            f"playbook forward evidence field must be finite: field={field}, value={value!r}"
        )
    return number


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise OSError(
            f"playbook forward ledger cannot be read: path={path}, error={error}"
        ) from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                "playbook forward ledger contains invalid JSON: "
                f"path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise TypeError(
                f"playbook forward ledger row must be an object: path={path}, line={line_number}"
            )
        records.append(cast(dict[str, object], value))
    return records


def _append_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(
                    json.dumps(
                        dict(record),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise OSError(
            f"playbook forward ledger append failed: path={path}, error={error}"
        ) from error


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise OSError(
            f"playbook forward ledger cannot be hashed: path={path}, error={error}"
        ) from error
    return digest.hexdigest()


def _evaluation_horizon(horizon: HorizonBucket) -> int:
    if horizon == "short_term":
        return SHORT_TERM_EVALUATION_HORIZON
    return LONG_TERM_EVALUATION_HORIZON


def _source_hashes(rankings: Mapping[str, object]) -> list[str]:
    raw_sources = rankings.get("source_artifacts")
    if not isinstance(raw_sources, list):
        raise TypeError("playbook source_artifacts must be a list")
    source_hashes: list[str] = []
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, Mapping):
            raise TypeError(
                f"playbook source artifact must be an object: index={index}"
            )
        source_hashes.append(
            _required_string(
                raw_source.get("sha256"), f"source_artifacts[{index}].sha256"
            )
        )
    return sorted(source_hashes)


def _weight_spec(
    rankings: Mapping[str, object], horizon: HorizonBucket
) -> dict[str, object]:
    raw_method = rankings.get("ranking_method")
    if not isinstance(raw_method, Mapping):
        raise TypeError("playbook ranking_method must be an object")
    weight_key = f"{horizon}_weights"
    raw_weights = raw_method.get(weight_key)
    if not isinstance(raw_weights, Mapping):
        raise TypeError(f"playbook ranking_method.{weight_key} must be an object")
    return {
        "schema_version": _required_string(
            rankings.get("schema_version"), "schema_version"
        ),
        "horizon": horizon,
        "weights": dict(raw_weights),
        "forward_trust_method": raw_method.get("forward_trust_method"),
        "valuation_use": raw_method.get("valuation_use"),
        "weight_calibration_status": raw_method.get("weight_calibration_status"),
        "automatic_weight_tuning_allowed": raw_method.get(
            "automatic_weight_tuning_allowed"
        ),
    }


def build_recommendation_snapshots(
    rankings: Mapping[str, object],
) -> list[dict[str, object]]:
    """Build deterministic, idempotent records for one published ranking batch."""

    raw_recommendations = rankings.get("recommendations")
    if not isinstance(raw_recommendations, Mapping):
        raise TypeError("playbook recommendations must be an object")
    generated_utc = _required_string(rankings.get("generated_utc"), "generated_utc")
    market_data_as_of = _required_string(
        rankings.get("market_data_as_of"), "market_data_as_of"
    )
    input_fingerprint = _required_string(
        rankings.get("input_fingerprint"), "input_fingerprint"
    )
    playbook_content_hash = _required_string(
        rankings.get("content_hash"), "content_hash"
    )
    source_hashes = _source_hashes(rankings)

    records: list[dict[str, object]] = []
    for recommendation_id in sorted(raw_recommendations):
        raw_recommendation = raw_recommendations[recommendation_id]
        if not isinstance(recommendation_id, str) or not isinstance(
            raw_recommendation, Mapping
        ):
            raise TypeError(
                "playbook recommendations must map string identifiers to objects"
            )
        recommendation = dict(raw_recommendation)
        if recommendation.get("recommendation_id") != recommendation_id:
            raise ValueError(
                "playbook recommendation key does not match its record: "
                f"key={recommendation_id!r}, record={recommendation.get('recommendation_id')!r}"
            )
        raw_horizon = _required_string(
            recommendation.get("horizon"),
            f"recommendations[{recommendation_id}].horizon",
        )
        if raw_horizon not in {"short_term", "long_term"}:
            raise ValueError(
                f"unsupported Playbook horizon for forward evidence: horizon={raw_horizon!r}"
            )
        horizon = cast(HorizonBucket, raw_horizon)
        raw_bias = _required_string(
            recommendation.get("directional_bias"),
            f"recommendations[{recommendation_id}].directional_bias",
        )
        if raw_bias not in {"bullish", "bearish"}:
            raise ValueError(
                f"unsupported Playbook direction for forward evidence: direction={raw_bias!r}"
            )
        bias = cast(DirectionalBias, raw_bias)
        raw_breakdown = recommendation.get("score_breakdown")
        if not isinstance(raw_breakdown, Mapping):
            raise TypeError(
                f"recommendation score_breakdown must be an object: id={recommendation_id}"
            )
        feature_vector = {
            str(name): _required_number(
                value, f"recommendations[{recommendation_id}].score_breakdown.{name}"
            )
            for name, value in sorted(raw_breakdown.items())
        }
        weight_spec = _weight_spec(rankings, horizon)
        weight_spec_hash = canonical_hash(weight_spec)
        evaluation_horizon = _evaluation_horizon(horizon)
        symbol = _required_string(
            recommendation.get("symbol"),
            f"recommendations[{recommendation_id}].symbol",
        )
        category = _required_string(
            recommendation.get("category"),
            f"recommendations[{recommendation_id}].category",
        )
        batch_id = (
            "playbook-forward-batch:"
            + canonical_hash(
                {
                    "market_data_as_of": market_data_as_of,
                    "horizon": horizon,
                    "evaluation_horizon_trading_days": evaluation_horizon,
                    "weight_spec_hash": weight_spec_hash,
                }
            )[:24]
        )
        stable_payload: dict[str, object] = {
            "recommendation_id": recommendation_id,
            "batch_id": batch_id,
            "market_data_as_of": market_data_as_of,
            "symbol": symbol,
            "category": category,
            "horizon": horizon,
            "directional_bias": bias,
            "evaluation_horizon_trading_days": evaluation_horizon,
            "research_priority_score": _required_number(
                recommendation.get("research_priority_score"),
                f"recommendations[{recommendation_id}].research_priority_score",
            ),
            "feature_vector": feature_vector,
            "weight_spec": weight_spec,
            "weight_spec_hash": weight_spec_hash,
            "input_fingerprint": input_fingerprint,
            "source_hashes": source_hashes,
            "recommendation_state": recommendation.get("recommendation_state"),
            "valuation_gate": (
                recommendation.get("valuation_context", {}).get("valuation_gate")
                if isinstance(recommendation.get("valuation_context"), Mapping)
                else None
            ),
        }
        payload_hash = canonical_hash(stable_payload)
        snapshot_id = (
            "playbook-forward-snapshot:"
            + canonical_hash(
                {
                    "market_data_as_of": market_data_as_of,
                    "symbol": symbol,
                    "category": category,
                    "evaluation_horizon_trading_days": evaluation_horizon,
                }
            )[:24]
        )
        records.append(
            {
                "artifact_type": "playbook_composite_recommendation_snapshot",
                "forward_evidence_version": FORWARD_EVIDENCE_VERSION,
                "snapshot_id": snapshot_id,
                "snapshot_payload_hash": payload_hash,
                "first_recorded_utc": generated_utc,
                "source_playbook_content_hash": playbook_content_hash,
                **stable_payload,
                "rank_score_is_not_probability": True,
                "order_construction_allowed": False,
                "strategy_promotion_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return records


def _snapshot_evidence_identity(
    snapshot: Mapping[str, object],
) -> SnapshotEvidenceIdentity:
    raw_horizon = snapshot.get("evaluation_horizon_trading_days")
    if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int):
        raise TypeError(
            "Playbook snapshot evaluation horizon must be an integer: "
            f"snapshot_id={snapshot.get('snapshot_id')!r}, value={raw_horizon!r}"
        )
    return (
        _required_string(snapshot.get("market_data_as_of"), "market_data_as_of"),
        _required_string(snapshot.get("symbol"), "symbol"),
        _required_string(snapshot.get("category"), "category"),
        raw_horizon,
    )


def _append_new_snapshots(
    snapshot_ledger_path: Path,
    proposed: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int, int, int]:
    existing = _read_jsonl(snapshot_ledger_path)
    effective: list[dict[str, object]] = []
    evidence_identities: set[SnapshotEvidenceIdentity] = set()
    identity_by_snapshot_id: dict[str, SnapshotEvidenceIdentity] = {}
    duplicate_count = 0
    for record in existing:
        snapshot_id = _required_string(record.get("snapshot_id"), "snapshot_id")
        identity = _snapshot_evidence_identity(record)
        prior_identity = identity_by_snapshot_id.get(snapshot_id)
        if prior_identity is not None and prior_identity != identity:
            raise ValueError(
                "immutable Playbook snapshot id maps to conflicting evidence identities: "
                f"snapshot_id={snapshot_id}"
            )
        identity_by_snapshot_id[snapshot_id] = identity
        if identity in evidence_identities:
            duplicate_count += 1
            continue
        evidence_identities.add(identity)
        effective.append(record)

    fresh: list[dict[str, object]] = []
    for raw_record in proposed:
        record = dict(raw_record)
        snapshot_id = _required_string(record.get("snapshot_id"), "snapshot_id")
        identity = _snapshot_evidence_identity(record)
        prior_identity = identity_by_snapshot_id.get(snapshot_id)
        if prior_identity is not None and prior_identity != identity:
            raise ValueError(
                "immutable Playbook snapshot id maps to conflicting evidence identities: "
                f"snapshot_id={snapshot_id}"
            )
        if identity in evidence_identities:
            continue
        identity_by_snapshot_id[snapshot_id] = identity
        evidence_identities.add(identity)
        effective.append(record)
        fresh.append(record)
    _append_jsonl(snapshot_ledger_path, fresh)
    raw_snapshot_count = len(existing) + len(fresh)
    return effective, len(fresh), raw_snapshot_count, duplicate_count


def _load_adjusted_history(
    history_root: Path, symbol: str
) -> tuple[list[str], list[float]] | None:
    path = history_root / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise OSError(
            f"Playbook settlement history cannot be read: symbol={symbol}, path={path}, error={error}"
        ) from error
    observations: list[tuple[str, float]] = []
    for row_number, row in enumerate(rows, start=2):
        raw_date = row.get("date")
        raw_price = row.get("adjusted_close")
        if not raw_date or raw_price is None:
            raise ValueError(
                "Playbook settlement history row is missing date or adjusted_close: "
                f"symbol={symbol}, path={path}, row={row_number}"
            )
        try:
            price = float(raw_price)
        except ValueError as error:
            raise ValueError(
                "Playbook settlement adjusted close must be numeric: "
                f"symbol={symbol}, path={path}, row={row_number}, value={raw_price!r}"
            ) from error
        if not math.isfinite(price):
            raise ValueError(
                "Playbook settlement adjusted close must be finite: "
                f"symbol={symbol}, path={path}, row={row_number}, value={raw_price!r}"
            )
        if price <= 0.0:
            raise ValueError(
                "Playbook settlement adjusted close must be positive: "
                f"symbol={symbol}, path={path}, row={row_number}, price={price}"
            )
        observations.append((raw_date, price))
    observations.sort(key=lambda item: item[0])
    dates = [item[0] for item in observations]
    if len(dates) != len(set(dates)):
        raise ValueError(
            f"Playbook settlement history contains duplicate dates: symbol={symbol}, path={path}"
        )
    return dates, [item[1] for item in observations]


def _settlement_record(
    snapshot: Mapping[str, object],
    history: tuple[list[str], list[float]] | None,
    history_manifest_hash: str,
) -> tuple[dict[str, object] | None, str]:
    if history is None:
        return None, "pending_missing_symbol_history"
    dates, prices = history
    market_data_as_of = _required_string(
        snapshot.get("market_data_as_of"), "market_data_as_of"
    )
    if market_data_as_of not in dates:
        return None, "pending_missing_entry_date"
    entry_index = dates.index(market_data_as_of)
    raw_horizon = snapshot.get("evaluation_horizon_trading_days")
    if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int):
        raise TypeError(
            "Playbook evaluation horizon must be an integer: "
            f"snapshot_id={snapshot.get('snapshot_id')!r}, value={raw_horizon!r}"
        )
    exit_index = entry_index + raw_horizon
    if exit_index >= len(dates):
        return None, "pending_minimum_horizon"
    direction = _required_string(snapshot.get("directional_bias"), "directional_bias")
    entry_price = prices[entry_index]
    exit_price = prices[exit_index]
    forward_return = exit_price / entry_price - 1.0
    signed_forward_return = (
        forward_return if direction == "bullish" else -forward_return
    )
    stable_payload: dict[str, object] = {
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_payload_hash": snapshot["snapshot_payload_hash"],
        "batch_id": snapshot["batch_id"],
        "symbol": snapshot["symbol"],
        "category": snapshot["category"],
        "horizon": snapshot["horizon"],
        "directional_bias": direction,
        "evaluation_horizon_trading_days": raw_horizon,
        "research_priority_score": snapshot["research_priority_score"],
        "weight_spec_hash": snapshot["weight_spec_hash"],
        "entry_market_date": market_data_as_of,
        "exit_market_date": dates[exit_index],
        "price_field": "adjusted_close",
        "entry_price": round(entry_price, 8),
        "exit_price": round(exit_price, 8),
        "forward_return": round(forward_return, 10),
        "signed_forward_return": round(signed_forward_return, 10),
        "directionally_correct": signed_forward_return > 0.0,
        "settlement_history_manifest_hash": history_manifest_hash,
    }
    payload_hash = canonical_hash(stable_payload)
    return (
        {
            "artifact_type": "playbook_composite_recommendation_settlement",
            "forward_evidence_version": FORWARD_EVIDENCE_VERSION,
            "settlement_id": "playbook-forward-settlement:"
            + _required_string(snapshot.get("snapshot_id"), "snapshot_id").split(":")[
                -1
            ],
            "settlement_payload_hash": payload_hash,
            **stable_payload,
            "rank_score_is_not_probability": True,
            "not_trade_evidence": True,
            "order_construction_allowed": False,
            "strategy_promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        },
        "settled_forward_outcome",
    )


def _append_new_settlements(
    snapshots: Sequence[Mapping[str, object]],
    history_root: Path,
    history_manifest_hash: str,
    settlement_ledger_path: Path,
) -> tuple[list[dict[str, object]], int, dict[str, int], int, int]:
    raw_existing = _read_jsonl(settlement_ledger_path)
    effective_snapshot_ids = {
        _required_string(snapshot.get("snapshot_id"), "snapshot_id")
        for snapshot in snapshots
    }
    existing: list[dict[str, object]] = []
    existing_by_snapshot: dict[str, dict[str, object]] = {}
    non_evidentiary_raw_settlement_count = 0
    for record in raw_existing:
        snapshot_id = _required_string(record.get("snapshot_id"), "snapshot_id")
        if snapshot_id not in effective_snapshot_ids:
            non_evidentiary_raw_settlement_count += 1
            continue
        prior = existing_by_snapshot.get(snapshot_id)
        if prior is not None:
            if prior.get("settlement_payload_hash") != record.get(
                "settlement_payload_hash"
            ):
                raise ValueError(
                    "immutable Playbook settlement has conflicting payloads: "
                    f"snapshot_id={snapshot_id}"
                )
            non_evidentiary_raw_settlement_count += 1
            continue
        existing_by_snapshot[snapshot_id] = record
        existing.append(record)
    history_by_symbol: dict[str, tuple[list[str], list[float]] | None] = {}
    fresh: list[dict[str, object]] = []
    pending_counts: dict[str, int] = defaultdict(int)
    for snapshot in snapshots:
        snapshot_id = _required_string(snapshot.get("snapshot_id"), "snapshot_id")
        if snapshot_id in existing_by_snapshot:
            continue
        symbol = _required_string(snapshot.get("symbol"), "symbol")
        if symbol not in history_by_symbol:
            history_by_symbol[symbol] = _load_adjusted_history(history_root, symbol)
        proposed, status = _settlement_record(
            snapshot,
            history_by_symbol[symbol],
            history_manifest_hash,
        )
        if proposed is None:
            pending_counts[status] += 1
            continue
        existing_by_snapshot[snapshot_id] = proposed
        fresh.append(proposed)
    _append_jsonl(settlement_ledger_path, fresh)
    return (
        [*existing, *fresh],
        len(fresh),
        dict(sorted(pending_counts.items())),
        len(raw_existing) + len(fresh),
        non_evidentiary_raw_settlement_count,
    )


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        tie_end = index
        while (
            tie_end + 1 < len(order)
            and values[order[tie_end + 1]] == values[order[index]]
        ):
            tie_end += 1
        average_rank = (index + tie_end) / 2.0 + 1.0
        for position in order[index : tie_end + 1]:
            ranks[position] = average_rank
        index = tie_end + 1
    return ranks


def _spearman(values: Sequence[float], outcomes: Sequence[float]) -> float:
    if len(values) != len(outcomes):
        raise ValueError(
            f"rank-IC vectors must have equal length: values={len(values)}, outcomes={len(outcomes)}"
        )
    if len(values) < 3:
        raise ValueError(
            f"rank-IC requires at least three observations: count={len(values)}"
        )
    value_ranks = _ranks(values)
    outcome_ranks = _ranks(outcomes)
    value_mean = fmean(value_ranks)
    outcome_mean = fmean(outcome_ranks)
    covariance = sum(
        (value - value_mean) * (outcome - outcome_mean)
        for value, outcome in zip(value_ranks, outcome_ranks)
    )
    value_variance = sum((value - value_mean) ** 2 for value in value_ranks)
    outcome_variance = sum((outcome - outcome_mean) ** 2 for outcome in outcome_ranks)
    if value_variance <= 0.0 or outcome_variance <= 0.0:
        return 0.0
    return covariance / math.sqrt(value_variance * outcome_variance)


def build_forward_evidence_report(
    snapshots: Sequence[Mapping[str, object]],
    settlements: Sequence[Mapping[str, object]],
    newly_recorded_count: int,
    newly_settled_count: int,
    pending_counts: Mapping[str, int],
    raw_snapshot_ledger_count: int,
    same_market_date_duplicate_snapshot_count: int,
    raw_settlement_ledger_count: int,
    non_evidentiary_raw_settlement_count: int,
    snapshot_ledger_path: Path,
    settlement_ledger_path: Path,
) -> dict[str, object]:
    """Summarize evidence without fitting probabilities or changing weights."""

    groups: dict[tuple[str, int], list[Mapping[str, object]]] = defaultdict(list)
    for settlement in settlements:
        batch_id = _required_string(settlement.get("batch_id"), "batch_id")
        raw_horizon = settlement.get("evaluation_horizon_trading_days")
        if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int):
            raise TypeError(
                f"settlement evaluation horizon must be an integer: value={raw_horizon!r}"
            )
        groups[(batch_id, raw_horizon)].append(settlement)

    cohorts: list[dict[str, object]] = []
    eligible_rank_ics: list[float] = []
    for (batch_id, horizon), records in sorted(groups.items()):
        sample_count = len(records)
        eligible = sample_count >= MINIMUM_RANK_IC_COHORT_SIZE
        rank_ic = (
            _spearman(
                [
                    _required_number(
                        record.get("research_priority_score"), "research_priority_score"
                    )
                    for record in records
                ],
                [
                    _required_number(
                        record.get("signed_forward_return"), "signed_forward_return"
                    )
                    for record in records
                ],
            )
            if eligible
            else None
        )
        if rank_ic is not None:
            eligible_rank_ics.append(rank_ic)
        cohorts.append(
            {
                "batch_id": batch_id,
                "evaluation_horizon_trading_days": horizon,
                "sample_count": sample_count,
                "minimum_sample_count": MINIMUM_RANK_IC_COHORT_SIZE,
                "rank_ic_status": (
                    "diagnostic_available" if eligible else "insufficient_cohort_sample"
                ),
                "rank_ic": round(rank_ic, 8) if rank_ic is not None else None,
            }
        )

    settled_count = len(settlements)
    sample_sufficient = (
        settled_count >= MINIMUM_SETTLED_RECOMMENDATIONS
        and len(eligible_rank_ics) >= MINIMUM_RANK_IC_COHORTS
    )
    directional_accuracy = (
        sum(bool(record.get("directionally_correct")) for record in settlements)
        / settled_count
        if settled_count
        else None
    )
    mean_signed_return = (
        fmean(
            _required_number(
                record.get("signed_forward_return"), "signed_forward_return"
            )
            for record in settlements
        )
        if settled_count
        else None
    )
    body: dict[str, object] = {
        "artifact_type": "playbook_composite_forward_evidence_report",
        "forward_evidence_version": FORWARD_EVIDENCE_VERSION,
        "evidence_status": (
            "forward_rank_diagnostics_available_weight_tuning_still_disabled"
            if sample_sufficient
            else "collecting_horizon_matched_forward_evidence"
        ),
        "weight_calibration_status": (
            "forward_rank_sample_available_manual_ablation_required"
            if sample_sufficient
            else "provisional_weights_insufficient_forward_rank_evidence"
        ),
        "snapshot_count": len(snapshots),
        "raw_snapshot_ledger_count": raw_snapshot_ledger_count,
        "same_market_date_duplicate_snapshot_count": (
            same_market_date_duplicate_snapshot_count
        ),
        "duplicate_snapshots_counted_as_evidence": False,
        "same_market_date_model_variants_counted_as_independent_evidence": False,
        "snapshot_evidence_identity_fields": list(SNAPSHOT_EVIDENCE_IDENTITY_FIELDS),
        "newly_recorded_snapshot_count": newly_recorded_count,
        "settled_count": settled_count,
        "raw_settlement_ledger_count": raw_settlement_ledger_count,
        "non_evidentiary_raw_settlement_count": (non_evidentiary_raw_settlement_count),
        "duplicate_settlements_counted_as_evidence": False,
        "newly_settled_count": newly_settled_count,
        "pending_count": sum(pending_counts.values()),
        "pending_by_status": dict(pending_counts),
        "minimum_settled_recommendations": MINIMUM_SETTLED_RECOMMENDATIONS,
        "minimum_rank_ic_cohorts": MINIMUM_RANK_IC_COHORTS,
        "minimum_rank_ic_cohort_size": MINIMUM_RANK_IC_COHORT_SIZE,
        "sample_sufficient": sample_sufficient,
        "eligible_rank_ic_cohort_count": len(eligible_rank_ics),
        "mean_within_batch_horizon_rank_ic": (
            round(fmean(eligible_rank_ics), 8) if eligible_rank_ics else None
        ),
        "directional_accuracy": (
            round(directional_accuracy, 8) if directional_accuracy is not None else None
        ),
        "mean_signed_forward_return": (
            round(mean_signed_return, 10) if mean_signed_return is not None else None
        ),
        "rank_ic_cohorts": cohorts,
        "snapshot_ledger_path": str(snapshot_ledger_path),
        "snapshot_ledger_sha256": _file_sha256(snapshot_ledger_path),
        "settlement_ledger_path": str(settlement_ledger_path),
        "settlement_ledger_sha256": _file_sha256(settlement_ledger_path),
        "short_term_evaluation_horizon_trading_days": SHORT_TERM_EVALUATION_HORIZON,
        "long_term_evaluation_horizon_trading_days": LONG_TERM_EVALUATION_HORIZON,
        "brier_score_claimed": False,
        "expected_calibration_error_claimed": False,
        "rank_score_is_not_probability": True,
        "automatic_weight_tuning_allowed": False,
        "weight_activation_allowed": False,
        "order_construction_allowed": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}


def update_playbook_forward_evidence(
    rankings: Mapping[str, object],
    history_root: Path,
    history_manifest_hash: str,
    snapshot_ledger_path: Path,
    settlement_ledger_path: Path,
    report_path: Path,
) -> dict[str, object]:
    """Record current composite ranks, settle matured records, and publish truth."""

    manifest_hash = _required_string(history_manifest_hash, "history_manifest_hash")
    proposed = build_recommendation_snapshots(rankings)
    (
        snapshots,
        newly_recorded_count,
        raw_snapshot_ledger_count,
        same_market_date_duplicate_snapshot_count,
    ) = _append_new_snapshots(
        snapshot_ledger_path,
        proposed,
    )
    (
        settlements,
        newly_settled_count,
        pending_counts,
        raw_settlement_ledger_count,
        non_evidentiary_raw_settlement_count,
    ) = _append_new_settlements(
        snapshots,
        history_root,
        manifest_hash,
        settlement_ledger_path,
    )
    report = build_forward_evidence_report(
        snapshots,
        settlements,
        newly_recorded_count,
        newly_settled_count,
        pending_counts,
        raw_snapshot_ledger_count,
        same_market_date_duplicate_snapshot_count,
        raw_settlement_ledger_count,
        non_evidentiary_raw_settlement_count,
        snapshot_ledger_path,
        settlement_ledger_path,
    )
    write_json_atomic(report_path, report)
    return report
