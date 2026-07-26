"""Pure fail-closed risk guard for prospective forward paper entries."""

from __future__ import annotations

from typing import Any, Final

from .adversarial_stress_engine import (
    stress_summary_has_complete_quotes,
    stress_summary_integrity_valid,
    stress_summary_matches_current_policy,
    stress_summary_matches_forward_book,
)


MAX_SYMBOL_PREMIUM_SHARE: Final[float] = 0.25
BEAR_FLAGS_REFUSE: Final[int] = 3
BEAR_FLAGS_REDUCE: Final[int] = 2
STRESS_GREEN_STATUSES: Final[frozenset[str]] = frozenset(
    {"book_survives_all_scenarios", "no_open_positions_book_trivially_survives"}
)
ENTRY_GUARD_VERSION: Final[str] = "dopey-forward-entry-risk-guard-v2"


def premium_at_risk_by_symbol(positions: list[dict[str, Any]]) -> dict[str, float]:
    premiums: dict[str, float] = {}
    for position in positions:
        symbol = str(position["symbol"])
        entry_fill = float(position["entry_fill"])
        if entry_fill <= 0:
            raise ValueError(
                f"open position entry_fill must be positive: symbol={symbol}, entry_fill={entry_fill}"
            )
        premiums[symbol] = premiums.get(symbol, 0.0) + entry_fill
    return premiums


def top_symbol_premium_share(positions: list[dict[str, Any]]) -> float:
    premiums = premium_at_risk_by_symbol(positions)
    total = sum(premiums.values())
    return max(premiums.values()) / total if total > 0 else 0.0


def concentration_rejection_reasons(
    positions: list[dict[str, Any]],
    candidate_symbol: str,
    candidate_entry_fill: float,
) -> tuple[str, ...]:
    if not candidate_symbol:
        raise ValueError("candidate symbol must not be empty")
    if candidate_entry_fill <= 0:
        raise ValueError(
            f"candidate entry_fill must be positive: symbol={candidate_symbol}, entry_fill={candidate_entry_fill}"
        )
    if not positions:
        return ()
    current_top_share = top_symbol_premium_share(positions)
    projected_positions = [
        *positions,
        {"symbol": candidate_symbol, "entry_fill": candidate_entry_fill},
    ]
    projected_top_share = top_symbol_premium_share(projected_positions)
    if current_top_share <= MAX_SYMBOL_PREMIUM_SHARE:
        if projected_top_share > MAX_SYMBOL_PREMIUM_SHARE:
            return ("projected_symbol_premium_share_exceeds_25pct",)
        return ()
    if projected_top_share >= current_top_share:
        return ("projected_entry_does_not_repair_existing_premium_concentration",)
    return ()


def adversarial_context_flags(
    symbol: str,
    candidate_strategy: str,
    context: dict[str, Any],
    macro: dict[str, Any],
) -> tuple[str, ...]:
    if candidate_strategy not in {"long_call", "long_put"}:
        raise ValueError(
            f"unsupported forward entry strategy: strategy={candidate_strategy}"
        )
    side = "call" if candidate_strategy == "long_call" else "put"
    bias_key = f"long_{side}_entry_bias"
    attention = (
        macro.get("attention", {}) if isinstance(macro.get("attention"), dict) else {}
    )
    crowded = {str(value) for value in attention.get("crowded_symbols", [])}
    congress = (
        macro.get("congress", {}) if isinstance(macro.get("congress"), dict) else {}
    )
    notable_selling = {str(value) for value in congress.get("notable_selling", [])}
    vol_term = (
        macro.get("vol_term_structure", {})
        if isinstance(macro.get("vol_term_structure"), dict)
        else {}
    )
    fundamentals = (
        macro.get("fundamentals", {})
        if isinstance(macro.get("fundamentals"), dict)
        else {}
    )
    short_candidates = {
        str(value) for value in fundamentals.get("short_candidate_flags", [])
    }
    flags: list[str] = []
    if bool(context.get("earnings_blackout")):
        flags.append("earnings_blackout_window")
    if str(context.get("gamma_regime", "")).startswith("short_gamma"):
        flags.append("dealer_short_gamma_amplifying")
    if str(context.get("crowd_state", "")) == "crowded" or symbol in crowded:
        flags.append("crowded_attention")
    if str(context.get(bias_key, "")) == "unfavorable":
        flags.append("fusion_bias_unfavorable_for_side")
    if bool(context.get("surface_tear_present")):
        flags.append("vol_surface_tear")
    if str(vol_term.get("state", "")) == "backwardation":
        flags.append("vix_term_backwardation")
    if symbol in notable_selling:
        flags.append("congress_notable_selling")
    if symbol in short_candidates:
        flags.append("speculative_excess_fundamentals")
    return tuple(flags)


def adversarial_rejection_reasons(
    symbol: str,
    candidate_strategy: str,
    context: dict[str, Any],
    macro: dict[str, Any],
) -> tuple[str, ...]:
    flags = adversarial_context_flags(symbol, candidate_strategy, context, macro)
    if "earnings_blackout_window" in flags or len(flags) >= BEAR_FLAGS_REFUSE:
        return ("adversarial_entry_verdict_would_refuse", *flags)
    if len(flags) >= BEAR_FLAGS_REDUCE:
        return (
            "adversarial_entry_verdict_would_reduce_but_one_contract_cannot_be_reduced",
            *flags,
        )
    return ()


def existing_book_stress_rejection_reasons(
    positions: list[dict[str, Any]],
    stress_summary: dict[str, Any],
) -> tuple[str, ...]:
    if not positions:
        return ()
    if not stress_summary:
        return ("missing_existing_book_stress_evidence",)
    if not stress_summary_integrity_valid(stress_summary):
        return ("unverified_existing_book_stress_integrity",)
    if not stress_summary_matches_forward_book(stress_summary, positions):
        return ("stale_existing_book_stress_evidence",)
    if not stress_summary_matches_current_policy(stress_summary):
        return ("stale_existing_book_stress_policy",)
    if not stress_summary_has_complete_quotes(stress_summary, positions):
        return ("unusable_current_quote_stress_evidence",)
    observed_count = stress_summary.get("open_position_count")
    if not isinstance(observed_count, int) or observed_count != len(positions):
        return ("stale_existing_book_stress_evidence",)
    if str(stress_summary.get("stress_status", "")) not in STRESS_GREEN_STATUSES:
        if (
            stress_summary.get("scenario_stress_green") is True
            and stress_summary.get("concentration_green") is False
        ):
            # Concentration is the ONLY breach. A blanket block would make it
            # permanent: exits shrink the book and concentrate it further, and
            # the sole honest repair is dilution by non-breaching entries -
            # which concentration_rejection_reasons already governs candidate
            # by candidate (repairing entries pass, worsening entries refuse).
            # Scenario-level vulnerability still blanket-blocks below.
            return ()
        return ("existing_book_stress_not_green",)
    return ()


def prospective_entry_rejection_reasons(
    positions: list[dict[str, Any]],
    candidate_symbol: str,
    candidate_strategy: str,
    candidate_entry_fill: float,
    context: dict[str, Any],
    macro: dict[str, Any],
    stress_summary: dict[str, Any],
) -> tuple[str, ...]:
    reasons = (
        *existing_book_stress_rejection_reasons(positions, stress_summary),
        *concentration_rejection_reasons(
            positions, candidate_symbol, candidate_entry_fill
        ),
        *adversarial_rejection_reasons(
            candidate_symbol, candidate_strategy, context, macro
        ),
    )
    return tuple(dict.fromkeys(reasons))
