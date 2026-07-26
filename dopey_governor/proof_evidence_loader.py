"""Load latest DOPEY proof/evidence registry records for the meta-governor.

All loaders are graceful: a missing registry returns an empty record so the governor can
still run and report missing-evidence. No network access, no broker connection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "artifacts" / "dopey"

EVIDENCE_PATHS = {
    "tournament": ARTIFACT_ROOT / "tournaments" / "dopey_tournament.jsonl",
    "mutation": ARTIFACT_ROOT / "mutations" / "mutation_registry.jsonl",
    "feedback": ARTIFACT_ROOT / "failure_feedback" / "failure_feedback_registry.jsonl",
    "failure_modes": ARTIFACT_ROOT / "failure_modes" / "failure_mode_registry.jsonl",
    "ensemble": ARTIFACT_ROOT / "ensemble_allocator" / "ensemble_allocation_registry.jsonl",
    "iv_surface": ARTIFACT_ROOT / "iv_surface" / "iv_surface_registry.jsonl",
    "macro_events": ARTIFACT_ROOT / "macro_events" / "macro_event_registry.jsonl",
    "champion": ARTIFACT_ROOT / "champion_registry" / "champion_registry.jsonl",
    "stronger_consistency": ARTIFACT_ROOT / "walk_forward_consistency" / "consistency_registry.jsonl",
    "regime_holdout_corpus_v2": ARTIFACT_ROOT / "regime_holdout_corpus_v2" / "corpus_registry.jsonl",
    "fundamental_fixtures": ARTIFACT_ROOT / "fundamental_fixtures" / "fundamental_registry.jsonl",
}


@dataclass
class EvidenceBundle:
    tournament: dict = field(default_factory=dict)
    mutation: dict = field(default_factory=dict)
    feedback: dict = field(default_factory=dict)
    failure_modes: dict = field(default_factory=dict)
    ensemble: dict = field(default_factory=dict)
    iv_surface: dict = field(default_factory=dict)
    macro_events: dict = field(default_factory=dict)
    champion: dict = field(default_factory=dict)
    stronger_consistency: dict = field(default_factory=dict)
    regime_holdout_corpus_v2: dict = field(default_factory=dict)
    fundamental_fixtures: dict = field(default_factory=dict)

    def layers_present(self) -> dict[str, bool]:
        return {
            "tournament": bool(self.tournament),
            "mutation": bool(self.mutation),
            "feedback": bool(self.feedback),
            "failure_modes": bool(self.failure_modes),
            "ensemble": bool(self.ensemble),
            "iv_surface": bool(self.iv_surface),
            "macro_events": bool(self.macro_events),
            "champion": bool(self.champion),
            "stronger_consistency": bool(self.stronger_consistency),
            "regime_holdout_corpus_v2": bool(self.regime_holdout_corpus_v2),
            "fundamental_fixtures": bool(self.fundamental_fixtures),
        }


def load_latest_jsonl(path: Path | str) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {}
    return json.loads(lines[-1])


def load_evidence_bundle(paths: dict[str, Path] | None = None) -> EvidenceBundle:
    paths = paths or EVIDENCE_PATHS
    return EvidenceBundle(
        tournament=load_latest_jsonl(paths["tournament"]),
        mutation=load_latest_jsonl(paths["mutation"]),
        feedback=load_latest_jsonl(paths["feedback"]),
        failure_modes=load_latest_jsonl(paths["failure_modes"]),
        ensemble=load_latest_jsonl(paths["ensemble"]),
        iv_surface=load_latest_jsonl(paths["iv_surface"]),
        macro_events=load_latest_jsonl(paths["macro_events"]),
        champion=load_latest_jsonl(paths["champion"]),
        stronger_consistency=load_latest_jsonl(paths["stronger_consistency"]),
        regime_holdout_corpus_v2=load_latest_jsonl(paths["regime_holdout_corpus_v2"]),
        fundamental_fixtures=load_latest_jsonl(paths["fundamental_fixtures"]),
    )
