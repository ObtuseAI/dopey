import { EmptyState, InstrumentPanel } from "../components/Instruments";
import { EvidenceWorkbench } from "../components/AnalyticsVisuals";
import { statusTone } from "../lib/tone";
import { displayLabel, formatExactTimestamp, formatScalar } from "../state";
import type { DopeySnapshot } from "../types";

const integer = (value: number | null): string => value === null ? "—" : Math.round(value).toLocaleString("en-US");

const modelUnits = (value: number | null): string => {
  if (value === null) {
    return "—";
  }
  const absolute = Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 1 });
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${absolute}`;
};

const EvidenceHeader = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => (
  <header className="view-header evidence-header">
    <div className="view-header__index">07</div>
    <div>
      <span className="eyebrow">DOPEY / STRATEGY INTERROGATION</span>
      <h1>Evidence dossier</h1>
      <p>{snapshot.evidence.dossier.headline ?? "No dossier headline was reported."}</p>
    </div>
    <time dateTime={snapshot.generatedUtc ?? ""}>{formatExactTimestamp(snapshot.generatedUtc)}</time>
  </header>
);

const DossierMetrics = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const dossier = snapshot.evidence.dossier;
  const metrics = [
    ["MODEL-PRICED TRADES", integer(dossier.tradeCount)],
    ["COHORTS INTERROGATED", integer(dossier.candidateCount)],
    ["HARD-GATE SURVIVORS", integer(dossier.eligibleCandidateCount)],
    ["DIAGNOSTIC FRONTIER", integer(dossier.diagnosticFrontierCount)],
    ["MUTATION ATTEMPTS", integer(dossier.mutationAttempts)],
    ["SELECTION-AWARE TRIALS", integer(dossier.effectiveTrials)],
    ["CAPITAL DIAGNOSTICS", integer(dossier.capitalCompleteCandidateCount)],
    ["CONTRACT ISSUES", integer(snapshot.evidence.contracts.issueCount)],
  ] as const;
  return (
    <div className="dossier-metrics">
      {metrics.map(([label, value], index) => <div key={label}><span>{String(index + 1).padStart(2, "0")} / {label}</span><strong>{value}</strong></div>)}
    </div>
  );
};

const EvidenceStack = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const dossier = snapshot.evidence.dossier;
  const layers = [
    { code: "D-1", label: "UNDERLYING HISTORY", value: dossier.realHistoryUsed === true ? "REAL / HASH-PINNED" : "UNVERIFIED", tone: dossier.realHistoryUsed === true ? "nominal" : "critical" },
    { code: "D-2", label: "OPTION OUTCOMES", value: dossier.realOptionChainUsed === true ? "QUOTE-PRICED" : "MODEL-PRICED ONLY", tone: dossier.realOptionChainUsed === true ? "nominal" : "warning" },
    { code: "D-3", label: "EXECUTABLE CHAIN", value: dossier.realOptionChainUsed === true ? "PRESENT" : "ABSENT", tone: dossier.realOptionChainUsed === true ? "nominal" : "critical" },
    { code: "D-4", label: "FITNESS", value: displayLabel(dossier.fitnessDecision), tone: statusTone(dossier.fitnessDecision) },
    { code: "D-5", label: "PROMOTION", value: dossier.promotionAllowed === true ? "ALLOWED" : "BLOCKED", tone: dossier.promotionAllowed === true ? "nominal" : "critical" },
  ] as const;
  return (
    <div className="evidence-stack">
      {layers.map((layer) => (
        <div className={`evidence-stack__layer evidence-stack__layer--${layer.tone}`} key={layer.code}>
          <span>{layer.code}</span><strong>{layer.label}</strong><b>{layer.value}</b><i />
        </div>
      ))}
    </div>
  );
};

const FrontierLedger = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const dossier = snapshot.evidence.dossier;
  if (dossier.frontierCandidateIds.length === 0) {
    return <EmptyState detail="No eligible or diagnostic frontier candidates were reported." label="FRONTIER / EMPTY" />;
  }
  return (
    <div className="frontier-ledger">
      {dossier.frontierCandidateIds.map((candidateId, index) => (
        <div key={candidateId}><span>{String(index + 1).padStart(2, "0")}</span><strong>{candidateId}</strong><em>DIAGNOSTIC ONLY</em></div>
      ))}
    </div>
  );
};

const OracleInstrument = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const oracle = snapshot.evidence.oracle;
  return (
    <div className="oracle-instrument">
      <div className="oracle-instrument__dial"><span>{integer(oracle.passedTestCount)} / {integer(oracle.testCount)}</span><i /></div>
      <dl>
        <div><dt>400-STEP BS ERROR</dt><dd>{formatScalar(oracle.convergenceError400Steps, 6)}</dd></div>
        <div><dt>AMERICAN PUT EXERCISE NODES</dt><dd>{integer(oracle.americanPutEarlyExerciseNodes)}</dd></div>
        <div><dt>DISCRETE-DIV CALL NODES</dt><dd>{integer(oracle.discreteDividendCallEarlyExerciseNodes)}</dd></div>
        <div><dt>SOURCE TIER</dt><dd>{displayLabel(oracle.pricingSourceTier)}</dd></div>
        <div><dt>SENSITIVITY GRID</dt><dd>{integer(oracle.sensitivityPointCount)} POINTS</dd></div>
        <div><dt>ODD / EVEN GAP</dt><dd>{formatScalar(oracle.oddEvenPriceGap, 6)}</dd></div>
      </dl>
    </div>
  );
};

const EvidenceIntegrityInstrument = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const contracts = snapshot.evidence.contracts;
  const mutation = snapshot.evidence.mutation;
  const dossier = snapshot.evidence.dossier;
  return (
    <div className="settlement-instrument evidence-integrity-instrument">
      <div><span>ARTIFACT CONTRACTS</span><strong>{displayLabel(contracts.status)}</strong></div>
      <div><span>CROSS-ARTIFACT ISSUES</span><strong>{integer(contracts.issueCount)}</strong></div>
      <div><span>CAPITAL NORMALIZATION</span><strong>{displayLabel(dossier.capitalNormalizationStatus)}</strong></div>
      <div><span>CHAMPIONS / CHANGES</span><strong>{integer(mutation.uniqueChampionCount)} / {integer(mutation.championChangeCount)}</strong></div>
      <p>
        Longest registry champion streak: {integer(mutation.longestChampionStreak)} generations. Contract registry {contracts.registryHash?.slice(0, 12) ?? "unreported"}; cycle {displayLabel(contracts.cycleStatus)}.
      </p>
    </div>
  );
};

const SettlementInstrument = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const settlement = snapshot.evidence.settlement;
  return (
    <div className="settlement-instrument">
      <div><span>OPERATION</span><strong>{displayLabel(settlement.status)}</strong></div>
      <div><span>RESOLVED / PENDING</span><strong>{integer(settlement.resolvedCountAfter)} / {integer(settlement.unresolvedCountAfter)}</strong></div>
      <div><span>SELECTIVE ROWS VERIFIED</span><strong>{integer(settlement.loadedRowCount)}</strong></div>
      <div><span>DECISION LEDGER</span><strong>{settlement.decisionLedgerImmutable === true ? "IMMUTABLE" : "UNVERIFIED"}</strong></div>
      <p>Resolution as of {settlement.resolutionAsOf ?? "not reported"}; hash-selective validation {settlement.selectiveHashValidation === true ? "active" : "unverified"}.</p>
    </div>
  );
};

export const EvidenceView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const dossier = snapshot.evidence.dossier;
  return (
    <div className="secondary-view evidence-view">
      <EvidenceHeader snapshot={snapshot} />
      <div className="evidence-grid">
        <InstrumentPanel className="evidence-grid__metrics" code="D-50" meta={displayLabel(dossier.status)} title="Dossier readout"><DossierMetrics snapshot={snapshot} /></InstrumentPanel>
        <InstrumentPanel className="evidence-grid__stack" code="D-51" meta="SOURCE CLASS / GATES" title="Evidence stack"><EvidenceStack snapshot={snapshot} /></InstrumentPanel>
        <InstrumentPanel className="evidence-grid__frontier" code="D-52" meta={displayLabel(dossier.frontierStatus)} title="Pareto frontier"><FrontierLedger snapshot={snapshot} /></InstrumentPanel>
        <InstrumentPanel className="" code="D-53" meta={displayLabel(snapshot.evidence.oracle.status)} title="CRR pricing oracle"><OracleInstrument snapshot={snapshot} /></InstrumentPanel>
        <InstrumentPanel className="" code="D-54" meta={displayLabel(snapshot.evidence.settlement.outcomeStatus)} title="Settlement engine"><SettlementInstrument snapshot={snapshot} /></InstrumentPanel>
        <InstrumentPanel className="" code="D-56" meta={displayLabel(snapshot.evidence.contracts.status)} title="Evidence integrity"><EvidenceIntegrityInstrument snapshot={snapshot} /></InstrumentPanel>
        <InstrumentPanel className="evidence-grid__economics" code="D-55" meta="MODEL UNITS / NOT RETURNS" title="Economic decomposition">
          <div className="economics-strip">
            <div><span>GROSS MODEL PNL</span><strong>{modelUnits(dossier.grossModelUnitPnl)}</strong></div>
            <div><span>COMPLETE COST STACK</span><strong>{modelUnits(dossier.totalCostModelUnits)}</strong></div>
            <div><span>NET MODEL PNL</span><strong>{modelUnits(dossier.netModelUnitPnl)}</strong></div>
            <p>Model-premium exposure and concurrent-risk diagnostics are available for comparison. Annualized return and Calmar remain unavailable because modeled premium is not a defensible real-capital denominator.</p>
          </div>
        </InstrumentPanel>
      </div>
      <EvidenceWorkbench analytics={snapshot.analytics} />
    </div>
  );
};
