"""Integration coverage for provenance-only repository capability intake."""

from __future__ import annotations

from pathlib import Path

from dopey_acceleration.capability_foundry import (
    CATALOG_PATH,
    build_capability_foundry_snapshot,
)


def test_repository_foundry_covers_org_and_quarantines_every_external_capability(
    tmp_path: Path,
) -> None:
    snapshot = build_capability_foundry_snapshot(
        CATALOG_PATH,
        tmp_path / "latest_snapshot.json",
    )
    candidates = {
        record["repository"]: record for record in snapshot["ranked_candidates"]
    }

    assert {
        "ObtuseAI/blunder",
        "ObtuseAI/dimwit",
        "ObtuseAI/doofus",
        "ObtuseAI/dummy",
        "ObtuseAI/nimrod",
        "ObtuseAI/universal-sports-engine",
    } <= set(candidates)
    assert snapshot["source_count"] == len(candidates)
    assert snapshot["obtuseai_internal_source_count"] == 6
    assert snapshot["external_oss_source_count"] >= 20
    assert snapshot["foreign_source_files_downloaded"] is False
    assert snapshot["foreign_code_executed"] is False
    assert snapshot["packages_installed"] is False
    assert snapshot["automatic_installation_allowed"] is False
    assert snapshot["automatic_source_copy_allowed"] is False
    assert snapshot["automatic_activation_allowed"] is False
    assert snapshot["readiness_effect"] == "none"
    assert snapshot["execution_effect"] == "none"
    assert snapshot["trade_authority_effect"] == "none"
    assert all(
        record["runtime_capability_status"] == "not_observed_usable"
        and record["provenance_gate_passed"] is False
        and record["remote_commit_ref_verified"] is False
        and record["license_blob_verified"] is False
        and record["capability_evidence_paths_verified"] is False
        and record["automatic_installation_allowed"] is False
        and record["automatic_source_copy_allowed"] is False
        and record["automatic_activation_allowed"] is False
        for record in candidates.values()
    )
    assert snapshot["remote_provenance_verification_status"] == (
        "not_performed_by_offline_foundry"
    )
    assert candidates["ObtuseAI/universal-sports-engine"]["adoption_mode"] == (
        "direct_reuse_candidate_with_attribution"
    )
    assert candidates["ObtuseAI/dummy"]["adoption_mode"] == (
        "architecture_reference_only"
    )
    assert candidates["nautechsystems/nautilus_trader"]["adoption_mode"] == (
        "subprocess_or_service_boundary_pilot_only"
    )
    assert snapshot["capability_graph"]["graph_status"] == "derived_index_not_truth"
    assert snapshot["priority_slices"]
