"""Build the portable, source-backed sovereign research observatory artifact."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _load_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"observatory source artifact is missing: path={path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"observatory source artifact must be a JSON object: path={path}")
    return value


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _portable_path(path: Path, repository_root: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = repository_root.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return path.name


def _file_source(
    source_id: str,
    label: str,
    path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    relative_path = _portable_path(path, repository_root)
    return {
        "id": source_id,
        "label": label,
        "path": relative_path,
    }


def _query_source(
    dataset_id: str,
    database_path: Path,
    repository_root: Path,
    generated_at: str,
    sql: str,
    metric_definitions: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "id": dataset_id,
        "label": f"Observatory snapshot: {dataset_id}",
        "path": _portable_path(database_path, repository_root),
        "query": {
            "engine": "sqlite",
            "language": "sql",
            "id": f"dopey-observatory-{dataset_id}",
            "executed_at": generated_at,
            "sql": sql,
            "description": (
                "Executed against the local observatory SQLite snapshot after deterministic "
                "materialization from the upstream JSON artifacts listed in source_health."
            ),
            "tables_used": [dataset_id],
            "filters": ["paper_only=true", "live_blocked=true"],
            "metric_definitions": dict(metric_definitions),
        },
    }


def _sqlite_type(values: Sequence[Any]) -> str:
    non_null = [value for value in values if value is not None]
    if not non_null or all(isinstance(value, str) for value in non_null):
        return "TEXT"
    if all(isinstance(value, (bool, int)) and not isinstance(value, float) for value in non_null):
        return "INTEGER"
    if all(isinstance(value, (bool, int, float)) for value in non_null):
        return "REAL"
    raise TypeError(f"observatory snapshot column has unsupported mixed values: types={sorted({type(value).__name__ for value in non_null})}")


def _dataset_sql(dataset_id: str, rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        raise ValueError(f"observatory dataset cannot be empty: dataset={dataset_id}")
    columns = tuple(rows[0])
    if not columns:
        raise ValueError(f"observatory dataset row cannot be empty: dataset={dataset_id}")
    if any(tuple(row) != columns for row in rows):
        raise ValueError(f"observatory dataset rows must share one ordered schema: dataset={dataset_id}")
    projection = ", ".join(f'"{column}"' for column in columns)
    return f'SELECT {projection} FROM "{dataset_id}" ORDER BY rowid'


def _materialize_snapshot_database(
    database_path: Path,
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    source_paths: Sequence[tuple[str, Path]],
    generated_at: str,
) -> dict[str, str]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    queries = {dataset_id: _dataset_sql(dataset_id, rows) for dataset_id, rows in datasets.items()}
    with sqlite3.connect(database_path) as connection:
        for dataset_id, rows in datasets.items():
            columns = tuple(rows[0])
            connection.execute(f'DROP TABLE IF EXISTS "{dataset_id}"')
            definitions = ", ".join(
                f'"{column}" {_sqlite_type([row[column] for row in rows])} NOT NULL'
                for column in columns
            )
            connection.execute(f'CREATE TABLE "{dataset_id}" ({definitions})')
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f'INSERT INTO "{dataset_id}" VALUES ({placeholders})',
                [tuple(int(value) if isinstance(value, bool) else value for value in row.values()) for row in rows],
            )
        connection.execute('DROP TABLE IF EXISTS "source_lineage"')
        connection.execute(
            'CREATE TABLE "source_lineage" ('
            '"source_label" TEXT NOT NULL, "source_path" TEXT NOT NULL, "materialized_at" TEXT NOT NULL)'
        )
        connection.executemany(
            'INSERT INTO "source_lineage" VALUES (?, ?, ?)',
            [(label, str(path), generated_at) for label, path in source_paths],
        )
        for dataset_id, sql in queries.items():
            result_count = len(connection.execute(sql).fetchall())
            if result_count != len(datasets[dataset_id]):
                raise RuntimeError(
                    "observatory SQLite verification returned an unexpected row count: "
                    f"dataset={dataset_id}, expected={len(datasets[dataset_id])}, actual={result_count}"
                )
        connection.commit()
    return queries


def _finding_count(guard: Mapping[str, Any]) -> int:
    fields = (
        "findings",
        "violations",
        "dangling_evidence_ids",
        "stale_or_future_evidence_ids",
        "exceeded_dimensions",
    )
    return sum(len(guard.get(field, [])) for field in fields if isinstance(guard.get(field, []), list))


def _agent_gap_count(agent: Mapping[str, Any]) -> int:
    gaps = agent.get("uncertainties", [])
    followups = agent.get("requested_followups", [])
    return len(gaps) + len(followups) if isinstance(gaps, list) and isinstance(followups, list) else 0


def _health_rows(homeostasis: Mapping[str, Any]) -> list[dict[str, Any]]:
    variables = homeostasis.get("variables", {})
    if not isinstance(variables, dict):
        raise TypeError("homeostasis variables must be an object")
    return [
        {
            "variable": str(name),
            "value": float(value),
            "attention": float(value) < 0.5 if name not in {"resource_pressure", "strategy_concentration"} else float(value) > 0.8,
        }
        for name, value in sorted(variables.items())
    ]


def _evolution_rows(evolution: Mapping[str, Any]) -> list[dict[str, Any]]:
    evaluations = evolution.get("evaluations", [])
    if not isinstance(evaluations, list):
        raise TypeError("evolution evaluations must be an array")
    if not evaluations:
        return [{
            "candidate_id": "none",
            "recommended_state": "NO_OPERATIONAL_CANDIDATE_EVALUATED",
            "causal_confidence": 0.0,
            "held_out": False,
            "promotion_allowed": False,
        }]
    return [
        {
            "candidate_id": str(record.get("candidate_id", "unknown")),
            "recommended_state": str(record.get("recommended_state", "QUARANTINED")),
            "causal_confidence": float(record.get("causal_evaluation", {}).get("causal_confidence", 0.0) or 0.0),
            "held_out": bool(record.get("held_out", False)),
            "promotion_allowed": bool(record.get("automatic_research_activation_allowed", False)),
        }
        for record in evaluations
        if isinstance(record, dict)
    ]


def _source_status_rows(
    generated_at: str,
    source_paths: Sequence[tuple[str, Path]],
    repository_root: Path,
) -> list[dict[str, Any]]:
    return [
        {
            "source": label,
            "path": _portable_path(path, repository_root),
            "status": "available" if path.exists() else "missing",
            "observed_at": generated_at,
        }
        for label, path in source_paths
    ]


def _validate_artifact_references(artifact: Mapping[str, Any]) -> None:
    manifest = artifact.get("manifest", {})
    snapshot = artifact.get("snapshot", {})
    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    datasets = snapshot.get("datasets", {}) if isinstance(snapshot, dict) else {}
    source_ids = {str(source.get("id")) for source in sources if isinstance(source, dict)}
    dataset_ids = set(datasets) if isinstance(datasets, dict) else set()
    for group_name in ("cards", "charts", "tables"):
        group = manifest.get(group_name, []) if isinstance(manifest, dict) else []
        for item in group:
            source_id = str(item.get("sourceId", ""))
            dataset_id = str(item.get("dataset", ""))
            if source_id not in source_ids:
                raise ValueError(f"observatory {group_name} source is unresolved: source_id={source_id}")
            if dataset_id not in dataset_ids:
                raise ValueError(f"observatory {group_name} dataset is unresolved: dataset={dataset_id}")


def build_observatory_artifact(
    vnext_output_dir: Path,
    readiness_path: Path,
    evolution_status_path: Path,
    settlement_cycle_path: Path,
    generated_at: str,
    repository_root: Path,
) -> dict[str, Any]:
    required_paths = {
        "summary": vnext_output_dir / "vnext_research_summary.json",
        "world": vnext_output_dir / "world_model.json",
        "technical": vnext_output_dir / "technical_evidence.json",
        "organism": vnext_output_dir / "organism_episode.json",
        "metacognition": vnext_output_dir / "metacognition.json",
        "shadow": vnext_output_dir / "shadow_controller.json",
        "homeostasis": vnext_output_dir / "homeostasis.json",
        "resource": vnext_output_dir / "resource_ledger.json",
        "constitution": vnext_output_dir / "constitution_state.json",
        "calibration": vnext_output_dir / "calibration_summary.json",
        "time_proofs": vnext_output_dir / "input_time_proofs.json",
        "readiness": readiness_path,
        "evolution": evolution_status_path,
        "settlement": settlement_cycle_path,
    }
    intelligence_path = repository_root / "artifacts" / "dopey" / "intelligence_research" / "latest_cycle.json"
    intelligence_evidence_path = repository_root / "artifacts" / "dopey" / "intelligence_research" / "latest_evidence_cycle.json"
    threshold_audit_path = repository_root / "artifacts" / "dopey" / "threshold_fabric" / "latest_audit.json"
    strategy_engineering_path = repository_root / "artifacts" / "dopey" / "strategy_engineering" / "latest_cycle.json"
    paths = {
        **required_paths,
        "intelligence": intelligence_path,
        "intelligence_evidence": intelligence_evidence_path,
        "threshold_audit": threshold_audit_path,
        "strategy_engineering": strategy_engineering_path,
    }
    loaded = {name: _load_object(path) for name, path in required_paths.items()}
    intelligence = _load_object(intelligence_path) if intelligence_path.exists() else {}
    intelligence_evidence = _load_object(intelligence_evidence_path) if intelligence_evidence_path.exists() else {}
    threshold_audit = _load_object(threshold_audit_path) if threshold_audit_path.exists() else {}
    strategy_engineering = _load_object(strategy_engineering_path) if strategy_engineering_path.exists() else {}
    summary = loaded["summary"]
    world = loaded["world"]
    technical = loaded["technical"]
    organism = loaded["organism"]
    metacognition = loaded["metacognition"]
    shadow = loaded["shadow"]
    homeostasis = loaded["homeostasis"]
    resource = loaded["resource"]
    constitution = loaded["constitution"]
    calibration = loaded["calibration"]
    time_proofs = loaded["time_proofs"]
    readiness = loaded["readiness"]
    evolution = loaded["evolution"]
    settlement = loaded["settlement"]
    cognitive_experiments = intelligence.get("experiments", [])
    discovery_questions = intelligence.get("discovery_questions", [])
    cognitive_hypotheses = intelligence.get("cognitive_hypotheses", [])
    cognitive_evaluations = intelligence_evidence.get("evaluations", [])
    if not isinstance(cognitive_experiments, list):
        raise TypeError("intelligence research experiments must be an array")
    if not isinstance(discovery_questions, list):
        raise TypeError("intelligence research discovery_questions must be an array")
    if not isinstance(cognitive_hypotheses, list):
        raise TypeError("intelligence research cognitive_hypotheses must be an array")
    if not isinstance(cognitive_evaluations, list):
        raise TypeError("intelligence evidence evaluations must be an array")

    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        raise ValueError("observatory rejects a vNext summary outside the sealed paper-only boundary")
    if readiness.get("readiness_status") == "action_ready":
        raise ValueError("observatory refuses to reinterpret external readiness as vNext research evidence")
    confidence = metacognition.get("confidence", {})
    if not isinstance(confidence, dict):
        raise TypeError("metacognition confidence must be an object")
    agents = organism.get("agent_results", [])
    if not isinstance(agents, list):
        raise TypeError("organism agent_results must be an array")
    regimes = world.get("regimes", {})
    if not isinstance(regimes, dict):
        raise TypeError("world model regimes must be an object")
    technical_measurements = technical.get("measurements", [])
    if not isinstance(technical_measurements, list):
        raise TypeError("technical measurements must be an array")
    time_proof_inputs = time_proofs.get("inputs", {})
    if not isinstance(time_proof_inputs, dict):
        raise TypeError("input time proofs must contain an inputs object")
    accepted_time_statuses = {
        "point_in_time_valid",
        "excluded_missing_point_in_time_timestamp",
    }
    time_proof_failure_count = sum(
        str(record.get("status", "")) not in accepted_time_statuses
        for record in time_proof_inputs.values()
        if isinstance(record, dict)
    )
    threshold_gate = summary.get("autonomous_threshold_gate", {})
    if not isinstance(threshold_gate, dict):
        raise TypeError("vNext autonomous_threshold_gate must be an object")
    reverse_report = strategy_engineering.get("reverse_report", {})
    quality_archive = strategy_engineering.get("quality_diversity_archive", {})
    if not isinstance(reverse_report, dict) or not isinstance(quality_archive, dict):
        raise TypeError("strategy engineering reverse report and archive must be objects")

    datasets: dict[str, list[dict[str, Any]]] = {
        "hero_metrics": [{
            "research_confidence": float(confidence.get("final_research_confidence", 0.0) or 0.0),
            "known_world_dimensions": int(world.get("known_dimension_count", 0) or 0),
            "technical_measurements": int(technical.get("measurement_count", 0) or 0),
            "agent_count": len(agents),
            "pending_settlements": int(settlement.get("pending_count", 0) or 0),
            "automatic_promotions": int(evolution.get("automatic_research_activation_count", 0) or 0),
            "cognitive_experiments": len(cognitive_experiments),
            "cognitive_trials": int(intelligence_evidence.get("trial_count", 0) or 0),
            "cognitive_method_activations": int(
                intelligence_evidence.get("automatic_cognitive_method_activation_count", 0) or 0
            ),
            "time_proof_failures": time_proof_failure_count,
            "threshold_policies": int(threshold_audit.get("policy_count", 0) or 0),
            "strategy_candidates": int(strategy_engineering.get("forward_candidate_count", 0) or 0),
            "action_ready": 0,
        }],
        "world_regimes": [
            {
                "dimension": str(name),
                "state": str(record.get("state", "unknown")),
                "probability": float(record.get("probability", 0.0) or 0.0),
                "uncertainty": float(record.get("uncertainty", 1.0) or 1.0),
                "limitation_count": len(record.get("limitations", [])),
            }
            for name, record in sorted(regimes.items())
            if isinstance(record, dict)
        ],
        "world_regime_chart": [
            {
                "dimension": str(name),
                "state": str(regimes[name].get("state", "unknown")),
                "probability": float(regimes[name].get("probability", 0.0) or 0.0),
                "uncertainty": float(regimes[name].get("uncertainty", 1.0) or 1.0),
            }
            for name in (
                "equity_trend",
                "volatility",
                "breadth",
                "liquidity",
                "credit",
                "rates",
                "market_fragility",
                "options_dealer_state",
            )
            if name in regimes and isinstance(regimes[name], dict)
        ],
        "technical_timeframes": [
            {
                "timeframe": timeframe,
                "measurement_count": sum(record.get("timeframe") == timeframe for record in technical_measurements),
                "positive_count": sum(record.get("timeframe") == timeframe and float(record.get("strength", 0.0) or 0.0) > 0.2 for record in technical_measurements),
                "negative_count": sum(record.get("timeframe") == timeframe and float(record.get("strength", 0.0) or 0.0) < -0.2 for record in technical_measurements),
            }
            for timeframe in ("daily", "weekly", "monthly")
        ],
        "hypotheses": [
            {"hypothesis": str(name), "probability": float(value)}
            for name, value in sorted(summary.get("hypotheses", {}).items())
        ],
        "agents": [
            {
                "agent_id": str(agent.get("agent_id", "unknown")),
                "status": str(agent.get("status", "unknown")),
                "confidence": float(agent.get("confidence", 0.0) or 0.0),
                "data_reads": int(agent.get("runtime", {}).get("data_reads", 0) or 0),
                "gap_count": _agent_gap_count(agent),
            }
            for agent in agents
            if isinstance(agent, dict)
        ],
        "confidence_dimensions": [
            {"dimension": name, "value": float(confidence.get(name, 0.0) or 0.0)}
            for name in (
                "model",
                "evidence_completeness",
                "evidence_freshness",
                "historical_analogue_quality",
                "calibration_quality",
                "causal_confidence",
                "regime_familiarity",
                "agent_disagreement",
                "final_research_confidence",
            )
        ],
        "shadow_guards": [
            {
                "guard": str(guard.get("guard", "unknown")),
                "status": str(guard.get("status", "unknown")),
                "finding_count": _finding_count(guard),
                "may_increase_readiness": bool(guard.get("may_increase_readiness", False)),
            }
            for guard in shadow.get("guards", [])
            if isinstance(guard, dict)
        ],
        "health_variables": _health_rows(homeostasis),
        "evolution_candidates": _evolution_rows(evolution),
        "intelligence_discoveries": (
            [
                {
                    "question_id": str(record.get("question_id", "unknown")),
                    "signal_type": str(record.get("signal_type", "unknown")),
                    "domain_id": str(record.get("domain_id", "unknown")),
                    "priority": float(record.get("priority", 0.0) or 0.0),
                    "method_count": sum(
                        hypothesis.get("question_id") == record.get("question_id")
                        for hypothesis in cognitive_hypotheses
                        if isinstance(hypothesis, dict)
                    ),
                }
                for record in discovery_questions
                if isinstance(record, dict)
            ]
            if discovery_questions
            else [{"question_id": "none", "signal_type": "NO_CYCLE", "domain_id": "none", "priority": 0.0, "method_count": 0}]
        ),
        "cognitive_method_evaluations": (
            [
                {
                    "method_id": str(record.get("method_id", "unknown")),
                    "promotion_state": str(record.get("promotion_state", "EXPERIMENTAL")),
                    "failed_threshold_count": len(record.get("failed_thresholds", [])),
                    "activation_allowed": bool(
                        record.get("automatic_cognitive_method_activation_allowed", False)
                    ),
                }
                for record in cognitive_evaluations
                if isinstance(record, dict)
            ]
            if cognitive_evaluations
            else [
                {
                    "method_id": "none",
                    "promotion_state": "NO_EVIDENCE_CYCLE",
                    "failed_threshold_count": 0,
                    "activation_allowed": False,
                }
            ]
        ),
        "constitution_invariants": [
            {"invariant": "paper_only", "state": bool(constitution.get("paper_only")), "sealed": True},
            {"invariant": "live_blocked", "state": bool(constitution.get("live_blocked")), "sealed": True},
            {"invariant": "broker_authority", "state": bool(constitution.get("broker_authority")), "sealed": True},
            {"invariant": "order_authority", "state": bool(constitution.get("order_authority")), "sealed": True},
            {"invariant": "credential_access", "state": bool(constitution.get("credential_access")), "sealed": True},
            {"invariant": "self_unlock_available", "state": bool(constitution.get("self_unlock_available")), "sealed": True},
        ],
        "source_health": _source_status_rows(generated_at, tuple(paths.items()), repository_root),
        "settlement_calibration": [{
            "settled_total": int(calibration.get("settled_total", 0) or 0),
            "pending_total": int(calibration.get("pending_total", 0) or 0),
            "ece": float(calibration.get("expected_calibration_error", 0.0) or 0.0),
            "sample_sufficient": bool(calibration.get("calibration_sample_sufficient", False)),
        }],
        "resource_utilization": [
            {"dimension": str(name), "utilization": float(value)}
            for name, value in sorted(resource.get("utilization", {}).items())
        ],
        "point_in_time_inputs": [
            {
                "input": str(name),
                "status": str(record.get("status", "unknown")),
                "timestamp": str(record.get("timestamp", "unavailable_excluded")),
                "age_hours": float(record.get("age_hours", -1.0) or 0.0),
                "maximum_age_hours": float(record.get("maximum_age_hours", -1.0) or 0.0),
                "used_as_evidence": bool(
                    record.get(
                        "used_as_calibration_evidence",
                        record.get("status") == "point_in_time_valid",
                    )
                ),
            }
            for name, record in sorted(time_proof_inputs.items())
            if isinstance(record, dict)
        ],
        "threshold_control": [{
            "policy_id": str(threshold_gate.get("policy_id", "not_materialized")),
            "decision": str(threshold_gate.get("decision", "NO_GATE_ARTIFACT")),
            "passed": bool(threshold_gate.get("passed", False)),
            "missing_metric_count": len(threshold_gate.get("missing_metrics", [])),
            "failed_rule_count": len(threshold_gate.get("failed_rules", [])),
            "positive_promotion_allowed": bool(threshold_gate.get("positive_promotion_allowed", False)),
        }],
        "strategy_engineering": [{
            "cycle_status": str(strategy_engineering.get("cycle_status", "NO_CYCLE")),
            "reverse_status": str(reverse_report.get("reverse_status", "NO_SETTLED_REVERSE_REPORT")),
            "settled_case_count": int(reverse_report.get("settled_case_count", 0) or 0),
            "reverse_hypothesis_count": int(reverse_report.get("hypothesis_count", 0) or 0),
            "forward_candidate_count": int(strategy_engineering.get("forward_candidate_count", 0) or 0),
            "quality_diversity_cells": int(quality_archive.get("occupied_cell_count", 0) or 0),
            "shadow_admitted_count": int(strategy_engineering.get("shadow_admitted_count", 0) or 0),
            "positive_promotion_allowed": bool(strategy_engineering.get("positive_promotion_allowed", False)),
        }],
    }

    labels = {
        "summary": "vNext research summary",
        "world": "Shared market world model",
        "technical": "Multi-timeframe technical evidence",
        "organism": "Research organism episode",
        "metacognition": "Metacognitive evaluation",
        "shadow": "Shadow-controller guards",
        "homeostasis": "Homeostasis state",
        "resource": "Research resource ledger",
        "constitution": "Sealed constitution state",
        "calibration": "Forward calibration summary",
        "time_proofs": "Point-in-time input proof",
        "readiness": "External readiness gate snapshot",
        "evolution": "Bounded evolution status",
        "settlement": "Forward settlement-cycle status",
        "intelligence": "Domain-independent intelligence research cycle",
        "intelligence_evidence": "Protected cognitive-method evidence cycle",
        "threshold_audit": "Autonomous threshold fabric audit",
        "strategy_engineering": "Reverse and forward strategy engineering cycle",
    }
    database_path = vnext_output_dir / "observatory_snapshot.sqlite"
    dataset_queries = _materialize_snapshot_database(
        database_path,
        datasets,
        tuple(paths.items()),
        generated_at,
    )
    dataset_definitions: dict[str, dict[str, str]] = {
        dataset_id: {
            field: f"Materialized observatory field '{field}' from the governed upstream artifact lineage."
            for field in rows[0]
        }
        for dataset_id, rows in datasets.items()
    }
    dataset_definitions["hero_metrics"].update({
        "research_confidence": "Conservative metacognitive confidence after weakest-critical-dimension cap and disagreement penalty.",
        "action_ready": "Always 0 because vNext cannot set the protected external readiness gate.",
        "automatic_promotions": "Symbol-strategy pairs activated automatically by the protected three-gate research matrix; this never changes action readiness.",
        "time_proof_failures": "Inputs that failed the governed point-in-time validation or explicit exclusion policy.",
        "cognitive_experiments": "Domain-independent cognitive-method experiments queued by the intelligence research engine.",
        "cognitive_trials": "Matched baseline and challenger trials across governed cognitive task domains.",
        "cognitive_method_activations": "Cognitive methods activated only after protected private, external, forward, and cross-domain thresholds.",
        "threshold_policies": "Sealed autonomous threshold policies verified by the structural audit.",
        "strategy_candidates": "Interpretable shadow-only forward research candidates; never order instructions.",
    })
    dataset_definitions["world_regimes"].update({
        "probability": "Dimension-specific evidence support probability; explicitly unknown dimensions remain zero.",
        "uncertainty": "One minus evidence support probability for the dimension.",
    })
    dataset_definitions["world_regime_chart"].update({
        "probability": "Evidence support probability for one of eight operator-critical world dimensions.",
        "uncertainty": "One minus evidence support probability for the operator-critical dimension.",
    })
    dataset_definitions["confidence_dimensions"].update({
        "value": "Unblended confidence component; agent_disagreement is adverse rather than supportive.",
    })
    raw_sources = [
        _file_source(
            name,
            labels[name],
            path,
            repository_root,
        )
        for name, path in paths.items()
    ]
    query_sources = [
        _query_source(
            dataset_id,
            database_path,
            repository_root,
            generated_at,
            dataset_queries[dataset_id],
            dataset_definitions[dataset_id],
        )
        for dataset_id in datasets
    ]
    sources = [*query_sources, *raw_sources]

    cards = [
        {"id": "confidence-card", "description": "Conservative research confidence, not action readiness.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Research confidence", "field": "research_confidence", "format": "percent"}]},
        {"id": "world-card", "description": "World-model dimensions supported by typed evidence.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Known world dimensions", "field": "known_world_dimensions", "format": "number"}]},
        {"id": "technical-card", "description": "Independent daily, weekly, and monthly measurements.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Technical measurements", "field": "technical_measurements", "format": "number"}]},
        {"id": "agents-card", "description": "Typed specialist and core agent results.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Research agents", "field": "agent_count", "format": "number"}]},
        {"id": "settlement-card", "description": "Recorded predictions still awaiting their minimum settlement horizon.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Pending settlements", "field": "pending_settlements", "format": "number"}]},
        {"id": "promotion-card", "description": "Protected threshold-qualified research activations; never trading authority.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Research activations", "field": "automatic_promotions", "format": "number"}]},
        {"id": "intelligence-card", "description": "Experiments on reasoning, discovery, planning, and evaluation methods.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Cognitive experiments", "field": "cognitive_experiments", "format": "number"}]},
        {"id": "cognitive-trials-card", "description": "Matched baseline/challenger trials; visible trials are never sufficient for activation.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Cognitive trials", "field": "cognitive_trials", "format": "number"}]},
        {"id": "cognitive-activation-card", "description": "Threshold-qualified cognitive methods with independent evidence; never execution authority.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Cognitive activations", "field": "cognitive_method_activations", "format": "number"}]},
        {"id": "time-proof-card", "description": "Invalid or ungoverned point-in-time inputs; this must remain zero.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Input time-proof failures", "field": "time_proof_failures", "format": "number"}]},
        {"id": "threshold-card", "description": "Sealed autonomous routing and abstention policies; no positive promotion authority.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Threshold policies", "field": "threshold_policies", "format": "number"}]},
        {"id": "strategy-engineering-card", "description": "Interpretable reverse and forward research candidates in shadow mode.", "dataset": "hero_metrics", "sourceId": "hero_metrics", "metrics": [{"label": "Strategy candidates", "field": "strategy_candidates", "format": "number"}]},
    ]
    charts = [
        {"id": "world-chart", "title": "Critical world-model support", "subtitle": "Eight operator-critical dimensions; the complete state remains in the table below.", "type": "bar", "dataset": "world_regime_chart", "sourceId": "world_regime_chart", "valueFormat": "percent", "encodings": {"x": {"field": "dimension", "type": "nominal", "label": "Dimension"}, "y": {"field": "probability", "type": "quantitative", "label": "Support probability"}, "tooltip": [{"field": "state", "label": "State"}, {"field": "uncertainty", "label": "Uncertainty", "format": "percent"}]}},
        {"id": "confidence-chart", "title": "Confidence decomposition", "subtitle": "No blended score is shown without its limiting dimensions.", "type": "bar", "dataset": "confidence_dimensions", "sourceId": "confidence_dimensions", "valueFormat": "percent", "encodings": {"x": {"field": "dimension", "type": "nominal", "label": "Dimension"}, "y": {"field": "value", "type": "quantitative", "label": "Value"}}},
        {"id": "hypothesis-chart", "title": "Competing hypotheses", "subtitle": "Bull, bear, neutral, and unknown probabilities before forward settlement.", "type": "bar", "dataset": "hypotheses", "sourceId": "hypotheses", "valueFormat": "percent", "encodings": {"x": {"field": "hypothesis", "type": "nominal", "label": "Hypothesis"}, "y": {"field": "probability", "type": "quantitative", "label": "Probability"}}},
        {"id": "health-chart", "title": "Research-system homeostasis", "subtitle": "Interventions are advisory and cannot mutate protected surfaces.", "type": "bar", "dataset": "health_variables", "sourceId": "health_variables", "valueFormat": "percent", "encodings": {"x": {"field": "variable", "type": "nominal", "label": "Variable"}, "y": {"field": "value", "type": "quantitative", "label": "Normalized value"}}},
    ]
    tables = [
        {"id": "regime-table", "title": "World-state detail", "subtitle": "State, support, uncertainty, and known limitations.", "dataset": "world_regimes", "sourceId": "world_regimes", "defaultSort": {"field": "uncertainty", "direction": "desc"}, "columns": [{"field": "dimension", "label": "Dimension", "type": "text"}, {"field": "state", "label": "State", "type": "text"}, {"field": "probability", "label": "Support", "format": "percent"}, {"field": "uncertainty", "label": "Uncertainty", "format": "percent"}, {"field": "limitation_count", "label": "Limitations", "format": "number"}]},
        {"id": "agent-table", "title": "Research organism agents", "subtitle": "Status, confidence, evidence reads, and unresolved gaps.", "dataset": "agents", "sourceId": "agents", "defaultSort": {"field": "gap_count", "direction": "desc"}, "columns": [{"field": "agent_id", "label": "Agent", "type": "text"}, {"field": "status", "label": "Status", "type": "text"}, {"field": "confidence", "label": "Confidence", "format": "percent"}, {"field": "data_reads", "label": "Data reads", "format": "number"}, {"field": "gap_count", "label": "Gaps", "format": "number"}]},
        {"id": "shadow-table", "title": "Shadow-controller guards", "subtitle": "Shadows may only downgrade, veto, request evidence, or force abstention.", "dataset": "shadow_guards", "sourceId": "shadow_guards", "defaultSort": {"field": "finding_count", "direction": "desc"}, "columns": [{"field": "guard", "label": "Guard", "type": "text"}, {"field": "status", "label": "Status", "type": "text"}, {"field": "finding_count", "label": "Findings", "format": "number"}, {"field": "may_increase_readiness", "label": "Can increase readiness", "type": "boolean"}]},
        {"id": "evolution-table", "title": "Recursive evolution", "subtitle": "Held-out evaluation and protected autonomous research activation status.", "dataset": "evolution_candidates", "sourceId": "evolution_candidates", "defaultSort": {"field": "candidate_id", "direction": "asc"}, "columns": [{"field": "candidate_id", "label": "Candidate", "type": "text"}, {"field": "recommended_state", "label": "State", "type": "text"}, {"field": "causal_confidence", "label": "Causal confidence", "format": "percent"}, {"field": "held_out", "label": "Held out", "type": "boolean"}, {"field": "promotion_allowed", "label": "Research active", "type": "boolean"}]},
        {"id": "intelligence-table", "title": "Intelligence research laboratory", "subtitle": "Unknowns and failures converted into testable cognitive-method questions.", "dataset": "intelligence_discoveries", "sourceId": "intelligence_discoveries", "defaultSort": {"field": "priority", "direction": "desc"}, "columns": [{"field": "question_id", "label": "Question", "type": "text"}, {"field": "signal_type", "label": "Source", "type": "text"}, {"field": "domain_id", "label": "Experimental domain", "type": "text"}, {"field": "priority", "label": "Priority", "format": "percent"}, {"field": "method_count", "label": "Methods", "format": "number"}]},
        {"id": "cognitive-evaluation-table", "title": "Cognitive-method promotion gates", "subtitle": "Independent evidence state and autonomous threshold decision for every method.", "dataset": "cognitive_method_evaluations", "sourceId": "cognitive_method_evaluations", "defaultSort": {"field": "method_id", "direction": "asc"}, "columns": [{"field": "method_id", "label": "Method", "type": "text"}, {"field": "promotion_state", "label": "State", "type": "text"}, {"field": "failed_threshold_count", "label": "Failed gates", "format": "number"}, {"field": "activation_allowed", "label": "Research active", "type": "boolean"}]},
        {"id": "constitution-table", "title": "Sealed constitution", "subtitle": "Execution and permission boundaries are non-evolvable.", "dataset": "constitution_invariants", "sourceId": "constitution_invariants", "defaultSort": {"field": "invariant", "direction": "asc"}, "columns": [{"field": "invariant", "label": "Invariant", "type": "text"}, {"field": "state", "label": "State", "type": "boolean"}, {"field": "sealed", "label": "Sealed", "type": "boolean"}]},
        {"id": "source-table", "title": "Artifact source health", "subtitle": "Every dashboard surface resolves to an inspected local artifact.", "dataset": "source_health", "sourceId": "source_health", "defaultSort": {"field": "source", "direction": "asc"}, "columns": [{"field": "source", "label": "Source", "type": "text"}, {"field": "path", "label": "Path", "type": "text"}, {"field": "status", "label": "Status", "type": "text"}, {"field": "observed_at", "label": "Observed", "type": "text"}]},
        {"id": "time-proof-table", "title": "Point-in-time input proofs", "subtitle": "Timestamp, freshness, and evidence-use status for every material context input.", "dataset": "point_in_time_inputs", "sourceId": "point_in_time_inputs", "defaultSort": {"field": "input", "direction": "asc"}, "columns": [{"field": "input", "label": "Input", "type": "text"}, {"field": "status", "label": "Status", "type": "text"}, {"field": "timestamp", "label": "Timestamp", "type": "text"}, {"field": "age_hours", "label": "Age hours", "format": "number"}, {"field": "maximum_age_hours", "label": "Max age hours", "format": "number"}, {"field": "used_as_evidence", "label": "Used", "type": "boolean"}]},
        {"id": "threshold-control-table", "title": "Autonomous threshold control", "subtitle": "Routing and abstention decisions are fail-closed and cannot promote or execute.", "dataset": "threshold_control", "sourceId": "threshold_control", "defaultSort": {"field": "policy_id", "direction": "asc"}, "columns": [{"field": "policy_id", "label": "Policy", "type": "text"}, {"field": "decision", "label": "Decision", "type": "text"}, {"field": "passed", "label": "Passed", "type": "boolean"}, {"field": "missing_metric_count", "label": "Missing metrics", "format": "number"}, {"field": "failed_rule_count", "label": "Failed rules", "format": "number"}, {"field": "positive_promotion_allowed", "label": "Can promote", "type": "boolean"}]},
        {"id": "strategy-engineering-table", "title": "Strategy engineering laboratory", "subtitle": "Association hypotheses and quality-diverse challengers remain shadow-only until protected evidence matures.", "dataset": "strategy_engineering", "sourceId": "strategy_engineering", "defaultSort": {"field": "cycle_status", "direction": "asc"}, "columns": [{"field": "cycle_status", "label": "Cycle", "type": "text"}, {"field": "reverse_status", "label": "Reverse status", "type": "text"}, {"field": "settled_case_count", "label": "Settled cases", "format": "number"}, {"field": "reverse_hypothesis_count", "label": "Hypotheses", "format": "number"}, {"field": "forward_candidate_count", "label": "Candidates", "format": "number"}, {"field": "quality_diversity_cells", "label": "Diversity cells", "format": "number"}, {"field": "shadow_admitted_count", "label": "Shadow admitted", "format": "number"}, {"field": "positive_promotion_allowed", "label": "Can promote", "type": "boolean"}]},
    ]
    status_body = (
        f"## Operating state\n\n"
        f"**{str(readiness.get('readiness_status', 'unknown')).upper()}** — research is paper-only, live remains blocked, "
        f"and the current control is **{str(summary.get('final_research_control', 'UNKNOWN'))}**. "
        f"The next prediction cannot be graded before **{str(summary.get('minimum_settlement_date', 'unknown'))}**."
    )
    caveat_body = (
        "## Evidence boundaries\n\n"
        "Unknown market dimensions remain explicit. Options dealer evidence is not synthesized. "
        "No historical replay is counted as forward proof, and no candidate may grade or activate itself. "
        "Qualified research activation is automatic only after independent symbol, strategy, and pair gates. "
        "The intelligence laboratory may evolve cognitive methods, never truth, verification, authority, or permissions; live execution remains structurally unavailable."
    )
    blocks = [
        {"id": "status", "type": "markdown", "body": status_body, "sourceId": "readiness"},
        {"id": "hero", "type": "metric-strip", "cardIds": [card["id"] for card in cards]},
        {"id": "world", "type": "chart", "chartId": "world-chart"},
        {"id": "world-detail", "type": "table", "tableId": "regime-table"},
        {"id": "confidence", "type": "chart", "chartId": "confidence-chart"},
        {"id": "hypotheses", "type": "chart", "chartId": "hypothesis-chart"},
        {"id": "agents", "type": "table", "tableId": "agent-table"},
        {"id": "shadows", "type": "table", "tableId": "shadow-table"},
        {"id": "health", "type": "chart", "chartId": "health-chart"},
        {"id": "evolution", "type": "table", "tableId": "evolution-table"},
        {"id": "intelligence", "type": "table", "tableId": "intelligence-table"},
        {"id": "cognitive-evaluations", "type": "table", "tableId": "cognitive-evaluation-table"},
        {"id": "constitution", "type": "table", "tableId": "constitution-table"},
        {"id": "boundaries", "type": "markdown", "body": caveat_body},
        {"id": "sources", "type": "table", "tableId": "source-table"},
        {"id": "time-proofs", "type": "table", "tableId": "time-proof-table"},
    ]
    artifact = {
        "surface": "dashboard",
        "manifest": {
            "version": 1,
            "surface": "dashboard",
            "title": "DOPEY Sovereign Research Observatory",
            "description": "Local, paper-only operating view of market research, intelligence-method experiments, uncertainty, settlement, evolution, and constitutional boundaries.",
            "generatedAt": generated_at,
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": sources,
            "blocks": blocks,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": datasets,
            "accessIssues": [],
        },
        "sources": sources,
        "package_info": {
            "paper_only": True,
            "live_blocked": True,
            "readiness_status": str(readiness.get("readiness_status", "unknown")),
            "action_ready": False,
        },
    }
    _validate_artifact_references(artifact)
    return artifact


def write_observatory_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    _validate_artifact_references(artifact)
    _write_object(path, artifact)
