"""Integration coverage for process-owned operation leases."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dopey.chronos.leases import LeaseAlreadyHeldError, operation_lease


def test_operation_lease_blocks_live_owner_and_quarantines_stale_owner(tmp_path: Path) -> None:
    lease_path = tmp_path / "operation.lease"
    quarantine = tmp_path / "quarantine"
    with operation_lease(lease_path, 60, quarantine) as lease:
        assert lease_path.exists()
        assert lease["process_id"] == os.getpid()
        with pytest.raises(LeaseAlreadyHeldError):
            with operation_lease(lease_path, 60, quarantine):
                raise AssertionError("unreachable")
    assert not lease_path.exists()

    lease_path.write_text(
        json.dumps(
            {
                "artifact_type": "dopey_operation_lease",
                "lease_version": "dopey-chronos-process-lease-v1",
                "lease_id": "stale-test",
                "process_id": 2_147_483_647,
                "acquired_at": "2026-07-14T00:00:00+00:00",
                "expires_at": "2026-07-14T00:01:00+00:00",
                "paper_only": True,
                "live_blocked": True,
            }
        ),
        encoding="utf-8",
    )
    with operation_lease(lease_path, 60, quarantine) as replacement:
        assert replacement["lease_id"] != "stale-test"
    quarantined = list(quarantine.glob("*.stale_process.json"))
    assert len(quarantined) == 1
