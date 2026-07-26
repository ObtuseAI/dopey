"""Forbidden boundary classifier for the offline pre-run safety scanner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .broker_readiness_models import stable_hash


FORBIDDEN_BOUNDARY_PATTERNS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ROBINHOOD",
    "ROBINHOOD_TOKEN",
    "RH_TOKEN",
    "access_token",
    "refresh_token",
    ".env",
    "place_order",
    "place_option_order",
    "cancel_order",
    "cancel_option_order",
    "review_option_order",
    "live_order",
    "live_trading_enabled=true",
    "live_allowed=true",
    "broker_connection",
    "broker_session",
    "account_balance",
    "buying_power",
    "real_capital",
    "real_sizing",
    "scheduler",
    "cron",
    "daemon",
    "network_market_data",
    "requests.get",
    "websocket",
    "mcp.connect",
    "robinhood_mcp",
)

ACTIVE_RUNTIME_CLASSIFICATION = "forbidden_active_runtime_usage"
DOCUMENTATION_CLASSIFICATION = "allowed_documentation_mention"
NEGATIVE_CONTROL_CLASSIFICATION = "allowed_negative_control_fixture"
BLOCKED_TEMPLATE_CLASSIFICATION = "allowed_blocked_command_template"
REPORT_CLASSIFICATION = "allowed_report_statement"


@dataclass(frozen=True)
class BoundaryScanSource:
    source_id: str
    source_path: str
    text: str
    context_type: str
    metadata: dict[str, Any]


def forbidden_boundary_pattern_payload() -> dict[str, Any]:
    seed = {
        "artifact_type": "pre_run_forbidden_boundary_patterns",
        "pattern_count": len(FORBIDDEN_BOUNDARY_PATTERNS),
        "patterns": list(FORBIDDEN_BOUNDARY_PATTERNS),
        "paper_only": True,
        "live_blocked": True,
        "pattern_hash": "",
    }
    return {**seed, "pattern_hash": stable_hash(seed)}


def classify_boundary_references(sources: list[BoundaryScanSource]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in sources:
        lowered_text = source.text.lower()
        for pattern in FORBIDDEN_BOUNDARY_PATTERNS:
            if pattern.lower() not in lowered_text:
                continue
            classification = _classification(source)
            active_forbidden = classification == ACTIVE_RUNTIME_CLASSIFICATION
            seed = {
                "classification_id": f"pre-run-boundary-classification-{len(records) + 1:03d}",
                "source_id": source.source_id,
                "source_path": source.source_path,
                "context_type": source.context_type,
                "pattern": pattern,
                "classification": classification,
                "active_forbidden": active_forbidden,
                "terminal_block": active_forbidden,
                "manual_review": False,
                "paper_only": True,
                "live_blocked": True,
                "classification_hash": "",
            }
            records.append({**seed, "classification_hash": stable_hash(seed)})
    return records


def build_boundary_scan_sources(
    command_templates: list[dict[str, Any]],
    fixture_cases: list[dict[str, Any]],
    source_paths: list[Path],
) -> list[BoundaryScanSource]:
    sources: list[BoundaryScanSource] = []
    for index, template in enumerate(command_templates):
        sources.append(BoundaryScanSource(
            source_id=f"disabled-command-template-{index + 1:03d}",
            source_path=str(template.get("template_id", "")),
            text=" ".join(str(value) for value in template.values()),
            context_type="blocked_command_template" if template.get("enabled") is False and template.get("allowed_now") is False else "active_runtime",
            metadata=template,
        ))
    for index, fixture in enumerate(fixture_cases):
        context_type = str(fixture.get("boundary_context", "negative_control_fixture"))
        sources.append(BoundaryScanSource(
            source_id=f"pre-run-fixture-case-{index + 1:03d}",
            source_path=str(fixture.get("case_id", "")),
            text=str(fixture.get("boundary_text", "")),
            context_type=context_type,
            metadata=fixture,
        ))
    for index, path in enumerate(source_paths):
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        sources.append(BoundaryScanSource(
            source_id=f"pre-run-source-path-{index + 1:03d}",
            source_path=str(path),
            text=text,
            context_type=_context_type_for_path(path),
            metadata={"suffix": path.suffix.lower()},
        ))
    return sources


def _classification(source: BoundaryScanSource) -> str:
    context_type = source.context_type
    source_path = source.source_path.lower().replace("\\", "/")
    if context_type == "active_runtime":
        return ACTIVE_RUNTIME_CLASSIFICATION
    if context_type == "blocked_command_template":
        return BLOCKED_TEMPLATE_CLASSIFICATION
    if context_type == "negative_control_fixture":
        return NEGATIVE_CONTROL_CLASSIFICATION
    if context_type == "report_statement":
        return REPORT_CLASSIFICATION
    if context_type == "documentation":
        return DOCUMENTATION_CLASSIFICATION
    if "/tests/" in source_path or "test_" in Path(source_path).name:
        return NEGATIVE_CONTROL_CLASSIFICATION
    if source_path.endswith(".md"):
        return DOCUMENTATION_CLASSIFICATION
    if "report" in source_path or "ledger" in source_path:
        return REPORT_CLASSIFICATION
    lowered_text = source.text.lower()
    safe_terms = ("blocked", "forbidden", "absent", "not run", "not created", "disabled", "no broker", "no credential")
    if any(term in lowered_text for term in safe_terms):
        return DOCUMENTATION_CLASSIFICATION
    return ACTIVE_RUNTIME_CLASSIFICATION


def _context_type_for_path(path: Path) -> str:
    normalized = str(path).replace("\\", "/").lower()
    if path.suffix.lower() == ".md":
        return "documentation"
    if "/tests/" in normalized or path.name.startswith("test_"):
        return "negative_control_fixture"
    if "report" in path.name.lower() or "ledger" in path.name.lower():
        return "report_statement"
    return "source"
