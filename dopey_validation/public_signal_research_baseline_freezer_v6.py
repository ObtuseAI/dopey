"""V5 baseline freezer for V6: copy V5 artifacts into immutable baseline snapshots.

For each V5 source artifact:
- source path
- destination path (under `artifacts/dopey/signal_research_v6/baseline_snapshots/v5/`)
- file size
- SHA256 hash
- copied status
- timestamp
- baseline_snapshot=true
- live_trading_enabled=false
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import (
    BASELINE_FREEZE_V6_PROOF_PATH,
    BASELINE_FREEZE_V6_SUMMARY_PATH,
    BASELINE_SNAPSHOT_V6_MANIFEST_PATH,
    BASELINE_V5_ROOT,
    RESEARCH_V6_VERSION,
    baseline_snapshot_sources_v5,
    research_v6_proof_record,
    utc_now_iso,
    write_baseline_snapshot,
)


__all__ = ["run_public_signal_research_baseline_freezer_v6"]


EXPECTED_FREEZE_STATUS = "v5_baseline_frozen"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_record(src: Path, dest_dir: Path) -> dict[str, object] | None:
    snap = write_baseline_snapshot(src, dest_dir)
    if snap is None:
        return record_with_hash(
            {
                "artifact_type": "public_signal_research_v6_baseline_snapshot_manifest",
                "source_path": str(src),
                "destination_path": str(dest_dir / src.name) if src.name else "",
                "copied": False,
                "skipped_reason": "source_missing_or_unreadable",
                "baseline_snapshot": True,
                "live_trading_enabled": False,
                "timestamp": _now_iso(),
            },
            "manifest_hash",
        )
    return record_with_hash(
        {
            "artifact_type": "public_signal_research_v6_baseline_snapshot_manifest",
            **snap,
        },
        "manifest_hash",
    )


def run_public_signal_research_baseline_freezer_v6() -> dict[str, object]:
    BASELINE_V5_ROOT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    copied_count = 0
    skipped_count = 0
    total_bytes = 0

    sources = baseline_snapshot_sources_v5()
    for src in sources:
        rec = _manifest_record(src, BASELINE_V5_ROOT)
        if rec is None:
            skipped_count += 1
            continue
        if rec.get("copied"):
            copied_count += 1
            total_bytes += int(rec.get("file_size", 0))
        else:
            skipped_count += 1
        manifest.append(rec)

    status = EXPECTED_FREEZE_STATUS if copied_count > 0 else "v5_baseline_freeze_empty"
    summary = {
        "artifact_type": "public_signal_research_v6_baseline_freeze_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "baseline_freeze_status": status,
        "expected_status": EXPECTED_FREEZE_STATUS,
        "baseline_root": str(BASELINE_V5_ROOT),
        "source_count": len(sources),
        "copied_count": copied_count,
        "skipped_count": skipped_count,
        "total_bytes": total_bytes,
        "timestamp": _now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(BASELINE_SNAPSHOT_V6_MANIFEST_PATH, manifest)
    write_summary_with_hash(BASELINE_FREEZE_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        BASELINE_FREEZE_V6_PROOF_PATH,
        [research_v6_proof_record("public-signal-research-v6-baseline-freeze", status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_baseline_freezer_v6(), indent=2, sort_keys=True, default=str))
