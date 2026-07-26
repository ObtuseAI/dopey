"""Fail-closed, append-only evidence for research mutation evaluations.

This ledger has no execution or promotion authority. It preserves every measured
candidate, binds each entry to its predecessor, pins the current head in a separate
content-addressed anchor, and makes any fitness drop an explicit rollback-required
decision. Corrupt or truncated history blocks every future append.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import NoReturn, TypeAlias, TypedDict, cast


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

EPISTEMIC_MUTATION_LEDGER_VERSION = "dopey-epistemic-mutation-ledger-v1"
GENESIS_HASH = "0" * 64
CONTAINED_LEDGER_DIRECTORY = Path("artifacts/dopey/epistemic")
CHAIN_FIELDS = frozenset({"sequence", "previous_hash", "entry_hash"})


class MutationDecision(TypedDict):
    decision: str
    rollback_required: bool
    fitness_delta: float
    reason_codes: list[str]


class CorruptionEvidence(TypedDict):
    failure_code: str
    message: str
    ledger_path: str
    verified_record_count: int
    line_number: int | None
    sequence: int | None
    expected: str | None
    observed: str | None
    evidence_hash: str


class LedgerAuditEvidence(TypedDict):
    ledger_version: str
    ledger_path: str
    integrity_status: str
    decision: str
    rollback_required: bool
    record_count: int
    head_hash: str
    corruption: CorruptionEvidence | None


class EpistemicMutationLedgerError(RuntimeError):
    """Base error for contained research-mutation ledger failures."""


class EpistemicMutationLedgerCorruptionError(EpistemicMutationLedgerError):
    """Raised when mutation history or its pinned head cannot be verified."""

    def __init__(self, evidence: CorruptionEvidence) -> None:
        self.evidence = evidence
        super().__init__(
            f"{evidence['failure_code']}: {evidence['message']}; "
            f"ledger_path={evidence['ledger_path']}"
        )


class EpistemicMutationLedgerLockError(EpistemicMutationLedgerError):
    """Raised when another writer may own the append lock."""


class EpistemicMutationConflictError(EpistemicMutationLedgerError):
    """Raised when an immutable mutation ID is reused with different evidence."""


class EpistemicMutationLedgerWriteError(EpistemicMutationLedgerError):
    """Raised when durable append or head-anchor persistence fails."""


def _canonical_json(value: Mapping[str, JsonValue]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_hash(value: Mapping[str, JsonValue]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _reject_nonfinite_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant is prohibited: value={value}")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_utc_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"timestamp is not ISO-8601: value={value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp must include a UTC offset: value={value!r}")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"timestamp must be UTC: value={value!r}")


def _validate_fitness(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"mutation fitness must be numeric: field={field_name}, value={value!r}"
        )
    if not math.isfinite(float(value)) or float(value) < 0.0 or float(value) > 1.0:
        raise ValueError(
            f"mutation fitness must be finite and within [0, 1]: "
            f"field={field_name}, value={value!r}"
        )


def evaluate_mutation_fitness(
    baseline_fitness: float,
    candidate_fitness: float,
) -> MutationDecision:
    """Return a measure-only decision; a drop always requires rollback."""
    _validate_fitness(baseline_fitness, "baseline_fitness")
    _validate_fitness(candidate_fitness, "candidate_fitness")
    fitness_delta = float(candidate_fitness) - float(baseline_fitness)
    if fitness_delta < 0.0:
        return {
            "decision": "rollback_required",
            "rollback_required": True,
            "fitness_delta": fitness_delta,
            "reason_codes": ["candidate_fitness_below_baseline"],
        }
    if fitness_delta == 0.0:
        return {
            "decision": "retain_baseline_no_improvement",
            "rollback_required": False,
            "fitness_delta": fitness_delta,
            "reason_codes": ["candidate_fitness_did_not_improve"],
        }
    return {
        "decision": "eligible_for_operator_review",
        "rollback_required": False,
        "fitness_delta": fitness_delta,
        "reason_codes": ["candidate_fitness_improved"],
    }


def resolve_epistemic_mutation_ledger_path(
    repository_root: Path,
    ledger_path: Path,
) -> Path:
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"repository root is not a directory: path={root}")
    contained_root = (root / CONTAINED_LEDGER_DIRECTORY).resolve(strict=False)
    candidate = ledger_path if ledger_path.is_absolute() else root / ledger_path
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(contained_root)
    except ValueError as error:
        raise PermissionError(
            "epistemic mutation ledger must remain under the contained artifact root: "
            f"contained_root={contained_root}, ledger_path={resolved}"
        ) from error
    if resolved.suffix != ".jsonl":
        raise ValueError(
            f"epistemic mutation ledger must use a .jsonl suffix: path={resolved}"
        )
    return resolved


def epistemic_mutation_ledger_anchor_path(ledger_path: Path) -> Path:
    return ledger_path.with_suffix(f"{ledger_path.suffix}.head.json")


def _replace_file(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _corruption_evidence(
    ledger_path: Path,
    failure_code: str,
    message: str,
    verified_record_count: int,
    line_number: int | None,
    sequence: int | None,
    expected: str | None,
    observed: str | None,
) -> CorruptionEvidence:
    body: dict[str, JsonValue] = {
        "failure_code": failure_code,
        "message": message,
        "ledger_path": str(ledger_path),
        "verified_record_count": verified_record_count,
        "line_number": line_number,
        "sequence": sequence,
        "expected": expected,
        "observed": observed,
    }
    return {
        "failure_code": failure_code,
        "message": message,
        "ledger_path": str(ledger_path),
        "verified_record_count": verified_record_count,
        "line_number": line_number,
        "sequence": sequence,
        "expected": expected,
        "observed": observed,
        "evidence_hash": _canonical_hash(body),
    }


def _raise_corruption(
    ledger_path: Path,
    failure_code: str,
    message: str,
    verified_record_count: int,
    line_number: int | None,
    sequence: int | None,
    expected: str | None,
    observed: str | None,
) -> NoReturn:
    raise EpistemicMutationLedgerCorruptionError(
        _corruption_evidence(
            ledger_path,
            failure_code,
            message,
            verified_record_count,
            line_number,
            sequence,
            expected,
            observed,
        )
    )


def _load_records(ledger_path: Path) -> list[dict[str, JsonValue]]:
    if not ledger_path.exists():
        return []
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        _raise_corruption(
            ledger_path,
            "ledger_unreadable",
            f"ledger could not be read: error={error}",
            0,
            None,
            None,
            None,
            None,
        )
    records: list[dict[str, JsonValue]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            _raise_corruption(
                ledger_path,
                "blank_ledger_line",
                "append-only ledger contains a blank line",
                len(records),
                line_number,
                len(records) + 1,
                "canonical JSON object",
                "blank line",
            )
        try:
            decoded = json.loads(
                line,
                parse_constant=_reject_nonfinite_json_constant,
            )
        except ValueError as error:
            _raise_corruption(
                ledger_path,
                "malformed_json",
                f"ledger record is not valid JSON: error={error}",
                len(records),
                line_number,
                len(records) + 1,
                "canonical JSON object",
                line[:256],
            )
        if not isinstance(decoded, dict):
            _raise_corruption(
                ledger_path,
                "non_object_record",
                "ledger record is not a JSON object",
                len(records),
                line_number,
                len(records) + 1,
                "JSON object",
                type(decoded).__name__,
            )
        records.append(cast(dict[str, JsonValue], decoded))
    return records


def _verify_record_semantics(
    ledger_path: Path,
    record: dict[str, JsonValue],
    expected_sequence: int,
) -> None:
    line_number = expected_sequence
    if record.get("ledger_version") != EPISTEMIC_MUTATION_LEDGER_VERSION:
        _raise_corruption(
            ledger_path,
            "ledger_version_mismatch",
            "record ledger version is not supported",
            expected_sequence - 1,
            line_number,
            expected_sequence,
            EPISTEMIC_MUTATION_LEDGER_VERSION,
            str(record.get("ledger_version")),
        )
    mutation_id = record.get("mutation_id")
    if not isinstance(mutation_id, str) or not mutation_id:
        _raise_corruption(
            ledger_path,
            "missing_mutation_id",
            "record lacks an immutable mutation ID",
            expected_sequence - 1,
            line_number,
            expected_sequence,
            "non-empty string",
            repr(mutation_id),
        )
    if record.get("event_kind") != "research_mutation_evaluation":
        _raise_corruption(
            ledger_path,
            "event_kind_mismatch",
            "record is not a research mutation evaluation",
            expected_sequence - 1,
            line_number,
            expected_sequence,
            "research_mutation_evaluation",
            str(record.get("event_kind")),
        )
    observed_at_utc = record.get("observed_at_utc")
    try:
        if not isinstance(observed_at_utc, str):
            raise TypeError("timestamp is not a string")
        _validate_utc_timestamp(observed_at_utc)
    except (TypeError, ValueError) as error:
        _raise_corruption(
            ledger_path,
            "invalid_observed_timestamp",
            f"record timestamp is invalid: error={error}",
            expected_sequence - 1,
            line_number,
            expected_sequence,
            "UTC ISO-8601 timestamp",
            repr(observed_at_utc),
        )
    for field_name in (
        "code_hash",
        "data_hash",
        "baseline_artifact_hash",
        "candidate_artifact_hash",
    ):
        if not _is_sha256(record.get(field_name)):
            _raise_corruption(
                ledger_path,
                "invalid_content_hash",
                f"record content hash is invalid: field={field_name}",
                expected_sequence - 1,
                line_number,
                expected_sequence,
                "lowercase SHA-256",
                repr(record.get(field_name)),
            )
    baseline = record.get("baseline_fitness")
    candidate = record.get("candidate_fitness")
    try:
        if not isinstance(baseline, (int, float)) or isinstance(baseline, bool):
            raise TypeError("baseline fitness is not numeric")
        if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
            raise TypeError("candidate fitness is not numeric")
        recomputed = evaluate_mutation_fitness(float(baseline), float(candidate))
    except (TypeError, ValueError) as error:
        _raise_corruption(
            ledger_path,
            "invalid_fitness_evidence",
            f"record fitness evidence is invalid: error={error}",
            expected_sequence - 1,
            line_number,
            expected_sequence,
            "finite fitness values within [0, 1]",
            f"baseline={baseline!r}, candidate={candidate!r}",
        )
    for field_name in (
        "decision",
        "rollback_required",
        "fitness_delta",
        "reason_codes",
    ):
        if record.get(field_name) != recomputed[field_name]:
            _raise_corruption(
                ledger_path,
                "mutation_decision_mismatch",
                f"record decision does not match measured fitness: field={field_name}",
                expected_sequence - 1,
                line_number,
                expected_sequence,
                repr(recomputed[field_name]),
                repr(record.get(field_name)),
            )
    expected_rollback_evidence: dict[str, JsonValue] = {
        "required": recomputed["rollback_required"],
        "target_artifact_hash": (
            str(record["baseline_artifact_hash"])
            if recomputed["rollback_required"]
            else None
        ),
        "candidate_evidence_preserved": True,
        "history_rewrite_permitted": False,
    }
    if record.get("rollback_evidence") != expected_rollback_evidence:
        _raise_corruption(
            ledger_path,
            "rollback_evidence_mismatch",
            "record rollback evidence does not match the measured decision",
            expected_sequence - 1,
            line_number,
            expected_sequence,
            repr(expected_rollback_evidence),
            repr(record.get("rollback_evidence")),
        )
    required_guards: dict[str, JsonValue] = {
        "research_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "operator_gate_required": True,
        "history_rewrite_permitted": False,
    }
    for field_name, expected_value in required_guards.items():
        if record.get(field_name) != expected_value:
            _raise_corruption(
                ledger_path,
                "research_boundary_violation",
                f"record weakens the research-only boundary: field={field_name}",
                expected_sequence - 1,
                line_number,
                expected_sequence,
                repr(expected_value),
                repr(record.get(field_name)),
            )


def _verify_anchor(
    ledger_path: Path,
    records: list[dict[str, JsonValue]],
) -> None:
    anchor_path = epistemic_mutation_ledger_anchor_path(ledger_path)
    if not records and not anchor_path.exists():
        return
    if not anchor_path.exists():
        _raise_corruption(
            ledger_path,
            "head_anchor_missing",
            "ledger history exists without its pinned head anchor",
            len(records),
            None,
            None,
            str(anchor_path),
            "missing",
        )
    try:
        decoded = json.loads(
            anchor_path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as error:
        _raise_corruption(
            ledger_path,
            "head_anchor_unreadable",
            f"ledger head anchor is unreadable: error={error}",
            len(records),
            None,
            None,
            "valid content-addressed anchor",
            str(anchor_path),
        )
    if not isinstance(decoded, dict):
        _raise_corruption(
            ledger_path,
            "head_anchor_non_object",
            "ledger head anchor is not a JSON object",
            len(records),
            None,
            None,
            "JSON object",
            type(decoded).__name__,
        )
    anchor = cast(dict[str, JsonValue], decoded)
    observed_anchor_hash = anchor.get("anchor_hash")
    anchor_body = {key: value for key, value in anchor.items() if key != "anchor_hash"}
    expected_anchor_hash = _canonical_hash(anchor_body)
    if observed_anchor_hash != expected_anchor_hash:
        _raise_corruption(
            ledger_path,
            "head_anchor_hash_mismatch",
            "ledger head anchor content hash does not verify",
            len(records),
            None,
            None,
            expected_anchor_hash,
            str(observed_anchor_hash),
        )
    expected_head = str(records[-1]["entry_hash"]) if records else GENESIS_HASH
    expected_anchor_fields: dict[str, JsonValue] = {
        "ledger_version": EPISTEMIC_MUTATION_LEDGER_VERSION,
        "ledger_file": ledger_path.name,
        "record_count": len(records),
        "head_hash": expected_head,
    }
    for field_name, expected_value in expected_anchor_fields.items():
        if anchor.get(field_name) != expected_value:
            _raise_corruption(
                ledger_path,
                "head_anchor_state_mismatch",
                "ledger head anchor does not match the append-only history",
                len(records),
                None,
                None,
                f"{field_name}={expected_value!r}",
                f"{field_name}={anchor.get(field_name)!r}",
            )


def _verify_records(
    ledger_path: Path,
) -> tuple[dict[str, JsonValue], ...]:
    records = _load_records(ledger_path)
    previous_hash = GENESIS_HASH
    seen_mutation_ids: set[str] = set()
    for expected_sequence, record in enumerate(records, start=1):
        observed_sequence = record.get("sequence")
        if (
            not isinstance(observed_sequence, int)
            or isinstance(observed_sequence, bool)
            or observed_sequence != expected_sequence
        ):
            _raise_corruption(
                ledger_path,
                "sequence_mismatch",
                "ledger sequence is not contiguous",
                expected_sequence - 1,
                expected_sequence,
                expected_sequence,
                str(expected_sequence),
                str(record.get("sequence")),
            )
        if record.get("previous_hash") != previous_hash:
            _raise_corruption(
                ledger_path,
                "previous_hash_mismatch",
                "ledger hash chain is broken",
                expected_sequence - 1,
                expected_sequence,
                expected_sequence,
                previous_hash,
                str(record.get("previous_hash")),
            )
        observed_entry_hash = record.get("entry_hash")
        body = {key: value for key, value in record.items() if key != "entry_hash"}
        expected_entry_hash = _canonical_hash(body)
        if observed_entry_hash != expected_entry_hash:
            _raise_corruption(
                ledger_path,
                "entry_hash_mismatch",
                "ledger entry content hash does not verify",
                expected_sequence - 1,
                expected_sequence,
                expected_sequence,
                expected_entry_hash,
                str(observed_entry_hash),
            )
        _verify_record_semantics(ledger_path, record, expected_sequence)
        mutation_id = cast(str, record["mutation_id"])
        if mutation_id in seen_mutation_ids:
            _raise_corruption(
                ledger_path,
                "duplicate_mutation_id",
                "immutable mutation ID appears more than once",
                expected_sequence - 1,
                expected_sequence,
                expected_sequence,
                "unique mutation ID",
                mutation_id,
            )
        seen_mutation_ids.add(mutation_id)
        previous_hash = expected_entry_hash
    _verify_anchor(ledger_path, records)
    return tuple(records)


def audit_epistemic_mutation_ledger(
    repository_root: Path,
    ledger_path: Path,
) -> LedgerAuditEvidence:
    resolved = resolve_epistemic_mutation_ledger_path(repository_root, ledger_path)
    try:
        records = _verify_records(resolved)
    except EpistemicMutationLedgerCorruptionError as error:
        return {
            "ledger_version": EPISTEMIC_MUTATION_LEDGER_VERSION,
            "ledger_path": str(resolved),
            "integrity_status": "corrupt_fail_closed",
            "decision": "rollback_required",
            "rollback_required": True,
            "record_count": error.evidence["verified_record_count"],
            "head_hash": GENESIS_HASH,
            "corruption": error.evidence,
        }
    head_hash = str(records[-1]["entry_hash"]) if records else GENESIS_HASH
    return {
        "ledger_version": EPISTEMIC_MUTATION_LEDGER_VERSION,
        "ledger_path": str(resolved),
        "integrity_status": "verified",
        "decision": "continue_research_only",
        "rollback_required": False,
        "record_count": len(records),
        "head_hash": head_hash,
        "corruption": None,
    }


def verify_epistemic_mutation_ledger(
    repository_root: Path,
    ledger_path: Path,
) -> tuple[dict[str, JsonValue], ...]:
    resolved = resolve_epistemic_mutation_ledger_path(repository_root, ledger_path)
    return _verify_records(resolved)


def _write_anchor(
    ledger_path: Path,
    record_count: int,
    head_hash: str,
) -> None:
    body: dict[str, JsonValue] = {
        "ledger_version": EPISTEMIC_MUTATION_LEDGER_VERSION,
        "ledger_file": ledger_path.name,
        "record_count": record_count,
        "head_hash": head_hash,
    }
    anchor: dict[str, JsonValue] = {
        **body,
        "anchor_hash": _canonical_hash(body),
    }
    anchor_path = epistemic_mutation_ledger_anchor_path(ledger_path)
    temporary_path = anchor_path.with_suffix(f"{anchor_path.suffix}.{os.getpid()}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical_json(anchor).decode("ascii"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _replace_file(temporary_path, anchor_path)
    except OSError as error:
        raise EpistemicMutationLedgerWriteError(
            "could not persist epistemic mutation ledger head anchor: "
            f"anchor_path={anchor_path}, error={error}"
        ) from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _mutation_payload(
    mutation_id: str,
    observed_at_utc: str,
    code_hash: str,
    data_hash: str,
    baseline_artifact_hash: str,
    candidate_artifact_hash: str,
    baseline_fitness: float,
    candidate_fitness: float,
    evidence: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    if not mutation_id:
        raise ValueError("mutation ID cannot be empty")
    _validate_utc_timestamp(observed_at_utc)
    supplied_hashes = {
        "code_hash": code_hash,
        "data_hash": data_hash,
        "baseline_artifact_hash": baseline_artifact_hash,
        "candidate_artifact_hash": candidate_artifact_hash,
    }
    invalid_hashes = [
        field_name
        for field_name, value in supplied_hashes.items()
        if not _is_sha256(value)
    ]
    if invalid_hashes:
        raise ValueError(
            "mutation content hashes must be lowercase SHA-256 values: "
            f"invalid_fields={invalid_hashes}"
        )
    decision = evaluate_mutation_fitness(baseline_fitness, candidate_fitness)
    evidence_body = dict(evidence)
    _canonical_json(evidence_body)
    rollback_evidence: dict[str, JsonValue] = {
        "required": decision["rollback_required"],
        "target_artifact_hash": (
            baseline_artifact_hash if decision["rollback_required"] else None
        ),
        "candidate_evidence_preserved": True,
        "history_rewrite_permitted": False,
    }
    return {
        "ledger_version": EPISTEMIC_MUTATION_LEDGER_VERSION,
        "event_kind": "research_mutation_evaluation",
        "mutation_id": mutation_id,
        "observed_at_utc": observed_at_utc,
        **supplied_hashes,
        "baseline_fitness": float(baseline_fitness),
        "candidate_fitness": float(candidate_fitness),
        **decision,
        "rollback_evidence": rollback_evidence,
        "evidence": evidence_body,
        "research_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "operator_gate_required": True,
        "history_rewrite_permitted": False,
    }


def append_epistemic_mutation_evaluation(
    repository_root: Path,
    ledger_path: Path,
    mutation_id: str,
    observed_at_utc: str,
    code_hash: str,
    data_hash: str,
    baseline_artifact_hash: str,
    candidate_artifact_hash: str,
    baseline_fitness: float,
    candidate_fitness: float,
    evidence: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    """Durably append one measured mutation or return its exact idempotent retry."""
    resolved = resolve_epistemic_mutation_ledger_path(repository_root, ledger_path)
    payload = _mutation_payload(
        mutation_id,
        observed_at_utc,
        code_hash,
        data_hash,
        baseline_artifact_hash,
        candidate_artifact_hash,
        baseline_fitness,
        candidate_fitness,
        evidence,
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    lock_path = resolved.with_suffix(f"{resolved.suffix}.lock")
    lock_descriptor: int | None = None
    lock_acquired = False
    try:
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as error:
            lock_owner = lock_path.read_text(encoding="ascii", errors="replace").strip()
            raise EpistemicMutationLedgerLockError(
                "epistemic mutation ledger append is already locked; "
                f"lock_path={lock_path}, lock_owner={lock_owner!r}"
            ) from error
        lock_acquired = True
        os.write(lock_descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(lock_descriptor)
        os.close(lock_descriptor)
        lock_descriptor = None

        records = _verify_records(resolved)
        matching_records = [
            record for record in records if record.get("mutation_id") == mutation_id
        ]
        if matching_records:
            existing = matching_records[0]
            existing_payload = {
                key: value for key, value in existing.items() if key not in CHAIN_FIELDS
            }
            if existing_payload == payload:
                return existing
            raise EpistemicMutationConflictError(
                "immutable mutation ID already exists with different evidence: "
                f"ledger_path={resolved}, mutation_id={mutation_id}"
            )
        previous_hash = str(records[-1]["entry_hash"]) if records else GENESIS_HASH
        body: dict[str, JsonValue] = {
            **payload,
            "sequence": len(records) + 1,
            "previous_hash": previous_hash,
        }
        record: dict[str, JsonValue] = {
            **body,
            "entry_hash": _canonical_hash(body),
        }
        try:
            with resolved.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(_canonical_json(record).decode("ascii"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise EpistemicMutationLedgerWriteError(
                "could not durably append epistemic mutation evidence: "
                f"ledger_path={resolved}, mutation_id={mutation_id}, error={error}"
            ) from error
        _write_anchor(resolved, len(records) + 1, str(record["entry_hash"]))
        _verify_records(resolved)
        return record
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if lock_acquired and lock_path.exists():
            lock_path.unlink()
