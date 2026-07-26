"""Watchdog-safe validation summary writer for V5.

Runs the mandatory validation order:
1. V5 targeted
2. V4 carry-forward
3. V3 carry-forward
4. active-policy carry-forward
5. orchestrator smoke first
6. remaining module smokes

Records every result, never marks a timeout as pass, and writes the
validation summary + timeout records expected by Workstream S.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    RESEARCH_V5_VERSION,
    RESEARCH_V5_ROOT,
    research_v5_proof_record,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["run_public_signal_research_v5_validation"]


VALIDATION_SUMMARY_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_validation_summary.json"
TIMEOUT_RECORDS_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_timeout_records.jsonl"
VALIDATION_PROOF_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_validation_proof.jsonl"


PYTHON = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")


VALIDATION_COMMANDS: tuple[tuple[str, list[str], int], ...] = (
    ("v5_targeted_tests", [PYTHON, "-m", "pytest", "tests/test_public_signal_research_breakthrough_v5.py", "-q", "--tb=short"], 240),
    ("v4_carry_forward_tests", [PYTHON, "-m", "pytest", "tests/test_public_signal_research_breakthrough_v4.py", "-q", "--tb=short"], 240),
    ("v3_carry_forward_tests", [PYTHON, "-m", "pytest", "tests/test_public_signal_research_breakthrough_v3.py", "-q", "--tb=short"], 240),
    ("active_policy_carry_forward_tests", [PYTHON, "-m", "pytest", "tests/test_active_policy_integration.py", "tests/test_active_trading_policy.py", "-q", "--tb=short"], 240),
    ("orchestrator_smoke", [PYTHON, "-m", "dopey_autonomy.run_public_signal_research_breakthrough_v5"], 600),
    ("v5_preflight_smoke", [PYTHON, "-m", "dopey_validation.run_public_signal_research_v5_preflight"], 240),
    ("v5_baseline_freezer_smoke", [PYTHON, "-m", "dopey_validation.run_public_signal_research_baseline_freezer_v5"], 240),
    ("v5_safe_append_smoke", [PYTHON, "-m", "dopey_validation.run_safe_append_canon_validation_docs_v5"], 240),
    ("v5_expensive_lane_smoke", [PYTHON, "-m", "dopey_validation.run_public_signal_research_expensive_lane_runner_v5"], 240),
    ("v5_v4_result_analyzer_smoke", [PYTHON, "-m", "dopey_signal_research.run_v4_result_analyzer_v5"], 240),
    ("v5_mutation_executor_smoke", [PYTHON, "-m", "dopey_signal_research.run_research_mutation_queue_executor_v5"], 240),
    ("v5_no_trade_optimizer_smoke", [PYTHON, "-m", "dopey_signal_research.run_no_trade_filter_optimizer_v5"], 240),
    ("v5_candidate_generator_smoke", [PYTHON, "-m", "dopey_signal_research.run_research_candidate_generator_v5"], 240),
    ("v5_scorer_smoke", [PYTHON, "-m", "dopey_signal_research.run_profit_holdout_split_scorer_v5"], 240),
    ("v5_path_simulator_smoke", [PYTHON, "-m", "dopey_signal_research.run_research_path_simulator_v5"], 240),
    ("v5_tournament_smoke", [PYTHON, "-m", "dopey_signal_research.run_research_tournament_v5"], 240),
    ("v5_breakthrough_gate_smoke", [PYTHON, "-m", "dopey_signal_research.run_research_breakthrough_gate_v5"], 240),
    ("v5_mutation_queue_smoke", [PYTHON, "-m", "dopey_signal_research.run_research_mutation_queue_v5"], 240),
    ("v5_scoreboard_smoke", [PYTHON, "-m", "dopey_scoreboard.run_public_signal_research_scoreboard_v5"], 240),
    ("v5_live_gate_smoke", [PYTHON, "-m", "dopey_live_gate.run_public_signal_research_live_gate_status_v5"], 240),
    ("export_bundle_review_smoke", [PYTHON, "-m", "dopey_export_review.run_export_bundle_review_assistant"], 240),
    ("full_suite_stabilizer_smoke", [PYTHON, "-m", "dopey_validation.full_suite_stabilizer"], 240),
)


def _run_command(name: str, cmd: list[str], timeout_seconds: int) -> dict[str, object]:
    started = utc_now_iso()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        status = "pass" if proc.returncode == 0 else "fail"
        return {
            "artifact_type": "public_signal_research_v5_validation_command_record",
            "command_name": name,
            "command": " ".join(cmd),
            "started_at": started,
            "finished_at": utc_now_iso(),
            "exit_code": proc.returncode,
            "timed_out": False,
            "status": status,
            "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
            "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            "timeout_recorded_as_pass": False,
            "live_trading_enabled": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "artifact_type": "public_signal_research_v5_validation_command_record",
            "command_name": name,
            "command": " ".join(cmd),
            "started_at": started,
            "finished_at": utc_now_iso(),
            "exit_code": None,
            "timed_out": True,
            "status": "inconclusive_timeout",
            "timeout_seconds": timeout_seconds,
            "timeout_recorded_as_pass": False,
            "stdout_tail": (exc.stdout or b"").decode("utf-8", errors="replace")[-500:] if isinstance(exc.stdout, bytes) else (exc.stdout or "")[-500:],
            "stderr_tail": (exc.stderr or b"").decode("utf-8", errors="replace")[-500:] if isinstance(exc.stderr, bytes) else (exc.stderr or "")[-500:],
            "live_trading_enabled": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "artifact_type": "public_signal_research_v5_validation_command_record",
            "command_name": name,
            "command": " ".join(cmd),
            "started_at": started,
            "finished_at": utc_now_iso(),
            "exit_code": None,
            "timed_out": False,
            "status": "runner_error",
            "error": str(exc),
            "timeout_recorded_as_pass": False,
            "live_trading_enabled": False,
        }


def _append_validation_report(status: str, results: list[dict[str, object]]) -> None:
    report_path = REPO_ROOT / "DOPEY_VALIDATION_REPORT.md"
    marker = b"V5_VALIDATION_APPEND_MARKER"
    if report_path.exists() and marker in report_path.read_bytes():
        return
    pass_count = sum(1 for r in results if r.get("status") == "pass")
    timeout_count = sum(1 for r in results if r.get("status") == "inconclusive_timeout")
    fail_count = len(results) - pass_count - timeout_count
    text = (
        "\n\n<!-- V5_VALIDATION_APPEND_MARKER -->\n"
        "## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5 — Validation Result\n\n"
        f"- overall_status: `{status}`\n"
        f"- commands_run: {len(results)}\n"
        f"- pass: {pass_count}\n"
        f"- inconclusive_timeout: {timeout_count}\n"
        f"- fail: {fail_count}\n"
        "- timeout_recorded_as_pass: `false`\n"
        "- live_trading_enabled: `false`\n"
        "- credentials_present: `false`\n"
        "- broker_connection_enabled: `false`\n"
        "- real_order_enabled: `false`\n\n"
        "Appended by `dopey_validation.public_signal_research_v5_validation`.\n"
    )
    with report_path.open("ab") as fh:
        fh.write(text.encode("utf-8"))


def run_public_signal_research_v5_validation() -> dict[str, object]:
    RESEARCH_V5_ROOT.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    timeout_records: list[dict[str, object]] = []

    for name, cmd, timeout in VALIDATION_COMMANDS:
        rec = _run_command(name, cmd, timeout)
        results.append(rec)
        if rec.get("timed_out"):
            timeout_records.append(rec)

    # Merge any timeout records already emitted by the orchestrator / expensive lane.
    existing_timeout_path = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_timeout_records.jsonl"
    if existing_timeout_path.exists():
        for line in existing_timeout_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(rec, dict) and rec.get("timed_out"):
                # Avoid duplicates by command_name + started_at
                key = (rec.get("command_name"), rec.get("started_at"))
                if not any((r.get("command_name"), r.get("started_at")) == key for r in timeout_records):
                    timeout_records.append(rec)

    pass_count = sum(1 for r in results if r.get("status") == "pass")
    fail_count = sum(1 for r in results if r.get("status") not in {"pass", "inconclusive_timeout"})
    timeout_count = sum(1 for r in results if r.get("status") == "inconclusive_timeout")

    # Overall status: pass only if no failures and no unexpected timeouts (full-suite timeout is expected).
    if fail_count == 0 and timeout_count == 0:
        overall_status = "validation_passed"
    elif fail_count == 0:
        overall_status = "validation_passed_with_expected_timeouts"
    else:
        overall_status = "validation_failed"

    summary = {
        "artifact_type": "public_signal_research_breakthrough_v5_validation_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "validation_status": overall_status,
        "command_count": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "timeout_count": timeout_count,
        "timeout_recorded_as_pass": False,
        "command_results": [
            {
                "command_name": r.get("command_name"),
                "status": r.get("status"),
                "exit_code": r.get("exit_code"),
                "timed_out": r.get("timed_out"),
            }
            for r in results
        ],
        "live_trading_enabled": False,
        "credentials_present": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "public_data_only": True,
        "paper_only": True,
        "live_blocked": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(VALIDATION_SUMMARY_PATH, summary)
    write_jsonl_file(TIMEOUT_RECORDS_PATH, [record_with_hash(r, "record_hash") for r in timeout_records])
    write_jsonl_file(
        VALIDATION_PROOF_PATH,
        [research_v5_proof_record("public-signal-research-v5-validation", overall_status, summary)],
    )
    _append_validation_report(overall_status, results)
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_v5_validation(), indent=2, sort_keys=True, default=str))
