"""One continuous but bounded autonomous strategy-research cycle."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from dopey.protocols.identity import canonical_hash

from .invention import invent_strategy_candidates
from .schema import ResearchFinding, StrategyBlueprint
from .task_suite import build_evaluation_task_suite
from .taxonomy import build_seed_strategies


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_ledger(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def _load_parent_pool(output_root: Path) -> tuple[tuple[StrategyBlueprint, ...], str, int]:
    seeds = build_seed_strategies()
    champion_path = output_root / "champion_strategies.json"
    if not champion_path.exists():
        return seeds, "seed_taxonomy", 0
    raw: Any = json.loads(champion_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or any(not isinstance(record, dict) for record in raw):
        raise ValueError(f"champion strategy registry must be an object array: path={champion_path}")
    champions = cast(list[StrategyBlueprint], raw)
    seed_by_lineage = {record["lineage_id"]: record for record in seeds}
    for champion in champions:
        lineage_id = str(champion.get("lineage_id", ""))
        if lineage_id not in seed_by_lineage:
            raise ValueError(
                f"champion strategy references unknown lineage: path={champion_path}, lineage_id={lineage_id}"
            )
        if champion.get("activation_state") != "RESEARCH_APPROVED":
            raise ValueError(
                "champion strategy is not research approved: "
                f"path={champion_path}, strategy_id={champion.get('strategy_id')}"
            )
        if champion.get("automatic_research_activation_allowed") is not True:
            raise ValueError(
                "champion strategy lacks protected activation decision: "
                f"path={champion_path}, strategy_id={champion.get('strategy_id')}"
            )
        seed_by_lineage[lineage_id] = champion
    return tuple(seed_by_lineage[record["lineage_id"]] for record in seeds), "approved_champions_plus_seeds", len(champions)


def run_autoresearch_cycle(
    output_root: Path,
    findings: Sequence[ResearchFinding],
    candidate_budget: int,
    generation: int,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("autoresearch issued_at must be timezone-aware")
    seeds, parent_pool_status, champion_count = _load_parent_pool(output_root)
    candidates = invent_strategy_candidates(seeds, findings, candidate_budget, generation)
    finding_status = "evidence_steered" if findings else "missing_findings_exploration_only"
    body: dict[str, Any] = {
        "artifact_type": "autonomous_recursive_strategy_research_cycle",
        "cycle_version": "dopey-autoresearch-cycle-v1",
        "cycle_status": "experiments_queued",
        "issued_at": issued_at.isoformat(),
        "generation": generation,
        "finding_status": finding_status,
        "finding_count": len(findings),
        "candidate_budget": candidate_budget,
        "candidate_count": len(candidates),
        "lineage_count": len({record["lineage_id"] for record in candidates}),
        "parent_pool_status": parent_pool_status,
        "approved_champion_count": champion_count,
        "candidates": list(candidates),
        "evaluation_task_suite": list(build_evaluation_task_suite()),
        "automatic_research_activation_count": 0,
        "human_review_required_for_qualified_activation": False,
        "candidate_self_activation_allowed": False,
        "backtest_only_activation_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    _append_ledger(output_root / "experiment_ledger.jsonl", output)
    _write_json_atomic(output_root / "latest_cycle.json", output)
    return output


def write_blocked_autoresearch_cycle(
    output_root: Path,
    findings_path: Path,
    generation: int,
    issued_at: datetime,
) -> dict[str, Any]:
    """Record that invention did not start because no validated finding exists."""

    if issued_at.tzinfo is None:
        raise ValueError("blocked autoresearch issued_at must be timezone-aware")
    body: dict[str, Any] = {
        "artifact_type": "autonomous_recursive_strategy_research_cycle",
        "cycle_version": "dopey-autoresearch-cycle-v2",
        "cycle_status": "blocked_missing_validated_research_findings",
        "issued_at": issued_at.isoformat(),
        "generation": generation,
        "generation_started": False,
        "findings_path": str(findings_path),
        "finding_count": 0,
        "candidate_budget": 0,
        "candidate_count": 0,
        "candidates": [],
        "automatic_research_activation_count": 0,
        "candidate_self_activation_allowed": False,
        "backtest_only_activation_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "required_next_evidence": (
            "independently validated typed ResearchFinding from a deterministic experiment"
        ),
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    _append_ledger(output_root / "blocked_cycle_ledger.jsonl", output)
    _write_json_atomic(output_root / "latest_cycle.json", output)
    return output
