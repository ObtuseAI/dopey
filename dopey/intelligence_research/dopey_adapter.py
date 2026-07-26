"""Translate DOPEY operating evidence into domain-neutral cognitive signals."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash
from dopey.protocols.status_semantics import classify_operational_status

from .schema import CognitiveKnowledgeState, KnowledgeSignal, KnowledgeSignalType
from .task_store import EXPERIMENTAL_DOMAINS


def _load_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, f"missing:{path}"
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"DOPEY intelligence adapter requires a JSON object: path={path}")
    return raw, f"artifact:{canonical_hash(raw)}"


def _signal(
    signal_type: KnowledgeSignalType,
    statement: str,
    severity: float,
    novelty: float,
    expected_reuse: float,
    evidence_ids: tuple[str, ...],
) -> KnowledgeSignal:
    identity = canonical_hash(
        {
            "signal_type": signal_type.value,
            "domain_id": "dopey_market_research",
            "statement": statement,
            "evidence_ids": evidence_ids,
        }
    )
    return {
        "signal_id": f"knowledge-signal:{identity[:24]}",
        "signal_type": signal_type,
        "domain_id": "dopey_market_research",
        "statement": statement,
        "severity": severity,
        "novelty": novelty,
        "expected_reuse": expected_reuse,
        "evidence_ids": evidence_ids,
    }


def _operational_artifact_paths(
    schedule_state_path: Path,
) -> dict[str, Path]:
    acceleration_root = schedule_state_path.parent
    dopey_artifact_root = acceleration_root.parent
    return {
        "system_snapshot": acceleration_root / "system_snapshot.json",
        "reliability_slo": dopey_artifact_root
        / "ops"
        / "reliability_slo.json",
        "nightly": dopey_artifact_root / "nightly" / "nightly_latest.json",
    }


def _append_operational_health_signals(
    signals: list[KnowledgeSignal],
    schedule_state_path: Path,
) -> None:
    paths = _operational_artifact_paths(schedule_state_path)
    snapshot, snapshot_id = _load_object(paths["system_snapshot"])
    if snapshot is not None:
        if snapshot.get("snapshot_status") != "consistent":
            signals.append(
                _signal(
                    KnowledgeSignalType.CONTRADICTION,
                    "system snapshot contains mixed-generation source projections",
                    0.95,
                    0.6,
                    1.0,
                    (snapshot_id,),
                )
            )
        pressure = snapshot.get("storage_pressure")
        if isinstance(pressure, dict) and pressure.get(
            "pressure_level"
        ) in {"ELEVATED", "CRITICAL"}:
            level = str(pressure["pressure_level"])
            signals.append(
                _signal(
                    KnowledgeSignalType.REPEATED_FAILURE,
                    (
                        f"storage pressure is {level.lower()} with "
                        f"{int(pressure.get('free_bytes', 0))} free bytes"
                    ),
                    1.0 if level == "CRITICAL" else 0.75,
                    0.45,
                    1.0,
                    (snapshot_id,),
                )
            )
    reliability, reliability_id = _load_object(paths["reliability_slo"])
    if (
        reliability is not None
        and reliability.get("slo_status") != "within_error_budget"
    ):
        signals.append(
            _signal(
                KnowledgeSignalType.REPEATED_FAILURE,
                (
                    "reliability SLO is "
                    f"{reliability.get('slo_status', 'unknown')}"
                ),
                0.95,
                0.45,
                1.0,
                (reliability_id,),
            )
        )
    nightly, nightly_id = _load_object(paths["nightly"])
    if nightly is not None:
        suite = nightly.get("suite")
        suite_status = (
            str(suite.get("suite_status", "unknown"))
            if isinstance(suite, dict)
            else "unknown"
        )
        if suite_status != "complete_green":
            signals.append(
                _signal(
                    KnowledgeSignalType.REPEATED_FAILURE,
                    f"nightly validation is {suite_status}",
                    0.90,
                    0.45,
                    0.95,
                    (nightly_id,),
                )
            )


def build_dopey_knowledge_state(
    readiness_path: Path,
    schedule_state_path: Path,
    autoresearch_path: Path,
    promotion_cycle_path: Path,
    llm_research_path: Path,
    observed_at: datetime,
) -> CognitiveKnowledgeState:
    if observed_at.tzinfo is None:
        raise ValueError("DOPEY knowledge-state observed_at must be timezone-aware")
    readiness, readiness_id = _load_object(readiness_path)
    schedule, schedule_id = _load_object(schedule_state_path)
    autoresearch, autoresearch_id = _load_object(autoresearch_path)
    promotion, promotion_id = _load_object(promotion_cycle_path)
    llm_research, llm_research_id = _load_object(llm_research_path)
    signals: list[KnowledgeSignal] = []
    if readiness is None:
        signals.append(_signal(KnowledgeSignalType.UNKNOWN, "operational readiness state is unavailable", 0.9, 0.2, 0.8, (readiness_id,)))
    else:
        bottlenecks = readiness.get("bottlenecks", [])
        if not isinstance(bottlenecks, list):
            raise ValueError(f"readiness bottlenecks must be an array: path={readiness_path}")
        for record in bottlenecks:
            if not isinstance(record, dict):
                raise ValueError(f"readiness bottleneck must be an object: path={readiness_path}")
            required = max(int(record.get("required", 1) or 1), 1)
            raw_remaining = record.get("remaining", required)
            remaining = max(
                int(required if raw_remaining is None else raw_remaining),
                0,
            )
            if remaining == 0:
                continue
            severity = min(1.0, remaining / required)
            statement = f"readiness bottleneck {record.get('bottleneck_id', 'unknown')} remains unresolved"
            signals.append(_signal(KnowledgeSignalType.BOTTLENECK, statement, severity, 0.4, 0.8, (readiness_id,)))
    if schedule is None:
        signals.append(_signal(KnowledgeSignalType.UNKNOWN, "research schedule state is unavailable", 0.7, 0.2, 0.7, (schedule_id,)))
    else:
        lane_statuses = schedule.get("lane_statuses", {})
        if not isinstance(lane_statuses, dict):
            raise ValueError(f"schedule lane_statuses must be an object: path={schedule_state_path}")
        for lane_id, record in sorted(lane_statuses.items()):
            if not isinstance(record, dict):
                continue
            raw_status = str(record.get("status", "unknown"))
            assessment = classify_operational_status(raw_status)
            if assessment["failure_signal"]:
                severity_by_class = {
                    "DEGRADED": 0.70,
                    "FAILED": 0.90,
                    "BLOCKED": 0.85,
                }
                severity = severity_by_class[assessment["status_class"].value]
                evidence_status = str(
                    (
                        record.get("evidence_verification", {})
                        if isinstance(record.get("evidence_verification"), dict)
                        else {}
                    ).get("verification_status", "unknown")
                )
                signals.append(
                    _signal(
                        KnowledgeSignalType.REPEATED_FAILURE,
                        (
                            f"research lane {lane_id} is {raw_status}; "
                            f"evidence verification is {evidence_status}"
                        ),
                        severity,
                        0.5,
                        0.85,
                        (schedule_id,),
                    )
                )
    _append_operational_health_signals(signals, schedule_state_path)
    if autoresearch is None:
        signals.append(_signal(KnowledgeSignalType.CAPABILITY_GAP, "strategy invention evidence is unavailable", 0.8, 0.5, 0.8, (autoresearch_id,)))
    else:
        candidate_count = int(autoresearch.get("candidate_count", 0) or 0)
        if autoresearch.get("finding_status") == "missing_findings_exploration_only":
            signals.append(
                _signal(
                    KnowledgeSignalType.UNKNOWN,
                    "strategy invention is not yet receiving settlement, calibration, failure, or backtest findings",
                    0.9,
                    0.7,
                    0.95,
                    (autoresearch_id,),
                )
            )
        if candidate_count > 0:
            signals.append(
                _signal(
                    KnowledgeSignalType.OPPORTUNITY,
                    f"{candidate_count} experimental strategies can become tasks for comparative cognitive-method research",
                    0.6,
                    0.8,
                    0.9,
                    (autoresearch_id,),
                )
            )
    if promotion is None or promotion.get("cycle_status") == "missing_promotion_evidence":
        signals.append(
            _signal(
                KnowledgeSignalType.CAPABILITY_GAP,
                "the system can invent candidates but cannot yet synthesize promotion evidence from independent evaluation",
                1.0,
                0.8,
                1.0,
                (promotion_id,),
            )
        )
    if autoresearch is not None and promotion is not None:
        if int(autoresearch.get("candidate_count", 0) or 0) > 0 and promotion.get("cycle_status") == "missing_promotion_evidence":
            signals.append(
                _signal(
                    KnowledgeSignalType.CONTRADICTION,
                    "candidate generation is operational while independent evidence synthesis is absent",
                    0.95,
                    0.75,
                    1.0,
                    (autoresearch_id, promotion_id),
                )
            )
    if llm_research is None:
        signals.append(
            _signal(
                KnowledgeSignalType.CAPABILITY_GAP,
                "frontier-model research deliberation is unavailable",
                0.65,
                0.55,
                0.75,
                (llm_research_id,),
            )
        )
    else:
        if llm_research.get("cycle_status") != "complete_analysis_current":
            signals.append(
                _signal(
                    KnowledgeSignalType.REPEATED_FAILURE,
                    "frontier-model research deliberation is not in a complete current state",
                    0.8,
                    0.5,
                    0.8,
                    (llm_research_id,),
                )
            )
        synthesis_council = llm_research.get("synthesis_council")
        if isinstance(synthesis_council, dict):
            results = synthesis_council.get("results")
            if isinstance(results, list):
                for result in results[:1]:
                    if not isinstance(result, dict):
                        continue
                    analysis = result.get("structured_analysis")
                    if not isinstance(analysis, dict):
                        continue
                    experiments = analysis.get("recommended_experiments")
                    if isinstance(experiments, list):
                        for experiment in experiments[:4]:
                            if not isinstance(experiment, dict):
                                continue
                            title = str(experiment.get("title", "unnamed experiment"))
                            signals.append(
                                _signal(
                                    KnowledgeSignalType.OPPORTUNITY,
                                    f"unverified LLM research hypothesis proposes experiment: {title}",
                                    0.55,
                                    0.85,
                                    0.75,
                                    (llm_research_id,),
                                )
                            )
                    uncertainties = analysis.get("uncertainties")
                    if isinstance(uncertainties, list):
                        for uncertainty in uncertainties[:4]:
                            signals.append(
                                _signal(
                                    KnowledgeSignalType.UNKNOWN,
                                    f"LLM-identified uncertainty requiring non-model evidence: {str(uncertainty)}",
                                    0.7,
                                    0.7,
                                    0.8,
                                    (llm_research_id,),
                                )
                            )
    state_body = {
        "observed_at": observed_at.isoformat(),
        "signal_ids": sorted(signal["signal_id"] for signal in signals),
        "protected_constraints": (
            "truth_is_non_evolvable",
            "verification_is_non_evolvable",
            "authority_is_non_evolvable",
            "permissions_are_non_evolvable",
            "candidate_cannot_grade_itself",
            "llm_output_is_unverified_hypothesis_only",
        ),
        "experimental_domain_ids": EXPERIMENTAL_DOMAINS,
    }
    return {
        "state_id": f"cognitive-state:{canonical_hash(state_body)[:24]}",
        "observed_at": observed_at.isoformat(),
        "signals": tuple(signals),
        "protected_constraints": state_body["protected_constraints"],
        "experimental_domain_ids": state_body["experimental_domain_ids"],
    }
