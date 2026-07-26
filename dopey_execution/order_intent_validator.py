"""Dopey order-intent validator: structural validation before any broker call.

DOPEY-native. Validates an ExecutionIntent against defined-risk + capability + fixture-chain
rules. Rejects any live intent deterministically.

Restored: per-leg fill-quality screening via the dynamic slippage model. When a
`fill_context` (regime/family) is provided, every leg is scored; legs whose deterministic
fill verdict is poor/reject label the intent a `poor_fill_candidate` (research label -
labeling never silently upgrades an intent, and structural validity rules are unchanged).
"""
from __future__ import annotations

from .execution_intent import ExecutionIntent
from .slippage_model import build_slippage_input_from_leg, estimate_slippage


def _leg_liquidity_proxy(leg: dict) -> float:
    """Deterministic per-leg liquidity proxy from the leg dict itself."""
    for key in ("liquidity_score", "liquidity", "fillability_score"):
        if key in leg:
            try:
                return max(0.0, min(1.0, float(leg[key])))
            except (TypeError, ValueError):
                continue
    return 0.5


def validate_intent(intent: ExecutionIntent, capability: dict | None = None,
                    fixture_symbols: set[str] | None = None,
                    fill_context: dict | None = None,
                    open_positions: list[dict] | None = None) -> dict:
    """Validate an intent. Returns {valid, errors, liquidity_checks, research_labels}.

    - capability: optional broker capability dict (structural support check).
    - fixture_symbols: optional set of allowed option-contract symbols (ensures legs come from a
      known fixture chain; rejects intents referencing contracts not in the chain).
    - fill_context: optional regime/family context; enables per-leg fill-quality screening.
    - open_positions: optional open-position records; active-trading-policy intents
      (order_action set) are validated against them - buy-to-open only, no naked selling,
      close requires a matching open position, no same-day close outside the zero-DTE
      special lifecycle (fail-closed).
    """
    errs = intent.validate()
    if intent.order_action or intent.active_policy_required or open_positions is not None:
        from .position_lifecycle import active_policy_errors_for_open, validate_active_order_intent

        if intent.order_action:
            errs.extend(validate_active_order_intent(intent, open_positions))
        else:
            # active-policy intent with no declared order_action: validate as an
            # open (fail-closed - the open validator rejects unsupported
            # structures, multi-leg actives, naked selling, undefined risk)
            errs.extend(active_policy_errors_for_open(intent))
    if capability is not None:
        supports = capability.get("supports_structure")
        if supports is None:
            structures = capability.get("supported_structures", [])
            supports = intent.structure in structures
        if not supports:
            errs.append("broker capability does not support the requested structure")
        if not intent.paper and not capability.get("options_exec_supported", False):
            errs.append("non-paper intent requires options_exec_supported capability")
    if not intent.paper and intent.live_allowed and not intent.defined_risk:
        errs.append("live undefined-risk intent is blocked (defined-risk default)")
    if intent.max_loss <= 0:
        errs.append("max_loss must be present and positive")
    if fixture_symbols is not None:
        for leg in intent.legs:
            sym = leg.get("symbol", "")
            if sym and sym not in fixture_symbols:
                errs.append(f"leg symbol {sym!r} is not from the fixture chain")

    liquidity_checks: list[dict] = []
    research_labels: list[str] = []
    if fill_context is not None:
        context = dict(fill_context)
        context.setdefault("structure_type", intent.structure)
        context.setdefault("leg_count", len(intent.legs))
        for leg in intent.legs:
            liquidity = _leg_liquidity_proxy(leg)
            quote_stability = float(leg.get("quote_stability_score", context.get("quote_stability_score", 0.5)))
            result = estimate_slippage(build_slippage_input_from_leg(
                dict(leg), liquidity, quote_stability, context))
            liquidity_checks.append({
                "symbol": leg.get("symbol", ""),
                "liquidity_score": liquidity,
                "expected_slippage_pct": result.expected_slippage_pct,
                "fill_quality_score": result.fill_quality_score,
                "slippage_verdict": result.slippage_verdict,
            })
        if any(check["slippage_verdict"] in {"poor", "reject"} for check in liquidity_checks):
            research_labels.append("poor_fill_candidate")
        if any(check["fill_quality_score"] < 0.35 for check in liquidity_checks):
            if "poor_fill_candidate" not in research_labels:
                research_labels.append("poor_fill_candidate")

    return {
        "valid": not errs,
        "errors": errs,
        "liquidity_checks": liquidity_checks,
        "research_labels": research_labels,
    }
