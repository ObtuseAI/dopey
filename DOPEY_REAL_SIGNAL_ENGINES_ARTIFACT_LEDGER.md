# DOPEY Real Signal Engines Artifact Ledger

## Source Files
- `dopey_analysis/signal_models.py`
- `dopey_analysis/technical_signal_engine.py`
- `dopey_analysis/history_signal_adapter.py`
- `dopey_analysis/run_real_signal_engines.py`
- `tests/test_real_signal_engines.py`

## Fixture Files
- `C:\Users\CH\dopey\dopey_data\fixtures\signals\sample_price_series.json` sha256=`f86edd4b6568f4b7400111b6ade47c9ef264711d1f4ffa2292396f30dce20059`
- `C:\Users\CH\dopey\dopey_data\fixtures\signals\sample_benchmark_series.json` sha256=`68ee7f5e2bf20650035289b2043d2749fb03ad01c98200f60fde439d141097b6`
- `C:\Users\CH\dopey\dopey_data\fixtures\signals\signal_expected_math_cases.json` sha256=`951725d41d83a1f566ae1387fd6752c9b012d361261529555e0fe63c2d01b2b1`

## Artifact Files
- `C:\Users\CH\dopey\artifacts\dopey\signals\signal_engine_input_summary.json` records=`1` sha256=`7f9d7008cf8fb45de073874bf46c29af07267e9cc51b0827d59589af600dff59`
- `C:\Users\CH\dopey\artifacts\dopey\signals\momentum_signals.jsonl` records=`10` sha256=`4c82d674b0f2fcab5f5a57c5334d41ed29c36147bfdeca93e3184139ca6aa0db`
- `C:\Users\CH\dopey\artifacts\dopey\signals\breakout_signals.jsonl` records=`20` sha256=`be7ac870b4b510f044fe2cca0b14288c5d818610ade9165348ff03510b83fc58`
- `C:\Users\CH\dopey\artifacts\dopey\signals\fakeout_signals.jsonl` records=`10` sha256=`892446e80c37aa252ead38849701c3f54a6b74f0719c09eec9dcfb48eb9ccbbf`
- `C:\Users\CH\dopey\artifacts\dopey\signals\trend_pullback_signals.jsonl` records=`10` sha256=`59110b28bf77207544eee612fd13a4e847124a1960d9ff22cd04aa2166fc8846`
- `C:\Users\CH\dopey\artifacts\dopey\signals\volatility_regime_signals.jsonl` records=`10` sha256=`e0d669cfd070bd9e1f5fef0f84de135335d281370955d49a4a34389aa0e25674`
- `C:\Users\CH\dopey\artifacts\dopey\signals\relative_strength_signals.jsonl` records=`10` sha256=`c09dea6d35e1fc372f31696c6257ede01264b694f7810635115d53b88ba1961e`
- `C:\Users\CH\dopey\artifacts\dopey\signals\market_regime_signals.jsonl` records=`10` sha256=`fd7873c666ab28beef7e8bfd14433f709d19f1c0df57389e8841e3d6d8d759aa`
- `C:\Users\CH\dopey\artifacts\dopey\signals\directional_setup_signals.jsonl` records=`80` sha256=`b777d2b8e3487ca400df0a49fdc0dd132a818b796c4f4260beda2658f62e6f5f`
- `C:\Users\CH\dopey\artifacts\dopey\signals\signal_quality_flags.jsonl` records=`3` sha256=`07e19bec16e6b2ceabe11bb757eeaa15597cfce31cfbfb8e52bf5bc07245a70d`
- `C:\Users\CH\dopey\artifacts\dopey\signals\signal_engine_summary.json` records=`1` sha256=`7f98b5b42650870c401ddfe1952dd044094273cac20fe9ac304dcd703da73c47`
- `C:\Users\CH\dopey\artifacts\dopey\signals\signal_engine_proof.jsonl` records=`1` sha256=`780b23b237497ca86847164b7cb6be7eaf723171ef46393b8bdd9cdec620a277`

## Record Counts
- fixture_only_case_count: `80`
- local_real_history_case_count: `194451`
- signal_family_distribution: `{'breakout': 20, 'directional_setup': 80, 'fakeout': 10, 'market_regime': 10, 'momentum': 10, 'relative_strength': 10, 'trend_pullback': 10, 'volatility_regime': 10}`
- direction_distribution: `{'bearish': 70, 'bullish': 70, 'neutral': 20}`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- not_real_edge_evidence: `true`
- no broker, credentials, scheduler, real sizing, or orders created

## Run Hash
- signal_engine_summary.run_hash: `cce58d41ce26ba768f97e6734cd0157719faabff0cb202fe05fd9fbb7df94d85`
