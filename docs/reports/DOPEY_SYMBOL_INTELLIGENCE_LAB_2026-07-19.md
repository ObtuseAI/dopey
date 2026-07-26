# DOPEY Symbol Intelligence Lab

## Outcome

DOPEY now has a governed, paper-only research organism for every symbol in the
200-name active universe. It combines hash-pinned price history, multi-timeframe
market structure, 62 chart indicators and pattern/divergence states, staged
earnings records, validated option-chain observations, chronological
strategy-family tests, scenario option valuation, and conditional meta-plans.

This is an operational research capability, not evidence of a profitable edge.
The desktop and batch artifacts keep `paper_only=true`, `live_blocked=true`,
`profitability_claim_allowed=false`, and `promotion_allowed=false`.

## Delivered capability

- Adjustable option-value projection over stock price, elapsed time, and implied
  volatility shift.
- Strategy-aware ranking for observed long calls/puts and research-only debit
  verticals, anchored to executable entry-side quotes rather than midpoint fills.
- Explicit DTE, relative-spread, open-interest, moneyness, and positive-quote
  eligibility gates. A symbol with no acceptable contract is blocked rather than
  assigned a synthetic expression.
- Price-by-time value surfaces for the highest scenario-fit expression.
- Twelve transparent, past-only strategy and indicator recipes spanning trend,
  momentum, breakout, volatility release, mean reversion, and reversal families.
- Chronological folds, a matched random-entry control, transaction-cost haircuts,
  multiple-search penalties, sample sufficiency, and stability/fragility labels.
- Per-symbol daily, weekly, and monthly trend agreement; support, resistance,
  confluence zones, ATR, realized volatility, pattern evidence, and divergences.
- Earnings proximity, chain spread/put-call/skew/term-structure diagnostics, and
  explicit missing-evidence states.
- Four conditional meta-plans per symbol, plus event abstention when a staged
  earnings event is inside the protected window.
- A daily autonomous `symbol_intelligence_lab` schedule lane and interactive
  read-only `get_symbol_lab` desktop bridge.

## 200-symbol verification

The governed batch completed all 200 requested symbols with zero computation
failures. The final batch hash is
`a1cd4f9c1628acb80cdd302bec2c894062a80715f8d06059da07cf2ab3a1a361`.
The complete cohort summary is recorded in
`artifacts/dopey/symbol_lab/latest_batch_summary.json`; each immutable dossier is
under `artifacts/dopey/symbol_lab/symbols/`.

The corrected final pass took 1,051 seconds against a 7,200-second lane timeout. It
produced 91 symbols with at least one current recipe condition, 194 symbols with
an acceptable ranked option expression, and one explicit no-chain block for
VIX. Five additional symbols had real chain rows but no contract passing the
declared eligibility filters; the projector reports those as
`blocked_no_contract_passing_eligibility_filters` rather than `complete`.

These counts describe evidence coverage and current rule conditions. They are
not trade counts, forecasts of profit, or readiness promotion.

## Desktop release proof

- Executable: `desktop/release/DOPEY Control Center.exe`
- SHA-256: `bcaad18bf3753ff66c27e5e1fc1a0fae721e35893a26642b43197590ddc38fdf`
- Bytes: `37,678,977`
- Authenticode: `NotSigned`
- Source smoke: pass
- Packaged smoke: pass
- Renderer: Edge WebView2 / `edgechromium`
- Server started by smoke check: false
- Live execution enabled: false
- Desktop shortcut: `%OneDrive%\\Desktop\\DOPEY Control Center.lnk`

The clean build originally exposed an incomplete Python desktop dependency lock.
The root cause was fixed by pinning the runtime cryptographic and exchange-calendar
closure in `desktop/requirements-build.in` and regenerating the hash-verified lock.
No import fallback or fixture bypass was introduced.

## Final control state

The repository-local schedule planner reports `dopey-research-schedule-v16`,
includes `symbol_intelligence_lab`, and verifies its batch artifact as complete.
The lane is not due on Sunday because its declared window is `after_close`; the
next eligible scheduled process will reconcile the already-complete evidence and
continue at the normal daily cadence.

The governed universe remains 200 symbols. Readiness remains
`not_action_ready`; only 21 of the required 100 forward-paper trades are closed,
0 of 200 required context decisions are resolved, and fractional compounding
remains disabled. The new research breadth does not lower any evidence threshold.

## Reproduction

```powershell
# One symbol, interactive scenario
.venv\Scripts\python.exe -m dopey_symbol_lab.run_symbol_lab --symbol SPY `
    --strategy trend --scenario-price 760 --days-forward 14 --iv-shift 0

# Entire governed universe
.venv\Scripts\python.exe -m dopey_symbol_lab.run_symbol_lab --all

# Focused verification
.venv\Scripts\python.exe -m ruff check dopey_symbol_lab dopey_dashboard\desktop_app.py `
    dopey_acceleration\schedule.py dopey_acceleration\cycle.py `
    dopey_acceleration\autonomous_improvement.py tests\test_symbol_intelligence_lab.py
.venv\Scripts\python.exe -m pytest -q tests\test_symbol_intelligence_lab.py `
    tests\test_desktop_control_center.py tests\test_acceleration_control_plane.py

# Deterministic desktop package and launcher
powershell -ExecutionPolicy Bypass -File desktop\build_desktop.ps1
powershell -ExecutionPolicy Bypass -File desktop\install_desktop_launcher.ps1
```

## Shared review packet

The source-review subset, report, screenshot, final batch summary, SPY example
dossier, release manifest, SHA-256 sidecar, and packaged executable were copied to:

`\\FRANKENSTEIN\Shared Folder\DOPEY_SYMBOL_LAB_20260719_102757Z`

The packet contains 38 files / 38,666,204 bytes. The copied executable hashes to
`bcaad18bf3753ff66c27e5e1fc1a0fae721e35893a26642b43197590ddc38fdf`,
matching the promoted local release.

## Evidence and limitations

- Base implementation ancestry: `e44f9bd00caddae1121301a3b68a0cc73f4e0405`.
  The publication commit containing this report is the authoritative source
  identity; reproduce it from a clean checkout of that commit.
- Black-Scholes scenario values do not model American early exercise or discrete
  dividends. Those risks are exposed in every projection artifact. The existing
  CRR oracle remains the independent American-option validation surface.
- Future option values are model projections, never future quotes. Observed chain
  data anchors entry context only.
- Fundamentals remain unavailable where no governed local fundamental artifact
  exists; the laboratory does not fabricate them.
- Historical recipe results are not forward evidence. Forward settlement,
  calibration, economic fill validation, and held-out promotion gates remain
  mandatory.
- Live broker execution, credential access, and order construction remain outside
  the desktop and research runtime.

## Research basis

The design follows the current [Cboe Options Calculator](https://www.cboe.com/optionsinstitute/tools/options-calculator)
principle of changing spot, time, and volatility inputs to inspect theoretical
option values, while preserving the [OCC Options Disclosure Document](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document)
risk boundary. Its selection-aware penalty is directionally grounded in the
[Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
literature: performance observed after many trials requires an explicit search and
non-normality correction before it can be treated as evidence.
