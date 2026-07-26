"""Smoke coverage for the governed 500-cap evolving research universe."""

from __future__ import annotations

import json
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE
from dopey_universe.evolving_universe import (
    evolve_registry,
    universe_evolution_policy,
)
from dopey_universe.universe_registry import (
    MAX_ACTIVE_UNIVERSE_SIZE,
    active_universe,
    promote_to_probation,
    record_candidate,
    record_staging_proof,
)


DECISION_TIME = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)


def _fresh_registry() -> dict:
    return {
        "artifact_type": "universe_registry",
        "symbols": {},
        "updated_utc": "",
        "paper_only": True,
        "live_blocked": True,
    }


def _staging_proof(market_cap: float) -> dict:
    return {
        "staged_rows": 500,
        "staged_frontier": "2026-07-22",
        "options_available": True,
        "validator_status": "valid_real_dataset",
        "market_cap": market_cap,
        "fund_assets": 0.0,
        "instrument_type": "EQUITY",
        "capitalization_kind": "market_cap",
        "capitalization_value": market_cap,
        "adv_usd": 100_000_000.0,
        "research_tradable": True,
        "probe_observed_at_utc": "2026-07-22T19:00:00+00:00",
    }


def _membership_proof() -> dict:
    return {
        "policy_version": "dopey-evolving-universe-v1",
        "decision_time_utc": "2026-07-22T19:30:00+00:00",
        "evidence_hash": "b" * 64,
        "selection_score": 0.8,
        "rank": 1,
        "reason_codes": ["fixture_active_membership"],
    }


def _registry_with_symbol(symbol: str, market_cap: float, active: bool) -> dict:
    registry = record_candidate(
        _fresh_registry(),
        symbol,
        "test_attention_discovery",
        {"why": "governed test symbol"},
    )
    registry = record_staging_proof(registry, symbol, _staging_proof(market_cap))
    if active:
        proof = _staging_proof(market_cap)
        proof["membership_evidence"] = _membership_proof()
        registry = promote_to_probation(registry, symbol, proof)
    return registry


def _merge_registries(*registries: dict) -> dict:
    merged = _fresh_registry()
    for registry in registries:
        merged["symbols"].update(registry["symbols"])
    return merged


def _write_history(history_root: Path, symbol: str, close: float, volume: int) -> None:
    history_root.mkdir(parents=True, exist_ok=True)
    first_day = date(2026, 7, 3)
    lines = ["date,symbol,open,high,low,close,adjusted_close,volume,source"]
    for index in range(20):
        day = first_day + timedelta(days=index)
        lines.append(
            f"{day.isoformat()},{symbol},{close},{close},{close},{close},{close},{volume},test"
        )
    (history_root / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_fundamentals(path: Path, symbol: str, market_cap: float) -> None:
    path.write_text(
        "date,symbol,market_cap\n"
        f"2026-07-22,{symbol},{market_cap}\n",
        encoding="utf-8",
    )


def _attention_record(symbol: str, score: float) -> dict[str, object]:
    record: dict[str, object] = {
        "symbol": symbol,
        "status": "scored",
        "attention_score": score,
        "completeness_ratio": 1.0,
        "latest_evidence_at_utc": "2026-07-22T19:45:00+00:00",
        "latest_market_evidence_date": "2026-07-22",
        "provenance_sha256": "",
    }
    record["provenance_sha256"] = hashlib.sha256(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return record


def _attention_snapshot(records: list[dict[str, object]]) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "schema_version": "dopey-attention-snapshot-v1",
        "engine_version": "dopey-attention-engine-v1",
        "generated_at_utc": "2026-07-22T19:50:00+00:00",
        "decision_time_utc": "2026-07-22T20:00:00+00:00",
        "status": "scored",
        "symbol_count": len(records),
        "symbols": records,
        "source_provenance": [],
        "missing_sources": [],
        "research_only": True,
        "research_priority_only": True,
        "live_execution_allowed": False,
        "trade_promotion_allowed": False,
        "future_observation_consumed": False,
        "directional_signal_allowed": False,
        "directional_bias": None,
        "snapshot_sha256": "",
    }
    snapshot["snapshot_sha256"] = hashlib.sha256(
        json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return snapshot


def test_evolving_universe_cap_is_500() -> None:
    assert MAX_ACTIVE_UNIVERSE_SIZE == 500
    assert universe_evolution_policy()["maximum_active_universe_size"] == 500


def test_membership_refresh_has_no_network_broker_or_order_surface() -> None:
    repository_root = Path(__file__).resolve().parent.parent
    source = "\n".join(
        (repository_root / "dopey_universe" / name).read_text(encoding="utf-8").lower()
        for name in ("evolving_universe.py", "run_membership_refresh.py")
    )
    for forbidden in (
        "requests.",
        "yfinance",
        "urllib",
        "place_order",
        "dopey_live",
        "robinhood",
    ):
        assert forbidden not in source


def test_complete_ranked_candidate_promotes_and_keeps_membership_reason_history(
    tmp_path: Path,
) -> None:
    symbol = "PROMO"
    history_root = tmp_path / "history"
    _write_history(history_root, symbol, 100.0, 1_000_000)
    registry = _registry_with_symbol(symbol, 100_000_000_000.0, False)
    attention = _attention_record(symbol, 0.90)
    attention["latest_evidence_at_utc"] = ""
    attention["provenance_sha256"] = ""
    attention["provenance_sha256"] = hashlib.sha256(
        json.dumps(
            attention,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    evolved, summary = evolve_registry(
        registry,
        _attention_snapshot([attention]),
        history_root,
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert summary["status"] == "evolved"
    assert summary["promoted_symbols"] == [symbol]
    assert evolved["symbols"][symbol]["tier"] == "probation"
    assert symbol in active_universe(evolved)
    history = evolved["symbols"][symbol]["membership_history"]
    assert history[-1]["decision"] == "promoted_to_active_research"
    assert history[-1]["reason_codes"] == [
        "attention_evidence_current",
        "average_dollar_volume_floor_passed",
        "capitalization_floor_passed",
        "research_tradability_passed",
        "ranked_selection_score_passed",
    ]


def test_low_attention_active_symbol_demotes_to_standby_without_deleting_proof(
    tmp_path: Path,
) -> None:
    symbol = "LOWATTN"
    history_root = tmp_path / "history"
    _write_history(history_root, symbol, 10.0, 600_000)
    registry = _registry_with_symbol(symbol, 2_000_000_000.0, True)
    staging_before = dict(registry["symbols"][symbol]["staging_proof"])

    evolved, summary = evolve_registry(
        registry,
        _attention_snapshot([_attention_record(symbol, 0.0)]),
        history_root,
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert summary["demoted_symbols"] == [symbol]
    assert evolved["symbols"][symbol]["tier"] == "standby"
    assert symbol not in active_universe(evolved)
    assert evolved["symbols"][symbol]["staging_proof"] == staging_before
    assert "attention_score_below_tier_threshold" in evolved["symbols"][symbol][
        "demotion_reason_codes"
    ]


def test_retention_refresh_reports_registry_update_without_composition_change(
    tmp_path: Path,
) -> None:
    symbol = "RETAIN"
    history_root = tmp_path / "history"
    _write_history(history_root, symbol, 100.0, 1_000_000)
    registry = _registry_with_symbol(symbol, 100_000_000_000.0, True)

    evolved, summary = evolve_registry(
        registry,
        _attention_snapshot([_attention_record(symbol, 0.90)]),
        history_root,
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert evolved != registry
    assert summary["retained_symbols"] == [symbol]
    assert summary["registry_mutated"] is True
    assert summary["membership_composition_changed"] is False


def test_missing_active_attention_aborts_entire_membership_transaction(
    tmp_path: Path,
) -> None:
    symbol = "ACTIVE"
    history_root = tmp_path / "history"
    _write_history(history_root, symbol, 100.0, 1_000_000)
    registry = _registry_with_symbol(symbol, 100_000_000_000.0, True)

    evolved, summary = evolve_registry(
        registry,
        _attention_snapshot([]),
        history_root,
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert summary["status"] == "blocked_active_membership_evidence_incomplete"
    assert summary["registry_mutated"] is False
    assert evolved == registry
    assert summary["blocked_symbols"][0]["reason_codes"] == ["missing_attention_record"]


def test_attention_hash_mismatch_blocks_without_registry_mutation(tmp_path: Path) -> None:
    registry = _fresh_registry()
    snapshot = _attention_snapshot([_attention_record("AAPL", 0.8)])
    snapshot["symbols"][0]["attention_score"] = 0.9

    evolved, summary = evolve_registry(
        registry,
        snapshot,
        tmp_path / "history",
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert evolved == registry
    assert summary["status"] == "blocked_invalid_attention_snapshot"
    assert summary["registry_mutated"] is False
    assert "SHA-256 mismatch" in summary["error"]


def test_capacity_rank_promotes_only_the_highest_scored_candidate(tmp_path: Path) -> None:
    history_root = tmp_path / "history"
    for symbol in ("HIGH", "SECOND"):
        _write_history(history_root, symbol, 100.0, 1_000_000)
    registry = _merge_registries(
        _registry_with_symbol("HIGH", 100_000_000_000.0, False),
        _registry_with_symbol("SECOND", 100_000_000_000.0, False),
    )
    policy = universe_evolution_policy()
    policy["maximum_active_universe_size"] = len(REQUIRED_HISTORY_UNIVERSE) + 1

    evolved, summary = evolve_registry(
        registry,
        _attention_snapshot(
            [_attention_record("HIGH", 0.95), _attention_record("SECOND", 0.80)]
        ),
        history_root,
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        policy,
    )

    assert summary["promoted_symbols"] == ["HIGH"]
    assert evolved["symbols"]["HIGH"]["tier"] == "probation"
    assert evolved["symbols"]["SECOND"]["tier"] == "standby"
    second = next(
        item for item in summary["blocked_symbols"] if item["symbol"] == "SECOND"
    )
    assert second["reason_codes"] == ["outside_maximum_active_universe_rank"]


def test_etf_uses_fund_assets_instead_of_fabricated_market_cap(tmp_path: Path) -> None:
    symbol = "FUNDX"
    history_root = tmp_path / "history"
    _write_history(history_root, symbol, 50.0, 2_000_000)
    registry = record_candidate(
        _fresh_registry(),
        symbol,
        "test_etf_discovery",
        {"why": "governed ETF candidate"},
    )
    proof = _staging_proof(0.0)
    proof.update(
        {
            "instrument_type": "ETF",
            "fund_assets": 5_000_000_000.0,
            "capitalization_kind": "fund_assets",
            "capitalization_value": 5_000_000_000.0,
        }
    )
    registry = record_staging_proof(registry, symbol, proof)

    evolved, summary = evolve_registry(
        registry,
        _attention_snapshot([_attention_record(symbol, 0.90)]),
        history_root,
        tmp_path / "fundamentals.csv",
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert summary["promoted_symbols"] == [symbol]
    member = next(item for item in summary["ranked_members"] if item["symbol"] == symbol)
    assert member["market_cap"] == 0.0
    assert member["fund_assets"] == 5_000_000_000.0
    assert member["capitalization_kind"] == "fund_assets"
    assert evolved["symbols"][symbol]["tier"] == "probation"


def test_ranked_members_include_full_immutable_core_with_evaluated_evidence(
    tmp_path: Path,
) -> None:
    history_root = tmp_path / "history"
    fundamentals_path = tmp_path / "fundamentals.csv"
    _write_history(history_root, "AAPL", 200.0, 2_000_000)
    _write_fundamentals(fundamentals_path, "AAPL", 3_000_000_000_000.0)

    evolved, summary = evolve_registry(
        _fresh_registry(),
        _attention_snapshot([_attention_record("AAPL", 0.95)]),
        history_root,
        fundamentals_path,
        DECISION_TIME,
        universe_evolution_policy(),
    )

    assert evolved == _fresh_registry()
    assert summary["active_after"] == len(REQUIRED_HISTORY_UNIVERSE)
    assert summary["ranked_member_count"] == summary["active_after"]
    assert summary["full_active_set_ranked"] is True
    aapl = next(item for item in summary["ranked_members"] if item["symbol"] == "AAPL")
    assert aapl["prior_tier"] == "core"
    assert aapl["resulting_tier"] == "core"
    assert aapl["market_cap"] == 3_000_000_000_000.0
    assert aapl["research_tradable"] is True
    assert aapl["research_priority_score"] is not None
    assert "immutable_core_membership" in aapl["reason_codes"]


def test_canonical_membership_refresh_persists_only_membership_and_refreshes_dossier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dopey_universe.evolving_universe as evolution_module
    import dopey_universe.symbol_dossier as dossier_module
    import dopey_universe.universe_registry as registry_module

    symbol = "PROMO"
    history_root = tmp_path / "history"
    artifact_root = tmp_path / "universe"
    attention_path = tmp_path / "attention_snapshot.json"
    _write_history(history_root, symbol, 100.0, 1_000_000)
    attention_path.write_text(
        json.dumps(_attention_snapshot([_attention_record(symbol, 0.95)])),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry_module, "UNIVERSE_ARTIFACT_DIR", artifact_root)
    monkeypatch.setattr(
        registry_module,
        "UNIVERSE_REGISTRY_PATH",
        artifact_root / "universe_registry.json",
    )
    monkeypatch.setattr(evolution_module, "ATTENTION_SNAPSHOT_PATH", attention_path)
    monkeypatch.setattr(evolution_module, "HISTORY_RAW_DIR", history_root)
    monkeypatch.setattr(
        evolution_module,
        "FUNDAMENTALS_PATH",
        tmp_path / "fundamentals.csv",
    )
    monkeypatch.setattr(
        evolution_module,
        "EVOLVING_UNIVERSE_SUMMARY_PATH",
        artifact_root / "evolving_universe_summary.json",
    )
    monkeypatch.setattr(
        evolution_module,
        "UNIVERSE_DOSSIERS_PATH",
        artifact_root / "symbol_dossiers.jsonl",
    )
    monkeypatch.setattr(dossier_module, "HISTORY_RAW_DIR", history_root)
    registry = _registry_with_symbol(symbol, 100_000_000_000.0, False)
    discovery_log_count = len(registry["symbols"][symbol]["discovery_log"])
    registry_module.save_registry(registry)

    summary = evolution_module.refresh_evolving_universe_membership(DECISION_TIME)

    persisted = registry_module.load_registry()
    dossiers = [
        json.loads(line)
        for line in (artifact_root / "symbol_dossiers.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    promoted_dossier = next(item for item in dossiers if item["symbol"] == symbol)
    assert summary["status"] == "evolved"
    assert summary["registry_persisted"] is True
    assert summary["dossiers_refreshed"] is True
    assert summary["membership_refresh_scope"] == "membership_only_no_discovery"
    assert persisted["symbols"][symbol]["tier"] == "probation"
    assert len(persisted["symbols"][symbol]["discovery_log"]) == discovery_log_count
    assert promoted_dossier["role"] == "discovered_probation"
