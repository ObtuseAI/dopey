"""Trade Memory Graph - case-based conditional retrieval, measure-only.

Enrichment must attach point-in-time spine conditions (never look ahead);
retrieval must surface the conditional breakdown so a reviewer sees WHERE a
family did worse; and everything stays not_edge_evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import operator_tools.operator_build_trade_memory as trade_memory_builder
from dopey.strategy_engineering.trade_memory import (
    TradeMemoryCorruptionError,
    OUTCOME_UNIT,
    _outcome_stats,
    build_memory_index,
    enrich_record,
    retrieve_similar,
    spine_conditions,
)
from dopey.strategy_engineering.trade_memory_active import (
    ACTIVE_POINTER_NAME,
    load_active_trade_memory_summary,
    resolve_active_trade_memory_packet,
)
from dopey.strategy_engineering.trade_memory_sqlite import (
    build_trade_memory_sqlite,
    retrieve_similar_indexed,
)


def _spine(stretched: bool) -> tuple[list[float], list[str]]:
    # 30 flat days at 100, then either a stretch above (110) or a normal level
    closes = [100.0] * 30
    dates = [
        f"2020-01-{d:02d}" if d < 32 else f"2020-02-{d - 31:02d}" for d in range(1, 31)
    ]
    dates = [f"2020-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(30)]
    closes.append(110.0 if stretched else 100.5)
    dates.append("2020-03-01")
    return closes, dates


def test_spine_conditions_flags_stretch_without_lookahead() -> None:
    closes, dates = _spine(stretched=True)
    cond = spine_conditions(closes, dates, "2020-03-01")
    assert cond["stretch_bucket"] == "stretched_above"  # 110/100 - 1 = +10%
    assert cond["stretch"] > 0.08


def test_spine_conditions_near_when_not_stretched() -> None:
    closes, dates = _spine(stretched=False)
    cond = spine_conditions(closes, dates, "2020-03-01")
    assert cond["stretch_bucket"] == "near"


def test_unknown_condition_when_symbol_absent() -> None:
    record = {
        "signal_family": "mean_reversion",
        "symbol": "ZZZ",
        "signal_date": "2020-03-01",
        "entry_premium": 2.0,
        "path_pnl": -0.2,
        "trade_return_model_units": -0.1,
        "win_loss_marker": "loss",
    }
    enriched = enrich_record(record, {})
    assert enriched is not None
    assert enriched["stretch_bucket"] == "unknown"


def test_retrieve_surfaces_conditional_breakdown() -> None:
    # build a corpus where the family LOSES when stretched_above and WINS near
    index = []
    for i in range(40):
        index.append(
            {
                "family": "momentum_continuation",
                "strategy": "long_call",
                "direction": "bullish",
                "symbol": f"S{i}",
                "signal_date": "2020-03-01",
                "path_pnl": -0.5 if i < 20 else 0.4,
                "trade_return_model_units": -0.25 if i < 20 else 0.2,
                "win": i >= 20,
                "mfe": 0.3,
                "mae": -0.5 if i < 20 else -0.1,
                "exit_reason": "premium_stop",
                "holding_steps": 3,
                "stretch_bucket": "stretched_above" if i < 20 else "near",
                "rvol_bucket": "medium",
            }
        )
    result = retrieve_similar(index, "momentum_continuation")
    breakdown = result["conditional_by_stretch"]
    assert breakdown["stretched_above"]["mean_trade_return_model_units"] < 0
    assert breakdown["near"]["mean_trade_return_model_units"] > 0
    assert breakdown["stretched_above"]["outcome_unit"] == OUTCOME_UNIT
    assert breakdown["stretched_above"]["win_rate"] == 0.0
    assert breakdown["near"]["win_rate"] == 1.0


def test_outcome_stats_use_fractional_return_not_premium_dollar_pnl() -> None:
    records = [
        {
            "path_pnl": -5.0,
            "trade_return_model_units": -0.10,
            "win": False,
            "mae": -5.5,
        },
        {
            "path_pnl": -0.5,
            "trade_return_model_units": -0.95,
            "win": False,
            "mae": -0.6,
        },
    ]

    statistics = _outcome_stats(records)

    assert statistics["outcome_unit"] == OUTCOME_UNIT
    assert statistics["mean_trade_return_model_units"] == -0.525
    assert statistics["catastrophic_loss_share"] == 0.5
    assert "mean_path_pnl" not in statistics


def test_enrichment_rejects_missing_fractional_return() -> None:
    record = {
        "signal_family": "mean_reversion",
        "candidate_strategy": "long_put",
        "symbol": "ZZZ",
        "signal_date": "2020-03-01",
        "path_pnl": -1.0,
    }

    with pytest.raises(ValueError, match="trade_return_model_units"):
        enrich_record(record, {})


def test_enrichment_quarantines_impossible_long_premium_loss() -> None:
    record = {
        "signal_family": "mean_reversion",
        "candidate_strategy": "long_put",
        "symbol": "VIXY",
        "signal_date": "2020-03-01",
        "entry_premium": 5.0,
        "path_pnl": -50.0,
        "trade_return_model_units": -10.0,
    }

    with pytest.raises(
        TradeMemoryCorruptionError,
        match="long_premium_return_below_total_loss",
    ):
        enrich_record(record, {})


def test_enrichment_enforces_fractional_return_pnl_identity() -> None:
    record = {
        "signal_family": "mean_reversion",
        "candidate_strategy": "long_put",
        "symbol": "TEST",
        "signal_date": "2020-03-01",
        "entry_premium": 5.0,
        "path_pnl": -1.0,
        "trade_return_model_units": -0.5,
    }

    with pytest.raises(
        TradeMemoryCorruptionError,
        match="fractional_return_pnl_identity_mismatch",
    ):
        enrich_record(record, {})


def test_enrichment_quarantines_missing_entry_premium() -> None:
    record = {
        "signal_family": "mean_reversion",
        "candidate_strategy": "long_put",
        "symbol": "TEST",
        "signal_date": "2020-03-01",
        "path_pnl": -0.5,
        "trade_return_model_units": -0.1,
    }

    with pytest.raises(
        TradeMemoryCorruptionError,
        match="missing_entry_premium",
    ):
        enrich_record(record, {})


@pytest.mark.parametrize("entry_premium", [float("nan"), float("inf")])
def test_enrichment_quarantines_non_finite_entry_premium(
    entry_premium: float,
) -> None:
    record = {
        "signal_family": "mean_reversion",
        "candidate_strategy": "long_put",
        "symbol": "TEST",
        "signal_date": "2020-03-01",
        "entry_premium": entry_premium,
        "path_pnl": -0.5,
        "trade_return_model_units": -0.1,
    }

    with pytest.raises(
        TradeMemoryCorruptionError,
        match="non_finite_entry_premium",
    ):
        enrich_record(record, {})


@pytest.mark.parametrize("path_pnl", [float("nan"), float("inf")])
def test_enrichment_quarantines_non_finite_path_pnl(
    path_pnl: float,
) -> None:
    record = {
        "signal_family": "mean_reversion",
        "candidate_strategy": "long_put",
        "symbol": "TEST",
        "signal_date": "2020-03-01",
        "entry_premium": 5.0,
        "path_pnl": path_pnl,
        "trade_return_model_units": -0.1,
    }

    with pytest.raises(
        TradeMemoryCorruptionError,
        match="non_finite_path_pnl",
    ):
        enrich_record(record, {})


def test_matched_filter_narrows_to_condition() -> None:
    index = [
        {
            "family": "mean_reversion",
            "strategy": "long_put",
            "direction": "bearish",
            "symbol": "A",
            "signal_date": "d",
            "path_pnl": -0.3,
            "trade_return_model_units": -0.15,
            "win": False,
            "mfe": 0.1,
            "mae": -0.3,
            "exit_reason": "stop",
            "holding_steps": 2,
            "stretch_bucket": "stretched_above",
            "rvol_bucket": "high",
        },
        {
            "family": "mean_reversion",
            "strategy": "long_put",
            "direction": "bearish",
            "symbol": "B",
            "signal_date": "d",
            "path_pnl": 0.2,
            "trade_return_model_units": 0.1,
            "win": True,
            "mfe": 0.4,
            "mae": -0.1,
            "exit_reason": "target",
            "holding_steps": 4,
            "stretch_bucket": "near",
            "rvol_bucket": "low",
        },
    ]
    result = retrieve_similar(index, "mean_reversion", stretch_bucket="stretched_above")
    assert result["matched"]["count"] == 1
    assert result["matched"]["win_rate"] == 0.0
    assert result["family_total"]["count"] == 2  # family total is unfiltered


def test_build_index_skips_unusable_and_stays_measure_only() -> None:
    records = [
        {
            "signal_family": "momentum_trend",
            "symbol": "A",
            "signal_date": "d",
            "entry_premium": 2.0,
            "path_pnl": 0.1,
            "trade_return_model_units": 0.05,
            "win_loss_marker": "win",
            "candidate_strategy": "long_call",
        },
        {"signal_family": "", "symbol": "B", "path_pnl": 0.2},  # no family -> skipped
        {
            "signal_family": "mean_reversion",
            "symbol": "C",
            "path_pnl": None,
        },  # no pnl -> skipped
    ]
    index = build_memory_index(records, {})
    assert len(index) == 1
    result = retrieve_similar(index, "momentum_trend")
    assert result["not_edge_evidence"] is True
    assert result["promotion_allowed"] is False


def test_sqlite_projection_preserves_duplicate_events_and_matches_retrieval(
    tmp_path: Path,
) -> None:
    records = [
        {
            "family": "mean_reversion",
            "strategy": "long_put",
            "direction": "bearish",
            "symbol": "A",
            "signal_date": "2020-03-01",
            "path_pnl": -0.3,
            "trade_return_model_units": -0.15,
            "win": False,
            "mfe": 0.1,
            "mae": -0.3,
            "exit_reason": "stop",
            "holding_steps": 2,
            "stretch": 0.1,
            "stretch_bucket": "stretched_above",
            "rvol": 0.5,
            "rvol_bucket": "high",
            "trailing_5d_return": 0.08,
        },
        {
            "family": "mean_reversion",
            "strategy": "long_put",
            "direction": "bearish",
            "symbol": "B",
            "signal_date": "2020-03-02",
            "path_pnl": 0.2,
            "trade_return_model_units": 0.1,
            "win": True,
            "mfe": 0.4,
            "mae": -0.1,
            "exit_reason": "target",
            "holding_steps": 4,
            "stretch": 0.01,
            "stretch_bucket": "near",
            "rvol": 0.15,
            "rvol_bucket": "low",
            "trailing_5d_return": 0.01,
        },
    ]
    source = tmp_path / "trade_memory.jsonl"
    source.write_text(
        "\n".join(json.dumps(record) for record in (*records, records[0])) + "\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "trade_memory.sqlite3"

    manifest = build_trade_memory_sqlite(source, index_path)
    indexed = retrieve_similar_indexed(
        index_path,
        "mean_reversion",
        "stretched_above",
        None,
        "long_put",
    )
    in_memory = retrieve_similar(
        (*records, records[0]),
        "mean_reversion",
        stretch_bucket="stretched_above",
        strategy="long_put",
    )

    assert manifest["row_count"] == 3
    assert manifest["unique_content_hash_count"] == 2
    assert manifest["duplicate_content_row_count"] == 1
    assert manifest["sqlite_is_rebuildable_derived_index"] is True
    assert indexed["family_total"] == in_memory["family_total"]
    assert indexed["matched"] == in_memory["matched"]
    assert indexed["conditional_by_stretch"] == in_memory["conditional_by_stretch"]
    assert indexed["not_edge_evidence"] is True
    assert indexed["promotion_allowed"] is False


def test_sqlite_projection_rejects_canonical_source_path_alias(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trade_memory.jsonl"
    canonical_bytes = b'{"canonical":"must-remain-unchanged"}\n'
    source.write_bytes(canonical_bytes)

    with pytest.raises(ValueError, match="paths alias"):
        build_trade_memory_sqlite(source, source)

    assert source.read_bytes() == canonical_bytes


def test_sqlite_projection_rejects_resolved_source_path_alias(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trade_memory.jsonl"
    canonical_bytes = b'{"canonical":"must-remain-unchanged"}\n'
    source.write_bytes(canonical_bytes)
    alias_directory = tmp_path / "alias"
    alias_directory.mkdir()
    resolved_alias = alias_directory / ".." / source.name

    with pytest.raises(ValueError, match="paths alias"):
        build_trade_memory_sqlite(source, resolved_alias)

    assert source.read_bytes() == canonical_bytes


def test_generation_publication_restores_prior_active_packet_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_paths = trade_memory_builder._packet_paths(tmp_path / "generation")
    stable_paths = trade_memory_builder._packet_paths(tmp_path / "active")
    new_bytes: dict[Path, bytes] = {}
    prior_bytes: dict[Path, bytes] = {}
    for index, path in enumerate(generation_paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        value = f"new-{index}".encode("utf-8")
        path.write_bytes(value)
        new_bytes[path] = value
    for index, path in enumerate(stable_paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        value = f"prior-{index}".encode("utf-8")
        path.write_bytes(value)
        prior_bytes[path] = value

    def controlled_validation(
        paths: trade_memory_builder.TradeMemoryPacketPaths,
    ) -> dict[str, object]:
        if paths == stable_paths:
            raise RuntimeError("injected active-packet validation failure")
        return {"packet_validation": "passed"}

    monkeypatch.setattr(
        trade_memory_builder,
        "_validate_packet",
        controlled_validation,
    )

    with pytest.raises(
        RuntimeError,
        match="injected active-packet validation failure",
    ):
        trade_memory_builder._publish_stable_packet(
            generation_paths,
            stable_paths,
        )

    assert all(path.read_bytes() == prior_bytes[path] for path in stable_paths)
    assert all(path.read_bytes() == new_bytes[path] for path in generation_paths)


def test_operator_build_publishes_valid_generation_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_directory = tmp_path / "trade_memory"
    monkeypatch.setattr(trade_memory_builder, "MEMORY_DIR", memory_directory)
    monkeypatch.setattr(
        trade_memory_builder,
        "INDEX_PATH",
        memory_directory / "trade_memory_index.jsonl",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "SQLITE_PATH",
        memory_directory / "trade_memory_index.sqlite3",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "INDEX_MANIFEST_PATH",
        memory_directory / "trade_memory_index_manifest.json",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "SUMMARY_PATH",
        memory_directory / "trade_memory_summary.json",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "GENERATIONS_DIR",
        memory_directory / "generations",
    )
    record = {
        "family": "mean_reversion",
        "strategy": "long_put",
        "direction": "bearish",
        "symbol": "A",
        "signal_date": "2020-03-01",
        "path_pnl": -0.3,
        "trade_return_model_units": -0.15,
        "win": False,
        "mfe": 0.1,
        "mae": -0.3,
        "exit_reason": "stop",
        "holding_steps": 2,
        "stretch": 0.1,
        "stretch_bucket": "stretched_above",
        "rvol": 0.5,
        "rvol_bucket": "high",
        "trailing_5d_return": 0.08,
    }
    monkeypatch.setattr(trade_memory_builder, "_spine_lookup", lambda: {})
    monkeypatch.setattr(
        trade_memory_builder,
        "resolve_default_backtest_trade_ledger",
        lambda: object(),
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "iter_verified_trade_records",
        lambda _resolution: iter((record, record)),
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "enrich_record",
        lambda raw_record, _spine: raw_record,
    )

    assert trade_memory_builder.main() == 0

    validation = trade_memory_builder._validate_packet(
        trade_memory_builder._stable_packet_paths()
    )
    assert validation["packet_validation"] == "passed"
    assert validation["row_count"] == 2
    assert validation["duplicate_content_row_count"] == 1
    generation_directories = list((memory_directory / "generations").iterdir())
    assert len(generation_directories) == 1
    active_packet = resolve_active_trade_memory_packet(memory_directory)
    assert active_packet.summary.parent == generation_directories[0]
    active_summary = load_active_trade_memory_summary(memory_directory)
    assert active_summary["indexed_trade_count"] == 2
    assert (memory_directory / ACTIVE_POINTER_NAME).is_file()


def test_active_generation_pointer_fails_closed_after_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_directory = tmp_path / "trade_memory"
    monkeypatch.setattr(trade_memory_builder, "MEMORY_DIR", memory_directory)
    monkeypatch.setattr(
        trade_memory_builder,
        "INDEX_PATH",
        memory_directory / "trade_memory_index.jsonl",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "SQLITE_PATH",
        memory_directory / "trade_memory_index.sqlite3",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "INDEX_MANIFEST_PATH",
        memory_directory / "trade_memory_index_manifest.json",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "SUMMARY_PATH",
        memory_directory / "trade_memory_summary.json",
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "GENERATIONS_DIR",
        memory_directory / "generations",
    )
    record = {
        "family": "mean_reversion",
        "strategy": "long_put",
        "direction": "bearish",
        "symbol": "A",
        "signal_date": "2020-03-01",
        "path_pnl": -0.3,
        "trade_return_model_units": -0.15,
        "win": False,
        "mfe": 0.1,
        "mae": -0.3,
        "exit_reason": "stop",
        "holding_steps": 2,
        "stretch": 0.1,
        "stretch_bucket": "stretched_above",
        "rvol": 0.5,
        "rvol_bucket": "high",
        "trailing_5d_return": 0.08,
    }
    monkeypatch.setattr(trade_memory_builder, "_spine_lookup", lambda: {})
    monkeypatch.setattr(
        trade_memory_builder,
        "resolve_default_backtest_trade_ledger",
        lambda: object(),
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "iter_verified_trade_records",
        lambda _resolution: iter((record,)),
    )
    monkeypatch.setattr(
        trade_memory_builder,
        "enrich_record",
        lambda raw_record, _spine: raw_record,
    )
    assert trade_memory_builder.main() == 0
    pointer_path = memory_directory / ACTIVE_POINTER_NAME
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["generation_id"] = "tampered"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact hash mismatch"):
        resolve_active_trade_memory_packet(memory_directory)
