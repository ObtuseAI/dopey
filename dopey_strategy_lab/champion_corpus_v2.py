"""Champion corpus v2 consistency record (paper-only).

Workstream E of `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`.

Writes a per-champion `champion_corpus_v2.jsonl` record that captures the
regime/holdout corpus v2 consistency verdict + holdout robustness + family challenge
state for the latest paper champion and runner-up.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "champion_registry"
CHAMPION_CORPUS_V2_PATH = ARTIFACT_DIR / "champion_corpus_v2.jsonl"
CHAMPION_REGISTRY_PATH = ARTIFACT_DIR / "champion_registry.jsonl"
CORPUS_V2_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
    / "dopey"
    / "regime_holdout_corpus_v2"
    / "corpus_registry.jsonl"
)


def _load_latest_champion(target: Path) -> dict:
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}


def _load_corpus_v2(target: Path) -> dict:
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}


def write_champion_corpus_v2_record(
    path: Path | str | None = None,
    safety_state: dict | None = None,
    champion_registry_path: Path | str | None = None,
    corpus_registry_path: Path | str | None = None,
) -> dict:
    """Build and write a champion-corpus-v2 record. Returns the record dict."""
    target = Path(path) if path else CHAMPION_CORPUS_V2_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    champion_source = Path(champion_registry_path) if champion_registry_path else CHAMPION_REGISTRY_PATH
    corpus_source = Path(corpus_registry_path) if corpus_registry_path else CORPUS_V2_REGISTRY_PATH
    champion = _load_latest_champion(champion_source)
    v2 = _load_corpus_v2(corpus_source)
    consistency_scores: dict[str, dict] = {}
    for s in v2.get("strategy_consistency_scores", []) or []:
        sid = str(s.get("strategy_id", ""))
        if sid:
            consistency_scores[sid] = s
    verdicts: dict[str, str] = {}
    for v in v2.get("consistency_verdicts", []) or []:
        sid = str(v.get("strategy_id", ""))
        if sid:
            verdicts[sid] = str(v.get("verdict", ""))
    champion_id = str(champion.get("champion_strategy_id", ""))
    runner_up_id = str(champion.get("runner_up_strategy_id", ""))
    coverage = v2.get("coverage_score", {})
    record = {
        "champion_strategy_id": champion_id,
        "runner_up_strategy_id": runner_up_id,
        "champion_corpus_v2": consistency_scores.get(champion_id, {}),
        "champion_corpus_v2_verdict": verdicts.get(champion_id, "missing_evidence"),
        "runner_up_corpus_v2": consistency_scores.get(runner_up_id, {}),
        "runner_up_corpus_v2_verdict": verdicts.get(runner_up_id, "missing_evidence"),
        "corpus_v2_status": "ok" if v2 else "missing",
        "total_windows": int(v2.get("total_windows", 0)),
        "new_windows_added": int(v2.get("new_windows_added", 0)),
        "coverage_score": coverage.get("coverage_fraction", 0.0) if isinstance(coverage, dict) else float(coverage or 0.0),
        "holdout_robustness": v2.get("holdout_robustness", {}),
        "stronger_wf_consistency_version": v2.get("stronger_wf_consistency_version", ""),
        "corpus_v2_version": v2.get("corpus_v2_version", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "safety_state": safety_state or {"mode": "RESEARCH", "live_trading_enabled": False,
                                          "funded_broker_connections_enabled": False,
                                          "allow_unofficial_robinhood_api": False,
                                          "paper_only_writer": True, "live_blocked": True},
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
