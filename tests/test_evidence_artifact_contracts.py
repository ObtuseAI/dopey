"""Fail-closed integration coverage for the evidence artifact contract registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey.protocols.artifact_contracts import (
    ArtifactContractError,
    assert_artifact_record,
    validate_artifact_record,
    write_artifact_contract_registry,
)


def test_contract_registry_emits_schemas_and_rejects_authority_drift(tmp_path: Path) -> None:
    registry = write_artifact_contract_registry(tmp_path / "contracts")
    valid_record: dict[str, object] = {
        "artifact_type": "strategy_capital_exposure_diagnostics",
        "normalization_status": "complete_model_premium_diagnostic",
        "candidate_count": 1,
        "candidate_diagnostics": [],
        "annualized_return_available": False,
        "profitability_claim_allowed": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }

    assert registry["contract_count"] >= 6
    assert validate_artifact_record("capital_exposure", valid_record)["contract_status"] == "complete"
    assert json.loads((tmp_path / "contracts" / "capital_exposure.schema.json").read_text(encoding="utf-8"))["properties"]["promotion_allowed"]["const"] is False

    unsafe_record = dict(valid_record)
    unsafe_record["promotion_allowed"] = True
    with pytest.raises(ArtifactContractError, match="field_const_mismatch"):
        assert_artifact_record("capital_exposure", unsafe_record)
