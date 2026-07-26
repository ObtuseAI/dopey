import type { HeadCoachId, InstrumentMode, LlmProviderId, SymbolLabStrategyMode } from "./types";
export type ResearchScope = "paper_research_only";

const PROVIDER_CONFIRMATION = "paper_research_configuration";

interface PyWebViewApi {
  get_chart: (symbol: string, timeframe: string) => Promise<unknown>;
  get_chart_coach: (symbol: string, timeframe: string, headCoachId: HeadCoachId) => Promise<unknown>;
  get_symbol_lab: (
    symbol: string,
    strategyMode: SymbolLabStrategyMode,
    scenarioStockPrice: number | null,
    daysForward: number,
    ivShift: number,
  ) => Promise<unknown>;
  get_state: () => Promise<unknown>;
  set_instrument_mode: (instrumentMode: InstrumentMode, confirmation: string) => Promise<unknown>;
  set_llm_provider: (provider: LlmProviderId, enabled: boolean, confirmation: string) => Promise<unknown>;
  set_openrouter_api_key: (apiKey: string, confirmation: string) => Promise<unknown>;
  set_options_execution: (enabled: boolean, confirmation: string) => Promise<unknown>;
  set_research_core: (enabled: boolean, scope: ResearchScope) => Promise<unknown>;
  minimize_window: () => Promise<unknown>;
  toggle_maximize_window: () => Promise<unknown>;
  close_window: () => Promise<unknown>;
}

interface PyWebViewBridge {
  api: PyWebViewApi;
}

declare global {
  interface Window {
    pywebview?: PyWebViewBridge;
  }
}

export class BridgeUnavailableError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "BridgeUnavailableError";
  }
}

const requireApi = (): PyWebViewApi => {
  const api = window.pywebview?.api;
  if (api === undefined) {
    throw new BridgeUnavailableError("Local pywebview control bridge is not available.");
  }
  return api;
};

export const readControlState = async (): Promise<unknown> => requireApi().get_state();

export const readChartState = async (symbol: string, timeframe: string): Promise<unknown> =>
  requireApi().get_chart(symbol, timeframe);

export const readChartCoachState = async (
  symbol: string,
  timeframe: string,
  headCoachId: HeadCoachId,
): Promise<unknown> => requireApi().get_chart_coach(symbol, timeframe, headCoachId);

export const readSymbolLabState = async (
  symbol: string,
  strategyMode: SymbolLabStrategyMode,
  scenarioStockPrice: number | null,
  daysForward: number,
  ivShift: number,
): Promise<unknown> => requireApi().get_symbol_lab(
  symbol,
  strategyMode,
  scenarioStockPrice,
  daysForward,
  ivShift,
);

export const setResearchCore = async (enabled: boolean): Promise<unknown> =>
  requireApi().set_research_core(enabled, "paper_research_only");

export const setInstrumentMode = async (instrumentMode: InstrumentMode): Promise<unknown> =>
  requireApi().set_instrument_mode(instrumentMode, PROVIDER_CONFIRMATION);

export const setLlmProvider = async (provider: LlmProviderId, enabled: boolean): Promise<unknown> =>
  requireApi().set_llm_provider(provider, enabled, PROVIDER_CONFIRMATION);

export const updateOpenRouterApiKey = async (apiKey: string): Promise<unknown> =>
  requireApi().set_openrouter_api_key(apiKey, PROVIDER_CONFIRMATION);

export const setOptionsExecution = async (enabled: boolean): Promise<unknown> =>
  requireApi().set_options_execution(enabled, "owner_live_branch_control");

export const minimizeWindow = async (): Promise<void> => {
  await requireApi().minimize_window();
};

export const toggleMaximizeWindow = async (): Promise<void> => {
  await requireApi().toggle_maximize_window();
};

export const closeWindow = async (): Promise<void> => {
  await requireApi().close_window();
};
