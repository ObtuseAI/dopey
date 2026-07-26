"""Strategy Claim Compiler: external claim -> falsifiable options specification.

The r/ai_trading audit's highest-value import (#1): a claim like "buy calls when
momentum turns bullish" is not testable until it is pinned down - which momentum
measure, which expiration, which delta, does IV rank matter, are earnings
allowed, how wide a spread is acceptable. This compiler ingests raw claim text
and produces a STRUCTURED, falsifiable options spec that DOPEY's existing
prosecution machinery can then test and (almost always) refuse.

Division of labor, per the same audit's #2 and DOPEY's constitution:
- the LLM (the existing gemini-3.6-flash OpenRouter config) does INTERPRETATION
  ONLY - it extracts the claimed fields and writes the faithful / conservative /
  cost-aware interpretations plus a benchmark. It never prices an option,
  computes a Greek, sizes a position, or asserts an edge.
- deterministic code owns everything execution-sensitive: it validates the
  returned structure against a fixed schema, coerces types, and stamps the spec
  unvalidated_hypothesis / paper_only / live_blocked / promotion_ineligible so
  a compiled claim can never masquerade as evidence or authority.

The LLM lives here in dopey_acceleration (the sanctioned in-repo LLM lane), not
in the LLM-free core. A compiled spec is a hypothesis to prosecute, nothing
more.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from dopey_acceleration.frontier import (
    OPENROUTER_ENDPOINT,
    OPENROUTER_MODELS,
    _redacted_error_text,
)
from dopey_acceleration.provider_control import ProviderControlError, resolve_openrouter_api_key

COMPILER_VERSION = "dopey-strategy-claim-compiler-v1"
COMPILER_PROVIDER = "openrouter_gemini_3_6_flash"  # the existing config, per request
LLM_TIMEOUT_SECONDS = 60

EXTRACTED_FIELDS = (
    "underlying_universe",
    "thesis_direction",
    "entry_trigger",
    "holding_period",
    "expiration_rule",
    "strike_delta_rule",
    "max_acceptable_spread",
    "iv_assumptions",
    "exit_conditions",
    "invalidation_conditions",
    "position_sizing",
    "claimed_stats",
    "missing_or_ambiguous",
)
INTERPRETATIONS = ("faithful", "conservative", "cost_aware", "benchmark")

_SYSTEM_PROMPT = (
    "You are an analysis-only research assistant. You convert a trading claim into a "
    "STRUCTURED, falsifiable options specification for later independent testing. You "
    "NEVER assert profitability, edge, readiness, or authority; you NEVER price options, "
    "compute Greeks, size positions, or produce an execution instruction. If a field is "
    "not stated in the claim, mark it explicitly as missing rather than inventing it. "
    "Return ONLY a JSON object matching the requested schema."
)


class ClaimCompilerError(RuntimeError):
    """Raised when the LLM output cannot be validated into a claim spec."""


def _prompt(raw_claim: str) -> str:
    fields = ", ".join(EXTRACTED_FIELDS)
    return (
        "Extract a falsifiable options specification from the trading claim below.\n\n"
        f"CLAIM:\n{raw_claim.strip()[:6000]}\n\n"
        "Return a JSON object with exactly these top-level keys: 'extracted' and "
        "'interpretations'.\n"
        f"'extracted' must be an object with these string keys: {fields}. "
        "Every value is a short string; 'missing_or_ambiguous' is an array of strings "
        "naming every rule the claim leaves undefined (expiration, delta, IV rank, "
        "earnings handling, spread tolerance, exit, sizing, etc.). "
        "'thesis_direction' must be one of: bullish, bearish, neutral, unclear.\n"
        "'interpretations' must be an object with keys 'faithful', 'conservative', "
        "'cost_aware', 'benchmark'. Each of the first three is an object with keys "
        "'entry', 'expiration', 'strike_or_delta', 'exit', 'notes'. 'benchmark' is a "
        "short string naming a simple comparison (e.g. buy-and-hold the underlying, or "
        "no-trade). Do not assert any claim is profitable."
    )


def _gemini_call(prompt: str) -> dict[str, Any]:
    """Single-model call to the existing gemini-3.6-flash OpenRouter config.

    Returns the parsed JSON object the model produced. Raises
    ClaimCompilerError on any credential / transport / parse failure so the
    caller can degrade to an explicit unavailable status rather than crash.
    """
    import requests  # local: keep the module importable without the dep resolved

    try:
        api_key = resolve_openrouter_api_key()
    except ProviderControlError as error:
        raise ClaimCompilerError(f"llm_credential_unavailable: {error}") from error
    body = {
        "model": OPENROUTER_MODELS[COMPILER_PROVIDER],
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ObtuseAI/dopey",
        "X-Title": "DOPEY strategy claim compiler",
    }
    try:
        response = requests.post(OPENROUTER_ENDPOINT, headers=headers, json=body, timeout=LLM_TIMEOUT_SECONDS)
        response.raise_for_status()
        envelope = response.json()
        content = envelope["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as error:  # noqa: BLE001 - any failure degrades to unavailable
        error_text = _redacted_error_text(str(error), api_key)
        raise ClaimCompilerError(
            f"llm_call_failed: {type(error).__name__}: {error_text[:200]}"
        ) from error


def validate_and_stamp(
    llm_output: dict[str, Any],
    raw_claim: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Validate the LLM's structure and stamp the spec - the deterministic half.

    The LLM's role ends here: nothing it returns can set an honesty flag, a
    price, a size, or a gate. Those are stamped by this function, always.
    """
    if not isinstance(llm_output, dict):
        raise ClaimCompilerError("llm output is not an object")
    extracted = llm_output.get("extracted")
    interpretations = llm_output.get("interpretations")
    if not isinstance(extracted, dict) or not isinstance(interpretations, dict):
        raise ClaimCompilerError("llm output missing 'extracted' or 'interpretations'")
    clean_extracted: dict[str, Any] = {}
    for field in EXTRACTED_FIELDS:
        value = extracted.get(field)
        if field == "missing_or_ambiguous":
            clean_extracted[field] = [str(v) for v in value] if isinstance(value, list) else []
        else:
            clean_extracted[field] = str(value) if value is not None else "not_stated"
    direction = str(clean_extracted.get("thesis_direction", "unclear")).lower()
    if direction not in ("bullish", "bearish", "neutral", "unclear"):
        direction = "unclear"
    clean_extracted["thesis_direction"] = direction
    clean_interps: dict[str, Any] = {}
    for key in INTERPRETATIONS:
        clean_interps[key] = interpretations.get(key, "not_provided")
    return {
        "artifact_type": "compiled_strategy_claim",
        "compiler_version": COMPILER_VERSION,
        "compiled_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": str(source.get("kind", "unknown")),
            "ref": str(source.get("ref", "")),
            "raw_excerpt": raw_claim.strip()[:600],
        },
        "extracted": clean_extracted,
        "interpretations": clean_interps,
        "llm_role": "interpretation_only_no_pricing_sizing_or_authority",
        "llm_provider": COMPILER_PROVIDER,
        # Deterministic honesty stamps - the LLM cannot set or clear these.
        "evidence_status": "unvalidated_hypothesis",
        "not_edge_evidence": True,
        "profitability_claim": False,
        "promotion_allowed": False,
        "requires_prosecution": [
            "historical_option_chain_test",
            "cost_and_slippage_stress",
            "walk_forward_and_holdout",
            "multiple_testing_correction",
            "forward_settlement",
        ],
        "paper_only": True,
        "live_blocked": True,
    }


def compile_claim(
    raw_claim: str,
    source: dict[str, Any] | None = None,
    llm_call: Callable[[str], dict[str, Any]] = _gemini_call,
) -> dict[str, Any]:
    """Compile raw claim text into a stamped, falsifiable options spec.

    On LLM failure returns an explicit unavailable spec (never a fabricated
    one). llm_call is injectable so the deterministic half is testable offline.
    """
    source = source or {}
    if not raw_claim or not raw_claim.strip():
        raise ClaimCompilerError("empty claim text")
    try:
        llm_output = llm_call(_prompt(raw_claim))
    except ClaimCompilerError as error:
        return {
            "artifact_type": "compiled_strategy_claim",
            "compiler_version": COMPILER_VERSION,
            "compile_status": "llm_unavailable",
            "reason": str(error),
            "source": {"kind": str(source.get("kind", "unknown")), "ref": str(source.get("ref", ""))},
            "evidence_status": "unvalidated_hypothesis",
            "not_edge_evidence": True,
            "promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
    spec = validate_and_stamp(llm_output, raw_claim, source)
    spec["compile_status"] = "compiled"
    return spec
