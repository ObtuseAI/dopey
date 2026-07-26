# DOPEY Source Inflow Report

## Purpose

The source inflow layer ranks future data/source candidates without fetching real data. This is
an offline planning scorecard only: no network calls, no credentials, no broker connection, and
no live market-data dependency.

## Model versions

- Source scorecard: `dopey-source-scorecard-v1`
- Data inflow registry: `dopey-data-inflow-registry-v1`

## Seeded candidates

Seeded source candidates: OpenBB, SEC/EDGAR filings, earnings calendar, macro calendar,
VIX/VVIX, realized volatility, options chain provider placeholder, IV surface provider
placeholder, unusual options activity if licensed, Alpaca options data, Tradier options data,
Robinhood MCP account/tool discovery, broker fill history future source, ProofLedger internal
outcome source, champion registry internal source, and pattern fixture corpus internal source.

## Promoted offline sources

Only local/offline/internal sources are promoted in this pass:

- `proofledger_internal`
- `champion_registry_internal`
- `pattern_fixture_corpus_internal`
- `realized_volatility`

These are promoted for fixture research only. They do not imply real-data readiness.

## Deferred sources

Deferred for network:

- `openbb`
- `sec_edgar`
- `earnings_calendar`
- `macro_calendar`
- `vix_vvix`

Deferred for credentials:

- `options_chain_provider_placeholder`
- `iv_surface_provider_placeholder`
- `unusual_options_activity`
- `alpaca_options_data`
- `tradier_options_data`
- `robinhood_mcp_discovery`
- `broker_fill_history_future`

## Scoring method

Each source is scored across freshness, reliability, latency, coverage, ontology fit, expected
edge contribution, cost/complexity, compliance, and paper research value. Sources requiring
network or credentials are automatically deferred regardless of score.

## Artifact path

- Source registry: `artifacts/dopey/source_registry/data_inflow_registry.jsonl`

## Safety notes

- `network_fetch_performed=false`
- `credentials_used=false`
- No source adapter fetches data in this bundle.
- Robinhood MCP remains discovery-only and deferred because it requires credentials/account
  authorization.
