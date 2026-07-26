"""Dopey proof ledger: append-only JSONL proof ledger + proof entry dataclass.

Forked from Blunder engine (Z:\\Obtuse\\engine\\blunder\\engine.py); the ProofEntry + ProofLedger
pieces were split out into this module as part of the Dopey rename/decomposition. Logic preserved;
internal import of parse_proof_ledger now resolves to dopey_core.validator_mesh.

DOPEY lineage: Blunder engine.py (ProofEntry/ProofLedger) -> dopey_core.proof_ledger
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .validator_mesh import parse_proof_ledger


@dataclass
class ProofEntry:
    run_id: str
    task_id: str
    timestamp: str
    input_hash: str
    plan_hash: str
    mock_trial_result: str
    execution_result: dict
    validation_result: str
    repair_attempts: int
    artifacts: list
    diffs: list
    test_results: dict
    final_status: str
    lessons_candidate: list
    promotion_candidate: list
    limitations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class ProofLedger:
    """Append-only JSONL proof ledger with a consistency self-check."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: ProofEntry) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def consistency_check(self) -> dict:
        text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        return parse_proof_ledger(text)
