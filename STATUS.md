# Value Finder: status

*Updated September 28, 2026*

Paper-only sports-betting research. The goal is to find prices the market gets wrong, and to prove each one on a pre-registered forward test graded on closing-line value (CLV) before any money goes in. Nothing in this repo places bets.

## Projects

| Folder | Question | Where it stands | Next step |
|---|---|---|---|
| [`nfl-weather/`](nfl-weather/) | Do NFL totals under-price wind? This extends the 2014 thesis. | Thesis replicated and audited. Rule B (forecast wind ≥ 15 mph → under) is pre-registered as playbook v2. Alerts run 4×/day. | Forward test is scored from Week 5 (Oct 8). |
| [`cfb-weather/`](cfb-weather/) | The same question for college football. | Rule B pre-registered (`cfb-v1-2026-09-28`). Alerts run 4×/day. | Forward test is scored from Oct 1. Add a second rule ([#4](https://github.com/maxzipperman/value-finder/issues/4)). |
| [`sharp-markets/`](sharp-markets/) | Do Kalshi markets misprice relative to sharp books, or lag behind them? | Pipeline built (NBA first, sport-agnostic), 22 tests. H4a (Kalshi NFL totals vs wind, 2025): Kalshi moves with the books and doesn't lag. | NBA sample week for H1/H2 once the Odds API key is in. H3 is waiting on licensed data. |
| [`strategy-research/`](strategy-research/) | Which "proven" strategies hold up in our data? | 109-variant screen done. Nothing passes a strict multiple-testing bar. Ranked ideas are in the backlog below. | Work through the backlog. |
| [`thesis-research/`](thesis-research/) | What has been published since the thesis? | Literature review and feedback done ([page](https://claude.ai/artifact/ULdbHSkgLLcf6bzBGEppNU)). | Its crosswind idea is part of [#6](https://github.com/maxzipperman/value-finder/issues/6). |
| [`thesis/`](thesis/) | The 2014 thesis, as text. | Reference only. | None. |

## Forward tests (the scoreboard)

| Rule | Scored from | Signals so far | Decision |
|---|---|---|---|
| NFL Rule B: early wind under ([`STRATEGY.md`](nfl-weather/STRATEGY.md)) | Week 5, Oct 8, 2026 | 0 | After Week 18 or 40 signals: keep only if average CLV > 0 with a 95% interval above zero. |
| CFB Rule B: early wind under ([`STRATEGY.md`](cfb-weather/STRATEGY.md)) | Oct 1, 2026 | 0 | After 40 signals or the regular season, whichever is later, by the same test. |

Stake for both: paper until 20 settled signals show positive average CLV. After that, 0.5% of bankroll at most.

## Waiting on you

1. **Odds API key.** `ODDS_API_KEY` is empty in `nfl-weather/.env` and `cfb-weather/.env`, and `sharp-markets/.env` doesn't exist yet (copy `.env.example`). Without the key:
   - NFL alerts only see nflverse consensus lines.
   - CFB alerts have no price source, so any trigger arrives as WATCH / no price.
   - The sharp-markets H1/H2 runs can't start.
2. **Phone alerts.** Subscribe to the `NTFY_TOPIC` from either `.env` in the ntfy app, if you haven't yet.

## Backlog

One issue per idea from [`strategy-research/`](strategy-research/README.md#ideas-to-add-ranked), in suggested order. Filter the [`idea` label](https://github.com/maxzipperman/value-finder/issues?q=is%3Aissue+label%3Aidea) on GitHub.

| # | Idea | Project | Needs |
|---|---|---|---|
| [#4](https://github.com/maxzipperman/value-finder/issues/4) | CFB high totals → under, as a second rule | cfb-weather | Nothing new. **Must be pre-registered before its first eligible game (2026 Week 6).** |
| [#5](https://github.com/maxzipperman/value-finder/issues/5) | Timing advice on every alert | nfl-weather, cfb-weather | Nothing new |
| [#6](https://github.com/maxzipperman/value-finder/issues/6) | Crosswind vs headwind; derivative markets; forecast-run timing | nfl-weather | Crosswind: nothing new. The other two parts need the Odds API. |
| [#7](https://github.com/maxzipperman/value-finder/issues/7) | Home teams off a bye; Week 1 unders (paper) | nfl-weather | Nothing new |
| [#8](https://github.com/maxzipperman/value-finder/issues/8) | Price engine: beat the sharp fair line (most proven) | sharp-markets | Odds API credits, Kalshi, Polymarket |
| [#9](https://github.com/maxzipperman/value-finder/issues/9) | Kalshi/Polymarket microstructure | sharp-markets | Free Kalshi and Polymarket data |
| [#10](https://github.com/maxzipperman/value-finder/issues/10) | Player props: median vs mean | nfl-weather | About 34,000 Odds API credits |
| [#11](https://github.com/maxzipperman/value-finder/issues/11) | CFB injury reports and early-season priors | cfb-weather | CFBD API |

Tested and skipped: primetime unders, the holdover bias, West Coast night games, fading big covers, turnover luck, road teams, CFB big underdogs, and service-academy unders. See [what the screen found](strategy-research/README.md#faded-or-never-there).

## Keeping this current

Any change that moves a project, a forward test or a backlog item updates this file in the same pull request. See [`CLAUDE.md`](CLAUDE.md).
