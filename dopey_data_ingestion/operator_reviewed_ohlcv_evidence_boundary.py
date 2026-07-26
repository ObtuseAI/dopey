"""Write the evidence boundary for operator-reviewed OHLCV stage reruns."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_reviewed_ohlcv_stage_models import OPERATOR_REVIEWED_OHLCV_STAGE_VERSION, OperatorReviewedOhlcvEvidenceBoundary


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
EVIDENCE_BOUNDARY_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_evidence_boundary.json"


def write_operator_reviewed_ohlcv_evidence_boundary() -> dict[str, Any]:
    record = OperatorReviewedOhlcvEvidenceBoundary(
        artifact_type="operator_reviewed_ohlcv_evidence_boundary",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        boundary_id="operator-reviewed-ohlcv-evidence-boundary-v1",
        ohlcv_evidence_possible_only_after_validator_pass=True,
        history_activation_required_for_real_history=True,
        real_signal_validation_required_for_signal_evidence=True,
        not_options_evidence=True,
        not_options_quote_evidence=True,
        not_quote_priced_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        not_strategy_promotion=True,
        paper_only=True,
        live_blocked=True,
        broker_connection_used=False,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        boundary_hash="",
    ).to_dict()
    _write_json(EVIDENCE_BOUNDARY_PATH, record)
    return {**record, "artifact_path": str(EVIDENCE_BOUNDARY_PATH)}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
