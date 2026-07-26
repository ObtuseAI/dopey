export type ConnectionPhase = "CONNECTING" | "CONNECTED" | "UNAVAILABLE" | "INVALID" | "ERROR";

export type CorePhase = "OFF" | "ON" | "RUNNING" | "DRAINING" | "FAULT" | "UNKNOWN";

export type Severity = "nominal" | "notice" | "warning" | "critical" | "unknown";

export type LlmProviderId = "openrouter" | "openrouter_hybrid" | "claude" | "codex";

export type InstrumentMode = "stocks" | "options" | "both";

export interface EnvelopeState {
  paperOnly: boolean | null;
  liveBlocked: boolean | null;
  executionSeal: string | null;
}

export interface HostCapabilities {
  reported: boolean;
  permanentNoLiveExecution: boolean | null;
  liveExecutionAvailable: boolean | null;
  detail: string | null;
}

export interface LiveBranchState {
  readonly mode: string | null;
  readonly status: string | null;
  readonly cycleStatus: string | null;
  readonly generatedUtc: string | null;
  readonly accountLabel: string | null;
  readonly accountType: string | null;
  readonly authenticated: boolean | null;
  readonly officialRobinhoodMcp: boolean | null;
  readonly liveBranchEnabled: boolean | null;
  readonly stockExecutionEnabled: boolean | null;
  readonly optionsExecutionCapable: boolean | null;
  readonly optionsExecutionEnabled: boolean | null;
  readonly paperTwinRequired: boolean | null;
  readonly noDayTradingEnforced: boolean | null;
  readonly useFullAvailableBalance: boolean | null;
  readonly marketOpen: boolean | null;
  readonly marketDate: string | null;
  readonly buyingPowerUsd: number | null;
  readonly totalEquityUsd: number | null;
  readonly equityPositionCount: number | null;
  readonly optionPositionCount: number | null;
  readonly liveOrderEventCount: number | null;
  readonly placedOrderCount: number | null;
  readonly paperTwinEventCount: number | null;
  readonly recentOrders: readonly Readonly<Record<string, unknown>>[];
  readonly error: string | null;
}

export interface AutomationScheduleState {
  id: string;
  name: string;
  present: boolean | null;
  enabled: boolean | null;
  state: string | null;
  identityVerified: boolean | null;
  actionVerified: boolean | null;
  verificationIssues: readonly string[];
}

export interface ResearchCoreState {
  enabled: boolean | null;
  phase: CorePhase;
  validated: boolean | null;
  lastRunUtc: string | null;
  nextRunUtc: string | null;
  lockStatus: string | null;
  pid: number | null;
  ownershipVerified: boolean | null;
  mode: string | null;
  mutationAvailable: boolean | null;
  activeAutomationPresent: boolean | null;
  automationSchedules: readonly AutomationScheduleState[];
}

export interface ReadinessCheck {
  id: string;
  label: string;
  status: string;
  detail: string | null;
}

export interface ReadinessState {
  status: string | null;
  operationalStatus: string | null;
  highestOperationalLevel: string | null;
  researchMechanicsReady: boolean | null;
  stockShadowReady: boolean | null;
  optionShadowReady: boolean | null;
  strategyPromotionReady: boolean | null;
  liveExecutionStatus: string | null;
  actionReady: boolean | null;
  closedTrades: number | null;
  closedRequired: number | null;
  resolvedDecisions: number | null;
  resolvedRequired: number | null;
  actionableShadowTheses: number | null;
  checks: readonly ReadinessCheck[];
  missingRequirements: readonly string[];
}

export interface UniverseSymbol {
  symbol: string;
  tier: string | null;
  status: string | null;
}

export interface UniverseState {
  activeCount: number | null;
  targetCount: number | null;
  maximumCount: number | null;
  publicLakeCount: number | null;
  tierCounts: Readonly<Record<string, number>>;
  symbols: readonly UniverseSymbol[];
}

export interface ScheduleLane {
  id: string;
  description: string;
  due: boolean | null;
  lastRunStatus: string | null;
  windowOpen: boolean | null;
  evidenceStatus: string | null;
  lastSuccessUtc: string | null;
}

export interface ScheduleState {
  dueLaneIds: readonly string[];
  lanes: readonly ScheduleLane[];
}

export interface PaperPosition {
  id: string;
  symbol: string;
  structure: string | null;
  status: string | null;
  value: number | null;
  openedUtc: string | null;
  closedUtc: string | null;
}

export interface PaperBookState {
  openCount: number | null;
  closedCount: number | null;
  wins: number | null;
  realizedPremiumUnits: number | null;
  unrealizedPremiumUnits: number | null;
  openPositions: readonly PaperPosition[];
  closedPositions: readonly PaperPosition[];
}

export interface WorldRegime {
  dimension: string;
  state: string;
  probability: number | null;
  uncertainty: number | null;
  limitations: readonly string[];
}

export interface WorldState {
  asOf: string | null;
  contradictions: readonly string[];
  regimes: readonly WorldRegime[];
}

export interface StockExtreme {
  readonly symbol: string;
  readonly direction: "up" | "down";
  readonly rank: number | null;
  readonly returnPct: number | null;
  readonly rsi14: number | null;
}

export interface OptionExtreme {
  readonly symbol: string;
  readonly contractKey: string;
  readonly tail: "winner" | "loser";
  readonly roiPct: number | null;
  readonly entryDate: string | null;
  readonly exitDate: string | null;
}

export interface ExtremesState {
  readonly marketStatus: string | null;
  readonly optionStatus: string | null;
  readonly gainers: readonly StockExtreme[];
  readonly decliners: readonly StockExtreme[];
  readonly optionWinners: readonly OptionExtreme[];
  readonly optionLosers: readonly OptionExtreme[];
}

export interface ConfidenceDimension {
  name: string;
  value: number | null;
}

export interface MetacognitionState {
  knowledgeBoundary: string | null;
  primaryControl: string | null;
  difficulty: number | null;
  confidence: readonly ConfidenceDimension[];
  expectedInformationGain: number | null;
  researchUtility: number | null;
}

export interface LlmResearchState {
  cycleStatus: string | null;
  action: string | null;
  issuedUtc: string | null;
  providers: readonly string[];
  reportedCostUsd: number | null;
  summary: string | null;
  experimentCount: number | null;
  abstain: boolean | null;
  evidenceClass: string | null;
}

export interface LlmCredentialState {
  configured: boolean | null;
  usable: boolean | null;
  validationStatus: string | null;
  source: string | null;
  updatedUtc: string | null;
  plaintextExposed: boolean | null;
  repositoryStorage: boolean | null;
}

export interface LlmModelRouteState {
  readonly routeId: string;
  readonly modelId: string;
  readonly role: string;
  readonly stage: string;
  readonly provider: string;
}

export interface LlmRoutingPolicyState {
  readonly provider: string | null;
  readonly routeId: string | null;
  readonly strategy: string | null;
  readonly stageOrder: readonly string[];
  readonly allModelStagesRequired: boolean | null;
  readonly fallbackAllowed: boolean | null;
  readonly independentExternalRoutesAllowed: boolean | null;
}

export interface LlmProviderControlState {
  schemaVersion: string | null;
  instrumentMode: InstrumentMode | null;
  providers: Readonly<Record<LlmProviderId, boolean | null>>;
  availability: Readonly<Record<LlmProviderId, boolean | null>>;
  activeModelRoster: readonly LlmModelRouteState[];
  routingPolicy: LlmRoutingPolicyState;
  activeRouteAvailable: boolean | null;
  credential: LlmCredentialState;
  paperOnly: boolean | null;
  liveBlocked: boolean | null;
}

export interface HealthVariable {
  name: string;
  value: string;
  severity: Severity;
}

export interface HomeostasisState {
  healthStatus: string | null;
  variables: readonly HealthVariable[];
  interventions: readonly string[];
}

export interface ObservatoryDatum {
  id: string;
  title: string;
  status: string | null;
  detail: string | null;
  value: string | null;
  confidence: number | null;
  dataReads: number | null;
  gapCount: number | null;
}

export interface ObservatoryState {
  generatedUtc: string | null;
  status: string | null;
  stale: boolean | null;
  agents: readonly ObservatoryDatum[];
  shadowGuards: readonly ObservatoryDatum[];
  evolutionCandidates: readonly ObservatoryDatum[];
  hypotheses: readonly ObservatoryDatum[];
  technicalTimeframes: readonly ObservatoryDatum[];
  constitutionInvariants: readonly ObservatoryDatum[];
}

export interface StrategyDossierState {
  status: string | null;
  runId: string | null;
  headline: string | null;
  runDirectory: string | null;
  candidateCount: number | null;
  eligibleCandidateCount: number | null;
  diagnosticFrontierCount: number | null;
  frontierStatus: string | null;
  frontierCandidateIds: readonly string[];
  tradeCount: number | null;
  grossModelUnitPnl: number | null;
  netModelUnitPnl: number | null;
  totalCostModelUnits: number | null;
  effectiveTrials: number | null;
  mutationAttempts: number | null;
  realHistoryUsed: boolean | null;
  realOptionChainUsed: boolean | null;
  truthDecision: string | null;
  fitnessDecision: string | null;
  promotionAllowed: boolean | null;
  capitalNormalizationStatus: string | null;
  capitalCompleteCandidateCount: number | null;
}

export interface MutationNode {
  nodeId: string;
  parentId: string | null;
  family: string;
  mutationType: string;
  status: string;
  score: number | null;
  scoreDelta: number | null;
  reasons: readonly string[];
  behaviorSignature: string | null;
}

export interface MutationEdge {
  edgeId: string;
  parentId: string;
  childId: string;
  mutationType: string;
  status: string;
}

export interface MutationFamilyBudget {
  family: string;
  attemptCount: number | null;
  allocationShare: number | null;
  frontierCandidateCount: number | null;
  rejectedCount: number | null;
  degradedCount: number | null;
  concentrationAlert: boolean | null;
}

export interface MutationGenealogyState {
  status: string | null;
  method: string | null;
  methodReason: string | null;
  registryRecordCount: number | null;
  nodeCount: number | null;
  edgeCount: number | null;
  prunedBranchCount: number | null;
  duplicateCandidateCount: number | null;
  mutationAttemptCount: number | null;
  paretoFrontierIds: readonly string[];
  nodes: readonly MutationNode[];
  edges: readonly MutationEdge[];
  familyBudgets: readonly MutationFamilyBudget[];
  uniqueChampionCount: number | null;
  championChangeCount: number | null;
  longestChampionStreak: number | null;
}

export interface BinomialOracleState {
  status: string | null;
  passedTestCount: number | null;
  failedTestCount: number | null;
  testCount: number | null;
  pricingSourceTier: string | null;
  realOptionChainAbsent: boolean | null;
  americanPutEarlyExerciseNodes: number | null;
  discreteDividendCallEarlyExerciseNodes: number | null;
  convergenceError400Steps: number | null;
  promotionAllowed: boolean | null;
  sensitivityPointCount: number | null;
  oddEvenPriceGap: number | null;
}

export interface EvidenceContractState {
  status: string | null;
  issueCount: number | null;
  artifactCount: number | null;
  registryHash: string | null;
  cycleStatus: string | null;
}

export interface ContextSettlementState {
  status: string | null;
  outcomeStatus: string | null;
  decisionCount: number | null;
  selectedDecisionCount: number | null;
  newlyResolvedCount: number | null;
  resolvedCountAfter: number | null;
  unresolvedCountAfter: number | null;
  resolutionAsOf: string | null;
  loadedRowCount: number | null;
  selectiveHashValidation: boolean | null;
  decisionLedgerImmutable: boolean | null;
}

export interface EvidenceIntelligenceState {
  dossier: StrategyDossierState;
  mutation: MutationGenealogyState;
  oracle: BinomialOracleState;
  settlement: ContextSettlementState;
  contracts: EvidenceContractState;
}

export interface SourceState {
  id: string;
  name: string;
  status: string | null;
  severity: Severity;
  freshness: string | null;
  observedUtc: string | null;
  fileModifiedUtc: string | null;
  boundaryValid: boolean | null;
  detail: string | null;
}

export interface IssueState {
  id: string;
  severity: Severity;
  message: string;
  detail: string | null;
}

export interface AnalyticsFoldMetric {
  readonly candidateId: string;
  readonly family: string;
  readonly structure: string;
  readonly era: string;
  readonly sampleCount: number | null;
  readonly expectancyModelUnits: number | null;
  readonly netModelUnits: number | null;
  readonly winRate: number | null;
  readonly profitFactor: number | null;
  readonly meetsMinimumSample: boolean | null;
}

export interface AnalyticsRobustnessGate {
  readonly candidateId: string;
  readonly gateId: string;
  readonly status: string;
  readonly observed: string;
  readonly required: string;
  readonly diagnosticOnly: boolean;
}

export interface AnalyticsParetoPoint {
  readonly candidateId: string;
  readonly tradeCount: number | null;
  readonly symbolCount: number | null;
  readonly expectancyModelUnits: number | null;
  readonly stressedExpectancyModelUnits: number | null;
  readonly maxDrawdownModelUnits: number | null;
  readonly tailLossP05ModelUnits: number | null;
  readonly foldStability: number | null;
  readonly positiveFoldCount: number | null;
  readonly gateFailureCount: number | null;
  readonly eligible: boolean | null;
  readonly evidenceClass: string;
}

export interface AnalyticsEquityPoint {
  readonly date: string;
  readonly tradeCount: number | null;
  readonly grossModelUnits: number | null;
  readonly costModelUnits: number | null;
  readonly netModelUnits: number | null;
  readonly cumulativeModelUnits: number | null;
  readonly drawdownModelUnits: number | null;
}

export interface AnalyticsFailureRank {
  readonly failureId: string;
  readonly candidateCount: number;
}

export interface AnalyticsSelectionPressure {
  readonly candidateCount: number | null;
  readonly eligibleCandidateCount: number | null;
  readonly diagnosticFrontierCount: number | null;
  readonly tradeCount: number | null;
  readonly effectiveTrials: number | null;
  readonly mutationAttempts: number | null;
  readonly deflatedSharpeDiagnostic: number | null;
}

export interface EvidenceAnalyticsState {
  readonly status: string;
  readonly runId: string | null;
  readonly evidenceClass: string | null;
  readonly foldMetrics: readonly AnalyticsFoldMetric[];
  readonly robustnessTests: readonly AnalyticsRobustnessGate[];
  readonly paretoFrontier: readonly AnalyticsParetoPoint[];
  readonly equityCurve: readonly AnalyticsEquityPoint[];
  readonly failureRanking: readonly AnalyticsFailureRank[];
  readonly selectionPressure: AnalyticsSelectionPressure;
}

export interface ReadinessAnalyticsLane {
  readonly laneId: string;
  readonly priority: number | null;
  readonly current: number | null;
  readonly required: number | null;
  readonly remaining: number | null;
  readonly thresholdUnchanged: boolean | null;
  readonly acceleration: string | null;
  readonly missingChecks: readonly string[];
  readonly estimatedTradingDays: number | null;
  readonly estimateOnlyNotAPromise: boolean | null;
  readonly maturityLagDays: number | null;
}

export interface ReadinessGovernanceState {
  readonly gatePolicyChanged: boolean | null;
  readonly removedGateIds: readonly string[];
  readonly remainingThresholdsLowered: boolean | null;
  readonly reproducibilityHash: string | null;
}

export interface ReadinessAnalyticsState {
  readonly status: string;
  readonly contextEvidenceStatus: string | null;
  readonly lanes: readonly ReadinessAnalyticsLane[];
  readonly governance: ReadinessGovernanceState;
  readonly newsPipelineStatus: string | null;
  readonly newsRequiredCoverageComplete: boolean | null;
  readonly newsFailedSourceIds: readonly string[];
}

export interface PaperAnalyticsPosition {
  readonly positionId: string;
  readonly symbol: string;
  readonly status: "open" | "closed" | "unknown";
  readonly structure: string | null;
  readonly direction: string;
  readonly sector: string;
  readonly entryDate: string | null;
  readonly lastMarkDate: string | null;
  readonly ageDays: number | null;
  readonly quoteAgeDays: number | null;
  readonly relativeSpread: number | null;
  readonly entryFill: number | null;
  readonly lastMarkBid: number | null;
  readonly pathPnl: number | null;
  readonly pricingSourceTier: string | null;
  readonly quotePriced: boolean | null;
}

export interface PaperExposure {
  readonly axis: string;
  readonly key: string;
  readonly positionCount: number;
  readonly entryPremiumUnits: number;
}

export interface PaperAnalyticsState {
  readonly status: string;
  readonly asOfDate: string | null;
  readonly openCount: number | null;
  readonly closedCount: number | null;
  readonly closedRequired: number | null;
  readonly positions: readonly PaperAnalyticsPosition[];
  readonly exposures: readonly PaperExposure[];
}

export interface OptionsSurfacePoint {
  readonly expiry: string;
  readonly dte: number | null;
  readonly optionType: string;
  readonly strike: number | null;
  readonly moneyness: number | null;
  readonly bid: number | null;
  readonly ask: number | null;
  readonly mid: number | null;
  readonly impliedVol: number | null;
  readonly volume: number | null;
  readonly openInterest: number | null;
  readonly relativeSpread: number | null;
}

export interface IvMultiplierPoint {
  readonly symbol: string;
  readonly contracts: number | null;
  readonly multiplier: number | null;
}

export interface IvCalibrationState {
  readonly status: string | null;
  readonly currentMultiplier: number | null;
  readonly recommendedMultiplier: number | null;
  readonly ivOverRvP25: number | null;
  readonly ivOverRvP75: number | null;
  readonly premiumErrorP25: number | null;
  readonly premiumErrorMedian: number | null;
  readonly premiumErrorP75: number | null;
  readonly symbolsCovered: number | null;
  readonly multipliers: readonly IvMultiplierPoint[];
}

export interface OptionsAnalyticsState {
  readonly status: string;
  readonly snapshotDate: string | null;
  readonly symbol: string | null;
  readonly availableSymbols: readonly string[];
  readonly surface: readonly OptionsSurfacePoint[];
  readonly ivCalibration: IvCalibrationState;
}

export interface CalibrationBin {
  readonly lower: number | null;
  readonly upper: number | null;
  readonly meanConfidence: number | null;
  readonly accuracy: number | null;
  readonly count: number | null;
}

export interface CalibrationAnalyticsState {
  readonly status: string;
  readonly sampleSufficient: boolean | null;
  readonly settledTotal: number | null;
  readonly pendingTotal: number | null;
  readonly minimumSample: number | null;
  readonly ece: number | null;
  readonly mce: number | null;
  readonly brier: number | null;
  readonly logLoss: number | null;
  readonly bins: readonly CalibrationBin[];
}

export interface SignalCalibrationState {
  readonly status: string;
  readonly semantics: string | null;
  readonly settledTotal: number | null;
  readonly overallHitRate: number | null;
  readonly contestedTotal: number | null;
  readonly contestedHitRate: number | null;
  readonly promotionAllowed: boolean | null;
}

export interface AgentAblationState {
  readonly status: string;
  readonly agentCount: number | null;
  readonly eligibleSettlementCount: number | null;
  readonly minimumSample: number | null;
  readonly protectedEvaluator: boolean | null;
  readonly evaluations: readonly Readonly<Record<string, unknown>>[];
}

export interface GatedCapabilityState {
  readonly status: string;
  readonly reason: string | null;
  readonly requiredEvidence: readonly string[];
}

export interface MachineLearningAnalyticsState {
  readonly calibration: CalibrationAnalyticsState;
  readonly signalCalibration: SignalCalibrationState;
  readonly agentAblation: AgentAblationState;
  readonly conformal: GatedCapabilityState;
  readonly shap: GatedCapabilityState;
  readonly embeddings: GatedCapabilityState;
  readonly training: GatedCapabilityState;
}

export interface AgentTelemetryEvent {
  readonly eventUtc: string;
  readonly runId: string;
  readonly agentId: string;
  readonly phase: string;
  readonly statusTransition: string;
  readonly inputArtifactHashes: readonly string[];
  readonly outputArtifactHashes: readonly string[];
  readonly durationMs: number | null;
  readonly error: string | null;
}

export interface TelemetryAnalyticsState {
  readonly status: string;
  readonly reason: string | null;
  readonly contractFields: readonly string[];
  readonly events: readonly AgentTelemetryEvent[];
  readonly observedLinkCount: number;
}

export interface RegimeHistoryPoint {
  readonly lane: string;
  readonly snapshotId: string;
  readonly fileCount: number;
}

export interface RegimeAnalyticsState {
  readonly status: string;
  readonly history: readonly RegimeHistoryPoint[];
  readonly transitionModel: GatedCapabilityState;
  readonly distributionDrift: GatedCapabilityState;
}

export interface AnalyticsSourceState {
  readonly sourceId: string;
  readonly relativePath: string;
  readonly status: string;
  readonly sha256: string | null;
  readonly detail: string;
}

export interface DesktopAnalyticsState {
  readonly schemaVersion: string | null;
  readonly status: string;
  readonly evidence: EvidenceAnalyticsState;
  readonly readiness: ReadinessAnalyticsState;
  readonly paper: PaperAnalyticsState;
  readonly options: OptionsAnalyticsState;
  readonly machineLearning: MachineLearningAnalyticsState;
  readonly telemetry: TelemetryAnalyticsState;
  readonly regime: RegimeAnalyticsState;
  readonly sources: readonly AnalyticsSourceState[];
  readonly errors: readonly string[];
}

export type PlaybookListId =
  | "short_term_bullish"
  | "short_term_bearish"
  | "long_term_bullish"
  | "long_term_bearish"
  | "overall";

export type PlaybookDirectionalBias = "bullish" | "bearish";

export interface PlaybookCatalyst {
  readonly catalystType: string;
  readonly date: string | null;
  readonly status: string | null;
}

export interface PlaybookScoreBreakdown {
  readonly withinSetupSignal: number | null;
  readonly independentFamilyAgreement: number | null;
  readonly forwardTrust: number | null;
  readonly directionNeutralAttention: number | null;
  readonly liquidity: number | null;
  readonly universeSelection: number | null;
  readonly swingDirectionalSupport: number | null;
  readonly valuationFit: number | null;
  readonly oppositionPenalty: number | null;
}

export interface PlaybookSetupEvidence {
  readonly detectionId: string;
  readonly setupId: string;
  readonly family: string;
  readonly withinSetupPercentile: number | null;
  readonly horizonDays: readonly number[];
  readonly details: Readonly<Record<string, unknown>>;
  readonly lineage: readonly string[];
}

export interface PlaybookTrustEvidence {
  readonly setupId: string;
  readonly trustState: string;
  readonly settled: number | null;
  readonly hitRate: number | null;
  readonly horizonMatch: string | null;
}

export interface PlaybookAttentionContext {
  readonly score: number | null;
  readonly status: string | null;
  readonly freshnessStatus: string | null;
  readonly completenessRatio: number | null;
  readonly drivers: readonly string[];
  readonly missingComponents: readonly string[];
  readonly provenanceSha256: string | null;
  readonly directionalUse: string | null;
}

export interface PlaybookTradability {
  readonly researchTradable: boolean | null;
  readonly tier: string | null;
  readonly marketCap: number | null;
  readonly averageDollarVolume20d: number | null;
  readonly selectionScore: number | null;
  readonly reasonCodes: readonly string[];
  readonly evidenceHash: string | null;
}

export interface PlaybookRecommendation {
  readonly recommendationId: string;
  readonly rank: number | null;
  readonly symbol: string;
  readonly category: Exclude<PlaybookListId, "overall">;
  readonly horizon: string;
  readonly horizonLabel: string | null;
  readonly directionalBias: PlaybookDirectionalBias;
  readonly predictionLabel: string | null;
  readonly researchPriorityScore: number | null;
  readonly rankScoreIsNotProbability: boolean | null;
  readonly recommendationState: string | null;
  readonly confidenceLabel: string | null;
  readonly thesisSummary: string | null;
  readonly variantWedge: string | null;
  readonly whyNow: readonly string[];
  readonly firstRejection: string | null;
  readonly whatWouldMakeInvestable: readonly string[];
  readonly whatWouldKillIt: readonly string[];
  readonly catalysts: readonly PlaybookCatalyst[];
  readonly risks: readonly string[];
  readonly missingEvidence: readonly string[];
  readonly scoreBreakdown: PlaybookScoreBreakdown;
  readonly setupEvidence: readonly PlaybookSetupEvidence[];
  readonly trustEvidence: readonly PlaybookTrustEvidence[];
  readonly attentionContext: PlaybookAttentionContext;
  readonly tradability: PlaybookTradability;
  readonly technicalEvidence: Readonly<Record<string, unknown>>;
  readonly fundamentalEvidence: Readonly<Record<string, unknown>>;
  readonly valuationContext: Readonly<Record<string, unknown>>;
  readonly competingContext: Readonly<Record<string, unknown>>;
  readonly researchInvalidationPrice: number | null;
  readonly marketDataAsOf: string | null;
  readonly executionState: string | null;
  readonly orderConstructionAllowed: boolean | null;
  readonly tradePromotionAllowed: boolean | null;
  readonly bearishExpressionPolicy: string | null;
}

export interface PlaybookSourceArtifact {
  readonly sourceId: string;
  readonly relativePath: string | null;
  readonly sha256: string | null;
  readonly status: string | null;
}

export interface PlaybookRankingMethod {
  readonly directionSource: string | null;
  readonly attentionUse: string | null;
  readonly strengthNormalization: string | null;
  readonly crossSetupRawStrengthCompared: boolean | null;
  readonly longTermTrustIndependentlySettled: boolean | null;
  readonly rankScoreIsNotProbability: boolean | null;
  readonly noPaddingWhenInsufficient: boolean | null;
}

export interface PlaybookState {
  readonly artifactType: string | null;
  readonly schemaVersion: string | null;
  readonly status: string;
  readonly generatedUtc: string | null;
  readonly marketDataAsOf: string | null;
  readonly attentionAsOf: string | null;
  readonly attentionGeneratedUtc: string | null;
  readonly nextRefreshDueUtc: string | null;
  readonly refreshIntervalMinutes: number | null;
  readonly universeActiveCount: number | null;
  readonly universeMaximumCount: number | null;
  readonly eligibleSingleStockCount: number | null;
  readonly lists: Readonly<Record<PlaybookListId, readonly string[]>>;
  readonly missingSlotsByList: Readonly<Record<Exclude<PlaybookListId, "overall">, number | null>>;
  readonly recommendations: Readonly<Record<string, PlaybookRecommendation>>;
  readonly recommendationCount: number | null;
  readonly sourceArtifacts: readonly PlaybookSourceArtifact[];
  readonly rankingMethod: PlaybookRankingMethod;
  readonly rankScoreIsNotProbability: boolean | null;
  readonly orderConstructionAllowed: boolean | null;
  readonly tradePromotionAllowed: boolean | null;
  readonly liveExecutionAllowed: boolean | null;
  readonly brokerAuthority: boolean | null;
  readonly paperOnly: boolean | null;
  readonly liveBlocked: boolean | null;
  readonly contentHash: string | null;
  readonly reproducibilityHash: string | null;
}

export interface DopeySnapshot {
  schemaVersion: string | null;
  generatedUtc: string | null;
  headline: string | null;
  envelope: EnvelopeState;
  hostCapabilities: HostCapabilities;
  liveBranch: LiveBranchState;
  researchCore: ResearchCoreState;
  readiness: ReadinessState;
  universe: UniverseState;
  schedule: ScheduleState;
  paperBook: PaperBookState;
  world: WorldState;
  extremes: ExtremesState;
  metacognition: MetacognitionState;
  llmResearch: LlmResearchState;
  llmProviderControl: LlmProviderControlState;
  homeostasis: HomeostasisState;
  observatory: ObservatoryState;
  evidence: EvidenceIntelligenceState;
  analytics: DesktopAnalyticsState;
  playbook: PlaybookState;
  sources: readonly SourceState[];
  issues: readonly IssueState[];
}

export interface ControlModel {
  connection: ConnectionPhase;
  connectionDetail: string;
  snapshot: DopeySnapshot;
}

export type ChartTimeframe = "daily" | "weekly" | "monthly";
export type HeadCoachId = "claude" | "codex";

export interface ChartBar {
  readonly date: string;
  readonly open: number;
  readonly high: number;
  readonly low: number;
  readonly close: number;
  readonly volume: number;
}

export interface ChartPattern {
  readonly id: string;
  readonly pattern: string;
  readonly family: string;
  readonly directionalBias: string;
  readonly probability: number | null;
  readonly evidenceQuality: number | null;
  readonly asOf: string | null;
  readonly failureCondition: string | null;
  readonly oscillator: string | null;
  readonly divergenceType: string | null;
}

export interface ChartIndicator {
  readonly indicator: string;
  readonly value: number | null;
  readonly percentile: number | null;
  readonly slope: number | null;
  readonly state: string;
  readonly reliability: number | null;
}

export interface GroundedNumericFact {
  readonly levelRef: string;
  readonly label: string;
  readonly valueDecimal: string;
  readonly canonicalDisplay: string;
  readonly unit: string;
  readonly derivation: string;
}

export interface GroundedChartStructure {
  readonly structureId: string;
  readonly definitionId: string;
  readonly structureType: string;
  readonly directionalBias: string;
  readonly availableAt: string;
  readonly levelRefs: readonly string[];
  readonly candidateNotTruth: boolean;
}

export interface BlindReplayEvidence {
  readonly status: string;
  readonly decisionCutoff: string | null;
  readonly revealEnd: string | null;
  readonly revealBarCount: number;
  readonly replayHash: string | null;
  readonly optionOutcomeStatus: string;
  readonly lookaheadBlocked: boolean;
}

export interface ChartPayload {
  readonly schemaVersion: string;
  readonly symbol: string;
  readonly timeframe: ChartTimeframe;
  readonly asOf: string;
  readonly bars: readonly ChartBar[];
  readonly overlays: Readonly<Record<string, readonly (number | null)[]>>;
  readonly oscillators: Readonly<Record<string, readonly (number | null)[]>>;
  readonly patterns: readonly ChartPattern[];
  readonly divergences: readonly ChartPattern[];
  readonly indicators: readonly ChartIndicator[];
  readonly indicatorCount: number;
  readonly patternFamilyCount: number;
  readonly groundedStructures: readonly GroundedChartStructure[];
  readonly numericFacts: readonly GroundedNumericFact[];
  readonly groundedEvidenceHash: string;
  readonly viewportIsDetectorInput: boolean;
  readonly blindReplay: BlindReplayEvidence;
  readonly contentHash: string;
  readonly syntheticDataUsed: boolean;
  readonly networkFetchPerformed: boolean;
  readonly paperOnly: boolean;
  readonly liveBlocked: boolean;
}

export interface CoachHypothesis {
  readonly title: string;
  readonly mechanism: string;
  readonly evidenceNeeded: string;
  readonly falsification: string;
}

export interface CoachAdversarialFinding {
  readonly title: string;
  readonly risk: string;
  readonly evidenceNeeded: string;
}

export interface CoachExperiment {
  readonly title: string;
  readonly objective: string;
  readonly expectedInformationGain: string;
  readonly falsification: string;
  readonly safetyConstraints: string;
}

export interface CoachAnalysis {
  readonly summary: string;
  readonly hypotheses: readonly CoachHypothesis[];
  readonly adversarialFindings: readonly CoachAdversarialFinding[];
  readonly uncertainties: readonly string[];
  readonly recommendedExperiments: readonly CoachExperiment[];
  readonly abstain: boolean;
}

export interface TwoCoachReview {
  readonly schemaVersion: string;
  readonly sessionId: string;
  readonly status: string;
  readonly verdict: string;
  readonly sessionHash: string;
  readonly headCoachId: HeadCoachId;
  readonly headCoachModel: string;
  readonly routeId: string;
  readonly supportingModels: readonly string[];
  readonly evidenceCoachId: string;
  readonly structureCount: number;
  readonly numericFactCount: number;
  readonly lessonCount: number;
  readonly numericGroundingStatus: string;
  readonly referenceCount: number;
  readonly analysis: CoachAnalysis;
  readonly paidResponseCount: number;
  readonly reportedCostUsd: number | null;
  readonly optionClaimStatus: string;
  readonly researchOnly: boolean;
  readonly paperOnly: boolean;
  readonly liveBlocked: boolean;
  readonly brokerAccess: boolean;
  readonly orderAuthority: boolean;
  readonly runtimeFallbackUsed: boolean;
}

export type SymbolLabStrategyMode =
  | "auto"
  | "trend"
  | "momentum"
  | "breakout"
  | "mean_reversion"
  | "volatility"
  | "bullish_scenario"
  | "bearish_scenario";

export interface SymbolLabZone {
  readonly zoneMid: number;
  readonly zoneLow: number;
  readonly zoneHigh: number;
  readonly role: string;
  readonly distancePct: number | null;
  readonly confluenceScore: number | null;
  readonly timeframes: readonly string[];
}

export interface SymbolLabStrategyResult {
  readonly strategyId: string;
  readonly family: string;
  readonly direction: string;
  readonly thesis: string;
  readonly currentSignalActive: boolean;
  readonly sampleCount: number;
  readonly meanNetReturn: number;
  readonly selectionAdjustedMean: number;
  readonly hitRate: number;
  readonly positiveFoldRate: number;
  readonly worstFoldMean: number;
  readonly robustnessScore: number;
  readonly evidenceStatus: string;
}

export interface SymbolLabPlan {
  readonly planId: string;
  readonly family: string;
  readonly direction: string;
  readonly status: string;
  readonly strategyId: string | null;
  readonly trigger: string;
  readonly invalidationPrice: number | null;
  readonly scenarioTargetPrice: number | null;
  readonly optionsExpressionBias: string;
  readonly confidenceCap: number;
}

export interface SymbolLabExpression {
  readonly expressionId: string;
  readonly expressionType: string;
  readonly expiry: string;
  readonly dte: number;
  readonly strike: number | null;
  readonly longStrike: number | null;
  readonly shortStrike: number | null;
  readonly bid: number | null;
  readonly ask: number | null;
  readonly impliedVol: number | null;
  readonly spreadPct: number | null;
  readonly scenarioModelValue: number;
  readonly projectedPnl: number;
  readonly projectedReturn: number;
  readonly maximumLoss: number;
  readonly delta: number | null;
  readonly theta: number | null;
  readonly liquidityScore: number | null;
  readonly valueScore: number;
  readonly activePolicyEligible: boolean;
}

export interface SymbolLabScenarioPoint {
  readonly stockPrice: number;
  readonly elapsedDays: number;
  readonly remainingDte: number;
  readonly theoreticalValue: number;
}

export interface SymbolLabPayload {
  readonly schemaVersion: string;
  readonly symbol: string;
  readonly asOf: string;
  readonly generatedUtc: string;
  readonly selectedDirection: string;
  readonly directionSource: string;
  readonly selectedStrategyId: string | null;
  readonly request: {
    readonly strategyMode: SymbolLabStrategyMode;
    readonly scenarioPriceRequested: number | null;
    readonly scenarioPriceEffective: number;
    readonly daysForward: number;
    readonly ivShift: number;
  };
  readonly marketProfile: {
    readonly currentPrice: number;
    readonly dailyAtr: number;
    readonly realizedVol: number;
    readonly timeframeDirection: string;
    readonly timeframeAgreement: number;
    readonly nearestSupport: SymbolLabZone | null;
    readonly nearestResistance: SymbolLabZone | null;
    readonly earningsDate: string | null;
    readonly daysUntilEarnings: number | null;
    readonly earningsStatus: string;
    readonly chainStatus: string;
    readonly chainSnapshotDate: string | null;
    readonly contractCount: number;
    readonly expiryCount: number;
    readonly medianSpreadPct: number | null;
    readonly putCallOiRatio: number | null;
    readonly nearAtmSkew: number | null;
    readonly zones: readonly SymbolLabZone[];
  };
  readonly indicatorCount: number;
  readonly divergenceCount: number;
  readonly strategies: readonly SymbolLabStrategyResult[];
  readonly activeStrategyIds: readonly string[];
  readonly plans: readonly SymbolLabPlan[];
  readonly projectorStatus: string;
  readonly eligibleContractCount: number;
  readonly bestExpression: SymbolLabExpression | null;
  readonly expressions: readonly SymbolLabExpression[];
  readonly scenarioSurface: readonly SymbolLabScenarioPoint[];
  readonly knowledgeBoundaries: readonly string[];
  readonly contentHash: string;
  readonly syntheticDataUsed: boolean;
  readonly paperOnly: boolean;
  readonly liveBlocked: boolean;
}

export type ViewId =
  | "command"
  | "market"
  | "chart"
  | "lab"
  | "playbook"
  | "organisms"
  | "truth"
  | "evidence"
  | "evolution"
  | "paper"
  | "constitution";
