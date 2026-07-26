"""As-of-safe, source-provenanced attention detection for research routing."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from dopey_data.history_models import HistoryBar, HistoryDataFile
from dopey_data.history_store import (
    HistoryDatasetError,
    file_sha256,
    load_history_manifest,
    load_raw_history_records,
    resolve_history_data_file_path,
)
from dopey_equity_swing.contract_selector import load_option_chain_snapshot
from dopey_equity_swing.news_context import (
    SYMBOL_ALIASES,
    classify_news_events,
    load_news_snapshot,
)
from dopey_equity_swing.snapshot_resolution import resolve_option_snapshot


ATTENTION_SCHEMA_VERSION = "dopey-attention-snapshot-v1"
ATTENTION_ENGINE_VERSION = "dopey-governed-attention-engine-v1"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


class AttentionDataError(RuntimeError):
    """Raised when an attention source violates its governed contract."""


class AttentionPaths(TypedDict):
    repository_root: Path
    history_manifest_path: Path
    news_data_path: Path
    news_manifest_path: Path
    options_chain_root: Path
    options_manifest_path: Path


class AttentionPolicy(TypedDict):
    history_min_bars: int
    baseline_window: int
    rank_lookback: int
    rank_min_observations: int
    news_window_hours: float
    news_manifest_max_age_hours: float
    component_weights: dict[str, float]


def default_attention_policy() -> AttentionPolicy:
    """Return the immutable v1 scoring and missingness policy."""
    return {
        "history_min_bars": 90,
        "baseline_window": 20,
        "rank_lookback": 252,
        "rank_min_observations": 60,
        "news_window_hours": 72.0,
        "news_manifest_max_age_hours": 24.0,
        "component_weights": {
            "market_activity": 0.35,
            "price_volatility_discontinuity": 0.25,
            "news_event_intensity": 0.20,
            "options_activity": 0.20,
        },
    }


def build_attention_snapshot(
    paths: AttentionPaths,
    symbols: list[str],
    market_as_of_date: date,
    decision_time: datetime,
    policy: AttentionPolicy,
) -> dict[str, Any]:
    """Build a deterministic attention snapshot from past/as-of evidence only."""
    normalized_symbols = _validate_request(symbols, market_as_of_date, decision_time)
    _validate_policy(policy)

    history_components, history_provenance = _load_history_components(
        paths,
        normalized_symbols,
        market_as_of_date,
        policy,
    )
    news_components, news_provenance, news_missing = _load_news_components(
        paths,
        normalized_symbols,
        decision_time,
        policy,
    )
    options_components, options_provenance, options_missing = (
        _load_options_components(
            paths,
            normalized_symbols,
            market_as_of_date,
            decision_time,
        )
    )

    symbol_records = [
        _combine_symbol_components(
            symbol,
            history_components[symbol],
            news_components[symbol],
            options_components[symbol],
            market_as_of_date,
            policy,
        )
        for symbol in normalized_symbols
    ]
    missing_sources = [*news_missing, *options_missing]
    scored_count = sum(record["status"] == "scored" for record in symbol_records)
    partial_count = sum(record["status"] == "partial" for record in symbol_records)
    abstained_count = sum(
        record["status"] == "abstained" for record in symbol_records
    )
    status = (
        "abstained"
        if abstained_count == len(symbol_records)
        else "scored"
        if scored_count == len(symbol_records) and not missing_sources
        else "partial"
    )
    payload: dict[str, Any] = {
        "schema_version": ATTENTION_SCHEMA_VERSION,
        "engine_version": ATTENTION_ENGINE_VERSION,
        "generated_at_utc": decision_time.astimezone(timezone.utc).isoformat(),
        "generation_clock": "operator_supplied_decision_time",
        "decision_time_utc": decision_time.astimezone(timezone.utc).isoformat(),
        "market_as_of_date": market_as_of_date.isoformat(),
        "status": status,
        "symbol_count": len(symbol_records),
        "scored_symbol_count": scored_count,
        "partial_symbol_count": partial_count,
        "abstained_symbol_count": abstained_count,
        "ranking_eligible_symbol_count": sum(
            record["attention_score"] is not None for record in symbol_records
        ),
        "policy": policy,
        "symbols": symbol_records,
        "source_provenance": {
            "daily_ohlcv": history_provenance,
            "news": news_provenance,
            "options": options_provenance,
        },
        "missing_sources": missing_sources,
        "future_observation_consumed": False,
        "research_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_execution_allowed": False,
        "broker_authority": False,
        "trade_promotion_allowed": False,
        "universe_research_input_allowed": True,
        "research_priority_only": True,
        "directional_signal_allowed": False,
        "directional_bias": None,
        "not_return_or_edge_evidence": True,
        "snapshot_sha256": "",
    }
    payload["snapshot_sha256"] = _stable_hash(payload)
    return payload


def write_attention_snapshot(snapshot: dict[str, Any], output_path: Path) -> None:
    """Atomically publish a validated attention snapshot."""
    expected_hash = str(snapshot.get("snapshot_sha256", ""))
    if len(expected_hash) != 64:
        raise AttentionDataError("attention snapshot lacks a valid SHA-256 identity")
    verification = {**snapshot, "snapshot_sha256": ""}
    actual_hash = _stable_hash(verification)
    if actual_hash != expected_hash:
        raise AttentionDataError(
            "attention snapshot hash mismatch before publication: "
            f"expected={expected_hash}, actual={actual_hash}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _validate_request(
    symbols: list[str],
    market_as_of_date: date,
    decision_time: datetime,
) -> list[str]:
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")
    if market_as_of_date > decision_time.astimezone(timezone.utc).date():
        raise ValueError(
            "market_as_of_date cannot be after decision_time: "
            f"market_as_of_date={market_as_of_date}, decision_time={decision_time}"
        )
    normalized = sorted({str(symbol).strip().upper() for symbol in symbols})
    if not normalized:
        raise ValueError("attention detection requires at least one symbol")
    invalid = [symbol for symbol in normalized if not _SYMBOL_PATTERN.fullmatch(symbol)]
    if invalid:
        raise ValueError(f"attention detection received invalid symbols: {invalid}")
    return normalized


def _validate_policy(policy: AttentionPolicy) -> None:
    weights = policy["component_weights"]
    expected = {
        "market_activity",
        "price_volatility_discontinuity",
        "news_event_intensity",
        "options_activity",
    }
    if set(weights) != expected:
        raise ValueError(
            f"attention component weights are incomplete: expected={expected}, actual={set(weights)}"
        )
    if any(not math.isfinite(value) or value <= 0.0 for value in weights.values()):
        raise ValueError("attention component weights must be finite and positive")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
        raise ValueError("attention component weights must sum to one")
    if policy["baseline_window"] < 5:
        raise ValueError("attention baseline_window must be at least five")
    if policy["history_min_bars"] <= policy["baseline_window"]:
        raise ValueError("attention history_min_bars must exceed baseline_window")
    if policy["rank_min_observations"] < 20:
        raise ValueError("attention rank_min_observations must be at least twenty")


def _load_history_components(
    paths: AttentionPaths,
    symbols: list[str],
    market_as_of_date: date,
    policy: AttentionPolicy,
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    manifest_path = paths["history_manifest_path"]
    try:
        manifest = load_history_manifest(manifest_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise AttentionDataError(
            f"daily OHLCV manifest is unusable: path={manifest_path}, error={error}"
        ) from error
    if (
        manifest.generated_real_data
        or not manifest.paper_only
        or not manifest.live_blocked
        or manifest.dataset_status != "operator_staged_real_dataset"
    ):
        raise AttentionDataError(
            "daily OHLCV manifest violates the authentic research-data contract: "
            f"path={manifest_path}, status={manifest.dataset_status}, "
            f"generated_real_data={manifest.generated_real_data}, "
            f"paper_only={manifest.paper_only}, live_blocked={manifest.live_blocked}"
        )
    manifest_hash = file_sha256(manifest_path)
    computed_manifest_hash = str(
        manifest.to_dict().get("manifest_reproducibility_hash", "")
    )
    if manifest.manifest_reproducibility_hash != computed_manifest_hash:
        raise AttentionDataError(
            "daily OHLCV manifest reproducibility hash mismatch: "
            f"path={manifest_path}, expected={manifest.manifest_reproducibility_hash}, "
            f"actual={computed_manifest_hash}"
        )
    files_by_symbol: dict[str, HistoryDataFile] = {}
    for file_reference in manifest.data_files:
        for raw_symbol in file_reference.symbols:
            symbol = raw_symbol.strip().upper()
            if symbol in files_by_symbol:
                raise AttentionDataError(
                    "daily OHLCV manifest maps a symbol to multiple files: "
                    f"symbol={symbol}, path={manifest_path}"
                )
            files_by_symbol[symbol] = file_reference

    output: dict[str, dict[str, dict[str, Any]]] = {}
    unavailable_count = 0
    for symbol in symbols:
        file_reference = files_by_symbol.get(symbol)
        if file_reference is None:
            reason = f"history_manifest_missing_symbol:{symbol}"
            output[symbol] = {
                "market_activity": _unavailable_component(
                    "market_activity", reason
                ),
                "price_volatility_discontinuity": _unavailable_component(
                    "price_volatility_discontinuity", reason
                ),
            }
            unavailable_count += 1
            continue
        try:
            output[symbol] = _load_symbol_history_components(
                manifest_path,
                manifest,
                file_reference,
                symbol,
                market_as_of_date,
                policy,
                paths["repository_root"],
            )
        except (OSError, ValueError, TypeError, HistoryDatasetError) as error:
            reason = f"history_symbol_unusable:{symbol}:{error}"
            output[symbol] = {
                "market_activity": _unavailable_component(
                    "market_activity", reason
                ),
                "price_volatility_discontinuity": _unavailable_component(
                    "price_volatility_discontinuity", reason
                ),
            }
            unavailable_count += 1
    provenance = {
        "status": "partial" if unavailable_count else "validated",
        "manifest_path": _relative_path(paths["repository_root"], manifest_path),
        "manifest_sha256": manifest_hash,
        "dataset_id": manifest.dataset_id,
        "dataset_status": manifest.dataset_status,
        "manifest_file_count": len(manifest.data_files),
        "requested_symbol_count": len(symbols),
        "unavailable_symbol_count": unavailable_count,
        "as_of_rule": "rows_with_date_lte_market_as_of_exact_frontier_required",
    }
    return output, provenance


def _load_symbol_history_components(
    manifest_path: Path,
    manifest: Any,
    file_reference: HistoryDataFile,
    symbol: str,
    market_as_of_date: date,
    policy: AttentionPolicy,
    repository_root: Path,
) -> dict[str, dict[str, Any]]:
    path = resolve_history_data_file_path(manifest_path, manifest, file_reference)
    actual_hash = file_sha256(path)
    if actual_hash != file_reference.sha256:
        raise ValueError(
            "daily OHLCV file hash mismatch: "
            f"path={path}, expected={file_reference.sha256}, actual={actual_hash}"
        )
    raw_records = load_raw_history_records(path, file_reference.format)
    if len(raw_records) != file_reference.row_count:
        raise ValueError(
            "daily OHLCV row count mismatch: "
            f"path={path}, expected={file_reference.row_count}, actual={len(raw_records)}"
        )
    all_bars = [HistoryBar.from_dict(record) for record in raw_records]
    _validate_history_bars(all_bars, symbol, path)
    selected = [
        bar for bar in all_bars if date.fromisoformat(bar.date) <= market_as_of_date
    ]
    future_excluded = len(all_bars) - len(selected)
    if not selected or selected[-1].date != market_as_of_date.isoformat():
        observed = selected[-1].date if selected else "none"
        raise ValueError(
            "daily OHLCV lacks the exact market frontier: "
            f"path={path}, expected={market_as_of_date}, observed={observed}"
        )
    if len(selected) < policy["history_min_bars"]:
        raise ValueError(
            "daily OHLCV has insufficient history: "
            f"path={path}, required={policy['history_min_bars']}, actual={len(selected)}"
        )
    slice_hash = _stable_hash([_history_bar_payload(bar) for bar in selected])
    source = {
        "path": _relative_path(repository_root, path),
        "source_sha256": actual_hash,
        "source_slice_sha256": slice_hash,
        "source_label": file_reference.source,
        "observation_date": market_as_of_date.isoformat(),
        "observed_at_utc": "",
        "timestamp_granularity": "market_session_date",
        "input_count": len(selected),
        "future_observation_count_excluded": future_excluded,
    }
    return {
        "market_activity": _score_market_activity(selected, source, policy),
        "price_volatility_discontinuity": _score_price_discontinuity(
            selected, source, policy
        ),
    }


def _validate_history_bars(
    bars: list[HistoryBar], symbol: str, path: Path
) -> None:
    if not bars:
        raise ValueError(f"daily OHLCV file is empty: path={path}")
    dates: set[str] = set()
    previous_date = ""
    for index, bar in enumerate(bars):
        if bar.symbol != symbol:
            raise ValueError(
                f"daily OHLCV symbol mismatch: path={path}, row={index + 2}, "
                f"expected={symbol}, actual={bar.symbol}"
            )
        if not bar.source:
            raise ValueError(
                f"daily OHLCV row lacks source: path={path}, row={index + 2}"
            )
        if bar.date in dates or (previous_date and bar.date <= previous_date):
            raise ValueError(
                f"daily OHLCV dates are duplicate or unordered: path={path}, date={bar.date}"
            )
        numeric = (
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.adjusted_close,
            float(bar.volume),
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError(
                f"daily OHLCV contains nonfinite data: path={path}, date={bar.date}"
            )
        if min(bar.open, bar.high, bar.low, bar.close, bar.adjusted_close) <= 0.0:
            raise ValueError(
                f"daily OHLCV contains nonpositive prices: path={path}, date={bar.date}"
            )
        if bar.volume < 0 or bar.high < max(bar.open, bar.close, bar.low):
            raise ValueError(
                f"daily OHLCV violates price or volume invariants: path={path}, date={bar.date}"
            )
        if bar.low > min(bar.open, bar.close, bar.high):
            raise ValueError(
                f"daily OHLCV low invariant failed: path={path}, date={bar.date}"
            )
        dates.add(bar.date)
        previous_date = bar.date


def _score_market_activity(
    bars: list[HistoryBar], source: dict[str, Any], policy: AttentionPolicy
) -> dict[str, Any]:
    window = policy["baseline_window"]
    final_index = len(bars) - 1
    current_volume_ratio = _relative_ratio(
        float(bars[final_index].volume),
        [float(bar.volume) for bar in bars[final_index - window : final_index]],
    )
    current_turnover = bars[final_index].close * bars[final_index].volume
    current_turnover_ratio = _relative_ratio(
        current_turnover,
        [
            bar.close * bar.volume
            for bar in bars[final_index - window : final_index]
        ],
    )
    volume_history = _historical_relative_ratios(
        [float(bar.volume) for bar in bars], window, final_index
    )[-policy["rank_lookback"] :]
    turnover_history = _historical_relative_ratios(
        [bar.close * bar.volume for bar in bars], window, final_index
    )[-policy["rank_lookback"] :]
    minimum = policy["rank_min_observations"]
    if (
        current_volume_ratio is None
        or current_turnover_ratio is None
        or len(volume_history) < minimum
        or len(turnover_history) < minimum
    ):
        return _unavailable_component(
            "market_activity",
            "insufficient_nonzero_relative_volume_or_turnover_baseline",
            source,
        )
    volume_rank = _percentile_rank(current_volume_ratio, volume_history)
    turnover_rank = _percentile_rank(current_turnover_ratio, turnover_history)
    score = 0.55 * volume_rank + 0.45 * turnover_rank
    return _scored_component(
        "market_activity",
        score,
        source,
        {
            "relative_volume": round(current_volume_ratio, 8),
            "relative_turnover": round(current_turnover_ratio, 8),
            "relative_volume_percentile": round(volume_rank, 8),
            "relative_turnover_percentile": round(turnover_rank, 8),
            "baseline_session_count": window,
            "rank_volume_observation_count": len(volume_history),
            "rank_turnover_observation_count": len(turnover_history),
        },
        [],
        "scored",
    )


def _score_price_discontinuity(
    bars: list[HistoryBar], source: dict[str, Any], policy: AttentionPolicy
) -> dict[str, Any]:
    final_index = len(bars) - 1
    previous = bars[final_index - 1]
    current = bars[final_index]
    current_return = abs(current.adjusted_close / previous.adjusted_close - 1.0)
    current_gap = abs(current.open / previous.close - 1.0)
    current_range = (current.high - current.low) / previous.close
    historical_returns = [
        abs(bars[index].adjusted_close / bars[index - 1].adjusted_close - 1.0)
        for index in range(1, final_index)
    ][-policy["rank_lookback"] :]
    historical_gaps = [
        abs(bars[index].open / bars[index - 1].close - 1.0)
        for index in range(1, final_index)
    ][-policy["rank_lookback"] :]
    historical_ranges = [
        (bars[index].high - bars[index].low) / bars[index - 1].close
        for index in range(1, final_index)
    ][-policy["rank_lookback"] :]
    minimum = policy["rank_min_observations"]
    if min(
        len(historical_returns), len(historical_gaps), len(historical_ranges)
    ) < minimum:
        return _unavailable_component(
            "price_volatility_discontinuity",
            "insufficient_price_discontinuity_rank_history",
            source,
        )
    return_rank = _percentile_rank(current_return, historical_returns)
    gap_rank = _percentile_rank(current_gap, historical_gaps)
    range_rank = _percentile_rank(current_range, historical_ranges)
    score = 0.45 * return_rank + 0.25 * gap_rank + 0.30 * range_rank
    return _scored_component(
        "price_volatility_discontinuity",
        score,
        source,
        {
            "absolute_adjusted_return": round(current_return, 8),
            "absolute_overnight_gap": round(current_gap, 8),
            "intraday_range_fraction": round(current_range, 8),
            "return_percentile": round(return_rank, 8),
            "gap_percentile": round(gap_rank, 8),
            "range_percentile": round(range_rank, 8),
            "rank_observation_count": len(historical_returns),
        },
        [],
        "scored",
    )


def _load_news_components(
    paths: AttentionPaths,
    symbols: list[str],
    decision_time: datetime,
    policy: AttentionPolicy,
) -> tuple[
    dict[str, dict[str, Any]], dict[str, Any], list[dict[str, str]]
]:
    data_path = paths["news_data_path"]
    manifest_path = paths["news_manifest_path"]
    try:
        events, manifest = load_news_snapshot(data_path, manifest_path)
        created_at = _parse_aware_datetime(
            manifest.get("created_at"), "news manifest created_at"
        )
        decision_utc = decision_time.astimezone(timezone.utc)
        if created_at > decision_utc:
            raise ValueError(
                "news manifest was created after the decision time: "
                f"created_at={created_at.isoformat()}, decision_time={decision_utc.isoformat()}"
            )
        age_hours = (decision_utc - created_at).total_seconds() / 3600.0
        if age_hours > policy["news_manifest_max_age_hours"]:
            raise ValueError(
                "news manifest is stale: "
                f"age_hours={age_hours:.6f}, maximum={policy['news_manifest_max_age_hours']}"
            )
        classified = classify_news_events(events, decision_time)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        reason = f"news_source_unavailable:{error}"
        return (
            {
                symbol: _unavailable_component("news_event_intensity", reason)
                for symbol in symbols
            },
            {
                "status": "unavailable",
                "manifest_path": _relative_path(
                    paths["repository_root"], manifest_path
                ),
                "data_path": _relative_path(paths["repository_root"], data_path),
                "reason": reason,
            },
            [{"source": "news", "reason": reason}],
        )

    output = {
        symbol: _score_news_symbol(
            symbol,
            classified,
            data_path,
            file_sha256(data_path),
            created_at,
            policy,
            paths["repository_root"],
        )
        for symbol in symbols
    }
    provenance = {
        "status": "validated",
        "manifest_path": _relative_path(paths["repository_root"], manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "data_path": _relative_path(paths["repository_root"], data_path),
        "data_sha256": file_sha256(data_path),
        "manifest_created_at_utc": created_at.isoformat(),
        "event_count": len(events),
        "provider_terms_reviewed": True,
        "full_text_stored": bool(manifest.get("full_text_stored", False)),
        "coverage_policy": "source_provenanced_query_selected_metadata",
    }
    return output, provenance, []


def _score_news_symbol(
    symbol: str,
    events: list[dict[str, Any]],
    data_path: Path,
    data_hash: str,
    created_at: datetime,
    policy: AttentionPolicy,
    repository_root: Path,
) -> dict[str, Any]:
    candidates = [
        event
        for event in events
        if event.get("age_hours_at_decision") is not None
        and 0.0 <= float(event["age_hours_at_decision"]) <= policy["news_window_hours"]
    ]
    exact_mentions = [
        event for event in candidates if _event_explicitly_mentions_symbol(event, symbol)
    ]
    alias_covered = symbol in SYMBOL_ALIASES
    matching = [
        event
        for event in candidates
        if symbol in event.get("affected_symbols", []) or event in exact_mentions
    ]
    if not alias_covered and not exact_mentions:
        return _unavailable_component(
            "news_event_intensity",
            f"news_symbol_identity_mapping_unavailable:{symbol}",
            {
                "path": _relative_path(repository_root, data_path),
                "source_sha256": data_hash,
                "source_slice_sha256": "",
                "source_label": "source_provenanced_news_context",
                "observation_date": created_at.date().isoformat(),
                "observed_at_utc": created_at.isoformat(),
                "timestamp_granularity": "event_timestamp",
                "input_count": 0,
                "future_observation_count_excluded": sum(
                    event.get("age_hours_at_decision") is not None
                    and float(event["age_hours_at_decision"]) < 0.0
                    for event in events
                ),
            },
        )
    intensity = 0.0
    for event in matching:
        age_hours = float(event["age_hours_at_decision"])
        recency = math.exp(-age_hours / 24.0)
        severity = float(event.get("severity_score", 0.0))
        source_quality = float(event.get("source_quality_score", 0.0))
        intensity += recency * (0.5 + severity) * (0.5 + source_quality)
    score = 1.0 - math.exp(-intensity / 2.0)
    latest = max(
        (
            _parse_aware_datetime(event.get("published_at"), "news event published_at")
            for event in matching
        ),
        default=created_at,
    )
    event_ids = sorted(str(event.get("event_id", "")) for event in matching)
    source = {
        "path": _relative_path(repository_root, data_path),
        "source_sha256": data_hash,
        "source_slice_sha256": _stable_hash(event_ids),
        "source_label": "source_provenanced_news_context",
        "observation_date": latest.date().isoformat(),
        "observed_at_utc": latest.isoformat(),
        "timestamp_granularity": "event_timestamp",
        "input_count": len(matching),
        "future_observation_count_excluded": sum(
            event.get("age_hours_at_decision") is not None
            and float(event["age_hours_at_decision"]) < 0.0
            for event in events
        ),
    }
    return _scored_component(
        "news_event_intensity",
        score,
        source,
        {
            "matching_event_count": len(matching),
            "independent_source_count": len(
                {str(event.get("source_id", "")) for event in matching}
            ),
            "weighted_event_intensity": round(intensity, 8),
            "alias_mapping_covered": alias_covered,
            "explicit_ticker_mention_count": len(exact_mentions),
            "window_hours": policy["news_window_hours"],
            "query_selection_bias_present": True,
            "headline_and_metadata_only": True,
        },
        [],
        "scored",
    )


def _load_options_components(
    paths: AttentionPaths,
    symbols: list[str],
    market_as_of_date: date,
    decision_time: datetime,
) -> tuple[
    dict[str, dict[str, Any]], dict[str, Any], list[dict[str, str]]
]:
    snapshot = resolve_option_snapshot(
        paths["repository_root"],
        paths["options_chain_root"],
        paths["options_manifest_path"],
        market_as_of_date,
        decision_time,
    )
    if snapshot["status"] != "current_hash_pinned_option_snapshot":
        reason = f"options_source_unavailable:{snapshot['blocker']}"
        return (
            {
                symbol: _unavailable_component("options_activity", reason)
                for symbol in symbols
            },
            {**snapshot, "path": ""},
            [{"source": "options", "reason": reason}],
        )
    snapshot_path = snapshot["path"]
    if snapshot_path is None:
        raise AttentionDataError("validated options snapshot lacks a path")
    try:
        chains = load_option_chain_snapshot(snapshot_path, market_as_of_date)
        aggregates = {
            symbol: _aggregate_option_activity(rows)
            for symbol, rows in chains.items()
        }
    except (OSError, ValueError, TypeError) as error:
        reason = f"options_source_unusable:{error}"
        return (
            {
                symbol: _unavailable_component("options_activity", reason)
                for symbol in symbols
            },
            {**snapshot, "path": str(snapshot_path), "reason": reason},
            [{"source": "options", "reason": reason}],
        )

    total_volumes = [float(item["total_volume"]) for item in aggregates.values()]
    turnover_ratios = [
        float(item["volume_to_open_interest_turnover"])
        for item in aggregates.values()
    ]
    active_shares = [
        float(item["active_contract_share"]) for item in aggregates.values()
    ]
    output: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        aggregate = aggregates.get(symbol)
        if aggregate is None:
            output[symbol] = _unavailable_component(
                "options_activity", f"current_option_chain_missing_symbol:{symbol}"
            )
            continue
        volume_rank = _percentile_rank(
            float(aggregate["total_volume"]), total_volumes
        )
        turnover_rank = _percentile_rank(
            float(aggregate["volume_to_open_interest_turnover"]), turnover_ratios
        )
        active_rank = _percentile_rank(
            float(aggregate["active_contract_share"]), active_shares
        )
        score = 0.45 * volume_rank + 0.35 * turnover_rank + 0.20 * active_rank
        chain_path = snapshot_path / f"{symbol}_chain.csv"
        source = {
            "path": _relative_path(paths["repository_root"], chain_path),
            "source_sha256": file_sha256(chain_path),
            "source_slice_sha256": file_sha256(chain_path),
            "source_label": "operator_staged_option_chain_snapshot",
            "observation_date": market_as_of_date.isoformat(),
            "observed_at_utc": snapshot["manifest_created_at"],
            "timestamp_granularity": "market_session_snapshot",
            "input_count": int(aggregate["contract_count"]),
            "future_observation_count_excluded": 0,
        }
        output[symbol] = _scored_component(
            "options_activity",
            score,
            source,
            {
                **aggregate,
                "total_volume_percentile": round(volume_rank, 8),
                "volume_to_open_interest_percentile": round(turnover_rank, 8),
                "active_contract_share_percentile": round(active_rank, 8),
                "cross_section_symbol_count": len(aggregates),
                "combined_snapshot_sha256": snapshot["combined_chain_sha256"],
                "not_live_data": True,
            },
            [
                "quote_timestamp_utc_unavailable",
                "underlying_quote_timestamp_utc_unavailable",
            ],
            "scored_session_snapshot",
        )
    provenance = {
        **snapshot,
        "path": _relative_path(paths["repository_root"], snapshot_path),
        "status": "validated_session_snapshot",
        "quote_timestamp_utc_available": False,
        "underlying_quote_timestamp_utc_available": False,
        "directional_use": False,
        "attention_only": True,
    }
    return output, provenance, []


def _aggregate_option_activity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("option activity aggregation requires nonempty rows")
    volumes = [int(row["volume"]) for row in rows]
    open_interests = [int(row["open_interest"]) for row in rows]
    if any(value < 0 for value in [*volumes, *open_interests]):
        raise ValueError("option activity contains negative volume or open interest")
    total_volume = sum(volumes)
    total_open_interest = sum(open_interests)
    denominator = total_volume + total_open_interest
    return {
        "contract_count": len(rows),
        "active_contract_count": sum(value > 0 for value in volumes),
        "total_volume": total_volume,
        "total_open_interest": total_open_interest,
        "volume_to_open_interest_turnover": round(
            total_volume / denominator if denominator > 0 else 0.0, 8
        ),
        "active_contract_share": round(
            sum(value > 0 for value in volumes) / len(rows), 8
        ),
    }


def _combine_symbol_components(
    symbol: str,
    history_components: dict[str, dict[str, Any]],
    news_component: dict[str, Any],
    options_component: dict[str, Any],
    market_as_of_date: date,
    policy: AttentionPolicy,
) -> dict[str, Any]:
    components = {
        **history_components,
        "news_event_intensity": news_component,
        "options_activity": options_component,
    }
    weights = policy["component_weights"]
    mandatory_available = all(
        components[name]["score"] is not None
        for name in ("market_activity", "price_volatility_discontinuity")
    )
    available_names = [
        name for name, component in components.items() if component["score"] is not None
    ]
    available_weight = sum(weights[name] for name in available_names)
    attention_score = None
    available_component_score = None
    completeness_ratio = available_weight / sum(weights.values())
    if mandatory_available and available_weight > 0.0:
        available_component_score = sum(
            weights[name] * float(components[name]["score"])
            for name in available_names
        ) / available_weight
        attention_score = 0.5 + completeness_ratio * (
            available_component_score - 0.5
        )
    missing_components = sorted(
        name for name, component in components.items() if component["score"] is None
    )
    missingness = {
        name: list(component["missing_reasons"])
        for name, component in components.items()
        if component["missing_reasons"]
    }
    all_clean = all(
        component["status"] == "scored" and not component["missing_reasons"]
        for component in components.values()
    )
    status = (
        "abstained"
        if attention_score is None
        else "scored"
        if all_clean
        else "partial"
    )
    observed_times = [
        str(component["observed_at_utc"])
        for component in components.values()
        if component["score"] is not None and component["observed_at_utc"]
    ]
    record: dict[str, Any] = {
        "symbol": symbol,
        "status": status,
        "attention_score": (
            round(float(attention_score), 8) if attention_score is not None else None
        ),
        "available_component_score": (
            round(float(available_component_score), 8)
            if available_component_score is not None
            else None
        ),
        "missingness_neutral_prior": 0.5,
        "component_scores": components,
        "available_weight": round(available_weight, 8),
        "total_weight": round(sum(weights.values()), 8),
        "completeness_ratio": round(completeness_ratio, 8),
        "missing_components": missing_components,
        "component_missingness": missingness,
        "latest_evidence_at_utc": max(observed_times, default=""),
        "latest_market_evidence_date": market_as_of_date.isoformat(),
        "market_evidence_timestamp_available": False,
        "freshness_basis": "latest_market_evidence_date_for_daily_market_components",
        "freshness_status": (
            "exact_market_frontier_with_optional_source_gaps"
            if mandatory_available and missing_components
            else "exact_market_frontier"
            if mandatory_available
            else "blocked_missing_exact_market_frontier"
        ),
        "future_observation_consumed": False,
        "research_only": True,
        "live_execution_allowed": False,
        "research_priority_only": True,
        "directional_signal_allowed": False,
        "directional_bias": None,
        "provenance_sha256": "",
    }
    record["provenance_sha256"] = _stable_hash(record)
    return record


def _scored_component(
    name: str,
    score: float,
    source: dict[str, Any],
    raw_metrics: dict[str, Any],
    missing_reasons: list[str],
    status: str,
) -> dict[str, Any]:
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError(f"attention component score is invalid: name={name}, score={score}")
    return {
        "component": name,
        "status": status,
        "score": round(score, 8),
        "raw_metrics": raw_metrics,
        "observation_date": source["observation_date"],
        "observed_at_utc": source["observed_at_utc"],
        "timestamp_granularity": source["timestamp_granularity"],
        "source_path": source["path"],
        "source_sha256": source["source_sha256"],
        "source_slice_sha256": source["source_slice_sha256"],
        "source_label": source["source_label"],
        "input_count": source["input_count"],
        "future_observation_count_excluded": source[
            "future_observation_count_excluded"
        ],
        "missing_reasons": missing_reasons,
    }


def _unavailable_component(
    name: str, reason: str, source: dict[str, Any] | None = None
) -> dict[str, Any]:
    source_record = source or {
        "path": "",
        "source_sha256": "",
        "source_slice_sha256": "",
        "source_label": "",
        "observation_date": "",
        "observed_at_utc": "",
        "timestamp_granularity": "unavailable",
        "input_count": 0,
        "future_observation_count_excluded": 0,
    }
    return {
        "component": name,
        "status": "abstained",
        "score": None,
        "raw_metrics": {},
        "observation_date": source_record["observation_date"],
        "observed_at_utc": source_record["observed_at_utc"],
        "timestamp_granularity": source_record["timestamp_granularity"],
        "source_path": source_record["path"],
        "source_sha256": source_record["source_sha256"],
        "source_slice_sha256": source_record["source_slice_sha256"],
        "source_label": source_record["source_label"],
        "input_count": source_record["input_count"],
        "future_observation_count_excluded": source_record[
            "future_observation_count_excluded"
        ],
        "missing_reasons": [reason],
    }


def _historical_relative_ratios(
    values: list[float], window: int, excluded_final_index: int
) -> list[float]:
    ratios: list[float] = []
    for index in range(window, excluded_final_index):
        ratio = _relative_ratio(values[index], values[index - window : index])
        if ratio is not None:
            ratios.append(ratio)
    return ratios


def _relative_ratio(value: float, baseline: list[float]) -> float | None:
    valid = [item for item in baseline if math.isfinite(item) and item >= 0.0]
    if not valid:
        return None
    center = statistics.median(valid)
    if center <= 0.0:
        return None
    return value / center


def _percentile_rank(value: float, population: list[float]) -> float:
    valid = sorted(item for item in population if math.isfinite(item))
    if not valid:
        raise ValueError("percentile rank requires a nonempty finite population")
    below = sum(item < value for item in valid)
    equal = sum(item == value for item in valid)
    return (below + 0.5 * equal) / len(valid)


def _event_explicitly_mentions_symbol(event: dict[str, Any], symbol: str) -> bool:
    if len(symbol) < 2:
        return False
    text = f"{event.get('title', '')} {event.get('summary', '')}"
    pattern = re.compile(
        rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])"
    )
    return pattern.search(text) is not None


def _parse_aware_datetime(value: Any, field: str) -> datetime:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} is invalid: value={raw!r}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware: value={raw!r}")
    return parsed.astimezone(timezone.utc)


def _history_bar_payload(bar: HistoryBar) -> dict[str, Any]:
    return {
        "date": bar.date,
        "symbol": bar.symbol,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "adjusted_close": bar.adjusted_close,
        "volume": bar.volume,
        "dividend": bar.dividend,
        "split_factor": bar.split_factor,
        "source": bar.source,
    }


def _relative_path(repository_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
