"""Deterministic walk-forward split builder (offline, paper-only).

Workstream A of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`.

This module builds 8+ deterministic walk-forward splits across the fixture corpus:
  * ≥ 3 rolling splits
  * ≥ 2 blocked splits (disjoint train/validation/holdout per split)
  * ≥ 1 anchored split
  * ≥ 1 regime-holdout split
  * ≥ 1 stress-holdout split

The builder reads walk-forward windows from the existing
`dopey_data/fixtures/walk_forward/` corpus, classifies them by regime, and assembles
deterministic splits. No real data. No network. No live state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .window_model import WalkForwardWindow, load_walk_forward_windows
from .consistency_models import (
    ALLOWED_SPLIT_TYPES,
    BlockedWalkForwardPlan,
    HoldoutWindowSet,
    RollingWalkForwardPlan,
    STRONGER_WF_CONSISTENCY_VERSION,
    WalkForwardSplit,
    WalkForwardSplitSet,
)


STRATEGY_FAMILIES: tuple[str, ...] = (
    "directional_convexity",
    "volatility_expansion",
    "volatility_compression",
    "short_duration_defined_risk",
)


# Required regime tags the consistency suite must cover. Each new window added to
# the corpus should match one of these so the consistency runner can find coverage.
REQUIRED_REGIME_TAGS: tuple[str, ...] = (
    "trend_vol_expansion",
    "chop_vol_compression",
    "gap_reversal",
    "liquidity_decay",
    "event_vol_expansion",
    "post_event_iv_crush",
    "bearish_breakdown",
    "bullish_breakout",
    "range_bound_pin",
    "high_spread_bad_fill",
    "low_liquidity_decay",
    "macro_shock_risk_off",
    "macro_contradiction_pressure",
    "surface_instability_fakeout",
    "short_duration_bad_fill",
    "vol_expansion_trap",
    "compression_shock_failure",
    "clean_directional_confirmation",
)


# Stress holdout coverage: windows that contain bad-fill OR macro-shock conditions.
STRESS_HOLDOUT_REGIMES: frozenset[str] = frozenset({
    "high_spread_bad_fill",
    "low_liquidity_decay",
    "macro_shock_risk_off",
    "macro_contradiction_pressure",
    "surface_instability_fakeout",
    "short_duration_bad_fill",
    "vol_expansion_trap",
    "compression_shock_failure",
})


@dataclass(frozen=True)
class WindowClass:
    window: WalkForwardWindow
    regime: str


def classify_windows(windows: Iterable[WalkForwardWindow]) -> list[WindowClass]:
    """Return windows classified by regime tag (window.regime_tag)."""
    out: list[WindowClass] = []
    for w in windows:
        out.append(WindowClass(window=w, regime=str(w.regime_tag)))
    return out


def _by_regime(windows: list[WindowClass]) -> dict[str, list[WindowClass]]:
    by: dict[str, list[WindowClass]] = {}
    for w in windows:
        by.setdefault(w.regime, []).append(w)
    return by


def _deterministic_split_id(prefix: str, train: list[str], val: list[str], holdout: list[str]) -> str:
    """Deterministic split id from a stable hash of sorted window ids (so re-runs are stable)."""
    import hashlib
    sig = "|".join(sorted(train)) + "#" + "|".join(sorted(val)) + "#" + "|".join(sorted(holdout))
    return f"{prefix}-{hashlib.sha1(sig.encode('utf-8')).hexdigest()[:10]}"


def build_rolling_splits(
    windows: list[WalkForwardWindow],
    seed: str = "dopey-stronger-wf-rolling",
    min_splits: int = 3,
) -> list[WalkForwardSplit]:
    """Build ≥ 3 rolling walk-forward splits. Each split uses 2 prior windows for train,
    1 for validation, and 1 future window for holdout. Splits are leak-free and ordered."""
    sorted_windows = sorted(windows, key=lambda w: w.sequence_id)
    splits: list[WalkForwardSplit] = []
    if len(sorted_windows) < 4:
        return splits
    for i in range(len(sorted_windows) - 3):
        if len(splits) >= max(min_splits, 3):
            break
        train = [sorted_windows[i].window_id, sorted_windows[i + 1].window_id]
        val = [sorted_windows[i + 2].window_id]
        hold = [sorted_windows[i + 3].window_id]
        regimes = [
            sorted_windows[i].regime_tag,
            sorted_windows[i + 1].regime_tag,
            sorted_windows[i + 2].regime_tag,
            sorted_windows[i + 3].regime_tag,
        ]
        splits.append(WalkForwardSplit(
            split_id=_deterministic_split_id("wf-rolling", train, val, hold),
            train_windows=tuple(train),
            validation_windows=tuple(val),
            holdout_windows=tuple(hold),
            regime_tags=tuple(sorted(set(regimes))),
            split_type="rolling",
            notes=f"{seed} rolling split idx={i}",
        ))
    return splits


def build_blocked_splits(
    windows: list[WalkForwardWindow],
    seed: str = "dopey-stronger-wf-blocked",
    min_splits: int = 2,
) -> list[WalkForwardSplit]:
    """Build ≥ 2 blocked walk-forward splits. Each split picks disjoint train/validation/holdout
    blocks. Block sizes are deterministic given the input order."""
    sorted_windows = sorted(windows, key=lambda w: w.sequence_id)
    splits: list[WalkForwardSplit] = []
    n = len(sorted_windows)
    if n < 9:
        return splits
    # Build two 3-block splits of equal-ish size: train block, validation block, holdout block.
    # Each window appears in exactly one block per split. No leakage by construction.
    def _block_split(s: int, train_size: int, val_size: int, holdout_size: int) -> WalkForwardSplit:
        offset = s * (train_size + val_size + holdout_size)
        train = [sorted_windows[offset + i].window_id for i in range(train_size)]
        val = [sorted_windows[offset + train_size + i].window_id for i in range(val_size)]
        hold = [sorted_windows[offset + train_size + val_size + i].window_id for i in range(holdout_size)]
        regimes = [sorted_windows[offset + i].regime_tag for i in range(train_size + val_size + holdout_size)]
        return WalkForwardSplit(
            split_id=_deterministic_split_id("wf-blocked", train, val, hold),
            train_windows=tuple(train),
            validation_windows=tuple(val),
            holdout_windows=tuple(hold),
            regime_tags=tuple(sorted(set(regimes))),
            split_type="blocked",
            notes=f"{seed} blocked split idx={s}",
        )

    # Two blocked splits, each train=3 / val=3 / holdout=3 (n=18 minimum).
    train_size = 3
    val_size = 3
    hold_size = 3
    block_size = train_size + val_size + hold_size
    max_splits = n // block_size
    for s in range(max(max_splits, min_splits)):
        if len(splits) >= max(min_splits, 2):
            break
        if (s + 1) * block_size > n:
            break
        splits.append(_block_split(s, train_size, val_size, hold_size))
    return splits


def build_anchored_split(windows: list[WalkForwardWindow], seed: str = "dopey-stronger-wf-anchored") -> WalkForwardSplit:
    """Build a single anchored walk-forward split: train = the first 2/3 of windows,
    validation = next 1/6, holdout = final 1/6. Same anchor for all subsequent updates."""
    sorted_windows = sorted(windows, key=lambda w: w.sequence_id)
    n = len(sorted_windows)
    train_end = max(1, n * 2 // 3)
    val_end = max(train_end + 1, n * 5 // 6)
    train = [w.window_id for w in sorted_windows[:train_end]]
    val = [w.window_id for w in sorted_windows[train_end:val_end]]
    hold = [w.window_id for w in sorted_windows[val_end:]]
    regimes = [w.regime_tag for w in sorted_windows]
    return WalkForwardSplit(
        split_id=_deterministic_split_id("wf-anchored", train, val, hold),
        train_windows=tuple(train),
        validation_windows=tuple(val),
        holdout_windows=tuple(hold),
        regime_tags=tuple(sorted(set(regimes))),
        split_type="anchored",
        notes=f"{seed} anchored split anchored-to-start",
    )


def build_regime_holdout_split(windows: list[WalkForwardWindow], target_regime: str,
                               seed: str = "dopey-stronger-wf-regime") -> WalkForwardSplit:
    """Build a single regime-holdout split: holdout contains windows for the target regime;
    train and validation contain a deterministic mix of the remaining windows."""
    matching = [w for w in windows if w.regime_tag == target_regime]
    others = [w for w in windows if w.regime_tag != target_regime]
    matching.sort(key=lambda w: w.sequence_id)
    others.sort(key=lambda w: w.sequence_id)
    if not matching:
        raise ValueError(f"no windows found for regime {target_regime}")
    hold = [w.window_id for w in matching[:max(1, len(matching) // 2)]]
    remaining = [w.window_id for w in matching[max(1, len(matching) // 2):]] + [w.window_id for w in others]
    remaining.sort()
    midpoint = max(1, len(remaining) // 2)
    train = remaining[:midpoint]
    val = remaining[midpoint:]
    regimes = sorted({w.regime_tag for w in windows})
    return WalkForwardSplit(
        split_id=_deterministic_split_id("wf-regime-holdout", train, val, hold),
        train_windows=tuple(train),
        validation_windows=tuple(val),
        holdout_windows=tuple(hold),
        regime_tags=tuple(regimes),
        split_type="regime_holdout",
        notes=f"{seed} regime-holdout target={target_regime}",
    )


def build_stress_holdout_split(windows: list[WalkForwardWindow],
                               seed: str = "dopey-stronger-wf-stress") -> WalkForwardSplit:
    """Build a single stress-holdout split: holdout is composed of bad-fill OR macro-shock
    regimes (or both). Train and validation cover the rest of the corpus."""
    stress = [w for w in windows if w.regime_tag in STRESS_HOLDOUT_REGIMES]
    rest = [w for w in windows if w.regime_tag not in STRESS_HOLDOUT_REGIMES]
    stress.sort(key=lambda w: w.sequence_id)
    rest.sort(key=lambda w: w.sequence_id)
    if not stress:
        raise ValueError("no stress-holdout windows found")
    hold = [w.window_id for w in stress]
    if not rest:
        raise ValueError("no non-stress windows found for train/validation")
    midpoint = max(1, len(rest) // 2)
    train = [w.window_id for w in rest[:midpoint]]
    val = [w.window_id for w in rest[midpoint:]]
    regimes = sorted({w.regime_tag for w in windows})
    return WalkForwardSplit(
        split_id=_deterministic_split_id("wf-stress-holdout", train, val, hold),
        train_windows=tuple(train),
        validation_windows=tuple(val),
        holdout_windows=tuple(hold),
        regime_tags=tuple(regimes),
        split_type="stress_holdout",
        notes=f"{seed} stress-holdout covering {sorted(STRESS_HOLDOUT_REGIMES)}",
    )


def build_holdout_window_set(
    splits: list[WalkForwardSplit],
    set_id: str = "wf-holdout-set",
    coverage_holds: tuple[str, ...] = ("regime_holdout", "stress_holdout"),
) -> HoldoutWindowSet:
    """Aggregate the unique holdout windows from a list of splits into a single set."""
    holdouts: set[str] = set()
    for s in splits:
        if s.split_type in coverage_holds:
            holdouts.update(s.holdout_windows)
    regimes = sorted({tag for s in splits if s.split_type in coverage_holds for tag in s.regime_tags})
    return HoldoutWindowSet(
        set_id=set_id,
        window_ids=tuple(sorted(holdouts)),
        regime_tags=tuple(regimes),
        coverage_holds=coverage_holds,
        notes=f"derived from {len(splits)} splits",
    )


# ---------------------------------------------------------------------------
# Higher-level plan builders.
# ---------------------------------------------------------------------------

def build_stronger_walk_forward_splits(
    windows: list[WalkForwardWindow] | None = None,
    seed: str = "dopey-stronger-wf-v1",
) -> WalkForwardSplitSet:
    """Build the canonical 8+ split set used by the stronger walk-forward runner."""
    if windows is None:
        windows = load_walk_forward_windows()
    rolling = build_rolling_splits(windows, seed=seed, min_splits=3)
    blocked = build_blocked_splits(windows, seed=seed, min_splits=2)
    anchored = build_anchored_split(windows, seed=seed)
    regime_holdout = build_regime_holdout_split(windows, target_regime="macro_shock_risk_off", seed=seed)
    stress_holdout = build_stress_holdout_split(windows, seed=seed)
    splits = rolling + blocked + [anchored, regime_holdout, stress_holdout]
    plan_id = f"dopey-stronger-wf-plan-{seed}"
    return WalkForwardSplitSet(plan_id=plan_id, splits=tuple(splits))


def build_rolling_plan(
    windows: list[WalkForwardWindow] | None = None,
    target_families: tuple[str, ...] = STRATEGY_FAMILIES,
    seed: str = "dopey-stronger-wf-rolling",
) -> RollingWalkForwardPlan:
    if windows is None:
        windows = load_walk_forward_windows()
    splits = build_rolling_splits(windows, seed=seed, min_splits=3)
    regime_cov = tuple(sorted({t for s in splits for t in s.regime_tags}))
    return RollingWalkForwardPlan(
        plan_id=f"dopey-stronger-wf-rolling-plan-{seed}",
        splits=tuple(splits),
        window_count=len(windows),
        holdout_count=sum(len(s.holdout_windows) for s in splits),
        regime_coverage=regime_cov,
        target_families=target_families,
        deterministic_seed=seed,
        notes="rolling plan: 3+ rolling splits; all families evaluated",
    )


def build_blocked_plan(
    windows: list[WalkForwardWindow] | None = None,
    target_families: tuple[str, ...] = STRATEGY_FAMILIES,
    seed: str = "dopey-stronger-wf-blocked",
) -> BlockedWalkForwardPlan:
    if windows is None:
        windows = load_walk_forward_windows()
    splits = build_blocked_splits(windows, seed=seed, min_splits=2)
    regime_cov = tuple(sorted({t for s in splits for t in s.regime_tags}))
    return BlockedWalkForwardPlan(
        plan_id=f"dopey-stronger-wf-blocked-plan-{seed}",
        splits=tuple(splits),
        window_count=len(windows),
        holdout_count=sum(len(s.holdout_windows) for s in splits),
        regime_coverage=regime_cov,
        target_families=target_families,
        deterministic_seed=seed,
        notes="blocked plan: 2+ disjoint train/val/holdout splits; no train leakage",
    )


def build_anchored_split_record(
    windows: list[WalkForwardWindow] | None = None,
    target_families: tuple[str, ...] = STRATEGY_FAMILIES,
    seed: str = "dopey-stronger-wf-anchored",
) -> WalkForwardSplit:
    if windows is None:
        windows = load_walk_forward_windows()
    return build_anchored_split(windows, seed=seed)


def build_regime_holdout_split_record(
    windows: list[WalkForwardWindow] | None = None,
    target_regime: str = "macro_shock_risk_off",
    target_families: tuple[str, ...] = STRATEGY_FAMILIES,
    seed: str = "dopey-stronger-wf-regime",
) -> WalkForwardSplit:
    if windows is None:
        windows = load_walk_forward_windows()
    return build_regime_holdout_split(windows, target_regime=target_regime, seed=seed)


def build_stress_holdout_split_record(
    windows: list[WalkForwardWindow] | None = None,
    target_families: tuple[str, ...] = STRATEGY_FAMILIES,
    seed: str = "dopey-stronger-wf-stress",
) -> WalkForwardSplit:
    if windows is None:
        windows = load_walk_forward_windows()
    return build_stress_holdout_split(windows, seed=seed)


# ---------------------------------------------------------------------------
# Corpus extension helper (Workstream B).
# ---------------------------------------------------------------------------

# Compact window templates for the additional corpus. These are returned as
# dictionaries; the runner / corpus builder materializes them into JSON.
ADDITIONAL_WINDOW_TEMPLATES: tuple[dict, ...] = (
    {
        "window_id": "window_013_train",
        "window_type": "train",
        "regime_tag": "macro_contradiction_pressure",
        "underlying": {"price": 450.0, "prev_close": 451.2, "realized_vol_20d": 0.235, "regime_score": 0.55},
        "expected": {"next_underlying_price": 449.0, "next_iv": 0.225, "days_to_exit": 4, "exit_reason": "invalidation_triggered", "favorable_move": 0.4, "adverse_move_pct": -0.7},
        "regime_context": {"liquidity_quality": 0.65, "spread_penalty": 0.20, "slippage_penalty": 0.18, "iv_effect": -0.05, "macro_contradiction": 0.7, "technical_fakeout": 0.3, "pattern_confidence": 0.5, "invalidation_quality": 0.55, "direction": "neutral", "vol_bias": "neutral"},
        "family_hints": {"directional_convexity": 0.45, "volatility_expansion": 0.35, "volatility_compression": 0.55, "short_duration_defined_risk": 0.35},
        "notes": "additional macro contradiction pressure window",
    },
    {
        "window_id": "window_014_train",
        "window_type": "train",
        "regime_tag": "surface_instability_fakeout",
        "underlying": {"price": 450.0, "prev_close": 449.4, "realized_vol_20d": 0.295, "regime_score": 0.45},
        "expected": {"next_underlying_price": 451.8, "next_iv": 0.31, "days_to_exit": 3, "exit_reason": "invalidation_triggered", "favorable_move": 0.5, "adverse_move_pct": -0.9},
        "regime_context": {"liquidity_quality": 0.55, "spread_penalty": 0.30, "slippage_penalty": 0.28, "iv_effect": 0.15, "macro_contradiction": 0.4, "technical_fakeout": 0.7, "pattern_confidence": 0.35, "invalidation_quality": 0.5, "direction": "bull", "vol_bias": "expansion"},
        "family_hints": {"directional_convexity": 0.35, "volatility_expansion": 0.45, "volatility_compression": 0.3, "short_duration_defined_risk": 0.20},
        "notes": "additional unstable surface fakeout window",
    },
    {
        "window_id": "window_015_train",
        "window_type": "train",
        "regime_tag": "short_duration_bad_fill",
        "underlying": {"price": 450.0, "prev_close": 450.4, "realized_vol_20d": 0.18, "regime_score": 0.40},
        "expected": {"next_underlying_price": 450.7, "next_iv": 0.185, "days_to_exit": 1, "exit_reason": "invalidation_triggered", "favorable_move": 0.2, "adverse_move_pct": -0.6},
        "regime_context": {"liquidity_quality": 0.4, "spread_penalty": 0.5, "slippage_penalty": 0.55, "iv_effect": 0.0, "macro_contradiction": 0.25, "technical_fakeout": 0.55, "pattern_confidence": 0.35, "invalidation_quality": 0.45, "direction": "neutral", "vol_bias": "neutral"},
        "family_hints": {"directional_convexity": 0.25, "volatility_expansion": 0.25, "volatility_compression": 0.35, "short_duration_defined_risk": 0.15},
        "notes": "additional short-duration bad-fill window",
    },
    {
        "window_id": "window_016_validation",
        "window_type": "validation",
        "regime_tag": "vol_expansion_trap",
        "underlying": {"price": 450.0, "prev_close": 448.8, "realized_vol_20d": 0.34, "regime_score": 0.35},
        "expected": {"next_underlying_price": 446.0, "next_iv": 0.21, "days_to_exit": 5, "exit_reason": "invalidation_triggered", "favorable_move": 0.3, "adverse_move_pct": -1.2},
        "regime_context": {"liquidity_quality": 0.55, "spread_penalty": 0.35, "slippage_penalty": 0.32, "iv_effect": -0.4, "macro_contradiction": 0.5, "technical_fakeout": 0.7, "pattern_confidence": 0.30, "invalidation_quality": 0.55, "direction": "bear", "vol_bias": "crush"},
        "family_hints": {"directional_convexity": 0.30, "volatility_expansion": 0.30, "volatility_compression": 0.55, "short_duration_defined_risk": 0.20},
        "notes": "additional vol expansion trap window (long-vol punished)",
    },
    {
        "window_id": "window_017_validation",
        "window_type": "validation",
        "regime_tag": "compression_shock_failure",
        "underlying": {"price": 450.0, "prev_close": 451.0, "realized_vol_20d": 0.13, "regime_score": 0.45},
        "expected": {"next_underlying_price": 444.5, "next_iv": 0.22, "days_to_exit": 3, "exit_reason": "invalidation_triggered", "favorable_move": 0.3, "adverse_move_pct": -1.1},
        "regime_context": {"liquidity_quality": 0.55, "spread_penalty": 0.30, "slippage_penalty": 0.30, "iv_effect": 0.15, "macro_contradiction": 0.55, "technical_fakeout": 0.65, "pattern_confidence": 0.30, "invalidation_quality": 0.45, "direction": "bear", "vol_bias": "expansion"},
        "family_hints": {"directional_convexity": 0.25, "volatility_expansion": 0.45, "volatility_compression": 0.30, "short_duration_defined_risk": 0.15},
        "notes": "additional compression shock failure window",
    },
    {
        "window_id": "window_018_validation",
        "window_type": "validation",
        "regime_tag": "clean_directional_confirmation",
        "underlying": {"price": 450.0, "prev_close": 449.2, "realized_vol_20d": 0.19, "regime_score": 0.86},
        "expected": {"next_underlying_price": 458.0, "next_iv": 0.215, "days_to_exit": 5, "exit_reason": "target_profit_reached", "favorable_move": 1.8, "adverse_move_pct": -0.40},
        "regime_context": {"liquidity_quality": 0.88, "spread_penalty": 0.06, "slippage_penalty": 0.06, "iv_effect": 0.10, "macro_contradiction": 0.05, "technical_fakeout": 0.10, "pattern_confidence": 0.85, "invalidation_quality": 0.75, "direction": "bull", "vol_bias": "expansion"},
        "family_hints": {"directional_convexity": 0.88, "volatility_expansion": 0.65, "volatility_compression": 0.25, "short_duration_defined_risk": 0.78},
        "notes": "additional clean directional confirmation window",
    },
    {
        "window_id": "window_019_holdout",
        "window_type": "holdout",
        "regime_tag": "trend_vol_expansion",
        "underlying": {"price": 450.0, "prev_close": 449.0, "realized_vol_20d": 0.255, "regime_score": 0.84},
        "expected": {"next_underlying_price": 459.5, "next_iv": 0.30, "days_to_exit": 6, "exit_reason": "target_profit_reached", "favorable_move": 1.9, "adverse_move_pct": -0.6},
        "regime_context": {"liquidity_quality": 0.85, "spread_penalty": 0.06, "slippage_penalty": 0.07, "iv_effect": 0.4, "macro_contradiction": 0.10, "technical_fakeout": 0.15, "pattern_confidence": 0.78, "invalidation_quality": 0.70, "direction": "bull", "vol_bias": "expansion"},
        "family_hints": {"directional_convexity": 0.85, "volatility_expansion": 0.85, "volatility_compression": 0.20, "short_duration_defined_risk": 0.70},
        "notes": "additional trend-vol expansion holdout (positive)",
    },
    {
        "window_id": "window_020_holdout",
        "window_type": "holdout",
        "regime_tag": "chop_vol_compression",
        "underlying": {"price": 450.0, "prev_close": 450.4, "realized_vol_20d": 0.11, "regime_score": 0.78},
        "expected": {"next_underlying_price": 450.9, "next_iv": 0.115, "days_to_exit": 5, "exit_reason": "expiry_time_decay", "favorable_move": 0.5, "adverse_move_pct": -0.3},
        "regime_context": {"liquidity_quality": 0.80, "spread_penalty": 0.10, "slippage_penalty": 0.10, "iv_effect": -0.10, "macro_contradiction": 0.10, "technical_fakeout": 0.20, "pattern_confidence": 0.55, "invalidation_quality": 0.65, "direction": "neutral", "vol_bias": "compression"},
        "family_hints": {"directional_convexity": 0.30, "volatility_expansion": 0.20, "volatility_compression": 0.85, "short_duration_defined_risk": 0.40},
        "notes": "additional chop/range holdout",
    },
    {
        "window_id": "window_021_holdout",
        "window_type": "holdout",
        "regime_tag": "bearish_breakdown",
        "underlying": {"price": 450.0, "prev_close": 452.0, "realized_vol_20d": 0.245, "regime_score": 0.74},
        "expected": {"next_underlying_price": 442.5, "next_iv": 0.26, "days_to_exit": 5, "exit_reason": "target_profit_reached", "favorable_move": 1.7, "adverse_move_pct": -0.5},
        "regime_context": {"liquidity_quality": 0.78, "spread_penalty": 0.10, "slippage_penalty": 0.10, "iv_effect": 0.20, "macro_contradiction": 0.20, "technical_fakeout": 0.20, "pattern_confidence": 0.70, "invalidation_quality": 0.70, "direction": "bear", "vol_bias": "expansion"},
        "family_hints": {"directional_convexity": 0.78, "volatility_expansion": 0.65, "volatility_compression": 0.20, "short_duration_defined_risk": 0.55},
        "notes": "additional bearish breakdown holdout",
    },
    {
        "window_id": "window_022_holdout",
        "window_type": "holdout",
        "regime_tag": "post_event_iv_crush",
        "underlying": {"price": 450.0, "prev_close": 449.5, "realized_vol_20d": 0.12, "regime_score": 0.70},
        "expected": {"next_underlying_price": 451.0, "next_iv": 0.10, "days_to_exit": 4, "exit_reason": "expiry_time_decay", "favorable_move": 0.6, "adverse_move_pct": -0.3},
        "regime_context": {"liquidity_quality": 0.75, "spread_penalty": 0.10, "slippage_penalty": 0.10, "iv_effect": -0.30, "macro_contradiction": 0.20, "technical_fakeout": 0.25, "pattern_confidence": 0.55, "invalidation_quality": 0.60, "direction": "neutral", "vol_bias": "compression"},
        "family_hints": {"directional_convexity": 0.40, "volatility_expansion": 0.18, "volatility_compression": 0.80, "short_duration_defined_risk": 0.40},
        "notes": "additional post-event IV crush holdout",
    },
    {
        "window_id": "window_023_holdout",
        "window_type": "holdout",
        "regime_tag": "bullish_breakout",
        "underlying": {"price": 450.0, "prev_close": 449.0, "realized_vol_20d": 0.22, "regime_score": 0.88},
        "expected": {"next_underlying_price": 460.5, "next_iv": 0.245, "days_to_exit": 5, "exit_reason": "target_profit_reached", "favorable_move": 2.0, "adverse_move_pct": -0.5},
        "regime_context": {"liquidity_quality": 0.85, "spread_penalty": 0.06, "slippage_penalty": 0.07, "iv_effect": 0.20, "macro_contradiction": 0.10, "technical_fakeout": 0.10, "pattern_confidence": 0.82, "invalidation_quality": 0.75, "direction": "bull", "vol_bias": "expansion"},
        "family_hints": {"directional_convexity": 0.88, "volatility_expansion": 0.65, "volatility_compression": 0.20, "short_duration_defined_risk": 0.75},
        "notes": "additional bullish breakout holdout",
    },
    {
        "window_id": "window_024_holdout",
        "window_type": "holdout",
        "regime_tag": "low_liquidity_decay",
        "underlying": {"price": 450.0, "prev_close": 450.5, "realized_vol_20d": 0.16, "regime_score": 0.20},
        "expected": {"next_underlying_price": 451.5, "next_iv": 0.165, "days_to_exit": 3, "exit_reason": "invalidation_triggered", "favorable_move": 0.3, "adverse_move_pct": -0.6},
        "regime_context": {"liquidity_quality": 0.30, "spread_penalty": 0.55, "slippage_penalty": 0.50, "iv_effect": 0.0, "macro_contradiction": 0.20, "technical_fakeout": 0.45, "pattern_confidence": 0.30, "invalidation_quality": 0.35, "direction": "neutral", "vol_bias": "neutral"},
        "family_hints": {"directional_convexity": 0.30, "volatility_expansion": 0.20, "volatility_compression": 0.35, "short_duration_defined_risk": 0.15},
        "notes": "additional low-liquidity decay holdout",
    },
)


def additional_window_count() -> int:
    """Number of additional window templates that ship with the consistency expansion."""
    return len(ADDITIONAL_WINDOW_TEMPLATES)
