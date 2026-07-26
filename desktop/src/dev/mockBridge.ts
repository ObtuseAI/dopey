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
