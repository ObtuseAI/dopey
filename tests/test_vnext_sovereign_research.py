"""Integration coverage for the governed DOPEY vNext vertical slice."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from dopey.macro import credit as credit_module
from dopey.technical import history_adapter
from dopey.constitution.execution_seal import (
    ExecutionSealViolation,
    assert_capabilities_research_only,
    assert_output_research_only,
)
from dopey.constitution.mutation_protection import (
    MutationProtectionViolation,
    assert_mutation_proposal_safe,
)
from dopey.runtime.vnext_research import VNextRunPaths, run_vnext_research
from dopey.technical.history_adapter import load_validated_symbol_history
from dopey_data.history_store import load_history_manifest, resolve_history_data_file_path
from tests.public_source_fixtures import (
    build_synthetic_history_rows,
    write_empty_vnext_governed_inputs,
    write_synthetic_history_manifest,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
VNEXT_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vnext"
FIXTURE_MANIFEST_CREATED_AT = "2026-07-14T20:45:00+00:00"


def _run_paths(output_dir: Path) -> VNextRunPaths:
    repository_root = output_dir.parent / "repository"
    governed = write_empty_vnext_governed_inputs(
        repository_root,
        FIXTURE_MANIFEST_CREATED_AT,
    )
    return VNextRunPaths(
        output_dir=output_dir,
        cross_asset_context=VNEXT_FIXTURE_ROOT / "cross_asset_context.json",
        news_context=VNEXT_FIXTURE_ROOT / "news_context.json",
        calibration_summary=VNEXT_FIXTURE_ROOT / "calibration_summary.json",
        cross_section_context=VNEXT_FIXTURE_ROOT / "cross_sectional_context.json",
        macro_manifest=governed["macro_manifest"],
        fundamental_file_reference="dopey_data/real/raw/macro_context/fundamentals.csv",
        options_manifest=governed["options_manifest"],
        earnings_directory=governed["earnings_directory"],
    )


def _causally_valid_event_time(paths: VNextRunPaths) -> str:
    news = json.loads(paths.news_context.read_text(encoding="utf-8"))
    timestamps = [
        datetime.fromisoformat(str(news["decision_time"]).replace("Z", "+00:00")),
    ]
    for manifest_path in (paths.macro_manifest, paths.options_manifest):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        timestamps.append(
            datetime.fromisoformat(str(manifest["created_at"]).replace("Z", "+00:00"))
        )
    return (max(timestamps) + timedelta(minutes=1)).isoformat()


def test_vnext_one_symbol_vertical_slice_is_deterministic_and_abstains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _run_paths(tmp_path / "vnext")
    history_manifest = write_synthetic_history_manifest(
        tmp_path / "history",
        "SPY",
        build_synthetic_history_rows("SPY", 260),
    )
    monkeypatch.setattr(history_adapter, "HISTORY_MANIFEST_PATH", history_manifest)
    monkeypatch.setattr(credit_module, "HISTORY_MANIFEST_PATH", history_manifest)
    event_time = _causally_valid_event_time(paths)
    first = run_vnext_research(
        "SPY",
        "breakout",
        event_time,
        "2026-07-14T20:00:00+00:00",
        paths,
    )
    second = run_vnext_research(
        "SPY",
        "breakout",
        event_time,
        "2026-07-14T20:00:00+00:00",
        paths,
    )

    assert first["reproducibility_hash"] == second["reproducibility_hash"]
    assert first["technical_measurement_count"] >= 144
    assert first["agent_count"] == 15
    assert first["final_research_control"] == "ABSTAIN"
    assert first["closed_loop_control"] == "TERMINATE"
    assert first["metabolism_termination"] is True
    assert first["action_ready"] is False
    assert first["strategy_promotion_allowed"] is False
    assert first["paper_only"] is True and first["live_blocked"] is True
    assert first["confidence"]["final_research_confidence"] <= first["confidence"]["weakest_critical_value"]
    assert second["prediction_append_status"] == "already_present_identical"
    assert len((paths.output_dir / "forward_predictions.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    technical = json.loads((paths.output_dir / "technical_evidence.json").read_text(encoding="utf-8"))
    assert technical["intraday_status"] == "unavailable_no_validated_local_intraday_history_not_synthesized"
    assert all(record["not_trade_decision"] is True for record in technical["measurements"])
    evidence_contracts = {
        "fundamental_evidence.json": {
            "validated_fundamental_evidence",
            "fundamental_data_gap",
        },
        "options_surface_evidence.json": {
            "validated_options_surface",
            "options_surface_data_gap",
        },
        "earnings_event_evidence.json": {
            "validated_earnings_event",
            "earnings_event_data_gap",
        },
        "credit_proxy_evidence.json": {
            "validated_credit_proxy",
            "credit_proxy_data_gap",
        },
    }
    evidence_records: dict[str, dict[str, object]] = {}
    for filename, allowed_types in evidence_contracts.items():
        record = json.loads((paths.output_dir / filename).read_text(encoding="utf-8"))
        evidence_records[filename] = record
        assert record["evidence_type"] in allowed_types
        assert record["evidence_status"]
        assert record["evidence_id"] and record["content_hash"]
        assert record["limitations"]
        assert record["not_trade_decision"] is True
        assert record["not_readiness_evidence"] is True
        assert record["paper_only"] is True and record["live_blocked"] is True
    assert evidence_records["options_surface_evidence.json"]["dealer_position_inference_allowed"] is False
    organism_episode = json.loads((paths.output_dir / "organism_episode.json").read_text(encoding="utf-8"))
    evidence_ids_by_agent = {
        record["agent_id"]: set(record["evidence_ids"])
        for record in organism_episode["agent_results"]
    }
    assert evidence_records["fundamental_evidence.json"]["evidence_id"] in evidence_ids_by_agent[
        "fundamental_context_agent"
    ]
    assert evidence_records["options_surface_evidence.json"]["evidence_id"] in evidence_ids_by_agent[
        "options_context_agent"
    ]


def test_vnext_execution_and_mutation_boundaries_fail_closed() -> None:
    with pytest.raises(ExecutionSealViolation):
        assert_capabilities_research_only(("read_typed_local_evidence", "place_order"))
    with pytest.raises(ExecutionSealViolation):
        assert_output_research_only({"paper_only": True, "live_blocked": True, "action_ready": True})
    with pytest.raises(MutationProtectionViolation):
        assert_mutation_proposal_safe(
            {
                "surface": "readiness_gate",
                "auto_apply": False,
                "promotion_state": "SHADOW_ONLY",
            }
        )
    assert_mutation_proposal_safe(
        {
            "surface": "agent_composition",
            "auto_apply": False,
            "promotion_state": "SHADOW_ONLY",
        }
    )


def test_vnext_symbol_adapter_rejects_hash_mismatch(tmp_path: Path) -> None:
    source_manifest = write_synthetic_history_manifest(
        tmp_path / "source_history",
        "SPY",
        [
            {
                "date": "2026-07-13",
                "symbol": "SPY",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "adjusted_close": 100.5,
                "volume": 1_000_000,
                "source": "integration_test_only_not_readiness_evidence",
            }
        ],
    )
    manifest = load_history_manifest(source_manifest)
    file_ref = next(file_ref for file_ref in manifest.data_files if "SPY" in file_ref.symbols)
    source_path = resolve_history_data_file_path(source_manifest, manifest, file_ref)
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    shutil.copy2(source_path, raw_directory / source_path.name)
    record = manifest.to_dict()
    record["raw_data_directory"] = "raw"
    record["data_files"] = [
        {
            **file_ref.to_dict(),
            "path": source_path.name,
            "sha256": "0" * 64,
        }
    ]
    record["required_universe"] = ["SPY"]
    target = tmp_path / "history_dataset_manifest.json"
    target.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the manifest"):
        load_validated_symbol_history("SPY", target)
