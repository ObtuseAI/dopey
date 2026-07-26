# DOPEY Real Data Activation V8 Artifact Ledger

## Safety State
- paper_only: `true`; live_blocked: `true`; promotion_allowed: `false`
- no broker, credentials, .env, orders, scheduler, or real sizing

## Source (new)
- `dopey_analysis/real_history_signal_engine.py` records=`1` sha256=`d6ce8c3585d77a3b3a539a0371d0fb62a151149c61635657a8cae94427b5ae71`
- `dopey_analysis/run_real_history_signal_engine.py` records=`1` sha256=`dc82e1d5808ebb57aaf8a0e2b6235652e4cd9c183ffe445bbbf2c070bbbfdbe9`
- `dopey_backtest/real_history_honest_backtester.py` records=`1` sha256=`a1cf6f2dfe92df6b4775da383c5f4861d84e298b2a6eed71440bc53ecc6e8bfe`
- `dopey_backtest/run_real_history_honest_backtester.py` records=`1` sha256=`553dd15d516d9e2feae2a1a97366b907a9f976009c3cf73537ea1c19087ea927`
- `tests/test_real_history_lane.py` records=`1` sha256=`c9d89a87f7d7ae54b9548aa204cdd92576e5c5b29f36c816922719f27ff6e91b`

## Source (repaired)
- `dopey_data_ingestion/local_ohlcv_quality_validator.py` records=`1` sha256=`6526c960d697a543e48c7d2badb663bfc80fc6be325b39e95072f354295f1d4b`
- `dopey_signal_research/research_candidate_generator_v7.py` records=`1` sha256=`705790a21e48c2a36cb4fa22be2e1f2c879fd50bd560c3c22e3a6df287b85f7e`
- `dopey_signal_research/research_path_simulator_v7.py` records=`1` sha256=`24efb621aad59f8db946694233d59c3c5cef7e39bccc19dd8c43a24ffcc6a653`
- `tests/test_local_free_ohlcv_import_validator_and_history_activation.py` records=`1` sha256=`c573c110527c40ba5ee89c091adc3f826c70b60ef200528c1ad87cdf3f8fc627`
- `tests/test_real_signal_engines.py` records=`1` sha256=`b7ef825b9aa92564c2222b2bf50c5a5a32c12fd236b51c2469aba47403816d15`
- `tests/test_honest_backtester.py` records=`1` sha256=`262f80624f85358d96744312ecb4238aa12e0baa4843a1bbc26280bc21bc4e53`
- `tests/test_public_signal_research_breakthrough_v7.py` records=`1` sha256=`dc38a5c27013ceff7ce9c51f6dc08fa0f46da23f0f0ab5372168aa7bb4aed226`

## Manifests
- `dopey_data/real/manifests/real_data_manifest.json` records=`1` sha256=`962c1fa5b25512a30cfc4dd048861468bccec07067b5727a8aa686700a2914c7`
- `dopey_data/history/history_dataset_manifest.json` records=`1` sha256=`8d337dd5e10976d821d185dd1cf988594befb61f6a8a85b72ab54a281c46c0f7`

## Key artifacts (gitignored, regenerable)
- `artifacts/dopey/history/history_spine_summary.json` records=`1` sha256=`17c3cb04b791d9898fff37498c14b133deecff85f109448bdab102a3cb9101ac`
- `artifacts/dopey/signals/real_history_signal_engine_summary.json` records=`1` sha256=`5a6bcaaebf70b557581e7a4aec57c13eb29e749c0f00ccb751b06a77bd219152`
- `artifacts/dopey/signals/directional_setup_signals.jsonl` records=`46690` sha256=`05b4f66a9ead87fa3313934c3be4cde80d645c2d9997d24ff90e8ed58f988841`
- `artifacts/dopey/backtest/backtest_run_summary.json` records=`1` sha256=`241623eb9de4b04275a8baf4913e072cbf2965b9fc054276b351517d32cab9ce`
- `artifacts/dopey/backtest/backtest_trade_records.jsonl` records=`9333` sha256=`ddbb426d9e991d5b735a15fa3a5ee447a0a8e482ecb297c6d2cb020596471568`
- `artifacts/dopey/backtest/real_history_cohort_scoreboard.jsonl` records=`11` sha256=`d9f11640a6a8266d77ae5dc1b0503d19d9d4ff317fb920b94b5aed5bb1fced83`
- `artifacts/dopey/stats/statistical_truth_summary.json` records=`1` sha256=`207c3bb018a1d0309e31fada65157548158a15644a55a4ebf40d41b2f199d63b`
- `artifacts/dopey/fitness/fitness_decision.json` (see fitness artifact dir)

## Staged Real Data (24 files each location)
- `dopey_data/history/raw`: files=`24` total_rows=`185453`
- `dopey_data/real/raw/daily_ohlcv`: files=`23` total_rows=`176257`
- `dopey_data/real/raw/market_context`: files=`1` total_rows=`9196`
