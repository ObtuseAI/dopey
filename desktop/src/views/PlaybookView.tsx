import { useEffect, useMemo, useState } from "react";
import { statusTone } from "../lib/tone";
import { formatTimestamp } from "../state";
import type {
  PlaybookListId,
  PlaybookRecommendation,
  PlaybookScoreBreakdown,
  PlaybookState,
} from "../types";

type DirectionalListId = Exclude<PlaybookListId, "overall">;

interface ListDefinition {
  readonly id: DirectionalListId;
  readonly title: string;
  readonly horizon: string;
  readonly bias: "bullish" | "bearish";
}

const LIST_DEFINITIONS: readonly ListDefinition[] = [
  { id: "short_term_bullish", title: "Short-term bullish prediction research", horizon: "1-10 trading sessions", bias: "bullish" },
  { id: "short_term_bearish", title: "Short-term bearish prediction research", horizon: "1-10 trading sessions", bias: "bearish" },
  { id: "long_term_bullish", title: "Long-term bullish prediction research", horizon: "20+ trading sessions", bias: "bullish" },
  { id: "long_term_bearish", title: "Long-term bearish prediction research", horizon: "20+ trading sessions", bias: "bearish" },
] as const;

const SCORE_FIELDS: readonly [keyof PlaybookScoreBreakdown, string][] = [
  ["withinSetupSignal", "Within-setup signal"],
  ["independentFamilyAgreement", "Independent family agreement"],
  ["forwardTrust", "Forward trust"],
  ["directionNeutralAttention", "Direction-neutral attention"],
  ["liquidity", "Liquidity"],
  ["universeSelection", "Universe selection"],
  ["swingDirectionalSupport", "Swing directional support"],
  ["valuationFit", "Horizon-aware valuation fit"],
  ["oppositionPenalty", "Opposition penalty"],
] as const;

const displayToken = (value: string | null): string =>
  value === null ? "NOT REPORTED" : value.replaceAll("_", " ").toUpperCase();

const formatScore = (value: number | null): string => value === null ? "--" : value.toFixed(1);

const boundedScore = (value: number | null): number => Math.max(0, Math.min(value ?? 0, 100));

const formatCount = (value: number | null): string => value === null ? "--" : Math.round(value).toLocaleString("en-US");

const formatMoney = (value: number | null): string => {
  if (value === null) {
    return "NOT REPORTED";
  }
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
    style: "currency",
    currency: "USD",
  }).format(value);
};

const formatEvidenceValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "NOT REPORTED";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(formatEvidenceValue).join(", ");
  }
  return JSON.stringify(value);
};

const recommendationRows = (
  playbook: PlaybookState,
  listId: PlaybookListId,
): readonly PlaybookRecommendation[] =>
  playbook.lists[listId]
    .map((recommendationId) => playbook.recommendations[recommendationId])
    .filter((recommendation): recommendation is PlaybookRecommendation => recommendation !== undefined);

const playbookTone = (status: string): "nominal" | "warning" | "critical" => {
  const tone = statusTone(status);
  return tone === "unknown" ? "critical" : tone;
};

const PredictionRow = ({
  recommendation,
  selected,
  onSelect,
}: {
  readonly recommendation: PlaybookRecommendation;
  readonly selected: boolean;
  readonly onSelect: (recommendationId: string) => void;
}) => (
  <button
    aria-label={`Open ${recommendation.symbol} ${recommendation.directionalBias} prediction research breakdown`}
    aria-pressed={selected}
    className={`playbook-row playbook-tone--${recommendation.directionalBias}`}
    onClick={() => onSelect(recommendation.recommendationId)}
    type="button"
  >
    <span className="playbook-row__rank">{String(recommendation.rank ?? 0).padStart(2, "0")}</span>
    <span className="playbook-row__identity">
      <strong>{recommendation.symbol}</strong>
      <small>{displayToken(recommendation.recommendationState)}</small>
    </span>
    <span className="playbook-row__signal">
      <strong>{formatScore(recommendation.researchPriorityScore)}</strong>
      <small>PRIORITY</small>
    </span>
    <span aria-hidden="true" className="playbook-row__arrow">-&gt;</span>
  </button>
);

const PredictionBoard = ({
  definition,
  rows,
  missingSlots,
  selectedId,
  onSelect,
}: {
  readonly definition: ListDefinition;
  readonly rows: readonly PlaybookRecommendation[];
  readonly missingSlots: number | null;
  readonly selectedId: string | null;
  readonly onSelect: (recommendationId: string) => void;
}) => (
  <section className={`playbook-board playbook-tone--${definition.bias}`} aria-labelledby={`playbook-list-${definition.id}`}>
    <header>
      <div>
        <span>{definition.bias.toUpperCase()} / RESEARCH RECOMMENDATIONS</span>
        <h2 id={`playbook-list-${definition.id}`}>{definition.title}</h2>
      </div>
      <strong>{rows.length}<small>/10</small></strong>
    </header>
    <div className="playbook-board__horizon">
      <span>{definition.horizon}</span>
      <span>{missingSlots === null || missingSlots === 0 ? "RANKED WITHOUT PADDING" : `${missingSlots} SLOT${missingSlots === 1 ? "" : "S"} UNFILLED`}</span>
    </div>
    <div className="playbook-board__rows">
      {rows.map((recommendation) => (
        <PredictionRow
          key={recommendation.recommendationId}
          onSelect={onSelect}
          recommendation={recommendation}
          selected={selectedId === recommendation.recommendationId}
        />
      ))}
      {rows.length === 0 ? (
        <div className="playbook-board__empty">
          <strong>NO ELIGIBLE PREDICTIONS</strong>
          <span>The governed sources did not support a ranked research candidate in this lane.</span>
        </div>
      ) : null}
    </div>
  </section>
);

const OverallCard = ({
  recommendation,
  index,
  selected,
  onSelect,
}: {
  readonly recommendation: PlaybookRecommendation;
  readonly index: number;
  readonly selected: boolean;
  readonly onSelect: (recommendationId: string) => void;
}) => (
  <button
    aria-label={`Open top overall play ${index + 1}, ${recommendation.symbol} ${recommendation.directionalBias} prediction research`}
    aria-pressed={selected}
    className={`playbook-overall-card playbook-tone--${recommendation.directionalBias}`}
    onClick={() => onSelect(recommendation.recommendationId)}
    type="button"
  >
    <span className="playbook-overall-card__rank">#{index + 1}</span>
    <span className="playbook-overall-card__bias">{recommendation.directionalBias.toUpperCase()}</span>
    <strong>{recommendation.symbol}</strong>
    <span>{displayToken(recommendation.category)}</span>
    <footer>
      <b>{formatScore(recommendation.researchPriorityScore)}</b>
      <small>RESEARCH PRIORITY / 100</small>
    </footer>
  </button>
);

const EvidenceList = ({
  title,
  items,
  emptyLabel,
}: {
  readonly title: string;
  readonly items: readonly string[];
  readonly emptyLabel: string;
}) => (
  <section className="playbook-inspector__section">
    <h3>{title}</h3>
    {items.length === 0 ? <p className="playbook-inspector__empty">{emptyLabel}</p> : (
      <ul>
        {items.map((item, index) => <li key={`${title}-${index}-${item}`}>{item}</li>)}
      </ul>
    )}
  </section>
);

const ScoreBreakdown = ({ breakdown }: { readonly breakdown: PlaybookScoreBreakdown }) => (
  <section className="playbook-inspector__section">
    <h3>Research-priority decomposition</h3>
    <div className="playbook-score-grid">
      {SCORE_FIELDS.map(([field, label]) => {
        const value = breakdown[field];
        const penalty = field === "oppositionPenalty";
        return (
          <div className={penalty ? "is-penalty" : ""} key={field}>
            <span>{label}</span>
            <strong>{formatScore(value)}</strong>
            <i aria-hidden="true"><b style={{ width: `${boundedScore(value)}%` }} /></i>
          </div>
        );
      })}
    </div>
  </section>
);

const StructuredEvidence = ({
  title,
  evidence,
}: {
  readonly title: string;
  readonly evidence: Readonly<Record<string, unknown>>;
}) => {
  const entries = Object.entries(evidence);
  return (
    <section className="playbook-inspector__section">
      <h3>{title}</h3>
      {entries.length === 0 ? <p className="playbook-inspector__empty">NO GOVERNED EVIDENCE REPORTED</p> : (
        <dl className="playbook-evidence-map">
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt>{displayToken(key)}</dt>
              <dd title={formatEvidenceValue(value)}>{formatEvidenceValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
};

const PredictionInspector = ({ recommendation }: { readonly recommendation: PlaybookRecommendation | null }) => {
  if (recommendation === null) {
    return (
      <aside className="playbook-inspector playbook-inspector--empty" aria-label="Prediction research breakdown">
        <span>BREAKDOWN / UNAVAILABLE</span>
        <h2>No ranked prediction selected</h2>
        <p>The current artifact did not expose an eligible research recommendation. No list is padded with unsupported symbols.</p>
      </aside>
    );
  }
  const attentionPercent = recommendation.attentionContext.completenessRatio === null
    ? null
    : recommendation.attentionContext.completenessRatio * 100;
  return (
    <aside className={`playbook-inspector playbook-tone--${recommendation.directionalBias}`} aria-label={`${recommendation.symbol} prediction research breakdown`}>
      <header className="playbook-inspector__header">
        <div>
          <span>SELECTED PREDICTION RESEARCH</span>
          <h2>{recommendation.symbol}</h2>
          <p>{displayToken(recommendation.category)} / {recommendation.horizonLabel ?? displayToken(recommendation.horizon)}</p>
        </div>
        <div className="playbook-inspector__priority">
          <strong>{formatScore(recommendation.researchPriorityScore)}</strong>
          <span>PRIORITY / 100</span>
          <small>NOT A PROBABILITY</small>
        </div>
      </header>

      <div className="playbook-inspector__status">
        <span>{recommendation.directionalBias.toUpperCase()} PREDICTION</span>
        <span>{displayToken(recommendation.confidenceLabel)}</span>
        <span>{displayToken(recommendation.recommendationState)}</span>
      </div>

      <section className="playbook-inspector__thesis">
        <span>RESEARCH THESIS</span>
        <p>{recommendation.thesisSummary ?? "No thesis summary was reported."}</p>
        <small>Variant wedge: {displayToken(recommendation.variantWedge)}</small>
      </section>

      <div className="playbook-inspector__facts">
        <div><span>MARKET DATA AS OF</span><strong>{recommendation.marketDataAsOf ?? "NOT REPORTED"}</strong></div>
        <div><span>RESEARCH TIER</span><strong>{displayToken(recommendation.tradability.tier)}</strong></div>
        <div><span>20D DOLLAR VOLUME</span><strong>{formatMoney(recommendation.tradability.averageDollarVolume20d)}</strong></div>
        <div><span>INVALIDATION PRICE</span><strong>{recommendation.researchInvalidationPrice === null ? "NOT REPORTED" : `$${recommendation.researchInvalidationPrice.toFixed(2)}`}</strong></div>
      </div>

      <EvidenceList emptyLabel="NO CURRENT WHY-NOW EVIDENCE" items={recommendation.whyNow} title="Why it is ranked now" />

      <section className="playbook-inspector__section">
        <h3>Observed catalysts</h3>
        {recommendation.catalysts.length === 0 ? <p className="playbook-inspector__empty">NO GOVERNED CATALYST REPORTED</p> : (
          <div className="playbook-catalyst-ledger">
            {recommendation.catalysts.map((catalyst, index) => (
              <div key={`${catalyst.catalystType}-${catalyst.date ?? index}`}>
                <strong>{displayToken(catalyst.catalystType)}</strong>
                <time dateTime={catalyst.date ?? ""}>{catalyst.date ?? "DATE NOT REPORTED"}</time>
                <span>{displayToken(catalyst.status)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="playbook-inspector__section playbook-inspector__rejection">
        <h3>First rejection / disconfirming test</h3>
        <p>{recommendation.firstRejection ?? "No rejection test was reported."}</p>
      </section>

      <ScoreBreakdown breakdown={recommendation.scoreBreakdown} />

      <section className="playbook-inspector__section">
        <h3>Direction-neutral attention context</h3>
        <div className="playbook-attention">
          <div><span>ATTENTION SCORE</span><strong>{formatScore(recommendation.attentionContext.score)}</strong></div>
          <div><span>COMPLETENESS</span><strong>{formatScore(attentionPercent)}%</strong></div>
          <div><span>FRESHNESS</span><strong>{displayToken(recommendation.attentionContext.freshnessStatus)}</strong></div>
        </div>
        <p className="playbook-attention__law">Attention changes research priority only. It never creates bullish or bearish direction.</p>
        {recommendation.attentionContext.drivers.length === 0 ? null : (
          <div className="playbook-chip-row">
            {recommendation.attentionContext.drivers.map((driver) => <span key={driver}>{displayToken(driver)}</span>)}
          </div>
        )}
      </section>

      <section className="playbook-inspector__section">
        <h3>Tradability and universe evidence</h3>
        <p>Research tradable: {recommendation.tradability.researchTradable === true ? "YES" : recommendation.tradability.researchTradable === false ? "NO" : "NOT REPORTED"}; market cap: {formatMoney(recommendation.tradability.marketCap)}; universe score: {formatScore(recommendation.tradability.selectionScore)}.</p>
        {recommendation.tradability.reasonCodes.length === 0 ? null : (
          <div className="playbook-chip-row">
            {recommendation.tradability.reasonCodes.map((reason) => <span key={reason}>{displayToken(reason)}</span>)}
          </div>
        )}
      </section>

      <section className="playbook-inspector__section">
        <h3>Setup and forward-trust evidence</h3>
        {recommendation.setupEvidence.length === 0 ? <p className="playbook-inspector__empty">NO SETUP EVIDENCE REPORTED</p> : (
          <div className="playbook-setup-ledger">
            {recommendation.setupEvidence.map((setup) => {
              const trust = recommendation.trustEvidence.find((row) => row.setupId === setup.setupId);
              return (
                <div key={setup.detectionId}>
                  <span>{displayToken(setup.family)}</span>
                  <strong>{displayToken(setup.setupId)}</strong>
                  <b>{formatScore(setup.withinSetupPercentile)} PCTL</b>
                  <small>{trust === undefined ? "TRUST UNREPORTED" : `${displayToken(trust.trustState)} / ${formatCount(trust.settled)} SETTLED`}</small>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <StructuredEvidence evidence={recommendation.technicalEvidence} title="Technical evidence" />
      <StructuredEvidence evidence={recommendation.fundamentalEvidence} title="Fundamental evidence" />
      <StructuredEvidence evidence={recommendation.valuationContext} title="Valuation gate and context" />
      <StructuredEvidence evidence={recommendation.competingContext} title="Competing context" />

      <EvidenceList emptyLabel="NO INVESTABILITY REQUIREMENTS REPORTED" items={recommendation.whatWouldMakeInvestable} title="What would make it investable" />
      <EvidenceList emptyLabel="NO KILL CONDITIONS REPORTED" items={recommendation.whatWouldKillIt} title="What would kill the thesis" />
      <EvidenceList emptyLabel="NO RISK RECORDS REPORTED" items={recommendation.risks} title="Risks and limitations" />
      <EvidenceList emptyLabel="NO MISSING-EVIDENCE RECORDS" items={recommendation.missingEvidence} title="Missing evidence" />

      {recommendation.directionalBias === "bearish" ? (
        <section className="playbook-inspector__section playbook-inspector__bearish-law">
          <h3>Bearish expression boundary</h3>
          <p>{recommendation.bearishExpressionPolicy ?? "Directional research only; no short-stock order is created."}</p>
        </section>
      ) : null}

      <footer className="playbook-inspector__footer">
        <span>{displayToken(recommendation.executionState)}</span>
        <strong>NO ORDER CONSTRUCTION / NO TRADE PROMOTION</strong>
      </footer>
    </aside>
  );
};

export const PlaybookView = ({ playbook }: { readonly playbook: PlaybookState }) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const overallRows = useMemo(() => recommendationRows(playbook, "overall"), [playbook]);
  const fallbackId = overallRows[0]?.recommendationId ??
    LIST_DEFINITIONS.map((definition) => playbook.lists[definition.id][0]).find((value) => value !== undefined) ??
    null;
  const effectiveId = selectedId !== null && playbook.recommendations[selectedId] !== undefined
    ? selectedId
    : fallbackId;
  const selected = effectiveId === null ? null : playbook.recommendations[effectiveId] ?? null;

  useEffect(() => {
    if (selectedId !== null && playbook.recommendations[selectedId] === undefined) {
      setSelectedId(null);
    }
  }, [playbook.recommendations, selectedId]);

  return (
    <div className="playbook-view">
      <header className="playbook-hero">
        <div className="playbook-hero__index">PB</div>
        <div className="playbook-hero__copy">
          <span>DOPEY / MULTI-HORIZON PREDICTION RESEARCH</span>
          <h1>Bullish &amp; bearish playbook</h1>
          <p>Ranked research recommendations across short and long horizons, with direction sourced from independent price/setup evidence.</p>
        </div>
        <div className={`playbook-hero__status playbook-status--${playbookTone(playbook.status)}`}>
          <i aria-hidden="true" />
          <span>{displayToken(playbook.status)}</span>
        </div>
      </header>

      <section className="playbook-provenance" aria-label="Playbook freshness and provenance">
        <div><span>RANKINGS GENERATED</span><strong>{formatTimestamp(playbook.generatedUtc)}</strong></div>
        <div><span>MARKET DATA AS OF</span><strong>{playbook.marketDataAsOf ?? "NOT REPORTED"}</strong></div>
        <div><span>ATTENTION AS OF</span><strong>{playbook.attentionAsOf ?? "NOT REPORTED"}</strong></div>
        <div><span>NEXT REFRESH DUE</span><strong>{formatTimestamp(playbook.nextRefreshDueUtc)}</strong></div>
        <div><span>EVOLVING UNIVERSE</span><strong>{formatCount(playbook.universeActiveCount)} / {formatCount(playbook.universeMaximumCount)}</strong></div>
        <div><span>ELIGIBLE STOCKS</span><strong>{formatCount(playbook.eligibleSingleStockCount)}</strong></div>
      </section>

      <div className="playbook-boundary" role="note">
        <strong>RESEARCH-RANKED PREDICTIONS</strong>
        <span>These are evidence-prioritized research recommendations, not execution instructions. Priority scores are not return probabilities.</span>
        <b>ATTENTION IS DIRECTION-NEUTRAL</b>
      </div>

      <section className="playbook-overall" aria-labelledby="playbook-overall-title">
        <header>
          <div>
            <span>PORTFOLIO RESEARCH QUEUE</span>
            <h2 id="playbook-overall-title">Top 5 overall prediction research plays</h2>
          </div>
          <strong>{overallRows.length}<small>/5</small></strong>
        </header>
        {overallRows.length === 0 ? (
          <div className="playbook-overall__empty">
            <strong>NO OVERALL RESEARCH PLAYS AVAILABLE</strong>
            <span>The engine does not pad the list when source gates or eligible predictions are insufficient.</span>
          </div>
        ) : (
          <div className="playbook-overall__cards">
            {overallRows.map((recommendation, index) => (
              <OverallCard
                index={index}
                key={recommendation.recommendationId}
                onSelect={setSelectedId}
                recommendation={recommendation}
                selected={effectiveId === recommendation.recommendationId}
              />
            ))}
          </div>
        )}
      </section>

      <div className="playbook-workspace">
        <div className="playbook-boards">
          {LIST_DEFINITIONS.map((definition) => (
            <PredictionBoard
              definition={definition}
              key={definition.id}
              missingSlots={playbook.missingSlotsByList[definition.id]}
              onSelect={setSelectedId}
              rows={recommendationRows(playbook, definition.id)}
              selectedId={effectiveId}
            />
          ))}
        </div>
        <PredictionInspector recommendation={selected} />
      </div>

      <section className="playbook-method">
        <div>
          <span>DIRECTION SOURCE</span>
          <strong>{displayToken(playbook.rankingMethod.directionSource)}</strong>
        </div>
        <div>
          <span>STRENGTH NORMALIZATION</span>
          <strong>{displayToken(playbook.rankingMethod.strengthNormalization)}</strong>
        </div>
        <div>
          <span>LONG-TERM TRUST</span>
          <strong>{playbook.rankingMethod.longTermTrustIndependentlySettled === true ? "INDEPENDENTLY SETTLED" : "NOT INDEPENDENTLY SETTLED"}</strong>
        </div>
        <div>
          <span>CONTENT HASH</span>
          <strong title={playbook.contentHash ?? "Not reported"}>{playbook.contentHash?.slice(0, 16) ?? "NOT REPORTED"}</strong>
        </div>
        <div>
          <span>SOURCE ARTIFACTS</span>
          <strong>{playbook.sourceArtifacts.length} HASHED INPUTS</strong>
        </div>
      </section>

      <span aria-live="polite" className="sr-only">
        {selected === null ? "No playbook prediction selected" : `${selected.symbol} ${selected.directionalBias} prediction research breakdown selected`}
      </span>
    </div>
  );
};
