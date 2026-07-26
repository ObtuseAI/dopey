"""Validate explicit manual approval text without reading or storing credentials."""
from __future__ import annotations

from typing import Any

from .broker_readiness_models import stable_hash
from .manual_approval_models import REQUIRED_OPERATOR_ACKNOWLEDGEMENT


FORBIDDEN_APPROVAL_EXPANSIONS: tuple[tuple[str, str], ...] = (
    ("allow live trading", "approval_mentions_live_trading"),
    ("approve live trading", "approval_mentions_live_trading"),
    ("enable live trading", "approval_mentions_live_trading"),
    ("allow credential storage", "approval_mentions_credential_storage"),
    ("store credentials", "approval_mentions_credential_storage"),
    ("approve credentials", "approval_mentions_credential_storage"),
    ("allow order placement", "approval_mentions_order_placement"),
    ("place orders", "approval_mentions_order_placement"),
    ("approve order placement", "approval_mentions_order_placement"),
    ("allow order cancellation", "approval_mentions_order_cancellation"),
    ("cancel orders", "approval_mentions_order_cancellation"),
    ("approve cancellation", "approval_mentions_order_cancellation"),
    ("allow scheduler", "approval_mentions_scheduler"),
    ("create scheduler", "approval_mentions_scheduler"),
    ("allow autonomous live trading", "approval_mentions_autonomous_live_trading"),
    ("autonomous live trading approved", "approval_mentions_autonomous_live_trading"),
    ("allow real sizing", "approval_mentions_real_sizing"),
    ("real sizing approved", "approval_mentions_real_sizing"),
    ("write access", "approval_expands_to_write_access"),
    ("broker execution", "approval_expands_to_broker_execution"),
)


def validate_manual_approval_text(approval_text: str | None, fixture_input: bool) -> dict[str, Any]:
    if approval_text is None or approval_text == "":
        return _result("approval_missing", False, False, ["approval_text_missing"], fixture_input, "")
    if approval_text == REQUIRED_OPERATOR_ACKNOWLEDGEMENT:
        return _result(
            "approval_valid_for_read_only_detector_only",
            True,
            True,
            ["exact_acknowledgement_fixture_valid", "future_bundle_still_required"],
            fixture_input,
            approval_text,
        )
    normalized = approval_text.lower()
    reason_codes = [
        reason_code
        for phrase, reason_code in FORBIDDEN_APPROVAL_EXPANSIONS
        if phrase in normalized
    ]
    if not reason_codes and "read-only" not in normalized:
        reason_codes.append("approval_not_scope_limited_to_read_only_detector")
    if not reason_codes:
        reason_codes.append("approval_text_does_not_exactly_match_required_acknowledgement")
    return _result("approval_invalid", True, False, sorted(set(reason_codes)), fixture_input, approval_text)


def _result(status: str, approval_present: bool, approval_valid: bool, reason_codes: list[str], fixture_input: bool, approval_text: str) -> dict[str, Any]:
    seed = {
        "validation_id": f"manual-gate-validation-{stable_hash({'status': status, 'text': approval_text})[:12]}",
        "gate_status": status,
        "approval_present": approval_present,
        "approval_valid": approval_valid,
        "detector_approved_now": False,
        "fixture_input": fixture_input,
        "approval_text_hash": stable_hash({"approval_text": approval_text}) if approval_text else "",
        "approval_text_stored": False,
        "reason_codes": reason_codes,
        "paper_only": True,
        "live_blocked": True,
        "no_credential": True,
        "no_external_file_read": True,
    }
    return {**seed, "validation_hash": stable_hash({**seed, "validation_hash": ""})}


def build_expected_manual_gate_results() -> list[dict[str, Any]]:
    samples: list[tuple[str, str | None]] = [
        ("missing_approval", None),
        ("exact_acknowledgement_future_fixture", REQUIRED_OPERATOR_ACKNOWLEDGEMENT),
        ("partial_acknowledgement", "I APPROVE DOPEY READ-ONLY BROKER CAPABILITY DETECTOR ONLY."),
        ("live_trading_expansion", "I approve read-only detector and allow live trading."),
        ("credential_storage_expansion", "I approve read-only detector and allow credential storage."),
        ("order_placement_expansion", "I approve read-only detector and allow order placement."),
        ("order_cancellation_expansion", "I approve read-only detector and allow order cancellation."),
        ("scheduler_expansion", "I approve read-only detector and allow scheduler."),
        ("autonomous_live_expansion", "I approve read-only detector and allow autonomous live trading."),
        ("real_sizing_expansion", "I approve read-only detector and allow real sizing."),
        ("write_access_expansion", "I approve read-only detector with write access."),
        ("broker_execution_expansion", "I approve read-only detector with broker execution."),
    ]
    results: list[dict[str, Any]] = []
    for case_id, approval_text in samples:
        result = validate_manual_approval_text(approval_text, True)
        results.append({**result, "case_id": case_id})
    return results
