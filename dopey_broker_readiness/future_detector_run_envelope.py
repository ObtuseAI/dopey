"""Envelope builders for a future read-only detector run bundle."""
from __future__ import annotations

from .approval_to_run_handoff_models import (
    FutureDetectorRunEnvelope,
    future_detector_run_envelope_hash,
)


def build_future_detector_run_envelope(
    envelope_id: str,
    handoff_input_id: str,
    command_template_id: str,
    future_bundle_allowed_to_be_prepared: bool,
) -> dict[str, object]:
    seed = FutureDetectorRunEnvelope(
        envelope_id=envelope_id,
        handoff_input_id=handoff_input_id,
        command_template_id=command_template_id,
        command_template_enabled=False,
        command_template_allowed_now=False,
        future_bundle_allowed_to_be_prepared=future_bundle_allowed_to_be_prepared,
        requires_separate_future_bundle=True,
        requires_explicit_operator_reapproval=True,
        requires_pre_run_safety_scan=True,
        requires_post_run_evidence=True,
        detector_run_allowed_now=False,
        broker_connection_allowed_now=False,
        credential_allowed_now=False,
        live_order_allowed_now=False,
        scheduler_allowed_now=False,
        real_sizing_allowed_now=False,
        paper_only=True,
        live_blocked=True,
        envelope_hash="",
    )
    return {**seed.to_dict(), "envelope_hash": future_detector_run_envelope_hash(seed)}
