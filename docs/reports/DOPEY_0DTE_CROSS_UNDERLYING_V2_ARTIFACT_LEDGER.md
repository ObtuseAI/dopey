# DOPEY 0DTE Cross-Underlying V2 Artifact Ledger

## Summary

- Artifact root: `artifacts/dopey/zero_dte_cross_underlying_v2`
- Family count: `12`
- Case count: `192`
- Path count: `192`
- Regime count: `16`
- Combined v1/v2 fixture count: `315`
- Proof layer: `cross_underlying_corpus_proof.jsonl`
- Safety state: `paper_only=true`, `live_blocked=true`, `no_real_market_data=true`, `no_broker=true`

## Artifacts

| Artifact type | Path | Records | SHA256 |
| --- | --- | ---: | --- |
| `zero_dte_underlying_families` | `artifacts/dopey/zero_dte_cross_underlying_v2/underlying_families.json` | 12 | `0c9013e40f5efe578dc4a257283c2ece472b858e999b8b65876678164d3559b0` |
| `zero_dte_cross_underlying_regime_cases` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_regime_cases.json` | 192 | `b954971bb7ce8a08a3de759892255caf22b7486d332b8226d2d8306063ac104b` |
| `zero_dte_cross_underlying_intraday_paths` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_intraday_paths.json` | 192 | `b05db54891d2e5042192bb57c50e75eb852b83c81234972896d068b8e1a8b2bf` |
| `zero_dte_cross_underlying_replay_outcomes` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_replay_outcomes.jsonl` | 192 | `4f459030901da8b4c99be6e082212e904d167cf3be3cc1e51b1244758aa52529` |
| `zero_dte_cross_underlying_threshold_feedback` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_threshold_feedback.jsonl` | 192 | `43b0d59786b6f2dac30e52e2c8c07ca4ae19797f8da17af85131237dae2974dc` |
| `zero_dte_cross_underlying_optimizer_effects` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_optimizer_effects.jsonl` | 192 | `0b74ef9d98de5eb554b69231a30d56993b5895b26340e774a64cbd6a498acc94` |
| `zero_dte_cross_underlying_coverage_summary` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_coverage_summary.json` | 1 | `c3465b71a89a3a77de879b583804c418269b5991cc7f2e067f00125ac0092262` |
| `zero_dte_combined_v1_v2_replay_summary` | `artifacts/dopey/zero_dte_cross_underlying_v2/combined_v1_v2_replay_summary.json` | 1 | `d29f23b79cdde2c9ddcee4dabfabd6f98e5e29540316f4153568ddafaa855ddf` |
| `zero_dte_cross_underlying_threshold_survival` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_threshold_survival.json` | 192 | `9f32aa5644b70bb48d456a3692d2cfc07534350212ab75c73cc12cf1d4ba1547` |
| `zero_dte_cross_underlying_corpus_proof` | `artifacts/dopey/zero_dte_cross_underlying_v2/cross_underlying_corpus_proof.jsonl` | 192 | `ef1ab3ca6ab3ab0fcbfde03c0d4bb7db0de1045b9923341dbec0859924402bd3` |

## Distribution Snapshot

- Underlying family distribution: every family has `16` cases.
- Regime family distribution: every regime has `12` cases.
- Option type distribution: `call=96`, `put=96`.
- Policy-loophole risk vectors: `same_day_churn_attempt=12`, `unsupported_structure_attempt=12`, `live_path_attempt=12`.

## Safety Notes

The artifacts are deterministic local fixtures. They contain no broker execution path, credential path, real market-data dependency, scheduler, or live promotion path.
