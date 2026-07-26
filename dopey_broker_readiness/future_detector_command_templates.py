"""Disabled command templates for a future read-only capability detector."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .broker_readiness_models import stable_hash


FORBIDDEN_COMMAND_SUBSTRINGS: tuple[str, ...] = (
    "credential",
    "token_path",
    "api_key",
    ".env",
    "place-order",
    "place_order",
    "cancel-order",
    "cancel_order",
    "scheduler",
    "live-execution",
    "enable-live",
    "market-data-network",
    "broker-connect",
)


@dataclass(frozen=True)
class FutureDetectorCommandTemplate:
    template_id: str
    command_template: str
    description: str
    enabled: bool
    requires_manual_approval: bool
    allowed_now: bool
    detector_runs_now: bool
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool
    template_hash: str

    def __post_init__(self) -> None:
        if self.enabled is not False:
            raise ValueError("future detector command templates must be disabled by default")
        if self.requires_manual_approval is not True:
            raise ValueError("future detector command templates must require manual approval")
        if self.allowed_now is not False or self.detector_runs_now is not False:
            raise ValueError("future detector command templates cannot run now")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("future detector command templates require paper_only=true and live_blocked=true")
        finding = validate_command_template_text(self.command_template)
        if finding:
            raise ValueError(f"forbidden command template content: {finding}")

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "FutureDetectorCommandTemplate":
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_command_template_text(command_template: str) -> str:
    normalized = command_template.lower()
    for token in FORBIDDEN_COMMAND_SUBSTRINGS:
        if token in normalized:
            return token
    return ""


def template_hash(template: FutureDetectorCommandTemplate) -> str:
    payload = asdict(template)
    payload["template_hash"] = ""
    return stable_hash(payload)


def _make_template(template_id: str, command_template: str, description: str) -> FutureDetectorCommandTemplate:
    seed = FutureDetectorCommandTemplate(
        template_id=template_id,
        command_template=command_template,
        description=description,
        enabled=False,
        requires_manual_approval=True,
        allowed_now=False,
        detector_runs_now=False,
        reason_codes=["disabled_template_only", "manual_approval_required", "detector_not_approved_now"],
        paper_only=True,
        live_blocked=True,
        template_hash="",
    )
    return FutureDetectorCommandTemplate(**{**seed.to_dict(), "template_hash": template_hash(seed)})


def build_future_detector_command_templates() -> list[FutureDetectorCommandTemplate]:
    return [
        _make_template(
            "read-only-capability-detector-requires-approval",
            "python -m dopey_broker_readiness.run_read_only_capability_detector --requires-approval",
            "future read-only capability detector entrypoint, disabled until exact approval exists",
        ),
        _make_template(
            "read-only-capability-detector-fixture-only-dry-run",
            "python -m dopey_broker_readiness.run_read_only_capability_detector --dry-run-fixture-only",
            "future fixture-only dry-run template, disabled in this packet bundle",
        ),
        _make_template(
            "read-only-options-tool-inventory-requires-approval",
            "python -m dopey_broker_readiness.run_read_only_capability_detector --inventory-shapes-only --requires-approval",
            "future read-only options tool inventory shape check, disabled until approval",
        ),
        _make_template(
            "read-only-account-metadata-shape-requires-approval",
            "python -m dopey_broker_readiness.run_read_only_capability_detector --metadata-shapes-only --requires-approval",
            "future read-only account metadata shape check, disabled until approval",
        ),
    ]


def command_template_records() -> list[dict[str, Any]]:
    return [template.to_dict() for template in build_future_detector_command_templates()]


def forbidden_command_template_cases() -> list[dict[str, Any]]:
    samples = [
        ("template-with-token-path", "python -m detector --token_path C:/secret"),
        ("template-with-env-file", "python -m detector --config .env"),
        ("template-with-order-placement", "python -m detector --place-order"),
        ("template-with-order-cancellation", "python -m detector --cancel-order"),
        ("template-with-scheduler", "python -m detector --scheduler"),
        ("template-with-live-execution", "python -m detector --live-execution"),
        ("template-with-network-market-data", "python -m detector --market-data-network"),
        ("template-with-broker-connection", "python -m detector --broker-connect"),
    ]
    records: list[dict[str, Any]] = []
    for case_id, command in samples:
        token = validate_command_template_text(command)
        records.append({
            "case_id": case_id,
            "command_template": command,
            "enabled": False,
            "requires_manual_approval": True,
            "allowed_now": False,
            "validation_status": "rejected",
            "reason_codes": [f"forbidden_command_token_{token}", "template_rejected"],
            "paper_only": True,
            "live_blocked": True,
        })
    return [{**record, "case_hash": stable_hash({**record, "case_hash": ""})} for record in records]
