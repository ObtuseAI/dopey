# DOPEY Wealth Engine Commands

Run the full bundle:

```powershell
python -m dopey_autonomy.run_wealth_engine_full_completion
```

Run workstreams:

```powershell
python -m dopey_runtime_bootstrap.run_local_dependency_bootstrap
python -m dopey_market_intake.run_market_data_lake_builder
python -m dopey_chart_vision.run_chart_vision_engine
python -m dopey_signal_engine.run_aggressive_signal_engine
python -m dopey_options_engine.run_model_priced_trade_constructor
python -m dopey_tournament.run_paper_money_tournament_engine
python -m dopey_scoreboard.run_performance_cockpit
python -m dopey_risk_engine.run_risk_throttle_engine
python -m dopey_evolution.run_winner_loser_evolution_loop
python -m dopey_live_gate.run_live_gate_status
python -m dopey_export_review.run_export_bundle_review_assistant
python -m dopey_validation.full_suite_stabilizer
```

Targeted validation:

```powershell
python -m pytest tests/test_wealth_engine_market_vision_paper_tournament_completion.py -q
```

No live broker/order command exists in this bundle.
