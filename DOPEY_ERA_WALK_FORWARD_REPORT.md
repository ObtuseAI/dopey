# DOPEY Era Walk-Forward Report

## Question
Which cohorts hold up across ALL market eras (net > 0 and PF > 1 in every era with
at least 30 trades) - and which are single-regime bets?

- regime-robust cohorts: `0` -> `[]`
- near-robust (two of three eras): `3` -> `['fakeout|long_call', 'fakeout|long_put', 'market_regime|long_call']`

## Per-era cohort stats (net model units, post-cost)
- `breakout|long_call`: 2015_2019_low_vol_bull: n=799 net=-94.060303 PF=0.671265, 2020_2022_covid_and_bear: n=572 net=-251.147474 PF=0.716886, 2023_2026_ai_bull: n=849 net=27.094532 PF=1.022124
- `breakout|long_put`: 2015_2019_low_vol_bull: n=650 net=11.163174 PF=1.038586, 2020_2022_covid_and_bear: n=630 net=-234.236476 PF=0.652964, 2023_2026_ai_bull: n=520 net=-242.400056 PF=0.652927
- `fakeout|long_call`: 2015_2019_low_vol_bull: n=179 net=26.154624 PF=1.458965, 2020_2022_covid_and_bear: n=218 net=111.212901 PF=1.504923, 2023_2026_ai_bull: n=270 net=-188.863641 PF=0.551617
- `fakeout|long_put`: 2015_2019_low_vol_bull: n=233 net=12.398213 PF=1.151537, 2020_2022_covid_and_bear: n=269 net=20.613436 PF=1.091604, 2023_2026_ai_bull: n=244 net=-41.160866 PF=0.864038
- `market_regime|long_call`: 2015_2019_low_vol_bull: n=51 net=-10.858608 PF=0.720865, 2020_2022_covid_and_bear: n=121 net=121.36336 PF=1.265322, 2023_2026_ai_bull: n=244 net=25.200512 PF=1.052603
- `market_regime|long_put`: 2015_2019_low_vol_bull: n=4012 net=-637.697274 PF=0.650416, 2020_2022_covid_and_bear: n=3455 net=-1261.183268 PF=0.691178, 2023_2026_ai_bull: n=3780 net=-2169.836759 PF=0.575092
- `momentum|long_call`: 2015_2019_low_vol_bull: n=5366 net=-709.100195 PF=0.656379, 2020_2022_covid_and_bear: n=4704 net=-1523.323292 PF=0.746641, 2023_2026_ai_bull: n=5920 net=-910.892282 PF=0.89393
- `momentum|long_put`: 2015_2019_low_vol_bull: n=3408 net=-529.645028 PF=0.665971, 2020_2022_covid_and_bear: n=3782 net=-922.227416 PF=0.792475, 2023_2026_ai_bull: n=3868 net=-1919.166275 PF=0.638338
- `relative_strength|long_call`: 2015_2019_low_vol_bull: n=7148 net=-638.88866 PF=0.75683, 2020_2022_covid_and_bear: n=5167 net=-1596.041697 PF=0.758922, 2023_2026_ai_bull: n=6430 net=-558.459915 PF=0.93783
- `relative_strength|long_put`: 2015_2019_low_vol_bull: n=6616 net=-764.758686 PF=0.662189, 2020_2022_covid_and_bear: n=5845 net=-1201.890661 PF=0.776048, 2023_2026_ai_bull: n=7489 net=-2876.988498 PF=0.664021
- `trend_pullback|long_call`: 2015_2019_low_vol_bull: n=7 net=-0.575783 PF=0.723868, 2020_2022_covid_and_bear: n=8 net=-19.607863 PF=0.107009, 2023_2026_ai_bull: n=19 net=-26.661012 PF=0.113864
- `trend_pullback|long_put`: 2015_2019_low_vol_bull: n=3 net=-2.188686 PF=0.374129, 2020_2022_covid_and_bear: n=2 net=0.030061 PF=1.294346, 2023_2026_ai_bull: n=2 net=-0.406973 PF=0.253033

## Honest Limits
- Era robustness is necessary, not sufficient; baseline arbitration and real chains still gate claims.
- paper_only: `true`; live_blocked: `true`.
