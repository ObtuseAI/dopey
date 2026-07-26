"""Candidate pipeline verdict logic + the playbook stage's soft study read.

The pipeline may refuse or keep accruing; it must never promote. The playbook
stage treats a missing study as a normal accruing state.
"""
from __future__ import annotations

import json
from pathlib import Path

import importlib

from operator_tools import operator_compression_candidate_pipeline as pipeline

# the package re-exports the same-named FUNCTION, shadowing attribute-style
# module imports - resolve the module itself explicitly
stage = importlib.import_module(
    "dopey.strategy_engineering.run_playbook_research_stage"
)


def _study(range_ok: bool, direction_ok: bool) -> dict:
    return {
        "range_question": {
            "survives_both_eras_same_sign_above_null": range_ok,
            "train": {"era_status": "evaluated"},
            "validation": {"era_status": "evaluated"},
        },
        "direction_question": {
            "directional_claim_supported": direction_ok,
            "train": {"era_status": "evaluated", "events": 100},
            "validation": {"era_status": "evaluated", "events": 80},
        },
        "parameters": {"BB_SQUEEZE_WINDOW": 20.0},
    }


def _run_with(monkeypatch, tmp_path: Path, range_ok: bool, direction_ok: bool) -> dict:
    monkeypatch.setattr(
        pipeline, "run_compression_expansion_study", lambda: _study(range_ok, direction_ok)
    )
    monkeypatch.setattr(pipeline, "TRUST_PATH", tmp_path / "trust.json")
    monkeypatch.setattr(pipeline, "VERDICT_PATH", tmp_path / "verdict.json")
    return pipeline.run_pipeline()


def test_no_claims_supported_yields_research_only_verdict(tmp_path, monkeypatch) -> None:
    result = _run_with(monkeypatch, tmp_path, range_ok=False, direction_ok=False)
    assert result["verdict"] == (
        "no_historical_claim_supported_detections_accrue_as_research_only"
    )
    assert result["promotion_allowed"] is False
    written = json.loads((tmp_path / "verdict.json").read_text(encoding="utf-8"))
    assert written["artifact_type"] == "compression_candidate_verdict"


def test_range_only_yields_directional_refusal(tmp_path, monkeypatch) -> None:
    result = _run_with(monkeypatch, tmp_path, range_ok=True, direction_ok=False)
    assert result["verdict"] == "range_claim_supported_directional_claim_refused"


def test_both_supported_still_requires_forward_settlement(tmp_path, monkeypatch) -> None:
    result = _run_with(monkeypatch, tmp_path, range_ok=True, direction_ok=True)
    assert result["verdict"] == (
        "historical_support_forward_settlement_must_still_earn_trust"
    )
    assert result["promotion_allowed"] is False


def test_missing_trust_history_is_a_named_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "TRUST_PATH", tmp_path / "absent.json")
    assert pipeline._setup_trust("bb_squeeze_breakout") == {
        "trust_status": "no_settlement_history_yet"
    }


def test_stale_trust_version_is_not_consumed(tmp_path, monkeypatch) -> None:
    trust_path = tmp_path / "trust.json"
    trust_path.write_text(
        json.dumps(
            {
                "playbook_trust_version": "dopey-playbook-trust-v1",
                "per_setup": {
                    "bb_squeeze_breakout": {
                        "trust_state": "rated",
                        "contested_settled": 100,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "TRUST_PATH", trust_path)

    trust = pipeline._setup_trust("bb_squeeze_breakout")

    assert trust["trust_status"] == "incompatible_trust_version"


def test_stage_context_reports_missing_study_as_not_yet_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "dopey.strategy_engineering.compression_expansion_study.STUDY_PATH",
        tmp_path / "absent.json",
    )
    assert stage._compression_study_context() == {"study_status": "not_yet_run"}


def test_stage_context_surfaces_study_flags(tmp_path, monkeypatch) -> None:
    study_path = tmp_path / "study.json"
    study_path.write_text(
        json.dumps(
            {
                "study_version": "dopey-compression-expansion-study-v1",
                "range_question": {"survives_both_eras_same_sign_above_null": True},
                "direction_question": {"directional_claim_supported": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dopey.strategy_engineering.compression_expansion_study.STUDY_PATH", study_path
    )
    context = stage._compression_study_context()
    assert context["study_status"] == "present"
    assert context["range_question_survives"] is True
    assert context["directional_claim_supported"] is False
