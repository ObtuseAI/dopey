import type { ReactNode } from "react";
import { displayLabel, formatRatio, formatTimestamp, normalizedPercent } from "../state";
import type {
  ConfidenceDimension,
  ObservatoryDatum,
  ScheduleLane,
  SourceState,
  UniverseSymbol,
  UniverseState,
  WorldRegime,
} from "../types";

interface PanelProps {
  readonly code: string;
  readonly title: string;
  readonly meta: string | null;
  readonly className: string;
  readonly children: ReactNode;
}

export const InstrumentPanel = ({ code, title, meta, className, children }: PanelProps) => (
  <section className={`instrument-panel ${className}`}>
    <header className="instrument-panel__header">
      <span className="instrument-panel__code">{code}</span>
      <h2>{title}</h2>
      {meta === null ? null : <span className="instrument-panel__meta">{meta}</span>}
    </header>
    <div className="instrument-panel__body">{children}</div>
  </section>
);

interface EmptyStateProps {
  readonly label: string;
  readonly detail: string;
}

export const EmptyState = ({ label, detail }: EmptyStateProps) => (
  <div className="empty-state">
    <span>{label}</span>
    <p>{detail}</p>
  </div>
);

type UniverseCoverageStatus = "observed" | "stale" | "missing" | "unassigned";

interface UniverseCoverageSlot {
  readonly id: string;
  readonly label: string;
  readonly status: UniverseCoverageStatus;
  readonly tier: string | null;
}

interface UniverseCoverageGroup {
  readonly id: string;
  readonly label: string;
  readonly symbols: readonly UniverseSymbol[];
}

interface UniverseCoverageStatusDefinition {
  readonly id: UniverseCoverageStatus;
  readonly label: string;
}

const universeCoverageStatuses: readonly UniverseCoverageStatusDefinition[] = [
  { id: "observed", label: "OBSERVED" },
  { id: "stale", label: "STALE" },
  { id: "missing", label: "MISSING" },
  { id: "unassigned", label: "OPEN" },
];

const tissueStatus = (symbolStatus: string | null, active: boolean): UniverseCoverageStatus => {
  if (!active) {
    return "unassigned";
  }
  const status = symbolStatus?.toLowerCase() ?? "";
  if (status.includes("missing") || status.includes("fail") || status.includes("error")) {
    return "missing";
  }
  if (status.includes("stale") || status.includes("degrad") || status.includes("warn")) {
    return "stale";
  }
  return "observed";
};

export const UniverseTissue = ({ universe, expanded }: { readonly universe: UniverseState; readonly expanded: boolean }) => {
  const slots = Array.from({ length: 200 }, (_, index) => {
    const symbol = universe.symbols[index];
    const active = symbol !== undefined;
    return {
      id: `slot-${index + 1}`,
      label: symbol?.symbol ?? `Unassigned slot ${index + 1}`,
      tier: symbol?.tier ?? null,
      status: tissueStatus(symbol?.status ?? null, active),
    };
  });

  return (
    <div className={`universe-tissue${expanded ? " universe-tissue--expanded" : ""}`}>
      <div className="universe-tissue__readout">
        <div>
          <span>ACTIVE / TARGET</span>
          <strong>{formatRatio(universe.activeCount, universe.targetCount)}</strong>
        </div>
        <div>
          <span>PUBLIC LAKE</span>
          <strong>{universe.publicLakeCount ?? "—"}</strong>
        </div>
        <div>
          <span>HARD CAP</span>
          <strong>{universe.maximumCount ?? "—"}</strong>
        </div>
      </div>
      <div className="tissue-grid" aria-label="Two hundred symbol research coverage slots">
        {slots.map((slot) => (
          <span
            aria-label={`${slot.label}; ${slot.tier === null ? "tier not reported" : `tier ${slot.tier}`}; ${slot.status}`}
            className={`tissue-cell tissue-cell--${slot.status}`}
            key={slot.id}
            title={`${slot.label} / ${slot.tier ?? "NO TIER"} / ${slot.status.toUpperCase()}`}
          />
        ))}
      </div>
      <div className="tissue-legend" aria-label="Coverage legend">
        <span><i className="tissue-cell--observed" /> OBSERVED</span>
        <span><i className="tissue-cell--stale" /> STALE / DEGRADED</span>
        <span><i className="tissue-cell--missing" /> MISSING / FAILED</span>
        <span><i className="tissue-cell--unassigned" /> UNASSIGNED</span>
        <em>ENCODES COVERAGE HEALTH — NEVER PRICE PERFORMANCE</em>
      </div>
    </div>
  );
};

const universeSlotCount = (universe: UniverseState): number => Math.max(
  universe.symbols.length,
  universe.targetCount ?? universe.symbols.length,
);

const universeCoverageSlots = (universe: UniverseState): readonly UniverseCoverageSlot[] =>
  Array.from({ length: universeSlotCount(universe) }, (_, index) => {
    const symbol = universe.symbols[index];
    const active = symbol !== undefined;
    return {
      id: `coverage-slot-${index + 1}`,
      label: symbol?.symbol ?? `Unassigned slot ${index + 1}`,
      tier: symbol?.tier ?? null,
      status: tissueStatus(symbol?.status ?? null, active),
    };
  });

const universeCoverageCount = (
  slots: readonly UniverseCoverageSlot[],
  status: UniverseCoverageStatus,
): number => slots.filter((slot) => slot.status === status).length;

const universeCoveragePercent = (count: number, total: number): number =>
  total <= 0 ? 0 : Math.round((count / total) * 100);

const universeCoverageTone = (
  attentionCount: number,
  activeCount: number,
  targetCount: number,
): "attention" | "nominal" | "open" => {
  if (attentionCount > 0) {
    return "attention";
  }
  if (targetCount > 0 && activeCount >= targetCount) {
    return "nominal";
  }
  return "open";
};

const UniverseCoverageRail = ({ slots }: { readonly slots: readonly UniverseCoverageSlot[] }) => {
  const total = slots.length;
  return (
    <div className="coverage-rail" aria-label="Universe coverage status distribution">
      <div className="coverage-rail__track">
        {universeCoverageStatuses.map((definition) => {
          const count = universeCoverageCount(slots, definition.id);
          return count === 0 ? null : (
            <i
              aria-hidden="true"
              className={`coverage-rail__segment coverage-rail__segment--${definition.id}`}
              key={definition.id}
              style={{ width: `${universeCoveragePercent(count, total)}%` }}
            />
          );
        })}
      </div>
      <div className="coverage-rail__legend">
        {universeCoverageStatuses.map((definition) => {
          const count = universeCoverageCount(slots, definition.id);
          return (
            <div className={`coverage-rail__stat coverage-rail__stat--${definition.id}`} key={definition.id}>
              <i aria-hidden="true" />
              <span>{definition.label}</span>
              <strong>{count}</strong>
              <small>{universeCoveragePercent(count, total)}%</small>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const UniverseCoverageSummary = ({ universe }: { readonly universe: UniverseState }) => {
  const slots = universeCoverageSlots(universe);
  const activeCount = universe.activeCount ?? universe.symbols.length;
  const targetCount = universe.targetCount ?? slots.length;
  const activePercent = universeCoveragePercent(activeCount, targetCount);
  const staleCount = universeCoverageCount(slots, "stale");
  const missingCount = universeCoverageCount(slots, "missing");
  const unassignedCount = universeCoverageCount(slots, "unassigned");
  const attentionCount = staleCount + missingCount;
  const tone = universeCoverageTone(attentionCount, activeCount, targetCount);
  const circumference = 289;
  const dashOffset = circumference - (circumference * Math.min(activePercent, 100)) / 100;

  return (
    <div className={`coverage-summary coverage-summary--${tone}`}>
      <div className="coverage-summary__hero">
        <div className="coverage-orbit" aria-label={`${activePercent}% of universe target active`}>
          <svg aria-hidden="true" viewBox="0 0 112 112">
            <circle className="coverage-orbit__track" cx="56" cy="56" r="46" />
            <circle
              className="coverage-orbit__value"
              cx="56"
              cy="56"
              r="46"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
            />
          </svg>
          <strong>{activePercent}%</strong>
          <span>ACTIVE</span>
        </div>
        <div className="coverage-summary__headline">
          <span>UNIVERSE HEALTH</span>
          <strong>{tone === "nominal" ? "Coverage nominal" : tone === "attention" ? `${attentionCount} symbols need attention` : `${unassignedCount} target slots open`}</strong>
          <p>{formatRatio(activeCount, targetCount)} governed symbols are active. Health state is explicit and never implies price performance.</p>
        </div>
      </div>
      <dl className="coverage-summary__metrics">
        <div><dt>ACTIVE</dt><dd>{activeCount}</dd><span>of {targetCount} target</span></div>
        <div><dt>PUBLIC LAKE</dt><dd>{universe.publicLakeCount ?? "N/A"}</dd><span>local observations</span></div>
        <div><dt>HARD CAP</dt><dd>{universe.maximumCount ?? "N/A"}</dd><span>governed ceiling</span></div>
      </dl>
      <UniverseCoverageRail slots={slots} />
      <div className="coverage-summary__callout">
        <span>{attentionCount === 0 ? "NO COVERAGE INCIDENTS" : "OPERATOR REVIEW"}</span>
        <p>{attentionCount === 0
          ? "No stale, degraded, missing, or failed symbols are reported in the active universe."
          : `${staleCount} stale or degraded and ${missingCount} missing or failed symbols are surfaced in Market Tissue.`}</p>
      </div>
    </div>
  );
};

const coverageAlphabetGroup = (symbol: UniverseSymbol): string => {
  const initial = symbol.symbol.trim().slice(0, 1).toUpperCase();
  if (initial >= "A" && initial <= "F") {
    return "a-f";
  }
  if (initial >= "G" && initial <= "L") {
    return "g-l";
  }
  if (initial >= "M" && initial <= "R") {
    return "m-r";
  }
  return "s-z";
};

const universeCoverageGroups = (symbols: readonly UniverseSymbol[]): readonly UniverseCoverageGroup[] => {
  const definitions = [
    { id: "a-f", label: "A-F" },
    { id: "g-l", label: "G-L" },
    { id: "m-r", label: "M-R" },
    { id: "s-z", label: "S-Z" },
  ] as const;
  return definitions.map((definition) => ({
    ...definition,
    symbols: symbols.filter((symbol) => coverageAlphabetGroup(symbol) === definition.id),
  }));
};

export const UniverseCoverageExplorer = ({ universe }: { readonly universe: UniverseState }) => {
  const slots = universeCoverageSlots(universe);
  const activeCount = universe.activeCount ?? universe.symbols.length;
  const targetCount = universe.targetCount ?? slots.length;
  const issues = slots.filter((slot) => slot.status !== "observed");
  const groups = universeCoverageGroups(universe.symbols);
  const tierCounts = Object.entries(universe.tierCounts).sort((left, right) => right[1] - left[1]);

  return (
    <div className="coverage-explorer">
      <div className="coverage-explorer__readout">
        <div><span>ACTIVE / TARGET</span><strong>{formatRatio(activeCount, targetCount)}</strong></div>
        <div><span>PUBLIC LAKE</span><strong>{universe.publicLakeCount ?? "N/A"}</strong></div>
        <div><span>HARD CAP</span><strong>{universe.maximumCount ?? "N/A"}</strong></div>
      </div>
      <UniverseCoverageRail slots={slots} />
      <div className="coverage-explorer__insight">
        <div className={`coverage-explorer__signal${issues.length === 0 ? " is-clear" : " is-attention"}`}>
          <span>{issues.length === 0 ? "COVERAGE CLEAR" : "ISSUE-FIRST QUEUE"}</span>
          <strong>{issues.length === 0 ? "No degraded symbols" : `${issues.length} require review`}</strong>
          <p>{issues.length === 0
            ? "Every active symbol reports an observed coverage state."
            : issues.slice(0, 6).map((slot) => `${slot.label} / ${slot.status.toUpperCase()}`).join(" / ")}</p>
        </div>
        <div className="coverage-explorer__tiers">
          <span>TIER DISTRIBUTION</span>
          {tierCounts.length === 0 ? (
            <div className="coverage-explorer__tier-empty"><strong>NOT REPORTED</strong><small>No taxonomy inferred.</small></div>
          ) : tierCounts.slice(0, 5).map(([tier, count]) => (
            <div key={tier}>
              <strong>{displayLabel(tier)}</strong>
              <i><b style={{ width: `${universeCoveragePercent(count, activeCount)}%` }} /></i>
              <span>{count}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="coverage-register" aria-label="Universe symbols grouped alphabetically">
        {groups.map((group) => (
          <details className="coverage-register__group" key={group.id}>
            <summary>
              <span>{group.label}</span>
              <strong>{group.symbols.length} SYMBOLS</strong>
              <small>{group.symbols.slice(0, 6).map((symbol) => symbol.symbol).join(" / ")}</small>
              <i aria-hidden="true" />
            </summary>
            <div className="coverage-register__symbols">
              {group.symbols.map((symbol) => {
                const status = tissueStatus(symbol.status, true);
                return (
                  <span className={`coverage-register__symbol coverage-register__symbol--${status}`} key={symbol.symbol}>
                    <strong>{symbol.symbol}</strong>
                    <small>{symbol.tier === null ? "NO TIER" : displayLabel(symbol.tier)}</small>
                    <em>{status.toUpperCase()}</em>
                  </span>
                );
              })}
            </div>
          </details>
        ))}
      </div>
      <p className="coverage-explorer__boundary">COVERAGE HEALTH ONLY / NEVER PRICE PERFORMANCE</p>
    </div>
  );
};

interface TruthRailProps {
  readonly closed: number | null;
  readonly closedTarget: number | null;
  readonly resolved: number | null;
  readonly resolvedTarget: number | null;
  readonly status: string | null;
}

const ratioWidth = (value: number | null, target: number | null): string => {
  if (value === null || target === null || target <= 0) {
    return "0%";
  }
  return `${Math.max(0, Math.min(100, (value / target) * 100))}%`;
};

export const TruthRail = ({ closed, closedTarget, resolved, resolvedTarget, status }: TruthRailProps) => (
  <div className="truth-rail">
    <div className="truth-rail__status">
      <span>READINESS STATE</span>
      <strong>{displayLabel(status)}</strong>
    </div>
    <div className="truth-stage">
      <div className="truth-stage__copy">
        <span>FORWARD PAPER OUTCOMES</span>
        <strong>{formatRatio(closed, closedTarget)}</strong>
      </div>
      <div className="truth-stage__track"><i style={{ width: ratioWidth(closed, closedTarget) }} /></div>
    </div>
    <div className="truth-stage">
      <div className="truth-stage__copy">
        <span>RESOLVED DECISIONS</span>
        <strong>{formatRatio(resolved, resolvedTarget)}</strong>
      </div>
      <div className="truth-stage__track"><i style={{ width: ratioWidth(resolved, resolvedTarget) }} /></div>
    </div>
  </div>
);

export const Worldline = ({ regimes }: { readonly regimes: readonly WorldRegime[] }) => {
  if (regimes.length === 0) {
    return <EmptyState detail="The current state source did not emit world-model regime bands." label="WORLD MODEL / NOT REPORTED" />;
  }
  return (
    <div className="worldline">
      {regimes.map((regime) => {
        const probability = normalizedPercent(regime.probability);
        const uncertainty = normalizedPercent(regime.uncertainty);
        return (
          <div className="worldline__band" key={regime.dimension}>
            <span className="worldline__dimension">{displayLabel(regime.dimension)}</span>
            <span className="worldline__state">{displayLabel(regime.state)}</span>
            <span className="worldline__track" aria-label={`${regime.dimension} probability`}>
              <i style={{ width: `${(probability ?? 0) * 100}%` }} />
              {uncertainty === null ? null : <b style={{ left: `${(1 - uncertainty) * 100}%` }} />}
            </span>
            <strong>{probability === null ? "—" : `${Math.round(probability * 100)}%`}</strong>
          </div>
        );
      })}
    </div>
  );
};

export const OrganismSpine = ({ agents }: { readonly agents: readonly ObservatoryDatum[] }) => {
  if (agents.length === 0) {
    return <EmptyState detail="No active agent records are present in the observatory dataset." label="ORGANISM / QUIET" />;
  }
  return (
    <ol className="organism-spine">
      {agents.slice(0, 8).map((agent, index) => (
        <li key={agent.id}>
          <span className="organism-spine__node">{String(index + 1).padStart(2, "0")}</span>
          <div>
            <strong>{agent.title}</strong>
            <span>{displayLabel(agent.status)}</span>
          </div>
          <p>{agent.detail ?? "No role detail reported."}</p>
        </li>
      ))}
    </ol>
  );
};

export const ConfidenceDecomposition = ({ dimensions }: { readonly dimensions: readonly ConfidenceDimension[] }) => {
  if (dimensions.length === 0) {
    return <EmptyState detail="Confidence dimensions are absent; no aggregate confidence is inferred." label="CALIBRATION / NOT REPORTED" />;
  }
  return (
    <div className="confidence-stack">
      {dimensions.map((dimension) => {
        const percent = normalizedPercent(dimension.value);
        return (
          <div className="confidence-row" key={dimension.name}>
            <span>{displayLabel(dimension.name)}</span>
            <div className="confidence-row__ticks">
              {Array.from({ length: 10 }, (_, index) => (
                <i className={percent !== null && index < Math.round(percent * 10) ? "is-filled" : ""} key={index} />
              ))}
            </div>
            <strong>{percent === null ? "—" : percent.toFixed(2)}</strong>
          </div>
        );
      })}
    </div>
  );
};

export const ScheduleLanes = ({ lanes }: { readonly lanes: readonly ScheduleLane[] }) => {
  if (lanes.length === 0) {
    return <EmptyState detail="Scheduler state includes no lanes." label="SCHEDULE / NOT REPORTED" />;
  }
  return (
    <div className="schedule-lanes">
      {lanes.slice(0, 7).map((lane) => (
        <div className="schedule-lane" key={lane.id}>
          <span className={`schedule-lane__signal${lane.due === true ? " is-due" : ""}`} aria-hidden="true" />
          <div>
            <strong>{lane.description}</strong>
            <span>{lane.id.toUpperCase()}</span>
          </div>
          <span className="schedule-lane__evidence">{displayLabel(lane.evidenceStatus)}</span>
          <time>{formatTimestamp(lane.lastSuccessUtc)}</time>
        </div>
      ))}
    </div>
  );
};

export const SourceFreshness = ({ sources }: { readonly sources: readonly SourceState[] }) => {
  if (sources.length === 0) {
    return <EmptyState detail="No source health records are present. Data-dependent controls remain unverified." label="SOURCES / NOT REPORTED" />;
  }
  return (
    <div className="source-list">
      {sources.slice(0, 7).map((source) => (
        <div
          className={`source-row source-row--${source.severity}`}
          key={source.id}
          title={source.detail ?? `${source.name}: ${displayLabel(source.status)}`}
        >
          <span aria-hidden="true" className={`source-row__mark source-row__mark--${source.severity}`} />
          <strong>{source.name}</strong>
          <span>{displayLabel(source.status)}{source.freshness === null ? "" : ` / ${source.freshness}`}</span>
          <div className="source-row__timestamps">
            <time dateTime={source.observedUtc ?? ""} title={source.observedUtc ?? "Source observed_at not reported"}>
              OBS {formatTimestamp(source.observedUtc)}
            </time>
            <time dateTime={source.fileModifiedUtc ?? ""} title={source.fileModifiedUtc ?? "Source file_modified_utc not reported"}>
              FILE {formatTimestamp(source.fileModifiedUtc)}
            </time>
          </div>
        </div>
      ))}
    </div>
  );
};
