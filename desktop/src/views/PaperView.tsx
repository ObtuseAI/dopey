import { EmptyState, InstrumentPanel } from "../components/Instruments";
import { PaperRiskCockpit } from "../components/AnalyticsVisuals";
import { PageHeader } from "../components/PageHeader";
import { displayLabel, formatTimestamp } from "../state";
import type { DopeySnapshot, PaperPosition } from "../types";

const PositionTable = ({ positions, emptyLabel }: { readonly positions: readonly PaperPosition[]; readonly emptyLabel: string }) => {
  if (positions.length === 0) {
    return <EmptyState detail="No position records were emitted in this category." label={emptyLabel} />;
  }
  return (
    <div className="position-table">
      {positions.map((position) => (
        <div className="position-row" key={position.id}>
          <strong>{position.symbol}</strong>
          <span>{displayLabel(position.structure)}</span>
          <span>{displayLabel(position.status)}</span>
          <b>{position.value === null ? "—" : position.value.toFixed(2)}</b>
          <time dateTime={position.closedUtc ?? position.openedUtc ?? ""}>{formatTimestamp(position.closedUtc ?? position.openedUtc)}</time>
        </div>
      ))}
    </div>
  );
};

export const PaperView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const book = snapshot.paperBook;
  return (
    <div className="secondary-view">
      <PageHeader index="09" thesis="Paper decisions and outcomes remain visibly separate from realized evidence and execution authority." timestamp={snapshot.generatedUtc} timestampText={formatTimestamp(snapshot.generatedUtc)} title="Paper book" />
      <div className="paper-grid">
        <InstrumentPanel className="paper-grid__ledger" code="P-61" meta="SIMULATED / NOT REALIZED" title="Book ledger">
          <div className="book-metrics">
            <BookMetric label="OPEN" value={book.openCount} />
            <BookMetric label="CLOSED" value={book.closedCount} />
            <BookMetric label="WINS" value={book.wins} />
            <BookMetric label="REALIZED PREMIUM UNITS" value={book.realizedPremiumUnits} />
            <BookMetric label="UNREALIZED PREMIUM UNITS" value={book.unrealizedPremiumUnits} />
          </div>
        </InstrumentPanel>
        <InstrumentPanel className="" code="P-62" meta={`${book.openPositions.length} RECORDS`} title="Open paper positions">
          <PositionTable emptyLabel="OPEN BOOK / EMPTY OR NOT REPORTED" positions={book.openPositions} />
        </InstrumentPanel>
        <InstrumentPanel className="" code="P-63" meta={`${book.closedPositions.length} RECORDS`} title="Settlement history">
          <PositionTable emptyLabel="SETTLEMENTS / NONE REPORTED" positions={book.closedPositions} />
        </InstrumentPanel>
      </div>
      <PaperRiskCockpit analytics={snapshot.analytics} />
    </div>
  );
};

const BookMetric = ({ label, value }: { readonly label: string; readonly value: number | null }) => (
  <div><span>{label}</span><strong>{value === null ? "—" : value.toFixed(Number.isInteger(value) ? 0 : 2)}</strong></div>
);
