"""Append-only research-genome registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import PromotionState, ResearchGenome


def load_genome_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"genome registry contains invalid JSON: path={path}, line_number={line_number}") from exc
        if not isinstance(value, dict) or not value.get("genome_id") or not value.get("content_hash"):
            raise ValueError(f"genome registry entry is incomplete: path={path}, line_number={line_number}")
        if value.get("paper_only") is not True or value.get("live_blocked") is not True:
            raise ValueError(f"genome registry violates research boundary: path={path}, line_number={line_number}")
        records.append(value)
    return records


def append_genome(path: Path, genome: ResearchGenome) -> dict[str, str]:
    records = load_genome_registry(path)
    matches = [record for record in records if record["genome_id"] == genome.genome_id]
    if matches:
        if matches[0]["content_hash"] != genome.content_hash:
            raise ValueError(f"genome identity conflict: genome_id={genome.genome_id}, path={path}")
        return {"append_status": "already_present_identical", "genome_id": genome.genome_id, "path": str(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(genome.to_dict(), sort_keys=True, ensure_ascii=True) + "\n")
    return {"append_status": "appended", "genome_id": genome.genome_id, "path": str(path)}


def genome_from_record(record: dict[str, Any]) -> ResearchGenome:
    return ResearchGenome(
        **{
            **record,
            "parent_ids": tuple(record["parent_ids"]),
            "agent_ids": tuple(record["agent_ids"]),
            "analysis_order": tuple(record["analysis_order"]),
            "indicator_ids": tuple(record["indicator_ids"]),
            "timeframes": tuple(record["timeframes"]),
            "data_lane_priorities": tuple(record["data_lane_priorities"]),
            "promotion_state": PromotionState(record["promotion_state"]),
        }
    )
