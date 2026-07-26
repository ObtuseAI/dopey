"""Safety contracts for the autonomous coached-evolution cycle."""

from __future__ import annotations

import json
from pathlib import Path

from dopey_evolution.coached_evolution_cycle import (
    count_paid_sessions_on_utc_date,
    session_matches_packet,
)


def test_session_reuse_requires_exact_packet_route_and_no_fallback() -> None:
    packet = {"session_id": "two-coach:one", "packet_hash": "packet-one"}
    session = {
        "artifact_type": "two_coach_chart_research_session",
        "session_id": "two-coach:one",
        "evidence_coach": {"packet_hash": "packet-one"},
        "topology": {
            "head_coach_id": "claude",
            "runtime_fallback_allowed": False,
        },
    }

    assert session_matches_packet(session, packet, "claude") is True
    assert session_matches_packet(session, packet, "codex") is False
    session["topology"]["runtime_fallback_allowed"] = True
    assert session_matches_packet(session, packet, "claude") is False


def test_paid_attempt_budget_includes_partial_paid_failures(tmp_path: Path) -> None:
    ledger_path = tmp_path / "session_ledger.jsonl"
    records = (
        {
            "artifact_type": "two_coach_chart_research_session",
            "generated_utc": "2026-07-22T10:00:00+00:00",
            "head_coach": {"paid_response_count": 5},
        },
        {
            "artifact_type": "two_coach_session_failure",
            "recorded_utc": "2026-07-22T11:00:00+00:00",
            "paid_response_count": 3,
        },
        {
            "artifact_type": "two_coach_session_failure",
            "recorded_utc": "2026-07-22T12:00:00+00:00",
            "paid_response_count": 0,
        },
        {
            "artifact_type": "two_coach_chart_research_session",
            "generated_utc": "2026-07-23T10:00:00+00:00",
            "head_coach": {"paid_response_count": 5},
        },
    )
    ledger_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    assert count_paid_sessions_on_utc_date(ledger_path, "2026-07-22") == 2
