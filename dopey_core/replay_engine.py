"""Dopey replay engine: fixture-based benchmark/replay harness (PREP, never scores).

Forked verbatim from Blunder benchmark (Z:\\Obtuse\\engine\\blunder\\benchmark.py). Renamed
module; internal import of validate_against_schema now resolves to dopey_core.validator_mesh.
This harness prepares for benchmark/replay runs; it never fabricates scores and never trains on
answers. DOPEY uses it for deterministic replay of research artifacts only.

DOPEY lineage: Blunder benchmark.py -> dopey_core.replay_engine
"""
from __future__ import annotations

from .validator_mesh import validate_against_schema


def benchmark_task_packet_schema() -> dict:
    """JSON schema for a single benchmark task packet."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["benchmark", "task_id", "category", "prompt", "expected_kind", "scoring", "answer_withheld"],
        "properties": {
            "benchmark": {"type": "string", "minLength": 1},
            "task_id": {"type": "string", "minLength": 1},
            "category": {"type": "string", "enum": ["code", "reasoning", "schema", "repair", "validation", "artifact"]},
            "prompt": {"type": "string", "minLength": 1},
            "expected_kind": {"type": "string", "enum": ["exact", "unit_test", "schema", "fixture", "judge"]},
            "scoring": {"type": "string", "enum": ["pass_fail", "partial", "score"]},
            # answers must be withheld from the harness until the real run (no training on answers).
            "answer_withheld": {"type": "boolean", "const": True},
            "max_time_s": {"type": "number", "minimum": 0},
        },
    }


def validate_packets(packets: list[dict]) -> dict:
    schema = benchmark_task_packet_schema()
    results = []
    for p in packets:
        errs = validate_against_schema(p, schema)
        results.append({"task_id": p.get("task_id", "?"), "ok": not errs, "errors": errs})
    return {"all_ok": all(r["ok"] for r in results), "results": results}


def mock_benchmark_trial(packets: list[dict]) -> dict:
    """MOCK-only: prove the harness can ingest + validate + dry-run packets. NO scores are produced.
    Returns MOCK_PASS only if every packet is schema-valid AND every packet has its answer withheld."""
    v = validate_packets(packets)
    answers_withheld = all(p.get("answer_withheld") is True for p in packets)
    ok = v["all_ok"] and answers_withheld
    return {
        "mock_benchmark_replay_result": "MOCK_PASS" if ok else "MOCK_FAIL",
        "packets_validated": len(packets),
        "all_schema_valid": v["all_ok"],
        "answers_withheld": answers_withheld,
        "scores_produced": False,   # explicit: prep never scores
        "detail": v["results"],
    }


def benchmark_readiness_report(packets: list[dict]) -> dict:
    trial = mock_benchmark_trial(packets)
    known_blockers = [
        "no networked benchmark client wired (submission lane is operator-gated)",
        "real scoring not implemented in prep (by design — calibration, not identity)",
        "benchmark answer keys intentionally absent from the harness",
        "no live trade placement and no funded broker connection (DOPEY boundary)",
    ]
    return {
        "report": "benchmark_readiness_report",
        "harness_status": "PREP_READY" if trial["mock_benchmark_replay_result"] == "MOCK_PASS" else "PREP_BLOCKED",
        "baseline_capability": {
            "can_define_packets": True,
            "can_validate_packets": trial["all_schema_valid"],
            "can_mock_dry_run": True,
            "can_score_locally": False,
            "trains_on_answers": False,
        },
        "mock_benchmark_replay_result": trial,
        "known_blockers": known_blockers,
        "operator_gate_needed": [
            "networked benchmark submission",
            "external benchmark dataset download",
            "publishing any claimed score",
        ],
        "note": "Benchmark is calibration, not identity. DOPEY uses replay for research proof only.",
    }


def replay_fixture_builder(records: list[dict]) -> dict:
    """Build a deterministic replay fixture from a list of artifact records. No network; no scoring.
    Returns a fixture dict suitable for validator-mesh sweep / schema-instance replay."""
    return {
        "kind": "replay_fixture",
        "record_count": len(records),
        "records": list(records),
        "scores_produced": False,
    }
