# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3_COMMANDS

All commands use the explicit repo venv. **No live broker or order commands.**

## Full orchestrator

```powershell
cd C:\Users\CH\dopey
.\.venv\Scripts\python.exe -m dopey_autonomy.run_public_signal_research_breakthrough_v3
```

## Individual stages

```powershell
.\.venv\Scripts\python.exe -m dopey_validation.run_public_signal_research_v3_preflight
.\.venv\Scripts\python.exe -m dopey_signal_research.run_research_mutation_queue_executor_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_stable_family_template_repair_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_research_candidate_generator_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_profit_holdout_repair_scorer_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_research_path_simulator_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_research_tournament_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_research_breakthrough_gate_v3
.\.venv\Scripts\python.exe -m dopey_signal_research.run_research_mutation_queue_v3
.\.venv\Scripts\python.exe -m dopey_active_policy.run_zero_dte_replay_outcomes_artifact_repair_v1
.\.venv\Scripts\python.exe -m dopey_scoreboard.run_public_signal_research_scoreboard_v3
.\.venv\Scripts\python.exe -m dopey_live_gate.run_public_signal_research_live_gate_status_v3
```

## Targeted validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_signal_research_breakthrough_v3.py -q
```

## Carry-forward validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_signal_research_breakthrough_v2.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_public_signal_research_breakthrough_v1.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_public_champion_repair_and_retune_v1.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_active_policy_integration.py tests/test_active_trading_policy.py -q
```

## Export / stabilizer (capped)

```powershell
.\.venv\Scripts\python.exe -m dopey_export_review.run_export_bundle_review_assistant
.\.venv\Scripts\python.exe -m dopey_validation.full_suite_stabilizer
```

Live trading remains **disabled**. Official Robinhood market-data lane allowed for research only.
