"""Primary-source doctrines for institutional-grade research governance.

The registry captures public, testable principles rather than reputations or
proprietary-method claims.  A source can inspire a check, but never becomes DOPEY
edge evidence by citation alone.
"""

from __future__ import annotations

from typing import Final

from .schema import DoctrineSpec, InstitutionalSourceRecord


SUPPORTED_INSTRUMENTS: Final[frozenset[str]] = frozenset(
    {
        "equity",
        "leveraged_etf",
        "leaps",
        "short_term_option",
        "zero_dte_option",
    }
)


INSTITUTIONAL_SOURCES: Final[tuple[InstitutionalSourceRecord, ...]] = (
    {
        "source_id": "aqr-value-momentum-everywhere",
        "title": "Value and Momentum Everywhere",
        "url": "https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere",
        "source_type": "manager_authored_primary_research",
        "published_at": "2013-06-01",
        "adopted_capability": "factor decomposition and correlated-evidence discounting",
        "evidence_restriction": "published factor results are not DOPEY forward evidence and do not prove transfer to another instrument",
    },
    {
        "source_id": "aqr-century-trend",
        "title": "A Century of Evidence on Trend-Following Investing",
        "url": "https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing",
        "source_type": "manager_authored_primary_research",
        "published_at": "2017-11-01",
        "adopted_capability": "replication across disjoint eras, markets, and signal horizons",
        "evidence_restriction": "futures and forwards evidence cannot be assumed to transfer to stocks or options",
    },
    {
        "source_id": "aqr-factor-premia-oos",
        "title": "How Do Factor Premia Vary Over Time? A Century of Evidence",
        "url": "https://www.aqr.com/Insights/Research/Journal-Article/How-Do-Factor-Premia-Vary-Over-Time-A-Century-of-Evidence",
        "source_type": "manager_authored_primary_research",
        "published_at": "2019-07-02",
        "adopted_capability": "discovery-to-validation shrinkage and lag-and-cost realism",
        "evidence_restriction": "reported average out-of-sample degradation is not a universal haircut",
    },
    {
        "source_id": "bridgewater-all-weather",
        "title": "The All Weather Story",
        "url": "https://www.bridgewater.com/research-and-insights/the-all-weather-story",
        "source_type": "manager_primary_research",
        "published_at": "2012-01-01",
        "adopted_capability": "separate cash, beta, and alpha and expose growth-inflation risk",
        "evidence_restriction": "risk balancing is not alpha and does not justify leveraged short-horizon sizing",
    },
    {
        "source_id": "man-ahl-speed-trend",
        "title": "The Need for Speed in Trend-Following Strategies",
        "url": "https://www.man.com/insights/need-for-speed-trend-following",
        "source_type": "manager_primary_research",
        "published_at": "2023-01-04",
        "adopted_capability": "horizon-specific turnover, cost, and crisis-response evaluation",
        "evidence_restriction": "proprietary simulations and execution performance are not reusable parameters",
    },
    {
        "source_id": "man-ahl-market-mix",
        "title": "Trend Following: The Optimal Market Mix",
        "url": "https://www.man.com/insights/trend-following-optimal-market-mix",
        "source_type": "manager_primary_research",
        "published_at": "2026-01-29",
        "adopted_capability": "marginal independent-driver and capacity testing for universe expansion",
        "evidence_restriction": "instrument count is not evidence of diversification",
    },
    {
        "source_id": "dimensional-high-bar",
        "title": "Setting a High Bar for Research",
        "url": "https://www.dimensional.com/us-en/insights/setting-a-high-bar-for-research",
        "source_type": "manager_primary_research",
        "published_at": "2024-04-30",
        "adopted_capability": "economic rationale, temporal replication, market replication, and live capturability",
        "evidence_restriction": "a sensible narrative cannot rescue failed replication or implementation",
    },
    {
        "source_id": "dimensional-variant-discipline",
        "title": "The Right Thing, Not the Easy Thing",
        "url": "https://www.dimensional.com/us-en/insights/the-right-thing-not-the-easy-thing",
        "source_type": "manager_primary_research",
        "published_at": "2020-11-16",
        "adopted_capability": "retain the full variant family and penalize selection complexity",
        "evidence_restriction": "reporting a surviving variant alone understates false-discovery risk",
    },
    {
        "source_id": "two-sigma-regime-modeling",
        "title": "A Machine Learning Approach to Regime Modeling",
        "url": "https://www.twosigma.com/articles/a-machine-learning-approach-to-regime-modeling/",
        "source_type": "manager_primary_research",
        "published_at": "undated_current_article_retrieved_2026-07-21",
        "adopted_capability": "probabilistic regime diagnostics with uncertainty and prospective validation",
        "evidence_restriction": "unsupervised clusters and retrospective labels are not directional forecasts",
    },
    {
        "source_id": "two-sigma-reverse-optimization",
        "title": "Estimating Global Investor Views with Reverse Optimization",
        "url": "https://www.twosigma.com/articles/estimating-global-investor-views-with-reverse-optimization/",
        "source_type": "manager_primary_research",
        "published_at": "undated_current_article_retrieved_2026-07-21",
        "adopted_capability": "invert allocations into explicit implied return and risk assumptions",
        "evidence_restriction": "implied expectations are an audit surface rather than truth or independent alpha",
    },
    {
        "source_id": "two-sigma-human-intuition-ml",
        "title": "Why Human Intuition Is Essential in Machine Learning",
        "url": "https://www.twosigma.com/articles/why-human-intuition-is-essential-in-machine-learning/",
        "source_type": "manager_primary_research",
        "published_at": "undated_current_article_retrieved_2026-07-21",
        "adopted_capability": "feature-budget discipline and separation of predictive from causal questions",
        "evidence_restriction": "more features and predictive association do not establish a causal execution policy",
    },
    {
        "source_id": "berkshire-1999-letter",
        "title": "Berkshire Hathaway 1999 Shareholder Letter",
        "url": "https://www.berkshirehathaway.com/letters/final1999pdf.pdf",
        "source_type": "owner_letter",
        "published_at": "2000-03-01",
        "adopted_capability": "valuation ranges, price-dependent capital allocation, and liquidity priority",
        "evidence_restriction": "Berkshire scale, taxes, control rights, and horizon do not transfer to short-dated trading",
    },
    {
        "source_id": "berkshire-2023-letter",
        "title": "Berkshire Hathaway 2023 Shareholder Letter",
        "url": "https://www.berkshirehathaway.com/letters/2023ltr.pdf",
        "source_type": "owner_letter",
        "published_at": "2024-02-24",
        "adopted_capability": "durable economics, incremental capital returns, inactivity baseline, and permanent-loss avoidance",
        "evidence_restriction": "quality and patience are hypotheses to test, not permission to ignore falsifiers",
    },
    {
        "source_id": "oaktree-prepare-cycles",
        "title": "You Can't Predict. You Can Prepare.",
        "url": "https://www.oaktreecapital.com/docs/default-source/memos/2001-11-20-you-cant-predict-you-can-prepare.pdf?sfvrsn=bc00f65_6",
        "source_type": "manager_memo",
        "published_at": "2001-11-20",
        "adopted_capability": "uncertain cycle state, scenarios, and preparation rather than turn-date prediction",
        "evidence_restriction": "a cycle label is not a deterministic market forecast",
    },
    {
        "source_id": "oaktree-risk",
        "title": "Risk",
        "url": "https://www.oaktreecapital.com/docs/default-source/memos/2006-01-19-risk.pdf?sfvrsn=afbc0f65_6",
        "source_type": "manager_memo",
        "published_at": "2006-01-19",
        "adopted_capability": "scenario, illiquidity, correlation, domino, and permanent-loss risk mapping",
        "evidence_restriction": "volatility is not a complete risk model",
    },
    {
        "source_id": "soros-reflexivity-address",
        "title": "IIF Spring Membership Meeting Address",
        "url": "https://www.georgesoros.com/2010/06/10/iif_spring_membership_meeting_address_june_10_2010/",
        "source_type": "investor_primary_address",
        "published_at": "2010-06-10",
        "adopted_capability": "testable price-fundamental feedback graphs and reversal conditions",
        "evidence_restriction": "momentum alone is not evidence of a reflexive causal mechanism",
    },
    {
        "source_id": "druckenmiller-hard-lessons",
        "title": "Hard Lessons with Stanley Druckenmiller",
        "url": "https://www.morganstanley.com/insights/videos/hard-lessons/duquesne-stan-druckenmiller-iliana-bouzali",
        "source_type": "first_party_interview",
        "published_at": "2026-02-27",
        "adopted_capability": "expectation deltas, causal catalysts, market confirmation, and named reversal evidence",
        "evidence_restriction": "intuition and personal conviction must be converted into observable hypotheses",
    },
    {
        "source_id": "finra-geared-etps",
        "title": "The Lowdown on Leveraged and Inverse Exchange-Traded Products",
        "url": "https://www.finra.org/investors/insights/lowdown-leveraged-and-inverse-exchange-traded-products",
        "source_type": "regulator_guidance",
        "published_at": "2022-07-28",
        "adopted_capability": "daily-reset, path-dependence, leverage, volatility, fee, and holding-period gates",
        "evidence_restriction": "an underlying proxy is not product-level evidence",
    },
    {
        "source_id": "occ-options-disclosure-2024",
        "title": "Characteristics and Risks of Standardized Options",
        "url": "https://www.theocc.com/getContentAsset/a151a9ae-d784-4a15-bdeb-23a029f50b70/dfc3d011-8f63-43f6-9ed8-4b444333a1d0/riskstoc.pdf",
        "source_type": "clearinghouse_disclosure",
        "published_at": "2024-06-01",
        "adopted_capability": "expiration, exercise, assignment, adjustment, and total-premium-loss lifecycle checks",
        "evidence_restriction": "option payoff diagrams do not establish tradable edge or executable prices",
    },
    {
        "source_id": "cboe-zero-dte-decoded",
        "title": "0DTEs Decoded: Positioning, Trends, and Market Impact",
        "url": "https://www.cboe.com/insights/posts/0-dt-es-decoded-positioning-trends-and-market-impact",
        "source_type": "exchange_primary_analysis",
        "published_at": "2025-05-07",
        "adopted_capability": "same-day expiry, capped-loss structure, and market-quality-specific evidence requirements",
        "evidence_restriction": "SPX aggregate market quality does not transfer to every symbol, contract, broker, or timestamp",
    },
    {
        "source_id": "cboe-equity-leaps",
        "title": "Equity LEAPS Options Product Specifications",
        "url": "https://www.cboe.com/tradable_products/equity_indices/leaps_options/specifications",
        "source_type": "exchange_product_specification",
        "published_at": "undated_current_specification_retrieved_2026-07-21",
        "adopted_capability": "long-dated contract identity, maturity, adjustment, and exercise-aware research",
        "evidence_restriction": "long maturity does not make a contract liquid, cheap, or equity-equivalent",
    },
    {
        "source_id": "sec-execution-quality",
        "title": "Execution Quality Statistics",
        "url": "https://www.sec.gov/investor/pubs/exquality.htm",
        "source_type": "regulator_guidance",
        "published_at": "undated_guidance_retrieved_2026-07-21",
        "adopted_capability": "arrival-quote, effective-spread, price-improvement, fill-rate, and routing evaluation",
        "evidence_restriction": "commission price alone is not execution quality",
    },
    {
        "source_id": "nyfed-volatility-term-premia",
        "title": "Equity Volatility Term Premia",
        "url": "https://libertystreeteconomics.newyorkfed.org/2021/02/equity-volatility-term-premia/",
        "source_type": "central_bank_primary_analysis",
        "published_at": "2021-02-03",
        "adopted_capability": "separate volatility forecasts from time-varying volatility risk premia",
        "evidence_restriction": "implied volatility is not a pure forecast and a premium is not free alpha",
    },
    {
        "source_id": "fed-iv-heterogeneity-2026",
        "title": "Capturing Heterogeneity: Machine Learning Approaches to Implied Volatility Forecasting",
        "url": "https://www.federalreserve.gov/econres/feds/capturing-heterogeneity-machine-learning-approaches-to-implied-volatility-forecasting.htm",
        "source_type": "central_bank_working_paper",
        "published_at": "2026-07-07",
        "adopted_capability": "moneyness-and-maturity-specific interpretable volatility forecasting with out-of-sample benchmarks",
        "evidence_restriction": "published S&P 500 results require independent replication on DOPEY data",
    },
    {
        "source_id": "kelly-1956",
        "title": "A New Interpretation of Information Rate",
        "url": "https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x",
        "source_type": "original_academic_paper",
        "published_at": "1956-07-01",
        "adopted_capability": "geometric-growth framing conditional on known probabilities and odds",
        "evidence_restriction": "estimated market probabilities, changing odds, drawdown constraints, and dependence violate the simple game",
    },
    {
        "source_id": "thorp-kelly-1997",
        "title": "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market",
        "url": "https://sites.oxy.edu/lengyel/M330/thorp/paper.htm",
        "source_type": "investor_authored_primary_paper",
        "published_at": "1997-06-01",
        "adopted_capability": "growth-optimal sizing as an upper-bound research benchmark",
        "evidence_restriction": "full Kelly is not authorized sizing and parameter uncertainty must reduce exposure",
    },
)


_ALL_INSTRUMENTS: Final[tuple[str, ...]] = tuple(sorted(SUPPORTED_INSTRUMENTS))
_OPTION_INSTRUMENTS: Final[tuple[str, ...]] = (
    "leaps",
    "short_term_option",
    "zero_dte_option",
)


INSTITUTIONAL_DOCTRINES: Final[tuple[DoctrineSpec, ...]] = (
    {
        "doctrine_id": "factor_residual_independence",
        "lens_id": "systematic_independence",
        "principle": "Nominal model count is replaced by marginal independent evidence after common-factor and data-family overlap.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "factor_attribution",
            "effective_rank",
            "incremental_residual_edge",
            "correlated_lens_discount",
        ),
        "failure_modes": (
            "funding_liquidity_common_shock",
            "crowding_reversal",
            "duplicate_feature_family",
        ),
        "source_ids": ("aqr-value-momentum-everywhere", "man-ahl-market-mix"),
        "prohibited_inferences": (
            "negative_historical_correlation_equals_independence",
            "symbol_count_equals_diversification",
        ),
    },
    {
        "doctrine_id": "multi_axis_generalization",
        "lens_id": "validation",
        "principle": "A candidate must survive disjoint time, instrument, and regime axes and remain capturable after costs.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "purged_rolling_origin",
            "cross_market_replication",
            "regime_holdout",
            "forward_capture",
            "oos_degradation",
        ),
        "failure_modes": (
            "selection_bias",
            "era_concentration",
            "market_specific_artifact",
            "implementation_decay",
        ),
        "source_ids": (
            "aqr-century-trend",
            "aqr-factor-premia-oos",
            "dimensional-high-bar",
        ),
        "prohibited_inferences": (
            "broad_backtest_equals_forward_edge",
            "fixed_oos_haircut_is_universal",
        ),
    },
    {
        "doctrine_id": "variant_family_accountability",
        "lens_id": "research_governance",
        "principle": "Every attempted variant remains in the selection family and pays a false-discovery and complexity burden.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "complete_genealogy",
            "familywise_error_control",
            "complexity_budget",
            "retired_variant_visibility",
        ),
        "failure_modes": (
            "winner_only_reporting",
            "repeated_peeking",
            "mutation_gate_weakening",
        ),
        "source_ids": ("dimensional-variant-discipline",),
        "prohibited_inferences": (
            "one_oos_winner_erases_search_burden",
            "mutation_count_equals_learning",
        ),
    },
    {
        "doctrine_id": "regime_diagnostic_uncertainty",
        "lens_id": "macro_risk",
        "principle": "Regime models remain probabilistic diagnostics until untouched forward evidence establishes a stable predictive use.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "assignment_probabilities",
            "label_stability",
            "transition_uncertainty",
            "prospective_regime_validation",
            "risk_reduction_counterfactual",
        ),
        "failure_modes": (
            "retrospective_regime_naming",
            "unstable_cluster_identity",
            "directional_alpha_relabeling",
        ),
        "source_ids": ("two-sigma-regime-modeling", "oaktree-prepare-cycles"),
        "prohibited_inferences": (
            "cluster_label_equals_forecast",
            "regime_fit_equals_timing_edge",
        ),
    },
    {
        "doctrine_id": "implied_assumption_inversion",
        "lens_id": "portfolio_risk",
        "principle": "Every proposed allocation is inverted into the return, volatility, correlation, liquidity, and persistence assumptions required to justify it.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "implied_return",
            "implied_volatility",
            "implied_correlation",
            "constraint_shadow_prices",
            "assumption_perturbation_stability",
        ),
        "failure_modes": (
            "opaque_optimizer_output",
            "fragile_correlation_assumption",
            "hidden_leverage_or_liquidity_dependency",
        ),
        "source_ids": ("two-sigma-reverse-optimization", "bridgewater-all-weather"),
        "prohibited_inferences": (
            "implied_expectation_equals_truth",
            "optimizer_precision_equals_forecast_precision",
        ),
    },
    {
        "doctrine_id": "causal_feature_budget",
        "lens_id": "validation",
        "principle": "Low-signal research earns fewer effective features, and causal policy claims require causal evidence rather than predictive association.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "effective_feature_count",
            "sample_to_feature_burden",
            "feature_stability",
            "predictive_vs_causal_claim_boundary",
            "intervention_or_natural_experiment_plan",
        ),
        "failure_modes": (
            "feature_proliferation",
            "post_selection_explanation",
            "execution_policy_from_association",
        ),
        "source_ids": ("two-sigma-human-intuition-ml", "dimensional-high-bar"),
        "prohibited_inferences": (
            "more_features_equals_more_intelligence",
            "predictive_accuracy_equals_causal_improvement",
        ),
    },
    {
        "doctrine_id": "risk_environment_balance",
        "lens_id": "macro_risk",
        "principle": "Separate cash, beta, and residual alpha and expose sensitivity to growth and inflation surprises.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "cash_beta_alpha_decomposition",
            "growth_inflation_scenarios",
            "risk_contribution",
            "correlation_break_stress",
        ),
        "failure_modes": (
            "hidden_equity_beta",
            "leverage_dependency",
            "correlation_convergence",
        ),
        "source_ids": ("bridgewater-all-weather", "oaktree-risk"),
        "prohibited_inferences": (
            "risk_parity_equals_alpha",
            "low_volatility_equals_low_risk",
        ),
    },
    {
        "doctrine_id": "net_edge_capacity_surface",
        "lens_id": "implementation",
        "principle": "Gross edge is evaluated over horizon, size, spread, volatility, liquidity, urgency, and capacity before expression choice.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "arrival_quote",
            "effective_spread",
            "slippage_surface",
            "fill_probability",
            "capacity",
            "urgency_vs_decay",
        ),
        "failure_modes": (
            "gross_edge_only",
            "stale_quote",
            "unfilled_limit_selection",
            "impact_exceeds_edge",
        ),
        "source_ids": ("man-ahl-speed-trend", "sec-execution-quality"),
        "prohibited_inferences": (
            "zero_commission_equals_zero_cost",
            "patient_execution_is_always_better",
        ),
    },
    {
        "doctrine_id": "valuation_quality_range",
        "lens_id": "fundamental_value",
        "principle": "Value is a sensitivity range anchored to durable economics, incremental capital returns, and price-dependent action.",
        "applicable_instruments": ("equity", "leveraged_etf", "leaps"),
        "required_checks": (
            "bear_base_bull_value_range",
            "point_in_time_fundamentals",
            "incremental_roic",
            "cash_conversion",
            "dilution_and_leverage",
        ),
        "failure_modes": (
            "false_precision",
            "peak_cycle_quality",
            "stale_filing",
            "multiple_only_valuation",
        ),
        "source_ids": ("berkshire-1999-letter", "berkshire-2023-letter"),
        "prohibited_inferences": (
            "cheap_multiple_equals_margin_of_safety",
            "long_horizon_cancels_falsifiers",
        ),
    },
    {
        "doctrine_id": "cycle_reflexivity_catalyst",
        "lens_id": "behavioral_catalyst",
        "principle": "Cycle state and price-fundamental feedback are uncertain causal hypotheses with observable checkpoints and reversal triggers.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "expectation_delta",
            "two_way_feedback_graph",
            "causal_catalyst",
            "leading_indicators",
            "alternative_explanations",
            "transition_rule",
        ),
        "failure_modes": (
            "narrative_leakage",
            "deterministic_turn_date",
            "momentum_relabelled_reflexivity",
        ),
        "source_ids": (
            "oaktree-prepare-cycles",
            "soros-reflexivity-address",
            "druckenmiller-hard-lessons",
        ),
        "prohibited_inferences": (
            "cycle_label_equals_forecast",
            "conviction_equals_machine_evidence",
        ),
    },
    {
        "doctrine_id": "permanent_loss_liquidity",
        "lens_id": "risk",
        "principle": "Risk includes permanent loss, gap, illiquidity, correlation, financing, and forced-sale pathways, not volatility alone.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "scenario_loss",
            "gap_loss",
            "liquidity_ladder",
            "factor_concentration",
            "correlation_stress",
            "forced_sale_dependency",
        ),
        "failure_modes": (
            "hidden_tail",
            "liquidity_disappearance",
            "financing_withdrawal",
            "correlated_loss_cluster",
        ),
        "source_ids": ("oaktree-risk", "berkshire-2023-letter"),
        "prohibited_inferences": (
            "historical_volatility_bounds_loss",
            "concentration_creates_alpha",
        ),
    },
    {
        "doctrine_id": "growth_optimal_uncertainty_bound",
        "lens_id": "sizing",
        "principle": "Growth-optimal sizing is only an upper-bound research comparator and shrinks with probability, payoff, dependence, and drawdown uncertainty.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "calibrated_probability",
            "payoff_distribution",
            "parameter_uncertainty",
            "dependence_stress",
            "drawdown_constraint",
            "fractional_upper_bound",
        ),
        "failure_modes": (
            "full_kelly_on_estimates",
            "nonstationary_edge",
            "correlated_bets",
            "ruin_path",
        ),
        "source_ids": ("kelly-1956", "thorp-kelly-1997"),
        "prohibited_inferences": (
            "kelly_creates_edge",
            "backtest_win_rate_authorizes_sizing",
        ),
    },
    {
        "doctrine_id": "leveraged_product_path_authority",
        "lens_id": "instrument_fit",
        "principle": "A daily-reset leveraged product requires its own point-in-time history, path, financing, tracking, and liquidity evidence.",
        "applicable_instruments": ("leveraged_etf",),
        "required_checks": (
            "product_level_ohlcv",
            "daily_reset_path",
            "volatility_drag",
            "tracking_difference",
            "rebalance_gap",
            "product_liquidity",
        ),
        "failure_modes": (
            "proxy_only_validation",
            "holding_period_mismatch",
            "derivative_financing_change",
        ),
        "source_ids": ("finra-geared-etps",),
        "prohibited_inferences": (
            "benchmark_prediction_equals_product_edge",
            "daily_multiple_equals_multi_day_multiple",
        ),
    },
    {
        "doctrine_id": "option_quote_lifecycle",
        "lens_id": "derivatives",
        "principle": "An option hypothesis requires timestamped executable quotes, exact contract identity, liquidity, adjustment, and complete lifecycle evidence.",
        "applicable_instruments": _OPTION_INSTRUMENTS,
        "required_checks": (
            "firm_quote_timestamp",
            "bid_ask_size",
            "spread",
            "exact_contract_id",
            "adjustment_identity",
            "exercise_assignment_settlement",
        ),
        "failure_modes": (
            "zero_bid",
            "stale_or_crossed_market",
            "adjusted_contract_ambiguity",
            "expiration_state_loss",
        ),
        "source_ids": ("occ-options-disclosure-2024", "sec-execution-quality"),
        "prohibited_inferences": (
            "model_price_equals_executable_price",
            "payoff_diagram_equals_edge",
        ),
    },
    {
        "doctrine_id": "same_day_expiry_lifecycle",
        "lens_id": "expiry_risk",
        "principle": "0DTE research must model intraday gamma, theta, liquidity, exercise or cash settlement, close handling, and constitutional compatibility.",
        "applicable_instruments": ("zero_dte_option",),
        "required_checks": (
            "intraday_quote_path",
            "gamma_theta_path",
            "close_auction_or_settlement",
            "exercise_cutoff",
            "defined_max_loss",
            "constitution_compatibility",
        ),
        "failure_modes": (
            "same_day_state_gap",
            "pin_risk",
            "liquidity_cliff",
            "unplanned_exercise",
            "authority_conflict",
        ),
        "source_ids": ("cboe-zero-dte-decoded", "occ-options-disclosure-2024"),
        "prohibited_inferences": (
            "aggregate_spx_liquidity_transfers_to_contract",
            "low_premium_equals_low_risk",
        ),
    },
    {
        "doctrine_id": "long_horizon_option_state",
        "lens_id": "long_horizon_derivatives",
        "principle": "LEAPS require term-aware volatility, rates, dividends, borrow, corporate actions, liquidity, and equity-alternative comparisons.",
        "applicable_instruments": ("leaps",),
        "required_checks": (
            "term_surface",
            "rates_and_dividends",
            "borrow",
            "corporate_actions",
            "long_dated_spread",
            "risk_matched_equity_baseline",
        ),
        "failure_modes": (
            "wide_spread",
            "term_model_error",
            "dividend_error",
            "adjustment_ambiguity",
            "equity_substitution_error",
        ),
        "source_ids": ("cboe-equity-leaps", "occ-options-disclosure-2024"),
        "prohibited_inferences": (
            "long_maturity_equals_liquidity",
            "leaps_equals_stock_replacement",
        ),
    },
    {
        "doctrine_id": "volatility_forecast_risk_premium",
        "lens_id": "volatility",
        "principle": "Implied volatility is decomposed into forecast and risk-premium components with state, moneyness, and maturity heterogeneity.",
        "applicable_instruments": _OPTION_INSTRUMENTS,
        "required_checks": (
            "realized_volatility_forecast",
            "risk_premium_decomposition",
            "moneyness_partition",
            "maturity_partition",
            "stress_oos_benchmark",
        ),
        "failure_modes": (
            "iv_as_pure_forecast",
            "surface_pooling_bias",
            "premium_sign_change",
            "stress_regime_failure",
        ),
        "source_ids": ("nyfed-volatility-term-premia", "fed-iv-heterogeneity-2026"),
        "prohibited_inferences": (
            "implied_minus_realized_equals_free_alpha",
            "single_surface_model_is_uniformly_best",
        ),
    },
    {
        "doctrine_id": "immutable_thesis_correction",
        "lens_id": "learning",
        "principle": "Freeze the original thesis and attribute every reversal or re-underwrite to a preregistered falsifier or named new fact.",
        "applicable_instruments": _ALL_INSTRUMENTS,
        "required_checks": (
            "immutable_original_thesis",
            "named_falsifiers",
            "decision_to_correction_latency",
            "alternative_explanation",
            "no_thesis_rewrite",
        ),
        "failure_modes": (
            "hindsight_rewrite",
            "noise_chasing",
            "unattributed_reversal",
            "failed_trial_erasure",
        ),
        "source_ids": ("berkshire-2023-letter", "druckenmiller-hard-lessons"),
        "prohibited_inferences": (
            "long_term_means_never_change",
            "fast_reversal_without_new_evidence_is_adaptation",
        ),
    },
)


def institutional_source_ids() -> frozenset[str]:
    return frozenset(record["source_id"] for record in INSTITUTIONAL_SOURCES)


def doctrine_ids() -> frozenset[str]:
    return frozenset(record["doctrine_id"] for record in INSTITUTIONAL_DOCTRINES)


def doctrine_by_id(doctrine_id: str) -> DoctrineSpec:
    matches = tuple(
        record
        for record in INSTITUTIONAL_DOCTRINES
        if record["doctrine_id"] == doctrine_id
    )
    if len(matches) != 1:
        raise ValueError(
            "institutional doctrine must resolve exactly once: "
            f"doctrine_id={doctrine_id}, matches={len(matches)}"
        )
    return matches[0]


def validate_institutional_registry() -> None:
    source_identity_count = len(institutional_source_ids())
    doctrine_identity_count = len(doctrine_ids())
    if source_identity_count != len(INSTITUTIONAL_SOURCES):
        raise ValueError(
            "institutional source registry contains duplicate source identities"
        )
    if doctrine_identity_count != len(INSTITUTIONAL_DOCTRINES):
        raise ValueError(
            "institutional doctrine registry contains duplicate doctrine identities"
        )
    for source in INSTITUTIONAL_SOURCES:
        if not source["url"].startswith("https://"):
            raise ValueError(
                "institutional source requires an HTTPS primary URL: "
                f"source_id={source['source_id']}, url={source['url']}"
            )
        for field in (
            "source_id",
            "title",
            "source_type",
            "published_at",
            "adopted_capability",
            "evidence_restriction",
        ):
            if not source[field].strip():
                raise ValueError(
                    "institutional source requires non-empty fields: "
                    f"source_id={source['source_id']}, field={field}"
                )
    source_ids = institutional_source_ids()
    for doctrine in INSTITUTIONAL_DOCTRINES:
        missing_sources = sorted(set(doctrine["source_ids"]) - source_ids)
        unsupported_instruments = sorted(
            set(doctrine["applicable_instruments"]) - SUPPORTED_INSTRUMENTS
        )
        if missing_sources:
            raise ValueError(
                "institutional doctrine references unknown sources: "
                f"doctrine_id={doctrine['doctrine_id']}, source_ids={missing_sources}"
            )
        if unsupported_instruments or not doctrine["applicable_instruments"]:
            raise ValueError(
                "institutional doctrine contains unsupported or missing instruments: "
                f"doctrine_id={doctrine['doctrine_id']}, instruments={unsupported_instruments}"
            )
        if (
            not doctrine["required_checks"]
            or not doctrine["failure_modes"]
            or not doctrine["prohibited_inferences"]
        ):
            raise ValueError(
                "institutional doctrine requires checks, failure modes, and prohibited inferences: "
                f"doctrine_id={doctrine['doctrine_id']}"
            )


validate_institutional_registry()
