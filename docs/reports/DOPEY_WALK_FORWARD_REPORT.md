# DOPEY WALK-FORWARD REPORT

## Purpose
The **offline walk-forward replay harness** (`dopey_walk_forward`) is the third executable Dopey
pass. It consumes the existing paper-only pipeline outputs (StrategyGenome, option-chain
fixtures, `ProofWeightedAggressionGate`, `PaperBroker`, `ProofLedger`) to evaluate whether a
strategy remains viable across segmented historical fixture windows without any live, broker,
credential, or network path. It proves DOPEY can score walk-forward consistency, detect
overfit/fragility, and feed summarized results back into the aggression gate as proof — while
keeping every live-trading path blocked.

## Fixture windows added
`dopey_data/fixtures/walk_forward/` — 4 deterministic JSON windows:

| File | window_type | regime_tag | outcome |
|---|---|---|---|
| `window_001_train.json` | train | `trend_vol_expansion` | uptrend continuation; convexity profits |
| `window_002_validation.json` | validation | `chop_vol_compression` | low-vol chop; theta survival (marginal) |
| `window_003_validation.json` | validation | `gap_reversal` | gap-down; invalidation trips |
| `window_004_holdout.json` | holdout | `liquidity_decay` | thin liquidity; wider spreads erode pnl |

Each window carries: underlying snapshot (price/prev_close/realized_vol/regime_score), a full
option-chain snapshot (calls+puts, varied bid/ask/IV/volume/OI/Greeks), a deterministic
next-step outcome (next price/iv/days-to-exit/exit-reason/favorable+adverse move), regime tag,
timestamp, and sequence id. 4 distinct regime tags; no external data calls.

## Replay scoring method
`dopey_walk_forward/scoring.py` computes the aggregate `WalkForwardScore`:
- **consistency_score** — 1 − stdev(pnls)/|mean| (lower dispersion = higher).
- **window_pass_rate** — fraction of windows with `verdict == "pass"` (pnl ≥ 0 or controlled
  invalidation).
- **regime_survival_score** — fraction of distinct regimes that produced a pass.
- **slippage_tolerance_score** — 1 − normalized avg slippage.
- **liquidity_robustness_score** — min(1, avg liquidity).
- **invalidation_quality_score** — fraction of losing windows that triggered invalidation
  (controlled downside).
- **overfit_suspicion_score** — blend of train-vs-OOS collapse and holdout collapse.
- **overall** — weighted blend of the above.

Penalized: works only in train, extreme sensitivity to one window, poor liquidity windows, bad
slippage windows, repeated invalidation failure, holdout collapse. Rewarded: stable performance,
controlled downside, fast invalidation, good liquidity filtering, consistent fill quality,
regime-aware survival. Simple deterministic first; limitations documented.

## Overfit detection method
`dopey_walk_forward/overfit_classifier.py` (extends `dopey_strategy_lab.overfit_detector`)
classifies `none | low | moderate | high`:
- **high**: train passes but validation AND holdout both fail (curve-fit).
- **moderate**: train+validation pass but holdout fails; OR train+holdout pass but validation
  fails; OR mixed survival.
- **low**: all windows pass but holdout pnl negative or elevated suspicion.
- **none**: all windows pass with non-negative holdout pnl.

## Aggression gate integration
`dopey_walk_forward/aggression_replay.py` maps the walk-forward summary onto the
`ProofWeightedAggressionGate`. Allowed promotion targets in this pass:
`research_only`, `paper_candidate`, `replay_promoted_paper_candidate`, `rejected`.
Explicitly DISALLOWED (and impossible from this path): `micro_live`, `adaptive_live`, any live
promotion. Overfit gating: high overfit forces `rejected`; moderate overfit caps at
`research_only`; none/low + holdout survival + overall≥0.55 → `replay_promoted_paper_candidate`.
Tests prove live promotion is impossible.

## ProofLedger output path
`artifacts/dopey/walk_forward/dopey_walk_forward.jsonl` — append-only JSONL; one reproducibility-
hashed `ProofEntry` per replay run. Each record includes: `run_id`, `task_id` (strategy id),
`input_hash` (reproducibility hash), `execution_result.window_results` + `walk_forward_score` +
`overfit_signal` + `replay_verdict`, `validation_result`, and `final_status`. Local artifact only;
no network.

## Command to run
```
python -m dopey_walk_forward.run_fixture_walk_forward
```
(Also importable: `from dopey_walk_forward import run_fixture_walk_forward; run_fixture_walk_forward()`.)

## Sample JSON summary
```json
{
  "mode": "RESEARCH",
  "live_trading_enabled": false,
  "walk_forward_status": "ok",
  "strategy_id": "genome-directional-convexity-spy-fixture-v1",
  "replay_run_id": "dopey-walk-forward-genome-directional-convexity-spy-fixture-v1",
  "windows_replayed": 4,
  "pass_rate": 0.75,
  "overfit_level": "none",
  "promotion_decision": "replay_promoted_paper_candidate",
  "proof_record_path": "C:\\Users\\CH\\dopey\\artifacts\\dopey\\walk_forward\\dopey_walk_forward.jsonl",
  "live_blocked": true,
  "aggression_score": 0.9
}
```

## Safety state
- `mode` = `RESEARCH`; `live_trading_enabled` = `false`;
  `funded_broker_connections_enabled` = `false`;
  `allow_unofficial_robinhood_api` = `false`.
- `ReplayEngine` rejects any `live_allowed=true` intent (`LiveTradingDisabledError`).
- `PaperBroker` is the only execution adapter used; refuses live intents.
- Robinhood/Alpaca/Tradier stubs still raise `LiveTradingDisabledError`.
- No broker connection, no credentials, no network, no Blunder modification.
- `safety_review()` utility returns `ok=True` (8 boundary checks pass).
- Original Blunder sources on `Z:` verified unchanged via SHA256 (78/78, 0 mismatches).
- No profit claims; replay PnL is explicitly simulated/paper-only.

## Files added
- `dopey_walk_forward/` package: `__init__.py`, `window_model.py`, `replay_models.py`,
  `overfit_classifier.py`, `scoring.py`, `replay_engine.py`, `aggression_replay.py`,
  `ledger_replay.py`, `runner.py`, `run_fixture_walk_forward.py`, `safety_review.py`.
- `dopey_data/fixtures/walk_forward/`: 4 window JSON fixtures.
- `tests/test_walk_forward.py` (12 new tests).
- `DOPEY_WALK_FORWARD_REPORT.md` (this file).

## Files modified
- (none beyond docs) — this pass is purely additive and reuses existing pipeline components.

## Tests run
```
python -m pytest -q   -> 39 passed (27 prior + 12 walk-forward), 0 failures
```
New walk-forward tests (`tests/test_walk_forward.py`):
1. `test_01_walk_forward_fixture_windows_load`
2. `test_02_walk_forward_replay_is_deterministic`
3. `test_03_replay_uses_paper_broker_only`
4. `test_04_replay_rejects_live_allowed_intent`
5. `test_05_walk_forward_score_penalizes_holdout_collapse`
6. `test_06_overfit_detector_classifies_high_overfit`
7. `test_07_overfit_detector_classifies_low_or_none_overfit`
8. `test_08_aggression_gate_cannot_promote_live_from_replay`
9. `test_09_walk_forward_appends_proof_ledger_record`
10. `test_10_walk_forward_does_not_enable_live_trading`
11. `test_11_existing_live_stubs_still_block_after_walk_forward`
12. `test_12_blunder_source_integrity_if_manifest_available`

## Known gaps
- Single deterministic fixture genome (directional convexity); no multi-strategy tournament yet.
- Crude deterministic exit model (vertical intrinsic − theta penalty); no richer Greeks model.
- Fixed 0.2% slippage heuristic; no real market-impact/queue model.
- Walk-forward windows are small (4); a larger window corpus would strengthen regime coverage.
- Replay PnL is simulated/paper-only and must not imply real execution quality.
- No schedule/daemon; the harness is invoked manually only.

## Next recommended build target
**Multi-strategy paper tournament** — extend the replay harness to run multiple StrategyGenomes
across the same fixture windows, rank them by `WalkForwardScore.overall`, and record a champion
registry — all offline, paper-only, and live-blocked. This builds directly on the per-window
replay + scoring + overfit foundation now in place.

> **Update (Pass 4):** the walk-forward harness is now consumed by the multi-strategy paper
> tournament (`dopey_tournament`), which runs multiple genomes across these same windows,
> adds S-tier analysis fusion (`dopey_analysis`), ranks by combined walk-forward + analysis
> score, and records a champion registry. See `DOPEY_TOURNAMENT_REPORT.md`. The walk-forward
> loader now skips `*_analysis.json` files so analysis fixtures coexist with window fixtures.
