"""Dodgers reclamation bench + golf miss-pattern (course management).

The bench never un-refuses: triggers only recommend re-running the same
prosecution. Miss-pattern stats make the scorecard dispersion-aware: a mild
mean with a fat catastrophic tail is AVOID.
"""
from __future__ import annotations

from dopey.strategy_engineering.reclamation_bench import BENCH, TRIGGERS, scout_reclamations
from dopey.strategy_engineering.playbook_settlement import PLAYBOOK_TRUST_VERSION
from dopey.strategy_engineering.situational_scorecard import build_situational_scorecard
from dopey.strategy_engineering.trade_memory import MEMORY_VERSION, _outcome_stats


# ---------- miss pattern (golf) ----------


def _records(pnls, maes=None):
    maes = maes or [-0.2] * len(pnls)
    return [
        {
            "path_pnl": p * 5.0,
            "trade_return_model_units": p,
            "win": p > 0,
            "mae": m,
        }
        for p, m in zip(pnls, maes)
    ]


def test_outcome_stats_include_miss_pattern() -> None:
    stats = _outcome_stats(_records([-1.0, -0.95, 0.2, 0.3, 0.1, -0.1, 0.05, 0.15, 0.25, -0.05]))
    assert stats["catastrophic_loss_share"] == 0.2  # 2 of 10 lost >= 90%
    assert stats["p10_trade_return_model_units"] == -1.0
    assert "mean_max_adverse_excursion_premium_units" in stats


def test_catastrophic_miss_profile_is_avoid_even_with_mild_mean() -> None:
    # mean is mild (-0.1) but 30% of trades are near-total losses
    pnls = [-0.95] * 3 + [0.25] * 7
    stats = _outcome_stats(_records(pnls))
    stats["count"] = 1000  # clear the scorecard's sample floor
    memory = {
        "memory_version": MEMORY_VERSION,
        "per_family": {
            "momentum": {"conditional_by_stretch": {"near": stats}}
        },
    }
    card = build_situational_scorecard(memory, {"families": []}, {})
    call = card["situations"][0]
    assert call["call"] == "avoid_catastrophic_miss"
    assert call["miss_pattern"]["catastrophic_loss_share"] == 0.3
    # and it lands on the avoid list
    assert any(a["entry_context"] == "near" for a in card["avoid_list"])


def test_safe_miss_profile_not_flagged() -> None:
    pnls = [-0.3] * 3 + [0.2] * 7  # same-ish mean, tight dispersion, no catastrophes
    stats = _outcome_stats(_records(pnls))
    stats["count"] = 1000
    memory = {
        "memory_version": MEMORY_VERSION,
        "per_family": {
            "momentum": {"conditional_by_stretch": {"near": stats}}
        },
    }
    card = build_situational_scorecard(memory, {"families": []}, {})
    assert card["situations"][0]["call"] != "avoid_catastrophic_miss"


# ---------- reclamation bench (Dodgers) ----------


def test_every_benched_entry_has_a_trigger_and_specific_flaw() -> None:
    for benched in BENCH:
        assert benched["bench_id"] in TRIGGERS
        assert "flaw" in benched["diagnosed_flaw"] or len(benched["diagnosed_flaw"]) > 20  # specific, not "failed"


def test_bench_holds_when_world_unchanged() -> None:
    report = scout_reclamations({
        "playbook_trust": {}, "scanner_fitness": {}, "screener_fitness": {},
        "convergence": {"families": [{"family": "momentum_continuation", "verdict": "contested_lanes_disagree"}]},
        "macro": {},
    })
    assert report["retest_recommended"] == []
    assert report["honesty_invariants"]["never_un_refuses"] is True
    assert "hold" in report["headline"]


def test_squeeze_retest_fires_on_rated_positive_forward_settlement() -> None:
    report = scout_reclamations({
        "playbook_trust": {
            "playbook_trust_version": PLAYBOOK_TRUST_VERSION,
            "per_setup": {
                "bb_squeeze_breakout": {
                    "trust_state": "rated",
                    "contested_settled": 40,
                    "contested_hit_rate": 0.60,
                    "effective_contested_settled": 40,
                    "effective_contested_hit_rate": 0.60,
                }
            },
        },
        "scanner_fitness": {}, "screener_fitness": {}, "convergence": {}, "macro": {},
    })
    assert "bb_squeeze_direction_5d" in report["retest_recommended"]


def test_squeeze_retest_ignores_autocorrelated_raw_settlements() -> None:
    report = scout_reclamations({
        "playbook_trust": {
            "playbook_trust_version": PLAYBOOK_TRUST_VERSION,
            "per_setup": {
                "bb_squeeze_breakout": {
                    "trust_state": (
                        "unrated_insufficient_effective_"
                        "contested_settlements"
                    ),
                    "contested_settled": 100,
                    "contested_hit_rate": 0.90,
                    "effective_contested_settled": 1,
                    "effective_contested_hit_rate": 0.90,
                }
            },
        },
        "scanner_fitness": {},
        "screener_fitness": {},
        "convergence": {},
        "macro": {},
    })

    assert "bb_squeeze_direction_5d" not in report["retest_recommended"]


def test_reversion_retest_fires_on_low_vix() -> None:
    report = scout_reclamations({
        "playbook_trust": {}, "scanner_fitness": {}, "screener_fitness": {},
        "convergence": {}, "macro": {"vol_term_structure": {"VIX": 12.5}},
    })
    assert "mean_reversion_long_option_expression" in report["retest_recommended"]


def test_stale_scanner_fitness_cannot_trigger_reversion_retest() -> None:
    report = scout_reclamations({
        "playbook_trust": {},
        "scanner_fitness": {
            "scanner_fitness_version": "dopey-scanner-holdout-fitness-v1",
            "per_detector": {
                "short_term_reversal": {
                    "events": 1_000,
                    "mean_excess": 0.50,
                }
            },
        },
        "screener_fitness": {},
        "convergence": {},
        "macro": {"vol_term_structure": {"VIX": 20.0}},
    })
    entry = next(
        value
        for value in report["entries"]
        if value["bench_id"] == "mean_reversion_long_option_expression"
    )

    assert "mean_reversion_long_option_expression" not in report["retest_recommended"]
    assert "version incompatible" in entry["trigger_evidence"]


def test_vol_expansion_retest_fires_on_ic_flip() -> None:
    report = scout_reclamations({
        "playbook_trust": {}, "scanner_fitness": {},
        "screener_fitness": {"per_archetype": {"long_premium_vol_expansion": {"mean_holdout_rank_ic": 0.008}}},
        "convergence": {}, "macro": {},
    })
    assert "vol_expansion_screener_archetype" in report["retest_recommended"]


def test_momentum_retest_fires_when_convergence_resolves() -> None:
    report = scout_reclamations({
        "playbook_trust": {}, "scanner_fitness": {}, "screener_fitness": {},
        "convergence": {"families": [{"family": "momentum_continuation", "verdict": "corroborated", "consensus_sign": "negative"}]},
        "macro": {},
    })
    assert "momentum_direction_contested" in report["retest_recommended"]


def test_bench_never_promotes() -> None:
    report = scout_reclamations({"playbook_trust": {}, "scanner_fitness": {}, "screener_fitness": {}, "convergence": {}, "macro": {}})
    assert report["honesty_invariants"]["promotion_allowed"] is False
    assert report["not_edge_evidence"] is True


def test_veto_shadow_retest_fires_on_rated_positive_phantom_class() -> None:
    report = scout_reclamations({
        "playbook_trust": {}, "scanner_fitness": {}, "screener_fitness": {},
        "convergence": {}, "macro": {},
        "veto_shadow": {"per_veto_class": {
            "vrp_rich_premium_expensive": {"n": 35, "mean_trade_return": 0.08},
            "entry_context_unfavorable": {"n": 50, "mean_trade_return": -0.12},
        }},
    })
    assert "context_veto_classes_earn_their_keep" in report["retest_recommended"]


def test_veto_shadow_holds_below_sample_floor_or_negative() -> None:
    report = scout_reclamations({
        "playbook_trust": {}, "scanner_fitness": {}, "screener_fitness": {},
        "convergence": {}, "macro": {},
        "veto_shadow": {"per_veto_class": {
            "vrp_rich_premium_expensive": {"n": 10, "mean_trade_return": 0.30},  # n below floor
            "entry_context_unfavorable": {"n": 60, "mean_trade_return": -0.05},  # negative
        }},
    })
    assert "context_veto_classes_earn_their_keep" not in report["retest_recommended"]
