import { InstrumentPanel, SourceFreshness, UniverseCoverageExplorer, Worldline } from "../components/Instruments";
import { OptionsIntelligence, RegimeIntelligence } from "../components/AnalyticsVisuals";
import { DatasetTable } from "../components/DatasetTable";
import { PageHeader } from "../components/PageHeader";
import { formatTimestamp } from "../state";
import type { DopeySnapshot, OptionExtreme, StockExtreme } from "../types";

const signedPercent = (value: number | null): string => {
  if (value === null) {
    return "—";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
};

const StockExtremeBoard = ({ rows, title }: { readonly rows: readonly StockExtreme[]; readonly title: string }) => (
  <section className="extreme-board">
    <header><span>{title}</span><b>{rows.length}</b></header>
    <div className="extreme-board__rows">
      {rows.slice(0, 6).map((row, index) => (
        <div className={`extreme-row extreme-row--${row.direction}`} key={`${row.direction}-${row.symbol}`}>
          <span>{String(row.rank ?? index + 1).padStart(2, "0")}</span>
          <strong>{row.symbol}</strong>
          <em>{signedPercent(row.returnPct)}</em>
          <small>RSI {row.rsi14 === null ? "—" : row.rsi14.toFixed(1)}</small>
        </div>
      ))}
      {rows.length === 0 ? <p className="extreme-board__empty">NO VERIFIED OBSERVATIONS</p> : null}
    </div>
  </section>
);

const OptionExtremeBoard = ({ rows, title }: { readonly rows: readonly OptionExtreme[]; readonly title: string }) => (
  <section className="extreme-board">
    <header><span>{title}</span><b>{rows.length}</b></header>
    <div className="extreme-board__rows">
      {rows.slice(0, 6).map((row, index) => (
        <div className={`extreme-row extreme-row--${row.tail}`} key={`${row.tail}-${row.contractKey}-${index}`}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{row.symbol}</strong>
          <em>{signedPercent(row.roiPct)}</em>
          <small title={row.contractKey}>{row.contractKey}</small>
        </div>
      ))}
      {rows.length === 0 ? <p className="extreme-board__empty">NO VERIFIED OBSERVATIONS</p> : null}
    </div>
  </section>
);

const ExtremesField = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => (
  <div className="extremes-field">
    <StockExtremeBoard rows={snapshot.extremes.gainers} title="STOCK GAINERS" />
    <StockExtremeBoard rows={snapshot.extremes.decliners} title="STOCK DECLINERS" />
    <OptionExtremeBoard rows={snapshot.extremes.optionWinners} title="OPTION WINNERS" />
    <OptionExtremeBoard rows={snapshot.extremes.optionLosers} title="OPTION LOSERS" />
  </div>
);

export const MarketView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => (
  <div className="secondary-view">
    <PageHeader index="02" thesis="Coverage, regime state, and source integrity—without implying directional performance." timestamp={snapshot.world.asOf} timestampText={formatTimestamp(snapshot.world.asOf)} title="Market tissue" />
    <div className="market-grid">
      <InstrumentPanel className="market-grid__extremes" code="M-20" meta="SIGNED / PAPER EVIDENCE" title="Four-tail discovery field">
        <ExtremesField snapshot={snapshot} />
      </InstrumentPanel>
      <InstrumentPanel className="market-grid__tissue instrument-panel--coverage-explorer" code="M-21" meta="ISSUE-FIRST REGISTER" title="Universe coverage explorer">
        <UniverseCoverageExplorer universe={snapshot.universe} />
      </InstrumentPanel>
      <InstrumentPanel className="market-grid__world" code="M-22" meta={`${snapshot.world.regimes.length} DIMENSIONS`} title="Regime worldline">
        <Worldline regimes={snapshot.world.regimes} />
      </InstrumentPanel>
      <InstrumentPanel className="market-grid__technical" code="M-23" meta="MULTI-TIMEFRAME" title="Technical field">
        <DatasetTable emptyLabel="TECHNICAL STATE / NOT REPORTED" rows={snapshot.observatory.technicalTimeframes} />
      </InstrumentPanel>
      <InstrumentPanel className="market-grid__sources" code="M-24" meta="PROVENANCE HEALTH" title="Source register">
        <SourceFreshness sources={snapshot.sources} />
      </InstrumentPanel>
    </div>
    <RegimeIntelligence analytics={snapshot.analytics} />
    <OptionsIntelligence analytics={snapshot.analytics} />
  </div>
);
