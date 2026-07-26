"""Integrity coverage for append-only cognitive ledger audits."""

from __future__ import annotations

import json
from pathlib import Path

from dopey.intelligence_research.ledger_audit import audit_cognitive_ledger


def test_cognitive_ledger_audit_distinguishes_duplicates_from_conflicts(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "trials.jsonl"
    first = {"trial_id": "trial:1", "score": 1}
    conflicting = {"trial_id": "trial:1", "score": 0}
    ledger.write_text(
        "\n".join(
            (
                json.dumps(first),
                json.dumps(first),
                json.dumps(conflicting),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    audit = audit_cognitive_ledger(ledger, "trial_id")

    assert audit["audit_status"] == "blocked_conflicting_identity_records"
    assert audit["row_count"] == 3
    assert audit["unique_identity_count"] == 1
    assert audit["identical_duplicate_count"] == 1
    assert audit["conflicting_identity_count"] == 1
    assert audit["ledger_rewritten"] is False
    assert audit["historical_records_deleted"] is False
