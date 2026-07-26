# DOPEY Trade Readiness Frontier

- status: `research_mechanics_ready_full_validation_pending`
- highest operational level: `research_mechanics`
- authority: `paper-only; live execution constitutionally unavailable`
- reproducibility hash: `7ac719d67291db7a30d092c13fe36cc7b636e8fce5a85863115567c205dd2e67`

## Capability levels

| Level | Ready | Meaning |
|---|---:|---|
| `research_mechanics` | `True` | Governed data plus deterministic risk, incident, and lifecycle mechanics. |
| `stock_shadow` | `False` | Stocks may produce forward paper decisions after current validation is green. |
| `option_shadow` | `False` | Options additionally require observed, validated, quote-priced chain evidence. |
| `strategy_promotion` | `False` | Forward sample, net evidence, regime robustness, and statistical truth all pass. |
| `live_execution` | `False` | Permanently outside this repository's authority. |

## Blocking gates

- `nightly_validation_green` — status=inconclusive_timeout; failed=0; errors=0 (evidence: `mechanical_validation`)
- `observed_options_quotes_validated` — options_data_validated=False; quote_priced_backtest_allowed=False (evidence: `observed_options_market_data`)
- `forward_sample_sufficient` — closed=4; required=100 (evidence: `prospective_forward_evidence`)
- `forward_track_net_positive` — gate=False (evidence: `prospective_forward_evidence`)
- `regime_robust_and_statistically_promotable` — requires regime robustness and statistical-truth promotion together (evidence: `held_out_selection_adjusted_evidence`)

## Autonomous next-action queue

1. run the resumable isolated nightly suite and publish a fresh green checkpoint
2. ingest timestamped licensed option chains and pass all quote-quality gates
3. continue immutable forward settlement; never synthesize or backfill outcomes
4. continue settlement and retire or retune only through held-out challenger evidence
5. run held-out, multiple-testing-adjusted cohort evaluation without changing the judge

## Interpretation

Mechanics readiness, paper-shadow readiness, strategy evidence, and live authority are separate.
A green lower tier never implies a green higher tier. Simulation never becomes realized evidence.
