"""Playbook settlement: every detection is graded at its horizon, traded or not.

This closes the experience loop the playbook needs to become more than a map:
each detection is appended to an immutable ledger, settled against the real
OHLCV spine once its horizon matures, and accrued into per-setup / per-family
hit rates with the contested-truth discipline — trust is earned ONLY where a
detection disagreed with the prevailing drift, because agreeing with the tape
and being right proves nothing.

Discipline (mirrors the phantom signal-calibration lane):
- Append-only ledgers; first-recorded outcomes are immutable.
- ``guard`` / ``either`` detections are recorded but not direction-graded.
- Families below the effective contested-settlement floor report
  ``unrated_insufficient_effective_contested_settlements`` — observations that
  merely agree with prevailing drift or overlap cannot make a family rated.
- The output is ADVISORY research telemetry. The readiness gate never reads
  it; it cannot promote, size, or order anything.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from .playbook_scanner import (
    BIG_MOVER_SELECTION_POLICY_VERSION,
    PLAYBOOK_SCAN_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "playbook"
DETECTION_LEDGER_PATH = PLAYBOOK_ARTIFACT_DIR / "playbook_detection_ledger.jsonl"
SETTLEMENT_LEDGER_PATH = PLAYBOOK_ARTIFACT_DIR / "playbook_settlement_ledger.jsonl"
TRUST_REPORT_PATH = PLAYBOOK_ARTIFACT_DIR / "playbook_family_trust.json"

RATED_FLOOR = 30  # independent contested clusters before a rate is quotable
DRIFT_WINDOW = 20
PLAYBOOK_TRUST_VERSION = "dopey-playbook-trust-v4"
LEGACY_DIRECTION_ASSUMPTION_SETUPS = frozenset(
    {
        "gamma_squeeze_flow",
        "short_squeeze_mechanics",
    }
)
LEGACY_DUAL_FRAMING_SETUPS = frozenset(
    {
        "big_mover_fade",
        "big_mover_momentum",
    }
)


def uses_legacy_direction_assumption(record: Mapping[str, Any]) -> bool:
    """Return whether a settlement came from a quarantined direction policy."""
    return (
        str(record.get("setup_id", ""))
        in LEGACY_DIRECTION_ASSUMPTION_SETUPS
    )


def uses_legacy_dual_framing(record: Mapping[str, Any]) -> bool:
    """Return whether a big-mover row predates independent setup selection."""
    setup_id = str(record.get("setup_id", ""))
    if setup_id not in LEGACY_DUAL_FRAMING_SETUPS:
        return False
    return not (
        record.get("independently_selected_setup") is True
        and record.get("framing_selection_policy_version")
        == BIG_MOVER_SELECTION_POLICY_VERSION
        and record.get("source_playbook_scan_version")
        == PLAYBOOK_SCAN_VERSION
    )


def is_rating_eligible_settlement(record: Mapping[str, Any]) -> bool:
    """Return whether a raw settlement may enter rated evidence."""
    return (
        bool(record.get("graded"))
        and not uses_legacy_direction_assumption(record)
        and not uses_legacy_dual_framing(record)
    )


def _settlement_window(
    record: Mapping[str, Any],
) -> tuple[str, date, date, bool] | None:
    symbol = str(record.get("symbol", "")).upper().strip()
    as_of_value = record.get("as_of_date")
    settle_value = record.get("settle_date")
    hit = record.get("hit")
    if (
        not symbol
        or not isinstance(as_of_value, str)
        or not isinstance(settle_value, str)
        or not isinstance(hit, bool)
    ):
        return None
    try:
        window_start = date.fromisoformat(as_of_value)
        window_end = date.fromisoformat(settle_value)
    except ValueError:
        return None
    if window_end < window_start:
        return None
    return symbol, window_start, window_end, hit


def _clustered_contested_stats(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    windows_by_symbol: dict[str, list[tuple[date, date, bool]]] = {}
    excluded = 0
    for record in records:
        window = _settlement_window(record)
        if window is None:
            excluded += 1
            continue
        symbol, window_start, window_end, hit = window
        windows_by_symbol.setdefault(symbol, []).append(
            (window_start, window_end, hit)
        )

    cluster_hit_rates: list[float] = []
    clusters_by_symbol: dict[str, int] = {}
    raw_by_symbol: dict[str, int] = {}
    for symbol, windows in sorted(windows_by_symbol.items()):
        ordered = sorted(windows, key=lambda value: (value[0], value[1]))
        raw_by_symbol[symbol] = len(ordered)
        cluster_count = 0
        current_end: date | None = None
        current_hits: list[bool] = []
        for window_start, window_end, hit in ordered:
            if current_end is not None and window_start <= current_end:
                current_end = max(current_end, window_end)
                current_hits.append(hit)
                continue
            if current_hits:
                cluster_hit_rates.append(
                    sum(current_hits) / len(current_hits)
                )
            cluster_count += 1
            current_end = window_end
            current_hits = [hit]
        if current_hits:
            cluster_hit_rates.append(sum(current_hits) / len(current_hits))
        clusters_by_symbol[symbol] = cluster_count

    return {
        "effective_contested_settled": len(cluster_hit_rates),
        "effective_contested_hit_rate": (
            round(sum(cluster_hit_rates) / len(cluster_hit_rates), 4)
            if cluster_hit_rates
            else None
        ),
        "effective_contested_clusters_by_symbol": clusters_by_symbol,
        "raw_contested_settled_by_symbol": raw_by_symbol,
        "contested_records_excluded_from_effective_count": excluded,
        "effective_count_method": (
            "connected_components_of_overlapping_as_of_to_settle_windows_"
            "within_symbol"
        ),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "invalid playbook JSONL evidence: "
                    f"path={path}, line_number={line_number}, error={error}"
                ) from error
            if not isinstance(value, dict):
                raise TypeError(
                    "playbook JSONL row must be an object: "
                    f"path={path}, line_number={line_number}, "
                    f"actual={type(value).__name__}"
                )
            records.append(value)
    return records


def _append_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record_detections(
    scan_report: Mapping[str, Any],
    *,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Append NEW detections to the immutable ledger (idempotent by id)."""
    path = ledger_path or DETECTION_LEDGER_PATH
    existing_ids = {str(r.get("detection_id", "")) for r in _read_jsonl(path)}
    fresh = [
        dict(d) for d in scan_report.get("detections", ())
        if str(d.get("detection_id", "")) not in existing_ids
    ]
    _append_jsonl(path, fresh)
    return {
        "artifact_type": "playbook_detection_recording",
        "appended": len(fresh),
        "already_recorded": len(scan_report.get("detections", ())) - len(fresh),
        "ledger_path": str(path),
        "paper_only": True,
        "live_blocked": True,
    }


def _horizon_for(detection: Mapping[str, Any]) -> int:
    horizons = detection.get("horizon_days") or (5,)
    try:
        return int(sorted(int(h) for h in horizons)[0])
    except (TypeError, ValueError):
        return 5


def _settle_one(
    detection: Mapping[str, Any],
    closes: Sequence[float],
    dates: Sequence[str],
) -> dict[str, Any] | None:
    """Grade a detection at its shortest horizon. None if not yet mature."""
    as_of = str(detection.get("as_of_date", ""))
    if as_of not in dates:
        return None
    index = dates.index(as_of)
    horizon = _horizon_for(detection)
    exit_index = index + horizon
    if exit_index >= len(closes):
        return None  # not mature yet — settle on a later run
    entry, exit_ = closes[index], closes[exit_index]
    if entry <= 0.0:
        return None
    forward_return = exit_ / entry - 1.0

    direction = str(detection.get("direction", ""))
    if direction not in ("long", "short"):
        graded, hit = False, None
    else:
        graded = True
        hit = forward_return > 0.0 if direction == "long" else forward_return < 0.0

    # Contested-truth: did the detection disagree with the prior drift?
    drift_start = max(0, index - DRIFT_WINDOW)
    drift = closes[index] / closes[drift_start] - 1.0 if closes[drift_start] > 0.0 else 0.0
    contested = graded and (
        (direction == "long" and drift <= 0.0) or (direction == "short" and drift >= 0.0)
    )
    eligibility_record = {
        **detection,
        "graded": graded,
    }

    return {
        "artifact_type": "playbook_settlement",
        "detection_id": detection.get("detection_id"),
        "setup_id": detection.get("setup_id"),
        "family": detection.get("family"),
        "symbol": detection.get("symbol"),
        "as_of_date": as_of,
        "settle_date": dates[exit_index],
        "horizon_days": horizon,
        "direction": direction,
        "forward_return": round(forward_return, 6),
        "graded": graded,
        "hit": hit,
        "contested_truth": contested,
        "prior_drift": round(drift, 6),
        "source_playbook_scan_version": detection.get(
            "source_playbook_scan_version"
        ),
        "independently_selected_setup": (
            detection.get("independently_selected_setup") is True
        ),
        "framing_selection_policy_version": detection.get(
            "framing_selection_policy_version"
        ),
        "legacy_direction_assumption": uses_legacy_direction_assumption(
            detection
        ),
        "legacy_dual_framing": uses_legacy_dual_framing(detection),
        "rating_eligible": is_rating_eligible_settlement(
            eligibility_record
        ),
        "rating_policy_version": PLAYBOOK_TRUST_VERSION,
        "not_trade_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def settle_matured(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, float]]],
    *,
    ledger_path: Path | None = None,
    settlement_path: Path | None = None,
) -> dict[str, Any]:
    """Settle every matured, not-yet-settled detection against the spine."""
    dpath = ledger_path or DETECTION_LEDGER_PATH
    spath = settlement_path or SETTLEMENT_LEDGER_PATH
    detections = _read_jsonl(dpath)
    settled_ids = {str(r.get("detection_id", "")) for r in _read_jsonl(spath)}

    series: dict[str, tuple[list[float], list[str]]] = {}
    for symbol, bars in bars_by_symbol.items():
        series[symbol] = (
            [float(b["close"]) for b in bars],
            [str(b.get("date", "")) for b in bars],
        )

    new_settlements: list[dict[str, Any]] = []
    pending = 0
    for detection in detections:
        if str(detection.get("detection_id", "")) in settled_ids:
            continue
        symbol = str(detection.get("symbol", ""))
        if symbol not in series:
            pending += 1
            continue
        closes, dates = series[symbol]
        settlement = _settle_one(detection, closes, dates)
        if settlement is None:
            pending += 1
        else:
            new_settlements.append(settlement)

    _append_jsonl(spath, new_settlements)
    return {
        "artifact_type": "playbook_settlement_run",
        "newly_settled": len(new_settlements),
        "still_pending": pending,
        "total_settled": len(settled_ids) + len(new_settlements),
        "settlement_path": str(spath),
        "paper_only": True,
        "live_blocked": True,
    }


def family_trust_report(
    *,
    settlement_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Per-setup and per-family earned-trust telemetry. Advisory only."""
    spath = settlement_path or SETTLEMENT_LEDGER_PATH
    settlements = [r for r in _read_jsonl(spath) if r.get("graded")]

    def _bucket(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        eligible = [
            record for record in records
            if is_rating_eligible_settlement(record)
        ]
        raw_count = len(records)
        raw_contested = [
            record
            for record in records
            if record.get("contested_truth")
        ]
        raw_contested_hits = sum(
            1 for record in raw_contested if record.get("hit")
        )
        n = len(eligible)
        hits = sum(1 for record in eligible if record.get("hit"))
        contested = [
            record
            for record in eligible
            if record.get("contested_truth")
        ]
        contested_hits = sum(1 for r in contested if r.get("hit"))
        contested_count = len(contested)
        clustered = _clustered_contested_stats(contested)
        effective_contested_count = int(
            clustered["effective_contested_settled"]
        )
        rated = effective_contested_count >= RATED_FLOOR
        legacy_direction_count = sum(
            1 for record in records
            if uses_legacy_direction_assumption(record)
        )
        legacy_dual_framing_count = sum(
            1 for record in records
            if uses_legacy_dual_framing(record)
        )
        excluded_cluster_count = int(
            clustered[
                "contested_records_excluded_from_effective_count"
            ]
        )
        trust_state = (
            "rated"
            if rated
            else (
                "unrated_legacy_direction_assumption"
                if legacy_direction_count > 0 and n == 0
                else (
                    "unrated_legacy_dual_framing"
                    if legacy_dual_framing_count > 0 and n == 0
                    else (
                        "unrated_invalid_contested_cluster_keys"
                        if (
                            contested_count > 0
                            and excluded_cluster_count
                            == contested_count
                        )
                        else (
                            "unrated_insufficient_effective_"
                            "contested_settlements"
                        )
                    )
                )
            )
        )
        return {
            "settled": n,
            "hit_rate": round(hits / n, 4) if n else None,
            "contested_settled": contested_count,
            "eligible_contested_settled": contested_count,
            "raw_contested_settled": len(raw_contested),
            "contested_hit_rate": (
                round(contested_hits / contested_count, 4)
                if contested
                else None
            ),
            "raw_contested_hit_rate": (
                round(
                    raw_contested_hits / len(raw_contested),
                    4,
                )
                if raw_contested
                else None
            ),
            **clustered,
            "trust_state": trust_state,
            "rated_floor": RATED_FLOOR,
            "rating_observation_count": effective_contested_count,
            "rating_count_basis": (
                "effective_contested_symbol_overlapping_"
                "settlement_window_clusters"
            ),
            "raw_graded_settled": raw_count,
            "legacy_direction_assumption_settled": legacy_direction_count,
            "legacy_dual_framing_settled": legacy_dual_framing_count,
        }

    per_setup: dict[str, list[Mapping[str, Any]]] = {}
    per_family: dict[str, list[Mapping[str, Any]]] = {}
    for record in settlements:
        per_setup.setdefault(str(record.get("setup_id", "")), []).append(record)
        per_family.setdefault(str(record.get("family", "")), []).append(record)

    report = {
        "artifact_type": "playbook_family_trust_report",
        "playbook_trust_version": PLAYBOOK_TRUST_VERSION,
        "graded_settlements": len(settlements),
        "rating_eligible_graded_settlements": sum(
            1 for record in settlements
            if is_rating_eligible_settlement(record)
        ),
        "legacy_direction_assumption_setups": sorted(
            LEGACY_DIRECTION_ASSUMPTION_SETUPS
        ),
        "legacy_dual_framing_setups": sorted(
            LEGACY_DUAL_FRAMING_SETUPS
        ),
        "big_mover_selection_policy_version": (
            BIG_MOVER_SELECTION_POLICY_VERSION
        ),
        "rating_count_basis": (
            "effective_contested_symbol_overlapping_"
            "settlement_window_clusters"
        ),
        "per_family": {family: _bucket(recs) for family, recs in sorted(per_family.items())},
        "per_setup": {setup: _bucket(recs) for setup, recs in sorted(per_setup.items())},
        "advisory_only_never_a_gate_input": True,
        "contested_truth_is_the_trust_currency": True,
        "profit_or_edge_claimed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    rpath = report_path or TRUST_REPORT_PATH
    rpath.parent.mkdir(parents=True, exist_ok=True)
    rpath.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if not math.isfinite(float(len(settlements))):  # pragma: no cover - impossible
        raise AssertionError("settlement count must be finite")
    return report
