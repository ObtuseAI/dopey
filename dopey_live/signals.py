"""Translate immutable equity-first theses into deterministic Live Branch intents."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from dopey_equity_swing.leveraged_etf import (
    LEVERAGED_ETF_CATALOG,
    MAX_LEVERAGED_ETF_GROSS_ALLOCATION_FRACTION,
    preferred_leveraged_etf_plans,
)

from .models import (
    EQUITY_SNAPSHOT_SOURCE,
    EquityExecutionSnapshot,
    EquityQuoteSnapshot,
    LiveExecutionIntent,
)


SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_STOCK_ENTRY_GROSS_ALLOCATION_FRACTION: Final[float] = 0.50
MAX_STOCK_SINGLE_NAME_ALLOCATION_FRACTION: Final[float] = 0.10
MAX_STOCK_RISK_PER_POSITION_FRACTION: Final[float] = 0.005
LEVERAGED_ETF_TRADE_SYMBOLS: Final[frozenset[str]] = frozenset(
    str(spec["trade_symbol"]) for spec in LEVERAGED_ETF_CATALOG
)
MAX_EQUITY_QUOTE_AGE_SECONDS: Final[float] = 60.0
MAX_EQUITY_QUOTE_FUTURE_SKEW_SECONDS: Final[float] = 5.0
MAX_EQUITY_QUOTE_SPREAD_BPS: Final[float] = 50.0
MAX_EQUITY_REFERENCE_DRIFT_FRACTION: Final[float] = 0.02
REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ACTION_READINESS_ARTIFACT_TYPE: Final[str] = "action_readiness_gate"
RELEASE_GATE_VERSION: Final[str] = "dopey-live-pivot-release-gate-v1"
CALIBRATION_VERSION: Final[str] = "dopey-vnext-calibration-v2"
CHAMPION_HARDENING_VERSION: Final[str] = (
    "dopey-public-champion-hardening-gate-v1"
)
MAX_GATE_RECOMPUTE_AGE: Final[timedelta] = timedelta(minutes=5)
MAX_RESEARCH_INPUT_AGE: Final[timedelta] = timedelta(hours=36)
MAX_ARTIFACT_FUTURE_SKEW: Final[timedelta] = timedelta(seconds=5)
NEW_YORK: Final[ZoneInfo] = ZoneInfo("America/New_York")


class LiveSignalError(RuntimeError):
    """Raised when a source thesis cannot safely become an execution intent."""


def _allowed_source_dates(market_date: date) -> frozenset[str]:
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(
        date.fromordinal(market_date.toordinal() - 10),
        market_date,
    )
    session_dates = [str(session.date()) for session in sessions]
    return frozenset(session_dates[-2:])


def _jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        raise LiveSignalError(
            f"Live Branch source thesis ledger is missing: path={path}"
        )
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise LiveSignalError(
                f"Invalid thesis JSON: path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(parsed, dict):
            raise LiveSignalError(
                f"Thesis row must be an object: path={path}, line={line_number}"
            )
        records.append(parsed)
    return tuple(records)


def _record_hash(record: dict[str, Any]) -> str:
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise LiveSignalError(
            f"Required research-maturity artifact is missing: path={path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LiveSignalError(
            f"Invalid research-maturity JSON: path={path}, error={error}"
        ) from error
    if not isinstance(payload, dict):
        raise LiveSignalError(
            f"Research-maturity artifact must be an object: path={path}"
        )
    return payload


def _reproducibility_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("reproducibility_hash", None)
    encoded = json.dumps([unsigned], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_summary_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("summary_hash", None)
    encoded = json.dumps(
        unsigned,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_summary_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("reproducibility_hash", None)
    encoded = json.dumps(
        unsigned,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calibration_source_hashes(calibration_path: Path) -> dict[str, str]:
    output_root = calibration_path.parent
    relative_paths = (
        "forward_predictions.jsonl",
        "memory/settlements.jsonl",
    )
    return {
        relative_path: _file_sha256(output_root / relative_path)
        if (output_root / relative_path).exists()
        else ""
        for relative_path in relative_paths
    }


CHAMPION_SOURCE_PATHS: tuple[str, ...] = (
    "champions/public_paper_champion_gate_v2_results.jsonl",
    "champion_hardening/public_champion_deep_stress_results_v1.jsonl",
    "champion_hardening/public_champion_holdout_expansion_results_v1.jsonl",
    "champion_hardening/public_champion_decay_alerts_v1.jsonl",
)


def _champion_source_hashes(champion_path: Path) -> dict[str, str]:
    root = champion_path.parent.parent
    return {
        relative_path: _file_sha256(root / relative_path)
        if (root / relative_path).exists()
        else ""
        for relative_path in CHAMPION_SOURCE_PATHS
    }


def _aware_artifact_timestamp(value: Any) -> datetime | None:
    try:
        observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    return observed.astimezone(timezone.utc)


def _fresh_timestamp(value: Any, now_utc: datetime, maximum_age: timedelta) -> bool:
    observed = _aware_artifact_timestamp(value)
    if observed is None:
        return False
    return (
        observed <= now_utc + MAX_ARTIFACT_FUTURE_SKEW
        and now_utc - observed <= maximum_age
    )


def _fresh_file(path: Path, now_utc: datetime, maximum_age: timedelta) -> bool:
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return False
    return (
        modified_at <= now_utc + MAX_ARTIFACT_FUTURE_SKEW
        and now_utc - modified_at <= maximum_age
    )


def _production_recomputed_artifacts(
    repository_root: Path,
    action_path: Path,
    release_path: Path,
    champion_path: Path,
    nightly_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if repository_root.resolve() != REPOSITORY_ROOT.resolve():
        return None
    from dopey_broker_readiness.action_readiness_gate import (
        run_action_readiness_gate,
    )

    input_hashes_before = {
        path: _file_sha256(path) if path.exists() else ""
        for path in (champion_path, nightly_path)
    }
    computed_action = run_action_readiness_gate()
    input_hashes_after = {
        path: _file_sha256(path) if path.exists() else ""
        for path in (champion_path, nightly_path)
    }
    if input_hashes_before != input_hashes_after:
        raise LiveSignalError(
            "Research maturity inputs changed while the entry gate was recomputed"
        )
    action = _json_object(action_path)
    release = _json_object(release_path)
    if action != computed_action:
        raise LiveSignalError(
            "Recomputed action-readiness result does not match its persisted artifact"
        )
    return action, release


def _artifact_integrity_blockers(
    action: dict[str, Any],
    release: dict[str, Any],
    calibration: dict[str, Any],
    champion: dict[str, Any],
    nightly: dict[str, Any],
    paths: tuple[Path, Path, Path, Path, Path],
    now_utc: datetime,
) -> tuple[str, ...]:
    action_path, release_path, calibration_path, champion_path, nightly_path = paths
    embedded_release = action.get("live_pivot_release_gate")
    stack_stability = nightly.get("stack_stability")
    fitness_determinism = nightly.get("fitness_determinism")
    nightly_green = bool(
        nightly.get("artifact_type") == "nightly_effectiveness_report"
        and nightly.get("verdict") == "all_green"
        and nightly.get("suite_green") is True
        and isinstance(stack_stability, dict)
        and stack_stability.get("green") is True
        and isinstance(fitness_determinism, dict)
        and fitness_determinism.get("deterministic") is True
    )
    hardened_champion_available = bool(
        champion.get("artifact_type")
        == "public_champion_hardening_gate_v1_summary"
        and champion.get("public_champion_hardening_gate_version")
        == CHAMPION_HARDENING_VERSION
        and type(champion.get("hardened_champion_count")) is int
        and int(champion["hardened_champion_count"]) > 0
    )
    release_checks = release.get("checks")
    release_checks_object = release_checks if isinstance(release_checks, dict) else {}
    checks = (
        (
            action.get("artifact_type") == ACTION_READINESS_ARTIFACT_TYPE,
            "action_readiness_schema_invalid",
        ),
        (
            action.get("gate_semantics")
            == "necessary_not_sufficient_human_operator_review_always_required",
            "action_readiness_semantics_invalid",
        ),
        (
            SHA256_PATTERN.fullmatch(str(action.get("reproducibility_hash", "")))
            is not None
            and action.get("reproducibility_hash") == _reproducibility_hash(action),
            "action_readiness_hash_invalid",
        ),
        (
            release.get("artifact_type") == "live_pivot_release_gate"
            and release.get("release_gate_version") == RELEASE_GATE_VERSION,
            "live_pivot_release_schema_invalid",
        ),
        (
            SHA256_PATTERN.fullmatch(str(release.get("reproducibility_hash", "")))
            is not None
            and release.get("reproducibility_hash") == _reproducibility_hash(release),
            "live_pivot_release_hash_invalid",
        ),
        (
            isinstance(embedded_release, dict) and embedded_release == release,
            "action_release_binding_invalid",
        ),
        (
            calibration.get("artifact_type")
            == "vnext_probability_calibration_summary"
            and calibration.get("calibration_version") == CALIBRATION_VERSION,
            "forward_calibration_schema_invalid",
        ),
        (
            SHA256_PATTERN.fullmatch(
                str(calibration.get("reproducibility_hash", ""))
            )
            is not None
            and calibration.get("reproducibility_hash")
            == _canonical_summary_hash(calibration),
            "forward_calibration_hash_invalid",
        ),
        (
            calibration.get("source_evidence_hashes")
            == _calibration_source_hashes(calibration_path),
            "forward_calibration_source_binding_invalid",
        ),
        (
            _fresh_timestamp(
                calibration.get("observed_at"),
                now_utc,
                MAX_RESEARCH_INPUT_AGE,
            ),
            "forward_calibration_stale",
        ),
        (
            champion.get("artifact_type")
            == "public_champion_hardening_gate_v1_summary"
            and champion.get("public_champion_hardening_gate_version")
            == CHAMPION_HARDENING_VERSION,
            "champion_hardening_schema_invalid",
        ),
        (
            SHA256_PATTERN.fullmatch(str(champion.get("summary_hash", "")))
            is not None
            and champion.get("summary_hash") == _stable_summary_hash(champion),
            "champion_hardening_hash_invalid",
        ),
        (
            _fresh_timestamp(
                champion.get("generated_utc"),
                now_utc,
                MAX_RESEARCH_INPUT_AGE,
            ),
            "champion_hardening_stale",
        ),
        (
            champion.get("source_artifact_hashes")
            == _champion_source_hashes(champion_path),
            "champion_hardening_source_binding_invalid",
        ),
        (
            nightly.get("artifact_type") == "nightly_effectiveness_report",
            "nightly_schema_invalid",
        ),
        (
            SHA256_PATTERN.fullmatch(str(nightly.get("summary_hash", "")))
            is not None
            and nightly.get("summary_hash") == _stable_summary_hash(nightly),
            "nightly_hash_invalid",
        ),
        (
            _fresh_timestamp(
                nightly.get("finished_at_utc"),
                now_utc,
                MAX_RESEARCH_INPUT_AGE,
            ),
            "nightly_stale",
        ),
        (
            release_checks_object.get("hardened_champion_available")
            is hardened_champion_available,
            "release_champion_binding_invalid",
        ),
        (
            release_checks_object.get("full_nightly_validation_green")
            is nightly_green,
            "release_nightly_binding_invalid",
        ),
        (
            _fresh_file(action_path, now_utc, MAX_GATE_RECOMPUTE_AGE)
            and _fresh_file(release_path, now_utc, MAX_GATE_RECOMPUTE_AGE),
            "readiness_gate_not_freshly_recomputed",
        ),
        (
            _fresh_file(calibration_path, now_utc, MAX_RESEARCH_INPUT_AGE)
            and _fresh_file(nightly_path, now_utc, MAX_RESEARCH_INPUT_AGE),
            "research_input_files_stale",
        ),
    )
    return tuple(reason for passed, reason in checks if not passed)


def research_maturity_blockers(repository_root: Path) -> tuple[str, ...]:
    artifact_root = repository_root.resolve() / "artifacts" / "dopey"
    action_path = artifact_root / "broker_readiness" / "action_readiness_gate.json"
    release_path = (
        artifact_root / "broker_readiness" / "live_pivot_release_gate.json"
    )
    calibration_path = (
        artifact_root
        / "vnext"
        / "cross_sectional_operational"
        / "calibration_summary.json"
    )
    champion_path = (
        artifact_root
        / "champion_hardening"
        / "public_champion_hardening_gate_v1_summary.json"
    )
    nightly_path = artifact_root / "nightly" / "nightly_latest.json"
    recomputed = _production_recomputed_artifacts(
        repository_root,
        action_path,
        release_path,
        champion_path,
        nightly_path,
    )
    if recomputed is None:
        action = _json_object(action_path)
        release = _json_object(release_path)
    else:
        action, release = recomputed
    calibration = _json_object(calibration_path)
    champion = _json_object(champion_path)
    nightly = _json_object(nightly_path)
    integrity_blockers = _artifact_integrity_blockers(
        action,
        release,
        calibration,
        champion,
        nightly,
        (
            action_path,
            release_path,
            calibration_path,
            champion_path,
            nightly_path,
        ),
        datetime.now(timezone.utc),
    )
    checks = (
        (action.get("action_ready") is True, "action_readiness_gate_not_ready"),
        (
            action.get("readiness_status") == "action_ready_pending_human_review",
            "action_readiness_status_not_ready",
        ),
        (
            action.get("strategy_promotion_allowed") is True,
            "strategy_promotion_not_allowed",
        ),
        (
            release.get("release_status") == "release_ready",
            "live_pivot_release_not_ready",
        ),
        (release.get("live_blocked") is False, "live_pivot_release_still_blocked"),
        (
            calibration.get("calibration_sample_sufficient") is True,
            "forward_calibration_sample_insufficient",
        ),
        (
            calibration.get("promotion_allowed") is True,
            "forward_calibration_promotion_not_allowed",
        ),
    )
    maturity_blockers = tuple(reason for passed, reason in checks if not passed)
    return (*integrity_blockers, *maturity_blockers)


def _thesis_promoted_for_execution(record: dict[str, Any]) -> bool:
    return bool(
        record.get("strategy_promotion_allowed") is True
        and record.get("not_edge_evidence") is False
    )


def _thesis_has_complete_earnings_evidence(record: dict[str, Any]) -> bool:
    evidence = record.get("earnings_evidence")
    if not isinstance(evidence, dict):
        return False
    as_of_date = str(record.get("as_of_date", ""))
    snapshot_date = str(evidence.get("snapshot_date", ""))
    next_earnings_date = str(evidence.get("next_earnings_date", ""))
    snapshot_symbol_count = evidence.get("snapshot_symbol_count")
    source_labels = evidence.get("source_labels")
    if (
        evidence.get("status") != "frontier_aligned_symbol_event_observed"
        or evidence.get("live_candidate_event_gate_passed") is not True
        or evidence.get("symbol_covered") is not True
        or snapshot_date != as_of_date
        or not SHA256_PATTERN.fullmatch(str(evidence.get("snapshot_sha256", "")))
        or type(snapshot_symbol_count) is not int
        or snapshot_symbol_count <= 0
        or not isinstance(source_labels, list)
        or not source_labels
        or not all(isinstance(label, str) and label.strip() for label in source_labels)
    ):
        return False
    try:
        snapshot_day = date.fromisoformat(snapshot_date)
        next_earnings_day = date.fromisoformat(next_earnings_date)
    except ValueError:
        return False
    return next_earnings_day >= snapshot_day


def _earnings_evidence_keys(
    repository_root: Path,
    allowed_source_dates: frozenset[str],
) -> frozenset[tuple[str, str]]:
    source_path = (
        repository_root.resolve()
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "equity_swing_theses.jsonl"
    )
    return frozenset(
        (str(record.get("symbol", "")), str(record.get("as_of_date", "")))
        for record in _jsonl(source_path)
        if str(record.get("as_of_date", "")) in allowed_source_dates
        and _thesis_has_complete_earnings_evidence(record)
    )


def _score(record: dict[str, Any]) -> float:
    bullish = float(record.get("equity_bullish_score", 0.0))
    bearish = float(record.get("equity_bearish_score", 0.0))
    quality = max(float(record.get("setup_quality_score", 0.0)), 0.0)
    reward_risk = min(max(float(record.get("reward_risk_ratio", 0.0)), 0.0), 3.0) / 3.0
    conviction = max(bullish - bearish, 0.0)
    return quality * reward_risk * conviction


def _stock_loss_fraction(record: dict[str, Any]) -> float | None:
    try:
        reference_price = float(record.get("entry_reference_price", 0.0))
        invalidation_price = float(record.get("invalidation_price", 0.0))
        target_price = float(record.get("target_price", 0.0))
    except (TypeError, ValueError):
        return None
    if not all(
        math.isfinite(value)
        for value in (reference_price, invalidation_price, target_price)
    ):
        return None
    if not 0.0 < invalidation_price < reference_price < target_price:
        return None
    return (reference_price - invalidation_price) / reference_price


def _risk_capped_stock_notional(
    capital_base_usd: float,
    weighted_notional_usd: float,
    loss_fraction: float,
) -> float:
    if (
        not math.isfinite(capital_base_usd)
        or not math.isfinite(weighted_notional_usd)
        or not math.isfinite(loss_fraction)
        or capital_base_usd <= 0.0
        or weighted_notional_usd <= 0.0
        or loss_fraction <= 0.0
    ):
        return 0.0
    single_name_cap = capital_base_usd * MAX_STOCK_SINGLE_NAME_ALLOCATION_FRACTION
    stop_risk_cap = (
        capital_base_usd * MAX_STOCK_RISK_PER_POSITION_FRACTION / loss_fraction
    )
    capped_notional = min(weighted_notional_usd, single_name_cap, stop_risk_cap)
    return float(
        Decimal(str(capped_notional)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    )


def _parsed_observed_at(value: str, context: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        observed_at = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise LiveSignalError(
            f"Equity quote observed_at must be ISO-8601: context={context}, value={value!r}"
        ) from error
    if observed_at.tzinfo is None:
        raise LiveSignalError(
            f"Equity quote observed_at must be timezone-aware: context={context}, value={value!r}"
        )
    return observed_at.astimezone(timezone.utc)


def _validated_quote_spread_bps(
    quote: EquityQuoteSnapshot,
    expected_symbol: str,
    now_utc: datetime,
    context: str,
) -> float:
    if quote.symbol != expected_symbol:
        raise LiveSignalError(
            "Equity quote symbol mismatch: "
            f"context={context}, expected={expected_symbol}, actual={quote.symbol!r}"
        )
    if not quote.tradable:
        raise LiveSignalError(
            f"Equity instrument is not tradable: context={context}, symbol={quote.symbol}"
        )
    prices = (quote.bid_price, quote.ask_price, quote.last_price)
    if not all(math.isfinite(value) and value > 0.0 for value in prices):
        raise LiveSignalError(
            f"Equity quote prices must be positive and finite: context={context}, prices={prices}"
        )
    if quote.bid_price > quote.ask_price:
        raise LiveSignalError(
            "Equity quote is crossed: "
            f"context={context}, bid={quote.bid_price}, ask={quote.ask_price}"
        )
    observed_at = _parsed_observed_at(quote.observed_at, context)
    age_seconds = (now_utc.astimezone(timezone.utc) - observed_at).total_seconds()
    if age_seconds > MAX_EQUITY_QUOTE_AGE_SECONDS:
        raise LiveSignalError(
            "Equity quote is stale: "
            f"context={context}, age_seconds={age_seconds:.3f}, maximum={MAX_EQUITY_QUOTE_AGE_SECONDS}"
        )
    if age_seconds < -MAX_EQUITY_QUOTE_FUTURE_SKEW_SECONDS:
        raise LiveSignalError(
            "Equity quote is future-dated: "
            f"context={context}, age_seconds={age_seconds:.3f}"
        )
    midpoint = (quote.bid_price + quote.ask_price) / 2.0
    spread_bps = (quote.ask_price - quote.bid_price) / midpoint * 10_000.0
    if spread_bps > MAX_EQUITY_QUOTE_SPREAD_BPS:
        raise LiveSignalError(
            "Equity quote spread exceeds policy: "
            f"context={context}, spread_bps={spread_bps:.3f}, maximum={MAX_EQUITY_QUOTE_SPREAD_BPS}"
        )
    return spread_bps


def prepare_equity_entry_for_execution(
    intent: LiveExecutionIntent,
    snapshot: EquityExecutionSnapshot,
    now_utc: datetime,
    capital_base_usd: float,
) -> LiveExecutionIntent:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    if intent.instrument != "equity" or intent.side != "buy":
        raise LiveSignalError("Equity entry preparation requires a long-equity entry")
    if snapshot.source != EQUITY_SNAPSHOT_SOURCE:
        raise LiveSignalError(
            "Equity execution snapshot source is not authoritative: "
            f"source={snapshot.source!r}"
        )
    _validated_quote_spread_bps(
        snapshot.execution_quote,
        intent.symbol,
        now_utc,
        "execution_quote",
    )
    _validated_quote_spread_bps(
        snapshot.analysis_quote,
        intent.analysis_symbol,
        now_utc,
        "analysis_quote",
    )
    reference_price = intent.analysis_reference_price
    invalidation_price = intent.analysis_invalidation_price
    target_price = intent.analysis_target_price
    authority_price = snapshot.analysis_quote.last_price
    if not all(
        math.isfinite(value) and value > 0.0
        for value in (
            reference_price,
            invalidation_price,
            target_price,
            authority_price,
        )
    ):
        raise LiveSignalError("Equity entry requires positive analysis price geometry")
    reference_drift = abs(authority_price / reference_price - 1.0)
    if reference_drift > MAX_EQUITY_REFERENCE_DRIFT_FRACTION:
        raise LiveSignalError(
            "Equity analysis quote drift exceeds policy: "
            f"drift={reference_drift:.6f}, maximum={MAX_EQUITY_REFERENCE_DRIFT_FRACTION}"
        )
    if intent.thesis_direction == "bullish":
        if not invalidation_price < authority_price < target_price:
            raise LiveSignalError(
                "Bullish equity analysis price crossed thesis geometry"
            )
        if intent.daily_reset and authority_price < reference_price:
            raise LiveSignalError(
                "Bullish leveraged-equity analysis confirmation is absent"
            )
    elif intent.thesis_direction == "bearish":
        if not target_price < authority_price < invalidation_price:
            raise LiveSignalError(
                "Bearish equity analysis price crossed thesis geometry"
            )
        if intent.daily_reset and authority_price > reference_price:
            raise LiveSignalError(
                "Bearish leveraged-equity analysis confirmation is absent"
            )
    else:
        raise LiveSignalError(
            f"Equity entry thesis direction is unsupported: {intent.thesis_direction!r}"
        )
    limit_price = float(
        Decimal(str(snapshot.execution_quote.ask_price)).quantize(
            Decimal("0.01"),
            rounding=ROUND_UP,
        )
    )
    if intent.analysis_relationship == "self":
        if not invalidation_price < limit_price < target_price:
            raise LiveSignalError("Equity limit price crossed thesis geometry")
        loss_fraction = (limit_price - invalidation_price) / limit_price
        notional_usd = _risk_capped_stock_notional(
            capital_base_usd,
            intent.notional_usd,
            loss_fraction,
        )
    else:
        capped_notional = min(
            intent.notional_usd,
            capital_base_usd * MAX_STOCK_SINGLE_NAME_ALLOCATION_FRACTION,
        )
        notional_usd = float(
            Decimal(str(capped_notional)).quantize(
                Decimal("0.01"),
                rounding=ROUND_DOWN,
            )
        )
    if notional_usd <= 0.0:
        raise LiveSignalError("Equity limit order has no positive risk-capped notional")
    return replace(
        intent,
        order_type="limit",
        limit_price=limit_price,
        notional_usd=notional_usd,
        execution_snapshot=snapshot,
        reason_codes=(
            *intent.reason_codes,
            "current_quote_and_tradability_validated",
            "price_collared_limit_order",
            "stop_risk_and_exposure_caps_applied",
        ),
    )


def build_stock_entry_intents(
    repository_root: Path,
    buying_power_usd: float,
    market_date: date,
    excluded_symbols: frozenset[str],
) -> tuple[LiveExecutionIntent, ...]:
    if not math.isfinite(buying_power_usd) or buying_power_usd <= 0.0:
        return ()
    allowed_source_dates = _allowed_source_dates(market_date)
    source_path = (
        repository_root.resolve()
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "equity_swing_theses.jsonl"
    )
    candidates = [
        record
        for record in _jsonl(source_path)
        if record.get("thesis_status") == "actionable_shadow_thesis"
        and _thesis_promoted_for_execution(record)
        and record.get("direction") == "bullish"
        and record.get("trade_intent") != "no_trade"
        and _thesis_has_complete_earnings_evidence(record)
        and str(record.get("as_of_date", "")) in allowed_source_dates
        and str(record.get("symbol", "")) not in excluded_symbols
        and str(record.get("symbol", "")) not in LEVERAGED_ETF_TRADE_SYMBOLS
    ]
    candidates = [
        record
        for record in candidates
        if SYMBOL_PATTERN.fullmatch(str(record.get("symbol", "")))
        and _stock_loss_fraction(record) is not None
    ]
    if not candidates:
        return ()
    weights = [_score(record) for record in candidates]
    total_weight = sum(weights)
    if total_weight <= 0.0:
        return ()
    gross_budget = buying_power_usd * MAX_STOCK_ENTRY_GROSS_ALLOCATION_FRACTION
    intents: list[LiveExecutionIntent] = []
    for record, raw_weight in sorted(
        zip(candidates, weights, strict=True),
        key=lambda pair: (-pair[1], str(pair[0].get("symbol", ""))),
    ):
        symbol = str(record["symbol"])
        source_hash = _record_hash(record)
        loss_fraction = _stock_loss_fraction(record)
        if loss_fraction is None:
            continue
        notional = _risk_capped_stock_notional(
            buying_power_usd,
            gross_budget * raw_weight / total_weight,
            loss_fraction,
        )
        reference_price = float(record.get("entry_reference_price", 0.0))
        if notional <= 0.0 or reference_price <= 0.0:
            continue
        intent_id = hashlib.sha256(
            f"equity|buy|{symbol}|{record.get('as_of_date')}|{source_hash}".encode(
                "utf-8"
            )
        ).hexdigest()
        intents.append(
            LiveExecutionIntent(
                intent_id=intent_id,
                instrument="equity",
                symbol=symbol,
                side="buy",
                order_type="market",
                limit_price=0.0,
                time_in_force="day",
                extended_hours=False,
                notional_usd=notional,
                quantity=0.0,
                source_as_of_date=str(record.get("as_of_date", "")),
                source_hash=source_hash,
                thesis_direction="bullish",
                analysis_symbol=symbol,
                analysis_relationship="self",
                analysis_reference_price=reference_price,
                analysis_invalidation_price=float(
                    record.get("invalidation_price") or 0.0
                ),
                analysis_target_price=float(record.get("target_price") or 0.0),
                daily_leverage_multiple=1.0,
                daily_reset=False,
                maximum_holding_sessions=int(
                    record.get("expected_hold_trading_days", 0)
                ),
                reference_price=reference_price,
                invalidation_price=float(record.get("invalidation_price") or 0.0),
                target_price=float(record.get("target_price") or 0.0),
                expected_hold_trading_days=int(
                    record.get("expected_hold_trading_days", 0)
                ),
                execution_snapshot=None,
                option_contract={},
                reason_codes=tuple(
                    str(value) for value in record.get("reason_codes", [])
                ),
            )
        )
    return tuple(intents)


def _leveraged_etf_plans(repository_root: Path) -> tuple[dict[str, Any], ...]:
    path = (
        repository_root.resolve()
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "leveraged_etf_swing_plans.jsonl"
    )
    if not path.exists():
        return ()
    return _jsonl(path)


def _leveraged_plan_score(plan: dict[str, Any]) -> float:
    bullish = float(plan.get("underlying_bullish_score", 0.0))
    bearish = float(plan.get("underlying_bearish_score", 0.0))
    direction = str(plan.get("exposure_direction", ""))
    conviction = bullish - bearish if direction == "bullish" else bearish - bullish
    quality = max(float(plan.get("setup_quality_score", 0.0)), 0.0)
    reward_risk = min(max(float(plan.get("reward_risk_ratio", 0.0)), 0.0), 3.0) / 3.0
    return max(conviction, 0.0) * quality * reward_risk


def _validated_leveraged_candidate(
    plan: dict[str, Any], allowed_source_dates: frozenset[str]
) -> bool:
    entry_plan = plan.get("entry_plan")
    exit_plan = plan.get("exit_plan")
    chart_evidence = plan.get("underlying_chart_evidence")
    trade_symbol = str(plan.get("trade_symbol", ""))
    analysis_symbol = str(plan.get("analysis_symbol", ""))
    relationship = str(plan.get("analysis_relationship", ""))
    category = str(plan.get("product_category", ""))
    direction = str(plan.get("exposure_direction", ""))
    leverage = float(plan.get("daily_leverage_multiple", 0.0))
    hold = int(plan.get("expected_hold_trading_days", 0))
    if (
        not isinstance(entry_plan, dict)
        or not isinstance(exit_plan, dict)
        or not isinstance(chart_evidence, dict)
    ):
        return False
    return bool(
        plan.get("schema_version") == "dopey-leveraged-etf-swing-plan-v2"
        and plan.get("plan_status") == "actionable_shadow_leveraged_etf_plan"
        and plan.get("actionable") is True
        and plan.get("strategy_promotion_allowed") is True
        and plan.get("not_edge_evidence") is False
        and plan.get("daily_reset") is True
        and plan.get("paper_twin_required") is True
        and plan.get("live_branch_candidate_route")
        == "independent_freshness_tradeability_and_paper_twin_gates"
        and plan.get("direct_short_sale_allowed") is False
        and str(plan.get("source_as_of_date", "")) in allowed_source_dates
        and SYMBOL_PATTERN.fullmatch(trade_symbol)
        and SYMBOL_PATTERN.fullmatch(analysis_symbol)
        and relationship in {"exact_underlying", "benchmark_proxy"}
        and category
        in {
            "single_stock",
            "broad_market",
            "sector",
            "fixed_income",
            "international",
            "commodity",
            "crypto_linked",
        }
        and len(str(plan.get("pair_id", ""))) > 0
        and int(plan.get("execution_priority", 0)) > 0
        and trade_symbol != analysis_symbol
        and (
            (direction == "bullish" and leverage >= 1.0)
            or (direction == "bearish" and leverage <= -1.0)
        )
        and 0.0 < float(plan.get("max_notional_fraction", 0.0)) <= 0.10
        and 2 <= hold <= int(exit_plan.get("maximum_holding_sessions", 0)) <= 5
        and str(entry_plan.get("chart_authority", "")) == analysis_symbol
        and str(exit_plan.get("chart_authority", "")) == analysis_symbol
        and float(entry_plan.get("analysis_reference_price", 0.0)) > 0.0
        and float(exit_plan.get("analysis_invalidation_price", 0.0)) > 0.0
        and float(exit_plan.get("analysis_target_price", 0.0)) > 0.0
        and len(str(chart_evidence.get("ohlcv_sha256", ""))) == 64
        and str(chart_evidence.get("analysis_symbol", "")) == analysis_symbol
        and str(chart_evidence.get("as_of_date", ""))
        == str(plan.get("source_as_of_date", ""))
        and len(str(plan.get("source_thesis_hash", ""))) == 64
    )


def build_leveraged_etf_entry_intents(
    repository_root: Path,
    buying_power_usd: float,
    market_date: date,
    held_equity_symbols: frozenset[str],
) -> tuple[LiveExecutionIntent, ...]:
    """Allocate a capped long-share expression for bullish and bearish ETF plans."""
    if not math.isfinite(buying_power_usd) or buying_power_usd <= 0.0:
        return ()
    allowed_source_dates = _allowed_source_dates(market_date)
    earnings_evidence_keys = _earnings_evidence_keys(
        repository_root,
        allowed_source_dates,
    )
    held_analysis_symbols = frozenset(
        spec["analysis_symbol"]
        for spec in LEVERAGED_ETF_CATALOG
        if spec["trade_symbol"] in held_equity_symbols
    )
    candidates = preferred_leveraged_etf_plans(
        [
            plan
            for plan in _leveraged_etf_plans(repository_root)
            if _validated_leveraged_candidate(plan, allowed_source_dates)
            and (
                str(plan.get("analysis_symbol", "")),
                str(plan.get("source_as_of_date", "")),
            )
            in earnings_evidence_keys
            and str(plan.get("trade_symbol", "")) not in held_equity_symbols
            and str(plan.get("analysis_symbol", "")) not in held_equity_symbols
            and str(plan.get("analysis_symbol", "")) not in held_analysis_symbols
        ]
    )
    weighted = [(plan, _leveraged_plan_score(plan)) for plan in candidates]
    weighted = [(plan, score) for plan, score in weighted if score > 0.0]
    total_weight = sum(score for _, score in weighted)
    if total_weight <= 0.0:
        return ()
    gross_budget = buying_power_usd * MAX_LEVERAGED_ETF_GROSS_ALLOCATION_FRACTION
    intents: list[LiveExecutionIntent] = []
    for plan, weight in sorted(
        weighted,
        key=lambda item: (-item[1], str(item[0].get("trade_symbol", ""))),
    ):
        max_notional = buying_power_usd * float(plan.get("max_notional_fraction", 0.0))
        notional = round(min(gross_budget * weight / total_weight, max_notional), 2)
        if notional <= 0.0:
            continue
        trade_symbol = str(plan["trade_symbol"])
        analysis_symbol = str(plan["analysis_symbol"])
        entry_plan = dict(plan["entry_plan"])
        exit_plan = dict(plan["exit_plan"])
        source_hash = _record_hash(plan)
        intent_id = hashlib.sha256(
            (
                f"leveraged_etf|buy|{trade_symbol}|{analysis_symbol}|"
                f"{plan.get('source_as_of_date')}|{source_hash}"
            ).encode("utf-8")
        ).hexdigest()
        intents.append(
            LiveExecutionIntent(
                intent_id=intent_id,
                instrument="equity",
                symbol=trade_symbol,
                side="buy",
                order_type="market",
                limit_price=0.0,
                time_in_force="day",
                extended_hours=False,
                notional_usd=notional,
                quantity=0.0,
                source_as_of_date=str(plan.get("source_as_of_date", "")),
                source_hash=source_hash,
                thesis_direction=str(plan.get("exposure_direction", "")),
                analysis_symbol=analysis_symbol,
                analysis_relationship=str(plan.get("analysis_relationship", "")),
                analysis_reference_price=float(entry_plan["analysis_reference_price"]),
                analysis_invalidation_price=float(
                    exit_plan["analysis_invalidation_price"]
                ),
                analysis_target_price=float(exit_plan["analysis_target_price"]),
                daily_leverage_multiple=float(plan["daily_leverage_multiple"]),
                daily_reset=True,
                maximum_holding_sessions=int(exit_plan["maximum_holding_sessions"]),
                reference_price=0.0,
                invalidation_price=0.0,
                target_price=0.0,
                expected_hold_trading_days=int(plan["expected_hold_trading_days"]),
                execution_snapshot=None,
                option_contract={},
                reason_codes=tuple(
                    str(value) for value in plan.get("reason_codes", [])
                ),
            )
        )
    return tuple(intents)


def _option_contracts(repository_root: Path) -> dict[str, dict[str, Any]]:
    path = (
        repository_root.resolve()
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl"
    )
    selected: dict[str, dict[str, Any]] = {}
    for record in _jsonl(path):
        primary = record.get("primary_contract")
        if record.get(
            "selection_status"
        ) != "tracked_contracts_selected" or not isinstance(primary, dict):
            continue
        if (
            record.get("live_branch_execution_eligible") is not True
            or record.get("contract_role")
            != "live_branch_candidate_after_independent_execution_gates"
            or record.get("live_blocked") is not False
            or not str(primary.get("contract_id", ""))
            or not str(primary.get("quote_observed_at", ""))
        ):
            continue
        symbol = str(record.get("symbol", ""))
        if SYMBOL_PATTERN.fullmatch(symbol):
            selected[symbol] = record
    return selected


def option_eligible_symbols(repository_root: Path) -> frozenset[str]:
    return frozenset(_option_contracts(repository_root))


def _option_quote_matches_market_session(
    primary_contract: dict[str, Any],
    market_date: date,
) -> bool:
    try:
        observed_at = datetime.fromisoformat(
            str(primary_contract.get("quote_observed_at", "")).replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return False
    return bool(
        observed_at.tzinfo is not None
        and observed_at.astimezone(NEW_YORK).date() == market_date
    )


def build_option_entry_intents(
    repository_root: Path,
    buying_power_usd: float,
    market_date: date,
) -> tuple[LiveExecutionIntent, ...]:
    if not math.isfinite(buying_power_usd) or buying_power_usd <= 0.0:
        return ()
    allowed_source_dates = _allowed_source_dates(market_date)
    thesis_path = (
        repository_root.resolve()
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "equity_swing_theses.jsonl"
    )
    theses = {
        str(record.get("symbol", "")): record
        for record in _jsonl(thesis_path)
        if record.get("thesis_status") == "actionable_shadow_thesis"
        and _thesis_promoted_for_execution(record)
        and record.get("trade_intent") != "no_trade"
        and str(record.get("as_of_date", "")) in allowed_source_dates
    }
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], float]] = []
    for symbol, selection in _option_contracts(repository_root).items():
        thesis = theses.get(symbol)
        primary = selection.get("primary_contract")
        if thesis is None or not isinstance(primary, dict):
            continue
        option_type = str(primary.get("option_type", selection.get("option_type", "")))
        direction = str(thesis.get("direction", ""))
        if (direction, option_type) not in {("bullish", "call"), ("bearish", "put")}:
            continue
        ask = float(primary.get("ask", 0.0))
        contract_score = float(primary.get("contract_score", 0.0))
        if (
            ask <= 0.0
            or contract_score <= 0.0
            or str(primary.get("hard_reject_reason", ""))
            or not _option_quote_matches_market_session(primary, market_date)
        ):
            continue
        candidates.append((thesis, selection, primary, _score(thesis) * contract_score))
    total_weight = sum(candidate[3] for candidate in candidates)
    if total_weight <= 0.0:
        return ()
    intents: list[LiveExecutionIntent] = []
    for thesis, selection, primary, weight in sorted(
        candidates,
        key=lambda candidate: (-candidate[3], str(candidate[0].get("symbol", ""))),
    ):
        symbol = str(thesis["symbol"])
        premium_per_contract = float(primary["ask"]) * 100.0
        allocation = buying_power_usd * weight / total_weight
        quantity = math.floor(allocation / premium_per_contract)
        if quantity <= 0:
            continue
        option_contract = {
            "contract_symbol_key": str(primary.get("contract_symbol_key", "")),
            "expiry": str(primary.get("expiry", "")),
            "option_type": str(
                primary.get("option_type", selection.get("option_type", ""))
            ),
            "strike": float(primary.get("strike", 0.0)),
            "limit_price": float(primary["ask"]),
            "order_action": "buy_to_open",
            "defined_risk": True,
            "quote_observed_at": str(primary["quote_observed_at"]),
            "maximum_loss_usd": round(premium_per_contract * quantity, 2),
        }
        source = {"thesis": thesis, "contract": selection}
        source_hash = _record_hash(source)
        intent_id = hashlib.sha256(
            f"option|buy|{symbol}|{thesis.get('as_of_date')}|{source_hash}".encode(
                "utf-8"
            )
        ).hexdigest()
        intents.append(
            LiveExecutionIntent(
                intent_id=intent_id,
                instrument="option",
                symbol=symbol,
                side="buy",
                order_type="limit",
                limit_price=float(primary["ask"]),
                time_in_force="day",
                extended_hours=False,
                notional_usd=round(premium_per_contract * quantity, 2),
                quantity=float(quantity),
                source_as_of_date=str(thesis.get("as_of_date", "")),
                source_hash=source_hash,
                thesis_direction=str(thesis.get("direction", "")),
                analysis_symbol=symbol,
                analysis_relationship="self",
                analysis_reference_price=float(
                    thesis.get("entry_reference_price") or 0.0
                ),
                analysis_invalidation_price=float(
                    thesis.get("invalidation_price") or 0.0
                ),
                analysis_target_price=float(thesis.get("target_price") or 0.0),
                daily_leverage_multiple=1.0,
                daily_reset=False,
                maximum_holding_sessions=int(
                    thesis.get("expected_hold_trading_days", 0)
                ),
                reference_price=float(primary.get("ask", 0.0)),
                invalidation_price=float(thesis.get("invalidation_price") or 0.0),
                target_price=float(thesis.get("target_price") or 0.0),
                expected_hold_trading_days=int(
                    thesis.get("expected_hold_trading_days", 0)
                ),
                execution_snapshot=None,
                option_contract=option_contract,
                reason_codes=tuple(
                    str(value) for value in thesis.get("reason_codes", [])
                ),
            )
        )
    return tuple(intents)


def build_entry_intents(
    repository_root: Path,
    buying_power_usd: float,
    market_date: date,
    stocks_enabled: bool,
    options_enabled: bool,
    held_equity_symbols: frozenset[str],
) -> tuple[LiveExecutionIntent, ...]:
    if research_maturity_blockers(repository_root):
        return ()
    thesis_path = (
        repository_root.resolve()
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "equity_swing_theses.jsonl"
    )
    allowed_source_dates = _allowed_source_dates(market_date)
    actionable = [
        record
        for record in _jsonl(thesis_path)
        if record.get("thesis_status") == "actionable_shadow_thesis"
        and _thesis_promoted_for_execution(record)
        and record.get("trade_intent") != "no_trade"
        and str(record.get("as_of_date", "")) in allowed_source_dates
    ]
    actionable_symbols = frozenset(
        str(record.get("symbol", "")) for record in actionable
    )
    leveraged = (
        build_leveraged_etf_entry_intents(
            repository_root,
            buying_power_usd,
            market_date,
            held_equity_symbols,
        )
        if stocks_enabled
        else ()
    )
    leveraged_underlyings = frozenset(intent.analysis_symbol for intent in leveraged)
    leveraged_notional = sum(intent.notional_usd for intent in leveraged)
    remaining_buying_power = max(buying_power_usd - leveraged_notional, 0.0)
    option_symbols = (
        option_eligible_symbols(repository_root)
        & actionable_symbols - leveraged_underlyings
        if options_enabled
        else frozenset()
    )
    equity_symbols = {
        str(record.get("symbol", ""))
        for record in actionable
        if record.get("direction") == "bullish"
        and str(record.get("symbol", "")) not in option_symbols
        and str(record.get("symbol", "")) not in leveraged_underlyings
        and str(record.get("symbol", "")) not in held_equity_symbols
        and stocks_enabled
    }
    expression_count = len(option_symbols) + len(equity_symbols)
    if expression_count == 0:
        return tuple(
            sorted(leveraged, key=lambda intent: (intent.instrument, intent.symbol))
        )
    option_budget = remaining_buying_power * len(option_symbols) / expression_count
    equity_budget = remaining_buying_power - option_budget
    options = (
        build_option_entry_intents(repository_root, option_budget, market_date)
        if option_symbols
        else ()
    )
    equities = (
        build_stock_entry_intents(
            repository_root,
            equity_budget,
            market_date,
            option_symbols | leveraged_underlyings | held_equity_symbols,
        )
        if equity_symbols
        else ()
    )
    return tuple(
        sorted(
            (*leveraged, *equities, *options),
            key=lambda intent: (intent.instrument, intent.symbol),
        )
    )
