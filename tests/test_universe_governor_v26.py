"""Tests: V26 self-governing universe (discovery / understanding / improvement).

The properties that matter: core is untouchable by machinery; promotion
requires a real staging proof; quarantine is mechanical-death-only and
reversible; discovery never invents evidence; the governor is offline and
recommend-only; consumers resolve the universe through the registry; and a
dead probation name can never freeze the spine's uniform advance.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE
from dopey_universe.discovery_engine import (
    MAX_CANDIDATES_PER_RUN,
    STAGING_QUEUE_LENGTH,
    build_staging_queue,
    discover_candidates,
)
from dopey_universe.run_universe_governor import (
    run_universe_governor,
)
from dopey_universe.symbol_dossier import build_dossiers
from dopey_universe.universe_registry import (
    MAX_ACTIVE_UNIVERSE_SIZE,
    MAX_PROBATION_SYMBOLS,
    UNIVERSE_CAPACITY_POLICY,
    active_universe,
    core_universe,
    load_registry,
    promote_to_probation,
    quarantine,
    record_candidate,
    save_registry,
    symbol_tier,
    tier_counts,
    unquarantine,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fresh() -> dict:
    return {"artifact_type": "universe_registry", "symbols": {}, "updated_utc": "", "paper_only": True, "live_blocked": True}


def _staging_proof() -> dict:
    return {
        "staged_rows": 5000,
        "staged_frontier": "2026-07-08",
        "options_available": True,
        "market_cap": 100_000_000_000.0,
        "fund_assets": 0.0,
        "instrument_type": "EQUITY",
        "capitalization_kind": "market_cap",
        "capitalization_value": 100_000_000_000.0,
        "adv_usd": 500_000_000.0,
        "research_tradable": True,
        "probe_observed_at_utc": "2026-07-08T20:00:00+00:00",
        "validator_status": "valid_real_dataset",
        "membership_evidence": {
            "policy_version": "dopey-evolving-universe-v1",
            "decision_time_utc": "2026-07-08T21:00:00+00:00",
            "evidence_hash": "a" * 64,
            "selection_score": 0.8,
            "rank": 1,
            "reason_codes": ["test_complete_evidence"],
        },
    }


# ---------------------------------------------------------------------------
# Registry tiers + governance invariants
# ---------------------------------------------------------------------------

def test_core_floor_is_the_code_universe() -> None:
    assert core_universe() == tuple(REQUIRED_HISTORY_UNIVERSE)
    assert len(core_universe()) == 37


def test_governed_universe_uses_evolving_cap_with_quarantine_headroom() -> None:
    assert UNIVERSE_CAPACITY_POLICY == "evolving_ranked_cap"
    assert MAX_ACTIVE_UNIVERSE_SIZE == 500
    assert len(core_universe()) + MAX_PROBATION_SYMBOLS == MAX_ACTIVE_UNIVERSE_SIZE
    assert MAX_CANDIDATES_PER_RUN >= MAX_ACTIVE_UNIVERSE_SIZE
    assert STAGING_QUEUE_LENGTH >= MAX_ACTIVE_UNIVERSE_SIZE


def test_core_symbols_can_never_become_candidates() -> None:
    registry = _fresh()
    registry = record_candidate(registry, "AAPL", "finra_market_activity_scan", {"why": "test"})
    assert "AAPL" not in registry["symbols"]
    assert symbol_tier("AAPL", registry) == "core"


def test_candidate_promotion_requires_full_staging_proof() -> None:
    registry = record_candidate(_fresh(), "FAKE", "fundamentals_watchlist_screen", {"why": "test"})
    registry = promote_to_probation(registry, "FAKE", {"staged_rows": 100})  # incomplete
    assert registry["symbols"]["FAKE"]["tier"] == "candidate"
    assert any("incomplete_staging_proof" in note for note in registry["symbols"]["FAKE"].get("notes", []))
    registry = promote_to_probation(registry, "FAKE", _staging_proof())
    assert registry["symbols"]["FAKE"]["tier"] == "probation"
    assert registry["symbols"]["FAKE"]["staging_proof"]["validator_status"] == "valid_real_dataset"


def test_probation_cap_defers_promotion() -> None:
    registry = _fresh()
    for index in range(MAX_PROBATION_SYMBOLS):
        symbol = f"CAP{index}"
        registry = record_candidate(registry, symbol, "test", {"why": "cap"})
        registry = promote_to_probation(registry, symbol, _staging_proof())
    registry = record_candidate(registry, "OVER", "test", {"why": "cap"})
    registry = promote_to_probation(registry, "OVER", _staging_proof())
    assert registry["symbols"]["OVER"]["tier"] == "candidate"
    assert any("universe_cap" in note for note in registry["symbols"]["OVER"].get("notes", []))


def test_quarantine_is_probation_only_and_reversible() -> None:
    registry = record_candidate(_fresh(), "DEAD", "test", {"why": "test"})
    registry = quarantine(registry, "DEAD", "fetch_failed")     # candidate: no-op
    assert registry["symbols"]["DEAD"]["tier"] == "candidate"
    registry = promote_to_probation(registry, "DEAD", _staging_proof())
    registry = quarantine(registry, "DEAD", "frontier_lag_4_sessions")
    assert registry["symbols"]["DEAD"]["tier"] == "quarantined"
    assert "DEAD" not in active_universe(registry)
    registry = unquarantine(registry, "DEAD", _staging_proof())
    assert registry["symbols"]["DEAD"]["tier"] == "standby"
    assert "DEAD" not in active_universe(registry)
    assert registry["symbols"]["DEAD"]["membership_history"][-1]["decision"] == (
        "staging_validated_awaiting_evolution_selection"
    )


def test_quarantine_requalification_requires_fresh_validator_proof() -> None:
    registry = record_candidate(_fresh(), "REQUAL", "test", {"why": "test"})
    registry = promote_to_probation(registry, "REQUAL", _staging_proof())
    registry = quarantine(registry, "REQUAL", "frontier_lag")
    registry = unquarantine(registry, "REQUAL", {"staged_rows": 5000})
    assert registry["symbols"]["REQUAL"]["tier"] == "quarantined"
    assert any(
        "staging_proof_refused_missing" in note
        for note in registry["symbols"]["REQUAL"].get("notes", [])
    )


def test_active_universe_is_floor_plus_probation_only() -> None:
    registry = _fresh()
    registry = record_candidate(registry, "CAND", "test", {"why": "candidate stays out"})
    registry = record_candidate(registry, "PROB", "test", {"why": "probation joins"})
    registry = promote_to_probation(registry, "PROB", _staging_proof())
    active = active_universe(registry)
    assert set(REQUIRED_HISTORY_UNIVERSE).issubset(active)
    assert "PROB" in active
    assert "CAND" not in active
    assert len(active) == len(REQUIRED_HISTORY_UNIVERSE) + 1


def test_rediscovery_of_staged_name_appends_evidence_not_demotes() -> None:
    registry = record_candidate(_fresh(), "SEEN", "test", {"why": "first"})
    registry = promote_to_probation(registry, "SEEN", _staging_proof())
    registry = record_candidate(registry, "SEEN", "finra_market_activity_scan", {"why": "again"})
    assert registry["symbols"]["SEEN"]["tier"] == "probation"
    assert len(registry["symbols"]["SEEN"]["discovery_log"]) >= 2


# ---------------------------------------------------------------------------
# Discovery honesty
# ---------------------------------------------------------------------------

def test_discovery_never_invents_candidates_without_lane_files() -> None:
    registry, discovered = discover_candidates(_fresh())
    # whatever the lane files say, every discovery carries evidence + source
    for entry in discovered:
        assert entry["discovered_by"] in {
            "fundamentals_watchlist_screen",
            "finra_market_activity_scan",
            "nasdaq_ipo_calendar",
            "protected_public_lake_inventory",
        }
        assert entry["why"]
        assert entry["evidence"]
        assert entry["symbol"] not in REQUIRED_HISTORY_UNIVERSE


def test_staging_queue_only_contains_unstaged_candidates() -> None:
    registry = _fresh()
    registry = record_candidate(registry, "QQ1", "test", {"why": "q"})
    registry = record_candidate(registry, "QQ2", "test", {"why": "q"})
    registry = promote_to_probation(registry, "QQ2", _staging_proof())
    discovered = [
        {"symbol": "QQ1", "discovery_score": 0.9, "discovered_by": "test", "why": "q", "evidence": {}},
        {"symbol": "QQ2", "discovery_score": 0.8, "discovered_by": "test", "why": "q", "evidence": {}},
    ]
    queue = build_staging_queue(registry, discovered)
    symbols = [entry["symbol"] for entry in queue]
    assert "QQ1" in symbols
    assert "QQ2" not in symbols  # already probation - never re-queued
    for entry in queue:
        assert "listed_options_available" not in entry["required_probes"]
        assert entry["optional_contract_probe"] == "listed_options_available"


def test_standby_returns_to_queue_for_metadata_requalification() -> None:
    registry = record_candidate(
        _fresh(),
        "RESTAGE",
        "test",
        {"why": "standby metadata refresh"},
    )
    registry = promote_to_probation(registry, "RESTAGE", _staging_proof())
    registry = quarantine(registry, "RESTAGE", "test_requalification")
    registry = unquarantine(registry, "RESTAGE", _staging_proof())

    queue = build_staging_queue(registry, [])

    entry = next(item for item in queue if item["symbol"] == "RESTAGE")
    assert entry["discovered_by"] == "standby_metadata_requalification_lane"
    assert entry["required_probes"] == [
        "equity_market_cap_floor_1e9_or_etf_assets_floor_250m",
        "adv_floor_5musd",
        "supported_research_instrument_type",
    ]


def test_standby_metadata_requalification_never_rewrites_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import operator_tools.operator_universe_ritual as ritual_module

    monkeypatch.setattr(ritual_module, "HISTORY_DIR", tmp_path)
    current_path = tmp_path / "CURRENT.csv"
    stale_path = tmp_path / "STALE.csv"
    header = ritual_module.CSV_HEADER
    current_lines = [header]
    stale_lines = [header]
    first_day = date(2026, 1, 1)
    for index in range(203):
        day = first_day + timedelta(days=index)
        row = f"{day.isoformat()},CURRENT,10,11,9,10,10,1000000,test"
        current_lines.append(row)
        stale_lines.append(row.replace(",CURRENT,", ",STALE,"))
    current_path.write_text("\n".join(current_lines) + "\n", encoding="utf-8")
    stale_path.write_text("\n".join(stale_lines[:-5]) + "\n", encoding="utf-8")
    current_before = current_path.read_bytes()
    stale_before = stale_path.read_bytes()

    current = ritual_module.reuse_validated_standby_history("CURRENT", "2026-07-22")
    stale = ritual_module.reuse_validated_standby_history("STALE", "2026-07-22")

    assert current == {
        "staged": True,
        "rows": 203,
        "frontier": "2026-07-22",
        "sha256": hashlib.sha256(current_before).hexdigest(),
        "source": "existing_governed_standby_history",
        "metadata_only_requalification": True,
    }
    assert stale["staged"] is False
    assert stale["reason"].startswith("standby_history_stale_")
    assert current_path.read_bytes() == current_before
    assert stale_path.read_bytes() == stale_before


# ---------------------------------------------------------------------------
# Understanding (dossiers) + improvement (recommend-only)
# ---------------------------------------------------------------------------

def test_dossiers_cover_every_active_symbol_with_provenance() -> None:
    registry, dossiers, _ = build_dossiers(load_registry())
    by_symbol = {dossier["symbol"]: dossier for dossier in dossiers}
    for symbol in active_universe(registry):
        assert symbol in by_symbol
        assert by_symbol[symbol]["why_in_universe"]
        assert by_symbol[symbol]["role"]
        assert by_symbol[symbol]["not_edge_evidence"] is True


def test_context_only_symbols_are_understood_not_flagged() -> None:
    registry, dossiers, recommendations = build_dossiers(load_registry())
    vix = next(dossier for dossier in dossiers if dossier["symbol"] == "VIX")
    assert vix["role"] == "context_only_volatility_index"
    assert not any(rec["symbol"] == "VIX" for rec in recommendations)


def test_improvement_is_recommend_only_never_auto_retires() -> None:
    registry, _, recommendations = build_dossiers(load_registry())
    for rec in recommendations:
        assert "human" in rec["action_required"]
    # and no registry tier was flipped to retired by the dossier pass
    assert all(record.get("tier") != "retired" for record in registry.get("symbols", {}).values())


# ---------------------------------------------------------------------------
# Governor runner artifacts + offline guarantee
# ---------------------------------------------------------------------------

def test_governor_writes_all_artifacts_and_stays_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dopey_universe.evolving_universe as evolution_module
    import dopey_universe.run_universe_governor as governor_module
    import dopey_universe.universe_registry as registry_module

    artifact_root = tmp_path / "universe"
    monkeypatch.setattr(registry_module, "UNIVERSE_ARTIFACT_DIR", artifact_root)
    monkeypatch.setattr(registry_module, "UNIVERSE_REGISTRY_PATH", artifact_root / "universe_registry.json")
    monkeypatch.setattr(governor_module, "UNIVERSE_ARTIFACT_DIR", artifact_root)
    monkeypatch.setattr(governor_module, "STAGING_QUEUE_PATH", artifact_root / "staging_queue.json")
    monkeypatch.setattr(governor_module, "UNIVERSE_SUMMARY_PATH", artifact_root / "universe_summary.json")
    monkeypatch.setattr(governor_module, "UNIVERSE_DOSSIERS_PATH", artifact_root / "symbol_dossiers.jsonl")
    monkeypatch.setattr(
        evolution_module,
        "EVOLVING_UNIVERSE_SUMMARY_PATH",
        artifact_root / "evolving_universe_summary.json",
    )
    summary = run_universe_governor()
    assert summary["universe_status"] == "universe_governed"
    assert summary["active_universe_size"] >= len(REQUIRED_HISTORY_UNIVERSE)
    assert summary["universe_capacity_policy"] == "evolving_ranked_cap"
    assert summary["maximum_active_universe_size"] == 500
    assert summary["available_active_slots"] >= 0
    assert isinstance(summary["evolution_status"], str)
    assert (artifact_root / "universe_summary.json").exists()
    assert (artifact_root / "staging_queue.json").exists()
    assert (artifact_root / "symbol_dossiers.jsonl").exists()
    assert summary["paper_only"] is True and summary["live_blocked"] is True
    assert summary["not_edge_evidence"] is True
    queue = json.loads((artifact_root / "staging_queue.json").read_text(encoding="utf-8"))
    assert "nothing is fetched" in queue["semantics"]


def test_governor_module_has_no_network_or_order_paths() -> None:
    text = "\n".join(
        (REPO_ROOT / "dopey_universe" / name).read_text(encoding="utf-8").lower()
        for name in ("run_universe_governor.py", "discovery_engine.py", "symbol_dossier.py", "universe_registry.py")
    )
    for forbidden in ("requests.", "yfinance", "urllib", "place_order", "broker", "sk-proj-", "apscheduler"):
        assert forbidden not in text


def test_supervisor_includes_universe_governor_stage() -> None:
    from dopey_autonomy.run_resilient_research_supervisor import STAGES

    names = [name for name, _, _ in STAGES]
    assert "universe_governor" in names
    assert len(names) == len(set(names))
    assert names[-1] == "action_readiness_gate"


def test_tier_counts_shape() -> None:
    counts = tier_counts(_fresh())
    assert counts["core"] == len(REQUIRED_HISTORY_UNIVERSE)
    assert set(counts) == {
        "core",
        "probation",
        "candidate",
        "standby",
        "quarantined",
        "retired",
    }


# ---------------------------------------------------------------------------
# Spine protection: the updater's tier-aware frontier
# ---------------------------------------------------------------------------

def test_updater_core_set_matches_required_universe() -> None:
    from operator_tools.operator_fetch_daily_ohlcv import _core_symbols

    assert _core_symbols() == frozenset(REQUIRED_HISTORY_UNIVERSE)


def test_updater_source_never_lets_noncore_hold_frontier() -> None:
    """The frontier computation must be restricted to CORE symbols and the
    non-core lag path must quarantine, not hold. Asserted on source structure
    (the network paths themselves are operator-lane, not unit-testable)."""
    text = (REPO_ROOT / "operator_tools" / "operator_fetch_daily_ohlcv.py").read_text(encoding="utf-8")
    assert "if symbol in core" in text
    assert "_quarantine_probation" in text
    assert "every CORE" in text


def test_registry_roundtrip_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dopey_universe.universe_registry as registry_module

    monkeypatch.setattr(registry_module, "UNIVERSE_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(registry_module, "UNIVERSE_ARTIFACT_DIR", tmp_path)
    registry = record_candidate(_fresh(), "PERSIST", "test", {"why": "roundtrip"})
    save_registry(registry)
    loaded = registry_module.load_registry()
    assert loaded["symbols"]["PERSIST"]["tier"] == "candidate"
    assert loaded["updated_utc"]
