from __future__ import annotations

from tests.test_local_free_ohlcv_import_validator_and_history_activation import _temporarily_clear_staging

from dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun import run_operator_reviewed_ohlcv_stage_rerun


def test_operator_stage_max_progress_compatibility_shard() -> None:
    with _temporarily_clear_staging():
        summary = run_operator_reviewed_ohlcv_stage_rerun()
    # Restore artifacts to the actual staged-data state for later tests in the
    # session-scoped isolated tree.
    run_operator_reviewed_ohlcv_stage_rerun()

    # All three are honest no-promotion outcomes from the stage's own status
    # vocabulary (operator_reviewed_ohlcv_stage_models.ALLOWED_*): nothing
    # staged, no review packet, or validation passed without promotion.
    assert summary["operator_reviewed_stage_status"] in {
        "operator_files_missing",
        "operator_review_packet_missing",
        "real_signal_validation_passed_no_promotion",
    }
    assert summary["valid_real_dataset"] is False or summary["strategy_promotion_allowed"] is False
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["broker_connection_used"] is False
    assert summary["not_profitability_claim"] is True
    assert summary["not_live_ready"] is True
    assert summary["strategy_promotion_allowed"] is False
