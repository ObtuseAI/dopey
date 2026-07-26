"""Champion consistency record (paper-only).

Workstream E of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`.

Writes a per-champion `champion_consistency.jsonl` record that the audit can recognize
as the `champion_consistency` artifact. The record includes the consistency verdict
and the holdout robustness from the stronger walk-forward consistency runner.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "champion_registry"
CHAMPION_CONSISTENCY_PATH = ARTIFACT_DIR / "champion_consistency.jsonl"
CHAMPION_REGISTRY_PATH = ARTIFACT_DIR / "champion_registry.jsonl"
CONSISTENCY_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
    / "dopey"
    / "walk_forward_consistency"
    / "consistency_registry.jsonl"
)


def _load_stronger_consistency(target: Path) -> dict:
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}


def _load_latest_champion(target: Path) -> dict:
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}


def write_champion_consistency_record(
    path: Path | str | None = None,
    safety_state: dict | None = None,
    champion_registry_path: Path | str | None = None,
    consistency_registry_path: Path | str | None = None,
) -> dict:
    """Build and write a champion-consistency record. Returns the record dict."""
    target = Path(path) if path else CHAMPION_CONSISTENCY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    champion_source = Path(champion_registry_path) if champion_registry_path else CHAMPION_REGISTRY_PATH
    consistency_source = Path(consistency_registry_path) if consistency_registry_path else CONSISTENCY_REGISTRY_PATH
    champion = _load_latest_champion(champion_source)
    stronger = _load_stronger_consistency(consistency_source)
    consistency_scores: dict[str, dict] = {}
    for s in stronger.get("strategy_consistency_scores", []) or []:
        sid = str(s.get("strategy_id", ""))
        if sid:
            consistency_scores[sid] = s
    verdicts: dict[str, str] = {}
    for v in stronger.get("consistency_verdicts", []) or []:
        sid = str(v.get("strategy_id", ""))
        if sid:
            verdicts[sid] = str(v.get("verdict", ""))
    champion_id = str(champion.get("champion_strategy_id", ""))
    runner_up_id = str(champion.get("runner_up_strategy_id", ""))
    record = {
        "champion_strategy_id": champion_id,
        "runner_up_strategy_id": runner_up_id,
        "champion_consistency": consistency_scores.get(champion_id, {}),
        "champion_consistency_verdict": verdicts.get(champion_id, "missing_evidence"),
        "runner_up_consistency": consistency_scores.get(runner_up_id, {}),
        "runner_up_consistency_verdict": verdicts.get(runner_up_id, "missing_evidence"),
        "holdout_robustness": stronger.get("holdout_robustness", {}),
        "consistency_status": "ok" if stronger else "missing",
        "stronger_wf_consistency_version": stronger.get("stronger_wf_consistency_version", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "safety_state": safety_state or {"mode": "RESEARCH", "live_trading_enabled": False,
                                          "funded_broker_connections_enabled": False,
                                          "allow_unofficial_robinhood_api": False,
                                          "paper_only_writer": True, "live_blocked": True},
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
