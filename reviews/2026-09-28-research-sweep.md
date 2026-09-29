# Research sweep, Sep 28, 2026

A background agent searched papers, datasets and code for the eight hypotheses in the backlog: about 60 pages opened in 25 minutes, no paid API calls, nothing changed in the repo. Confidence marks whether the agent opened the page (High) or saw only an abstract or search result (Med/Low). The hub verified item 1 by making the calls itself.

## The three findings that change a decision

1. **A true forecast archive back to 2003: Iowa State's MOS archive.** `https://mesonet.agron.iastate.edu/api/1/mos.json?station=KBUF&model=GFS&runtime=2021-11-20T12:00:00Z` returns 21 forecast rows with wind speed (knots), direction, temperature and the run time. GFS MOS from Dec 2003, NAM from Dec 2008, hourly NBM from Nov 2018. The hub confirmed it: a 2010 run at Green Bay returns 28-knot wind forecasts. This makes a forecast-based replay of both wind rules possible for 2004–25, not just 2024–25 (Open-Meteo previous runs start in 2024), and it carries run times, which unblocks the deferred forecast-run-timing question (#6). Caveats: airport station, 3-hourly steps, knots, and its bias against the Open-Meteo forecasts the alerts use must be measured. **Free, and the single most valuable item found.**
2. **Props: the median-vs-mean argument may be wrong as stated.** For a bet that simply wins or loses, only the median vs the line matters; the mean matters only when payoff scales with the margin. A yardage over/under set at the median hits ~50% by construction. So #10 should be pre-registered as "does the posted line sit above the empirical median of the outcome distribution", with the over/under price asymmetry checked, before the 137K-credit props pull (F3) is spent. (analytics.bet; Wizard of Odds; no published hit-rate study exists.)
3. **Line-move reversal shows up after the close, not before it.** Moskowitz 2021 (J. Finance, free PDF), Table III, NFL: open-to-close move +1.22 (t=2.88) and close-to-end return −3.72 (t=−2.25), before vig; the abstract says it fails to beat transaction costs. So #16 should be two pre-registered hypotheses: "fade the move, bet at the close" (graded on win rate/ROI, must beat the vig) and "reversal before the close" (graded on CLV). This is the test F1 must pass before F4's 1.44M credits are unlocked.

## Useful, lower impact

- **De-vig choice.** Shin equals the additive method for two-outcome markets (mberk/shin; Clarke et al. 2017), so it adds nothing for spreads and totals. Default to the power method, report the spread across methods. `penaltyblog` implements seven methods with American-odds input.
- **Kalshi/Polymarket trade tape, free:** Becker's dataset (github.com/jon-becker/prediction-market-analysis, MIT, ~36 GiB parquet; HF mirror). Schema and sports coverage unverified. Answers #9 with no API pulls if the taker-side field exists. Also: a Kalshi scraper with research permission (jdkatz21/Prediction_Markets_Public) and Polymarket's unauthenticated `/prices-history`.
- **Bürgi, Deng & Whelan 2026 (read in full):** Kalshi contracts under 10¢ lose >60%; makers −9.6% vs takers −31.5%; sports only from Jan 2025, so little sports-specific evidence. **Moshrefi 2026:** Kalshi calibration worsens in the last 10 minutes; parlays ~1.22× overpriced at 10 legs. Rule: never take Kalshi near expiry.
- **Post-2015 margin tables** (Doc's Sports, 6,967 games from nflverse): 3 steady at ~15%; 6 and 8 noisy year to year, so don't let them drive teaser pricing. Sides, Harvill & Sides 2022: CFB margin SD ~15 for spreads, ~21 for totals (NFL 13.5); use the CFB numbers for CFB alternates.
- **NFL stadium orientation datasets** (greerreNFL/Stadiums; ThompsonJamesBliss/WeatherData) for crosswind (#6). None found for CFB.
- **Soccer heat:** a 2025 study (PMC11829705; Bundesliga, La Liga, A-League) finds no association between temperature and goals or shots. Supports keeping S-H1 descriptive. **MLB:** Callahan & Mankin 2023 and Nathan: ~1% more home runs per °F; no runs-per-degree estimate exists.
- **MLB park table** (sportsdataverse mlb_park_dimensions: roof, azimuth, elevation) as a free cross-check of `config/venues/`.
- **Multiple testing beyond Bonferroni:** deflated Sharpe (Bailey & López de Prado), Holm/BHY (Harvey, Liu & Zhu), Romano–Wolf StepM in the `arch` package. Clegg & Cartlidge 2024: one erroneous odds row drove a published tennis result, so add an outlier-odds audit to every backtest.
- **Buchdahl:** the ratio of price taken to Pinnacle's close predicts realized yield with slope ~1.00 (87,960 soccer pairs). The justification for grading on CLV. Also his model-testing calculator.
- **BeatTheBookie** (Lisandro79, GPL-3): Kaunitz's code plus ~1M soccer matches of closing odds, a free test bed for the price-engine threshold logic (soccer only).

## Not found
A free timestamped multi-book NFL/CFB odds dataset; any prop-price archive or prop hit-rate study; a rigorous ranking of soft books; free hourly line data; a Kalshi-vs-sportsbook lead-lag paper; a pre-registered forward test in sports betting to copy; a CFB stadium-orientation dataset; teaser-EV code; a runs-per-degree MLB estimate.

## Blocked (paywalled or 403)
Simon 2024 (Management Science), Štrumbelj 2014, Borghesi 2007, Applied Economics Letters 2022 (NCAA weather), Bartlett (SSRN), Taylor & Francis, ResearchGate.

The full agent report, with every URL and confidence mark, is in the hub's transcript.
