"""Atomic one-shot reservation for aggregate-only sealed evaluation requests."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROHIBITED_REQUEST_TERMS = frozenset(
    {"observation", "trade", "timestamp", "quote", "contract", "row", "feature", "outcome"}
)


@dataclass(frozen=True, slots=True)
class SealedEvaluationRequest:
    request_id: str
    candidate_id: str
    frozen_specification_hash: str
    aggregate_metric_ids: tuple[str, ...]
    evaluator_id: str
    evaluator_version: str
    requested_at: str
    submission_number: int
    raw_holdout_access: bool
    paper_only: bool
    live_blocked: bool


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"sealed request SHA-256 identity is invalid: field={field_name}")


def _require_utc(value: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("sealed request timestamp requires a UTC offset")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if value != canonical:
        raise ValueError(f"sealed request timestamp must be canonical UTC: value={value!r}")


def _validate_metric_ids(metric_ids: tuple[str, ...]) -> None:
    if not metric_ids or len(metric_ids) != len(set(metric_ids)):
        raise ValueError("sealed request requires unique predeclared aggregate metric IDs")
    prohibited = sorted(
        metric_id
        for metric_id in metric_ids
        if not metric_id
        or any(term in metric_id.lower() for term in PROHIBITED_REQUEST_TERMS)
    )
    if prohibited:
        raise ValueError(f"sealed request asks for raw or invalid fields: metric_ids={prohibited}")


SUBMISSION_RECORD_FIELDS = frozenset(
    {
        "candidate_id",
        "frozen_specification_hash",
        "submission_count",
        "request_id",
        "requested_at",
        "evaluator_id",
        "evaluator_version",
        "aggregate_metric_ids",
    }
)


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"sealed holdout budget field must be a non-empty string: field={field_name}")
    return value


def _validate_existing_submissions(
    candidate_submissions: dict[str, object],
    frozen_hash_submissions: dict[str, object],
    submissions_used: int,
    aggregate_metric_ids: tuple[str, ...],
    evaluator_id: str,
    evaluator_version: str,
) -> None:
    if (
        submissions_used != len(candidate_submissions)
        or submissions_used != len(frozen_hash_submissions)
    ):
        raise ValueError("sealed holdout budget global and per-candidate accounting disagree")
    seen_request_ids: set[str] = set()
    for candidate_key, raw_record in candidate_submissions.items():
        if not isinstance(candidate_key, str) or not candidate_key:
            raise ValueError("sealed holdout budget contains an invalid candidate key")
        if not isinstance(raw_record, dict) or set(raw_record) != SUBMISSION_RECORD_FIELDS:
            raise ValueError("sealed holdout budget contains an invalid submission record schema")
        record = raw_record
        if record.get("candidate_id") != candidate_key:
            raise ValueError("sealed holdout budget candidate key does not match its record")
        frozen_hash = _require_non_empty_string(
            record.get("frozen_specification_hash"),
            "frozen_specification_hash",
        )
        _require_sha256(frozen_hash, "frozen_specification_hash")
        if frozen_hash_submissions.get(frozen_hash) != record:
            raise ValueError("sealed holdout budget candidate and frozen-hash maps disagree")
        if record.get("submission_count") != 1:
            raise ValueError("sealed holdout budget contains a non-one-shot submission")
        request_id = _require_non_empty_string(record.get("request_id"), "request_id")
        if not request_id.startswith("sealed-request-") or request_id in seen_request_ids:
            raise ValueError("sealed holdout budget request identity is invalid or duplicated")
        seen_request_ids.add(request_id)
        requested_at = _require_non_empty_string(record.get("requested_at"), "requested_at")
        _require_utc(requested_at)
        if record.get("evaluator_id") != evaluator_id:
            raise ValueError("sealed holdout budget evaluator identity changed after reservation")
        if record.get("evaluator_version") != evaluator_version:
            raise ValueError("sealed holdout budget evaluator version changed after reservation")
        if record.get("aggregate_metric_ids") != list(aggregate_metric_ids):
            raise ValueError("sealed holdout budget metrics changed after reservation")
    for frozen_hash_key, raw_record in frozen_hash_submissions.items():
        if not isinstance(frozen_hash_key, str):
            raise ValueError("sealed holdout budget contains an invalid frozen-hash key")
        _require_sha256(frozen_hash_key, "frozen_specification_hash")
        if not isinstance(raw_record, dict):
            raise ValueError("sealed holdout budget contains an invalid frozen-hash record")
        candidate_key = raw_record.get("candidate_id")
        if raw_record.get("frozen_specification_hash") != frozen_hash_key:
            raise ValueError("sealed holdout budget frozen-hash key does not match its record")
        if not isinstance(candidate_key, str) or candidate_submissions.get(candidate_key) != raw_record:
            raise ValueError("sealed holdout budget frozen-hash reverse mapping is invalid")


def reserve_sealed_submission(
    budget_path: Path,
    candidate_id: str,
    frozen_specification_hash: str,
    aggregate_metric_ids: tuple[str, ...],
    evaluator_version: str,
    requested_at: str,
) -> SealedEvaluationRequest:
    if not candidate_id or not evaluator_version:
        raise ValueError("sealed request identity fields cannot be empty")
    _require_sha256(frozen_specification_hash, "frozen_specification_hash")
    _require_utc(requested_at)
    _validate_metric_ids(aggregate_metric_ids)
    lock_path = budget_path.with_suffix(f"{budget_path.suffix}.lock")
    temporary_path = budget_path.with_suffix(f"{budget_path.suffix}.{os.getpid()}.tmp")
    descriptor: int | None = None
    lock_acquired = False
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        lock_acquired = True
        os.close(descriptor)
        descriptor = None
        decoded = json.loads(budget_path.read_text(encoding="utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("sealed holdout budget must be a mapping")
        if decoded.get("schema_version") != "dopey-sealed-budget-v1":
            raise ValueError("sealed holdout budget schema version is unsupported")
        if decoded.get("environment_id") != "dopey-options-paper-v1":
            raise ValueError("sealed holdout budget environment identity mismatch")
        if decoded.get("raw_holdout_access") is not False or decoded.get("aggregate_feedback_only") is not True:
            raise ValueError("sealed holdout budget violates aggregate-only isolation")
        if decoded.get("status") != "configured_external_evaluator":
            raise PermissionError("sealed evaluator is not externally configured")
        configured_evaluator_id = _require_non_empty_string(
            decoded.get("evaluator_id"),
            "evaluator_id",
        )
        configured_evaluator_version = _require_non_empty_string(
            decoded.get("evaluator_version"),
            "evaluator_version",
        )
        if evaluator_version != configured_evaluator_version:
            raise PermissionError("sealed request evaluator version differs from frozen configuration")
        maximum = decoded.get("maximum_submissions_per_frozen_candidate")
        if maximum != 1:
            raise ValueError("sealed holdout budget must be one-shot")
        maximum_total = decoded.get("maximum_total_submissions")
        submissions_used = decoded.get("submissions_used")
        if (
            not isinstance(maximum_total, int)
            or isinstance(maximum_total, bool)
            or maximum_total <= 0
            or not isinstance(submissions_used, int)
            or isinstance(submissions_used, bool)
            or submissions_used < 0
        ):
            raise ValueError("sealed holdout budget has invalid global submission accounting")
        if submissions_used >= maximum_total:
            raise PermissionError("sealed holdout global submission budget is exhausted")
        allowed_metric_ids = decoded.get("allowed_aggregate_metric_ids")
        if (
            not isinstance(allowed_metric_ids, list)
            or any(not isinstance(metric_id, str) for metric_id in allowed_metric_ids)
            or tuple(allowed_metric_ids) != aggregate_metric_ids
        ):
            raise PermissionError("sealed request metrics differ from the frozen evaluation declaration")
        submissions = decoded.get("candidate_submissions")
        hash_submissions = decoded.get("frozen_hash_submissions")
        if not isinstance(submissions, dict) or not isinstance(hash_submissions, dict):
            raise ValueError("sealed holdout budget lacks candidate and specification-hash accounting")
        _validate_existing_submissions(
            submissions,
            hash_submissions,
            submissions_used,
            aggregate_metric_ids,
            configured_evaluator_id,
            configured_evaluator_version,
        )
        if candidate_id in submissions:
            raise PermissionError(f"sealed holdout submission already consumed: candidate_id={candidate_id}")
        if frozen_specification_hash in hash_submissions:
            raise PermissionError(
                "sealed holdout submission already consumed for frozen specification hash"
            )
        request_body = {
            "candidate_id": candidate_id,
            "frozen_specification_hash": frozen_specification_hash,
            "aggregate_metric_ids": list(aggregate_metric_ids),
            "evaluator_id": configured_evaluator_id,
            "evaluator_version": evaluator_version,
            "requested_at": requested_at,
            "submission_number": 1,
            "raw_holdout_access": False,
            "paper_only": True,
            "live_blocked": True,
        }
        request_id = f"sealed-request-{_canonical_hash(request_body)[:24]}"
        submission_record = {
            "candidate_id": candidate_id,
            "frozen_specification_hash": frozen_specification_hash,
            "submission_count": 1,
            "request_id": request_id,
            "requested_at": requested_at,
            "evaluator_id": configured_evaluator_id,
            "evaluator_version": configured_evaluator_version,
            "aggregate_metric_ids": list(aggregate_metric_ids),
        }
        submissions[candidate_id] = submission_record
        hash_submissions[frozen_specification_hash] = submission_record
        decoded["submissions_used"] = submissions_used + 1
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    decoded,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, budget_path)
        return SealedEvaluationRequest(
            request_id=request_id,
            candidate_id=candidate_id,
            frozen_specification_hash=frozen_specification_hash,
            aggregate_metric_ids=aggregate_metric_ids,
            evaluator_id=configured_evaluator_id,
            evaluator_version=evaluator_version,
            requested_at=requested_at,
            submission_number=1,
            raw_holdout_access=False,
            paper_only=True,
            live_blocked=True,
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path.exists():
            temporary_path.unlink()
        if lock_acquired and lock_path.exists():
            lock_path.unlink()
