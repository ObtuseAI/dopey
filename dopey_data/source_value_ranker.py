"""Offline source-value ranking for future DOPEY data inflow.

No candidate in this module is fetched. The ranker only scores metadata and promotes internal
fixture/proof artifacts that are already local and allowed in the current research pass.
"""
from __future__ import annotations

from .source_candidate import (
    SourceCandidate,
    SourceContributionHypothesis,
    SourcePromotionDecision,
)
from .source_scorecard import SourceScorecard


SOURCE_SCORECARD_VERSION = "dopey-source-scorecard-v1"

PROMOTED_STATUS = "promoted_for_fixture_research"
DEFERRED_CREDENTIAL_STATUS = "deferred_requires_credentials"
DEFERRED_NETWORK_STATUS = "deferred_requires_network"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def seed_source_candidates() -> list[SourceCandidate]:
    """Return the deterministic offline candidate list. No source is fetched."""
    return [
        SourceCandidate("openbb", "OpenBB", "external_market_data", "future broad market research",
                        "multi_asset", "delayed_or_batch", "fresh_when_connected", "review_required",
                        False, True, False, "network fetch deferred", "broad data integration candidate"),
        SourceCandidate("sec_edgar", "SEC/EDGAR filings", "official_filing_source",
                        "future filing/fundamental context", "equity", "batch", "event_driven",
                        "official_public", False, True, False, "network fetch deferred",
                        "fundamental event and filing context"),
        SourceCandidate("earnings_calendar", "earnings calendar", "external_event_calendar",
                        "future earnings/event risk", "equity", "daily_batch", "scheduled",
                        "license_review_required", False, True, False, "network fetch deferred",
                        "event-risk timing context"),
        SourceCandidate("macro_calendar", "macro calendar", "external_event_calendar",
                        "future CPI/FOMC/macro event risk", "macro", "daily_batch", "scheduled",
                        "license_review_required", False, True, False, "network fetch deferred",
                        "macro shock timing context"),
        SourceCandidate("vix_vvix", "VIX/VVIX", "external_volatility_index",
                        "future volatility regime context", "index_volatility", "near_realtime",
                        "fresh_when_connected", "license_review_required", False, True, False,
                        "network fetch deferred", "vol regime and crush/expansion context"),
        SourceCandidate("realized_volatility", "realized volatility", "derived_fixture_metric",
                        "offline realized-vol fixture enrichment", "equity_options", "offline_batch",
                        "fixture_current", "internal", False, False, True, "local fixture math only",
                        "volatility regime feature"),
        SourceCandidate("options_chain_provider_placeholder", "options chain provider placeholder",
                        "external_options_chain", "future option-chain enrichment", "equity_options",
                        "near_realtime", "fresh_when_connected", "license_review_required",
                        True, True, False, "requires licensed provider credentials",
                        "chain depth and Greeks calibration candidate"),
        SourceCandidate("iv_surface_provider_placeholder", "IV surface provider placeholder",
                        "external_iv_surface", "future IV surface calibration", "equity_options",
                        "near_realtime", "fresh_when_connected", "license_review_required",
                        True, True, False, "requires licensed provider credentials",
                        "surface/skew/term calibration candidate"),
        SourceCandidate("unusual_options_activity", "unusual options activity if licensed",
                        "external_options_flow", "future flow anomaly context", "equity_options",
                        "near_realtime", "fresh_when_connected", "license_review_required",
                        True, True, False, "legal/license review and credentials required",
                        "flow anomaly candidate"),
        SourceCandidate("alpaca_options_data", "Alpaca options data", "broker_data",
                        "future sandbox/market-data research", "equity_options", "near_realtime",
                        "fresh_when_connected", "broker_terms", True, True, False,
                        "requires credentials; no broker connection in this pass",
                        "broker-supported options data candidate"),
        SourceCandidate("tradier_options_data", "Tradier options data", "broker_data",
                        "future options market-data research", "equity_options", "near_realtime",
                        "fresh_when_connected", "broker_terms", True, True, False,
                        "requires credentials; no broker connection in this pass",
                        "broker-supported options data candidate"),
        SourceCandidate("robinhood_mcp_discovery", "Robinhood MCP account/tool discovery",
                        "broker_discovery", "future capability discovery only", "account_options",
                        "operator_gated", "fresh_when_authorized", "broker_terms", True, True,
                        False, "credentials and account authorization required; execution remains blocked",
                        "capability discovery candidate only"),
        SourceCandidate("broker_fill_history_future", "broker fill history future source",
                        "broker_history", "future realized fill-quality attribution", "account_options",
                        "batch", "historical", "broker_terms", True, True, False,
                        "requires credentials and account history; deferred", "fill-quality calibration candidate"),
        SourceCandidate("proofledger_internal", "ProofLedger internal outcome source",
                        "internal_artifact", "offline outcome/proof analysis", "dopey_internal",
                        "offline_batch", "current_local", "owned_internal", False, False, True,
                        "local append-only proof artifact", "validated internal outcome source"),
        SourceCandidate("champion_registry_internal", "champion registry internal source",
                        "internal_artifact", "offline champion lineage analysis", "dopey_internal",
                        "offline_batch", "current_local", "owned_internal", False, False, True,
                        "local champion registry artifact", "strategy lineage source"),
        SourceCandidate("pattern_fixture_corpus_internal", "pattern fixture corpus internal source",
                        "offline_fixture", "offline pattern-recognition fixture enrichment",
                        "dopey_internal", "offline_batch", "fixture_current", "owned_internal",
                        False, False, True, "fixture-only pattern corpus",
                        "pattern scoring and mutation context"),
    ]


def contribution_hypothesis(candidate: SourceCandidate) -> SourceContributionHypothesis:
    target_map = {
        "internal_artifact": ["proof_ledger", "tournament", "mutation"],
        "offline_fixture": ["analysis_fusion", "pattern_recognition", "mutation"],
        "derived_fixture_metric": ["walk_forward", "greeks_iv", "analysis_fusion"],
        "external_options_chain": ["options", "greeks_iv"],
        "external_iv_surface": ["greeks_iv", "analysis_fusion"],
        "broker_data": ["execution_quality"],
    }
    targets = target_map.get(candidate.source_type, ["future_research"])
    lift = 0.75 if candidate.allowed_in_current_pass else 0.45
    confidence = 0.85 if not candidate.network_required and not candidate.credential_required else 0.35
    return SourceContributionHypothesis(
        source_id=candidate.source_id,
        contribution_type=candidate.expected_edge_contribution,
        target_layers=targets,
        expected_lift_score=round(lift, 6),
        confidence=round(confidence, 6),
        notes="offline hypothesis only; no fetch performed",
    )


def score_source_candidate(candidate: SourceCandidate) -> tuple[SourceScorecard, SourcePromotionDecision]:
    if candidate.credential_required:
        status = DEFERRED_CREDENTIAL_STATUS
    elif candidate.network_required:
        status = DEFERRED_NETWORK_STATUS
    elif candidate.allowed_in_current_pass and candidate.source_type in {
        "internal_artifact", "offline_fixture", "derived_fixture_metric"
    }:
        status = PROMOTED_STATUS
    elif candidate.allowed_in_current_pass:
        status = "candidate"
    else:
        status = "research_later"

    freshness = 0.85 if candidate.freshness_class in {"current_local", "fixture_current"} else 0.45
    reliability = 0.90 if candidate.license_status in {"owned_internal", "internal", "official_public"} else 0.55
    latency = 0.90 if candidate.latency_class == "offline_batch" else 0.50
    coverage = 0.80 if candidate.asset_scope in {"dopey_internal", "equity_options", "multi_asset"} else 0.60
    ontology = 0.90 if candidate.source_type in {
        "internal_artifact", "offline_fixture", "derived_fixture_metric"
    } else 0.55
    edge = contribution_hypothesis(candidate).expected_lift_score
    complexity = 0.90 if not candidate.network_required and not candidate.credential_required else 0.25
    compliance = 0.95 if not candidate.credential_required and candidate.license_status in {
        "owned_internal", "internal", "official_public"
    } else 0.35
    paper_value = 0.90 if status == PROMOTED_STATUS else (0.45 if status.startswith("deferred") else 0.60)
    overall = _clamp(
        0.12 * freshness
        + 0.14 * reliability
        + 0.10 * latency
        + 0.10 * coverage
        + 0.14 * ontology
        + 0.15 * edge
        + 0.10 * complexity
        + 0.10 * compliance
        + 0.05 * paper_value,
        0.0,
        1.0,
    )
    scorecard = SourceScorecard(
        source_id=candidate.source_id,
        freshness_score=round(freshness, 6),
        reliability_score=round(reliability, 6),
        latency_score=round(latency, 6),
        coverage_score=round(coverage, 6),
        ontology_fit_score=round(ontology, 6),
        edge_contribution_score=round(edge, 6),
        cost_complexity_score=round(complexity, 6),
        compliance_score=round(compliance, 6),
        paper_research_value_score=round(paper_value, 6),
        overall_score=round(overall, 6),
        status=status,
    )
    reasons = []
    if candidate.credential_required:
        reasons.append("credentials required; deferred in offline pass")
    if candidate.network_required:
        reasons.append("network required; deferred in offline pass")
    if status == PROMOTED_STATUS:
        reasons.append("local offline/internal source allowed for fixture research")
    decision = SourcePromotionDecision(
        source_id=candidate.source_id,
        decision=status,
        reasons=reasons,
        allowed_in_current_pass=(status == PROMOTED_STATUS),
        network_required=candidate.network_required,
        credential_required=candidate.credential_required,
    )
    return scorecard, decision


def rank_source_candidates(candidates: list[SourceCandidate] | None = None) -> list[dict]:
    rows = []
    for candidate in candidates or seed_source_candidates():
        scorecard, decision = score_source_candidate(candidate)
        rows.append({
            "candidate": candidate.to_dict(),
            "scorecard": scorecard.to_dict(),
            "decision": decision.to_dict(),
            "hypothesis": contribution_hypothesis(candidate).to_dict(),
        })
    rows.sort(key=lambda row: (-row["scorecard"]["overall_score"], row["candidate"]["source_id"]))
    return rows


def source_scorecard_summary(candidates: list[SourceCandidate] | None = None) -> dict:
    rows = rank_source_candidates(candidates)
    promoted = [r for r in rows if r["scorecard"]["status"] == PROMOTED_STATUS]
    deferred_network = [r for r in rows if r["scorecard"]["status"] == DEFERRED_NETWORK_STATUS]
    deferred_creds = [r for r in rows if r["scorecard"]["status"] == DEFERRED_CREDENTIAL_STATUS]
    return {
        "source_scorecard_version": SOURCE_SCORECARD_VERSION,
        "candidate_count": len(rows),
        "promoted_source_ids": [r["candidate"]["source_id"] for r in promoted],
        "deferred_network_source_ids": [r["candidate"]["source_id"] for r in deferred_network],
        "deferred_credential_source_ids": [r["candidate"]["source_id"] for r in deferred_creds],
        "top_sources": [
            {
                "source_id": r["candidate"]["source_id"],
                "overall_score": r["scorecard"]["overall_score"],
                "status": r["scorecard"]["status"],
            }
            for r in rows[:5]
        ],
        "network_fetch_performed": False,
        "credentials_used": False,
    }
