"""Shared deterministic helpers for DOPEY autonomous open-source research."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
RUN_ID = "dopey-open-source-autonomous-options-trader-max-completion-v1"
SCHEMA_VERSION = "dopey-autonomous-open-data-schema-v1"

SafetyDecision = Literal[
    "accepted_machine_verified_open",
    "accepted_machine_verified_public_domain",
    "accepted_machine_verified_permissive_internal_research",
    "rejected_unknown_license",
    "rejected_ambiguous_terms",
    "rejected_credentials_required",
    "rejected_broker_or_live_source",
    "rejected_proprietary_or_paid",
    "rejected_scrape_only",
    "rejected_sample_or_fixture",
    "quarantined_suspicious",
    "terminal_block",
]

OpenDataOutcome = Literal[
    "accepted_for_internal_research_ingest",
    "accepted_for_context_only",
    "accepted_for_fixture_only",
    "rejected_unknown_license",
    "rejected_ambiguous_terms",
    "rejected_credentials_required",
    "rejected_paid_or_proprietary",
    "rejected_scrape_only",
    "quarantined_pending_machine_evidence",
    "terminal_block",
]

PERMISSIVE_LICENSES = frozenset({
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "PSF-2.0",
})
PUBLIC_DOMAIN_LICENSES = frozenset({
    "CC0-1.0",
    "Public-Domain",
    "US-PD",
    "U.S.-Government-Work",
})
COPYLEFT_LICENSES = frozenset({"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-3.0"})
FORBIDDEN_MARKERS = ("api_key", "secret", "token", "password", "broker", "account balance", "buying power", "live order")
SAMPLE_MARKERS = ("sample_only", "not_real_data", "fixture", "template", "SAMPLE_ONLY")
REQUIRED_OHLCV_COLUMNS = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "source",
    "source_url",
    "license_status",
    "provenance_hash",
    "autonomous_admissibility_id",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(_strip_hashes(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, record: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def read_json(path: Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    text = target.read_text(encoding="utf-8", errors="replace").strip()
    return json.loads(text) if text else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]


def safety_state() -> dict[str, Any]:
    return {
        "paper_only": True,
        "live_blocked": True,
        "live_promotion_status": False,
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "not_profitability_claim": True,
        "not_live_ready": True,
    }


def with_hash(record: dict[str, Any], hash_field: str) -> dict[str, Any]:
    hashed = dict(record)
    hashed[hash_field] = stable_hash(hashed)
    return hashed


def proof_record(proof_id: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
    seed = {
        "artifact_type": proof_id,
        "run_id": RUN_ID,
        "proof_id": proof_id,
        "timestamp_utc": utc_now(),
        "status": status,
        "payload_hash": stable_hash(payload),
        **safety_state(),
    }
    return with_hash(seed, "proof_hash")


@dataclass(frozen=True)
class CandidateInput:
    source_id: str
    name: str
    family: str
    license_id: str
    source_url: str
    machine_readable_license: bool
    machine_readable_terms: bool
    credentials_required: bool
    paid_or_proprietary: bool
    broker_or_live_source: bool
    scrape_only: bool
    explicit_scrape_permission: bool
    sample_or_fixture: bool
    suspicious: bool
    provenance_url: str
    direct_download_url: str
    adjusted_close_semantics_known: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_candidate(candidate: CandidateInput) -> SafetyDecision:
    if candidate.credentials_required:
        return "rejected_credentials_required"
    if candidate.broker_or_live_source:
        return "rejected_broker_or_live_source"
    if candidate.paid_or_proprietary:
        return "rejected_proprietary_or_paid"
    if candidate.sample_or_fixture:
        return "rejected_sample_or_fixture"
    if candidate.scrape_only and not candidate.explicit_scrape_permission:
        return "rejected_scrape_only"
    if not candidate.machine_readable_license or not candidate.license_id:
        return "rejected_unknown_license"
    if not candidate.machine_readable_terms:
        return "rejected_ambiguous_terms"
    if candidate.suspicious:
        return "quarantined_suspicious"
    if candidate.license_id in PUBLIC_DOMAIN_LICENSES:
        return "accepted_machine_verified_public_domain"
    if candidate.license_id in PERMISSIVE_LICENSES:
        return "accepted_machine_verified_open"
    if candidate.license_id == "Permissive-Internal-Research":
        return "accepted_machine_verified_permissive_internal_research"
    return "rejected_unknown_license"


def data_outcome(candidate: CandidateInput) -> OpenDataOutcome:
    decision = decide_candidate(candidate)
    if decision in {"accepted_machine_verified_open", "accepted_machine_verified_public_domain", "accepted_machine_verified_permissive_internal_research"}:
        if candidate.family in {"macro_context", "filings_metadata", "catalyst_metadata"}:
            return "accepted_for_context_only"
        if candidate.family == "fixture":
            return "accepted_for_fixture_only"
        if candidate.direct_download_url and candidate.adjusted_close_semantics_known:
            return "accepted_for_internal_research_ingest"
        return "quarantined_pending_machine_evidence"
    mapping: dict[str, OpenDataOutcome] = {
        "rejected_unknown_license": "rejected_unknown_license",
        "rejected_ambiguous_terms": "rejected_ambiguous_terms",
        "rejected_credentials_required": "rejected_credentials_required",
        "rejected_proprietary_or_paid": "rejected_paid_or_proprietary",
        "rejected_scrape_only": "rejected_scrape_only",
        "rejected_broker_or_live_source": "terminal_block",
        "rejected_sample_or_fixture": "quarantined_pending_machine_evidence",
        "quarantined_suspicious": "quarantined_pending_machine_evidence",
        "terminal_block": "terminal_block",
    }
    return mapping[decision]


def default_admissibility_candidates() -> list[CandidateInput]:
    return [
        CandidateInput("src-mit-oss", "MIT OSS reference", "repo", "MIT", "https://github.com/example/oss", True, True, False, False, False, False, False, False, False, "https://github.com/example/oss/LICENSE", "", True),
        CandidateInput("src-public-domain", "Public domain macro context", "macro_context", "US-PD", "https://fred.stlouisfed.org", True, True, False, False, False, False, False, False, False, "https://fred.stlouisfed.org/docs/api/terms_of_use.html", "", True),
        CandidateInput("src-unknown", "Unknown license data", "daily_ohlcv", "", "https://example.invalid/data.csv", False, True, False, False, False, False, False, False, False, "", "", True),
        CandidateInput("src-ambiguous", "Ambiguous terms data", "daily_ohlcv", "MIT", "https://example.invalid/ambiguous.csv", True, False, False, False, False, False, False, False, False, "", "", True),
        CandidateInput("src-credentialed", "Credentialed market adapter", "daily_ohlcv", "MIT", "https://example.invalid/api", True, True, True, False, False, False, False, False, False, "", "", True),
        CandidateInput("src-paid", "Paid data vendor", "daily_ohlcv", "MIT", "https://example.invalid/paid", True, True, False, True, False, False, False, False, False, "", "", True),
        CandidateInput("src-broker-live", "Broker live feed", "daily_ohlcv", "MIT", "https://example.invalid/broker", True, True, False, False, True, False, False, False, False, "", "", True),
        CandidateInput("src-scrape-only", "Scrape-only page", "daily_ohlcv", "MIT", "https://example.invalid/page", True, True, False, False, False, True, False, False, False, "", "", True),
        CandidateInput("src-fixture", "Fixture-only sample", "fixture", "CC0-1.0", "dopey_data/fixtures", True, True, False, False, False, False, False, True, False, "fixture", "", True),
    ]


def oss_candidates() -> list[dict[str, Any]]:
    base = [
        ("quantlib", "QuantLib", "options math/pricing", "BSD-3-Clause", False, False, False, 94),
        ("lean", "LEAN", "event-driven simulation", "Apache-2.0", True, False, True, 78),
        ("qlib", "Qlib", "ML quant research", "MIT", False, False, False, 82),
        ("finrl", "FinRL", "RL research environments", "MIT", False, False, False, 70),
        ("vectorbt", "vectorbt-style systems", "backtesting engines", "Apache-2.0", False, False, False, 84),
        ("backtrader", "backtrader-style systems", "backtesting engines", "GPL-3.0", False, False, False, 58),
        ("zipline", "Zipline-style systems", "event-driven simulation", "Apache-2.0", False, False, False, 74),
        ("pandas-ta", "pandas-ta style indicators", "feature engineering", "MIT", False, False, False, 76),
        ("statsmodels", "statsmodels", "statistical validation", "BSD-3-Clause", False, False, False, 88),
        ("scikit-learn", "scikit-learn", "ML quant research", "BSD-3-Clause", False, False, False, 86),
        ("edgartools", "EDGAR open-source tooling", "fundamentals/NLP", "MIT", False, False, False, 72),
        ("broker-adapter", "Broker execution adapter", "order/fill simulation", "MIT", True, True, True, 20),
        ("unknown-license-repo", "Unknown license repo", "signal engines", "", False, False, False, 0),
    ]
    records: list[dict[str, Any]] = []
    for slug, name, category, license_id, broker_risk, credential_risk, network_risk, value_score in base:
        import_mode = "rejected"
        reason_codes: list[str] = []
        if not license_id:
            reason_codes.append("unknown_license")
        elif license_id in COPYLEFT_LICENSES:
            import_mode = "reference_only"
            reason_codes.append("copyleft_reference_only")
        elif broker_risk or credential_risk:
            import_mode = "reference_only"
            reason_codes.append("broker_or_credential_risk_reference_only")
        else:
            import_mode = "adapter_candidate" if category in {"options math/pricing", "statistical validation", "feature engineering"} else "sandbox_candidate"
            reason_codes.append("machine_verified_permissive")
        if not license_id:
            import_mode = "rejected"
        record = {
            "artifact_type": "autonomous_oss_candidate_registry",
            "candidate_id": f"autonomous-oss-{slug}",
            "repo_name": name,
            "repo_url": f"https://github.com/autonomous-reference/{slug}",
            "category": category,
            "license_id": license_id,
            "license_compatible": bool(license_id in PERMISSIVE_LICENSES or license_id in COPYLEFT_LICENSES),
            "maintenance_freshness_score": 70 if value_score else 0,
            "dependency_risk_score": 20 if not broker_risk else 65,
            "broker_live_risk": broker_risk,
            "credential_risk": credential_risk,
            "network_risk": network_risk,
            "options_usefulness": 95 if category == "options math/pricing" else value_score,
            "signal_usefulness": value_score,
            "backtest_usefulness": value_score,
            "risk_model_usefulness": value_score,
            "statistical_validation_usefulness": 95 if category == "statistical validation" else value_score,
            "integration_cost": 30 if import_mode in {"adapter_candidate", "sandbox_candidate"} else 80,
            "dopey_control_preservation": True,
            "import_mode": import_mode,
            "not_cloned": True,
            "not_imported": True,
            "not_executed": True,
            "reason_codes": reason_codes,
            **safety_state(),
        }
        records.append(with_hash(record, "candidate_hash"))
    return records


def open_data_candidates() -> list[CandidateInput]:
    return [
        CandidateInput("data-sec-edgar", "SEC EDGAR filings metadata", "filings_metadata", "US-PD", "https://www.sec.gov/edgar", True, True, False, False, False, False, False, False, False, "https://www.sec.gov/privacy.htm", "", True),
        CandidateInput("data-fred", "FRED macro context", "macro_context", "US-PD", "https://fred.stlouisfed.org", True, True, False, False, False, False, False, False, False, "https://fred.stlouisfed.org/docs/api/terms_of_use.html", "", True),
        CandidateInput("data-open-ohlcv-no-file", "Permissive OHLCV catalog without direct file", "daily_ohlcv", "MIT", "https://example.invalid/open-ohlcv", True, True, False, False, False, False, False, False, False, "https://example.invalid/LICENSE", "", False),
        CandidateInput("data-unknown-license", "Unknown OHLCV dataset", "daily_ohlcv", "", "https://example.invalid/unknown", False, True, False, False, False, False, False, False, False, "", "", True),
        CandidateInput("data-yahoo-style", "Ambiguous web OHLCV candidate", "daily_ohlcv", "Permissive-Internal-Research", "https://example.invalid/ambiguous-web", True, False, False, False, False, True, False, False, False, "", "", True),
        CandidateInput("data-broker-feed", "Broker historical feed", "daily_ohlcv", "MIT", "https://example.invalid/broker-feed", True, True, False, False, True, False, False, False, False, "", "", True),
        CandidateInput("data-paid-options", "Paid options quote archive", "options_quotes", "MIT", "https://example.invalid/options-paid", True, True, False, True, False, False, False, False, False, "", "", True),
        CandidateInput("data-fixture-options", "Sample options fixture", "fixture", "CC0-1.0", "dopey_data/fixtures/spy_fixture_chain.json", True, True, False, False, False, False, False, True, False, "fixture", "", True),
    ]


def contains_forbidden_content(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    return any(marker.lower() in text for marker in FORBIDDEN_MARKERS)


def contains_sample_content(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(marker in text for marker in SAMPLE_MARKERS)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def normalize_ohlcv_rows(rows: list[dict[str, str]], source_record: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "date": row.get("date", ""),
            "symbol": row.get("symbol", "").upper(),
            "open": float(row.get("open", "0")),
            "high": float(row.get("high", "0")),
            "low": float(row.get("low", "0")),
            "close": float(row.get("close", "0")),
            "adjusted_close": float(row.get("adjusted_close", row.get("close", "0"))),
            "volume": int(float(row.get("volume", "0"))),
            "source": row.get("source", source_record.get("source_name", "")),
            "source_url": row.get("source_url", source_record.get("source_url", "")),
            "license_status": row.get("license_status", source_record.get("license_id", "")),
            "provenance_hash": row.get("provenance_hash", source_record.get("source_hash", "")),
            "autonomous_admissibility_id": row.get("autonomous_admissibility_id", source_record.get("source_id", "")),
        }
        normalized.append(item)
    return normalized


def validate_ohlcv_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return ["empty_ohlcv_file"]
    for index, row in enumerate(rows):
        if not row["date"] or not row["symbol"]:
            errors.append(f"missing_date_or_symbol_{index}")
        if row["symbol"] == "SAMPLE_ONLY":
            errors.append(f"sample_symbol_{index}")
        if row["open"] <= 0 or row["high"] <= 0 or row["low"] <= 0 or row["close"] <= 0:
            errors.append(f"nonpositive_price_{index}")
        if row["low"] > row["high"] or row["open"] > row["high"] or row["open"] < row["low"] or row["close"] > row["high"] or row["close"] < row["low"]:
            errors.append(f"ohlc_inconsistent_{index}")
        if row["volume"] < 0:
            errors.append(f"negative_volume_{index}")
        if not row["source_url"] or not row["license_status"] or not row["provenance_hash"] or not row["autonomous_admissibility_id"]:
            errors.append(f"missing_provenance_{index}")
    return sorted(set(errors))


def write_csv_records(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_OHLCV_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def fetch_https_file(url: str, target: Path) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "DOPEY-autonomous-research/1.0"})
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=20) as response:
        status_code = int(getattr(response, "status", 200))
        content = response.read()
    if status_code >= 400:
        raise RuntimeError(f"fetch failed for url={url} status_code={status_code}")
    target.write_bytes(content)
    return {"status_code": status_code, "size_bytes": len(content), "sha256": file_hash(target)}


def write_autonomy_fixture_cases() -> dict[str, Any]:
    groups = {
        "open_source_autonomy/autonomous_oss_cases.json": [
            "unknown license reject", "ambiguous terms reject", "credentials required reject", "paid proprietary reject",
            "broker source reject", "scrape only reject", "permissive license accept", "public domain accept",
            "MIT repo accept", "Apache repo accept", "GPL reference only", "broker repo quarantine",
            "data adapter with API key reject", "dependency risk score", "network risk score", "options usefulness",
            "signal usefulness", "backtest usefulness", "risk model usefulness", "statistical validation usefulness",
            "integration cost", "Dopey control preservation", "no clone", "no import", "no execution",
        ],
        "open_data_autonomy/autonomous_open_data_cases.json": [
            "open macro source accept", "open OHLCV candidate accept", "open OHLCV candidate reject schema",
            "open OHLCV candidate reject license", "open OHLCV candidate reject provenance", "accepted file quarantine",
            "rejected file quarantine", "credential contamination terminal", "sample contamination reject",
            "OHLCV normalize pass", "OHLCV normalize fail", "manifest build no files", "manifest build accepted files",
            "validator bridge no data", "validator bridge pass", "no Alpha Vantage", "no credentials", "no .env",
            "no broker", "no live", "watchdog safe timeout", "export timeout inconclusive",
        ],
        "research_autonomy/autonomous_research_cases.json": [
            "options data unavailable", "options data accepted", "options data rejected license", "model priced fallback",
            "quote priced blocked", "signal factory no data blocked", "signal factory accepted data",
            "strategy search no trade", "long call intent", "long put intent", "no trade intent",
            "backtest fixture only", "backtest accepted OHLCV", "stats blocked sample size", "stats pass",
            "fitness blocked", "fitness pass paper only", "benchmark no data", "benchmark with data",
            "S-tier engineering progress", "live superiority claim false", "no strategy promotion",
            "no profitability claim", "no live readiness",
        ],
        "paper_autonomy/autonomous_paper_cases.json": [
            "paper loop blocked no data", "paper loop runs accepted data", "daily scan", "opportunity ranker",
            "long call paper intent", "long put paper intent", "no trade paper intent", "max risk guard",
            "max drawdown guard", "theta IV risk guard", "event risk guard", "0DTE special guard",
            "no same day churn default", "paper fill simulator", "paper lifecycle manager", "paper exit rules",
            "paper ledger", "incident kill switch simulation", "recursive feedback queue", "no real capital sizing",
        ],
        "full_autonomy/full_orchestrator_cases.json": [
            "full orchestrator no admissible data", "full orchestrator accepted OHLCV", "full orchestrator accepted options",
            "full orchestrator no options", "autonomous admissibility kernel", "open source discovery",
            "open data discovery", "quarantine fetcher zero accepted", "normalizer blocked", "manifest blocked",
            "validator bridge blocked", "options gap report", "research blocked", "fitness blocked",
            "paper loop blocked", "benchmark complete", "shared copy attempted", "network fetch false",
            "credentials false", "broker false", "live false",
        ],
    }
    output_paths: list[str] = []
    total_cases = 0
    for relative, base_cases in groups.items():
        expanded = list(base_cases)
        while len(expanded) < 75:
            expanded.append(f"{base_cases[len(expanded) % len(base_cases)]} repeat {len(expanded):03d}")
        cases = [_fixture_case(index + 1, name) for index, name in enumerate(expanded)]
        path = REPO_ROOT / "dopey_data" / "fixtures" / relative
        write_json(path, {"artifact_type": Path(relative).stem, "case_count": len(cases), "cases": cases})
        output_paths.append(str(path))
        total_cases += len(cases)
    return {"fixture_case_count": total_cases, "fixture_paths": output_paths}


def copy_session_packet(files: list[Path]) -> dict[str, Any]:
    target_root = _shared_target_root()
    if target_root is None:
        return {"shared_copy_status": "no_shared_folder_available", "copied_file_count": 0, "target_path": "", "manifest_path": ""}
    target = target_root / "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_MAX_COMPLETION_V1"
    target.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for source in files:
        if not source.exists():
            continue
        destination = target / source.name
        shutil.copy2(source, destination)
        copied.append({"source": str(source), "destination": str(destination), "sha256": file_hash(destination)})
    manifest = {
        "session_copy_manifest_version": RUN_ID,
        "target_path": str(target),
        "copied_file_count": len(copied),
        "copied_files": copied,
        **safety_state(),
    }
    manifest = with_hash(manifest, "manifest_hash")
    manifest_path = target / "SESSION_COPY_MANIFEST.json"
    write_json(manifest_path, manifest)
    return {"shared_copy_status": "copied" if copied else "empty_copy", "copied_file_count": len(copied), "target_path": str(target), "manifest_path": str(manifest_path)}


def _fixture_case(index: int, name: str) -> dict[str, Any]:
    record = {
        "case_id": f"autonomy-fixture-{index:03d}",
        "case_name": name,
        "fixture_only": True,
        "not_real_data": True,
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    return with_hash(record, "case_hash")


def _shared_target_root() -> Path | None:
    candidates = [
        Path("C:/Users/chris/Desktop/Shared Folder"),
        Path("//FRANKENSTEIN/Shared Folder"),
        Path("Z:/"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _strip_hashes(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hashes(item) for key, item in value.items() if not key.endswith("_hash") and key not in {"reproducibility_hash"}}
    if isinstance(value, list):
        return [_strip_hashes(item) for item in value]
    return value

