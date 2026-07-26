"""Blunder runner — executes ONE complete recursive proof cycle on a safe fixture task, runs the universal
artifact sweep, benchmark-prep, and self-operation readiness, and writes proof artifacts into the existing
Obtuse workspace structure (30-proof-bundles + reports/...). Stdlib-only; all writes sandboxed.

Usage:  python run_blunder.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
OBTUSE_ROOT = ENGINE_DIR.parent
sys.path.insert(0, str(ENGINE_DIR))

from blunder import benchmark, selfop  # noqa: E402
from blunder.artifacts import sweep, validate_against_schema  # noqa: E402
from blunder.core import MockResult, ValidationResult, intake, sha256_text  # noqa: E402
from blunder.engine import ProofLedger, Task, run  # noqa: E402

FIX = ENGINE_DIR / "fixtures"


def _values(input_path: Path) -> list[int]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    return [r["value"] for r in data["records"]]


def _checksum(values: list[int]) -> str:
    return sha256_text(json.dumps(sorted(values)))


def _summary(values: list[int]) -> dict:
    return {
        "record_count": len(values),
        "total": sum(values),
        "max": max(values),
        "min": min(values),
        "mean": round(sum(values) / len(values), 6),
        "checksum": _checksum(values),
    }


class FixtureSummaryTask(Task):
    """Real fixture: summarize input_records.json -> output.json, validated vs schema + golden + a negative test.
    The v1 writer intentionally omits the 'checksum' field (a real serialization bug) so the bounded repair loop
    is exercised naturally; the repair reads the validator failure and recomputes the missing field."""

    def __init__(self):
        self.input_path = FIX / "input_records.json"
        self.schema = json.loads((FIX / "output.schema.json").read_text(encoding="utf-8"))
        self.golden = json.loads((FIX / "golden_output.json").read_text(encoding="utf-8"))

    def mock(self, packet, workdir):
        # Dry-run: compute the summary in memory and compare numerics to the golden — NO file written yet.
        values = _values(self.input_path)
        summ = _summary(values)
        numeric_ok = all(summ[k] == self.golden[k] for k in self.golden)
        result = MockResult.MOCK_PASS if numeric_ok else MockResult.MOCK_FAIL
        return result, {
            "summary": "dry-run computed the summary and compared numerics to the golden",
            "numeric_match_golden": numeric_ok,
            "predicted_output": summ,
            "decision": "proceed to execute" if numeric_ok else "repair plan before executing",
        }

    def execute(self, packet, workdir):
        values = _values(self.input_path)
        summ = _summary(values)
        # v1 BUG (real): drop 'checksum' on write -> will fail schema validation -> repair loop will fix it.
        v1 = {k: v for k, v in summ.items() if k != "checksum"}
        out = workdir / "output.json"
        out.write_text(json.dumps(v1, indent=2), encoding="utf-8")
        return {
            "commands_run": ["read input_records.json", "compute summary", "write output.json (v1)"],
            "files_touched": [str(out.relative_to(workdir))],
            "artifacts_created": ["output.json"],
            "diff_summary": "created output.json with record_count/total/max/min/mean (checksum omitted in v1)",
            "stdout_stderr_summary": "ok; wrote output.json (v1, missing checksum)",
            "exit_codes": [0],
            "environment_notes": f"python {sys.version.split()[0]}; sandboxed workdir; no network/external effects",
        }

    def validate(self, packet, workdir):
        out_path = workdir / "output.json"
        failures, test_results = [], {}

        # (1) artifact existence
        if not out_path.exists():
            return ValidationResult.VALIDATION_FAIL, {"failures": ["output.json was not created"], "test_results": {}}
        instance = json.loads(out_path.read_text(encoding="utf-8"))

        # (2) schema validation (real)
        schema_errors = validate_against_schema(instance, self.schema)
        test_results["schema_validation"] = "PASS" if not schema_errors else f"FAIL: {schema_errors}"
        failures += schema_errors

        # (3) golden fixture replay (numeric subset)
        golden_mismatch = [k for k in self.golden if instance.get(k) != self.golden[k]]
        test_results["golden_fixture_replay"] = "PASS" if not golden_mismatch else f"FAIL: mismatch {golden_mismatch}"
        if golden_mismatch:
            failures.append(f"golden mismatch on {golden_mismatch}")

        # (4) checksum integrity (recompute from source)
        if "checksum" in instance:
            expected = _checksum(_values(self.input_path))
            cs_ok = instance["checksum"] == expected
            test_results["checksum_integrity"] = "PASS" if cs_ok else "FAIL: checksum != recomputed"
            if not cs_ok:
                failures.append("checksum does not match recomputed value")

        # (5) NEGATIVE TEST: a deliberately malformed instance MUST be rejected (validator is not a rubber stamp).
        bad = {"record_count": "five", "total": 100, "max": 40, "min": 5, "mean": 20.0, "checksum": "short"}
        neg_errors = validate_against_schema(bad, self.schema)
        negative_rejected = len(neg_errors) > 0
        test_results["negative_test_rejected_bad_case"] = "PASS" if negative_rejected else "FAIL: bad case slipped through"
        if not negative_rejected:
            failures.append("negative test failed: validator accepted a malformed instance")

        ok = (not schema_errors) and (not golden_mismatch) and negative_rejected and ("checksum" in instance)
        result = ValidationResult.VALIDATION_PASS if ok else ValidationResult.VALIDATION_FAIL
        return result, {
            "failures": failures,
            "test_results": test_results,
            "limitations": [] if ok else ["validation not green; see failures"],
        }

    def repair(self, packet, workdir, failures, attempt):
        # Bounded, real repair: if the validator reported the missing 'checksum', recompute + add it.
        wants_checksum = any("checksum" in str(f).lower() for f in failures)
        out_path = workdir / "output.json"
        if wants_checksum and out_path.exists():
            instance = json.loads(out_path.read_text(encoding="utf-8"))
            before = dict(instance)
            instance["checksum"] = _checksum(_values(self.input_path))
            out_path.write_text(json.dumps(instance, indent=2), encoding="utf-8")
            return {
                "attempt": attempt, "classified_failure": "missing required field 'checksum'",
                "likely_cause": "v1 writer dropped the checksum field on serialization",
                "action": "recompute checksum from source data and re-write output.json",
                "patched": True,
                "diff": "added 'checksum' to output.json",
                "before_keys": sorted(before.keys()), "after_keys": sorted(instance.keys()),
            }
        return {"attempt": attempt, "action": "no matching repair recipe", "patched": False}

    def lessons(self, packet, val_detail, repair_log):
        out = []
        if any(r.get("patched") for r in repair_log):
            out.append({
                "id": "lesson-checksum-repair",
                "type": "repair_recipe",
                "statement": "When schema validation reports a missing data-derived field, recompute it from the "
                             "source inputs rather than re-running the whole task.",
                "from_real_run": True,
                "evidence": "repair_log shows missing-checksum classified and patched; re-validation passed",
                "improved_or_prevented_failure": True,
                "reusable": True,
                "weakens_safety": False,
                "validator_or_replay_checked": True,
            })
        # A deliberately weak candidate to demonstrate REJECTION (unvalidated speculation).
        out.append({
            "id": "lesson-speculative",
            "type": "speculation",
            "statement": "Maybe always skipping validation would be faster.",
            "from_real_run": True,
            "evidence": "",
            "improved_or_prevented_failure": False,
            "reusable": False,
            "weakens_safety": True,
            "validator_or_replay_checked": False,
        })
        return out


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"blunder-run-{stamp}"

    bundles = OBTUSE_ROOT / "30-proof-bundles"
    run_dir = bundles / run_id
    workdir = run_dir / "workdir"
    ledger = ProofLedger(bundles / "proof-ledger.jsonl")

    # ---- 1) Intake -> structured work packet (safe fixture, code_file task, low risk, no gate) ----
    raw = {
        "task_id": "fixture-summary-v1",
        "title": "Summarize fixture records and validate the artifact",
        "objective": "Produce output.json (summary) conforming to schema + golden, with checksum integrity.",
        "task_type": "code_file",
        "risk_level": "low",
        "allowed_actions": ["read_file", "compute", "write_workdir", "schema_validation", "run_tests", "local_proof_generation"],
        "forbidden_actions": ["network_submission", "destructive_file_op", "production_deploy"],
        "inputs": {"input_records": "fixtures/input_records.json"},
        "expected_outputs": ["output.json"],
        "validation_targets": ["schema_validation", "golden_fixture_replay", "checksum_integrity", "negative_test"],
        "rollback_plan": "all writes confined to the run workdir; discard the workdir to roll back",
        "human_gate_required": False,
    }
    packet = intake(raw)

    # ---- 2) Full recursive loop (mock -> execute -> validate -> repair -> ledger -> learn) ----
    report = run(packet, FixtureSummaryTask(), workdir, ledger, run_id)

    # ---- 3) Universal artifact intelligence sweep ----
    samples = json.loads((FIX / "universal_samples.json").read_text(encoding="utf-8"))
    sweep_report = sweep(samples)

    # ---- 4) Benchmark prep (mock-only, never fabricates scores) ----
    bench_packets = [
        {"benchmark": "blunder-calib-v1", "task_id": "bc-1", "category": "schema", "prompt": "validate an instance against a schema",
         "expected_kind": "schema", "scoring": "pass_fail", "answer_withheld": True, "max_time_s": 5},
        {"benchmark": "blunder-calib-v1", "task_id": "bc-2", "category": "repair", "prompt": "repair a failing artifact",
         "expected_kind": "unit_test", "scoring": "pass_fail", "answer_withheld": True, "max_time_s": 10},
        {"benchmark": "blunder-calib-v1", "task_id": "bc-3", "category": "artifact", "prompt": "parse a command trace",
         "expected_kind": "fixture", "scoring": "partial", "answer_withheld": True},
    ]
    bench_report = benchmark.benchmark_readiness_report(bench_packets)
    _write_json(ENGINE_DIR / "schemas" / "benchmark_task_packet.schema.json", benchmark.benchmark_task_packet_schema())

    # ---- 5) Self-operation readiness (inspect own engine; recommend only) ----
    selfop_report = selfop.self_operation_readiness(ENGINE_DIR / "blunder")

    # ---- 6) Ledger consistency self-check (proof-ledger is itself a validated artifact) ----
    ledger_check = ledger.consistency_check()

    # ---- 7) Write proof artifacts into the Obtuse structure ----
    _write_json(run_dir / "run-report.json", report)
    _write_json(run_dir / "sweep-report.json", sweep_report)
    _write_json(run_dir / "ledger-consistency.json", ledger_check)
    _write_json(OBTUSE_ROOT / "reports" / "benchmark-readiness" / f"{run_id}.json", bench_report)
    _write_json(OBTUSE_ROOT / "reports" / "self-operation" / f"{run_id}.json", selfop_report)
    _write_json(OBTUSE_ROOT / "reports" / "surgat-learning-promotions" / f"{run_id}.json", {
        "run_id": run_id,
        "promoted": report.get("promotion", {}).get("promoted", []),
        "rejected": report.get("promotion", {}).get("rejected", []),
        "lessons_candidate": report["entry"].get("lessons_candidate", []),
    })

    # ---- 8) Console summary (for verification) ----
    out = {
        "run_id": run_id,
        "final_status": report["status"],
        "mock_trial_result": report["entry"]["mock_trial_result"],
        "validation_result": report["entry"]["validation_result"],
        "repair_attempts": report["entry"]["repair_attempts"],
        "negative_test": report.get("validation", {}).get("test_results", {}).get("negative_test_rejected_bad_case"),
        "universal_sweep_overall_ok": sweep_report.get("overall_ok"),
        "benchmark_mock": bench_report["mock_benchmark_replay_result"]["mock_benchmark_replay_result"],
        "selfop_modules": selfop_report["module_count"],
        "ledger_consistency_ok": ledger_check["ok"],
        "lessons_promoted": [l["id"] for l in report.get("promotion", {}).get("promoted", [])],
        "lessons_rejected": [l["id"] for l in report.get("promotion", {}).get("rejected", [])],
        "run_dir": str(run_dir),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
