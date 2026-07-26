import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  closeWindow,
  minimizeWindow,
  setInstrumentMode,
  setLlmProvider,
  setOptionsExecution,
  setResearchCore,
  toggleMaximizeWindow,
  updateOpenRouterApiKey,
} from "./bridge";
import { CommandPalette } from "./components/CommandPalette";
import { Navigation, TitleBar } from "./components/Chrome";
import { ContextBar } from "./components/ContextBar";
import { RefreshIcon, SearchIcon } from "./components/Icons";
import { useSnapshotPoll } from "./hooks/useSnapshotPoll";
import { CommandView } from "./views/CommandView";
import { ConstitutionView } from "./views/ConstitutionView";
import { EvolutionView } from "./views/EvolutionView";
import { MarketView } from "./views/MarketView";
import { OrganismsView } from "./views/OrganismsView";
import { PaperView } from "./views/PaperView";
import { TruthView } from "./views/TruthView";
import { ChartView } from "./views/ChartView";
import { EvidenceView } from "./views/EvidenceView";
import { SymbolLabView } from "./views/SymbolLabView";
import { PlaybookView } from "./views/PlaybookView";
import {
  desktopHostCapabilityLabel,
  displayLabel,
  executionSealPresentation,
  formatTimestamp,
} from "./state";
import type { InstrumentMode, LlmProviderId, ViewId } from "./types";
import { isViewId, viewDefinitionFor, VIEW_DEFINITIONS } from "./viewMetadata";

const REFRESH_INTERVAL_MS = 15000;

const initialView = (): ViewId => {
  const requested = window.location.hash.replace(/^#/, "");
  return isViewId(requested) ? requested : "command";
};

export default function App() {
  const [activeView, setActiveView] = useState<ViewId>(initialView);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [density, setDensity] = useState<"dense" | "comfortable">("dense");
  const [textScale, setTextScale] = useState<"100" | "115" | "130">("100");
  const [highContrast, setHighContrast] = useState(false);
  const { model, refreshing, refresh, operatorError, setOperatorError } = useSnapshotPoll(REFRESH_INTERVAL_MS);
  const paletteTriggerRef = useRef<HTMLButtonElement>(null);

  const navigateToView = useCallback((view: ViewId): void => {
    setActiveView(view);
    window.history.replaceState(null, "", `#${view}`);
    window.requestAnimationFrame(() => {
      document.getElementById("workbench-stage")?.focus({ preventScroll: true });
    });
  }, []);

  useEffect(() => {
    const onHashChange = (): void => {
      const requested = window.location.hash.replace(/^#/, "");
      if (isViewId(requested)) {
        setActiveView(requested);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    const onGlobalKeyDown = (event: KeyboardEvent): void => {
      const target = event.target;
      const editing = target instanceof HTMLElement && (
        target.isContentEditable ||
        target.tagName === "INPUT" ||
        target.tagName === "SELECT" ||
        target.tagName === "TEXTAREA"
      );
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
        return;
      }
      if (editing || !event.altKey || event.ctrlKey || event.metaKey) {
        return;
      }
      const shortcut = `alt+${event.key.toLocaleLowerCase()}`;
      const destination = VIEW_DEFINITIONS.find((view) => view.shortcut.toLocaleLowerCase() === shortcut);
      if (destination !== undefined) {
        event.preventDefault();
        navigateToView(destination.id);
      }
    };
    window.addEventListener("keydown", onGlobalKeyDown);
    return () => window.removeEventListener("keydown", onGlobalKeyDown);
  }, [navigateToView]);

  const mutateResearchCore = async (enabled: boolean): Promise<void> => {
    setToggleBusy(true);
    setOperatorError(null);
    try {
      await setResearchCore(enabled);
      await refresh();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Research core transition failed without an error message.";
      await refresh();
      setOperatorError({ kind: "mutation", message });
    } finally {
      setToggleBusy(false);
    }
  };

  const mutatePaperControl = async (operation: () => Promise<unknown>): Promise<void> => {
    setToggleBusy(true);
    setOperatorError(null);
    try {
      await operation();
      await refresh();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Paper research control failed without an error message.";
      await refresh();
      setOperatorError({ kind: "mutation", message });
    } finally {
      setToggleBusy(false);
    }
  };

  const mutateInstrumentMode = async (mode: InstrumentMode): Promise<void> =>
    mutatePaperControl(() => setInstrumentMode(mode));

  const mutateLlmProvider = async (provider: LlmProviderId, enabled: boolean): Promise<void> =>
    mutatePaperControl(() => setLlmProvider(provider, enabled));

  const mutateOpenRouterKey = async (apiKey: string): Promise<void> =>
    mutatePaperControl(() => updateOpenRouterApiKey(apiKey));

  const mutateOptionsExecution = async (enabled: boolean): Promise<void> =>
    mutatePaperControl(() => setOptionsExecution(enabled));

  const invokeWindowControl = async (operation: () => Promise<void>, operationName: string): Promise<void> => {
    try {
      await operation();
    } catch (error: unknown) {
      const detail = error instanceof Error ? error.message : "Unknown window bridge error.";
      setOperatorError((current) => current?.kind === "mutation"
        ? current
        : { kind: "window", message: `${operationName} failed: ${detail}` });
    }
  };

  const snapshot = model.snapshot;
  const seal = executionSealPresentation(snapshot.envelope.executionSeal);
  const hostCapability = desktopHostCapabilityLabel(snapshot.hostCapabilities);
  const activeDefinition = viewDefinitionFor(activeView);
  const staleSourceCount = snapshot.sources.filter((source) => source.severity === "warning" || source.severity === "critical").length;
  const evidenceHash = snapshot.analytics.sources.find((source) => source.sourceId === "latest_dossier")?.sha256 ?? null;
  const canToggleCore = model.connection === "CONNECTED" &&
    snapshot.envelope.executionSeal === "SEALED" &&
    (snapshot.researchCore.enabled === true || snapshot.researchCore.validated === true);

  const selectedView = useMemo(() => {
    switch (activeView) {
      case "command":
        return (
          <CommandView
            canToggleCore={canToggleCore}
            onInstrumentMode={mutateInstrumentMode}
            onOpenRouterKey={mutateOpenRouterKey}
            onOptionsExecution={mutateOptionsExecution}
            onProvider={mutateLlmProvider}
            onToggleCore={mutateResearchCore}
            refreshIntervalMs={REFRESH_INTERVAL_MS}
            snapshot={snapshot}
            syncing={refreshing}
            toggleBusy={toggleBusy}
          />
        );
      case "market":
        return <MarketView snapshot={snapshot} />;
      case "chart":
        return <ChartView regimeHistory={snapshot.analytics.regime.history} regimes={snapshot.world.regimes} symbols={snapshot.universe.symbols} />;
      case "lab":
        return <SymbolLabView symbols={snapshot.universe.symbols} />;
      case "playbook":
        return <PlaybookView playbook={snapshot.playbook} />;
      case "organisms":
        return <OrganismsView snapshot={snapshot} />;
      case "truth":
        return <TruthView snapshot={snapshot} />;
      case "evidence":
        return <EvidenceView snapshot={snapshot} />;
      case "evolution":
        return <EvolutionView snapshot={snapshot} />;
      case "paper":
        return <PaperView snapshot={snapshot} />;
      case "constitution":
        return <ConstitutionView snapshot={snapshot} />;
    }
  }, [activeView, canToggleCore, refreshing, snapshot, toggleBusy]);

  return (
    <div className="app-shell" data-contrast={highContrast ? "high" : "standard"} data-density={density} data-text-scale={textScale}>
      <TitleBar
        connection={model.connection}
        onClose={() => void invokeWindowControl(closeWindow, "Hide to tray")}
        onMaximize={() => void invokeWindowControl(toggleMaximizeWindow, "Maximize")}
        onMinimize={() => void invokeWindowControl(minimizeWindow, "Minimize")}
      />
      <div className="app-workspace">
        <Navigation
          activeView={activeView}
          executionSeal={snapshot.envelope.executionSeal}
          issueCount={snapshot.issues.length}
          onSelect={navigateToView}
        />
        <main className="main-surface" data-view={activeView}>
          <div className="command-strip">
            <div className="command-strip__identity">
              <span className="command-strip__index">{String(VIEW_DEFINITIONS.findIndex((view) => view.id === activeView) + 1).padStart(2, "0")}</span>
              <div className="command-strip__copy">
                <strong>{activeDefinition.title}</strong>
                <span>{snapshot.headline ?? activeDefinition.description}</span>
              </div>
            </div>
            <div className="command-strip__telemetry">
              <span className="command-strip__asof">AS OF <b>{formatTimestamp(snapshot.generatedUtc)}</b></span>
              <span className="command-strip__schema">SCHEMA <b>{snapshot.schemaVersion ?? "UNKNOWN"}</b></span>
              <button
                aria-controls="workspace-palette"
                aria-expanded={paletteOpen}
                aria-haspopup="dialog"
                className="command-strip__palette-trigger"
                onClick={() => setPaletteOpen(true)}
                ref={paletteTriggerRef}
                type="button"
              >
                <SearchIcon size={15} />
                <span>EXPLORE</span>
                <kbd>CTRL K</kbd>
              </button>
              <button aria-label="Refresh system state" className={`command-strip__refresh${refreshing ? " is-refreshing" : ""}`} disabled={refreshing} onClick={() => void refresh()} type="button">
                <RefreshIcon size={15} />
                <span>{refreshing ? "SYNCING" : "REFRESH"}</span>
              </button>
            </div>
          </div>

          <ContextBar
            density={density}
            evidenceHash={evidenceHash}
            highContrast={highContrast}
            onCycleDensity={() => setDensity((current) => current === "dense" ? "comfortable" : "dense")}
            onCycleTextScale={() => setTextScale((current) => current === "100" ? "115" : current === "115" ? "130" : "100")}
            onToggleContrast={() => setHighContrast((current) => !current)}
            snapshot={snapshot}
            staleSourceCount={staleSourceCount}
            textScale={textScale}
          />

          {operatorError === null ? null : (
            <div className="operator-error" role="alert">
              <span>{operatorError.kind === "mutation" ? "CONTROL MUTATION FAILED" : "CONTROL PATH ERROR"}</span>
              <p>{operatorError.message}</p>
              <button onClick={() => setOperatorError(null)} type="button">DISMISS</button>
            </div>
          )}

          <div aria-label={`${activeDefinition.title} workspace`} className="view-stage" id="workbench-stage" tabIndex={-1}>
            <div className="view-stage__canvas" key={activeView}>{selectedView}</div>
          </div>

          <span aria-live="polite" className="sr-only">{activeDefinition.title} workspace active</span>

          <footer className="status-footer">
            <span><i className={`status-dot status-dot--${model.connection === "CONNECTED" ? "nominal" : "critical"}`} /> CONTROL {model.connection}</span>
            <span>AUTOMATION {snapshot.researchCore.phase}</span>
            <span>HEALTH {displayLabel(snapshot.homeostasis.healthStatus)}</span>
            <span>OBSERVATORY {snapshot.observatory.stale === true ? "STALE" : displayLabel(snapshot.observatory.status)}</span>
            <span>ISSUES {snapshot.issues.length}</span>
            <strong className={`status-footer__seal status-footer__seal--${seal.state}`}>
              {seal.label} // {hostCapability}
            </strong>
          </footer>
        </main>
      </div>
      <CommandPalette
        activeView={activeView}
        onClose={() => setPaletteOpen(false)}
        onSelect={navigateToView}
        open={paletteOpen}
      />
    </div>
  );
}
