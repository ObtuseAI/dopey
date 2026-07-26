# DOPEY Reporting Artifact Ledger

## Bundle

- Version: `dopey-tournament-performance-reporting-dashboard-v1`
- Root: `artifacts/dopey/reporting/`
- Status: `ok`
- Mode: `RESEARCH`
- Paper-only: `true`
- Live blocked: `true`

## Artifact hashes

| Artifact | Records | Bytes | SHA256 |
| --- | ---: | ---: | --- |
| `artifacts/dopey/reporting/dashboard_index.json` | 1 | 12683 | `036951e1a3dd9f80ffc4d0903f33bd62d66fd710fca9272603545b7083f0eb87` |
| `artifacts/dopey/reporting/dashboard_index.md` | 1 | 2647 | `3e7af67d5e8a81c5d6cb8b62035a8403c5ea9b08a2192d4861c67f9c305d88b5` |
| `artifacts/dopey/reporting/strategy_report_cards.jsonl` | 37 | 213205 | `8cbbf18904ca9df44a05da807e8b5deb2ab4505211984f182378a7f5d5b9fe12` |
| `artifacts/dopey/reporting/family_report_cards.jsonl` | 4 | 6441 | `454c725141ce507f31a588b875d36d4debacc2767e1c387f50e8d665cb578c2e` |
| `artifacts/dopey/reporting/scenario_report_cards.jsonl` | 81 | 58192 | `aa7c84568cc574e709b6c1dfa6f0de899983c83fb07bbfdebf9797fef6a90966` |
| `artifacts/dopey/reporting/regime_report_cards.jsonl` | 35 | 23802 | `078405034a48a8e8332046767c4388240d56c2fb569932c7bc97cf5d51e28aee` |
| `artifacts/dopey/reporting/performance_attribution.jsonl` | 37 | 41273 | `e876f6ed6c23495b32f100a108c65eefc26bd5796b9b6eec07c3c2391abef86c` |
| `artifacts/dopey/reporting/reporting_bundle_summary.json` | 1 | 2461 | `c070990b1e5ebfe3795ad1a7e676d5c1e35927acf0542ad24dc486c28c67cfab` |
| `artifacts/dopey/reporting/static_dashboard.html` | 1 | 3725 | `3e07b92734f7b1b0e9162564f6a64ec78f5603a0eb5fba44f700731ffd2323eb` |
| `artifacts/dopey/reporting/reporting_bundle_proof.jsonl` | 14 | 87528 | `afb639515d9232ce53e042f83ddb646030a73b417baab52b64cd5de0cfc5a920d` |

## Counts

- Strategy report cards: `37`
- Family report cards: `4`
- Scenario report cards: `81`
- Regime report cards: `35`
- Performance attribution records: `37`
- Proof records: `14`

## Audit recognition

The audit loader recognizes `.json` and `.jsonl` reporting artifacts. The current strict-hash reporting surfaces are:

- `reporting_dashboard_index`
- `strategy_report_cards`
- `family_report_cards`

The reporting consistency audit verifies:

- strategy report-card ids reference known strategy ids;
- report cards remain `paper_only=true`;
- report cards keep `live_allowed=false`;
- dashboard safety state keeps `live_blocked=true`;
- reporting proof remains fixture-only and paper-only.

## Current dashboard summary

- Top reporting strategy: `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`
- Top reporting family: `short_duration_defined_risk`
- Strong positive drivers: `tournament_baseline`, `walk_forward_consistency`, `meta_governor_trust`, `liquidity_slippage`, `greeks_fit`
- Strong negative drivers: `failure_feedback`, `failure_pressure`
- Safety: paper-only, fixture-only, live-blocked

## Reproduction command

```text
python -m dopey_reporting.run_tournament_performance_reporting_bundle
```

## Audit command

```text
python -m dopey_audit.run_offline_evidence_replay_audit
```
