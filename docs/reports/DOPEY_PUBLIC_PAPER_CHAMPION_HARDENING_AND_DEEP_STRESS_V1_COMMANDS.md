# DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1_COMMANDS

All commands use the explicit repo venv. No live broker/order commands.

- `.\.venv\Scripts\python.exe -m dopey_autonomy.run_public_paper_champion_hardening_and_deep_stress_v1`
- `.\.venv\Scripts\python.exe -m dopey_validation.run_champion_hardening_preflight`
- `.\.venv\Scripts\python.exe -m dopey_signal_engine.run_public_signal_artifact_cleaner_v1`
- `.\.venv\Scripts\python.exe -m dopey_champion.run_public_champion_inventory_v1`
- `.\.venv\Scripts\python.exe -m dopey_champion.run_public_champion_deep_stress_matrix_v1`
- `.\.venv\Scripts\python.exe -m dopey_champion.run_public_champion_holdout_expansion_v1`
- `.\.venv\Scripts\python.exe -m dopey_champion.run_public_champion_decay_monitor_v1`
- `.\.venv\Scripts\python.exe -m dopey_champion.run_public_champion_hardening_gate_v1`
- `.\.venv\Scripts\python.exe -m dopey_evolution.run_public_champion_hardening_repair_queue_v1`
- `.\.venv\Scripts\python.exe -m dopey_scoreboard.run_public_champion_hardening_scoreboard_v1`
- `.\.venv\Scripts\python.exe -m dopey_live_gate.run_public_champion_hardening_live_gate_status_v3`
- `.\.venv\Scripts\python.exe -m pytest tests/test_public_paper_champion_hardening_and_deep_stress_v1.py -q`
