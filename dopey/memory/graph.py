"""Content-addressed causal and provenance graph over canonical memory ledgers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .ledger import load_memory_records


MEMORY_GRAPH_VERSION = "dopey-memory-graph-v1"


def _observed_at(record: Mapping[str, Any]) -> datetime:
    value = str(record["observed_at"])
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(
            f"memory graph timestamp requires timezone: memory_id={record['memory_id']}"
        )
    return parsed


def _causal_cycle_ids(
    memory_ids: set[str],
    parent_by_memory: Mapping[str, str],
) -> list[str]:
    state: dict[str, int] = {}
    cycle_ids: set[str] = set()

    def visit(memory_id: str, path: tuple[str, ...]) -> None:
        marker = state.get(memory_id, 0)
        if marker == 2:
            return
        if marker == 1:
            if memory_id in path:
                cycle_ids.update(path[path.index(memory_id) :])
            return
        state[memory_id] = 1
        parent_id = parent_by_memory.get(memory_id, "")
        if parent_id in memory_ids:
            visit(parent_id, (*path, memory_id))
        state[memory_id] = 2

    for memory_id in sorted(memory_ids):
        visit(memory_id, ())
    return sorted(cycle_ids)


def build_memory_graph(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_memory_id: dict[str, Mapping[str, Any]] = {}
    for record in records:
        memory_id = str(record.get("memory_id", ""))
        content_hash = str(record.get("content_hash", ""))
        if not memory_id or not content_hash:
            raise ValueError("memory graph input requires memory_id and content_hash")
        existing = by_memory_id.get(memory_id)
        if existing is not None and existing["content_hash"] != content_hash:
            raise ValueError(
                "memory graph identity conflict: "
                f"memory_id={memory_id}, existing_hash={existing['content_hash']}, "
                f"new_hash={content_hash}"
            )
        by_memory_id[memory_id] = record
    memory_ids = set(by_memory_id)
    reference_ids: set[str] = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    parent_by_memory: dict[str, str] = {}
    temporal_violations: list[dict[str, str]] = []
    for memory_id in sorted(by_memory_id):
        record = by_memory_id[memory_id]
        nodes.append(
            {
                "node_id": memory_id,
                "node_kind": "memory",
                "memory_kind": str(record["memory_kind"]),
                "observed_at": str(record["observed_at"]),
                "content_hash": str(record["content_hash"]),
            }
        )
        parent_id = str(record.get("causal_parent_id", ""))
        if parent_id:
            parent_by_memory[memory_id] = parent_id
            if parent_id not in memory_ids:
                reference_ids.add(parent_id)
            edge_body = {
                "source_node_id": memory_id,
                "target_node_id": parent_id,
                "edge_kind": "causal_parent",
            }
            edges.append(
                {
                    **edge_body,
                    "edge_id": f"memory-edge:{canonical_hash(edge_body)[:24]}",
                }
            )
            parent = by_memory_id.get(parent_id)
            if parent is not None and _observed_at(record) < _observed_at(parent):
                temporal_violations.append(
                    {
                        "memory_id": memory_id,
                        "parent_memory_id": parent_id,
                        "memory_observed_at": str(record["observed_at"]),
                        "parent_observed_at": str(parent["observed_at"]),
                    }
                )
        raw_sources = record.get("source_ids", [])
        if not isinstance(raw_sources, list):
            raise TypeError(
                f"memory graph source IDs must be a list: memory_id={memory_id}"
            )
        for source_id in raw_sources:
            source_text = str(source_id)
            if not source_text:
                continue
            if source_text not in memory_ids:
                reference_ids.add(source_text)
            edge_body = {
                "source_node_id": memory_id,
                "target_node_id": source_text,
                "edge_kind": "source_provenance",
            }
            edges.append(
                {
                    **edge_body,
                    "edge_id": f"memory-edge:{canonical_hash(edge_body)[:24]}",
                }
            )
    nodes.extend(
        {
            "node_id": reference_id,
            "node_kind": "external_reference",
        }
        for reference_id in sorted(reference_ids)
    )
    cycle_ids = _causal_cycle_ids(memory_ids, parent_by_memory)
    graph_status = (
        "blocked_causal_cycle"
        if cycle_ids
        else "blocked_temporal_order_violation"
        if temporal_violations
        else "complete_derived_index"
    )
    graph_body: dict[str, Any] = {
        "artifact_type": "content_addressed_research_memory_graph",
        "graph_version": MEMORY_GRAPH_VERSION,
        "graph_status": graph_status,
        "memory_node_count": len(memory_ids),
        "external_reference_node_count": len(reference_ids),
        "edge_count": len(edges),
        "causal_cycle_memory_ids": cycle_ids,
        "temporal_order_violations": temporal_violations,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda edge: edge["edge_id"]),
        "canonical_memory_ledgers_remain_source_of_truth": True,
        "graph_is_rebuildable_derived_index": True,
        "automatic_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**graph_body, "graph_hash": canonical_hash(graph_body)}


def build_memory_graph_from_ledgers(
    ledger_paths: Sequence[Path],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in ledger_paths:
        records.extend(load_memory_records(path, None))
    graph = build_memory_graph(records)
    return {
        **graph,
        "source_ledgers": [str(path.resolve()) for path in ledger_paths],
    }
