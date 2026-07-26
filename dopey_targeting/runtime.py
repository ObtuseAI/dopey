"""Deterministic runtime for gate-blind per-symbol targeting research."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dopey.protocols.identity import canonical_hash
from dopey_acceleration.common import write_json_atomic

from .models import TargetingPolicy, default_targeting_policy
from .per_symbol_forecast_skill import (
    FORECAST_SKILL_VERSION,
    build_per_symbol_forecast_skill,
    load_playbook_settlement_records,
)
from .shadow_targeting_ledger import (
    SHADOW_LEDGER_VERSION,
    append_current_shadow_signals,
    build_shadow_evidence_report,
    settle_shadow_signals,
)
from .source_validation import validate_targeting_sources
from .symbol_candidate_registry import (
    CANDIDATE_REGISTRY_VERSION,
    build_symbol_candidate_registry,
    build_symbol_iv_profiles,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "dopey" / "targeting"
FORECAST_SKILL_PATH = ARTIFACT_ROOT / "per_symbol_forecast_skill.json"
CANDIDATE_REGISTRY_PATH = ARTIFACT_ROOT / "symbol_candidate_registry.json"
SHADOW_SIGNAL_LEDGER_PATH = ARTIFACT_ROOT / "shadow_targeting_ledger.jsonl"
SHADOW_SETTLEMENT_LEDGER_PATH = (
    ARTIFACT_ROOT / "shadow_targeting_settlement_ledger.jsonl"
)
SHADOW_EVIDENCE_PATH = ARTIFACT_ROOT / "shadow_targeting_evidence.json"
SOURCE_VALIDATION_PATH = ARTIFACT_ROOT / "targeting_source_validation.json"
SUMMARY_PATH = ARTIFACT_ROOT / "targeting_summary.json"
JsonObject = dict[str, object]
HistoryBars = Mapping[str, Sequence[Mapping[str, object]]]


@dataclass(frozen=True)
class TargetingPaths:
    history_root: Path
    history_manifest_path: Path
    playbook_detection_path: Path
    playbook_settlement_path: Path
    scanner_fitness_path: Path
    iv_calibration_rows_path: Path
    iv_calibration_summary_path: Path
    artifact_root: Path


def default_paths() -> TargetingPaths:
    """Return repository-local production research paths."""

    return TargetingPaths(
        history_root=REPOSITORY_ROOT / "dopey_data" / "history" / "raw",
        history_manifest_path=(
            REPOSITORY_ROOT
            / "dopey_data"
            / "history"
            / "history_dataset_manifest.json"
        ),
        playbook_detection_path=(
            REPOSITORY_ROOT
            / "artifacts"
            / "dopey"
            / "playbook"
            / "playbook_detection_ledger.jsonl"
        ),
        playbook_settlement_path=(
            REPOSITORY_ROOT
            / "artifacts"
            / "dopey"
            / "playbook"
            / "playbook_settlement_ledger.jsonl"
        ),
        scanner_fitness_path=(
            REPOSITORY_ROOT
            / "artifacts"
            / "dopey"
            / "evolution"
            / "scanner_fitness_last_eval.json"
        ),
        iv_calibration_rows_path=(
            REPOSITORY_ROOT
            / "artifacts"
            / "dopey"
            / "chain_analytics"
            / "model_iv_calibration_rows.jsonl"
        ),
        iv_calibration_summary_path=(
            REPOSITORY_ROOT
            / "artifacts"
            / "dopey"
            / "chain_analytics"
            / "model_iv_calibration_summary.json"
        ),
        artifact_root=ARTIFACT_ROOT,
    )


def _artifact_paths(root: Path) -> dict[str, Path]:
    return {
        "forecast_skill": root / FORECAST_SKILL_PATH.name,
        "candidate_registry": root / CANDIDATE_REGISTRY_PATH.name,
        "shadow_signals": root / SHADOW_SIGNAL_LEDGER_PATH.name,
        "shadow_settlements": root / SHADOW_SETTLEMENT_LEDGER_PATH.name,
        "shadow_evidence": root / SHADOW_EVIDENCE_PATH.name,
        "source_validation": root / SOURCE_VALIDATION_PATH.name,
        "summary": root / SUMMARY_PATH.name,
    }


def _validated_registry_hash(registry: Mapping[str, object]) -> str:
    supplied = registry.get("reproducibility_hash")
    if not isinstance(supplied, str) or not supplied:
        raise ValueError("candidate registry lacks reproducibility_hash")
    payload = {
        key: value
        for key, value in registry.items()
        if key != "reproducibility_hash"
    }
    expected = canonical_hash(payload)
    if supplied != expected:
        raise ValueError(
            "candidate registry reproducibility hash mismatch: "
            f"declared={supplied}, expected={expected}"
        )
    return supplied


def _persist_candidate_registry(
    registry: JsonObject,
    artifact_root: Path,
    stable_alias_path: Path,
) -> Path:
    registry_hash = _validated_registry_hash(registry)
    generation_path = (
        artifact_root
        / "registry_generations"
        / f"{registry_hash}.json"
    )
    if generation_path.exists():
        try:
            existing = json.loads(
                generation_path.read_text(
                    encoding="utf-8",
                    errors="strict",
                )
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                "immutable registry generation is unreadable: "
                f"path={generation_path}, error={error}"
            ) from error
        if existing != registry:
            raise ValueError(
                "immutable registry generation collision: "
                f"path={generation_path}"
            )
    else:
        write_json_atomic(generation_path, registry)
    write_json_atomic(stable_alias_path, registry)
    return generation_path


def _blocked_candidate_registry(
    source_validation: Mapping[str, object],
    source_hashes: Mapping[str, str],
    policy: TargetingPolicy,
    history: HistoryBars,
) -> JsonObject:
    candidates: list[JsonObject] = [
        {
            "symbol": symbol,
            "candidate_status": (
                "blocked_invalid_or_stale_upstream_evidence"
            ),
            "research_priority_score": 0.0,
            "targeting_score": 0.0,
            "directional_preference": "unavailable_upstream_evidence_blocked",
            "per_family_skill": {},
            "per_family_option_cost": {},
            "per_family_targeting_score": {},
            "history_profile": {
                "bar_count": len(bars),
                "latest_date": (
                    str(bars[-1].get("date", "")) if bars else None
                ),
                "data_quality_flags": [],
                "history_validation_status": "valid_hash_pinned_history",
            },
            "iv_profile": None,
            "shadow_attention_weight": 0.0,
            "stale_or_mismatched_evidence_consumed": False,
            "targeting_research_only": True,
            "promotion_allowed": False,
        }
        for symbol, bars in sorted(history.items())
    ]
    status_counts = (
        {
            "blocked_invalid_or_stale_upstream_evidence": len(candidates)
        }
        if candidates
        else {}
    )
    registry: JsonObject = {
        "artifact_type": "symbol_candidate_registry",
        "candidate_registry_version": CANDIDATE_REGISTRY_VERSION,
        "registry_status": "blocked_invalid_or_stale_upstream_evidence",
        "candidate_count": len(candidates),
        "candidate_status_counts": status_counts,
        "candidates": candidates,
        "source_hashes": dict(sorted(source_hashes.items())),
        "source_validation_reproducibility_hash": str(
            source_validation.get("reproducibility_hash", "")
        ),
        "capacity_policy": {
            "minimum_average_dollar_volume": (
                policy.minimum_average_dollar_volume
            ),
            "maximum_shadow_candidates": policy.maximum_shadow_candidates,
            "maximum_shadow_candidates_per_direction": (
                policy.maximum_shadow_candidates_per_direction
            ),
            "maximum_symbol_weight": policy.maximum_symbol_weight,
            "sector_concentration_status": (
                "unavailable_blocked_upstream_evidence"
            ),
        },
        "every_history_symbol_is_a_candidate": bool(history),
        "stale_or_mismatched_evidence_consumed": False,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    registry["reproducibility_hash"] = canonical_hash(registry)
    return registry


def _blocked_forecast_skill(
    source_validation: Mapping[str, object],
    source_hashes: Mapping[str, str],
) -> JsonObject:
    report: JsonObject = {
        "artifact_type": "per_symbol_forecast_skill",
        "forecast_skill_version": FORECAST_SKILL_VERSION,
        "forecast_skill_status": "blocked_invalid_or_stale_upstream_evidence",
        "symbol_count_with_settlements": 0,
        "graded_observation_count": 0,
        "duplicate_detection_count": 0,
        "rejected_reason_counts": {},
        "verdict_counts": {},
        "family_verdict_counts": {},
        "detector_verdict_counts": {},
        "per_symbol": {},
        "source_hashes": dict(sorted(source_hashes.items())),
        "source_validation_reproducibility_hash": str(
            source_validation.get("reproducibility_hash", "")
        ),
        "stale_or_mismatched_evidence_consumed": False,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    report["reproducibility_hash"] = canonical_hash(report)
    return report


def _blocked_shadow_evidence(
    source_validation: Mapping[str, object],
) -> JsonObject:
    report: JsonObject = {
        "artifact_type": "targeting_shadow_evidence_report",
        "shadow_ledger_version": SHADOW_LEDGER_VERSION,
        "shadow_evidence_status": (
            "blocked_invalid_or_stale_upstream_evidence"
        ),
        "settlement_count": 0,
        "symbol_family_count": 0,
        "human_research_review_eligible_count": 0,
        "raw_positive_buckets_requiring_overlap_review": 0,
        "per_symbol_family": {},
        "source_validation_reproducibility_hash": str(
            source_validation.get("reproducibility_hash", "")
        ),
        "stale_or_mismatched_evidence_consumed": False,
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    report["reproducibility_hash"] = canonical_hash(report)
    return report


def _blocked_summary(
    sources_report: Mapping[str, object],
    blockers: Sequence[Mapping[str, object]],
    history_symbol_count: int,
    candidate_registry: Mapping[str, object],
    observed_at: datetime,
    artifact_paths: Mapping[str, Path],
    registry_generation_path: Path,
) -> JsonObject:
    return {
        "artifact_type": "symbol_targeting_summary",
        "targeting_status": "blocked_invalid_or_stale_upstream_evidence",
        "observed_at_utc": observed_at.astimezone(timezone.utc).isoformat(),
        "history_symbol_count": history_symbol_count,
        "symbol_count_with_settled_skill_evidence": 0,
        "candidate_count": candidate_registry["candidate_count"],
        "verified_shadow_candidate_count": 0,
        "forecast_verdict_counts": {},
        "candidate_status_counts": candidate_registry[
            "candidate_status_counts"
        ],
        "shadow_recording": {
            "recording_status": "suppressed_upstream_evidence_blocked",
            "appended_signal_count": 0,
        },
        "shadow_settlement": {
            "settlement_status": "suppressed_upstream_evidence_blocked",
            "new_settlement_count": 0,
        },
        "shadow_evidence_status": "suppressed_upstream_evidence_blocked",
        "source_validation": dict(sources_report),
        "upstream_blocker_count": len(blockers),
        "upstream_blockers": [dict(blocker) for blocker in blockers],
        "candidate_registry_generation_path": str(
            registry_generation_path
        ),
        "artifacts": {
            **{
                key: str(value)
                for key, value in sorted(artifact_paths.items())
            },
            "candidate_registry_generation": str(
                registry_generation_path
            ),
        },
        "stale_or_mismatched_evidence_consumed": False,
        "gate_inputs_read": [],
        "live_book_inputs_read": [],
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "automatic_policy_mutation_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }


def run_symbol_targeting(
    paths: TargetingPaths,
    policy: TargetingPolicy,
    observed_at: datetime,
) -> JsonObject:
    """Run the complete shadow targeting cycle against local real evidence."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    artifact_paths = _artifact_paths(paths.artifact_root.resolve())
    sources = validate_targeting_sources(
        paths.history_root,
        paths.history_manifest_path,
        paths.playbook_detection_path,
        paths.playbook_settlement_path,
        paths.scanner_fitness_path,
        paths.iv_calibration_rows_path,
        paths.iv_calibration_summary_path,
        observed_at,
    )
    write_json_atomic(
        artifact_paths["source_validation"],
        sources.validation_report,
    )
    if sources.blockers:
        write_json_atomic(
            artifact_paths["forecast_skill"],
            _blocked_forecast_skill(
                sources.validation_report,
                sources.source_hashes,
            ),
        )
        write_json_atomic(
            artifact_paths["shadow_evidence"],
            _blocked_shadow_evidence(sources.validation_report),
        )
        blocked_registry = _blocked_candidate_registry(
            sources.validation_report,
            sources.source_hashes,
            policy,
            sources.history,
        )
        registry_generation_path = _persist_candidate_registry(
            blocked_registry,
            paths.artifact_root.resolve(),
            artifact_paths["candidate_registry"],
        )
        blocked_summary = _blocked_summary(
            sources.validation_report,
            sources.blockers,
            len(sources.history),
            blocked_registry,
            observed_at,
            artifact_paths,
            registry_generation_path,
        )
        write_json_atomic(artifact_paths["summary"], blocked_summary)
        return blocked_summary

    history: HistoryBars = sources.history
    settlement_load = load_playbook_settlement_records(
        sources.playbook_settlements
    )
    source_hashes = dict(sources.source_hashes)
    forecast_report = build_per_symbol_forecast_skill(
        settlement_load,
        source_hashes,
        policy,
    )

    iv_profiles = build_symbol_iv_profiles(
        sources.iv_calibration_rows,
        sources.iv_calibration_summary,
    )
    candidate_sources = {
        **source_hashes,
        "forecast_skill": str(forecast_report["reproducibility_hash"]),
        "source_validation": str(
            sources.validation_report["reproducibility_hash"]
        ),
    }
    candidate_registry = build_symbol_candidate_registry(
        history,
        forecast_report,
        iv_profiles,
        candidate_sources,
        policy,
    )

    write_json_atomic(
        artifact_paths["forecast_skill"],
        forecast_report,  # type: ignore[arg-type]
    )
    registry_generation_path = _persist_candidate_registry(
        candidate_registry,
        paths.artifact_root.resolve(),
        artifact_paths["candidate_registry"],
    )

    settled_detection_ids = {
        str(row.get("detection_id", ""))
        for row in sources.playbook_settlements
    }
    recording = append_current_shadow_signals(
        sources.playbook_detections,
        settled_detection_ids,
        candidate_registry,
        artifact_paths["shadow_signals"],
    )
    settlement = settle_shadow_signals(
        history,
        artifact_paths["shadow_signals"],
        artifact_paths["shadow_settlements"],
    )
    shadow_evidence = build_shadow_evidence_report(
        artifact_paths["shadow_settlements"],
        policy.minimum_effective_samples,
    )
    write_json_atomic(
        artifact_paths["shadow_evidence"],
        shadow_evidence,  # type: ignore[arg-type]
    )

    status_counts = candidate_registry.get("candidate_status_counts")
    eligible_count = (
        int(
            status_counts.get(
                "targeting_shadow_eligible_for_forward_validation",
                0,
            )
        )
        if isinstance(status_counts, dict)
        else 0
    )
    summary: JsonObject = {
        "artifact_type": "symbol_targeting_summary",
        "targeting_status": (
            "complete_shadow_research_candidates_require_forward_validation"
            if eligible_count
            else "complete_shadow_research_no_verified_candidates"
        ),
        "observed_at_utc": observed_at.astimezone(timezone.utc).isoformat(),
        "history_symbol_count": len(history),
        "symbol_count_with_settled_skill_evidence": forecast_report[
            "symbol_count_with_settlements"
        ],
        "candidate_count": candidate_registry["candidate_count"],
        "verified_shadow_candidate_count": eligible_count,
        "forecast_verdict_counts": forecast_report["verdict_counts"],
        "candidate_status_counts": candidate_registry[
            "candidate_status_counts"
        ],
        "source_validation": sources.validation_report,
        "upstream_blocker_count": 0,
        "upstream_blockers": [],
        "shadow_recording": recording,
        "shadow_settlement": settlement,
        "shadow_evidence_status": (
            "human_review_candidates_present"
            if shadow_evidence["human_research_review_eligible_count"]
            else "insufficient_forward_shadow_evidence"
        ),
        "candidate_registry_generation_path": str(
            registry_generation_path
        ),
        "artifacts": {
            **{
                key: str(value)
                for key, value in sorted(artifact_paths.items())
            },
            "candidate_registry_generation": str(
                registry_generation_path
            ),
        },
        "stale_or_mismatched_evidence_consumed": False,
        "gate_inputs_read": [],
        "live_book_inputs_read": [],
        "targeting_research_only": True,
        "advisory_only_never_a_gate_input": True,
        "promotion_allowed": False,
        "automatic_policy_mutation_allowed": False,
        "order_capability_present": False,
        "paper_only": True,
        "live_blocked": True,
        "profit_or_edge_claimed": False,
    }
    write_json_atomic(
        artifact_paths["summary"],
        summary,  # type: ignore[arg-type]
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run gate-blind per-symbol targeting research"
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=ARTIFACT_ROOT,
    )
    arguments = parser.parse_args()
    paths = default_paths()
    configured_paths = TargetingPaths(
        history_root=paths.history_root,
        history_manifest_path=paths.history_manifest_path,
        playbook_detection_path=paths.playbook_detection_path,
        playbook_settlement_path=paths.playbook_settlement_path,
        scanner_fitness_path=paths.scanner_fitness_path,
        iv_calibration_rows_path=paths.iv_calibration_rows_path,
        iv_calibration_summary_path=paths.iv_calibration_summary_path,
        artifact_root=arguments.artifact_root,
    )
    summary = run_symbol_targeting(
        configured_paths,
        default_targeting_policy(),
        datetime.now(timezone.utc),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
