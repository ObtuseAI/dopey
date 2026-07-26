"""Dopey walk-forward fixture replay engine (offline, deterministic, paper-only).

For each window: rank + enrich contracts (liquidity/slippage models + fixture greeks),
build a FAMILY-AWARE defined-risk paper ExecutionIntent, validate it, price the entry with
the slippage model, compute the deterministic family-aware outcome, then attach the greek /
IV-context / IV-surface-scenario fit dimensions the tournament layers aggregate.

Reconstructed after the branch-switch file loss: the public-release engine only replayed a
hardcoded long-call vertical and returned the slim ReplayResult, while the restored
tournament runner / evolution tournament / slippage / greeks / IV test suites consume the
rich family-aware result. The scoring building blocks (family_structures, family_outcome,
liquidity_model, slippage_model, greeks_validation, iv_surface_fixture,
iv_surface_scenarios, iv_family_scoring) all survived; this module is the wiring.

No live path; PaperBroker is the only execution adapter; no network. Every number here is a
deterministic fixture measurement, never real execution quality.
"""
from __future__ import annotations

from dopey_execution.paper_broker import PaperBroker
from dopey_execution.order_intent_validator import validate_intent
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.liquidity_model import score_contract_liquidity
from dopey_execution.slippage_model import build_slippage_input_from_leg, estimate_slippage
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_options.greeks_validation import (
    attribute_greek_outcome,
    evaluate_greek_risk,
    iv_surface_family_score,
    summarize_greek_exposure,
)
from dopey_options.iv_family_scoring import score_family_iv_surface
from dopey_options.iv_surface_fixture import (
    build_iv_context,
    summarize_iv_surface,
    summarize_skew,
    summarize_term_structure,
)
from dopey_options.iv_surface_scenarios import scenario_for_regime
from dopey_research_pipeline.ranker import rank_pipeline_candidates
from dopey_research_pipeline.aggression import evaluate_paper_promotion

from .family_outcome import compute_family_outcome
from .family_structures import build_family_intent, entry_net_from_intent
from .replay_models import ReplayResult
from .scoring import score_walk_forward
from .window_model import WalkForwardWindow


def _dte_bucket(genome) -> str:
    parameters = getattr(genome, "parameters", {}) or {}
    bucket = str(parameters.get("dte_bucket", "")).strip()
    if bucket:
        return bucket
    return "short" if getattr(genome, "family", "") == "short_duration_defined_risk" else "swing"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class ReplayEngine:
    """Deterministic offline replay engine. PaperBroker is the only execution adapter.

    Hard boundary: any attempt to set live_allowed on a replay intent is rejected.
    """

    def __init__(self, gate: ProofWeightedAggressionGate | None = None):
        self.gate = gate or ProofWeightedAggressionGate()

    def _enriched_candidates(self, chain, window: WalkForwardWindow, genome,
                             structure_hint: str, dte_bucket: str) -> list[dict]:
        """Rank the chain, then merge fixture greeks + liquidity/slippage model scores
        into each candidate row (the structure builder and leg dicts read them)."""
        ranked = rank_pipeline_candidates(chain)
        by_symbol = {c.symbol: c for c in chain.contracts}
        regime_context = getattr(window, "regime_context", None) or {}
        family = getattr(genome, "family", "")
        for row in ranked:
            contract = by_symbol.get(row["symbol"])
            if contract is None:
                continue
            liquidity = score_contract_liquidity(
                contract,
                window.regime_tag,
                regime_context,
                family,
                structure_hint,
                dte_bucket,
                leg_count=1,
            )
            row["gamma"] = contract.gamma
            row["theta"] = contract.theta
            row["vega"] = contract.vega
            row["rho"] = contract.rho
            row["liquidity_score"] = liquidity.liquidity_score
            row["liquidity_verdict"] = liquidity.liquidity_verdict
            row["quote_stability_score"] = liquidity.quote_stability_score
            row["fillability_score"] = liquidity.fillability_score
            row["depth_proxy_score"] = liquidity.depth_proxy_score
            slippage = estimate_slippage(build_slippage_input_from_leg(
                dict(row, side="buy"),
                liquidity.liquidity_score,
                liquidity.quote_stability_score,
                {
                    "regime_tag": window.regime_tag,
                    "strategy_family": family,
                    "structure_type": structure_hint,
                    "leg_count": 1,
                    "dte_bucket": dte_bucket,
                    "microstructure_context": regime_context,
                },
            ))
            row["expected_slippage_pct"] = slippage.expected_slippage_pct
        return ranked

    def _leg_slippage(self, intent, window: WalkForwardWindow, genome,
                      structure: str, dte_bucket: str) -> tuple[float, float, float]:
        """Per-leg slippage model pass. Returns (avg expected pct, avg fill quality,
        total absolute fill-price adjustment across legs)."""
        regime_context = getattr(window, "regime_context", None) or {}
        family = getattr(genome, "family", "")
        expected: list[float] = []
        quality: list[float] = []
        total_adjustment = 0.0
        for leg in intent.legs:
            result = estimate_slippage(build_slippage_input_from_leg(
                leg,
                float(leg.get("liquidity_score", 0.5)),
                float(leg.get("quote_stability_score", 0.5)),
                {
                    "regime_tag": window.regime_tag,
                    "strategy_family": family,
                    "structure_type": structure,
                    "leg_count": len(intent.legs),
                    "dte_bucket": dte_bucket,
                    "microstructure_context": regime_context,
                },
            ))
            expected.append(result.expected_slippage_pct)
            quality.append(result.fill_quality_score)
            total_adjustment += abs(result.fill_price_adjustment) * float(leg.get("ratio", 1.0))
        return round(_mean(expected), 6), round(_mean(quality), 6), round(total_adjustment, 6)

    def _fail_result(self, genome, window: WalkForwardWindow, intent_id: str,
                     contracts: list[str], structure: str, liquidity: float,
                     slippage: float = 0.0) -> ReplayResult:
        return ReplayResult(
            strategy_id=genome.genome_id, window_id=window.window_id,
            window_type=window.window_type, regime_tag=window.regime_tag,
            selected_contracts=contracts, paper_intent_id=intent_id,
            verdict="fail", structure=structure,
            liquidity_score=liquidity, slippage_score=slippage,
        )

    def replay_window(self, genome, proof_bundle: dict, window: WalkForwardWindow,
                      sequence: int = 1) -> ReplayResult:
        """Replay one StrategyGenome over one fixture window. Returns a ReplayResult."""
        chain = window.option_chain
        symbols = window.chain_symbols()
        family = getattr(genome, "family", "")
        dte_bucket = _dte_bucket(genome)

        # 1. rank + enrich contracts for this window's chain (family/regime aware)
        ranked = self._enriched_candidates(chain, window, genome, "vertical", dte_bucket)

        # 2. aggression gate (paper-only promotion mapping) using this window's liquidity
        top_liquidity = float(ranked[0].get("liquidity", 0.0)) if ranked else 0.0
        cap = PaperBroker().get_capabilities()
        promo = evaluate_paper_promotion(self.gate, genome.to_dict(), proof_bundle,
                                         top_liquidity, window.regime_tag, cap)
        promotion_decision = {"decision": promo.decision, "aggression_score": promo.aggression.score,
                              "reasons": promo.reasons}

        # 3. build the FAMILY-AWARE defined-risk paper intent
        try:
            intent, structure = build_family_intent(
                genome, chain.underlying.symbol, ranked, window.regime_tag,
                promotion_decision, proof_bundle)
        except ValueError:
            return self._fail_result(genome, window, f"replay-{genome.genome_id}-{window.window_id}",
                                     [], "structure_build_rejected", top_liquidity)
        intent.intent_id = f"replay-{genome.genome_id}-{window.window_id}"
        build_result = getattr(intent, "structure_build_result", {}) or {}
        structure_risk_summary = dict(build_result.get("risk_summary", {}))
        selected = [str(leg.get("symbol", "")) for leg in intent.legs]

        # Hard boundary: ensure no live path (defensive; builder already sets false)
        if intent.live_allowed:
            raise LiveTradingDisabledError("replay engine refuses live_allowed intents")

        # intent-level liquidity = mean of leg liquidity model scores
        leg_liquidity = round(_mean([float(leg.get("liquidity_score", 0.0)) for leg in intent.legs]), 6)

        # slippage model pass first: even a rejected window keeps its honest
        # fill-condition measurements (the tournament aggregates them).
        expected_slippage_pct, fill_quality, slip_cost = self._leg_slippage(
            intent, window, genome, structure, dte_bucket)

        # 4. validate intent against capability + fixture chain
        validation = validate_intent(intent, capability=cap, fixture_symbols=symbols)
        if not validation["valid"]:
            failed = self._fail_result(genome, window, intent.intent_id, selected,
                                       structure, leg_liquidity, expected_slippage_pct)
            failed.expected_slippage_pct = expected_slippage_pct
            failed.fill_quality_score = fill_quality
            return failed

        # 5. entry pricing: net debit/credit from mids, worsened by the slippage model
        entry_net = entry_net_from_intent(intent)
        if structure == "iron_condor":
            entry_effective = round(max(0.0, entry_net - slip_cost), 6)
        else:
            entry_effective = round(entry_net + slip_cost, 6)

        # 6. deterministic family-aware outcome (fixture simulation, not execution quality)
        outcome = compute_family_outcome(
            family=family, structure=structure, legs=intent.legs, window=window,
            entry_net=entry_effective, max_loss=intent.max_loss,
            hints=window.family_hints())
        paper_pnl = outcome.paper_pnl
        verdict = "pass" if paper_pnl >= 0 else ("hold" if outcome.invalidation_triggered else "fail")

        # 7. greek + IV context fit dimensions
        regime_context = getattr(window, "regime_context", None) or {}
        exposure = summarize_greek_exposure(intent.legs)
        iv_context = build_iv_context(chain, window.regime_tag, window.underlying_snapshot, regime_context)
        surface = summarize_iv_surface(chain, window.underlying_snapshot)
        skew = summarize_skew(chain, window.underlying_snapshot)
        term = summarize_term_structure(chain, window.underlying_snapshot, window.regime_tag)
        greek_verdict = evaluate_greek_risk(
            genome.genome_id, family, exposure, iv_context, surface, skew, term,
            window.regime_tag, leg_liquidity)
        iv_scores = iv_surface_family_score(family, iv_context, surface, skew, term, window.regime_tag)

        window_outcome = window.expected_outcome or {}
        start_price = float(window.underlying_snapshot.get("price", 0.0))
        end_price = float(window_outcome.get("next_underlying_price", start_price))
        end_iv = float(window_outcome.get("next_iv", surface.atm_iv))
        attribution = attribute_greek_outcome(
            genome.genome_id, window.window_id, family, exposure, paper_pnl,
            start_price, end_price, surface.atm_iv, end_iv,
            int(window_outcome.get("days_to_exit", 1)))

        # 8. IV surface scenario lane (regime-matched deterministic scenario)
        scenario = scenario_for_regime(window.regime_tag)
        family_surface = score_family_iv_surface(family, scenario)

        return ReplayResult(
            strategy_id=genome.genome_id,
            window_id=window.window_id,
            window_type=window.window_type,
            regime_tag=window.regime_tag,
            selected_contracts=selected,
            paper_intent_id=intent.intent_id,
            simulated_fill=entry_effective,
            simulated_exit=round(outcome.base_structure_payoff, 6),
            paper_pnl=paper_pnl,
            max_adverse_excursion=outcome.max_adverse_excursion,
            max_favorable_excursion=outcome.max_favorable_excursion,
            slippage_score=expected_slippage_pct,
            liquidity_score=leg_liquidity,
            invalidation_triggered=outcome.invalidation_triggered,
            verdict=verdict,
            structure=structure,
            structure_risk_summary=structure_risk_summary,
            fill_quality_score=fill_quality,
            expected_slippage_pct=expected_slippage_pct,
            greek_fit_score=greek_verdict.greek_fit_score,
            delta_fit_score=greek_verdict.delta_fit_score,
            gamma_fit_score=greek_verdict.gamma_fit_score,
            theta_fit_score=greek_verdict.theta_fit_score,
            vega_fit_score=greek_verdict.vega_fit_score,
            greek_risk_flags=list(greek_verdict.risk_flags),
            greek_risk_verdict=greek_verdict.verdict,
            greek_attribution_quality_score=attribution.attribution_quality_score,
            iv_context_score=iv_scores["iv_context_score"],
            skew_score=iv_scores["skew_score"],
            term_structure_score=iv_scores["term_structure_score"],
            iv_surface_scenario_id=family_surface.scenario_id,
            iv_surface_fit_score=family_surface.iv_surface_fit_score,
            family_iv_fit_score=family_surface.family_iv_fit_score,
            skew_term_score=family_surface.skew_term_score,
            premium_overpayment_score=family_surface.premium_overpayment_score,
            iv_crush_score=family_surface.iv_crush_score,
            iv_expansion_score=family_surface.iv_expansion_score,
            front_event_bump_score=family_surface.front_event_bump_score,
            skew_trap_score=family_surface.skew_trap_score,
            wing_elevation_score=family_surface.wing_elevation_score,
            surface_instability_penalty=family_surface.surface_instability_penalty,
            term_structure_risk_penalty=family_surface.term_structure_risk_penalty,
            iv_crush_expansion_mismatch_penalty=family_surface.iv_crush_expansion_mismatch_penalty,
            iv_surface_risk_flags=list(family_surface.risk_flags),
            iv_surface_verdict=family_surface.verdict,
            regime_match_score=outcome.regime_match_score,
            family_fit_score=outcome.family_fit_score,
            exit_reason=outcome.exit_reason,
        )

    def replay(self, genome, proof_bundle: dict, windows: list[WalkForwardWindow]) -> list[ReplayResult]:
        """Replay a genome across all windows. Deterministic; returns per-window results."""
        return [self.replay_window(genome, proof_bundle, w, i + 1)
                for i, w in enumerate(windows)]


def replay_walk_forward(genome, proof_bundle: dict, windows: list[WalkForwardWindow]) -> dict:
    """Convenience: replay + score. Returns {results, score}."""
    engine = ReplayEngine()
    results = engine.replay(genome, proof_bundle, windows)
    score = score_walk_forward(results)
    return {"results": results, "score": score}
