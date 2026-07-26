"""Refresh the governed attention, universe, and prediction Playbook artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

from dopey_acceleration.common import write_json_atomic
from dopey_attention import (
    build_attention_snapshot,
    default_attention_policy,
    write_attention_snapshot,
)
from dopey_attention.engine import AttentionPaths
from dopey_data.history_store import load_history_manifest
from dopey_data.run_history_dataset_validation import run_history_dataset_validation
from dopey_equity_swing.fundamentals import (
    resolve_fundamental_snapshot,
    score_fundamental_snapshot,
)
from dopey_universe.evolving_universe import refresh_evolving_universe_membership

from .playbook_forward_evidence import update_playbook_forward_evidence
from .playbook_rankings import build_playbook_rankings
from .run_playbook_research_stage import run_playbook_research_stage


REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_MANIFEST_PATH = (
    REPO_ROOT / "dopey_data" / "history" / "history_dataset_manifest.json"
)
HISTORY_VALIDATION_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "history" / "history_dataset_validation.json"
)
HISTORY_RAW_ROOT = REPO_ROOT / "dopey_data" / "history" / "raw"
ATTENTION_OUTPUT_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "attention" / "attention_snapshot.json"
)
EVOLVING_UNIVERSE_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "universe" / "evolving_universe_summary.json"
)
SYMBOL_DOSSIERS_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "universe" / "symbol_dossiers.jsonl"
)
SCAN_REPORT_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "playbook" / "playbook_scan_report.json"
)
TRUST_REPORT_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "playbook" / "playbook_family_trust.json"
)
SWING_THESES_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl"
)
FUNDAMENTALS_PATH = (
    REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context" / "fundamentals.csv"
)
PLAYBOOK_OUTPUT_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "playbook" / "playbook_rankings.json"
)
PLAYBOOK_REFRESH_RESULT_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "playbook" / "playbook_refresh_result.json"
)
PLAYBOOK_FORWARD_SNAPSHOT_LEDGER_PATH = (
    REPO_ROOT
    / "artifacts"
    / "dopey"
    / "playbook"
    / "playbook_composite_recommendation_ledger.jsonl"
)
PLAYBOOK_FORWARD_SETTLEMENT_LEDGER_PATH = (
    REPO_ROOT
    / "artifacts"
    / "dopey"
    / "playbook"
    / "playbook_composite_settlement_ledger.jsonl"
)
PLAYBOOK_FORWARD_EVIDENCE_REPORT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "dopey"
    / "playbook"
    / "playbook_composite_forward_evidence.json"
)
REFRESH_INTERVAL_MINUTES = 240


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise OSError(
            f"playbook source is unavailable: path={path}, error={error}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"playbook source contains invalid JSON: path={path}, error={error}"
        ) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"playbook source must be a JSON object: path={path}")
    return cast(dict[str, object], value)


def _read_jsonl_objects(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise OSError(
            f"playbook JSONL source is unavailable: path={path}, error={error}"
        ) from error
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"playbook JSONL source contains invalid JSON: path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise TypeError(
                f"playbook JSONL row must be an object: path={path}, line={line_number}"
            )
        records.append(cast(dict[str, object], value))
    return records


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise OSError(
            f"playbook source cannot be hashed: path={path}, error={error}"
        ) from error
    return digest.hexdigest()


def _source_record(path: Path) -> dict[str, object]:
    try:
        stat = path.stat()
    except OSError as error:
        raise OSError(
            f"playbook source metadata is unavailable: path={path}, error={error}"
        ) from error
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _file_sha256(path),
        "size_bytes": stat.st_size,
        "file_modified_utc": datetime.fromtimestamp(
            stat.st_mtime, timezone.utc
        ).isoformat(),
    }


def _history_request() -> tuple[list[str], date]:
    manifest = load_history_manifest(HISTORY_MANIFEST_PATH)
    validation = _read_json_object(HISTORY_VALIDATION_PATH)
    if validation.get("dataset_status") != "valid_real_dataset":
        raise ValueError(
            "playbook refresh requires a valid real history dataset: "
            f"status={validation.get('dataset_status')!r}"
        )
    raw_end_date = validation.get("end_date")
    if not isinstance(raw_end_date, str):
        raise TypeError("history validation end_date must be a string")
    market_as_of = date.fromisoformat(raw_end_date)
    if (
        validation.get("manifest_reproducibility_hash")
        != manifest.manifest_reproducibility_hash
    ):
        raise ValueError(
            "history validation does not match the current manifest generation: "
            f"validation_hash={validation.get('manifest_reproducibility_hash')!r}, "
            f"manifest_hash={manifest.manifest_reproducibility_hash!r}"
        )
    symbols = sorted(
        {
            symbol
            for file_reference in manifest.data_files
            for symbol in file_reference.symbols
        }
    )
    if not symbols:
        raise ValueError(
            "history manifest contains no symbols for attention or playbook research"
        )
    return symbols, market_as_of


def _attention_paths() -> AttentionPaths:
    return {
        "repository_root": REPO_ROOT,
        "history_manifest_path": HISTORY_MANIFEST_PATH,
        "news_data_path": REPO_ROOT
        / "dopey_data"
        / "real"
        / "raw"
        / "news"
        / "news_events.jsonl",
        "news_manifest_path": REPO_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "news_context_manifest.json",
        "options_chain_root": REPO_ROOT
        / "dopey_data"
        / "real"
        / "raw"
        / "options_chains",
        "options_manifest_path": REPO_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "options_data_manifest.json",
    }


def publish_playbook_rankings(generated_utc: datetime) -> dict[str, object]:
    """Build and atomically publish rankings from the current governed sources."""

    if generated_utc.tzinfo is None or generated_utc.utcoffset() is None:
        raise ValueError("generated_utc must be timezone-aware")
    attention_snapshot = _read_json_object(ATTENTION_OUTPUT_PATH)
    raw_market_as_of = attention_snapshot.get("market_as_of_date")
    if not isinstance(raw_market_as_of, str):
        raise TypeError("playbook attention market_as_of_date must be a string")
    market_as_of = date.fromisoformat(raw_market_as_of)
    fundamental_snapshot = resolve_fundamental_snapshot(
        FUNDAMENTALS_PATH,
        market_as_of,
    )
    fundamental_confirmations = score_fundamental_snapshot(
        fundamental_snapshot["rows"],
        market_as_of,
    )
    source_snapshot_sha256 = str(fundamental_snapshot["sha256"])
    fundamental_confirmations = {
        symbol: {
            **record,
            "source_snapshot_sha256": source_snapshot_sha256,
        }
        for symbol, record in fundamental_confirmations.items()
    }
    source_paths = (
        HISTORY_VALIDATION_PATH,
        ATTENTION_OUTPUT_PATH,
        EVOLVING_UNIVERSE_PATH,
        SCAN_REPORT_PATH,
        TRUST_REPORT_PATH,
        SWING_THESES_PATH,
        FUNDAMENTALS_PATH,
        SYMBOL_DOSSIERS_PATH,
    )
    rankings = build_playbook_rankings(
        _read_json_object(SCAN_REPORT_PATH),
        _read_json_object(TRUST_REPORT_PATH),
        attention_snapshot,
        _read_json_object(EVOLVING_UNIVERSE_PATH),
        _read_jsonl_objects(SWING_THESES_PATH),
        fundamental_confirmations,
        _read_jsonl_objects(SYMBOL_DOSSIERS_PATH),
        [_source_record(path) for path in source_paths],
        generated_utc.astimezone(timezone.utc).isoformat(),
        REFRESH_INTERVAL_MINUTES,
    )
    write_json_atomic(PLAYBOOK_OUTPUT_PATH, rankings)
    return rankings


def publish_playbook_refresh_result(
    rankings: dict[str, object],
    attention: dict[str, object],
    universe: dict[str, object],
    forward_evidence: dict[str, object],
    completed_utc: datetime,
) -> dict[str, Any]:
    """Publish the schedule evidence bound to one exact rankings artifact."""

    if completed_utc.tzinfo is None or completed_utc.utcoffset() is None:
        raise ValueError("completed_utc must be timezone-aware")
    raw_lists = rankings.get("lists")
    if not isinstance(raw_lists, dict) or not all(
        isinstance(list_id, str) and isinstance(recommendation_ids, list)
        for list_id, recommendation_ids in raw_lists.items()
    ):
        raise TypeError("playbook rankings lists must map strings to lists")
    lists = cast(dict[str, list[object]], raw_lists)
    frontier_checks = (
        (
            "attention_generated_utc",
            rankings.get("attention_generated_utc"),
            attention.get("generated_at_utc"),
        ),
        (
            "market_data_as_of",
            rankings.get("market_data_as_of"),
            attention.get("market_as_of_date"),
        ),
        (
            "universe_active_count",
            rankings.get("universe_active_count"),
            universe.get("active_after"),
        ),
        (
            "universe_maximum_count",
            rankings.get("universe_maximum_count"),
            universe.get("maximum_active_universe_size"),
        ),
    )
    mismatches = [
        f"{field}: rankings={ranking_value!r}, source={source_value!r}"
        for field, ranking_value, source_value in frontier_checks
        if ranking_value != source_value
    ]
    if mismatches:
        raise ValueError(
            "playbook refresh result cannot certify mismatched source frontiers: "
            + "; ".join(mismatches)
        )

    result: dict[str, Any] = {
        "artifact_type": "playbook_refresh_result",
        "refresh_status": "complete",
        "playbook_status": rankings["playbook_status"],
        "generated_utc": rankings["generated_utc"],
        "completed_utc": completed_utc.astimezone(timezone.utc).isoformat(),
        "market_data_as_of": rankings["market_data_as_of"],
        "attention_status": attention["status"],
        "attention_rank_eligible_symbols": attention["ranking_eligible_symbol_count"],
        "universe_active_count": universe["active_after"],
        "universe_maximum_count": universe["maximum_active_universe_size"],
        "list_counts": {
            list_id: len(recommendation_ids)
            for list_id, recommendation_ids in lists.items()
        },
        "content_hash": rankings["content_hash"],
        "artifact_path": str(PLAYBOOK_OUTPUT_PATH),
        "forward_weight_evidence_status": forward_evidence["weight_calibration_status"],
        "forward_snapshot_count": forward_evidence["snapshot_count"],
        "forward_settled_count": forward_evidence["settled_count"],
        "forward_pending_count": forward_evidence["pending_count"],
        "forward_sample_sufficient": forward_evidence["sample_sufficient"],
        "forward_evidence_reproducibility_hash": forward_evidence[
            "reproducibility_hash"
        ],
        "forward_evidence_report_path": str(PLAYBOOK_FORWARD_EVIDENCE_REPORT_PATH),
        "research_ranked_not_execution_instruction": True,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(PLAYBOOK_REFRESH_RESULT_PATH, result)
    return result


def run_playbook_refresh(generated_utc: datetime) -> dict[str, Any]:
    """Run one multi-daily, research-only Playbook refresh."""

    if generated_utc.tzinfo is None or generated_utc.utcoffset() is None:
        raise ValueError("generated_utc must be timezone-aware")
    decision_time = generated_utc.astimezone(timezone.utc)
    validation_result = run_history_dataset_validation()
    if validation_result.get("dataset_status") != "valid_real_dataset":
        raise ValueError(
            "playbook refresh stopped because current history validation did not pass: "
            f"status={validation_result.get('dataset_status')!r}"
        )
    symbols, market_as_of = _history_request()
    attention = build_attention_snapshot(
        _attention_paths(),
        symbols,
        market_as_of,
        decision_time,
        default_attention_policy(),
    )
    write_attention_snapshot(attention, ATTENTION_OUTPUT_PATH)

    universe = refresh_evolving_universe_membership(decision_time)
    if universe.get("status") != "evolved":
        raise ValueError(
            "playbook refresh stopped because universe membership did not evolve cleanly: "
            f"status={universe.get('status')!r}, error={universe.get('error')!r}"
        )

    stage = run_playbook_research_stage()
    if stage.get("playbook_stage_status") != "playbook_research_complete":
        raise ValueError(
            "playbook refresh stopped because the research scan did not complete: "
            f"status={stage.get('playbook_stage_status')!r}"
        )

    rankings = publish_playbook_rankings(decision_time)
    persisted_validation = _read_json_object(HISTORY_VALIDATION_PATH)
    if persisted_validation.get("dataset_status") != "valid_real_dataset":
        raise ValueError(
            "persisted history validation stopped Playbook forward evidence: "
            f"status={persisted_validation.get('dataset_status')!r}"
        )
    raw_manifest_hash = persisted_validation.get("manifest_reproducibility_hash")
    if not isinstance(raw_manifest_hash, str) or not raw_manifest_hash:
        raise TypeError(
            "history validation manifest_reproducibility_hash must be a nonempty string"
        )
    forward_evidence = update_playbook_forward_evidence(
        rankings,
        HISTORY_RAW_ROOT,
        raw_manifest_hash,
        PLAYBOOK_FORWARD_SNAPSHOT_LEDGER_PATH,
        PLAYBOOK_FORWARD_SETTLEMENT_LEDGER_PATH,
        PLAYBOOK_FORWARD_EVIDENCE_REPORT_PATH,
    )
    return publish_playbook_refresh_result(
        rankings,
        attention,
        universe,
        forward_evidence,
        datetime.now(timezone.utc),
    )


def main() -> int:
    result = run_playbook_refresh(datetime.now(timezone.utc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
