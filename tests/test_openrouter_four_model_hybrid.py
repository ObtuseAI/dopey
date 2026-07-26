"""Focused integration coverage for the governed OpenRouter four-model hybrid."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from dopey_acceleration import frontier as frontier_module
from dopey_acceleration import llm_research as llm_research_module
from dopey_acceleration import mcp_server as mcp_server_module
from dopey_acceleration import provider_control as provider_control_module
from dopey_acceleration.provider_control import ProviderControl


EXPECTED_PROVIDER_MODELS: dict[str, str] = {
    "openrouter_gemini_3_6_flash": "google/gemini-3.6-flash",
    "openrouter_luna_5_6": "openai/gpt-5.6-luna",
    "openrouter_glm_5_2": "z-ai/glm-5.2",
    "openrouter_claude_sonnet_5": "anthropic/claude-sonnet-5",
}
EXPECTED_COMPONENTS: tuple[str, ...] = tuple(EXPECTED_PROVIDER_MODELS)
EXPECTED_ROUTING_PLAN: tuple[tuple[str, str, str], ...] = (
    ("openrouter_gemini_3_6_flash", "evidence_mapper", "parallel_discovery"),
    ("openrouter_luna_5_6", "hypothesis_scout", "parallel_discovery"),
    ("openrouter_glm_5_2", "adversarial_auditor", "deep_review"),
    ("openrouter_claude_sonnet_5", "final_adjudicator", "synthesis"),
)
HYBRID_PROVIDER = "openrouter_four_model_hybrid"
HYBRID_POLICY = "four_model_role_routed_conservative_adjudication"
TEST_API_KEY = "unit-test-openrouter-token-not-a-real-secret-123456789"


class _FakeOpenRouterResponse:
    """Minimal OpenRouter response connector used without network access."""

    def __init__(self, response_id: str, analysis: dict[str, Any]) -> None:
        self.status_code = 200
        self.text = json.dumps(
            {
                "id": response_id,
                "choices": [{"message": {"content": json.dumps(analysis)}}],
            }
        )
        self._response_id = response_id
        self._analysis = analysis

    def json(self) -> dict[str, Any]:
        return {
            "id": self._response_id,
            "choices": [{"message": {"content": json.dumps(self._analysis)}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
                "cost": 0.001,
            },
        }


class _PaidOpenRouterResponse:
    """Configurable paid 2xx response for retry-accounting coverage."""

    def __init__(
        self,
        response_id: str,
        analysis: dict[str, Any],
        usage: dict[str, int | float],
    ) -> None:
        self.status_code = 200
        self.text = json.dumps({"id": response_id})
        self._response_id = response_id
        self._analysis = analysis
        self._usage = usage

    def json(self) -> dict[str, Any]:
        return {
            "id": self._response_id,
            "choices": [{"message": {"content": json.dumps(self._analysis)}}],
            "usage": self._usage,
        }


def _analysis(provider: str) -> dict[str, Any]:
    evidence_identity = (
        "parallel_discovery"
        if provider in {"openrouter_gemini_3_6_flash", "openrouter_luna_5_6"}
        else provider
    )
    return {
        "summary": f"bounded-summary::{provider}",
        "hypotheses": [
            {
                "title": f"hypothesis::{provider}",
                "mechanism": "falsifiable mechanism",
                "evidence_needed": "held-out evidence",
                "falsification": "predeclared rejection condition",
            }
        ],
        "adversarial_findings": [
            {
                "title": f"risk::{evidence_identity}",
                "risk": "unsupported certainty",
                "evidence_needed": "independent settlement",
            }
        ],
        "uncertainties": [f"uncertainty::{evidence_identity}"],
        "recommended_experiments": [
            {
                "title": f"experiment::{provider}",
                "objective": "increase information",
                "expected_information_gain": "bounded",
                "falsification": "no measured improvement",
                "safety_constraints": "analysis only",
            }
        ],
        "abstain": provider == "openrouter_luna_5_6",
    }


def _expected_conservative_analysis() -> dict[str, Any]:
    final_analysis = dict(_analysis("openrouter_claude_sonnet_5"))
    findings: list[dict[str, Any]] = []
    finding_titles: set[str] = set()
    uncertainties: list[str] = []
    uncertainty_values: set[str] = set()
    risk_priority_providers = (
        "openrouter_glm_5_2",
        "openrouter_claude_sonnet_5",
        "openrouter_gemini_3_6_flash",
        "openrouter_luna_5_6",
    )
    for provider in risk_priority_providers:
        finding = _analysis(provider)["adversarial_findings"][0]
        if finding["title"] not in finding_titles:
            finding_titles.add(str(finding["title"]))
            findings.append(finding)
        uncertainty = str(_analysis(provider)["uncertainties"][0])
        if uncertainty not in uncertainty_values:
            uncertainty_values.add(uncertainty)
            uncertainties.append(uncertainty)
    final_analysis["adversarial_findings"] = findings
    final_analysis["uncertainties"] = uncertainties
    final_analysis["abstain"] = True
    return final_analysis


def _component_record(provider: str) -> dict[str, Any]:
    analysis = _analysis(provider)
    routing = frontier_module.OPENROUTER_COMPONENT_ROLES[provider]
    return {
        "provider": provider,
        "status": "completed_analysis_only",
        "attempt": 1,
        "output": json.dumps(analysis),
        "structured_analysis": analysis,
        "model": EXPECTED_PROVIDER_MODELS[provider],
        "role": _metadata_value(routing, "role", "role_id"),
        "stage": _metadata_value(routing, "stage", "stage_id"),
        "reasoning_effort": "high",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cost": 0.001,
        },
        "response_id": f"response::{provider}",
    }


def _provider_control() -> ProviderControl:
    return cast(
        ProviderControl,
        {
            "schema_version": "dopey-provider-control-v1",
            "updated_utc": "2026-07-22T12:00:00+00:00",
            "instrument_mode": "both",
            "providers": {
                "openrouter": True,
                "openrouter_hybrid": True,
                "claude": False,
                "codex": False,
            },
            "paper_only": True,
            "live_blocked": True,
        },
    )


def _routing_records(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list) and all(isinstance(record, dict) for record in value):
        return cast(list[dict[str, Any]], value)
    if not isinstance(value, dict) or not isinstance(value.get("stages"), list):
        raise AssertionError("routing_plan must expose ordered stage objects")
    records: list[dict[str, Any]] = []
    for raw_stage in value["stages"]:
        if not isinstance(raw_stage, dict):
            raise AssertionError("routing_plan stages must be objects")
        providers = raw_stage.get("providers")
        roles = raw_stage.get("roles")
        stage = raw_stage.get("stage", raw_stage.get("stage_id"))
        if not isinstance(providers, list) or not isinstance(roles, list) or len(providers) != len(roles):
            raise AssertionError("routing_plan stage provider and role lists must align")
        records.extend(
            {
                "provider": provider,
                "role": role,
                "stage": stage,
            }
            for provider, role in zip(providers, roles, strict=True)
        )
    return records


def _metadata_value(record: dict[str, Any], primary: str, compatibility: str) -> str:
    value = record.get(primary, record.get(compatibility))
    if not isinstance(value, str) or not value:
        raise AssertionError(f"routing metadata is missing: field={primary}")
    return value


def _roster_models(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise AssertionError("active_model_roster must be a list or tuple")
    models: list[str] = []
    for item in value:
        if isinstance(item, str):
            models.append(item)
            continue
        if isinstance(item, dict) and isinstance(item.get("model", item.get("model_id")), str):
            models.append(str(item.get("model", item.get("model_id"))))
            continue
        raise AssertionError("active_model_roster items must expose exact model slugs")
    return models


def _hybrid_council_result() -> dict[str, Any]:
    routing_plan = [
        {
            "provider": provider,
            "model": EXPECTED_PROVIDER_MODELS[provider],
            "role": role,
            "stage": stage,
        }
        for provider, role, stage in EXPECTED_ROUTING_PLAN
    ]
    components = [_component_record(provider) for provider in EXPECTED_COMPONENTS]
    component_analyses = [
        {
            "provider": record["provider"],
            "model": record["model"],
            "role": routing_plan[index]["role"],
            "stage": routing_plan[index]["stage"],
            "analysis": record["structured_analysis"],
        }
        for index, record in enumerate(components)
    ]
    final_analysis = _expected_conservative_analysis()
    hybrid_record = {
        "provider": HYBRID_PROVIDER,
        "status": "completed_analysis_only",
        "attempt": 1,
        "model": " + ".join(EXPECTED_PROVIDER_MODELS.values()),
        "component_models": list(EXPECTED_PROVIDER_MODELS.values()),
        "component_results": components,
        "component_analyses": component_analyses,
        "routing_plan": routing_plan,
        "structured_analysis": final_analysis,
        "output": json.dumps(final_analysis),
        "usage": {"cost": 0.004},
        "hybrid_policy": HYBRID_POLICY,
    }
    return {
        "status": "completed_analysis_only",
        "completed_provider_count": 1,
        "failed_provider_count": 0,
        "results": [hybrid_record],
        "paper_only": True,
        "live_blocked": True,
        "repo_write_access": False,
    }


def test_four_model_roster_and_role_plan_are_exact_and_deterministic() -> None:
    assert frontier_module.OPENROUTER_MODELS == EXPECTED_PROVIDER_MODELS
    assert frontier_module.OPENROUTER_HYBRID_COMPONENTS == EXPECTED_COMPONENTS
    assert HYBRID_PROVIDER in frontier_module.ALLOWED_PROVIDERS
    assert set(EXPECTED_COMPONENTS).isdisjoint(frontier_module.ALLOWED_PROVIDERS)

    actual_roles = frontier_module.OPENROUTER_COMPONENT_ROLES
    assert tuple(actual_roles) == EXPECTED_COMPONENTS
    assert tuple(
        (
            provider,
            _metadata_value(actual_roles[provider], "role", "role_id"),
            _metadata_value(actual_roles[provider], "stage", "stage_id"),
        )
        for provider in EXPECTED_COMPONENTS
    ) == EXPECTED_ROUTING_PLAN


def test_mcp_frontier_tool_exposes_only_the_canonical_active_openrouter_topology() -> None:
    tool = next(
        record
        for record in mcp_server_module.TOOLS
        if record["name"] == "run_frontier_analysis_council"
    )
    provider_values = tool["inputSchema"]["properties"]["providers"]["items"]["enum"]
    exposed_contract = json.dumps(
        {
            "description": tool["description"],
            "provider_values": provider_values,
        },
        sort_keys=True,
    )

    assert provider_values == [HYBRID_PROVIDER]
    assert tool["inputSchema"]["properties"]["providers"]["minItems"] == 1
    assert tool["inputSchema"]["properties"]["providers"]["maxItems"] == 1
    assert HYBRID_PROVIDER in exposed_contract
    assert all(provider not in exposed_contract for provider in EXPECTED_COMPONENTS)
    assert {
        "openrouter_gemini_3_5_flash",
        "openrouter_terra_5_6_pro",
    }.isdisjoint(provider_values)
    legacy_alias = "openrouter_gemini_terra_hybrid"
    if legacy_alias in provider_values:
        assert legacy_alias in tool["description"]
        assert "compatibility" in tool["description"].casefold()


@pytest.mark.parametrize(
    "providers",
    (
        (),
        ("openrouter_gemini_3_6_flash",),
        ("openrouter_luna_5_6",),
        ("codex",),
        ("claude",),
        (HYBRID_PROVIDER, HYBRID_PROVIDER),
    ),
)
def test_public_frontier_rejects_component_adapter_and_duplicate_bypasses(
    monkeypatch: pytest.MonkeyPatch,
    providers: tuple[str, ...],
) -> None:
    calls: list[str] = []

    def run_provider(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
        del prompt, timeout_seconds
        calls.append(provider)
        return _component_record("openrouter_gemini_3_6_flash")

    monkeypatch.setattr(frontier_module, "_run_provider", run_provider)

    with pytest.raises(ValueError):
        frontier_module.run_frontier_council("bounded research", providers, {}, 300)

    assert calls == []


def test_component_prompt_budget_blocks_before_any_paid_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def run_component(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
        del prompt, timeout_seconds
        calls.append(provider)
        return _component_record(provider)

    monkeypatch.setattr(frontier_module, "_run_openrouter_provider", run_component)

    with pytest.raises(RuntimeError, match="pre-paid byte budget"):
        frontier_module._run_required_hybrid_component(
            "openrouter_gemini_3_6_flash",
            "x" * (frontier_module.OPENROUTER_MAX_COMPONENT_PROMPT_BYTES + 1),
            300,
        )

    assert calls == []


def test_hybrid_calls_every_model_once_preserves_evidence_and_feeds_prior_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, int]] = []

    def run_component(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
        calls.append((provider, prompt, timeout_seconds))
        return _component_record(provider)

    monkeypatch.setattr(frontier_module, "_run_openrouter_provider", run_component)

    result = frontier_module._run_openrouter_hybrid("base objective", 91)

    called_providers = [provider for provider, _, _ in calls]
    assert len(called_providers) == 4
    assert {provider: called_providers.count(provider) for provider in EXPECTED_COMPONENTS} == {
        provider: 1 for provider in EXPECTED_COMPONENTS
    }
    assert all(timeout_seconds == 91 for _, _, timeout_seconds in calls)
    assert result["provider"] == HYBRID_PROVIDER
    assert result["hybrid_policy"] == HYBRID_POLICY
    assert result["component_models"] == list(EXPECTED_PROVIDER_MODELS.values())
    assert len(result["component_results"]) == 4
    assert len(result["component_analyses"]) == 4
    assert result["structured_analysis"] == _expected_conservative_analysis()
    assert result["structured_analysis"]["summary"] == _analysis("openrouter_claude_sonnet_5")["summary"]
    assert result["structured_analysis"]["hypotheses"] == _analysis("openrouter_claude_sonnet_5")["hypotheses"]
    assert result["structured_analysis"]["recommended_experiments"] == _analysis(
        "openrouter_claude_sonnet_5"
    )["recommended_experiments"]
    assert result["structured_analysis"]["adversarial_findings"] == _expected_conservative_analysis()[
        "adversarial_findings"
    ]
    assert result["structured_analysis"]["uncertainties"] == _expected_conservative_analysis()["uncertainties"]
    assert len(result["structured_analysis"]["adversarial_findings"]) == 3
    assert len(result["structured_analysis"]["uncertainties"]) == 3
    assert _analysis("openrouter_gemini_3_6_flash")["adversarial_findings"][0] in result[
        "structured_analysis"
    ]["adversarial_findings"]
    assert _analysis("openrouter_luna_5_6")["abstain"] is True
    assert _analysis("openrouter_claude_sonnet_5")["abstain"] is False
    assert result["structured_analysis"]["abstain"] is True

    routing_plan = _routing_records(result["routing_plan"])
    assert tuple(
        (
            str(record["provider"]),
            _metadata_value(record, "role", "role_id"),
            _metadata_value(record, "stage", "stage_id"),
        )
        for record in routing_plan
    ) == EXPECTED_ROUTING_PLAN

    prompts = {provider: prompt for provider, prompt, _ in calls}
    assert "bounded-summary::openrouter_gemini_3_6_flash" in prompts["openrouter_glm_5_2"]
    assert "bounded-summary::openrouter_luna_5_6" in prompts["openrouter_glm_5_2"]
    assert "bounded-summary::openrouter_gemini_3_6_flash" in prompts["openrouter_claude_sonnet_5"]
    assert "bounded-summary::openrouter_luna_5_6" in prompts["openrouter_claude_sonnet_5"]
    assert "bounded-summary::openrouter_glm_5_2" in prompts["openrouter_claude_sonnet_5"]

    for index, provider in enumerate(EXPECTED_COMPONENTS):
        component_analysis = result["component_analyses"][index]
        assert component_analysis["provider"] == provider
        assert component_analysis["model"] == EXPECTED_PROVIDER_MODELS[provider]
        assert component_analysis["analysis"] == _analysis(provider)


def test_conservative_risk_cap_round_robins_across_every_model() -> None:
    component_records: list[dict[str, Any]] = []
    for provider in EXPECTED_COMPONENTS:
        record = _component_record(provider)
        analysis = dict(record["structured_analysis"])
        analysis["adversarial_findings"] = [
            {
                "title": f"risk::{provider}::{index}",
                "risk": "bounded source-specific risk",
                "evidence_needed": "independent settlement",
            }
            for index in range(8)
        ]
        analysis["uncertainties"] = [
            f"uncertainty::{provider}::{index}"
            for index in range(8)
        ]
        record["structured_analysis"] = analysis
        component_records.append(record)

    result = frontier_module._conservative_adjudicated_analysis(tuple(component_records))

    fair_provider_order = (
        "openrouter_glm_5_2",
        "openrouter_claude_sonnet_5",
        "openrouter_gemini_3_6_flash",
        "openrouter_luna_5_6",
    )
    expected_titles = [
        f"risk::{provider}::{index}"
        for index in range(2)
        for provider in fair_provider_order
    ]
    expected_uncertainties = [
        f"uncertainty::{provider}::{index}"
        for index in range(2)
        for provider in fair_provider_order
    ]
    assert [record["title"] for record in result["adversarial_findings"]] == expected_titles
    assert result["uncertainties"] == expected_uncertainties


@pytest.mark.parametrize("failing_provider", EXPECTED_COMPONENTS)
def test_hybrid_fails_closed_when_any_required_component_fails(
    monkeypatch: pytest.MonkeyPatch,
    failing_provider: str,
) -> None:
    calls: list[str] = []

    def run_component(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
        del prompt, timeout_seconds
        calls.append(provider)
        if provider == failing_provider:
            raise RuntimeError(f"required component failed: {provider}")
        return _component_record(provider)

    monkeypatch.setattr(frontier_module, "_run_openrouter_provider", run_component)

    with pytest.raises(RuntimeError, match=failing_provider):
        frontier_module._run_openrouter_hybrid("base objective", 91)

    assert failing_provider in calls


def test_hybrid_failure_aggregates_paid_evidence_from_completed_and_failed_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_component(provider: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
        del prompt, timeout_seconds
        if provider == "openrouter_glm_5_2":
            raise frontier_module.OpenRouterPaidFailure(
                "fixture deep review failed",
                {"prompt_tokens": 60, "completion_tokens": 40, "total_tokens": 100, "cost": 0.006},
                2,
                ("glm-paid-1", "glm-paid-2"),
            )
        record = _component_record(provider)
        record["paid_response_count"] = 1
        record["paid_response_ids"] = [f"paid::{provider}"]
        return record

    monkeypatch.setattr(frontier_module, "_run_openrouter_provider", run_component)

    with pytest.raises(frontier_module.OpenRouterPaidFailure) as raised:
        frontier_module._run_openrouter_hybrid("base objective", 300)

    assert raised.value.paid_response_count == 4
    assert raised.value.paid_response_ids == (
        "paid::openrouter_gemini_3_6_flash",
        "paid::openrouter_luna_5_6",
        "glm-paid-1",
        "glm-paid-2",
    )
    assert raised.value.usage == {
        "prompt_tokens": 80,
        "completion_tokens": 80,
        "total_tokens": 160,
        "cost": 0.008,
    }


@pytest.mark.parametrize("provider,model", tuple(EXPECTED_PROVIDER_MODELS.items()))
def test_each_component_uses_its_exact_openrouter_model_and_redacts_the_key(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
) -> None:
    requests_seen: list[dict[str, Any]] = []

    def post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: int,
    ) -> _FakeOpenRouterResponse:
        requests_seen.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": dict(json),
                "timeout": timeout,
            }
        )
        return _FakeOpenRouterResponse(f"response::{provider}", _analysis(provider))

    monkeypatch.setattr(frontier_module, "resolve_openrouter_api_key", lambda: TEST_API_KEY)
    monkeypatch.setattr(frontier_module.requests, "post", post)

    result = frontier_module._run_openrouter_provider(provider, "bounded prompt", 73)

    assert len(requests_seen) == 1
    assert requests_seen[0]["url"] == frontier_module.OPENROUTER_ENDPOINT
    assert requests_seen[0]["body"]["model"] == model
    assert requests_seen[0]["timeout"] == 73
    assert result["model"] == model
    assert result["structured_analysis"] == _analysis(provider)
    assert TEST_API_KEY not in json.dumps(result, sort_keys=True)


def test_paid_contract_retry_aggregates_every_2xx_usage_and_response_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = "openrouter_gemini_3_6_flash"
    responses = [
        _PaidOpenRouterResponse(
            "paid-invalid",
            {"summary": "invalid incomplete contract"},
            {"prompt_tokens": 11, "completion_tokens": 13, "total_tokens": 24, "cost": 0.01},
        ),
        _PaidOpenRouterResponse(
            "paid-valid",
            _analysis(provider),
            {"prompt_tokens": 17, "completion_tokens": 19, "total_tokens": 36, "cost": 0.02},
        ),
    ]
    calls: list[int] = []

    def post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: int,
    ) -> _PaidOpenRouterResponse:
        del url, headers, json, timeout
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr(frontier_module, "resolve_openrouter_api_key", lambda: TEST_API_KEY)
    monkeypatch.setattr(frontier_module.requests, "post", post)

    result = frontier_module._run_openrouter_provider(provider, "bounded prompt", 300)

    assert frontier_module.OPENROUTER_MAX_ATTEMPTS == 2
    assert len(calls) == 2
    assert result["attempt"] == 2
    assert result["paid_response_count"] == 2
    assert result["paid_response_ids"] == ["paid-invalid", "paid-valid"]
    assert result["response_id"] == "paid-valid"
    assert result["usage"] == {
        "prompt_tokens": 28,
        "completion_tokens": 32,
        "total_tokens": 60,
        "cost": 0.03,
    }
    assert TEST_API_KEY not in json.dumps(result, sort_keys=True)


def test_paid_contract_failure_stops_after_two_attempts_with_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = "openrouter_gemini_3_6_flash"
    calls: list[int] = []

    def post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: int,
    ) -> _PaidOpenRouterResponse:
        del url, headers, json, timeout
        calls.append(1)
        return _PaidOpenRouterResponse(
            f"paid-invalid-{len(calls)}",
            {"summary": "invalid incomplete contract"},
            {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8, "cost": 0.004},
        )

    monkeypatch.setattr(frontier_module, "resolve_openrouter_api_key", lambda: TEST_API_KEY)
    monkeypatch.setattr(frontier_module.requests, "post", post)

    with pytest.raises(frontier_module.OpenRouterPaidFailure) as raised:
        frontier_module._run_openrouter_provider(provider, "bounded prompt", 300)

    assert len(calls) == 2
    assert raised.value.paid_response_count == 2
    assert raised.value.paid_response_ids == ("paid-invalid-1", "paid-invalid-2")
    assert raised.value.usage == {
        "prompt_tokens": 6,
        "completion_tokens": 10,
        "total_tokens": 16,
        "cost": 0.008,
    }


def test_existing_dpapi_config_is_reused_unchanged_and_state_is_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "provider-control"
    config_path = runtime_root / provider_control_module.CONFIG_FILENAME
    secret_path = runtime_root / "secrets" / provider_control_module.SECRET_FILENAME
    control = _provider_control()
    config_payload = json.dumps(control, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    ciphertext = b"existing-dpapi-ciphertext-must-not-be-rewritten"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_bytes(config_payload)
    secret_path.write_bytes(ciphertext)

    monkeypatch.setenv("DOPEY_PROVIDER_CONTROL_ROOT", str(runtime_root))
    monkeypatch.setattr(
        provider_control_module,
        "_unprotect_secret",
        lambda payload: TEST_API_KEY.encode("utf-8") if payload == ciphertext else b"unexpected",
    )

    state = provider_control_module.provider_control_state()
    resolved_key = provider_control_module.resolve_openrouter_api_key()

    assert resolved_key == TEST_API_KEY
    assert provider_control_module.SCHEMA_VERSION == "dopey-provider-control-v1"
    assert provider_control_module.SECRET_FILENAME == "openrouter_api_key.dpapi"
    assert provider_control_module.CONFIG_FILENAME == "provider_control.json"
    assert state["credential"]["source"] == "windows_dpapi_user_scope"
    assert state["credential"]["configured"] is True
    assert state["credential"]["usable"] is True
    assert state["credential"]["validation_status"] == "validated_usable"
    assert state["credential"]["plaintext_exposed"] is False
    assert state["credential"]["repository_storage"] is False
    assert state["api_key_value_exposed"] is False
    assert state["providers"] == control["providers"]
    assert _roster_models(state["active_model_roster"]) == list(EXPECTED_PROVIDER_MODELS.values())
    assert TEST_API_KEY not in json.dumps(state, sort_keys=True)
    assert config_path.read_bytes() == config_payload
    assert secret_path.read_bytes() == ciphertext


def test_unusable_dpapi_key_blocks_route_without_rewriting_existing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "provider-control"
    config_path = runtime_root / provider_control_module.CONFIG_FILENAME
    secret_path = runtime_root / "secrets" / provider_control_module.SECRET_FILENAME
    control = _provider_control()
    config_payload = json.dumps(control, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    ciphertext = b"configured-but-unusable-dpapi-ciphertext"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_bytes(config_payload)
    secret_path.write_bytes(ciphertext)

    def reject_secret(payload: bytes) -> bytes:
        assert payload == ciphertext
        raise provider_control_module.ProviderControlError("fixture DPAPI validation failure")

    monkeypatch.setenv("DOPEY_PROVIDER_CONTROL_ROOT", str(runtime_root))
    monkeypatch.setattr(provider_control_module, "_unprotect_secret", reject_secret)

    state = provider_control_module.provider_control_state()

    assert state["credential"]["configured"] is True
    assert state["credential"]["usable"] is False
    assert state["credential"]["validation_status"] == "configured_unusable"
    assert state["active_route_available"] is False
    with pytest.raises(provider_control_module.ProviderControlError, match="configured and usable"):
        provider_control_module.set_provider_enabled("openrouter_hybrid", True)
    assert config_path.read_bytes() == config_payload
    assert secret_path.read_bytes() == ciphertext


def test_llm_research_uses_one_hybrid_council_and_reuses_final_adjudication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], int]] = []
    council = _hybrid_council_result()

    def run_council(
        objective: str,
        providers: tuple[str, ...],
        state: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        assert objective
        assert state
        calls.append((providers, timeout_seconds))
        return council

    monkeypatch.setattr(llm_research_module, "load_provider_control", _provider_control)
    monkeypatch.setattr(llm_research_module, "run_frontier_council", run_council)

    discovery_routes, synthesis_routes = llm_research_module._provider_routes(_provider_control())
    assert discovery_routes == (HYBRID_PROVIDER,)
    assert synthesis_routes == ()

    output = llm_research_module.run_llm_research_cycle(
        tmp_path,
        tmp_path / "artifacts" / "dopey" / "llm_research",
        90,
        True,
        datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
    )

    assert calls == [((HYBRID_PROVIDER,), 90)]
    assert output["discovery_provider_routes"] == [HYBRID_PROVIDER]
    assert output["synthesis_provider_routes"] == []
    assert output["discovery_council"]["results"][0]["structured_analysis"] == _expected_conservative_analysis()
    assert output["synthesis_council"]["results"][0]["structured_analysis"] == _expected_conservative_analysis()
    assert output["provider_models"] == list(EXPECTED_PROVIDER_MODELS.values())
    assert output["synthesis_council"]["providers"] == [HYBRID_PROVIDER]
    assert output["synthesis_council"]["requested_provider_count"] == 1
    assert output["synthesis_council"]["completed_provider_count"] == 1
    assert output["synthesis_council"]["reused_discovery_result_count"] == 1
    assert output["synthesis_council"]["additional_frontier_call_count"] == 0
    assert output["synthesis_council"]["additional_frontier_call_performed"] is False
    assert output["synthesis_council"]["additional_reported_cost_usd"] == 0.0
    assert output["synthesis_council"]["reused_discovery_cost_counted_again"] is False
    assert output["additional_synthesis_frontier_call_performed"] is False
    assert output["reported_openrouter_cost_usd"] == 0.004
    assert output["paper_only"] is True
    assert output["live_blocked"] is True
    assert output["no_order_authority"] is True
