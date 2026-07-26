# Data Notice

## Public source, bring-your-own market data

This public repository contains source code, schemas, deterministic test
fixtures, explicitly labeled synthetic samples, and aggregate engineering
validation metadata. One hash-pinned integration fixture preserves derived,
paper-only outputs from historical public-market observations. It does **not**
contain raw provider market datasets, broker exports, account history,
credentials, private runtime ledgers, private session reports, or the
operator's local market lake.

A fresh clone therefore starts with a clean **operational** market-data slate.
The bundled integration fixture is extracted only into isolated temporary test
directories and cannot seed the operational market lake, forward evidence, or
live state. The public release manifest in
[`PUBLIC_SOURCE_MANIFEST.json`](PUBLIC_SOURCE_MANIFEST.json) records the
boundary used to create this history-free source release.

## Local-only data paths

The following paths are ignored and must remain untracked:

- `dopey_data/real/**`, except reviewed `*.template.json` and files under
  `dopey_data/real/templates/`;
- `dopey_data/history/`;
- `dopey_data/market_lake/`;
- local environment, credential, MCP, editor-agent, log, and backup files.
- private broker reconciliation, session, handoff, and copy-proof reports.

Do not contribute raw or derived provider datasets, option-chain archives,
broker statements, account identifiers, order history, authentication
material, or other operator-specific evidence. Pull requests that add these
materials will be rejected even if the contributor believes redistribution is
permitted.

## Staging your own evidence

Operators obtain and stage their own data outside Git history, subject to each
provider's license and terms. DOPEY's intake gates require explicit provenance,
freshness, schema validation, content hashes, and reviewed redistribution
status. Missing or invalid inputs produce typed blocked states; they are never
replaced with fabricated "real" data.

Typical operator-owned entry points include:

```powershell
.venv\Scripts\python.exe operator_tools\operator_fetch_daily_ohlcv.py --help
.venv\Scripts\python.exe operator_tools\operator_fetch_option_chains.py --help
.venv\Scripts\python.exe -m dopey_autonomy.run_resilient_research_supervisor
```

These tools write only to local governed paths. Review provider terms before
fetching, retaining, or sharing any data.

## Evidence labels

- Files under test and fixture paths are deterministic validation material,
  not current market observations. Some are derived from historical public
  observations and are labeled paper-only, live-blocked, and not-forward
  evidence.
- Historical engineering reports describe prior internal validation and do
  not ship their underlying provider datasets.
- Paper, replay, model-priced, broker-read, and live evidence remain distinct.
- This project is experimental software, not investment advice or a
  representation of profitability.
