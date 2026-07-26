"""Strategy Claim Compiler - LLM interprets, deterministic code owns the truth.

The LLM's output can never set an honesty flag, price, size, or gate: the
compiler always stamps unvalidated_hypothesis / not_edge / promotion-ineligible
and forces the prosecution requirements. A malformed or malicious LLM response
must be rejected or coerced, never trusted; an unavailable LLM degrades to an
explicit status, never a fabricated spec. The LLM call is injected so this is
tested with no network.
"""
from __future__ import annotations

import pytest

import dopey_acceleration.strategy_claim_compiler as compiler_module
from dopey_acceleration.strategy_claim_compiler import (
    ClaimCompilerError,
    compile_claim,
    validate_and_stamp,
)


def _good_llm_output():
    return {
        "extracted": {
            "underlying_universe": "large-cap tech",
            "thesis_direction": "bullish",
            "entry_trigger": "20-day momentum turns positive",
            "holding_period": "not_stated",
            "expiration_rule": "not_stated",
            "strike_delta_rule": "not_stated",
            "max_acceptable_spread": "not_stated",
            "iv_assumptions": "not_stated",
            "exit_conditions": "not_stated",
            "invalidation_conditions": "not_stated",
            "position_sizing": "not_stated",
            "claimed_stats": "none given",
            "missing_or_ambiguous": ["expiration", "delta", "IV rank", "exit rule", "sizing"],
        },
        "interpretations": {
            "faithful": {"entry": "buy calls on momentum flip", "expiration": "~30 DTE", "strike_or_delta": "ATM", "exit": "unspecified", "notes": "as literally stated"},
            "conservative": {"entry": "require volume confirmation", "expiration": "45-60 DTE", "strike_or_delta": "0.6 delta", "exit": "time stop 10d", "notes": "tighter"},
            "cost_aware": {"entry": "only liquid names, spread<=5%", "expiration": "45 DTE", "strike_or_delta": "0.55 delta", "exit": "close before theta accel", "notes": "cost-sensitive"},
            "benchmark": "buy-and-hold the underlying",
        },
    }


def test_compile_stamps_are_deterministic_not_from_llm() -> None:
    # even if the LLM tries to claim profitability/authority, the compiler
    # overrides with honest stamps
    poisoned = _good_llm_output()
    poisoned["promotion_allowed"] = True
    poisoned["not_edge_evidence"] = False
    poisoned["profitability_claim"] = True
    spec = compile_claim("buy calls when momentum turns bullish", {"kind": "reddit"}, llm_call=lambda p: poisoned)
    assert spec["evidence_status"] == "unvalidated_hypothesis"
    assert spec["not_edge_evidence"] is True
    assert spec["promotion_allowed"] is False
    assert spec["profitability_claim"] is False
    assert spec["live_blocked"] is True
    assert "forward_settlement" in spec["requires_prosecution"]


def test_extracts_fields_and_missing_list() -> None:
    spec = compile_claim("buy calls when momentum turns bullish", {"kind": "reddit", "ref": "u/x"}, llm_call=lambda p: _good_llm_output())
    assert spec["compile_status"] == "compiled"
    assert spec["extracted"]["thesis_direction"] == "bullish"
    assert "expiration" in spec["extracted"]["missing_or_ambiguous"]
    assert spec["source"]["kind"] == "reddit"


def test_bad_direction_coerced_to_unclear() -> None:
    out = _good_llm_output()
    out["extracted"]["thesis_direction"] = "MOON"
    spec = validate_and_stamp(out, "claim", {"kind": "reddit"})
    assert spec["extracted"]["thesis_direction"] == "unclear"


def test_missing_fields_default_to_not_stated() -> None:
    out = {"extracted": {"thesis_direction": "bearish"}, "interpretations": {}}
    spec = validate_and_stamp(out, "claim", {})
    assert spec["extracted"]["entry_trigger"] == "not_stated"
    assert spec["extracted"]["missing_or_ambiguous"] == []
    assert spec["interpretations"]["faithful"] == "not_provided"


def test_malformed_llm_output_rejected() -> None:
    with pytest.raises(ClaimCompilerError):
        validate_and_stamp(["not", "a", "dict"], "claim", {})
    with pytest.raises(ClaimCompilerError):
        validate_and_stamp({"extracted": {}}, "claim", {})  # missing interpretations


def test_llm_unavailable_degrades_not_crashes() -> None:
    def boom(prompt):
        raise ClaimCompilerError("llm_credential_unavailable: no key")

    spec = compile_claim("buy calls", {"kind": "reddit"}, llm_call=boom)
    assert spec["compile_status"] == "llm_unavailable"
    assert spec["promotion_allowed"] is False
    assert spec["evidence_status"] == "unvalidated_hypothesis"


def test_gemini_transport_error_redacts_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    secret = "sk-sensitive-test-key"
    monkeypatch.setattr(
        compiler_module,
        "resolve_openrouter_api_key",
        lambda: secret,
    )

    def fail_request(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"transport included credential {secret}")

    monkeypatch.setattr(requests, "post", fail_request)

    with pytest.raises(ClaimCompilerError) as captured:
        compiler_module._gemini_call("test prompt")

    assert secret not in str(captured.value)
    assert "<redacted>" in str(captured.value)


def test_empty_claim_rejected() -> None:
    with pytest.raises(ClaimCompilerError):
        compile_claim("   ", {}, llm_call=lambda p: _good_llm_output())
