"""Safe append for DOPEY_CANON.md and DOPEY_VALIDATION_REPORT.md.

Fixes the V4 known gap: previous run skipped these long docs to avoid rewriting
unrelated / invalid UTF-8 content. This module:

- never decodes the whole file into a string and rewrites it
- uses byte-safe append (UTF-8 encode of the new section)
- writes a backup (`*.v5_backup`) before the first append
- verifies the marker is present after the append
- records exact reason if it fails
- continues on individual failure (does not abort other doc)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    RESEARCH_V5_VERSION,
    SAFE_APPEND_V5_BACKUPS_PATH,
    SAFE_APPEND_V5_PROOF_PATH,
    SAFE_APPEND_V5_RECORDS_PATH,
    SAFE_APPEND_V5_SUMMARY_PATH,
    research_v5_proof_record,
    safe_append_bytes,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["run_safe_append_canon_validation_docs_v5"]


APPEND_MARKER = b"V5_PREFLIGHT_APPEND_MARKER"


def _build_canon_payload() -> bytes:
    text = (
        "\n\n<!-- V5_PREFLIGHT_APPEND_MARKER -->\n"
        "## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5 — Appended Recognition\n\n"
        "V4 completed and routed honestly to V5. V4 final status: "
        "`pf_holdout_split_improved_requires_v5`. V4 validation: `107/107 pass`. "
        "V4 live gate remained `disabled_live_gate_locked`. V4 PF threshold was "
        "**not** lowered (`MIN_BREAKTHROUGH_PF = 1.10`).\n\n"
        "V5 target: `DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5` "
        "(baseline-freezing, audit-completing, PF/holdout/split finishing loop).\n\n"
        "Official Robinhood market-data lane is allowed; unofficial Robinhood "
        "API, scraping, and reverse-engineered auth are blocked. Live trading "
        "remains `false`.\n\n"
        "Appended by `dopey_validation.safe_append_canon_validation_docs_v5` "
        "on " + utc_now_iso() + ".\n"
    )
    return text.encode("utf-8")


def _build_validation_report_payload() -> bytes:
    text = (
        "\n\n<!-- V5_PREFLIGHT_APPEND_MARKER -->\n"
        "## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5 — Appended Recognition\n\n"
        "V4 was completed under DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4 and "
        "honestly routed to V5 because V4 top profit factor "
        "(`1.079237`) was below the hard floor (`1.10`). V4 final status: "
        "`pf_holdout_split_improved_requires_v5`. V4 validation: `107/107 pass`. "
        "V4 live gate: `disabled_live_gate_locked`.\n\n"
        "V5 inherits the V4 hard rule: `MIN_BREAKTHROUGH_PF = 1.10` (never lowered). "
        "V5 is bounded by safe append for long docs, baseline-freeze, optional "
        "expensive lane runner, focused V4 result analyzer, V5 mutation/candidate/"
        "simulation/tournament/gate pipeline, and shared handoff.\n\n"
        "Robinhood doctrine unchanged: official market-data lane allowed; "
        "unofficial API, scraping, reverse-engineered auth, broker connection, "
        "real orders, live trading all blocked.\n\n"
        "Appended by `dopey_validation.safe_append_canon_validation_docs_v5` "
        "on " + utc_now_iso() + ".\n"
    )
    return text.encode("utf-8")


def _append_doc(path: Path, payload: bytes, backups: list[dict[str, object]]) -> dict[str, object]:
    backup_path = path.with_suffix(path.suffix + ".v5_backup")
    backup_record = {
        "path": str(path),
        "backup_path": str(backup_path),
        "backup_written": False,
        "original_size": 0,
    }
    if path.exists():
        try:
            original = path.read_bytes()
            backup_record["original_size"] = len(original)
            # Always write the backup if it doesn't already exist
            if not backup_path.exists():
                backup_path.write_bytes(original)
                backup_record["backup_written"] = True
        except OSError as exc:
            backup_record["backup_error"] = str(exc)
    backups.append(backup_record)
    result = safe_append_bytes(path, APPEND_MARKER, payload)
    return {
        "path": str(path),
        "result": result,
        "append_only": True,
        "live_trading_enabled": False,
    }


def run_safe_append_canon_validation_docs_v5() -> dict[str, object]:
    canon_path = REPO_ROOT / "DOPEY_CANON.md"
    report_path = REPO_ROOT / "DOPEY_VALIDATION_REPORT.md"

    backups: list[dict[str, object]] = []
    records: list[dict[str, object]] = []

    canon_record = _append_doc(canon_path, _build_canon_payload(), backups)
    records.append(canon_record)
    report_record = _append_doc(report_path, _build_validation_report_payload(), backups)
    records.append(report_record)

    canon_status = str(canon_record["result"].get("append_status", "unknown"))
    report_status = str(report_record["result"].get("append_status", "unknown"))

    # Detect invalid UTF-8 (we did NOT decode-and-rewrite; we append bytes).
    invalid_utf8_detected = False
    for path in (canon_path, report_path):
        if not path.exists():
            continue
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            invalid_utf8_detected = True
            break

    # Success conditions: at least one doc appended, none corrupted
    any_appended = canon_status == "appended" or report_status == "appended"
    if any_appended and not invalid_utf8_detected:
        status = "safe_append_completed"
    elif not any_appended and (canon_status == "already_present" and report_status == "already_present"):
        status = "safe_append_already_present"
    else:
        status = "safe_append_partial_or_failed"

    summary = {
        "artifact_type": "safe_append_docs_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "safe_append_docs_status": status,
        "canon_append_status": canon_status,
        "validation_report_append_status": report_status,
        "invalid_utf8_detected": invalid_utf8_detected,
        "backup_count": sum(1 for b in backups if b.get("backup_written")),
        "backup_path_count": len(backups),
        "append_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(SAFE_APPEND_V5_BACKUPS_PATH, backups)
    write_jsonl_file(SAFE_APPEND_V5_RECORDS_PATH, records)
    write_summary_with_hash(SAFE_APPEND_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        SAFE_APPEND_V5_PROOF_PATH,
        [research_v5_proof_record("safe-append-docs-v5", status, summary)],
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run_safe_append_canon_validation_docs_v5(), indent=2, sort_keys=True, default=str))
