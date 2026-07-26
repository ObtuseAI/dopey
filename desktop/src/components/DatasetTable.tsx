import { EmptyState } from "./Instruments";
import { statusTone } from "../lib/tone";
import { displayLabel } from "../state";
import type { ObservatoryDatum } from "../types";

export const DatasetTable = ({ rows, emptyLabel }: { readonly rows: readonly ObservatoryDatum[]; readonly emptyLabel: string }) => {
  if (rows.length === 0) {
    return <EmptyState detail="The connected observatory did not emit records for this surface." label={emptyLabel} />;
  }
  return (
    <div className="dataset-table">
      {rows.map((row, index) => (
        <div className="dataset-row" key={row.id}>
          <span className="dataset-row__index">{String(index + 1).padStart(2, "0")}</span>
          <div><strong>{row.title}</strong><p>{row.detail ?? "No descriptive field reported."}</p></div>
          <span className={`status-cell status-cell--${statusTone(row.status)}`}>{displayLabel(row.status)}</span>
          <b>{row.value ?? "—"}</b>
        </div>
      ))}
    </div>
  );
};
