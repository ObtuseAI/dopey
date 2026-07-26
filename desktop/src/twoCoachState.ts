import type {
  CoachAdversarialFinding,
  CoachAnalysis,
  CoachExperiment,
  CoachHypothesis,
  HeadCoachId,
  TwoCoachReview,
} from "./types";

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const record = (value: unknown, label: string): UnknownRecord => {
  if (!isRecord(value)) {
    throw new TypeError(`${label} is not an object.`);
  }
  return value;
};

const string = (value: unknown, label: string): string => {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new TypeError(`${label} is not a non-empty string.`);
  }
  return value.trim();
};

const number = (value: unknown, label: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`${label} is not finite.`);
  }
  return value;
};

const boolean = (value: unknown, label: string): boolean => {
  if (typeof value !== "boolean") {
    throw new TypeError(`${label} is not boolean.`);
  }
  return value;
};

const stringArray = (value: unknown, label: string): readonly string[] => {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new TypeError(`${label} is not a string array.`);
  }
  return value;
};

const objectArray = (value: unknown, label: string): readonly UnknownRecord[] => {
  if (!Array.isArray(value) || !value.every(isRecord)) {
    throw new TypeError(`${label} is not an object array.`);
  }
  return value;
};

const headCoachId = (value: unknown): HeadCoachId => {
  if (value === "claude" || value === "codex") {
    return value;
  }
  throw new TypeError(`Head coach identity is invalid: ${String(value)}`);
};

const hypothesis = (value: UnknownRecord, index: number): CoachHypothesis => ({
  title: string(value.title, `hypotheses[${index}].title`),
  mechanism: string(value.mechanism, `hypotheses[${index}].mechanism`),
  evidenceNeeded: string(value.evidence_needed, `hypotheses[${index}].evidence_needed`),
  falsification: string(value.falsification, `hypotheses[${index}].falsification`),
});

const adversarialFinding = (value: UnknownRecord, index: number): CoachAdversarialFinding => ({
  title: string(value.title, `adversarial_findings[${index}].title`),
  risk: string(value.risk, `adversarial_findings[${index}].risk`),
  evidenceNeeded: string(value.evidence_needed, `adversarial_findings[${index}].evidence_needed`),
});

const experiment = (value: UnknownRecord, index: number): CoachExperiment => ({
  title: string(value.title, `recommended_experiments[${index}].title`),
  objective: string(value.objective, `recommended_experiments[${index}].objective`),
  expectedInformationGain: string(value.expected_information_gain, `recommended_experiments[${index}].expected_information_gain`),
  falsification: string(value.falsification, `recommended_experiments[${index}].falsification`),
  safetyConstraints: string(value.safety_constraints, `recommended_experiments[${index}].safety_constraints`),
});

const analysis = (value: unknown): CoachAnalysis => {
  const raw = record(value, "rendered_analysis");
  return {
    summary: string(raw.summary, "rendered_analysis.summary"),
    hypotheses: objectArray(raw.hypotheses, "rendered_analysis.hypotheses").map(hypothesis),
    adversarialFindings: objectArray(raw.adversarial_findings, "rendered_analysis.adversarial_findings").map(adversarialFinding),
    uncertainties: stringArray(raw.uncertainties, "rendered_analysis.uncertainties"),
    recommendedExperiments: objectArray(raw.recommended_experiments, "rendered_analysis.recommended_experiments").map(experiment),
    abstain: boolean(raw.abstain, "rendered_analysis.abstain"),
  };
};

export const normalizeTwoCoachReview = (value: unknown): TwoCoachReview => {
  const root = record(value, "two-coach review");
  const topology = record(root.topology, "topology");
  const evidenceCoach = record(root.evidence_coach, "evidence_coach");
  const headCoach = record(root.head_coach, "head_coach");
  const grounding = record(headCoach.grounding, "head_coach.grounding");
  const usage = record(headCoach.usage, "head_coach.usage");
  const authority = record(root.authority, "authority");
  const optionBoundary = record(root.option_claim_boundary, "option_claim_boundary");
  const cost = usage.cost;
  return {
    schemaVersion: string(root.schema_version, "schema_version"),
    sessionId: string(root.session_id, "session_id"),
    status: string(root.status, "status"),
    verdict: string(root.verdict, "verdict"),
    sessionHash: string(root.session_hash, "session_hash"),
    headCoachId: headCoachId(headCoach.head_coach_id ?? topology.head_coach_id),
    headCoachModel: string(headCoach.head_coach_model, "head_coach.head_coach_model"),
    routeId: string(headCoach.route_id, "head_coach.route_id"),
    supportingModels: stringArray(headCoach.supporting_models, "head_coach.supporting_models"),
    evidenceCoachId: string(evidenceCoach.coach_id, "evidence_coach.coach_id"),
    structureCount: number(evidenceCoach.structure_count, "evidence_coach.structure_count"),
    numericFactCount: number(evidenceCoach.numeric_fact_count, "evidence_coach.numeric_fact_count"),
    lessonCount: number(evidenceCoach.lesson_count, "evidence_coach.lesson_count"),
    numericGroundingStatus: string(grounding.numeric_grounding_status, "head_coach.grounding.numeric_grounding_status"),
    referenceCount: number(grounding.reference_count, "head_coach.grounding.reference_count"),
    analysis: analysis(headCoach.rendered_analysis),
    paidResponseCount: number(headCoach.paid_response_count, "head_coach.paid_response_count"),
    reportedCostUsd: typeof cost === "number" && Number.isFinite(cost) ? cost : null,
    optionClaimStatus: string(optionBoundary.status, "option_claim_boundary.status"),
    researchOnly: boolean(authority.research_only, "authority.research_only"),
    paperOnly: boolean(authority.paper_only, "authority.paper_only"),
    liveBlocked: boolean(authority.live_blocked, "authority.live_blocked"),
    brokerAccess: boolean(authority.broker_access, "authority.broker_access"),
    orderAuthority: boolean(authority.order_authority, "authority.order_authority"),
    runtimeFallbackUsed: boolean(headCoach.runtime_fallback_used, "head_coach.runtime_fallback_used"),
  };
};
