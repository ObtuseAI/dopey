# DOPEY Baseline Arbitration Report

## Question
Do the real-lane cohorts beat a seeded random-entry baseline run through the identical
pricing, exit, and cost engine - or is their P&L just market drift?

- baseline trades: `82880` (seed `20260709`)
- cohorts evaluated: `11`
- cohorts beating baseline after familywise control (nominal 95%): `0`

## Verdicts (mean net P&L per trade, cohort minus baseline)
- `fakeout|long_call`: diff `0.498819` clustered CI [`-0.374206`, `1.383933`] (months `110`) -> indistinguishable
- `fakeout|long_put`: diff `0.486898` clustered CI [`-0.058746`, `1.094694`] (months `130`) -> indistinguishable
- `relative_strength|long_put`: diff `-0.16287` clustered CI [`-0.252889`, `-0.076814`] (months `139`) -> WORSE than baseline
- `relative_strength|long_call`: diff `-0.310459` clustered CI [`-0.436722`, `-0.204821`] (months `139`) -> WORSE than baseline
- `market_regime|long_put`: diff `-0.343652` clustered CI [`-0.497985`, `-0.206743`] (months `139`) -> WORSE than baseline
- `market_regime|long_call`: diff `-0.351157` clustered CI [`-2.142306`, `2.735069`] (months `80`) -> indistinguishable
- `momentum|long_call`: diff `-0.50423` clustered CI [`-0.649961`, `-0.354798`] (months `139`) -> WORSE than baseline
- `momentum|long_put`: diff `-0.543823` clustered CI [`-0.716305`, `-0.380972`] (months `139`) -> WORSE than baseline
- `breakout|long_put`: diff `-0.724464` clustered CI [`-1.218203`, `-0.135235`] (months `134`) -> WORSE than baseline
- `breakout|long_call`: diff `-0.789683` clustered CI [`-1.279724`, `-0.435928`] (months `136`) -> WORSE than baseline
- `trend_pullback|long_call`: diff `-1.177796` clustered CI [`-2.534488`, `0.043285`] (months `23`) -> indistinguishable

## Honest Limits
- Model-priced marks on both sides; identical engine, so the comparison isolates entry-signal value.
- Month-cluster resampling and Bonferroni control reduce false confidence from overlapping trades and cohort search.
- Beating baseline is necessary, not sufficient: era stability and real chains still gate promotion.
- paper_only: `true`; live_blocked: `true`.
