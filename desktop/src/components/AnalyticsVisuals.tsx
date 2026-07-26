import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { statusTone } from "../lib/tone";
import { displayLabel, formatScalar } from "../state";
import type {
  AnalyticsEquityPoint,
  AnalyticsFoldMetric,
  AnalyticsParetoPoint,
  AnalyticsRobustnessGate,
  AnalyticsSourceState,
  DesktopAnalyticsState,
  GatedCapabilityState,
  OptionsSurfacePoint,
  PaperAnalyticsPosition,
} from "../types";

type VisualizationTab = "summary" | "chart" | "table" | "provenance" | "method";

interface VisualizationTable {
  readonly headers: readonly string[];
  readonly rows: readonly (readonly string[])[];
}

interface VisualizationFrameProps {
  readonly code: string;
  readonly title: string;
  readonly status: string;
  readonly summary: string;
  readonly method: string;
  readonly table: VisualizationTable;
  readonly sources: readonly AnalyticsSourceState[];
  readonly children: ReactNode;
  readonly className?: string;
}

const available = (status: string): boolean => status.startsWith("available");

const compactNumber = (value: number | null): string => value === null
  ? "—"
  : new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, notation: Math.abs(value) >= 10_000 ? "compact" : "standard" }).format(value);

const percent = (value: number | null): string => value === null ? "—" : `${(value * 100).toFixed(1)}%`;

const signed = (value: number | null): string => {
  if (value === null) {
    return "—";
  }
  const prefix = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${prefix}${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
};

const normalized = (value: number, minimum: number, maximum: number): number =>
  maximum === minimum ? 0.5 : (value - minimum) / (maximum - minimum);

const DataTable = ({ table, caption }: { readonly table: VisualizationTable; readonly caption: string }) => (
  <div className="analytics-table-wrap">
    <table className="analytics-table">
      <caption>{caption}</caption>
      <thead><tr>{table.headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead>
      <tbody>
        {table.rows.map((row, rowIndex) => (
          <tr key={`${caption}-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ProvenanceList = ({ sources }: { readonly sources: readonly AnalyticsSourceState[] }) => sources.length === 0 ? (
  <UnavailableState title="No provenance records" detail="This analytical surface did not report a local artifact source." />
) : (
  <div className="provenance-register">
    {sources.map((source) => (
      <div className={`provenance-row provenance-row--${statusTone(source.status)}`} key={source.sourceId}>
        <div><strong>{source.sourceId}</strong><span>{source.relativePath}</span></div>
        <em>{displayLabel(source.status)}</em>
        <code title={source.sha256 ?? "Hash unavailable"}>{source.sha256?.slice(0, 18) ?? "NO HASH"}</code>
      </div>
    ))}
  </div>
);

const VisualizationFrame = ({
  code,
  title,
  status,
  summary,
  method,
  table,
  sources,
  children,
  className = "",
}: VisualizationFrameProps) => {
  const [tab, setTab] = useState<VisualizationTab>("chart");
  const tabs: readonly VisualizationTab[] = ["summary", "chart", "table", "provenance", "method"];
  return (
    <section className={`analytics-frame ${className}`}>
      <header className="analytics-frame__header">
        <div><span>{code}</span><h3>{title}</h3></div>
        <em className={`status-pill status-pill--${statusTone(status)}`}>{displayLabel(status)}</em>
      </header>
      <div aria-label={`${title} display mode`} className="analytics-tabs" role="tablist">
        {tabs.map((candidate) => (
          <button
            aria-controls={`${code}-${candidate}`}
            aria-selected={tab === candidate}
            className={tab === candidate ? "is-active" : ""}
            key={candidate}
            onClick={() => setTab(candidate)}
            role="tab"
            type="button"
          >
            {candidate.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="analytics-frame__body" id={`${code}-${tab}`} role="tabpanel">
        {tab === "summary" ? <p className="chart-summary" role="status">{summary}</p> : null}
        {tab === "chart" ? children : null}
        {tab === "table" ? <DataTable caption={`${title} data`} table={table} /> : null}
        {tab === "provenance" ? <ProvenanceList sources={sources} /> : null}
        {tab === "method" ? <p className="chart-method">{method}</p> : null}
      </div>
    </section>
  );
};

export const UnavailableState = ({ title, detail }: { readonly title: string; readonly detail: string }) => (
  <div className="analytics-unavailable" role="status">
    <span aria-hidden="true">×</span>
    <div><strong>{title}</strong><p>{detail}</p></div>
  </div>
);

const FoldHeatmap = ({ metrics }: { readonly metrics: readonly AnalyticsFoldMetric[] }) => {
  const eras = [...new Set(metrics.map((metric) => metric.era))];
  const candidates = [...new Set(metrics.map((metric) => metric.candidateId))];
  const absoluteMaximum = Math.max(...metrics.map((metric) => Math.abs(metric.expectancyModelUnits ?? 0)), 0.001);
  return (
    <div className="matrix-chart matrix-chart--folds" style={{ "--matrix-columns": eras.length } as CSSProperties}>
      <span className="matrix-chart__corner">COHORT / ERA</span>
      {eras.map((era) => <strong className="matrix-chart__column" key={era}>{era.replaceAll("_", " ")}</strong>)}
      {candidates.map((candidate) => (
        <div className="matrix-chart__row" key={candidate}>
          <strong>{candidate}</strong>
          {eras.map((era) => {
            const metric = metrics.find((item) => item.candidateId === candidate && item.era === era);
            const value = metric?.expectancyModelUnits ?? null;
            const magnitude = value === null ? 0 : Math.min(Math.abs(value) / absoluteMaximum, 1);
            const tone = value === null ? "unknown" : value >= 0 ? "positive" : "negative";
            return (
              <button
                aria-label={`${candidate}, ${era}, expectancy ${signed(value)} model units, ${metric?.sampleCount ?? "unknown"} samples`}
                className={`matrix-cell matrix-cell--${tone}`}
                key={`${candidate}-${era}`}
                style={{ "--cell-intensity": magnitude } as CSSProperties}
                title={`${candidate}\n${era}\nExpectancy ${signed(value)} model units\nSample ${metric?.sampleCount ?? "unknown"}`}
                type="button"
              ><span>{signed(value)}</span></button>
            );
          })}
        </div>
      ))}
      <div className="chart-legend"><span><i className="legend-swatch legend-swatch--positive" /> POSITIVE</span><span><i className="legend-swatch legend-swatch--negative" /> NEGATIVE</span><em>MODEL UNITS / DIAGNOSTIC</em></div>
    </div>
  );
};

const RobustnessMatrix = ({ gates }: { readonly gates: readonly AnalyticsRobustnessGate[] }) => {
  const candidates = [...new Set(gates.map((gate) => gate.candidateId))];
  const gateIds = [...new Set(gates.map((gate) => gate.gateId))];
  return (
    <div className="robustness-matrix" style={{ "--matrix-columns": gateIds.length } as CSSProperties}>
      <div className="robustness-matrix__head">
        <span>COHORT</span>
        {gateIds.map((gateId) => <strong key={gateId} title={gateId}>{gateId.replaceAll("_", " ")}</strong>)}
      </div>
      {candidates.map((candidate) => (
        <div className="robustness-matrix__row" key={candidate}>
          <strong>{candidate}</strong>
          {gateIds.map((gateId) => {
            const gate = gates.find((item) => item.candidateId === candidate && item.gateId === gateId);
            const status = gate?.status ?? "unknown";
            return (
              <button
                aria-label={`${candidate}, ${gateId}, ${status}, observed ${gate?.observed ?? "unreported"}, required ${gate?.required ?? "unreported"}`}
                className={`robustness-cell robustness-cell--${statusTone(status)}`}
                key={`${candidate}-${gateId}`}
                title={`${gateId}\n${status}\nObserved ${gate?.observed ?? "—"}\nRequired ${gate?.required ?? "—"}`}
                type="button"
              ><span>{status === "pass" ? "P" : status === "fail" ? "F" : "U"}</span></button>
            );
          })}
        </div>
      ))}
      <div className="chart-legend"><span><i className="legend-swatch legend-swatch--pass" /> PASS</span><span><i className="legend-swatch legend-swatch--fail" /> FAIL</span><span><i className="legend-swatch legend-swatch--unknown" /> UNAVAILABLE</span></div>
    </div>
  );
};

const ParetoBubbleChart = ({ points }: { readonly points: readonly AnalyticsParetoPoint[] }) => {
  const xValues = points.map((point) => point.stressedExpectancyModelUnits ?? 0);
  const yValues = points.map((point) => point.tailLossP05ModelUnits ?? 0);
  const xMinimum = Math.min(...xValues, 0);
  const xMaximum = Math.max(...xValues, 0);
  const yMinimum = Math.min(...yValues, 0);
  const yMaximum = Math.max(...yValues, 0);
  return (
    <svg aria-label="Pareto diagnostic scatter plot. X axis is stressed expectancy in model units, Y axis is tail loss at the fifth percentile, and bubble size is trade count." className="pareto-chart" role="img" viewBox="0 0 720 330">
      <line className="chart-axis" x1="62" x2="690" y1="282" y2="282" />
      <line className="chart-axis" x1="62" x2="62" y1="24" y2="282" />
      <text className="chart-axis-label" x="365" y="319">STRESSED EXPECTANCY / MODEL UNITS</text>
      <text className="chart-axis-label" transform="translate(17 220) rotate(-90)">TAIL LOSS P05 / MODEL UNITS</text>
      {points.map((point, index) => {
        const x = 72 + normalized(point.stressedExpectancyModelUnits ?? 0, xMinimum, xMaximum) * 608;
        const y = 272 - normalized(point.tailLossP05ModelUnits ?? 0, yMinimum, yMaximum) * 238;
        const radius = 7 + Math.sqrt(Math.max(point.tradeCount ?? 0, 0)) / 45;
        return (
          <g className={`pareto-point pareto-point--${point.eligible === true ? "eligible" : "diagnostic"}`} key={point.candidateId} tabIndex={0}>
            <circle cx={x} cy={y} r={Math.min(radius, 28)} />
            <text x={x + 10} y={y - 10}>{String(index + 1).padStart(2, "0")}</text>
            <title>{`${point.candidateId}; stressed expectancy ${signed(point.stressedExpectancyModelUnits)} model units; tail p05 ${signed(point.tailLossP05ModelUnits)}; ${compactNumber(point.tradeCount)} trades; ${point.gateFailureCount ?? "unknown"} gate failures`}</title>
          </g>
        );
      })}
    </svg>
  );
};

const linePath = (
  points: readonly AnalyticsEquityPoint[],
  field: "cumulativeModelUnits" | "drawdownModelUnits",
  yTop: number,
  height: number,
): string => {
  const values = points.map((point) => point[field] ?? 0);
  const minimum = Math.min(...values, 0);
  const maximum = Math.max(...values, 0);
  return points.map((point, index) => {
    const x = 46 + index * (634 / Math.max(points.length - 1, 1));
    const y = yTop + height - normalized(point[field] ?? 0, minimum, maximum) * height;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
};

const EquityUnderwaterChart = ({ points }: { readonly points: readonly AnalyticsEquityPoint[] }) => (
  <svg aria-label="Synchronized diagnostic equity and drawdown paths in model units. These are not returns." className="equity-chart" role="img" viewBox="0 0 720 360">
    <line className="chart-axis" x1="46" x2="690" y1="168" y2="168" />
    <line className="chart-axis" x1="46" x2="690" y1="328" y2="328" />
    <path className="equity-chart__equity" d={linePath(points, "cumulativeModelUnits", 20, 125)} />
    <path className="equity-chart__drawdown" d={linePath(points, "drawdownModelUnits", 192, 120)} />
    <text className="chart-panel-label" x="52" y="34">CUMULATIVE DIAGNOSTIC MODEL PNL</text>
    <text className="chart-panel-label" x="52" y="207">UNDERWATER / DRAWDOWN MODEL UNITS</text>
    <text className="chart-axis-label" x="52" y="350">{points[0]?.date ?? "NO START"}</text>
    <text className="chart-axis-label" x="688" y="350" textAnchor="end">{points.at(-1)?.date ?? "NO END"}</text>
  </svg>
);

const FailureBars = ({ failures }: { readonly failures: readonly { readonly failureId: string; readonly candidateCount: number }[] }) => {
  const maximum = Math.max(...failures.map((failure) => failure.candidateCount), 1);
  return (
    <div className="failure-bars">
      {failures.map((failure, index) => (
        <div className="failure-bar" key={failure.failureId}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{failure.failureId.replaceAll("_", " ")}</strong>
          <i><b style={{ width: `${(failure.candidateCount / maximum) * 100}%` }} /></i>
          <em>{failure.candidateCount} / 12</em>
        </div>
      ))}
    </div>
  );
};

const chartSources = (analytics: DesktopAnalyticsState, ids: readonly string[]): readonly AnalyticsSourceState[] =>
  analytics.sources.filter((source) => ids.includes(source.sourceId));

export const EvidenceWorkbench = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const evidence = analytics.evidence;
  if (!available(evidence.status)) {
    return <UnavailableState title="Evidence workbench unavailable" detail={displayLabel(evidence.status)} />;
  }
  const foldTable: VisualizationTable = {
    headers: ["Candidate", "Era", "Sample", "Expectancy (model units)", "Win rate", "Profit factor"],
    rows: evidence.foldMetrics.map((metric) => [metric.candidateId, metric.era, compactNumber(metric.sampleCount), signed(metric.expectancyModelUnits), percent(metric.winRate), formatScalar(metric.profitFactor, 3)]),
  };
  const robustnessTable: VisualizationTable = {
    headers: ["Candidate", "Gate", "Status", "Observed", "Required"],
    rows: evidence.robustnessTests.map((gate) => [gate.candidateId, gate.gateId, gate.status, gate.observed, gate.required]),
  };
  const paretoTable: VisualizationTable = {
    headers: ["Candidate", "Trades", "Stressed expectancy", "Tail p05", "Drawdown", "Failures"],
    rows: evidence.paretoFrontier.map((point) => [point.candidateId, compactNumber(point.tradeCount), signed(point.stressedExpectancyModelUnits), signed(point.tailLossP05ModelUnits), signed(point.maxDrawdownModelUnits), compactNumber(point.gateFailureCount)]),
  };
  const equityTable: VisualizationTable = {
    headers: ["Date", "Trades", "Net model units", "Cumulative model units", "Drawdown model units"],
    rows: evidence.equityCurve.map((point) => [point.date, compactNumber(point.tradeCount), signed(point.netModelUnits), signed(point.cumulativeModelUnits), signed(point.drawdownModelUnits)]),
  };
  const evidenceSources = chartSources(analytics, ["latest_dossier", "fold_metrics", "robustness_tests", "pareto_frontier", "equity_curve", "failure_modes"]);
  return (
    <section className="evidence-workbench" aria-label="Strategy evidence analytics workbench">
      <div className="selection-pressure-strip">
        <div><span>CANDIDATES</span><strong>{compactNumber(evidence.selectionPressure.candidateCount)}</strong></div>
        <div><span>DIAGNOSTIC FRONTIER</span><strong>{compactNumber(evidence.selectionPressure.diagnosticFrontierCount)}</strong></div>
        <div><span>ELIGIBLE</span><strong>{compactNumber(evidence.selectionPressure.eligibleCandidateCount)}</strong></div>
        <div><span>EFFECTIVE TRIALS</span><strong>{compactNumber(evidence.selectionPressure.effectiveTrials)}</strong></div>
        <div><span>MUTATION ATTEMPTS</span><strong>{compactNumber(evidence.selectionPressure.mutationAttempts)}</strong></div>
        <div><span>TRADE RECORDS</span><strong>{compactNumber(evidence.selectionPressure.tradeCount)}</strong></div>
        <p>SELECTION PRESSURE / MODEL-PRICED DIAGNOSTIC ONLY / ZERO ELIGIBLE FOR PROMOTION</p>
      </div>
      <div className="analytics-bento analytics-bento--evidence">
        <VisualizationFrame className="analytics-frame--wide" code="E-70" method="Each cell is one candidate-by-era fold. Color sign and numeric labels encode average model-unit P&L; sample counts remain visible in the table and keyboard tooltip." sources={evidenceSources} status={evidence.status} summary={`${evidence.foldMetrics.length} walk-forward candidate-era folds are displayed. Every value is diagnostic model-unit evidence, not a realized or forward return.`} table={foldTable} title="Walk-forward fold heatmap">
          <FoldHeatmap metrics={evidence.foldMetrics} />
        </VisualizationFrame>
        <VisualizationFrame className="analytics-frame--wide" code="E-71" method="Rows are candidates and columns are predeclared hard gates. P, F, and U remain visible so the matrix never relies on color alone." sources={evidenceSources} status={evidence.status} summary={`${evidence.robustnessTests.filter((gate) => gate.status === "fail").length} failed hard-gate evaluations remain visible across ${new Set(evidence.robustnessTests.map((gate) => gate.candidateId)).size} candidates.`} table={robustnessTable} title="Robustness gate matrix">
          <RobustnessMatrix gates={evidence.robustnessTests} />
        </VisualizationFrame>
        <VisualizationFrame code="E-72" method="X encodes stressed-cost expectancy, Y encodes fifth-percentile tail loss, and bubble size encodes diagnostic trade count. No bubble is an eligible strategy." sources={evidenceSources} status={evidence.status} summary={`${evidence.paretoFrontier.length} candidates lie on the diagnostic frontier; eligibility remains ${evidence.selectionPressure.eligibleCandidateCount ?? 0}.`} table={paretoTable} title="Pareto diagnostic field">
          <ParetoBubbleChart points={evidence.paretoFrontier} />
        </VisualizationFrame>
        <VisualizationFrame code="E-73" method="The upper panel is cumulative model-unit P&L and the lower panel is drawdown in the same non-capital unit. The renderer downsamples long series while preserving first and last observations." sources={evidenceSources} status={evidence.status} summary={`${evidence.equityCurve.length} downsampled observations show diagnostic path behavior. This panel is explicitly not annualized return or realized capital performance.`} table={equityTable} title="Diagnostic equity + underwater">
          <EquityUnderwaterChart points={evidence.equityCurve} />
        </VisualizationFrame>
        <VisualizationFrame className="analytics-frame--wide" code="E-74" method="Gate failures are counted once per candidate from the governed failure-mode artifact and ranked descending." sources={evidenceSources} status={evidence.status} summary={`${evidence.failureRanking[0]?.failureId.replaceAll("_", " ") ?? "No failure"} is the most common candidate blocker.`} table={{ headers: ["Failure", "Candidate count"], rows: evidence.failureRanking.map((failure) => [failure.failureId, String(failure.candidateCount)]) }} title="Failure mode ranking">
          <FailureBars failures={evidence.failureRanking} />
        </VisualizationFrame>
      </div>
    </section>
  );
};

const ReadinessLane = ({ lane }: { readonly lane: DesktopAnalyticsState["readiness"]["lanes"][number] }) => {
  const ratio = lane.current === null || lane.required === null ? null : Math.min(lane.current / Math.max(lane.required, 1), 1);
  const status = lane.missingChecks.length > 0 ? "blocked" : ratio === null ? "unavailable" : ratio >= 1 ? "complete" : "accruing";
  return (
    <article className={`readiness-lane readiness-lane--${statusTone(status)}`}>
      <header><span>P{lane.priority ?? "—"}</span><strong>{lane.laneId.replaceAll("_", " ")}</strong><em>{displayLabel(status)}</em></header>
      <div className="readiness-lane__meter" aria-label={`${lane.current ?? "unknown"} of ${lane.required ?? "unknown"}`} role="progressbar" aria-valuemin={0} aria-valuemax={lane.required ?? undefined} aria-valuenow={lane.current ?? undefined}><i style={{ width: `${(ratio ?? 0) * 100}%` }} /></div>
      <dl>
        <div><dt>CURRENT</dt><dd>{compactNumber(lane.current)}</dd></div>
        <div><dt>REQUIRED</dt><dd>{compactNumber(lane.required)}</dd></div>
        <div><dt>REMAINING</dt><dd>{compactNumber(lane.remaining)}</dd></div>
        <div><dt>ETA BAND</dt><dd>{lane.estimatedTradingDays !== null ? `≈ ${lane.estimatedTradingDays.toFixed(1)} sessions` : lane.maturityLagDays !== null ? `≥ ${lane.maturityLagDays} days maturity lag` : "EVIDENCE-DEPENDENT"}</dd></div>
      </dl>
      <p>{lane.acceleration ?? "No acceleration procedure reported."}</p>
      {lane.missingChecks.length > 0 ? <ul>{lane.missingChecks.map((check) => <li key={check}>{check.replaceAll("_", " ")}</li>)}</ul> : null}
      <footer><span>{lane.thresholdUnchanged === true ? "THRESHOLD UNCHANGED" : "THRESHOLD UNVERIFIED"}</span>{lane.estimateOnlyNotAPromise === true ? <em>ESTIMATE / NOT A PROMISE</em> : null}</footer>
    </article>
  );
};

export const ReadinessAccrualCockpit = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const readiness = analytics.readiness;
  const governance = readiness.governance;
  return (
    <section className="readiness-cockpit" aria-label="Readiness accrual cockpit">
      <header className="analytics-section-header"><div><span>FORWARD EVIDENCE VELOCITY</span><h2>Readiness accrual cockpit</h2></div><em className={`status-pill status-pill--${statusTone(readiness.status)}`}>{displayLabel(readiness.status)}</em></header>
      <div className="readiness-lanes">{readiness.lanes.map((lane) => <ReadinessLane key={lane.laneId} lane={lane} />)}</div>
      <div className="governance-ledger">
        <div><span>POLICY DELTA</span><strong>{governance.gatePolicyChanged === true ? "RECORDED" : "NO REPORTED CHANGE"}</strong></div>
        <div><span>REMOVED GATES</span><strong>{governance.removedGateIds.length === 0 ? "NONE" : governance.removedGateIds.join(", ").replaceAll("_", " ")}</strong></div>
        <div><span>REMAINING THRESHOLDS</span><strong>{governance.remainingThresholdsLowered === false ? "NOT LOWERED" : "UNVERIFIED"}</strong></div>
        <div><span>CONTEXT EVIDENCE</span><strong>{displayLabel(readiness.contextEvidenceStatus)}</strong></div>
        <div><span>NEWS INTAKE</span><strong>{displayLabel(readiness.newsPipelineStatus)} / {readiness.newsRequiredCoverageComplete === true ? "REQUIRED COVERAGE COMPLETE" : "COVERAGE UNVERIFIED"}</strong></div>
        <div><span>SUPPLEMENTAL FAILURES</span><strong>{readiness.newsFailedSourceIds.length === 0 ? "NONE" : readiness.newsFailedSourceIds.join(", ")}</strong></div>
        <code title={governance.reproducibilityHash ?? "Hash not reported"}>{governance.reproducibilityHash ?? "NO GOVERNANCE HASH"}</code>
      </div>
    </section>
  );
};

const CapabilityCard = ({ label, capability }: { readonly label: string; readonly capability: GatedCapabilityState }) => (
  <article className={`capability-card capability-card--${statusTone(capability.status)}`}>
    <header><span>CAPABILITY</span><strong>{label}</strong></header>
    <em>{displayLabel(capability.status)}</em>
    <p>{capability.reason ?? "The governed evidence contract is not yet satisfied."}</p>
    {capability.requiredEvidence.length > 0 ? <ul>{capability.requiredEvidence.map((requirement) => <li key={requirement}>{requirement.replaceAll("_", " ")}</li>)}</ul> : null}
  </article>
);

const ReliabilityDiagram = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const calibration = analytics.machineLearning.calibration;
  if (calibration.sampleSufficient !== true || calibration.settledTotal === null || calibration.settledTotal < (calibration.minimumSample ?? Number.POSITIVE_INFINITY)) {
    return <UnavailableState title="Forward reliability diagram gated" detail={`${compactNumber(calibration.settledTotal)} settled / ${compactNumber(calibration.minimumSample)} required. Empty bins are not rendered as calibration evidence.`} />;
  }
  return (
    <svg aria-label="Forward calibration reliability diagram" className="reliability-chart" role="img" viewBox="0 0 360 320">
      <line className="reliability-chart__ideal" x1="42" x2="330" y1="280" y2="24" />
      <polyline className="reliability-chart__observed" points={calibration.bins.filter((bin) => (bin.count ?? 0) > 0).map((bin) => `${42 + (bin.meanConfidence ?? 0) * 288},${280 - (bin.accuracy ?? 0) * 256}`).join(" ")} />
    </svg>
  );
};

export const MachineLearningTruth = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const ml = analytics.machineLearning;
  const calibration = ml.calibration;
  const signal = ml.signalCalibration;
  const table: VisualizationTable = {
    headers: ["Bin", "Count", "Mean confidence", "Accuracy"],
    rows: calibration.bins.map((bin) => [`${formatScalar(bin.lower, 1)}–${formatScalar(bin.upper, 1)}`, compactNumber(bin.count), percent(bin.meanConfidence), percent(bin.accuracy)]),
  };
  return (
    <section className="ml-truth" aria-label="Machine learning evidence truth surfaces">
      <header className="analytics-section-header"><div><span>GATED ML EVIDENCE</span><h2>Calibration, ablation & uncertainty</h2></div><em>NO SYNTHETIC CHARTS</em></header>
      <div className="analytics-bento analytics-bento--ml">
        <VisualizationFrame code="ML-01" method="Forward reliability is rendered only after the declared minimum settled sample. The diagonal is ideal calibration; bins require observed predictions and independently settled targets." sources={chartSources(analytics, ["forward_calibration"])} status={calibration.status} summary={`${compactNumber(calibration.settledTotal)} settled and ${compactNumber(calibration.pendingTotal)} pending against a ${compactNumber(calibration.minimumSample)} minimum sample.`} table={table} title="Forward reliability">
          <ReliabilityDiagram analytics={analytics} />
        </VisualizationFrame>
        <article className="signal-calibration-card">
          <header><span>ADVISORY LANE</span><strong>Phantom signal grading</strong></header>
          <dl><div><dt>SETTLED</dt><dd>{compactNumber(signal.settledTotal)}</dd></div><div><dt>HIT RATE</dt><dd>{percent(signal.overallHitRate)}</dd></div><div><dt>CONTESTED</dt><dd>{compactNumber(signal.contestedTotal)}</dd></div><div><dt>CONTESTED HIT</dt><dd>{percent(signal.contestedHitRate)}</dd></div></dl>
          <p>{displayLabel(signal.semantics)}. This lane is advisory, not edge evidence, and promotion is {signal.promotionAllowed === false ? "blocked" : "unverified"}.</p>
        </article>
        <CapabilityCard label="Agent ablation forest plot" capability={{ status: ml.agentAblation.status, reason: `${compactNumber(ml.agentAblation.eligibleSettlementCount)} eligible settlements; ${compactNumber(ml.agentAblation.minimumSample)} required under the protected evaluator.`, requiredEvidence: ["protected evaluator results", "precommitted counterfactuals"] }} />
        <CapabilityCard label="Conformal coverage" capability={ml.conformal} />
        <CapabilityCard label="Feature attribution / SHAP" capability={ml.shap} />
        <CapabilityCard label="Embedding projection / UMAP" capability={ml.embeddings} />
        <CapabilityCard label="Neural training curves" capability={ml.training} />
      </div>
    </section>
  );
};

const ExposureBars = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const exposures = analytics.paper.exposures;
  const maximum = Math.max(...exposures.map((exposure) => exposure.entryPremiumUnits), 1);
  return (
    <div className="exposure-bars">
      {exposures.map((exposure) => (
        <div className="exposure-bar" key={`${exposure.axis}-${exposure.key}`}>
          <span>{exposure.axis.toUpperCase()}</span><strong>{exposure.key.replaceAll("_", " ")}</strong>
          <i><b style={{ width: `${(exposure.entryPremiumUnits / maximum) * 100}%` }} /></i>
          <em>{exposure.positionCount} / {exposure.entryPremiumUnits.toFixed(2)} premium units</em>
        </div>
      ))}
    </div>
  );
};

const PositionRiskTable = ({ positions }: { readonly positions: readonly PaperAnalyticsPosition[] }) => (
  <div className="paper-risk-table">
    {positions.map((position) => (
      <div className={`paper-risk-row paper-risk-row--${position.status}`} key={position.positionId}>
        <strong>{position.symbol}</strong>
        <span>{displayLabel(position.structure)}</span>
        <span>{position.sector.replaceAll("_", " ")}</span>
        <span>{position.ageDays ?? "—"}d AGE</span>
        <span>{position.quoteAgeDays ?? "—"}d QUOTE</span>
        <i title="Terminal path P/L only; no intraposition path series is available"><b className={(position.pathPnl ?? 0) >= 0 ? "is-positive" : "is-negative"} style={{ width: `${Math.min(Math.abs(position.pathPnl ?? 0) * 18, 100)}%` }} /></i>
        <em>{signed(position.pathPnl)} {position.status === "closed" ? "PATH PNL" : "MARK DELTA N/A"}</em>
      </div>
    ))}
  </div>
);

export const PaperRiskCockpit = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const paper = analytics.paper;
  if (!available(paper.status)) {
    return <UnavailableState title="Paper risk cockpit unavailable" detail={displayLabel(paper.status)} />;
  }
  const closed = paper.positions.filter((position) => position.status === "closed");
  return (
    <section className="paper-risk-cockpit">
      <header className="analytics-section-header"><div><span>QUOTE-DERIVED PAPER BOOK</span><h2>Exposure, age & path diagnostics</h2></div><em>{compactNumber(paper.closedCount)} / {compactNumber(paper.closedRequired)} CLOSED</em></header>
      <div className="paper-risk-grid">
        <article><header><span>OPEN EXPOSURE</span><strong>Sector & direction</strong></header><ExposureBars analytics={analytics} /></article>
        <article><header><span>POSITION REGISTER</span><strong>Age, quote staleness & terminal path P/L</strong></header><PositionRiskTable positions={paper.positions} /></article>
        <article className="paper-distribution"><header><span>CLOSED SAMPLE</span><strong>Early distribution — not a profitability claim</strong></header><div className="paper-distribution__marks">{closed.map((position) => <i className={(position.pathPnl ?? 0) >= 0 ? "is-positive" : "is-negative"} key={position.positionId} style={{ height: `${8 + Math.min(Math.abs(position.pathPnl ?? 0) * 12, 72)}%` }} title={`${position.symbol}: ${signed(position.pathPnl)} path P/L`} />)}</div><p>{closed.length} closed quote-derived paper outcomes. Distribution inference remains immature until the declared {paper.closedRequired ?? 100}-trade threshold.</p></article>
      </div>
    </section>
  );
};

type OptionsMetric = "impliedVol" | "relativeSpread" | "openInterest";

const optionsMetricValue = (point: OptionsSurfacePoint, metric: OptionsMetric): number | null => point[metric];

const OptionsSurfaceChart = ({ points, metric }: { readonly points: readonly OptionsSurfacePoint[]; readonly metric: OptionsMetric }) => {
  const strikes = [...new Set(points.map((point) => point.strike).filter((value): value is number => value !== null))].sort((left, right) => left - right);
  const dtes = [...new Set(points.map((point) => point.dte).filter((value): value is number => value !== null))].sort((left, right) => left - right);
  const reducedStrikes = strikes.filter((_, index) => index % Math.max(Math.ceil(strikes.length / 16), 1) === 0).slice(0, 16);
  const reducedDtes = dtes.slice(0, 10);
  const values = points.map((point) => optionsMetricValue(point, metric)).filter((value): value is number => value !== null);
  const minimum = Math.min(...values, 0);
  const maximum = Math.max(...values, 1);
  return (
    <div className="options-surface" style={{ "--surface-columns": reducedDtes.length } as CSSProperties}>
      <span className="options-surface__corner">STRIKE / DTE</span>
      {reducedDtes.map((dte) => <strong key={dte}>{dte}D</strong>)}
      {reducedStrikes.map((strike) => (
        <div className="options-surface__row" key={strike}>
          <strong>{strike.toFixed(0)}</strong>
          {reducedDtes.map((dte) => {
            const point = points.find((candidate) => candidate.strike === strike && candidate.dte === dte);
            const value = point === undefined ? null : optionsMetricValue(point, metric);
            return <button aria-label={`Strike ${strike}, ${dte} days, ${metric} ${value ?? "unavailable"}`} className={value === null ? "is-empty" : ""} key={`${strike}-${dte}`} style={{ "--cell-intensity": value === null ? 0 : normalized(value, minimum, maximum) } as CSSProperties} title={value === null ? "No quote" : `${metric}: ${value.toFixed(4)}`} type="button"><span>{value === null ? "—" : metric === "openInterest" ? compactNumber(value) : value.toFixed(2)}</span></button>;
          })}
        </div>
      ))}
    </div>
  );
};

const SmileChart = ({ points }: { readonly points: readonly OptionsSurfacePoint[] }) => {
  const expiries = [...new Set(points.map((point) => point.expiry))].slice(0, 4);
  const colors = ["var(--celadon)", "var(--mineral)", "var(--ochre)", "var(--violet)"];
  const series = expiries.map((expiry) => points.filter((point) => point.expiry === expiry && point.moneyness !== null && point.impliedVol !== null).sort((left, right) => (left.moneyness ?? 0) - (right.moneyness ?? 0)));
  const allIv = series.flat().map((point) => point.impliedVol ?? 0);
  const minIv = Math.min(...allIv, 0);
  const maxIv = Math.max(...allIv, 1);
  return (
    <div className="smile-chart-wrap">
      <svg aria-label="Implied volatility smile by expiry" className="smile-chart" role="img" viewBox="0 0 620 280">
        <line className="chart-axis" x1="46" x2="600" y1="242" y2="242" /><line className="chart-axis" x1="46" x2="46" y1="18" y2="242" />
        {series.map((pointsForExpiry, index) => <polyline fill="none" key={expiries[index]} points={pointsForExpiry.map((point) => `${46 + normalized(point.moneyness ?? 1, 0.65, 1.35) * 554},${234 - normalized(point.impliedVol ?? 0, minIv, maxIv) * 204}`).join(" ")} stroke={colors[index]} strokeWidth="2" />)}
        <text className="chart-axis-label" x="320" y="272">MONEYNESS / STRIKE ÷ SPOT</text>
      </svg>
      <div className="chart-legend">{expiries.map((expiry, index) => <span key={expiry}><i style={{ background: colors[index] }} />{expiry}</span>)}</div>
    </div>
  );
};

export const OptionsIntelligence = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const options = analytics.options;
  const [optionType, setOptionType] = useState("call");
  const [metric, setMetric] = useState<OptionsMetric>("impliedVol");
  const points = useMemo(() => options.surface.filter((point) => point.optionType === optionType), [optionType, options.surface]);
  if (!available(options.status)) {
    return <UnavailableState title="Options intelligence unavailable" detail={displayLabel(options.status)} />;
  }
  const table: VisualizationTable = {
    headers: ["Expiry", "DTE", "Type", "Strike", "IV", "Spread", "OI", "Volume"],
    rows: points.map((point) => [point.expiry, compactNumber(point.dte), point.optionType, compactNumber(point.strike), percent(point.impliedVol), percent(point.relativeSpread), compactNumber(point.openInterest), compactNumber(point.volume)]),
  };
  return (
    <section className="options-intelligence">
      <header className="analytics-section-header"><div><span>QUOTE-DERIVED / {options.snapshotDate ?? "UNKNOWN DATE"}</span><h2>{options.symbol ?? "UNKNOWN"} options surface</h2></div><em>NOT EDGE EVIDENCE</em></header>
      <div className="options-controls"><div role="group" aria-label="Option type">{["call", "put"].map((type) => <button aria-pressed={type === optionType} className={type === optionType ? "is-active" : ""} key={type} onClick={() => setOptionType(type)} type="button">{type.toUpperCase()}</button>)}</div><div role="group" aria-label="Surface metric">{(["impliedVol", "relativeSpread", "openInterest"] as const).map((candidate) => <button aria-pressed={candidate === metric} className={candidate === metric ? "is-active" : ""} key={candidate} onClick={() => setMetric(candidate)} type="button">{candidate === "impliedVol" ? "IV" : candidate === "relativeSpread" ? "SPREAD" : "OPEN INTEREST"}</button>)}</div></div>
      <div className="analytics-bento analytics-bento--options">
        <VisualizationFrame className="analytics-frame--wide" code="OP-01" method="Cells use the latest local quote-derived option chain. Strike is restricted around spot and DTE to 120 days. Numeric labels and a full table prevent color-only interpretation." sources={chartSources(analytics, ["options_surface"])} status={options.status} summary={`${points.length} ${optionType} quotes are available for ${options.symbol}. The surface is quote-derived paper research and not evidence of an edge.`} table={table} title="Strike × expiry surface">
          <OptionsSurfaceChart metric={metric} points={points} />
        </VisualizationFrame>
        <VisualizationFrame code="OP-02" method="Lines connect quote-derived implied volatility by moneyness for up to four expiries. This is a cross-sectional chain view, not a forecast." sources={chartSources(analytics, ["options_surface"])} status={options.status} summary="Expiry smiles expose skew and curvature directly from the latest chain snapshot." table={table} title="IV smile by expiry">
          <SmileChart points={points} />
        </VisualizationFrame>
        <article className="iv-calibration-card"><header><span>MODEL ↔ QUOTE CALIBRATION</span><strong>{displayLabel(options.ivCalibration.status)}</strong></header><dl><div><dt>CURRENT</dt><dd>{formatScalar(options.ivCalibration.currentMultiplier, 3)}</dd></div><div><dt>RECOMMENDED</dt><dd>{formatScalar(options.ivCalibration.recommendedMultiplier, 3)}</dd></div><div><dt>IV/RV P25–P75</dt><dd>{formatScalar(options.ivCalibration.ivOverRvP25, 3)}–{formatScalar(options.ivCalibration.ivOverRvP75, 3)}</dd></div><div><dt>PREMIUM ERROR MEDIAN</dt><dd>{percent(options.ivCalibration.premiumErrorMedian)}</dd></div><div><dt>SYMBOLS</dt><dd>{compactNumber(options.ivCalibration.symbolsCovered)}</dd></div></dl><p>Quote-derived calibration diagnoses model-pricing bias. It is not strategy performance or promotion evidence.</p></article>
      </div>
    </section>
  );
};

export const RegimeIntelligence = ({ analytics }: { readonly analytics: DesktopAnalyticsState }) => {
  const regime = analytics.regime;
  return (
    <section className="regime-intelligence">
      <header className="analytics-section-header"><div><span>PROVENANCE HISTORY</span><h2>Regime & source telemetry</h2></div><em>{regime.history.length} SNAPSHOTS INDEXED</em></header>
      <div className="regime-ribbon" aria-label="Recent cross-asset and news snapshot history">
        {regime.history.slice(0, 32).map((point) => <button aria-label={`${point.lane} snapshot ${point.snapshotId}, ${point.fileCount} files`} className={`regime-ribbon__point regime-ribbon__point--${point.lane}`} key={`${point.lane}-${point.snapshotId}`} title={`${point.lane}\n${point.snapshotId}\n${point.fileCount} files`} type="button"><i /><span>{point.snapshotId.slice(4, 12)}</span></button>)}
      </div>
      <div className="capability-grid"><CapabilityCard label="Regime transition probabilities" capability={regime.transitionModel} /><CapabilityCard label="Distribution drift tests" capability={regime.distributionDrift} /></div>
    </section>
  );
};
