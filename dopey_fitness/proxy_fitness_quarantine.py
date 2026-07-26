"""Detect and quarantine old proxy/theater fitness references."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fitness_models import stable_fitness_hash


PROXY_TOKENS: tuple[str, ...] = (
    "combined_score",
    "proxy_score",
    "oos_edge",
    "expected_outcome",
    "REGIME_FAMILY_HINTS",
    "paper_shadow_candidate",
    "fitness_score",
    "champion",
    "promotion_candidate",
    "accepted_candidate",
    "strategy_promoted",
    "profitability_claim",
    "alpha_claim",
    "live_ready",
)
BLOCKING_CONTEXT_TOKENS: tuple[str, ...] = (
    "blocked",
    "false",
    "diagnostic",
    "fixture",
    "not_real",
    "no_promotion",
    "quarantine",
    "hold",
    "paper_only",
    "not_",
)
ACTIVE_PROMOTION_PATTERNS: tuple[str, ...] = (
    "strategy_promoted=true",
    "\"strategy_promoted\": true",
    "'strategy_promoted': true",
    "promotion_allowed=true",
    "\"promotion_allowed\": true",
    "'promotion_allowed': true",
    "profitability_claim=true",
    "alpha_claim=true",
    "live_ready=true",
)


def scan_proxy_fitness_references(repo_root: Path | str) -> list[dict[str, Any]]:
    root = Path(repo_root)
    findings: list[dict[str, Any]] = []
    for path in _scan_paths(root):
        if not path.exists() or path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            tokens = [token for token in PROXY_TOKENS if token in line]
            if not tokens:
                continue
            findings.append(_finding(root, path, line_number, line, tokens))
    return findings


def classify_proxy_reference(path: str, line_text: str, matched_tokens: list[str]) -> tuple[str, str, bool, bool]:
    normalized_path = path.replace("\\", "/").lower()
    normalized_line = line_text.lower()
    if normalized_path.startswith("dopey_fitness/"):
        return "allowed_blocked_reference", "fitness_replacement_self_reference_not_promotion_input", False, False
    if "/dopey_data/fixtures/" in normalized_path or normalized_path.startswith("dopey_data/fixtures/") or "/tests/" in normalized_path or normalized_path.startswith("tests/"):
        return "allowed_fixture_case", "fixture_or_test_reference_not_promotion_input", False, False
    if normalized_path.endswith(".md") or "/artifacts/" in normalized_path:
        return "allowed_historical_doc", "historical_or_artifact_reference_not_promotion_input", False, False
    if any(token in normalized_line for token in BLOCKING_CONTEXT_TOKENS):
        return "allowed_blocked_reference", "blocked_reference_not_promotion_input", False, False
    if any(pattern in normalized_line for pattern in ACTIVE_PROMOTION_PATTERNS):
        return "blocked_active_promotion_input", "active_proxy_promotion_terminal_block", True, False
    if "champion" in matched_tokens and ("registry" in normalized_path or "report" in normalized_path):
        return "allowed_blocked_reference", "champion_reporting_reference_not_fitness_promotion_input", False, False
    return "manual_review_required", "proxy_fitness_reference_requires_review", False, True


def quarantine_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "blocked_active_proxy_promotion_count": sum(1 for finding in findings if finding["classification"] == "blocked_active_promotion_input"),
        "manual_review_proxy_reference_count": sum(1 for finding in findings if finding["classification"] == "manual_review_required"),
        "finding_count": len(findings),
    }


def _scan_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for folder_name in [
        "dopey_core",
        "dopey_strategy_lab",
        "dopey_tournament",
        "dopey_walk_forward",
        "dopey_reporting",
        "dopey_audit",
        "dopey_export",
        "dopey_export_review",
        "dopey_stats",
        "dopey_backtest",
        "dopey_fitness",
        "dopey_data",
        "tests",
    ]:
        folder = root / folder_name
        if folder.exists():
            candidates.extend(path for path in folder.rglob("*") if path.suffix.lower() in {".py", ".json", ".jsonl", ".md"})
    for path in root.glob("DOPEY_*.md"):
        candidates.append(path)
    return sorted(set(candidates))


def _finding(root: Path, path: Path, line_number: int, line: str, tokens: list[str]) -> dict[str, Any]:
    relative_path = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    classification, reason_code, terminal_block, manual_review = classify_proxy_reference(relative_path, line, tokens)
    record = {
        "artifact_type": "proxy_fitness_quarantine_finding",
        "source_path": relative_path,
        "line_number": line_number,
        "matched_tokens": sorted(tokens),
        "classification": classification,
        "reason_code": reason_code,
        "terminal_block": terminal_block,
        "manual_review_required": manual_review,
        "not_real_fitness_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["line_excerpt"] = line.strip()[:240]
    record["finding_hash"] = stable_fitness_hash(record)
    return record


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
