"""Safety-boundary drift audit for the offline evidence replay harness.

Verifies that live safety settings are unchanged, no active forbidden live decisions exist,
no hidden live promotion tier appears, and the original Blunder source hash is unchanged.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter

from .artifact_loader import load_records
from .evidence_models import (
    ConsistencyFinding,
    EvidenceInventory,
    FORBIDDEN_LIVE_TOKENS,
)


BLUNDER_MANIFEST_PATH = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")

# Field names that legitimately list forbidden terms as documentation (allowed references).
DOCUMENTATION_FORBIDDEN_LIST_FIELDS = {
    "forbidden_live_decisions",
    "forbidden_live_tiers",
    "forbidden_live_statuses",
    "forbidden_live_decisions_present",
    "forbidden_live_tiers_emitted",
    "allowed_tiers",
    "blocked_tiers",
    "limitations",
    "term_id",
    "pattern",
    "token",
}


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="audit-live-x",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
            {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5},
        ],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )


def _walk_active_decisions(node, path: str, active_findings: list[tuple[str, str]]):
    """Recursively find any *active* forbidden token used as a decision/tier value."""
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            if isinstance(value, str) and value in FORBIDDEN_LIVE_TOKENS:
                # A forbidden token as a *value* is only an active decision if the key looks like
                # a decision/tier/status field; documentation-list fields are allowed.
                if key in DOCUMENTATION_FORBIDDEN_LIST_FIELDS or "forbidden" in key or "allowed" in key or "blocked" in key:
                    continue
                active_findings.append((child_path, value))
            else:
                _walk_active_decisions(value, child_path, active_findings)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            _walk_active_decisions(item, f"{path}[{idx}]", active_findings)


def audit_config_safety() -> list[ConsistencyFinding]:
    cfg = load_config(default_config_path())
    findings: list[ConsistencyFinding] = []
    if str(cfg.get("mode", "RESEARCH")) != "RESEARCH":
        findings.append(ConsistencyFinding(check_id="config_research_mode", severity="safety_error", message=f"mode is {cfg.get('mode')} (expected RESEARCH)"))
    if cfg.get("live_trading_enabled", False) is not False:
        findings.append(ConsistencyFinding(check_id="config_live_disabled", severity="safety_error", message="live_trading_enabled is not false"))
    if cfg.get("funded_broker_connections_enabled", False) is not False:
        findings.append(ConsistencyFinding(check_id="config_funded_disabled", severity="safety_error", message="funded_broker_connections_enabled is not false"))
    if cfg.get("allow_unofficial_robinhood_api", False) is not False:
        findings.append(ConsistencyFinding(check_id="config_robinhood_disabled", severity="safety_error", message="allow_unofficial_robinhood_api is not false"))
    return findings


def audit_live_stubs_block() -> list[ConsistencyFinding]:
    findings: list[ConsistencyFinding] = []
    intent = _live_intent()
    for name, adapter in [("robinhood", RobinhoodMCPAdapter()), ("alpaca", AlpacaOptionsAdapter()), ("tradier", TradierOptionsAdapter()), ("paper", PaperBroker())]:
        try:
            adapter.place_order(intent)
            findings.append(ConsistencyFinding(check_id="live_stubs_block", severity="safety_error", message=f"{name} adapter did not block live order"))
        except LiveTradingDisabledError:
            pass
    return findings


def audit_forbidden_decisions_in_records(inventory: EvidenceInventory) -> list[ConsistencyFinding]:
    findings: list[ConsistencyFinding] = []
    for artifact in inventory.artifacts:
        if artifact.status not in {"present", "stale"}:
            continue
        for record in load_records(artifact.path):
            active: list[tuple[str, str]] = []
            _walk_active_decisions(record, artifact.artifact_type, active)
            for field_path, token in active:
                findings.append(ConsistencyFinding(
                    check_id="forbidden_live_decisions_active",
                    severity="safety_error",
                    message=f"active forbidden live token '{token}' at {field_path}",
                ))
    return findings


def audit_blunder_integrity(manifest_path: Path | str | None = None) -> list[ConsistencyFinding]:
    target = Path(manifest_path) if manifest_path else BLUNDER_MANIFEST_PATH
    findings: list[ConsistencyFinding] = []
    if not target.exists():
        findings.append(ConsistencyFinding(check_id="blunder_integrity", severity="info", message="Blunder SHA256 manifest not available; skipped"))
        return findings
    checked = 0
    for line in target.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        expected, path = parts
        candidate = Path(path)
        if not candidate.exists():
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
        if actual != expected.upper():
            findings.append(ConsistencyFinding(check_id="blunder_integrity", severity="safety_error", message=f"Blunder source hash mismatch: {path}"))
        checked += 1
    if checked == 0:
        findings.append(ConsistencyFinding(check_id="blunder_integrity", severity="warning", message="Blunder manifest present but no files checked"))
    return findings


def run_safety_audit(inventory: EvidenceInventory) -> tuple[list[ConsistencyFinding], int]:
    """Run all safety-boundary checks. Returns (findings, active_forbidden_decision_count)."""
    findings: list[ConsistencyFinding] = []
    findings.extend(audit_config_safety())
    findings.extend(audit_live_stubs_block())
    forbidden = audit_forbidden_decisions_in_records(inventory)
    findings.extend(forbidden)
    findings.extend(audit_blunder_integrity())
    active_forbidden = sum(1 for f in findings if f.check_id == "forbidden_live_decisions_active")
    return findings, active_forbidden
