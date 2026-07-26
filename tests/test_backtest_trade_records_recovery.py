"""Temp-path integration tests for exact backtest-ledger recovery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_backtest.backtest_models import stable_backtest_hash
from dopey_backtest.trade_records_recovery import (
    BacktestLedgerRecoveryError,
    RecoverySpecification,
    iter_verified_trade_records,
    recover_exact_byte_incident,
    resolve_exact_recovered_ledger,
    resolve_verified_trade_ledger,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash


CORRUPT_BYTES = bytes.fromhex("d270c5f78cbcf0bb16d0d49720826800")
REPLACEMENT_BYTES = b'te": "2021-12-16'


def _trade_record(symbol: str, signal_date: str) -> dict[str, object]:
    record: dict[str, object] = {
        "artifact_type": "backtest_trade_record",
        "candidate_strategy": "long_call",
        "signal_date": signal_date,
        "signal_family": "relative_strength",
        "symbol": symbol,
        "trade_return_model_units": 0.125,
        "win_loss_marker": "win_model_validation_only",
    }
    record["record_hash"] = stable_backtest_hash(record)
    return record


def _fixture_paths(
    tmp_path: Path,
) -> tuple[Path, Path, Path, RecoverySpecification, bytes, bytes]:
    source_path = tmp_path / "backtest_trade_records.jsonl"
    recovered_path = tmp_path / "backtest_trade_records.recovered.jsonl"
    manifest_path = tmp_path / "backtest_trade_records.recovery_manifest.json"
    records = (
        _trade_record("MSFT", "2021-12-15"),
        _trade_record("EQIX", "2021-12-16"),
    )
    healthy_bytes = b"".join(
        (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        for record in records
    )
    patch_offset = healthy_bytes.index(REPLACEMENT_BYTES)
    source_bytes = (
        healthy_bytes[:patch_offset]
        + CORRUPT_BYTES
        + healthy_bytes[patch_offset + len(REPLACEMENT_BYTES) :]
    )
    source_path.write_bytes(source_bytes)
    specification: RecoverySpecification = {
        "incident_id": "test-invalid-utf8-record",
        "source_size_bytes": len(source_bytes),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "patch_offset": patch_offset,
        "source_bytes_hex": CORRUPT_BYTES.hex(),
        "replacement_bytes_hex": REPLACEMENT_BYTES.hex(),
        "affected_record_symbol": "EQIX",
        "affected_record_hash": str(records[1]["record_hash"]),
    }
    return (
        source_path,
        recovered_path,
        manifest_path,
        specification,
        source_bytes,
        healthy_bytes,
    )


def _write_authoritative_evidence(
    tmp_path: Path,
    source_path: Path,
    record_count: int,
    ledger_sha256: str | None,
) -> tuple[Path, Path]:
    summary_path = tmp_path / "backtest_run_summary.json"
    proof_path = tmp_path / "backtest_proof.jsonl"
    summary: dict[str, object] = {
        "artifact_type": "backtest_run_summary",
        "artifact_paths": {"backtest_trade_records": str(source_path.resolve())},
        "trade_record_count": record_count,
    }
    if ledger_sha256 is not None:
        summary["backtest_trade_records_sha256"] = ledger_sha256
    summary["run_hash"] = stable_backtest_hash(summary)
    proof: dict[str, object] = {
        "artifact_type": "backtest_proof",
        "proof_id": "dopey-real-history-honest-backtester-v1-proof",
        "trade_record_count": record_count,
    }
    proof["proof_hash"] = reproducibility_hash(proof)
    summary_path.write_text(
        json.dumps(summary, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    proof_path.write_text(
        json.dumps(proof, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path, proof_path


def test_recovery_preserves_source_and_publishes_exact_verified_mirror(
    tmp_path: Path,
) -> None:
    (
        source_path,
        recovered_path,
        manifest_path,
        specification,
        source_bytes,
        healthy_bytes,
    ) = _fixture_paths(tmp_path)

    manifest = recover_exact_byte_incident(
        source_path,
        recovered_path,
        manifest_path,
        specification,
    )
    resolution = resolve_exact_recovered_ledger(
        source_path,
        recovered_path,
        manifest_path,
        specification,
    )

    assert source_path.read_bytes() == source_bytes
    assert recovered_path.read_bytes() == healthy_bytes
    assert manifest["source_preserved"] is True
    assert manifest["patch"]["exact_single_patch_verified"] is True
    assert manifest["verification"]["record_count"] == 2
    assert manifest["verification"]["verified_record_hash_count"] == 2
    assert resolution["status"] == "recovered_mirror_verified"
    assert resolution["record_count"] == 2
    assert resolution["affected_record_symbol"] == "EQIX"
    assert resolution["affected_record_hash"] == specification["affected_record_hash"]


def test_resolver_fails_closed_when_recovered_mirror_changes(tmp_path: Path) -> None:
    (
        source_path,
        recovered_path,
        manifest_path,
        specification,
        _,
        _,
    ) = _fixture_paths(tmp_path)
    recover_exact_byte_incident(
        source_path,
        recovered_path,
        manifest_path,
        specification,
    )
    recovered_path.write_bytes(recovered_path.read_bytes() + b" ")

    with pytest.raises(BacktestLedgerRecoveryError, match="size"):
        resolve_exact_recovered_ledger(
            source_path,
            recovered_path,
            manifest_path,
            specification,
        )


def test_resolver_fails_closed_when_manifest_proof_changes(tmp_path: Path) -> None:
    (
        source_path,
        recovered_path,
        manifest_path,
        specification,
        _,
        _,
    ) = _fixture_paths(tmp_path)
    recover_exact_byte_incident(
        source_path,
        recovered_path,
        manifest_path,
        specification,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["verification"]["record_count"] += 1
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(BacktestLedgerRecoveryError, match="manifest proof"):
        resolve_exact_recovered_ledger(
            source_path,
            recovered_path,
            manifest_path,
            specification,
        )


def test_general_resolver_accepts_fully_verified_current_source(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "backtest_trade_records.jsonl"
    recovered_path = tmp_path / "backtest_trade_records.recovered.jsonl"
    manifest_path = tmp_path / "backtest_trade_records.recovery_manifest.json"
    records = (
        _trade_record("MSFT", "2026-07-20"),
        _trade_record("AAPL", "2026-07-21"),
    )
    source_bytes = b"".join(
        (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        for record in records
    )
    source_path.write_bytes(source_bytes)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    summary_path, proof_path = _write_authoritative_evidence(
        tmp_path,
        source_path,
        len(records),
        source_sha256,
    )
    unrelated_specification: RecoverySpecification = {
        "incident_id": "unrelated-incident",
        "source_size_bytes": 1,
        "source_sha256": "0" * 64,
        "patch_offset": 0,
        "source_bytes_hex": "00",
        "replacement_bytes_hex": "01",
        "affected_record_symbol": "NONE",
        "affected_record_hash": "0" * 64,
    }

    resolution = resolve_verified_trade_ledger(
        source_path,
        recovered_path,
        manifest_path,
        (summary_path, proof_path),
        unrelated_specification,
    )

    assert resolution["status"] == "source_ledger_verified_current"
    assert resolution["resolved_path"] == str(source_path.resolve())
    assert resolution["resolved_sha256"] == source_sha256
    assert resolution["record_count"] == len(records)
    assert resolution["verified_record_hash_count"] == len(records)
    assert resolution["incident_recovery_used"] is False
    assert len(resolution["authoritative_evidence"]) == 2
    assert list(iter_verified_trade_records(resolution)) == list(records)


def test_general_resolver_uses_recovery_only_for_exact_incident(
    tmp_path: Path,
) -> None:
    (
        source_path,
        recovered_path,
        manifest_path,
        specification,
        _,
        healthy_bytes,
    ) = _fixture_paths(tmp_path)
    recover_exact_byte_incident(
        source_path,
        recovered_path,
        manifest_path,
        specification,
    )
    summary_path, proof_path = _write_authoritative_evidence(
        tmp_path,
        source_path,
        2,
        hashlib.sha256(healthy_bytes).hexdigest(),
    )

    resolution = resolve_verified_trade_ledger(
        source_path,
        recovered_path,
        manifest_path,
        (summary_path, proof_path),
        specification,
    )

    assert resolution["status"] == "recovered_mirror_verified"
    assert resolution["resolved_path"] == str(recovered_path.resolve())
    assert resolution["incident_recovery_used"] is True
    assert resolution["source_sha256"] == specification["source_sha256"]


def test_general_resolver_rejects_changed_nonincident_source(
    tmp_path: Path,
) -> None:
    (
        source_path,
        recovered_path,
        manifest_path,
        specification,
        _,
        _,
    ) = _fixture_paths(tmp_path)
    changed = bytearray(source_path.read_bytes())
    changed[-2] ^= 1
    source_path.write_bytes(bytes(changed))
    summary_path, proof_path = _write_authoritative_evidence(
        tmp_path,
        source_path,
        2,
        None,
    )

    with pytest.raises(
        BacktestLedgerRecoveryError,
        match="neither fully valid nor the exact declared incident",
    ):
        resolve_verified_trade_ledger(
            source_path,
            recovered_path,
            manifest_path,
            (summary_path, proof_path),
            specification,
        )


def test_general_resolver_rejects_authoritative_count_mismatch(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "backtest_trade_records.jsonl"
    recovered_path = tmp_path / "backtest_trade_records.recovered.jsonl"
    manifest_path = tmp_path / "backtest_trade_records.recovery_manifest.json"
    record = _trade_record("MSFT", "2026-07-20")
    source_path.write_text(
        json.dumps(record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path, proof_path = _write_authoritative_evidence(
        tmp_path,
        source_path,
        2,
        None,
    )
    unrelated_specification: RecoverySpecification = {
        "incident_id": "unrelated-incident",
        "source_size_bytes": 1,
        "source_sha256": "0" * 64,
        "patch_offset": 0,
        "source_bytes_hex": "00",
        "replacement_bytes_hex": "01",
        "affected_record_symbol": "NONE",
        "affected_record_hash": "0" * 64,
    }

    with pytest.raises(BacktestLedgerRecoveryError, match="record count disagrees"):
        resolve_verified_trade_ledger(
            source_path,
            recovered_path,
            manifest_path,
            (summary_path, proof_path),
            unrelated_specification,
        )


def test_general_resolver_accepts_fixture_backtester_proof_hash_contract(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "backtest_trade_records.jsonl"
    recovered_path = tmp_path / "backtest_trade_records.recovered.jsonl"
    manifest_path = tmp_path / "backtest_trade_records.recovery_manifest.json"
    record = _trade_record("MSFT", "2026-07-20")
    source_path.write_text(
        json.dumps(record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path, proof_path = _write_authoritative_evidence(
        tmp_path,
        source_path,
        1,
        None,
    )
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["proof_id"] = "dopey-honest-backtester-v1-proof"
    proof["proof_hash"] = stable_backtest_hash(proof)
    proof_path.write_text(
        json.dumps(proof, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    unrelated_specification: RecoverySpecification = {
        "incident_id": "unrelated-incident",
        "source_size_bytes": 1,
        "source_sha256": "0" * 64,
        "patch_offset": 0,
        "source_bytes_hex": "00",
        "replacement_bytes_hex": "01",
        "affected_record_symbol": "NONE",
        "affected_record_hash": "0" * 64,
    }

    resolution = resolve_verified_trade_ledger(
        source_path,
        recovered_path,
        manifest_path,
        (summary_path, proof_path),
        unrelated_specification,
    )

    assert resolution["status"] == "source_ledger_verified_current"
    assert resolution["authoritative_evidence"][1]["self_hash_verified"] is True
