"""Deflation trial count = DISTINCT configs, not raw invocations.

The review-time deflated-Sharpe penalty scales with search breadth. A
deterministic re-evaluation of the same exit config (the nightly determinism
check runs the fitness twice, every night) adds zero data-snooping, so it must
not raise the penalty's N; a genuinely new config must. The raw invocation
count stays in the ledger for audit.
"""
from __future__ import annotations

import json

from operator_tools import operator_evolve_fitness as fitness


def _with_ledger(tmp_path, monkeypatch):
    ledger_path = tmp_path / "trial_ledger.json"
    monkeypatch.setattr(fitness, "TRIAL_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(fitness, "STATE_DIR", tmp_path)
    return ledger_path


def test_same_config_reruns_do_not_inflate_trials(tmp_path, monkeypatch) -> None:
    _with_ledger(tmp_path, monkeypatch)
    config = {"max_holding_steps": 3, "premium_stop_pct": -0.5, "premium_target_pct": 1.0}
    assert fitness.bump_trial_ledger(config) == 1
    assert fitness.bump_trial_ledger(config) == 1
    assert fitness.bump_trial_ledger(config) == 1


def test_new_configs_each_count_as_a_trial(tmp_path, monkeypatch) -> None:
    _with_ledger(tmp_path, monkeypatch)
    base = {"max_holding_steps": 3, "premium_stop_pct": -0.5, "premium_target_pct": 1.0}
    assert fitness.bump_trial_ledger(base) == 1
    assert fitness.bump_trial_ledger({**base, "max_holding_steps": 5}) == 2
    assert fitness.bump_trial_ledger({**base, "premium_stop_pct": -0.4}) == 3
    # and re-running an old one still does not inflate
    assert fitness.bump_trial_ledger(base) == 3


def test_raw_invocation_count_is_preserved_for_audit(tmp_path, monkeypatch) -> None:
    ledger_path = _with_ledger(tmp_path, monkeypatch)
    config = {"max_holding_steps": 3, "premium_stop_pct": -0.5, "premium_target_pct": 1.0}
    for _ in range(4):
        fitness.bump_trial_ledger(config)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["cumulative_evals"] == 4
    assert ledger["distinct_config_count"] == 1


def test_legacy_ledger_migration_never_lowers_the_penalty_floor(tmp_path, monkeypatch) -> None:
    ledger_path = _with_ledger(tmp_path, monkeypatch)
    ledger_path.write_text(
        json.dumps(
            {
                "artifact_type": "evolution_fitness_trial_ledger",
                "cumulative_evals": 12,
                "first_eval_utc": "2026-07-10T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    config = {"max_holding_steps": 3, "premium_stop_pct": -0.5, "premium_target_pct": 1.0}
    # Legacy 12 evals collapse to one historical config-group + this new one.
    assert fitness.bump_trial_ledger(config) == 2
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["cumulative_evals"] == 13
    assert ledger["config_eval_counts"]["legacy_unattributed"] == 12
