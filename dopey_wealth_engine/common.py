"""Common stdlib-only helpers for the DOPEY wealth engine."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
DATA_ROOT = REPO_ROOT / "dopey_data"
WEALTH_VERSION = "dopey-wealth-engine-market-vision-paper-tournament-v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def stable_hash(record: Mapping[str, object]) -> str:
    encoded = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def with_hash(record: dict, field_name: str) -> dict:
    output = dict(record)
    output[field_name] = stable_hash(output)
    return output


def write_json(path: Path, record: Mapping[str, object]) -> Path:
    ensure_directory(path.parent)
    path.write_text(json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def write_jsonl(path: Path, records: Iterable[Mapping[str, object]], append: bool) -> Path:
    ensure_directory(path.parent)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")
    return path


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {"records": parsed}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if value:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                records.append(parsed)
    return records


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> Path:
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def proof_record(proof_id: str, status: str, payload: Mapping[str, object]) -> dict:
    seed = {
        "artifact_type": "wealth_engine_proof",
        "proof_id": proof_id,
        "status": status,
        "timestamp": utc_now_iso(),
        "payload": dict(payload),
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    return with_hash(seed, "proof_hash")

