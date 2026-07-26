import { useState } from "react";
import { displayLabel, formatTimestamp } from "../state";
import type { LlmResearchState, ObservatoryDatum, TelemetryAnalyticsState } from "../types";

type NeuralAgentPhase = "sensors" | "reasoning" | "challenge" | "synthesis";
type NeuralAgentTone = "active" | "blocked" | "complete" | "gap" | "unknown";
type NeuralFilter = "all" | "clear" | "gaps";
type NeuralMode = "observed" | "topology";

interface NeuralPhaseDefinition {
  readonly id: NeuralAgentPhase;
  readonly index: string;
  readonly label: string;
}

interface NeuralActivityFieldProps {
  readonly agents: readonly ObservatoryDatum[];
  readonly controlUtc: string | null;
  readonly llmResearch: LlmResearchState;
  readonly observedUtc: string | null;
  readonly refreshIntervalMs: number;
  readonly stale: boolean | null;
  readonly syncing: boolean;
  readonly telemetry: TelemetryAnalyticsState;
}

const neuralPhases: readonly NeuralPhaseDefinition[] = [
  { id: "sensors", index: "L1", label: "EVIDENCE" },
  { id: "reasoning", index: "L2", label: "HYPOTHESES" },
  { id: "challenge", index: "L3", label: "CHALLENGE" },
  { id: "synthesis", index: "L4", label: "SYNTHESIS" },
];

const phaseForAgent = (agent: ObservatoryDatum): NeuralAgentPhase => {
  const id = agent.id.toLowerCase();
  if (id.includes("synthesizer")) {
    return "synthesis";
  }
  if (id.includes("adversarial") || id.includes("calibration") || id.includes("knowledge_boundary")) {
    return "challenge";
  }
  if (id.includes("bull_") || id.includes("bear_") || id.includes("neutral_unknown")) {
    return "reasoning";
  }
  return "sensors";
};

const agentHasGap = (agent: ObservatoryDatum): boolean => {
  const status = agent.status?.toLowerCase() ?? "";
  return (agent.gapCount ?? 0) > 0 || status.includes("gap") || status.includes("degrad") || status.includes("missing");
};

const agentTone = (agent: ObservatoryDatum): NeuralAgentTone => {
  const status = agent.status?.toLowerCase() ?? "";
  if (status.includes("running") || status.includes("active") || status.includes("processing")) {
    return "active";
  }
  if (status.includes("block") || status.includes("fail") || status.includes("error")) {
    return "blocked";
  }
  if (agentHasGap(agent)) {
    return "gap";
  }
  if (status.includes("complete") || status.includes("ready") || status.includes("pass")) {
    return "complete";
  }
  return "unknown";
};

const compactAgentLabel = (agent: ObservatoryDatum): string => displayLabel(agent.title)
  .replace(/ AGENT$/u, "")
  .replace(/ PARTICIPATION$/u, " PART.")
  .replace(/ KNOWLEDGE BOUNDARY$/u, "KNOWLEDGE");

const confidenceLabel = (value: number | null): string => value === null
  ? "N/A"
  : `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;

const agentsForFilter = (
  agents: readonly ObservatoryDatum[],
  filter: NeuralFilter,
): readonly ObservatoryDatum[] => {
  if (filter === "gaps") {
    return agents.filter(agentHasGap);
  }
  if (filter === "clear") {
    return agents.filter((agent) => !agentHasGap(agent));
  }
  return agents;
};

const filterLabel = (filter: NeuralFilter): string => filter === "all"
  ? "ALL"
  : filter === "clear"
    ? "CLEAR"
    : "GAPS";

export const NeuralActivityField = ({
  agents,
  controlUtc,
  llmResearch,
  observedUtc,
  refreshIntervalMs,
  stale,
  syncing,
  telemetry,
}: NeuralActivityFieldProps) => {
  const [filter, setFilter] = useState<NeuralFilter>("all");
  const [mode, setMode] = useState<NeuralMode>(telemetry.events.length > 0 ? "observed" : "topology");
  const [paused, setPaused] = useState(false);
  const [replayOffset, setReplayOffset] = useState(0);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(() => agents[0]?.id ?? null);
  const visibleAgents = agentsForFilter(agents, filter);
  const selectedAgent = visibleAgents.find((agent) => agent.id === selectedAgentId) ?? visibleAgents[0] ?? agents[0] ?? null;
  const completedCount = agents.filter((agent) => agentTone(agent) === "complete").length;
  const activeCount = agents.filter((agent) => agentTone(agent) === "active").length;
  const gapAgentCount = agents.filter(agentHasGap).length;
  const totalReads = agents.reduce((total, agent) => total + (agent.dataReads ?? 0), 0);
  const telemetryEvents = telemetry.events.slice(0, Math.max(telemetry.events.length - replayOffset, 0)).slice(-32);
  const telemetryErrors = telemetryEvents.filter((event) => event.error !== null).length;
  const durations = telemetryEvents.map((event) => event.durationMs).filter((value): value is number => value !== null);
  const averageDuration = durations.length === 0 ? null : durations.reduce((total, value) => total + value, 0) / durations.length;
  const outputCount = telemetryEvents.reduce((total, event) => total + event.outputArtifactHashes.length, 0);
  const lastSuccess = [...telemetryEvents].reverse().find((event) => event.error === null) ?? null;
  const networkStatus = syncing
    ? "SYNCING TELEMETRY"
    : activeCount > 0
      ? `${activeCount} AGENTS PROCESSING`
      : stale === true
        ? "OBSERVATORY SNAPSHOT STALE"
        : "OBSERVATORY READY";
  const filters: readonly NeuralFilter[] = ["all", "clear", "gaps"];

  return (
    <div className={`neural-activity${syncing ? " is-syncing" : ""}`}>
      <header className="neural-activity__control">
        <div className="neural-activity__live" aria-live="polite">
          <i aria-hidden="true" />
          <div><span>LIVE CONTROL LINK</span><strong>{networkStatus}</strong></div>
        </div>
        <div className="neural-activity__timestamps">
          <span title={observedUtc ?? "Agent snapshot timestamp not reported"}>AGENTS {formatTimestamp(observedUtc)}</span>
          <span title={controlUtc ?? "Control timestamp not reported"}>CONTROL {formatTimestamp(controlUtc)}</span>
          <strong>AUTO SYNC {Math.round(refreshIntervalMs / 1000)}S</strong>
        </div>
        <div className="neural-activity__filters" aria-label="Filter neural activity agents" role="group">
          {filters.map((item) => {
            const count = agentsForFilter(agents, item).length;
            return (
              <button aria-pressed={filter === item} key={item} onClick={() => setFilter(item)} type="button">
                {filterLabel(item)} <b>{count}</b>
              </button>
            );
          })}
        </div>
      </header>

      <dl className="neural-activity__metrics">
        <div><dt>AGENTS</dt><dd>{agents.length}</dd><span>reported nodes</span></div>
        <div><dt>COMPLETE</dt><dd>{completedCount}</dd><span>clean status</span></div>
        <div><dt>DATA GAPS</dt><dd>{gapAgentCount}</dd><span>review required</span></div>
        <div><dt>DATA READS</dt><dd>{totalReads}</dd><span>reported total</span></div>
        <div><dt>FRONTIER</dt><dd>{llmResearch.providers.length}</dd><span>provider routes</span></div>
      </dl>

      <div className="neural-modebar">
        <div aria-label="Neural activity display" role="group">
          <button aria-pressed={mode === "observed"} onClick={() => setMode("observed")} type="button">OBSERVED EVENTS <b>{telemetry.events.length}</b></button>
          <button aria-pressed={mode === "topology"} onClick={() => setMode("topology")} type="button">DECLARED TOPOLOGY <b>{agents.length}</b></button>
        </div>
        <div aria-label="Telemetry playback controls" role="group">
          <button aria-pressed={paused} disabled={telemetry.events.length === 0} onClick={() => setPaused((current) => !current)} type="button">{paused ? "RESUME" : "PAUSE"}</button>
          <button disabled={telemetry.events.length === 0} onClick={() => { setPaused(true); setReplayOffset((current) => Math.min(current + 16, Math.max(telemetry.events.length - 1, 0))); }} type="button">REPLAY −16</button>
          <button disabled={replayOffset === 0} onClick={() => setReplayOffset((current) => Math.max(current - 16, 0))} type="button">FORWARD +16</button>
          <button disabled={replayOffset === 0} onClick={() => { setReplayOffset(0); setPaused(false); }} type="button">LIVE EDGE</button>
        </div>
      </div>

      {mode === "observed" && telemetry.events.length === 0 ? (
        <div className="neural-telemetry-unavailable" role="status">
          <div><span>OBSERVED FLOW / UNAVAILABLE</span><strong>{displayLabel(telemetry.status)}</strong><p>{telemetry.reason ?? "No append-only activity event stream has been emitted."}</p></div>
          <dl>{telemetry.contractFields.map((field) => <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>REQUIRED</dd></div>)}</dl>
          <p>No connector animates until an observed event binds its input and output artifact hashes.</p>
        </div>
      ) : mode === "observed" ? (
        <div className={`neural-event-console${paused ? " is-paused" : ""}`}>
          <dl className="neural-event-metrics">
            <div><dt>WINDOW</dt><dd>{telemetryEvents.length}</dd><span>observed events</span></div>
            <div><dt>AVG DURATION</dt><dd>{averageDuration === null ? "—" : `${Math.round(averageDuration)}ms`}</dd><span>reported only</span></div>
            <div><dt>OUTPUTS</dt><dd>{outputCount}</dd><span>artifact hashes</span></div>
            <div><dt>ERRORS</dt><dd>{telemetryErrors}</dd><span>explicit records</span></div>
            <div><dt>QUEUE DEPTH</dt><dd>—</dd><span>not in contract</span></div>
            <div><dt>LAST SUCCESS</dt><dd>{lastSuccess === null ? "—" : formatTimestamp(lastSuccess.eventUtc)}</dd><span>{lastSuccess?.agentId ?? "unreported"}</span></div>
          </dl>
          <div className="neural-swimlanes" aria-label="Observed agent event swimlanes">
            {[...new Set(telemetryEvents.map((event) => event.agentId))].map((agentId) => (
              <div className="neural-swimlane" key={agentId}>
                <strong>{agentId}</strong>
                <div>{telemetryEvents.filter((event) => event.agentId === agentId).map((event, index) => <button aria-label={`${event.agentId}, ${event.phase}, ${event.statusTransition}, ${event.durationMs ?? "unknown"} milliseconds`} className={event.error === null ? "is-success" : "is-error"} key={`${event.eventUtc}-${index}`} title={`${event.eventUtc}\n${event.statusTransition}\n${event.durationMs ?? "—"} ms\n${event.outputArtifactHashes.length} outputs`} type="button"><i style={{ width: `${Math.max(14, Math.min((event.durationMs ?? 1) / 20, 100))}%` }} /><span>{event.phase}</span></button>)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : agents.length === 0 ? (
        <div className="neural-activity__empty">
          <strong>AGENT TELEMETRY NOT REPORTED</strong>
          <p>The observatory emitted no agent nodes. No topology is inferred.</p>
        </div>
      ) : (
        <div className="neural-topology" aria-label="Research agent topology">
          {neuralPhases.map((phase) => {
            const phaseAgents = visibleAgents.filter((agent) => phaseForAgent(agent) === phase.id);
            return (
              <section className={`neural-stage neural-stage--${phase.id}`} key={phase.id}>
                <header><span>{phase.index}</span><strong>{phase.label}</strong><b>{phaseAgents.length}</b></header>
                <div className="neural-stage__nodes">
                  {phaseAgents.map((agent) => {
                    const tone = agentTone(agent);
                    return (
                      <button
                        aria-label={`${displayLabel(agent.title)}; ${displayLabel(agent.status)}; confidence ${confidenceLabel(agent.confidence)}`}
                        aria-pressed={selectedAgent?.id === agent.id}
                        className={`neural-node neural-node--${tone}`}
                        key={agent.id}
                        onClick={() => setSelectedAgentId(agent.id)}
                        type="button"
                      >
                        <i aria-hidden="true" />
                        <strong>{compactAgentLabel(agent)}</strong>
                        <small>{confidenceLabel(agent.confidence)}</small>
                        <em>{tone.toUpperCase()}</em>
                      </button>
                    );
                  })}
                  {phaseAgents.length === 0 ? <span className="neural-stage__empty">NO MATCHING NODES</span> : null}
                </div>
              </section>
            );
          })}
        </div>
      )}

      <section className="neural-inspector" aria-live="polite">
        {selectedAgent === null ? (
          <div><span>NODE INSPECTOR</span><strong>NO AGENT SELECTED</strong><p>Select a reported node to inspect its exact telemetry.</p></div>
        ) : (
          <>
            <div className="neural-inspector__identity">
              <span>SELECTED NODE / {phaseForAgent(selectedAgent).toUpperCase()}</span>
              <strong>{displayLabel(selectedAgent.title)}</strong>
              <p>{selectedAgent.detail ?? "No descriptive role detail was reported by the observatory."}</p>
            </div>
            <dl className="neural-inspector__telemetry">
              <div><dt>STATUS</dt><dd>{displayLabel(selectedAgent.status)}</dd></div>
              <div><dt>CONFIDENCE</dt><dd>{confidenceLabel(selectedAgent.confidence)}</dd></div>
              <div><dt>READS</dt><dd>{selectedAgent.dataReads ?? "N/A"}</dd></div>
              <div><dt>GAPS</dt><dd>{selectedAgent.gapCount ?? "N/A"}</dd></div>
            </dl>
            <div className="neural-inspector__routes">
              <span>FRONTIER ROUTES</span>
              <div>{llmResearch.providers.length === 0
                ? <em>NONE REPORTED</em>
                : llmResearch.providers.map((provider) => <em key={provider}>{provider}</em>)}</div>
            </div>
          </>
        )}
      </section>

      <p className="neural-activity__boundary">{telemetry.events.length > 0 ? "OBSERVED EVENT LINKS ONLY / PAUSE AND REPLAY AVAILABLE / PAPER RESEARCH ONLY" : "DECLARED TOPOLOGY ONLY / NO CONNECTOR CLAIMS MESSAGE FLOW / OBSERVED TELEMETRY UNAVAILABLE / PAPER RESEARCH ONLY"}</p>
    </div>
  );
};
