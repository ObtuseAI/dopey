# DOPEY Desktop UI/UX Redesign — Phase 1: Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the desktop frontend's foundations — unified status-tone module, decoupled view files, extracted app chrome/polling, a dev-mode mock bridge, and a layered CSS architecture — so the Phase 2–6 redesign work is safe and fast.

**Architecture:** Token-first rebuild in place. Every task is behavior-preserving (verified by typecheck + build + visual-QA screenshot comparison) except the deliberate status-tone unification. No backend, bridge, CSP, or build-pipeline changes.

**Tech Stack:** React 19.2, TypeScript 7 (strict, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`), Vite 8, zero runtime dependencies, hand-rolled CSS.

**Spec:** `docs/superpowers/specs/2026-07-25-desktop-uiux-redesign-design.md` (phases P2–P6 get their own plans after this one lands).

## Global Constraints

- Working tree: repo root `C:/Users/CH/dopey`; all app paths below are relative to `desktop/`.
- Runtime dependencies: **react + react-dom only**. Do not add any dependency (dev or runtime).
- Do not touch `src/bridge.ts`'s API surface, `index.html`'s CSP, `tools/inline_frontend.mjs`, or any Python/host code.
- Evidence copy is frozen: boundary rails (`PAPER-ONLY // LIVE-BLOCKED`), seal labels, "not a probability" disclaimers, and panel codes render byte-identical after every task.
- Toolchain pins: Node 24.15.0, npm 11.14.1. Verify with `node --version && npm --version` before starting.
- Source files use CRLF line endings and no formatter; match the existing style (2-space indent, double quotes, semicolons, `readonly` props). Never reformat code you are not changing.
- Gate for every task: `npm run typecheck` clean, `npm run build` clean, `node tools/generate_visual_qa.mjs` prints `"status":"pass"`, then open `visual-qa/index.html#<view>` and compare against the existing `visual-qa/*_v3.png` screenshots for every view the task touches. No visual drift except where a task explicitly allows it.
- Commit after every task with the exact message given.

## Before you begin

- [ ] `cd /c/Users/CH/dopey && git status --short` — if there are uncommitted changes inside `desktop/`, stop and report before proceeding.
- [ ] `cd /c/Users/CH/dopey/desktop && node --version && npm --version` — expect `v24.15.0` and `11.14.1`.
- [ ] Baseline gates: `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` — all must pass before any edit. Capture the stylesheet checksum for Task 5: `grep -o '{' src/styles.css | wc -l` → record the number (call it `BASELINE_BRACES`).

---

### Task 1: Unified tone module (`src/lib/tone.ts`)

**Files:**
- Create: `desktop/src/lib/tone.ts`
- Modify: `desktop/src/views/ChartView.tsx` (local `tone` at lines 43–50)
- Modify: `desktop/src/views/SymbolLabView.tsx` (local `tone` at lines 27–31)
- Modify: `desktop/src/views/EvidenceView.tsx` (local `tone` at lines 17–29)
- Modify: `desktop/src/views/SecondaryViews.tsx` (local `statusTone` at lines 29–49)
- Modify: `desktop/src/components/AnalyticsVisuals.tsx` (local `toneFromStatus` at lines 54–66)
- Modify: `desktop/src/views/PlaybookView.tsx` (local `statusTone` at lines 80–88)
- Modify: `desktop/src/styles.css` (rename Symbol-Lab-only `--positive`/`--negative` class selectors)

**Interfaces:**
- Produces: `statusTone(status: string | null): StatusTone` and `directionTone(direction: string): DirectionTone` from `src/lib/tone.ts`; types `StatusTone = "nominal" | "warning" | "critical" | "unknown"`, `DirectionTone = "bullish" | "bearish" | "neutral"`. All later tasks and phases import tones from here.
- Consumes: nothing.

Known deliberate drift (allowed, reviewer confirms on screenshots): status precedence is now critical → warning → nominal everywhere (AnalyticsVisuals previously checked nominal first); PlaybookView statuses other than `complete`/`partial`/critical-markers may render `warning`/`critical` per the canonical vocabulary instead of blanket `critical`; Symbol Lab's `positive`/`negative` class suffixes become `bullish`/`bearish`.

- [ ] **Step 1: Create `src/lib/tone.ts` with this exact content**

```ts
export type StatusTone = "nominal" | "warning" | "critical" | "unknown";
export type DirectionTone = "bullish" | "bearish" | "neutral";

const CRITICAL_MARKERS = [
  "fail", "fault", "block", "error", "missing", "unreadable", "invalid", "reject", "no_eligible", "unavailable",
] as const;
const WARNING_MARKERS = [
  "stale", "warn", "pending", "unknown", "diagnostic", "degraded", "partial", "insufficient",
] as const;
const NOMINAL_MARKERS = [
  "pass", "healthy", "active", "running", "available", "complete", "ready", "parent",
] as const;

const includesAny = (value: string, markers: readonly string[]): boolean =>
  markers.some((marker) => value.includes(marker));

export const statusTone = (status: string | null): StatusTone => {
  const normalized = status?.toLowerCase() ?? "";
  if (includesAny(normalized, CRITICAL_MARKERS)) {
    return "critical";
  }
  if (includesAny(normalized, WARNING_MARKERS)) {
    return "warning";
  }
  if (includesAny(normalized, NOMINAL_MARKERS)) {
    return "nominal";
  }
  return "unknown";
};

export const directionTone = (direction: string): DirectionTone => {
  const normalized = direction.toLowerCase();
  if (normalized.includes("bull") || normalized.includes("positive") || normalized.includes("supported") || normalized.includes("active")) {
    return "bullish";
  }
  if (normalized.includes("bear") || normalized.includes("negative") || normalized.includes("fragile") || normalized.includes("blocked")) {
    return "bearish";
  }
  return "neutral";
};
```

- [ ] **Step 2: ChartView** — delete the local `tone` (lines 43–50), add `import { directionTone } from "../lib/tone";`, and replace every `tone(` call with `directionTone(`: `grep -n 'tone(' src/views/ChartView.tsx` to find call sites (do not touch unrelated identifiers like `tone--` class strings, which keep working because `directionTone` emits the same `bullish`/`bearish`/`neutral` vocabulary).

- [ ] **Step 3: SymbolLabView** — delete local `tone` (lines 27–31), import `directionTone`, replace call sites. Then find the class templates it feeds (`grep -n 'directionTone(' src/views/SymbolLabView.tsx` — note each surrounding class prefix, e.g. `lab-chip--${directionTone(...)}`) and rename the corresponding selectors in `src/styles.css` from `--positive` → `--bullish` and `--negative` → `--bearish` **only for those class prefixes**. Audit: `grep -rn -- '--positive\|--negative' src/` → the only remaining hits may belong to components that never used SymbolLab's `tone`; leave those untouched.

- [ ] **Step 4: EvidenceView** — delete local `tone` (lines 17–29), import `statusTone`, replace call sites (`grep -n 'tone(' src/views/EvidenceView.tsx`; `MutationGenealogyPanel` and `NodeInspector` call sites included — they move house in Task 2, still from `../lib/tone`).

- [ ] **Step 5: SecondaryViews** — delete local `statusTone` (lines 29–49), import `statusTone` from `../lib/tone`. Call sites (`DatasetTable`, `CheckTable`) already pass `string | null`-compatible values.

- [ ] **Step 6: AnalyticsVisuals** — delete `toneFromStatus` (lines 54–66), import `statusTone`, replace `toneFromStatus(` with `statusTone(`.

- [ ] **Step 7: PlaybookView** — replace the local tri-state function to preserve its rendering exactly:

```ts
import { statusTone } from "../lib/tone";

const playbookTone = (status: string): "nominal" | "warning" | "critical" => {
  const tone = statusTone(status);
  return tone === "unknown" ? "critical" : tone;
};
```

Replace call sites of the old `statusTone(` with `playbookTone(`.

- [ ] **Step 8: Verify** — `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` all pass; `grep -rn 'const tone\|toneFromStatus' src/` → no hits. Open `visual-qa/index.html#chart`, `#lab`, `#evidence`, `#playbook`, `#market` and compare with the `*_v3.png` screenshots; only the deliberate drift listed above may differ.

- [ ] **Step 9: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src && git commit -m "Unify desktop status and direction tones in src/lib/tone"
```

---

### Task 2: Split `SecondaryViews.tsx` into six view files

**Files:**
- Create: `desktop/src/components/PageHeader.tsx`
- Create: `desktop/src/components/DatasetTable.tsx`
- Create: `desktop/src/components/MutationGenealogyPanel.tsx`
- Create: `desktop/src/views/MarketView.tsx`, `OrganismsView.tsx`, `TruthView.tsx`, `EvolutionView.tsx`, `PaperView.tsx`, `ConstitutionView.tsx`
- Modify: `desktop/src/views/EvidenceView.tsx` (remove moved code, trim imports)
- Modify: `desktop/src/App.tsx:18` (import the six views from their new files)
- Delete: `desktop/src/views/SecondaryViews.tsx`

**Interfaces:**
- Consumes: `statusTone` from `src/lib/tone` (Task 1).
- Produces: six view components, each `({ snapshot }: { readonly snapshot: DopeySnapshot }) => JSX.Element`, imported by `App.tsx`; `PageHeader`, `DatasetTable`, `MutationGenealogyPanel` shared components reused by later phases.

Component placement (code moves verbatim except imports; nothing is rewritten):

| New file | Contents (from `SecondaryViews.tsx` unless noted) |
|---|---|
| `components/PageHeader.tsx` | `PageHeader` (lines 51–73), exported |
| `components/DatasetTable.tsx` | `DatasetTable` (lines 75–91), exported |
| `components/MutationGenealogyPanel.tsx` | `graphPositions` + `shortNode` + `MutationGenealogyPanel` + `NodeInspector` — all currently in `EvidenceView.tsx` (panel at lines 161–204, `NodeInspector` 206–220, helpers directly above the panel); only the panel is exported |
| `views/MarketView.tsx` | `signedPercent`, `StockExtremeBoard`, `OptionExtremeBoard`, `ExtremesField`, `MarketView` |
| `views/OrganismsView.tsx` | `OrganismsView` |
| `views/TruthView.tsx` | `CheckTable`, `ThresholdDial`, `TruthView` |
| `views/EvolutionView.tsx` | `EvolutionView` |
| `views/PaperView.tsx` | `PositionTable`, `BookMetric`, `PaperView` |
| `views/ConstitutionView.tsx` | `constitutionalLaw`, `ConstitutionView` |

Delete `severityClass` (line 433) — confirmed dead: `grep -rn 'severityClass' src/` shows only its definition.

- [ ] **Step 1: Create `components/PageHeader.tsx`** — move `PageHeader` verbatim and export it. No imports needed (pure JSX).

- [ ] **Step 2: Create `components/DatasetTable.tsx`** — move `DatasetTable` verbatim and export it. Imports:

```ts
import { EmptyState } from "./Instruments";
import { statusTone } from "../lib/tone";
import { displayLabel } from "../state";
import type { ObservatoryDatum } from "../types";
```

- [ ] **Step 3: Create `components/MutationGenealogyPanel.tsx`** — cut `graphPositions`, `shortNode`, `MutationGenealogyPanel`, `NodeInspector` from `EvidenceView.tsx` into this file; export only `MutationGenealogyPanel`. Imports:

```ts
import { useMemo, useState } from "react";
import { EmptyState } from "./Instruments";
import { statusTone } from "../lib/tone";
import { displayLabel, formatScalar } from "../state";
import type { MutationGenealogyState, MutationNode } from "../types";
```

In the moved code, `tone(` becomes `statusTone(` (already done in Task 1 if Task 1 ran first — keep the names consistent).

- [ ] **Step 4: Trim `EvidenceView.tsx`** — after the cut, remove now-unused imports (`useMemo`/`useState` if unused, `MutationGenealogyState`/`MutationNode` types if unused — verify with `npm run typecheck`; `noUnusedLocals` will name every straggler).

- [ ] **Step 5: Create the six view files** with the contents from the table above. Exact import sets:

`views/MarketView.tsx`:

```ts
import { InstrumentPanel, SourceFreshness, UniverseCoverageExplorer, Worldline } from "../components/Instruments";
import { OptionsIntelligence, RegimeIntelligence } from "../components/AnalyticsVisuals";
import { DatasetTable } from "../components/DatasetTable";
import { PageHeader } from "../components/PageHeader";
import { formatTimestamp } from "../state";
import type { DopeySnapshot, OptionExtreme, StockExtreme } from "../types";
```

`views/OrganismsView.tsx`:

```ts
import { InstrumentPanel } from "../components/Instruments";
import { DatasetTable } from "../components/DatasetTable";
import { PageHeader } from "../components/PageHeader";
import { formatExactTimestamp } from "../state";
import type { DopeySnapshot } from "../types";
```

`views/TruthView.tsx`:

```ts
import { EmptyState, InstrumentPanel } from "../components/Instruments";
import { MachineLearningTruth, ReadinessAccrualCockpit } from "../components/AnalyticsVisuals";
import { PageHeader } from "../components/PageHeader";
import { statusTone } from "../lib/tone";
import { displayLabel, formatTimestamp, normalizedPercent } from "../state";
import type { DopeySnapshot, ReadinessCheck } from "../types";
```

`views/EvolutionView.tsx`:

```ts
import { InstrumentPanel } from "../components/Instruments";
import { DatasetTable } from "../components/DatasetTable";
import { MutationGenealogyPanel } from "../components/MutationGenealogyPanel";
import { PageHeader } from "../components/PageHeader";
import { displayLabel, formatExactTimestamp, formatScalar } from "../state";
import type { DopeySnapshot } from "../types";
```

`views/PaperView.tsx`:

```ts
import { EmptyState, InstrumentPanel } from "../components/Instruments";
import { PaperRiskCockpit } from "../components/AnalyticsVisuals";
import { PageHeader } from "../components/PageHeader";
import { displayLabel, formatTimestamp } from "../state";
import type { DopeySnapshot, PaperPosition } from "../types";
```

`views/ConstitutionView.tsx`:

```ts
import { InstrumentPanel } from "../components/Instruments";
import { DatasetTable } from "../components/DatasetTable";
import { PageHeader } from "../components/PageHeader";
import { desktopHostCapabilityLabel, displayLabel, executionSealPresentation, formatTimestamp } from "../state";
import type { DopeySnapshot } from "../types";
```

If `npm run typecheck` flags an import as unused or missing in any file, adjust that file's import list only — do not edit the moved component bodies.

- [ ] **Step 6: Update `App.tsx:18`** — replace the `SecondaryViews` import with:

```ts
import { ConstitutionView } from "./views/ConstitutionView";
import { EvolutionView } from "./views/EvolutionView";
import { MarketView } from "./views/MarketView";
import { OrganismsView } from "./views/OrganismsView";
import { PaperView } from "./views/PaperView";
import { TruthView } from "./views/TruthView";
```

- [ ] **Step 7: Delete `SecondaryViews.tsx`** — `rm desktop/src/views/SecondaryViews.tsx`.

- [ ] **Step 8: Verify** — `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` pass; compare `#market`, `#organisms`, `#truth`, `#evolution`, `#paper`, `#constitution`, `#evidence` against the PNGs. Zero visual drift.

- [ ] **Step 9: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src && git commit -m "Split SecondaryViews into per-view files and shared panels"
```

---

### Task 3: Extract `useSnapshotPoll` and `ContextBar` from `App.tsx`

**Files:**
- Create: `desktop/src/hooks/useSnapshotPoll.ts`
- Create: `desktop/src/components/ContextBar.tsx`
- Modify: `desktop/src/App.tsx`

**Interfaces:**
- Produces: `useSnapshotPoll(refreshIntervalMs: number): UseSnapshotPollResult` with `{ model, refreshing, refresh, operatorError, setOperatorError }`; exported types `OperatorErrorKind`, `OperatorErrorState`; `ContextBar(props: ContextBarProps)`. `App.tsx` is the only consumer in this task.

- [ ] **Step 1: Create `src/hooks/useSnapshotPoll.ts` with this exact content**

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { BridgeUnavailableError, readControlState } from "../bridge";
import { disconnectedModel, failedModel, normalizeSnapshot } from "../state";
import type { ControlModel } from "../types";

export type OperatorErrorKind = "mutation" | "refresh" | "window";

export interface OperatorErrorState {
  readonly kind: OperatorErrorKind;
  readonly message: string;
}

export interface UseSnapshotPollResult {
  readonly model: ControlModel;
  readonly refreshing: boolean;
  readonly refresh: () => Promise<void>;
  readonly operatorError: OperatorErrorState | null;
  readonly setOperatorError: Dispatch<SetStateAction<OperatorErrorState | null>>;
}

export const useSnapshotPoll = (refreshIntervalMs: number): UseSnapshotPollResult => {
  const [model, setModel] = useState<ControlModel>(() => disconnectedModel("Awaiting local control bridge."));
  const [refreshing, setRefreshing] = useState(false);
  const [operatorError, setOperatorError] = useState<OperatorErrorState | null>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async (): Promise<void> => {
    if (refreshInFlight.current) {
      return;
    }
    refreshInFlight.current = true;
    setRefreshing(true);
    try {
      const raw = await readControlState();
      setModel(normalizeSnapshot(raw));
      setOperatorError((current) => current?.kind === "mutation" ? current : null);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown local control bridge error.";
      setModel(failedModel(error instanceof BridgeUnavailableError ? "UNAVAILABLE" : "ERROR", message));
      setOperatorError((current) => current?.kind === "mutation"
        ? current
        : { kind: "refresh", message });
    } finally {
      refreshInFlight.current = false;
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const onBridgeReady = (): void => {
      void refresh();
    };
    window.addEventListener("pywebviewready", onBridgeReady);
    void refresh();
    const refreshTimer = window.setInterval(() => void refresh(), refreshIntervalMs);
    return () => {
      window.removeEventListener("pywebviewready", onBridgeReady);
      window.clearInterval(refreshTimer);
    };
  }, [refresh, refreshIntervalMs]);

  return { model, refreshing, refresh, operatorError, setOperatorError };
};
```

- [ ] **Step 2: Create `src/components/ContextBar.tsx` with this exact content** (markup moved verbatim from `App.tsx` lines 294–306)

```tsx
import { displayLabel, formatTimestamp } from "../state";
import type { DopeySnapshot } from "../types";

export interface ContextBarProps {
  readonly snapshot: DopeySnapshot;
  readonly staleSourceCount: number;
  readonly evidenceHash: string | null;
  readonly density: "dense" | "comfortable";
  readonly textScale: "100" | "115" | "130";
  readonly highContrast: boolean;
  readonly onCycleDensity: () => void;
  readonly onCycleTextScale: () => void;
  readonly onToggleContrast: () => void;
}

export const ContextBar = ({
  snapshot,
  staleSourceCount,
  evidenceHash,
  density,
  textScale,
  highContrast,
  onCycleDensity,
  onCycleTextScale,
  onToggleContrast,
}: ContextBarProps) => (
  <div className="global-context-bar" aria-label="Global analytical context">
    <div><span>UNIVERSE</span><strong>{snapshot.universe.activeCount ?? "—"} / {snapshot.universe.targetCount ?? "—"}</strong></div>
    <div><span>TIMEFRAME</span><strong>MULTI-HORIZON</strong></div>
    <div><span>AS OF</span><strong>{formatTimestamp(snapshot.generatedUtc)}</strong></div>
    <div><span>EVIDENCE CLASS</span><strong>{displayLabel(snapshot.analytics.evidence.evidenceClass)}</strong></div>
    <div><span>FRESHNESS</span><strong>{staleSourceCount === 0 ? "ALL REPORTED CLEAR" : `${staleSourceCount} NEED REVIEW`}</strong></div>
    <div><span>RUN HASH</span><strong title={evidenceHash ?? "Hash unavailable"}>{evidenceHash?.slice(0, 12) ?? "UNAVAILABLE"}</strong></div>
    <div className="appearance-controls" aria-label="Display preferences" role="group">
      <button aria-pressed={density === "comfortable"} onClick={onCycleDensity} type="button">{density === "dense" ? "COMFORT" : "DENSE"}</button>
      <button aria-label="Cycle text size" onClick={onCycleTextScale} type="button">TEXT {textScale}%</button>
      <button aria-pressed={highContrast} onClick={onToggleContrast} type="button">CONTRAST</button>
    </div>
  </div>
);
```

- [ ] **Step 3: Rewire `App.tsx`**

Remove from `App.tsx`: the local `OperatorErrorKind`/`OperatorErrorState` declarations (lines 42–47), the `model`/`refreshing`/`operatorError` state declarations (lines 50, 52, 54), `refreshInFlight` (line 59), the `refresh` callback (lines 109–129), and the polling effect (lines 131–142). Add:

```ts
import { ContextBar } from "./components/ContextBar";
import { useSnapshotPoll } from "./hooks/useSnapshotPoll";
```

and inside `App()`, immediately after the remaining state declarations:

```ts
const { model, refreshing, refresh, operatorError, setOperatorError } = useSnapshotPoll(REFRESH_INTERVAL_MS);
```

Replace the inline `<div className="global-context-bar" …>…</div>` block with:

```tsx
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
```

Remove imports that are now unused (`BridgeUnavailableError`, `readControlState`, `disconnectedModel`, `failedModel`, `normalizeSnapshot` — `npm run typecheck` will confirm the exact list; keep `formatTimestamp` if still used by the command strip, keep everything else that is still referenced).

- [ ] **Step 4: Verify** — `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` pass; compare `#command` and one secondary view against the PNGs (the context bar and footer must be pixel-identical).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src && git commit -m "Extract snapshot polling hook and context bar from App"
```

---

### Task 4: Dev-mode mock bridge (real UI in `npm run dev`)

**Files:**
- Create: `desktop/src/dev/mockBridge.ts`
- Modify: `desktop/src/main.tsx`
- Modify: `desktop/package.json` (add one script)

**Interfaces:**
- Consumes: `desktop/visual-qa/control-state.json` (3.7 MB fixture, already in repo; same source `tools/generate_visual_qa.mjs` uses).
- Produces: `installMockBridge(): void`, dev-only. Mirrors the QA harness semantics exactly: `get_state` → whole fixture; `get_symbol_lab` → `fixture.visual_qa_symbol_lab`; `get_chart` / `get_chart_coach` → throw `qa_fixture_*_not_loaded`; every mutation → throw `qa_fixture_read_only`.

Why `?raw`: the CSP is `connect-src 'none'`, so no dev fetch; a JSON module import would sit outside `tsconfig.app.json`'s `"include": ["src"]`; a `?raw` import is typed by `vite/client`'s ambient wildcard declaration (already referenced in `src/vite-env.d.ts`) and never touches the TS file list. The dynamic `import()` plus `import.meta.env.DEV` guard keeps the 3.7 MB fixture out of the production bundle (Rollup eliminates the dead branch).

- [ ] **Step 1: Create `src/dev/mockBridge.ts` with this exact content**

```ts
import fixtureRaw from "../../visual-qa/control-state.json?raw";

interface MockFixture {
  readonly visual_qa_symbol_lab?: unknown;
}

let cachedFixture: MockFixture | null = null;

const loadFixture = (): MockFixture => {
  if (cachedFixture === null) {
    cachedFixture = JSON.parse(fixtureRaw) as MockFixture;
  }
  return cachedFixture;
};

const rejected = async (): Promise<never> => {
  throw new Error("qa_fixture_read_only");
};

export const installMockBridge = (): void => {
  if (window.pywebview !== undefined) {
    return;
  }
  window.pywebview = {
    api: {
      get_state: async () => loadFixture(),
      get_chart: async () => { throw new Error("qa_fixture_chart_not_loaded"); },
      get_chart_coach: async () => { throw new Error("qa_fixture_coach_not_loaded"); },
      get_symbol_lab: async () => loadFixture().visual_qa_symbol_lab ?? null,
      set_instrument_mode: rejected,
      set_llm_provider: rejected,
      set_openrouter_api_key: rejected,
      set_options_execution: rejected,
      set_research_core: rejected,
      minimize_window: rejected,
      toggle_maximize_window: rejected,
      close_window: rejected,
    },
  };
};
```

- [ ] **Step 2: Replace `src/main.tsx` with this exact content** (App import stays static so production bundling is unchanged; render is deferred until the mock is installed so the first poll sees it)

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("DOPEY desktop root element is missing.");
}

const render = (): void => {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
};

if (import.meta.env.DEV) {
  void import("./dev/mockBridge").then(({ installMockBridge }) => {
    installMockBridge();
    render();
  });
} else {
  render();
}
```

- [ ] **Step 3: Add the QA script to `package.json`** — inside `"scripts"`, after `"preview"`, add:

```json
    "qa:visual": "npm run build && node tools/generate_visual_qa.mjs"
```

(keep the existing trailing-comma style valid JSON).

- [ ] **Step 4: Verify dev loop** — `npm run typecheck` clean; `npm run dev`, open `http://127.0.0.1:4173`, confirm the full app renders with fixture data (Command Center populated, `#market` boards populated) instead of "Awaiting local control bridge"; stop the dev server.

- [ ] **Step 5: Verify production purity** — `npm run build` clean, then `grep -c 'visual_qa_symbol_lab' dist/index.html` → expect `0`, and `grep -c 'equity_curve' dist/index.html` → expect `0` (fixture is not shipped). `node tools/generate_visual_qa.mjs` still prints `"status":"pass"`.

- [ ] **Step 6: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src desktop/package.json && git commit -m "Add dev-only mock bridge so npm run dev renders the real app"
```

---

### Task 5: Dissolve `styles.css` into a layered architecture (pure move)

**Files:**
- Create: `desktop/src/styles/base.css`, `chrome.css`, `components.css`, `analytics.css`, `utilities.css`
- Create: `desktop/src/styles/views/command.css`, `market.css`, `chart.css`, `symbol-lab.css`, `playbook.css`, `evidence.css`, `truth.css`, `organisms.css`, `evolution.css`, `paper.css`, `constitution.css`
- Modify: `desktop/src/styles.css` (becomes the import manifest)

**Interfaces:**
- Produces: the fixed layer order that Tasks 6–7 and all later phases edit within: `base → chrome → components → analytics → utilities → views/*`.
- Rule for this task: **not one declaration changes**. Rules move whole and unmodified; relative order inside each destination file matches the original file order. This is what keeps the cascade (and the visual QA diff) exact.

Destination mapping (match on the rule's first class/element selector; longest prefix wins):

| Selector prefix | Destination |
|---|---|
| `:root`, `*`, `html`, `body`, `#root`, `button`, `input`, `textarea`, `select`, `::selection`, `@media (prefers-reduced-motion)` global blocks, `@media (prefers-contrast)` | `styles/base.css` |
| `.app-shell`, `.title-bar`, `.nav-`, `.command-strip`, `.global-context-bar`, `.appearance-controls`, `.status-footer`, `.command-palette`, `.palette-`, `.main-surface`, `.view-stage`, `.operator-error` | `styles/chrome.css` |
| `.instrument-panel`, `.empty-state`, `.eyebrow`, `.view-header`, `.dataset-`, `.status-cell`, `.status-dot`, `.truth-rail`, `.worldline`, `.organism-spine`, `.confidence-`, `.schedule-`, `.source-freshness`, `.universe-`, `.boundary-` | `styles/components.css` |
| `.analytics-`, `.visualization-`, `.fold-`, `.robustness-`, `.pareto-`, `.equity-`, `.underwater-`, `.readiness-lanes`, `.ml-`, `.paper-risk`, `.options-surface`, `.regime-intel` | `styles/analytics.css` |
| `.sr-only`, generic `.tone--*` utilities | `styles/utilities.css` |
| `.command-grid`, `.execution-seal`, `.neural-`, `.research-core`, `.live-branch`, `.metacognition`, `.organism-field` | `styles/views/command.css` |
| `.market-`, `.extreme-`, `.four-tail` | `styles/views/market.css` |
| `.chart-`, `.candle`, `.coach-`, `.indicator-`, `.pattern-`, `.overlay-` | `styles/views/chart.css` |
| `.lab-`, `.scenario-`, `.expression-`, `.strategy-`, `.meta-plan` | `styles/views/symbol-lab.css` |
| `.playbook-`, `.prediction-`, `.inspector-` | `styles/views/playbook.css` |
| `.evidence-`, `.dossier-`, `.genealogy-`, `.mutation-`, `.node-inspector`, `.crr-`, `.settlement-`, `.economics-` | `styles/views/evidence.css` |
| `.truth-`, `.readiness-`, `.threshold-`, `.check-`, `.issue-`, `.numbered-ledger` | `styles/views/truth.css` |
| `.organism-view-grid` | `styles/views/organisms.css` |
| `.evolution-`, `.selection-field`, `.promotion-stack`, `.family-budget` | `styles/views/evolution.css` |
| `.paper-grid`, `.paper-book`, `.book-`, `.position-` | `styles/views/paper.css` |
| `.constitution-`, `.law-list` | `styles/views/constitution.css` |

Disambiguation: `.organism-spine` → `components.css` (shared instrument), `.organism-view-grid` → `views/organisms.css`; `.paper-risk` → `analytics.css`, other `.paper-*` → `views/paper.css`; `.readiness-lanes` → `analytics.css`, other `.readiness-*` → `views/truth.css`. Any selector matched by no row goes to `components.css` under a trailing `/* UNCLASSIFIED — triage in Task 7 */` comment.

- [ ] **Step 1: Confirm the baseline** — `grep -o '{' src/styles.css | wc -l` equals the `BASELINE_BRACES` recorded in "Before you begin".

- [ ] **Step 2: Partition the file** — work top-to-bottom through `src/styles.css`; cut each rule (including its enclosing `@media` block when the whole block belongs to one destination — if a media block spans destinations, split it so each destination receives its own complete `@media` wrapper) into the destination file from the mapping table. Keep original order within each file. Do not edit declaration contents, do not delete comments that sit inside rules; standalone section comments travel with the rules that follow them.

- [ ] **Step 3: Write the manifest** — `src/styles.css` becomes exactly:

```css
@import "./styles/base.css";
@import "./styles/chrome.css";
@import "./styles/components.css";
@import "./styles/analytics.css";
@import "./styles/utilities.css";
@import "./styles/views/command.css";
@import "./styles/views/market.css";
@import "./styles/views/chart.css";
@import "./styles/views/symbol-lab.css";
@import "./styles/views/playbook.css";
@import "./styles/views/evidence.css";
@import "./styles/views/truth.css";
@import "./styles/views/organisms.css";
@import "./styles/views/evolution.css";
@import "./styles/views/paper.css";
@import "./styles/views/constitution.css";
```

- [ ] **Step 4: Brace-count audit** — `cat src/styles/*.css src/styles/views/*.css | grep -o '{' | wc -l` must equal `BASELINE_BRACES`. A mismatch means a rule was dropped or duplicated; find it with `git diff --stat` and by re-counting per file before proceeding.

- [ ] **Step 5: Verify** — `npm run build && node tools/generate_visual_qa.mjs` pass (typecheck is unaffected by CSS but run it anyway); compare `#command`, `#chart`, `#lab`, `#playbook`, `#evidence`, `#market` against the PNGs. Zero drift.

- [ ] **Step 6: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src && git commit -m "Dissolve monolithic stylesheet into layered CSS architecture"
```

---

### Task 6: Consolidate design tokens (`styles/tokens.css`)

**Files:**
- Create: `desktop/src/styles/tokens.css`
- Modify: `desktop/src/styles/base.css` (give up the `:root` block), `chrome.css` (give up mid-file token definitions), `desktop/src/styles.css` (import tokens first)

**Interfaces:**
- Produces: `styles/tokens.css` as the **only** file containing custom-property definitions (`--*:`). Later phases consume and extend these tokens; P2 fixes the text-scale wiring on top of this layout.
- Values do not change in this task — consolidation only.

- [ ] **Step 1: Move the `:root` block** — the `:root { … }` block (graphite/hairline/limestone/muted/dim/accent/panel/font tokens, originally `styles.css:1-28`, now at the top of `styles/base.css`) moves verbatim into `styles/tokens.css`.

- [ ] **Step 2: Move the mid-file token definitions** — locate (they landed in `chrome.css` or `base.css` after Task 5; find with `grep -rn -- '--space-1:\|--surface-blue:\|--app-text-scale: 1' src/styles/`) and move into `tokens.css`, verbatim and in this order after the `:root` block: the `--space-1…--space-5` and `--surface-blue/amber/red` definitions (originally `styles.css:2105-2123`), the `.app-shell` `--app-text-scale` rules including the `data-text-scale` variants (originally `:2136-2143`), the `.app-shell[data-contrast="high"]` remap (`:2145-2159`), and the `.app-shell[data-density="comfortable"]` remap blocks (`:2161-2173`).

- [ ] **Step 3: Import tokens first** — add `@import "./styles/tokens.css";` as the **first** line of `src/styles.css` (before `base.css`).

- [ ] **Step 4: Audit** — `grep -rn -- '^\s*--[a-z0-9-]*:' src/styles/ src/styles/views/ | grep -v 'tokens.css'` → report every hit; the only acceptable remainder is `--app-text-scale` nowhere (it moved) and genuinely component-local custom properties set from inline styles (e.g. `--x`, `--width` style hooks) — list them in the commit body. `grep -c '{' src/styles/tokens.css` sanity check: non-zero, and total braces across all files still equal `BASELINE_BRACES`.

- [ ] **Step 5: Verify** — `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` pass; compare `#command` and `#truth` (heavy token consumers) against PNGs. Zero drift.

- [ ] **Step 6: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src && git commit -m "Consolidate all design tokens into styles/tokens.css"
```

---

### Task 7: CSS dedupe — remove exact duplicates, dead breakpoints, cascade patches

**Files:**
- Modify: `desktop/src/styles/base.css`, `chrome.css`, `views/command.css`, `views/playbook.css` (only the files holding the blocks below)

**Interfaces:**
- Consumes: the Task 5/6 layout.
- Produces: a cascade with one source of truth per rule. `!important` removal is **not** in this task (each surviving `!important` is removed by the phase that redesigns its selectors); the two inside the playbook reduced-motion block stay for now.

- [ ] **Step 1: Delete the phantom-font `body` rule** — find `body { font-family: "Atkinson Hyperlegible Next", … }` (originally `styles.css:2132-2134`, now in `base.css`) and delete it. That font is never loaded (CSP `font-src 'self'`, no font files); the effective stack stays the `:root` one. `grep -rn 'Atkinson' src/` → 0 hits.

- [ ] **Step 2: Resolve the `html, body, #root` min-size conflict** — two blocks exist: the early one sets `min-width: 1024px; min-height: 720px` (originally `:34-43`), a later one resets both to `0` (originally `:2125-2130`) and currently wins. Preserve today's computed behavior: delete the two `min-*` declarations from the early block, then delete the later reset block entirely.

- [ ] **Step 3: Deduplicate `focus-visible`** — two definitions exist (originally `:62-66` and `:5155-5159`). Diff them first (`grep -n -A4 'focus-visible' src/styles/base.css src/styles/chrome.css src/styles/components.css`): keep exactly one rule whose declarations equal the *later* (currently winning) block; delete both originals and place the survivor in `base.css` next to the other interaction base rules.

- [ ] **Step 4: Fold the "Final adaptive override" patch section** (originally `:6778-6828`; landed at the end of `views/command.css` and/or `chrome.css`) — move `.main-surface { grid-template-columns: minmax(0, 1fr); }` into `chrome.css` beside the other `.main-surface` rules, the `.command-grid__seal > .execution-seal--compact` and `.execution-seal--compact …` rules into `views/command.css` beside the other execution-seal rules, and the `@media (max-width: 1120px)` `.command-grid` block into `views/command.css`. Delete the `/* Final adaptive override … */` comment.

- [ ] **Step 5: Remove unreachable breakpoints** — the host window minimum is 1024×720, so `@media (max-width: Npx)` blocks with N < 1000 can never match. List them: `grep -rn 'max-width' src/styles/ src/styles/views/`; delete each block with N < 1000 (known: the `@media (max-width: 820px)` block from the old patch section, plus any 375/700px blocks Task 5 scattered). Keep N ≥ 1000 (e.g. 1120px) untouched. Note every deleted block's selector in the commit body.

- [ ] **Step 6: Verify** — `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` pass; compare all eleven views at default width plus a manual 1024×720 window check of `#command` and `#playbook` (open `visual-qa/index.html`, resize the browser). Zero drift at ≥1024px.

- [ ] **Step 7: Commit**

```bash
cd /c/Users/CH/dopey && git add desktop/src && git commit -m "Remove duplicate CSS rules, dead breakpoints, and cascade patches"
```

---

## Phase 1 completion check

- [ ] All seven tasks committed; `git log --oneline -7` shows the sequence.
- [ ] `npm run typecheck && npm run build && node tools/generate_visual_qa.mjs` pass from a clean tree.
- [ ] `npm run dev` renders the full fixture-backed app at `http://127.0.0.1:4173`.
- [ ] `grep -o '{' src/styles.css | wc -l` reports only the manifest (0), and the layered files' combined count equals `BASELINE_BRACES` minus the duplicates deliberately removed in Task 7 (list them).
- [ ] Report the before/after PNG comparison notes to the user, then write the Phase 2 plan (readability & accessibility) from the spec's §9.
