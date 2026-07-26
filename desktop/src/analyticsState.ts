import type {
  AgentAblationState,
  AgentTelemetryEvent,
  AnalyticsEquityPoint,
  AnalyticsFailureRank,
  AnalyticsFoldMetric,
  AnalyticsParetoPoint,
  AnalyticsRobustnessGate,
  AnalyticsSourceState,
  CalibrationAnalyticsState,
  CalibrationBin,
  DesktopAnalyticsState,
  GatedCapabilityState,
  IvMultiplierPoint,
  OptionsSurfacePoint,
  PaperAnalyticsPosition,
  PaperExposure,
  RegimeHistoryPoint,
  ReadinessAnalyticsLane,
} from "./types";

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const record = (value: unknown): UnknownRecord => isRecord(value) ? value : {};
const records = (value: unknown): readonly UnknownRecord[] => Array.isArray(value)
  ? value.filter(isRecord)
  : [];

const text = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }
  const stripped = value.trim();
  return stripped.length > 0 ? stripped : null;
};

const number = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const boolean = (value: unknown): boolean | null => typeof value === "boolean" ? value : null;
const strings = (value: unknown): readonly string[] => Array.isArray(value)
  ? value.filter((item): item is string => typeof item === "string")
  : [];

const capability = (value: unknown): GatedCapabilityState => {
  const raw = record(value);
  return {
    status: text(raw["status"]) ?? "unavailable_no_contract",
    reason: text(raw["reason"]),
    requiredEvidence: strings(raw["required_evidence"]),
  };
};

const foldMetrics = (value: unknown): readonly AnalyticsFoldMetric[] => records(value).map((row) => ({
  candidateId: text(row["candidate_id"]) ?? "unknown_candidate",
  family: text(row["family"]) ?? "unknown_family",
  structure: text(row["structure"]) ?? "unknown_structure",
  era: text(row["era"]) ?? "unknown_era",
  sampleCount: number(row["sample_count"]),
  expectancyModelUnits: number(row["expectancy_model_units"]),
  netModelUnits: number(row["net_model_units"]),
  winRate: number(row["win_rate"]),
  profitFactor: number(row["profit_factor"]),
  meetsMinimumSample: boolean(row["meets_minimum_sample"]),
}));

const robustness = (value: unknown): readonly AnalyticsRobustnessGate[] => records(value).map((row) => ({
  candidateId: text(row["candidate_id"]) ?? "unknown_candidate",
  gateId: text(row["gate_id"]) ?? "unknown_gate",
  status: text(row["status"]) ?? "unknown",
  observed: text(row["observed"]) ?? "unreported",
  required: text(row["required"]) ?? "unreported",
  diagnosticOnly: boolean(row["diagnostic_only"]) === true,
}));

const pareto = (value: unknown): readonly AnalyticsParetoPoint[] => records(value).map((row) => ({
  candidateId: text(row["candidate_id"]) ?? "unknown_candidate",
  tradeCount: number(row["trade_count"]),
  symbolCount: number(row["symbol_count"]),
  expectancyModelUnits: number(row["expectancy_model_units"]),
  stressedExpectancyModelUnits: number(row["stressed_expectancy_model_units"]),
  maxDrawdownModelUnits: number(row["max_drawdown_model_units"]),
  tailLossP05ModelUnits: number(row["tail_loss_p05_model_units"]),
  foldStability: number(row["fold_stability"]),
  positiveFoldCount: number(row["positive_fold_count"]),
  gateFailureCount: number(row["gate_failure_count"]),
  eligible: boolean(row["eligible"]),
  evidenceClass: text(row["evidence_class"]) ?? "unknown",
}));

const equity = (value: unknown): readonly AnalyticsEquityPoint[] => records(value).map((row) => ({
  date: text(row["date"]) ?? "unknown_date",
  tradeCount: number(row["trade_count"]),
  grossModelUnits: number(row["gross_model_units"]),
  costModelUnits: number(row["cost_model_units"]),
  netModelUnits: number(row["net_model_units"]),
  cumulativeModelUnits: number(row["cumulative_model_units"]),
  drawdownModelUnits: number(row["drawdown_model_units"]),
}));

const failureRanking = (value: unknown): readonly AnalyticsFailureRank[] => records(value).map((row) => ({
  failureId: text(row["failure_id"]) ?? "unknown_failure",
  candidateCount: number(row["candidate_count"]) ?? 0,
}));

const readinessLanes = (value: unknown): readonly ReadinessAnalyticsLane[] => records(value).map((row) => ({
  laneId: text(row["lane_id"]) ?? "unknown_lane",
  priority: number(row["priority"]),
  current: number(row["current"]),
  required: number(row["required"]),
  remaining: number(row["remaining"]),
  thresholdUnchanged: boolean(row["threshold_unchanged"]),
  acceleration: text(row["acceleration"]),
  missingChecks: strings(row["missing_checks"]),
  estimatedTradingDays: number(row["estimated_trading_days"]),
  estimateOnlyNotAPromise: boolean(row["estimate_only_not_a_promise"]),
  maturityLagDays: number(row["maturity_lag_days"]),
}));

const paperPositions = (value: unknown): readonly PaperAnalyticsPosition[] => records(value).map((row) => {
  const rawStatus = text(row["status"]);
  const status = rawStatus === "open" || rawStatus === "closed" ? rawStatus : "unknown";
  return {
    positionId: text(row["position_id"]) ?? "unknown_position",
    symbol: text(row["symbol"]) ?? "UNKNOWN",
    status,
    structure: text(row["structure"]),
    direction: text(row["direction"]) ?? "unknown",
    sector: text(row["sector"]) ?? "unclassified",
    entryDate: text(row["entry_date"]),
    lastMarkDate: text(row["last_mark_date"]),
    ageDays: number(row["age_days"]),
    quoteAgeDays: number(row["quote_age_days"]),
    relativeSpread: number(row["relative_spread"]),
    entryFill: number(row["entry_fill"]),
    lastMarkBid: number(row["last_mark_bid"]),
    pathPnl: number(row["path_pnl"]),
    pricingSourceTier: text(row["pricing_source_tier"]),
    quotePriced: boolean(row["quote_priced"]),
  };
});

const exposures = (value: unknown): readonly PaperExposure[] => records(value).map((row) => ({
  axis: text(row["axis"]) ?? "unknown",
  key: text(row["key"]) ?? "unknown",
  positionCount: number(row["position_count"]) ?? 0,
  entryPremiumUnits: number(row["entry_premium_units"]) ?? 0,
}));

const surface = (value: unknown): readonly OptionsSurfacePoint[] => records(value).map((row) => ({
  expiry: text(row["expiry"]) ?? "unknown_expiry",
  dte: number(row["dte"]),
  optionType: text(row["option_type"]) ?? "unknown",
  strike: number(row["strike"]),
  moneyness: number(row["moneyness"]),
  bid: number(row["bid"]),
  ask: number(row["ask"]),
  mid: number(row["mid"]),
  impliedVol: number(row["implied_vol"]),
  volume: number(row["volume"]),
  openInterest: number(row["open_interest"]),
  relativeSpread: number(row["relative_spread"]),
}));

const multipliers = (value: unknown): readonly IvMultiplierPoint[] => records(value).map((row) => ({
  symbol: text(row["symbol"]) ?? "UNKNOWN",
  contracts: number(row["contracts"]),
  multiplier: number(row["multiplier"]),
}));

const bins = (value: unknown): readonly CalibrationBin[] => records(value).map((row) => ({
  lower: number(row["lower"]),
  upper: number(row["upper"]),
  meanConfidence: number(row["mean_confidence"]),
  accuracy: number(row["accuracy"]),
  count: number(row["count"]),
}));

const calibration = (value: unknown): CalibrationAnalyticsState => {
  const raw = record(value);
  return {
    status: text(raw["calibration_status"] ?? raw["status"]) ?? "unavailable_no_calibration_contract",
    sampleSufficient: boolean(raw["calibration_sample_sufficient"]),
    settledTotal: number(raw["settled_total"]),
    pendingTotal: number(raw["pending_total"]),
    minimumSample: number(raw["minimum_calibration_sample"]),
    ece: number(raw["expected_calibration_error"]),
    mce: number(raw["maximum_calibration_error"]),
    brier: number(raw["mean_multiclass_brier_score"]),
    logLoss: number(raw["mean_multiclass_log_loss"]),
    bins: bins(raw["reliability_bins"]),
  };
};

const agentAblation = (value: unknown): AgentAblationState => {
  const raw = record(value);
  return {
    status: text(raw["evaluation_status"] ?? raw["status"]) ?? "unavailable_no_agent_ablation_contract",
    agentCount: number(raw["agent_count"]),
    eligibleSettlementCount: number(raw["eligible_settlement_count"]),
    minimumSample: number(raw["minimum_sample"]),
    protectedEvaluator: boolean(raw["protected_evaluator"]),
    evaluations: records(raw["evaluations"]),
  };
};

const telemetryEvents = (value: unknown): readonly AgentTelemetryEvent[] => records(value).map((row) => ({
  eventUtc: text(row["event_utc"]) ?? "unknown_time",
  runId: text(row["run_id"]) ?? "unknown_run",
  agentId: text(row["agent_id"]) ?? "unknown_agent",
  phase: text(row["phase"]) ?? "unknown_phase",
  statusTransition: text(row["status_transition"]) ?? "unknown_transition",
  inputArtifactHashes: strings(row["input_artifact_hashes"]),
  outputArtifactHashes: strings(row["output_artifact_hashes"]),
  durationMs: number(row["duration_ms"]),
  error: text(row["error"]),
}));

const regimeHistory = (value: unknown): readonly RegimeHistoryPoint[] => records(value).map((row) => ({
  lane: text(row["lane"]) ?? "unknown_lane",
  snapshotId: text(row["snapshot_id"]) ?? "unknown_snapshot",
  fileCount: number(row["file_count"]) ?? 0,
}));

const sources = (value: unknown): readonly AnalyticsSourceState[] => records(value).map((row) => ({
  sourceId: text(row["source_id"]) ?? "unknown_source",
  relativePath: text(row["relative_path"]) ?? "unknown_path",
  status: text(row["status"]) ?? "unknown",
  sha256: text(row["sha256"]),
  detail: text(row["detail"]) ?? "No source detail reported.",
}));

export const emptyAnalyticsState = (): DesktopAnalyticsState => ({
  schemaVersion: null,
  status: "unavailable_no_analytics_contract",
  evidence: {
    status: "unavailable_no_dossier_analytics",
    runId: null,
    evidenceClass: null,
    foldMetrics: [],
    robustnessTests: [],
    paretoFrontier: [],
    equityCurve: [],
    failureRanking: [],
    selectionPressure: {
      candidateCount: null,
      eligibleCandidateCount: null,
      diagnosticFrontierCount: null,
      tradeCount: null,
      effectiveTrials: null,
      mutationAttempts: null,
      deflatedSharpeDiagnostic: null,
    },
  },
  readiness: {
    status: "unavailable_missing_readiness_acceleration_plan",
    contextEvidenceStatus: null,
    lanes: [],
    governance: {
      gatePolicyChanged: null,
      removedGateIds: [],
      remainingThresholdsLowered: null,
      reproducibilityHash: null,
    },
    newsPipelineStatus: null,
    newsRequiredCoverageComplete: null,
    newsFailedSourceIds: [],
  },
  paper: {
    status: "unavailable_no_paper_analytics",
    asOfDate: null,
    openCount: null,
    closedCount: null,
    closedRequired: null,
    positions: [],
    exposures: [],
  },
  options: {
    status: "unavailable_no_options_analytics",
    snapshotDate: null,
    symbol: null,
    availableSymbols: [],
    surface: [],
    ivCalibration: {
      status: null,
      currentMultiplier: null,
      recommendedMultiplier: null,
      ivOverRvP25: null,
      ivOverRvP75: null,
      premiumErrorP25: null,
      premiumErrorMedian: null,
      premiumErrorP75: null,
      symbolsCovered: null,
      multipliers: [],
    },
  },
  machineLearning: {
    calibration: calibration({}),
    signalCalibration: {
      status: "unavailable_no_signal_calibration_contract",
      semantics: null,
      settledTotal: null,
      overallHitRate: null,
      contestedTotal: null,
      contestedHitRate: null,
      promotionAllowed: null,
    },
    agentAblation: agentAblation({}),
    conformal: capability({}),
    shap: capability({}),
    embeddings: capability({}),
    training: capability({}),
  },
  telemetry: {
    status: "unavailable_declared_topology_only",
    reason: "No observed event telemetry contract was reported.",
    contractFields: [],
    events: [],
    observedLinkCount: 0,
  },
  regime: {
    status: "unavailable_no_regime_history_index",
    history: [],
    transitionModel: capability({}),
    distributionDrift: capability({}),
  },
  sources: [],
  errors: [],
});

export const normalizeAnalytics = (value: unknown): DesktopAnalyticsState => {
  const raw = record(value);
  if (Object.keys(raw).length === 0) {
    return emptyAnalyticsState();
  }
  const evidence = record(raw["evidence"]);
  const selection = record(evidence["selection_pressure"]);
  const readiness = record(raw["readiness"]);
  const governance = record(readiness["governance"]);
  const intakeHealth = record(readiness["intake_health"]);
  const paper = record(raw["paper"]);
  const options = record(raw["options"]);
  const iv = record(options["iv_calibration"]);
  const machineLearning = record(raw["machine_learning"]);
  const signal = record(machineLearning["signal_calibration"]);
  const telemetry = record(raw["telemetry"]);
  const regime = record(raw["regime"]);
  return {
    schemaVersion: text(raw["schema_version"]),
    status: text(raw["status"]) ?? "unavailable_invalid_analytics_contract",
    evidence: {
      status: text(evidence["status"]) ?? "unavailable_no_dossier_analytics",
      runId: text(evidence["run_id"]),
      evidenceClass: text(evidence["evidence_class"]),
      foldMetrics: foldMetrics(evidence["fold_metrics"]),
      robustnessTests: robustness(evidence["robustness_tests"]),
      paretoFrontier: pareto(evidence["pareto_frontier"]),
      equityCurve: equity(evidence["equity_curve"]),
      failureRanking: failureRanking(evidence["failure_ranking"]),
      selectionPressure: {
        candidateCount: number(selection["candidate_count"]),
        eligibleCandidateCount: number(selection["eligible_candidate_count"]),
        diagnosticFrontierCount: number(selection["diagnostic_frontier_count"]),
        tradeCount: number(selection["trade_count"]),
        effectiveTrials: number(selection["effective_trials"]),
        mutationAttempts: number(selection["mutation_attempts"]),
        deflatedSharpeDiagnostic: number(selection["deflated_sharpe_diagnostic"]),
      },
    },
    readiness: {
      status: text(readiness["status"]) ?? "unavailable_missing_readiness_acceleration_plan",
      contextEvidenceStatus: text(readiness["context_evidence_status"]),
      lanes: readinessLanes(readiness["lanes"]),
      governance: {
        gatePolicyChanged: boolean(governance["gate_policy_changed"]),
        removedGateIds: strings(governance["removed_gate_ids"]),
        remainingThresholdsLowered: boolean(governance["remaining_thresholds_lowered"]),
        reproducibilityHash: text(governance["reproducibility_hash"]),
      },
      newsPipelineStatus: text(intakeHealth["news_pipeline_status"]),
      newsRequiredCoverageComplete: boolean(intakeHealth["news_required_coverage_complete"]),
      newsFailedSourceIds: strings(intakeHealth["news_failed_source_ids"]),
    },
    paper: {
      status: text(paper["status"]) ?? "unavailable_no_paper_analytics",
      asOfDate: text(paper["as_of_date"]),
      openCount: number(paper["open_count"]),
      closedCount: number(paper["closed_count"]),
      closedRequired: number(paper["closed_required"]),
      positions: paperPositions(paper["positions"]),
      exposures: exposures(paper["exposures"]),
    },
    options: {
      status: text(options["status"]) ?? "unavailable_no_options_analytics",
      snapshotDate: text(options["snapshot_date"]),
      symbol: text(options["symbol"]),
      availableSymbols: strings(options["available_symbols"]),
      surface: surface(options["surface"]),
      ivCalibration: {
        status: text(iv["status"]),
        currentMultiplier: number(iv["current_multiplier"]),
        recommendedMultiplier: number(iv["recommended_multiplier"]),
        ivOverRvP25: number(iv["iv_over_rv_p25"]),
        ivOverRvP75: number(iv["iv_over_rv_p75"]),
        premiumErrorP25: number(iv["premium_error_p25"]),
        premiumErrorMedian: number(iv["premium_error_median"]),
        premiumErrorP75: number(iv["premium_error_p75"]),
        symbolsCovered: number(iv["symbols_covered"]),
        multipliers: multipliers(iv["multipliers"]),
      },
    },
    machineLearning: {
      calibration: calibration(machineLearning["calibration"]),
      signalCalibration: {
        status: text(signal["signal_calibration_status"] ?? signal["status"]) ?? "unavailable_no_signal_calibration_contract",
        semantics: text(signal["semantics"]),
        settledTotal: number(signal["settled_total"]),
        overallHitRate: number(signal["overall_hit_rate"]),
        contestedTotal: number(signal["contested_total"]),
        contestedHitRate: number(signal["contested_hit_rate"]),
        promotionAllowed: boolean(signal["promotion_allowed"]),
      },
      agentAblation: agentAblation(machineLearning["agent_ablation"]),
      conformal: capability(machineLearning["conformal"]),
      shap: capability(machineLearning["shap"]),
      embeddings: capability(machineLearning["embeddings"]),
      training: capability(machineLearning["training"]),
    },
    telemetry: {
      status: text(telemetry["status"]) ?? "unavailable_declared_topology_only",
      reason: text(telemetry["reason"]),
      contractFields: strings(telemetry["contract_fields"]),
      events: telemetryEvents(telemetry["events"]),
      observedLinkCount: number(telemetry["observed_link_count"]) ?? 0,
    },
    regime: {
      status: text(regime["status"]) ?? "unavailable_no_regime_history_index",
      history: regimeHistory(regime["history"]),
      transitionModel: capability(regime["transition_model"]),
      distributionDrift: capability(regime["distribution_drift"]),
    },
    sources: sources(raw["sources"]),
    errors: strings(raw["errors"]),
  };
};
