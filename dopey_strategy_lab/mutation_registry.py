"""Append-only local mutation registry for DOPEY."""
from __future__ import annotations

import json
from pathlib import Path


MUTATION_REGISTRY_VERSION = "dopey-mutation-registry-v1"
MUTATION_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "mutations"
MUTATION_REGISTRY_PATH = MUTATION_ARTIFACT_DIR / "mutation_registry.jsonl"
MUTATION_LEDGER_PATH = MUTATION_ARTIFACT_DIR / "dopey_mutation_tournament.jsonl"


def write_mutation_registry(record: dict, path: Path | str | None = None) -> Path:
    target = Path(path) if path else MUTATION_REGISTRY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def latest_mutation_summary(path: Path | str | None = None) -> dict:
    target = Path(path) if path else MUTATION_REGISTRY_PATH
    if not target.exists():
        return {
            "mutation_registry_version": MUTATION_REGISTRY_VERSION,
            "registry_path": str(target),
            "mutation_records_available": False,
            "best_mutated_strategy_id": "",
            "parent_vs_mutation_comparison": {},
        }
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {
            "mutation_registry_version": MUTATION_REGISTRY_VERSION,
            "registry_path": str(target),
            "mutation_records_available": False,
            "best_mutated_strategy_id": "",
            "parent_vs_mutation_comparison": {},
        }
    last = json.loads(lines[-1])
    return {
        "mutation_registry_version": MUTATION_REGISTRY_VERSION,
        "registry_path": str(target),
        "mutation_records_available": True,
        "batch_id": last.get("batch_id", ""),
        "best_mutated_strategy_id": last.get("best_mutated_strategy_id", ""),
        "parent_vs_mutation_comparison": last.get("parent_vs_mutation_comparison", {}),
        "promotion_decisions": last.get("promotion_decisions", {}),
    }
