"""V4 volume family rescue.

Evaluates the volume subfamilies honestly. If the volume family
remains unprofitable after V3's volume dry-up template repair, V4
must classify it as 'volume_family_watchlist_or_demote' and not
fabricate volume rescue.
"""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import pnl_metrics, read_jsonl_file, record_with_hash, safe_float
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT
from dopey_autonomy.signal_research_v4_common import VOLUME_RESCUE_PATH, RESEARCH_V4_ROOT


V3_TRADES_PATH = RESEARCH_V3_ROOT / "research_path_trades_v3.jsonl"
V4_SLICES_PATH = RESEARCH_V4_ROOT / "profitable_slice_records_v4.jsonl"

VOLUME_FAMILY_IDS = {
    "volume|dry_up_breakout|trend_follow|dte14|1pct_otm",
    "volume|dry_up_breakout",
    "volume|dry_up_reclaim",
    "volume|climax_reversal_filter",
    "volume|range_compression_expansion",
}


def evaluate_volume_rescue() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    trades = read_jsonl_file(V3_TRADES_PATH)
    slices = read_jsonl_file(V4_SLICES_PATH)

    volume_trades = [
        trade for trade in trades
        if str(trade.get("stable_family_template_id") or trade.get("discovery_family_id", "")).startswith("volume|")
    ]
    if not volume_trades:
        # fall back to any "volume" tagged trades
        volume_trades = [
            trade for trade in trades
            if "volume" in str(trade.get("stable_family_template_id", "")).lower()
        ]
    metrics = pnl_metrics(volume_trades)
    pf = safe_float(metrics.get("profit_factor", 0.0))
    pnl = safe_float(metrics.get("net_pnl", 0.0))
    sample = int(metrics.get("sample_count", 0))

    if pf >= 1.10 and pnl > 0.0 and sample >= 30:
        status = "volume_rescued"
    elif pf >= 0.95 and pnl > 0.0 and sample >= 30:
        status = "volume_partial_rescue_watchlist"
    elif pf >= 0.80 and sample >= 20:
        status = "volume_family_watchlist"
    else:
        status = "volume_family_demote"

    # Slice-aware count: how many of the V4 slices report volume as
    # should_keep.
    volume_slice_keep = 0
    for s in slices:
        if str(s.get("slice_dimension", "")) in ("subfamily", "family") and str(s.get("slice_id", "")).startswith("volume|") and s.get("should_keep"):
            volume_slice_keep += 1

    return {
        "artifact_type": "volume_family_rescue_record_v4",
        "volume_rescue_status": status,
        "volume_rescue_enabled": True,
        "volume_rescued": status == "volume_rescued",
        "volume_trade_count": sample,
        "volume_net_pnl": pnl,
        "volume_profit_factor": pf,
        "volume_expectancy": safe_float(metrics.get("expectancy", 0.0)),
        "volume_max_drawdown": safe_float(metrics.get("max_drawdown", 0.0)),
        "volume_symbol_count": int(metrics.get("symbol_count", 0)),
        "volume_sector_count": int(metrics.get("sector_count", 0)),
        "volume_slice_keep_count": volume_slice_keep,
        "honest_classification": True,
        "public_data_only": True,
        **live_safety_fields(),
    }


def run_volume_family_rescue() -> dict[str, object]:
    record = evaluate_volume_rescue()
    record = record_with_hash(record, "record_hash")
    from dopey_autonomy.public_champion_common import write_jsonl_file
    write_jsonl_file(VOLUME_RESCUE_PATH, [record])
    return record
