"""Option ROI discovery: mine both tails of realized option outcomes.

The lane treats the largest winners and largest losers as equally important
research cohorts. Winners suggest mechanisms worth attempting to reproduce;
losers are failure evidence used to identify ruinous entry conditions and to
challenge apparently successful mechanisms.

This is the options-native front end to the reverse -> forward engineering loop
(``reverse.infer_reverse_hypotheses`` -> ``forward.generate_forward_candidates``).

Pipeline
--------
1. Load two or more dated option-chain snapshots.
2. For every contract present in an early *entry* snapshot and a later *exit*
   snapshot, compute forward ROI = ``exit_mid / entry_mid - 1``.
3. Label the positive top-quantile ROI contracts as winners and the negative
   bottom-quantile contracts as losers, retaining the conditions observable at
   entry (moneyness, DTE, IV, spread, liquidity, option type).
4. Emit ``ReverseCase`` records and run them through the shared reverse-engine,
   which reports feature->winner associations only if they transfer across
   symbols and sessions.
5. Turn surviving associations into ``EXPERIMENTAL`` forward candidates plus an
   evaluation manifest.

Honesty contract (enforced, not decorative)
-------------------------------------------
Identifying what already won is **not** evidence it repeats — it is the single
most seductive overfitting trap in options research. Nothing here claims profit
or edge. Winners become *hypotheses*; hypotheses become *candidates*; candidates
are ``paper_only`` / ``live_blocked`` / ``positive_promotion_allowed=False`` and
must clear the full evaluation manifest (leakage, circular-shift null, random
entry, PBO, deflated Sharpe, held-out era, cross-symbol transfer, forward paper
settlement) before any of it is allowed to mean anything. No order-construction
capability exists in this module.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .forward import (
    build_evaluation_manifest,
    build_quality_diversity_archive,
    generate_forward_candidates,
)
from .reverse import infer_reverse_hypotheses
from .schema import ReverseCase

# Entry-liquidity floors: a "winner" computed off an untradeable quote is noise,
# not a discovery. These keep divide-by-tiny ROI blowups and phantom fills out.
MIN_ENTRY_MID = 0.05
MAX_ENTRY_RELATIVE_SPREAD = 0.60
_ROI_CLIP = 50.0  # cap absurd ROI from stale/one-sided quotes at +5000%


def _f(row: Mapping[str, str], key: str) -> float:
    raw = row.get(key, "")
    if raw is None or str(raw).strip() == "":
        return math.nan
    try:
        return float(raw)
    except (TypeError, ValueError):
        return math.nan


def load_chain_snapshots(chains_root: Path) -> dict[str, list[dict[str, str]]]:
    """Load ``<root>/<YYYY-MM-DD>/<SYMBOL>_chain.csv`` snapshots.

    Returns a mapping of snapshot_date -> contract rows. Only well-formed rows
    are kept; a malformed file never aborts the sweep.
    """
    snapshots: dict[str, list[dict[str, str]]] = {}
    root = Path(chains_root)
    if not root.is_dir():
        return snapshots
    for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        rows: list[dict[str, str]] = []
        for csv_path in sorted(date_dir.glob("*_chain.csv")):
            try:
                text = csv_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            reader = csv.DictReader(text.splitlines())
            for row in reader:
                if row.get("snapshot_date") and row.get("symbol"):
                    rows.append(row)
        if rows:
            snapshots[date_dir.name] = rows
    return snapshots


def _contract_key(row: Mapping[str, str]) -> str:
    # Normalize strike so "100" and "100.0" from different snapshots match the
    # same contract; without this, ROI silently fails to compute across sessions.
    symbol = str(row.get("symbol", "")).strip().upper()
    expiry = str(row.get("expiry", "")).strip()
    option_type = str(row.get("option_type", "")).strip().lower()
    raw_strike = str(row.get("strike", "")).strip()
    try:
        strike = format(float(raw_strike), ".4f")
    except (TypeError, ValueError):
        strike = raw_strike
    return f"{symbol}|{expiry}|{option_type}|{strike}"


def _entry_features(row: Mapping[str, str], entry_mid: float) -> dict[str, float] | None:
    """Leak-free conditions observable at entry. None if any is non-finite."""
    spot = _f(row, "underlying_spot")
    strike = _f(row, "strike")
    bid = _f(row, "bid")
    ask = _f(row, "ask")
    iv = _f(row, "implied_vol")
    dte = _f(row, "dte_calendar")
    volume = _f(row, "volume")
    open_interest = _f(row, "open_interest")
    if not (spot > 0.0 and strike > 0.0 and ask >= bid >= 0.0 and entry_mid > 0.0):
        return None
    relative_spread = (ask - bid) / entry_mid
    features = {
        "log_moneyness": math.log(strike / spot),
        "dte_calendar": dte,
        "implied_vol": iv,
        "relative_spread": relative_spread,
        "log_volume": math.log1p(max(volume, 0.0)),
        "log_open_interest": math.log1p(max(open_interest, 0.0)),
        "is_call": 1.0 if str(row.get("option_type", "")).strip().lower() == "call" else 0.0,
        "entry_mid": entry_mid,
    }
    if any(not math.isfinite(value) for value in features.values()):
        return None
    return features


def compute_contract_roi(
    entry_rows: Sequence[Mapping[str, str]],
    exit_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Match contracts across two snapshots and compute forward ROI at entry.

    ROI = exit_mid / entry_mid - 1, using only contracts whose entry quote is
    liquid enough to be real (mid >= floor, relative spread <= cap).
    """
    exit_by_key: dict[str, Mapping[str, str]] = {}
    for row in exit_rows:
        exit_by_key.setdefault(_contract_key(row), row)

    outcomes: list[dict[str, Any]] = []
    for entry in entry_rows:
        entry_mid = _f(entry, "mid")
        if not (entry_mid >= MIN_ENTRY_MID):
            continue
        features = _entry_features(entry, entry_mid)
        if features is None or features["relative_spread"] > MAX_ENTRY_RELATIVE_SPREAD:
            continue
        exit_row = exit_by_key.get(_contract_key(entry))
        if exit_row is None:
            continue
        exit_mid = _f(exit_row, "mid")
        if not (exit_mid >= 0.0):
            continue
        roi = min(exit_mid / entry_mid - 1.0, _ROI_CLIP)
        entry_spot = _f(entry, "underlying_spot")
        exit_spot = _f(exit_row, "underlying_spot")
        underlying_return = (
            exit_spot / entry_spot - 1.0
            if entry_spot > 0.0 and exit_spot > 0.0
            else 0.0
        )
        outcomes.append(
            {
                "symbol": str(entry.get("symbol", "")).strip(),
                "entry_date": str(entry.get("snapshot_date", "")).strip(),
                "exit_date": str(exit_row.get("snapshot_date", "")).strip(),
                "contract_key": _contract_key(entry),
                "roi": roi,
                "underlying_return": underlying_return,
                "is_call": features["is_call"],
                "features": features,
            }
        )
    return outcomes


def _regime(features: Mapping[str, float]) -> str:
    iv = features["implied_vol"]
    if iv >= 0.80:
        return "iv_high"
    if iv >= 0.40:
        return "iv_mid"
    return "iv_low"


def build_option_reverse_cases(
    outcomes: Sequence[Mapping[str, Any]],
    winner_quantile: float,
) -> tuple[ReverseCase, ...]:
    """Label top-quantile-ROI contracts as winners and emit ReverseCase records.

    ``era`` is the entry session date (cross-session transfer is the relevant
    robustness axis for short-horizon option behavior); ``contested_truth`` marks
    winners whose gain ran *against* the underlying's realized drift (the option
    was repriced by vol/gamma, not carried by direction) — the discipline that
    only credits a signal when it disagreed with the tape.
    """
    if not 0.0 < winner_quantile < 1.0:
        raise ValueError(f"winner_quantile must be in (0,1): winner_quantile={winner_quantile}")
    if not outcomes:
        return ()
    rois = sorted(float(o["roi"]) for o in outcomes)
    index = min(len(rois) - 1, int(math.ceil(winner_quantile * len(rois))) - 1)
    threshold = rois[max(index, 0)]

    cases: list[ReverseCase] = []
    for outcome in outcomes:
        roi = float(outcome["roi"])
        is_winner = roi >= threshold and roi > 0.0
        is_call = float(outcome["is_call"]) >= 0.5
        underlying_return = float(outcome["underlying_return"])
        # Winner whose option-direction bet opposed (or ignored) the drift.
        contested = bool(
            is_winner
            and ((is_call and underlying_return <= 0.0) or (not is_call and underlying_return >= 0.0))
        )
        body = {
            "symbol": str(outcome["symbol"]),
            "era": str(outcome["entry_date"]),
            "regime": _regime(outcome["features"]),
            "feature_values": {k: float(v) for k, v in outcome["features"].items()},
            "dominant_correct": 1.0 if is_winner else 0.0,
            "contested_truth": contested,
            "evidence_ids": (f"option-chain-snapshot:{outcome['entry_date']}",),
            "point_in_time_proof_id": f"option-roi-entry:{canonical_hash(dict(outcome['features']))[:20]}",
            "prediction_id": f"option-contract:{canonical_hash({'k': outcome['contract_key'], 'd': outcome['entry_date']})[:24]}",
        }
        case_id = f"option-reverse-case:{canonical_hash(body)[:24]}"
        cases.append({"case_id": case_id, **body})  # type: ignore[arg-type]
    return tuple(sorted(cases, key=lambda record: record["case_id"]))


def _tail_contract_record(outcome: Mapping[str, Any], tail: str) -> dict[str, Any]:
    if tail not in {"winner", "loser"}:
        raise ValueError(f"tail must be winner or loser: tail={tail}")
    roi = float(outcome["roi"])
    return {
        "symbol": str(outcome["symbol"]),
        "contract_key": str(outcome["contract_key"]),
        "entry_date": str(outcome["entry_date"]),
        "exit_date": str(outcome["exit_date"]),
        "tail": tail,
        "roi": round(roi, 6),
        "roi_pct": round(roi * 100.0, 4),
        "underlying_return_pct": round(float(outcome["underlying_return"]) * 100.0, 4),
        "entry_conditions": {
            key: round(float(value), 8)
            for key, value in sorted(dict(outcome["features"]).items())
        },
        "research_role": (
            "mechanism_hypothesis_only"
            if tail == "winner"
            else "failure_memory_and_avoidance_hypothesis"
        ),
        "is_trade_signal": False,
    }


def _loser_threshold(outcomes: Sequence[Mapping[str, Any]], winner_quantile: float) -> float:
    rois = sorted(float(outcome["roi"]) for outcome in outcomes)
    loser_quantile = 1.0 - winner_quantile
    index = min(len(rois) - 1, max(0, int(math.ceil(loser_quantile * len(rois))) - 1))
    return rois[index]


def discover_option_roi_strategies(
    chains_root: Path,
    *,
    winner_quantile: float = 0.80,
    minimum_support: int = 8,
    minimum_absolute_effect: float = 0.10,
    maximum_hypotheses: int = 12,
    forward_candidate_budget: int = 8,
    top_winner_report: int = 25,
    top_loser_report: int = 25,
) -> dict[str, Any]:
    """Full option-ROI discovery -> reverse -> forward report.

    Deterministic and network-free. Returns an honest, promotion-ineligible
    report. Requires at least two dated snapshots.
    """
    snapshots = load_chain_snapshots(Path(chains_root))
    dates = sorted(snapshots)
    if len(dates) < 2:
        return {
            "artifact_type": "option_roi_discovery_report",
            "option_roi_discovery_version": "dopey-option-roi-discovery-v2",
            "status": "insufficient_snapshots_need_two_sessions",
            "snapshot_dates": tuple(dates),
            "winner_count": 0,
            "loser_count": 0,
            "top_winners": (),
            "top_losers": (),
            "hypotheses": (),
            "forward_candidates": (),
            "profit_or_edge_claimed": False,
            "paper_only": True,
            "live_blocked": True,
            "order_construction_allowed": False,
        }

    # Chain every adjacent (entry, exit) session pair so each snapshot's winners
    # are measured against the next available session.
    outcomes: list[dict[str, Any]] = []
    for entry_date, exit_date in zip(dates, dates[1:]):
        outcomes.extend(compute_contract_roi(snapshots[entry_date], snapshots[exit_date]))

    ranked = sorted(outcomes, key=lambda o: float(o["roi"]), reverse=True)
    top_winners = tuple(
        _tail_contract_record(outcome, "winner")
        for outcome in (record for record in ranked if float(record["roi"]) > 0.0)
    )[: max(top_winner_report, 0)]
    top_losers = tuple(
        _tail_contract_record(outcome, "loser")
        for outcome in (record for record in reversed(ranked) if float(record["roi"]) < 0.0)
    )[: max(top_loser_report, 0)]

    loser_threshold = _loser_threshold(outcomes, winner_quantile) if outcomes else 0.0
    loser_count = sum(
        1
        for outcome in outcomes
        if float(outcome["roi"]) <= loser_threshold and float(outcome["roi"]) < 0.0
    )

    cases = build_option_reverse_cases(outcomes, winner_quantile)
    winner_count = sum(1 for case in cases if case["dominant_correct"] >= 0.5)

    reverse_report: dict[str, Any] = {
        "reverse_status": "insufficient_settled_observations",
        "hypotheses": [],
    }
    forward_candidates: tuple[dict[str, Any], ...] = ()
    quality_diversity: dict[str, Any] = {}
    evaluation_manifests: tuple[dict[str, Any], ...] = ()

    if len(cases) >= minimum_support:
        reverse_report = infer_reverse_hypotheses(
            cases,
            minimum_support=minimum_support,
            minimum_absolute_effect=minimum_absolute_effect,
            maximum_hypotheses=maximum_hypotheses,
        )
        transferable = [
            h
            for h in reverse_report["hypotheses"]
            if h["hypothesis_status"] == "association_only_replay_required"
        ]
        if transferable:
            forward_candidates = generate_forward_candidates(forward_candidate_budget, transferable)
            quality_diversity = build_quality_diversity_archive(forward_candidates)
            evaluation_manifests = tuple(build_evaluation_manifest(c) for c in forward_candidates)

    return {
        "artifact_type": "option_roi_discovery_report",
        "option_roi_discovery_version": "dopey-option-roi-discovery-v2",
        "status": "complete",
        "snapshot_dates": tuple(dates),
        "session_pairs": tuple(f"{a}->{b}" for a, b in zip(dates, dates[1:])),
        "contract_outcome_count": len(outcomes),
        "reverse_case_count": len(cases),
        "winner_quantile": winner_quantile,
        "winner_count": winner_count,
        "loser_quantile": round(1.0 - winner_quantile, 6),
        "loser_threshold": round(loser_threshold, 6),
        "loser_count": loser_count,
        "top_winners": top_winners,
        "top_losers": top_losers,
        "reverse_status": reverse_report["reverse_status"],
        "hypotheses": tuple(reverse_report["hypotheses"]),
        "forward_candidate_count": len(forward_candidates),
        "forward_candidates": forward_candidates,
        "quality_diversity_archive": quality_diversity,
        "evaluation_manifests": evaluation_manifests,
        # Honesty invariants — reverse-engineered winners are hypotheses, not edge.
        "reverse_engineered_winners_are_not_evidence": True,
        "reverse_engineered_losers_are_failure_evidence_not_trade_signals": True,
        "loser_cohort_is_counterevidence": True,
        "profit_or_edge_claimed": False,
        "candidates_require_full_evaluation_manifest_before_meaning": True,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
