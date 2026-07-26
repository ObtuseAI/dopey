# DOPEY Era Walk-Forward Report

## Question
Which cohorts hold up across ALL market eras (net > 0 and PF > 1 in every era with
at least 30 trades) - and which are single-regime bets?

- regime-robust cohorts: `0` -> `[]`
- near-robust (two of three eras): `0` -> `[]`

## Per-era cohort stats (net model units, post-cost)
- `breakout|long_call`: 2015_2019_low_vol_bull: n=3016 net=-1875.164247 PF=0.527633, 2020_2022_covid_and_bear: n=2197 net=-1656.657528 PF=0.577627, 2023_2026_ai_bull: n=2794 net=-1510.970854 PF=0.734983
- `breakout|long_put`: 2015_2019_low_vol_bull: n=2489 net=287.282348 PF=1.061815, 2020_2022_covid_and_bear: n=2146 net=-1497.817067 PF=0.557654, 2023_2026_ai_bull: n=1895 net=-1210.24874 PF=0.592389
- `fakeout|long_call`: 2015_2019_low_vol_bull: n=785 net=-1742.643631 PF=0.270942, 2020_2022_covid_and_bear: n=747 net=293.695541 PF=1.3162, 2023_2026_ai_bull: n=848 net=-408.548729 PF=0.714695
- `fakeout|long_put`: 2015_2019_low_vol_bull: n=990 net=-1231.953233 PF=0.279161, 2020_2022_covid_and_bear: n=956 net=322.088513 PF=1.304154, 2023_2026_ai_bull: n=932 net=-646.381321 PF=0.614582
- `market_regime|long_call`: 2015_2019_low_vol_bull: n=99 net=-833.814864 PF=0.110209, 2020_2022_covid_and_bear: n=281 net=-222.572113 PF=0.869401, 2023_2026_ai_bull: n=437 net=-327.411144 PF=0.787055
- `market_regime|long_put`: 2015_2019_low_vol_bull: n=16631 net=-115.395374 PF=0.995488, 2020_2022_covid_and_bear: n=12108 net=-6454.450228 PF=0.632978, 2023_2026_ai_bull: n=14387 net=-9340.993411 PF=0.576828
- `momentum|long_call`: 2015_2019_low_vol_bull: n=21971 net=-17538.826099 PF=0.597846, 2020_2022_covid_and_bear: n=18147 net=-9089.972661 PF=0.670321, 2023_2026_ai_bull: n=20800 net=-8793.674655 PF=0.766446
- `momentum|long_put`: 2015_2019_low_vol_bull: n=14746 net=-5252.680564 PF=0.834142, 2020_2022_covid_and_bear: n=13453 net=-6300.753866 PF=0.692516, 2023_2026_ai_bull: n=14370 net=-10089.945864 PF=0.576837
- `relative_strength|long_call`: 2015_2019_low_vol_bull: n=30240 net=-11062.661307 PF=0.777335, 2020_2022_covid_and_bear: n=21217 net=-9572.470055 PF=0.70116, 2023_2026_ai_bull: n=23952 net=-7962.864044 PF=0.809442
- `relative_strength|long_put`: 2015_2019_low_vol_bull: n=28747 net=-840.674247 PF=0.975333, 2020_2022_covid_and_bear: n=21794 net=-7823.951176 PF=0.706079, 2023_2026_ai_bull: n=28175 net=-13221.666335 PF=0.669726
- `trend_pullback|long_call`: 2015_2019_low_vol_bull: n=9 net=-320.5642 PF=0.004754, 2020_2022_covid_and_bear: n=21 net=-370.442272 PF=0.025015, 2023_2026_ai_bull: n=25 net=-23.10066 PF=0.66585
- `trend_pullback|long_put`: 2015_2019_low_vol_bull: n=5 net=-1.804978 PF=0.493602, 2020_2022_covid_and_bear: n=4 net=-2.231708 PF=0.070218, 2023_2026_ai_bull: n=2 net=-0.238544 PF=0.366262

## Honest Limits
- Era robustness is necessary, not sufficient; baseline arbitration and real chains still gate claims.
- paper_only: `true`; live_blocked: `true`.
