import { EmptyState, InstrumentPanel } from "../components/Instruments";
import { MachineLearningTruth, ReadinessAccrualCockpit } from "../components/AnalyticsVisuals";
import { PageHeader } from "../components/PageHeader";
import { statusTone } from "../lib/tone";
import { displayLabel, formatTimestamp, normalizedPercent } from "../state";
import type { DopeySnapshot, ReadinessCheck } from "../types";

const CheckTable = ({ checks }: { readonly checks: readonly ReadinessCheck[] }) => {
  if (checks.length === 0) {
    return <EmptyState detail="Readiness did not provide individual gate results." label="GATES / NOT REPORTED" />;
  }
  return (
    <div className="check-table">
      {checks.map((check, index) => (
        <div className="check-row" key={check.id}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{check.label}</strong>
          <em className={`status-cell status-cell--${statusTone(check.status)}`}>{displayLabel(check.status)}</em>
          <p>{check.detail ?? "No detail reported."}</p>
        </div>
      ))}
    </div>
  );
};

export const TruthView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const closedRatio = snapshot.readiness.closedRequired === null || snapshot.readiness.closedTrades === null
    ? null
    : snapshot.readiness.closedTrades / Math.max(snapshot.readiness.closedRequired, 1);
  const resolvedRatio = snapshot.readiness.resolvedRequired === null || snapshot.readiness.resolvedDecisions === null
    ? null
    : snapshot.readiness.resolvedDecisions / Math.max(snapshot.readiness.resolvedRequired, 1);
  const readinessTiers = [
    ["RESEARCH MECHANICS", snapshot.readiness.researchMechanicsReady],
    ["STOCK SHADOW", snapshot.readiness.stockShadowReady],
    ["OPTION SHADOW", snapshot.readiness.optionShadowReady],
    ["STRATEGY PROMOTION", snapshot.readiness.strategyPromotionReady],
  ] as const;
  return (
    <div className="secondary-view">
      <PageHeader index="06" thesis="Forward evidence is accrued, settled, and blocked here. Agreement alone never becomes readiness." timestamp={snapshot.generatedUtc} timestampText={formatTimestamp(snapshot.generatedUtc)} title="Truth & settlement" />
      <div className="truth-view-grid">
        <InstrumentPanel className="truth-view-grid__frontier" code="T-40" meta={displayLabel(snapshot.readiness.highestOperationalLevel)} title="Operational readiness frontier">
          <div className="readiness-frontier-grid">
            {readinessTiers.map(([label, ready], index) => (
              <div className={`readiness-frontier-tier readiness-frontier-tier--${ready === true ? "ready" : ready === false ? "blocked" : "unknown"}`} key={label}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{label}</strong>
                <em>{ready === true ? "READY" : ready === false ? "BLOCKED" : "UNKNOWN"}</em>
              </div>
            ))}
            <div className="readiness-frontier-tier readiness-frontier-tier--sealed">
              <span>05</span>
              <strong>LIVE EXECUTION</strong>
              <em>{displayLabel(snapshot.readiness.liveExecutionStatus)}</em>
            </div>
          </div>
          <p className="readiness-frontier-caption">{displayLabel(snapshot.readiness.operationalStatus)} · each tier inherits every gate to its left</p>
        </InstrumentPanel>
        <InstrumentPanel className="truth-view-grid__meter" code="T-41" meta={displayLabel(snapshot.readiness.status)} title="Evidence thresholds">
          <div className="threshold-dials">
            <ThresholdDial label="CLOSED PAPER OUTCOMES" ratio={closedRatio} value={snapshot.readiness.closedTrades} target={snapshot.readiness.closedRequired} />
            <ThresholdDial label="RESOLVED DECISIONS" ratio={resolvedRatio} value={snapshot.readiness.resolvedDecisions} target={snapshot.readiness.resolvedRequired} />
            <ThresholdDial label="ACTIONABLE SHADOW THESES" ratio={null} value={snapshot.readiness.actionableShadowTheses} target={null} />
          </div>
        </InstrumentPanel>
        <InstrumentPanel className="truth-view-grid__checks" code="T-42" meta={`${snapshot.readiness.checks.length} GATES`} title="Gate register">
          <CheckTable checks={snapshot.readiness.checks} />
        </InstrumentPanel>
        <InstrumentPanel className="" code="T-43" meta={`${snapshot.readiness.missingRequirements.length} OPEN`} title="Missing requirements">
          {snapshot.readiness.missingRequirements.length === 0 ? (
            <EmptyState detail="The state source reported no missing-requirement records." label="NO REQUIREMENT RECORDS" />
          ) : (
            <ol className="numbered-ledger">
              {snapshot.readiness.missingRequirements.map((requirement, index) => (
                <li key={`${requirement}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><p>{requirement}</p></li>
              ))}
            </ol>
          )}
        </InstrumentPanel>
        <InstrumentPanel className="" code="T-44" meta={`${snapshot.issues.length} OPEN`} title="Integrity issues">
          {snapshot.issues.length === 0 ? (
            <EmptyState detail="No current issue records were emitted." label="ISSUES / NONE REPORTED" />
          ) : (
            <div className="issue-ledger">
              {snapshot.issues.map((issue) => (
                <div className={`issue-row issue-row--${issue.severity}`} key={issue.id}>
                  <span>{issue.severity.toUpperCase()}</span><strong>{issue.message}</strong><p>{issue.detail ?? "No detail reported."}</p>
                </div>
              ))}
            </div>
          )}
        </InstrumentPanel>
      </div>
      <ReadinessAccrualCockpit analytics={snapshot.analytics} />
      <MachineLearningTruth analytics={snapshot.analytics} />
    </div>
  );
};

const ThresholdDial = ({ label, ratio, value, target }: { readonly label: string; readonly ratio: number | null; readonly value: number | null; readonly target: number | null }) => {
  const percent = normalizedPercent(ratio);
  return (
    <div className="threshold-dial">
      <div className="threshold-dial__scale" aria-hidden="true">
        {Array.from({ length: 20 }, (_, index) => <i className={percent !== null && index < Math.round(percent * 20) ? "is-filled" : ""} key={index} />)}
      </div>
      <strong>{value ?? "—"}<small>{target === null ? "" : ` / ${target}`}</small></strong>
      <span>{label}</span>
    </div>
  );
};
