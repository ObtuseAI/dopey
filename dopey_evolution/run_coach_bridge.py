"""Persist deterministic quarantined proposals from the latest two-coach sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dopey.evolution.coach_bridge import build_quarantined_coach_proposal_batch
from dopey.protocols.identity import canonical_hash
from dopey_research_pipeline.artifact_io import append_jsonl, write_json_atomic


def _load_sessions(coach_root: Path) -> tuple[dict[str, Any], ...]:
    if not coach_root.is_dir():
        raise FileNotFoundError(
            f"coach artifact root does not exist: path={coach_root}"
        )
    sessions: list[dict[str, Any]] = []
    for path in sorted(coach_root.glob("*.json")):
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(f"coach artifact must be a JSON object: path={path}")
        sessions.append(value)
    if not sessions:
        raise FileNotFoundError(
            f"coach artifact root contains no session JSON files: path={coach_root}"
        )
    return tuple(sessions)


def _append_batch_idempotently(path: Path, batch: dict[str, Any]) -> bool:
    batch_id = str(batch["batch_id"])
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record: Any = json.loads(stripped)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"coach proposal ledger is malformed: path={path}, line={line_number}, error={error}"
                    ) from error
                if not isinstance(record, dict):
                    raise TypeError(
                        f"coach proposal ledger record must be an object: path={path}, line={line_number}"
                    )
                if record.get("batch_id") != batch_id:
                    continue
                if canonical_hash(record) != canonical_hash(batch):
                    raise ValueError(
                        f"coach proposal batch identity conflict: path={path}, batch_id={batch_id}"
                    )
                return False
    append_jsonl(path, batch)
    return True


def persist_coach_batch(
    sessions: tuple[dict[str, Any], ...],
    output_root: Path,
) -> dict[str, Any]:
    if not sessions:
        raise ValueError("coach proposal persistence requires at least one session")
    batch = dict(build_quarantined_coach_proposal_batch(sessions))
    quarantine_path = (
        output_root / "quarantine" / f"{batch['batch_id'].replace(':', '_')}.json"
    )
    if quarantine_path.exists():
        existing: Any = json.loads(quarantine_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or canonical_hash(existing) != canonical_hash(
            batch
        ):
            raise ValueError(
                "coach proposal quarantine identity conflict: "
                f"path={quarantine_path}, batch_id={batch['batch_id']}"
            )
    else:
        write_json_atomic(quarantine_path, batch)
    appended = _append_batch_idempotently(output_root / "batch_ledger.jsonl", batch)
    write_json_atomic(output_root / "latest_batch.json", batch)
    return {
        "batch_id": batch["batch_id"],
        "batch_status": batch["batch_status"],
        "outcome_status": batch["outcome_status"],
        "source_session_count": batch["source_session_count"],
        "proposal_count": batch["proposal_count"],
        "linked_proposal_count": batch["linked_proposal_count"],
        "blocked_proposal_count": batch["blocked_proposal_count"],
        "ledger_appended": appended,
        "latest_batch_path": str(output_root / "latest_batch.json"),
        "quarantine_path": str(quarantine_path),
    }


def run_coach_bridge(coach_root: Path, output_root: Path) -> dict[str, Any]:
    return persist_coach_batch(_load_sessions(coach_root), output_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Quarantine grounded coach research proposals"
    )
    parser.add_argument("--coach-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            run_coach_bridge(arguments.coach_root, arguments.output_root),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
