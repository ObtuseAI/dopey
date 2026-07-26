# DOPEY Control Center — UI/UX Redesign Design ("Refined Instrument")

Date: 2026-07-25
Status: Approved direction (brainstorm); pending implementation plan
Scope: `desktop/` frontend only. No backend, bridge, or evidence-contract changes.

## 1. Context

The DOPEY Control Center desktop app (`desktop/`) is a React 19 + Vite + TypeScript
operator console for the trading-research system. It is deliberately engineered around
evidence integrity: zero runtime dependencies (react/react-dom only), a single-file
inlined bundle with sha256 CSP hashes (`tools/inline_frontend.mjs`), `connect-src 'none'`,
`font-src 'self'`, a hand-rolled SVG chart runtime, and governance "boundary" chrome
(PAPER-ONLY // LIVE-BLOCKED rails, hash pins, seal states) on every surface. The Python
pywebview host loads `dist/index.html` from disk; the typed bridge (`src/bridge.ts`) is
read-mostly with confirmation-gated mutations. Eleven surfaces are served from
`src/viewMetadata.ts` (Command, Market, Chart, Symbol Lab, Playbook, Evidence, Truth,
Evolution, Paper, Organisms, Constitution).

A full UI/UX review (2026-07-25) found the app functionally rich and philosophically
distinctive, but held back by:

- **CSS architecture collapse** — one 6,828-line global stylesheet with duplicate base
  rules (two conflicting `body` font stacks at `styles.css:4` and `:2132`, two
  `focus-visible` definitions at `:62-66` and `:5155-5159`), a cascade-by-append
  "Final adaptive override" patch section (`:6778-6828`), and 27 `!important`s.
- **Token failure** — ~20 tokens vs 2,328 raw px values (169 unique); dozens of
  hard-coded near-duplicate hexes drifting from tokens; retheming is impossible.
- **Readability floor** — 308 font-size declarations at 8–10px, all-caps mono for long
  prose, borderline dim contrast; the user-facing TEXT 115/130% control is broken
  (`--app-text-scale` consumed exactly once at `styles.css:2139`).
- **Interaction gaps** — global `user-select: none` (`styles.css:48`) blocks copying
  hashes/prices; command palette never restores focus on close; ARIA tabs lack keyboard
  semantics; Symbol Lab shows stale results while sliders draft.
- **Chart ceiling** — fixed 1000×455 viewBox, no zoom/pan/crosshair, first/last-only
  date labels, truncated markers (`ChartView.tsx:84,93-99,145,161-164`).
- **Structural coupling** — six views + six sub-components crammed into
  `SecondaryViews.tsx` (433 lines); status→tone mapping re-implemented 5–6 times with
  subtly different rules; `MutationGenealogyPanel` imported across view files.
- **Dev-loop friction** — `npm run dev` renders only the "Awaiting local control bridge"
  shell; real-data preview requires a full release build + fixture regeneration.
- **Ornamental design system** — `design-system/dopey-control-center/MASTER.md` is a
  generic template that does not describe this app (wrong category, light palette,
  fonts that violate CSP); `pages/` is empty.

## 2. Hard constraints (must be preserved)

1. **Evidence-first identity.** Boundary rails, hash pins, seal states, "evidence, not
   probability" disclaimers stay visible on every surface. The redesign must make DOPEY
   more itself, not a generic trading terminal.
2. **Evidence contract.** No network calls from the frontend (CSP `connect-src 'none'`),
   no external fonts (`font-src 'self'`), no third-party chart runtime, no synthetic
   chart data. Chart requests keep hash-pinned revalidation messaging.
3. **Zero runtime dependencies.** Only react/react-dom ship. Build-time devDependencies
   are acceptable but not anticipated to be needed.
4. **Bridge API and snapshot contract unchanged.** All mutations remain
   confirmation-gated; the frontend consumes existing snapshot fields only. No backend
   changes.
5. **Build pipeline unchanged** — `tsc -b && vite build && node tools/inline_frontend.mjs`;
   Node 24.15.0 / npm 11.14.1 pins.
6. **AGENTS.md rules** — credentials redacted from UI state; evidence classes never
   relabeled.
7. **Host window realities** — frameless, min 1024×720; breakpoints below 1024px are
   dead code and will be removed, not fixed.

## 3. Design direction

**Refined Instrument, executed at modern-SaaS polish level.** Keep the graphite-green
dark identity, hairline borders, mono-for-data, and panel codes that make DOPEY
recognizable — rebuild the craft: a real token system, a modular type scale, calm
density, one status language, complete keyboard support, and motion with meaning.
Chosen over (B) neutral modern-fintech reskin, which discards the identity, and (C)
glass/glow command deck, which risks gimmick and readability.

### Design principles

1. **Evidence first, always visible** — boundary, provenance, and staleness are
   first-class layout elements, never footnotes.
2. **Readable by default** — 12px base, sentence case, real hierarchy; uppercase only
   for eyebrow micro-labels.
3. **Calm density** — information-rich but breathable; density is a working user
   preference, not a survival strategy.
4. **One voice** — one status→tone system, one timestamp format, one panel grammar
   across all 11 surfaces.
5. **Keyboard-complete** — every workflow reachable and reversible by keyboard.
6. **Motion with meaning** — subtle transitions for state change only, always
   `prefers-reduced-motion`-gated.

## 4. Approaches considered

### A. Token-first rebuild in place (recommended)

Rebuild foundations (tokens, CSS architecture, shared helpers), then redesign
surface-by-surface in independent phases, each shippable and reviewable on its own.
The app works throughout; diffs stay scoped; the visual-QA harness verifies each phase.

- Pros: low risk; reviewable; each phase delivers visible value; no big-bang cutover.
- Cons: transitional inconsistency between done and pending surfaces; requires
  discipline to keep phases independent.

### B. Big-bang component rewrite

Rewrite all views and styles from scratch atop a new kit, cut over at once.

- Pros: cleanest end state; no transitional inconsistency.
- Cons: unreviewable diff; app broken or forked for the duration; high regression risk
  against evidence-chrome requirements; violates minimal-change discipline.

### C. Critical-fixes only

Tokens + the top five pain points (readability, user-select, focus restore, text-scale,
tone dedupe); leave structure and chart as-is.

- Pros: cheapest; immediate relief.
- Cons: leaves the 6,828-line stylesheet, SecondaryViews coupling, chart ceiling, and
  dev-loop pain in place; the "state of the art" goal is not met.

**Decision: A**, phased as in §9.

## 5. Design

### 5.1 Token system (`styles/tokens.css`)

- **Color, layered surfaces:** `--bg-0` (#050806) through `--bg-3` (#17231c) retained
  and formalized; hairline `--line` / `--line-strong`.
- **Text:** `--text` (#d8e6dc), `--text-dim` raised from #6f8378 to ≈#7d9184 so dim
  text meets ≥4.5:1 at 11px; `--text-faint` reserved for non-essential metadata.
- **Semantic tones (single source):** `--tone-ok` celadon #76f0a6, `--tone-warn` ochre
  #f1bd62, `--tone-danger` vermilion #ff6d61, `--tone-info` cyan, `--tone-accent`
  violet; each with a `-dim` background variant for badges. All status colors in all
  views consume these — near-duplicate hard-coded hexes (#efbd58, #ff8173, …) deleted.
- **Data-series palette:** 8 categorical colors, checked for deuteranopia
  distinguishability, used by charts/graphs only.
- **Type:** `--font-ui` Segoe UI Variable Display stack, `--font-mono` Cascadia Mono
  stack (both CSP-legal system fonts; the phantom "Atkinson Hyperlegible Next"
  declaration at `styles.css:2132` is removed). Modular scale: 11 / 12 / 13 / 16 / 20 /
  28px via `--text-xs…--text-xxl`; `--text-micro` 10px uppercase +0.08em tracking for
  eyebrow labels only. Root font-size driven by `--app-text-scale` so the TEXT
  100/115/130% control scales everything (all component sizes in rem).
- **Spacing:** 4px grid, `--space-1` (4px) … `--space-12` (48px); raw px spacing banned
  outside tokens (1px hairlines excepted).
- **Radius/elevation:** `--radius-1` 2px, `--radius-2` 4px; elevation = hairline +
  subtle fill change (no heavy shadows — not the identity).
- **Focus/motion:** single `--focus-ring` token; `--dur-fast` 120ms, `--dur-med` 200ms,
  `--ease-standard`; all motion wrapped in `prefers-reduced-motion` checks.
- **Remaps:** `data-contrast="high"` and `data-density="comfort|dense"` become pure
  token remaps (they already exist at `styles.css:2145-2171`; they are preserved and
  extended to cover every token).

### 5.2 CSS architecture

`styles.css` (6,828 lines) is dissolved into layered imports:

```
src/styles/tokens.css        tokens + contrast/density remaps
src/styles/base.css          reset, body (one font stack), selection, focus-visible (one rule)
src/styles/chrome.css        titlebar, nav rail, context bar, command palette
src/styles/components.css    InstrumentPanel, EmptyState, tables, badges, buttons, forms, switch
src/styles/views/<name>.css  one file per view (11 files, each < 600 lines)
src/styles/utilities.css     sr-only, tone utilities
```

`src/styles.css` becomes an `@import` manifest in fixed order. Rules: zero `!important`
(current 27 removed by fixing specificity at the source); no duplicate selectors; the
"Final adaptive override" section folded into proper files; dead <1024px breakpoints
removed; 1024–1540px adaptive behavior kept in the view files that own it.

### 5.3 Typography & readability

- Sentence case everywhere; uppercase only for eyebrow micro-labels.
- Hero numerals (buying power, key metrics) at 20–28px; data tables 12px mono with
  tabular figures; body/prose (two-coach analyses, dossier text) 12–13px, line-height
  1.5, measure ≤72ch.
- `user-select: text` global default; `none` only on buttons, the hold switch, and nav.
- One timestamp format (`formatTimestamp` relative-ish style) everywhere; raw ISO
  headers in Evidence/Organisms (`EvidenceView.tsx:39`) replaced; exact ISO available
  on hover/title.

### 5.4 Navigation & information architecture

- Nav rail: Monitor / Research / Governance groups get visual separators + group
  labels; primary surfaces (Command, Market, Chart, Lab, Playbook) get 40px targets,
  secondary 32px; `aria-current` kept; seal footer and issue badge retained.
- Standardized view header: title, as-of timestamp, staleness chip, primary action —
  implemented once in a `ViewHeader` component and adopted by all 11 views.
- Command palette (`CommandPalette.tsx`): focus restored to the trigger on close
  (fixes `App.tsx:60,280` dead ref); results grouped by nav group; recent-view ordering.
- Hash routing kept; `document.title` reflects current view.

### 5.5 Surface notes

- **Command:** hero row = Research Core switch + Live Branch; truth rail / worldline /
  organism spine condensed into one "system strip"; source freshness becomes a single
  chip row; unavailable-capability panels lose above-the-fold placement (collapsed
  below primary content).
- **Market:** four-tail boards become proper tables (numeric right-alignment, sortable
  columns); regime summary strip on top.
- **Symbol Lab:** draft/run split made honest — when sliders diverge from the run, the
  results header shows a "stale — reprice" chip; slider readouts preview the drafted
  delta; REPRICE & RERANK stays the explicit commit.
- **Playbook:** one card grammar for every ranked list (rank, symbol, direction, setup,
  evidence meter, boundary); the evidence inspector opens as a side panel instead of
  displacing the list; `aria-live` selection announcements kept.
- **Evidence:** genealogy graph gets a legend and pan/zoom (SVG transform, no library);
  unified timestamps.
- **Truth / Evolution / Paper / Organisms / Constitution:** split out of
  `SecondaryViews.tsx` into one file per view; `DatasetTable` gains sort + filter;
  ConstitutionView keeps its static law copy but is explicitly labeled a static
  summary (no snapshot field exists; backend unchanged).

### 5.6 Chart workbench

Hand-rolled SVG runtime retained (constraint); the component is rebuilt:

- `ResizeObserver`-driven fluid sizing; viewBox computed from container, replacing the
  fixed 1000×455 with hard-coded paddings (`ChartView.tsx:93-99`).
- Crosshair with OHLC/volume legend readout (replaces `<title>`-only tooltips at `:145`).
- Wheel zoom + drag pan with clamping; double-click reset.
- Adaptive x-axis date ticks and nice-number y grid (replaces first/last-only labels at
  `:161-164`); magic scales (`candleWidth` clamp at `:118`, `pathPnl * 18` at
  `AnalyticsVisuals.tsx:462`) replaced with computed scales.
- Indicator matrix: all 62 indicators reachable via searchable popover (24-of-62
  hard cutoff removed); pattern markers get a legend instead of 18-char truncated
  labels (`:84`).
- Hash-pinned revalidation messaging stays visible.
- Two-coach panel: prose typography (§5.3), skeleton while coaching, selectable text.

### 5.7 Interaction patterns

- **Hold-to-confirm:** kept as-is (pointer capture, Escape cancel, focus return — it is
  genuinely good); adds an `aria-live` progress announcement for screen readers.
- **Loading:** skeleton rows matching final layout (no layout shift) for chart, lab,
  playbook; existing busy labels kept.
- **Error:** banners keep `role="alert"`; idempotent bridge reads get a Retry action;
  raw ALL-CAPS strings mapped to plain language with a detail disclosure.
- **Stale data:** global as-of + per-panel staleness chips; the 15s poll gets a subtle
  pulse in the context bar so refreshes are perceptible.
- **Copy:** every hash/price/timestamp selectable; long hashes get click-to-copy with
  toast confirmation (formalizing the COPY HASH workaround at `ChartView.tsx:507`).

### 5.8 Accessibility

- WCAG 2.2 AA: text ≥4.5:1, large text/UI ≥3:1 at the new sizes; dim-token raise (§5.1);
  verify every tone on `--bg-0`.
- ARIA tabs pattern completed for `VisualizationFrame` (Left/Right/Home/End,
  `aria-selected`, roving tabindex — `AnalyticsVisuals.tsx:115-129`).
- Single `focus-visible` definition; palette focus restore; hold-confirm focus return
  retained.
- TEXT scale fixed via root rem; DENSITY and CONTRAST preferences verified end-to-end;
  reduced-motion audit of every animation.

### 5.9 Dev workflow

- `src/dev/mockBridge.ts`: dev-only (`import.meta.env.DEV`) read-only mock of
  `window.pywebview.api` backed by `visual-qa/control-state.json`, so `npm run dev`
  renders the full app; mutations throw `qa_fixture_read_only`, matching the QA harness
  (`tools/generate_visual_qa.mjs` semantics).
- `npm run qa:fixture` script wrapping the existing fixture generator; visual-QA PNG
  review flow documented in `desktop/README.md`.

### 5.10 Component refactors (enablers)

- `src/lib/tone.ts`: single status→tone mapping; the 5–6 divergent duplicates
  (`ChartView.tsx:43-50`, `SymbolLabView.tsx:27-31`, `EvidenceView.tsx:17-29`,
  `SecondaryViews.tsx:29-49`, `AnalyticsVisuals.tsx:54-66`, `PlaybookView.tsx:80-88`)
  deleted.
- `SecondaryViews.tsx` split into `views/MarketView.tsx`, `OrganismsView.tsx`,
  `TruthView.tsx`, `EvolutionView.tsx`, `PaperView.tsx`, `ConstitutionView.tsx`;
  `MutationGenealogyPanel` moved to `components/`; the stray `severityClass` export
  removed.
- `App.tsx`: poll loop extracted to `useSnapshotPoll()`; context bar extracted to
  `components/ContextBar.tsx`.

## 6. What does not change

Bridge API and snapshot contract; CSP; build/inline pipeline; Python host; boundary /
evidence rendering requirements; hold-to-confirm semantics; zero runtime deps;
`viewMetadata.ts` surface set and shortcuts.

## 7. Success criteria

- `npm run typecheck` and `npm run build` clean; visual-QA harness regenerates.
- No text below 11px except 10px eyebrow micro-labels; dim text ≥4.5:1 (verified on
  `--bg-0`); manual AA pass on all 11 surfaces.
- Zero `!important` in `src/styles/`; grep audit shows no raw hex colors outside
  `tokens.css`; no raw px spacing outside tokens.
- `npm run dev` renders the full app via the mock bridge with fixture data.
- Every surface keyboard-operable (tab-through + shortcuts + palette) at 1024×720.
- Any hash, price, or timestamp is selectable; long hashes copy on click with toast.
- TEXT 100/115/130 visibly scales the whole app; COMFORT/DENSE and CONTRAST verified.

## 8. Out of scope

Backend or bridge changes; new surfaces; charting-library adoption; light theme;
layouts below 1024px; i18n; packaging/installer changes.

## 9. Phasing (input to the implementation plan)

- **P1 Foundations** — token system; CSS architecture split; `tone.ts`; SecondaryViews
  split; `useSnapshotPoll`/ContextBar extraction; dev mock bridge.
- **P2 Readability & accessibility** — type scale applied; sentence-case pass;
  user-select; unified focus system; tabs keyboard; TEXT-scale fix; timestamp unification.
- **P3 Chrome & navigation** — nav rail grouping, ViewHeader everywhere, palette
  grouping + focus restore, context-bar polish.
- **P4 Core surfaces** — Command, Market, Playbook, Evidence redesigns.
- **P5 Chart workbench & Symbol Lab** — fluid chart, crosshair, zoom/pan, indicator
  popover; lab stale-state honesty; two-coach typography.
- **P6 Polish & docs** — loading skeletons, error mapping, toast copy, reduced-motion
  audit, visual-QA regeneration, `design-system/…/MASTER.md` rewritten to document the
  real system.
