"""Render market-structure charts from validated real history.

Candlesticks + volume + support/resistance zones + trap-event markers, drawn
with matplotlib from the hash-pinned history spine and the market-structure
artifacts. The numeric features remain the primary machine interface; these
PNGs are the multimodal review surface (human or vision-model reads).

No fixtures, no network. Paper-only, live-blocked, not edge evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dopey_data.history_validator import validate_default_history_dataset
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
CHART_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "chart_vision_real"
CHART_SUMMARY_PATH = CHART_ARTIFACT_DIR / "real_structure_chart_summary.json"
SR_ZONES_PATH = REPO_ROOT / "artifacts" / "dopey" / "market_structure" / "support_resistance_zones.jsonl"
TRAP_EVENTS_PATH = REPO_ROOT / "artifacts" / "dopey" / "market_structure" / "trap_events.jsonl"

RENDER_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "NVDA", "TSLA")
RENDER_BARS = 250


def run_real_structure_chart_renderer() -> dict[str, Any]:
    dataset = validate_default_history_dataset()
    if dataset["dataset_status"] != "valid_real_dataset":
        summary = {
            "artifact_type": "real_structure_chart_summary",
            "chart_status": "blocked_missing_valid_real_history",
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(CHART_SUMMARY_PATH, summary)
        return summary
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for bar in dataset["bars_loaded"]:
        bars_by_symbol.setdefault(str(bar["symbol"]), []).append(bar)
    zones = _load_jsonl(SR_ZONES_PATH)
    traps = _load_jsonl(TRAP_EVENTS_PATH)
    CHART_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    for symbol in RENDER_SYMBOLS:
        rows = sorted(bars_by_symbol.get(symbol, []), key=lambda row: str(row["date"]))[-RENDER_BARS:]
        if len(rows) < 50:
            continue
        png_path = CHART_ARTIFACT_DIR / f"{symbol}_structure_chart.png"
        _render_chart(symbol, rows, zones, traps, png_path)
        rendered.append({"symbol": symbol, "png_path": str(png_path), "bars_rendered": len(rows)})
    summary = {
        "artifact_type": "real_structure_chart_summary",
        "chart_status": "real_structure_charts_rendered",
        "rendered": rendered,
        "render_bars": RENDER_BARS,
        "overlays": ["candlesticks", "volume", "sr_zones", "trap_markers"],
        "data_source_tier": "local_real_history",
        "real_history_used": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write_json(CHART_SUMMARY_PATH, summary)
    return summary


def _render_chart(
    symbol: str,
    rows: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    traps: list[dict[str, Any]],
    png_path: Path,
) -> None:
    dates = [str(row["date"]) for row in rows]
    opens = [float(row["open"]) for row in rows]
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    closes = [float(row["close"]) for row in rows]
    volumes = [int(row["volume"]) for row in rows]
    x_values = list(range(len(rows)))
    date_index = {date: index for index, date in enumerate(dates)}
    figure, (price_axis, volume_axis) = plt.subplots(
        2, 1, figsize=(16, 9), sharex=True, gridspec_kw={"height_ratios": [4, 1]}
    )
    up_color, down_color = "#2e7d32", "#c62828"
    for index in x_values:
        color = up_color if closes[index] >= opens[index] else down_color
        price_axis.vlines(index, lows[index], highs[index], color=color, linewidth=0.8)
        body_low = min(opens[index], closes[index])
        body_high = max(opens[index], closes[index])
        price_axis.add_patch(
            plt.Rectangle((index - 0.35, body_low), 0.7, max(body_high - body_low, 1e-9), color=color, alpha=0.9)
        )
    low_bound, high_bound = min(lows), max(highs)
    for zone in zones:
        if zone.get("symbol") != symbol:
            continue
        zone_mid = float(zone["zone_mid"])
        if low_bound * 0.98 <= zone_mid <= high_bound * 1.02:
            price_axis.axhline(zone_mid, color="#1565c0", linewidth=0.9, alpha=0.5, linestyle="--")
    trap_labels_used = set()
    for trap in traps:
        if trap.get("symbol") != symbol:
            continue
        index = date_index.get(str(trap.get("fail_date", "")))
        if index is None:
            continue
        is_bull = trap["trap_type"] == "bull_trap"
        marker, color = ("v", "#e65100") if is_bull else ("^", "#6a1b9a")
        label = trap["trap_type"] if trap["trap_type"] not in trap_labels_used else None
        trap_labels_used.add(trap["trap_type"])
        offset = highs[index] * 1.01 if is_bull else lows[index] * 0.99
        price_axis.scatter([index], [offset], marker=marker, color=color, s=70, zorder=5, label=label)
    volume_axis.bar(x_values, volumes, color="#546e7a", width=0.7)
    tick_step = max(len(dates) // 10, 1)
    volume_axis.set_xticks(x_values[::tick_step])
    volume_axis.set_xticklabels(dates[::tick_step], rotation=45, ha="right", fontsize=8)
    price_axis.set_title(
        f"{symbol} - real daily history, last {len(rows)} bars | SR zones (dashed) + trap events | paper-only research"
    )
    price_axis.grid(alpha=0.2)
    if trap_labels_used:
        price_axis.legend(loc="upper left", fontsize=9)
    volume_axis.set_ylabel("volume")
    price_axis.set_ylabel("price")
    figure.tight_layout()
    figure.savefig(png_path, dpi=110)
    plt.close(figure)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
