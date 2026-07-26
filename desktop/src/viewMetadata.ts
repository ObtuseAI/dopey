import type { ViewId } from "./types";

export interface ViewDefinition {
  readonly id: ViewId;
  readonly label: string;
  readonly shorthand: string;
  readonly title: string;
  readonly description: string;
  readonly shortcut: string;
  readonly group: "Monitor" | "Research" | "Governance";
}

export const VIEW_DEFINITIONS: readonly ViewDefinition[] = [
  { id: "command", label: "Command", shorthand: "CMD", title: "Command", description: "System posture, controls, schedules, and research boundaries.", shortcut: "Alt+1", group: "Monitor" },
  { id: "market", label: "Market Tissue", shorthand: "MKT", title: "Market tissue", description: "Regime context, worldline signals, and cross-market structure.", shortcut: "Alt+2", group: "Monitor" },
  { id: "chart", label: "Chart Intelligence", shorthand: "CHT", title: "Chart intelligence", description: "Evidence-aware price structure, overlays, and pattern telemetry.", shortcut: "Alt+3", group: "Monitor" },
  { id: "lab", label: "Symbol Lab", shorthand: "LAB", title: "Symbol lab", description: "Interactive symbol scenarios and strategy expression research.", shortcut: "Alt+4", group: "Research" },
  { id: "playbook", label: "Playbook", shorthand: "PLY", title: "Prediction playbook", description: "Ranked bullish and bearish prediction research across short and long horizons.", shortcut: "Alt+P", group: "Research" },
  { id: "organisms", label: "Organisms", shorthand: "ORG", title: "Organisms", description: "Agent status, roles, outputs, and observatory health.", shortcut: "Alt+5", group: "Research" },
  { id: "truth", label: "Truth", shorthand: "TRU", title: "Truth", description: "Forward-only evidence accrual and readiness constraints.", shortcut: "Alt+6", group: "Research" },
  { id: "evidence", label: "Evidence Dossier", shorthand: "EVD", title: "Evidence dossier", description: "Provenance, proof coverage, contradictions, and freshness.", shortcut: "Alt+7", group: "Research" },
  { id: "evolution", label: "Evolution", shorthand: "EVO", title: "Evolution", description: "Paper-only research generations, genealogy, and budgets.", shortcut: "Alt+8", group: "Research" },
  { id: "paper", label: "Paper Book", shorthand: "PPR", title: "Paper book", description: "Simulated exposure, positions, and paper outcomes.", shortcut: "Alt+9", group: "Research" },
  { id: "constitution", label: "Constitution", shorthand: "LAW", title: "Constitution", description: "Immutable authority boundaries and live-execution blocks.", shortcut: "Alt+0", group: "Governance" },
] as const;

export const isViewId = (candidate: string): candidate is ViewId =>
  VIEW_DEFINITIONS.some((view) => view.id === candidate);

export const viewDefinitionFor = (viewId: ViewId): ViewDefinition => {
  const definition = VIEW_DEFINITIONS.find((view) => view.id === viewId);
  if (definition === undefined) {
    throw new Error(`Unknown DOPEY desktop view: ${viewId}`);
  }
  return definition;
};
