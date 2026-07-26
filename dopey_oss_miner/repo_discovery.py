"""Dopey repo discovery: build a candidate source registry (no network scraping).

Forked from Blunder inflow source_registry.py (Z:\\BFORK-20260630-020500\\blunder\\inflow\\
source_registry.py). Renamed module; the build_source_registry logic is preserved but the
hard-coded Obtuse artifact paths are replaced with a Dopey-native research-only candidate
builder that emits candidates without performing any network fetch. DOPEY never scrapes; all
external fetches require an explicit operator gate.

DOPEY lineage: Blunder inflow/source_registry.py -> dopey_oss_miner.repo_discovery
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from ._models import SourceCandidate


def _candidate(
    source_uri: str,
    source_type: str,
    trust_class: str,
    license_class: str,
    path: str,
    inline_text: str,
    scores: dict[str, float],
) -> SourceCandidate:
    candidate: SourceCandidate = {
        "source_uri": source_uri,
        "source_type": source_type,
        "trust_class": trust_class,
        "license_class": license_class,
        "authority_score": scores["authority_score"],
        "relevance_score": scores["relevance_score"],
        "freshness_score": scores["freshness_score"],
        "reproducibility_score": scores["reproducibility_score"],
        "validation_history_score": scores["validation_history_score"],
        "replayability_score": scores["replayability_score"],
        "internal_alignment_score": scores["internal_alignment_score"],
    }
    if path:
        candidate["path"] = path
    if inline_text:
        candidate["inline_text"] = inline_text
    return candidate


_MEDIUM = {
    "authority_score": 0.78,
    "relevance_score": 0.82,
    "freshness_score": 0.72,
    "reproducibility_score": 0.72,
    "validation_history_score": 0.68,
    "replayability_score": 0.74,
    "internal_alignment_score": 0.78,
}


def build_candidate(
    source_uri: str,
    source_type: str,
    trust_class: str,
    license_class: str,
    inline_text: str = "",
    path: str = "",
    scores: dict[str, float] | None = None,
) -> SourceCandidate:
    """Construct a single research-only SourceCandidate. No network access is performed."""
    return _candidate(
        source_uri=source_uri,
        source_type=source_type,
        trust_class=trust_class,
        license_class=license_class,
        path=path,
        inline_text=inline_text,
        scores=scores or dict(_MEDIUM),
    )


def build_source_registry(repo_root: Path) -> list[SourceCandidate]:
    """Build a candidate registry from a local workspace root. Only files that already exist on
    disk are referenced; nothing is fetched. DOPEY uses this for research-grade OSS discovery."""
    repo_root = Path(repo_root)
    candidates: list[SourceCandidate] = []
    for py in sorted(repo_root.rglob("*.py")):
        rel = str(py.relative_to(repo_root)).replace("\\", "/")
        candidates.append(
            build_candidate(
                source_uri=f"file://{py.resolve().as_posix()}",
                source_type="owned_workspace_file",
                trust_class="OWNED_WORKSPACE",
                license_class="OWNED",
                path=str(py),
            )
        )
    candidates.append(
        build_candidate(
            source_uri="official://operator-approved-reference-placeholder",
            source_type="official_reference",
            trust_class="OFFICIAL_REFERENCE",
            license_class="OFFICIAL_REFERENCE",
            inline_text=json.dumps(
                {
                    "source": "official-reference-placeholder",
                    "rule": "Official references are recordable but not fetched by autonomous scraping.",
                    "scheduler_containment": "No uncontrolled web access; current docs require explicit operator-approved fetch.",
                },
                sort_keys=True,
            ),
        )
    )
    candidates.append(
        build_candidate(
            source_uri="quarantine://blocked-private-repo-marker-sample",
            source_type="agent_trace",
            trust_class="UNTRUSTED_QUARANTINE",
            license_class="UNKNOWN",
            inline_text="Controlled blocked-source fixture: private repo marker and leaked code marker. This must be rejected.",
        )
    )
    return candidates


def write_source_registry(artifact_root: Path, candidates: list[SourceCandidate]) -> Path:
    output = artifact_root / "source_registry.json"
    artifact_root.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidates, indent=2, sort_keys=True), encoding="utf-8")
    return output
