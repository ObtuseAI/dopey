"""Governed repository capability intake without foreign-code execution."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, TypedDict, cast

from .common import ARTIFACT_ROOT, REPO_ROOT, stable_hash, stamped, write_json_atomic


CAPABILITY_FOUNDRY_VERSION: Final[str] = "dopey-capability-foundry-v2"
CAPABILITY_FOUNDRY_STATUS: Final[str] = (
    "complete_quarantined_unverified_provenance_candidates"
)
CAPABILITY_FOUNDRY_ARTIFACT_TYPE: Final[str] = (
    "governed_repository_capability_foundry_snapshot"
)
CAPABILITY_FOUNDRY_SNAPSHOT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "artifact_type",
        "automatic_activation_allowed",
        "automatic_installation_allowed",
        "automatic_source_copy_allowed",
        "capability_graph",
        "catalog_hash",
        "catalog_version",
        "credentials_written",
        "execution_effect",
        "external_oss_source_count",
        "foreign_code_executed",
        "foreign_source_files_downloaded",
        "foundry_status",
        "foundry_version",
        "license_class_counts",
        "live_blocked",
        "obtuseai_internal_source_count",
        "packages_installed",
        "paper_only",
        "priority_slices",
        "ranked_candidates",
        "readiness_effect",
        "remote_observation_status",
        "remote_provenance_verification_status",
        "remote_verification_limitations",
        "reproducibility_hash",
        "scoring_semantics",
        "snapshot_observed_at_utc",
        "source_count",
        "trade_authority_effect",
    }
)
CATALOG_PATH: Final[Path] = REPO_ROOT / "dopey_acceleration" / "capability_sources.json"
CAPABILITY_FOUNDRY_PATH: Final[Path] = (
    ARTIFACT_ROOT / "capability_foundry" / "latest_snapshot.json"
)
PERMISSIVE_LICENSES: Final[frozenset[str]] = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "MIT",
        "Unlicense",
    }
)
BOUNDARY_LICENSES: Final[frozenset[str]] = frozenset(
    {
        "AGPL-3.0",
        "GPL-2.0",
        "GPL-3.0",
        "LGPL-2.1",
        "LGPL-3.0",
    }
)
SCORE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "dopey_fit",
        "evidence_value",
        "replayability",
        "isolation_fit",
        "integration_cost",
        "adoption_risk",
    }
)
SOURCE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "repository",
        "url",
        "source_kind",
        "visibility",
        "license_spdx",
        "license_evidence",
        "default_ref",
        "observed_head_sha",
        "pushed_at_utc",
        "stars",
        "capabilities",
        "scores",
        "rationale",
    }
)


class SourceScores(TypedDict):
    dopey_fit: float
    evidence_value: float
    replayability: float
    isolation_fit: float
    integration_cost: float
    adoption_risk: float


class RepositorySource(TypedDict):
    repository: str
    url: str
    source_kind: Literal["obtuseai_internal", "external_oss"]
    visibility: Literal["private", "public"]
    license_spdx: str
    license_evidence: str
    default_ref: str
    observed_head_sha: str
    pushed_at_utc: str
    stars: int
    capabilities: tuple[str, ...]
    scores: SourceScores
    rationale: str


class CapabilitySlice(TypedDict):
    slice_id: str
    purpose: str
    capability_ids: tuple[str, ...]


CAPABILITY_SLICES: Final[tuple[CapabilitySlice, ...]] = (
    {
        "slice_id": "truth_and_lineage_kernel",
        "purpose": "point-in-time joins, immutable lineage, tamper evidence, and trustworthy evaluation",
        "capability_ids": (
            "point_in_time_data",
            "point_in_time_world_model",
            "lineage_events",
            "evaluator_isolation",
            "tamper_evident_witness",
        ),
    },
    {
        "slice_id": "falsification_and_uncertainty_kernel",
        "purpose": "calibrated abstention, causal refutation, regime shifts, and failure localization",
        "capability_ids": (
            "conformal_risk",
            "causal_refutation",
            "change_point_detection",
            "causal_confidence",
            "agent_failure_localization",
        ),
    },
    {
        "slice_id": "differential_simulation_oracle_mesh",
        "purpose": "compare identical frozen scenarios across independent pricing and execution engines",
        "capability_ids": (
            "semantic_rng",
            "common_random_numbers",
            "deterministic_replay",
            "derivatives_pricing_oracle",
            "event_driven_backtest",
            "microstructure_replay",
        ),
    },
    {
        "slice_id": "measured_agent_and_tool_layer",
        "purpose": "prove task competence, tool safety, and browser behavior through repeatable evaluations",
        "capability_ids": (
            "agent_evaluation",
            "browser_evaluation",
            "typed_tool_contracts",
            "skill_evaluation",
            "experiment_tracking",
        ),
    },
    {
        "slice_id": "governed_web_document_memory",
        "purpose": "source-hashed acquisition, deterministic parsing, vision challengers, and bitemporal retrieval",
        "capability_ids": (
            "browser_acquisition",
            "web_crawling",
            "document_vision",
            "temporal_evidence_graph",
            "scientific_memory",
        ),
    },
    {
        "slice_id": "isolated_recursive_research_cell",
        "purpose": "bounded proposer, developer, falsifier, and promotion loops inside default-deny sandboxes",
        "capability_ids": (
            "automated_quant_research",
            "research_optimization",
            "policy_sandbox",
            "sandbox_orchestration",
            "lineage_allocation",
        ),
    },
)


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"capability catalog timestamp is invalid: field={field_name}, value={value}"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(
            f"capability catalog timestamp requires timezone: field={field_name}, value={value}"
        )
    return parsed


def _require_string(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"capability catalog source requires a non-empty string: field={field_name}"
        )
    return value


def _validated_scores(value: object, repository: str) -> SourceScores:
    if not isinstance(value, Mapping) or set(value) != SCORE_FIELDS:
        observed = set(value) if isinstance(value, Mapping) else set()
        raise ValueError(
            "capability catalog scores differ from the exact schema: "
            f"repository={repository}, missing={sorted(SCORE_FIELDS - observed)}, "
            f"unexpected={sorted(observed - SCORE_FIELDS)}"
        )
    scores: dict[str, float] = {}
    for field_name in sorted(SCORE_FIELDS):
        raw = value[field_name]
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise TypeError(
                "capability catalog score must be numeric: "
                f"repository={repository}, field={field_name}"
            )
        score = float(raw)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(
                "capability catalog score must be within [0, 1]: "
                f"repository={repository}, field={field_name}, value={score}"
            )
        scores[field_name] = score
    return cast(SourceScores, scores)


def _validated_source(value: object) -> RepositorySource:
    if not isinstance(value, Mapping) or set(value) != SOURCE_FIELDS:
        observed = set(value) if isinstance(value, Mapping) else set()
        raise ValueError(
            "capability catalog source differs from the exact schema: "
            f"missing={sorted(SOURCE_FIELDS - observed)}, "
            f"unexpected={sorted(observed - SOURCE_FIELDS)}"
        )
    record = {str(key): item for key, item in value.items()}
    repository = _require_string(record, "repository")
    url = _require_string(record, "url")
    if url != f"https://github.com/{repository}":
        raise ValueError(
            "capability catalog URL is not bound to the repository identity: "
            f"repository={repository}, url={url}"
        )
    source_kind = record["source_kind"]
    if source_kind not in {"obtuseai_internal", "external_oss"}:
        raise ValueError(
            f"capability catalog source kind is unsupported: repository={repository}, value={source_kind}"
        )
    visibility = record["visibility"]
    if visibility not in {"private", "public"}:
        raise ValueError(
            f"capability catalog visibility is unsupported: repository={repository}, value={visibility}"
        )
    head_sha = _require_string(record, "observed_head_sha")
    if len(head_sha) != 40 or any(
        character not in "0123456789abcdef" for character in head_sha
    ):
        raise ValueError(
            f"capability catalog requires a pinned Git commit: repository={repository}, sha={head_sha}"
        )
    pushed_at = _require_string(record, "pushed_at_utc")
    _parse_utc(pushed_at, f"{repository}.pushed_at_utc")
    raw_stars = record["stars"]
    if not isinstance(raw_stars, int) or isinstance(raw_stars, bool) or raw_stars < 0:
        raise ValueError(
            f"capability catalog stars must be a non-negative integer: repository={repository}"
        )
    raw_capabilities = record["capabilities"]
    if (
        not isinstance(raw_capabilities, list)
        or not raw_capabilities
        or any(not isinstance(item, str) or not item for item in raw_capabilities)
        or len(raw_capabilities) != len(set(raw_capabilities))
    ):
        raise ValueError(
            f"capability catalog requires unique capability IDs: repository={repository}"
        )
    return {
        "repository": repository,
        "url": url,
        "source_kind": cast(
            Literal["obtuseai_internal", "external_oss"],
            source_kind,
        ),
        "visibility": cast(Literal["private", "public"], visibility),
        "license_spdx": _require_string(record, "license_spdx"),
        "license_evidence": _require_string(record, "license_evidence"),
        "default_ref": _require_string(record, "default_ref"),
        "observed_head_sha": head_sha,
        "pushed_at_utc": pushed_at,
        "stars": raw_stars,
        "capabilities": tuple(raw_capabilities),
        "scores": _validated_scores(record["scores"], repository),
        "rationale": _require_string(record, "rationale"),
    }


def load_capability_catalog(
    path: Path,
) -> tuple[str, str, str, str, tuple[RepositorySource, ...], str]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"capability catalog contains invalid JSON: path={path}"
        ) from exc
    if not isinstance(decoded, dict) or set(decoded) != {
        "catalog_version",
        "observed_at_utc",
        "remote_observation_status",
        "remote_verification_limitations",
        "score_provenance",
        "sources",
    }:
        observed = set(decoded) if isinstance(decoded, dict) else set()
        raise ValueError(
            "capability catalog root differs from the exact schema: "
            f"path={path}, observed_fields={sorted(observed)}"
        )
    catalog_version = _require_string(decoded, "catalog_version")
    observed_at = _require_string(decoded, "observed_at_utc")
    _parse_utc(observed_at, "observed_at_utc")
    score_provenance = _require_string(decoded, "score_provenance")
    remote_observation_status = _require_string(
        decoded,
        "remote_observation_status",
    )
    remote_verification_limitations = _require_string(
        decoded,
        "remote_verification_limitations",
    )
    raw_sources = decoded["sources"]
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError(f"capability catalog requires source records: path={path}")
    sources = tuple(_validated_source(source) for source in raw_sources)
    repository_ids = tuple(source["repository"] for source in sources)
    if len(repository_ids) != len(set(repository_ids)):
        raise ValueError("capability catalog contains duplicate repository identities")
    catalog_hash = stable_hash(
        {
            "catalog_version": catalog_version,
            "observed_at_utc": observed_at,
            "remote_observation_status": remote_observation_status,
            "remote_verification_limitations": remote_verification_limitations,
            "score_provenance": score_provenance,
            "sources": [dict(source) for source in sources],
        }
    )
    return (
        catalog_version,
        observed_at,
        remote_observation_status,
        remote_verification_limitations,
        sources,
        catalog_hash,
    )


def _license_class(license_spdx: str) -> str:
    if license_spdx in PERMISSIVE_LICENSES:
        return "permissive"
    if license_spdx in BOUNDARY_LICENSES:
        return "copyleft_boundary_required"
    if license_spdx in {"NOASSERTION", "Proprietary"}:
        return "unresolved_or_proprietary"
    return "manual_review_required"


def _adoption_mode(source: RepositorySource, license_class: str) -> str:
    if license_class == "unresolved_or_proprietary":
        return "architecture_reference_only"
    if license_class in {"copyleft_boundary_required", "manual_review_required"}:
        return "subprocess_or_service_boundary_pilot_only"
    if source["source_kind"] == "obtuseai_internal":
        return "direct_reuse_candidate_with_attribution"
    return "clean_room_or_dependency_pilot_candidate"


def _freshness_score(observed_at: datetime, pushed_at: datetime) -> float:
    age_days = max(0.0, (observed_at - pushed_at).total_seconds() / 86_400)
    if age_days <= 30:
        return 1.0
    if age_days <= 180:
        return 0.8
    if age_days <= 365:
        return 0.6
    if age_days <= 730:
        return 0.35
    return 0.1


def _priority_score(
    source: RepositorySource,
    freshness_score: float,
) -> float:
    scores = source["scores"]
    maturity_score = min(1.0, math.log10(source["stars"] + 1) / 5.0)
    benefit = (
        0.26 * scores["dopey_fit"]
        + 0.18 * scores["evidence_value"]
        + 0.16 * scores["replayability"]
        + 0.12 * scores["isolation_fit"]
        + 0.12 * freshness_score
        + 0.08 * maturity_score
        + 0.08 * (1.0 - scores["integration_cost"])
    )
    return round(max(0.0, min(1.0, benefit - 0.2 * scores["adoption_risk"])), 6)


def _candidate_record(
    source: RepositorySource,
    observed_at: datetime,
) -> dict[str, Any]:
    license_class = _license_class(source["license_spdx"])
    freshness = _freshness_score(
        observed_at,
        _parse_utc(source["pushed_at_utc"], f"{source['repository']}.pushed_at_utc"),
    )
    priority = _priority_score(source, freshness)
    adoption_mode = _adoption_mode(source, license_class)
    body: dict[str, Any] = {
        **dict(source),
        "capabilities": list(source["capabilities"]),
        "license_class": license_class,
        "freshness_score": freshness,
        "priority_score": priority,
        "adoption_mode": adoption_mode,
        "quarantine_status": (
            "reference_only_unverified_provenance"
            if adoption_mode == "architecture_reference_only"
            else "quarantined_pending_provenance_verification"
        ),
        "remote_commit_ref_verified": False,
        "license_blob_verified": False,
        "capability_evidence_paths_verified": False,
        "provenance_gate_passed": False,
        "runtime_capability_status": "not_observed_usable",
        "automatic_installation_allowed": False,
        "automatic_source_copy_allowed": False,
        "automatic_activation_allowed": False,
        "trade_authority_effect": "none",
    }
    return {
        **body,
        "candidate_id": f"repository-capability:{stable_hash(body)[:24]}",
        "content_hash": stable_hash(body),
    }


def _capability_graph(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    capability_ids = sorted(
        {
            str(capability)
            for candidate in candidates
            for capability in cast(list[object], candidate["capabilities"])
        }
    )
    repository_nodes = [
        {
            "node_id": str(candidate["candidate_id"]),
            "node_kind": "repository",
            "label": str(candidate["repository"]),
            "content_hash": str(candidate["content_hash"]),
        }
        for candidate in candidates
    ]
    capability_nodes = [
        {
            "node_id": f"capability:{capability_id}",
            "node_kind": "capability",
            "label": capability_id,
        }
        for capability_id in capability_ids
    ]
    edges: list[dict[str, str]] = []
    for candidate in candidates:
        for capability in cast(list[object], candidate["capabilities"]):
            edge_body = {
                "source_node_id": str(candidate["candidate_id"]),
                "target_node_id": f"capability:{capability}",
                "edge_kind": "offers_candidate_capability",
                "source_commit": str(candidate["observed_head_sha"]),
            }
            edges.append(
                {
                    **edge_body,
                    "edge_id": f"capability-edge:{stable_hash(edge_body)[:24]}",
                }
            )
    graph_body: dict[str, Any] = {
        "graph_status": "derived_index_not_truth",
        "nodes": [*repository_nodes, *capability_nodes],
        "edges": edges,
        "canonical_source": "content_addressed_repository_candidate_records",
    }
    return {**graph_body, "graph_hash": stable_hash(graph_body)}


def _slice_records(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for capability_slice in CAPABILITY_SLICES:
        capability_ids = set(capability_slice["capability_ids"])
        matching = [
            candidate
            for candidate in candidates
            if capability_ids.intersection(
                str(capability)
                for capability in cast(list[object], candidate["capabilities"])
            )
        ]
        ranked = sorted(
            matching,
            key=lambda candidate: (
                -float(candidate["priority_score"]),
                str(candidate["repository"]),
            ),
        )
        records.append(
            {
                **dict(capability_slice),
                "capability_ids": list(capability_slice["capability_ids"]),
                "candidate_repositories": [
                    {
                        "repository": str(candidate["repository"]),
                        "priority_score": float(candidate["priority_score"]),
                        "adoption_mode": str(candidate["adoption_mode"]),
                        "runtime_capability_status": str(
                            candidate["runtime_capability_status"]
                        ),
                    }
                    for candidate in ranked[:5]
                ],
                "automatic_adoption_allowed": False,
            }
        )
    return records


def compose_capability_foundry_snapshot(
    catalog_path: Path,
) -> dict[str, Any]:
    (
        catalog_version,
        observed_at_text,
        remote_observation_status,
        remote_verification_limitations,
        sources,
        catalog_hash,
    ) = load_capability_catalog(catalog_path)
    observed_at = _parse_utc(observed_at_text, "observed_at_utc")
    candidates = sorted(
        (_candidate_record(source, observed_at) for source in sources),
        key=lambda candidate: (
            -float(candidate["priority_score"]),
            str(candidate["repository"]),
        ),
    )
    license_counts: dict[str, int] = {}
    for candidate in candidates:
        license_class = str(candidate["license_class"])
        license_counts[license_class] = license_counts.get(license_class, 0) + 1
    body: dict[str, Any] = {
        "artifact_type": CAPABILITY_FOUNDRY_ARTIFACT_TYPE,
        "foundry_version": CAPABILITY_FOUNDRY_VERSION,
        "foundry_status": CAPABILITY_FOUNDRY_STATUS,
        "catalog_version": catalog_version,
        "catalog_hash": catalog_hash,
        "snapshot_observed_at_utc": observed_at_text,
        "remote_observation_status": remote_observation_status,
        "remote_verification_limitations": remote_verification_limitations,
        "remote_provenance_verification_status": "not_performed_by_offline_foundry",
        "source_count": len(candidates),
        "obtuseai_internal_source_count": sum(
            candidate["source_kind"] == "obtuseai_internal" for candidate in candidates
        ),
        "external_oss_source_count": sum(
            candidate["source_kind"] == "external_oss" for candidate in candidates
        ),
        "license_class_counts": dict(sorted(license_counts.items())),
        "ranked_candidates": candidates,
        "capability_graph": _capability_graph(candidates),
        "priority_slices": _slice_records(candidates),
        "scoring_semantics": (
            "human-reviewed architecture fit and repository metadata; "
            "not runtime proof, alpha evidence, or permission to adopt"
        ),
        "foreign_source_files_downloaded": False,
        "foreign_code_executed": False,
        "packages_installed": False,
        "credentials_written": False,
        "automatic_installation_allowed": False,
        "automatic_source_copy_allowed": False,
        "automatic_activation_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "trade_authority_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return stamped(body)


def build_capability_foundry_snapshot(
    catalog_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    result = compose_capability_foundry_snapshot(catalog_path)
    write_json_atomic(output_path, result)
    return result
