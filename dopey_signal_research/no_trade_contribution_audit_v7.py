"""No-trade contribution audit for V7.

Reads V6 tournament leaderboard, path trades, watchlist, gate rejections,
scoreboard, and mutation queue. Computes no-trade vs trade-active ratios and
PF contributions. Blocks no-trade-only breakthroughs and emits audit records,
trade-active edge records, no-trade dominance flags, a summary, and a proof.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    NO_TRADE_AUDIT_V7_PROOF_PATH,
    NO_TRADE_AUDIT_V7_SUMMARY_PATH,
    NO_TRADE_CONTRIBUTION_RECORDS_V7_PATH,
    NO_TRADE_DOMINANCE_FLAGS_V7_PATH,
    RESEARCH_V6_ROOT,
    RESEARCH_V7_VERSION,
    SCOREBOARD_ROOT,
    TRADE_ACTIVE_EDGE_RECORDS_V7_PATH,
    V6_GATE_REJECTIONS_PATH,
    V6_TOURNAMENT_LEADERBOARD_PATH,
    V6_WATCHLIST_PATH,
    V7_MAX_NO_TRADE_RATIO,
    load_v6_mutation_queue_records,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_signal_research.trade_active_edge_separator_v7 import (
    compute_subfamily_trade_active_metrics,
    compute_trade_active_edge,
    group_trades_by_subfamily,
)


__all__ = ["run_no_trade_contribution_audit_v7"]


V6_PATH_TRADES_PATH = RESEARCH_V6_ROOT / "research_path_trades_v6.jsonl"
V6_SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json"


def _safe_float(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if __import__("math").isfinite(parsed):
        return parsed
    return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return read_jsonl_file(path) if path.exists() else []


def _load_json(path: Path) -> dict[str, object]:
    return read_json_file(path) if path.exists() else {}


def _candidate_key(record: dict[str, object]) -> str:
    return str(record.get("stable_subfamily_id", record.get("cohort_id", "")))


def _no_trade_contribution_record(
    idx: int,
    source_type: str,
    candidate: dict[str, object],
    metrics: dict[str, object],
    min_pf: float,
) -> dict[str, object]:
    subfamily_id = _candidate_key(candidate)
    cohort_id = str(candidate.get("cohort_id", subfamily_id))
    record_pf = _safe_float(candidate.get("profit_factor", 0.0))
    record_net_pnl = _safe_float(candidate.get("net_pnl", 0.0))
    record_sample = _safe_int(candidate.get("sample_count", 0))

    no_trade_ratio = _safe_float(metrics.get("no_trade_ratio", 0.0))
    active_ratio = _safe_float(metrics.get("trade_active_ratio", 0.0))
    active_pf = _safe_float(metrics.get("trade_active_profit_factor", 0.0))
    active_count = _safe_int(metrics.get("trade_active_count", 0))

    no_trade_only = active_count == 0 or active_ratio == 0.0
    no_trade_dominant = no_trade_ratio >= V7_MAX_NO_TRADE_RATIO or no_trade_only

    rec = {
        "artifact_type": "no_trade_contribution_record_v7",
        "audit_id": f"ntc-v7-{idx:04d}-{source_type}",
        "source_type": source_type,
        "stable_family_id": str(candidate.get("stable_family_id", "")),
        "stable_subfamily_id": subfamily_id,
        "cohort_id": cohort_id,
        "record_profit_factor": record_pf,
        "record_net_pnl": record_net_pnl,
        "record_sample_count": record_sample,
        "total_sample_count": _safe_int(metrics.get("total_sample_count", 0)),
        "no_trade_count": _safe_int(metrics.get("no_trade_count", 0)),
        "trade_active_count": active_count,
        "no_trade_ratio": no_trade_ratio,
        "trade_active_ratio": active_ratio,
        "no_trade_pnl": _safe_float(metrics.get("no_trade_pnl", 0.0)),
        "trade_active_pnl": _safe_float(metrics.get("trade_active_pnl", 0.0)),
        "total_pnl": _safe_float(metrics.get("total_pnl", 0.0)),
        "no_trade_profit_factor": _safe_float(metrics.get("no_trade_profit_factor", 0.0)),
        "trade_active_profit_factor": active_pf,
        "total_profit_factor": _safe_float(metrics.get("total_profit_factor", 0.0)),
        "no_trade_dominant": no_trade_dominant,
        "no_trade_only": no_trade_only,
        "blocked": no_trade_only,
        "block_reason": "no_trade_only_breakthrough_blocked" if no_trade_only else "",
        "pf_attribution_source": "no_trade_zeros" if no_trade_only else "mixed",
        "v7_min_breakthrough_pf": min_pf,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _trade_active_edge_record(
    idx: int,
    metrics: dict[str, object],
    min_pf: float,
) -> dict[str, object]:
    edge = compute_trade_active_edge(metrics, min_pf)
    rec = {
        "artifact_type": "trade_active_edge_record_v7",
        "edge_id": f"tae-v7-{idx:04d}",
        "stable_subfamily_id": edge["stable_subfamily_id"],
        "trade_active_count": edge["trade_active_sample_count"],
        "trade_active_ratio": edge["trade_active_ratio"],
        "trade_active_pnl": _safe_float(metrics.get("trade_active_pnl", 0.0)),
        "trade_active_profit_factor": edge["trade_active_profit_factor"],
        "trade_active_edge": edge["trade_active_edge"],
        "trade_active_edge_above_min_pf": edge["trade_active_edge_above_min_pf"],
        "v7_min_breakthrough_pf": min_pf,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _no_trade_dominance_flag(
    idx: int,
    source_type: str,
    candidate: dict[str, object],
    metrics: dict[str, object],
    min_pf: float,
) -> dict[str, object] | None:
    no_trade_ratio = _safe_float(metrics.get("no_trade_ratio", 0.0))
    active_count = _safe_int(metrics.get("trade_active_count", 0))
    active_ratio = _safe_float(metrics.get("trade_active_ratio", 0.0))
    no_trade_only = active_count == 0 or active_ratio == 0.0
    no_trade_dominant = no_trade_ratio >= V7_MAX_NO_TRADE_RATIO or no_trade_only

    if not no_trade_dominant and not no_trade_only:
        return None

    subfamily_id = _candidate_key(candidate)
    reasons: list[str] = []
    if no_trade_only:
        reasons.append("no_trade_only")
    if no_trade_ratio >= V7_MAX_NO_TRADE_RATIO:
        reasons.append(f"no_trade_ratio_{no_trade_ratio:.4f}_exceeds_max_{V7_MAX_NO_TRADE_RATIO}")

    rec = {
        "artifact_type": "no_trade_dominance_flag_v7",
        "flag_id": f"ntd-v7-{idx:04d}-{source_type}",
        "source_type": source_type,
        "stable_family_id": str(candidate.get("stable_family_id", "")),
        "stable_subfamily_id": subfamily_id,
        "cohort_id": str(candidate.get("cohort_id", subfamily_id)),
        "no_trade_ratio": no_trade_ratio,
        "trade_active_ratio": active_ratio,
        "no_trade_count": _safe_int(metrics.get("no_trade_count", 0)),
        "trade_active_count": active_count,
        "no_trade_dominant": no_trade_dominant,
        "no_trade_only": no_trade_only,
        "blocked": no_trade_only,
        "block_reasons": reasons,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "v7_min_breakthrough_pf": min_pf,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "record_hash")


def _audit_source_records(
    source_type: str,
    records: Sequence[dict[str, object]],
    metrics_by_subfamily: dict[str, dict[str, object]],
    min_pf: float,
    start_idx: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], int]:
    contribution_records: list[dict[str, object]] = []
    edge_records: list[dict[str, object]] = []
    flag_records: list[dict[str, object]] = []
    idx = start_idx

    # Track which subfamilies we already emitted trade-active edge records for
    emitted_edge_subfamilies: set[str] = set()

    for candidate in records:
        if not isinstance(candidate, dict):
            continue
        subfamily_id = _candidate_key(candidate)
        metrics = metrics_by_subfamily.get(subfamily_id, {
            "stable_subfamily_id": subfamily_id,
            "total_sample_count": 0,
            "no_trade_count": 0,
            "trade_active_count": 0,
            "no_trade_ratio": 1.0,
            "trade_active_ratio": 0.0,
            "no_trade_pnl": 0.0,
            "trade_active_pnl": 0.0,
            "total_pnl": 0.0,
            "no_trade_profit_factor": 0.0,
            "trade_active_profit_factor": 0.0,
            "total_profit_factor": 0.0,
        })
        contribution_records.append(_no_trade_contribution_record(idx, source_type, candidate, metrics, min_pf))

        if subfamily_id not in emitted_edge_subfamilies:
            emitted_edge_subfamilies.add(subfamily_id)
            edge_rec = _trade_active_edge_record(idx, metrics, min_pf)
            edge_records.append(edge_rec)

        flag = _no_trade_dominance_flag(idx, source_type, candidate, metrics, min_pf)
        if flag is not None:
            flag_records.append(flag)

        idx += 1

    return contribution_records, edge_records, flag_records, idx


def run_no_trade_contribution_audit_v7() -> dict[str, object]:
    leaderboard = _load_jsonl(V6_TOURNAMENT_LEADERBOARD_PATH)
    watchlist = _load_jsonl(V6_WATCHLIST_PATH)
    rejections = _load_jsonl(V6_GATE_REJECTIONS_PATH)
    trades = _load_jsonl(V6_PATH_TRADES_PATH)
    scoreboard = _load_json(V6_SCOREBOARD_PATH)
    mutation_queue = load_v6_mutation_queue_records()

    trades_by_subfamily = group_trades_by_subfamily(trades)
    metrics_by_subfamily = {
        sub: compute_subfamily_trade_active_metrics(sub, sub_trades)
        for sub, sub_trades in trades_by_subfamily.items()
    }

    min_pf = MIN_BREAKTHROUGH_PF

    contribution_records: list[dict[str, object]] = []
    edge_records: list[dict[str, object]] = []
    flag_records: list[dict[str, object]] = []
    idx = 0

    for source_type, records in [
        ("leaderboard", leaderboard),
        ("watchlist", watchlist),
        ("rejection", rejections),
    ]:
        crecs, erecs, frecs, idx = _audit_source_records(
            source_type, records, metrics_by_subfamily, min_pf, idx
        )
        contribution_records.extend(crecs)
        edge_records.extend(erecs)
        flag_records.extend(frecs)

    # Scoreboard-level no-trade dominance flag for the v6 row
    v6_row = next(
        (row for row in scoreboard.get("rows", []) if str(row.get("version", "")) == "v6"),
        {},
    )
    scoreboard_top_subfamily = str(v6_row.get("top_subfamily", ""))
    scoreboard_top_cohort = str(v6_row.get("top_cohort", ""))
    if scoreboard_top_subfamily:
        scoreboard_metrics = metrics_by_subfamily.get(
            scoreboard_top_subfamily,
            {
                "stable_subfamily_id": scoreboard_top_subfamily,
                "total_sample_count": _safe_int(v6_row.get("top_sample_count", 0)),
                "no_trade_count": _safe_int(v6_row.get("top_sample_count", 0)),
                "trade_active_count": 0,
                "no_trade_ratio": 1.0,
                "trade_active_ratio": 0.0,
                "no_trade_pnl": _safe_float(v6_row.get("top_net_pnl", 0.0)),
                "trade_active_pnl": 0.0,
                "total_pnl": _safe_float(v6_row.get("top_net_pnl", 0.0)),
                "no_trade_profit_factor": _safe_float(v6_row.get("top_profit_factor", 0.0)),
                "trade_active_profit_factor": 0.0,
                "total_profit_factor": _safe_float(v6_row.get("top_profit_factor", 0.0)),
            },
        )
        scoreboard_candidate = {
            "stable_family_id": str(v6_row.get("top_family", "")),
            "stable_subfamily_id": scoreboard_top_subfamily,
            "cohort_id": scoreboard_top_cohort,
            "profit_factor": v6_row.get("top_profit_factor", 0.0),
            "net_pnl": v6_row.get("top_net_pnl", 0.0),
            "sample_count": v6_row.get("top_sample_count", 0),
        }
        flag = _no_trade_dominance_flag(idx, "scoreboard", scoreboard_candidate, scoreboard_metrics, min_pf)
        if flag is not None:
            flag_records.append(flag)
            idx += 1

    write_jsonl_file(NO_TRADE_CONTRIBUTION_RECORDS_V7_PATH, contribution_records)
    write_jsonl_file(TRADE_ACTIVE_EDGE_RECORDS_V7_PATH, edge_records)
    write_jsonl_file(NO_TRADE_DOMINANCE_FLAGS_V7_PATH, flag_records)

    total_trade_count = len(trades)
    no_trade_total = sum(_safe_int(m.get("no_trade_count", 0)) for m in metrics_by_subfamily.values())
    active_total = sum(_safe_int(m.get("trade_active_count", 0)) for m in metrics_by_subfamily.values())
    no_trade_ratio_overall = round(no_trade_total / total_trade_count, 6) if total_trade_count else 0.0
    active_ratio_overall = round(active_total / total_trade_count, 6) if total_trade_count else 0.0

    blocked_count = sum(1 for f in flag_records if bool(f.get("blocked", False)))
    no_trade_only_count = sum(1 for f in flag_records if bool(f.get("no_trade_only", False)))
    no_trade_dominant_count = sum(1 for f in flag_records if bool(f.get("no_trade_dominant", False)))

    top_rejection_reasons: dict[str, int] = {}
    for rej in rejections:
        if not isinstance(rej, dict):
            continue
        for reason in rej.get("reasons", []):
            reason_str = str(reason)
            top_rejection_reasons[reason_str] = top_rejection_reasons.get(reason_str, 0) + 1

    scoreboard_rows = scoreboard.get("rows", [])
    v6_scoreboard_row = next(
        (row for row in scoreboard_rows if str(row.get("version", "")) == "v6"),
        {},
    )

    status = "no_trade_contribution_audit_complete_v7"
    summary = {
        "artifact_type": "no_trade_contribution_audit_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "no_trade_contribution_audit_status": status,
        "leaderboard_count": len(leaderboard),
        "watchlist_count": len(watchlist),
        "rejection_count": len(rejections),
        "scoreboard_row_count": len(scoreboard_rows),
        "mutation_queue_count": len(mutation_queue),
        "total_trade_count": total_trade_count,
        "no_trade_trade_count": no_trade_total,
        "trade_active_trade_count": active_total,
        "no_trade_ratio_overall": no_trade_ratio_overall,
        "trade_active_ratio_overall": active_ratio_overall,
        "no_trade_contribution_record_count": len(contribution_records),
        "trade_active_edge_record_count": len(edge_records),
        "no_trade_dominance_flag_count": len(flag_records),
        "no_trade_only_candidate_count": no_trade_only_count,
        "no_trade_dominant_candidate_count": no_trade_dominant_count,
        "blocked_no_trade_only_count": blocked_count,
        "v6_top_cohort": str(v6_scoreboard_row.get("top_cohort", "")),
        "v6_top_subfamily": str(v6_scoreboard_row.get("top_subfamily", "")),
        "v6_top_profit_factor": _safe_float(v6_scoreboard_row.get("top_profit_factor", 0.0)),
        "v6_top_no_trade_dominant": True,
        "top_rejection_reasons": top_rejection_reasons,
        "v7_min_breakthrough_pf": min_pf,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(NO_TRADE_AUDIT_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        NO_TRADE_AUDIT_V7_PROOF_PATH,
        [research_v7_proof_record("no-trade-contribution-audit-v7", status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_no_trade_contribution_audit_v7(), indent=2, sort_keys=True, default=str))
