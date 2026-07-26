"""Integration proofs for the production epistemic artifact adapter."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dopey_validation import epistemic_runtime
from dopey_validation.epistemic_adversary import (
    canonical_epistemic_hash,
    default_epistemic_policy,
)
from dopey_validation.epistemic_runtime import (
    EpistemicRuntimePaths,
    run_epistemic_supervision,
)

EVALUATED_AT = datetime(2026, 7, 26, 15, 30, tzinfo=timezone.utc)
DECISION_AT = "2026-07-26T15:00:00+00:00"


def _write_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(
    path: Path,
    records: tuple[dict[str, object], ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _content_addressed(record: dict[str, object]) -> dict[str, object]:
    return {
        **record,
        "reproducibility_hash": canonical_epistemic_hash(record),
    }


def _paths(root: Path) -> EpistemicRuntimePaths:
    return EpistemicRuntimePaths(
        repository_root=root,
        squeeze_assessments_path=(
            root / "artifacts" / "squeeze" / "symbol_assessments.jsonl"
        ),
        squeeze_rankings_path=(
            root / "artifacts" / "squeeze" / "candidate_rankings.json"
        ),
        squeeze_summary_path=(
            root / "artifacts" / "squeeze" / "squeeze_bubble_summary.json"
        ),
        targeting_registry_path=(
            root / "artifacts" / "targeting" / "symbol_candidate_registry.json"
        ),
        targeting_forecast_path=(
            root / "artifacts" / "targeting" / "per_symbol_forecast_skill.json"
        ),
        targeting_summary_path=(
            root / "artifacts" / "targeting" / "targeting_summary.json"
        ),
        output_path=(
            root / "artifacts" / "epistemic" / "epistemic_supervision_summary.json"
        ),
    )


def _assessment() -> dict[str, object]:
    robustness = {
        "robustness_score": 0.80,
        "independent_source_count": 4,
    }
    return {
        "artifact_type": "squeeze_bubble_symbol_assessment",
        "engine_version": "dopey-squeeze-bubble-intelligence-v2",
        "assessment_id": "squeeze-bubble:fixture",
        "symbol": "AAA",
        "decision_at_utc": DECISION_AT,
        "paper_only": True,
        "live_blocked": True,
        "order_construction_allowed": False,
        "evidence": {
            "integrity": {
                "observed_at_utc": DECISION_AT,
                "path_containment_verified": True,
                "technical_source_id": ("local:prices.csv:sha256:" + "a" * 64),
                "lane_observation_counts": [
                    ["technical", 252],
                    ["short_crowding", 2],
                    ["fundamentals", 1],
                    ["options", 100],
                ],
                "stale_lanes": [],
                "future_dated_lanes": [],
            },
            "fundamentals": {
                "theme": "technology",
                "days_since_first_trade": 30,
                "source_ids": [
                    "local:fundamentals.csv:sha256:" + "b" * 64,
                ],
            },
            "short_crowding": {
                "source_ids": [
                    "local:short.csv:sha256:" + "c" * 64,
                ],
            },
        },
        "squeeze": {
            "status": "squeeze_candidate_requires_existing_execution_gates",
            "direction": "bullish",
            "score": 0.80,
            "pressure_score": 0.85,
            "ignition_score": 0.75,
            "persistence_score": 0.70,
            "robustness": robustness,
            "observed_liquidity_stress": {"score": 0.60},
        },
        "bubble": {
            "status": "bubble_watch_or_blocked",
            "direction": "bearish",
            "score": 0.70,
            "fragility_score": 0.85,
            "unwind_trigger_score": 0.50,
            "extreme_pe_score": 0.90,
            "revenue_valuation_excess_score": 0.80,
            "ipo_reflexivity_score": 0.75,
            "persistence_score": 0.65,
            "robustness": robustness,
            "observed_liquidity_air_pocket": {"score": 0.55},
        },
    }


def _rankings() -> dict[str, object]:
    return {
        "artifact_type": "squeeze_bubble_candidate_rankings",
        "decision_at_utc": DECISION_AT,
        "queues": {
            "squeeze_candidates": ["squeeze-bubble:fixture"],
            "squeeze_watch": [],
            "bubble_unwind_candidates": [],
            "bubble_fragility_monitors": [],
            "bubble_watch": ["squeeze-bubble:fixture"],
        },
        "paper_only": True,
        "live_blocked": True,
        "order_construction_allowed": False,
    }


def _squeeze_summary() -> dict[str, object]:
    return {
        "artifact_type": "squeeze_bubble_intelligence_summary",
        "squeeze_bubble_status": "complete_research_only",
        "decision_at_utc": DECISION_AT,
        "paper_only": True,
        "live_blocked": True,
        "order_construction_allowed": False,
    }


def _family_skill() -> dict[str, object]:
    return {
        "verdict": "positive_verified",
        "effective_sample_size": 90,
        "mean_directional_excess_over_horizon_adjusted_drift": 0.03,
        "eras": [
            {
                "era": "pre_2020",
                "effective_samples": 30,
                "mean_directional_excess": 0.02,
            },
            {
                "era": "2020_2022",
                "effective_samples": 30,
                "mean_directional_excess": 0.03,
            },
            {
                "era": "2023_2026",
                "effective_samples": 30,
                "mean_directional_excess": 0.04,
            },
        ],
    }


def _targeting_registry(forecast_hash: str) -> dict[str, object]:
    body: dict[str, object] = {
        "artifact_type": "symbol_candidate_registry",
        "candidate_registry_version": "dopey-symbol-candidate-registry-v1",
        "candidate_count": 1,
        "candidates": [
            {
                "symbol": "AAA",
                "candidate_status": (
                    "targeting_shadow_eligible_for_forward_validation"
                ),
                "targeting_score": 0.80,
                "per_family_skill": {
                    "earnings_revision": _family_skill(),
                },
                "per_family_targeting_score": {
                    "earnings_revision": 0.80,
                },
                "order_capability_present": False,
            }
        ],
        "source_hashes": {
            "settlements": "1" * 64,
            "forecast_skill": forecast_hash,
        },
        "targeting_research_only": True,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return _content_addressed(body)


def _targeting_forecast() -> dict[str, object]:
    body: dict[str, object] = {
        "artifact_type": "per_symbol_forecast_skill",
        "per_symbol": {
            "AAA": {
                "per_family": {
                    "earnings_revision": _family_skill(),
                }
            }
        },
        "source_hashes": {"settlements": "1" * 64},
        "targeting_research_only": True,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return _content_addressed(body)


def _targeting_summary(registry_hash: str) -> dict[str, object]:
    return {
        "artifact_type": "symbol_targeting_summary",
        "targeting_status": (
            "complete_shadow_research_candidates_require_forward_validation"
        ),
        "observed_at_utc": DECISION_AT,
        "candidate_registry_generation_path": (
            f"C:/fixture/registry_generations/{registry_hash}.json"
        ),
        "targeting_research_only": True,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _write_complete_inputs(paths: EpistemicRuntimePaths) -> None:
    forecast = _targeting_forecast()
    forecast_hash = str(forecast["reproducibility_hash"])
    registry = _targeting_registry(forecast_hash)
    registry_hash = str(registry["reproducibility_hash"])
    _write_jsonl(paths.squeeze_assessments_path, (_assessment(),))
    _write_json(paths.squeeze_rankings_path, _rankings())
    _write_json(paths.squeeze_summary_path, _squeeze_summary())
    _write_json(paths.targeting_registry_path, registry)
    _write_json(paths.targeting_forecast_path, forecast)
    _write_json(
        paths.targeting_summary_path,
        _targeting_summary(registry_hash),
    )


def test_runtime_adapts_real_schemas_and_atomically_downgrades(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    paths = _paths(root)
    _write_complete_inputs(paths)

    first = run_epistemic_supervision(
        paths,
        default_epistemic_policy(),
        EVALUATED_AT,
    )
    persisted = json.loads(paths.output_path.read_text(encoding="utf-8"))
    second = run_epistemic_supervision(
        paths,
        default_epistemic_policy(),
        EVALUATED_AT,
    )

    assert first == second
    assert json.loads(json.dumps(first, sort_keys=True)) == persisted
    assert first["epistemic_status"] == "blocked_epistemic_claims_present"
    assert first["input_blocker_count"] == 0
    assert first["claim_count"] == 3
    assert set(first["source_claim_counts"]) == {
        "squeeze_assessments",
        "targeting_registry",
    }
    assert all(first["input_content_hashes"].values())
    assert first["research_only"] is True
    assert first["simulated_execution_separated"] is True
    assert first["promotion_allowed"] is False
    assert first["order_construction_allowed"] is False
    assert first["paper_only"] is True
    assert first["live_blocked"] is True
    assert first["source_artifacts_mutated"] is False
    assert not tuple(paths.output_path.parent.glob("*.tmp"))

    envelopes = {(row["symbol"], row["lane"]): row for row in first["claim_verdicts"]}
    squeeze = envelopes[("AAA", "squeeze")]
    assert squeeze["source_queue"] == "squeeze_candidates"
    assert {
        "crowding_without_independent_catalyst",
        "insufficient_independent_regimes",
    } <= set(squeeze["verdict"]["finding_reason_codes"])
    assert (
        "missing_evidence_source_identity"
        not in (squeeze["verdict"]["finding_reason_codes"])
    )
    assert (
        "missing_or_insufficient_denominator"
        not in (squeeze["verdict"]["finding_reason_codes"])
    )
    bubble = envelopes[("AAA", "bubble")]
    assert bubble["verdict"]["supervision_status"] == ("bubble_watch_or_blocked")
    targeting = envelopes[("AAA", "targeting")]
    assert (
        "non_point_in_time_evidence" in (targeting["verdict"]["finding_reason_codes"])
    )


def test_missing_inputs_write_one_fail_closed_summary(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    paths = _paths(root)

    result = run_epistemic_supervision(
        paths,
        default_epistemic_policy(),
        EVALUATED_AT,
    )

    assert result["epistemic_status"] == ("blocked_missing_or_invalid_epistemic_inputs")
    assert result["input_blocker_count"] == 6
    assert result["claim_count"] == 0
    assert paths.output_path.is_file()
    assert len(tuple(paths.output_path.parent.glob("*.json"))) == 1
    assert result["promotion_allowed"] is False
    assert result["live_blocked"] is True


def test_invalid_declared_targeting_hash_blocks_runtime(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    paths = _paths(root)
    _write_complete_inputs(paths)
    forecast = _targeting_forecast()
    registry = _targeting_registry(str(forecast["reproducibility_hash"]))
    registry["reproducibility_hash"] = "0" * 64
    _write_json(paths.targeting_registry_path, registry)

    result = run_epistemic_supervision(
        paths,
        default_epistemic_policy(),
        EVALUATED_AT,
    )

    assert result["epistemic_status"] == ("blocked_missing_or_invalid_epistemic_inputs")
    assert "registry_content_hash_invalid" in {
        blocker["reason_code"] for blocker in result["input_blockers"]
    }
    assert result["promotion_allowed"] is False


def test_stale_degraded_producer_cycle_cannot_reuse_prior_artifacts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    paths = _paths(root)
    _write_complete_inputs(paths)
    degraded_summary = _squeeze_summary()
    degraded_summary["squeeze_bubble_status"] = "degraded"
    degraded_summary["decision_at_utc"] = "2026-07-10T15:00:00+00:00"
    _write_json(paths.squeeze_summary_path, degraded_summary)

    result = run_epistemic_supervision(
        paths,
        default_epistemic_policy(),
        EVALUATED_AT,
    )
    reason_codes = {blocker["reason_code"] for blocker in result["input_blockers"]}

    assert result["epistemic_status"] == ("blocked_missing_or_invalid_epistemic_inputs")
    assert {
        "artifact_timestamp_stale",
        "squeeze_cycle_timestamp_mismatch",
        "squeeze_producer_not_complete",
    } <= reason_codes
    assert result["promotion_allowed"] is False


def test_path_escape_fails_before_any_output(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    paths = _paths(root)
    escaped = EpistemicRuntimePaths(
        repository_root=root,
        squeeze_assessments_path=tmp_path / "outside.jsonl",
        squeeze_rankings_path=paths.squeeze_rankings_path,
        squeeze_summary_path=paths.squeeze_summary_path,
        targeting_registry_path=paths.targeting_registry_path,
        targeting_forecast_path=paths.targeting_forecast_path,
        targeting_summary_path=paths.targeting_summary_path,
        output_path=paths.output_path,
    )

    with pytest.raises(
        ValueError,
        match="epistemic runtime path escapes repository root",
    ):
        run_epistemic_supervision(
            escaped,
            default_epistemic_policy(),
            EVALUATED_AT,
        )

    assert not paths.output_path.exists()


def test_runtime_source_has_no_execution_or_live_imports() -> None:
    source_path = Path(epistemic_runtime.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not {
        module
        for module in imported_modules
        if module.startswith(
            (
                "dopey_execution",
                "dopey_live",
                "dopey_broker_readiness",
            )
        )
    }


def test_supervisor_stage_uses_current_producer_artifact_bindings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from dopey_autonomy import run_resilient_research_supervisor as supervisor
    from dopey_squeeze_bubble import runtime as squeeze_runtime
    from dopey_targeting import runtime as targeting_runtime

    root = tmp_path / "isolated"
    squeeze_root = root / "artifacts" / "dopey" / "squeeze_bubble"
    targeting_root = root / "artifacts" / "dopey" / "targeting"
    monkeypatch.setattr(
        squeeze_runtime,
        "ASSESSMENTS_PATH",
        squeeze_root / "symbol_assessments.jsonl",
    )
    monkeypatch.setattr(
        squeeze_runtime,
        "RANKINGS_PATH",
        squeeze_root / "candidate_rankings.json",
    )
    monkeypatch.setattr(
        squeeze_runtime,
        "SUMMARY_PATH",
        squeeze_root / "squeeze_bubble_summary.json",
    )
    monkeypatch.setattr(
        targeting_runtime,
        "CANDIDATE_REGISTRY_PATH",
        targeting_root / "symbol_candidate_registry.json",
    )
    monkeypatch.setattr(
        targeting_runtime,
        "FORECAST_SKILL_PATH",
        targeting_root / "per_symbol_forecast_skill.json",
    )
    monkeypatch.setattr(
        targeting_runtime,
        "SUMMARY_PATH",
        targeting_root / "targeting_summary.json",
    )

    observed: dict[str, object] = {}

    def capture(
        paths: EpistemicRuntimePaths,
        _policy: object,
        evaluated_at: datetime,
    ) -> dict[str, object]:
        observed["paths"] = paths
        observed["evaluated_at"] = evaluated_at
        return {"epistemic_status": "blocked_fixture"}

    monkeypatch.setattr(epistemic_runtime, "run_epistemic_supervision", capture)

    result = supervisor._stage_epistemic_supervision()

    assert result == {"epistemic_status": "blocked_fixture"}
    paths = observed["paths"]
    assert isinstance(paths, EpistemicRuntimePaths)
    assert paths.repository_root == root
    assert paths.squeeze_assessments_path == squeeze_runtime.ASSESSMENTS_PATH
    assert paths.squeeze_rankings_path == squeeze_runtime.RANKINGS_PATH
    assert paths.squeeze_summary_path == squeeze_runtime.SUMMARY_PATH
    assert paths.targeting_registry_path == targeting_runtime.CANDIDATE_REGISTRY_PATH
    assert paths.targeting_forecast_path == targeting_runtime.FORECAST_SKILL_PATH
    assert paths.targeting_summary_path == targeting_runtime.SUMMARY_PATH
    assert paths.output_path == (
        root
        / "artifacts"
        / "dopey"
        / "epistemic_supervision"
        / "epistemic_supervision_summary.json"
    )
