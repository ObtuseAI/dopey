import { useEffect, useMemo, useState } from "react";
import { readSymbolLabState } from "../bridge";
import { directionTone } from "../lib/tone";
import { displayLabel } from "../state";
import { normalizeSymbolLab } from "../symbolLabState";
import type {
  SymbolLabExpression,
  SymbolLabPayload,
  SymbolLabScenarioPoint,
  SymbolLabStrategyMode,
  UniverseSymbol,
} from "../types";

const strategyModes: readonly { readonly id: SymbolLabStrategyMode; readonly label: string }[] = [
  { id: "auto", label: "AUTO ROUTER" },
  { id: "trend", label: "TREND" },
  { id: "momentum", label: "MOMENTUM" },
  { id: "breakout", label: "BREAKOUT" },
  { id: "mean_reversion", label: "MEAN REVERSION" },
  { id: "volatility", label: "VOLATILITY" },
  { id: "bullish_scenario", label: "BULL SCENARIO" },
  { id: "bearish_scenario", label: "BEAR SCENARIO" },
];

const fixed = (value: number | null, digits: number): string => value === null ? "--" : value.toFixed(digits);
const percent = (value: number | null, digits: number): string => value === null ? "--" : `${(value * 100).toFixed(digits)}%`;
const signedPercent = (value: number): string => `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
const strikeLabel = (expression: SymbolLabExpression): string => expression.strike !== null
  ? expression.strike.toFixed(2)
  : `${fixed(expression.longStrike, 2)} / ${fixed(expression.shortStrike, 2)}`;

const ExpressionLedger = ({ expressions, bestId }: {
  readonly expressions: readonly SymbolLabExpression[];
  readonly bestId: string | null;
}) => (
  <div className="lab-expression-ledger">
    <div className="lab-expression-row lab-expression-row--header">
      <span>EXPRESSION</span><span>EXP / DTE</span><span>STRIKE</span><span>IV / SPREAD</span><span>SCENARIO VALUE</span><span>P/L</span><span>FIT</span>
    </div>
    {expressions.slice(0, 14).map((expression) => (
      <div className={`lab-expression-row${expression.expressionId === bestId ? " is-best" : ""}`} key={expression.expressionId}>
        <span><strong>{displayLabel(expression.expressionType)}</strong><small>{expression.activePolicyEligible ? "CANON ELIGIBLE" : "RESEARCH STRUCTURE"}</small></span>
        <span>{expression.expiry}<small>{expression.dte} DTE</small></span>
        <span>{strikeLabel(expression)}<small>MAX LOSS {fixed(expression.maximumLoss, 2)}</small></span>
        <span>{percent(expression.impliedVol, 1)}<small>SPR {percent(expression.spreadPct, 1)}</small></span>
        <span>{fixed(expression.scenarioModelValue, 2)}<small>DELTA {fixed(expression.delta, 3)}</small></span>
        <span className={`lab-tone--${expression.projectedPnl >= 0 ? "positive" : "negative"}`}>{fixed(expression.projectedPnl, 2)}<small>{signedPercent(expression.projectedReturn)}</small></span>
        <span>{Math.round(expression.valueScore * 100)}<small>LIQ {expression.liquidityScore === null ? "--" : Math.round(expression.liquidityScore * 100)}</small></span>
      </div>
    ))}
  </div>
);

const ScenarioMatrix = ({ points }: { readonly points: readonly SymbolLabScenarioPoint[] }) => {
  const prices = [...new Set(points.map((point) => point.stockPrice))].sort((left, right) => left - right);
  const elapsed = [...new Set(points.map((point) => point.elapsedDays))].sort((left, right) => left - right);
  const lookup = new Map(points.map((point) => [`${point.stockPrice}|${point.elapsedDays}`, point]));
  return (
    <div className="lab-scenario-matrix" style={{ gridTemplateColumns: `88px repeat(${elapsed.length}, minmax(76px, 1fr))` }}>
      <span className="lab-scenario-corner">STOCK / TIME</span>
      {elapsed.map((days) => <strong key={days}>T+{days}D</strong>)}
      {prices.map((price) => (
        <div className="lab-scenario-row" key={price} style={{ gridColumn: `1 / span ${elapsed.length + 1}` }}>
          <b>{price.toFixed(2)}</b>
          {elapsed.map((days) => {
            const point = lookup.get(`${price}|${days}`);
            return <span key={days}>{point === undefined ? "--" : point.theoreticalValue.toFixed(2)}<small>{point === undefined ? "" : `${point.remainingDte} DTE`}</small></span>;
          })}
        </div>
      ))}
    </div>
  );
};

export const SymbolLabView = ({ symbols }: { readonly symbols: readonly UniverseSymbol[] }) => {
  const symbolNames = useMemo(() => symbols.map((item) => item.symbol).filter((symbol) => symbol.length > 0), [symbols]);
  const initialSymbol = symbolNames.includes("SPY") ? "SPY" : symbolNames[0] ?? "SPY";
  const [symbol, setSymbol] = useState(initialSymbol);
  const [symbolDraft, setSymbolDraft] = useState(initialSymbol);
  const [strategyMode, setStrategyMode] = useState<SymbolLabStrategyMode>("auto");
  const [scenarioPrice, setScenarioPrice] = useState<number | null>(null);
  const [daysForward, setDaysForward] = useState(14);
  const [ivShift, setIvShift] = useState(0);
  const [payload, setPayload] = useState<SymbolLabPayload | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void readSymbolLabState(symbol, strategyMode, scenarioPrice, daysForward, ivShift)
      .then(normalizeSymbolLab)
      .then((result) => {
        if (active) {
          setPayload(result);
          setScenarioPrice(result.request.scenarioPriceEffective);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Symbol laboratory request failed.");
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
  }, [symbol, requestVersion]);

  const runProjection = (): void => {
    const normalized = symbolDraft.trim().toUpperCase();
    if (!symbolNames.includes(normalized)) {
      setError(`SYMBOL ${normalized || "<EMPTY>"} IS NOT IN THE GOVERNED ACTIVE UNIVERSE.`);
      return;
    }
    if (scenarioPrice !== null && scenarioPrice <= 0) {
      setError("SCENARIO STOCK PRICE MUST BE POSITIVE.");
      return;
    }
    setSymbolDraft(normalized);
    if (normalized !== symbol) {
      setSymbol(normalized);
      setScenarioPrice(null);
      return;
    }
    setRequestVersion((value) => value + 1);
  };

  const currentPrice = payload?.marketProfile.currentPrice ?? 100;
  const minimumPrice = Math.max(0.01, currentPrice * 0.65);
  const maximumPrice = currentPrice * 1.35;
  const bestId = payload?.bestExpression?.expressionId ?? null;

  return (
    <div className="symbol-lab-view">
      <header className="symbol-lab-command">
        <div className="symbol-lab-command__title">
          <span className="eyebrow">04 / SYMBOL-SPECIFIC RESEARCH ORGANISM</span>
          <h1>Options value & meta-plan laboratory</h1>
          <p>Change stock price, time, volatility, and strategy. DOPEY reranks observed contracts and research structures without pretending model values are future quotes.</p>
        </div>
        <label><span>SYMBOL</span><input list="lab-symbols" onChange={(event) => setSymbolDraft(event.target.value.toUpperCase())} value={symbolDraft} /><datalist id="lab-symbols">{symbolNames.map((item) => <option key={item} value={item} />)}</datalist></label>
        <label><span>RESEARCH STRATEGY</span><select onChange={(event) => setStrategyMode(event.target.value as SymbolLabStrategyMode)} value={strategyMode}>{strategyModes.map((mode) => <option key={mode.id} value={mode.id}>{mode.label}</option>)}</select></label>
        <button disabled={loading} onClick={runProjection} type="button">{loading ? "RECONSTRUCTING" : "RUN LAB"}</button>
      </header>

      {error === null ? null : <div className="lab-error" role="alert">{error}</div>}
      {payload === null ? <div className="lab-loading">ASSEMBLING HASH-PINNED SYMBOL DOSSIER...</div> : (
        <>
          <section className="lab-telemetry-spine">
            <div><span>SPOT</span><strong>{payload.marketProfile.currentPrice.toFixed(2)}</strong><small>{payload.symbol} / {payload.asOf}</small></div>
            <div><span>STRUCTURE</span><strong className={`lab-tone--${directionTone(payload.marketProfile.timeframeDirection)}`}>{displayLabel(payload.marketProfile.timeframeDirection)}</strong><small>{Math.round(payload.marketProfile.timeframeAgreement * 100)}% AGREEMENT</small></div>
            <div><span>SUPPORT</span><strong>{fixed(payload.marketProfile.nearestSupport?.zoneMid ?? null, 2)}</strong><small>{payload.marketProfile.nearestSupport?.timeframes.join(" / ").toUpperCase() || "UNRESOLVED"}</small></div>
            <div><span>RESISTANCE</span><strong>{fixed(payload.marketProfile.nearestResistance?.zoneMid ?? null, 2)}</strong><small>{payload.marketProfile.nearestResistance?.timeframes.join(" / ").toUpperCase() || "UNRESOLVED"}</small></div>
            <div><span>EARNINGS</span><strong>{payload.marketProfile.earningsDate ?? "NONE STAGED"}</strong><small>{payload.marketProfile.daysUntilEarnings === null ? displayLabel(payload.marketProfile.earningsStatus) : `${payload.marketProfile.daysUntilEarnings} CALENDAR DAYS`}</small></div>
            <div><span>OPTION TISSUE</span><strong>{payload.marketProfile.contractCount.toLocaleString()}</strong><small>{payload.marketProfile.expiryCount} EXPIRIES / {payload.marketProfile.chainSnapshotDate ?? "NO SNAPSHOT"}</small></div>
          </section>

          <section className="lab-workbench">
            <article className="lab-scenario-controls">
              <header><span>V-90</span><strong>VALUE PROJECTOR</strong><b>{displayLabel(payload.projectorStatus)}</b></header>
              <label><span>SCENARIO STOCK PRICE</span><input min={minimumPrice} max={maximumPrice} onChange={(event) => setScenarioPrice(Number(event.target.value))} step="0.01" type="range" value={scenarioPrice ?? currentPrice} /><b>{fixed(scenarioPrice, 2)}</b></label>
              <label><span>TIME FORWARD</span><input min="0" max="90" onChange={(event) => setDaysForward(Number(event.target.value))} step="1" type="range" value={daysForward} /><b>T+{daysForward}D</b></label>
              <label><span>IMPLIED VOLATILITY SHIFT</span><input min="-0.50" max="0.50" onChange={(event) => setIvShift(Number(event.target.value))} step="0.01" type="range" value={ivShift} /><b>{ivShift >= 0 ? "+" : ""}{Math.round(ivShift * 100)} VOL</b></label>
              <button disabled={loading} onClick={runProjection} type="button">REPRICE & RERANK</button>
              <div className="lab-control-proof"><span>SELECTED DIRECTION</span><strong className={`lab-tone--${directionTone(payload.selectedDirection)}`}>{displayLabel(payload.selectedDirection)}</strong><small>{displayLabel(payload.directionSource)}</small></div>
              <div className="lab-control-proof"><span>CHAIN MICROSTRUCTURE</span><strong>SPREAD {percent(payload.marketProfile.medianSpreadPct, 1)}</strong><small>PUT/CALL OI {fixed(payload.marketProfile.putCallOiRatio, 2)} / SKEW {percent(payload.marketProfile.nearAtmSkew, 1)}</small></div>
            </article>

            <article className="lab-best-expression">
              <header><span>X-91</span><strong>HIGHEST SCENARIO-FIT EXPRESSION</strong><b>NOT A TRADE ORDER</b></header>
              {payload.bestExpression === null ? <p>NO OBSERVED CONTRACT CLEARED DTE, LIQUIDITY, SPREAD, AND STRATEGY-FIT FILTERS.</p> : (
                <div className="lab-best-core">
                  <span>{displayLabel(payload.bestExpression.expressionType)}</span>
                  <strong>{strikeLabel(payload.bestExpression)}</strong>
                  <em>{payload.bestExpression.expiry} / {payload.bestExpression.dte} DTE</em>
                  <div><b>{fixed(payload.bestExpression.scenarioModelValue, 2)}</b><small>SCENARIO MODEL VALUE</small></div>
                  <div><b className={`lab-tone--${payload.bestExpression.projectedPnl >= 0 ? "positive" : "negative"}`}>{fixed(payload.bestExpression.projectedPnl, 2)}</b><small>PROJECTED P/L PER SHARE</small></div>
                  <div><b>{Math.round(payload.bestExpression.valueScore * 100)}</b><small>SCENARIO-FIT SCORE</small></div>
                  <p>Observed quotes anchor the entry. Exit value is theoretical and friction-adjusted. American exercise, discrete dividends, and future liquidity remain explicit model risks.</p>
                </div>
              )}
            </article>

            <article className="lab-surface-panel">
              <header><span>S-92</span><strong>PRICE x TIME VALUE SURFACE</strong><b>{payload.scenarioSurface.length} NODES</b></header>
              <ScenarioMatrix points={payload.scenarioSurface} />
            </article>
          </section>

          <section className="lab-expression-panel">
            <header><span>R-93</span><strong>CONTRACT & DEFINED-RISK EXPRESSION RANKING</strong><b>{payload.eligibleContractCount} ELIGIBLE CONTRACTS</b></header>
            <ExpressionLedger bestId={bestId} expressions={payload.expressions} />
          </section>

          <section className="lab-lower-grid">
            <article className="lab-strategy-panel">
              <header><span>E-94</span><strong>SYMBOL-SPECIFIC COMBINATION TESTS</strong><b>{payload.strategies.length} RECIPES</b></header>
              <div className="lab-strategy-ledger">
                {payload.strategies.slice(0, 10).map((strategy) => (
                  <div className={strategy.currentSignalActive ? "is-active" : ""} key={strategy.strategyId}>
                    <span>{displayLabel(strategy.family)} / {displayLabel(strategy.direction)}</span>
                    <strong>{displayLabel(strategy.strategyId)}</strong>
                    <p>{strategy.thesis}</p>
                    <b>{Math.round(strategy.robustnessScore * 100)}</b>
                    <small>N {strategy.sampleCount} // HIT {percent(strategy.hitRate, 0)} // FOLDS {percent(strategy.positiveFoldRate, 0)} // ADJ {signedPercent(strategy.selectionAdjustedMean)}</small>
                    <em>{displayLabel(strategy.evidenceStatus)}</em>
                  </div>
                ))}
              </div>
            </article>
            <article className="lab-plan-panel">
              <header><span>M-95</span><strong>CUSTOM META-PLANS</strong><b>{payload.plans.length} PATHS</b></header>
              <div className="lab-plan-stack">
                {payload.plans.map((plan) => (
                  <div key={plan.planId}>
                    <span>{displayLabel(plan.family)}</span><strong>{displayLabel(plan.planId)}</strong><em className={`lab-tone--${directionTone(plan.direction)}`}>{displayLabel(plan.direction)}</em>
                    <p>{displayLabel(plan.trigger)}</p>
                    <small>INVALIDATE {fixed(plan.invalidationPrice, 2)} // TARGET {fixed(plan.scenarioTargetPrice, 2)} // CAP {percent(plan.confidenceCap, 0)}</small>
                    <b>{displayLabel(plan.status)}</b>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <footer className="lab-boundary">
            <span>{payload.indicatorCount} INDICATORS</span><span>{payload.divergenceCount} DIVERGENCES</span><span>{payload.activeStrategyIds.length} CURRENT RECIPE SIGNALS</span><span>HASH {payload.contentHash.slice(0, 14)}</span>
            <strong>{payload.paperOnly && payload.liveBlocked && !payload.syntheticDataUsed ? "REAL LOCAL EVIDENCE // PAPER-ONLY // LIVE-BLOCKED" : "BOUNDARY FAULT"}</strong>
          </footer>
        </>
      )}
    </div>
  );
};
