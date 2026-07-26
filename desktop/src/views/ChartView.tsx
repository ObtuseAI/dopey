import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { readChartCoachState, readChartState } from "../bridge";
import { normalizeChartPayload } from "../chartState";
import { directionTone } from "../lib/tone";
import { displayLabel } from "../state";
import { normalizeTwoCoachReview } from "../twoCoachState";
import type {
  ChartBar,
  ChartPayload,
  ChartPattern,
  ChartTimeframe,
  HeadCoachId,
  RegimeHistoryPoint,
  TwoCoachReview,
  UniverseSymbol,
  WorldRegime,
} from "../types";

const timeframeOptions: readonly ChartTimeframe[] = ["daily", "weekly", "monthly"];

const overlayDefinitions = [
  { id: "sma20", label: "SMA 20", color: "#84a98c" },
  { id: "sma50", label: "SMA 50", color: "#d1a85a" },
  { id: "ema20", label: "EMA 20", color: "#d7ded5" },
  { id: "anchored_vwap", label: "YEAR AVWAP", color: "#e87967" },
  { id: "bollinger_upper", label: "BB UPPER", color: "#59645d" },
  { id: "bollinger_lower", label: "BB LOWER", color: "#59645d" },
] as const;

type OverlayId = (typeof overlayDefinitions)[number]["id"];
type OverlayVisibility = Readonly<Record<OverlayId, boolean>>;
type ChartDisplayMode = "chart" | "table";

const initialVisibility: OverlayVisibility = {
  sma20: true,
  sma50: true,
  ema20: false,
  anchored_vwap: true,
  bollinger_upper: false,
  bollinger_lower: false,
};

const fixed = (value: number | null, digits: number): string =>
  value === null ? "—" : value.toFixed(digits);

const probability = (value: number | null): string =>
  value === null ? "UNRATED" : `${Math.round(value * 100)}%`;

const linePoints = (
  series: readonly (number | null)[],
  xAt: (index: number) => number,
  yAt: (value: number) => number,
): string => series
  .map((value, index) => value === null ? null : `${xAt(index).toFixed(2)},${yAt(value).toFixed(2)}`)
  .filter((point): point is string => point !== null)
  .join(" ");

const ChartMarker = ({ pattern, bars, xAt, yAt }: {
  readonly pattern: ChartPattern;
  readonly bars: readonly ChartBar[];
  readonly xAt: (index: number) => number;
  readonly yAt: (value: number) => number;
}) => {
  const index = pattern.asOf === null ? -1 : bars.findIndex((bar) => bar.date === pattern.asOf);
  const bar = bars[index];
  if (index < 0 || bar === undefined) {
    return null;
  }
  const y = yAt(bar.close);
  const bias = directionTone(pattern.directionalBias);
  return (
    <g className={`chart-marker chart-marker--${bias}`}>
      <circle cx={xAt(index)} cy={y} r="4.5" />
      <line x1={xAt(index)} x2={xAt(index)} y1={y - 7} y2={y - 18} />
      <text x={xAt(index)} y={y - 22}>{pattern.pattern.replaceAll("_", " ").slice(0, 18)}</text>
    </g>
  );
};

const CandlestickField = ({ chart, visibility }: {
  readonly chart: ChartPayload;
  readonly visibility: OverlayVisibility;
}) => {
  const width = 1000;
  const left = 52;
  const right = 74;
  const priceTop = 18;
  const priceBottom = 356;
  const volumeTop = 370;
  const volumeBottom = 438;
  const plotWidth = width - left - right;
  const visibleOverlayValues = overlayDefinitions
    .filter((definition) => visibility[definition.id])
    .flatMap((definition) => chart.overlays[definition.id] ?? [])
    .filter((value): value is number => value !== null);
  const extrema = [
    ...chart.bars.flatMap((bar) => [bar.high, bar.low]),
    ...visibleOverlayValues,
  ];
  const minimum = Math.min(...extrema);
  const maximum = Math.max(...extrema);
  const priceSpan = Math.max(maximum - minimum, maximum * 0.01, 1e-9);
  const paddedMinimum = minimum - priceSpan * 0.04;
  const paddedMaximum = maximum + priceSpan * 0.04;
  const paddedSpan = paddedMaximum - paddedMinimum;
  const xAt = (index: number): number => left + ((index + 0.5) / chart.bars.length) * plotWidth;
  const yAt = (value: number): number => priceTop + (paddedMaximum - value) / paddedSpan * (priceBottom - priceTop);
  const maximumVolume = Math.max(...chart.bars.map((bar) => bar.volume), 1);
  const candleWidth = Math.max(1.5, Math.min(7, plotWidth / chart.bars.length * 0.64));
  const markerPatterns = chart.patterns.filter((pattern) => pattern.asOf !== null).slice(0, 9);
  const firstDate = chart.bars[0]?.date ?? "";
  const lastDate = chart.bars.at(-1)?.date ?? "";
  return (
    <svg aria-label={`${chart.symbol} ${chart.timeframe} candlestick chart`} className="candlestick-field" role="img" viewBox="0 0 1000 455">
      <rect className="chart-field__background" height="455" width="1000" x="0" y="0" />
      {Array.from({ length: 6 }, (_, index) => {
        const ratio = index / 5;
        const y = priceTop + ratio * (priceBottom - priceTop);
        const price = paddedMaximum - ratio * paddedSpan;
        return (
          <g className="chart-gridline" key={index}>
            <line x1={left} x2={width - right} y1={y} y2={y} />
            <text x={width - right + 9} y={y + 3}>{price.toFixed(2)}</text>
          </g>
        );
      })}
      <line className="chart-axis" x1={left} x2={width - right} y1={priceBottom} y2={priceBottom} />
      {chart.bars.map((bar, index) => {
        const bullish = bar.close >= bar.open;
        const bodyTop = yAt(Math.max(bar.open, bar.close));
        const bodyBottom = yAt(Math.min(bar.open, bar.close));
        const bodyHeight = Math.max(1.2, bodyBottom - bodyTop);
        const volumeHeight = bar.volume / maximumVolume * (volumeBottom - volumeTop);
        return (
          <g className={bullish ? "candle candle--up" : "candle candle--down"} key={bar.date}>
            <title>{`${bar.date}  O ${bar.open.toFixed(2)}  H ${bar.high.toFixed(2)}  L ${bar.low.toFixed(2)}  C ${bar.close.toFixed(2)}  V ${Math.round(bar.volume).toLocaleString()}`}</title>
            <line x1={xAt(index)} x2={xAt(index)} y1={yAt(bar.high)} y2={yAt(bar.low)} />
            <rect height={bodyHeight} width={candleWidth} x={xAt(index) - candleWidth / 2} y={bodyTop} />
            <rect className="candle__volume" height={volumeHeight} width={Math.max(1, candleWidth)} x={xAt(index) - candleWidth / 2} y={volumeBottom - volumeHeight} />
          </g>
        );
      })}
      {overlayDefinitions.map((definition) => visibility[definition.id] ? (
        <polyline
          className={`chart-overlay chart-overlay--${definition.id}`}
          key={definition.id}
          points={linePoints(chart.overlays[definition.id] ?? [], xAt, yAt)}
          style={{ stroke: definition.color }}
        />
      ) : null)}
      {markerPatterns.map((pattern) => <ChartMarker bars={chart.bars} key={pattern.id} pattern={pattern} xAt={xAt} yAt={yAt} />)}
      <g className="chart-date-axis">
        <text x={left} y="451">{firstDate}</text>
        <text textAnchor="end" x={width - right} y="451">{lastDate}</text>
      </g>
    </svg>
  );
};

const OscillatorField = ({ chart }: { readonly chart: ChartPayload }) => {
  const rsi = chart.oscillators.rsi ?? [];
  const macd = chart.oscillators.macd_histogram ?? [];
  const left = 46;
  const width = 960;
  const plotWidth = width - left - 28;
  const xAt = (index: number): number => left + ((index + 0.5) / chart.bars.length) * plotWidth;
  const rsiY = (value: number): number => 8 + (100 - value) / 100 * 74;
  const macdFinite = macd.filter((value): value is number => value !== null);
  const macdRange = Math.max(...macdFinite.map(Math.abs), 1e-9);
  const zero = 120;
  return (
    <svg aria-label="RSI and MACD evidence strip" className="oscillator-field" role="img" viewBox="0 0 960 166">
      <line className="oscillator-threshold" x1={left} x2={width - 28} y1={rsiY(70)} y2={rsiY(70)} />
      <line className="oscillator-threshold" x1={left} x2={width - 28} y1={rsiY(30)} y2={rsiY(30)} />
      <polyline className="oscillator-rsi" points={linePoints(rsi, xAt, rsiY)} />
      <line className="oscillator-zero" x1={left} x2={width - 28} y1={zero} y2={zero} />
      {macd.map((value, index) => value === null ? null : (
        <rect
          className={value >= 0 ? "macd-bar macd-bar--up" : "macd-bar macd-bar--down"}
          height={Math.max(1, Math.abs(value) / macdRange * 34)}
          key={chart.bars[index]?.date ?? index}
          width={Math.max(1, plotWidth / chart.bars.length * 0.66)}
          x={xAt(index) - Math.max(1, plotWidth / chart.bars.length * 0.66) / 2}
          y={value >= 0 ? zero - Math.abs(value) / macdRange * 34 : zero}
        />
      ))}
      <text className="oscillator-label" x="8" y="20">RSI</text>
      <text className="oscillator-label" x="8" y="124">MACD</text>
    </svg>
  );
};

const PatternLedger = ({ patterns }: { readonly patterns: readonly ChartPattern[] }) => (
  <div className="pattern-ledger">
    {patterns.length === 0 ? (
      <div className="chart-empty">NO CURRENT FORMATION CLEARED THE DETERMINISTIC THRESHOLDS</div>
    ) : patterns.slice(0, 18).map((pattern, index) => (
      <div className={`pattern-record pattern-record--${directionTone(pattern.directionalBias)}${pattern.divergenceType?.startsWith("hidden") === true ? " pattern-record--hidden" : ""}`} key={pattern.id}>
        <span>{String(index + 1).padStart(2, "0")}</span>
        <div>
          <strong>{displayLabel(pattern.pattern)}</strong>
          <small>{displayLabel(pattern.oscillator ?? pattern.family)} // {pattern.asOf ?? "CURRENT WINDOW"}</small>
        </div>
        <b>{probability(pattern.probability)}</b>
        <em>{displayLabel(pattern.directionalBias)}</em>
        <p title={pattern.failureCondition ?? "No failure condition reported."}>{pattern.failureCondition ?? "No failure condition reported."}</p>
      </div>
    ))}
  </div>
);

const IndicatorMatrix = ({ chart }: { readonly chart: ChartPayload }) => {
  const priority = new Set(["RSI", "MACD_HISTOGRAM", "ADX", "CHOPPINESS_INDEX", "RELATIVE_VIGOR_INDEX", "SCHAFF_TREND_CYCLE", "CHAIKIN_OSCILLATOR", "VWMA_DISTANCE", "PARABOLIC_SAR_DISTANCE", "MASS_INDEX", "NORMALIZED_ATR", "MONEY_FLOW_INDEX"]);
  const ordered = [...chart.indicators].sort((left, right) => Number(priority.has(right.indicator)) - Number(priority.has(left.indicator)) || left.indicator.localeCompare(right.indicator));
  return (
    <div className="indicator-matrix">
      {ordered.slice(0, 24).map((indicator) => (
        <div className="indicator-cell" key={indicator.indicator}>
          <span>{displayLabel(indicator.indicator)}</span>
          <strong>{fixed(indicator.value, 3)}</strong>
          <small>{displayLabel(indicator.state)}</small>
          <i><b style={{ width: `${Math.round((indicator.percentile ?? 0) * 100)}%` }} /></i>
        </div>
      ))}
    </div>
  );
};

const GroundedStructureLedger = ({ chart }: { readonly chart: ChartPayload }) => {
  const facts = new Map(chart.numericFacts.map((fact) => [fact.levelRef, fact]));
  return (
    <div className="grounded-structure-ledger">
      {chart.groundedStructures.slice(-18).reverse().map((structure) => (
        <article className={`grounded-structure grounded-structure--${directionTone(structure.directionalBias)}`} key={structure.structureId}>
          <header>
            <span>{displayLabel(structure.structureType)}</span>
            <strong>{displayLabel(structure.directionalBias)}</strong>
          </header>
          <small>{displayLabel(structure.definitionId)} // AVAILABLE {structure.availableAt}</small>
          <div>
            {structure.levelRefs.map((reference) => {
              const fact = facts.get(reference);
              return fact === undefined ? (
                <em key={reference}>UNRESOLVED LEVEL</em>
              ) : (
                <em key={reference} title={fact.derivation}>{displayLabel(fact.label)} <b>{fact.canonicalDisplay}</b></em>
              );
            })}
          </div>
        </article>
      ))}
    </div>
  );
};

const AnalysisList = ({ values, empty }: { readonly values: readonly string[]; readonly empty: string }) => (
  values.length === 0
    ? <p className="coach-empty">{empty}</p>
    : <ul>{values.map((value, index) => <li key={`${index}:${value}`}>{value}</li>)}</ul>
);

const TwoCoachWorkspace = ({ review, loading, error, headCoach, onHeadCoach, onRun }: {
  readonly review: TwoCoachReview | null;
  readonly loading: boolean;
  readonly error: string | null;
  readonly headCoach: HeadCoachId;
  readonly onHeadCoach: (value: HeadCoachId) => void;
  readonly onRun: () => void;
}) => (
  <section className="two-coach-workspace" aria-labelledby="two-coach-title">
    <header>
      <div>
        <span>COACHING / GROUNDING CONTRACT</span>
        <h2 id="two-coach-title">Evidence coach + head coach</h2>
        <p>Raw OHLC owns every level. The selected head coach can interpret registered facts, but cannot author prices, orders, or promotion.</p>
      </div>
      <label>
        <span>HEAD COACH</span>
        <select disabled={loading} onChange={(event) => onHeadCoach(event.target.value as HeadCoachId)} value={headCoach}>
          <option value="claude">CLAUDE / OPENROUTER HYBRID</option>
          <option value="codex">CODEX / READ-ONLY</option>
        </select>
      </label>
      <button disabled={loading} onClick={onRun} type="button">{loading ? "COACHING..." : "RUN TWO-COACH REVIEW"}</button>
    </header>
    {error === null ? null : <div className="coach-error" role="alert">{error}</div>}
    {review === null ? (
      <div className="two-coach-empty">
        <strong>DETERMINISTIC COACH READY</strong>
        <span>Run an explicit review to send the frozen evidence packet to {headCoach.toUpperCase()}. No provider fallback is allowed.</span>
      </div>
    ) : (
      <>
        <div className="coach-proof-strip">
          <div><span>VERDICT</span><strong>{displayLabel(review.verdict)}</strong></div>
          <div><span>HEAD COACH</span><strong>{review.headCoachId.toUpperCase()}</strong><small>{review.headCoachModel}</small></div>
          <div><span>GROUNDING</span><strong>{displayLabel(review.numericGroundingStatus)}</strong><small>{review.referenceCount} RESOLVED REFS</small></div>
          <div><span>EVIDENCE</span><strong>{review.structureCount} STRUCTURES</strong><small>{review.numericFactCount} FACTS / {review.lessonCount} LESSONS</small></div>
          <div><span>OPENROUTER</span><strong>{review.reportedCostUsd === null ? "NOT REPORTED" : `$${review.reportedCostUsd.toFixed(4)}`}</strong><small>{review.paidResponseCount} PAID RESPONSES</small></div>
        </div>
        <div className="coach-grid">
          <article className="coach-card coach-card--evidence">
            <header><span>COACH ONE</span><strong>Deterministic Evidence / Replay</strong></header>
            <p>Viewport and pixels excluded. Blind replay blocks lookahead. Prior lessons use validated closed outcomes only.</p>
            <dl><div><dt>STRUCTURES</dt><dd>{review.structureCount}</dd></div><div><dt>FACTS</dt><dd>{review.numericFactCount}</dd></div><div><dt>LESSONS</dt><dd>{review.lessonCount}</dd></div></dl>
            <small>{displayLabel(review.optionClaimStatus)}</small>
          </article>
          <article className="coach-card coach-card--head">
            <header><span>HEAD COACH</span><strong>{review.headCoachId.toUpperCase()} / {displayLabel(review.status)}</strong></header>
            <p>{review.analysis.summary}</p>
            <small>{review.routeId} // FALLBACK {review.runtimeFallbackUsed ? "USED" : "BLOCKED"}</small>
          </article>
          <article className="coach-card">
            <header><span>HYPOTHESES</span><strong>{review.analysis.hypotheses.length}</strong></header>
            <AnalysisList empty="No hypothesis survived the head-coach contract." values={review.analysis.hypotheses.map((item) => `${item.title} — ${item.mechanism} Falsify: ${item.falsification}`)} />
          </article>
          <article className="coach-card coach-card--risk">
            <header><span>SKEPTIC REGISTER</span><strong>{review.analysis.adversarialFindings.length}</strong></header>
            <AnalysisList empty="No adversarial finding was returned." values={review.analysis.adversarialFindings.map((item) => `${item.title} — ${item.risk} Need: ${item.evidenceNeeded}`)} />
          </article>
          <article className="coach-card">
            <header><span>UNCERTAINTIES</span><strong>{review.analysis.uncertainties.length}</strong></header>
            <AnalysisList empty="No uncertainty was reported." values={review.analysis.uncertainties} />
          </article>
          <article className="coach-card">
            <header><span>SAFE NEXT EXPERIMENTS</span><strong>{review.analysis.recommendedExperiments.length}</strong></header>
            <AnalysisList empty="The head coach recommended no new experiment." values={review.analysis.recommendedExperiments.map((item) => `${item.title} — ${item.objective} Safety: ${item.safetyConstraints}`)} />
          </article>
        </div>
        <footer>
          <span>{review.sessionHash.slice(0, 20)}</span>
          <strong>{review.researchOnly && review.paperOnly && review.liveBlocked && !review.brokerAccess && !review.orderAuthority ? "RESEARCH-ONLY // NO ORDER AUTHORITY" : "COACH BOUNDARY FAULT"}</strong>
        </footer>
      </>
    )}
  </section>
);

const ChartDataTable = ({ chart }: { readonly chart: ChartPayload }) => (
  <div className="chart-data-table-wrap">
    <table className="chart-data-table">
      <caption>{chart.symbol} {chart.timeframe} OHLCV evidence</caption>
      <thead><tr><th scope="col">Date</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Volume</th></tr></thead>
      <tbody>{chart.bars.slice(-160).map((bar) => <tr key={bar.date}><th scope="row">{bar.date}</th><td>{fixed(bar.open, 2)}</td><td>{fixed(bar.high, 2)}</td><td>{fixed(bar.low, 2)}</td><td>{fixed(bar.close, 2)}</td><td>{Math.round(bar.volume).toLocaleString("en-US")}</td></tr>)}</tbody>
    </table>
  </div>
);

interface ChartViewProps {
  readonly symbols: readonly UniverseSymbol[];
  readonly regimes: readonly WorldRegime[];
  readonly regimeHistory: readonly RegimeHistoryPoint[];
}

const ChartContextRibbon = ({ regimes, history }: { readonly regimes: readonly WorldRegime[]; readonly history: readonly RegimeHistoryPoint[] }) => (
  <section className="chart-context-ribbon" aria-label="Current regime annotations and source history">
    <header><span>R-80 / CURRENT REGIME ANNOTATION</span><strong>As-of context — not a historical transition inference</strong><em>{history.length} SOURCE SNAPSHOTS INDEXED</em></header>
    <div>{regimes.map((regime) => <button aria-label={`${regime.dimension}, ${regime.state}, probability ${regime.probability ?? "unknown"}, uncertainty ${regime.uncertainty ?? "unknown"}`} key={regime.dimension} title={`${regime.dimension}\n${regime.state}\nP ${regime.probability ?? "—"}\nU ${regime.uncertainty ?? "—"}`} type="button"><span>{regime.dimension.replaceAll("_", " ")}</span><strong>{regime.state.replaceAll("_", " ")}</strong><i style={{ width: `${Math.max(4, Math.min((regime.probability ?? 0) * 100, 100))}%` }} /></button>)}</div>
  </section>
);

export const ChartView = ({ symbols, regimes, regimeHistory }: ChartViewProps) => {
  const symbolNames = useMemo(() => symbols.map((item) => item.symbol).filter((symbol) => symbol.length > 0), [symbols]);
  const initialSymbol = symbolNames.includes("SPY") ? "SPY" : symbolNames[0] ?? "SPY";
  const [symbol, setSymbol] = useState(initialSymbol);
  const [symbolDraft, setSymbolDraft] = useState(initialSymbol);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("daily");
  const [chart, setChart] = useState<ChartPayload | null>(null);
  const [visibility, setVisibility] = useState<OverlayVisibility>(initialVisibility);
  const [displayMode, setDisplayMode] = useState<ChartDisplayMode>("chart");
  const [copyStatus, setCopyStatus] = useState("COPY HASH");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [headCoach, setHeadCoach] = useState<HeadCoachId>("claude");
  const [coachReview, setCoachReview] = useState<TwoCoachReview | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachError, setCoachError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setCoachReview(null);
    setCoachError(null);
    void readChartState(symbol, timeframe)
      .then(normalizeChartPayload)
      .then((payload) => {
        if (active) {
          setChart(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setChart(null);
          setError(reason instanceof Error ? reason.message : "Chart evidence request failed.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [symbol, timeframe]);

  const applySymbol = (): void => {
    const normalized = symbolDraft.trim().toUpperCase();
    if (!symbolNames.includes(normalized)) {
      setError(`SYMBOL ${normalized || "<EMPTY>"} IS NOT IN THE GOVERNED ACTIVE UNIVERSE.`);
      return;
    }
    setSymbolDraft(normalized);
    setSymbol(normalized);
  };

  const copyContentHash = async (contentHash: string): Promise<void> => {
    if (navigator.clipboard === undefined) {
      setError("SYSTEM CLIPBOARD IS UNAVAILABLE IN THIS DESKTOP RENDERER.");
      return;
    }
    try {
      await navigator.clipboard.writeText(contentHash);
      setCopyStatus("HASH COPIED");
      window.setTimeout(() => setCopyStatus("COPY HASH"), 1800);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? `HASH COPY FAILED: ${reason.message}` : "HASH COPY FAILED WITHOUT AN ERROR MESSAGE.");
    }
  };

  const runCoachReview = (): void => {
    setCoachLoading(true);
    setCoachError(null);
    void readChartCoachState(symbol, timeframe, headCoach)
      .then(normalizeTwoCoachReview)
      .then(setCoachReview)
      .catch((reason: unknown) => {
        setCoachReview(null);
        setCoachError(reason instanceof Error ? reason.message : "Two-coach review failed closed.");
      })
      .finally(() => setCoachLoading(false));
  };

  const selectHeadCoach = (value: HeadCoachId): void => {
    setHeadCoach(value);
    setCoachReview(null);
    setCoachError(null);
  };

  return (
    <div className="chart-view">
      <header className="chart-command">
        <div>
          <span className="eyebrow">03 / TECHNICAL EVIDENCE LAB</span>
          <h1>Candlestick intelligence</h1>
          <p>Price geometry, participation, hidden divergence, and 62 versioned primitives. Evidence—not an order signal.</p>
        </div>
        <div className="chart-symbol-control">
          <label htmlFor="chart-symbol">INSTRUMENT</label>
          <input
            id="chart-symbol"
            list="chart-symbols"
            onChange={(event) => setSymbolDraft(event.target.value.toUpperCase())}
            onKeyDown={(event) => event.key === "Enter" ? applySymbol() : undefined}
            spellCheck={false}
            value={symbolDraft}
          />
          <datalist id="chart-symbols">{symbolNames.map((item) => <option key={item} value={item} />)}</datalist>
          <button onClick={applySymbol} type="button">LOAD</button>
        </div>
        <div className="chart-timeframes" role="group" aria-label="Chart timeframe">
          {timeframeOptions.map((option) => (
            <button className={timeframe === option ? "is-active" : ""} key={option} onClick={() => setTimeframe(option)} type="button">{option.slice(0, 1).toUpperCase()}</button>
          ))}
        </div>
      </header>

      {error === null ? null : <div className="chart-error" role="alert">{error}</div>}
      {loading ? <div className="chart-loading"><i /> RECONSTRUCTING HASH-PINNED MARKET GEOMETRY</div> : null}
      {chart === null ? null : (
        <>
          <section className="chart-primary">
            <div className="chart-primary__header">
              <div><strong>{chart.symbol}</strong><span>{chart.timeframe.toUpperCase()} / {chart.asOf}</span></div>
              <div className="overlay-bank">
                {overlayDefinitions.map((definition) => (
                  <button
                    className={visibility[definition.id] ? "is-active" : ""}
                    key={definition.id}
                    onClick={() => setVisibility((current) => ({ ...current, [definition.id]: !current[definition.id] }))}
                    style={{ "--overlay-color": definition.color } as CSSProperties}
                    type="button"
                  >{definition.label}</button>
                ))}
              </div>
              <div className="chart-display-toggle" aria-label="Chart display mode" role="group"><button aria-pressed={displayMode === "chart"} onClick={() => setDisplayMode("chart")} type="button">CHART</button><button aria-pressed={displayMode === "table"} onClick={() => setDisplayMode("table")} type="button">DATA TABLE</button></div>
              <div className="chart-proof"><span>REAL / LOCAL / HASH-PINNED</span><b>{chart.contentHash.slice(0, 14)}</b><button onClick={() => void copyContentHash(chart.contentHash)} type="button">{copyStatus}</button></div>
            </div>
            {displayMode === "chart" ? <><CandlestickField chart={chart} visibility={visibility} /><OscillatorField chart={chart} /></> : <ChartDataTable chart={chart} />}
          </section>
          <ChartContextRibbon history={regimeHistory} regimes={regimes} />
          <section className="chart-intelligence-grid">
            <article className="chart-module chart-module--patterns">
              <header><span>P-81</span><strong>Formation & divergence register</strong><b>{chart.patterns.length} ACTIVE</b></header>
              <PatternLedger patterns={chart.patterns} />
            </article>
            <article className="chart-module chart-module--indicators">
              <header><span>I-82</span><strong>Indicator arsenal</strong><b>{chart.indicatorCount} VERSIONED</b></header>
              <IndicatorMatrix chart={chart} />
            </article>
            <article className="chart-module chart-module--grounded">
              <header><span>G-83</span><strong>Grounded structure registry</strong><b>{chart.groundedStructures.length} CANDIDATES</b></header>
              <GroundedStructureLedger chart={chart} />
            </article>
          </section>
          <TwoCoachWorkspace
            error={coachError}
            headCoach={headCoach}
            loading={coachLoading}
            onHeadCoach={selectHeadCoach}
            onRun={runCoachReview}
            review={coachReview}
          />
          <footer className="chart-boundary">
            <span>{chart.patternFamilyCount} PATTERN FAMILIES</span>
            <span>{chart.divergences.length} PIVOT-ALIGNED DIVERGENCES</span>
            <span>VIEWPORT INPUT {chart.viewportIsDetectorInput ? "FAULT" : "EXCLUDED"}</span>
            <span>BLIND REPLAY {displayLabel(chart.blindReplay.status)}</span>
            <strong>{chart.paperOnly && chart.liveBlocked ? "PAPER-ONLY // LIVE-BLOCKED" : "BOUNDARY FAULT"}</strong>
          </footer>
        </>
      )}
    </div>
  );
};
