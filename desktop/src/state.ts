import type {
  AutomationScheduleState,
  ConfidenceDimension,
  ControlModel,
  CorePhase,
  DopeySnapshot,
  MutationEdge,
  MutationFamilyBudget,
  MutationNode,
  HealthVariable,
  HostCapabilities,
  InstrumentMode,
  IssueState,
  LlmModelRouteState,
  LlmProviderId,
  LlmRoutingPolicyState,
  OptionExtreme,
  ObservatoryDatum,
  PaperPosition,
  ReadinessCheck,
  ScheduleLane,
  Severity,
  SourceState,
  StockExtreme,
  UniverseSymbol,
  WorldRegime,
} from "./types";
import { emptyAnalyticsState, normalizeAnalytics } from "./analyticsState";
import { emptyPlaybookState, normalizePlaybook } from "./playbookState";

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const recordAt = (record: UnknownRecord, key: string): UnknownRecord => {
  const value = record[key];
  return isRecord(value) ? value : {};
};

const valueAtPath = (record: UnknownRecord, path: readonly string[]): unknown => {
  let cursor: unknown = record;
  for (const segment of path) {
    if (!isRecord(cursor)) {
      return undefined;
    }
    cursor = cursor[segment];
  }
  return cursor;
};

const firstValue = (record: UnknownRecord, paths: readonly (readonly string[])[]): unknown => {
  for (const path of paths) {
    const value = valueAtPath(record, path);
    if (value !== undefined && value !== null) {
      return value;
    }
  }
  return null;
};

const asString = (value: unknown): string | null => {
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const asBoolean = (value: unknown): boolean | null => {
  if (typeof value === "boolean") {
    return value;
  }
  if (value === 1 || value === "1" || value === "true" || value === "TRUE") {
    return true;
  }
  if (value === 0 || value === "0" || value === "false" || value === "FALSE") {
    return false;
  }
  return null;
};

const stringArray = (value: unknown): readonly string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(asString).filter((item): item is string => item !== null);
};

const recordArray = (value: unknown): readonly UnknownRecord[] =>
  Array.isArray(value) ? value.filter(isRecord) : [];

const normalizeCorePhase = (value: unknown, enabled: boolean | null): CorePhase => {
  const raw = asString(value)?.toUpperCase() ?? "";
  if (raw.includes("DRAIN")) {
    return "DRAINING";
  }
  if (raw.includes("FAULT") || raw.includes("ERROR") || raw.includes("FAIL")) {
    return "FAULT";
  }
  if (raw.includes("RUN")) {
    return "RUNNING";
  }
  if (raw === "ON" || raw.includes("ACTIVE") || raw.includes("ENABLED")) {
    return "ON";
  }
  if (raw === "OFF" || raw.includes("STOP") || raw.includes("DISABLED")) {
    return "OFF";
  }
  if (enabled === true) {
    return "ON";
  }
  if (enabled === false) {
    return "OFF";
  }
  return "UNKNOWN";
};

const normalizeInstrumentMode = (value: unknown): InstrumentMode | null => {
  const mode = asString(value)?.toLowerCase();
  return mode === "stocks" || mode === "options" || mode === "both" ? mode : null;
};

const providerFlags = (value: unknown): Readonly<Record<LlmProviderId, boolean | null>> => {
  const record = isRecord(value) ? value : {};
  return {
    openrouter: asBoolean(record["openrouter"]),
    openrouter_hybrid: asBoolean(record["openrouter_hybrid"]),
    claude: asBoolean(record["claude"]),
    codex: asBoolean(record["codex"]),
  };
};

const modelRoster = (value: unknown): readonly LlmModelRouteState[] =>
  recordArray(value).map((record) => ({
    routeId: asString(record["route_id"]) ?? "unknown_route",
    modelId: asString(record["model_id"]) ?? "unknown_model",
    role: asString(record["role"]) ?? "unknown_role",
    stage: asString(record["stage"]) ?? "unknown_stage",
    provider: asString(record["provider"]) ?? "unknown_provider",
  }));

const routingPolicy = (value: unknown): LlmRoutingPolicyState => {
  const record = isRecord(value) ? value : {};
  return {
    provider: asString(record["provider"]),
    routeId: asString(record["route_id"]),
    strategy: asString(record["strategy"]),
    stageOrder: stringArray(record["stage_order"]),
    allModelStagesRequired: asBoolean(record["all_model_stages_required"]),
    fallbackAllowed: asBoolean(record["fallback_allowed"]),
    independentExternalRoutesAllowed: asBoolean(record["independent_external_routes_allowed"]),
  };
};

const severityFrom = (value: unknown): Severity => {
  const raw = asString(value)?.toLowerCase() ?? "";
  if (
    raw.includes("critical") ||
    raw.includes("fatal") ||
    raw.includes("error") ||
    raw.includes("fault") ||
    raw.includes("missing") ||
    raw.includes("unreadable") ||
    raw.includes("invalid") ||
    raw.includes("corrupt")
  ) {
    return "critical";
  }
  if (raw.includes("warn") || raw.includes("stale") || raw.includes("degrad")) {
    return "warning";
  }
  if (raw.includes("notice") || raw.includes("pending") || raw.includes("unknown")) {
    return "notice";
  }
  if (
    raw.includes("ok") ||
    raw.includes("healthy") ||
    raw.includes("nominal") ||
    raw.includes("pass") ||
    raw.includes("available")
  ) {
    return "nominal";
  }
  return "unknown";
};

const normalizeAutomationSchedule = (
  item: UnknownRecord,
  index: number,
): AutomationScheduleState => {
  const name = asString(firstValue(item, [["task_name"], ["name"], ["id"]])) ??
    `schedule-${index + 1}`;
  return {
    id: name,
    name,
    present: asBoolean(firstValue(item, [["present"], ["exists"]])),
    enabled: asBoolean(firstValue(item, [["enabled"], ["active"]])),
    state: asString(firstValue(item, [["state"], ["status"], ["phase"]])),
    identityVerified: asBoolean(firstValue(item, [["identity_verified"], ["verified"]])),
    actionVerified: asBoolean(firstValue(item, [["action_verified"], ["configuration_valid"]])),
    verificationIssues: stringArray(firstValue(item, [["verification_issues"], ["issues"]])),
  };
};

const normalizeAutomationSchedules = (
  coreTask: UnknownRecord,
  auxiliaryTasks: unknown,
): readonly AutomationScheduleState[] => {
  const records = [
    ...(Object.keys(coreTask).length === 0 ? [] : [coreTask]),
    ...recordArray(auxiliaryTasks),
  ];
  const seen = new Set<string>();
  return records
    .map(normalizeAutomationSchedule)
    .filter((schedule) => {
      if (seen.has(schedule.id)) {
        return false;
      }
      seen.add(schedule.id);
      return true;
    });
};

const automationSchedulesValidated = (
  schedules: readonly AutomationScheduleState[],
): boolean | null => {
  if (schedules.length === 0) {
    return null;
  }
  const requiredScheduleNames = new Set([
    "DOPEY_AccelerationCycle",
    "DOPEY_DailyRitual",
  ]);
  if (
    schedules.length !== requiredScheduleNames.size ||
    schedules.some((schedule) => !requiredScheduleNames.has(schedule.name))
  ) {
    return false;
  }
  return schedules.every(
    (schedule) =>
      schedule.present === true &&
      schedule.identityVerified === true &&
      schedule.actionVerified === true,
  );
};

const normalizePermanentNoLiveExecution = (hostCapabilities: UnknownRecord): boolean | null => {
  const direct = asBoolean(firstValue(hostCapabilities, [
    ["permanent_no_live_execution"],
    ["live_execution_permanently_absent"],
    ["desktop_live_path_permanently_absent"],
    ["permanent_live_path_absent"],
  ]));
  if (direct !== null) {
    return direct;
  }
  const liveCapabilityPresent = asBoolean(firstValue(hostCapabilities, [
    ["live_execution_capability_present"],
  ]));
  if (liveCapabilityPresent !== null) {
    return !liveCapabilityPresent;
  }
  const capability = asString(firstValue(hostCapabilities, [
    ["live_execution_capability"],
    ["live_order_capability"],
    ["live_path_capability"],
  ]))?.toLowerCase();
  if (capability === undefined) {
    return null;
  }
  if (capability.includes("permanent") && (capability.includes("absent") || capability.includes("none"))) {
    return true;
  }
  return false;
};

const normalizeChecks = (value: unknown): readonly ReadinessCheck[] =>
  recordArray(value).map((item, index) => ({
    id: asString(firstValue(item, [["check_id"], ["gate_id"], ["id"], ["name"]])) ?? `check-${index + 1}`,
    label: asString(firstValue(item, [["label"], ["name"], ["check_id"], ["gate_id"], ["id"]])) ?? `Check ${index + 1}`,
    status: asString(firstValue(item, [["status"], ["result"], ["state"]])) ?? "UNKNOWN",
    detail: asString(firstValue(item, [["detail"], ["reason"], ["message"]])),
  }));

const normalizeSymbols = (value: unknown): readonly UniverseSymbol[] =>
  Array.isArray(value)
    ? value
        .map((item): UniverseSymbol | null => {
          const directSymbol = asString(item);
          if (directSymbol !== null) {
            return { symbol: directSymbol, tier: null, status: "observed" };
          }
          if (!isRecord(item)) {
            return null;
          }
          const symbol = asString(firstValue(item, [["symbol"], ["ticker"], ["id"]]));
          return symbol === null
            ? null
            : {
                symbol,
                tier: asString(firstValue(item, [["tier"], ["cohort"], ["class"]])),
                status: asString(firstValue(item, [["status"], ["health"], ["freshness"]])),
              };
        })
        .filter((item): item is UniverseSymbol => item !== null)
    : [];

const normalizeTierCounts = (value: unknown): Readonly<Record<string, number>> => {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, item]) => [key, asNumber(item)] as const)
      .filter((entry): entry is readonly [string, number] => entry[1] !== null),
  );
};

const normalizeSchedule = (value: unknown): readonly ScheduleLane[] =>
  recordArray(value).map((item, index) => {
    const evidence = recordAt(item, "evidence_verification");
    return {
      id: asString(firstValue(item, [["lane_id"], ["id"], ["name"]])) ?? `lane-${index + 1}`,
      description: asString(firstValue(item, [["description"], ["label"], ["name"]])) ?? "Undescribed lane",
      due: asBoolean(firstValue(item, [["due"], ["is_due"]])),
      lastRunStatus: asString(firstValue(item, [["last_run_status"], ["status"], ["last_status"]])),
      windowOpen: asBoolean(firstValue(item, [["window_open"], ["is_window_open"]])),
      evidenceStatus: asString(firstValue(item, [["evidence_status"], ["data_status"]])) ??
        asString(firstValue(evidence, [["verification_status"], ["actual_status"]])),
      lastSuccessUtc: asString(firstValue(item, [["last_verified_success_utc"], ["last_success_utc"], ["last_success"], ["observed_utc"]])),
    };
  });

const normalizePosition = (item: UnknownRecord, index: number): PaperPosition => {
  const openedUtc = asString(firstValue(item, [["opened_utc"], ["entry_utc"], ["entry_date"], ["created_utc"]]));
  const closedUtc = asString(firstValue(item, [["closed_utc"], ["exit_utc"], ["exit_date"], ["settled_utc"]]));
  const explicitStatus = asString(firstValue(item, [["status"], ["state"], ["outcome"]]));
  return {
    id: asString(firstValue(item, [["position_id"], ["trade_id"], ["id"]])) ?? `position-${index + 1}`,
    symbol: asString(firstValue(item, [["symbol"], ["underlying"], ["ticker"]])) ?? "UNKNOWN",
    structure: asString(firstValue(item, [["structure"], ["strategy"], ["candidate_strategy"], ["instrument"]])),
    status: explicitStatus ?? (closedUtc === null ? "open paper position" : "closed paper outcome"),
    value: asNumber(firstValue(item, [["premium_units"], ["path_pnl"], ["trade_return"], ["pnl"], ["value"]])),
    openedUtc,
    closedUtc,
  };
};

const normalizePositions = (value: unknown): readonly PaperPosition[] =>
  recordArray(value).map(normalizePosition);

const normalizeStockExtremes = (
  value: unknown,
  direction: "up" | "down",
): readonly StockExtreme[] =>
  recordArray(value).map((item) => ({
    symbol: asString(firstValue(item, [["symbol"]])) ?? "UNKNOWN",
    direction,
    rank: asNumber(firstValue(item, [["direction_rank"], ["rank"]])),
    returnPct: asNumber(firstValue(item, [["latest_return_pct"], ["return_pct"]])),
    rsi14: asNumber(firstValue(item, [["rsi_14"]])),
  }));

const normalizeOptionExtremes = (
  value: unknown,
  tail: "winner" | "loser",
): readonly OptionExtreme[] =>
  recordArray(value).map((item) => ({
    symbol: asString(firstValue(item, [["symbol"]])) ?? "UNKNOWN",
    contractKey: asString(firstValue(item, [["contract_key"]])) ?? "UNKNOWN CONTRACT",
    tail,
    roiPct: asNumber(firstValue(item, [["roi_pct"]])),
    entryDate: asString(firstValue(item, [["entry_date"]])),
    exitDate: asString(firstValue(item, [["exit_date"]])),
  }));

const normalizeRegimes = (value: unknown): readonly WorldRegime[] =>
  (Array.isArray(value)
    ? recordArray(value).map((item, index) => [
        asString(firstValue(item, [["dimension"], ["name"], ["regime"]])) ?? `dimension-${index + 1}`,
        item,
      ] as const)
    : isRecord(value)
      ? Object.entries(value).filter((entry): entry is [string, UnknownRecord] => isRecord(entry[1]))
      : []
  ).map(([dimension, item]) => ({
    dimension,
    state: asString(firstValue(item, [["state"], ["label"], ["classification"]])) ?? "UNKNOWN",
    probability: asNumber(firstValue(item, [["probability"], ["confidence"], ["strength"]])),
    uncertainty: asNumber(firstValue(item, [["uncertainty"], ["entropy"], ["variance"]])),
    limitations: stringArray(firstValue(item, [["limitations"], ["caveats"]])),
  }));

const normalizeConfidence = (value: unknown): readonly ConfidenceDimension[] => {
  if (!isRecord(value)) {
    return [];
  }
  return Object.entries(value)
    .map(([name, rawValue]) => ({
      name,
      value: asNumber(isRecord(rawValue) ? firstValue(rawValue, [["value"], ["score"]]) : rawValue),
    }))
    .filter((dimension): dimension is ConfidenceDimension & { readonly value: number } => dimension.value !== null);
};

const scalarDisplay = (value: unknown): string => {
  const direct = asString(value);
  if (direct !== null) {
    return direct;
  }
  if (Array.isArray(value)) {
    return `${value.length} items`;
  }
  if (isRecord(value)) {
    return `${Object.keys(value).length} fields`;
  }
  return "UNKNOWN";
};

const normalizeHealth = (value: unknown): readonly HealthVariable[] => {
  if (Array.isArray(value)) {
    return value.filter(isRecord).map((item, index) => {
      const name = asString(firstValue(item, [["name"], ["variable"], ["id"]])) ?? `variable-${index + 1}`;
      const rawValue = firstValue(item, [["value"], ["state"], ["status"]]);
      return { name, value: scalarDisplay(rawValue), severity: severityFrom(firstValue(item, [["severity"], ["status"], ["state"]])) };
    });
  }
  if (isRecord(value)) {
    return Object.entries(value).map(([name, rawValue]) => ({
      name,
      value: scalarDisplay(rawValue),
      severity: severityFrom(rawValue),
    }));
  }
  return [];
};

const datumTitle = (item: UnknownRecord, index: number): string =>
  asString(firstValue(item, [["title"], ["name"], ["agent_id"], ["candidate_id"], ["hypothesis_id"], ["id"]])) ??
  `record-${index + 1}`;

const normalizeDataset = (value: unknown): readonly ObservatoryDatum[] => {
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      if (!isRecord(item)) {
        return {
          id: `record-${index + 1}`,
          title: scalarDisplay(item),
          status: null,
          detail: null,
          value: null,
          confidence: null,
          dataReads: null,
          gapCount: null,
        };
      }
      const title = datumTitle(item, index);
      return {
        id: asString(firstValue(item, [["id"], ["agent_id"], ["candidate_id"], ["hypothesis_id"]])) ?? title,
        title,
        status: asString(firstValue(item, [["status"], ["state"], ["phase"], ["promotion_state"]])),
        detail: asString(firstValue(item, [["detail"], ["description"], ["role"], ["thesis"]])),
        value: asString(firstValue(item, [["value"], ["score"], ["confidence"]])),
        confidence: asNumber(firstValue(item, [["confidence"]])),
        dataReads: asNumber(firstValue(item, [["data_reads"], ["read_count"]])),
        gapCount: asNumber(firstValue(item, [["gap_count"], ["data_gap_count"]])),
      };
    });
  }
  if (isRecord(value)) {
    return Object.entries(value).map(([key, item]) => {
      if (isRecord(item)) {
        return {
          id: key,
          title: asString(firstValue(item, [["title"], ["name"], ["id"]])) ?? key,
          status: asString(firstValue(item, [["status"], ["state"]])),
          detail: asString(firstValue(item, [["detail"], ["description"]])),
          value: asString(firstValue(item, [["value"], ["score"], ["count"]])),
          confidence: asNumber(firstValue(item, [["confidence"]])),
          dataReads: asNumber(firstValue(item, [["data_reads"], ["read_count"]])),
          gapCount: asNumber(firstValue(item, [["gap_count"], ["data_gap_count"]])),
        };
      }
      return {
        id: key,
        title: key,
        status: null,
        detail: null,
        value: scalarDisplay(item),
        confidence: null,
        dataReads: null,
        gapCount: null,
      };
    });
  }
  return [];
};

const normalizeMutationNodes = (value: unknown): readonly MutationNode[] =>
  recordArray(value).map((item, index) => ({
    nodeId: asString(firstValue(item, [["node_id"]])) ?? `mutation-node-${index + 1}`,
    parentId: asString(firstValue(item, [["parent_id"]])),
    family: asString(firstValue(item, [["family"]])) ?? "unknown",
    mutationType: asString(firstValue(item, [["mutation_type"]])) ?? "unknown",
    status: asString(firstValue(item, [["status"]])) ?? "unknown",
    score: asNumber(firstValue(item, [["score"]])),
    scoreDelta: asNumber(firstValue(item, [["score_delta"]])),
    reasons: stringArray(firstValue(item, [["reasons"]])),
    behaviorSignature: asString(firstValue(item, [["behavior_signature"]])),
  }));

const normalizeMutationEdges = (value: unknown): readonly MutationEdge[] =>
  recordArray(value).map((item, index) => ({
    edgeId: asString(firstValue(item, [["edge_id"]])) ?? `mutation-edge-${index + 1}`,
    parentId: asString(firstValue(item, [["parent_id"]])) ?? "unknown-parent",
    childId: asString(firstValue(item, [["child_id"]])) ?? "unknown-child",
    mutationType: asString(firstValue(item, [["mutation_type"]])) ?? "unknown",
    status: asString(firstValue(item, [["status"]])) ?? "unknown",
  }));

const normalizeMutationFamilyBudgets = (value: unknown): readonly MutationFamilyBudget[] =>
  recordArray(value).map((item, index) => ({
    family: asString(firstValue(item, [["family"]])) ?? `family-${index + 1}`,
    attemptCount: asNumber(firstValue(item, [["attempt_count"]])),
    allocationShare: asNumber(firstValue(item, [["allocation_share"]])),
    frontierCandidateCount: asNumber(firstValue(item, [["frontier_candidate_count"]])),
    rejectedCount: asNumber(firstValue(item, [["rejected_count"]])),
    degradedCount: asNumber(firstValue(item, [["degraded_count"]])),
    concentrationAlert: asBoolean(firstValue(item, [["concentration_alert"]])),
  }));

const normalizeSources = (value: unknown): readonly SourceState[] =>
  recordArray(value).map((item, index) => {
    const status = asString(firstValue(item, [["status"], ["state"], ["health"]]));
    const boundaryValid = asBoolean(firstValue(item, [
      ["boundary_valid"],
      ["safety_boundary_valid"],
      ["paper_boundary_valid"],
    ]));
    const reportedSeverity = severityFrom(firstValue(item, [["severity"], ["level"], ["status"], ["state"]]));
    return {
      id: asString(firstValue(item, [["source_id"], ["id"], ["name"]])) ?? `source-${index + 1}`,
      name: asString(firstValue(item, [["name"], ["source"], ["provider"], ["source_id"]])) ?? `Source ${index + 1}`,
      status,
      severity: boundaryValid === false ? "critical" : reportedSeverity,
      freshness: asString(firstValue(item, [["freshness"], ["freshness_status"], ["age"]])),
      observedUtc: asString(firstValue(item, [["observed_at"], ["observed_utc"], ["last_success_utc"], ["as_of"]])),
      fileModifiedUtc: asString(firstValue(item, [["file_modified_utc"], ["modified_utc"], ["mtime_utc"]])),
      boundaryValid,
      detail: asString(firstValue(item, [["detail"], ["message"], ["reason"], ["issue"], ["path"]])),
    };
  });

const progressRecord = (value: unknown, bottleneckId: string): UnknownRecord =>
  recordArray(value).find((item) => asString(item["bottleneck_id"]) === bottleneckId) ?? {};

const progressRequirements = (value: unknown): readonly string[] =>
  recordArray(value).map((item) => {
    const bottleneckId = asString(item["bottleneck_id"]) ?? "unnamed_bottleneck";
    const current = asNumber(item["current"]);
    const required = asNumber(item["required"]);
    if (current === null || required === null) {
      return bottleneckId;
    }
    return `${bottleneckId}: ${Math.round(current)} / ${Math.round(required)}`;
  });

const normalizeIssues = (value: unknown): readonly IssueState[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item, index) => {
    if (!isRecord(item)) {
      return { id: `issue-${index + 1}`, severity: "unknown", message: scalarDisplay(item), detail: null };
    }
    return {
      id: asString(firstValue(item, [["issue_id"], ["id"]])) ?? `issue-${index + 1}`,
      severity: severityFrom(firstValue(item, [["severity"], ["level"], ["status"]])),
      message: asString(firstValue(item, [["message"], ["title"], ["issue"], ["code"]])) ?? "Unspecified issue",
      detail: asString(firstValue(item, [["detail"], ["reason"], ["remediation"]])),
    };
  });
};

const emptySnapshot = (): DopeySnapshot => ({
  schemaVersion: null,
  generatedUtc: null,
  headline: null,
  envelope: { paperOnly: null, liveBlocked: null, executionSeal: null },
  hostCapabilities: {
    reported: false,
    permanentNoLiveExecution: null,
    liveExecutionAvailable: null,
    detail: null,
  },
  liveBranch: {
    mode: "LIVE",
    status: null,
    cycleStatus: null,
    generatedUtc: null,
    accountLabel: "agentic",
    accountType: null,
    authenticated: null,
    officialRobinhoodMcp: null,
    liveBranchEnabled: null,
    stockExecutionEnabled: null,
    optionsExecutionCapable: null,
    optionsExecutionEnabled: null,
    paperTwinRequired: null,
    noDayTradingEnforced: null,
    useFullAvailableBalance: null,
    marketOpen: null,
    marketDate: null,
    buyingPowerUsd: null,
    totalEquityUsd: null,
    equityPositionCount: null,
    optionPositionCount: null,
    liveOrderEventCount: null,
    placedOrderCount: null,
    paperTwinEventCount: null,
    recentOrders: [],
    error: null,
  },
  researchCore: {
    enabled: null,
    phase: "UNKNOWN",
    validated: null,
    lastRunUtc: null,
    nextRunUtc: null,
    lockStatus: null,
    pid: null,
    ownershipVerified: null,
    mode: null,
    mutationAvailable: null,
    activeAutomationPresent: null,
    automationSchedules: [],
  },
  readiness: {
    status: null,
    operationalStatus: null,
    highestOperationalLevel: null,
    researchMechanicsReady: null,
    stockShadowReady: null,
    optionShadowReady: null,
    strategyPromotionReady: null,
    liveExecutionStatus: null,
    actionReady: null,
    closedTrades: null,
    closedRequired: null,
    resolvedDecisions: null,
    resolvedRequired: null,
    actionableShadowTheses: null,
    checks: [],
    missingRequirements: [],
  },
  universe: {
    activeCount: null,
    targetCount: null,
    maximumCount: null,
    publicLakeCount: null,
    tierCounts: {},
    symbols: [],
  },
  schedule: { dueLaneIds: [], lanes: [] },
  paperBook: {
    openCount: null,
    closedCount: null,
    wins: null,
    realizedPremiumUnits: null,
    unrealizedPremiumUnits: null,
    openPositions: [],
    closedPositions: [],
  },
  world: { asOf: null, contradictions: [], regimes: [] },
  extremes: {
    marketStatus: null,
    optionStatus: null,
    gainers: [],
    decliners: [],
    optionWinners: [],
    optionLosers: [],
  },
  metacognition: {
    knowledgeBoundary: null,
    primaryControl: null,
    difficulty: null,
    confidence: [],
    expectedInformationGain: null,
    researchUtility: null,
  },
  llmResearch: {
    cycleStatus: null,
    action: null,
    issuedUtc: null,
    providers: [],
    reportedCostUsd: null,
    summary: null,
    experimentCount: null,
    abstain: null,
    evidenceClass: null,
  },
  llmProviderControl: {
    schemaVersion: null,
    instrumentMode: null,
    providers: { openrouter: null, openrouter_hybrid: null, claude: null, codex: null },
    availability: { openrouter: null, openrouter_hybrid: null, claude: null, codex: null },
    activeModelRoster: [],
    routingPolicy: {
      provider: null,
      routeId: null,
      strategy: null,
      stageOrder: [],
      allModelStagesRequired: null,
      fallbackAllowed: null,
      independentExternalRoutesAllowed: null,
    },
    activeRouteAvailable: null,
    credential: {
      configured: null,
      usable: null,
      validationStatus: null,
      source: null,
      updatedUtc: null,
      plaintextExposed: null,
      repositoryStorage: null,
    },
    paperOnly: null,
    liveBlocked: null,
  },
  homeostasis: { healthStatus: null, variables: [], interventions: [] },
  observatory: {
    generatedUtc: null,
    status: null,
    stale: null,
    agents: [],
    shadowGuards: [],
    evolutionCandidates: [],
    hypotheses: [],
    technicalTimeframes: [],
    constitutionInvariants: [],
  },
  evidence: {
    dossier: {
      status: null,
      runId: null,
      headline: null,
      runDirectory: null,
      candidateCount: null,
      eligibleCandidateCount: null,
      diagnosticFrontierCount: null,
      frontierStatus: null,
      frontierCandidateIds: [],
      tradeCount: null,
      grossModelUnitPnl: null,
      netModelUnitPnl: null,
      totalCostModelUnits: null,
      effectiveTrials: null,
      mutationAttempts: null,
      realHistoryUsed: null,
      realOptionChainUsed: null,
      truthDecision: null,
      fitnessDecision: null,
      promotionAllowed: null,
      capitalNormalizationStatus: null,
      capitalCompleteCandidateCount: null,
    },
    mutation: {
      status: null,
      method: null,
      methodReason: null,
      registryRecordCount: null,
      nodeCount: null,
      edgeCount: null,
      prunedBranchCount: null,
      duplicateCandidateCount: null,
      mutationAttemptCount: null,
      paretoFrontierIds: [],
      nodes: [],
      edges: [],
      familyBudgets: [],
      uniqueChampionCount: null,
      championChangeCount: null,
      longestChampionStreak: null,
    },
    oracle: {
      status: null,
      passedTestCount: null,
      failedTestCount: null,
      testCount: null,
      pricingSourceTier: null,
      realOptionChainAbsent: null,
      americanPutEarlyExerciseNodes: null,
      discreteDividendCallEarlyExerciseNodes: null,
      convergenceError400Steps: null,
      promotionAllowed: null,
      sensitivityPointCount: null,
      oddEvenPriceGap: null,
    },
    settlement: {
      status: null,
      outcomeStatus: null,
      decisionCount: null,
      selectedDecisionCount: null,
      newlyResolvedCount: null,
      resolvedCountAfter: null,
      unresolvedCountAfter: null,
      resolutionAsOf: null,
      loadedRowCount: null,
      selectiveHashValidation: null,
      decisionLedgerImmutable: null,
    },
    contracts: {
      status: null,
      issueCount: null,
      artifactCount: null,
      registryHash: null,
      cycleStatus: null,
    },
  },
  analytics: emptyAnalyticsState(),
  playbook: emptyPlaybookState(),
  sources: [],
  issues: [],
});

export const disconnectedModel = (connectionDetail: string): ControlModel => ({
  connection: "CONNECTING",
  connectionDetail,
  snapshot: emptySnapshot(),
});

export const failedModel = (
  connection: "UNAVAILABLE" | "INVALID" | "ERROR",
  connectionDetail: string,
): ControlModel => ({
  connection,
  connectionDetail,
  snapshot: emptySnapshot(),
});

export const normalizeSnapshot = (raw: unknown): ControlModel => {
  if (!isRecord(raw)) {
    return failedModel("INVALID", "Control bridge returned a non-object state payload.");
  }

  const provisionalEnvelope = recordAt(raw, "envelope");
  const constitution = recordAt(raw, "constitution");
  const constitutionState = recordAt(constitution, "state");
  const provisionalControl = recordAt(raw, "control");
  const researchCore = recordAt(raw, "research_core");
  const control = Object.keys(researchCore).length > 0 ? researchCore : provisionalControl;
  const coreTask = recordAt(control, "core_task");
  const provisionalTask = recordAt(control, "task");
  const task = Object.keys(coreTask).length > 0 ? coreTask : provisionalTask;
  const accelerationLock = recordAt(control, "acceleration_lock");
  const provisionalCycle = recordAt(control, "cycle");
  const cycle = Object.keys(accelerationLock).length > 0 ? accelerationLock : provisionalCycle;
  const readiness = recordAt(raw, "readiness");
  const tradeReadiness = recordAt(raw, "trade_readiness_frontier");
  const tradeReadinessLevels = recordAt(tradeReadiness, "levels");
  const researchMechanicsLevel = recordAt(tradeReadinessLevels, "research_mechanics");
  const stockShadowLevel = recordAt(tradeReadinessLevels, "stock_shadow");
  const optionShadowLevel = recordAt(tradeReadinessLevels, "option_shadow");
  const strategyPromotionLevel = recordAt(tradeReadinessLevels, "strategy_promotion");
  const liveExecutionLevel = recordAt(tradeReadinessLevels, "live_execution");
  const readinessProgress = firstValue(raw, [["readiness_progress"]]);
  const closedProgress = progressRecord(readinessProgress, "forward_closed_trade_sample");
  const resolvedProgress = progressRecord(readinessProgress, "resolved_context_decisions");
  const universe = recordAt(raw, "universe");
  const universeSummary = recordAt(universe, "summary");
  const schedule = recordAt(raw, "schedule");
  const paper = recordAt(raw, "paper_record");
  const worldModel = recordAt(raw, "world_model");
  const provisionalWorld = recordAt(raw, "world");
  const world = Object.keys(worldModel).length > 0 ? worldModel : provisionalWorld;
  const optionExtremes = recordAt(raw, "option_extremes");
  const marketExtremes = recordAt(raw, "market_extremes");
  const meta = recordAt(raw, "metacognition");
  const metaDifficulty = recordAt(meta, "difficulty");
  const llmResearch = recordAt(raw, "llm_research");
  const llmProviderControl = recordAt(raw, "llm_provider_control");
  const llmCredential = recordAt(llmProviderControl, "credential");
  const synthesisCouncil = recordAt(llmResearch, "synthesis_council");
  const synthesisResult = recordArray(firstValue(synthesisCouncil, [["results"]]))[0] ?? {};
  const synthesisAnalysis = recordAt(synthesisResult, "structured_analysis");
  const homeostasis = recordAt(raw, "homeostasis");
  const strategyDossier = recordAt(raw, "strategy_dossier");
  const capitalExposure = recordAt(raw, "capital_exposure");
  const dossierSelectionRisk = recordAt(strategyDossier, "selection_risk");
  const dossierTruthState = recordAt(strategyDossier, "truth_state");
  const mutationGenealogy = recordAt(raw, "mutation_genealogy");
  const historicalMutationBudget = recordAt(mutationGenealogy, "historical_search_budget");
  const championDynamics = recordAt(mutationGenealogy, "champion_dynamics");
  const binomialOracle = recordAt(raw, "binomial_oracle");
  const oracleConvergenceDiagnostics = recordAt(binomialOracle, "convergence_diagnostics");
  const oracleSensitivityGrid = recordArray(firstValue(binomialOracle, [["sensitivity_grid"]]));
  const oracleFixtures = recordAt(binomialOracle, "fixtures");
  const americanPutFixture = recordAt(oracleFixtures, "american_put");
  const dividendCallFixture = recordAt(oracleFixtures, "discrete_dividend_american_call");
  const convergence400 = recordArray(firstValue(binomialOracle, [["convergence"]])).find(
    (item) => asString(item["option_type"]) === "call" && asNumber(item["steps"]) === 400,
  ) ?? {};
  const contextSettlement = recordAt(raw, "context_settlement");
  const settlementHistoryEvidence = recordAt(contextSettlement, "history_evidence");
  const evidenceContractAudit = recordAt(raw, "evidence_contract_audit");
  const evidenceCycle = recordAt(raw, "evidence_cycle");
  const observatory = recordAt(raw, "observatory");
  const observatorySnapshot = recordAt(observatory, "snapshot");
  const observatoryManifest = recordAt(observatory, "manifest");
  const observatoryDatasets = recordAt(raw, "observatory_datasets");
  const provisionalDatasets = recordAt(observatory, "datasets");
  const snapshotDatasets = recordAt(observatorySnapshot, "datasets");
  const datasets = Object.keys(observatoryDatasets).length > 0
    ? observatoryDatasets
    : Object.keys(snapshotDatasets).length > 0
      ? snapshotDatasets
      : provisionalDatasets;
  const hostCapabilities = recordAt(raw, "host_capabilities");
  const liveBranch = recordAt(raw, "live_branch");
  const directPlaybook = recordAt(raw, "playbook_rankings");
  const playbook = Object.keys(directPlaybook).length > 0 ? directPlaybook : recordAt(raw, "playbook");
  const auxiliaryTasks = firstValue(control, [["auxiliary_tasks"], ["controlled_auxiliary_tasks"]]) ??
    firstValue(raw, [["auxiliary_schedules"]]);
  const automationSchedules = normalizeAutomationSchedules(task, auxiliaryTasks);
  const enabled = asBoolean(firstValue(control, [["enabled"], ["active"]])) ??
    asBoolean(firstValue(task, [["enabled"], ["active"]]));
  const readinessStatus = asString(firstValue(readiness, [["readiness_status"], ["status"], ["state"]]));
  const directPaperOnly = asBoolean(firstValue(raw, [["paper_only"]]));
  const directLiveBlocked = asBoolean(firstValue(raw, [["live_blocked"]]));

  const snapshot: DopeySnapshot = {
    schemaVersion: asString(firstValue(raw, [["schema_version"], ["version"]])),
    generatedUtc: asString(firstValue(raw, [["generated_utc"], ["as_of"], ["observed_utc"]])),
    headline: asString(firstValue(raw, [["headline"], ["summary"]])),
    envelope: {
      paperOnly: directPaperOnly ??
        asBoolean(firstValue(provisionalEnvelope, [["paper_only"], ["research_only"]])) ??
        asBoolean(firstValue(constitutionState, [["paper_only"]])),
      liveBlocked: directLiveBlocked ??
        asBoolean(firstValue(provisionalEnvelope, [["live_blocked"], ["execution_blocked"]])) ??
        asBoolean(firstValue(constitutionState, [["live_blocked"]])),
      executionSeal: asString(firstValue(constitution, [["execution_seal_state"]])) ??
        asString(firstValue(provisionalEnvelope, [["execution_seal"], ["seal"], ["execution_status"]])),
    },
    hostCapabilities: {
      reported: Object.keys(hostCapabilities).length > 0,
      permanentNoLiveExecution: normalizePermanentNoLiveExecution(hostCapabilities),
      liveExecutionAvailable: asBoolean(firstValue(hostCapabilities, [
        ["live_execution_capability_present"],
        ["live_execution_available"],
        ["live_order_path_available"],
        ["live_trading_available"],
        ["can_execute_live_orders"],
      ])),
      detail: asString(firstValue(hostCapabilities, [
        ["detail"],
        ["description"],
        ["reason"],
        ["control_authority"],
      ])),
    },
    liveBranch: {
      mode: asString(firstValue(liveBranch, [["mode"]])),
      status: asString(firstValue(liveBranch, [["status"]])),
      cycleStatus: asString(firstValue(liveBranch, [["cycle_status"]])),
      generatedUtc: asString(firstValue(liveBranch, [["generated_utc"]])),
      accountLabel: asString(firstValue(liveBranch, [["account_label"]])),
      accountType: asString(firstValue(liveBranch, [["account_type"]])),
      authenticated: asBoolean(firstValue(liveBranch, [["authenticated"]])),
      officialRobinhoodMcp: asBoolean(firstValue(liveBranch, [["official_robinhood_mcp"]])),
      liveBranchEnabled: asBoolean(firstValue(liveBranch, [["live_branch_enabled"]])),
      stockExecutionEnabled: asBoolean(firstValue(liveBranch, [["stock_execution_enabled"]])),
      optionsExecutionCapable: asBoolean(firstValue(liveBranch, [["options_execution_capable"]])),
      optionsExecutionEnabled: asBoolean(firstValue(liveBranch, [["options_execution_enabled"]])),
      paperTwinRequired: asBoolean(firstValue(liveBranch, [["paper_twin_required"]])),
      noDayTradingEnforced: asBoolean(firstValue(liveBranch, [["no_day_trading_enforced"]])),
      useFullAvailableBalance: asBoolean(firstValue(liveBranch, [["use_full_available_balance"]])),
      marketOpen: asBoolean(firstValue(liveBranch, [["market_open"]])),
      marketDate: asString(firstValue(liveBranch, [["market_date"]])),
      buyingPowerUsd: asNumber(firstValue(liveBranch, [["buying_power_usd"]])),
      totalEquityUsd: asNumber(firstValue(liveBranch, [["total_equity_usd"]])),
      equityPositionCount: asNumber(firstValue(liveBranch, [["equity_position_count"]])),
      optionPositionCount: asNumber(firstValue(liveBranch, [["option_position_count"]])),
      liveOrderEventCount: asNumber(firstValue(liveBranch, [["live_order_event_count"]])),
      placedOrderCount: asNumber(firstValue(liveBranch, [["placed_order_count"]])),
      paperTwinEventCount: asNumber(firstValue(liveBranch, [["paper_twin_event_count"]])),
      recentOrders: recordArray(firstValue(liveBranch, [["recent_orders"]])),
      error: asString(firstValue(liveBranch, [["error"]])),
    },
    researchCore: {
      enabled,
      phase: normalizeCorePhase(firstValue(control, [["state"], ["status"], ["phase"]]), enabled),
      validated: asBoolean(firstValue(control, [["all_tasks_verified"], ["validated"], ["configuration_valid"]])) ??
        automationSchedulesValidated(automationSchedules),
      lastRunUtc: asString(firstValue(task, [["last_run_utc"], ["last_success_utc"]])),
      nextRunUtc: asString(firstValue(task, [["next_run_utc"], ["next_due_utc"]])),
      lockStatus: asString(firstValue(cycle, [["lock_status"], ["status"]])) ??
        (asBoolean(firstValue(cycle, [["present"]])) === true ? "present" : "absent"),
      pid: asNumber(firstValue(cycle, [["pid"], ["process_id"]])),
      ownershipVerified: asBoolean(firstValue(cycle, [["verified"], ["ownership_verified"], ["owner_verified"]])),
      mode: asString(firstValue(control, [["control_scope"], ["mode"], ["scope"]])),
      mutationAvailable: asBoolean(firstValue(control, [["mutation_available"], ["can_mutate"]])),
      activeAutomationPresent: asBoolean(firstValue(control, [["active_automation_present"], ["active_cycle_verified"]])),
      automationSchedules,
    },
    readiness: {
      status: readinessStatus,
      operationalStatus: asString(firstValue(tradeReadiness, [["frontier_status"]])),
      highestOperationalLevel: asString(firstValue(tradeReadiness, [["highest_operational_level"]])),
      researchMechanicsReady: asBoolean(firstValue(researchMechanicsLevel, [["ready"]])),
      stockShadowReady: asBoolean(firstValue(stockShadowLevel, [["ready"]])),
      optionShadowReady: asBoolean(firstValue(optionShadowLevel, [["ready"]])),
      strategyPromotionReady: asBoolean(firstValue(strategyPromotionLevel, [["ready"]])),
      liveExecutionStatus: asString(firstValue(liveExecutionLevel, [["status"]])),
      actionReady: asBoolean(firstValue(readiness, [["action_ready"], ["ready"]])) ??
        (readinessStatus === null ? null : readinessStatus === "action_ready"),
      closedTrades: asNumber(firstValue(readiness, [["closed_trades"], ["closed_count"]])) ?? asNumber(closedProgress["current"]),
      closedRequired: asNumber(firstValue(readiness, [["closed_required"], ["required_closed_trades"]])) ?? asNumber(closedProgress["required"]),
      resolvedDecisions: asNumber(firstValue(readiness, [["resolved_decisions"], ["settled_decisions"]])) ?? asNumber(resolvedProgress["current"]),
      resolvedRequired: asNumber(firstValue(readiness, [["resolved_required"], ["required_resolved_decisions"]])) ?? asNumber(resolvedProgress["required"]),
      actionableShadowTheses: asNumber(firstValue(readiness, [["actionable_shadow_thesis_count"], ["actionable_shadow_theses"], ["shadow_theses"]])),
      checks: (() => {
        const reported = normalizeChecks(firstValue(readiness, [["checks"], ["gates"]]));
        return reported.length > 0
          ? reported
          : normalizeChecks(firstValue(tradeReadiness, [["gates"]]));
      })(),
      missingRequirements: (() => {
        const direct = stringArray(firstValue(readiness, [["missing_requirements"], ["blockers"]]));
        if (direct.length > 0) {
          return direct;
        }
        const progress = progressRequirements(readinessProgress);
        if (progress.length > 0) {
          return progress;
        }
        return recordArray(firstValue(tradeReadiness, [["blocked_gates"]]))
          .map((item) => asString(firstValue(item, [["gate_id"]])))
          .filter((item): item is string => item !== null);
      })(),
    },
    universe: {
      activeCount: asNumber(firstValue(universe, [["active_symbol_count"], ["active_count"], ["observed_count"], ["symbol_count"]])),
      targetCount: asNumber(firstValue(universe, [["starting_active_universe_target"], ["target_count"], ["target"]])) ??
        asNumber(firstValue(universeSummary, [["starting_active_universe_target"]])),
      maximumCount: asNumber(firstValue(universe, [["maximum_count"], ["maximum"]])) ??
        asNumber(firstValue(universeSummary, [["maximum_active_universe_size"], ["maximum_count"]])),
      publicLakeCount: asNumber(firstValue(universe, [["public_lake_count"], ["lake_count"]])) ??
        asNumber(firstValue(universeSummary, [["public_lake_symbol_count"], ["public_lake_count"]])),
      tierCounts: normalizeTierCounts(firstValue(universe, [["tier_counts"], ["tiers"]]) ?? firstValue(universeSummary, [["tier_counts"], ["tiers"]])),
      symbols: normalizeSymbols(firstValue(universe, [["symbols"], ["members"]])),
    },
    schedule: {
      dueLaneIds: stringArray(firstValue(schedule, [["due_lane_ids"], ["due_lanes"]])),
      lanes: normalizeSchedule(firstValue(raw, [["schedule_lanes"]]) ?? firstValue(schedule, [["lanes"], ["schedule_lanes"]])),
    },
    paperBook: {
      openCount: asNumber(firstValue(paper, [["open_position_count"], ["open_count"], ["positions_open"]])),
      closedCount: asNumber(firstValue(paper, [["closed_trade_count"], ["closed_count"], ["positions_closed"]])),
      wins: asNumber(firstValue(paper, [["closed_win_count"], ["wins"], ["win_count"]])),
      realizedPremiumUnits: asNumber(firstValue(paper, [["closed_net_pnl_premium_units"], ["realized_premium_units"], ["realized_pnl"]])),
      unrealizedPremiumUnits: asNumber(firstValue(paper, [["unrealized_premium_units"], ["unrealized_pnl"]])),
      openPositions: normalizePositions(firstValue(paper, [["open_positions"], ["positions"]])),
      closedPositions: normalizePositions(firstValue(paper, [["closed_positions"], ["history"]])),
    },
    world: {
      asOf: asString(firstValue(world, [["as_of"], ["generated_utc"]])),
      contradictions: stringArray(firstValue(world, [["contradictions"], ["conflicts"]])),
      regimes: normalizeRegimes(firstValue(world, [["regimes"], ["dimensions"]])),
    },
    extremes: {
      marketStatus: asString(firstValue(marketExtremes, [["status"]])),
      optionStatus: asString(firstValue(optionExtremes, [["status"]])),
      gainers: normalizeStockExtremes(firstValue(marketExtremes, [["top_gainers"]]), "up"),
      decliners: normalizeStockExtremes(firstValue(marketExtremes, [["top_decliners"]]), "down"),
      optionWinners: normalizeOptionExtremes(firstValue(optionExtremes, [["top_winners"]]), "winner"),
      optionLosers: normalizeOptionExtremes(firstValue(optionExtremes, [["top_losers"]]), "loser"),
    },
    metacognition: {
      knowledgeBoundary: asString(firstValue(meta, [["knowledge_boundary"], ["boundary"]])),
      primaryControl: asString(firstValue(meta, [["primary_control"], ["control"]])),
      difficulty: asNumber(firstValue(meta, [["difficulty_score"]])) ?? asNumber(firstValue(metaDifficulty, [["score"], ["value"]])),
      confidence: normalizeConfidence(firstValue(meta, [["confidence"], ["confidence_decomposition"]])),
      expectedInformationGain: asNumber(firstValue(meta, [["expected_information_gain"], ["information_gain"]])),
      researchUtility: asNumber(firstValue(meta, [["research_utility"], ["utility"]])),
    },
    llmResearch: {
      cycleStatus: asString(firstValue(llmResearch, [["cycle_status"]])),
      action: asString(firstValue(llmResearch, [["analysis_action"]])),
      issuedUtc: asString(firstValue(llmResearch, [["issued_at"]])),
      providers: stringArray(firstValue(llmResearch, [["provider_models"]])),
      reportedCostUsd: asNumber(firstValue(llmResearch, [["reported_openrouter_cost_usd"]])),
      summary: asString(firstValue(synthesisAnalysis, [["summary"]])),
      experimentCount: Array.isArray(synthesisAnalysis["recommended_experiments"])
        ? synthesisAnalysis["recommended_experiments"].length
        : null,
      abstain: asBoolean(firstValue(synthesisAnalysis, [["abstain"]])),
      evidenceClass: asString(firstValue(llmResearch, [["llm_output_evidence_class"]])),
    },
    llmProviderControl: {
      schemaVersion: asString(firstValue(llmProviderControl, [["schema_version"]])),
      instrumentMode: normalizeInstrumentMode(firstValue(llmProviderControl, [["instrument_mode"]])),
      providers: providerFlags(firstValue(llmProviderControl, [["providers"]])),
      availability: providerFlags(firstValue(llmProviderControl, [["availability"]])),
      activeModelRoster: modelRoster(firstValue(llmProviderControl, [["active_model_roster"]])),
      routingPolicy: routingPolicy(firstValue(llmProviderControl, [["routing_policy"]])),
      activeRouteAvailable: asBoolean(firstValue(llmProviderControl, [["active_route_available"]])),
      credential: {
        configured: asBoolean(firstValue(llmCredential, [["configured"]])),
        usable: asBoolean(firstValue(llmCredential, [["usable"]])),
        validationStatus: asString(firstValue(llmCredential, [["validation_status"]])),
        source: asString(firstValue(llmCredential, [["source"]])),
        updatedUtc: asString(firstValue(llmCredential, [["updated_utc"]])),
        plaintextExposed: asBoolean(firstValue(llmCredential, [["plaintext_exposed"]])),
        repositoryStorage: asBoolean(firstValue(llmCredential, [["repository_storage"]])),
      },
      paperOnly: asBoolean(firstValue(llmProviderControl, [["paper_only"]])),
      liveBlocked: asBoolean(firstValue(llmProviderControl, [["live_blocked"]])),
    },
    homeostasis: {
      healthStatus: asString(firstValue(homeostasis, [["health_status"], ["status"]])),
      variables: normalizeHealth(firstValue(homeostasis, [["variables"], ["metrics"]])),
      interventions: stringArray(firstValue(homeostasis, [["interventions"], ["actions"]])),
    },
    observatory: {
      generatedUtc: asString(firstValue(observatory, [["snapshot_generated_utc"], ["snapshot_generated_at"]])) ??
        asString(firstValue(observatorySnapshot, [["generated_utc"], ["generatedAt"], ["as_of"], ["observed_at"]])) ??
        asString(firstValue(observatoryManifest, [["generated_utc"], ["generatedAt"]])),
      status: asString(firstValue(observatory, [["snapshot_status"]])) ??
        asString(firstValue(observatorySnapshot, [["status"], ["state"]])) ??
        asString(firstValue(observatory, [["status"], ["state"]])),
      stale: asBoolean(firstValue(observatory, [["snapshot_stale"], ["stale"], ["is_stale"]])) ??
        asBoolean(firstValue(observatorySnapshot, [["stale"], ["is_stale"]])),
      agents: normalizeDataset(firstValue(datasets, [["agents"], ["active_agents"]])),
      shadowGuards: normalizeDataset(firstValue(datasets, [["shadow_guards"], ["shadows"]])),
      evolutionCandidates: normalizeDataset(firstValue(datasets, [["evolution_candidates"], ["candidates"]])),
      hypotheses: normalizeDataset(firstValue(datasets, [["hypotheses"], ["active_hypotheses"]])),
      technicalTimeframes: normalizeDataset(firstValue(datasets, [["technical_timeframes"], ["timeframes"]])),
      constitutionInvariants: normalizeDataset(firstValue(datasets, [["constitution_invariants"], ["invariants"]])),
    },
    evidence: {
      dossier: {
        status: asString(firstValue(strategyDossier, [["dossier_status"]])),
        runId: asString(firstValue(strategyDossier, [["run_id"]])),
        headline: asString(firstValue(strategyDossier, [["headline"]])),
        runDirectory: asString(firstValue(strategyDossier, [["run_directory"]])),
        candidateCount: asNumber(firstValue(strategyDossier, [["candidate_count"]])),
        eligibleCandidateCount: asNumber(firstValue(strategyDossier, [["eligible_candidate_count"]])),
        diagnosticFrontierCount: asNumber(firstValue(strategyDossier, [["diagnostic_frontier_count"]])),
        frontierStatus: asString(firstValue(strategyDossier, [["frontier_status"]])),
        frontierCandidateIds: stringArray(firstValue(strategyDossier, [["frontier_candidate_ids"]])),
        tradeCount: asNumber(firstValue(strategyDossier, [["trade_count"]])),
        grossModelUnitPnl: asNumber(firstValue(strategyDossier, [["gross_model_unit_pnl"]])),
        netModelUnitPnl: asNumber(firstValue(strategyDossier, [["net_model_unit_pnl"]])),
        totalCostModelUnits: asNumber(firstValue(strategyDossier, [["total_cost_model_units"]])),
        effectiveTrials: asNumber(firstValue(dossierSelectionRisk, [["effective_trials"]])),
        mutationAttempts: asNumber(firstValue(dossierSelectionRisk, [["mutation_attempts_recorded"]])),
        realHistoryUsed: asBoolean(firstValue(dossierTruthState, [["real_history_used"]])),
        realOptionChainUsed: asBoolean(firstValue(dossierTruthState, [["real_option_chain_used"]])),
        truthDecision: asString(firstValue(dossierTruthState, [["truth_decision"]])),
        fitnessDecision: asString(firstValue(dossierTruthState, [["fitness_decision"]])),
        promotionAllowed: asBoolean(firstValue(strategyDossier, [["promotion_allowed"]])),
        capitalNormalizationStatus: asString(firstValue(capitalExposure, [["normalization_status"]])),
        capitalCompleteCandidateCount: asNumber(firstValue(capitalExposure, [["complete_candidate_count"]])),
      },
      mutation: {
        status: asString(firstValue(mutationGenealogy, [["explorer_status"]])),
        method: asString(firstValue(mutationGenealogy, [["search_method"]])),
        methodReason: asString(firstValue(mutationGenealogy, [["search_method_reason"]])),
        registryRecordCount: asNumber(firstValue(mutationGenealogy, [["registry_record_count"]])),
        nodeCount: asNumber(firstValue(mutationGenealogy, [["node_count"]])),
        edgeCount: asNumber(firstValue(mutationGenealogy, [["edge_count"]])),
        prunedBranchCount: asNumber(firstValue(mutationGenealogy, [["pruned_branch_count"]])),
        duplicateCandidateCount: asNumber(firstValue(mutationGenealogy, [["duplicate_candidate_count"]])),
        mutationAttemptCount: asNumber(firstValue(historicalMutationBudget, [["mutation_attempt_count"]])),
        paretoFrontierIds: stringArray(firstValue(mutationGenealogy, [["mutation_pareto_frontier_ids"]])),
        nodes: normalizeMutationNodes(firstValue(mutationGenealogy, [["nodes"]])),
        edges: normalizeMutationEdges(firstValue(mutationGenealogy, [["edges"]])),
        familyBudgets: normalizeMutationFamilyBudgets(firstValue(mutationGenealogy, [["family_budgets"]])),
        uniqueChampionCount: asNumber(firstValue(championDynamics, [["unique_champion_count"]])),
        championChangeCount: asNumber(firstValue(championDynamics, [["champion_change_count"]])),
        longestChampionStreak: asNumber(firstValue(championDynamics, [["longest_champion_streak"]])),
      },
      oracle: {
        status: asString(firstValue(binomialOracle, [["validation_status"]])),
        passedTestCount: asNumber(firstValue(binomialOracle, [["passed_test_count"]])),
        failedTestCount: asNumber(firstValue(binomialOracle, [["failed_test_count"]])),
        testCount: asNumber(firstValue(binomialOracle, [["test_count"]])),
        pricingSourceTier: asString(firstValue(binomialOracle, [["pricing_source_tier"]])),
        realOptionChainAbsent: asBoolean(firstValue(binomialOracle, [["real_option_chain_absent"]])),
        americanPutEarlyExerciseNodes: asNumber(firstValue(americanPutFixture, [["early_exercise_node_count"]])),
        discreteDividendCallEarlyExerciseNodes: asNumber(firstValue(dividendCallFixture, [["early_exercise_node_count"]])),
        convergenceError400Steps: asNumber(firstValue(convergence400, [["absolute_error"]])),
        promotionAllowed: asBoolean(firstValue(binomialOracle, [["promotion_allowed"]])),
        sensitivityPointCount: Object.keys(binomialOracle).length > 0 ? oracleSensitivityGrid.length : null,
        oddEvenPriceGap: asNumber(firstValue(oracleConvergenceDiagnostics, [["odd_even_price_gap"]])),
      },
      settlement: {
        status: asString(firstValue(contextSettlement, [["operation_status"]])),
        outcomeStatus: asString(firstValue(contextSettlement, [["outcome_status"]])),
        decisionCount: asNumber(firstValue(contextSettlement, [["decision_count"]])),
        selectedDecisionCount: asNumber(firstValue(contextSettlement, [["selected_decision_count"]])),
        newlyResolvedCount: asNumber(firstValue(contextSettlement, [["newly_resolved_count"]])),
        resolvedCountAfter: asNumber(firstValue(contextSettlement, [["resolved_count_after"]])),
        unresolvedCountAfter: asNumber(firstValue(contextSettlement, [["unresolved_count_after"]])),
        resolutionAsOf: asString(firstValue(contextSettlement, [["resolution_as_of"]])),
        loadedRowCount: asNumber(firstValue(settlementHistoryEvidence, [["loaded_row_count"]])),
        selectiveHashValidation: asBoolean(firstValue(settlementHistoryEvidence, [["selective_hash_validation"]])),
        decisionLedgerImmutable: asBoolean(firstValue(contextSettlement, [["decision_ledger_immutable"]])),
      },
      contracts: {
        status: asString(firstValue(evidenceContractAudit, [["audit_status"]])),
        issueCount: asNumber(firstValue(evidenceContractAudit, [["cross_artifact_issue_count"]])),
        artifactCount: asNumber(firstValue(evidenceContractAudit, [["artifact_count"]])),
        registryHash: asString(firstValue(evidenceContractAudit, [["contract_registry_hash"]])),
        cycleStatus: asString(firstValue(evidenceCycle, [["cycle_status"]])),
      },
    },
    analytics: normalizeAnalytics(firstValue(raw, [["analytics"]])),
    playbook: normalizePlaybook(playbook),
    sources: normalizeSources(firstValue(raw, [["source_health"], ["sources"], ["data_sources"]])),
    issues: normalizeIssues(firstValue(raw, [["issues"], ["alerts"]])),
  };

  return {
    connection: "CONNECTED",
    connectionDetail: "Local control bridge linked.",
    snapshot,
  };
};

export const formatTimestamp = (value: string | null): string => {
  if (value === null) {
    return "NOT REPORTED";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value.toUpperCase();
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).format(parsed);
};

export const formatExactTimestamp = (value: string | null): string =>
  value === null ? "NOT REPORTED" : value;

export const executionSealPresentation = (
  executionSeal: string | null,
): { readonly state: "sealed" | "fault" | "unverified"; readonly label: string } => {
  if (executionSeal === "SEALED") {
    return { state: "sealed", label: "EXECUTION SEALED" };
  }
  if (executionSeal === null) {
    return { state: "unverified", label: "SEAL UNVERIFIED" };
  }
  return { state: "fault", label: "SEAL FAULT" };
};

export const desktopHostCapabilityLabel = (hostCapabilities: HostCapabilities): string => {
  if (!hostCapabilities.reported) {
    return "DESKTOP HOST CAPABILITY UNREPORTED";
  }
  if (hostCapabilities.permanentNoLiveExecution === true) {
    return "DESKTOP HOST: PERMANENTLY NO LIVE EXECUTION CAPABILITY";
  }
  if (hostCapabilities.liveExecutionAvailable === false) {
    return "DESKTOP HOST: LIVE EXECUTION CAPABILITY ABSENT";
  }
  if (hostCapabilities.liveExecutionAvailable === true) {
    return "DESKTOP HOST: LIVE EXECUTION CAPABILITY REPORTED";
  }
  return "DESKTOP HOST: LIVE EXECUTION CAPABILITY UNVERIFIED";
};

export const formatRatio = (value: number | null, target: number | null): string =>
  `${value === null ? "—" : Math.round(value)} / ${target === null ? "—" : Math.round(target)}`;

export const formatScalar = (value: number | null, digits: number): string =>
  value === null ? "UNKNOWN" : value.toFixed(digits);

export const normalizedPercent = (value: number | null): number | null => {
  if (value === null) {
    return null;
  }
  const fraction = value > 1 ? value / 100 : value;
  return Math.max(0, Math.min(1, fraction));
};

export const displayLabel = (value: string | null): string =>
  value === null ? "UNKNOWN" : value.replaceAll("_", " ").toUpperCase();
