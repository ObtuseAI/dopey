"""Factor assembly for the target screener.

Two strictly separated factor classes:

POINT-IN-TIME (spine-derived, honest for held-out evaluation):
  momentum   - 20d/60d adjusted-close momentum blend, known at each date
  structure  - realized-vol compression (rv20/rv120), known at each date

SNAPSHOT (artifact-derived, CURRENT-DAY ONLY):
  value_rot / attention / flow / quality, plus the options-structure overlay
  (gamma regime, VRP, surface tear). These come from today's macro/fusion
  artifacts. Applying today's snapshot to PAST dates would be lookahead, so
  the elite archive's held-out fitness NEVER scores them - they enter the
  live screen only, stamped as such. (The macro lanes accrue history daily;
  point-in-time versions become possible as the archive grows.)

Missing data never becomes a made-up number: absent factors contribute 0.0
and the symbol's coverage record says which families were live.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_RAW_DIR = REPO_ROOT / "dopey_data" / "history" / "raw"
MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
FUSION_PATH = REPO_ROOT / "artifacts" / "dopey" / "market_context" / "entry_context_fusion.jsonl"

MOMENTUM_FAST_DAYS = 20
MOMENTUM_SLOW_DAYS = 60
RV_FAST_DAYS = 20
RV_SLOW_DAYS = 120
FORWARD_RETURN_DAYS = 10

# Symbols in the history universe that are context-only, never screen targets.
CONTEXT_ONLY_PREFIXES = ("^",)
CONTEXT_ONLY_SYMBOLS = frozenset({"VIX"})


def _squash(value: float) -> float:
    """Bounded, monotone map to (-1, 1); robust to outliers, deterministic."""
    return value / (1.0 + abs(value))


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def screenable_universe(universe: tuple[str, ...]) -> list[str]:
    return [
        symbol for symbol in universe
        if symbol not in CONTEXT_ONLY_SYMBOLS and not symbol.startswith(CONTEXT_ONLY_PREFIXES)
    ]


def load_adjusted_closes(symbol: str) -> list[tuple[str, float]]:
    """(date, adjusted_close) ascending from the governed raw spine file."""
    path = HISTORY_RAW_DIR / f"{symbol}.csv"
    if not path.exists():
        return []
    rows: list[tuple[str, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            try:
                close = float(record.get("adjusted_close") or record.get("close") or 0.0)
            except (TypeError, ValueError):
                continue
            date = str(record.get("date", ""))
            if date and close > 0:
                rows.append((date, close))
    rows.sort(key=lambda item: item[0])
    return rows


def point_in_time_factors(closes: list[float], index: int) -> dict[str, float] | None:
    """Spine-derived factor values known AT ``index`` (no future rows read)."""
    if index < RV_SLOW_DAYS or index >= len(closes):
        return None
    spot = closes[index]
    fast_base = closes[index - MOMENTUM_FAST_DAYS]
    slow_base = closes[index - MOMENTUM_SLOW_DAYS]
    if fast_base <= 0 or slow_base <= 0:
        return None
    momentum_fast = spot / fast_base - 1.0
    momentum_slow = spot / slow_base - 1.0
    momentum = _squash(6.0 * (0.6 * momentum_fast + 0.4 * momentum_slow))

    def _rv(window: int) -> float:
        rets = [
            math.log(closes[i] / closes[i - 1])
            for i in range(index - window + 1, index + 1)
            if closes[i - 1] > 0
        ]
        if len(rets) < 2:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(max(var, 0.0))

    rv_fast, rv_slow = _rv(RV_FAST_DAYS), _rv(RV_SLOW_DAYS)
    # compression = fast vol well below slow vol -> positive structure signal
    compression = _clip((1.0 - (rv_fast / rv_slow if rv_slow > 1e-12 else 1.0)) * 2.0)
    return {"momentum": momentum, "structure": compression}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_fusion_by_symbol() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    try:
        lines = FUSION_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return latest
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        symbol = str(record.get("symbol", ""))
        if symbol:
            latest[symbol] = record  # later lines win = newest snapshot
    return latest


def snapshot_factors(symbols: list[str]) -> tuple[dict[str, dict[str, float]], dict]:
    """Artifact-derived factors for TODAY's cross-section + provenance record.

    Returns ({symbol: {family: value}}, provenance). Absent lanes contribute
    nothing (callers treat missing families as 0.0-weight contributions).
    """
    macro = _load_json(MACRO_SUMMARY_PATH)
    fusion = _latest_fusion_by_symbol()
    fundamentals = macro.get("fundamentals", {}) if isinstance(macro.get("fundamentals"), dict) else {}
    screen = fundamentals.get("screen", {}) if isinstance(fundamentals.get("screen"), dict) else {}
    attention = macro.get("attention", {}) if isinstance(macro.get("attention"), dict) else {}
    attention_z = attention.get("attention_z_by_symbol", {}) if isinstance(attention.get("attention_z_by_symbol"), dict) else {}
    short_flow = macro.get("short_flow", {}) if isinstance(macro.get("short_flow"), dict) else {}
    flow_ratio = short_flow.get("short_volume_ratio_by_symbol", {}) if isinstance(short_flow.get("short_volume_ratio_by_symbol"), dict) else {}

    factors: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        row: dict[str, float] = {}
        info = screen.get(symbol, {}) if isinstance(screen.get(symbol), dict) else {}
        flags = info.get("excess_flags", [])
        if isinstance(flags, list) and info:
            rot = len(flags) / 5.0
            row["value_rot"] = _clip(rot * 2.0 - 0.2)      # 0 flags ~ -0.2, 3+ flags -> strongly positive
            row["quality"] = _clip(1.0 - 2.0 * rot)        # clean names -> +1
        z = attention_z.get(symbol)
        if isinstance(z, (int, float)):
            row["attention"] = _clip(float(z) / 3.0)
        ratio = flow_ratio.get(symbol)
        if isinstance(ratio, (int, float)):
            row["flow"] = _clip((float(ratio) - 0.45) / 0.2)
        fused = fusion.get(symbol, {})
        if fused:
            overlay = 0.0
            if fused.get("gamma_regime") == "short_gamma_amplifying":
                overlay += 0.4
            if fused.get("surface_tear_present") is True:
                overlay += 0.3
            if fused.get("vrp_rich_market") is True:
                overlay -= 0.3   # rich VRP = expensive premium, headwind for buyers
            if fused.get("earnings_blackout") is True:
                overlay -= 0.4
            row["structure_overlay"] = _clip(overlay)
        factors[symbol] = row

    provenance = {
        "macro_summary_present": bool(macro),
        "fusion_symbols": len(fusion),
        "fundamentals_as_of": str(fundamentals.get("as_of_newest", "")),
        "attention_symbols": len(attention_z),
        "flow_symbols": len(flow_ratio),
        "snapshot_semantics": "current_day_cross_section_only_not_backcastable",
    }
    return factors, provenance
