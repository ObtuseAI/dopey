from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from dopey_autonomy.run_resilient_research_supervisor import STAGES
from dopey_targeting.models import default_targeting_policy
from dopey_targeting.per_symbol_forecast_skill import (
    build_per_symbol_forecast_skill,
    load_playbook_settlements,
)
from dopey_targeting.shadow_targeting_ledger import (
    append_current_shadow_signals,
    settle_shadow_signals,
)
from dopey_targeting.symbol_candidate_registry import (
    build_symbol_candidate_registry,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _settlements(
    symbol: str,
    family: str,
    favorable: bool,
) -> list[dict[str, object]]:
    generator = random.Random(f"{symbol}:{family}")
    signs = [1 if generator.random() >= 0.5 else -1 for _ in range(40)]
    start = date(2024, 1, 2)
    records: list[dict[str, object]] = []
    for index, sign in enumerate(signs):
        as_of = start + timedelta(days=index * 5)
        direction = "long" if sign > 0 else "short"
        signed_return = 0.025 * sign * (1.0 if favorable else -1.0)
        records.append(
            {
                "artifact_type": "playbook_settlement",
                "detection_id": f"{symbol}:{family}:{index}",
                "setup_id": f"{family}_setup",
                "family": family,
                "symbol": symbol,
                "as_of_date": as_of.isoformat(),
                "settle_date": (as_of + timedelta(days=2)).isoformat(),
                "horizon_days": 2,
                "direction": direction,
                "forward_return": signed_return,
                "graded": True,
                "hit": favorable,
                "contested_truth": True,
                "prior_drift": 0.0,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return records


def _history(start: date, count: int) -> list[dict[str, object]]:
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "close": 100.0 + index,
            "volume": 2_000_000.0,
        }
        for index in range(count)
    ]


def test_per_symbol_forecast_skill_requires_effective_null_robustness(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "settlements.jsonl"
    records = [
        *_settlements("POS", "mean_reversion", True),
        *_settlements("NEG", "momentum_trend", False),
    ]
    _write_jsonl(ledger, records)

    report = build_per_symbol_forecast_skill(
        load_playbook_settlements(ledger),
        {"playbook_settlements": "test-hash"},
        default_targeting_policy(),
    )

    positive = report["per_symbol"]["POS"]["per_family"]["mean_reversion"]
    negative = report["per_symbol"]["NEG"]["per_family"]["momentum_trend"]
    positive_detector = report["per_symbol"]["POS"]["per_detector"][
        "mean_reversion_setup"
    ]
    assert positive["verdict"] == "positive_verified"
    assert positive_detector["verdict"] == "positive_verified"
    assert negative["verdict"] == "negative_verified"
    assert positive["effective_sample_size"] == 40
    assert positive["circular_shift_null_p_value"] <= 0.10
    assert all(era["effective_samples"] == 20 for era in positive["eras"])
    assert report["advisory_only_never_a_gate_input"] is True
    assert report["promotion_allowed"] is False


def test_overlapping_daily_refires_do_not_meet_effective_sample_floor(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "overlap.jsonl"
    start = date(2026, 1, 2)
    records = []
    for index in range(40):
        as_of = start + timedelta(days=index)
        records.append(
            {
                "detection_id": f"overlap:{index}",
                "setup_id": "overlap_setup",
                "family": "mean_reversion",
                "symbol": "OVR",
                "as_of_date": as_of.isoformat(),
                "settle_date": (as_of + timedelta(days=5)).isoformat(),
                "horizon_days": 5,
                "direction": "long",
                "forward_return": 0.03,
                "prior_drift": 0.0,
                "graded": True,
                "contested_truth": True,
            }
        )
    _write_jsonl(ledger, records)

    report = build_per_symbol_forecast_skill(
        load_playbook_settlements(ledger),
        {"playbook_settlements": "test-hash"},
        default_targeting_policy(),
    )
    row = report["per_symbol"]["OVR"]["per_family"]["mean_reversion"]

    assert row["raw_contested_samples"] == 40
    assert row["effective_sample_size"] < 10
    assert row["verdict"] == "insufficient_evidence"


def test_targeting_excludes_legacy_hard_coded_direction_settlements(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "legacy.jsonl"
    row = _settlements("LEGACY", "flow_positioning", True)[0]
    row["setup_id"] = "gamma_squeeze_flow"
    _write_jsonl(ledger, [row])

    loaded = load_playbook_settlements(ledger)

    assert loaded.observations == ()
    assert loaded.rejected_reason_counts == {
        "legacy_direction_assumption_quarantined": 1
    }


def test_registry_includes_every_symbol_and_applies_iv_cost_and_liquidity(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "settlements.jsonl"
    _write_jsonl(
        ledger,
        [
            *_settlements("POS", "mean_reversion", True),
            *_settlements("NEG", "momentum_trend", False),
        ],
    )
    forecast = build_per_symbol_forecast_skill(
        load_playbook_settlements(ledger),
        {"playbook_settlements": "test-hash"},
        default_targeting_policy(),
    )
    histories = {
        symbol: _history(date(2025, 1, 1), 80)
        for symbol in ("POS", "NEG", "NONE")
    }
    registry = build_symbol_candidate_registry(
        histories,
        forecast,
        {
            "POS": {
                "snapshot_date": "2026-01-01",
                "median_mid_bisection_iv": 0.20,
                "contract_count": 50,
            },
            "NEG": {
                "snapshot_date": "2026-01-01",
                "median_mid_bisection_iv": 0.20,
                "contract_count": 50,
            },
        },
        {"history_manifest": "history-hash"},
        default_targeting_policy(),
    )
    by_symbol = {row["symbol"]: row for row in registry["candidates"]}

    assert registry["candidate_count"] == 3
    assert set(by_symbol) == {"POS", "NEG", "NONE"}
    assert (
        by_symbol["POS"]["candidate_status"]
        == "targeting_shadow_eligible_for_forward_validation"
    )
    assert (
        by_symbol["NEG"]["candidate_status"]
        == "avoid_observed_families_graded"
    )
    assert (
        by_symbol["NONE"]["candidate_status"]
        == "insufficient_evidence_shadow_watch"
    )
    assert by_symbol["POS"]["targeting_score"] > 0.0
    assert by_symbol["POS"]["shadow_attention_weight"] <= 0.10
    assert registry["order_capability_present"] is False
    assert registry["promotion_allowed"] is False


def test_shadow_targeting_ledger_is_idempotent_and_gate_blind(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    registry = {
        "reproducibility_hash": "registry-hash",
        "candidate_registry_version": "test-registry-v1",
        "capacity_policy": {
            "maximum_shadow_candidates": 20,
            "maximum_shadow_candidates_per_direction": 10,
        },
        "candidates": [
            {
                "symbol": "POS",
                "candidate_status": (
                    "targeting_shadow_eligible_for_forward_validation"
                ),
                "targeting_score": 0.8,
                "shadow_attention_weight": 0.1,
                "per_family_targeting_score": {"mean_reversion": 0.8},
            }
        ],
    }
    detections = [
        {
            "detection_id": "detection-1",
            "symbol": "POS",
            "family": "mean_reversion",
            "setup_id": "snapback",
            "as_of_date": "2026-01-05",
            "direction": "long",
            "horizon_days": [2, 5],
            "strength": 0.7,
        }
    ]

    first = append_current_shadow_signals(
        detections,
        set(),
        registry,
        signal_path,
    )
    second = append_current_shadow_signals(
        detections,
        set(),
        registry,
        signal_path,
    )
    histories = {"POS": _history(date(2026, 1, 1), 20)}
    settlement_first = settle_shadow_signals(
        histories,
        signal_path,
        settlement_path,
    )
    settlement_second = settle_shadow_signals(
        histories,
        signal_path,
        settlement_path,
    )

    assert first["appended_signal_count"] == 1
    assert second["appended_signal_count"] == 0
    assert settlement_first["new_settlement_count"] == 1
    assert settlement_second["new_settlement_count"] == 0
    signal = json.loads(signal_path.read_text(encoding="utf-8"))
    assert signal["phantom_position"] is True
    assert signal["advisory_only_never_a_gate_input"] is True
    assert signal["promotion_allowed"] is False
    assert signal["order_capability_present"] is False


def test_shadow_targeting_deduplicates_source_detection_across_registry_versions(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.jsonl"
    detection = {
        "detection_id": "stable-detection",
        "symbol": "POS",
        "family": "mean_reversion",
        "setup_id": "snapback",
        "as_of_date": "2026-01-05",
        "direction": "long",
        "horizon_days": [5],
        "strength": 0.7,
    }

    def registry(registry_hash: str) -> dict[str, object]:
        return {
            "reproducibility_hash": registry_hash,
            "candidate_registry_version": "test-registry-v1",
            "capacity_policy": {
                "maximum_shadow_candidates": 20,
                "maximum_shadow_candidates_per_direction": 10,
            },
            "candidates": [
                {
                    "symbol": "POS",
                    "candidate_status": (
                        "targeting_shadow_eligible_for_forward_validation"
                    ),
                    "targeting_score": 0.8,
                    "shadow_attention_weight": 0.1,
                    "per_family_targeting_score": {"mean_reversion": 0.8},
                }
            ],
        }

    first = append_current_shadow_signals(
        [detection],
        set(),
        registry("registry-a"),
        signal_path,
    )
    second = append_current_shadow_signals(
        [detection],
        set(),
        registry("registry-b"),
        signal_path,
    )

    assert first["appended_signal_count"] == 1
    assert second["appended_signal_count"] == 0
    assert len(signal_path.read_text(encoding="utf-8").splitlines()) == 1


def test_shadow_targeting_enforces_symbol_and_direction_capacity(
    tmp_path: Path,
) -> None:
    signal_path = tmp_path / "signals.jsonl"
    candidates = [
        {
            "symbol": f"S{index:02d}",
            "candidate_status": (
                "targeting_shadow_eligible_for_forward_validation"
            ),
            "targeting_score": 1.0 - index / 100.0,
            "shadow_attention_weight": 0.04 if index < 20 else 0.0,
            "per_family_targeting_score": {"mean_reversion": 0.8},
        }
        for index in range(25)
    ]
    registry = {
        "reproducibility_hash": "registry-capacity",
        "candidate_registry_version": "test-registry-v1",
        "capacity_policy": {
            "maximum_shadow_candidates": 20,
            "maximum_shadow_candidates_per_direction": 10,
        },
        "candidates": candidates,
    }
    detections = [
        {
            "detection_id": f"detection-{index}",
            "symbol": f"S{index:02d}",
            "family": "mean_reversion",
            "setup_id": "snapback",
            "as_of_date": "2026-01-05",
            "direction": "long" if index < 15 else "short",
            "horizon_days": [5],
            "strength": 0.7,
        }
        for index in range(25)
    ]

    result = append_current_shadow_signals(
        detections,
        set(),
        registry,
        signal_path,
    )
    rows = [
        json.loads(line)
        for line in signal_path.read_text(encoding="utf-8").splitlines()
    ]

    assert result["pre_capacity_candidate_signal_count"] == 20
    assert result["candidate_signal_count"] == 15
    assert result["capacity_dropped_count"] == 5
    assert len({row["symbol"] for row in rows}) == 15
    assert sum(row["direction"] == "long" for row in rows) == 10
    assert sum(row["direction"] == "short" for row in rows) == 5


def test_symbol_targeting_supervisor_stage_is_dependency_safe() -> None:
    stage_dependencies = {name: dependencies for name, _, dependencies in STAGES}
    stage_order = [name for name, _, _ in STAGES]

    assert stage_dependencies["symbol_targeting"] == (
        "playbook_research",
        "model_iv_calibration",
    )
    assert stage_order.index("playbook_research") < stage_order.index(
        "symbol_targeting"
    )
    assert stage_order.index("model_iv_calibration") < stage_order.index(
        "symbol_targeting"
    )
