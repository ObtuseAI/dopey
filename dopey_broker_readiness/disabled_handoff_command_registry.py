"""Disabled command templates for a future read-only detector bundle."""
from __future__ import annotations

from typing import Any

from .approval_to_run_handoff_models import APPROVAL_TO_RUN_HANDOFF_GATE_VERSION, APPROVAL_TO_RUN_NEXT_GATE
from .broker_readiness_models import stable_hash


def build_disabled_handoff_command_templates() -> list[dict[str, Any]]:
    records = [
        _template(
            "disabled-handoff-template-prepare-future-bundle",
            "prepare_read_only_detector_future_bundle",
            "python -m dopey_broker_readiness.prepare_read_only_detector_future_bundle --paper-only --offline-fixtures",
        ),
        _template(
            "disabled-handoff-template-run-human-approved-detector",
            "run_human_approved_read_only_broker_capability_detector",
            "python -m dopey_broker_readiness.run_human_approved_read_only_broker_capability_detector --paper-only --offline-fixtures",
        ),
        _template(
            "disabled-handoff-template-verify-future-bundle",
            "verify_future_read_only_detector_bundle_safety",
            "python -m dopey_broker_readiness.verify_future_read_only_detector_bundle_safety --paper-only --offline-fixtures",
        ),
    ]
    return [{**record, "template_hash": _template_hash(record)} for record in records]


def _template(template_id: str, command_name: str, command_template: str) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "command_name": command_name,
        "command_template": command_template,
        "enabled": False,
        "allowed_now": False,
        "requires_separate_future_bundle": True,
        "requires_explicit_operator_reapproval": True,
        "requires_pre_run_safety_scan": True,
        "requires_post_run_evidence": True,
        "no_credential_read": True,
        "no_order_placement": True,
        "no_order_cancellation": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "paper_only": True,
        "live_blocked": True,
        "handoff_gate_version": APPROVAL_TO_RUN_HANDOFF_GATE_VERSION,
        "next_required_gate": APPROVAL_TO_RUN_NEXT_GATE,
        "template_hash": "",
    }


def _template_hash(record: dict[str, Any]) -> str:
    return stable_hash({**record, "template_hash": ""})
