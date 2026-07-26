"""Fail-closed reliability evidence for bounded research-cadence acceleration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from .common import read_optional_json, stable_hash


RELIABILITY_SLO_VERSION: Final[str] = "dopey-reliability-slo-v3"
MAX_RELIABILITY_SLO_AGE_HOURS: Final[float] = 30.0
MAX_FUTURE_CLOCK_SKEW_MINUTES: Final[float] = 5.0


def _blocked(
    artifact_path: Path,
    artifact_availability: str,
    slo_status: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "guard_status": "blocked_unverified_reliability_artifact",
        "cadence_acceleration_allowed": False,
        "artifact_path": str(artifact_path),
        "artifact_availability": artifact_availability,
        "slo_status": slo_status,
        "detail": detail,
    }


def evaluate_reliability_guard(
    repo_root: Path,
    issued_at: datetime,
) -> dict[str, Any]:
    """Verify current SLO integrity and decide only cadence acceleration."""
    if issued_at.tzinfo is None:
        raise ValueError("issued_at must be timezone-aware")
    slo_path = repo_root / "artifacts" / "dopey" / "ops" / "reliability_slo.json"
    try:
        slo, availability = read_optional_json(slo_path)
    except (OSError, TypeError, ValueError) as error:
        return _blocked(
            slo_path,
            "unreadable",
            "unverified",
            f"{type(error).__name__}: {error}",
        )
    if availability != "available":
        return _blocked(
            slo_path,
            availability,
            "unverified",
            "reliability SLO artifact is unavailable",
        )
    claimed_hash = slo.get("reproducibility_hash")
    unhashed = dict(slo)
    unhashed.pop("reproducibility_hash", None)
    if (
        not isinstance(claimed_hash, str)
        or not claimed_hash
        or stable_hash(unhashed) != claimed_hash
    ):
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            "reliability SLO reproducibility hash is missing or invalid",
        )
    required_boundary = (
        slo.get("artifact_type") == "reliability_slo"
        and slo.get("slo_version") == RELIABILITY_SLO_VERSION
        and slo.get("operational_cadence_guard_allowed") is True
        and slo.get("operational_cadence_guard_scope")
        == "fail_closed_cadence_acceleration_only"
        and slo.get("edge_evidence_allowed") is False
        and slo.get("readiness_gate_input_allowed") is False
        and slo.get("trading_gate_input_allowed") is False
        and slo.get("paper_only") is True
        and slo.get("live_blocked") is True
        and isinstance(slo.get("breaches"), list)
    )
    if not required_boundary:
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            "reliability SLO boundary or schema fields are invalid",
        )
    generated_at_text = str(slo.get("generated_at_utc", ""))
    try:
        generated_at = datetime.fromisoformat(generated_at_text)
    except ValueError:
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            f"reliability SLO generated_at_utc is invalid: value={generated_at_text!r}",
        )
    if generated_at.tzinfo is None:
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            "reliability SLO generated_at_utc must be timezone-aware",
        )
    generated_age_hours = (
        issued_at.astimezone(timezone.utc) - generated_at.astimezone(timezone.utc)
    ).total_seconds() / 3600.0
    if generated_age_hours < -(MAX_FUTURE_CLOCK_SKEW_MINUTES / 60.0):
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            "reliability SLO is future-dated beyond allowed clock skew",
        )
    if generated_age_hours > MAX_RELIABILITY_SLO_AGE_HOURS:
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            "reliability SLO generation timestamp is stale",
        )
    as_of_date = str(slo.get("as_of_date", ""))
    try:
        as_of = datetime.fromisoformat(as_of_date).date()
    except ValueError:
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            f"reliability SLO as_of_date is invalid: value={as_of_date!r}",
        )
    age_days = (issued_at.astimezone(timezone.utc).date() - as_of).days
    if age_days < 0 or age_days > 1:
        return _blocked(
            slo_path,
            availability,
            str(slo.get("slo_status", "unverified")),
            "reliability SLO as_of_date is future-dated or stale",
        )
    slo_status = str(slo.get("slo_status", "unverified"))
    breaches = [str(value) for value in slo["breaches"]]
    base = {
        "artifact_path": str(slo_path),
        "artifact_availability": availability,
        "slo_status": slo_status,
        "as_of_date": as_of_date,
        "age_days": age_days,
        "generated_at_utc": generated_at_text,
        "generated_age_hours": round(generated_age_hours, 4),
        "reproducibility_hash": claimed_hash,
        "breaches": breaches,
    }
    if slo_status == "within_error_budget" and not breaches:
        return {
            **base,
            "guard_status": "within_error_budget",
            "cadence_acceleration_allowed": True,
            "detail": "reliability evidence permits bounded cadence acceleration",
        }
    if slo_status == "error_budget_breached" and breaches:
        return {
            **base,
            "guard_status": "blocked_error_budget_breached",
            "cadence_acceleration_allowed": False,
            "detail": (
                "reliability work outranks cadence acceleration until the "
                "error budget is green"
            ),
        }
    return {
        **base,
        "guard_status": "blocked_unverified_reliability_artifact",
        "cadence_acceleration_allowed": False,
        "detail": "reliability SLO status and breach list are contradictory or unknown",
    }
