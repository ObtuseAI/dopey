"""Evidence-gated evolution of the non-core research symbol universe.

This module ranks staged non-core symbols on four independent surfaces:
current attention, observed dollar liquidity, capitalization, and local
research tradability. It never reads broker state and never creates an order.

Membership changes are transactional. If any currently active non-core symbol
lacks a required evidence field, the whole cycle is blocked and the registry
is returned unchanged. Candidate evidence gaps block only that candidate.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from dopey.protocols.identity import canonical_hash
from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE
from dopey_research_pipeline.artifact_io import write_json_atomic, write_jsonl_atomic

from .symbol_dossier import build_dossiers
from .universe_registry import (
    MAX_ACTIVE_UNIVERSE_SIZE,
    MEMBERSHIP_POLICY_VERSION,
    UNIVERSE_ARTIFACT_DIR,
    UNIVERSE_CAPACITY_POLICY,
    active_universe,
    demote_to_standby,
    load_registry,
    promote_to_probation,
    save_registry,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
ATTENTION_SNAPSHOT_PATH = REPO_ROOT / "artifacts" / "dopey" / "attention" / "attention_snapshot.json"
HISTORY_RAW_DIR = REPO_ROOT / "dopey_data" / "history" / "raw"
FUNDAMENTALS_PATH = REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context" / "fundamentals.csv"
EVOLVING_UNIVERSE_SUMMARY_PATH = UNIVERSE_ARTIFACT_DIR / "evolving_universe_summary.json"
UNIVERSE_DOSSIERS_PATH = UNIVERSE_ARTIFACT_DIR / "symbol_dossiers.jsonl"

EVOLVING_UNIVERSE_SCHEMA_VERSION = "dopey-evolving-universe-summary-v1"
MINIMUM_HISTORY_ROWS = 20
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
CORE_FUND_SYMBOLS = frozenset(
    {
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "IBIT",
        "XLF",
        "XLK",
        "XLE",
        "XLY",
        "XLI",
        "XLU",
        "XLP",
        "XLV",
    }
)
CORE_CONTEXT_SYMBOLS = frozenset({"VIX"})


class EvolutionPolicy(TypedDict):
    maximum_active_universe_size: int
    attention_weight: float
    liquidity_weight: float
    market_cap_weight: float
    tradability_weight: float
    promotion_score_floor: float
    retention_score_floor: float
    promotion_attention_floor: float
    retention_attention_floor: float
    minimum_attention_completeness: float
    minimum_average_dollar_volume: float
    minimum_market_cap: float
    minimum_etf_fund_assets: float
    attention_max_age_hours: float
    liquidity_max_age_calendar_days: int
    market_cap_max_age_calendar_days: int


class UniverseEvolutionEvidenceError(ValueError):
    """Raised when a governed evidence artifact violates its schema."""


def universe_evolution_policy() -> EvolutionPolicy:
    """Return the immutable v1 selection policy as a fresh value."""

    return {
        "maximum_active_universe_size": MAX_ACTIVE_UNIVERSE_SIZE,
        "attention_weight": 0.45,
        "liquidity_weight": 0.25,
        "market_cap_weight": 0.20,
        "tradability_weight": 0.10,
        "promotion_score_floor": 0.55,
        "retention_score_floor": 0.40,
        "promotion_attention_floor": 0.20,
        "retention_attention_floor": 0.05,
        "minimum_attention_completeness": 0.50,
        "minimum_average_dollar_volume": 5_000_000.0,
        "minimum_market_cap": 1_000_000_000.0,
        "minimum_etf_fund_assets": 250_000_000.0,
        "attention_max_age_hours": 36.0,
        "liquidity_max_age_calendar_days": 7,
        "market_cap_max_age_calendar_days": 45,
    }


def _parse_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise UniverseEvolutionEvidenceError(f"{field_name} must be a non-empty UTC timestamp")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise UniverseEvolutionEvidenceError(
            f"{field_name} is not an ISO-8601 timestamp: value={value!r}"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UniverseEvolutionEvidenceError(f"{field_name} must include a UTC offset: value={value!r}")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UniverseEvolutionEvidenceError(f"{field_name} must be numeric: value={value!r}")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise UniverseEvolutionEvidenceError(f"{field_name} must be finite: value={value!r}")
    return numeric


def _bounded_score(value: object, field_name: str) -> float:
    score = _finite_number(value, field_name)
    if score < 0.0 or score > 1.0:
        raise UniverseEvolutionEvidenceError(f"{field_name} must be in [0, 1]: value={score}")
    return score


def _stable_json_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_csv_number(value: object, field_name: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise UniverseEvolutionEvidenceError(
            f"{field_name} must be a non-empty numeric CSV field: value={value!r}"
        )
    try:
        numeric = float(value)
    except ValueError as error:
        raise UniverseEvolutionEvidenceError(
            f"{field_name} must be numeric: value={value!r}"
        ) from error
    if not math.isfinite(numeric):
        raise UniverseEvolutionEvidenceError(f"{field_name} must be finite: value={value!r}")
    return numeric


def _load_attention_snapshot(path: Path) -> dict[str, object]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise UniverseEvolutionEvidenceError(
            f"attention snapshot is unavailable: path={path}, error={error}"
        ) from error
    except json.JSONDecodeError as error:
        raise UniverseEvolutionEvidenceError(
            f"attention snapshot is invalid JSON: path={path}, error={error}"
        ) from error
    if not isinstance(parsed, dict):
        raise UniverseEvolutionEvidenceError(f"attention snapshot must be an object: path={path}")
    return parsed


def _validated_attention_records(
    snapshot: dict[str, object],
    now_utc: datetime,
    policy: EvolutionPolicy,
) -> tuple[datetime, dict[str, dict[str, object]]]:
    if snapshot.get("schema_version") != "dopey-attention-snapshot-v1":
        raise UniverseEvolutionEvidenceError(
            f"attention snapshot schema is unsupported: {snapshot.get('schema_version')!r}"
        )
    status = snapshot.get("status")
    if status not in {"scored", "partial"}:
        raise UniverseEvolutionEvidenceError(
            f"attention snapshot status is not usable: status={status!r}"
        )
    if snapshot.get("research_only") is not True:
        raise UniverseEvolutionEvidenceError("attention snapshot must declare research_only=true")
    if snapshot.get("live_execution_allowed") is not False:
        raise UniverseEvolutionEvidenceError("attention snapshot must declare live_execution_allowed=false")
    if snapshot.get("future_observation_consumed") is not False:
        raise UniverseEvolutionEvidenceError("attention snapshot must exclude future observations")
    if snapshot.get("directional_signal_allowed") is not False:
        raise UniverseEvolutionEvidenceError("attention snapshot must be direction-neutral")
    if snapshot.get("directional_bias") is not None:
        raise UniverseEvolutionEvidenceError("attention snapshot directional_bias must be null")
    if snapshot.get("research_priority_only") is not True:
        raise UniverseEvolutionEvidenceError("attention snapshot must declare research_priority_only=true")
    if snapshot.get("trade_promotion_allowed") is not False:
        raise UniverseEvolutionEvidenceError("attention snapshot must declare trade_promotion_allowed=false")
    expected_snapshot_hash = snapshot.get("snapshot_sha256")
    if not isinstance(expected_snapshot_hash, str) or len(expected_snapshot_hash) != 64:
        raise UniverseEvolutionEvidenceError("attention snapshot lacks a valid snapshot_sha256")
    actual_snapshot_hash = _stable_json_hash({**snapshot, "snapshot_sha256": ""})
    if actual_snapshot_hash != expected_snapshot_hash:
        raise UniverseEvolutionEvidenceError(
            "attention snapshot SHA-256 mismatch: "
            f"expected={expected_snapshot_hash}, actual={actual_snapshot_hash}"
        )
    decision_time = _parse_utc(snapshot.get("decision_time_utc"), "attention.decision_time_utc")
    generated_time = _parse_utc(snapshot.get("generated_at_utc"), "attention.generated_at_utc")
    if decision_time > now_utc or generated_time > now_utc:
        raise UniverseEvolutionEvidenceError(
            "attention snapshot contains future-dated decision or generation time"
        )
    age_hours = (now_utc - generated_time).total_seconds() / 3600.0
    if age_hours > policy["attention_max_age_hours"]:
        raise UniverseEvolutionEvidenceError(
            "attention snapshot is stale: "
            f"age_hours={age_hours:.3f}, maximum={policy['attention_max_age_hours']}"
        )
    raw_symbols = snapshot.get("symbols")
    if not isinstance(raw_symbols, list):
        raise UniverseEvolutionEvidenceError("attention.symbols must be a list")
    if snapshot.get("symbol_count") != len(raw_symbols):
        raise UniverseEvolutionEvidenceError(
            "attention symbol_count does not match symbols length: "
            f"declared={snapshot.get('symbol_count')}, actual={len(raw_symbols)}"
        )
    records: dict[str, dict[str, object]] = {}
    for index, raw_record in enumerate(raw_symbols):
        if not isinstance(raw_record, dict):
            raise UniverseEvolutionEvidenceError(
                f"attention.symbols[{index}] must be an object"
            )
        symbol = str(raw_record.get("symbol", "")).strip().upper()
        if not SYMBOL_PATTERN.fullmatch(symbol):
            raise UniverseEvolutionEvidenceError(
                f"attention.symbols[{index}].symbol is invalid: value={symbol!r}"
            )
        if symbol in records:
            raise UniverseEvolutionEvidenceError(f"attention snapshot contains duplicate symbol: {symbol}")
        records[symbol] = dict(raw_record)
    return decision_time, records


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_core_capitalizations(
    path: Path,
    decision_time: datetime,
) -> tuple[dict[str, dict[str, object]], str]:
    try:
        source_hash = _file_sha256(path)
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or [])
            required = {"date", "symbol", "market_cap"}
            if not required.issubset(fieldnames):
                return {}, (
                    "fundamentals_missing_required_columns:"
                    f"path={path}, missing={sorted(required - fieldnames)}"
                )
            rows = list(reader)
    except OSError as error:
        return {}, f"fundamentals_unavailable:path={path}, error={error}"
    latest: dict[str, dict[str, object]] = {}
    invalid_rows: list[str] = []
    for index, row in enumerate(rows, start=2):
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol not in REQUIRED_HISTORY_UNIVERSE:
            continue
        raw_date = str(row.get("date", ""))[:10]
        try:
            observed_at = _parse_utc(
                f"{raw_date}T00:00:00+00:00",
                f"fundamentals.row_{index}.date",
            )
            market_cap = _finite_csv_number(
                row.get("market_cap"),
                f"fundamentals.row_{index}.market_cap",
            )
        except UniverseEvolutionEvidenceError as error:
            invalid_rows.append(str(error))
            continue
        if observed_at.date() > decision_time.date() or market_cap <= 0.0:
            continue
        existing = latest.get(symbol)
        if existing is None or str(existing["observed_date"]) < raw_date:
            latest[symbol] = {
                "market_cap": market_cap,
                "observed_date": raw_date,
                "source_path": str(path),
                "source_sha256": source_hash,
            }
    error = ""
    if invalid_rows:
        error = f"fundamentals_invalid_row_count:{len(invalid_rows)}"
    return latest, error


def _history_liquidity_evidence(
    symbol: str,
    history_root: Path,
    decision_time: datetime,
    policy: EvolutionPolicy,
) -> dict[str, object]:
    path = history_root / f"{symbol}.csv"
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = deque(csv.DictReader(handle), maxlen=MINIMUM_HISTORY_ROWS)
    except OSError as error:
        raise UniverseEvolutionEvidenceError(
            f"history file is unavailable: symbol={symbol}, path={path}, error={error}"
        ) from error
    if len(rows) != MINIMUM_HISTORY_ROWS:
        raise UniverseEvolutionEvidenceError(
            f"history has insufficient rows: symbol={symbol}, rows={len(rows)}, required={MINIMUM_HISTORY_ROWS}"
        )
    observed_dates: list[datetime] = []
    dollar_volumes: list[float] = []
    share_volumes: list[float] = []
    for row_index, row in enumerate(rows):
        row_symbol = str(row.get("symbol", "")).strip().upper()
        if row_symbol != symbol:
            raise UniverseEvolutionEvidenceError(
                f"history symbol mismatch: requested={symbol}, row_symbol={row_symbol}, tail_index={row_index}"
            )
        observed_at = _parse_utc(f"{str(row.get('date', ''))[:10]}T00:00:00+00:00", f"{symbol}.date")
        adjusted_close = _finite_csv_number(
            row.get("adjusted_close"),
            f"{symbol}.adjusted_close",
        )
        volume = _finite_csv_number(row.get("volume"), f"{symbol}.volume")
        if adjusted_close <= 0.0 or volume <= 0.0:
            raise UniverseEvolutionEvidenceError(
                f"history liquidity fields must be positive: symbol={symbol}, adjusted_close={adjusted_close}, volume={volume}"
            )
        observed_dates.append(observed_at)
        dollar_volumes.append(adjusted_close * volume)
        share_volumes.append(volume)
    if observed_dates != sorted(set(observed_dates)):
        raise UniverseEvolutionEvidenceError(
            f"history tail dates must be unique and increasing: symbol={symbol}"
        )
    latest = observed_dates[-1]
    if latest.date() > decision_time.date():
        raise UniverseEvolutionEvidenceError(
            f"history contains future evidence: symbol={symbol}, latest={latest.date()}, decision={decision_time.date()}"
        )
    age_days = (decision_time.date() - latest.date()).days
    if age_days > policy["liquidity_max_age_calendar_days"]:
        raise UniverseEvolutionEvidenceError(
            "history liquidity evidence is stale: "
            f"symbol={symbol}, age_days={age_days}, maximum={policy['liquidity_max_age_calendar_days']}"
        )
    return {
        "avg_dollar_volume_20d": round(sum(dollar_volumes) / len(dollar_volumes), 2),
        "avg_share_volume_20d": round(sum(share_volumes) / len(share_volumes), 2),
        "liquidity_observed_at_utc": latest.isoformat(),
        "history_path": str(path),
        "history_sha256": _file_sha256(path),
        "research_tradable": SYMBOL_PATTERN.fullmatch(symbol) is not None,
        "research_tradability_source": "validated_positive_local_ohlcv_tail",
        "broker_tradability_asserted": False,
    }


def _scaled_log_score(value: float, floor: float, ceiling: float) -> float:
    if value <= floor:
        return 0.0
    if value >= ceiling:
        return 1.0
    return math.log(value / floor) / math.log(ceiling / floor)


def _symbol_evidence(
    symbol: str,
    record: dict[str, object],
    attention_record: dict[str, object] | None,
    core_capitalization: dict[str, object] | None,
    history_root: Path,
    decision_time: datetime,
    policy: EvolutionPolicy,
) -> dict[str, object]:
    missing_reasons: list[str] = []
    attention_score: float | None = None
    completeness_ratio: float | None = None
    attention_provenance = ""
    if attention_record is None:
        missing_reasons.append("missing_attention_record")
    else:
        attention_status = attention_record.get("status")
        if attention_status not in {"scored", "partial"}:
            missing_reasons.append(f"attention_status_{attention_status or 'missing'}")
        try:
            attention_score = _bounded_score(
                attention_record.get("attention_score"),
                f"attention.{symbol}.attention_score",
            )
            completeness_ratio = _bounded_score(
                attention_record.get("completeness_ratio"),
                f"attention.{symbol}.completeness_ratio",
            )
            latest_timestamp = attention_record.get("latest_evidence_at_utc")
            if isinstance(latest_timestamp, str) and latest_timestamp.strip():
                latest_attention = _parse_utc(
                    latest_timestamp,
                    f"attention.{symbol}.latest_evidence_at_utc",
                )
                if latest_attention > decision_time:
                    missing_reasons.append("future_attention_evidence")
                attention_age_hours = (
                    decision_time - latest_attention
                ).total_seconds() / 3600.0
                if attention_age_hours > policy["attention_max_age_hours"]:
                    missing_reasons.append("stale_attention_evidence")
            else:
                market_evidence_date = _parse_utc(
                    f"{str(attention_record.get('latest_market_evidence_date', ''))[:10]}T00:00:00+00:00",
                    f"attention.{symbol}.latest_market_evidence_date",
                )
                if market_evidence_date.date() > decision_time.date():
                    missing_reasons.append("future_attention_market_evidence")
                market_age_days = (
                    decision_time.date() - market_evidence_date.date()
                ).days
                if market_age_days > policy["liquidity_max_age_calendar_days"]:
                    missing_reasons.append("stale_attention_market_evidence")
            if completeness_ratio < policy["minimum_attention_completeness"]:
                missing_reasons.append("attention_completeness_below_floor")
            provenance_value = attention_record.get("provenance_sha256")
            if not isinstance(provenance_value, str) or len(provenance_value) != 64:
                missing_reasons.append("missing_attention_provenance_sha256")
            else:
                actual_provenance = _stable_json_hash(
                    {**attention_record, "provenance_sha256": ""}
                )
                if actual_provenance != provenance_value:
                    missing_reasons.append("attention_provenance_sha256_mismatch")
                else:
                    attention_provenance = provenance_value
        except UniverseEvolutionEvidenceError as error:
            missing_reasons.append(f"invalid_attention_fields:{error}")

    is_core = record.get("tier") == "core"
    staging_proof = record.get("staging_proof")
    market_cap: float | None = None
    fund_assets: float | None = None
    capitalization_kind = "market_cap"
    capitalization_value: float | None = None
    capitalization_floor = policy["minimum_market_cap"]
    instrument_type = ""
    market_cap_observed_at = ""
    if is_core:
        if symbol in CORE_CONTEXT_SYMBOLS:
            instrument_type = "INDEX_CONTEXT"
            capitalization_kind = "not_applicable_context"
            capitalization_floor = 0.0
            missing_reasons.append("core_context_has_no_tradable_capitalization")
        elif symbol in CORE_FUND_SYMBOLS:
            instrument_type = "ETF"
            capitalization_kind = "fund_assets"
            capitalization_floor = policy["minimum_etf_fund_assets"]
            missing_reasons.append("missing_core_fund_assets_evidence")
        else:
            instrument_type = "EQUITY"
            if core_capitalization is None:
                missing_reasons.append("missing_core_market_cap_evidence")
            else:
                try:
                    market_cap = _finite_number(
                        core_capitalization.get("market_cap"),
                        f"{symbol}.core_market_cap",
                    )
                    capitalization_value = market_cap
                    market_cap_observed_at = str(core_capitalization.get("observed_date", ""))
                    observed_time = _parse_utc(
                        f"{market_cap_observed_at[:10]}T00:00:00+00:00",
                        f"{symbol}.core_market_cap_observed_at",
                    )
                    market_cap_observed_at = observed_time.isoformat()
                    market_cap_age = (decision_time.date() - observed_time.date()).days
                    if market_cap_age > policy["market_cap_max_age_calendar_days"]:
                        missing_reasons.append("stale_core_market_cap_evidence")
                except UniverseEvolutionEvidenceError as error:
                    missing_reasons.append(f"invalid_core_market_cap:{error}")
    elif not isinstance(staging_proof, dict):
        missing_reasons.append("missing_staging_proof")
        staging_proof = {}
    else:
        if staging_proof.get("validator_status") != "valid_real_dataset":
            missing_reasons.append("staging_validator_not_valid_real_dataset")
        try:
            market_cap = _finite_number(staging_proof.get("market_cap"), f"{symbol}.market_cap")
        except UniverseEvolutionEvidenceError as error:
            missing_reasons.append(f"invalid_market_cap:{error}")
        raw_instrument_type = staging_proof.get("instrument_type")
        instrument_type = (
            str(raw_instrument_type).strip().upper()
            if isinstance(raw_instrument_type, str)
            else ""
        )
        if instrument_type == "ETF":
            capitalization_kind = "fund_assets"
            capitalization_floor = policy["minimum_etf_fund_assets"]
            try:
                fund_assets = _finite_number(
                    staging_proof.get("fund_assets"),
                    f"{symbol}.fund_assets",
                )
                capitalization_value = fund_assets
            except UniverseEvolutionEvidenceError as error:
                missing_reasons.append(f"invalid_fund_assets:{error}")
        else:
            capitalization_value = market_cap
        observed_value = staging_proof.get("probe_observed_at_utc", record.get("staged_utc"))
        try:
            observed_time = _parse_utc(observed_value, f"{symbol}.market_cap_observed_at_utc")
            market_cap_observed_at = observed_time.isoformat()
            if observed_time > decision_time:
                missing_reasons.append("future_market_cap_evidence")
            market_cap_age = (decision_time.date() - observed_time.date()).days
            if market_cap_age > policy["market_cap_max_age_calendar_days"]:
                missing_reasons.append("stale_market_cap_evidence")
        except UniverseEvolutionEvidenceError as error:
            missing_reasons.append(f"invalid_market_cap_observation_time:{error}")

    liquidity: dict[str, object] = {}
    try:
        liquidity = _history_liquidity_evidence(symbol, history_root, decision_time, policy)
    except UniverseEvolutionEvidenceError as error:
        missing_reasons.append(f"invalid_liquidity_or_tradability:{error}")

    avg_dollar_volume = (
        float(liquidity["avg_dollar_volume_20d"])
        if isinstance(liquidity.get("avg_dollar_volume_20d"), (int, float))
        else None
    )
    research_tradable = liquidity.get("research_tradable") is True
    if symbol in CORE_CONTEXT_SYMBOLS:
        research_tradable = False
    evidence_complete = len(missing_reasons) == 0
    eligibility_reasons: list[str] = []
    if evidence_complete:
        if capitalization_value is None or capitalization_value < capitalization_floor:
            eligibility_reasons.append(
                "etf_fund_assets_below_floor"
                if capitalization_kind == "fund_assets"
                else "market_cap_below_floor"
            )
        if avg_dollar_volume is None or avg_dollar_volume < policy["minimum_average_dollar_volume"]:
            eligibility_reasons.append("average_dollar_volume_below_floor")
        if not research_tradable:
            eligibility_reasons.append("not_research_tradable")

    selection_score: float | None = None
    research_priority_score: float | None = None
    attention_evidence_valid = attention_score is not None and not any(
        "attention" in reason for reason in missing_reasons
    )
    liquidity_evidence_valid = avg_dollar_volume is not None and not any(
        reason.startswith("invalid_liquidity_or_tradability") for reason in missing_reasons
    )
    liquidity_score: float | None = None
    if liquidity_evidence_valid and avg_dollar_volume is not None:
        liquidity_score = _scaled_log_score(
            avg_dollar_volume,
            policy["minimum_average_dollar_volume"],
            1_000_000_000.0,
        )
    if attention_evidence_valid and liquidity_score is not None and attention_score is not None:
        research_priority_score = round(0.65 * attention_score + 0.35 * liquidity_score, 8)
    if (
        evidence_complete
        and attention_score is not None
        and capitalization_value is not None
        and avg_dollar_volume is not None
    ):
        if liquidity_score is None:
            raise UniverseEvolutionEvidenceError(
                f"liquidity score unexpectedly unavailable for complete evidence: symbol={symbol}"
            )
        capitalization_score = _scaled_log_score(
            capitalization_value,
            capitalization_floor,
            1_000_000_000_000.0,
        )
        selection_score = round(
            policy["attention_weight"] * attention_score
            + policy["liquidity_weight"] * liquidity_score
            + policy["market_cap_weight"] * capitalization_score
            + policy["tradability_weight"] * float(research_tradable),
            8,
        )
    body: dict[str, object] = {
        "symbol": symbol,
        "prior_tier": str(record.get("tier", "")),
        "attention_score": attention_score,
        "attention_completeness_ratio": completeness_ratio,
        "attention_provenance_sha256": attention_provenance,
        "avg_dollar_volume_20d": avg_dollar_volume,
        "avg_share_volume_20d": liquidity.get("avg_share_volume_20d"),
        "liquidity_observed_at_utc": liquidity.get("liquidity_observed_at_utc"),
        "history_path": liquidity.get("history_path"),
        "history_sha256": liquidity.get("history_sha256"),
        "market_cap": market_cap,
        "fund_assets": fund_assets,
        "instrument_type": instrument_type or "legacy_unclassified",
        "capitalization_kind": capitalization_kind,
        "capitalization_value": capitalization_value,
        "capitalization_floor": capitalization_floor,
        "market_cap_observed_at_utc": market_cap_observed_at,
        "research_tradable": research_tradable,
        "research_tradability_source": liquidity.get("research_tradability_source"),
        "broker_tradability_asserted": False,
        "selection_score": selection_score,
        "research_priority_score": research_priority_score,
        "evidence_complete": evidence_complete,
        "missing_reason_codes": sorted(missing_reasons),
        "eligibility_reason_codes": sorted(eligibility_reasons),
        "decision_time_utc": decision_time.isoformat(),
    }
    return {**body, "evidence_hash": canonical_hash(body)}


def _positive_reason_codes() -> tuple[str, ...]:
    return (
        "attention_evidence_current",
        "average_dollar_volume_floor_passed",
        "capitalization_floor_passed",
        "research_tradability_passed",
        "ranked_selection_score_passed",
    )


def _blocked_summary(
    status: str,
    decision_time_utc: str,
    registry: dict,
    blocked_symbols: list[dict[str, object]],
    policy: EvolutionPolicy,
    error: str,
) -> dict[str, object]:
    active_count = len(active_universe(registry))
    body: dict[str, object] = {
        "artifact_type": "evolving_symbol_universe",
        "schema_version": EVOLVING_UNIVERSE_SCHEMA_VERSION,
        "policy_version": MEMBERSHIP_POLICY_VERSION,
        "decision_time_utc": decision_time_utc,
        "status": status,
        "capacity_policy": UNIVERSE_CAPACITY_POLICY,
        "maximum_active_universe_size": policy["maximum_active_universe_size"],
        "active_before": active_count,
        "active_after": active_count,
        "available_active_slots": max(policy["maximum_active_universe_size"] - active_count, 0),
        "promoted_symbols": [],
        "demoted_symbols": [],
        "retained_symbols": [],
        "blocked_symbols": blocked_symbols,
        "ranked_members": [],
        "registry_mutated": False,
        "error": error,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}


def evolve_registry(
    registry: dict,
    attention_snapshot: dict[str, object],
    history_root: Path,
    fundamentals_path: Path,
    now_utc: datetime,
    policy: EvolutionPolicy,
) -> tuple[dict, dict[str, object]]:
    """Return an evolved registry and a complete transactional decision artifact."""

    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    if policy["maximum_active_universe_size"] < len(REQUIRED_HISTORY_UNIVERSE):
        raise ValueError(
            "maximum_active_universe_size cannot be smaller than the immutable core universe"
        )
    try:
        decision_time, attention_records = _validated_attention_records(
            attention_snapshot,
            now_utc.astimezone(timezone.utc),
            policy,
        )
    except UniverseEvolutionEvidenceError as error:
        return copy.deepcopy(registry), _blocked_summary(
            "blocked_invalid_attention_snapshot",
            now_utc.astimezone(timezone.utc).isoformat(),
            registry,
            [],
            policy,
            str(error),
        )

    source_registry = copy.deepcopy(registry)
    symbol_records = source_registry.get("symbols")
    if not isinstance(symbol_records, dict):
        return copy.deepcopy(registry), _blocked_summary(
            "blocked_invalid_registry",
            decision_time.isoformat(),
            registry,
            [],
            policy,
            "registry.symbols must be an object",
        )
    core_capitalizations, core_capitalization_source_error = _load_core_capitalizations(
        fundamentals_path,
        decision_time,
    )
    evaluations: dict[str, dict[str, object]] = {
        symbol: _symbol_evidence(
            symbol,
            {"tier": "core"},
            attention_records.get(symbol),
            core_capitalizations.get(symbol),
            history_root,
            decision_time,
            policy,
        )
        for symbol in REQUIRED_HISTORY_UNIVERSE
    }
    for symbol, raw_record in sorted(symbol_records.items()):
        if not isinstance(raw_record, dict):
            continue
        tier = raw_record.get("tier")
        if tier not in {"candidate", "standby", "probation"}:
            continue
        evaluations[str(symbol)] = _symbol_evidence(
            str(symbol),
            raw_record,
            attention_records.get(str(symbol)),
            None,
            history_root,
            decision_time,
            policy,
        )

    incomplete_active = [
        {
            "symbol": symbol,
            "reason_codes": evaluation["missing_reason_codes"],
            "evidence_hash": evaluation["evidence_hash"],
        }
        for symbol, evaluation in sorted(evaluations.items())
        if evaluation["prior_tier"] == "probation" and evaluation["evidence_complete"] is not True
    ]
    if incomplete_active:
        return copy.deepcopy(registry), _blocked_summary(
            "blocked_active_membership_evidence_incomplete",
            decision_time.isoformat(),
            registry,
            incomplete_active,
            policy,
            "at least one active non-core symbol lacks complete current membership evidence",
        )

    eligible_pool: list[dict[str, object]] = []
    blocked_symbols: list[dict[str, object]] = []
    for symbol, evaluation in sorted(evaluations.items()):
        score = evaluation["selection_score"]
        attention_score = evaluation["attention_score"]
        complete = evaluation["evidence_complete"] is True
        hard_reasons = list(evaluation["eligibility_reason_codes"])
        prior_tier = str(evaluation["prior_tier"])
        if prior_tier == "core":
            continue
        retention_eligible = (
            complete
            and not hard_reasons
            and isinstance(score, float)
            and isinstance(attention_score, float)
            and score >= policy["retention_score_floor"]
            and attention_score >= policy["retention_attention_floor"]
        )
        promotion_eligible = (
            complete
            and not hard_reasons
            and isinstance(score, float)
            and isinstance(attention_score, float)
            and score >= policy["promotion_score_floor"]
            and attention_score >= policy["promotion_attention_floor"]
        )
        if (prior_tier == "probation" and retention_eligible) or (
            prior_tier in {"candidate", "standby"} and promotion_eligible
        ):
            eligible_pool.append(evaluation)
            continue
        reasons = list(evaluation["missing_reason_codes"]) + hard_reasons
        if complete and not hard_reasons and isinstance(score, float):
            required_score = (
                policy["retention_score_floor"]
                if prior_tier == "probation"
                else policy["promotion_score_floor"]
            )
            required_attention = (
                policy["retention_attention_floor"]
                if prior_tier == "probation"
                else policy["promotion_attention_floor"]
            )
            if score < required_score:
                reasons.append("selection_score_below_tier_threshold")
            if isinstance(attention_score, float) and attention_score < required_attention:
                reasons.append("attention_score_below_tier_threshold")
        blocked_symbols.append(
            {
                "symbol": symbol,
                "prior_tier": prior_tier,
                "selection_score": score,
                "reason_codes": sorted(set(str(reason) for reason in reasons)),
                "evidence_hash": evaluation["evidence_hash"],
            }
        )

    eligible_pool.sort(
        key=lambda item: (
            -float(item["selection_score"]),
            str(item["symbol"]),
        )
    )
    non_core_slots = policy["maximum_active_universe_size"] - len(REQUIRED_HISTORY_UNIVERSE)
    selected = eligible_pool[:non_core_slots]
    selected_symbols = {str(item["symbol"]) for item in selected}
    ranking = {str(item["symbol"]): index + 1 for index, item in enumerate(eligible_pool)}
    for overflow in eligible_pool[non_core_slots:]:
        blocked_symbols.append(
            {
                "symbol": str(overflow["symbol"]),
                "prior_tier": str(overflow["prior_tier"]),
                "selection_score": overflow["selection_score"],
                "reason_codes": ["outside_maximum_active_universe_rank"],
                "evidence_hash": overflow["evidence_hash"],
            }
        )

    evolved = copy.deepcopy(source_registry)
    promoted: list[str] = []
    demoted: list[str] = []
    retained: list[str] = []
    for symbol, evaluation in sorted(evaluations.items()):
        prior_tier = str(evaluation["prior_tier"])
        if prior_tier == "core":
            continue
        selected_for_membership = symbol in selected_symbols
        rank = ranking.get(symbol)
        reason_codes = _positive_reason_codes() if selected_for_membership else tuple(
            str(value)
            for blocked in blocked_symbols
            if blocked["symbol"] == symbol
            for value in blocked["reason_codes"]
        )
        membership_evidence = {
            "policy_version": MEMBERSHIP_POLICY_VERSION,
            "decision_time_utc": decision_time.isoformat(),
            "evidence_hash": str(evaluation["evidence_hash"]),
            "selection_score": evaluation["selection_score"],
            "rank": rank,
            "reason_codes": list(reason_codes),
        }
        if selected_for_membership and prior_tier in {"candidate", "standby"}:
            record = evolved["symbols"][symbol]
            staging_proof = dict(record.get("staging_proof", {}))
            staging_proof["market_cap"] = evaluation["market_cap"]
            staging_proof["fund_assets"] = evaluation["fund_assets"]
            staging_proof["instrument_type"] = evaluation["instrument_type"]
            staging_proof["capitalization_kind"] = evaluation["capitalization_kind"]
            staging_proof["capitalization_value"] = evaluation["capitalization_value"]
            staging_proof["adv_usd"] = evaluation["avg_dollar_volume_20d"]
            staging_proof["research_tradable"] = evaluation["research_tradable"]
            staging_proof["probe_observed_at_utc"] = str(
                staging_proof.get("probe_observed_at_utc", record.get("staged_utc", ""))
            )
            staging_proof["membership_evidence"] = membership_evidence
            evolved = promote_to_probation(evolved, symbol, staging_proof)
            if evolved["symbols"][symbol].get("tier") == "probation":
                promoted.append(symbol)
        elif selected_for_membership and prior_tier == "probation":
            evolved["symbols"][symbol]["latest_membership_evidence"] = membership_evidence
            retained.append(symbol)
        elif not selected_for_membership and prior_tier == "probation":
            evolved = demote_to_standby(evolved, symbol, reason_codes, membership_evidence)
            demoted.append(symbol)

    active_before = len(active_universe(source_registry))
    active_after = len(active_universe(evolved))
    active_after_symbols = set(active_universe(evolved))
    active_evaluations = [
        evaluation
        for symbol, evaluation in evaluations.items()
        if symbol in active_after_symbols
    ]
    active_evaluations.sort(
        key=lambda item: (
            -float(item["research_priority_score"])
            if isinstance(item["research_priority_score"], float)
            else 1.0,
            str(item["symbol"]),
        )
    )
    research_rank = {
        str(evaluation["symbol"]): index + 1
        for index, evaluation in enumerate(active_evaluations)
    }
    ranked_members: list[dict[str, object]] = []
    for evaluation in active_evaluations:
        symbol = str(evaluation["symbol"])
        prior_tier = str(evaluation["prior_tier"])
        resulting_tier = "core" if prior_tier == "core" else str(
            evolved["symbols"][symbol].get("tier", prior_tier)
        )
        member_reasons = (
            [
                "immutable_core_membership",
                *list(evaluation["missing_reason_codes"]),
                *list(evaluation["eligibility_reason_codes"]),
            ]
            if prior_tier == "core"
            else list(_positive_reason_codes())
        )
        ranked_members.append(
            {
                "symbol": symbol,
                "prior_tier": prior_tier,
                "resulting_tier": resulting_tier,
                "rank": research_rank[symbol],
                "membership_rank": ranking.get(symbol),
                "selection_score": evaluation["selection_score"],
                "research_priority_score": evaluation["research_priority_score"],
                "attention_score": evaluation["attention_score"],
                "avg_dollar_volume_20d": evaluation["avg_dollar_volume_20d"],
                "market_cap": evaluation["market_cap"],
                "fund_assets": evaluation["fund_assets"],
                "instrument_type": evaluation["instrument_type"],
                "capitalization_kind": evaluation["capitalization_kind"],
                "capitalization_value": evaluation["capitalization_value"],
                "research_tradable": evaluation["research_tradable"],
                "evidence_complete": evaluation["evidence_complete"],
                "ranking_eligible_for_playbook": (
                    evaluation["evidence_complete"] is True
                    and evaluation["research_tradable"] is True
                ),
                "reason_codes": sorted(set(str(value) for value in member_reasons)),
                "evidence_hash": evaluation["evidence_hash"],
            }
        )
    body: dict[str, object] = {
        "artifact_type": "evolving_symbol_universe",
        "schema_version": EVOLVING_UNIVERSE_SCHEMA_VERSION,
        "policy_version": MEMBERSHIP_POLICY_VERSION,
        "decision_time_utc": decision_time.isoformat(),
        "status": "evolved",
        "capacity_policy": UNIVERSE_CAPACITY_POLICY,
        "maximum_active_universe_size": policy["maximum_active_universe_size"],
        "active_before": active_before,
        "active_after": active_after,
        "available_active_slots": max(policy["maximum_active_universe_size"] - active_after, 0),
        "promoted_symbols": sorted(promoted),
        "demoted_symbols": sorted(demoted),
        "retained_symbols": sorted(retained),
        "blocked_symbols": sorted(blocked_symbols, key=lambda item: str(item["symbol"])),
        "ranked_members": sorted(
            ranked_members,
            key=lambda item: (
                int(item["rank"]) if isinstance(item["rank"], int) else 1_000_000,
                str(item["symbol"]),
            ),
        ),
        "ranked_member_count": len(ranked_members),
        "full_active_set_ranked": len(ranked_members) == active_after,
        "core_capitalization_source_error": core_capitalization_source_error,
        "registry_mutated": evolved != source_registry,
        "membership_composition_changed": bool(promoted or demoted),
        "ranking_dimensions": [
            "attention",
            "average_dollar_volume",
            "market_cap_or_etf_fund_assets",
            "research_tradability",
        ],
        "broker_tradability_asserted": False,
        "membership_history_retained": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return evolved, {**body, "reproducibility_hash": canonical_hash(body)}


def run_evolving_universe_cycle(
    registry: dict,
    now_utc: datetime,
) -> tuple[dict, dict[str, object]]:
    """Load canonical inputs, run one cycle, and write its decision artifact."""

    policy = universe_evolution_policy()
    try:
        snapshot = _load_attention_snapshot(ATTENTION_SNAPSHOT_PATH)
    except UniverseEvolutionEvidenceError as error:
        summary = _blocked_summary(
            "blocked_missing_or_invalid_attention_snapshot",
            now_utc.astimezone(timezone.utc).isoformat(),
            registry,
            [],
            policy,
            str(error),
        )
        write_json_atomic(EVOLVING_UNIVERSE_SUMMARY_PATH, summary)
        return copy.deepcopy(registry), summary
    evolved, summary = evolve_registry(
        registry,
        snapshot,
        HISTORY_RAW_DIR,
        FUNDAMENTALS_PATH,
        now_utc,
        policy,
    )
    write_json_atomic(EVOLVING_UNIVERSE_SUMMARY_PATH, summary)
    return evolved, summary


def _rehash_summary(
    summary: dict[str, object],
    updates: dict[str, object],
) -> dict[str, object]:
    body = {**summary, **updates}
    body.pop("reproducibility_hash", None)
    return {**body, "reproducibility_hash": canonical_hash(body)}


def refresh_evolving_universe_membership(now_utc: datetime) -> dict[str, object]:
    """Run the canonical multi-daily membership-only refresh.

    Discovery is intentionally absent. A blocked or malformed decision writes
    its blocked summary but never persists the candidate registry. A valid
    evolved decision persists the registry atomically and refreshes dossiers
    so newly promoted symbols are immediately explainable to research UIs.
    """

    registry = load_registry()
    evolved, summary = run_evolving_universe_cycle(registry, now_utc)
    if summary["status"] != "evolved":
        blocked = _rehash_summary(
            summary,
            {
                "registry_persisted": False,
                "dossiers_refreshed": False,
                "membership_refresh_scope": "membership_only_no_discovery",
            },
        )
        write_json_atomic(EVOLVING_UNIVERSE_SUMMARY_PATH, blocked)
        return blocked

    evolved, dossiers, recommendations = build_dossiers(evolved)
    save_registry(evolved)
    write_jsonl_atomic(UNIVERSE_DOSSIERS_PATH, dossiers, keep_backup=True)
    completed = _rehash_summary(
        summary,
        {
            "registry_persisted": True,
            "dossiers_refreshed": True,
            "dossier_count": len(dossiers),
            "dossier_reproducibility_hash": canonical_hash(dossiers),
            "retire_recommendation_count": len(recommendations),
            "membership_refresh_scope": "membership_only_no_discovery",
        },
    )
    write_json_atomic(EVOLVING_UNIVERSE_SUMMARY_PATH, completed)
    return completed
