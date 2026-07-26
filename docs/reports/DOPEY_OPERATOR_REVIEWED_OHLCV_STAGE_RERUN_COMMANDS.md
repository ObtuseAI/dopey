# DOPEY Operator Reviewed OHLCV Stage Rerun Commands

```powershell
python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun
python -m dopey_data_ingestion.run_operator_ohlcv_source_review_contract
python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_manifest_candidate
python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft
python -m dopey_data_ingestion.run_manual_ohlcv_preflight_linter
python -m dopey_data_ingestion.run_local_ohlcv_import_validator
python -m dopey_data.run_real_ohlcv_history_spine_activation
python -m dopey_analysis.run_real_signal_validation_gate
python -m dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack
```

No curl, wget, browser automation, API, Alpha Vantage, broker, credential setup, or `.env` commands are part of this packet.
