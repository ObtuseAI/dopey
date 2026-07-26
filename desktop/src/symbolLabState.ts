import type {
  SymbolLabExpression,
  SymbolLabPayload,
  SymbolLabPlan,
  SymbolLabScenarioPoint,
  SymbolLabStrategyMode,
  SymbolLabStrategyResult,
  SymbolLabZone,
} from "./types";

const record = (value: unknown, context: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TypeError(`${context} must be an object.`);
  }
  return value as Record<string, unknown>;
};

const records = (value: unknown): readonly Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null && !Array.isArray(item))
    : [];

const text = (value: unknown, fallback: string): string => typeof value === "string" ? value : fallback;
const nullableText = (value: unknown): string | null => typeof value === "string" && value.length > 0 ? value : null;
const number = (value: unknown, fallback: number): number => typeof value === "number" && Number.isFinite(value) ? value : fallback;
const nullableNumber = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const boolean = (value: unknown): boolean => value === true;
const strings = (value: unknown): readonly string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const strategyMode = (value: unknown): SymbolLabStrategyMode => {
  const parsed = text(value, "auto");
  const allowed: readonly SymbolLabStrategyMode[] = ["auto", "trend", "momentum", "breakout", "mean_reversion", "volatility", "bullish_scenario", "bearish_scenario"];
  if (!allowed.includes(parsed as SymbolLabStrategyMode)) {
    throw new TypeError(`Symbol lab strategy mode is unsupported: ${parsed}`);
  }
  return parsed as SymbolLabStrategyMode;
};

const zone = (value: unknown): SymbolLabZone | null => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const source = value as Record<string, unknown>;
  const zoneMid = nullableNumber(source.zone_mid);
  if (zoneMid === null) {
    return null;
  }
  return {
    zoneMid,
    zoneLow: number(source.zone_low, zoneMid),
    zoneHigh: number(source.zone_high, zoneMid),
    role: text(source.role_now, "unknown"),
    distancePct: nullableNumber(source.distance_pct),
    confluenceScore: nullableNumber(source.confluence_score),
    timeframes: strings(source.timeframes),
  };
};

const strategy = (source: Record<string, unknown>): SymbolLabStrategyResult => ({
  strategyId: text(source.strategy_id, "unknown_strategy"),
  family: text(source.family, "unknown"),
  direction: text(source.direction, "neutral"),
  thesis: text(source.thesis, "No thesis reported."),
  currentSignalActive: boolean(source.current_signal_active),
  sampleCount: number(source.sample_count, 0),
  meanNetReturn: number(source.mean_net_return, 0),
  selectionAdjustedMean: number(source.selection_adjusted_mean, 0),
  hitRate: number(source.hit_rate, 0),
  positiveFoldRate: number(source.positive_fold_rate, 0),
  worstFoldMean: number(source.worst_fold_mean, 0),
  robustnessScore: number(source.robustness_score, 0),
  evidenceStatus: text(source.evidence_status, "unknown"),
});

const plan = (source: Record<string, unknown>): SymbolLabPlan => ({
  planId: text(source.plan_id, "unknown_plan"),
  family: text(source.family, "unknown"),
  direction: text(source.direction, "neutral"),
  status: text(source.plan_status, "unknown"),
  strategyId: nullableText(source.strategy_id),
  trigger: text(source.trigger, "No trigger reported."),
  invalidationPrice: nullableNumber(source.invalidation_price),
  scenarioTargetPrice: nullableNumber(source.scenario_target_price),
  optionsExpressionBias: text(source.options_expression_bias, "none"),
  confidenceCap: number(source.confidence_cap, 0),
});

const expression = (source: Record<string, unknown>): SymbolLabExpression => {
  const projectedReturn = nullableNumber(source.projected_return_on_premium) ?? nullableNumber(source.projected_return_on_debit) ?? 0;
  return {
    expressionId: text(source.expression_id, "unknown_expression"),
    expressionType: text(source.expression_type, "unknown"),
    expiry: text(source.expiry, "unknown"),
    dte: number(source.dte_calendar, 0),
    strike: nullableNumber(source.strike),
    longStrike: nullableNumber(source.long_strike),
    shortStrike: nullableNumber(source.short_strike),
    bid: nullableNumber(source.bid),
    ask: nullableNumber(source.ask),
    impliedVol: nullableNumber(source.implied_vol),
    spreadPct: nullableNumber(source.spread_pct),
    scenarioModelValue: number(source.scenario_model_value, 0),
    projectedPnl: number(source.projected_pnl_per_share, 0),
    projectedReturn,
    maximumLoss: number(source.maximum_loss_per_share, 0),
    delta: nullableNumber(source.delta),
    theta: nullableNumber(source.theta_per_day),
    liquidityScore: nullableNumber(source.liquidity_score),
    valueScore: number(source.value_score, 0),
    activePolicyEligible: boolean(source.active_policy_eligible),
  };
};

const scenarioPoint = (source: Record<string, unknown>): SymbolLabScenarioPoint => ({
  stockPrice: number(source.stock_price, 0),
  elapsedDays: number(source.elapsed_calendar_days, 0),
  remainingDte: number(source.remaining_dte, 0),
  theoreticalValue: number(source.theoretical_value, 0),
});

export const normalizeSymbolLab = (raw: unknown): SymbolLabPayload => {
  const root = record(raw, "Symbol lab payload");
  if (root.paper_only !== true || root.live_blocked !== true || root.synthetic_data_used !== false) {
    throw new TypeError("Symbol lab payload violates its paper-only, real-data boundary.");
  }
  const request = record(root.request, "Symbol lab request");
  const market = record(root.market_profile, "Symbol lab market profile");
  const earnings = record(market.earnings, "Symbol lab earnings context");
  const chain = record(market.options_chain, "Symbol lab option-chain context");
  const technical = record(root.technical_intelligence, "Symbol lab technical intelligence");
  const strategyResearch = record(root.strategy_research, "Symbol lab strategy research");
  const optionLab = record(root.options_value_lab, "Symbol lab options projection");
  const longExpressions = records(optionLab.long_candidates).map(expression);
  const verticalExpressions = records(optionLab.vertical_candidates).map(expression);
  const bestSource = optionLab.best_expression;
  const bestExpression = typeof bestSource === "object" && bestSource !== null && !Array.isArray(bestSource)
    ? expression(bestSource as Record<string, unknown>)
    : null;
  return {
    schemaVersion: text(root.schema_version, "unknown"),
    symbol: text(root.symbol, "UNKNOWN"),
    asOf: text(root.as_of_date, "unknown"),
    generatedUtc: text(root.generated_utc, "unknown"),
    selectedDirection: text(root.selected_research_direction, "neutral"),
    directionSource: text(root.direction_source, "unknown"),
    selectedStrategyId: nullableText(root.selected_strategy_id),
    request: {
      strategyMode: strategyMode(request.strategy_mode),
      scenarioPriceRequested: nullableNumber(request.scenario_stock_price_requested),
      scenarioPriceEffective: number(request.scenario_stock_price_effective, 0),
      daysForward: number(request.days_forward, 0),
      ivShift: number(request.iv_shift_decimal, 0),
    },
    marketProfile: {
      currentPrice: number(market.current_price, 0),
      dailyAtr: number(market.daily_atr, 0),
      realizedVol: number(market.realized_volatility_20d_annualized, 0),
      timeframeDirection: text(market.multi_timeframe_direction, "neutral"),
      timeframeAgreement: number(market.multi_timeframe_agreement_score, 0),
      nearestSupport: zone(market.nearest_support),
      nearestResistance: zone(market.nearest_resistance),
      earningsDate: nullableText(earnings.earnings_date),
      daysUntilEarnings: nullableNumber(earnings.days_until_earnings),
      earningsStatus: text(earnings.status, "unknown"),
      chainStatus: text(chain.status, "unknown"),
      chainSnapshotDate: nullableText(chain.snapshot_date),
      contractCount: number(chain.contract_count, 0),
      expiryCount: number(chain.expiry_count, 0),
      medianSpreadPct: nullableNumber(chain.median_spread_pct),
      putCallOiRatio: nullableNumber(chain.put_call_open_interest_ratio),
      nearAtmSkew: nullableNumber(chain.near_atm_put_minus_call_iv),
      zones: records(market.confluence_zones).map(zone).filter((item): item is SymbolLabZone => item !== null),
    },
    indicatorCount: number(technical.indicator_count, 0),
    divergenceCount: records(technical.divergences).length,
    strategies: records(strategyResearch.strategy_results).map(strategy),
    activeStrategyIds: strings(strategyResearch.current_active_strategy_ids),
    plans: records(root.meta_plans).map(plan),
    projectorStatus: text(optionLab.projector_status, "unknown"),
    eligibleContractCount: number(optionLab.eligible_contract_count, 0),
    bestExpression,
    expressions: [...longExpressions, ...verticalExpressions].sort((left, right) => right.valueScore - left.valueScore),
    scenarioSurface: records(optionLab.scenario_surface).map(scenarioPoint),
    knowledgeBoundaries: strings(root.knowledge_boundaries),
    contentHash: text(root.content_hash, ""),
    syntheticDataUsed: boolean(root.synthetic_data_used),
    paperOnly: boolean(root.paper_only),
    liveBlocked: boolean(root.live_blocked),
  };
};
