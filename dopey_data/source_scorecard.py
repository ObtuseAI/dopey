"""Dopey source scorecard: data-source trust/quality scorecard (stdlib dataclass).

DOPEY-native. No pydantic. Records the research trust/quality of a data source.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class SourceScorecard:
    source_id: str
    authority: float = 0.0
    freshness: float = 0.0
    license_class: str = "UNKNOWN"
    research_only: bool = True
    credentialed: bool = False
    notes: str = ""
    # Restored source-value-ranker dimensions (lost in the branch-switch file
    # loss; dopey_data/source_value_ranker.py builds scorecards with them and
    # ranks on overall_score). Defaults 0.0 / "unscored" keep the simple
    # adapter scorecards valid and sort them last, never inflating trust.
    freshness_score: float = 0.0
    reliability_score: float = 0.0
    latency_score: float = 0.0
    coverage_score: float = 0.0
    ontology_fit_score: float = 0.0
    edge_contribution_score: float = 0.0
    cost_complexity_score: float = 0.0
    compliance_score: float = 0.0
    paper_research_value_score: float = 0.0
    overall_score: float = 0.0
    status: str = "unscored"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SourceScorecard":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def trust_score(self) -> float:
        lic = 1.0 if self.license_class in {"MIT", "APACHE-2.0", "OWNED", "OFFICIAL_REFERENCE", "PUBLIC_DOMAIN"} else 0.35
        return round(0.4 * self.authority + 0.3 * self.freshness + 0.3 * lic, 6)
