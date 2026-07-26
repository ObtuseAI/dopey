"""Auditable mutation genealogy and bounded search-budget telemetry."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence, cast


MUTATION_EXPLORER_VERSION = "dopey-mutation-genealogy-explorer-v2"
MAX_GRAPH_NODES = 72


def build_mutation_genealogy(
    mutation_registry_path: Path,
    dossier_summary_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Build a compact graph without pretending noisy strategy search is A*."""

    registry_records = list(_read_jsonl_objects(mutation_registry_path))
    if not registry_records:
        raise ValueError(f"mutation registry is empty: path={mutation_registry_path}")
    latest = registry_records[-1]
    scorecards = _object_list(latest.get("scorecards"), "scorecards")
    ranking = _object_list(latest.get("ranking"), "ranking")
    decisions = _string_mapping(latest.get("promotion_decisions"), "promotion_decisions")
    ranking_by_id = {str(record.get("strategy_id", "")): record for record in ranking}
    rejected_reasons = _rejected_reason_mapping(latest.get("rejected_mutations"))
    dossier = _read_optional_json_object(dossier_summary_path)

    nodes = _build_nodes(scorecards, ranking_by_id, decisions, rejected_reasons)
    roots = _root_nodes(nodes)
    all_nodes = roots + nodes
    edges = [
        {
            "edge_id": _stable_hash({"parent_id": node["parent_id"], "child_id": node["node_id"]})[:16],
            "parent_id": node["parent_id"],
            "child_id": node["node_id"],
            "mutation_type": node["mutation_type"],
            "status": node["status"],
        }
        for node in nodes
        if str(node["parent_id"])
    ]
    duplicate_groups = _duplicate_groups(nodes)
    frontier_ids = _mutation_pareto_frontier(nodes)
    historical_budget = _historical_search_budget(registry_records)
    generation_history = _generation_history(registry_records)
    champion_dynamics = _champion_dynamics(generation_history)
    historical_mechanisms = _historical_mechanism_statistics(registry_records)
    historical_family_budgets = _historical_family_budgets(registry_records)
    current_budget = _current_generation_budget(nodes, rejected_reasons)
    family_budgets = _family_budgets(nodes, current_budget)
    visible_nodes = _select_visible_nodes(all_nodes, frontier_ids)
    visible_ids = {str(node["node_id"]) for node in visible_nodes}
    visible_edges = [
        edge for edge in edges
        if str(edge["parent_id"]) in visible_ids and str(edge["child_id"]) in visible_ids
    ]
    status_counts = Counter(str(node["status"]) for node in nodes)
    result: dict[str, object] = {
        "artifact_type": "mutation_genealogy_explorer",
        "explorer_version": MUTATION_EXPLORER_VERSION,
        "explorer_status": "complete",
        "search_method": "deterministic_bounded_mutation_graph_not_a_star",
        "search_method_reason": "strategy objectives are noisy and discontinuous; no admissible distance-to-optimum heuristic is claimed",
        "registry_record_count": len(registry_records),
        "latest_batch_id": str(latest.get("batch_id", "unknown")),
        "node_count": len(all_nodes),
        "edge_count": len(edges),
        "visible_node_count": len(visible_nodes),
        "visible_edge_count": len(visible_edges),
        "status_counts": dict(sorted(status_counts.items())),
        "historical_search_budget": historical_budget,
        "generation_history": generation_history,
        "champion_dynamics": champion_dynamics,
        "historical_mechanism_statistics": historical_mechanisms,
        "historical_family_budgets": historical_family_budgets,
        "current_generation_budget": current_budget,
        "family_budgets": family_budgets,
        "duplicate_groups": duplicate_groups,
        "duplicate_candidate_count": sum(len(group["node_ids"]) - 1 for group in duplicate_groups),
        "mutation_pareto_frontier_ids": sorted(frontier_ids),
        "dossier_frontier_status": str(dossier.get("frontier_status", "unavailable")),
        "dossier_frontier_candidate_ids": list(dossier.get("frontier_candidate_ids", [])),
        "nodes": visible_nodes,
        "edges": visible_edges,
        "pruned_branch_count": sum(1 for node in nodes if str(node["status"]) in {"rejected", "degraded"}),
        "selection_law": "frontier_is_diagnostic_and_never_overrides_truth_or_promotion_gates",
        "paper_only": True,
        "live_blocked": True,
        "promotion_allowed": False,
    }
    result["explorer_hash"] = _stable_hash(result)
    _write_json_atomic(output_path, result)
    return result


def _build_nodes(
    scorecards: Sequence[dict[str, object]],
    ranking_by_id: Mapping[str, dict[str, object]],
    decisions: Mapping[str, str],
    rejected_reasons: Mapping[str, list[str]],
) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    known_ids: set[str] = set()
    for scorecard in scorecards:
        strategy_id = str(scorecard.get("strategy_id", ""))
        if not strategy_id:
            raise ValueError("mutation scorecard is missing strategy_id")
        known_ids.add(strategy_id)
        ranking = ranking_by_id.get(strategy_id, {})
        parameters = ranking.get("parameters", {}) if isinstance(ranking.get("parameters"), dict) else {}
        status = decisions.get(strategy_id, str(scorecard.get("promotion_decision", "unknown")))
        reasons = [str(value) for value in scorecard.get("reasons", [])] if isinstance(scorecard.get("reasons"), list) else []
        reasons.extend(rejected_reasons.get(strategy_id, []))
        nodes.append(_node_record(strategy_id, scorecard, ranking, cast(dict[str, object], parameters), status, reasons))
    for strategy_id, reasons in sorted(rejected_reasons.items()):
        if strategy_id in known_ids:
            continue
        parent_id = _infer_parent_id(strategy_id)
        nodes.append({
            "node_id": strategy_id,
            "parent_id": parent_id,
            "family": _infer_family(strategy_id),
            "mutation_type": "constitutionally_rejected_before_scoring",
            "mutation_id": strategy_id.removeprefix(parent_id + "-") if parent_id else strategy_id,
            "status": "rejected",
            "score": None,
            "score_delta": None,
            "walk_forward_score": None,
            "robustness_score": None,
            "liquidity_score": None,
            "failure_penalty": None,
            "reasons": sorted(set(reasons)),
            "behavior_signature": _stable_hash({"family": _infer_family(strategy_id), "reasons": sorted(reasons)}),
            "live_allowed": False,
            "defined_risk_only": True,
            "paper_only": True,
            "live_blocked": True,
        })
    return sorted(nodes, key=lambda node: (str(node["family"]), str(node["parent_id"]), str(node["node_id"])))


def _node_record(
    strategy_id: str,
    scorecard: Mapping[str, object],
    ranking: Mapping[str, object],
    parameters: Mapping[str, object],
    status: str,
    reasons: Sequence[str],
) -> dict[str, object]:
    parent_id = str(scorecard.get("parent_strategy_id", ranking.get("parent_genome_id", "")))
    family = str(scorecard.get("family", ranking.get("strategy_family", "unknown")))
    behavior = {
        key: value
        for key, value in parameters.items()
        if key not in {
            "mutation_parent_id", "mutation_id", "mutation_type", "mutation_rationale",
            "proof_score_placeholder", "forbidden_live_targets", "promotion_tier",
        }
    }
    return {
        "node_id": strategy_id,
        "parent_id": parent_id,
        "family": family,
        "mutation_type": str(ranking.get("mutation_type", parameters.get("mutation_type", "unknown"))),
        "mutation_id": str(ranking.get("mutation_id", parameters.get("mutation_id", "unknown"))),
        "status": status,
        "score": _optional_float(scorecard.get("adjusted_score", ranking.get("population_adjusted_score"))),
        "score_delta": _optional_float(scorecard.get("score_delta", ranking.get("population_score_delta"))),
        "walk_forward_score": _optional_float(ranking.get("walk_forward_overall")),
        "robustness_score": _optional_float(ranking.get("slippage_robustness_score")),
        "liquidity_score": _optional_float(ranking.get("average_liquidity_score")),
        "failure_penalty": _optional_float(scorecard.get("failure_constraint_penalty")),
        "reasons": sorted(set(reasons)),
        "behavior_signature": _stable_hash({"family": family, "behavior": behavior}),
        "live_allowed": False,
        "defined_risk_only": bool(ranking.get("defined_risk_only", True)),
        "paper_only": True,
        "live_blocked": True,
    }


def _root_nodes(nodes: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    child_ids = {str(node["node_id"]) for node in nodes}
    roots: list[dict[str, object]] = []
    for parent_id in sorted({str(node["parent_id"]) for node in nodes if str(node["parent_id"]) and str(node["parent_id"]) not in child_ids}):
        children = [node for node in nodes if str(node["parent_id"]) == parent_id]
        roots.append({
            "node_id": parent_id,
            "parent_id": "",
            "family": str(children[0]["family"]) if children else "unknown",
            "mutation_type": "root_parent",
            "mutation_id": "root",
            "status": "parent",
            "score": None,
            "score_delta": 0.0,
            "walk_forward_score": None,
            "robustness_score": None,
            "liquidity_score": None,
            "failure_penalty": None,
            "reasons": ["immutable_generation_parent"],
            "behavior_signature": _stable_hash({"parent_id": parent_id}),
            "live_allowed": False,
            "defined_risk_only": True,
            "paper_only": True,
            "live_blocked": True,
        })
    return roots


def _duplicate_groups(nodes: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_signature: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        by_signature[str(node["behavior_signature"])].append(str(node["node_id"]))
    return [
        {"behavior_signature": signature, "node_ids": sorted(node_ids), "duplicate_count": len(node_ids)}
        for signature, node_ids in sorted(by_signature.items())
        if len(node_ids) > 1
    ]


def _mutation_pareto_frontier(nodes: Sequence[dict[str, object]]) -> set[str]:
    comparable = [node for node in nodes if node["score"] is not None and str(node["status"]) != "rejected"]
    dimensions = ("score", "walk_forward_score", "robustness_score", "liquidity_score")
    frontier: set[str] = set()
    for node in comparable:
        dominated = False
        for challenger in comparable:
            if challenger is node:
                continue
            pairs = [
                (float(challenger[key]), float(node[key]))
                for key in dimensions
                if challenger[key] is not None and node[key] is not None
            ]
            if pairs and all(left >= right for left, right in pairs) and any(left > right for left, right in pairs):
                dominated = True
                break
        if not dominated:
            frontier.add(str(node["node_id"]))
    return frontier


def _historical_search_budget(records: Sequence[dict[str, object]]) -> dict[str, object]:
    generated = sum(int(record.get("mutations_generated", 0)) for record in records)
    valid = sum(int(record.get("mutations_valid", 0)) for record in records)
    rejected = sum(int(record.get("mutations_rejected", 0)) for record in records)
    return {
        "generation_count": len(records),
        "mutation_attempt_count": generated,
        "valid_mutation_count": valid,
        "rejected_mutation_count": rejected,
        "valid_rate": round(valid / generated, 6) if generated else 0.0,
        "trial_accounting_complete": generated == valid + rejected,
    }


def _generation_history(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    history: list[dict[str, object]] = []
    for generation_index, record in enumerate(records, start=1):
        raw_decisions = record.get("promotion_decisions", {})
        decisions = (
            {str(key): str(value) for key, value in raw_decisions.items()}
            if isinstance(raw_decisions, dict)
            else {}
        )
        comparison = record.get("parent_vs_mutation_comparison", {})
        comparison_record = cast(dict[str, object], comparison) if isinstance(comparison, dict) else {}
        raw_families = record.get("family_coverage", [])
        families = sorted(str(value) for value in raw_families) if isinstance(raw_families, list) else []
        statuses = Counter(decisions.values())
        history.append({
            "generation_index": generation_index,
            "batch_id": str(record.get("batch_id", f"generation-{generation_index}")),
            "record_hash": _stable_hash(record),
            "mutations_generated": int(record.get("mutations_generated", 0)),
            "mutations_valid": int(record.get("mutations_valid", 0)),
            "mutations_rejected": int(record.get("mutations_rejected", 0)),
            "family_coverage": families,
            "family_count": len(families),
            "champion_strategy_id": str(record.get("best_mutated_strategy_id", "")),
            "champion_score": _optional_float(comparison_record.get("best_mutated_score")),
            "parent_score": _optional_float(comparison_record.get("parent_score")),
            "champion_score_delta": _optional_float(comparison_record.get("score_delta")),
            "decision_status_counts": dict(sorted(statuses.items())),
        })
    return history


def _champion_dynamics(history: Sequence[dict[str, object]]) -> dict[str, object]:
    champions = [str(record["champion_strategy_id"]) for record in history if str(record["champion_strategy_id"])]
    changes = sum(1 for previous, current in zip(champions, champions[1:]) if previous != current)
    longest_streak = 0
    current_streak = 0
    previous = ""
    for champion in champions:
        current_streak = current_streak + 1 if champion == previous else 1
        longest_streak = max(longest_streak, current_streak)
        previous = champion
    counts = Counter(champions)
    return {
        "observed_champion_generation_count": len(champions),
        "unique_champion_count": len(counts),
        "champion_change_count": changes,
        "champion_change_rate": round(changes / max(len(champions) - 1, 1), 6) if champions else 0.0,
        "longest_champion_streak": longest_streak,
        "current_champion_id": champions[-1] if champions else "",
        "current_champion_recurrence_count": counts.get(champions[-1], 0) if champions else 0,
        "champion_frequency": [
            {"strategy_id": strategy_id, "generation_count": count}
            for strategy_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "stability_claim_allowed": False,
        "reason": "registry recurrence is search telemetry and not held-out or forward evidence",
    }


def _historical_mechanism_statistics(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    attempts: Counter[str] = Counter()
    statuses_by_mechanism: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        decisions_raw = record.get("promotion_decisions", {})
        decisions = cast(dict[str, object], decisions_raw) if isinstance(decisions_raw, dict) else {}
        ranking_raw = record.get("ranking", [])
        ranking = cast(list[object], ranking_raw) if isinstance(ranking_raw, list) else []
        ranked_ids: set[str] = set()
        for raw_candidate in ranking:
            if not isinstance(raw_candidate, dict):
                continue
            candidate = cast(dict[str, object], raw_candidate)
            strategy_id = str(candidate.get("strategy_id", ""))
            mechanism = str(candidate.get("mutation_type", "unknown"))
            attempts[mechanism] += 1
            statuses_by_mechanism[mechanism][str(decisions.get(strategy_id, "unclassified"))] += 1
            ranked_ids.add(strategy_id)
        for strategy_id, status in decisions.items():
            if strategy_id in ranked_ids:
                continue
            attempts["constitutionally_rejected_before_scoring"] += 1
            statuses_by_mechanism["constitutionally_rejected_before_scoring"][str(status)] += 1
    return [
        {
            "mutation_type": mechanism,
            "attempt_count": attempt_count,
            "decision_status_counts": dict(sorted(statuses_by_mechanism[mechanism].items())),
            "champion_count": statuses_by_mechanism[mechanism].get("offline_mutation_champion", 0),
            "rejected_count": statuses_by_mechanism[mechanism].get("rejected", 0),
        }
        for mechanism, attempt_count in sorted(attempts.items())
    ]


def _historical_family_budgets(records: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    allocations: Counter[str] = Counter()
    total = 0
    for record in records:
        scorecards_raw = record.get("scorecards", [])
        scorecards = cast(list[object], scorecards_raw) if isinstance(scorecards_raw, list) else []
        for raw_scorecard in scorecards:
            if not isinstance(raw_scorecard, dict):
                continue
            family = str(raw_scorecard.get("family", "unknown"))
            allocations[family] += 1
            total += 1
    return [
        {
            "family": family,
            "scored_candidate_count": count,
            "allocation_share": round(count / total, 6) if total else 0.0,
            "concentration_alert": count / total > 0.4 if total else False,
        }
        for family, count in sorted(allocations.items())
    ]


def _current_generation_budget(
    nodes: Sequence[dict[str, object]],
    rejected_reasons: Mapping[str, list[str]],
) -> dict[str, object]:
    attempted = len(nodes)
    rejected = len(rejected_reasons)
    signatures = {str(node["behavior_signature"]) for node in nodes}
    novelty_rate = len(signatures) / attempted if attempted else 0.0
    return {
        "attempted_candidates": attempted,
        "constitutionally_rejected_candidates": rejected,
        "unique_behavior_signatures": len(signatures),
        "novelty_rate": round(novelty_rate, 6),
        "duplicate_rate": round(1.0 - novelty_rate, 6),
        "budget_exhaustion_status": "observed_generation_complete",
        "heuristic_claim": "none",
    }


def _family_budgets(
    nodes: Sequence[dict[str, object]],
    current_budget: Mapping[str, object],
) -> list[dict[str, object]]:
    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    for node in nodes:
        by_family[str(node["family"])].append(node)
    attempted = max(int(current_budget["attempted_candidates"]), 1)
    rows: list[dict[str, object]] = []
    for family, family_nodes in sorted(by_family.items()):
        statuses = Counter(str(node["status"]) for node in family_nodes)
        rows.append({
            "family": family,
            "attempt_count": len(family_nodes),
            "allocation_share": round(len(family_nodes) / attempted, 6),
            "frontier_candidate_count": sum(1 for node in family_nodes if str(node["status"]) == "offline_mutation_champion"),
            "rejected_count": statuses.get("rejected", 0),
            "degraded_count": statuses.get("degraded", 0),
            "concentration_alert": len(family_nodes) / attempted > 0.4,
        })
    return rows


def _select_visible_nodes(nodes: Sequence[dict[str, object]], frontier_ids: set[str]) -> list[dict[str, object]]:
    priority = sorted(
        nodes,
        key=lambda node: (
            0 if str(node["node_id"]) in frontier_ids else 1,
            0 if str(node["status"]) in {"offline_mutation_champion", "parent", "rejected"} else 1,
            -float(node["score"] or -math.inf),
            str(node["node_id"]),
        ),
    )
    selected = priority[:MAX_GRAPH_NODES]
    selected_ids = {str(node["node_id"]) for node in selected}
    missing_parents = {
        str(node["parent_id"])
        for node in selected
        if str(node["parent_id"]) and str(node["parent_id"]) not in selected_ids
    }
    parents = [node for node in nodes if str(node["node_id"]) in missing_parents]
    return sorted((selected + parents)[:MAX_GRAPH_NODES], key=lambda node: (str(node["family"]), str(node["parent_id"]), str(node["node_id"])))


def _rejected_reason_mapping(value: object) -> dict[str, list[str]]:
    records = value if isinstance(value, list) else [value]
    result: dict[str, list[str]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        reasons = record.get("reasons_by_id", {})
        if not isinstance(reasons, dict):
            continue
        for strategy_id, raw_values in reasons.items():
            if isinstance(raw_values, list):
                result[str(strategy_id)] = [str(item) for item in raw_values]
    return result


def _infer_parent_id(strategy_id: str) -> str:
    marker = "-mut-"
    return strategy_id.split(marker, 1)[0] if marker in strategy_id else ""


def _infer_family(strategy_id: str) -> str:
    prefix = "genome-"
    normalized = strategy_id.removeprefix(prefix)
    marker = "-spy-fixture"
    return normalized.split(marker, 1)[0].replace("-", "_") if marker in normalized else "unknown"


def _object_list(value: object, field: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(f"mutation registry field must be an array of objects: field={field}")
    return [cast(dict[str, object], item) for item in value]


def _string_mapping(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError(f"mutation registry field must be an object: field={field}")
    return {str(key): str(item) for key, item in value.items()}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"mutation explorer metric must be numeric or null: value={value!r}")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"mutation explorer metric must be finite: value={value!r}")
    return round(numeric, 6)


def _read_jsonl_objects(path: Path) -> Iterable[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"mutation registry is missing: path={path}")
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
                raise TypeError(f"mutation registry row must be an object: path={path}, line={line_number}")
            yield cast(dict[str, object], parsed)


def _read_optional_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"mutation explorer optional source must be an object: path={path}")
    return cast(dict[str, object], parsed)


def _stable_hash(record: Mapping[str, object]) -> str:
    normalized = {key: value for key, value in record.items() if not key.endswith("_hash")}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
