"""Point-in-time audit for trend-channel containment semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Final, TypedDict

from dopey.evolution.coach_bridge import REFERENCE_PATTERN, build_quarantined_coach_proposal_batch
from dopey.protocols.identity import canonical_hash
from dopey_chart_vision.grounded_structure_engine import SWING_CONFIRMATION_RADIUS
from dopey_equity_swing.market_structure import Bar, confirmed_pivots, trend_channel


CHANNEL_CONTAINMENT_AUDIT_VERSION: Final[str] = "dopey-channel-containment-audit-v1"
CHANNEL_LOOKBACK_BARS: Final[int] = 90
MINIMUM_PREFIX_BARS: Final[int] = 60
PRICE_QUANTUM: Final[Decimal] = Decimal("0.000001")


class ChannelContainmentObservation(TypedDict):
    as_of: str
    close_decimal: str
    lower_bound_decimal: str
    upper_bound_decimal: str
    channel_position_decimal: str
    trend_direction: str
    containment_state: str
    support_pivots_used: int
    resistance_pivots_used: int
    point_in_time_prefix_only: bool


def _decimal(value: float) -> str:
    normalized = Decimal(str(value)).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
    if normalized == Decimal("-0.000000"):
        normalized = Decimal("0.000000")
    return format(normalized, "f")


def _containment_state(position: float) -> str:
    if position < 0.0:
        return "below_lower_bound"
    if position > 1.0:
        return "above_upper_bound"
    return "contained"


def _source_window(session: Mapping[str, Any], rows: Sequence[Bar]) -> tuple[tuple[Bar, ...], Mapping[str, Any]]:
    evidence = session.get("evidence_coach")
    if not isinstance(evidence, Mapping):
        raise ValueError("channel audit source lacks evidence_coach")
    replay = evidence.get("blind_replay")
    if not isinstance(replay, Mapping):
        raise ValueError("channel audit source lacks blind_replay")
    frozen = replay.get("frozen_evidence")
    if not isinstance(frozen, Mapping):
        raise ValueError("channel audit source lacks frozen_evidence")
    visible_count = int(frozen.get("visible_bar_count", 0))
    reveal_count = int(replay.get("reveal_bar_count", 0))
    required_count = visible_count + reveal_count
    reveal_end = str(replay.get("reveal_end", ""))
    eligible = tuple(row for row in rows if str(row["date"]) <= reveal_end)
    if required_count < MINIMUM_PREFIX_BARS or len(eligible) < required_count:
        raise ValueError(
            "channel audit cannot reconstruct source window: "
            f"required={required_count}, eligible={len(eligible)}, reveal_end={reveal_end!r}"
        )
    window = eligible[-required_count:]
    if str(window[-1]["date"]) != reveal_end:
        raise ValueError(
            "channel audit source end date is unavailable: "
            f"required={reveal_end!r}, actual={window[-1]['date']!r}"
        )
    return window, replay


def _bar_id(symbol: str, row: Bar) -> str:
    body = {
        "symbol": symbol,
        "date": row["date"],
        "open": _decimal(float(row["open"])),
        "high": _decimal(float(row["high"])),
        "low": _decimal(float(row["low"])),
        "close": _decimal(float(row["close"])),
        "volume": int(row["volume"]),
    }
    return f"bar:{canonical_hash(body)[:24]}"


def _visible_ohlcv_hash(symbol: str, rows: Sequence[Bar]) -> str:
    return canonical_hash(
        [
            {
                "bar_id": _bar_id(symbol, row),
                "date": row["date"],
                "open": _decimal(float(row["open"])),
                "high": _decimal(float(row["high"])),
                "low": _decimal(float(row["low"])),
                "close": _decimal(float(row["close"])),
                "volume": int(row["volume"]),
            }
            for row in rows
        ]
    )


def _reveal_window_hash(rows: Sequence[Bar]) -> str:
    return canonical_hash(
        [
            {
                "date": row["date"],
                "open": _decimal(float(row["open"])),
                "high": _decimal(float(row["high"])),
                "low": _decimal(float(row["low"])),
                "close": _decimal(float(row["close"])),
                "volume": int(row["volume"]),
            }
            for row in rows
        ]
    )


def _validate_source_rows(session: Mapping[str, Any], window: Sequence[Bar], replay: Mapping[str, Any]) -> None:
    frozen = replay.get("frozen_evidence")
    if not isinstance(frozen, Mapping):
        raise ValueError("channel audit source lacks frozen_evidence")
    reveal_count = int(replay["reveal_bar_count"])
    frozen_rows = window[:-reveal_count]
    reveal_rows = window[-reveal_count:]
    symbol = str(replay["symbol"])
    actual_visible_hash = _visible_ohlcv_hash(symbol, frozen_rows)
    expected_visible_hash = str(frozen.get("visible_ohlcv_hash", ""))
    if actual_visible_hash != expected_visible_hash:
        raise ValueError(
            "channel audit frozen OHLCV hash mismatch: "
            f"session_hash={session.get('session_hash')}, expected={expected_visible_hash}, "
            f"actual={actual_visible_hash}"
        )
    actual_reveal_hash = _reveal_window_hash(reveal_rows)
    expected_reveal_hash = str(replay.get("reveal_window_hash", ""))
    if actual_reveal_hash != expected_reveal_hash:
        raise ValueError(
            "channel audit reveal-window hash mismatch: "
            f"session_hash={session.get('session_hash')}, expected={expected_reveal_hash}, "
            f"actual={actual_reveal_hash}"
        )


def _channel_proposal_id(
    session: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> tuple[str, str]:
    evidence = session["evidence_coach"]
    structures = evidence["structure_registry"]
    trend_refs = {
        str(record["structure_id"])
        for record in structures
        if isinstance(record, Mapping) and record.get("structure_type") == "trend_channel"
    }
    sessions = batch.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != 1:
        raise ValueError("channel audit requires exactly one validated coach session")
    proposals = sessions[0].get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("channel audit proposal batch is malformed")
    matches: list[Mapping[str, Any]] = []
    for record in proposals:
        if not isinstance(record, Mapping) or record.get("proposal_state") != "QUARANTINED":
            continue
        hypothesis = record.get("hypothesis")
        if not isinstance(hypothesis, Mapping):
            raise ValueError(
                "channel audit proposal lacks its validated hypothesis: "
                f"proposal_id={record.get('proposal_id')}"
            )
        hypothesis_refs: set[str] = set()
        for field in ("title", "mechanism", "evidence_needed", "falsification"):
            value = hypothesis.get(field)
            if not isinstance(value, str):
                raise ValueError(
                    "channel audit proposal hypothesis is malformed: "
                    f"proposal_id={record.get('proposal_id')}, field={field}"
                )
            hypothesis_refs.update(REFERENCE_PATTERN.findall(value))
        if trend_refs.intersection(hypothesis_refs):
            matches.append(record)
    if len(matches) != 1:
        raise ValueError(
            "channel audit requires one experiment-linked trend-channel proposal: "
            f"actual={len(matches)}, trend_refs={sorted(trend_refs)}"
        )
    linked_experiments = matches[0].get("linked_experiments")
    if not isinstance(linked_experiments, list):
        raise ValueError(
            "channel audit proposal linked experiments are malformed: "
            f"proposal_id={matches[0].get('proposal_id')}"
        )
    experiment_matches = [
        record
        for record in linked_experiments
        if isinstance(record, Mapping)
        and trend_refs.intersection(str(value) for value in record.get("evidence_refs", []))
    ]
    if len(experiment_matches) != 1:
        raise ValueError(
            "channel audit requires one linked experiment that directly references the trend channel: "
            f"proposal_id={matches[0].get('proposal_id')}, actual={len(experiment_matches)}"
        )
    return str(matches[0]["proposal_id"]), str(experiment_matches[0]["experiment_id"])


def _observations(rows: Sequence[Bar]) -> tuple[ChannelContainmentObservation, ...]:
    observations: list[ChannelContainmentObservation] = []
    for end in range(MINIMUM_PREFIX_BARS, len(rows) + 1):
        prefix = list(rows[:end])
        pivots = confirmed_pivots(prefix, SWING_CONFIRMATION_RADIUS)
        channel = trend_channel(prefix, pivots, CHANNEL_LOOKBACK_BARS)
        if channel["channel_status"] != "confirmed":
            continue
        position = float(channel["channel_position"])
        observations.append(
            {
                "as_of": str(prefix[-1]["date"]),
                "close_decimal": _decimal(float(prefix[-1]["close"])),
                "lower_bound_decimal": _decimal(float(channel["lower_bound"])),
                "upper_bound_decimal": _decimal(float(channel["upper_bound"])),
                "channel_position_decimal": _decimal(position),
                "trend_direction": str(channel["direction"]),
                "containment_state": _containment_state(position),
                "support_pivots_used": int(channel["support_pivots_used"]),
                "resistance_pivots_used": int(channel["resistance_pivots_used"]),
                "point_in_time_prefix_only": True,
            }
        )
    return tuple(observations)


def build_channel_containment_audit(
    session: Mapping[str, Any],
    rows: Sequence[Bar],
) -> dict[str, Any]:
    """Run the coach-requested definition audit without claiming predictive edge."""

    batch = build_quarantined_coach_proposal_batch((session,))
    proposal_id, experiment_id = _channel_proposal_id(session, batch)
    window, replay = _source_window(session, rows)
    _validate_source_rows(session, window, replay)
    observations = _observations(window)
    contained_count = sum(record["containment_state"] == "contained" for record in observations)
    below_count = sum(record["containment_state"] == "below_lower_bound" for record in observations)
    above_count = sum(record["containment_state"] == "above_upper_bound" for record in observations)
    hard_falsification_triggered = bool(observations) and contained_count == 0
    latest = observations[-1] if observations else None
    latest_outside = latest is not None and latest["containment_state"] != "contained"
    if not observations:
        outcome_status = "blocked_no_confirmed_point_in_time_channels"
    elif hard_falsification_triggered:
        outcome_status = "complete_channel_definition_hard_falsification_triggered"
    elif latest_outside:
        outcome_status = "complete_definition_survives_latest_supportive_bias_blocked"
    else:
        outcome_status = "complete_definition_survives_latest_contained"
    body: dict[str, Any] = {
        "artifact_type": "channel_containment_point_in_time_audit",
        "schema_version": CHANNEL_CONTAINMENT_AUDIT_VERSION,
        "audit_status": "complete",
        "outcome_status": outcome_status,
        "source_session_id": str(session["session_id"]),
        "source_session_hash": str(session["session_hash"]),
        "source_proposal_batch_hash": str(batch["batch_hash"]),
        "source_proposal_id": proposal_id,
        "source_experiment_id": experiment_id,
        "source_replay_hash": str(replay["replay_hash"]),
        "symbol": str(replay["symbol"]),
        "timeframe": str(replay["timeframe"]),
        "window_start": str(window[0]["date"]),
        "window_end": str(window[-1]["date"]),
        "window_bar_count": len(window),
        "channel_observation_count": len(observations),
        "contained_observation_count": contained_count,
        "below_lower_bound_count": below_count,
        "above_upper_bound_count": above_count,
        "hard_falsification_triggered": hard_falsification_triggered,
        "latest_observation": latest,
        "observation_hash": canonical_hash(observations),
        "observations": list(observations),
        "definition_integrity_finding": (
            "trend direction and current containment are distinct; an outside-channel observation "
            "must not inherit a supportive directional bias from channel slope"
        ),
        "predictive_edge_status": "blocked_pending_purged_multi_symbol_held_out_validation",
        "mutation_resolution": {
            "surface": "grounded_chart_structure_directional_bias_semantics",
            "resolved_change": "gate_channel_directional_bias_on_current_containment",
            "resolution_basis": "deterministic_definition_consistency_not_performance",
            "strategy_parameter_mutation_allowed": False,
            "automatic_code_mutation_allowed": False,
            "automatic_activation_allowed": False,
        },
        "option_outcome_claim_allowed": False,
        "broker_access": False,
        "order_authority": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "audit_hash": canonical_hash(body)}
