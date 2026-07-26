"""Local deterministic data-inflow registry for source scorecards."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .source_value_ranker import rank_source_candidates


DATA_INFLOW_REGISTRY_VERSION = "dopey-data-inflow-registry-v1"
DEFAULT_SOURCE_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "source_registry" /
    "data_inflow_registry.jsonl"
)


@dataclass
class DataInflowRegistry:
    registry_id: str = DATA_INFLOW_REGISTRY_VERSION
    candidates: list[dict] = field(default_factory=list)
    scorecards: list[dict] = field(default_factory=list)
    promotion_decisions: list[dict] = field(default_factory=list)
    contribution_hypotheses: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_ranked_rows(cls, rows: list[dict]) -> "DataInflowRegistry":
        return cls(
            candidates=[row["candidate"] for row in rows],
            scorecards=[row["scorecard"] for row in rows],
            promotion_decisions=[row["decision"] for row in rows],
            contribution_hypotheses=[row["hypothesis"] for row in rows],
            summary=_summary_from_rows(rows),
        )


def _summary_from_rows(rows: list[dict]) -> dict:
    promoted = [r for r in rows if r["scorecard"]["status"] == "promoted_for_fixture_research"]
    deferred_network = [r for r in rows if r["scorecard"]["status"] == "deferred_requires_network"]
    deferred_creds = [r for r in rows if r["scorecard"]["status"] == "deferred_requires_credentials"]
    return {
        "source_scorecard_version": "dopey-source-scorecard-v1",
        "candidate_count": len(rows),
        "promoted_source_ids": [r["candidate"]["source_id"] for r in promoted],
        "deferred_network_source_ids": [r["candidate"]["source_id"] for r in deferred_network],
        "deferred_credential_source_ids": [r["candidate"]["source_id"] for r in deferred_creds],
        "top_sources": [
            {
                "source_id": r["candidate"]["source_id"],
                "overall_score": r["scorecard"]["overall_score"],
                "status": r["scorecard"]["status"],
            }
            for r in rows[:5]
        ],
        "network_fetch_performed": False,
        "credentials_used": False,
    }


def build_data_inflow_registry() -> DataInflowRegistry:
    return DataInflowRegistry.from_ranked_rows(rank_source_candidates())


def write_data_inflow_registry(path: Path | str | None = None) -> Path:
    target = Path(path) if path else DEFAULT_SOURCE_REGISTRY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    registry = build_data_inflow_registry()
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(registry.to_dict(), ensure_ascii=False) + "\n")
    return target
