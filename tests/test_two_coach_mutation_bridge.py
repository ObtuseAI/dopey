"""Integration coverage for coach quarantine and the first deterministic experiment."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from dopey.evolution.coach_bridge import (
    REFERENCE_PATTERN,
    CoachBridgeContractError,
    build_quarantined_coach_proposal_batch,
)
from dopey.protocols.identity import canonical_hash
from dopey_chart_vision.channel_containment_audit import build_channel_containment_audit
from dopey_chart_vision.grounded_structure_engine import (
    SWING_CONFIRMATION_RADIUS,
    _bar_id,
    build_blind_replay_evidence,
    build_grounded_structure_evidence,
)
from dopey_equity_swing.market_structure import Bar, confirmed_pivots, trend_channel
from dopey_evolution.run_coach_bridge import run_coach_bridge


def _history(count: int) -> list[Bar]:
    start = date(2024, 1, 2)
    rows: list[Bar] = []
    prior_close = 100.0
    for index in range(count):
        center = 100.0 + index * 0.08 + math.sin(index / 4.0) * 3.2
        close = center + math.sin(index / 2.7) * 0.35
        rows.append(
            Bar(
                date=(start + timedelta(days=index)).isoformat(),
                open=prior_close,
                high=max(prior_close, close) + 0.75,
                low=min(prior_close, close) - 0.75,
                close=close,
                adjusted_close=close,
                volume=1_000_000 + index * 2_000,
            )
        )
        prior_close = close
    last = rows[-1]
    rows[-1] = Bar(
        date=last["date"],
        open=last["open"],
        high=float(last["open"]) + 0.75,
        low=49.25,
        close=50.0,
        adjusted_close=50.0,
        volume=last["volume"],
    )
    return rows


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in _strings(child)]
    if isinstance(value, list):
        return [text for child in value for text in _strings(child)]
    return []


def _session(rows: list[Bar]) -> dict[str, Any]:
    data_version = "fixture-data-version"
    grounded = build_grounded_structure_evidence("SPY", "daily", rows, data_version)
    replay = build_blind_replay_evidence("SPY", "daily", rows, data_version, 5)
    channel = next(
        record
        for record in grounded["structures"]
        if record["structure_type"] == "trend_channel"
    )
    unrelated = next(
        record
        for record in grounded["structures"]
        if record["structure_type"] != "trend_channel"
    )
    channel_ref = str(channel["structure_id"])
    unrelated_ref = str(unrelated["structure_id"])
    analysis: dict[str, Any] = {
        "summary": f"Audit [[{channel_ref}]] before assigning a supportive interpretation.",
        "hypotheses": [
            {
                "title": "Channel containment unresolved",
                "mechanism": f"Current containment for [[{channel_ref}]] is unresolved.",
                "evidence_needed": f"Reconstruct [[{channel_ref}]] from past bars only.",
                "falsification": f"Reject the definition if [[{channel_ref}]] was never contained.",
            },
            {
                "title": "Unlinked structure remains blocked",
                "mechanism": f"Candidate [[{unrelated_ref}]] lacks an experiment.",
                "evidence_needed": f"A linked test for [[{unrelated_ref}]] is required.",
                "falsification": f"No claim follows from [[{unrelated_ref}]].",
            },
        ],
        "adversarial_findings": [
            {
                "title": "Supportive label can contradict containment",
                "risk": f"Slope alone can overstate [[{channel_ref}]].",
                "evidence_needed": f"Audit [[{channel_ref}]] at every timestamp.",
            }
        ],
        "uncertainties": [
            f"The definition around [[{channel_ref}]] may not generalize."
        ],
        "recommended_experiments": [
            {
                "title": "Channel containment audit",
                "objective": f"Rebuild [[{channel_ref}]] using only past bars.",
                "falsification": f"Invalidate if [[{channel_ref}]] was never contained.",
                "expected_information_gain": f"Resolve the meaning of [[{channel_ref}]].",
                "safety_constraints": "Paper research only with no activation or execution.",
            }
        ],
        "abstain": False,
    }
    reference_occurrences = [
        reference
        for text in _strings(analysis)
        for reference in REFERENCE_PATTERN.findall(text)
    ]
    body: dict[str, Any] = {
        "artifact_type": "two_coach_chart_research_session",
        "schema_version": "dopey-two-coach-chart-replay-v1",
        "generated_utc": "2026-07-22T12:00:00+00:00",
        "session_id": "two-coach:fixture",
        "status": "complete_research_coaching_no_prior_lessons",
        "verdict": "revise",
        "topology": {
            "coach_count": 2,
            "evidence_coach_id": "deterministic_structure_replay_coach_v1",
            "head_coach_id": "claude",
            "runtime_fallback_allowed": False,
        },
        "evidence_coach": {
            "coach_id": "deterministic_structure_replay_coach_v1",
            "packet_hash": "packet-hash",
            "structure_count": len(grounded["structures"]),
            "numeric_fact_count": len(grounded["numeric_facts"]),
            "lesson_count": 0,
            "structure_registry": grounded["structures"],
            "numeric_fact_registry": grounded["numeric_facts"],
            "prior_trade_lessons": {"lessons": [], "lesson_count": 0},
            "blind_replay": replay,
        },
        "head_coach": {
            "head_coach_id": "claude",
            "status": "completed_analysis_only",
            "analysis_only": True,
            "paper_only": True,
            "live_blocked": True,
            "runtime_fallback_used": False,
            "model_input_hash": "model-input-hash",
            "model_input_reveal_values_visible": False,
            "structured_analysis": analysis,
            "grounding": {
                "all_references_resolved": True,
                "direct_model_authored_levels_allowed": False,
                "numeric_grounding_status": "verified_no_free_numeric_literals",
                "reference_count": len(reference_occurrences),
                "unique_reference_count": len(set(reference_occurrences)),
                "referenced_ids": sorted(set(reference_occurrences)),
            },
        },
        "option_claim_boundary": {
            "status": "blocked_missing_point_in_time_entry_and_exit_option_evidence",
            "underlying_ohlcv_cannot_validate_option_pnl": True,
            "zero_dte_weekly_option_outcome_claim_allowed": False,
        },
        "mutation_boundary": {
            "coach_suggestions_quarantined": True,
            "purged_walk_forward_required": True,
            "held_out_validation_required": True,
            "automatic_activation_allowed": False,
        },
        "authority": {
            "research_only": True,
            "paper_only": True,
            "live_blocked": True,
            "broker_access": False,
            "order_authority": False,
            "strategy_promotion_allowed": False,
            "parameter_mutation_allowed": False,
        },
    }
    return {**body, "session_hash": canonical_hash(body)}


def test_coach_bridge_quarantines_linked_work_and_blocks_unlinked_hypotheses(
    tmp_path: Path,
) -> None:
    session = _session(_history(170))
    batch = build_quarantined_coach_proposal_batch((session,))
    projection = batch["sessions"][0]
    states = [record["proposal_state"] for record in projection["proposals"]]

    assert batch["outcome_status"] == "complete_quarantined_proposals"
    assert states == ["QUARANTINED", "BLOCKED_MISSING_LINKED_EXPERIMENT"]
    assert batch["evidence_weight"] == 0.0
    assert batch["mutation_targets_resolved"] == 0
    assert batch["automatic_apply_allowed"] is False
    assert batch["strategy_promotion_allowed"] is False
    encoded_batch = json.dumps(batch, sort_keys=True)
    assert "underlying_close_return_decimal" not in encoded_batch
    assert "underlying_max_adverse_excursion_decimal" not in encoded_batch

    coach_root = tmp_path / "coach"
    coach_root.mkdir()
    (coach_root / "spy_daily.json").write_text(json.dumps(session), encoding="utf-8")
    output_root = tmp_path / "proposals"
    first = run_coach_bridge(coach_root, output_root)
    second = run_coach_bridge(coach_root, output_root)
    assert first["ledger_appended"] is True
    assert second["ledger_appended"] is False
    assert first["batch_id"] == second["batch_id"]
    assert (
        len(
            (output_root / "batch_ledger.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        == 1
    )


def test_coach_bridge_fails_closed_before_writing_on_tampered_authority(
    tmp_path: Path,
) -> None:
    session = _session(_history(170))
    session["authority"]["order_authority"] = True
    session["session_hash"] = canonical_hash(
        {key: value for key, value in session.items() if key != "session_hash"}
    )
    coach_root = tmp_path / "coach"
    coach_root.mkdir()
    (coach_root / "spy_daily.json").write_text(json.dumps(session), encoding="utf-8")
    output_root = tmp_path / "proposals"

    with pytest.raises(CoachBridgeContractError, match="order_authority"):
        run_coach_bridge(coach_root, output_root)

    assert not output_root.exists()


def test_coach_bridge_fails_closed_before_writing_on_empty_session_root(
    tmp_path: Path,
) -> None:
    coach_root = tmp_path / "coach"
    coach_root.mkdir()
    output_root = tmp_path / "proposals"

    with pytest.raises(FileNotFoundError, match="contains no session JSON files"):
        run_coach_bridge(coach_root, output_root)

    assert not output_root.exists()


def test_coach_bridge_rejects_missing_abstention_on_abstained_session() -> None:
    session = _session(_history(170))
    session["status"] = "complete_research_coaching_abstained"
    del session["head_coach"]["structured_analysis"]["abstain"]
    session["session_hash"] = canonical_hash(
        {key: value for key, value in session.items() if key != "session_hash"}
    )

    with pytest.raises(CoachBridgeContractError, match="boolean abstention decision"):
        build_quarantined_coach_proposal_batch((session,))


def test_coach_bridge_rejects_false_abstention_on_abstained_session() -> None:
    session = _session(_history(170))
    session["status"] = "complete_research_coaching_abstained"
    session["head_coach"]["structured_analysis"]["abstain"] = False
    session["session_hash"] = canonical_hash(
        {key: value for key, value in session.items() if key != "session_hash"}
    )

    with pytest.raises(CoachBridgeContractError, match="conflicts with session status"):
        build_quarantined_coach_proposal_batch((session,))


def test_channel_audit_resolves_semantics_without_granting_predictive_or_live_authority() -> (
    None
):
    rows = _history(170)
    session = _session(rows)
    audit = build_channel_containment_audit(session, rows)
    grounded = build_grounded_structure_evidence(
        "SPY", "daily", rows, "fixture-data-version"
    )
    channel = next(
        record
        for record in grounded["structures"]
        if record["structure_type"] == "trend_channel"
    )

    assert audit["audit_status"] == "complete"
    assert audit["channel_observation_count"] > 0
    assert audit["contained_observation_count"] > 0
    assert audit["latest_observation"]["containment_state"] == "below_lower_bound"
    assert audit["hard_falsification_triggered"] is False
    assert (
        audit["predictive_edge_status"]
        == "blocked_pending_purged_multi_symbol_held_out_validation"
    )
    assert audit["mutation_resolution"]["strategy_parameter_mutation_allowed"] is False
    assert audit["order_authority"] is False and audit["live_blocked"] is True
    assert channel["containment_state"] == "below_lower_bound"
    assert channel["trend_direction"] == "uptrend"
    assert channel["directional_bias"] == "neutral"
    position_facts = [
        fact
        for fact in grounded["numeric_facts"]
        if fact["label"] == "confirmed_trend_channel_position"
    ]
    assert len(position_facts) == 1 and position_facts[0]["unit"] == "ratio"
    pivots = confirmed_pivots(rows, SWING_CONFIRMATION_RADIUS)
    channel_model = trend_channel(rows, pivots, 90)
    start_index = max(len(rows) - 90, 0)
    consumed_pivots = [
        pivot
        for pivot in pivots
        if pivot["role"] in {"support", "resistance"}
        and int(pivot["bar_index"]) >= start_index
    ]
    expected_source_ids = list(
        dict.fromkeys(
            [
                *(
                    _bar_id("SPY", rows[int(pivot["bar_index"])])
                    for pivot in consumed_pivots
                ),
                _bar_id("SPY", rows[-1]),
            ]
        )
    )
    assert len(consumed_pivots) == (
        int(channel_model["support_pivots_used"])
        + int(channel_model["resistance_pivots_used"])
    )
    assert channel["anchor_bar_ids"] == expected_source_ids
    assert channel["available_at_bar_id"] == expected_source_ids[-1]
    assert position_facts[0]["source_bar_ids"] == expected_source_ids


def test_channel_audit_selects_direct_hypothesis_ref_not_inherited_experiment_ref() -> (
    None
):
    rows = _history(170)
    session = _session(rows)
    structures = session["evidence_coach"]["structure_registry"]
    channel_ref = next(
        str(record["structure_id"])
        for record in structures
        if record["structure_type"] == "trend_channel"
    )
    unrelated_ref = next(
        str(record["structure_id"])
        for record in structures
        if record["structure_type"] != "trend_channel"
    )
    analysis = session["head_coach"]["structured_analysis"]
    experiment = analysis["recommended_experiments"][0]
    experiment["objective"] = (
        f"Rebuild [[{channel_ref}]] and compare [[{unrelated_ref}]] using only past bars."
    )
    analysis["hypotheses"][0]["falsification"] = (
        f"Reject [[{channel_ref}]] if it fails against [[{unrelated_ref}]]."
    )
    analysis["recommended_experiments"].append(
        {
            "title": "Unrelated structure stress test",
            "objective": f"Stress [[{unrelated_ref}]] under frozen assumptions.",
            "falsification": f"Reject the comparison if [[{unrelated_ref}]] changes definition.",
            "expected_information_gain": f"Bound sensitivity to [[{unrelated_ref}]].",
            "safety_constraints": "Paper research only with no activation or execution.",
        }
    )
    reference_occurrences = [
        reference
        for text in _strings(analysis)
        for reference in REFERENCE_PATTERN.findall(text)
    ]
    grounding = session["head_coach"]["grounding"]
    grounding["reference_count"] = len(reference_occurrences)
    grounding["unique_reference_count"] = len(set(reference_occurrences))
    grounding["referenced_ids"] = sorted(set(reference_occurrences))
    session["session_hash"] = canonical_hash(
        {key: value for key, value in session.items() if key != "session_hash"}
    )

    batch = build_quarantined_coach_proposal_batch((session,))
    proposals = batch["sessions"][0]["proposals"]
    quarantined = [
        record for record in proposals if record["proposal_state"] == "QUARANTINED"
    ]
    assert len(quarantined) == 2
    direct = next(
        record
        for record in quarantined
        if channel_ref
        in REFERENCE_PATTERN.findall(" ".join(record["hypothesis"].values()))
    )
    inherited = next(record for record in quarantined if record is not direct)
    assert len(direct["linked_experiments"]) == 2
    assert channel_ref in inherited["evidence_refs"]
    assert channel_ref not in REFERENCE_PATTERN.findall(
        " ".join(inherited["hypothesis"].values())
    )

    audit = build_channel_containment_audit(session, rows)

    assert audit["source_proposal_id"] == direct["proposal_id"]
    assert (
        audit["source_experiment_id"]
        == direct["linked_experiments"][0]["experiment_id"]
    )


def test_coach_bridge_has_no_live_or_mutation_executor_imports() -> None:
    paths = (
        Path("dopey/evolution/coach_bridge.py"),
        Path("dopey_evolution/run_coach_bridge.py"),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "dopey_live" not in source
    assert "propose_genome_mutation" not in source
    assert "apply_mutation_instruction" not in source
