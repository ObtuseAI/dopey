import { useState } from "react";
import type { InstrumentMode, LlmProviderControlState, LlmProviderId } from "../types";


interface ResearchRoutingControlProps {
  readonly state: LlmProviderControlState;
  readonly canConfigure: boolean;
  readonly busy: boolean;
  readonly onInstrumentMode: (mode: InstrumentMode) => Promise<void>;
  readonly onProvider: (provider: LlmProviderId, enabled: boolean) => Promise<void>;
  readonly onOpenRouterKey: (apiKey: string) => Promise<void>;
}

const MODES: readonly InstrumentMode[] = ["stocks", "options", "both"];
const displayToken = (value: string): string => value.replaceAll("_", " ").toUpperCase();

export const ResearchRoutingControl = ({
  state,
  canConfigure,
  busy,
  onInstrumentMode,
  onProvider,
  onOpenRouterKey,
}: ResearchRoutingControlProps) => {
  const [keyEditorOpen, setKeyEditorOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const keyCanSave = apiKey.trim().length >= 20 && canConfigure && !busy;
  const routeEnabled = state.providers.openrouter === true && state.providers.openrouter_hybrid === true;
  const routeCredentialAvailable = state.availability.openrouter_hybrid === true;
  const routeStatus = routeEnabled
    ? state.activeRouteAvailable === true
      ? "READY"
      : state.credential.configured === true && state.credential.usable === false
        ? "KEY UNUSABLE"
        : "KEY REQUIRED"
    : "DISABLED";
  const credentialStatus = state.credential.configured === true
    ? state.credential.usable === true ? "USER-SCOPED / READY" : "PRESENT / UNUSABLE"
    : "NOT CONFIGURED";

  const saveKey = async (): Promise<void> => {
    if (!keyCanSave) {
      return;
    }
    const submitted = apiKey;
    setApiKey("");
    try {
      await onOpenRouterKey(submitted);
      setKeyEditorOpen(false);
    } finally {
      setApiKey("");
    }
  };

  return (
    <div className="research-routing" aria-label="Paper research expression and LLM routing">
      <div className="research-routing__mode">
        <span>PAPER EXPRESSION</span>
        <div role="group" aria-label="Stock and options research mode">
          {MODES.map((mode) => (
            <button
              aria-pressed={state.instrumentMode === mode}
              className={state.instrumentMode === mode ? "is-active" : ""}
              disabled={!canConfigure || busy}
              key={mode}
              onClick={() => void onInstrumentMode(mode)}
              type="button"
            >
              {mode.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="research-routing__providers">
        <span>GOVERNED FRONTIER ROUTE</span>
        <div
          aria-label={`OpenRouter four-model hybrid ${routeStatus.toLowerCase()}`}
          className={`provider-route${state.activeRouteAvailable === true ? " is-ready" : ""}`}
          role="group"
        >
          <i aria-hidden="true" />
          <span>
            OPENROUTER 4-MODEL HYBRID
            <small>{state.routingPolicy.strategy === null ? "CAPABILITY-FIT STAGED ROUTING" : displayToken(state.routingPolicy.strategy)}</small>
          </span>
          <strong>{routeStatus}</strong>
          <button
            aria-pressed={routeEnabled}
            disabled={!canConfigure || busy || (!routeEnabled && !routeCredentialAvailable)}
            onClick={() => void onProvider("openrouter_hybrid", !routeEnabled)}
            type="button"
          >
            {routeEnabled ? "DISABLE" : "ENABLE"}
          </button>
        </div>
        <div className="model-roster" aria-label="Active OpenRouter model roster">
          {state.activeModelRoster.length === 0 ? (
            <p>ROSTER NOT REPORTED</p>
          ) : state.activeModelRoster.map((model) => (
            <article key={model.routeId}>
              <span>{displayToken(model.stage)}</span>
              <strong>{model.modelId}</strong>
              <small>{displayToken(model.role)}</small>
            </article>
          ))}
        </div>
      </div>

      <div className="research-routing__key">
        <div>
          <span>OPENROUTER KEY</span>
          <strong>{credentialStatus}</strong>
        </div>
        <button
          className="key-editor-trigger"
          disabled={!canConfigure || busy}
          onClick={() => {
            setApiKey("");
            setKeyEditorOpen((current) => !current);
          }}
          type="button"
        >
          {state.credential.configured === true ? "UPDATE" : "ADD KEY"}
        </button>
        {keyEditorOpen ? (
          <div className="key-editor">
            <label htmlFor="openrouter-api-key">OPENROUTER API KEY</label>
            <input
              autoComplete="new-password"
              id="openrouter-api-key"
              onChange={(event) => setApiKey(event.currentTarget.value)}
              placeholder="Paste key — never displayed again"
              spellCheck={false}
              type="password"
              value={apiKey}
            />
            <button disabled={!keyCanSave} onClick={() => void saveKey()} type="button">ENCRYPT + SAVE</button>
            <button
              onClick={() => {
                setApiKey("");
                setKeyEditorOpen(false);
              }}
              type="button"
            >
              CANCEL
            </button>
            <p>Windows DPAPI user scope. No repository, artifact, log, or value readback.</p>
          </div>
        ) : null}
      </div>
    </div>
  );
};
