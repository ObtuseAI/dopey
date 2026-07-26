# DOPEY Control Center desktop host

The desktop host wraps the compiled control-center interface in a native,
frameless Windows window using pywebview 6.2.1 and the installed Edge WebView2
runtime. It loads `desktop/dist/index.html` directly from disk. It does not
start a web server.

The exposed Python bridge is deliberately narrow:

- `get_state()` reads a fresh operator snapshot;
- `get_chart(symbol, timeframe)` reads bounded, hash-pinned real OHLCV and returns
  candlesticks, overlays, 62 versioned indicator states, probabilistic formations,
  and regular or hidden divergences for daily, weekly, or monthly views;
- `get_chart_coach(symbol, timeframe, head_coach_id)` runs the deterministic
  Evidence/Replay Coach plus exactly one explicitly selected `claude` or `codex`
  head coach; Claude is the default and uses the fixed four-model OpenRouter
  route, while Codex uses the existing read-only CLI adapter with no fallback;
- `get_symbol_lab(symbol, strategy_mode, scenario_stock_price, days_forward,
  iv_shift)` composes hash-pinned history, multi-timeframe levels, earnings,
  observed option-chain quotes, strategy-combination research, and scenario
  option values without mutating evidence or creating an order;
- `set_research_core(enabled, confirmation)` atomically enables or disables
  both allowlisted paper-automation schedules; a failed transition forces
  future starts back off and never terminates an active cycle;
- `set_instrument_mode(mode, confirmation)` selects stocks, options, or both
  for future paper-research expression;
- `set_options_execution(enabled, confirmation)` changes only the owner-custodied
  Live Branch options gate; stocks remain enabled and options start disabled;
- `set_llm_provider(provider, enabled, confirmation)` controls the single governed
  OpenRouter four-model hybrid research route; retired independent provider flags
  remain unavailable and are separate from the bounded chart head-coach selector;
- `set_openrouter_api_key(api_key, confirmation)` writes a key into Windows
  DPAPI user-scoped encrypted storage and never returns the plaintext value;
- `minimize_window()` and `toggle_maximize_window()` manage the native window;
  `close_window()` hides the window while the native tray remains active.
- The Windows tray menu restores DOPEY or explicitly exits the application.
- Windows notifications are deduplicated from the protected research-promotion
  artifact, canonical forward paper-trade ledger, and hash-chained Live Branch
  ledger. Existing records are baselined on first launch and never replayed as
  new activity. Live order-open and position-close events identify themselves as live.

There is no browser bridge for a shell, arbitrary filesystem access, credential
readback, or arbitrary order submission. The only credential mutation is the
write-only OpenRouter DPAPI operation above. Live Branch execution runs through
the typed scheduled service and official Robinhood MCP; the desktop can only
change the explicit options execution gate with owner confirmation. The protected
research boundary remains visible and is not controlled by the Live Branch.

The desktop has eleven surfaces. Command Center includes a live account panel with
authenticated state, buying power, position counts, stock/options gates, paper-twin
activity, and the zero-day-trade status. Market Tissue reads the scheduled playbook's
protected four-tail artifacts and presents separate stock-gainer,
stock-decliner, option-winner, and option-loser boards. Chart Intelligence is an
SVG-native market workbench with no third-party chart runtime and no network
dependency. Every chart request revalidates the governed real-history manifest;
synthetic data and direct desktop network fetches are rejected from the evidence
contract. Its two-coach panel sends a compact no-reveal projection of deterministic
structures, registered numeric facts, and eligible point-in-time trade lessons to
the selected head coach. Model-authored numbers and unknown references fail closed;
the UI resolves accepted reference tokens from the local registry. Replay outcomes,
broker authority, order construction, automatic strategy promotion, and option-P&L
claims from underlying-only OHLC remain outside the coach input and authority.

Prediction Playbook presents the five highest-priority overall research plays plus
four unpadded top-ten lists: short-term bullish, short-term bearish, long-term
bullish, and long-term bearish predictions. Every list row opens an evidence
breakdown with why-now signals, rejection tests, kill conditions, setup trust,
direction-neutral attention, liquidity, missing evidence, and source timestamps.
Its priority scores are explicitly not probabilities or execution instructions;
the surface exposes no order controls, and bearish stock research cannot create a
short-stock order.

The adaptive shell adds shared universe, timeframe, as-of, evidence-class, source-
freshness, and run-hash context plus density, text-size, and contrast controls.
Quantitative frames provide Summary, Chart, Table, Provenance, and Method modes.
M-01 keeps observed append-only telemetry separate from declared agent topology;
if the event stream is absent, playback is disabled and the missing contract is
shown explicitly. Market Tissue owns the single Universe Coverage Explorer.

Symbol Lab adds a dynamic, symbol-specific options value and meta-plan workbench.
Operators can change the strategy family, future stock-price scenario, elapsed
time, and implied-volatility shift; the bridge then reranks only contracts that
pass explicit DTE, liquidity, spread, open-interest, and moneyness filters. The
surface also exposes supports, resistances, earnings proximity, chain tissue,
strategy-family fold results, selection-aware penalties, and multiple conditional
plans. Scenario values are theoretical, friction-adjusted research projections,
not future quotes, expected returns, recommendations, or execution instructions.

Evidence is the research-verdict surface. It presents the content-addressed
strategy dossier, hard-gate failures, model-unit economic decomposition,
model-premium capital diagnostics, cross-artifact contract health, diagnostic
Pareto frontier, settlement state, and 18 CRR oracle invariants without
turning any model-priced result into a profitability claim. Evolution adds an
interactive parent/mutation genealogy, node inspector, rejection reasons,
champion dynamics, all recorded generations, and family search-budget ledger.
The graph is a deterministic bounded mutation
search, not a false A* claim over a noisy strategy landscape.

Installed scanner tasks run through `operator_tools/run_scheduled_hidden.vbs`.
The launcher accepts only eight fixed command identities and starts each `.cmd`
with window style `0`. Reapply and verify the no-window task actions with:

```powershell
.\operator_tools\install_hidden_scheduled_launchers.ps1
```

## Build

From PowerShell at the repository root:

```powershell
.\desktop\build_desktop.ps1
```

The deterministic local build recreates a dedicated `desktop/.desktop-venv`, installs the
complete Python closure from a hash-verified lock, requires Python 3.13.13, Node 24.15.0, and
npm 11.14.1, performs `npm ci`, compiles the frontend, generates the geometric evidence-spine
D icon, validates the read-only state adapter, fails immediately when the installed release is
running, builds and smoke-tests in an isolated staging directory, then atomically promotes a one-file windowed
executable at:

```text
desktop/release/DOPEY Control Center.exe
```

The release directory also receives a SHA-256 sidecar and a source/toolchain manifest. The manifest hashes the dependency locks, frontend
sources, inlining tool, build script, compiled single-document UI, assets, and native host
inputs. It records the actual Windows Authenticode result and smoke-test contract. UPX is
disabled so the binary does not vary with an ambient UPX installation. Authenticode signing
remains a separate release-authority step and is never implied by the build script.

The PyInstaller manifest includes only Python code, the compiled frontend, and
brand assets. It does not bundle the artifact lake, market data, environment
files, credentials, or operator evidence.

The build also generates `desktop/visual-qa/index.html` from a path-redacted,
source-backed state fixture. That page exposes a read-only bridge: every scheduler,
provider, credential, process, and window mutation fails with `qa_fixture_read_only`.
Open it locally with `#lab` to review the compiled Symbol Lab surface or with
`#evidence` to review the Evidence surface, or with `#playbook` to review the
ranked bullish/bearish prediction research surface, without
starting a desktop host or research process.

## Launch

Install or repair the actual Windows Desktop shortcut and automatic sign-in launch:

```powershell
.\desktop\install_desktop_launcher.ps1
```

The installer creates matching shortcuts on the current Windows Desktop and in the
current user's Windows Startup folder. Both target the hidden PowerShell bootstrap,
preserve the repository root, and use the packaged executable icon. The operating
system resolves the actual Desktop and Startup locations, including a OneDrive-managed
Desktop. DOPEY therefore opens automatically whenever the current user signs in.

Launch directly:

```powershell
.\desktop\launch_desktop.ps1
```

The launcher sets `DOPEY_REPO_ROOT` to the current checkout and opens the
visible interactive application. For a separately installed executable, set
`DOPEY_REPO_ROOT` explicitly. The host otherwise checks its development
parent and `~/dopey`, then fails with the exact paths it inspected.

## Smoke check

Source host, after dependencies and frontend assets are built:

```powershell
$env:DOPEY_REPO_ROOT = (Get-Location).Path
.\desktop\.desktop-venv\Scripts\python.exe -m dopey_dashboard.desktop_app --smoke-check
```

Packaged host:

```powershell
$env:DOPEY_REPO_ROOT = (Get-Location).Path
& '.\desktop\release\DOPEY Control Center.exe' --smoke-check
```

Both checks are read-only. They never start or stop the scheduler.
