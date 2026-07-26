"""Protected synthesis and autonomous activation for cognitive-method evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from dopey.protocols.identity import canonical_hash

from .creativity import CREATIVITY_OPERATORS
from .evaluator import evaluate_cognitive_method
from .execution import execute_cognitive_experiments
from .genome import build_cognitive_genome
from .schema import (
    BoundCognitiveTrialResult,
    CognitiveExperiment,
    CognitiveHypothesis,
    CognitiveMethodEvidence,
    CognitivePartitionEvidence,
    CognitiveTrialResult,
    EvaluationPartition,
)
from .task_store import (
    build_visible_task_suite,
    load_independent_task_store,
    write_task_store,
)
from .theory import build_theory_candidate


_HIDDEN_PARTITIONS: Final[tuple[str, ...]] = (
    "PRIVATE_SELECTION",
    "EXTERNAL_GENERALIZATION",
    "REAL_TASK_FORWARD",
)
_DISCOVERY_CYCLE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "artifact_type",
        "cycle_version",
        "cycle_status",
        "issued_at",
        "generation",
        "cognitive_level",
        "mission",
        "optimization_target",
        "knowledge_state_id",
        "discovery_questions",
        "cognitive_hypotheses",
        "experiments",
        "cognitive_world_model",
        "cognitive_roles",
        "automatic_cognitive_method_activation_count",
        "human_review_required_for_qualified_activation",
        "candidate_self_activation_allowed",
        "candidate_self_evaluation_allowed",
        "authority_effect",
        "permission_effect",
        "truth_effect",
        "paper_only",
        "live_blocked",
        "cycle_hash",
    }
)
_DISCOVERY_QUESTION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "question_id",
        "source_signal_id",
        "signal_type",
        "domain_id",
        "question",
        "priority",
        "evidence_ids",
    }
)
_HYPOTHESIS_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "method_id",
        "question_id",
        "cognitive_level",
        "creativity_operator",
        "method_statement",
        "prediction",
        "independent_variable",
        "dependent_metrics",
        "falsification_conditions",
        "evidence_parent_ids",
        "promotion_state",
        "candidate_may_grade_itself",
    }
)
_EXPERIMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "experiment_id",
        "method_id",
        "baseline_method",
        "experimental_domain_ids",
        "partitions",
        "primary_metrics",
        "replication_required",
        "cross_domain_promotion_blocked",
    }
)
_PARTITION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "partition",
        "item_level_feedback_visible",
        "selection_authority",
        "required_checks",
    }
)
_WORLD_MODEL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "artifact_type",
        "world_model_version",
        "knowledge_graph",
        "unknown_graph",
        "failure_graph",
        "opportunity_graph",
        "research_graph",
        "theory_graph",
        "capability_graph",
        "experimental_domain_ids",
    }
)
_RESEARCH_GRAPH_FIELDS: Final[frozenset[str]] = frozenset(
    {"question_ids", "method_ids", "experiment_ids"}
)
_EXPECTED_PARTITION_FLAGS: Final[tuple[tuple[str, bool, bool], ...]] = (
    ("VISIBLE_DEVELOPMENT", True, False),
    ("PRIVATE_SELECTION", False, True),
    ("EXTERNAL_GENERALIZATION", False, False),
    ("REAL_TASK_FORWARD", False, False),
)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _ledger_bytes(path: Path) -> tuple[bytes, str | None]:
    if not path.exists():
        return b"", None
    if not path.is_file():
        raise ValueError(f"cognitive ledger path must be a file: path={path}")
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        raise ValueError(f"cognitive ledger must end with a newline: path={path}")
    return content, hashlib.sha256(content).hexdigest()


def _plan_jsonl_idempotent_append(
    path: Path,
    records: Sequence[dict[str, Any]],
    identity_field: str,
) -> tuple[tuple[dict[str, Any], ...], str | None]:
    existing_hashes: dict[str, str] = {}
    content, source_digest = _ledger_bytes(path)
    if content:
        try:
            decoded_content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"cognitive ledger is not valid UTF-8: path={path}"
            ) from exc
        for line_number, line in enumerate(decoded_content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"cognitive ledger contains invalid JSON: path={path}, line={line_number}"
                ) from exc
            if not isinstance(decoded, dict):
                raise TypeError(
                    f"cognitive ledger entry must be an object: path={path}, line={line_number}"
                )
            identity = decoded.get(identity_field)
            if not isinstance(identity, str) or not identity:
                raise ValueError(
                    "cognitive ledger entry lacks its required identity: "
                    f"path={path}, line={line_number}, identity_field={identity_field}"
                )
            record_hash = canonical_hash(decoded)
            previous_hash = existing_hashes.get(identity)
            if previous_hash is not None and previous_hash != record_hash:
                raise ValueError(
                    "cognitive ledger identity conflict: "
                    f"path={path}, identity_field={identity_field}, identity={identity}"
                )
            existing_hashes[identity] = record_hash
    fresh: list[dict[str, Any]] = []
    for record in records:
        identity = record.get(identity_field)
        if not isinstance(identity, str) or not identity:
            raise ValueError(
                "cognitive ledger append requires a record identity: "
                f"path={path}, identity_field={identity_field}"
            )
        record_hash = canonical_hash(record)
        previous_hash = existing_hashes.get(identity)
        if previous_hash is not None:
            if previous_hash != record_hash:
                raise ValueError(
                    "cognitive ledger append conflicts with existing identity: "
                    f"path={path}, identity_field={identity_field}, identity={identity}"
                )
            continue
        existing_hashes[identity] = record_hash
        fresh.append(record)
    return tuple(fresh), source_digest


def _append_jsonl_preflighted(
    path: Path,
    records: Sequence[dict[str, Any]],
    expected_source_digest: str | None,
) -> None:
    _content, observed_source_digest = _ledger_bytes(path)
    if observed_source_digest != expected_source_digest:
        raise ValueError(
            "cognitive ledger changed after preflight: "
            f"path={path}, expected_digest={expected_source_digest}, "
            f"observed_digest={observed_source_digest}"
        )
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
        handle.flush()


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _lower_interval(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    average = _mean(values)
    if len(values) == 1:
        return min(0.0, average)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return average - 1.96 * math.sqrt(variance / len(values))


def _partition_evidence(
    partition: str,
    trials: Sequence[BoundCognitiveTrialResult],
) -> CognitivePartitionEvidence:
    partition_trials = tuple(
        trial for trial in trials if trial["partition"] == partition
    )
    domains: dict[str, list[float]] = defaultdict(list)
    for trial in partition_trials:
        domains[trial["domain_id"]].append(trial["quality_delta"])
    positive_domain_count = sum(1 for values in domains.values() if _mean(values) > 0.0)
    quality_values = tuple(trial["quality_delta"] for trial in partition_trials)
    calibration_values = tuple(trial["calibration_delta"] for trial in partition_trials)
    costs = tuple(trial["cost_delta"] for trial in partition_trials)
    positive_quality = max(0.0, _mean(quality_values))
    efficiency = positive_quality / (1.0 + _mean(costs)) if partition_trials else 0.0
    return {
        "partition": partition,
        "sample_count": len(partition_trials),
        "domain_count": len(domains),
        "replication_count": min(
            (len(values) for values in domains.values()),
            default=0,
        ),
        "effect_size": _mean(quality_values),
        "effect_interval_lower": _lower_interval(quality_values),
        "calibration_improvement": _mean(calibration_values),
        "transfer_score": (positive_domain_count / len(domains) if domains else 0.0),
        "efficiency_score": min(1.0, efficiency),
        "complexity_score": min(1.0, _mean(costs)) if partition_trials else 1.0,
        "deterministic": bool(partition_trials)
        and all(trial["deterministic"] for trial in partition_trials),
        "evaluator_independent": bool(partition_trials)
        and all(trial["evaluator_independent"] for trial in partition_trials),
    }


def synthesize_cognitive_method_evidence(
    method_id: str,
    trials: Sequence[BoundCognitiveTrialResult],
    source_discovery_cycle_hash: str,
    source_task_store_content_hash: str,
) -> CognitiveMethodEvidence:
    method_trials = tuple(trial for trial in trials if trial["method_id"] == method_id)
    partition_counts = defaultdict(int)
    for trial in method_trials:
        partition_counts[trial["partition"]] += 1
    hidden_partition_metrics = {
        partition: _partition_evidence(partition, method_trials)
        for partition in _HIDDEN_PARTITIONS
    }
    hidden_metrics = tuple(
        hidden_partition_metrics[partition] for partition in _HIDDEN_PARTITIONS
    )
    all_hidden_partitions_trusted = all(
        metric["evaluator_independent"] for metric in hidden_metrics
    )
    domain_count = (
        min(metric["domain_count"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0
    )
    replication_count = (
        min(metric["replication_count"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0
    )
    effect_size = (
        min(metric["effect_size"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0.0
    )
    effect_interval_lower = (
        min(metric["effect_interval_lower"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0.0
    )
    calibration_improvement = (
        min(metric["calibration_improvement"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0.0
    )
    transfer_score = (
        min(metric["transfer_score"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0.0
    )
    efficiency_score = (
        min(metric["efficiency_score"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 0.0
    )
    complexity_score = (
        max(metric["complexity_score"] for metric in hidden_metrics)
        if all_hidden_partitions_trusted
        else 1.0
    )
    evidence: CognitiveMethodEvidence = {
        "method_id": method_id,
        "source_discovery_cycle_hash": source_discovery_cycle_hash,
        "source_task_store_content_hash": source_task_store_content_hash,
        "promotion_metrics_source": (
            "worst_case_across_trusted_independent_hidden_partitions"
        ),
        "hidden_partition_metrics": hidden_partition_metrics,
        "visible_samples": partition_counts["VISIBLE_DEVELOPMENT"],
        "private_samples": partition_counts["PRIVATE_SELECTION"],
        "external_samples": partition_counts["EXTERNAL_GENERALIZATION"],
        "real_task_samples": partition_counts["REAL_TASK_FORWARD"],
        "domain_count": domain_count,
        "replication_count": replication_count,
        "effect_size": effect_size,
        "effect_interval_lower": effect_interval_lower,
        "calibration_improvement": calibration_improvement,
        "transfer_score": transfer_score,
        "efficiency_score": efficiency_score,
        "complexity_score": complexity_score,
        "deterministic": bool(method_trials)
        and all(trial["deterministic"] for trial in method_trials),
        "evaluator_independent": all_hidden_partitions_trusted,
        "reward_hacking_detected": False,
        "constitutional_violation": False,
    }
    return evidence


def _exact_object(
    value: object,
    expected_fields: frozenset[str],
    context: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    actual_fields = set(value)
    if actual_fields != expected_fields:
        raise ValueError(
            f"{context} has an invalid schema: "
            f"missing={sorted(expected_fields - actual_fields)}, "
            f"unexpected={sorted(actual_fields - expected_fields)}"
        )
    return {str(key): item for key, item in value.items()}


def _non_empty_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a string array")
    strings = tuple(
        _non_empty_string(item, f"{context}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(strings)) != len(strings):
        raise ValueError(f"{context} must contain unique strings")
    return strings


def _strict_bool(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be boolean")
    return value


def _strict_int(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context} must be an integer")
    return value


def _validate_discovery_question(
    value: object,
    path: Path,
    index: int,
) -> str:
    context = f"cognitive discovery question: path={path}, index={index}"
    record = _exact_object(value, _DISCOVERY_QUESTION_FIELDS, context)
    question_id = _non_empty_string(record["question_id"], f"{context}, question_id")
    for field in (
        "source_signal_id",
        "signal_type",
        "domain_id",
        "question",
    ):
        _non_empty_string(record[field], f"{context}, {field}")
    priority = record["priority"]
    if (
        not isinstance(priority, (int, float))
        or isinstance(priority, bool)
        or not math.isfinite(float(priority))
    ):
        raise ValueError(f"{context}, priority must be finite")
    _string_tuple(record["evidence_ids"], f"{context}, evidence_ids")
    return question_id


def _parse_hypothesis(
    value: object,
    path: Path,
    index: int,
    question_ids: frozenset[str],
    cycle_cognitive_level: int,
) -> CognitiveHypothesis:
    context = f"cognitive hypothesis: path={path}, index={index}"
    record = _exact_object(value, _HYPOTHESIS_FIELDS, context)
    method_id = _non_empty_string(record["method_id"], f"{context}, method_id")
    question_id = _non_empty_string(record["question_id"], f"{context}, question_id")
    if question_id not in question_ids:
        raise ValueError(
            f"{context} references an unknown question: question_id={question_id}"
        )
    cognitive_level = _strict_int(
        record["cognitive_level"],
        f"{context}, cognitive_level",
    )
    if cognitive_level != cycle_cognitive_level:
        raise ValueError(
            f"{context} cognitive level differs from its source cycle: "
            f"expected={cycle_cognitive_level}, actual={cognitive_level}"
        )
    operator = _non_empty_string(
        record["creativity_operator"],
        f"{context}, creativity_operator",
    )
    if operator not in CREATIVITY_OPERATORS:
        raise ValueError(
            f"{context} uses an unsupported creativity operator: operator={operator}"
        )
    method_statement = _non_empty_string(
        record["method_statement"],
        f"{context}, method_statement",
    )
    prediction = _non_empty_string(
        record["prediction"],
        f"{context}, prediction",
    )
    independent_variable = _non_empty_string(
        record["independent_variable"],
        f"{context}, independent_variable",
    )
    dependent_metrics = _string_tuple(
        record["dependent_metrics"],
        f"{context}, dependent_metrics",
    )
    falsification_conditions = _string_tuple(
        record["falsification_conditions"],
        f"{context}, falsification_conditions",
    )
    evidence_parent_ids = _string_tuple(
        record["evidence_parent_ids"],
        f"{context}, evidence_parent_ids",
    )
    if record["promotion_state"] != "EXPERIMENTAL":
        raise ValueError(f"{context} must begin in EXPERIMENTAL promotion state")
    if _strict_bool(
        record["candidate_may_grade_itself"],
        f"{context}, candidate_may_grade_itself",
    ):
        raise ValueError(f"{context} cannot grant candidate self-grading")
    expected_method_id = (
        "cognitive-method:"
        + canonical_hash(
            {
                "question_id": question_id,
                "operator": operator,
                "method_statement": method_statement,
                "cognitive_level": cognitive_level,
            }
        )[:24]
    )
    if method_id != expected_method_id:
        raise ValueError(
            f"{context} method identity is not bound to its content: "
            f"expected={expected_method_id}, actual={method_id}"
        )
    return {
        "method_id": method_id,
        "question_id": question_id,
        "cognitive_level": cognitive_level,
        "creativity_operator": operator,
        "method_statement": method_statement,
        "prediction": prediction,
        "independent_variable": independent_variable,
        "dependent_metrics": dependent_metrics,
        "falsification_conditions": falsification_conditions,
        "evidence_parent_ids": evidence_parent_ids,
        "promotion_state": "EXPERIMENTAL",
        "candidate_may_grade_itself": False,
    }


def _parse_partition(
    value: object,
    path: Path,
    experiment_index: int,
    partition_index: int,
) -> EvaluationPartition:
    context = (
        "cognitive evaluation partition: "
        f"path={path}, experiment_index={experiment_index}, "
        f"partition_index={partition_index}"
    )
    record = _exact_object(value, _PARTITION_FIELDS, context)
    partition = _non_empty_string(record["partition"], f"{context}, partition")
    visible = _strict_bool(
        record["item_level_feedback_visible"],
        f"{context}, item_level_feedback_visible",
    )
    selection_authority = _strict_bool(
        record["selection_authority"],
        f"{context}, selection_authority",
    )
    required_checks = _string_tuple(
        record["required_checks"],
        f"{context}, required_checks",
    )
    if not required_checks:
        raise ValueError(f"{context} requires at least one check")
    expected_partition, expected_visible, expected_selection = (
        _EXPECTED_PARTITION_FLAGS[partition_index]
    )
    if (
        partition != expected_partition
        or visible is not expected_visible
        or selection_authority is not expected_selection
    ):
        raise ValueError(
            f"{context} does not match the sealed partition contract: "
            f"partition={partition}, visible={visible}, "
            f"selection_authority={selection_authority}"
        )
    return {
        "partition": partition,
        "item_level_feedback_visible": visible,
        "selection_authority": selection_authority,
        "required_checks": required_checks,
    }


def _parse_experiment(
    value: object,
    path: Path,
    index: int,
    hypothesis_by_method: dict[str, CognitiveHypothesis],
) -> CognitiveExperiment:
    context = f"cognitive experiment: path={path}, index={index}"
    record = _exact_object(value, _EXPERIMENT_FIELDS, context)
    experiment_id = _non_empty_string(
        record["experiment_id"],
        f"{context}, experiment_id",
    )
    method_id = _non_empty_string(record["method_id"], f"{context}, method_id")
    hypothesis = hypothesis_by_method.get(method_id)
    if hypothesis is None:
        raise ValueError(
            f"{context} references an unknown method: method_id={method_id}"
        )
    baseline_method = _non_empty_string(
        record["baseline_method"],
        f"{context}, baseline_method",
    )
    if baseline_method != "precommitted_current_best_method":
        raise ValueError(f"{context} changes the precommitted baseline")
    experimental_domain_ids = _string_tuple(
        record["experimental_domain_ids"],
        f"{context}, experimental_domain_ids",
    )
    if not experimental_domain_ids:
        raise ValueError(f"{context} requires at least one experimental domain")
    raw_partitions = record["partitions"]
    if not isinstance(raw_partitions, list) or len(raw_partitions) != len(
        _EXPECTED_PARTITION_FLAGS
    ):
        raise ValueError(
            f"{context}, partitions must contain the complete sealed partition set"
        )
    partitions = tuple(
        _parse_partition(item, path, index, partition_index)
        for partition_index, item in enumerate(raw_partitions)
    )
    primary_metrics = _string_tuple(
        record["primary_metrics"],
        f"{context}, primary_metrics",
    )
    if primary_metrics != hypothesis["dependent_metrics"]:
        raise ValueError(f"{context} primary metrics differ from the source hypothesis")
    if not _strict_bool(
        record["replication_required"],
        f"{context}, replication_required",
    ):
        raise ValueError(f"{context} cannot disable replication")
    cross_domain_blocked = _strict_bool(
        record["cross_domain_promotion_blocked"],
        f"{context}, cross_domain_promotion_blocked",
    )
    if cross_domain_blocked != (len(experimental_domain_ids) < 3):
        raise ValueError(f"{context} cross-domain promotion state is inconsistent")
    expected_experiment_id = (
        "cognitive-experiment:"
        + canonical_hash(
            {
                "method_id": method_id,
                "experimental_domain_ids": experimental_domain_ids,
                "partitions": partitions,
            }
        )[:24]
    )
    if experiment_id != expected_experiment_id:
        raise ValueError(
            f"{context} identity is not bound to its content: "
            f"expected={expected_experiment_id}, actual={experiment_id}"
        )
    return {
        "experiment_id": experiment_id,
        "method_id": method_id,
        "baseline_method": baseline_method,
        "experimental_domain_ids": experimental_domain_ids,
        "partitions": partitions,
        "primary_metrics": primary_metrics,
        "replication_required": True,
        "cross_domain_promotion_blocked": cross_domain_blocked,
    }


def _validate_world_model(
    value: object,
    path: Path,
    question_ids: tuple[str, ...],
    method_ids: tuple[str, ...],
    experiment_ids: tuple[str, ...],
    cognitive_roles: tuple[str, ...],
    experimental_domain_ids: tuple[str, ...],
) -> None:
    context = f"cognitive world model: path={path}"
    record = _exact_object(value, _WORLD_MODEL_FIELDS, context)
    if record["artifact_type"] != "shared_cognitive_world_model":
        raise ValueError(f"{context} has an unsupported artifact type")
    if record["world_model_version"] != "dopey-cognitive-world-model-v1":
        raise ValueError(f"{context} has an unsupported version")
    node_fields = frozenset({"node_id", "node_type", "domain_id", "statement"})
    knowledge_nodes: set[str] = set()
    for graph_name in (
        "knowledge_graph",
        "unknown_graph",
        "failure_graph",
        "opportunity_graph",
    ):
        nodes = record[graph_name]
        if not isinstance(nodes, list):
            raise ValueError(f"{context}, {graph_name} must be an object array")
        for node_index, node in enumerate(nodes):
            node_context = f"{context}, {graph_name}[{node_index}]"
            parsed_node = _exact_object(node, node_fields, node_context)
            for field in node_fields:
                _non_empty_string(parsed_node[field], f"{node_context}, {field}")
            if graph_name == "knowledge_graph":
                knowledge_nodes.add(canonical_hash(parsed_node))
            elif canonical_hash(parsed_node) not in knowledge_nodes:
                raise ValueError(
                    f"{node_context} is not present in the knowledge graph"
                )
    research_graph = _exact_object(
        record["research_graph"],
        _RESEARCH_GRAPH_FIELDS,
        f"{context}, research_graph",
    )
    expected_research_ids = {
        "question_ids": question_ids,
        "method_ids": method_ids,
        "experiment_ids": experiment_ids,
    }
    for field, expected_ids in expected_research_ids.items():
        observed_ids = _string_tuple(
            research_graph[field],
            f"{context}, research_graph.{field}",
        )
        if observed_ids != expected_ids:
            raise ValueError(
                f"{context}, research_graph.{field} differs from the cycle"
            )
    if record["theory_graph"] != []:
        raise ValueError(f"{context} cannot contain pre-activated theories")
    capability_graph = record["capability_graph"]
    if not isinstance(capability_graph, list):
        raise ValueError(f"{context}, capability_graph must be an object array")
    capability_roles: list[str] = []
    for index, item in enumerate(capability_graph):
        capability = _exact_object(
            item,
            frozenset({"role_id", "state"}),
            f"{context}, capability_graph[{index}]",
        )
        role_id = _non_empty_string(
            capability["role_id"],
            f"{context}, capability_graph[{index}].role_id",
        )
        if capability["state"] != "available":
            raise ValueError(
                f"{context}, capability_graph[{index}] has an invalid state"
            )
        capability_roles.append(role_id)
    if tuple(capability_roles) != cognitive_roles:
        raise ValueError(f"{context} capability roles differ from the cycle")
    observed_domains = _string_tuple(
        record["experimental_domain_ids"],
        f"{context}, experimental_domain_ids",
    )
    if observed_domains != experimental_domain_ids:
        raise ValueError(f"{context} experimental domains differ from experiments")


def _load_cycle(
    path: Path,
) -> tuple[
    tuple[CognitiveHypothesis, ...],
    tuple[CognitiveExperiment, ...],
    int,
    str,
]:
    try:
        raw_value: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"cognitive discovery cycle contains invalid JSON: path={path}"
        ) from exc
    raw = _exact_object(
        raw_value,
        _DISCOVERY_CYCLE_FIELDS,
        f"cognitive discovery cycle: path={path}",
    )
    observed_cycle_hash = _non_empty_string(
        raw["cycle_hash"],
        f"cognitive discovery cycle hash: path={path}",
    )
    source_body = {str(key): value for key, value in raw.items() if key != "cycle_hash"}
    expected_cycle_hash = canonical_hash(source_body)
    if observed_cycle_hash != expected_cycle_hash:
        raise ValueError(
            "cognitive discovery cycle content hash mismatch: "
            f"path={path}, expected={expected_cycle_hash}, "
            f"observed={observed_cycle_hash}"
        )
    expected_constants = {
        "artifact_type": "autonomous_intelligence_research_cycle",
        "cycle_version": "dopey-intelligence-research-cycle-v1",
        "mission": "discover_better_ways_of_discovering",
        "optimization_target": "evidence_validated_cognitive_methods",
        "authority_effect": "none",
        "permission_effect": "none",
        "truth_effect": "none",
    }
    for field, expected in expected_constants.items():
        if raw[field] != expected:
            raise ValueError(
                f"cognitive discovery cycle has an invalid {field}: path={path}"
            )
    if raw["paper_only"] is not True or raw["live_blocked"] is not True:
        raise ValueError(
            f"cognitive discovery cycle violates research-only authority: path={path}"
        )
    activation_count = _strict_int(
        raw["automatic_cognitive_method_activation_count"],
        f"cognitive discovery cycle activation count: path={path}",
    )
    if activation_count != 0:
        raise ValueError(
            f"cognitive discovery cycle contains autonomous activations: path={path}"
        )
    activation_flags = (
        (
            "human_review_required_for_qualified_activation",
            raw["human_review_required_for_qualified_activation"],
        ),
        (
            "candidate_self_activation_allowed",
            raw["candidate_self_activation_allowed"],
        ),
        (
            "candidate_self_evaluation_allowed",
            raw["candidate_self_evaluation_allowed"],
        ),
    )
    if any(
        _strict_bool(value, f"cognitive discovery cycle {field}: path={path}")
        for field, value in activation_flags
    ):
        raise ValueError(
            f"cognitive discovery cycle contains unauthorized activation state: path={path}"
        )
    issued_at = _non_empty_string(
        raw["issued_at"],
        f"cognitive discovery cycle issued_at: path={path}",
    )
    parsed_issued_at = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    if parsed_issued_at.tzinfo is None:
        raise ValueError(
            f"cognitive discovery cycle issued_at requires a timezone: path={path}"
        )
    generation = _strict_int(
        raw["generation"],
        f"cognitive discovery cycle generation: path={path}",
    )
    if generation <= 0:
        raise ValueError(
            f"cognitive discovery cycle generation must be positive: path={path}"
        )
    cognitive_level = _strict_int(
        raw["cognitive_level"],
        f"cognitive discovery cycle cognitive_level: path={path}",
    )
    if not 0 <= cognitive_level <= 7:
        raise ValueError(
            f"cognitive discovery cycle cognitive_level is outside [0, 7]: path={path}"
        )
    _non_empty_string(
        raw["knowledge_state_id"],
        f"cognitive discovery cycle knowledge_state_id: path={path}",
    )
    raw_questions = raw["discovery_questions"]
    if not isinstance(raw_questions, list):
        raise ValueError(
            f"cognitive discovery questions must be an object array: path={path}"
        )
    question_ids = tuple(
        _validate_discovery_question(item, path, index)
        for index, item in enumerate(raw_questions)
    )
    if len(set(question_ids)) != len(question_ids):
        raise ValueError(
            f"cognitive discovery question identities must be unique: path={path}"
        )
    raw_hypotheses = raw["cognitive_hypotheses"]
    if not isinstance(raw_hypotheses, list):
        raise ValueError(
            f"cognitive discovery hypotheses must be an object array: path={path}"
        )
    hypotheses = tuple(
        _parse_hypothesis(
            item,
            path,
            index,
            frozenset(question_ids),
            cognitive_level,
        )
        for index, item in enumerate(raw_hypotheses)
    )
    hypothesis_by_method = {record["method_id"]: record for record in hypotheses}
    if len(hypothesis_by_method) != len(hypotheses):
        raise ValueError(f"cognitive hypothesis identities must be unique: path={path}")
    raw_experiments = raw["experiments"]
    if not isinstance(raw_experiments, list):
        raise ValueError(
            f"cognitive discovery experiments must be an object array: path={path}"
        )
    experiments = tuple(
        _parse_experiment(item, path, index, hypothesis_by_method)
        for index, item in enumerate(raw_experiments)
    )
    experiment_ids = tuple(record["experiment_id"] for record in experiments)
    if len(set(experiment_ids)) != len(experiment_ids):
        raise ValueError(f"cognitive experiment identities must be unique: path={path}")
    experiment_method_ids = tuple(record["method_id"] for record in experiments)
    method_ids = tuple(record["method_id"] for record in hypotheses)
    if experiment_method_ids != method_ids:
        raise ValueError(
            f"cognitive experiments must map one-to-one to hypotheses: path={path}"
        )
    expected_status = (
        "cognitive_experiments_queued" if experiments else "no_governed_discoveries"
    )
    if raw["cycle_status"] != expected_status:
        raise ValueError(
            f"cognitive discovery cycle status is inconsistent: path={path}"
        )
    cognitive_roles = _string_tuple(
        raw["cognitive_roles"],
        f"cognitive discovery cycle roles: path={path}",
    )
    experimental_domain_ids = (
        experiments[0]["experimental_domain_ids"] if experiments else ()
    )
    if experiments and any(
        experiment["experimental_domain_ids"] != experimental_domain_ids
        for experiment in experiments
    ):
        raise ValueError(
            f"cognitive experiments disagree on experimental domains: path={path}"
        )
    if not experiments:
        world_value = raw["cognitive_world_model"]
        world_record = _exact_object(
            world_value,
            _WORLD_MODEL_FIELDS,
            f"cognitive world model: path={path}",
        )
        experimental_domain_ids = _string_tuple(
            world_record["experimental_domain_ids"],
            f"cognitive world model experimental domains: path={path}",
        )
    _validate_world_model(
        raw["cognitive_world_model"],
        path,
        question_ids,
        method_ids,
        experiment_ids,
        cognitive_roles,
        experimental_domain_ids,
    )
    return hypotheses, experiments, generation, observed_cycle_hash


def _bind_trial_to_sources(
    trial: CognitiveTrialResult,
    source_discovery_cycle_hash: str,
    source_task_store_content_hash: str,
) -> BoundCognitiveTrialResult:
    execution_trial_id = trial["trial_id"]
    identity = canonical_hash(
        {
            "execution_trial_id": execution_trial_id,
            "source_discovery_cycle_hash": source_discovery_cycle_hash,
            "source_task_store_content_hash": source_task_store_content_hash,
        }
    )
    return {
        **trial,
        "trial_id": f"cognitive-trial:{identity[:24]}",
        "execution_trial_id": execution_trial_id,
        "source_discovery_cycle_hash": source_discovery_cycle_hash,
        "source_task_store_content_hash": source_task_store_content_hash,
    }


def run_cognitive_evidence_cycle(
    discovery_cycle_path: Path,
    task_store_root: Path,
    output_root: Path,
    visible_variants_per_operator_domain: int,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("cognitive evidence cycle issued_at must be timezone-aware")
    if not discovery_cycle_path.exists():
        body: dict[str, Any] = {
            "artifact_type": "autonomous_cognitive_evidence_cycle",
            "cycle_version": "dopey-cognitive-evidence-cycle-v2",
            "cycle_status": "missing_discovery_cycle",
            "issued_at": issued_at.isoformat(),
            "automatic_cognitive_method_activation_count": 0,
            "candidate_self_activation_allowed": False,
            "candidate_self_evaluation_allowed": False,
            "authority_effect": "none",
            "readiness_effect": "none",
            "execution_effect": "none",
            "paper_only": True,
            "live_blocked": True,
        }
        output = {**body, "cycle_hash": canonical_hash(body)}
        _write_json_atomic(output_root / "latest_evidence_cycle.json", output)
        return output
    (
        hypotheses,
        experiments,
        generation,
        source_discovery_cycle_hash,
    ) = _load_cycle(discovery_cycle_path)
    visible_tasks = build_visible_task_suite(visible_variants_per_operator_domain)
    independent_tasks, task_store_audit = load_independent_task_store(
        task_store_root,
        visible_tasks,
    )
    source_task_store_content_hash = task_store_audit["task_store_content_hash"]
    visible_execution_trials = execute_cognitive_experiments(
        hypotheses,
        experiments,
        visible_tasks,
        False,
    )
    independent_execution_trials = execute_cognitive_experiments(
        hypotheses,
        experiments,
        independent_tasks,
        task_store_audit["evaluator_independent"],
    )
    visible_trials = tuple(
        _bind_trial_to_sources(
            trial,
            source_discovery_cycle_hash,
            source_task_store_content_hash,
        )
        for trial in visible_execution_trials
    )
    independent_trials = tuple(
        _bind_trial_to_sources(
            trial,
            source_discovery_cycle_hash,
            source_task_store_content_hash,
        )
        for trial in independent_execution_trials
    )
    trials = (*visible_trials, *independent_trials)
    evidence = tuple(
        synthesize_cognitive_method_evidence(
            hypothesis["method_id"],
            trials,
            source_discovery_cycle_hash,
            source_task_store_content_hash,
        )
        for hypothesis in hypotheses
    )
    evaluations = tuple(evaluate_cognitive_method(record) for record in evidence)
    evidence_by_method = {record["method_id"]: record for record in evidence}
    hypothesis_by_method = {record["method_id"]: record for record in hypotheses}
    activated_method_ids = tuple(
        str(record["method_id"])
        for record in evaluations
        if record["automatic_cognitive_method_activation_allowed"] is True
    )
    theories = tuple(
        build_theory_candidate(
            hypothesis_by_method[method_id],
            evidence_by_method[method_id],
            next(record for record in evaluations if record["method_id"] == method_id),
        )
        for method_id in activated_method_ids
    )
    genomes = tuple(
        build_cognitive_genome(
            (),
            generation,
            (method_id,),
            ("scientific_discovery_loop_v1",),
            (hypothesis_by_method[method_id]["creativity_operator"],),
            ("uncertainty_first_planning_v1",),
            ("independent_hidden_evaluator_v1",),
            ("scientific_theory_memory_v1",),
            ("competing_cognitive_organism_v1",),
        )
        for method_id in activated_method_ids
    )
    missing_partitions = tuple(
        partition
        for partition in _HIDDEN_PARTITIONS
        if not any(task["partition"] == partition for task in independent_tasks)
    )
    status = (
        "evaluation_complete_activated"
        if activated_method_ids
        else "visible_evaluation_complete_waiting_independent_partitions"
        if missing_partitions
        else "evaluation_complete_blocked_untrusted_independent_task_store"
        if not task_store_audit["activation_eligible"]
        else "evaluation_complete_no_activations"
    )
    body = {
        "artifact_type": "autonomous_cognitive_evidence_cycle",
        "cycle_version": "dopey-cognitive-evidence-cycle-v2",
        "cycle_status": status,
        "evidence_status": "evaluation_complete",
        "issued_at": issued_at.isoformat(),
        "source_discovery_cycle_hash": source_discovery_cycle_hash,
        "source_task_store_content_hash": source_task_store_content_hash,
        "discovery_generation": generation,
        "visible_task_count": len(visible_tasks),
        "independent_task_count": len(independent_tasks),
        "independent_task_store_audit": task_store_audit,
        "trial_count": len(trials),
        "method_evidence": list(evidence),
        "evaluations": list(evaluations),
        "missing_independent_partitions": list(missing_partitions),
        "automatic_cognitive_method_activation_count": len(activated_method_ids),
        "activated_method_ids": list(activated_method_ids),
        "theory_candidate_count": len(theories),
        "cognitive_genome_count": len(genomes),
        "human_review_required": False,
        "candidate_self_activation_allowed": False,
        "candidate_self_evaluation_allowed": False,
        "authority_effect": "none",
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    trial_ledger_path = output_root / "cognitive_trial_ledger.jsonl"
    evidence_cycle_ledger_path = output_root / "cognitive_evidence_cycle_ledger.jsonl"
    trial_records = tuple(dict(record) for record in trials)
    fresh_trial_records, trial_ledger_digest = _plan_jsonl_idempotent_append(
        trial_ledger_path,
        trial_records,
        "trial_id",
    )
    fresh_cycle_records, evidence_cycle_ledger_digest = _plan_jsonl_idempotent_append(
        evidence_cycle_ledger_path,
        (output,),
        "cycle_hash",
    )
    _append_jsonl_preflighted(
        trial_ledger_path,
        fresh_trial_records,
        trial_ledger_digest,
    )
    _append_jsonl_preflighted(
        evidence_cycle_ledger_path,
        fresh_cycle_records,
        evidence_cycle_ledger_digest,
    )
    write_task_store(output_root / "visible_development_tasks.jsonl", visible_tasks)
    _write_json_atomic(
        output_root / "independent_task_store_audit.json",
        task_store_audit,
    )
    _write_json_atomic(output_root / "cognitive_method_evidence.json", list(evidence))
    _write_json_atomic(
        output_root / "cognitive_method_evaluations.json", list(evaluations)
    )
    _write_json_atomic(output_root / "cognitive_theory_memory.json", list(theories))
    _write_json_atomic(output_root / "activated_cognitive_genomes.json", list(genomes))
    _write_json_atomic(output_root / "latest_evidence_cycle.json", output)
    return output
