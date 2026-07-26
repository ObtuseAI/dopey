# DOPEY Honest Backtester Artifact Ledger

## Source Files
- `dopey_backtest/backtest_models.py`
- `dopey_backtest/signal_trade_mapper.py`
- `dopey_backtest/model_priced_trade_simulator.py`
- `dopey_backtest/honest_backtester.py`
- `dopey_backtest/run_honest_backtester.py`
- `tests/test_honest_backtester.py`

## Fixture Files
- `C:\Users\CH\dopey\dopey_data\fixtures\backtest\backtest_expected_math_cases.json` records=`24` sha256=`eba8a68ae85035ad71885a7f04f17de9b90c41faf1f617f221c04b422a47abda`
- `C:\Users\CH\dopey\dopey_data\fixtures\backtest\backtest_policy_cases.json` records=`28` sha256=`f49c7c041c71649e235ca2f76540a1256a8738105e4a869153221fab14046f97`
- `C:\Users\CH\dopey\dopey_data\fixtures\backtest\backtest_exit_cases.json` records=`15` sha256=`eb82bd2d5ddaa2688034b40005fbea9db3b3e2f370827169f678439a190255a3`

## Artifact Files
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_signal_inputs.jsonl` records=`80` sha256=`100683b1ac9411d3b861ef00efd8756695d2b2744f2007230f7f76670c8697a1`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_trade_intents.jsonl` records=`80` sha256=`27954aef5587f10c632b49a15b3a36d7550d09da1e3dd9e52010f8fcccf5d3d8`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_entry_decisions.jsonl` records=`80` sha256=`228074ec5f1555a57c37498d27657ddd7dd693fef8983da5cd79ea8e397bbc8b`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_exit_decisions.jsonl` records=`80` sha256=`b6d8e716ae1a9c4ea0611b368b41c781150e70a8b731e83a565a65275dd87490`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_position_states.jsonl` records=`165` sha256=`7ee4ee32067a411988075d022a82729a0956ce458214d0ede4aedec78dbb83d6`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_mark_records.jsonl` records=`165` sha256=`d5b57ee0129f7a59000e1e56bb55b074da1cf2392d712fc5c6b145ec8764e6e3`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_trade_records.jsonl` records=`55` sha256=`128bd0b6231e46ebd84a82921f90ff4b8eca9b3c778ecd09e02f626d06c6e2ff`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_quality_flags.jsonl` records=`5` sha256=`677726e788c9fb9f4228bf1d7b56155901d75d278e7a8fab50189e22cf4bc7e8`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_run_summary.json` records=`1` sha256=`2d1d07341be0b7f46fbafc83df585ce42b6bc59f25191bc3ae4c7daa422f1d8a`
- `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_proof.jsonl` records=`1` sha256=`d9917d8ab5af298c956cb932a82eec17e2cbd419ef40fa8d1ce0454280c8bae6`

## Record Counts
- trade_intent_count: `80`
- trade_record_count: `55`
- long_call_trade_count: `25`
- long_put_trade_count: `30`
- no_trade_count: `25`
- model_priced_trade_count: `55`
- quote_priced_trade_count: `0`

## Hashes
- backtest_run_summary.run_hash: `8f00dfa1434ea9b18f859eae31dc6a6103b0283c418c318a8e2fca7033ec636e`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- not_real_backtest_evidence: `true`
- not_profitability_claim: `true`
- not_live_ready: `true`
- no broker, credentials, scheduler, real sizing, or orders created
