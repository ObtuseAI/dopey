"""Integration coverage for forward settlement, calibration, and durable memory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey.memory.graph import build_memory_graph
from dopey.memory.ledger import (
    MemoryKind,
    append_memory_record,
    build_memory_record,
    load_memory_records,
)
from dopey.protocols.identity import canonical_hash
from dopey.settlement.calibration import summarize_calibration
from dopey.settlement.grading import SettlementPolicy, grade_forward_prediction
from dopey.settlement.predictions import build_forward_prediction
from dopey_equity_swing.market_structure import Bar


def _bar(day: str, close: float) -> Bar:
    return {
        "date": day,
        "symbol": "SPY",
        "open": close,
        "high": close * 1.002,
        "low": close * 0.998,
        "close": close,
        "adjusted_close": close,
        "volume": 1_000_000,
        "source": "integration_test_only_not_readiness_evidence",
    }


def _rehashed_memory_record(
    record: dict[str, object],
    updates: dict[str, object],
    removed_fields: tuple[str, ...],
) -> dict[str, object]:
    merged = {**record, **updates}
    body = {
        key: value
        for key, value in merged.items()
        if key not in {"content_hash", "memory_id"} and key not in removed_fields
    }
    content_hash = canonical_hash(body)
    memory_kind = str(body["memory_kind"])
    return {
        **body,
        "memory_id": f"memory:{memory_kind}:{content_hash[:24]}",
        "content_hash": content_hash,
    }


def test_forward_settlement_calibration_and_memory_are_append_only(
    tmp_path: Path,
) -> None:
    prediction = build_forward_prediction(
        "SPY",
        "2026-07-06T21:00:00+00:00",
        "2026-07-06T20:00:00+00:00",
        {"bull": 0.6, "bear": 0.1, "neutral": 0.2, "unknown": 0.1},
        0.4,
        "ABSTAIN",
        ("evidence:1",),
        "vnext-input-time-proof:test",
        True,
        2,
        {"momentum_agent": 0.2},
        {
            "momentum_agent": {
                "bull": 0.55,
                "bear": 0.1,
                "neutral": 0.25,
                "unknown": 0.1,
            }
        },
    )
    rows = [
        _bar("2026-07-06", 100.0),
        _bar("2026-07-07", 101.0),
        _bar("2026-07-08", 103.0),
    ]
    policy = SettlementPolicy(0.01, 0.0025, 5, 1e-12)

    pending = grade_forward_prediction(prediction, rows, "2026-07-07", policy)
    settled = grade_forward_prediction(prediction, rows, "2026-07-08", policy)

    assert pending["settlement_status"] == "pending_minimum_horizon"
    assert pending["early_grading_performed"] is False
    assert settled["settlement_status"] == "settled_forward_outcome"
    assert settled["realized_class"] == "bull"
    assert settled["dominant_correct"] is True
    assert settled["promotion_allowed"] is False

    calibration = summarize_calibration((pending, settled), 10, 30)
    assert calibration["settled_total"] == 1
    assert calibration["pending_total"] == 1
    assert calibration["quarantined_missing_point_in_time_proof_total"] == 0
    assert calibration["expected_calibration_error"] == 0.6
    assert calibration["calibration_sample_sufficient"] is False

    record = build_memory_record(
        MemoryKind.SETTLEMENT,
        settled,
        "2026-07-08T21:00:00+00:00",
        str(prediction["prediction_id"]),
        (str(settled["settlement_id"]),),
        "integration-settlement-v1",
    )
    ledger = tmp_path / "memory" / "settlements.jsonl"
    first = append_memory_record(ledger, record)
    second = append_memory_record(ledger, record)

    assert first["append_status"] == "appended"
    assert second["append_status"] == "already_present_identical"
    assert len(load_memory_records(ledger, MemoryKind.SETTLEMENT)) == 1


def test_memory_load_rejects_payload_tampering_and_identity_spoofing(
    tmp_path: Path,
) -> None:
    record = build_memory_record(
        MemoryKind.OBSERVATION,
        {"symbol": "SPY", "state": "observed"},
        "2026-07-08T21:00:00+00:00",
        "observation-parent",
        ("source:1",),
        "integration-observation-v1",
    )
    tampered = dict(record)
    tampered["payload"] = {"symbol": "SPY", "state": "rewritten_after_outcome"}
    ledger = tmp_path / "memory" / "tampered.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="content hash mismatch"):
        load_memory_records(ledger, None)

    spoofed = dict(record)
    spoofed["memory_id"] = "memory:observation:" + "0" * 24
    ledger.write_text(json.dumps(spoofed) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="identity is not bound"):
        load_memory_records(ledger, None)


@pytest.mark.parametrize(
    (
        "case_name",
        "updates",
        "removed_fields",
        "error_type",
        "error_pattern",
    ),
    (
        (
            "append_only_false",
            {"append_only": False},
            (),
            ValueError,
            "canonical research-only boundary",
        ),
        (
            "trade_authority_enabled",
            {"not_trade_authority": False},
            (),
            ValueError,
            "canonical research-only boundary",
        ),
        (
            "paper_boundary_disabled",
            {"paper_only": False},
            (),
            ValueError,
            "canonical research-only boundary",
        ),
        (
            "live_boundary_disabled",
            {"live_blocked": False},
            (),
            ValueError,
            "canonical research-only boundary",
        ),
        (
            "wrong_artifact_type",
            {"artifact_type": "unsafe_memory_record"},
            (),
            ValueError,
            "artifact type is unsupported",
        ),
        (
            "wrong_memory_version",
            {"memory_version": "dopey-memory-v2"},
            (),
            ValueError,
            "version is unsupported",
        ),
        (
            "unsupported_kind",
            {"memory_kind": "authority"},
            (),
            ValueError,
            "unsupported kind",
        ),
        (
            "empty_schema",
            {"schema_version": ""},
            (),
            ValueError,
            "schema version cannot be empty",
        ),
        (
            "non_string_schema",
            {"schema_version": 1},
            (),
            TypeError,
            "schema version must be a string",
        ),
        (
            "naive_timestamp",
            {"observed_at": "2026-07-08T21:00:00"},
            (),
            ValueError,
            "timestamp requires a timezone",
        ),
        (
            "non_string_timestamp",
            {"observed_at": 1},
            (),
            TypeError,
            "timestamp must be a string",
        ),
        (
            "non_string_parent",
            {"causal_parent_id": 1},
            (),
            TypeError,
            "causal parent identity must be a string",
        ),
        (
            "non_list_sources",
            {"source_ids": "source:1"},
            (),
            TypeError,
            "source identities must be a list",
        ),
        (
            "non_string_source",
            {"source_ids": ["source:1", 2]},
            (),
            TypeError,
            "source identities must contain only strings",
        ),
        (
            "empty_source",
            {"source_ids": [""]},
            (),
            ValueError,
            "source identities cannot contain empty values",
        ),
        (
            "noncanonical_sources",
            {"source_ids": ["source:2", "source:1", "source:1"]},
            (),
            ValueError,
            "source identities must be sorted and unique",
        ),
        (
            "non_object_payload",
            {"payload": ["unsafe"]},
            (),
            TypeError,
            "payload must be an object",
        ),
        (
            "empty_payload",
            {"payload": {}},
            (),
            ValueError,
            "payload cannot be empty",
        ),
        (
            "missing_artifact_type",
            {},
            ("artifact_type",),
            ValueError,
            "envelope differs from the exact schema",
        ),
        (
            "missing_memory_version",
            {},
            ("memory_version",),
            ValueError,
            "envelope differs from the exact schema",
        ),
        (
            "missing_lineage",
            {},
            ("causal_parent_id", "source_ids"),
            ValueError,
            "envelope differs from the exact schema",
        ),
        (
            "missing_safety_fields",
            {},
            ("append_only", "not_trade_authority"),
            ValueError,
            "envelope differs from the exact schema",
        ),
        (
            "unexpected_authority_field",
            {"trade_authority": True},
            (),
            ValueError,
            "envelope differs from the exact schema",
        ),
    ),
)
def test_memory_envelope_rejects_internally_rehashed_unsafe_records(
    tmp_path: Path,
    case_name: str,
    updates: dict[str, object],
    removed_fields: tuple[str, ...],
    error_type: type[Exception],
    error_pattern: str,
) -> None:
    valid = build_memory_record(
        MemoryKind.OBSERVATION,
        {"symbol": "SPY", "state": "observed"},
        "2026-07-08T21:00:00+00:00",
        "observation-parent",
        ("source:1",),
        "integration-observation-v1",
    )
    candidate = _rehashed_memory_record(valid, updates, removed_fields)
    ledger = tmp_path / f"{case_name}.jsonl"

    with pytest.raises(error_type, match=error_pattern):
        append_memory_record(ledger, candidate)
    ledger.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    with pytest.raises(error_type, match=error_pattern):
        load_memory_records(ledger, None)


def test_memory_graph_preserves_causal_and_source_lineage() -> None:
    parent = build_memory_record(
        MemoryKind.OBSERVATION,
        {"symbol": "SPY", "state": "observed"},
        "2026-07-08T20:00:00+00:00",
        "",
        ("source:market-snapshot",),
        "integration-observation-v1",
    )
    child = build_memory_record(
        MemoryKind.EPISODE,
        {"symbol": "SPY", "state": "interpreted"},
        "2026-07-08T21:00:00+00:00",
        str(parent["memory_id"]),
        (str(parent["memory_id"]), "source:research-cycle"),
        "integration-episode-v1",
    )

    graph = build_memory_graph((parent, child))

    assert graph["graph_status"] == "complete_derived_index"
    assert graph["memory_node_count"] == 2
    assert graph["external_reference_node_count"] == 2
    assert graph["causal_cycle_memory_ids"] == []
    assert graph["temporal_order_violations"] == []
    assert graph["canonical_memory_ledgers_remain_source_of_truth"] is True
    assert {edge["edge_kind"] for edge in graph["edges"]} == {
        "causal_parent",
        "source_provenance",
    }


def test_prediction_without_point_in_time_proof_is_quarantined() -> None:
    legacy_prediction = {
        "prediction_id": "legacy-prediction",
        "symbol": "SPY",
        "minimum_settlement_date": "2026-07-08",
        "prediction_market_time": "2026-07-06T20:00:00+00:00",
        "paper_only": True,
        "live_blocked": True,
    }
    policy = SettlementPolicy(0.01, 0.0025, 5, 1e-12)

    result = grade_forward_prediction(legacy_prediction, (), "2026-07-08", policy)
    calibration = summarize_calibration((result,), 10, 30)

    assert result["settlement_status"] == "quarantined_missing_point_in_time_proof"
    assert result["calibration_eligible"] is False
    assert calibration["settled_total"] == 0
    assert calibration["pending_total"] == 0
    assert calibration["quarantined_missing_point_in_time_proof_total"] == 1


def test_forward_settlement_never_reads_a_price_after_as_of_date() -> None:
    prediction = build_forward_prediction(
        "SPY",
        "2026-07-06T21:00:00+00:00",
        "2026-07-06T20:00:00+00:00",
        {"bull": 0.6, "bear": 0.1, "neutral": 0.2, "unknown": 0.1},
        0.4,
        "ABSTAIN",
        ("evidence:1",),
        "vnext-input-time-proof:test",
        True,
        2,
        {"momentum_agent": 0.2},
        {
            "momentum_agent": {
                "bull": 0.55,
                "bear": 0.1,
                "neutral": 0.25,
                "unknown": 0.1,
            }
        },
    )
    rows = [_bar("2026-07-06", 100.0), _bar("2026-07-09", 104.0)]
    policy = SettlementPolicy(0.01, 0.0025, 5, 1e-12)

    result = grade_forward_prediction(prediction, rows, "2026-07-08", policy)

    assert result["settlement_status"] == "due_missing_verified_price"
    assert result["settlement_price_available"] is False
    assert result["early_grading_performed"] is False


def test_forward_prediction_rejects_invalid_probability_mass() -> None:
    with pytest.raises(ValueError, match="finite and within"):
        build_forward_prediction(
            "SPY",
            "2026-07-06T21:00:00+00:00",
            "2026-07-06T20:00:00+00:00",
            {"bull": 1.1, "bear": -0.1, "neutral": 0.0, "unknown": 0.0},
            0.4,
            "ABSTAIN",
            ("evidence:1",),
            "vnext-input-time-proof:test",
            True,
            2,
            {"momentum_agent": 0.2},
            {
                "momentum_agent": {
                    "bull": 0.55,
                    "bear": 0.1,
                    "neutral": 0.25,
                    "unknown": 0.1,
                }
            },
        )


def test_memory_ledger_recovers_torn_tail_and_preserves_interior_strictness(
    tmp_path: Path,
) -> None:
    record = build_memory_record(
        MemoryKind.SETTLEMENT,
        {"symbol": "SPY", "state": "settled"},
        "2026-07-08T21:00:00+00:00",
        "settlement-parent",
        ("source:1",),
        "integration-settlement-v1",
    )
    ledger = tmp_path / "memory" / "settlements.jsonl"
    append_memory_record(ledger, record)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write('{"torn_append":')

    assert len(load_memory_records(ledger, None)) == 1

    followup = build_memory_record(
        MemoryKind.SETTLEMENT,
        {"symbol": "QQQ", "state": "settled"},
        "2026-07-08T22:00:00+00:00",
        "settlement-parent",
        ("source:2",),
        "integration-settlement-v1",
    )
    assert append_memory_record(ledger, followup)["append_status"] == "appended"
    assert len(load_memory_records(ledger, None)) == 2

    interior_corrupt = tmp_path / "memory" / "interior.jsonl"
    interior_corrupt.parent.mkdir(parents=True, exist_ok=True)
    interior_corrupt.write_text(
        json.dumps(dict(record), sort_keys=True)
        + '\n{"torn_append":\n'
        + json.dumps(dict(followup), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        load_memory_records(interior_corrupt, None)


def test_memory_ledger_preserves_complete_unterminated_record(
    tmp_path: Path,
) -> None:
    first = build_memory_record(
        MemoryKind.SETTLEMENT,
        {"symbol": "SPY", "state": "settled"},
        "2026-07-08T21:00:00+00:00",
        "settlement-parent",
        ("source:1",),
        "integration-settlement-v1",
    )
    second = build_memory_record(
        MemoryKind.SETTLEMENT,
        {"symbol": "QQQ", "state": "settled"},
        "2026-07-08T22:00:00+00:00",
        "settlement-parent",
        ("source:2",),
        "integration-settlement-v1",
    )
    ledger = tmp_path / "memory" / "settlements.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(dict(first), sort_keys=True), encoding="utf-8")

    append_memory_record(ledger, second)

    records = load_memory_records(ledger, None)
    assert [record["memory_id"] for record in records] == [
        first["memory_id"],
        second["memory_id"],
    ]


def test_memory_ledger_rejects_newline_terminated_corrupt_tail(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "memory" / "settlements.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"corrupt":\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_memory_records(ledger, None)


def test_forward_settlement_stale_price_is_data_gap_not_fatal() -> None:
    prediction = build_forward_prediction(
        "STALE",
        "2026-07-06T21:00:00+00:00",
        "2026-07-06T20:00:00+00:00",
        {"bull": 0.6, "bear": 0.1, "neutral": 0.2, "unknown": 0.1},
        0.4,
        "ABSTAIN",
        ("evidence:1",),
        "vnext-input-time-proof:test",
        True,
        2,
        {"momentum_agent": 0.2},
        {
            "momentum_agent": {
                "bull": 0.55,
                "bear": 0.1,
                "neutral": 0.25,
                "unknown": 0.1,
            }
        },
    )
    # Delisted-symbol shape: the last verified bar is far beyond the allowed
    # price gap, so grading must report a data gap instead of raising and
    # wedging every other prediction in the batch.
    rows = [_bar("2026-07-06", 100.0), _bar("2026-07-20", 104.0)]
    policy = SettlementPolicy(0.01, 0.0025, 5, 1e-12)

    result = grade_forward_prediction(prediction, rows, "2026-07-21", policy)

    assert result["settlement_status"] == "due_missing_verified_price"
    assert result["settlement_price_available"] is False
    assert result["price_gap_reason"] == "settlement_price_too_stale_for_grading"
    assert result["settlement_price_gap_days"] > policy.maximum_price_gap_days
    assert result["early_grading_performed"] is False
    assert result["promotion_allowed"] is False
