"""Select strategically tracked option contracts after the equity thesis is fixed."""
from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path
from typing import Any


_REQUIRED_CHAIN_FIELDS = {
    "snapshot_date",
    "symbol",
    "expiry",
    "dte_calendar",
    "option_type",
    "strike",
    "bid",
    "ask",
    "mid",
    "last",
    "volume",
    "open_interest",
    "implied_vol",
    "underlying_spot",
    "source",
}


def load_option_chain_snapshot(
    chain_dir: Path,
    expected_snapshot_date: date,
) -> dict[str, list[dict[str, Any]]]:
    if not chain_dir.is_dir():
        raise FileNotFoundError(f"option-chain snapshot directory is missing: {chain_dir}")
    if chain_dir.name != expected_snapshot_date.isoformat():
        raise ValueError(
            "option-chain directory does not match the governed snapshot date: "
            f"path={chain_dir}, expected={expected_snapshot_date.isoformat()}"
        )
    output: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(chain_dir.glob("*_chain.csv")):
        expected_symbol = path.name[: -len("_chain.csv")].strip().upper()
        rows = _read_validated_option_chain_file(
            path,
            expected_snapshot_date,
            expected_symbol,
        )
        if expected_symbol in output:
            raise ValueError(
                "option-chain snapshot contains duplicate underlying files: "
                f"path={path}, symbol={expected_symbol}"
            )
        output[expected_symbol] = rows
    if not output:
        raise ValueError(f"option-chain snapshot contains no readable contracts: {chain_dir}")
    return output


def validate_option_chain_file(
    path: Path,
    expected_snapshot_date: date,
    expected_symbol: str,
) -> int:
    """Validate a chain file's schema and path-bound row identity."""
    return len(
        _read_validated_option_chain_file(
            path,
            expected_snapshot_date,
            expected_symbol,
        )
    )


def _read_validated_option_chain_file(
    path: Path,
    expected_snapshot_date: date,
    expected_symbol: str,
) -> list[dict[str, Any]]:
    normalized_symbol = expected_symbol.strip().upper()
    expected_name = f"{normalized_symbol}_chain.csv"
    if not normalized_symbol or path.name.casefold() != expected_name.casefold():
        raise ValueError(
            "option-chain path does not encode the expected underlying: "
            f"path={path}, expected_symbol={normalized_symbol!r}"
        )
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            actual_fields = set(reader.fieldnames or ())
            if not _REQUIRED_CHAIN_FIELDS.issubset(actual_fields):
                raise ValueError(
                    "option-chain schema is incomplete: "
                    f"path={path}, required={sorted(_REQUIRED_CHAIN_FIELDS)}, "
                    f"actual={sorted(actual_fields)}"
                )
            source_rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError(
            f"option-chain file is unreadable: path={path}, error={error}"
        ) from error
    if not source_rows:
        raise ValueError(f"option-chain file contains zero contracts: path={path}")
    rows: list[dict[str, Any]] = []
    for line_number, source_row in enumerate(source_rows, start=2):
        rows.append(
            _normalize_chain_row(
                source_row,
                path,
                line_number,
                expected_snapshot_date,
                normalized_symbol,
            )
        )
    return rows


MAX_SHORT_RATE_AGE_DAYS = 7


def load_short_rate(path: Path, as_of_date: date) -> float:
    if not path.exists():
        raise FileNotFoundError(f"Treasury yield curve is missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    candidates = [row for row in rows if str(row.get("label")) in {"1Mo", "2Mo", "3Mo"}]
    if not candidates:
        raise ValueError(f"Treasury yield curve lacks a short rate: {path}")
    latest_date = max(str(row["date"]) for row in candidates)
    try:
        latest_date_value = date.fromisoformat(latest_date)
    except ValueError as error:
        raise ValueError(
            f"Treasury yield curve latest date is invalid: path={path}, date={latest_date!r}"
        ) from error
    age_days = (as_of_date - latest_date_value).days
    if age_days < 0 or age_days > MAX_SHORT_RATE_AGE_DAYS:
        raise ValueError(
            "Treasury short rate is outside its recency boundary: "
            f"path={path}, latest_date={latest_date}, as_of_date={as_of_date.isoformat()}, "
            f"age_days={age_days}, max_age_days={MAX_SHORT_RATE_AGE_DAYS}"
        )
    latest = [row for row in candidates if str(row["date"]) == latest_date]
    return sum(float(row["yield_pct"]) for row in latest) / len(latest) / 100.0


def select_strategic_contracts(
    thesis: dict[str, Any],
    chain_rows: list[dict[str, Any]],
    risk_free_rate: float,
) -> dict[str, Any]:
    symbol = str(thesis["symbol"])
    if thesis["trade_intent"] not in {"long_call", "long_put"}:
        return _blocked_selection(symbol, thesis, "equity_thesis_not_actionable")
    expected_hold = int(thesis["expected_hold_trading_days"])
    as_of = str(thesis["as_of_date"])
    if any(
        str(row.get("snapshot_date", "")).strip() != as_of
        or str(row.get("symbol", "")).strip().upper() != symbol.strip().upper()
        for row in chain_rows
    ):
        return _blocked_selection(
            symbol,
            thesis,
            "option_chain_identity_not_aligned_with_equity_thesis",
        )
    earnings_date = thesis.get("earnings_date")
    if earnings_date and _calendar_days(as_of, str(earnings_date)) <= max(int(expected_hold * 1.6), 7):
        return _blocked_selection(symbol, thesis, "earnings_inside_expected_holding_window")
    option_type = "call" if thesis["trade_intent"] == "long_call" else "put"
    target_delta = 0.58 if option_type == "call" else -0.58
    minimum_dte = max(21, int(math.ceil(expected_hold * 1.8)))
    target_dte = max(35, min(75, expected_hold * 3))
    candidates = [
        row
        for row in chain_rows
        if row["option_type"] == option_type
        and minimum_dte <= int(row["dte_calendar"]) <= 100
        and float(row["ask"]) > 0.0
        and float(row["bid"]) >= 0.0
        and float(row["implied_vol"]) > 0.0
        and int(row["open_interest"]) >= 10
    ]
    if not candidates:
        return _blocked_selection(symbol, thesis, "no_contract_cleared_dte_quote_and_open_interest_floors")
    iv_values = sorted(float(row["implied_vol"]) for row in candidates)
    scored: list[dict[str, Any]] = []
    for row in candidates:
        scored_record = score_contract_candidate(
            thesis,
            row,
            risk_free_rate,
            target_delta,
            target_dte,
            iv_values,
        )
        if scored_record["hard_reject_reason"] == "":
            scored.append(scored_record)
    scored.sort(key=lambda record: (-float(record["contract_score"]), str(record["expiry"]), float(record["strike"])))
    if not scored:
        return _blocked_selection(symbol, thesis, "all_contracts_rejected_for_spread_or_payoff_geometry")
    tracked = scored[:3]
    return {
        "artifact_type": "strategic_option_contract_selection",
        "symbol": symbol,
        "selection_status": "tracked_contracts_selected",
        "equity_thesis_direction": thesis["direction"],
        "direction_inherited_not_recomputed": True,
        "options_direction_weight": 0.0,
        "option_type": option_type,
        "expected_hold_trading_days": expected_hold,
        "minimum_dte": minimum_dte,
        "target_dte": target_dte,
        "target_delta": target_delta,
        "primary_contract": tracked[0],
        "tracked_contracts": tracked,
        "candidate_count_before_hard_filters": len(candidates),
        "candidate_count_scored": len(scored),
        "contract_role": "strategic_tracking_only_no_order_authority",
        "chain_snapshot_identity_verified": True,
        "quote_priced": True,
        "paper_only": True,
        "live_blocked": True,
    }


def score_contract_candidate(
    thesis: dict[str, Any],
    row: dict[str, Any],
    risk_free_rate: float,
    target_delta: float,
    target_dte: int,
    iv_values: list[float],
) -> dict[str, Any]:
    spot = float(row["underlying_spot"])
    strike = float(row["strike"])
    ask = float(row["ask"])
    bid = float(row["bid"])
    mid = float(row["mid"])
    dte = int(row["dte_calendar"])
    iv = float(row["implied_vol"])
    option_type = str(row["option_type"])
    spread_pct = (ask - bid) / mid if mid > 0.0 else 1.0
    delta = black_scholes_delta(spot, strike, dte, risk_free_rate, iv, option_type)
    delta_fit = _clamp01(1.0 - abs(delta - target_delta) / 0.35)
    dte_fit = _clamp01(1.0 - abs(dte - target_dte) / max(float(target_dte), 1.0))
    oi_score = _clamp01(math.log1p(int(row["open_interest"])) / math.log(5001.0))
    volume_score = _clamp01(math.log1p(int(row["volume"])) / math.log(1001.0))
    spread_score = _clamp01(1.0 - spread_pct / 0.20)
    liquidity = 0.50 * spread_score + 0.35 * oi_score + 0.15 * volume_score
    target_price = float(thesis["target_price"])
    target_intrinsic = max(target_price - strike, 0.0) if option_type == "call" else max(strike - target_price, 0.0)
    target_payoff_multiple = target_intrinsic / ask if ask > 0.0 else 0.0
    payoff_fit = _clamp01(target_payoff_multiple / 2.0)
    breakeven = strike + ask if option_type == "call" else strike - ask
    target_clears_breakeven = target_price > breakeven if option_type == "call" else target_price < breakeven
    iv_rank = _percentile_rank(iv, iv_values)
    iv_value_score = 1.0 - iv_rank
    hard_reject = ""
    if spread_pct > 0.25:
        hard_reject = "spread_above_25pct"
    elif not target_clears_breakeven and target_payoff_multiple < 0.65:
        hard_reject = "thesis_target_does_not_support_contract_breakeven"
    score = 0.24 * delta_fit + 0.18 * dte_fit + 0.28 * liquidity + 0.20 * payoff_fit + 0.10 * iv_value_score
    return {
        "contract_symbol_key": f"{row['symbol']}|{row['expiry']}|{option_type}|{strike}",
        "expiry": row["expiry"],
        "dte_calendar": dte,
        "option_type": option_type,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "implied_vol": iv,
        "volume": int(row["volume"]),
        "open_interest": int(row["open_interest"]),
        "delta": round(delta, 6),
        "spread_pct": round(spread_pct, 6),
        "breakeven": round(breakeven, 6),
        "target_intrinsic": round(target_intrinsic, 6),
        "target_payoff_multiple": round(target_payoff_multiple, 6),
        "target_clears_breakeven": target_clears_breakeven,
        "delta_fit_score": round(delta_fit, 6),
        "dte_fit_score": round(dte_fit, 6),
        "liquidity_score": round(liquidity, 6),
        "iv_value_score": round(iv_value_score, 6),
        "contract_score": round(score, 6),
        "hard_reject_reason": hard_reject,
    }


def black_scholes_delta(
    spot: float,
    strike: float,
    dte_calendar: int,
    risk_free_rate: float,
    implied_vol: float,
    option_type: str,
) -> float:
    if spot <= 0.0 or strike <= 0.0 or dte_calendar <= 0 or implied_vol <= 0.0:
        raise ValueError(
            "Black-Scholes delta requires positive spot, strike, DTE, and IV: "
            f"spot={spot}, strike={strike}, dte={dte_calendar}, iv={implied_vol}"
        )
    time_years = dte_calendar / 365.0
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate + 0.5 * implied_vol * implied_vol) * time_years
    ) / (implied_vol * math.sqrt(time_years))
    normal_cdf = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
    if option_type == "call":
        return normal_cdf
    if option_type == "put":
        return normal_cdf - 1.0
    raise ValueError(f"unsupported option type for delta: {option_type}")


def _normalize_chain_row(
    row: dict[str, Any],
    path: Path,
    line_number: int,
    expected_snapshot_date: date,
    expected_symbol: str,
) -> dict[str, Any]:
    raw_snapshot_date = str(row.get("snapshot_date", "")).strip()
    raw_expiry = str(row.get("expiry", "")).strip()
    symbol = str(row.get("symbol", "")).strip().upper()
    try:
        snapshot_date = date.fromisoformat(raw_snapshot_date)
        expiry = date.fromisoformat(raw_expiry)
        normalized: dict[str, Any] = {
            "snapshot_date": snapshot_date.isoformat(),
            "symbol": symbol,
            "expiry": expiry.isoformat(),
            "dte_calendar": int(row["dte_calendar"]),
            "option_type": str(row["option_type"]).strip().lower(),
            "strike": float(row["strike"]),
            "bid": float(row["bid"]),
            "ask": float(row["ask"]),
            "mid": float(row["mid"]),
            "last": float(row["last"]),
            "volume": int(row["volume"]),
            "open_interest": int(row["open_interest"]),
            "implied_vol": float(row["implied_vol"]),
            "underlying_spot": float(row["underlying_spot"]),
            "source": str(row["source"]).strip(),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "option-chain row cannot be parsed: "
            f"path={path}, line={line_number}, error={error}"
        ) from error
    if snapshot_date != expected_snapshot_date:
        raise ValueError(
            "option-chain row snapshot date does not match its path and manifest: "
            f"path={path}, line={line_number}, observed={snapshot_date.isoformat()}, "
            f"expected={expected_snapshot_date.isoformat()}"
        )
    if symbol != expected_symbol:
        raise ValueError(
            "option-chain row symbol does not match its path and manifest: "
            f"path={path}, line={line_number}, observed={symbol!r}, "
            f"expected={expected_symbol!r}"
        )
    for identity_field in ("underlying", "underlying_symbol"):
        if identity_field not in row:
            continue
        underlying = str(row.get(identity_field, "")).strip().upper()
        if underlying and underlying != expected_symbol:
            raise ValueError(
                "option-chain row underlying identity does not match its path and manifest: "
                f"path={path}, line={line_number}, field={identity_field}, "
                f"observed={underlying!r}, expected={expected_symbol!r}"
            )
    if normalized["option_type"] not in {"call", "put"}:
        raise ValueError(
            "option-chain row has an unsupported option type: "
            f"path={path}, line={line_number}, value={normalized['option_type']!r}"
        )
    if expiry <= snapshot_date or normalized["dte_calendar"] != (
        expiry - snapshot_date
    ).days:
        raise ValueError(
            "option-chain row expiry and DTE are inconsistent: "
            f"path={path}, line={line_number}, snapshot_date={snapshot_date.isoformat()}, "
            f"expiry={expiry.isoformat()}, dte_calendar={normalized['dte_calendar']}"
        )
    numeric_fields = (
        "strike",
        "bid",
        "ask",
        "mid",
        "last",
        "implied_vol",
        "underlying_spot",
    )
    if any(not math.isfinite(float(normalized[field])) for field in numeric_fields):
        raise ValueError(
            "option-chain row contains a nonfinite numeric value: "
            f"path={path}, line={line_number}"
        )
    if (
        normalized["strike"] <= 0.0
        or normalized["underlying_spot"] <= 0.0
        or normalized["implied_vol"] <= 0.0
        or normalized["bid"] < 0.0
        or normalized["ask"] < normalized["bid"]
        or normalized["mid"] < normalized["bid"]
        or normalized["mid"] > normalized["ask"]
        or normalized["last"] < 0.0
        or normalized["volume"] < 0
        or normalized["open_interest"] < 0
        or not normalized["source"]
    ):
        raise ValueError(
            "option-chain row violates quote, contract, or provenance constraints: "
            f"path={path}, line={line_number}"
        )
    return normalized


def _blocked_selection(symbol: str, thesis: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "strategic_option_contract_selection",
        "symbol": symbol,
        "selection_status": "blocked",
        "block_reason": reason,
        "equity_thesis_direction": thesis.get("direction", "neutral"),
        "direction_inherited_not_recomputed": True,
        "options_direction_weight": 0.0,
        "primary_contract": None,
        "tracked_contracts": [],
        "contract_role": "strategic_tracking_only_no_order_authority",
        "chain_snapshot_identity_verified": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _calendar_days(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def _percentile_rank(value: float, values: list[float]) -> float:
    if not values:
        return 0.5
    below = sum(candidate < value for candidate in values)
    equal = sum(candidate == value for candidate in values)
    return (below + 0.5 * equal) / len(values)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
