"""Tests: DOPEY accelerated offline edge bundle.

All tests are deterministic, offline, fixture-only, paper-only, and live-blocked.
"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest

from dopey_analysis.analysis_fusion import fuse_analysis
from dopey_analysis.models import FundamentalContext, MacroContext, MicrostructureContext, PatternSignal, TechnicalContext
from dopey_analysis.pattern_fixture_library import REQUIRED_PATTERN_TYPES, build_pattern_fixture_library
from dopey_analysis.pattern_scorecard import score_pattern_context, score_pattern_fixture
from dopey_core.config import default_config_path, load_config
from dopey_data.source_candidate import SourceCandidate
from dopey_data.source_registry import build_data_inflow_registry
from dopey_data.source_value_ranker import rank_source_candidates, source_scorecard_summary
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_strategy_lab.evolution_tournament import (
    ALLOWED_MUTATION_DECISIONS,
    FORBIDDEN_MUTATION_DECISIONS,
    mutation_score_adjustment,
    run_offline_mutation_tournament,
)
from dopey_strategy_lab.genome_mutation import build_mutation_batch
from dopey_strategy_lab.mutation_policy import MUTATION_TYPES, build_mutation_instructions
from dopey_strategy_lab.strategy_genome import StrategyGenome
from dopey_tournament.aggression_tournament import ALLOWED_TARGETS, FORBIDDEN_LIVE_TARGETS
from dopey_tournament.genome_set import build_tournament_genomes
from dopey_tournament.runner import run_fixture_tournament


@pytest.fixture(scope="module")
def mutation_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("mutation_bundle")
    return run_offline_mutation_tournament(
        proof_ledger_path=root / "mutation_ledger.jsonl",
        mutation_registry_path=root / "mutation_registry.jsonl",
    )


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="accelerated-live-x",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
             "option_type": "call", "mid": 1.0},
            {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19",
             "option_type": "call", "mid": 0.5},
        ],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )


def test_source_candidate_serializes_deterministically() -> None:
    candidate = SourceCandidate(
        source_id="fixture",
        source_name="Fixture",
        source_type="offline_fixture",
        intended_use="unit test",
        asset_scope="dopey_internal",
        latency_class="offline_batch",
        freshness_class="fixture_current",
        license_status="owned_internal",
        credential_required=False,
        network_required=False,
        allowed_in_current_pass=True,
        risk_notes="none",
        expected_edge_contribution="fixture context",
    )
    assert json.dumps(candidate.to_dict(), sort_keys=True) == json.dumps(
        SourceCandidate.from_dict(candidate.to_dict()).to_dict(),
        sort_keys=True,
    )


def test_source_ranker_promotes_only_offline_internal_sources() -> None:
    rows = rank_source_candidates()
    promoted = [row for row in rows if row["scorecard"]["status"] == "promoted_for_fixture_research"]
    assert promoted
    for row in promoted:
        candidate = row["candidate"]
        assert candidate["network_required"] is False
        assert candidate["credential_required"] is False
        assert candidate["source_type"] in {"internal_artifact", "offline_fixture", "derived_fixture_metric"}


def test_source_ranker_defers_network_or_credential_sources() -> None:
    rows = rank_source_candidates()
    for row in rows:
        candidate = row["candidate"]
        status = row["scorecard"]["status"]
        if candidate["credential_required"]:
            assert status == "deferred_requires_credentials"
        elif candidate["network_required"]:
            assert status == "deferred_requires_network"


def test_source_registry_records_fixture_and_proofledger_sources() -> None:
    registry = build_data_inflow_registry().to_dict()
    promoted = set(registry["summary"]["promoted_source_ids"])
    assert "proofledger_internal" in promoted
    assert "champion_registry_internal" in promoted
    assert "pattern_fixture_corpus_internal" in promoted


def test_source_scorecard_does_not_fetch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    summary = source_scorecard_summary()
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_used"] is False


def test_pattern_fixture_library_loads() -> None:
    fixtures = build_pattern_fixture_library()
    assert len(fixtures) == 16
    assert all(f.pattern_id for f in fixtures)


def test_pattern_fixture_types_cover_required_patterns() -> None:
    types = {fixture.pattern_type for fixture in build_pattern_fixture_library()}
    assert set(REQUIRED_PATTERN_TYPES).issubset(types)


def test_pattern_scorecard_rewards_matching_strategy_family() -> None:
    fixture = next(
        f for f in build_pattern_fixture_library()
        if f.pattern_type == "volatility_expansion_setup"
    )
    matching = score_pattern_fixture(fixture, "volatility_expansion", "event_vol_expansion")
    penalized = score_pattern_fixture(fixture, "volatility_compression", "event_vol_expansion")
    assert matching.overall_score > penalized.overall_score
    assert matching.status == "supports_family"


def test_pattern_scorecard_penalizes_known_failure_mode() -> None:
    fixture = next(f for f in build_pattern_fixture_library() if f.pattern_type == "range_pin")
    clean = score_pattern_fixture(fixture, "volatility_compression", "range_bound_pin")
    failed = score_pattern_fixture(
        fixture,
        "volatility_compression",
        "range_bound_pin",
        active_failure_modes=[fixture.failure_mode],
    )
    assert failed.overall_score < clean.overall_score


def test_analysis_fusion_changes_when_pattern_context_changes() -> None:
    macro = MacroContext(risk_on_score=0.6)
    micro = MicrostructureContext(liquidity_score=0.6)
    technical = TechnicalContext(trend_score=0.6)
    fundamental = FundamentalContext(growth_quality_score=0.6)
    patterns = [PatternSignal(pattern_id="p", confidence=0.6)]
    strong = fuse_analysis(
        macro_ctx=macro,
        micro_ctx=micro,
        tech_ctx=technical,
        fund_ctx=fundamental,
        patterns=patterns,
        pattern_fixture_score=0.90,
    )
    weak = fuse_analysis(
        macro_ctx=macro,
        micro_ctx=micro,
        tech_ctx=technical,
        fund_ctx=fundamental,
        patterns=patterns,
        pattern_fixture_score=0.10,
    )
    assert strong.overall_score > weak.overall_score


def test_mutation_batch_is_deterministic() -> None:
    parents = [build_tournament_genomes()[0]]
    instructions = build_mutation_instructions()
    first = build_mutation_batch(parents, instructions).to_dict()
    second = build_mutation_batch(parents, instructions).to_dict()
    assert first == second
    assert len(first["mutations"]) == len(MUTATION_TYPES)


def test_mutations_preserve_live_allowed_false() -> None:
    batch = build_mutation_batch([build_tournament_genomes()[0]], build_mutation_instructions())
    assert all(mutation.genome.live_allowed is False for mutation in batch.mutations)


def test_mutations_do_not_create_undefined_risk_selling() -> None:
    batch = build_mutation_batch([build_tournament_genomes()[0]], build_mutation_instructions())
    for mutation in batch.mutations:
        assert mutation.genome.defined_risk_only is True
        assert mutation.genome.parameters["structure_risk"] == "defined"
        assert "naked" not in json.dumps(mutation.genome.to_dict()).lower()


def test_mutated_genomes_remain_paper_only() -> None:
    batch = build_mutation_batch([build_tournament_genomes()[0]], build_mutation_instructions())
    for mutation in batch.mutations:
        data = mutation.genome.to_dict()
        assert data["live_allowed"] is False
        assert data["parameters"]["promotion_tier"] in {"research_only", "paper_candidate"}


def test_mutation_tournament_ranks_parent_and_children(mutation_result: dict) -> None:
    ranking = mutation_result["ranking"]
    assert any(row["mutation_type"] == "parent" for row in ranking)
    assert any(row["mutation_type"] != "parent" for row in ranking)
    scores = [row["combined_score"] for row in ranking]
    assert scores == sorted(scores, reverse=True)


def test_mutation_registry_records_best_and_rejected_mutations(mutation_result: dict) -> None:
    registry_path = Path(mutation_result["mutation_registry_path"])
    record = json.loads(registry_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["best_mutated_strategy_id"] == mutation_result["best_mutated_strategy_id"]
    assert "rejected" in record["promotion_decisions"].values()


def test_mutation_proof_ledger_record_written(mutation_result: dict) -> None:
    ledger_path = Path(mutation_result["proof_record_path"])
    record = json.loads(ledger_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["task_id"] == "offline-mutation-tournament"
    execution = record["execution_result"]
    assert execution["mutation_batch"]["batch_id"] == mutation_result["batch_id"]
    assert execution["best_mutation"] == mutation_result["best_mutated_strategy_id"]
    assert execution["source_registry_snapshot"]["network_fetch_performed"] is False


def test_offline_mutation_champion_cannot_promote_live(mutation_result: dict) -> None:
    decisions = set(mutation_result["promotion_decisions"].values())
    assert decisions.issubset(ALLOWED_MUTATION_DECISIONS)
    assert decisions.isdisjoint(FORBIDDEN_MUTATION_DECISIONS)
    assert "offline_mutation_champion" in decisions


def test_mutation_score_changes_with_delta_or_liquidity_threshold() -> None:
    genome = StrategyGenome(
        genome_id="g",
        family="directional_convexity",
        defined_risk_only=True,
        live_allowed=False,
        parameters={"delta_preference": 0.58, "liquidity_threshold": 0.45, "structure_risk": "defined"},
    )
    inputs = {
        "avg_liquidity_score": 0.60,
        "avg_expected_slippage_pct": 0.04,
        "avg_pattern_fixture_score": 0.60,
        "invalidation_quality": 0.70,
        "average_theta_fit_score": 0.80,
        "average_vega_fit_score": 0.80,
        "overfit_level": "low",
    }
    base = mutation_score_adjustment(StrategyGenome("base", "directional_convexity"), inputs)
    adjusted = mutation_score_adjustment(genome, inputs)
    assert adjusted > base


def test_overfit_penalty_applies_to_mutated_overfit_candidate() -> None:
    genome = StrategyGenome(
        genome_id="g",
        family="volatility_expansion",
        defined_risk_only=True,
        live_allowed=False,
        parameters={"overfit_penalty": 0.12, "structure_risk": "defined"},
    )
    inputs = {
        "avg_liquidity_score": 0.60,
        "avg_expected_slippage_pct": 0.04,
        "avg_pattern_fixture_score": 0.60,
        "invalidation_quality": 0.70,
        "average_theta_fit_score": 0.80,
        "average_vega_fit_score": 0.80,
        "overfit_level": "high",
    }
    assert mutation_score_adjustment(genome, inputs) <= -0.12


def test_no_live_promotion_possible_after_accelerated_bundle(tmp_path: Path) -> None:
    summary = run_fixture_tournament(
        proof_ledger_path=tmp_path / "ledger.jsonl",
        champion_registry_path=tmp_path / "registry.jsonl",
    )
    for decision in summary["promotion_decisions"].values():
        assert decision in ALLOWED_TARGETS
        assert decision not in FORBIDDEN_LIVE_TARGETS
        assert "live" not in decision
    assert summary["live_blocked"] is True


def test_live_stubs_still_block_after_accelerated_bundle() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_accelerated_bundle() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_accelerated_bundle(mutation_result: dict) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert mutation_result["safety_state"]["live_blocked"] is True


def test_blunder_source_integrity_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping integrity check")
    bad = 0
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        expected, path = parts
        candidate = Path(path)
        if not candidate.exists():
            continue
        checked += 1
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
        if actual != expected.strip().upper():
            bad += 1
    assert checked > 0, "no Blunder files were checked (manifest paths unresolved)"
    assert bad == 0, f"{bad} Blunder source file(s) changed since baseline (checked {checked})"
