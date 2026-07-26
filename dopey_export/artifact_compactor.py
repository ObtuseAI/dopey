"""Deterministic JSONL compaction summaries for DOPEY export bundles."""
from __future__ import annotations

import json
from pathlib import Path

from .artifact_selector import COMPACTED_ROOT, resolve_repo_path
from .export_manifest import canonical_export_hash, sha256_file, with_reproducibility_hash, write_json
from .export_models import (
    CompactedArtifact,
    CompactionPlan,
    CompactionSummary,
    ExportArtifact,
    LedgerCompactionSummary,
    FORBIDDEN_ACTIVE_EXPORT_TOKENS,
)


JSONL_SUMMARY_THRESHOLD_BYTES = 32_768
LARGE_JSONL_FULL_PARSE_THRESHOLD_BYTES = 8 * 1024 * 1024
MODEL_VERSION_KEYS = {
    "version",
    "registry_version",
    "mutation_registry_version",
    "feedback_optimizer_version",
    "iv_surface_expansion_version",
    "macro_event_expansion_version",
    "meta_governor_version",
    "ensemble_allocator_version",
    "reporting_bundle_version",
    "reporting_dashboard_index_version",
    "sector_peer_fundamental_expansion_version",
    "stronger_wf_consistency_version",
    "corpus_v2_version",
}
STRATEGY_ID_KEYS = {
    "strategy_id",
    "champion_strategy_id",
    "runner_up_strategy_id",
    "best_mutation",
    "best_mutated_strategy_id",
    "top_strategy",
    "top_consistent_strategy",
    "top_consistent_strategy_v2",
}
SUMMARY_METRIC_KEYS = {
    "strategies_reported",
    "families_reported",
    "scenario_report_card_count",
    "regime_report_card_count",
    "performance_attribution_count",
    "artifacts_scanned",
    "records_scanned",
    "hash_mismatches",
    "schema_warnings",
    "consistency_errors",
    "safety_errors",
    "forbidden_live_decisions_active",
    "live_blocked",
}


def _record_hash(record: dict) -> str:
    return canonical_export_hash(record)


def _collect_values(node, keys: set[str], values: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in keys and value not in (None, ""):
                values.add(str(value))
            _collect_values(value, keys, values)
    elif isinstance(node, list):
        for item in node:
            _collect_values(item, keys, values)


def _collect_safety_fields(node, values: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"mode", "live_trading_enabled", "funded_broker_connections_enabled", "allow_unofficial_robinhood_api", "live_blocked", "paper_only", "live_allowed"}:
                values.add(f"{key}={value}")
            _collect_safety_fields(value, values)
    elif isinstance(node, list):
        for item in node:
            _collect_safety_fields(item, values)


def _count_forbidden_tokens(node) -> int:
    if isinstance(node, dict):
        count = 0
        for key, value in node.items():
            if isinstance(value, str) and value in FORBIDDEN_ACTIVE_EXPORT_TOKENS:
                if "forbidden" in key or "blocked" in key or "allowed" in key:
                    continue
                count += 1
            count += _count_forbidden_tokens(value)
        return count
    if isinstance(node, list):
        return sum(_count_forbidden_tokens(item) for item in node)
    return 0


def _summary_metrics(record: dict) -> dict:
    metrics: dict[str, object] = {}
    for key in SUMMARY_METRIC_KEYS:
        if key in record:
            metrics[key] = record[key]
    return metrics


def build_ledger_compaction_summary(source_path: Path | str) -> LedgerCompactionSummary:
    path = Path(source_path)
    parse_all_records = path.stat().st_size <= LARGE_JSONL_FULL_PARSE_THRESHOLD_BYTES
    record_count = 0
    first_hash = ""
    last_hash = ""
    first_line = ""
    last_line = ""
    schema_keys: set[str] = set()
    versions: set[str] = set()
    strategy_ids: set[str] = set()
    safety_fields: set[str] = set()
    forbidden_count = 0
    top_metrics: dict[str, object] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if not first_line:
                first_line = line
            last_line = line
            record_count += 1
            if parse_all_records:
                record = json.loads(line)
                record_hash = _record_hash(record)
                if not first_hash:
                    first_hash = record_hash
                last_hash = record_hash
                schema_keys.update(str(key) for key in record.keys())
                _collect_values(record, MODEL_VERSION_KEYS, versions)
                _collect_values(record, STRATEGY_ID_KEYS, strategy_ids)
                _collect_safety_fields(record, safety_fields)
                forbidden_count += _count_forbidden_tokens(record)
                top_metrics.update(_summary_metrics(record))
    if not parse_all_records:
        sample_lines = [line for line in (first_line, last_line) if line]
        for line in sample_lines:
            record = json.loads(line)
            record_hash = _record_hash(record)
            if not first_hash:
                first_hash = record_hash
            last_hash = record_hash
            schema_keys.update(str(key) for key in record.keys())
            _collect_values(record, MODEL_VERSION_KEYS, versions)
            _collect_values(record, STRATEGY_ID_KEYS, strategy_ids)
            _collect_safety_fields(record, safety_fields)
            forbidden_count += _count_forbidden_tokens(record)
            top_metrics.update(_summary_metrics(record))
        top_metrics["large_jsonl_stream_summary"] = True
        top_metrics["source_size_bytes"] = path.stat().st_size
    seed = {
        "source_path": str(path),
        "record_count": record_count,
        "first_record_hash": first_hash,
        "last_record_hash": last_hash,
        "schema_keys": sorted(schema_keys),
        "model_versions_observed": sorted(versions),
        "strategy_ids_observed": sorted(strategy_ids),
        "safety_state_fields_observed": sorted(safety_fields),
        "forbidden_live_decision_count": forbidden_count,
        "top_level_summary_metrics": top_metrics,
        "source_sha256": sha256_file(path),
    }
    hashed = with_reproducibility_hash(seed)
    return LedgerCompactionSummary(
        source_path=str(path),
        record_count=record_count,
        first_record_hash=first_hash,
        last_record_hash=last_hash,
        schema_keys=sorted(schema_keys),
        model_versions_observed=sorted(versions),
        strategy_ids_observed=sorted(strategy_ids),
        safety_state_fields_observed=sorted(safety_fields),
        forbidden_live_decision_count=forbidden_count,
        top_level_summary_metrics=top_metrics,
        source_sha256=seed["source_sha256"],
        reproducibility_hash=hashed["reproducibility_hash"],
    )


def compact_jsonl_artifact(artifact: ExportArtifact, output_dir: Path | str) -> CompactedArtifact:
    source = resolve_repo_path(artifact.source_path)
    summary = build_ledger_compaction_summary(source)
    target = Path(output_dir) / f"{artifact.artifact_id}.summary.json"
    write_json(target, summary.to_dict())
    seed = {
        "source_artifact_id": artifact.artifact_id,
        "source_path": artifact.source_path,
        "compaction_method": "jsonl_ledger_summary_v1",
        "source_sha256": artifact.sha256,
        "compacted_sha256": sha256_file(target),
        "source_size_bytes": artifact.size_bytes,
        "compacted_size_bytes": target.stat().st_size,
        "record_count": artifact.record_count,
        "notes": ["source artifact preserved; compacted summary added for review"],
    }
    hashed = with_reproducibility_hash(seed)
    return CompactedArtifact(
        source_artifact_id=artifact.artifact_id,
        source_path=artifact.source_path,
        compacted_path=str(target),
        compaction_method="jsonl_ledger_summary_v1",
        source_sha256=artifact.sha256,
        compacted_sha256=seed["compacted_sha256"],
        source_size_bytes=artifact.size_bytes,
        compacted_size_bytes=seed["compacted_size_bytes"],
        record_count=artifact.record_count,
        notes=seed["notes"],
        reproducibility_hash=hashed["reproducibility_hash"],
    )


def build_compaction_plan(bundle_id: str, profile: str, artifacts: list[ExportArtifact], output_dir: Path | str) -> CompactionPlan:
    source_artifacts = [
        artifact for artifact in artifacts
        if artifact.source_path.endswith(".jsonl") and artifact.size_bytes >= JSONL_SUMMARY_THRESHOLD_BYTES
    ]
    seed = {
        "bundle_id": bundle_id,
        "profile": profile,
        "source_artifacts": [artifact.to_dict() for artifact in source_artifacts],
        "output_dir": str(output_dir),
        "jsonl_summary_threshold_bytes": JSONL_SUMMARY_THRESHOLD_BYTES,
    }
    return CompactionPlan(
        bundle_id=bundle_id,
        profile=profile,
        source_artifacts=source_artifacts,
        output_dir=str(output_dir),
        jsonl_summary_threshold_bytes=JSONL_SUMMARY_THRESHOLD_BYTES,
        reproducibility_hash=canonical_export_hash(seed),
    )


def compact_export_artifacts(bundle_id: str, profile: str, artifacts: list[ExportArtifact]) -> CompactionSummary:
    output_dir = COMPACTED_ROOT / bundle_id
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = build_compaction_plan(bundle_id, profile, artifacts, output_dir)
    compacted = [compact_jsonl_artifact(artifact, output_dir) for artifact in plan.source_artifacts]
    skipped = [
        {
            "artifact_id": artifact.artifact_id,
            "reason": "not_jsonl_or_below_threshold",
            "size_bytes": artifact.size_bytes,
        }
        for artifact in artifacts
        if artifact not in plan.source_artifacts
    ]
    seed = {
        "bundle_id": bundle_id,
        "compacted_artifacts": [artifact.to_dict() for artifact in compacted],
        "skipped_artifacts": skipped,
        "output_dir": str(output_dir),
    }
    return CompactionSummary(
        bundle_id=bundle_id,
        compacted_artifact_count=len(compacted),
        compacted_artifacts=compacted,
        skipped_artifacts=skipped,
        output_dir=str(output_dir),
        reproducibility_hash=canonical_export_hash(seed),
    )
