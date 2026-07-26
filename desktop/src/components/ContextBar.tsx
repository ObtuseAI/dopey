import { displayLabel, formatTimestamp } from "../state";
import type { DopeySnapshot } from "../types";

export interface ContextBarProps {
  readonly snapshot: DopeySnapshot;
  readonly staleSourceCount: number;
  readonly evidenceHash: string | null;
  readonly density: "dense" | "comfortable";
  readonly textScale: "100" | "115" | "130";
  readonly highContrast: boolean;
  readonly onCycleDensity: () => void;
  readonly onCycleTextScale: () => void;
  readonly onToggleContrast: () => void;
}

export const ContextBar = ({
  snapshot,
  staleSourceCount,
  evidenceHash,
  density,
  textScale,
  highContrast,
  onCycleDensity,
  onCycleTextScale,
  onToggleContrast,
}: ContextBarProps) => (
  <div className="global-context-bar" aria-label="Global analytical context">
    <div><span>UNIVERSE</span><strong>{snapshot.universe.activeCount ?? "—"} / {snapshot.universe.targetCount ?? "—"}</strong></div>
    <div><span>TIMEFRAME</span><strong>MULTI-HORIZON</strong></div>
    <div><span>AS OF</span><strong>{formatTimestamp(snapshot.generatedUtc)}</strong></div>
    <div><span>EVIDENCE CLASS</span><strong>{displayLabel(snapshot.analytics.evidence.evidenceClass)}</strong></div>
    <div><span>FRESHNESS</span><strong>{staleSourceCount === 0 ? "ALL REPORTED CLEAR" : `${staleSourceCount} NEED REVIEW`}</strong></div>
    <div><span>RUN HASH</span><strong title={evidenceHash ?? "Hash unavailable"}>{evidenceHash?.slice(0, 12) ?? "UNAVAILABLE"}</strong></div>
    <div className="appearance-controls" aria-label="Display preferences" role="group">
      <button aria-pressed={density === "comfortable"} onClick={onCycleDensity} type="button">{density === "dense" ? "COMFORT" : "DENSE"}</button>
      <button aria-label="Cycle text size" onClick={onCycleTextScale} type="button">TEXT {textScale}%</button>
      <button aria-pressed={highContrast} onClick={onToggleContrast} type="button">CONTRAST</button>
    </div>
  </div>
);
