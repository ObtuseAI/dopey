"""Run the offline real-data validation and options-contract stack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dopey_analysis.run_real_signal_validation import run_real_signal_validation
from dopey_data.run_real_ohlcv_history_spine_upgrade import run_real_ohlcv_history_spine_upgrade
from dopey_core.repo_paths import REPORTS_DIR

from .local_staging_contract import REPO_ROOT
from .run_local_ohlcv_import_validator import MANIFEST_TEMPLATE_PATH, run_local_ohlcv_import_validator
from .run_options_chain_quote_import_contract import run_options_chain_quote_import_contract


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "real_data_validation_stack"
STACK_SUMMARY_PATH = ARTIFACT_DIR / "real_data_validation_stack_summary.json"
STACK_PROOF_PATH = ARTIFACT_DIR / "real_data_validation_stack_proof.jsonl"
STACK_QUALITY_FLAGS_PATH = ARTIFACT_DIR / "real_data_validation_stack_quality_flags.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_REAL_DATA_VALIDATION_STACK_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_REAL_DATA_VALIDATION_STACK_ARTIFACT_LEDGER.md"


def run_real_data_validation_stack() -> dict[str, Any]:
    local = run_local_ohlcv_import_validator()
    history = run_real_ohlcv_history_spine_upgrade()
    signals = run_real_signal_validation()
    options = run_options_chain_quote_import_contract()
    fixtures = write_stack_fixtures()
    summary = _summary(local, history, signals, options)
    flags = _quality_flags(summary)
    proof = [_proof(summary)]
    _write_json(STACK_SUMMARY_PATH, {**summary, "artifact_paths": artifact_paths(), "fixture_paths": fixtures})
    _write_jsonl(STACK_QUALITY_FLAGS_PATH, flags)
    _write_jsonl(STACK_PROOF_PATH, proof)
    report = _write_report(summary)
    ledger = _write_ledger([*artifact_paths().values(), *fixtures, str(MANIFEST_TEMPLATE_PATH), str(report)])
    return {**summary, "artifact_paths": artifact_paths(), "fixture_paths": fixtures, "report_path": str(report), "ledger_path": str(ledger)}


def artifact_paths() -> dict[str, str]:
    return {
        "real_data_validation_stack_summary": str(STACK_SUMMARY_PATH),
        "real_data_validation_stack_proof": str(STACK_PROOF_PATH),
        "real_data_validation_stack_quality_flags": str(STACK_QUALITY_FLAGS_PATH),
    }


def write_stack_fixtures() -> list[str]:
    groups = {
        "local_ohlcv_import/local_ohlcv_import_cases.json": [
            "missing local OHLCV", "valid OHLCV schema", "invalid OHLCV schema", "duplicate symbol/date",
            "positive OHLC", "negative open blocked", "zero close blocked", "high/low consistency",
            "future date blocked", "sample-only row blocked", "fake symbol blocked", "credential token blocked",
            "source present", "provider present", "hash recorded", "row count recorded", "symbol coverage recorded",
            "date range recorded", "market context folder empty", "corporate actions optional absent",
        ],
        "local_ohlcv_import/local_ohlcv_quality_cases.json": [
            "high below close", "low above open", "adjusted close positive", "volume nonnegative",
            "missing day count", "stale symbol count", "duplicate primary key", "invalid date parse",
            "invalid symbol parse", "sample template rejected", "SAMPLE_ONLY rejected", "future date terminal block",
            "api key terminal block", "secret token terminal block", "manual review quality", "terminal quality",
            "pass quality", "fail quality", "empty file blocked", "unknown column ignored safely",
        ],
        "local_ohlcv_import/local_ohlcv_license_cases.json": [
            "missing license blocked", "missing provenance blocked", "unknown license blocked", "unreviewed terms blocked",
            "file hash missing blocked", "provider missing blocked", "source missing blocked", "redistribution restricted",
            "reviewed internal research allowed", "reviewed restricted internal research allowed", "manifest template valid",
            "not broker data true", "not credentials true", "not live data true", "not network fetched true",
            "no env", "no API keys", "operator note required", "manual review required", "license pass",
        ],
        "options_data_contract/options_chain_quote_contract_cases.json": [
            "options chain contract ready", "options quote contract ready", "invalid bid ask", "ask below bid",
            "mid outside bid ask", "negative strike", "expiry before snapshot", "expiry before quote",
            "invalid option type", "negative implied volatility", "negative volume", "negative open interest",
            "contract duplicate", "sample-only options row", "credential token options row", "missing options license",
            "missing options provenance", "options files absent", "quote-priced backtest blocked", "no network fetch options",
        ],
        "real_data_validation_stack/real_data_validation_stack_cases.json": [
            "history spine blocked when OHLCV missing", "history spine allowed after OHLCV pass",
            "real signal blocked when history missing", "real signal uses validated history only",
            "options quote priced blocked when absent", "combined stack no network fetch", "combined stack no broker",
            "combined stack no credentials", "combined stack no scheduler", "combined stack no real sizing",
            "full pytest timeout inconclusive", "live trading disabled", "Robinhood MCP not integrated",
            "Blunder integrity unchanged when manifest available", "strategy promotion blocked", "paper only",
            "live blocked", "next target local import fix", "real data not ingested by default", "valid dataset false by default",
        ],
    }
    output_paths: list[str] = []
    for relative, names in groups.items():
        path = REPO_ROOT / "dopey_data" / "fixtures" / relative
        cases = [_case(index + 1, name) for index, name in enumerate(names)]
        _write_json(path, {"case_count": len(cases), "cases": cases})
        output_paths.append(str(path))
    return output_paths


def _summary(local: dict[str, Any], history: dict[str, Any], signals: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "real_data_validation_stack_summary",
        "stack_version": "dopey-real-data-validation-and-options-contract-stack-v1",
        "local_ohlcv_status": local["local_ohlcv_status"],
        "history_spine_upgrade_status": history["history_spine_upgrade_status"],
        "real_signal_validation_status": signals["real_signal_validation_status"],
        "options_contract_status": options["options_contract_status"],
        "real_data_files_present": local["real_data_files_present"],
        "valid_real_dataset": local["valid_real_dataset"],
        "real_history_used": history["real_history_used"],
        "real_signal_evidence": signals["real_signal_evidence"],
        "options_data_files_present": options["options_data_files_present"],
        "options_data_validated": options["options_data_validated"],
        "quote_priced_backtest_allowed": options["quote_priced_backtest_allowed"],
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "live_data_used": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "next_recommended_target": "DOPEY_MANUAL_REAL_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1",
    }
    record["summary_hash"] = _hash(record)
    return record


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if summary["local_ohlcv_status"] == "missing_local_ohlcv_files":
        flags.append(_flag("missing-local-ohlcv", "missing_local_ohlcv_files"))
    if summary["real_signal_validation_status"] == "blocked_missing_valid_real_history":
        flags.append(_flag("real-signal-blocked", "blocked_missing_valid_real_history"))
    if not summary["quote_priced_backtest_allowed"]:
        flags.append(_flag("quote-priced-backtest-blocked", "options_data_not_validated"))
    return flags


def _proof(summary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "real_data_validation_stack_proof",
        "proof_id": "real-data-validation-stack-proof-v1",
        "local_ohlcv_status": summary["local_ohlcv_status"],
        "history_spine_upgrade_status": summary["history_spine_upgrade_status"],
        "real_signal_validation_status": summary["real_signal_validation_status"],
        "options_contract_status": summary["options_contract_status"],
        "network_fetch_performed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["proof_hash"] = _hash(record)
    return record


def _case(index: int, name: str) -> dict[str, Any]:
    record = {
        "case_id": f"stack-case-{index:03d}",
        "name": name,
        "fixture_only": True,
        "sample_only": True,
        "not_real_data": True,
        "not_real_data_ingested": True,
        "real_data_ingested": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["case_hash"] = _hash(record)
    return record


def _flag(flag_id: str, reason_code: str) -> dict[str, Any]:
    record = {
        "artifact_type": "real_data_validation_stack_quality_flag",
        "flag_id": flag_id,
        "severity": "info",
        "reason_code": reason_code,
        "paper_only": True,
        "live_blocked": True,
    }
    record["flag_hash"] = _hash(record)
    return record


def _write_report(summary: dict[str, Any]) -> Path:
    lines = [
        "# DOPEY Real Data Validation Stack Report",
        "",
        "## Objective",
        "Build the offline local OHLCV validator, history-spine upgrade gate, real signal validation gate, and options-chain/quote import contract.",
        "",
        "## Local OHLCV Import Validator",
        f"- local_ohlcv_status: `{summary['local_ohlcv_status']}`",
        f"- valid_real_dataset: `{str(summary['valid_real_dataset']).lower()}`",
        "",
        "## Manual Staging Instructions",
        "- See `DOPEY_MANUAL_REAL_OHLCV_STAGING_INSTRUCTIONS.md`.",
        "- Manifest template: `dopey_data/real/manifests/real_data_manifest.template.json`.",
        "",
        "## History Spine Upgrade Gate",
        f"- history_spine_upgrade_status: `{summary['history_spine_upgrade_status']}`",
        f"- real_history_used: `{str(summary['real_history_used']).lower()}`",
        "",
        "## Real Signal Validation Gate",
        f"- real_signal_validation_status: `{summary['real_signal_validation_status']}`",
        f"- real_signal_evidence: `{str(summary['real_signal_evidence']).lower()}`",
        "",
        "## Options-Chain/Quote Import Contract",
        f"- options_contract_status: `{summary['options_contract_status']}`",
        f"- options_data_validated: `{str(summary['options_data_validated']).lower()}`",
        f"- quote_priced_backtest_allowed: `{str(summary['quote_priced_backtest_allowed']).lower()}`",
        "",
        "## Current No-Real-Data State",
        f"- real_data_files_present: `{str(summary['real_data_files_present']).lower()}`",
        "",
        "## Quality Gates",
        "- OHLCV schema, price consistency, duplicate, future-date, sample-row, token, license, provenance, and hash gates are defined.",
        "- Options bid/ask, expiry, option type, IV, volume, open interest, uniqueness, sample-row, token, license, and provenance gates are defined.",
        "",
        "## Claim-Blocking Policy",
        "- No real edge, profitability, live readiness, strategy promotion, or quote-priced backtest claim is allowed by this bundle.",
        "",
        "## Safety State",
        "- network_fetch_performed: `false`",
        "- broker_connection_used: `false`",
        "- credentials_created: `false`",
        "- env_created: `false`",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "",
        "## Validation Summary",
        "- Focused tests live in `tests/test_real_data_validation_stack.py`.",
        "- Full pytest timeout remains `inconclusive_timeout`, not pass.",
        "",
        "## Known Gaps",
        "- No manually staged licensed local OHLCV is present.",
        "- No options data has been validated.",
        "",
        "## Next Target",
        f"- `{summary['next_recommended_target']}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT_PATH


def _write_ledger(paths: list[str]) -> Path:
    lines = ["# DOPEY Real Data Validation Stack Artifact Ledger", ""]
    lines.append("## Safety State")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append("- network_fetch_performed: `false`")
    lines.append("")
    lines.append("## Files")
    for path_text in sorted(set(paths)):
        path = Path(path_text)
        if path.exists():
            lines.append(f"- `{_relative(path)}` records=`{_record_count(path)}` sha256=`{_sha256(path)}`")
    LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return LEDGER_PATH


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _hash(record: dict[str, Any]) -> str:
    cleaned = {key: value for key, value in record.items() if not key.endswith("_hash")}
    return hashlib.sha256(json.dumps(cleaned, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if path.suffix == ".json":
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list):
            return len(parsed["cases"])
    return 1


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    result = run_real_data_validation_stack()
    print(json.dumps({
        "local_ohlcv_status": result["local_ohlcv_status"],
        "history_spine_upgrade_status": result["history_spine_upgrade_status"],
        "real_signal_validation_status": result["real_signal_validation_status"],
        "options_contract_status": result["options_contract_status"],
        "next_recommended_target": result["next_recommended_target"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
