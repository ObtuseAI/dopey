"""Deterministic defined-risk option-structure builder for DOPEY.

The builder consumes fixture candidates only. It never fetches data, never connects to a
broker, and never creates live execution authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .defined_risk_structures import validate_defined_risk_structure
from .greeks_validation import summarize_greek_exposure
from .structure_profiles import STRUCTURE_PROFILE_VERSION, profile_for_structure


STRUCTURE_BUILDER_VERSION = "dopey-structure-builder-v1"


@dataclass(frozen=True)
class OptionLeg:
    side: str
    symbol: str
    strike: float
    expiry: str
    option_type: str
    mid: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    spread_pct: float
    liquidity_score: float
    liquidity_verdict: str
    quote_stability_score: float
    fillability_score: float
    depth_proxy_score: float
    slippage_sensitivity_score: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float
    ratio: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OptionStructure:
    structure_type: str
    execution_structure: str
    family: str
    legs: list[OptionLeg]
    paper_only: bool
    defined_risk: bool
    directional_bias: str
    volatility_bias: str
    model_version: str = STRUCTURE_BUILDER_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["legs"] = [leg.to_dict() for leg in self.legs]
        return data


@dataclass(frozen=True)
class StructureBuildRequest:
    structure_type: str
    strategy_family: str
    symbol: str
    regime_tag: str
    candidates: list[dict]
    quantity: int = 1
    allow_undefined_risk: bool = False
    paper_only: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StructureRiskSummary:
    structure_type: str
    execution_structure: str
    leg_count: int
    net_debit: float
    net_credit: float
    max_loss: float
    max_reward: float
    directional_bias: str
    volatility_bias: str
    greek_exposure_summary: dict
    liquidity_aggregate: float
    slippage_aggregate: float
    structure_safety_verdict: str
    active_policy_status: str
    active_policy_reasons: list[str]
    unsafe_reasons: list[str] = field(default_factory=list)
    model_version: str = STRUCTURE_BUILDER_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StructureBuildResult:
    request: StructureBuildRequest
    structure: OptionStructure | None
    risk_summary: StructureRiskSummary
    ok: bool
    rejection_reason: str = ""
    model_version: str = STRUCTURE_BUILDER_VERSION

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "structure": self.structure.to_dict() if self.structure else None,
            "risk_summary": self.risk_summary.to_dict(),
            "ok": self.ok,
            "rejection_reason": self.rejection_reason,
            "model_version": self.model_version,
        }


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _candidate_mid(candidate: dict) -> float:
    mid = _as_float(candidate.get("mid"), 0.0)
    if mid > 0.0:
        return mid
    bid = _as_float(candidate.get("bid"), 0.0)
    ask = _as_float(candidate.get("ask"), 0.0)
    return round((bid + ask) / 2.0, 6) if bid > 0.0 and ask > 0.0 else _as_float(candidate.get("last"), 0.0)


def _candidate_spread_pct(candidate: dict, mid: float) -> float:
    explicit = _as_float(candidate.get("spread_pct"), 0.0)
    if explicit > 0.0:
        return explicit
    bid = _as_float(candidate.get("bid"), mid)
    ask = _as_float(candidate.get("ask"), mid)
    return round((ask - bid) / mid, 6) if mid > 0.0 else 1.0


def _leg(candidate: dict, side: str, ratio: float) -> OptionLeg:
    mid = _candidate_mid(candidate)
    return OptionLeg(
        side=side,
        symbol=str(candidate.get("symbol", "")),
        strike=_as_float(candidate.get("strike"), 0.0),
        expiry=str(candidate.get("expiry", "")),
        option_type=str(candidate.get("option_type", "call")),
        mid=mid,
        bid=_as_float(candidate.get("bid"), mid),
        ask=_as_float(candidate.get("ask"), mid),
        volume=_as_int(candidate.get("volume"), 0),
        open_interest=_as_int(candidate.get("open_interest"), 0),
        spread_pct=_candidate_spread_pct(candidate, mid),
        liquidity_score=_as_float(candidate.get("liquidity_score", candidate.get("liquidity")), 0.5),
        liquidity_verdict=str(candidate.get("liquidity_verdict", "")),
        quote_stability_score=_as_float(candidate.get("quote_stability_score"), 0.5),
        fillability_score=_as_float(candidate.get("fillability_score"), 0.5),
        depth_proxy_score=_as_float(candidate.get("depth_proxy_score"), 0.0),
        slippage_sensitivity_score=_as_float(
            candidate.get("slippage_sensitivity_score", candidate.get("expected_slippage_pct")),
            0.02,
        ),
        delta=_as_float(candidate.get("delta"), 0.0),
        gamma=_as_float(candidate.get("gamma"), 0.0),
        theta=_as_float(candidate.get("theta"), 0.0),
        vega=_as_float(candidate.get("vega"), 0.0),
        rho=_as_float(candidate.get("rho"), 0.0),
        iv=_as_float(candidate.get("iv"), 0.0),
        ratio=ratio,
    )


def _strikes(candidates: list[dict]) -> tuple[float, float, float]:
    strikes = sorted({round(_as_float(candidate.get("strike"), 0.0), 6) for candidate in candidates})
    if len(strikes) >= 3:
        return strikes[0], strikes[len(strikes) // 2], strikes[-1]
    if len(strikes) == 2:
        low, high = strikes
        return low, round((low + high) / 2.0, 6), high
    strike = strikes[0] if strikes else 450.0
    return strike - 10.0, strike, strike + 10.0


def _by_strike_and_type(candidates: list[dict], option_type: str, strike: float) -> dict | None:
    exact = [
        candidate for candidate in candidates
        if candidate.get("option_type") == option_type
        and abs(_as_float(candidate.get("strike"), 0.0) - strike) < 1e-9
    ]
    if exact:
        return exact[0]
    typed = [candidate for candidate in candidates if candidate.get("option_type") == option_type]
    if not typed:
        return None
    typed.sort(key=lambda candidate: abs(_as_float(candidate.get("strike"), 0.0) - strike))
    return typed[0]


def _select_structure_legs(structure_type: str, candidates: list[dict]) -> list[OptionLeg]:
    low, mid, high = _strikes(candidates)
    if structure_type == "long_call_vertical":
        buy = _by_strike_and_type(candidates, "call", mid)
        sell = _by_strike_and_type(candidates, "call", high)
        if buy is None or sell is None:
            raise ValueError("long_call_vertical requires call candidates")
        return [_leg(buy, "buy", 1.0), _leg(sell, "sell", 1.0)]
    if structure_type == "long_put_vertical":
        buy = _by_strike_and_type(candidates, "put", mid)
        sell = _by_strike_and_type(candidates, "put", low)
        if buy is None or sell is None:
            raise ValueError("long_put_vertical requires put candidates")
        return [_leg(buy, "buy", 1.0), _leg(sell, "sell", 1.0)]
    if structure_type == "long_straddle_proxy":
        call = _by_strike_and_type(candidates, "call", mid)
        put = _by_strike_and_type(candidates, "put", mid)
        if call is None or put is None:
            raise ValueError("long_straddle_proxy requires call and put candidates")
        return [_leg(call, "buy", 1.0), _leg(put, "buy", 1.0)]
    if structure_type == "long_strangle_proxy":
        call = _by_strike_and_type(candidates, "call", high)
        put = _by_strike_and_type(candidates, "put", low)
        if call is None or put is None:
            raise ValueError("long_strangle_proxy requires call and put candidates")
        return [_leg(call, "buy", 1.0), _leg(put, "buy", 1.0)]
    if structure_type in {"iron_condor_proxy", "credit_spread_pair_proxy"}:
        short_call = _by_strike_and_type(candidates, "call", mid)
        long_call = _by_strike_and_type(candidates, "call", high)
        short_put = _by_strike_and_type(candidates, "put", mid)
        long_put = _by_strike_and_type(candidates, "put", low)
        if not all([short_call, long_call, short_put, long_put]):
            raise ValueError(f"{structure_type} requires protected call and put spreads")
        return [
            _leg(short_call or {}, "sell", 1.0),
            _leg(long_call or {}, "buy", 1.0),
            _leg(short_put or {}, "sell", 1.0),
            _leg(long_put or {}, "buy", 1.0),
        ]
    if structure_type == "butterfly_proxy":
        low_call = _by_strike_and_type(candidates, "call", low)
        mid_call = _by_strike_and_type(candidates, "call", mid)
        high_call = _by_strike_and_type(candidates, "call", high)
        if not all([low_call, mid_call, high_call]):
            raise ValueError("butterfly_proxy requires three call strikes")
        return [_leg(low_call or {}, "buy", 1.0), _leg(mid_call or {}, "sell", 2.0), _leg(high_call or {}, "buy", 1.0)]
    if structure_type == "short_dte_debit_spread_proxy":
        buy = _by_strike_and_type(candidates, "call", mid)
        sell = _by_strike_and_type(candidates, "call", high)
        if buy is None or sell is None:
            raise ValueError("short_dte_debit_spread_proxy requires call candidates")
        return [_leg(buy, "buy", 1.0), _leg(sell, "sell", 1.0)]
    raise ValueError(f"unsupported structure_type: {structure_type}")


def _net_premium(legs: list[OptionLeg]) -> float:
    total = 0.0
    for leg in legs:
        value = leg.mid * leg.ratio
        total += value if leg.side == "buy" else -value
    return round(total, 6)


def _width_from_legs(legs: list[OptionLeg]) -> float:
    strikes = sorted({leg.strike for leg in legs})
    if len(strikes) < 2:
        return 0.0
    gaps = [round(strikes[index + 1] - strikes[index], 6) for index in range(len(strikes) - 1)]
    return max(gaps) if gaps else 0.0


def _risk_summary(structure_type: str, execution_structure: str, legs: list[OptionLeg], directional_bias: str, volatility_bias: str, verdict: str, reasons: list[str]) -> StructureRiskSummary:
    leg_dicts = [leg.to_dict() for leg in legs]
    net_premium = _net_premium(legs)
    net_debit = round(max(0.0, net_premium), 6)
    net_credit = round(max(0.0, -net_premium), 6)
    width = _width_from_legs(legs)
    if execution_structure in {"iron_condor"}:
        max_loss = round(max(0.01, width - net_credit), 6)
        max_reward = round(max(0.0, net_credit), 6)
    elif execution_structure in {"strangle"}:
        max_loss = round(max(0.01, net_debit), 6)
        max_reward = round(max_loss * 2.0, 6)
    else:
        max_loss = round(max(0.01, net_debit), 6)
        max_reward = round(max(0.0, width - net_debit), 6)
    liquidity = round(sum(leg.liquidity_score for leg in legs) / len(legs), 6) if legs else 0.0
    slippage = round(sum(leg.slippage_sensitivity_score for leg in legs) / len(legs), 6) if legs else 0.0
    greek_summary = summarize_greek_exposure(leg_dicts).to_dict() if legs else {}
    active_policy_reasons = _active_policy_reasons(structure_type, len(legs))
    return StructureRiskSummary(
        structure_type=structure_type,
        execution_structure=execution_structure,
        leg_count=len(legs),
        net_debit=net_debit,
        net_credit=net_credit,
        max_loss=max_loss,
        max_reward=max_reward,
        directional_bias=directional_bias,
        volatility_bias=volatility_bias,
        greek_exposure_summary=greek_summary,
        liquidity_aggregate=liquidity,
        slippage_aggregate=slippage,
        structure_safety_verdict=verdict,
        active_policy_status="active_policy_compliant" if not active_policy_reasons else "research_legacy_unsupported",
        active_policy_reasons=active_policy_reasons,
        unsafe_reasons=reasons,
    )


def build_option_structure(request: StructureBuildRequest) -> StructureBuildResult:
    try:
        profile = profile_for_structure(request.structure_type)
        legs = _select_structure_legs(request.structure_type, request.candidates)
    except ValueError as exc:
        empty_summary = StructureRiskSummary(
            structure_type=request.structure_type,
            execution_structure="",
            leg_count=0,
            net_debit=0.0,
            net_credit=0.0,
            max_loss=0.0,
            max_reward=0.0,
            directional_bias="",
            volatility_bias="",
            greek_exposure_summary={},
            liquidity_aggregate=0.0,
            slippage_aggregate=0.0,
            structure_safety_verdict="unsafe_rejected",
            active_policy_status="rejected_by_active_policy",
            active_policy_reasons=["not_active_trading_policy_compliant"],
            unsafe_reasons=[str(exc)],
        )
        return StructureBuildResult(request, None, empty_summary, False, str(exc))
    leg_dicts = [leg.to_dict() for leg in legs]
    safety = validate_defined_risk_structure(
        request.structure_type,
        request.allow_undefined_risk,
        leg_dicts,
    )
    summary = _risk_summary(
        request.structure_type,
        profile.execution_structure,
        legs,
        profile.directional_bias,
        profile.volatility_bias,
        safety.verdict,
        safety.reasons,
    )
    if not safety.safe:
        return StructureBuildResult(request, None, summary, False, "; ".join(safety.reasons))
    structure = OptionStructure(
        structure_type=request.structure_type,
        execution_structure=profile.execution_structure,
        family=request.strategy_family,
        legs=legs,
        paper_only=True,
        defined_risk=True,
        directional_bias=profile.directional_bias,
        volatility_bias=profile.volatility_bias,
    )
    return StructureBuildResult(request, structure, summary, True, "")


def structure_type_for_family(strategy_family: str, regime_tag: str, parameters: dict[str, Any]) -> str:
    proxy = str(parameters.get("spread_structure_proxy", ""))
    if strategy_family == "directional_convexity":
        if "bearish" in proxy or regime_tag in {"bearish_breakdown", "macro_shock_risk_off"}:
            return "long_put_vertical"
        return "long_call_vertical"
    if strategy_family == "volatility_expansion":
        if proxy == "long_straddle_proxy":
            return "long_straddle_proxy"
        return "long_strangle_proxy"
    if strategy_family == "volatility_compression":
        if proxy == "credit_spread_pair_proxy":
            return "credit_spread_pair_proxy"
        return "iron_condor_proxy"
    if strategy_family == "short_duration_defined_risk":
        if proxy == "short_dte_debit_spread_proxy":
            return "short_dte_debit_spread_proxy"
        return "butterfly_proxy"
    return "long_call_vertical"


def _active_policy_reasons(structure_type: str, leg_count: int) -> list[str]:
    reasons: list[str] = []
    if structure_type not in {"long_call", "long_put", "single"}:
        reasons.append("not_active_trading_policy_compliant")
    if leg_count != 1:
        reasons.append("unsupported_multileg_structure_rejected")
    if structure_type in {"short_straddle", "short_strangle", "credit_spread_pair_proxy", "iron_condor_proxy"}:
        reasons.append("undefined_risk_structure_rejected")
    output: list[str] = []
    for reason in reasons:
        if reason not in output:
            output.append(reason)
    return output


def build_structure_for_family(
    strategy_family: str,
    symbol: str,
    ranked_candidates: list[dict],
    regime_tag: str,
    parameters: dict[str, Any],
) -> StructureBuildResult:
    structure_type = structure_type_for_family(strategy_family, regime_tag, parameters)
    request = StructureBuildRequest(
        structure_type=structure_type,
        strategy_family=strategy_family,
        symbol=symbol,
        regime_tag=regime_tag,
        candidates=ranked_candidates,
        quantity=1,
        allow_undefined_risk=False,
        paper_only=True,
    )
    return build_option_structure(request)
