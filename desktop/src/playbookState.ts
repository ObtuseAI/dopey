import type {
  PlaybookCatalyst,
  PlaybookDirectionalBias,
  PlaybookListId,
  PlaybookRecommendation,
  PlaybookScoreBreakdown,
  PlaybookSetupEvidence,
  PlaybookSourceArtifact,
  PlaybookState,
  PlaybookTradability,
  PlaybookTrustEvidence,
} from "./types";

type UnknownRecord = Record<string, unknown>;
type DirectionalListId = Exclude<PlaybookListId, "overall">;

const DIRECTIONAL_LIST_IDS: readonly DirectionalListId[] = [
  "short_term_bullish",
  "short_term_bearish",
  "long_term_bullish",
  "long_term_bearish",
] as const;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const recordValue = (value: unknown): UnknownRecord => isRecord(value) ? value : {};

const asString = (value: unknown): string | null =>
  typeof value === "string" && value.trim().length > 0 ? value.trim() : null;

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
};

const asBoolean = (value: unknown): boolean | null => typeof value === "boolean" ? value : null;

const stringArray = (value: unknown): readonly string[] =>
  Array.isArray(value)
    ? value.map(asString).filter((item): item is string => item !== null)
    : [];

const numberArray = (value: unknown): readonly number[] =>
  Array.isArray(value)
    ? value.map(asNumber).filter((item): item is number => item !== null)
    : [];

const recordArray = (value: unknown): readonly UnknownRecord[] =>
  Array.isArray(value) ? value.filter(isRecord) : [];

const asDirectionalListId = (value: unknown): DirectionalListId | null => {
  const candidate = asString(value);
  return candidate !== null && DIRECTIONAL_LIST_IDS.includes(candidate as DirectionalListId)
    ? candidate as DirectionalListId
    : null;
};

const asDirectionalBias = (value: unknown): PlaybookDirectionalBias | null =>
  value === "bullish" || value === "bearish" ? value : null;

const normalizeScoreBreakdown = (value: unknown): PlaybookScoreBreakdown => {
  const row = recordValue(value);
  return {
    withinSetupSignal: asNumber(row["within_setup_signal"]),
    independentFamilyAgreement: asNumber(row["independent_family_agreement"]),
    forwardTrust: asNumber(row["forward_trust"]),
    directionNeutralAttention: asNumber(row["direction_neutral_attention"]),
    liquidity: asNumber(row["liquidity"]),
    universeSelection: asNumber(row["universe_selection"]),
    swingDirectionalSupport: asNumber(row["swing_directional_support"]),
    valuationFit: asNumber(row["valuation_fit"]),
    oppositionPenalty: asNumber(row["opposition_penalty"]),
  };
};

const normalizeSetupEvidence = (value: unknown): readonly PlaybookSetupEvidence[] =>
  recordArray(value).map((row) => ({
    detectionId: asString(row["detection_id"]) ?? "unidentified_detection",
    setupId: asString(row["setup_id"]) ?? "unidentified_setup",
    family: asString(row["family"]) ?? "unidentified_family",
    withinSetupPercentile: asNumber(row["within_setup_percentile"]),
    horizonDays: numberArray(row["horizon_days"]),
    details: recordValue(row["details"]),
    lineage: stringArray(row["lineage"]),
  }));

const normalizeTrustEvidence = (value: unknown): readonly PlaybookTrustEvidence[] =>
  recordArray(value).map((row) => ({
    setupId: asString(row["setup_id"]) ?? "unidentified_setup",
    trustState: asString(row["trust_state"]) ?? "unreported",
    settled: asNumber(row["settled"]),
    hitRate: asNumber(row["hit_rate"]),
    horizonMatch: asString(row["horizon_match"]),
  }));

const normalizeCatalysts = (value: unknown): readonly PlaybookCatalyst[] =>
  recordArray(value).map((row) => ({
    catalystType: asString(row["catalyst_type"]) ?? "unclassified",
    date: asString(row["date"]),
    status: asString(row["status"]),
  }));

const normalizeTradability = (value: unknown): PlaybookTradability => {
  const row = recordValue(value);
  return {
    researchTradable: asBoolean(row["research_tradable"]),
    tier: asString(row["tier"]),
    marketCap: asNumber(row["market_cap"]),
    averageDollarVolume20d: asNumber(row["avg_dollar_volume_20d"]),
    selectionScore: asNumber(row["selection_score"]),
    reasonCodes: stringArray(row["reason_codes"]),
    evidenceHash: asString(row["evidence_hash"]),
  };
};

const normalizeRecommendation = (
  value: unknown,
  recommendationKey: string,
): PlaybookRecommendation | null => {
  const row = recordValue(value);
  const category = asDirectionalListId(row["category"]);
  const directionalBias = asDirectionalBias(row["directional_bias"]);
  const symbol = asString(row["symbol"]);
  if (category === null || directionalBias === null || symbol === null) {
    return null;
  }
  const attention = recordValue(row["attention_context"]);
  return {
    recommendationId: asString(row["recommendation_id"]) ?? recommendationKey,
    rank: asNumber(row["rank"]),
    symbol,
    category,
    horizon: asString(row["horizon"]) ?? "unreported",
    horizonLabel: asString(row["horizon_label"]),
    directionalBias,
    predictionLabel: asString(row["prediction_label"]),
    researchPriorityScore: asNumber(row["research_priority_score"]),
    rankScoreIsNotProbability: asBoolean(row["rank_score_is_not_probability"]),
    recommendationState: asString(row["recommendation_state"]),
    confidenceLabel: asString(row["confidence_label"]),
    thesisSummary: asString(row["thesis_summary"]),
    variantWedge: asString(row["variant_wedge"]),
    whyNow: stringArray(row["why_now"]),
    firstRejection: asString(row["first_rejection"]),
    whatWouldMakeInvestable: stringArray(row["what_would_make_investable"]),
    whatWouldKillIt: stringArray(row["what_would_kill_it"]),
    catalysts: normalizeCatalysts(row["catalysts"]),
    risks: stringArray(row["risks"]),
    missingEvidence: stringArray(row["missing_evidence"]),
    scoreBreakdown: normalizeScoreBreakdown(row["score_breakdown"]),
    setupEvidence: normalizeSetupEvidence(row["setup_evidence"]),
    trustEvidence: normalizeTrustEvidence(row["trust_evidence"]),
    attentionContext: {
      score: asNumber(attention["score"]),
      status: asString(attention["status"]),
      freshnessStatus: asString(attention["freshness_status"]),
      completenessRatio: asNumber(attention["completeness_ratio"]),
      drivers: stringArray(attention["drivers"]),
      missingComponents: stringArray(attention["missing_components"]),
      provenanceSha256: asString(attention["provenance_sha256"]),
      directionalUse: asString(attention["directional_use"]),
    },
    tradability: normalizeTradability(row["tradability"]),
    technicalEvidence: recordValue(row["technical_evidence"]),
    fundamentalEvidence: recordValue(row["fundamental_evidence"]),
    valuationContext: recordValue(row["valuation_context"]),
    competingContext: recordValue(row["competing_context"]),
    researchInvalidationPrice: asNumber(row["research_invalidation_price"]),
    marketDataAsOf: asString(row["market_data_as_of"]),
    executionState: asString(row["execution_state"]),
    orderConstructionAllowed: asBoolean(row["order_construction_allowed"]),
    tradePromotionAllowed: asBoolean(row["trade_promotion_allowed"]),
    bearishExpressionPolicy: asString(row["bearish_expression_policy"]),
  };
};

const normalizeSourceArtifacts = (value: unknown): readonly PlaybookSourceArtifact[] =>
  recordArray(value).map((row, index) => ({
    sourceId: asString(row["source_id"]) ?? asString(row["id"]) ?? `source-${index + 1}`,
    relativePath: asString(row["relative_path"]) ?? asString(row["path"]),
    sha256: asString(row["sha256"]),
    status: asString(row["status"]),
  }));

const emptyLists = (): Readonly<Record<PlaybookListId, readonly string[]>> => ({
  short_term_bullish: [],
  short_term_bearish: [],
  long_term_bullish: [],
  long_term_bearish: [],
  overall: [],
});

export const emptyPlaybookState = (): PlaybookState => ({
  artifactType: null,
  schemaVersion: null,
  status: "not_reported",
  generatedUtc: null,
  marketDataAsOf: null,
  attentionAsOf: null,
  attentionGeneratedUtc: null,
  nextRefreshDueUtc: null,
  refreshIntervalMinutes: null,
  universeActiveCount: null,
  universeMaximumCount: null,
  eligibleSingleStockCount: null,
  lists: emptyLists(),
  missingSlotsByList: {
    short_term_bullish: null,
    short_term_bearish: null,
    long_term_bullish: null,
    long_term_bearish: null,
  },
  recommendations: {},
  recommendationCount: null,
  sourceArtifacts: [],
  rankingMethod: {
    directionSource: null,
    attentionUse: null,
    strengthNormalization: null,
    crossSetupRawStrengthCompared: null,
    longTermTrustIndependentlySettled: null,
    rankScoreIsNotProbability: null,
    noPaddingWhenInsufficient: null,
  },
  rankScoreIsNotProbability: null,
  orderConstructionAllowed: null,
  tradePromotionAllowed: null,
  liveExecutionAllowed: null,
  brokerAuthority: null,
  paperOnly: null,
  liveBlocked: null,
  contentHash: null,
  reproducibilityHash: null,
});

export const normalizePlaybook = (value: unknown): PlaybookState => {
  const row = recordValue(value);
  if (Object.keys(row).length === 0) {
    return emptyPlaybookState();
  }
  const rawLists = recordValue(row["lists"]);
  const rawMissing = recordValue(row["missing_slots_by_list"]);
  const rawRecommendations = recordValue(row["recommendations"]);
  const recommendations = Object.fromEntries(
    Object.entries(rawRecommendations)
      .map(([key, recommendation]) => normalizeRecommendation(recommendation, key))
      .filter((recommendation): recommendation is PlaybookRecommendation => recommendation !== null)
      .map((recommendation) => [recommendation.recommendationId, recommendation]),
  );
  const rankingMethod = recordValue(row["ranking_method"]);
  return {
    artifactType: asString(row["artifact_type"]),
    schemaVersion: asString(row["schema_version"]),
    status: asString(row["playbook_status"]) ?? "invalid_or_unreported",
    generatedUtc: asString(row["generated_utc"]),
    marketDataAsOf: asString(row["market_data_as_of"]),
    attentionAsOf: asString(row["attention_as_of"]),
    attentionGeneratedUtc: asString(row["attention_generated_utc"]),
    nextRefreshDueUtc: asString(row["next_refresh_due_utc"]),
    refreshIntervalMinutes: asNumber(row["refresh_interval_minutes"]),
    universeActiveCount: asNumber(row["universe_active_count"]),
    universeMaximumCount: asNumber(row["universe_maximum_count"]),
    eligibleSingleStockCount: asNumber(row["eligible_single_stock_count"]),
    lists: {
      short_term_bullish: stringArray(rawLists["short_term_bullish"]),
      short_term_bearish: stringArray(rawLists["short_term_bearish"]),
      long_term_bullish: stringArray(rawLists["long_term_bullish"]),
      long_term_bearish: stringArray(rawLists["long_term_bearish"]),
      overall: stringArray(rawLists["overall"]),
    },
    missingSlotsByList: {
      short_term_bullish: asNumber(rawMissing["short_term_bullish"]),
      short_term_bearish: asNumber(rawMissing["short_term_bearish"]),
      long_term_bullish: asNumber(rawMissing["long_term_bullish"]),
      long_term_bearish: asNumber(rawMissing["long_term_bearish"]),
    },
    recommendations,
    recommendationCount: asNumber(row["recommendation_count"]) ?? Object.keys(recommendations).length,
    sourceArtifacts: normalizeSourceArtifacts(row["source_artifacts"]),
    rankingMethod: {
      directionSource: asString(rankingMethod["direction_source"]),
      attentionUse: asString(rankingMethod["attention_use"]),
      strengthNormalization: asString(rankingMethod["strength_normalization"]),
      crossSetupRawStrengthCompared: asBoolean(rankingMethod["cross_setup_raw_strength_compared"]),
      longTermTrustIndependentlySettled: asBoolean(rankingMethod["long_term_trust_independently_settled"]),
      rankScoreIsNotProbability: asBoolean(rankingMethod["rank_score_is_not_probability"]),
      noPaddingWhenInsufficient: asBoolean(rankingMethod["no_padding_when_insufficient"]),
    },
    rankScoreIsNotProbability: asBoolean(row["rank_score_is_not_probability"]),
    orderConstructionAllowed: asBoolean(row["order_construction_allowed"]),
    tradePromotionAllowed: asBoolean(row["trade_promotion_allowed"]),
    liveExecutionAllowed: asBoolean(row["live_execution_allowed"]),
    brokerAuthority: asBoolean(row["broker_authority"]),
    paperOnly: asBoolean(row["paper_only"]),
    liveBlocked: asBoolean(row["live_blocked"]),
    contentHash: asString(row["content_hash"]),
    reproducibilityHash: asString(row["reproducibility_hash"]),
  };
};
