"""Integration coverage for validated cross-sectional world-model enrichment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey.macro import credit as credit_module
from dopey.macro.credit import build_credit_proxy_evidence
from dopey.world_model.cross_section import build_cross_sectional_context
from dopey.world_model.enrichment import enrich_world_model
from dopey_equity_swing.market_structure import Bar
from tests.public_source_fixtures import write_empty_history_manifest


def _history(symbol: str, multiplier: float) -> list[Bar]:
    return [
        {
            "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
            "symbol": symbol,
            "open": 100.0 + multiplier * index,
            "high": 101.0 + multiplier * index,
            "low": 99.0 + multiplier * index,
            "close": 100.0 + multiplier * index,
            "adjusted_close": 100.0 + multiplier * index,
            "volume": 1_000_000,
            "source": "integration_test_only_not_readiness_evidence",
        }
        for index in range(84)
    ]


def test_cross_section_enriches_unknown_dimensions_without_claiming_readiness() -> None:
    symbols = ("SPY", "QQQ", "IWM", "DIA", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
    histories = {symbol: _history(symbol, 0.05 + index * 0.005) for index, symbol in enumerate(symbols)}
    proofs = {
        symbol: {"actual_sha256": f"hash-{symbol}", "paper_only": True, "live_blocked": True}
        for symbol in symbols
    }
    context = build_cross_sectional_context(histories, proofs, "2026-07-14T20:00:00+00:00", 20, 50, 60)
    unknown = {"state": "unknown", "probability": 0.0, "uncertainty": 1.0, "evidence_ids": [], "limitations": []}
    base = {
        "artifact_type": "shared_market_world_model",
        "world_model_version": "dopey-world-model-v1",
        "regimes": {
            "equity_trend": {**unknown, "state": "uptrend_supported"},
            "breadth": unknown,
            "sector_leadership": unknown,
            "correlation_structure": unknown,
            "market_fragility": unknown,
            "crowding": unknown,
        },
        "contradictions": ["symbol_technical_strength_lacks_validated_market_breadth_confirmation"],
        "evidence_ids": [],
        "paper_only": True,
        "live_blocked": True,
    }
    credit = {
        "paper_only": True,
        "live_blocked": True,
        "evidence_id": "credit:test",
        "values": {"state": "mixed_or_stable", "probability": 0.61},
    }
    enriched = enrich_world_model(base, context, {"es_positioning": {"noncomm_net_z_52w": 2.1}}, credit)

    assert context["validated_symbol_count"] == len(symbols)
    assert enriched["regimes"]["breadth"]["state"] != "unknown"
    assert enriched["regimes"]["sector_leadership"]["state"] == "ranked_validated_sector_etfs"
    assert enriched["regimes"]["correlation_structure"]["state"] != "unknown"
    assert enriched["regimes"]["crowding"]["state"] == "relative_positioning_extreme_positive_z"
    assert enriched["not_readiness_evidence"] is True
    assert enriched["paper_only"] is True and enriched["live_blocked"] is True


def test_credit_proxy_emits_typed_gap_when_required_histories_are_not_governed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_manifest = write_empty_history_manifest(tmp_path / "history")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    required_symbols = {"HYG", "IEF", "SHY"}
    manifest["data_files"] = [
        record
        for record in manifest["data_files"]
        if not required_symbols.intersection(str(symbol).upper() for symbol in record["symbols"])
    ]
    manifest["required_universe"] = [
        symbol
        for symbol in manifest["required_universe"]
        if str(symbol).upper() not in required_symbols
    ]
    manifest_path = tmp_path / "history_dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(credit_module, "HISTORY_MANIFEST_PATH", manifest_path)

    result = build_credit_proxy_evidence(
        "2026-07-14T21:00:00+00:00",
        "2026-07-14T20:00:00+00:00",
    )

    assert result["evidence_type"] == "credit_proxy_data_gap"
    assert result["evidence_status"] == "unavailable_missing_hash_pinned_history_symbols"
    assert result["values"]["state"] == "unknown"
    assert result["values"]["missing_symbols"] == ["HYG", "IEF", "SHY"]
    assert result["not_trade_decision"] is True
    assert result["not_readiness_evidence"] is True
    assert result["paper_only"] is True and result["live_blocked"] is True
