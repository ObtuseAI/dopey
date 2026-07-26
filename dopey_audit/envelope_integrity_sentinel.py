"""Envelope-integrity sentinel: DOPEY polices its own containment every run.

The project envelope is a promise: paper-only, no credentials in the repo, no
live-order wiring, execution sealed behind the action gate plus explicit human
approval, and hash-pinned governed data. Promises rot unless something checks
them. This stage re-verifies the envelope mechanically:

1. SOURCE SCAN - every runtime dopey_* package and operator_tools is scanned
   for credential-literal patterns and unsealed live-order wiring. Simulation
   stubs that raise LiveTradingDisabledError are the allowed exception and are
   listed explicitly, never silently.
2. SEAL CHECK - the action-readiness source must still declare the execution
   policy blocked_until_gate_all_green_plus_explicit_human_approval.
3. PIN VERIFICATION - every file pinned in the real-data and history manifests
   is re-hashed; a tamper or bit-rot shows up as a hash mismatch, a vanished
   file as missing. (This is how the branch-switch data loss of 2026-07-09
   would have been caught in minutes instead of by a manual audit.)

Any violation fails the stage loudly. The sentinel's own file is excluded from
the source scan (it necessarily contains the patterns it hunts).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTINEL_PATH = Path(__file__).resolve()
INTEGRITY_PATH = REPO_ROOT / "artifacts" / "dopey" / "governance" / "envelope_integrity.json"
GATE_SOURCE = REPO_ROOT / "dopey_broker_readiness" / "action_readiness_gate.py"
EXECUTION_SEAL = "blocked_until_gate_all_green_plus_explicit_human_approval"

MANIFESTS = (
    REPO_ROOT / "dopey_data" / "real" / "manifests" / "real_data_manifest.json",
    REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json",
    REPO_ROOT / "dopey_data" / "history" / "history_dataset_manifest.json",
)

# Assembled from fragments so the sentinel never matches its own pattern table.
CREDENTIAL_PATTERNS = tuple(
    re.compile(fragment_a + fragment_b, re.IGNORECASE)
    for fragment_a, fragment_b in (
        (r"(api[_-]?key|secret[_-]?key|access[_-]?token|refresh[_-]?token|passw", r"ord)\s*=\s*[\"'][A-Za-z0-9+/_\-]{8,}"),
        (r"(bearer\s+[A-Za-z0-9\-_]{16,}|authorization[\"']?\s*:\s*[\"']b", r"earer)"),
        (r"load_dotenv\s*\(|dotenv\.", r"load"),
    )
)
ORDER_WIRING_PATTERNS = tuple(
    re.compile(fragment_a + fragment_b, re.IGNORECASE)
    for fragment_a, fragment_b in (
        (r"(requests|httpx|urllib\.request|aiohttp)\s*\.\s*(post|put)\s*\(.{0,120}(order", r"|trade|execution)"),
        (r"api\.robinho", r"od\.com"),
    )
)
ALLOWED_SIMULATION_MARKER = "LiveTradingDisabledError"
SCAN_ROOT_PREFIXES = ("dopey_", "operator_tools")
EXCLUDED_DIR_PARTS = {"__pycache__", "_forked_blunder", "_forked_blunder_tests", "_forked_scripts"}


def scan_source_tree() -> dict[str, list[str]]:
    credential_hits: list[str] = []
    order_hits: list[str] = []
    allowed_simulation_files: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if path == SENTINEL_PATH or not relative.startswith(SCAN_ROOT_PREFIXES):
            continue
        if any(part in EXCLUDED_DIR_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            credential_hits.append(f"unreadable:{relative}")
            continue
        if any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS):
            credential_hits.append(relative)
        if any(pattern.search(text) for pattern in ORDER_WIRING_PATTERNS):
            if ALLOWED_SIMULATION_MARKER in text:
                allowed_simulation_files.append(relative)
            else:
                order_hits.append(relative)
    return {
        "credential_pattern_hits": credential_hits,
        "unsealed_order_wiring_hits": order_hits,
        "allowed_simulation_stub_files": allowed_simulation_files,
    }


def verify_execution_seal() -> bool:
    if not GATE_SOURCE.exists():
        return False
    return EXECUTION_SEAL in GATE_SOURCE.read_text(encoding="utf-8", errors="replace")


def verify_manifest_pins() -> dict[str, Any]:
    checked = 0
    mismatched: list[str] = []
    missing: list[str] = []
    manifests_seen = 0
    for manifest_path in MANIFESTS:
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mismatched.append(f"unparseable_manifest:{manifest_path.name}")
            continue
        manifests_seen += 1
        for relative, recorded in dict(manifest.get("file_hashes", {})).items():
            target = REPO_ROOT / str(relative).replace("\\", "/")
            if not target.exists():
                missing.append(str(relative))
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            checked += 1
            if actual != str(recorded):
                mismatched.append(str(relative))
    return {
        "manifests_seen": manifests_seen,
        "pinned_files_verified": checked,
        "pin_mismatches": sorted(mismatched),
        "pinned_files_missing": sorted(missing),
    }


def run_envelope_integrity_sentinel() -> dict[str, Any]:
    scan = scan_source_tree()
    seal_intact = verify_execution_seal()
    pins = verify_manifest_pins()
    violations: list[str] = []
    if scan["credential_pattern_hits"]:
        violations.append("credential_pattern_in_source")
    if scan["unsealed_order_wiring_hits"]:
        violations.append("unsealed_order_wiring_in_source")
    if not seal_intact:
        violations.append("execution_seal_missing")
    if pins["pin_mismatches"]:
        violations.append("manifest_pin_mismatch")
    if pins["pinned_files_missing"]:
        violations.append("pinned_file_missing")
    summary: dict[str, Any] = {
        "artifact_type": "envelope_integrity_summary",
        "integrity_status": "envelope_intact" if not violations else "envelope_violation",
        "violations": violations,
        **scan,
        "execution_seal_intact": seal_intact,
        "execution_seal": EXECUTION_SEAL,
        **pins,
        "known_accepted_gaps": [
            "earnings_calendar CSVs are staged without sha256 pins (operator lane, low blast radius)",
        ],
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(INTEGRITY_PATH, summary)
    if violations:
        raise RuntimeError(f"envelope_violation:{violations}")
    return summary
