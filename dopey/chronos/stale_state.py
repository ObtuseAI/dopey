"""Point-in-time validation for every material vNext context artifact."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


def _parse_time(value: str, artifact_label: str, field: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "context artifact timestamp is invalid: "
            f"artifact={artifact_label}, field={field}, value={value}"
        ) from exc
    if parsed.tzinfo is None:
        if len(value) == 10:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            raise ValueError(
                "context artifact timestamp requires timezone: "
                f"artifact={artifact_label}, field={field}, value={value}"
            )
    return parsed.astimezone(timezone.utc)


def validate_point_in_time_artifact(
    artifact: Mapping[str, Any],
    artifact_label: str,
    comparison_time: str,
    timestamp_fields: tuple[str, ...],
    maximum_age_hours: float,
) -> dict[str, Any]:
    if maximum_age_hours <= 0.0:
        raise ValueError(
            "point-in-time maximum age must be positive: "
            f"artifact={artifact_label}, maximum_age_hours={maximum_age_hours}"
        )
    if artifact.get("paper_only") is not True or artifact.get("live_blocked") is not True:
        raise ValueError(f"context artifact violates research governance: artifact={artifact_label}")
    timestamp_field = next(
        (field for field in timestamp_fields if str(artifact.get(field, "")).strip()),
        "",
    )
    if not timestamp_field:
        raise ValueError(
            "context artifact lacks point-in-time identity: "
            f"artifact={artifact_label}, accepted_fields={timestamp_fields}"
        )
    observed = _parse_time(str(artifact[timestamp_field]), artifact_label, timestamp_field)
    comparison = _parse_time(comparison_time, artifact_label, "comparison_time")
    age_hours = (comparison - observed).total_seconds() / 3600.0
    if age_hours < 0.0:
        raise ValueError(
            "context artifact is from the future: "
            f"artifact={artifact_label}, timestamp={observed.isoformat()}, comparison={comparison.isoformat()}"
        )
    if age_hours > maximum_age_hours:
        raise ValueError(
            "context artifact is stale: "
            f"artifact={artifact_label}, age_hours={age_hours:.6f}, maximum_age_hours={maximum_age_hours}"
        )
    return {
        "artifact": artifact_label,
        "status": "point_in_time_valid",
        "timestamp_field": timestamp_field,
        "timestamp": observed.isoformat(),
        "comparison_time": comparison.isoformat(),
        "age_hours": round(age_hours, 6),
        "maximum_age_hours": maximum_age_hours,
        "paper_only": True,
        "live_blocked": True,
    }


def calibration_context_or_unavailable(
    artifact: Mapping[str, Any],
    comparison_time: str,
    maximum_age_hours: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    timestamp_fields = ("observed_at", "generated_at", "as_of", "as_of_date")
    timestamp_field = next(
        (field for field in timestamp_fields if str(artifact.get(field, "")).strip()),
        "",
    )
    if not timestamp_field:
        unavailable = {
            "artifact_type": "vnext_calibration_context",
            "input_status": "unavailable_missing_point_in_time_timestamp",
            "settled_total": 0,
            "contested_total": 0,
            "expected_calibration_error": None,
            "promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
        proof = {
            "artifact": "calibration_summary",
            "status": "excluded_missing_point_in_time_timestamp",
            "accepted_fields": list(timestamp_fields),
            "used_as_calibration_evidence": False,
            "paper_only": True,
            "live_blocked": True,
        }
        return unavailable, proof
    proof = validate_point_in_time_artifact(
        artifact,
        "calibration_summary",
        comparison_time,
        timestamp_fields,
        maximum_age_hours,
    )
    return dict(artifact), {**proof, "used_as_calibration_evidence": True}
