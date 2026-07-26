import { ConfidenceDecomposition, InstrumentPanel, OrganismSpine, ScheduleLanes, SourceFreshness, TruthRail, Worldline } from "../components/Instruments";
import { NeuralActivityField } from "../components/NeuralActivityField";
import { ResearchCoreControl } from "../components/ResearchCoreControl";
import { LiveBranchControl } from "../components/LiveBranchControl";
import {
  desktopHostCapabilityLabel,
  displayLabel,
  executionSealPresentation,
  formatScalar,
  formatTimestamp,
} from "../state";
import type { DopeySnapshot, InstrumentMode, LlmProviderId } from "../types";

interface CommandViewProps {
  readonly snapshot: DopeySnapshot;
  readonly canToggleCore: boolean;
  readonly toggleBusy: boolean;
  readonly onToggleCore: (enabled: boolean) => Promise<void>;
  readonly onInstrumentMode: (mode: InstrumentMode) => Promise<void>;
  readonly onProvider: (provider: LlmProviderId, enabled: boolean) => Promise<void>;
  readonly onOpenRouterKey: (apiKey: string) => Promise<void>;
  readonly onOptionsExecution: (enabled: boolean) => Promise<void>;
  readonly refreshIntervalMs: number;
  readonly syncing: boolean;
}

export const CommandView = ({
  snapshot,
  canToggleCore,
  toggleBusy,
  onToggleCore,
  onInstrumentMode,
  onProvider,
  onOpenRouterKey,
  onOptionsExecution,
  refreshIntervalMs,
  syncing,
}: CommandViewProps) => {
  const core = snapshot.researchCore;
  const metacognition = snapshot.metacognition;
  const seal = executionSealPresentation(snapshot.envelope.executionSeal);
  const hostCapability = desktopHostCapabilityLabel(snapshot.hostCapabilities);
  return (
    <div className="command-grid">
      <div className="command-grid__live">
        <LiveBranchControl branch={snapshot.liveBranch} busy={toggleBusy} onOptionsExecution={onOptionsExecution} />
      </div>
      <div className="command-grid__core">
        <ResearchCoreControl
          busy={toggleBusy}
          canToggle={canToggleCore}
          detail={`Last cycle ${formatTimestamp(core.lastRunUtc)} · Next cycle ${formatTimestamp(core.nextRunUtc)} · Lock ${displayLabel(core.lockStatus)} · ${displayLabel(core.mode)}`}
          enabled={core.enabled}
          onInstrumentMode={onInstrumentMode}
          onOpenRouterKey={onOpenRouterKey}
          onProvider={onProvider}
          onToggle={onToggleCore}
          phase={core.phase}
          schedules={core.automationSchedules}
          providerControl={snapshot.llmProviderControl}
          validated={core.validated}
        />
      </div>

      <div className="command-grid__seal">
        <section className={`execution-seal execution-seal--compact execution-seal--${seal.state}`} aria-label={seal.label}>
          <span className="execution-seal__index">C-00</span>
          <div className="execution-seal__sigil" aria-hidden="true"><i /><b /></div>
          <div>
            <span>SEALED RESEARCH BRANCH</span>
            <strong>{seal.label}</strong>
            <em title={snapshot.hostCapabilities.detail ?? hostCapability}>{hostCapability}</em>
          </div>
          <dl>
            <div><dt>RESEARCH</dt><dd>SEALED</dd></div>
            <div><dt>LIVE BRANCH</dt><dd>{snapshot.liveBranch.liveBranchEnabled ? "ACTIVE" : "OFF"}</dd></div>
          </dl>
        </section>
      </div>

      <div className="command-grid__neural">
        <InstrumentPanel className="instrument-panel--neural-activity" code="M-01" meta={`${snapshot.analytics.telemetry.events.length} OBSERVED EVENTS / ${snapshot.observatory.agents.length} DECLARED NODES / SYNC ${Math.round(refreshIntervalMs / 1000)}S`} title="Neural network activity">
          <NeuralActivityField
            agents={snapshot.observatory.agents}
            controlUtc={snapshot.generatedUtc}
            llmResearch={snapshot.llmResearch}
            observedUtc={snapshot.observatory.generatedUtc}
            refreshIntervalMs={refreshIntervalMs}
            stale={snapshot.observatory.stale}
            syncing={syncing}
            telemetry={snapshot.analytics.telemetry}
          />
        </InstrumentPanel>
      </div>

      <div className="command-grid__truth">
        <InstrumentPanel className="" code="T-02" meta="FORWARD-ONLY" title="Truth accrual rail">
          <TruthRail
            closed={snapshot.readiness.closedTrades}
            closedTarget={snapshot.readiness.closedRequired}
            resolved={snapshot.readiness.resolvedDecisions}
            resolvedTarget={snapshot.readiness.resolvedRequired}
            status={snapshot.readiness.status}
          />
        </InstrumentPanel>
      </div>

      <div className="command-grid__world">
        <InstrumentPanel className="" code="W-03" meta={formatTimestamp(snapshot.world.asOf)} title="Market worldline">
          <Worldline regimes={snapshot.world.regimes} />
          {snapshot.world.contradictions.length > 0 ? (
            <div className="contradiction-strip">
              <span>CONTRADICTION</span>
              <p>{snapshot.world.contradictions.join(" · ")}</p>
            </div>
          ) : null}
        </InstrumentPanel>
      </div>

      <div className="command-grid__organisms">
        <InstrumentPanel className="" code="O-04" meta={`${snapshot.observatory.agents.length} PRESENT`} title="Organism spine">
          <OrganismSpine agents={snapshot.observatory.agents} />
        </InstrumentPanel>
      </div>

      <div className="command-grid__meta">
        <InstrumentPanel className="" code="C-05" meta={displayLabel(metacognition.knowledgeBoundary)} title="Metacognitive field">
          <div className="meta-header">
            <div><span>PRIMARY CONTROL</span><strong>{displayLabel(metacognition.primaryControl)}</strong></div>
            <div><span>DIFFICULTY</span><strong>{formatScalar(metacognition.difficulty, 2)}</strong></div>
            <div><span>INFO GAIN</span><strong>{formatScalar(metacognition.expectedInformationGain, 2)}</strong></div>
          </div>
          <ConfidenceDecomposition dimensions={metacognition.confidence} />
          <div className="llm-mesh">
            <div className="llm-mesh__header">
              <span>FRONTIER DELIBERATION</span>
              <strong>{displayLabel(snapshot.llmResearch.cycleStatus)}</strong>
            </div>
            <div className="llm-mesh__providers">
              {snapshot.llmResearch.providers.length === 0
                ? <em>NO MODEL EVIDENCE</em>
                : snapshot.llmResearch.providers.map((provider) => <em key={provider}>{provider}</em>)}
            </div>
            <p>{snapshot.llmResearch.summary ?? "No current synthesis has been emitted."}</p>
            <dl>
              <div><dt>EXPERIMENTS</dt><dd>{snapshot.llmResearch.experimentCount ?? "—"}</dd></div>
              <div><dt>ABSTAIN</dt><dd>{snapshot.llmResearch.abstain === null ? "UNKNOWN" : snapshot.llmResearch.abstain ? "YES" : "NO"}</dd></div>
              <div><dt>OPENROUTER</dt><dd>{snapshot.llmResearch.reportedCostUsd === null ? "—" : `$${snapshot.llmResearch.reportedCostUsd.toFixed(4)}`}</dd></div>
            </dl>
          </div>
        </InstrumentPanel>
      </div>

      <div className="command-grid__schedule">
        <InstrumentPanel className="" code="S-06" meta={`${snapshot.schedule.dueLaneIds.length} DUE`} title="Clock lanes">
          <ScheduleLanes lanes={snapshot.schedule.lanes} />
        </InstrumentPanel>
      </div>

      <div className="command-grid__sources">
        <InstrumentPanel className="" code="D-07" meta={`${snapshot.sources.length} SOURCES`} title="Source freshness">
          <SourceFreshness sources={snapshot.sources} />
        </InstrumentPanel>
      </div>
    </div>
  );
};
