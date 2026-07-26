"""Optional analysis-only frontier council adapters."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from .provider_control import (
    ProviderControlError,
    openrouter_credential_status,
    resolve_openrouter_api_key,
)


ALLOWED_PROVIDERS = (
    "openrouter_four_model_hybrid",
)
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MAX_ATTEMPTS = 2
OPENROUTER_MAX_COMPONENT_PROMPT_BYTES = 48_000
OPENROUTER_MODELS = {
    "openrouter_gemini_3_6_flash": "google/gemini-3.6-flash",
    "openrouter_luna_5_6": "openai/gpt-5.6-luna",
    "openrouter_glm_5_2": "z-ai/glm-5.2",
    "openrouter_claude_sonnet_5": "anthropic/claude-sonnet-5",
}
OPENROUTER_REASONING_EFFORTS = {
    "openrouter_gemini_3_6_flash": "medium",
    "openrouter_luna_5_6": "high",
    "openrouter_glm_5_2": "high",
    "openrouter_claude_sonnet_5": "high",
}
OPENROUTER_MAX_TOKENS = {
    "openrouter_gemini_3_6_flash": 6_000,
    "openrouter_luna_5_6": 8_000,
    "openrouter_glm_5_2": 7_000,
    "openrouter_claude_sonnet_5": 8_000,
}
OPENROUTER_HYBRID_PROVIDER = "openrouter_four_model_hybrid"
OPENROUTER_HYBRID_ALIASES = frozenset({"openrouter_gemini_terra_hybrid"})
OPENROUTER_HYBRID_COMPONENTS = (
    "openrouter_gemini_3_6_flash",
    "openrouter_luna_5_6",
    "openrouter_glm_5_2",
    "openrouter_claude_sonnet_5",
)
OPENROUTER_HYBRID_MODEL = " + ".join(
    OPENROUTER_MODELS[provider] for provider in OPENROUTER_HYBRID_COMPONENTS
)
OPENROUTER_COMPONENT_ROLES = {
    "openrouter_gemini_3_6_flash": {
        "role_id": "evidence_mapper",
        "stage_id": "parallel_discovery",
        "mission": (
            "Map observed evidence, missing evidence, freshness, provenance, contradictions, "
            "and decision-relevant state without inventing facts or directional conviction."
        ),
    },
    "openrouter_luna_5_6": {
        "role_id": "hypothesis_scout",
        "stage_id": "parallel_discovery",
        "mission": (
            "Rapidly surface distinct falsifiable hypotheses, mechanisms, horizons, catalysts, "
            "and disconfirming evidence directly from the supplied state."
        ),
    },
    "openrouter_glm_5_2": {
        "role_id": "adversarial_auditor",
        "stage_id": "deep_review",
        "mission": (
            "Attack leakage, overfitting, hidden assumptions, regime dependence, execution gaps, "
            "and unsupported confidence in both the source state and proposed hypotheses."
        ),
    },
    "openrouter_claude_sonnet_5": {
        "role_id": "final_adjudicator",
        "stage_id": "synthesis",
        "mission": (
            "Adjudicate only the validated specialist records, preserve material disagreement, "
            "prefer abstention under unresolved evidence, and emit the final machine contract."
        ),
    },
}
OPENROUTER_ROUTE_PROFILES = (
    {
        "route_id": "risk_and_execution_integrity",
        "priority": 0,
        "signals": (
            "0dte",
            "option",
            "leverage",
            "drawdown",
            "risk",
            "execution",
            "liquidity",
            "slippage",
            "capital",
            "position sizing",
        ),
        "focus": (
            "Lead with loss containment, liquidity, implementation shortfall, lifecycle constraints, "
            "tail behavior, and explicit abstention conditions."
        ),
    },
    {
        "route_id": "market_hypothesis_and_forecast",
        "priority": 1,
        "signals": (
            "predict",
            "forecast",
            "bullish",
            "bearish",
            "long",
            "short",
            "price",
            "market",
            "trade",
            "catalyst",
        ),
        "focus": (
            "Separate observation from forecast, state horizon and invalidation, test competing "
            "bullish and bearish mechanisms, and reject unsupported point-estimate certainty."
        ),
    },
    {
        "route_id": "data_quality_and_evidence",
        "priority": 2,
        "signals": (
            "data",
            "evidence",
            "missing",
            "freshness",
            "provenance",
            "calibration",
            "settlement",
            "sample",
            "leakage",
            "validation",
        ),
        "focus": (
            "Lead with provenance, missingness, frontier alignment, leakage controls, sample adequacy, "
            "calibration, and the smallest evidence acquisition that changes the decision."
        ),
    },
    {
        "route_id": "experiment_and_system_design",
        "priority": 3,
        "signals": (
            "experiment",
            "research",
            "improve",
            "architecture",
            "system",
            "model",
            "strategy",
            "hypothesis",
            "benchmark",
            "ablation",
        ),
        "focus": (
            "Lead with falsifiable mechanisms, controlled comparisons, information gain, reproducible "
            "artifacts, and minimal safe experiments."
        ),
    },
)
OPENROUTER_DEFAULT_ROUTE = {
    "route_id": "general_evidence_ranked_research",
    "priority": 4,
    "signals": (),
    "focus": (
        "Rank claims by source evidence, expose uncertainty and disagreement, and recommend the "
        "smallest safe falsifiable next experiment."
    ),
}


class OpenRouterPaidFailure(RuntimeError):
    """OpenRouter failure carrying non-secret paid-response audit evidence."""

    def __init__(
        self,
        message: str,
        usage: dict[str, int | float],
        paid_response_count: int,
        paid_response_ids: tuple[str, ...],
    ) -> None:
        super().__init__(message)
        self.usage = dict(usage)
        self.paid_response_count = paid_response_count
        self.paid_response_ids = paid_response_ids


CODEX_FRONTIER_MODEL = "gpt-5.6-sol"
CODEX_REASONING_EFFORT = "xhigh"
CLAUDE_FRONTIER_MODEL = "sonnet"
CLAUDE_REASONING_EFFORT = "high"
CLAUDE_MAX_BUDGET_USD = "0.75"
HEAD_COACH_IDS = ("claude", "codex")


def _analysis_contract() -> str:
    return "\n".join(
        [
            "Return only one valid JSON object with no Markdown fence.",
            "Required keys:",
            '- "summary": concise string.',
            '- "hypotheses": array of objects with title, mechanism, evidence_needed, and falsification.',
            '- "adversarial_findings": array of objects with title, risk, and evidence_needed.',
            '- "uncertainties": array of strings.',
            '- "recommended_experiments": array of objects with title, objective, expected_information_gain, falsification, and safety_constraints.',
            '- "abstain": boolean indicating whether the evidence supports no new experiment.',
            "Do not claim profitability, readiness, causal proof, or authority from model output.",
            "Limit every array to at most eight items.",
            "Keep the summary under 120 words and every other string field under 180 words.",
        ]
    )


def _council_prompt(objective: str, state: dict[str, Any]) -> str:
    return "\n".join(
        [
            "You are an analysis-only council member for a paper-market research system.",
            "Do not edit files, run commands, request credentials, connect to a broker, or place orders.",
            "Return an evidence-ranked recommendation, explicit uncertainties, and the safest next experiment.",
            _analysis_contract(),
            f"Objective: {objective}",
            "Current machine-readable state:",
            json.dumps(state, sort_keys=True, ensure_ascii=False),
        ]
    )


def _objective_from_prompt(prompt: str) -> str:
    objective_marker = "Objective:"
    state_marker = "Current machine-readable state:"
    objective_start = prompt.find(objective_marker)
    if objective_start < 0:
        return prompt.strip()
    objective_start += len(objective_marker)
    state_start = prompt.find(state_marker, objective_start)
    objective = prompt[objective_start:state_start] if state_start >= 0 else prompt[objective_start:]
    return objective.strip()


def _select_openrouter_route(prompt: str) -> dict[str, Any]:
    objective = _objective_from_prompt(prompt)
    normalized = " ".join(objective.casefold().split())
    scored_profiles: list[tuple[int, int, dict[str, Any], list[str]]] = []
    route_scores: dict[str, int] = {}
    for profile in OPENROUTER_ROUTE_PROFILES:
        signals = profile["signals"]
        if not isinstance(signals, tuple):
            raise TypeError(f"OpenRouter route signals must be a tuple: route_id={profile['route_id']}")
        matches = [signal for signal in signals if signal in normalized]
        score = len(matches)
        route_scores[str(profile["route_id"])] = score
        scored_profiles.append((score, -int(profile["priority"]), profile, matches))
    score, _priority, selected_profile, matches = max(
        scored_profiles,
        key=lambda record: (record[0], record[1]),
    )
    if score == 0:
        selected_profile = OPENROUTER_DEFAULT_ROUTE
        matches = []
        route_scores[str(OPENROUTER_DEFAULT_ROUTE["route_id"])] = 0
    return {
        "route_id": str(selected_profile["route_id"]),
        "focus": str(selected_profile["focus"]),
        "selection_policy": "objective_signal_score_then_fixed_priority_v1",
        "matched_signals": matches,
        "route_scores": route_scores,
        "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
        "all_components_required": True,
        "required_component_count": len(OPENROUTER_HYBRID_COMPONENTS),
        "maximum_attempts_per_model": OPENROUTER_MAX_ATTEMPTS,
        "maximum_sequential_stage_windows": 3,
    }


def _active_model_roster() -> list[dict[str, Any]]:
    return [
        {
            "provider": provider,
            "model": OPENROUTER_MODELS[provider],
            "role": str(OPENROUTER_COMPONENT_ROLES[provider]["role_id"]),
            "stage": str(OPENROUTER_COMPONENT_ROLES[provider]["stage_id"]),
            "required": True,
        }
        for provider in OPENROUTER_HYBRID_COMPONENTS
    ]


def _openrouter_routing_plan(route_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "topology": "parallel_discovery_then_deep_review_then_synthesis",
        "route_id": str(route_metadata["route_id"]),
        "all_components_required": True,
        "stages": [
            {
                "stage_id": "parallel_discovery",
                "sequence": 1,
                "execution": "parallel",
                "providers": ["openrouter_gemini_3_6_flash", "openrouter_luna_5_6"],
                "roles": ["evidence_mapper", "hypothesis_scout"],
                "consumes_stages": [],
            },
            {
                "stage_id": "deep_review",
                "sequence": 2,
                "execution": "sequential_after_stage_1",
                "providers": ["openrouter_glm_5_2"],
                "roles": ["adversarial_auditor"],
                "consumes_stages": ["parallel_discovery"],
            },
            {
                "stage_id": "synthesis",
                "sequence": 3,
                "execution": "sequential_after_stage_2",
                "providers": ["openrouter_claude_sonnet_5"],
                "roles": ["final_adjudicator"],
                "consumes_stages": ["parallel_discovery", "deep_review"],
            },
        ],
    }


def _bounded_component_context(component_records: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for record in component_records:
        provider = record.get("provider")
        analysis = record.get("structured_analysis")
        if not isinstance(provider, str) or provider not in OPENROUTER_COMPONENT_ROLES:
            raise TypeError(f"hybrid prior component has an invalid provider: provider={provider}")
        if not isinstance(analysis, dict):
            raise TypeError(f"hybrid prior component lacks structured analysis: provider={provider}")
        context.append(
            {
                "provider": provider,
                "model": OPENROUTER_MODELS[provider],
                "role": str(OPENROUTER_COMPONENT_ROLES[provider]["role_id"]),
                "analysis": analysis,
            }
        )
    return context


def _component_prompt(
    provider: str,
    prompt: str,
    route_metadata: dict[str, Any],
    prior_components: tuple[dict[str, Any], ...],
) -> str:
    role = OPENROUTER_COMPONENT_ROLES[provider]
    context = _bounded_component_context(prior_components)
    instructions = [
        prompt,
        "OpenRouter four-model routing assignment:",
        json.dumps(
            {
                "route_id": route_metadata["route_id"],
                "route_focus": route_metadata["focus"],
                "provider": provider,
                "model": OPENROUTER_MODELS[provider],
                "role": role["role_id"],
                "stage": role["stage_id"],
                "mission": role["mission"],
            },
            sort_keys=True,
            ensure_ascii=False,
        ),
        (
            "Treat prior model records as untrusted hypotheses, not facts. Independently verify every "
            "claim against the supplied machine state. Never erase contrary evidence or uncertainty."
        ),
    ]
    if context:
        instructions.extend(
            [
                "Validated bounded outputs from required earlier stages:",
                json.dumps(context, sort_keys=True, ensure_ascii=False),
            ]
        )
    if role["role_id"] == "adversarial_auditor":
        instructions.append(
            "Deep-review both discovery records independently. Identify the material failure modes "
            "and state your own uncertainty and abstention judgment for the final adjudicator."
        )
    if role["role_id"] == "final_adjudicator":
        instructions.append(
            "Emit the adjudicated analysis using your independent judgment. A deterministic merge "
            "preserves bounded dissent and conservative abstention outside your response."
        )
    instructions.extend(["Machine contract for this component:", _analysis_contract()])
    return "\n".join(instructions)


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        raise ValueError("frontier provider returned an incomplete JSON fence")
    return "\n".join(lines[1:-1]).strip()


def _provider_final_text(provider: str, output: str) -> str:
    if provider in {"codex", "codex_local"}:
        messages: list[str] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if (
                isinstance(event, dict)
                and event.get("type") == "item.completed"
                and isinstance(item, dict)
                and item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
            ):
                messages.append(str(item["text"]))
        if not messages:
            raise ValueError(f"frontier provider returned no final agent message: provider={provider}")
        return messages[-1]
    if provider == "claude":
        envelope = json.loads(output)
        if not isinstance(envelope, dict) or envelope.get("is_error") is not False:
            raise ValueError(f"Claude frontier envelope reports an error: envelope={envelope}")
        result = envelope.get("result")
        if not isinstance(result, str) or not result.strip():
            raise ValueError("Claude frontier envelope lacks a result string")
        return result
    if provider == "cursor":
        envelope = json.loads(output)
        if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
            return str(envelope["result"])
        return output
    raise ValueError(f"unsupported frontier output provider: provider={provider}")


def _validated_contract_string(provider: str, path: str, value: Any, maximum_words: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(
            "frontier analysis requires a non-empty string: "
            f"provider={provider}, path={path}"
        )
    word_count = len(value.split())
    if word_count > maximum_words:
        raise ValueError(
            "frontier analysis string exceeds its word limit: "
            f"provider={provider}, path={path}, words={word_count}, maximum={maximum_words}"
        )
    return value


def _validate_contract_object_array(
    provider: str,
    key: str,
    values: Any,
    required_fields: tuple[str, ...],
) -> None:
    if not isinstance(values, list):
        raise TypeError(f"frontier analysis field must be an array: provider={provider}, key={key}")
    if len(values) > 8:
        raise ValueError(
            f"frontier analysis exceeds the bounded array contract: provider={provider}, key={key}, count={len(values)}"
        )
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise TypeError(
                "frontier analysis array item must be an object: "
                f"provider={provider}, key={key}, index={index}"
            )
        for field in required_fields:
            _validated_contract_string(
                provider,
                f"{key}[{index}].{field}",
                value.get(field),
                180,
            )


def _validated_analysis_text(provider: str, final_text: str) -> dict[str, Any]:
    final_text = _strip_json_fence(final_text)
    parsed = json.loads(final_text)
    if not isinstance(parsed, dict):
        raise TypeError(f"frontier analysis must be a JSON object: provider={provider}")
    required_types: dict[str, type] = {
        "summary": str,
        "hypotheses": list,
        "adversarial_findings": list,
        "uncertainties": list,
        "recommended_experiments": list,
        "abstain": bool,
    }
    for key, expected_type in required_types.items():
        if not isinstance(parsed.get(key), expected_type):
            raise TypeError(
                "frontier analysis violates its structured contract: "
                f"provider={provider}, key={key}, expected={expected_type.__name__}"
            )
    _validated_contract_string(provider, "summary", parsed["summary"], 120)
    _validate_contract_object_array(
        provider,
        "hypotheses",
        parsed["hypotheses"],
        ("title", "mechanism", "evidence_needed", "falsification"),
    )
    _validate_contract_object_array(
        provider,
        "adversarial_findings",
        parsed["adversarial_findings"],
        ("title", "risk", "evidence_needed"),
    )
    uncertainties = parsed["uncertainties"]
    if len(uncertainties) > 8:
        raise ValueError(
            "frontier analysis exceeds the bounded array contract: "
            f"provider={provider}, key=uncertainties, count={len(uncertainties)}"
        )
    for index, uncertainty in enumerate(uncertainties):
        _validated_contract_string(provider, f"uncertainties[{index}]", uncertainty, 180)
    _validate_contract_object_array(
        provider,
        "recommended_experiments",
        parsed["recommended_experiments"],
        (
            "title",
            "objective",
            "expected_information_gain",
            "falsification",
            "safety_constraints",
        ),
    )
    return parsed


def _validated_analysis(provider: str, output: str) -> dict[str, Any]:
    return _validated_analysis_text(provider, _provider_final_text(provider, output))


def _provider_model(provider: str) -> str:
    if provider == OPENROUTER_HYBRID_PROVIDER or provider in OPENROUTER_HYBRID_ALIASES:
        return OPENROUTER_HYBRID_MODEL
    if provider in OPENROUTER_MODELS:
        return OPENROUTER_MODELS[provider]
    if provider == "codex":
        return CODEX_FRONTIER_MODEL
    if provider == "claude":
        return CLAUDE_FRONTIER_MODEL
    if provider == "codex_local":
        return f"local:{os.environ.get('DOPEY_LOCAL_FRONTIER_PROVIDER', 'unconfigured')}"
    return "provider_default"


def _provider_reasoning_effort(provider: str) -> str:
    if provider == OPENROUTER_HYBRID_PROVIDER or provider in OPENROUTER_HYBRID_ALIASES:
        return "role_routed_medium_high_high_high"
    if provider in OPENROUTER_REASONING_EFFORTS:
        return OPENROUTER_REASONING_EFFORTS[provider]
    if provider == "codex":
        return CODEX_REASONING_EFFORT
    if provider == "claude":
        return CLAUDE_REASONING_EFFORT
    return "provider_default"


def _openrouter_final_text(provider: str, envelope: dict[str, Any]) -> str:
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"OpenRouter response has no choices: provider={provider}")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise TypeError(f"OpenRouter choice must be an object: provider={provider}")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise TypeError(f"OpenRouter choice has no message object: provider={provider}")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"OpenRouter message has no text content: provider={provider}")
    return content


def _openrouter_usage(envelope: dict[str, Any]) -> dict[str, int | float]:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        return {}
    allowed_keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "cost_details",
    )
    result: dict[str, int | float] = {}
    for key in allowed_keys:
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result[key] = value
    return result


def _summed_usage(usages: tuple[dict[str, int | float], ...]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost"):
        numeric = [
            usage[key]
            for usage in usages
            if key in usage
            and isinstance(usage[key], (int, float))
            and not isinstance(usage[key], bool)
        ]
        if numeric:
            totals[key] = (
                round(sum(float(value) for value in numeric), 8)
                if key == "cost"
                else int(sum(numeric))
            )
    return totals


def _redacted_error_text(value: str, secret: str) -> str:
    return value.replace(secret, "<redacted>") if secret else value


def _fair_hybrid_object_array(
    analyses: tuple[dict[str, Any], ...],
    key: str,
    maximum_items: int,
) -> list[dict[str, Any]]:
    arrays: list[list[Any]] = []
    for analysis in analyses:
        values = analysis.get(key)
        if not isinstance(values, list):
            raise TypeError(f"hybrid component field must be an array: key={key}")
        arrays.append(values)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    maximum_depth = max((len(values) for values in arrays), default=0)
    for item_index in range(maximum_depth):
        for values in arrays:
            if item_index >= len(values):
                continue
            value = values[item_index]
            if not isinstance(value, dict):
                raise TypeError(f"hybrid component array item must be an object: key={key}")
            title = value.get("title")
            identity = str(title if isinstance(title, str) else value).strip().casefold()
            if identity and identity not in seen:
                seen.add(identity)
                merged.append(dict(value))
            if len(merged) >= maximum_items:
                return merged
    return merged


def _fair_hybrid_string_array(
    analyses: tuple[dict[str, Any], ...],
    key: str,
    maximum_items: int,
) -> list[str]:
    arrays: list[list[Any]] = []
    for analysis in analyses:
        values = analysis.get(key)
        if not isinstance(values, list):
            raise TypeError(f"hybrid component field must be an array: key={key}")
        arrays.append(values)
    merged: list[str] = []
    seen: set[str] = set()
    maximum_depth = max((len(values) for values in arrays), default=0)
    for item_index in range(maximum_depth):
        for values in arrays:
            if item_index >= len(values):
                continue
            value = values[item_index]
            if not isinstance(value, str):
                raise TypeError(f"hybrid component array item must be a string: key={key}")
            identity = value.strip().casefold()
            if identity and identity not in seen:
                seen.add(identity)
                merged.append(value)
            if len(merged) >= maximum_items:
                return merged
    return merged


def _conservative_adjudicated_analysis(
    component_records: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    actual_providers = tuple(str(record.get("provider", "")) for record in component_records)
    if actual_providers != OPENROUTER_HYBRID_COMPONENTS:
        raise ValueError(
            "OpenRouter adjudication requires the complete ordered component roster: "
            f"expected={OPENROUTER_HYBRID_COMPONENTS}, actual={actual_providers}"
        )
    final_analysis = component_records[-1].get("structured_analysis")
    if not isinstance(final_analysis, dict):
        raise TypeError("OpenRouter final adjudicator returned no structured analysis")
    risk_priority_records = (
        component_records[2],
        component_records[3],
        component_records[0],
        component_records[1],
    )
    risk_priority_analyses = tuple(
        record["structured_analysis"] for record in risk_priority_records
    )
    if not all(isinstance(analysis, dict) for analysis in risk_priority_analyses):
        raise TypeError("OpenRouter adjudication requires four structured component analyses")
    abstentions = [record["structured_analysis"].get("abstain") for record in component_records]
    if not all(type(value) is bool for value in abstentions):
        raise TypeError("OpenRouter adjudication requires boolean abstention from every component")
    structured_analysis = {
        "summary": str(final_analysis["summary"]),
        "hypotheses": [dict(value) for value in final_analysis["hypotheses"]],
        "adversarial_findings": _fair_hybrid_object_array(
            risk_priority_analyses,
            "adversarial_findings",
            8,
        ),
        "uncertainties": _fair_hybrid_string_array(
            risk_priority_analyses,
            "uncertainties",
            8,
        ),
        "recommended_experiments": [
            dict(value) for value in final_analysis["recommended_experiments"]
        ],
        "abstain": any(bool(value) for value in abstentions),
    }
    _validated_analysis_text(
        OPENROUTER_HYBRID_PROVIDER,
        json.dumps(structured_analysis, sort_keys=True, ensure_ascii=False),
    )
    return structured_analysis


def _hybrid_usage(component_records: tuple[dict[str, Any], ...]) -> dict[str, int | float]:
    usages: list[dict[str, int | float]] = []
    for record in component_records:
        usage = record.get("usage")
        if not isinstance(usage, dict):
            continue
        usages.append(
            {
                str(key): value
                for key, value in usage.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
        )
    return _summed_usage(tuple(usages))


def _hybrid_paid_audit(component_records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    paid_response_ids: list[str] = []
    paid_response_count = 0
    for record in component_records:
        raw_ids = record.get("paid_response_ids")
        if isinstance(raw_ids, (list, tuple)) and all(isinstance(value, str) for value in raw_ids):
            record_ids = [str(value) for value in raw_ids]
        else:
            response_id = record.get("response_id")
            record_ids = [str(response_id)] if isinstance(response_id, str) else []
        raw_count = record.get("paid_response_count")
        record_count = raw_count if isinstance(raw_count, int) and raw_count >= 0 else len(record_ids)
        paid_response_count += record_count
        paid_response_ids.extend(record_ids)
    return {
        "paid_response_count": paid_response_count,
        "paid_response_ids": paid_response_ids,
        "usage": _hybrid_usage(component_records),
    }


def _hybrid_stage_failure(
    stage: str,
    completed_records: tuple[dict[str, Any], ...],
    failures: tuple[tuple[str, RuntimeError], ...],
) -> OpenRouterPaidFailure:
    completed_audit = _hybrid_paid_audit(completed_records)
    usages: list[dict[str, int | float]] = []
    completed_usage = completed_audit["usage"]
    if isinstance(completed_usage, dict):
        usages.append(
            {
                str(key): value
                for key, value in completed_usage.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
        )
    paid_response_count = int(completed_audit["paid_response_count"])
    paid_response_ids = [str(value) for value in completed_audit["paid_response_ids"]]
    failure_messages: list[dict[str, str]] = []
    for provider, error in failures:
        failure_messages.append({"provider": provider, "error": str(error)})
        if not isinstance(error, OpenRouterPaidFailure):
            continue
        usages.append(error.usage)
        paid_response_count += error.paid_response_count
        paid_response_ids.extend(error.paid_response_ids)
    usage = _summed_usage(tuple(usages))
    message = json.dumps(
        {
            "stage": stage,
            "failures": failure_messages,
            "paid_response_count": paid_response_count,
            "paid_response_ids": paid_response_ids,
            "usage": usage,
        },
        sort_keys=True,
    )
    return OpenRouterPaidFailure(
        f"OpenRouter four-model hybrid stage failed: audit={message}",
        usage,
        paid_response_count,
        tuple(paid_response_ids),
    )


def _validate_hybrid_component_record(
    record: dict[str, Any],
    expected_provider: str,
) -> None:
    if record.get("provider") != expected_provider:
        raise ValueError(
            "OpenRouter hybrid component provider mismatch: "
            f"expected={expected_provider}, actual={record.get('provider')}"
        )
    if record.get("model") != OPENROUTER_MODELS[expected_provider]:
        raise ValueError(
            "OpenRouter hybrid component model mismatch: "
            f"provider={expected_provider}, expected={OPENROUTER_MODELS[expected_provider]}, "
            f"actual={record.get('model')}"
        )
    if record.get("status") != "completed_analysis_only":
        raise ValueError(
            "OpenRouter hybrid component is incomplete: "
            f"provider={expected_provider}, status={record.get('status')}"
        )
    analysis = record.get("structured_analysis")
    if not isinstance(analysis, dict):
        raise TypeError(
            f"OpenRouter hybrid component lacks structured output: provider={expected_provider}"
        )
    _validated_analysis_text(
        expected_provider,
        json.dumps(analysis, sort_keys=True, ensure_ascii=False),
    )
    role = OPENROUTER_COMPONENT_ROLES[expected_provider]
    if record.get("role") != role["role_id"] or record.get("stage") != role["stage_id"]:
        raise ValueError(
            "OpenRouter hybrid component routing identity mismatch: "
            f"provider={expected_provider}, role={record.get('role')}, stage={record.get('stage')}"
        )


def _run_required_hybrid_component(
    provider: str,
    prompt: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt_bytes = len(prompt.encode("utf-8"))
    if prompt_bytes > OPENROUTER_MAX_COMPONENT_PROMPT_BYTES:
        raise RuntimeError(
            "OpenRouter component prompt exceeds the pre-paid byte budget: "
            f"provider={provider}, bytes={prompt_bytes}, "
            f"maximum={OPENROUTER_MAX_COMPONENT_PROMPT_BYTES}"
        )
    record = _run_openrouter_provider(provider, prompt, timeout_seconds)
    try:
        _validate_hybrid_component_record(record, provider)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        audit = _hybrid_paid_audit((record,))
        raise OpenRouterPaidFailure(
            "OpenRouter required hybrid component failed validation: "
            f"provider={provider}, model={OPENROUTER_MODELS[provider]}, "
            f"error={type(error).__name__}: {error}",
            audit["usage"] if isinstance(audit["usage"], dict) else {},
            int(audit["paid_response_count"]),
            tuple(str(value) for value in audit["paid_response_ids"]),
        ) from error
    return record


def _run_openrouter_hybrid(prompt: str, timeout_seconds: int) -> dict[str, Any]:
    route_metadata = _select_openrouter_route(prompt)
    discovery_providers = OPENROUTER_HYBRID_COMPONENTS[:2]
    with ThreadPoolExecutor(
        max_workers=len(discovery_providers),
        thread_name_prefix="dopey_openrouter_discovery",
    ) as pool:
        futures = {
            provider: pool.submit(
                _run_required_hybrid_component,
                provider,
                _component_prompt(provider, prompt, route_metadata, ()),
                timeout_seconds,
            )
            for provider in discovery_providers
        }
        discovery_results: dict[str, dict[str, Any]] = {}
        discovery_failures: list[tuple[str, RuntimeError]] = []
        for provider in discovery_providers:
            try:
                discovery_results[provider] = futures[provider].result()
            except RuntimeError as error:
                discovery_failures.append((provider, error))
    if discovery_failures:
        raise _hybrid_stage_failure(
            "parallel_discovery",
            tuple(discovery_results.values()),
            tuple(discovery_failures),
        )
    discovery_records = tuple(discovery_results[provider] for provider in discovery_providers)
    deep_review_provider = OPENROUTER_HYBRID_COMPONENTS[2]
    try:
        deep_review_record = _run_required_hybrid_component(
            deep_review_provider,
            _component_prompt(deep_review_provider, prompt, route_metadata, discovery_records),
            timeout_seconds,
        )
    except RuntimeError as error:
        raise _hybrid_stage_failure(
            "deep_review",
            discovery_records,
            ((deep_review_provider, error),),
        ) from error
    synthesis_provider = OPENROUTER_HYBRID_COMPONENTS[3]
    pre_synthesis_records = (*discovery_records, deep_review_record)
    try:
        synthesis_record = _run_required_hybrid_component(
            synthesis_provider,
            _component_prompt(synthesis_provider, prompt, route_metadata, pre_synthesis_records),
            timeout_seconds,
        )
    except RuntimeError as error:
        raise _hybrid_stage_failure(
            "synthesis",
            pre_synthesis_records,
            ((synthesis_provider, error),),
        ) from error
    component_records = (*pre_synthesis_records, synthesis_record)
    actual_providers = tuple(str(record.get("provider", "")) for record in component_records)
    if actual_providers != OPENROUTER_HYBRID_COMPONENTS:
        error = RuntimeError(
            "invalid component roster: "
            f"expected={OPENROUTER_HYBRID_COMPONENTS}, actual={actual_providers}"
        )
        raise _hybrid_stage_failure("final_merge", component_records, (("hybrid", error),))
    try:
        structured_analysis = _conservative_adjudicated_analysis(component_records)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        merge_error = RuntimeError(f"{type(error).__name__}: {error}")
        raise _hybrid_stage_failure(
            "final_merge",
            component_records,
            (("hybrid", merge_error),),
        ) from error
    component_evidence = [
        {
            key: value
            for key, value in record.items()
            if key not in {"output", "structured_analysis"}
        }
        for record in component_records
    ]
    component_analyses = [
        {
            "provider": str(record["provider"]),
            "model": str(record["model"]),
            "role": str(record["role"]),
            "stage": str(record["stage"]),
            "analysis": record["structured_analysis"],
        }
        for record in component_records
    ]
    if len(component_evidence) != 4 or len(component_analyses) != 4:
        raise RuntimeError(
            "OpenRouter hybrid requires exactly four completed component records: "
            f"results={len(component_evidence)}, analyses={len(component_analyses)}"
        )
    paid_audit = _hybrid_paid_audit(component_records)
    return {
        "provider": OPENROUTER_HYBRID_PROVIDER,
        "status": "completed_analysis_only",
        "attempt": max(int(record["attempt"]) for record in component_records),
        "output": json.dumps(structured_analysis, sort_keys=True, ensure_ascii=False),
        "structured_analysis": structured_analysis,
        "model": OPENROUTER_HYBRID_MODEL,
        "component_models": [OPENROUTER_MODELS[provider] for provider in OPENROUTER_HYBRID_COMPONENTS],
        "component_results": component_evidence,
        "component_analyses": component_analyses,
        "active_model_roster": _active_model_roster(),
        "routing_plan": _openrouter_routing_plan(route_metadata),
        "route_metadata": route_metadata,
        "reasoning_effort": _provider_reasoning_effort(OPENROUTER_HYBRID_PROVIDER),
        "usage": paid_audit["usage"],
        "response_ids": [str(record.get("response_id", "")) for record in component_records],
        "paid_response_count": paid_audit["paid_response_count"],
        "paid_response_ids": paid_audit["paid_response_ids"],
        "hybrid_policy": "four_model_role_routed_conservative_adjudication",
        "adjudication_merge_policy": (
            "claude_summary_hypotheses_experiments_with_fair_round_robin_risk_union_and_any_abstain"
        ),
    }


def _run_openrouter_provider(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
    if provider not in OPENROUTER_MODELS or provider not in OPENROUTER_COMPONENT_ROLES:
        raise ValueError(f"unsupported OpenRouter component provider: provider={provider}")
    try:
        api_key = resolve_openrouter_api_key()
    except ProviderControlError as error:
        raise RuntimeError(f"OpenRouter credential is unavailable: {error}") from error
    model = OPENROUTER_MODELS[provider]
    reasoning_effort = OPENROUTER_REASONING_EFFORTS[provider]
    role = OPENROUTER_COMPONENT_ROLES[provider]
    request_body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an independent analysis-only scientist in a required four-model research topology. "
                    f"Your assigned role is {role['role_id']}: {role['mission']} "
                    "Follow the requested JSON contract exactly. Never claim trading authority, profitability, "
                    "readiness, or permission to weaken evidence gates. Never request credentials, connect to a "
                    "broker, place orders, or convert research output into an execution instruction."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
        "max_tokens": OPENROUTER_MAX_TOKENS[provider],
        "response_format": {"type": "json_object"},
        "reasoning": {"effort": reasoning_effort, "exclude": True},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ObtuseAI/dopey",
        "X-Title": "DOPEY paper-market research council",
    }
    last_error = ""
    paid_usages: list[dict[str, int | float]] = []
    paid_response_ids: list[str] = []
    paid_response_count = 0
    for attempt in range(1, OPENROUTER_MAX_ATTEMPTS + 1):
        attempt_body = dict(request_body)
        if last_error:
            attempt_body["messages"] = [
                *request_body["messages"],
                {
                    "role": "user",
                    "content": (
                        "Your previous response was rejected by the machine contract. "
                        f"Correct this exact failure and return only the required JSON object: {last_error[:1_500]}"
                    ),
                },
            ]
        try:
            response = requests.post(
                OPENROUTER_ENDPOINT,
                headers=headers,
                json=attempt_body,
                timeout=timeout_seconds,
            )
        except requests.RequestException as error:
            last_error = _redacted_error_text(f"{type(error).__name__}: {error}", api_key)
            print(
                json.dumps(
                    {
                        "warning": "openrouter_provider_attempt_failed",
                        "provider": provider,
                        "model": model,
                        "attempt": attempt,
                        "error": last_error,
                    }
                ),
                file=sys.stderr,
            )
            continue
        if response.status_code < 200 or response.status_code >= 300:
            response_tail = _redacted_error_text(response.text[-4_000:], api_key)
            last_error = f"status_code={response.status_code}, response={response_tail}"
            print(
                json.dumps(
                    {
                        "warning": "openrouter_provider_non_success",
                        "provider": provider,
                        "model": model,
                        "attempt": attempt,
                        "error": last_error,
                    }
                ),
                file=sys.stderr,
            )
            continue
        paid_response_count += 1
        attempt_usage: dict[str, int | float] = {}
        attempt_response_id = ""
        try:
            raw_envelope: Any = response.json()
            if not isinstance(raw_envelope, dict):
                raise TypeError("OpenRouter response must be a JSON object")
            envelope: dict[str, Any] = raw_envelope
            attempt_usage = _openrouter_usage(envelope)
            attempt_response_id = str(envelope.get("id", ""))
            final_text = _openrouter_final_text(provider, envelope)
            analysis = _validated_analysis_text(provider, final_text)
        except (TypeError, ValueError, json.JSONDecodeError, requests.JSONDecodeError) as error:
            paid_usages.append(attempt_usage)
            paid_response_ids.append(attempt_response_id)
            last_error = f"structured_output_error={type(error).__name__}: {error}"
            print(
                json.dumps(
                    {
                        "warning": "openrouter_provider_structured_output_invalid",
                        "provider": provider,
                        "model": model,
                        "attempt": attempt,
                        "error": last_error,
                        "response_id": attempt_response_id,
                        "paid_response_count": paid_response_count,
                        "usage": _summed_usage(tuple(paid_usages)),
                    }
                ),
                file=sys.stderr,
            )
            continue
        paid_usages.append(attempt_usage)
        paid_response_ids.append(attempt_response_id)
        return {
            "provider": provider,
            "status": "completed_analysis_only",
            "attempt": attempt,
            "output": final_text[-100_000:],
            "structured_analysis": analysis,
            "model": model,
            "role": str(role["role_id"]),
            "stage": str(role["stage_id"]),
            "reasoning_effort": reasoning_effort,
            "usage": _summed_usage(tuple(paid_usages)),
            "response_id": attempt_response_id,
            "paid_response_count": paid_response_count,
            "paid_response_ids": list(paid_response_ids),
        }
    paid_usage = _summed_usage(tuple(paid_usages))
    raise OpenRouterPaidFailure(
        f"OpenRouter frontier provider failed: provider={provider}, model={model}, error={last_error}",
        paid_usage,
        paid_response_count,
        tuple(paid_response_ids),
    )


def _provider_command(provider: str) -> tuple[list[str], str | None]:
    if provider == "codex":
        executable = shutil.which("codex")
        return ([
            executable or "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--model",
            CODEX_FRONTIER_MODEL,
            "-c",
            f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
            "--json",
            "-",
        ], executable)
    if provider == "claude":
        executable = shutil.which("claude")
        return ([
            executable or "claude",
            "--print",
            "--model",
            CLAUDE_FRONTIER_MODEL,
            "--effort",
            CLAUDE_REASONING_EFFORT,
            "--max-budget-usd",
            CLAUDE_MAX_BUDGET_USD,
            "--permission-mode",
            "plan",
            "--disallowedTools",
            "Bash",
            "Edit",
            "Write",
            "--tools",
            "",
            "--no-session-persistence",
            "--output-format",
            "json",
        ], executable)
    if provider == "cursor":
        executable = shutil.which("cursor-agent")
        return ([executable or "cursor-agent", "--print", "--output-format", "json"], executable)
    if provider == "codex_local":
        executable = shutil.which("codex")
        local_provider = os.environ.get("DOPEY_LOCAL_FRONTIER_PROVIDER", "")
        if local_provider not in {"ollama", "lmstudio"}:
            raise RuntimeError("DOPEY_LOCAL_FRONTIER_PROVIDER must be ollama or lmstudio for codex_local")
        return ([
            executable or "codex",
            "exec",
            "--oss",
            "--local-provider",
            local_provider,
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "-",
        ], executable)
    raise ValueError(f"unsupported frontier provider: {provider}")


def _run_provider(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
    if provider == OPENROUTER_HYBRID_PROVIDER or provider in OPENROUTER_HYBRID_ALIASES:
        result = _run_openrouter_hybrid(prompt, timeout_seconds)
        if provider != OPENROUTER_HYBRID_PROVIDER:
            return {**result, "requested_provider": provider}
        return result
    if provider in OPENROUTER_MODELS:
        return _run_openrouter_provider(provider, prompt, timeout_seconds)
    command, executable = _provider_command(provider)
    if executable is None:
        return {"provider": provider, "status": "unavailable_command_not_installed", "output": ""}
    last_error = ""
    with tempfile.TemporaryDirectory(prefix="dopey_frontier_council_") as temp_dir:
        for attempt in range(1, 3):
            try:
                completed = subprocess.run(
                    command,
                    cwd=temp_dir,
                    input=prompt,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                last_error = f"{type(error).__name__}: {error}"
                print(json.dumps({"warning": "frontier_provider_attempt_failed", "provider": provider, "attempt": attempt, "error": last_error}), file=sys.stderr)
                continue
            if completed.returncode == 0:
                try:
                    analysis = _validated_analysis(provider, completed.stdout)
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    last_error = f"structured_output_error={type(error).__name__}: {error}"
                    print(
                        json.dumps(
                            {
                                "warning": "frontier_provider_structured_output_invalid",
                                "provider": provider,
                                "attempt": attempt,
                                "error": last_error,
                            }
                        ),
                        file=sys.stderr,
                    )
                    continue
                return {
                    "provider": provider,
                    "status": "completed_analysis_only",
                    "attempt": attempt,
                    "output": completed.stdout[-100000:],
                    "stderr_tail": completed.stderr[-4000:],
                    "structured_analysis": analysis,
                    "model": _provider_model(provider),
                    "reasoning_effort": _provider_reasoning_effort(provider),
                }
            last_error = (
                f"return_code={completed.returncode}, stdout={completed.stdout[-4000:]}, "
                f"stderr={completed.stderr[-4000:]}"
            )
            print(json.dumps({"warning": "frontier_provider_nonzero", "provider": provider, "attempt": attempt, "error": last_error}), file=sys.stderr)
    raise RuntimeError(f"frontier provider failed: provider={provider}, error={last_error}")


def run_frontier_council(objective: str, providers: tuple[str, ...], state: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    if not objective.strip():
        raise ValueError("frontier council objective must not be empty")
    if len(providers) != 1:
        raise ValueError(
            "frontier council requires exactly one governed aggregate provider: "
            f"providers={list(providers)}"
        )
    provider = providers[0]
    if provider != OPENROUTER_HYBRID_PROVIDER and provider not in OPENROUTER_HYBRID_ALIASES:
        raise ValueError(
            "frontier council rejects direct component and independent adapter routes: "
            f"provider={provider}, required={OPENROUTER_HYBRID_PROVIDER}"
        )
    prompt = _council_prompt(objective, state)
    results: list[dict[str, Any]] = []
    try:
        results.append(_run_provider(provider, prompt, timeout_seconds))
    except RuntimeError as error:
        failure_record: dict[str, Any] = {
            "provider": provider,
            "status": "failed_after_retries",
            "error": str(error),
            "output": "",
        }
        if isinstance(error, OpenRouterPaidFailure):
            failure_record.update(
                {
                    "usage": error.usage,
                    "paid_response_count": error.paid_response_count,
                    "paid_response_ids": list(error.paid_response_ids),
                }
            )
        results.append(failure_record)
    completed_count = sum(record.get("status") == "completed_analysis_only" for record in results)
    if completed_count == 0:
        failure = results[0]
        failure_message = json.dumps(
            {
                "error": str(failure.get("error", "unknown")),
                "paid_response_count": int(failure.get("paid_response_count", 0)),
                "paid_response_ids": failure.get("paid_response_ids", []),
                "usage": failure.get("usage", {}),
            },
            sort_keys=True,
        )
        if isinstance(failure.get("paid_response_count"), int):
            raise OpenRouterPaidFailure(
                f"governed frontier provider failed: audit={failure_message}",
                failure.get("usage", {}) if isinstance(failure.get("usage"), dict) else {},
                int(failure.get("paid_response_count", 0)),
                tuple(
                    str(value)
                    for value in failure.get("paid_response_ids", [])
                    if isinstance(value, str)
                ),
            )
        raise RuntimeError(f"governed frontier provider failed: audit={failure_message}")
    return {
        "artifact_type": "frontier_analysis_council_result",
        "objective": objective,
        "providers": list(providers),
        "results": results,
        "council_status": "completed_all_providers" if completed_count == len(results) else "completed_partial_provider_failure",
        "completed_provider_count": completed_count,
        "failed_provider_count": len(results) - completed_count,
        "analysis_only": True,
        "repo_write_access": False,
        "paper_only": True,
        "live_blocked": True,
    }


def head_coach_availability() -> dict[str, dict[str, Any]]:
    """Report non-secret availability for the explicit research head-coach slots."""

    credential = openrouter_credential_status()
    codex_executable = shutil.which("codex")
    return {
        "claude": {
            "head_coach_id": "claude",
            "model": OPENROUTER_MODELS["openrouter_claude_sonnet_5"],
            "route_id": OPENROUTER_HYBRID_PROVIDER,
            "available": credential["usable"] is True,
            "availability_reason": (
                "existing_openrouter_config_usable"
                if credential["usable"] is True
                else "existing_openrouter_config_unusable"
            ),
            "silent_fallback_allowed": False,
        },
        "codex": {
            "head_coach_id": "codex",
            "model": CODEX_FRONTIER_MODEL,
            "route_id": "codex_read_only_cli",
            "available": codex_executable is not None,
            "availability_reason": (
                "codex_read_only_cli_installed"
                if codex_executable is not None
                else "codex_read_only_cli_not_installed"
            ),
            "silent_fallback_allowed": False,
        },
    }


def run_research_head_coach(
    objective: str,
    head_coach_id: str,
    state: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run exactly the selected head coach without provider substitution."""

    if not objective.strip():
        raise ValueError("research head-coach objective must not be empty")
    normalized_coach_id = head_coach_id.strip().casefold()
    if normalized_coach_id not in HEAD_COACH_IDS:
        raise ValueError(
            "research head coach is unsupported: "
            f"actual={head_coach_id!r}, allowed={HEAD_COACH_IDS}"
        )
    availability = head_coach_availability()[normalized_coach_id]
    if availability["available"] is not True:
        raise RuntimeError(
            "selected research head coach is unavailable and no fallback is allowed: "
            f"head_coach_id={normalized_coach_id}, reason={availability['availability_reason']}"
        )
    if normalized_coach_id == "claude":
        council = run_frontier_council(
            objective,
            (OPENROUTER_HYBRID_PROVIDER,),
            state,
            timeout_seconds,
        )
        results = council.get("results")
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise RuntimeError("Claude head-coach council returned an invalid result topology")
        result = results[0]
        component_models = result.get("component_models")
        expected_models = [
            OPENROUTER_MODELS[provider]
            for provider in OPENROUTER_HYBRID_COMPONENTS
        ]
        if component_models != expected_models:
            raise RuntimeError(
                "Claude head-coach identity cannot be verified from the governed route: "
                f"expected={expected_models}, actual={component_models}"
            )
        return {
            "head_coach_id": "claude",
            "head_coach_model": OPENROUTER_MODELS["openrouter_claude_sonnet_5"],
            "route_id": OPENROUTER_HYBRID_PROVIDER,
            "supporting_models": expected_models[:-1],
            "status": "completed_analysis_only",
            "structured_analysis": result["structured_analysis"],
            "usage": result.get("usage", {}),
            "paid_response_count": result.get("paid_response_count", 0),
            "paid_response_ids": result.get("paid_response_ids", []),
            "routing_plan": result.get("routing_plan", {}),
            "runtime_fallback_used": False,
            "analysis_only": True,
            "repo_write_access": False,
            "paper_only": True,
            "live_blocked": True,
        }
    result = _run_provider(
        "codex",
        _council_prompt(objective, state),
        timeout_seconds,
    )
    if result.get("status") != "completed_analysis_only":
        raise RuntimeError(
            "Codex head coach did not complete and no fallback is allowed: "
            f"status={result.get('status')}"
        )
    if result.get("model") != CODEX_FRONTIER_MODEL:
        raise RuntimeError(
            "Codex head-coach identity mismatch: "
            f"expected={CODEX_FRONTIER_MODEL}, actual={result.get('model')}"
        )
    return {
        "head_coach_id": "codex",
        "head_coach_model": CODEX_FRONTIER_MODEL,
        "route_id": "codex_read_only_cli",
        "supporting_models": [],
        "status": "completed_analysis_only",
        "structured_analysis": result["structured_analysis"],
        "usage": {},
        "paid_response_count": 0,
        "paid_response_ids": [],
        "routing_plan": {
            "topology": "single_read_only_codex_head_coach",
            "sandbox": "read_only",
        },
        "runtime_fallback_used": False,
        "analysis_only": True,
        "repo_write_access": False,
        "paper_only": True,
        "live_blocked": True,
    }
