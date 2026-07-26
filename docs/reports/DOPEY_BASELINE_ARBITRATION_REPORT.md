# DOPEY Baseline Arbitration Report

## Question
Do the real-lane cohorts beat a seeded random-entry baseline run through the identical
pricing, exit, and cost engine - or is their P&L just market drift?

- baseline trades: `321416` (seed `20260709`)
- cohorts evaluated: `11`
- cohorts beating baseline after familywise control (nominal 95%): `0`

## Verdicts (mean net P&L per trade, cohort minus baseline)
- `fakeout|long_call`: diff `0.479266` clustered CI [`-1.196305`, `1.736403`] (months `137`) -> indistinguishable
- `fakeout|long_put`: diff `0.204114` clustered CI [`-0.523186`, `0.768106`] (months `139`) -> indistinguishable
- `relative_strength|long_call`: diff `-0.333114` clustered CI [`-0.669828`, `0.129849`] (months `139`) -> indistinguishable
- `relative_strength|long_put`: diff `-0.34429` clustered CI [`-0.694319`, `-0.016517`] (months `139`) -> WORSE than baseline
- `market_regime|long_put`: diff `-0.448817` clustered CI [`-0.686736`, `-0.120794`] (months `139`) -> WORSE than baseline
- `momentum|long_call`: diff `-0.547043` clustered CI [`-0.950963`, `0.013632`] (months `139`) -> indistinguishable
- `breakout|long_call`: diff `-0.926245` clustered CI [`-1.422571`, `-0.43069`] (months `139`) -> WORSE than baseline
- `momentum|long_put`: diff `-1.266718` clustered CI [`-1.876553`, `-0.742994`] (months `139`) -> WORSE than baseline
- `market_regime|long_call`: diff `-1.873342` clustered CI [`-5.768819`, `2.672957`] (months `104`) -> indistinguishable
- `breakout|long_put`: diff `-1.967667` clustered CI [`-3.447814`, `-0.9881`] (months `139`) -> WORSE than baseline
- `trend_pullback|long_call`: diff `-9.346505` clustered CI [`-36.602882`, `3.556501`] (months `33`) -> indistinguishable

## Honest Limits
- Model-priced marks on both sides; identical engine, so the comparison isolates entry-signal value.
- Month-cluster resampling and Bonferroni control reduce false confidence from overlapping trades and cohort search.
- Beating baseline is necessary, not sufficient: era stability and real chains still gate promotion.
- paper_only: `true`; live_blocked: `true`.
