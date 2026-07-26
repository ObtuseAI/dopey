# DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2_COMMANDS

All commands use the explicit repo venv. No live broker/order commands.

- `.\.venv\Scripts\python.exe -m dopey_autonomy.run_public_market_signal_mutation_deepening_v2`
- `.\.venv\Scripts\python.exe -m dopey_market_intake.run_public_lake_final_state_lock_v2`
- `.\.venv\Scripts\python.exe -m dopey_strategy_cohorts.run_strategy_id_canonicalizer`
- `.\.venv\Scripts\python.exe -m dopey_signal_engine.run_public_signal_mutation_factory_v4`
- `.\.venv\Scripts\python.exe -m dopey_options_engine.run_model_priced_path_simulator_v4`
- `.\.venv\Scripts\python.exe -m dopey_tournament.run_public_cohort_walk_forward_tournament_v4`
- `.\.venv\Scripts\python.exe -m dopey_champion.run_public_paper_champion_gate_v2`
- `.\.venv\Scripts\python.exe -m dopey_evolution.run_public_signal_deepening_loop_v2`
- `.\.venv\Scripts\python.exe -m dopey_scoreboard.run_public_signal_deepening_scoreboard_v4`
- `.\.venv\Scripts\python.exe -m dopey_live_gate.run_public_signal_deepening_live_gate_status_v2`
- `.\.venv\Scripts\python.exe -m pytest tests/test_public_market_signal_mutation_deepening_v2.py -q`
