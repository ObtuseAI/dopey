import type {
  BlindReplayEvidence,
  ChartBar,
  ChartIndicator,
  ChartPattern,
  ChartPayload,
  ChartTimeframe,
  GroundedChartStructure,
  GroundedNumericFact,
} from "./types";

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const asString = (value: unknown): string | null =>
  typeof value === "string" && value.trim().length > 0 ? value.trim() : null;

const asNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const asBoolean = (value: unknown): boolean | null =>
  typeof value === "boolean" ? value : null;

const asTimeframe = (value: unknown): ChartTimeframe => {
  if (value === "daily" || value === "weekly" || value === "monthly") {
    return value;
  }
  throw new TypeError(`Chart timeframe is invalid: ${String(value)}`);
};

const normalizeBar = (value: unknown, index: number): ChartBar => {
  if (!isRecord(value)) {
    throw new TypeError(`Chart bar ${index} is not an object.`);
  }
  const date = asString(value.date);
  const open = asNumber(value.open);
  const high = asNumber(value.high);
  const low = asNumber(value.low);
  const close = asNumber(value.close);
  const volume = asNumber(value.volume);
  if (date === null || open === null || high === null || low === null || close === null || volume === null) {
    throw new TypeError(`Chart bar ${index} is incomplete.`);
  }
  if (high < Math.max(open, close, low) || low > Math.min(open, close, high) || volume < 0) {
    throw new RangeError(`Chart bar ${index} violates OHLCV bounds.`);
  }
  return { date, open, high, low, close, volume };
};

const normalizePattern = (value: unknown, index: number): ChartPattern => {
  if (!isRecord(value)) {
    throw new TypeError(`Chart pattern ${index} is not an object.`);
  }
  const pattern = asString(value.pattern) ?? "unknown_pattern";
  const family = asString(value.family) ?? "geometric_structure";
  const asOf = asString(value.as_of);
  const oscillator = asString(value.oscillator);
  return {
    id: `${family}:${pattern}:${asOf ?? index}:${oscillator ?? "price"}`,
    pattern,
    family,
    directionalBias: asString(value.directional_bias) ?? "neutral",
    probability: asNumber(value.probability),
    evidenceQuality: asNumber(value.evidence_quality),
    asOf,
    failureCondition: asString(value.failure_condition),
    oscillator,
    divergenceType: asString(value.divergence_type),
  };
};

const normalizeIndicator = (value: unknown, index: number): ChartIndicator => {
  if (!isRecord(value)) {
    throw new TypeError(`Chart indicator ${index} is not an object.`);
  }
  const indicator = asString(value.indicator);
  if (indicator === null) {
    throw new TypeError(`Chart indicator ${index} has no identity.`);
  }
  return {
    indicator,
    value: asNumber(value.value),
    percentile: asNumber(value.percentile),
    slope: asNumber(value.slope),
    state: asString(value.state) ?? "unknown",
    reliability: asNumber(value.reliability),
  };
};

const normalizeSeries = (value: unknown, expectedLength: number, label: string): readonly (number | null)[] => {
  if (!Array.isArray(value) || value.length !== expectedLength) {
    throw new TypeError(`${label} must contain exactly ${expectedLength} observations.`);
  }
  return value.map((item, index) => {
    if (item === null) {
      return null;
    }
    const number = asNumber(item);
    if (number === null) {
      throw new TypeError(`${label}[${index}] is not finite or null.`);
    }
    return number;
  });
};

const normalizeSeriesRecord = (value: unknown, expectedLength: number, label: string): Readonly<Record<string, readonly (number | null)[]>> => {
  if (!isRecord(value)) {
    throw new TypeError(`${label} is not an object.`);
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, series]) => [key, normalizeSeries(series, expectedLength, `${label}.${key}`)]),
  );
};

const normalizePatternArray = (value: unknown, label: string): readonly ChartPattern[] => {
  if (!Array.isArray(value)) {
    throw new TypeError(`${label} is not an array.`);
  }
  return value.map(normalizePattern);
};

const normalizeGroundedStructure = (value: unknown, index: number): GroundedChartStructure => {
  if (!isRecord(value)) {
    throw new TypeError(`Grounded chart structure ${index} is not an object.`);
  }
  const structureId = asString(value.structure_id);
  const definitionId = asString(value.definition_id);
  const structureType = asString(value.structure_type);
  const availableAt = asString(value.available_at_date);
  if (structureId === null || definitionId === null || structureType === null || availableAt === null) {
    throw new TypeError(`Grounded chart structure ${index} has incomplete identity fields.`);
  }
  if (!Array.isArray(value.level_refs) || !value.level_refs.every((item) => typeof item === "string")) {
    throw new TypeError(`Grounded chart structure ${index} has invalid level references.`);
  }
  return {
    structureId,
    definitionId,
    structureType,
    directionalBias: asString(value.directional_bias) ?? "neutral",
    availableAt,
    levelRefs: value.level_refs,
    candidateNotTruth: asBoolean(value.candidate_not_truth) === true,
  };
};

const normalizeNumericFact = (value: unknown, index: number): GroundedNumericFact => {
  if (!isRecord(value)) {
    throw new TypeError(`Grounded numeric fact ${index} is not an object.`);
  }
  const levelRef = asString(value.level_ref);
  const label = asString(value.label);
  const valueDecimal = asString(value.value_decimal);
  const canonicalDisplay = asString(value.canonical_display);
  const unit = asString(value.unit);
  const derivation = asString(value.derivation);
  if (levelRef === null || label === null || valueDecimal === null || canonicalDisplay === null || unit === null || derivation === null) {
    throw new TypeError(`Grounded numeric fact ${index} is incomplete.`);
  }
  return { levelRef, label, valueDecimal, canonicalDisplay, unit, derivation };
};

const normalizeBlindReplay = (value: unknown): BlindReplayEvidence => {
  if (!isRecord(value)) {
    throw new TypeError("Blind replay evidence is not an object.");
  }
  const outcome = isRecord(value.outcome) ? value.outcome : {};
  const blockedStatus = asString(value.replay_status);
  return {
    status: blockedStatus ?? "completed_underlying_only",
    decisionCutoff: asString(value.decision_cutoff),
    revealEnd: asString(value.reveal_end),
    revealBarCount: asNumber(value.reveal_bar_count) ?? 0,
    replayHash: asString(value.replay_hash),
    optionOutcomeStatus: asString(outcome.option_outcome_status) ?? "blocked_missing_point_in_time_option_evidence",
    lookaheadBlocked: asBoolean(value.future_data_visible_during_frozen_detection) === false,
  };
};

export const normalizeChartPayload = (value: unknown): ChartPayload => {
  if (!isRecord(value)) {
    throw new TypeError("Chart bridge returned a non-object payload.");
  }
  const schemaVersion = asString(value.schema_version);
  const symbol = asString(value.symbol);
  const asOf = asString(value.as_of);
  const contentHash = asString(value.content_hash);
  if (schemaVersion === null || symbol === null || asOf === null || contentHash === null) {
    throw new TypeError("Chart payload identity fields are incomplete.");
  }
  if (!Array.isArray(value.bars)) {
    throw new TypeError("Chart payload bars are not an array.");
  }
  const bars = value.bars.map(normalizeBar);
  if (bars.length < 20) {
    throw new RangeError(`Chart payload has insufficient display bars: ${bars.length}`);
  }
  const geometric = normalizePatternArray(value.geometric_patterns, "geometric_patterns");
  const candlesticks = normalizePatternArray(value.candlestick_patterns, "candlestick_patterns");
  const divergences = normalizePatternArray(value.divergences, "divergences");
  if (!Array.isArray(value.indicator_snapshot)) {
    throw new TypeError("indicator_snapshot is not an array.");
  }
  if (!isRecord(value.grounded_structure_evidence)) {
    throw new TypeError("grounded_structure_evidence is not an object.");
  }
  const grounded = value.grounded_structure_evidence;
  if (!Array.isArray(grounded.structures) || !Array.isArray(grounded.numeric_facts)) {
    throw new TypeError("Grounded structure registries are not arrays.");
  }
  const groundedEvidenceHash = asString(grounded.evidence_hash);
  if (groundedEvidenceHash === null) {
    throw new TypeError("Grounded structure evidence hash is missing.");
  }
  return {
    schemaVersion,
    symbol,
    timeframe: asTimeframe(value.timeframe),
    asOf,
    bars,
    overlays: normalizeSeriesRecord(value.overlays, bars.length, "overlays"),
    oscillators: normalizeSeriesRecord(value.oscillators, bars.length, "oscillators"),
    patterns: [...divergences, ...candlesticks, ...geometric],
    divergences,
    indicators: value.indicator_snapshot.map(normalizeIndicator),
    indicatorCount: asNumber(value.indicator_count) ?? 0,
    patternFamilyCount: asNumber(value.pattern_family_count) ?? 0,
    groundedStructures: grounded.structures.map(normalizeGroundedStructure),
    numericFacts: grounded.numeric_facts.map(normalizeNumericFact),
    groundedEvidenceHash,
    viewportIsDetectorInput: asBoolean(grounded.viewport_is_detector_input) === true,
    blindReplay: normalizeBlindReplay(value.blind_replay_evidence),
    contentHash,
    syntheticDataUsed: asBoolean(value.synthetic_data_used) === true,
    networkFetchPerformed: asBoolean(value.network_fetch_performed) === true,
    paperOnly: asBoolean(value.paper_only) === true,
    liveBlocked: asBoolean(value.live_blocked) === true,
  };
};
