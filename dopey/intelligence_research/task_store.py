"""Deterministic task stores for visible and independently sealed cognitive evaluation."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final, cast

from dopey.protocols.identity import canonical_hash

from .creativity import CREATIVITY_OPERATORS
from .schema import (
    CognitiveBenchmarkTask,
    CognitiveTaskCandidate,
    CognitiveTaskStoreAudit,
)


COGNITIVE_EVALUATOR_VERSION: Final[str] = "dopey-cognitive-task-evaluator-v1"
EXPERIMENTAL_DOMAINS: Final[tuple[str, ...]] = (
    "dopey_market_research",
    "software_engineering",
    "security_analysis",
)
PARTITION_FILES: Final[dict[str, str]] = {
    "PRIVATE_SELECTION": "private_selection_tasks.jsonl",
    "EXTERNAL_GENERALIZATION": "external_generalization_tasks.jsonl",
    "REAL_TASK_FORWARD": "real_task_forward_tasks.jsonl",
}
_OPERATOR_FEATURES: Final[dict[str, tuple[str, ...]]] = {
    "ANALOGY": ("transfer",),
    "INVERSION": ("counterevidence",),
    "MORPHOLOGICAL_SEARCH": ("coverage",),
    "CONSTRAINT_INVERSION": ("constraint_safety",),
    "RECOMBINATION": ("support", "coverage"),
    "COUNTERFACTUAL_REASONING": ("falsifiability",),
    "FIRST_PRINCIPLES_RECONSTRUCTION": ("reliability",),
    "ABSTRACTION": ("simplicity",),
}


def _candidate(candidate_id: str, values: dict[str, float]) -> CognitiveTaskCandidate:
    fields = (
        "support",
        "counterevidence",
        "reliability",
        "transfer",
        "novelty",
        "simplicity",
        "coverage",
        "constraint_safety",
        "falsifiability",
    )
    missing = tuple(field for field in fields if field not in values)
    if missing:
        raise ValueError(
            f"cognitive task candidate is missing features: candidate_id={candidate_id}, fields={missing}"
        )
    if any(not 0.0 <= values[field] <= 1.0 for field in fields):
        raise ValueError(
            f"cognitive task candidate features must be within [0, 1]: candidate_id={candidate_id}"
        )
    return cast(CognitiveTaskCandidate, {"candidate_id": candidate_id, **values})


def _visible_candidates(
    operator: str, variant: int
) -> tuple[CognitiveTaskCandidate, ...]:
    baseline_values = {
        "support": 0.72,
        "counterevidence": 0.28,
        "reliability": 0.72,
        "transfer": 0.72,
        "novelty": 0.72,
        "simplicity": 0.72,
        "coverage": 0.72,
        "constraint_safety": 0.72,
        "falsifiability": 0.72,
    }
    method_values = {
        "support": 0.54,
        "counterevidence": 0.46,
        "reliability": 0.54,
        "transfer": 0.54,
        "novelty": 0.54,
        "simplicity": 0.54,
        "coverage": 0.54,
        "constraint_safety": 0.54,
        "falsifiability": 0.54,
    }
    for feature in _OPERATOR_FEATURES[operator]:
        method_values[feature] = 0.01 if feature == "counterevidence" else 0.99
    noise = (variant % 5) * 0.005
    method_values["novelty"] = min(1.0, method_values["novelty"] + noise)
    rejected_values = {
        "support": 0.45,
        "counterevidence": 0.55,
        "reliability": 0.42,
        "transfer": 0.40,
        "novelty": 0.90,
        "simplicity": 0.35,
        "coverage": 0.40,
        "constraint_safety": 0.30,
        "falsifiability": 0.35,
    }
    return (
        _candidate("baseline_generalist", baseline_values),
        _candidate("operator_specialist", method_values),
        _candidate("novel_but_unsupported", rejected_values),
    )


def build_visible_task_suite(
    variants_per_operator_domain: int,
) -> tuple[CognitiveBenchmarkTask, ...]:
    if variants_per_operator_domain <= 0:
        raise ValueError(
            "visible cognitive task variants must be positive: "
            f"variants_per_operator_domain={variants_per_operator_domain}"
        )
    tasks: list[CognitiveBenchmarkTask] = []
    for domain_id in EXPERIMENTAL_DOMAINS:
        for operator in CREATIVITY_OPERATORS:
            for variant in range(variants_per_operator_domain):
                identity = canonical_hash(
                    {
                        "domain_id": domain_id,
                        "operator": operator,
                        "variant": variant,
                        "evaluator_version": COGNITIVE_EVALUATOR_VERSION,
                    }
                )
                tasks.append(
                    {
                        "task_id": f"visible-cognitive-task:{identity[:24]}",
                        "domain_id": domain_id,
                        "partition": "VISIBLE_DEVELOPMENT",
                        "task_family": operator,
                        "expected_candidate_id": "operator_specialist",
                        "candidates": _visible_candidates(operator, variant),
                        "source_provenance": "repository_visible_development_benchmark_v1",
                        "evaluator_version": COGNITIVE_EVALUATOR_VERSION,
                    }
                )
    return tuple(tasks)


def _parse_task(
    record: Any, path: Path, line_number: int, partition: str
) -> CognitiveBenchmarkTask:
    if not isinstance(record, dict):
        raise ValueError(
            f"cognitive task must be an object: path={path}, line={line_number}"
        )
    required_strings = (
        "task_id",
        "domain_id",
        "partition",
        "task_family",
        "expected_candidate_id",
        "source_provenance",
        "evaluator_version",
    )
    for field in required_strings:
        if not isinstance(record.get(field), str) or not str(record[field]).strip():
            raise ValueError(
                f"cognitive task requires a non-empty string: path={path}, line={line_number}, field={field}"
            )
    if record["partition"] != partition:
        raise ValueError(
            f"cognitive task partition mismatch: path={path}, line={line_number}, "
            f"expected={partition}, actual={record['partition']}"
        )
    if record["evaluator_version"] != COGNITIVE_EVALUATOR_VERSION:
        raise ValueError(
            f"cognitive task evaluator version mismatch: path={path}, line={line_number}, "
            f"expected={COGNITIVE_EVALUATOR_VERSION}, actual={record['evaluator_version']}"
        )
    raw_candidates = record.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) < 2:
        raise ValueError(
            f"cognitive task requires at least two candidates: path={path}, line={line_number}"
        )
    candidates = tuple(
        _candidate(str(item["candidate_id"]), dict(item))
        for item in raw_candidates
        if isinstance(item, dict)
    )
    if len(candidates) != len(raw_candidates):
        raise ValueError(
            f"cognitive task candidate must be an object: path={path}, line={line_number}"
        )
    candidate_ids = {candidate["candidate_id"] for candidate in candidates}
    if (
        len(candidate_ids) != len(candidates)
        or record["expected_candidate_id"] not in candidate_ids
    ):
        raise ValueError(
            f"cognitive task candidate identities are invalid: path={path}, line={line_number}"
        )
    return {
        "task_id": str(record["task_id"]),
        "domain_id": str(record["domain_id"]),
        "partition": str(record["partition"]),
        "task_family": str(record["task_family"]),
        "expected_candidate_id": str(record["expected_candidate_id"]),
        "candidates": candidates,
        "source_provenance": str(record["source_provenance"]),
        "evaluator_version": str(record["evaluator_version"]),
    }


def task_semantic_fingerprint(task: CognitiveBenchmarkTask) -> str:
    """Hash task semantics without trusting any renameable identity or label."""

    candidate_semantics = [
        {str(key): value for key, value in candidate.items() if key != "candidate_id"}
        for candidate in task["candidates"]
    ]
    expected_candidate = next(
        candidate
        for candidate in task["candidates"]
        if candidate["candidate_id"] == task["expected_candidate_id"]
    )
    expected_semantics = {
        str(key): value
        for key, value in expected_candidate.items()
        if key != "candidate_id"
    }
    return canonical_hash(
        {
            "candidate_feature_vectors": sorted(
                candidate_semantics,
                key=canonical_hash,
            ),
            "expected_candidate_feature_vector": expected_semantics,
        }
    )


def _partition_fingerprint_hashes(
    tasks: tuple[CognitiveBenchmarkTask, ...],
) -> dict[str, str]:
    by_partition: dict[str, list[str]] = {
        partition: [] for partition in PARTITION_FILES
    }
    for task in tasks:
        by_partition[task["partition"]].append(task_semantic_fingerprint(task))
    return {
        partition: canonical_hash({"fingerprints": sorted(fingerprints)})
        for partition, fingerprints in sorted(by_partition.items())
    }


def _task_store_audit(
    tasks: tuple[CognitiveBenchmarkTask, ...],
    visible_tasks: tuple[CognitiveBenchmarkTask, ...],
) -> CognitiveTaskStoreAudit:
    partition_counts = Counter(task["partition"] for task in tasks)
    missing_partitions = tuple(
        partition for partition in PARTITION_FILES if partition_counts[partition] == 0
    )
    status = (
        "missing_independent_partitions"
        if not tasks
        else "incomplete_local_raw_task_store_untrusted"
        if missing_partitions
        else "local_raw_task_store_untrusted"
    )
    fingerprints = tuple(task_semantic_fingerprint(task) for task in tasks)
    visible_fingerprints = tuple(
        task_semantic_fingerprint(task) for task in visible_tasks
    )
    ordered_tasks = sorted(
        tasks,
        key=lambda record: (record["partition"], record["task_id"]),
    )
    content_hash = canonical_hash({"tasks": ordered_tasks})
    semantic_hash = canonical_hash(
        {
            "tasks": [
                {
                    "task_id": task["task_id"],
                    "partition": task["partition"],
                    "semantic_fingerprint": task_semantic_fingerprint(task),
                }
                for task in ordered_tasks
            ]
        }
    )
    return {
        "store_status": status,
        "task_count": len(tasks),
        "partition_counts": {
            partition: partition_counts[partition] for partition in PARTITION_FILES
        },
        "task_store_hash": content_hash,
        "task_store_content_hash": content_hash,
        "task_store_semantic_hash": semantic_hash,
        "visible_suite_hash": canonical_hash(
            {"semantic_fingerprints": sorted(visible_fingerprints)}
        ),
        "semantic_fingerprint_count": len(set(fingerprints)),
        "partition_fingerprint_hashes": _partition_fingerprint_hashes(tasks),
        "cross_partition_overlap_count": 0,
        "evaluator_independent": False,
        "activation_eligible": False,
        "raw_answers_accessible_to_local_process": bool(tasks),
        "signature_verification_status": "not_configured",
        "os_isolation_status": "not_verified",
    }


def load_independent_task_store(
    task_store_root: Path,
    visible_tasks: tuple[CognitiveBenchmarkTask, ...],
) -> tuple[tuple[CognitiveBenchmarkTask, ...], CognitiveTaskStoreAudit]:
    tasks: list[CognitiveBenchmarkTask] = []
    seen_ids: set[str] = set()
    seen_fingerprints: dict[str, tuple[str, str]] = {
        task_semantic_fingerprint(task): ("VISIBLE_DEVELOPMENT", task["task_id"])
        for task in visible_tasks
    }
    resolved_root = task_store_root.resolve()
    for partition, filename in PARTITION_FILES.items():
        path = task_store_root / filename
        if not path.exists():
            continue
        resolved_path = path.resolve(strict=True)
        if resolved_path.parent != resolved_root:
            raise ValueError(
                "cognitive task-store partition escapes its declared root: "
                f"root={resolved_root}, path={resolved_path}"
            )
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "cognitive task store contains invalid JSON: "
                    f"path={path}, line={line_number}"
                ) from exc
            task = _parse_task(decoded, path, line_number, partition)
            if task["task_id"] in seen_ids:
                raise ValueError(
                    f"duplicate cognitive task identity: path={path}, task_id={task['task_id']}"
                )
            fingerprint = task_semantic_fingerprint(task)
            previous = seen_fingerprints.get(fingerprint)
            if previous is not None:
                previous_partition, previous_task_id = previous
                raise ValueError(
                    "cognitive task contamination detected across evaluator partitions: "
                    f"fingerprint={fingerprint}, previous_partition={previous_partition}, "
                    f"previous_task_id={previous_task_id}, current_partition={partition}, "
                    f"current_task_id={task['task_id']}"
                )
            seen_ids.add(task["task_id"])
            seen_fingerprints[fingerprint] = (partition, task["task_id"])
            tasks.append(task)
    task_tuple = tuple(tasks)
    return task_tuple, _task_store_audit(task_tuple, visible_tasks)


def write_task_store(path: Path, tasks: Iterable[CognitiveBenchmarkTask]) -> None:
    records = tuple(tasks)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            )
    temporary.replace(path)
