"""Exact, non-destructive recovery for the July 2026 trade-ledger incident."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Final, Iterator, NotRequired, Protocol, TypedDict, cast

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .backtest_models import stable_backtest_hash


RECOVERY_POLICY_VERSION: Final[str] = "dopey-backtest-ledger-exact-recovery-v1"
RECOVERY_STATUS: Final[str] = "recovered_mirror_verified"
LEDGER_INTEGRITY_POLICY_VERSION: Final[str] = (
    "dopey-backtest-ledger-integrity-resolver-v1"
)
SOURCE_LEDGER_STATUS: Final[str] = "source_ledger_verified_current"
COPY_CHUNK_BYTES: Final[int] = 1024 * 1024


class BacktestLedgerRecoveryError(RuntimeError):
    """Raised when the source or recovered mirror cannot be proven exact."""


class RecoverySpecification(TypedDict):
    incident_id: str
    source_size_bytes: int
    source_sha256: str
    patch_offset: int
    source_bytes_hex: str
    replacement_bytes_hex: str
    affected_record_symbol: str
    affected_record_hash: str


class LedgerFileEvidence(TypedDict):
    path: str
    size_bytes: int
    sha256: str


class PatchRecordEvidence(TypedDict):
    line_number: int
    byte_start: int
    byte_end_exclusive: int
    symbol: str
    stored_record_hash: str
    computed_record_hash: str
    record_hash_verified: bool


class PatchEvidence(TypedDict):
    absolute_offset: int
    byte_count: int
    expected_source_bytes_hex: str
    observed_source_bytes_hex: str
    replacement_bytes_hex: str
    observed_replacement_bytes_hex: str
    replacement_ascii: str
    exact_single_patch_verified: bool
    affected_record: PatchRecordEvidence


class RecordVerificationEvidence(TypedDict):
    encoding: str
    utf8_valid: bool
    jsonl_valid: bool
    record_count: int
    stored_record_hash_count: int
    verified_record_hash_count: int
    record_hash_failure_count: int
    hash_function: str


class RecoveryManifest(TypedDict):
    artifact_type: str
    recovery_policy_version: str
    incident_id: str
    recovery_status: str
    generated_at: str
    source: LedgerFileEvidence
    recovered: LedgerFileEvidence
    patch: PatchEvidence
    verification: RecordVerificationEvidence
    source_preserved: bool
    records_deleted: int
    records_reordered: bool
    paper_only: bool
    live_blocked: bool


class RecoveryResolution(TypedDict):
    status: str
    source_path: str
    resolved_path: str
    manifest_path: str
    source_size_bytes: int
    source_sha256: str
    recovered_size_bytes: int
    recovered_sha256: str
    manifest_sha256: str
    patch_offset: int
    patch_byte_count: int
    record_count: int
    verified_record_hash_count: int
    affected_record_symbol: str
    affected_record_hash: str
    exact_single_patch_verified: bool
    source_preserved: bool


class AuthoritativeLedgerEvidence(TypedDict):
    path: str
    artifact_type: str
    declared_record_count: int | None
    declared_ledger_sha256: str | None
    source_path_binding_verified: bool
    self_hash_verified: bool


class VerifiedLedgerResolution(TypedDict):
    status: str
    integrity_policy_version: str
    source_path: str
    resolved_path: str
    source_size_bytes: int
    source_sha256: str
    resolved_size_bytes: int
    resolved_sha256: str
    record_count: int
    verified_record_hash_count: int
    authoritative_evidence: list[AuthoritativeLedgerEvidence]
    incident_recovery_used: bool
    paper_only: bool
    live_blocked: bool
    recovery_manifest_path: NotRequired[str]
    recovery_manifest_sha256: NotRequired[str]
    incident_id: NotRequired[str]


class _LedgerScan(TypedDict):
    source_size_bytes: int
    source_sha256: str
    record_count: int
    verified_record_hash_count: int
    verification_error: str | None


BACKTEST_TRADE_RECORDS_INCIDENT: Final[RecoverySpecification] = {
    "incident_id": "backtest-trade-records-invalid-utf8-offset-234397696",
    "source_size_bytes": 543_141_252,
    "source_sha256": "a08df4681e739ca9463e90b8c913950bcd151d87b7142f983235b0eeb10a2831",
    "patch_offset": 234_397_696,
    "source_bytes_hex": "d270c5f78cbcf0bb16d0d49720826800",
    "replacement_bytes_hex": "7465223a2022323032312d31322d3136",
    "affected_record_symbol": "EQIX",
    "affected_record_hash": "9a2fc6ffb19b4ebd0f3bd253bea899faa9b794edf3177f47da250ccf3b87c24a",
}

_REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_DEFAULT_BACKTEST_ARTIFACT_DIR: Final[Path] = (
    _REPOSITORY_ROOT / "artifacts" / "dopey" / "backtest"
)
DEFAULT_BACKTEST_TRADE_RECORDS_PATH: Final[Path] = (
    _DEFAULT_BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
)
DEFAULT_BACKTEST_TRADE_RECORDS_RECOVERED_PATH: Final[Path] = (
    _DEFAULT_BACKTEST_ARTIFACT_DIR / "backtest_trade_records.recovered.jsonl"
)
DEFAULT_BACKTEST_TRADE_RECORDS_RECOVERY_MANIFEST_PATH: Final[Path] = (
    _DEFAULT_BACKTEST_ARTIFACT_DIR
    / "backtest_trade_records.recovery_manifest.json"
)
DEFAULT_BACKTEST_RUN_SUMMARY_PATH: Final[Path] = (
    _DEFAULT_BACKTEST_ARTIFACT_DIR / "backtest_run_summary.json"
)
DEFAULT_BACKTEST_PROOF_PATH: Final[Path] = (
    _DEFAULT_BACKTEST_ARTIFACT_DIR / "backtest_proof.jsonl"
)


def resolve_default_backtest_trade_ledger() -> VerifiedLedgerResolution:
    """Resolve the repository ledger only after full integrity reconciliation."""

    return resolve_verified_trade_ledger(
        DEFAULT_BACKTEST_TRADE_RECORDS_PATH,
        DEFAULT_BACKTEST_TRADE_RECORDS_RECOVERED_PATH,
        DEFAULT_BACKTEST_TRADE_RECORDS_RECOVERY_MANIFEST_PATH,
        (DEFAULT_BACKTEST_RUN_SUMMARY_PATH, DEFAULT_BACKTEST_PROOF_PATH),
        BACKTEST_TRADE_RECORDS_INCIDENT,
    )


def resolve_verified_trade_ledger(
    source_path: Path,
    recovered_path: Path,
    recovery_manifest_path: Path,
    authoritative_evidence_paths: tuple[Path, ...],
    specification: RecoverySpecification,
) -> VerifiedLedgerResolution:
    """Resolve a current valid ledger or the one exact declared incident mirror."""

    _validate_distinct_paths(source_path, recovered_path, recovery_manifest_path)
    _validate_specification(specification)
    if not source_path.is_file():
        raise FileNotFoundError(
            f"backtest trade-record source is missing: {source_path}"
        )
    scan = _scan_ledger(source_path)
    incident_matches = (
        scan["source_size_bytes"] == specification["source_size_bytes"]
        and hmac.compare_digest(
            scan["source_sha256"], specification["source_sha256"]
        )
    )
    if incident_matches:
        recovery = resolve_exact_recovered_ledger(
            source_path,
            recovered_path,
            recovery_manifest_path,
            specification,
        )
        resolved_path = Path(recovery["resolved_path"])
        resolved_size_bytes = recovery["recovered_size_bytes"]
        resolved_sha256 = recovery["recovered_sha256"]
        record_count = recovery["record_count"]
        verified_record_hash_count = recovery["verified_record_hash_count"]
        authoritative = _verify_authoritative_evidence(
            authoritative_evidence_paths,
            source_path,
            resolved_sha256,
            record_count,
        )
        return {
            "status": RECOVERY_STATUS,
            "integrity_policy_version": LEDGER_INTEGRITY_POLICY_VERSION,
            "source_path": str(source_path.resolve()),
            "resolved_path": str(resolved_path.resolve()),
            "source_size_bytes": scan["source_size_bytes"],
            "source_sha256": scan["source_sha256"],
            "resolved_size_bytes": resolved_size_bytes,
            "resolved_sha256": resolved_sha256,
            "record_count": record_count,
            "verified_record_hash_count": verified_record_hash_count,
            "authoritative_evidence": authoritative,
            "incident_recovery_used": True,
            "recovery_manifest_path": recovery["manifest_path"],
            "recovery_manifest_sha256": recovery["manifest_sha256"],
            "incident_id": specification["incident_id"],
            "paper_only": True,
            "live_blocked": True,
        }
    if scan["verification_error"] is not None:
        raise BacktestLedgerRecoveryError(
            "source ledger is neither fully valid nor the exact declared incident: "
            f"path={source_path}, size_bytes={scan['source_size_bytes']}, "
            f"sha256={scan['source_sha256']}, "
            f"verification_error={scan['verification_error']}"
        )
    if scan["record_count"] == 0:
        raise BacktestLedgerRecoveryError(
            f"source ledger is empty; refusing current-ledger resolution: {source_path}"
        )
    authoritative = _verify_authoritative_evidence(
        authoritative_evidence_paths,
        source_path,
        scan["source_sha256"],
        scan["record_count"],
    )
    return {
        "status": SOURCE_LEDGER_STATUS,
        "integrity_policy_version": LEDGER_INTEGRITY_POLICY_VERSION,
        "source_path": str(source_path.resolve()),
        "resolved_path": str(source_path.resolve()),
        "source_size_bytes": scan["source_size_bytes"],
        "source_sha256": scan["source_sha256"],
        "resolved_size_bytes": scan["source_size_bytes"],
        "resolved_sha256": scan["source_sha256"],
        "record_count": scan["record_count"],
        "verified_record_hash_count": scan["verified_record_hash_count"],
        "authoritative_evidence": authoritative,
        "incident_recovery_used": False,
        "paper_only": True,
        "live_blocked": True,
    }


def iter_verified_trade_records(
    resolution: VerifiedLedgerResolution,
) -> Iterator[dict[str, object]]:
    """Yield a resolved ledger while rechecking its pinned bytes and records."""

    resolved_path = Path(resolution["resolved_path"])
    if not resolved_path.is_file():
        raise BacktestLedgerRecoveryError(
            f"resolved ledger disappeared before consumption: path={resolved_path}"
        )
    initial_stat = resolved_path.stat()
    digest = hashlib.sha256()
    observed_size_bytes = 0
    observed_record_count = 0
    with resolved_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            digest.update(raw_line)
            observed_size_bytes += len(raw_line)
            record, verification_error = _parse_verified_record_line(
                resolved_path,
                line_number,
                raw_line,
            )
            if verification_error is not None or record is None:
                raise BacktestLedgerRecoveryError(
                    "resolved ledger failed verification during consumption: "
                    f"path={resolved_path}, error={verification_error}"
                )
            observed_record_count += 1
            yield record
    final_stat = resolved_path.stat()
    observed_sha256 = digest.hexdigest()
    mismatch_fields: list[str] = []
    if initial_stat.st_size != final_stat.st_size:
        mismatch_fields.append("file_size_changed")
    if initial_stat.st_mtime_ns != final_stat.st_mtime_ns:
        mismatch_fields.append("file_mtime_changed")
    if observed_size_bytes != resolution["resolved_size_bytes"]:
        mismatch_fields.append("resolved_size_bytes")
    if observed_record_count != resolution["record_count"]:
        mismatch_fields.append("record_count")
    if not hmac.compare_digest(observed_sha256, resolution["resolved_sha256"]):
        mismatch_fields.append("resolved_sha256")
    if mismatch_fields:
        raise BacktestLedgerRecoveryError(
            "resolved ledger changed or disagreed during consumption: "
            f"path={resolved_path}, mismatches={mismatch_fields}, "
            f"expected_size={resolution['resolved_size_bytes']}, "
            f"observed_size={observed_size_bytes}, "
            f"expected_count={resolution['record_count']}, "
            f"observed_count={observed_record_count}, "
            f"expected_sha256={resolution['resolved_sha256']}, "
            f"observed_sha256={observed_sha256}"
        )


def _scan_ledger(source_path: Path) -> _LedgerScan:
    initial_stat = source_path.stat()
    digest = hashlib.sha256()
    source_size_bytes = 0
    record_count = 0
    verification_error: str | None = None
    with source_path.open("rb") as source:
        for line_number, raw_line in enumerate(source, start=1):
            digest.update(raw_line)
            source_size_bytes += len(raw_line)
            if verification_error is not None:
                continue
            verification_error = _verify_current_record_line(
                source_path,
                line_number,
                raw_line,
            )
            if verification_error is None:
                record_count += 1
    final_stat = source_path.stat()
    if (
        initial_stat.st_size != final_stat.st_size
        or initial_stat.st_mtime_ns != final_stat.st_mtime_ns
        or source_size_bytes != final_stat.st_size
    ):
        raise BacktestLedgerRecoveryError(
            "source ledger changed during integrity verification: "
            f"path={source_path}, initial_size={initial_stat.st_size}, "
            f"final_size={final_stat.st_size}, bytes_read={source_size_bytes}, "
            f"initial_mtime_ns={initial_stat.st_mtime_ns}, "
            f"final_mtime_ns={final_stat.st_mtime_ns}"
        )
    return {
        "source_size_bytes": source_size_bytes,
        "source_sha256": digest.hexdigest(),
        "record_count": record_count,
        "verified_record_hash_count": record_count,
        "verification_error": verification_error,
    }


def _verify_current_record_line(
    source_path: Path,
    line_number: int,
    raw_line: bytes,
) -> str | None:
    _, verification_error = _parse_verified_record_line(
        source_path,
        line_number,
        raw_line,
    )
    return verification_error


def _parse_verified_record_line(
    source_path: Path,
    line_number: int,
    raw_line: bytes,
) -> tuple[dict[str, object] | None, str | None]:
    if not raw_line.strip():
        return None, f"blank JSONL line at line={line_number}"
    try:
        decoded = raw_line.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, (
            "invalid UTF-8 at "
            f"line={line_number}, byte_offset_within_line={error.start}"
        )
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as error:
        return None, (
            f"invalid JSON at line={line_number}, column={error.colno}"
        )
    if not isinstance(parsed, dict):
        return None, f"JSONL record is not an object at line={line_number}"
    record = cast(dict[str, object], parsed)
    stored_hash = record.get("record_hash")
    if not isinstance(stored_hash, str) or len(stored_hash) != 64:
        return None, (
            "record_hash is missing or malformed at "
            f"line={line_number}, path={source_path}"
        )
    try:
        bytes.fromhex(stored_hash)
    except ValueError:
        return None, f"record_hash is not hexadecimal at line={line_number}"
    computed_hash = stable_backtest_hash(record)
    if not hmac.compare_digest(stored_hash, computed_hash):
        return None, (
            "record_hash verification failed at "
            f"line={line_number}, stored={stored_hash}, computed={computed_hash}"
        )
    return record, None


def _verify_authoritative_evidence(
    evidence_paths: tuple[Path, ...],
    source_path: Path,
    resolved_sha256: str,
    record_count: int,
) -> list[AuthoritativeLedgerEvidence]:
    if not evidence_paths:
        raise BacktestLedgerRecoveryError(
            "at least one authoritative run summary, proof, or manifest is required"
        )
    resolved_paths = [path.resolve() for path in evidence_paths]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise BacktestLedgerRecoveryError(
            "authoritative evidence paths must be unique: "
            f"paths={[str(path) for path in evidence_paths]}"
        )
    evidence: list[AuthoritativeLedgerEvidence] = []
    for evidence_path in evidence_paths:
        record = _load_authoritative_record(evidence_path)
        artifact_type = str(record.get("artifact_type", ""))
        if not artifact_type:
            raise BacktestLedgerRecoveryError(
                "authoritative ledger evidence has no artifact_type: "
                f"path={evidence_path}"
            )
        self_hash_verified = _verify_authoritative_self_hash(
            evidence_path,
            artifact_type,
            record,
        )
        declared_count = _declared_record_count(evidence_path, record)
        declared_sha256 = _declared_ledger_sha256(evidence_path, record)
        if declared_count is None and declared_sha256 is None:
            raise BacktestLedgerRecoveryError(
                "authoritative ledger evidence declares neither record count nor hash: "
                f"path={evidence_path}, artifact_type={artifact_type}"
            )
        if declared_count is not None and declared_count != record_count:
            raise BacktestLedgerRecoveryError(
                "authoritative ledger record count disagrees with verified records: "
                f"path={evidence_path}, declared={declared_count}, "
                f"verified={record_count}"
            )
        if declared_sha256 is not None and not hmac.compare_digest(
            declared_sha256, resolved_sha256
        ):
            raise BacktestLedgerRecoveryError(
                "authoritative ledger hash disagrees with verified ledger: "
                f"path={evidence_path}, declared={declared_sha256}, "
                f"verified={resolved_sha256}"
            )
        source_path_binding_verified = _verify_source_path_binding(
            evidence_path,
            record,
            source_path,
        )
        evidence.append(
            {
                "path": str(evidence_path.resolve()),
                "artifact_type": artifact_type,
                "declared_record_count": declared_count,
                "declared_ledger_sha256": declared_sha256,
                "source_path_binding_verified": source_path_binding_verified,
                "self_hash_verified": self_hash_verified,
            }
        )
    return evidence


def _verify_authoritative_self_hash(
    evidence_path: Path,
    artifact_type: str,
    record: dict[str, object],
) -> bool:
    if artifact_type == "backtest_run_summary":
        field = "run_hash"
        expected = stable_backtest_hash(record)
    elif artifact_type == "backtest_proof":
        field = "proof_hash"
        proof_id = str(record.get("proof_id", ""))
        if proof_id == "dopey-honest-backtester-v1-proof":
            expected = stable_backtest_hash(record)
        elif proof_id == "dopey-real-history-honest-backtester-v1-proof":
            unhashed = {key: value for key, value in record.items() if key != field}
            expected = reproducibility_hash(unhashed)
        else:
            raise BacktestLedgerRecoveryError(
                "authoritative backtest proof has an unsupported proof_id: "
                f"path={evidence_path}, proof_id={proof_id!r}"
            )
    else:
        return False
    observed = record.get(field)
    if not isinstance(observed, str) or len(observed) != 64:
        raise BacktestLedgerRecoveryError(
            "authoritative evidence self-hash is missing or malformed: "
            f"path={evidence_path}, field={field}, observed={observed!r}"
        )
    if not hmac.compare_digest(observed, expected):
        raise BacktestLedgerRecoveryError(
            "authoritative evidence self-hash verification failed: "
            f"path={evidence_path}, field={field}, "
            f"observed={observed}, expected={expected}"
        )
    return True


def _load_authoritative_record(evidence_path: Path) -> dict[str, object]:
    if not evidence_path.is_file():
        raise BacktestLedgerRecoveryError(
            f"authoritative ledger evidence is missing: path={evidence_path}"
        )
    try:
        text = evidence_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BacktestLedgerRecoveryError(
            f"authoritative ledger evidence is unreadable: path={evidence_path}"
        ) from error
    if not text.strip():
        raise BacktestLedgerRecoveryError(
            f"authoritative ledger evidence is empty: path={evidence_path}"
        )
    if evidence_path.suffix.lower() == ".jsonl":
        lines = text.splitlines()
        if any(not line.strip() for line in lines) or len(lines) != 1:
            raise BacktestLedgerRecoveryError(
                "authoritative JSONL evidence must contain exactly one nonblank record: "
                f"path={evidence_path}, line_count={len(lines)}"
            )
        payload = lines[0]
    else:
        payload = text
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise BacktestLedgerRecoveryError(
            "authoritative ledger evidence is invalid JSON: "
            f"path={evidence_path}, line={error.lineno}, column={error.colno}"
        ) from error
    if not isinstance(parsed, dict):
        raise BacktestLedgerRecoveryError(
            f"authoritative ledger evidence is not an object: path={evidence_path}"
        )
    return cast(dict[str, object], parsed)


def _declared_record_count(
    evidence_path: Path,
    record: dict[str, object],
) -> int | None:
    candidate: object | None = record.get("trade_record_count")
    if candidate is None:
        candidate = record.get("record_count")
    if candidate is None and isinstance(record.get("verification"), dict):
        verification = cast(dict[str, object], record["verification"])
        candidate = verification.get("record_count")
    if candidate is None:
        return None
    if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate < 0:
        raise BacktestLedgerRecoveryError(
            "authoritative ledger record count is not a nonnegative integer: "
            f"path={evidence_path}, observed={candidate!r}"
        )
    return candidate


def _declared_ledger_sha256(
    evidence_path: Path,
    record: dict[str, object],
) -> str | None:
    candidate: object | None = None
    for field in (
        "backtest_trade_records_sha256",
        "trade_records_sha256",
        "ledger_sha256",
    ):
        if record.get(field) is not None:
            candidate = record[field]
            break
    if candidate is None and isinstance(record.get("artifact_hashes"), dict):
        artifact_hashes = cast(dict[str, object], record["artifact_hashes"])
        candidate = artifact_hashes.get("backtest_trade_records")
    if candidate is None:
        return None
    if not isinstance(candidate, str) or len(candidate) != 64:
        raise BacktestLedgerRecoveryError(
            "authoritative ledger hash is malformed: "
            f"path={evidence_path}, observed={candidate!r}"
        )
    try:
        bytes.fromhex(candidate)
    except ValueError as error:
        raise BacktestLedgerRecoveryError(
            "authoritative ledger hash is not hexadecimal: "
            f"path={evidence_path}, observed={candidate!r}"
        ) from error
    return candidate.lower()


def _verify_source_path_binding(
    evidence_path: Path,
    record: dict[str, object],
    source_path: Path,
) -> bool:
    artifact_paths = record.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        return False
    declared = cast(dict[str, object], artifact_paths).get(
        "backtest_trade_records"
    )
    if declared is None:
        return False
    if not isinstance(declared, str) or not declared.strip():
        raise BacktestLedgerRecoveryError(
            "authoritative backtest_trade_records path binding is malformed: "
            f"path={evidence_path}, observed={declared!r}"
        )
    declared_path = Path(declared)
    if not declared_path.is_absolute():
        declared_path = Path.cwd() / declared_path
    if declared_path.resolve() != source_path.resolve():
        raise BacktestLedgerRecoveryError(
            "authoritative evidence is bound to a different source ledger: "
            f"path={evidence_path}, declared_source={declared_path.resolve()}, "
            f"expected_source={source_path.resolve()}"
        )
    return True


def recover_exact_byte_incident(
    source_path: Path,
    recovered_path: Path,
    manifest_path: Path,
    specification: RecoverySpecification,
) -> RecoveryManifest:
    """Create a verified mirror while preserving the source byte-for-byte."""

    _validate_distinct_paths(source_path, recovered_path, manifest_path)
    _validate_specification(specification)
    if recovered_path.exists() or manifest_path.exists():
        if recovered_path.exists() and manifest_path.exists():
            resolve_exact_recovered_ledger(
                source_path,
                recovered_path,
                manifest_path,
                specification,
            )
            return _load_manifest(manifest_path)
        raise BacktestLedgerRecoveryError(
            "recovery output is incomplete; refusing to overwrite evidence: "
            f"recovered_exists={recovered_path.exists()}, "
            f"manifest_exists={manifest_path.exists()}"
        )
    if not source_path.is_file():
        raise FileNotFoundError(
            f"backtest trade-record source is missing: {source_path}"
        )
    observed_size = source_path.stat().st_size
    if observed_size != specification["source_size_bytes"]:
        raise BacktestLedgerRecoveryError(
            "source size does not match the incident specification: "
            f"path={source_path}, expected={specification['source_size_bytes']}, "
            f"observed={observed_size}"
        )
    observed_patch = _read_exact_patch(source_path, specification)

    recovered_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    recovered_temp = _temporary_path(recovered_path)
    manifest_temp: Path | None = None
    try:
        source_sha256, recovered_sha256 = _write_recovered_temp(
            source_path,
            recovered_temp,
            specification,
        )
        if source_sha256 != specification["source_sha256"]:
            raise BacktestLedgerRecoveryError(
                "source hash does not match the incident specification: "
                f"path={source_path}, expected={specification['source_sha256']}, "
                f"observed={source_sha256}"
            )
        verification, affected_record = _verify_jsonl_records(
            recovered_temp,
            specification,
        )
        manifest = _build_manifest(
            source_path,
            recovered_path,
            observed_size,
            source_sha256,
            recovered_sha256,
            observed_patch,
            verification,
            affected_record,
            specification,
        )
        manifest_temp = _temporary_path(manifest_path)
        _write_json_temp(manifest_temp, manifest)
        os.replace(recovered_temp, recovered_path)
        os.replace(manifest_temp, manifest_path)
        resolve_exact_recovered_ledger(
            source_path,
            recovered_path,
            manifest_path,
            specification,
        )
        return manifest
    except Exception:
        _unlink_if_present(recovered_temp)
        if manifest_temp is not None:
            _unlink_if_present(manifest_temp)
        raise


def resolve_exact_recovered_ledger(
    source_path: Path,
    recovered_path: Path,
    manifest_path: Path,
    specification: RecoverySpecification,
) -> RecoveryResolution:
    """Resolve only a mirror that is still the exact declared byte repair."""

    _validate_distinct_paths(source_path, recovered_path, manifest_path)
    _validate_specification(specification)
    for label, path in (
        ("source", source_path),
        ("recovered mirror", recovered_path),
        ("recovery manifest", manifest_path),
    ):
        if not path.is_file():
            raise BacktestLedgerRecoveryError(
                f"{label} is missing; recovered evidence fails closed: {path}"
            )

    manifest = _load_manifest(manifest_path)
    comparison = _verify_exact_single_patch(
        source_path,
        recovered_path,
        specification,
    )
    verification, affected_record = _verify_jsonl_records(
        recovered_path,
        specification,
    )
    _verify_manifest(
        manifest,
        source_path,
        recovered_path,
        comparison,
        verification,
        affected_record,
        specification,
    )
    return {
        "status": RECOVERY_STATUS,
        "source_path": str(source_path.resolve()),
        "resolved_path": str(recovered_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "source_size_bytes": comparison["source_size_bytes"],
        "source_sha256": comparison["source_sha256"],
        "recovered_size_bytes": comparison["recovered_size_bytes"],
        "recovered_sha256": comparison["recovered_sha256"],
        "manifest_sha256": _sha256_file(manifest_path),
        "patch_offset": specification["patch_offset"],
        "patch_byte_count": len(bytes.fromhex(specification["source_bytes_hex"])),
        "record_count": verification["record_count"],
        "verified_record_hash_count": verification["verified_record_hash_count"],
        "affected_record_symbol": affected_record["symbol"],
        "affected_record_hash": affected_record["stored_record_hash"],
        "exact_single_patch_verified": True,
        "source_preserved": True,
    }


class _ComparisonEvidence(TypedDict):
    source_size_bytes: int
    source_sha256: str
    recovered_size_bytes: int
    recovered_sha256: str
    observed_source_bytes_hex: str
    observed_replacement_bytes_hex: str


def _validate_specification(specification: RecoverySpecification) -> None:
    source_bytes = bytes.fromhex(specification["source_bytes_hex"])
    replacement_bytes = bytes.fromhex(specification["replacement_bytes_hex"])
    if not source_bytes or len(source_bytes) != len(replacement_bytes):
        raise ValueError(
            "incident source and replacement bytes must be non-empty and equal length: "
            f"source_length={len(source_bytes)}, replacement_length={len(replacement_bytes)}"
        )
    patch_end = specification["patch_offset"] + len(source_bytes)
    if (
        specification["patch_offset"] < 0
        or patch_end > specification["source_size_bytes"]
    ):
        raise ValueError(
            "incident patch range is outside the specified source: "
            f"offset={specification['patch_offset']}, patch_end={patch_end}, "
            f"source_size={specification['source_size_bytes']}"
        )
    if len(specification["source_sha256"]) != 64:
        raise ValueError(
            "incident source_sha256 must contain 64 hexadecimal characters"
        )
    if len(specification["affected_record_hash"]) != 64:
        raise ValueError(
            "incident affected_record_hash must contain 64 hexadecimal characters"
        )


def _validate_distinct_paths(
    source_path: Path,
    recovered_path: Path,
    manifest_path: Path,
) -> None:
    resolved = {
        source_path.resolve(),
        recovered_path.resolve(),
        manifest_path.resolve(),
    }
    if len(resolved) != 3:
        raise ValueError(
            "source, recovered mirror, and manifest paths must be distinct: "
            f"source={source_path}, recovered={recovered_path}, manifest={manifest_path}"
        )


def _read_exact_patch(
    source_path: Path,
    specification: RecoverySpecification,
) -> bytes:
    expected = bytes.fromhex(specification["source_bytes_hex"])
    with source_path.open("rb") as source:
        source.seek(specification["patch_offset"])
        observed = source.read(len(expected))
    if observed != expected:
        raise BacktestLedgerRecoveryError(
            "source bytes do not match the incident specification: "
            f"path={source_path}, offset={specification['patch_offset']}, "
            f"expected={expected.hex()}, observed={observed.hex()}"
        )
    return observed


def _write_recovered_temp(
    source_path: Path,
    recovered_temp: Path,
    specification: RecoverySpecification,
) -> tuple[str, str]:
    source_digest = hashlib.sha256()
    recovered_digest = hashlib.sha256()
    source_bytes = bytes.fromhex(specification["source_bytes_hex"])
    replacement_bytes = bytes.fromhex(specification["replacement_bytes_hex"])
    with source_path.open("rb") as source, recovered_temp.open("wb") as recovered:
        _copy_exact_bytes(
            source,
            recovered,
            specification["patch_offset"],
            source_digest,
            recovered_digest,
        )
        observed = source.read(len(source_bytes))
        if observed != source_bytes:
            raise BacktestLedgerRecoveryError(
                "source changed while recovery was running: "
                f"offset={specification['patch_offset']}, expected={source_bytes.hex()}, "
                f"observed={observed.hex()}"
            )
        source_digest.update(observed)
        recovered.write(replacement_bytes)
        recovered_digest.update(replacement_bytes)
        while True:
            chunk = source.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            source_digest.update(chunk)
            recovered_digest.update(chunk)
            recovered.write(chunk)
        recovered.flush()
        os.fsync(recovered.fileno())
    if recovered_temp.stat().st_size != specification["source_size_bytes"]:
        raise BacktestLedgerRecoveryError(
            "recovered mirror size changed unexpectedly: "
            f"expected={specification['source_size_bytes']}, "
            f"observed={recovered_temp.stat().st_size}"
        )
    return source_digest.hexdigest(), recovered_digest.hexdigest()


def _copy_exact_bytes(
    source: BinaryIO,
    recovered: BinaryIO,
    byte_count: int,
    source_digest: "_HashUpdater",
    recovered_digest: "_HashUpdater",
) -> None:
    remaining = byte_count
    while remaining:
        chunk = source.read(min(COPY_CHUNK_BYTES, remaining))
        if not chunk:
            raise BacktestLedgerRecoveryError(
                f"source ended before the patch offset: remaining_bytes={remaining}"
            )
        source_digest.update(chunk)
        recovered_digest.update(chunk)
        recovered.write(chunk)
        remaining -= len(chunk)


class _HashUpdater(Protocol):
    def update(self, data: bytes) -> None: ...


def _verify_exact_single_patch(
    source_path: Path,
    recovered_path: Path,
    specification: RecoverySpecification,
) -> _ComparisonEvidence:
    source_size = source_path.stat().st_size
    recovered_size = recovered_path.stat().st_size
    if (
        source_size != specification["source_size_bytes"]
        or recovered_size != source_size
    ):
        raise BacktestLedgerRecoveryError(
            "source or recovered size does not match the exact recovery contract: "
            f"expected_source={specification['source_size_bytes']}, "
            f"observed_source={source_size}, observed_recovered={recovered_size}"
        )
    source_digest = hashlib.sha256()
    recovered_digest = hashlib.sha256()
    expected_source = bytes.fromhex(specification["source_bytes_hex"])
    expected_replacement = bytes.fromhex(specification["replacement_bytes_hex"])
    with source_path.open("rb") as source, recovered_path.open("rb") as recovered:
        remaining = specification["patch_offset"]
        while remaining:
            read_size = min(COPY_CHUNK_BYTES, remaining)
            source_chunk = source.read(read_size)
            recovered_chunk = recovered.read(read_size)
            if source_chunk != recovered_chunk or len(source_chunk) != read_size:
                raise BacktestLedgerRecoveryError(
                    "recovered mirror differs before the declared patch: "
                    f"remaining_before_patch={remaining}"
                )
            source_digest.update(source_chunk)
            recovered_digest.update(recovered_chunk)
            remaining -= read_size
        source_patch = source.read(len(expected_source))
        recovered_patch = recovered.read(len(expected_replacement))
        if source_patch != expected_source or recovered_patch != expected_replacement:
            raise BacktestLedgerRecoveryError(
                "declared patch bytes do not match the source and recovered mirror: "
                f"source_expected={expected_source.hex()}, source_observed={source_patch.hex()}, "
                f"replacement_expected={expected_replacement.hex()}, "
                f"replacement_observed={recovered_patch.hex()}"
            )
        source_digest.update(source_patch)
        recovered_digest.update(recovered_patch)
        while True:
            source_chunk = source.read(COPY_CHUNK_BYTES)
            recovered_chunk = recovered.read(COPY_CHUNK_BYTES)
            if source_chunk != recovered_chunk:
                raise BacktestLedgerRecoveryError(
                    "recovered mirror differs after the declared patch"
                )
            if not source_chunk:
                break
            source_digest.update(source_chunk)
            recovered_digest.update(recovered_chunk)
    source_sha256 = source_digest.hexdigest()
    if source_sha256 != specification["source_sha256"]:
        raise BacktestLedgerRecoveryError(
            "source hash does not match the incident specification: "
            f"expected={specification['source_sha256']}, observed={source_sha256}"
        )
    return {
        "source_size_bytes": source_size,
        "source_sha256": source_sha256,
        "recovered_size_bytes": recovered_size,
        "recovered_sha256": recovered_digest.hexdigest(),
        "observed_source_bytes_hex": source_patch.hex(),
        "observed_replacement_bytes_hex": recovered_patch.hex(),
    }


def _verify_jsonl_records(
    recovered_path: Path,
    specification: RecoverySpecification,
) -> tuple[RecordVerificationEvidence, PatchRecordEvidence]:
    record_count = 0
    byte_start = 0
    affected_record: PatchRecordEvidence | None = None
    with recovered_path.open("rb") as recovered:
        for line_number, raw_line in enumerate(recovered, start=1):
            byte_end = byte_start + len(raw_line)
            if not raw_line.strip():
                raise BacktestLedgerRecoveryError(
                    f"recovered JSONL contains a blank line: path={recovered_path}, line={line_number}"
                )
            try:
                decoded = raw_line.decode("utf-8")
            except UnicodeDecodeError as error:
                raise BacktestLedgerRecoveryError(
                    "recovered JSONL is not valid UTF-8: "
                    f"path={recovered_path}, line={line_number}, offset={error.start}"
                ) from error
            try:
                parsed = json.loads(decoded)
            except json.JSONDecodeError as error:
                raise BacktestLedgerRecoveryError(
                    "recovered JSONL line is invalid JSON: "
                    f"path={recovered_path}, line={line_number}, column={error.colno}"
                ) from error
            if not isinstance(parsed, dict):
                raise BacktestLedgerRecoveryError(
                    f"recovered JSONL line is not an object: path={recovered_path}, line={line_number}"
                )
            record = cast(dict[str, object], parsed)
            stored_hash = str(record.get("record_hash", ""))
            computed_hash = stable_backtest_hash(record)
            if len(stored_hash) != 64 or not hmac.compare_digest(
                stored_hash, computed_hash
            ):
                raise BacktestLedgerRecoveryError(
                    "recovered record hash verification failed: "
                    f"path={recovered_path}, line={line_number}, "
                    f"stored={stored_hash}, computed={computed_hash}"
                )
            record_count += 1
            if byte_start <= specification["patch_offset"] < byte_end:
                if affected_record is not None:
                    raise BacktestLedgerRecoveryError(
                        "declared patch offset resolved to more than one JSONL record"
                    )
                affected_record = {
                    "line_number": line_number,
                    "byte_start": byte_start,
                    "byte_end_exclusive": byte_end,
                    "symbol": str(record.get("symbol", "")),
                    "stored_record_hash": stored_hash,
                    "computed_record_hash": computed_hash,
                    "record_hash_verified": True,
                }
            byte_start = byte_end
    if affected_record is None:
        raise BacktestLedgerRecoveryError(
            "declared patch offset does not resolve to a recovered JSONL record: "
            f"offset={specification['patch_offset']}"
        )
    if affected_record["symbol"] != specification["affected_record_symbol"]:
        raise BacktestLedgerRecoveryError(
            "recovered patch record symbol does not match the incident: "
            f"expected={specification['affected_record_symbol']}, "
            f"observed={affected_record['symbol']}"
        )
    if not hmac.compare_digest(
        affected_record["stored_record_hash"],
        specification["affected_record_hash"],
    ):
        raise BacktestLedgerRecoveryError(
            "recovered patch record hash does not match the incident: "
            f"expected={specification['affected_record_hash']}, "
            f"observed={affected_record['stored_record_hash']}"
        )
    verification: RecordVerificationEvidence = {
        "encoding": "utf-8",
        "utf8_valid": True,
        "jsonl_valid": True,
        "record_count": record_count,
        "stored_record_hash_count": record_count,
        "verified_record_hash_count": record_count,
        "record_hash_failure_count": 0,
        "hash_function": "dopey_backtest.backtest_models.stable_backtest_hash",
    }
    return verification, affected_record


def _build_manifest(
    source_path: Path,
    recovered_path: Path,
    size_bytes: int,
    source_sha256: str,
    recovered_sha256: str,
    observed_patch: bytes,
    verification: RecordVerificationEvidence,
    affected_record: PatchRecordEvidence,
    specification: RecoverySpecification,
) -> RecoveryManifest:
    replacement_bytes = bytes.fromhex(specification["replacement_bytes_hex"])
    return {
        "artifact_type": "backtest_trade_records_recovery_manifest",
        "recovery_policy_version": RECOVERY_POLICY_VERSION,
        "incident_id": specification["incident_id"],
        "recovery_status": RECOVERY_STATUS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(source_path.resolve()),
            "size_bytes": size_bytes,
            "sha256": source_sha256,
        },
        "recovered": {
            "path": str(recovered_path.resolve()),
            "size_bytes": size_bytes,
            "sha256": recovered_sha256,
        },
        "patch": {
            "absolute_offset": specification["patch_offset"],
            "byte_count": len(observed_patch),
            "expected_source_bytes_hex": specification["source_bytes_hex"],
            "observed_source_bytes_hex": observed_patch.hex(),
            "replacement_bytes_hex": specification["replacement_bytes_hex"],
            "observed_replacement_bytes_hex": replacement_bytes.hex(),
            "replacement_ascii": replacement_bytes.decode("ascii"),
            "exact_single_patch_verified": True,
            "affected_record": affected_record,
        },
        "verification": verification,
        "source_preserved": True,
        "records_deleted": 0,
        "records_reordered": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _verify_manifest(
    manifest: RecoveryManifest,
    source_path: Path,
    recovered_path: Path,
    comparison: _ComparisonEvidence,
    verification: RecordVerificationEvidence,
    affected_record: PatchRecordEvidence,
    specification: RecoverySpecification,
) -> None:
    expected_values: tuple[tuple[str, object, object], ...] = (
        (
            "artifact_type",
            manifest["artifact_type"],
            "backtest_trade_records_recovery_manifest",
        ),
        (
            "recovery_policy_version",
            manifest["recovery_policy_version"],
            RECOVERY_POLICY_VERSION,
        ),
        ("incident_id", manifest["incident_id"], specification["incident_id"]),
        ("recovery_status", manifest["recovery_status"], RECOVERY_STATUS),
        ("source.path", manifest["source"]["path"], str(source_path.resolve())),
        (
            "source.size_bytes",
            manifest["source"]["size_bytes"],
            comparison["source_size_bytes"],
        ),
        ("source.sha256", manifest["source"]["sha256"], comparison["source_sha256"]),
        (
            "recovered.path",
            manifest["recovered"]["path"],
            str(recovered_path.resolve()),
        ),
        (
            "recovered.size_bytes",
            manifest["recovered"]["size_bytes"],
            comparison["recovered_size_bytes"],
        ),
        (
            "recovered.sha256",
            manifest["recovered"]["sha256"],
            comparison["recovered_sha256"],
        ),
        (
            "patch.absolute_offset",
            manifest["patch"]["absolute_offset"],
            specification["patch_offset"],
        ),
        (
            "patch.byte_count",
            manifest["patch"]["byte_count"],
            len(bytes.fromhex(specification["source_bytes_hex"])),
        ),
        (
            "patch.expected_source_bytes_hex",
            manifest["patch"]["expected_source_bytes_hex"],
            specification["source_bytes_hex"],
        ),
        (
            "patch.observed_source_bytes_hex",
            manifest["patch"]["observed_source_bytes_hex"],
            comparison["observed_source_bytes_hex"],
        ),
        (
            "patch.replacement_bytes_hex",
            manifest["patch"]["replacement_bytes_hex"],
            specification["replacement_bytes_hex"],
        ),
        (
            "patch.observed_replacement_bytes_hex",
            manifest["patch"]["observed_replacement_bytes_hex"],
            comparison["observed_replacement_bytes_hex"],
        ),
        (
            "patch.affected_record",
            manifest["patch"]["affected_record"],
            affected_record,
        ),
        ("verification", manifest["verification"], verification),
        ("source_preserved", manifest["source_preserved"], True),
        ("records_deleted", manifest["records_deleted"], 0),
        ("records_reordered", manifest["records_reordered"], False),
        ("paper_only", manifest["paper_only"], True),
        ("live_blocked", manifest["live_blocked"], True),
    )
    for field, observed, expected in expected_values:
        if observed != expected:
            raise BacktestLedgerRecoveryError(
                "recovery manifest proof does not match current evidence: "
                f"field={field}, expected={expected!r}, observed={observed!r}"
            )
    if manifest["patch"]["exact_single_patch_verified"] is not True:
        raise BacktestLedgerRecoveryError(
            "recovery manifest does not assert exact_single_patch_verified=true"
        )
    expected_ascii = bytes.fromhex(specification["replacement_bytes_hex"]).decode(
        "ascii"
    )
    if manifest["patch"]["replacement_ascii"] != expected_ascii:
        raise BacktestLedgerRecoveryError(
            "recovery manifest replacement_ascii does not match the replacement bytes"
        )


def _load_manifest(manifest_path: Path) -> RecoveryManifest:
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BacktestLedgerRecoveryError(
            f"recovery manifest is unreadable or invalid JSON: path={manifest_path}"
        ) from error
    if not isinstance(value, dict):
        raise BacktestLedgerRecoveryError(
            f"recovery manifest must be a JSON object: path={manifest_path}"
        )
    required = {
        "artifact_type",
        "recovery_policy_version",
        "incident_id",
        "recovery_status",
        "generated_at",
        "source",
        "recovered",
        "patch",
        "verification",
        "source_preserved",
        "records_deleted",
        "records_reordered",
        "paper_only",
        "live_blocked",
    }
    if set(value) != required:
        raise BacktestLedgerRecoveryError(
            "recovery manifest fields do not match the exact schema: "
            f"path={manifest_path}, missing={sorted(required - set(value))}, "
            f"extra={sorted(set(value) - required)}"
        )
    for field in ("source", "recovered", "patch", "verification"):
        if not isinstance(value[field], dict):
            raise BacktestLedgerRecoveryError(
                f"recovery manifest field must be an object: path={manifest_path}, field={field}"
            )
    nested_fields = {
        "source": {"path", "size_bytes", "sha256"},
        "recovered": {"path", "size_bytes", "sha256"},
        "patch": {
            "absolute_offset",
            "byte_count",
            "expected_source_bytes_hex",
            "observed_source_bytes_hex",
            "replacement_bytes_hex",
            "observed_replacement_bytes_hex",
            "replacement_ascii",
            "exact_single_patch_verified",
            "affected_record",
        },
        "verification": {
            "encoding",
            "utf8_valid",
            "jsonl_valid",
            "record_count",
            "stored_record_hash_count",
            "verified_record_hash_count",
            "record_hash_failure_count",
            "hash_function",
        },
    }
    for field, expected_fields in nested_fields.items():
        observed_fields = set(cast(dict[str, object], value[field]))
        if observed_fields != expected_fields:
            raise BacktestLedgerRecoveryError(
                "recovery manifest nested fields do not match the exact schema: "
                f"path={manifest_path}, field={field}, "
                f"missing={sorted(expected_fields - observed_fields)}, "
                f"extra={sorted(observed_fields - expected_fields)}"
            )
    patch = cast(dict[str, object], value["patch"])
    if not isinstance(patch["affected_record"], dict):
        raise BacktestLedgerRecoveryError(
            f"recovery manifest patch.affected_record must be an object: path={manifest_path}"
        )
    affected_record_fields = {
        "line_number",
        "byte_start",
        "byte_end_exclusive",
        "symbol",
        "stored_record_hash",
        "computed_record_hash",
        "record_hash_verified",
    }
    observed_affected_fields = set(cast(dict[str, object], patch["affected_record"]))
    if observed_affected_fields != affected_record_fields:
        raise BacktestLedgerRecoveryError(
            "recovery manifest affected-record fields do not match the exact schema: "
            f"path={manifest_path}, "
            f"missing={sorted(affected_record_fields - observed_affected_fields)}, "
            f"extra={sorted(observed_affected_fields - affected_record_fields)}"
        )
    try:
        generated_at = datetime.fromisoformat(str(value["generated_at"]))
    except ValueError as error:
        raise BacktestLedgerRecoveryError(
            f"recovery manifest generated_at is not ISO-8601: path={manifest_path}"
        ) from error
    if generated_at.tzinfo is None:
        raise BacktestLedgerRecoveryError(
            f"recovery manifest generated_at must be timezone-aware: path={manifest_path}"
        )
    return cast(RecoveryManifest, value)


def _temporary_path(target_path: Path) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=target_path.parent,
    )
    os.close(descriptor)
    return Path(temporary_name)


def _write_json_temp(path: Path, payload: RecoveryManifest) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise BacktestLedgerRecoveryError(
            f"failed to remove incomplete recovery temp file: path={path}"
        ) from error
