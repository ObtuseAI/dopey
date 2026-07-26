"""The strategy playbook: the documented canon of how great traders, quants,
and investors win — mapped as a typed, scannable, evolvable baseline.

Purpose
-------
Strategy scope in this laboratory previously grew one hand-typed setup at a
time. This module fixes that structurally: it catalogs the canonical setup
families from the documented record — academic factor literature, published
practitioner methods, and audited track records — so the scanner can hunt
EVERY archetype autonomously, and the evolution machinery can refine each one
against held-out evidence.

Sources of the canon (lineage is stamped per setup):
- Academic: Jegadeesh-Titman momentum; Moskowitz-Ooi-Pedersen time-series
  momentum; Daniel-Moskowitz momentum crashes; Lehmann short-term reversal;
  De Bondt-Thaler overreaction; Fama-French value; Novy-Marx profitability;
  Piotroski F-score; George-Hwang 52-week high; Ball-Brown / Bernard-Thomas
  post-earnings drift; Gatev et al. pairs trading; Haugen/Baker low-vol;
  Ikenberry buybacks; Seyhun insider trades; Lucca-Moench pre-FOMC drift;
  McLean-Pontiff publication decay.
- Practitioner: Livermore (pyramiding winners); Darvas (box breakouts);
  O'Neil/IBD (base breakouts, relative-strength leadership); Minervini
  (volatility contraction); Dennis/Eckhardt turtles (channel trend
  following); Zweig (breadth thrust); Graham (deep value); Greenblatt
  (magic formula, spinoffs); Chanos (fundamental-rot shorts); Druckenmiller
  (liquidity-driven risk appetite); Soros (reflexivity); Asness/AQR
  (value+momentum, quality-minus-junk, VRP).

Honesty contract (structural, not decorative)
---------------------------------------------
Cataloging how great traders won is NOT evidence any setup wins here, now,
after costs. Every entry ships ``evidence_status="unvalidated_hypothesis"``
and stays there until the forward-settlement ledger EARNS it per-family trust
through the laboratory's own gates. Documented edges decay after publication
(McLean-Pontiff), regimes change, and costs eat paper edges. The playbook is
a map of where to look — never a list of what works. No entry can promote
itself, grade itself, or construct an order.
"""

from __future__ import annotations

from typing import Final, TypedDict


class PlaybookSetup(TypedDict):
    setup_id: str
    family: str
    direction: str
    lineage: tuple[str, ...]
    economic_rationale: str
    entry_conditions: str
    exit_invalidation: str
    regime_affinity: tuple[str, ...]
    failure_modes: tuple[str, ...]
    horizon_days: tuple[int, ...]
    required_data: tuple[str, ...]
    mechanism_id: str
    computable_detector: str
    evidence_status: str
    paper_only: bool
    live_blocked: bool


_U = "unvalidated_hypothesis"


def _setup(
    setup_id: str,
    family: str,
    direction: str,
    lineage: tuple[str, ...],
    rationale: str,
    entry: str,
    exit_: str,
    regimes: tuple[str, ...],
    failures: tuple[str, ...],
    horizons: tuple[int, ...],
    data: tuple[str, ...],
    mechanism_id: str,
    detector: str,
) -> PlaybookSetup:
    return {
        "setup_id": setup_id,
        "family": family,
        "direction": direction,
        "lineage": lineage,
        "economic_rationale": rationale,
        "entry_conditions": entry,
        "exit_invalidation": exit_,
        "regime_affinity": regimes,
        "failure_modes": failures,
        "horizon_days": horizons,
        "required_data": data,
        "mechanism_id": mechanism_id,
        "computable_detector": detector,
        "evidence_status": _U,
        "paper_only": True,
        "live_blocked": True,
    }


# Detector ids: "" = not computable with currently governed data (typed gap).
PLAYBOOK: Final[tuple[PlaybookSetup, ...]] = (
    # ------------------------------------------------------------------ #
    # MOMENTUM / TREND — the deepest documented anomaly family
    # ------------------------------------------------------------------ #
    _setup(
        "ts_momentum_12m", "momentum_trend", "either",
        ("Moskowitz-Ooi-Pedersen 2012", "AQR managed futures"),
        "12-month own-return sign persists (underreaction + slow capital); works across asset classes",
        "sign of trailing 12m return, skip most recent month; hold with the sign",
        "sign flips on the same lookback; vol-target the position",
        ("trending", "any"), ("sharp reversals at turning points", "1987/2009-style momentum crashes"),
        (20, 60), ("ohlcv",), "crash_aware_momentum", "detect_ts_momentum",
    ),
    _setup(
        "cross_sectional_momentum_12_1", "momentum_trend", "either",
        ("Jegadeesh-Titman 1993", "Carhart 1997", "AQR"),
        "past 12-1 month relative winners keep outperforming losers ~3-12 months (underreaction)",
        "long top-decile 12-1 return rank, short bottom decile; skip last month (reversal)",
        "rank decays out of extreme decile; momentum-crash guard trips",
        ("trending", "low_vol"), ("crowding unwinds", "crashes after panic bottoms (Daniel-Moskowitz)"),
        (20, 60), ("ohlcv", "universe_breadth"), "crash_aware_momentum", "detect_relative_momentum_rank",
    ),
    _setup(
        "channel_breakout_trend", "momentum_trend", "either",
        ("Donchian", "Dennis-Eckhardt turtles", "Covel trend following"),
        "N-day channel breaks capture the fat right tail of trends; losses are many-small, wins few-huge",
        "close breaks N-day high (long) / low (short) with ATR-based initial stop",
        "opposite M-day channel break (M<N); ATR trailing stop",
        ("trending", "vol_expansion"), ("chop bleeds stops in ranges", "whipsaw clusters"),
        (10, 20, 60), ("ohlcv",), "breadth_confirmed_breakout", "detect_channel_breakout",
    ),
    _setup(
        "gap_go_continuation", "momentum_trend", "either",
        ("practitioner canon; event-underreaction literature"),
        "large gaps on real news underreact intraday-to-days when they hold their range",
        "gap beyond prior range that HOLDS (close in gap direction, strong close location)",
        "gap fill; close back inside prior range",
        ("vol_expansion", "trending"), ("exhaustion gaps reverse", "fade-prone in chop"),
        (2, 5, 10), ("ohlcv",), "breadth_confirmed_breakout", "detect_gap_continuation",
    ),
    _setup(
        "week52_high_momentum", "momentum_trend", "long",
        ("George-Hwang 2004",),
        "anchoring near the 52-week high suppresses buying; breaks through it keep drifting",
        "price within 2% of 52-week high with positive 6m momentum",
        "close falls >10% from the high; momentum sign flips",
        ("trending",), ("double-top failure", "broad-market regime break"),
        (20, 60), ("ohlcv",), "crash_aware_momentum", "detect_52w_high_proximity",
    ),
    _setup(
        "darvas_box_breakout", "momentum_trend", "long",
        ("Darvas — How I Made $2,000,000",),
        "consolidation boxes stacked in an uptrend break upward on volume as demand overwhelms supply",
        "tight N-day box near highs breaks up on above-average volume",
        "re-entry into the box; box-low stop",
        ("trending",), ("false breakouts in weak tape",),
        (5, 10, 20), ("ohlcv",), "breadth_confirmed_breakout", "detect_box_breakout",
    ),
    _setup(
        "base_breakout_oneil", "momentum_trend", "long",
        ("O'Neil CANSLIM", "IBD"),
        "long bases digest supply; breakout with volume + earnings growth marks institutional accumulation",
        "multi-week base depth <35%, pivot break on volume >=1.5x average, RS rank strong",
        "close below pivot; 7-8% hard stop (O'Neil rule)",
        ("trending", "market_uptrend"), ("late-stage bases fail", "market top drags leaders down"),
        (10, 20, 60), ("ohlcv", "fundamentals"), "breadth_confirmed_breakout", "detect_base_breakout",
    ),
    _setup(
        "vcp_contraction", "momentum_trend", "long",
        ("Minervini SEPA/VCP",),
        "successive volatility contractions show supply drying up; the final pivot has low-risk asymmetry",
        "sequence of tightening pullbacks (each shallower), volume drying, then pivot break",
        "undercut of last contraction low",
        ("trending",), ("contraction resolves down in weak markets",),
        (10, 20), ("ohlcv",), "breadth_confirmed_breakout", "detect_vcp",
    ),
    _setup(
        "pyramiding_winners", "momentum_trend", "either",
        ("Livermore — Reminiscences", "turtle add rules"),
        "concentrating into confirmed winners exploits trend persistence while initial risk stays fixed",
        "add on each favorable N-ATR move from entry; never add to losers",
        "trail stop below last add; exit all on trend break",
        ("trending",), ("adds raise average cost into the reversal",),
        (10, 20, 60), ("ohlcv",), "crash_aware_momentum", "detect_pyramid_context",
    ),
    _setup(
        "rs_line_leadership", "momentum_trend", "long",
        ("O'Neil/IBD relative-strength line",),
        "RS line making new highs BEFORE price marks institutional accumulation in leaders",
        "symbol/benchmark ratio at N-day high while price is not yet",
        "RS line rolls over below its own trend",
        ("trending", "market_uptrend"), ("leadership rotates",),
        (10, 20), ("ohlcv", "benchmark_ohlcv"), "breadth_confirmed_breakout", "detect_rs_leadership",
    ),
    _setup(
        "breadth_thrust", "macro_regime", "long",
        ("Zweig breadth thrust",),
        "rare surges from oversold breadth to overwhelming advances mark major bottoms (demand shock)",
        "advance ratio swings from <40% to >61.5% within 10 sessions",
        "thrust fails if breadth recedes within a month",
        ("panic_bottom", "vol_expansion"), ("bear-market rallies fake it",),
        (20, 60), ("universe_breadth",), "state_conditioned_factor_timing", "detect_breadth_thrust",
    ),
    _setup(
        "golden_cross_regime", "macro_regime", "either",
        ("classic 50/200 regime overlay; documented timing literature"),
        "long-horizon MA crosses crudely separate trending regimes; best as a FILTER not a signal",
        "50d SMA crosses 200d (golden/death) — gates other setups' direction",
        "opposite cross",
        ("any",), ("whipsaws in sideways decades", "lag at turns"),
        (60,), ("ohlcv",), "state_conditioned_factor_timing", "detect_golden_cross_state",
    ),
    _setup(
        "momentum_crash_guard", "momentum_trend", "guard",
        ("Daniel-Moskowitz 2016",),
        "momentum crashes in panic rebounds: after big drawdowns + vol spikes, losers snap back violently",
        "GUARD: suppress momentum entries when market is <-20% off high AND vol percentile >80",
        "guard lifts when stress normalizes",
        ("panic_bottom",), ("guard misses slow-motion reversals",),
        (5, 10), ("ohlcv", "benchmark_ohlcv"), "crash_aware_momentum", "detect_crash_guard_state",
    ),
    _setup(
        "pead_drift", "event_driven", "either",
        ("Ball-Brown 1968", "Bernard-Thomas 1989"),
        "prices underreact to earnings surprises; drift persists ~60 days in surprise direction",
        "standardized earnings surprise in top/bottom decile; enter next session, drift with it",
        "next earnings event; drift stalls",
        ("any",), ("edge decayed post-publication; costs on small caps",),
        (20, 60), ("earnings_events", "ohlcv"), "quality_revision_compounder", "",
    ),
    # ------------------------------------------------------------------ #
    # MEAN REVERSION
    # ------------------------------------------------------------------ #
    _setup(
        "short_term_reversal", "mean_reversion", "either",
        ("Lehmann 1990", "Jegadeesh 1990"),
        "1-week extreme moves partially reverse (liquidity provision premium)",
        "fade top/bottom weekly-return extremes; strongest in high-vol names",
        "5-10 sessions or reversal completes; momentum regime overrides",
        ("choppy", "high_vol"), ("real news doesn't reverse", "costs eat the small edge"),
        (2, 5), ("ohlcv",), "relative_value_reversion", "detect_short_term_reversal",
    ),
    _setup(
        "oversold_quality_pullback", "mean_reversion", "long",
        ("practitioner canon: buy quality dips in uptrends",),
        "temporary flow-driven dips in structurally strong names revert to trend",
        "uptrend intact (above 200d) + short-term oversold (RSI<30 / lower band)",
        "trend break below 200d invalidates the premise",
        ("trending",), ("catching a real breakdown disguised as a dip",),
        (5, 10, 20), ("ohlcv",), "relative_value_reversion", "detect_quality_pullback",
    ),
    _setup(
        "bollinger_snapback", "mean_reversion", "either",
        ("Bollinger; band-reversion literature",),
        "2-sigma band tags in NON-trending regimes revert to the mean",
        "close beyond 2-sigma band while ADX/trend measure is LOW",
        "mean touch or trend measure turns up (band-walk = do not fade)",
        ("choppy",), ("band-walking trends destroy faders",),
        (2, 5, 10), ("ohlcv",), "relative_value_reversion", "detect_band_snapback",
    ),
    _setup(
        "long_horizon_overreaction", "mean_reversion", "either",
        ("De Bondt-Thaler 1985",),
        "3-5 year extreme losers beat extreme winners (overreaction + risk premia)",
        "rank on trailing 3-5y return extremes; hold contrarian for months",
        "multi-quarter horizon; fundamental confirmation preferred",
        ("any",), ("value traps; overlaps distress risk"),
        (60,), ("ohlcv",), "relative_value_reversion", "detect_long_horizon_reversal",
    ),
    _setup(
        "pairs_spread_reversion", "mean_reversion", "market_neutral",
        ("Gatev-Goetzmann-Rouwenhorst 2006", "stat-arb canon"),
        "cointegrated pairs' spreads revert; hedged both ways (relative-value premium)",
        "spread z>2 on a stationarity-screened pair: short rich leg, long cheap leg",
        "z reverts toward 0; STRUCTURAL BREAK exits immediately",
        ("choppy", "low_vol"), ("cointegration breaks (the classic blowup)", "crowding"),
        # data-gapped until a governed, stationarity-screened pair universe exists
        (5, 10, 20), ("ohlcv", "pair_universe"), "relative_value_reversion", "",
    ),
    _setup(
        "big_mover_fade", "mean_reversion", "either",
        ("short-term reversal applied to stretch extremes",),
        "biggest daily movers stretched to statistical extremes partially revert",
        "top-N |daily move| AND (RSI/z-score/band extreme) against the move",
        "reversion to 20d mean or continuation invalidates (competing hypothesis wins)",
        ("choppy", "high_vol"), ("momentum regime: winners keep running",),
        (2, 5, 10), ("ohlcv",), "relative_value_reversion", "detect_big_mover_dual",
    ),
    _setup(
        "big_mover_momentum", "momentum_trend", "either",
        ("gap/news underreaction; O'Neil follow-through",),
        "biggest movers WITH trend alignment, range hold, and participation continue (underreaction)",
        "top-N |daily move| AND move aligned with trend AND strong close location AND volume confirm",
        "close back through the move's midpoint; participation dies",
        ("trending", "vol_expansion"), ("exhaustion move marks the top",),
        (2, 5, 10), ("ohlcv",), "breadth_confirmed_breakout", "detect_big_mover_dual",
    ),
    _setup(
        "panic_capitulation_rebound", "mean_reversion", "long",
        ("selling-climax canon; Zweig; Daniel-Moskowitz rebound state",),
        "capitulation (vol spike + washout breadth + gap down) exhausts sellers; sharp rebounds follow",
        "market -N% in M days + vol percentile >90 + washout day (huge range, close off lows)",
        "rebound window ~2-4 weeks; lower low invalidates",
        ("panic_bottom",), ("catching knives in real crises",),
        (5, 10, 20), ("ohlcv", "benchmark_ohlcv"), "volatility_regime_transition", "detect_capitulation",
    ),
    # ------------------------------------------------------------------ #
    # VALUE / QUALITY / FUNDAMENTAL
    # ------------------------------------------------------------------ #
    _setup(
        "deep_value_net_net", "value_quality", "long",
        ("Graham net-nets",),
        "price below net current asset value = margin of safety; liquidation floor",
        "market cap < 2/3 * (current assets - total liabilities)",
        "price approaches NCAV; thesis breaks on cash burn",
        ("any",), ("value traps burning the float", "modern scarcity of net-nets"),
        (60,), ("fundamentals",), "quality_revision_compounder", "",
    ),
    _setup(
        "value_composite", "value_quality", "either",
        ("Graham-Dodd", "Fama-French HML", "O'Shaughnessy What Works"),
        "cheap composites (E/P, B/P, CF/P, S/P) outperform expensive over long horizons (risk + behavior)",
        "top-decile composite cheapness vs sector; short expensive junk (optionally)",
        "multi-quarter rebalance discipline",
        ("any",), ("decade-long droughts (2010s)", "value traps"),
        (60,), ("fundamentals",), "quality_revision_compounder", "",
    ),
    _setup(
        "quality_profitability", "value_quality", "long",
        ("Novy-Marx 2013", "AQR QMJ"),
        "gross profitability predicts returns like value but negatively correlated with it",
        "top-decile gross profits/assets, tilted against junk",
        "quarterly refresh; deterioration exits",
        ("any",), ("quality crowding richens the factor",),
        (60,), ("fundamentals",), "quality_revision_compounder", "",
    ),
    _setup(
        "piotroski_f_score", "value_quality", "long",
        ("Piotroski 2000",),
        "9-point fundamental improvement score separates winners inside the cheap-book universe",
        "F-score >= 8 within top-quintile book/market",
        "annual refresh; score decay exits",
        ("any",), ("small/illiquid tilt inflates paper results",),
        (60,), ("fundamentals",), "quality_revision_compounder", "",
    ),
    _setup(
        "magic_formula", "value_quality", "long",
        ("Greenblatt — Little Book That Beats the Market",),
        "combined ranks of earnings yield + return on capital buy good businesses cheap",
        "top combined-rank names, annual rebalance",
        "annual; behavioral discipline is the real edge",
        ("any",), ("tracking-error abandonment (documented user failure mode)",),
        (60,), ("fundamentals",), "quality_revision_compounder", "",
    ),
    _setup(
        "fundamental_rot_short", "value_quality", "short",
        ("Chanos", "existing DOPEY short-screen lane"),
        "extreme valuation + deteriorating fundamentals (margins, FCF, dilution) precede de-ratings",
        "valuation extreme AND >=3 rot flags (already implemented in the fundamentals lane)",
        "puts-only expression per constitution; de-rating or thesis break",
        ("vol_expansion", "risk_off"), ("bubbles outlast solvency; squeezes"),
        (20, 60), ("fundamentals", "ohlcv"), "quality_revision_compounder", "detect_rot_short_context",
    ),
    _setup(
        "value_momentum_combo", "value_quality", "either",
        ("Asness-Moskowitz-Pedersen — Value and Momentum Everywhere",),
        "value and momentum are negatively correlated premia; the combo's Sharpe beats either alone",
        "joint rank: cheap AND improving beats cheap-alone and hot-alone",
        "factor-level rebalance",
        ("any",), ("both legs crash together in liquidity events",),
        (20, 60), ("fundamentals", "ohlcv"), "state_conditioned_factor_timing", "",
    ),
    _setup(
        "insider_cluster_buying", "flow_positioning", "long",
        ("Seyhun; insider literature",),
        "clustered open-market buys by multiple executives predict abnormal returns (information)",
        ">=3 distinct insider open-market buys within a month, non-trivial size",
        "6-12 month drift horizon",
        ("any",), ("routine/plan sales pollute the signal",),
        (60,), ("insider_filings",), "quality_revision_compounder", "",
    ),
    _setup(
        "buyback_announcement_drift", "event_driven", "long",
        ("Ikenberry-Lakonishok-Vermaelen 1995",),
        "buyback announcements drift upward for months, strongest in cheap names (signal + flow)",
        "announced repurchase + value tilt",
        "multi-quarter drift horizon",
        ("any",), ("leverage-funded buybacks in downturns",),
        (60,), ("corporate_events",), "quality_revision_compounder", "",
    ),
    _setup(
        "spinoff_orphan", "event_driven", "long",
        ("Greenblatt — You Can Be a Stock Market Genius",),
        "spun-off entities face forced selling by index/mandate holders, creating mispricing",
        "recent spinoff + post-forced-selling stabilization",
        "6-24 month realization horizon",
        ("any",), ("garbage-barge spinoffs loaded with debt",),
        (60,), ("corporate_events",), "quality_revision_compounder", "",
    ),
    # ------------------------------------------------------------------ #
    # VOLATILITY
    # ------------------------------------------------------------------ #
    _setup(
        "variance_risk_premium", "volatility", "short_vol",
        ("Carr-Wu", "AQR VRP research"),
        "implied vol systematically exceeds realized; harvesting the gap is a documented premium",
        "sell richly-priced variance — TOPOLOGY-BLOCKED: v1 permits no naked sell-bearing structures",
        "registered honestly as blocked; expressible only via defined-risk verticals if ever",
        ("low_vol",), ("short-vol blowups (Feb 2018); tail dwarfs carry"),
        (10, 20), ("chains",), "volatility_regime_transition", "",
    ),
    _setup(
        "vol_regime_transition", "volatility", "either",
        ("existing DOPEY VIX term-structure lane", "change-point literature"),
        "contango/backwardation flips mark regime transitions that re-price everything",
        "term-structure state flip + realized-vol percentile confirmation",
        "state reverts; positions re-gated by new regime",
        ("vol_expansion",), ("false flips in chop",),
        (2, 5, 10), ("vix_term_structure", "ohlcv"), "volatility_regime_transition", "detect_vol_regime_shift",
    ),
    _setup(
        "earnings_iv_crush_avoidance", "volatility", "guard",
        ("existing DOPEY earnings-blackout lane",),
        "long premium into earnings pays peak IV that crushes on the print — a known negative edge",
        "GUARD: block long-premium entries <=3 days before earnings (implemented)",
        "guard lifts post-print",
        ("any",), ("occasionally skips a genuine pre-earnings drift",),
        (2, 5), ("earnings_events", "chains"), "risk_controlled_abstention", "",
    ),
    _setup(
        "gamma_squeeze_flow", "flow_positioning", "long",
        ("dealer-positioning literature", "existing DOPEY GEX lane"),
        "negative dealer gamma forces hedging that amplifies moves; call-buying cascades self-reinforce",
        "negative GEX + spot above gamma flip + call-volume surge",
        "gamma normalizes; flow reverses violently",
        ("vol_expansion",), ("squeezes end in air pockets both ways",),
        (2, 5), ("chains", "gex_lane"), "volatility_regime_transition", "detect_gamma_squeeze_context",
    ),
    _setup(
        "low_vol_anomaly", "volatility", "long",
        ("Haugen-Baker", "Frazzini-Pedersen betting-against-beta"),
        "low-beta/low-vol names outperform risk-adjusted (leverage constraints + lottery demand)",
        "overweight bottom-quintile trailing vol, underweight top",
        "quarterly refresh",
        ("any",), ("rate-sensitive crowding; underperforms melt-ups"),
        (60,), ("ohlcv",), "state_conditioned_factor_timing", "detect_low_vol_rank",
    ),
    _setup(
        "vol_expansion_coil", "volatility", "either",
        ("NR7/inside-bar canon", "existing DOPEY screener archetype"),
        "volatility clusters: compressed ranges precede expansions; direction decided by the break",
        "range percentile bottom decile (NR7-style) + squeeze; enter on break direction",
        "expansion realizes or coil re-forms",
        ("any",), ("break direction is a coin flip until confirmed",),
        (2, 5, 10), ("ohlcv",), "volatility_regime_transition", "detect_vol_coil",
    ),
    _setup(
        "bb_squeeze_breakout", "volatility", "either",
        ("Bollinger — the Squeeze", "Carter TTM squeeze (variant)"),
        "multi-session Bollinger bandwidth compression marks temporary supply/demand"
        " equilibrium; the first CONFIRMED band break with participation tends to open"
        " the expansion leg. Distinct from vol_expansion_coil: persistent multi-day"
        " band-width state, not a single narrowest-range day, and each detection"
        " resolves a direction so forward settlement can actually grade it",
        "trailing 20d bandwidth in the bottom percentile of its own lookback window"
        " (the squeeze), then close breaks the prior session's upper band (long) or"
        " lower band (short) on above-average volume",
        "close back inside the bands; bandwidth percentile normalizes; time stop",
        ("any", "vol_expansion"),
        (
            "first break head-fakes against the prevailing trend",
            "compression predicts RANGE expansion, not direction - the directional"
            " claim must be earned separately (see compression_expansion_study)",
        ),
        (2, 5, 10), ("ohlcv",), "volatility_regime_transition", "detect_bb_squeeze",
    ),
    # ------------------------------------------------------------------ #
    # FLOW / POSITIONING / STRUCTURAL
    # ------------------------------------------------------------------ #
    _setup(
        "short_squeeze_mechanics", "flow_positioning", "long",
        ("squeeze literature; documented episodes",),
        "high short interest + catalyst + illiquidity forces covering cascades",
        "actual open SI/float + days-to-cover extreme, then independent price-strength trigger",
        "covering exhausts; retraces are violent",
        ("vol_expansion",), ("being early = being the squeezed",),
        (2, 5, 10), ("actual_short_interest_lane", "ohlcv"), "volatility_regime_transition", "detect_squeeze_context",
    ),
    _setup(
        "index_rebalance_flow", "flow_positioning", "either",
        ("index-effect literature",),
        "forced index fund flows around add/delete events create predictable pressure and reversal",
        "announced index change: front-run flow, fade post-effective distortion",
        "event-anchored exits",
        ("any",), ("effect has compressed as arbs crowded it",),
        (2, 5), ("index_events",), "relative_value_reversion", "",
    ),
    _setup(
        "congressional_following", "flow_positioning", "long",
        ("STOCK Act disclosure literature", "existing DOPEY congress lane"),
        "disclosed congressional purchases historically preceded abnormal returns (information proxy)",
        "clustered notable purchases (lane already distills; 45-day lag stamped)",
        "multi-month horizon; lag caveat is structural",
        ("any",), ("disclosure lag kills short-horizon value",),
        (60,), ("congress_lane",), "quality_revision_compounder", "detect_congress_cluster",
    ),
    _setup(
        "cot_positioning_extreme", "flow_positioning", "either",
        ("CFTC COT literature", "existing DOPEY COT lane"),
        "commercial/speculator positioning extremes mark sentiment exhaustion at multi-week horizons",
        "COT net z-score beyond ±2 (lane computes); fade speculative extremes",
        "z reverts toward mean",
        ("any",), ("extremes extend for months in strong trends",),
        (20, 60), ("cot_lane",), "state_conditioned_factor_timing", "detect_cot_extreme",
    ),
    _setup(
        "turn_of_month_flow", "flow_positioning", "long",
        ("turn-of-month literature (Lakonishok-Smidt)",),
        "pension/401k contribution flows cluster at month boundaries",
        "long bias final trading day through first 3 of new month",
        "calendar-anchored exit",
        ("any",), ("small edge; costs and crowding decay",),
        (2, 5), ("ohlcv",), "state_conditioned_factor_timing", "detect_turn_of_month",
    ),
    _setup(
        "crowded_attention_fade", "flow_positioning", "short",
        ("attention literature (Da-Engelberg-Gao)", "existing DOPEY screener archetype"),
        "retail attention spikes mark demand exhaustion; hype peaks precede weak forward returns",
        "attention z>=2 (Wikipedia lane) + price extension",
        "attention normalizes; puts-only expression",
        ("vol_expansion",), ("memes can double again before fading",),
        (5, 10, 20), ("attention_lane", "ohlcv"), "relative_value_reversion", "detect_attention_fade",
    ),
    _setup(
        "tax_loss_rebound", "flow_positioning", "long",
        ("January-effect literature (Roll; Reinganum)",),
        "December tax-loss selling depresses losers; forced pressure lifts in January",
        "beaten-down names late December, hold through January",
        "calendar-anchored",
        ("any",), ("effect has weakened; concentrated in illiquid smalls",),
        (10, 20), ("ohlcv",), "relative_value_reversion", "detect_tax_loss_window",
    ),
    # ------------------------------------------------------------------ #
    # MACRO / REGIME
    # ------------------------------------------------------------------ #
    _setup(
        "liquidity_impulse_risk", "macro_regime", "either",
        ("Druckenmiller: liquidity drives markets", "existing DOPEY WALCL-RRP-TGA lane"),
        "central-bank net liquidity expansion lifts risk assets; contraction drains them",
        "liquidity impulse state (lane computes flooding/draining) gates aggression",
        "impulse flips",
        ("any",), ("fiscal offsets; regime dependence"),
        (20, 60), ("liquidity_lane",), "state_conditioned_factor_timing", "detect_liquidity_state",
    ),
    _setup(
        "reflexivity_divergence", "macro_regime", "either",
        ("Soros — Alchemy of Finance",),
        "price->fundamentals feedback loops overshoot both ways; divergence between trend and fundamentals marks the boom-bust phase",
        "PROXY: price trend accelerating while fundamental trend decelerates (or vice versa) flags reflexive phase",
        "phase transition (trend break) is the actionable moment",
        ("vol_expansion",), ("timing the turn is the whole difficulty",),
        (20, 60), ("ohlcv", "fundamentals"), "state_conditioned_factor_timing", "",
    ),
    _setup(
        "sector_rotation_cycle", "macro_regime", "either",
        ("business-cycle rotation canon", "Murphy intermarket analysis"),
        "leadership rotates with the cycle (early: discretionary/financials; late: energy/staples)",
        "sector relative-strength ranks vs cycle-state estimate (rates, curve, breadth)",
        "leadership handoff",
        ("any",), ("cycle stage identification is noisy",),
        (20, 60), ("sector_ohlcv", "macro_lanes"), "state_conditioned_factor_timing", "detect_sector_rotation",
    ),
    _setup(
        "risk_on_off_confirmation", "macro_regime", "guard",
        ("cross-asset canon", "existing DOPEY cross-asset mesh"),
        "equity signals confirmed by credit, rates, dollar, and vol agree more often than solo signals",
        "GUARD/TILT: cross-asset stress composite gates equity aggression (mesh computes)",
        "stress normalizes",
        ("any",), ("correlations flip in crises",),
        (5, 10, 20), ("cross_asset_lanes",), "risk_controlled_abstention", "detect_cross_asset_state",
    ),
    _setup(
        "pre_fomc_drift", "macro_regime", "long",
        ("Lucca-Moench 2015",),
        "documented pre-FOMC announcement equity drift (uncertainty-premium resolution)",
        "long bias 24h before scheduled FOMC announcements",
        "announcement-anchored exit",
        ("any",), ("post-publication decay; regime dependence"),
        (2,), ("fomc_calendar", "ohlcv"), "state_conditioned_factor_timing", "",
    ),
    # ------------------------------------------------------------------ #
    # EVENT-DRIVEN (additional)
    # ------------------------------------------------------------------ #
    _setup(
        "analyst_revision_momentum", "event_driven", "either",
        ("estimate-revision literature (Zacks)",),
        "clustered estimate revisions drift; analysts herd and under-adjust",
        "revision breadth extreme (primitive exists: estimate_revision)",
        "revision impulse fades",
        ("any",), ("revisions lag price as often as lead",),
        (20, 60), ("analyst_estimates",), "quality_revision_compounder", "",
    ),
    _setup(
        "merger_arb_spread", "event_driven", "market_neutral",
        ("merger-arb canon (documented insurance premium)",),
        "definitive-deal spreads price deal-break risk; harvesting them is selling event insurance",
        "definitive deal + financing certainty; spread vs break-risk assessment",
        "close or break; sized to survive breaks",
        ("any",), ("regulatory breaks cluster in stress",),
        (20, 60), ("deal_events",), "risk_controlled_abstention", "",
    ),
)


def playbook_by_family() -> dict[str, tuple[PlaybookSetup, ...]]:
    families: dict[str, list[PlaybookSetup]] = {}
    for setup in PLAYBOOK:
        families.setdefault(setup["family"], []).append(setup)
    return {family: tuple(entries) for family, entries in sorted(families.items())}


def computable_setups() -> tuple[PlaybookSetup, ...]:
    """Setups with an implemented detector for currently governed data."""
    return tuple(s for s in PLAYBOOK if s["computable_detector"])


def data_gapped_setups() -> tuple[PlaybookSetup, ...]:
    """Honestly registered setups awaiting data lanes or topology permissions."""
    return tuple(s for s in PLAYBOOK if not s["computable_detector"])


def playbook_summary() -> dict[str, object]:
    families = playbook_by_family()
    return {
        "artifact_type": "strategy_playbook_summary",
        "playbook_version": "dopey-strategy-playbook-v1",
        "setup_count": len(PLAYBOOK),
        "family_counts": {family: len(entries) for family, entries in families.items()},
        "computable_count": len(computable_setups()),
        "data_gapped_count": len(data_gapped_setups()),
        "all_entries_unvalidated": all(s["evidence_status"] == _U for s in PLAYBOOK),
        "trust_must_be_earned_via_forward_settlement": True,
        "publication_decay_expected": "McLean-Pontiff 2016",
        "profit_or_edge_claimed": False,
        "paper_only": True,
        "live_blocked": True,
    }
