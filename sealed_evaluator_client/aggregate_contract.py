"""Validate aggregate-only sealed responses without exposing observations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SealedAggregateResponse:
    request_id: str
    candidate_id: str
    frozen_specification_hash: str
    submission_number: int
    aggregate_metrics: tuple[tuple[str, float], ...]
    failure_codes: tuple[str, ...]
    evaluator_version: str
    passed: bool
    evaluator_issued_at: str


PROHIBITED_RAW_KEYS = frozenset(
    {
        "observations",
        "trades",
        "timestamps",
        "quotes",
        "contracts",
        "rows",
        "features",
        "outcomes",
    }
)
ALLOWED_FAILURE_CODES = frozenset(
    {
        "candidate_failed_metric_floor",
        "insufficient_holdout_sample",
        "negative_control_anomaly",
        "risk_limit_breach",
        "schema_mismatch",
        "sealed_evaluator_internal_error",
    }
)


def require_canonical_utc(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"sealed response requires a canonical UTC timestamp: field={field_name}"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"sealed response timestamp is invalid: field={field_name}, value={value!r}"
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(
            f"sealed response timestamp requires a UTC offset: field={field_name}"
        )
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if value != canonical:
        raise ValueError(
            "sealed response timestamp must be canonical UTC ISO-8601: "
            f"field={field_name}, value={value!r}, expected={canonical!r}"
        )
    return value


def validate_aggregate_response(
    response: SealedAggregateResponse,
    allowed_metric_ids: frozenset[str],
    expected_request_id: str,
    expected_candidate_id: str,
    expected_frozen_specification_hash: str,
    expected_evaluator_version: str,
) -> None:
    if response.request_id != expected_request_id or not response.request_id.startswith("sealed-request-"):
        raise ValueError("sealed response is not bound to the frozen request")
    if response.candidate_id != expected_candidate_id:
        raise ValueError("sealed response candidate identity mismatch")
    if response.frozen_specification_hash != expected_frozen_specification_hash:
        raise ValueError("sealed response specification identity mismatch")
    if response.submission_number != 1:
        raise ValueError("sealed evaluation is one-shot per frozen candidate")
    if not expected_evaluator_version or response.evaluator_version != expected_evaluator_version:
        raise ValueError("sealed response evaluator version mismatch")
    require_canonical_utc(response.evaluator_issued_at, "evaluator_issued_at")
    if not isinstance(response.passed, bool):
        raise ValueError("sealed response passed verdict must be boolean")
    if len(response.frozen_specification_hash) != 64 or any(
        character not in "0123456789abcdef" for character in response.frozen_specification_hash
    ):
        raise ValueError("sealed response requires a hexadecimal frozen specification identity")
    metric_ids = [metric_id for metric_id, _ in response.aggregate_metrics]
    if len(metric_ids) != len(set(metric_ids)):
        raise ValueError("sealed response contains duplicate aggregate metric IDs")
    prohibited = sorted(
        metric_id
        for metric_id in metric_ids
        if any(raw_key in metric_id.lower() for raw_key in PROHIBITED_RAW_KEYS)
    )
    if prohibited:
        raise ValueError(f"sealed response exposes raw holdout fields: keys={prohibited}")
    undeclared = sorted(set(metric_ids).difference(allowed_metric_ids))
    if undeclared:
        raise ValueError(f"sealed response contains undeclared aggregate metrics: keys={undeclared}")
    if any(not math.isfinite(value) for _, value in response.aggregate_metrics):
        raise ValueError("sealed aggregate metrics must be finite")
    if any(Decimal(str(value)).as_tuple().exponent < -12 for _, value in response.aggregate_metrics):
        raise ValueError("sealed aggregate metric precision exceeds the declared 12-decimal limit")
    if len(response.failure_codes) != len(set(response.failure_codes)) or any(
        not code for code in response.failure_codes
    ):
        raise ValueError("sealed failure codes must be non-empty and unique")
    unknown_failure_codes = sorted(set(response.failure_codes).difference(ALLOWED_FAILURE_CODES))
    if unknown_failure_codes:
        raise ValueError(f"sealed response contains undeclared failure codes: codes={unknown_failure_codes}")
    if response.passed:
        if not response.aggregate_metrics or response.failure_codes:
            raise ValueError(
                "passed sealed response requires aggregate metrics and no failure codes"
            )
    elif response.aggregate_metrics or not response.failure_codes:
        raise ValueError(
            "failed sealed response requires failure codes and no aggregate metrics"
        )
    if not response.candidate_id or not response.evaluator_version:
        raise ValueError("sealed response identity is incomplete")
