"""Canonical environment-v1 evaluation identities shared by authors and judges."""

from __future__ import annotations


V1_REQUIRED_NEGATIVE_CONTROL_IDS = frozenset(
    {
        "shifted_features",
        "shuffled_outcomes",
        "placebo_event_dates",
        "randomized_opportunity_identities",
        "randomized_entry_times",
        "stale_quotes",
        "inverted_signals",
        "impossible_fills",
        "costs_exceed_theoretical_edge",
        "random_strategy_selection",
        "synthetic_fair_value_market",
    }
)
