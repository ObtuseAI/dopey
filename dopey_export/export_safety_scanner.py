"""Safety and forbidden-content scanner for DOPEY export artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .artifact_selector import resolve_repo_path
from .export_manifest import canonical_export_hash
from .export_models import (
    FORBIDDEN_ACTIVE_EXPORT_TOKENS,
    ExportArtifact,
    ExportSafetyFinding,
    ExportSafetyScanResult,
)


SECRET_PREFIX_PATTERN = re.compile(r"\b(?:sk-proj-[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{16,})")
CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"[A-Za-z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)\s*=\s*['\"]?[A-Za-z0-9_./+=-]{12,}"
)
CREDENTIAL_ASSIGNMENT_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
ACTIVE_DECISION_MARKERS = ("decision", "tier", "status", "action")
ENV_ASSIGNMENT_PATTERN = re.compile(r"^\s*[A-Za-z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)\s*=", re.MULTILINE)
STREAM_SCAN_THRESHOLD_BYTES = 8 * 1024 * 1024
DOCUMENTATION_FIELD_HINTS = {
    "forbidden",
    "blocked",
    "allowed",
    "limitations",
    "safety",
    "known_gaps",
    "notes",
    "term_id",
    "pattern",
    "classification",
}


def _finding(finding_id: str, severity: str, artifact_path: str, reason: str, token: str, field_path: str) -> ExportSafetyFinding:
    return ExportSafetyFinding(
        finding_id=finding_id,
        severity=severity,
        artifact_path=artifact_path,
        reason=reason,
        token=token,
        field_path=field_path,
    )


def _is_documentation_path(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".md", ".txt"}


def _allowed_documentation_field(field_path: str) -> bool:
    lowered = field_path.lower()
    return any(hint in lowered for hint in DOCUMENTATION_FIELD_HINTS)


def _walk_json(node, path: str, artifact_path: str, findings: list[ExportSafetyFinding]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            if isinstance(value, str) and value in FORBIDDEN_ACTIVE_EXPORT_TOKENS:
                if not _allowed_documentation_field(child_path):
                    findings.append(_finding(
                        finding_id=f"forbidden-live-{len(findings)}",
                        severity="safety_error",
                        artifact_path=artifact_path,
                        reason="active forbidden live decision token",
                        token=value,
                        field_path=child_path,
                    ))
            else:
                _walk_json(value, child_path, artifact_path, findings)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_json(item, f"{path}[{index}]", artifact_path, findings)


def _credential_like_tokens(text: str) -> tuple[str, ...]:
    """Find credential-shaped tokens without regex-scanning every byte as a potential identifier.

    Large JSONL audit records can be tens of megabytes on one physical line.
    The former expression began with an unbounded identifier wildcard, making
    a no-match scan effectively quadratic. Fixed-marker search is linear and
    the anchored expressions retain the same accepted token forms.
    """
    tokens: list[str] = []
    assignment_spans: list[tuple[int, int]] = []
    for marker in CREDENTIAL_ASSIGNMENT_MARKERS:
        marker_offset = 0
        while True:
            marker_offset = text.find(marker, marker_offset)
            if marker_offset < 0:
                break
            identifier_start = marker_offset
            while identifier_start > 0 and (text[identifier_start - 1].isalnum() or text[identifier_start - 1] == "_"):
                identifier_start -= 1
            match = CREDENTIAL_ASSIGNMENT_PATTERN.match(text, identifier_start)
            if match is not None:
                tokens.append(match.group(0)[:24])
                assignment_spans.append(match.span())
            marker_offset += len(marker)

    secret_offset = 0
    while True:
        secret_offset = text.find("sk-", secret_offset)
        if secret_offset < 0:
            break
        match = SECRET_PREFIX_PATTERN.match(text, secret_offset)
        covered_by_assignment = any(start <= secret_offset < end for start, end in assignment_spans)
        if match is not None and not covered_by_assignment:
            tokens.append(match.group(0)[:24])
        secret_offset += 3
    return tuple(tokens)


def _active_decision_tokens(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    tokens: list[str] = []
    for token in FORBIDDEN_ACTIVE_EXPORT_TOKENS:
        lowered_token = token.lower()
        token_offset = 0
        while True:
            token_offset = lowered.find(lowered_token, token_offset)
            if token_offset < 0:
                break
            cursor = token_offset - 1
            if cursor >= 0 and text[cursor] in {'"', "'"}:
                cursor -= 1
            while cursor >= 0 and text[cursor].isspace():
                cursor -= 1
            if cursor < 0 or text[cursor] not in {":", "="}:
                token_offset += len(lowered_token)
                continue
            cursor -= 1
            while cursor >= 0 and text[cursor].isspace():
                cursor -= 1
            for marker in ACTIVE_DECISION_MARKERS:
                marker_start = cursor - len(marker) + 1
                if marker_start < 0 or lowered[marker_start : cursor + 1] != marker:
                    continue
                before_is_word = marker_start > 0 and (
                    lowered[marker_start - 1].isalnum() or lowered[marker_start - 1] == "_"
                )
                if not before_is_word:
                    tokens.append(text[token_offset : token_offset + len(lowered_token)])
                break
            token_offset += len(lowered_token)
    return tuple(tokens)


def _json_forbidden_fields(text: str) -> tuple[tuple[str, str], ...]:
    lowered = text.lower()
    matches: list[tuple[str, str]] = []
    for token in FORBIDDEN_ACTIVE_EXPORT_TOKENS:
        token_offset = 0
        lowered_token = token.lower()
        while True:
            token_offset = lowered.find(lowered_token, token_offset)
            if token_offset < 0:
                break
            token_end = token_offset + len(lowered_token)
            cursor = token_offset - 1
            if cursor < 0 or text[cursor] != '"' or token_end >= len(text) or text[token_end] != '"':
                token_offset = token_end
                continue
            cursor -= 1
            while cursor >= 0 and text[cursor].isspace():
                cursor -= 1
            if cursor < 0 or text[cursor] != ":":
                token_offset = token_end
                continue
            cursor -= 1
            while cursor >= 0 and text[cursor].isspace():
                cursor -= 1
            if cursor < 0 or text[cursor] != '"':
                token_offset = token_end
                continue
            field_end = cursor
            field_start = text.rfind('"', 0, field_end)
            if field_start >= 0 and field_start + 1 < field_end:
                matches.append((text[field_start + 1 : field_end], text[token_offset:token_end]))
            token_offset = token_end
    return tuple(matches)


def scan_text_for_sensitive_content(path: Path, text: str) -> list[ExportSafetyFinding]:
    findings: list[ExportSafetyFinding] = []
    normalized_path = str(path).replace("\\", "/").lower()
    if normalized_path.endswith(".env") or "/.env" in normalized_path:
        findings.append(_finding("env-file-export", "safety_error", str(path), "env file export attempt", ".env", "path"))
    for token in _credential_like_tokens(text):
        findings.append(_finding(
            finding_id=f"credential-like-{len(findings)}",
            severity="safety_error",
            artifact_path=str(path),
            reason="credential or API-key-like string detected",
            token=token,
            field_path="text",
        ))
    if ENV_ASSIGNMENT_PATTERN.search(text):
        findings.append(_finding(
            finding_id=f"env-dump-{len(findings)}",
            severity="safety_error",
            artifact_path=str(path),
            reason="environment variable dump detected",
            token="env_assignment",
            field_path="text",
        ))
    if not _is_documentation_path(path):
        for token in _active_decision_tokens(text):
            findings.append(_finding(
                finding_id=f"active-text-live-{len(findings)}",
                severity="safety_error",
                artifact_path=str(path),
                reason="active forbidden live decision text detected",
                token=token,
                field_path="text",
            ))
    return findings


def _scan_streamed_line(path: Path, line: str, findings: list[ExportSafetyFinding]) -> None:
    for token in _credential_like_tokens(line):
        findings.append(_finding(
            finding_id=f"credential-like-{len(findings)}",
            severity="safety_error",
            artifact_path=str(path),
            reason="credential or API-key-like string detected",
            token=token,
            field_path="text",
        ))
    if ENV_ASSIGNMENT_PATTERN.match(line):
        findings.append(_finding(
            finding_id=f"env-dump-{len(findings)}",
            severity="safety_error",
            artifact_path=str(path),
            reason="environment variable dump detected",
            token="env_assignment",
            field_path="text",
        ))
    if _is_documentation_path(path):
        return
    for token in _active_decision_tokens(line):
        findings.append(_finding(
            finding_id=f"active-text-live-{len(findings)}",
            severity="safety_error",
            artifact_path=str(path),
            reason="active forbidden live decision text detected",
            token=token,
            field_path="text",
        ))
    for field_name, token in _json_forbidden_fields(line):
        if _allowed_documentation_field(field_name):
            continue
        findings.append(_finding(
            finding_id=f"forbidden-live-{len(findings)}",
            severity="safety_error",
            artifact_path=str(path),
            reason="active forbidden live decision token",
            token=token,
            field_path=field_name,
        ))


def _scan_large_text_stream(path: Path) -> list[ExportSafetyFinding]:
    findings: list[ExportSafetyFinding] = []
    normalized_path = str(path).replace("\\", "/").lower()
    if normalized_path.endswith(".env") or "/.env" in normalized_path:
        findings.append(_finding("env-file-export", "safety_error", str(path), "env file export attempt", ".env", "path"))
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            _scan_streamed_line(path, line, findings)
    return findings


def scan_artifact_path(path: Path | str) -> list[ExportSafetyFinding]:
    target = Path(path)
    if target.stat().st_size > STREAM_SCAN_THRESHOLD_BYTES:
        return _scan_large_text_stream(target)
    text = target.read_text(encoding="utf-8", errors="replace")
    findings = scan_text_for_sensitive_content(target, text)
    suffix = target.suffix.lower()
    if suffix == ".json":
        try:
            parsed = json.loads(text)
            _walk_json(parsed, target.name, str(target), findings)
        except json.JSONDecodeError:
            pass
    if suffix == ".jsonl":
        for index, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
                _walk_json(parsed, f"{target.name}[{index}]", str(target), findings)
            except json.JSONDecodeError:
                continue
    return findings


def scan_export_artifacts(bundle_id: str, artifacts: list[ExportArtifact]) -> ExportSafetyScanResult:
    findings: list[ExportSafetyFinding] = []
    for artifact in artifacts:
        source = resolve_repo_path(artifact.source_path)
        findings.extend(scan_artifact_path(source))
    active_forbidden = sum(1 for finding in findings if finding.reason == "active forbidden live decision token" or "forbidden live decision" in finding.reason)
    credential_findings = sum(1 for finding in findings if "credential" in finding.reason or "API-key" in finding.reason)
    env_findings = sum(1 for finding in findings if "env" in finding.reason.lower())
    blocked = bool(findings)
    seed = {
        "scan_id": f"export-safety-scan-{bundle_id}",
        "bundle_id": bundle_id,
        "artifacts_scanned": len(artifacts),
        "findings": [finding.to_dict() for finding in findings],
        "active_forbidden_live_decisions": active_forbidden,
        "credential_findings": credential_findings,
        "env_file_findings": env_findings,
        "verification_blocked": blocked,
        "scan_status": "fail_safety" if blocked else "pass",
    }
    return ExportSafetyScanResult(
        scan_id=seed["scan_id"],
        bundle_id=bundle_id,
        artifacts_scanned=len(artifacts),
        findings=findings,
        active_forbidden_live_decisions=active_forbidden,
        credential_findings=credential_findings,
        env_file_findings=env_findings,
        verification_blocked=blocked,
        scan_status=seed["scan_status"],
        reproducibility_hash=canonical_export_hash(seed),
    )
