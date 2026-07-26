# DOPEY Market Provider Expansion V2 Commands

Run from `C:\Users\CH\dopey`.

## Preferred Explicit Venv Commands

```powershell
.\.venv\Scripts\python.exe -m dopey_autonomy.run_real_public_market_wealth_engine_rerun
.\.venv\Scripts\python.exe -m dopey_runtime_bootstrap.run_provider_install_repair
.\.venv\Scripts\python.exe -m dopey_market_intake.run_provider_health_diagnostics
.\.venv\Scripts\python.exe -m dopey_market_intake.run_public_ohlcv_provider_ladder_v2
.\.venv\Scripts\python.exe -m dopey_market_intake.run_market_data_cache_manager
.\.venv\Scripts\python.exe -m dopey_market_intake.run_market_lake_public_promotion
.\.venv\Scripts\python.exe -m dopey_market_intake.run_market_universe_expander
.\.venv\Scripts\python.exe -m dopey_scoreboard.run_public_vs_fixture_scoreboard_split
```

## Normal Module Commands

```powershell
python -m dopey_autonomy.run_real_public_market_wealth_engine_rerun
python -m dopey_runtime_bootstrap.run_provider_install_repair
python -m dopey_market_intake.run_provider_health_diagnostics
python -m dopey_market_intake.run_public_ohlcv_provider_ladder_v2
python -m dopey_market_intake.run_market_data_cache_manager
python -m dopey_market_intake.run_market_lake_public_promotion
python -m dopey_scoreboard.run_public_vs_fixture_scoreboard_split
```

If plain `python` points outside `.venv`, use the explicit venv commands.

## Downstream Reruns

```powershell
.\.venv\Scripts\python.exe -m dopey_chart_vision.run_chart_vision_engine
.\.venv\Scripts\python.exe -m dopey_signal_engine.run_aggressive_signal_engine
.\.venv\Scripts\python.exe -m dopey_options_engine.run_model_priced_trade_constructor
.\.venv\Scripts\python.exe -m dopey_tournament.run_paper_money_tournament_engine
.\.venv\Scripts\python.exe -m dopey_scoreboard.run_performance_cockpit
.\.venv\Scripts\python.exe -m dopey_risk_engine.run_risk_throttle_engine
.\.venv\Scripts\python.exe -m dopey_evolution.run_winner_loser_evolution_loop
.\.venv\Scripts\python.exe -m dopey_live_gate.run_live_gate_status
```

No live broker, live order, credential, funded account, or real-capital command is part of this bundle.
