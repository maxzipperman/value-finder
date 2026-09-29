# The 5M month: day-one checklist

For the hub, on the Mac, once the owner has bought the 5M plan on Thursday, October 1, 2026. The plan, its
gates and its March list are in
[`strategy-research/odds-api-credits.md`](../../strategy-research/odds-api-credits.md#the-5m-month-owner-decisions-september-28-2026-rewritten-september-29).
The pulls are defined in [`config/odds5m.yaml`](../config/odds5m.yaml) and run by
`uv run markets odds5m <stage>` (code: `src/markets/oddsapi/bulk.py`). Everything is GET-only.

Run every command from `sharp-markets/`.

**Day one buys at most 238,590 credits** (about 210K of it exists on October 1; the rest is 2026 games not yet played):
the probe, F1, F2, the NBA sample week, and the heat closes. Then it stops. F3, N1 and F4 are gated (below).
The **hard ceiling for the whole month is 4,440,000 credits**, and day one plus every gate is 2,304,050.

## How a run protects the credits

- **Dry run by default.** Without `--confirm`, no stage calls the API. Every stage without `--confirm` prints what it would do and the most it could cost.
- **Run budget.** `--max-credits N` is checked before each call against that call's upper-bound cost, so a run can never go over N.
- **Reserve floor.** `--floor` defaults to 531,630: the 300K reserve plus the 231,630 freed by dropping X3. The run stops before the account's remaining credits would drop below it.
- **Groups, not `all`.** `--pull` takes pull IDs or a group from the config: `day_one` (F1, F2, F3, HB1, HS1), `gated` (N1, F4), `march` (H1, N2, F5, F6). The `full` stage refuses `--pull all`, so nothing runs every pull in the config by accident.
- **Circuit breaker.** The run stops at once:
  - when a call bills more than its upper bound (`x-requests-last` above 10 × markets × regions, or above 1 for `/events`);
  - on HTTP 401 (key rejected);
  - on HTTP 429 after retries (quota used up);
  - after 5 errors in a row.
- **Cache first and resumable.** Every response is stored before it is used, under `data/raw/{sport_key}/oddsapi/...`. N1 is the exception: it is stored under `data/raw/nba/oddsapi_hist/`, where `markets build --sport nba` reads it, and where the sample week's `odds-pull` snapshots already are. Rerunning a command skips everything cached, so a stopped or interrupted run resumes for free. Errors aren't cached, so they are retried.
- **Manifest.** Every real request gets a row in `data/raw/_manifest/oddsapi_manifest.csv`. Each row has:
  - the requested and returned snapshot times;
  - credits billed and credits remaining;
  - the SHA-256 of the body;
  - the cache key;
  - the sealed flag.
- **Sealed holdout.** Sealed seasons are pulled but never read by default:
  - the 2026 seasons of NFL and CFB;
  - 2026-27 for NBA and NHL;
  - calendar 2026 for MLB and soccer, including the 2026 World Cup.

  `bulk.load_rows()` leaves those rows out unless `include_sealed=True`, which only a pre-registered test may pass. The seasons change if the owner decides differently (decision 1). In that case, edit `sealed:` in the config before the pull.

## Before buying

1. `git pull` on main, then `uv run pytest`. Everything passes, including `tests/test_bulk.py`, which covers the puller against mocked responses, and `tests/test_weather.py`, which covers the heat triggers.
2. Check free disk space: plan for about 3 GB under `data/raw/` for day one (about 16 GB if F4 is later earned; an extrapolation from two live responses). If the internal disk is short, point `MARKETS_DATA_DIR` at an external one.
3. Run `uv run markets odds5m probe` (no `--confirm`). It prints the `/events` sweep calls per sport, about 10,400 in all, and the number of probes.
4. Run `uv run markets odds5m plan` (free). With no schedules yet it prints zero calls per pull, in group order. That's expected.

## Day one

1. **New key, in all three `.env` files.** Put the paid key in `sharp-markets/.env`, `nfl-weather/.env` and `cfb-weather/.env` as `ODDS_API_KEY=...`, the same key in each.
   - The three projects share one quota file (`~/.cache/value-finder/odds_quota.json`). Each record carries a fingerprint of the key that made the call, and a project ignores records made with a different key. With one key everywhere, the alerts, close capture and live uses all see the paid plan's real balance.
   - `ops/install_live_uses.sh` refuses to install the live uses unless the three keys match ([`ops/LIVE_USES.md`](../../ops/LIVE_USES.md)).
2. **Probe (P0), about 10,700 credits at most:**
   ```bash
   uv run markets odds5m probe --confirm --max-credits 11000
   ```
   It does four things:
   - checks the key for free (`/v4/sports`) and prints the credits remaining;
   - sweeps historical `/events` for all 16 sport keys and writes exact schedules to `data/raw/_schedules/`;
   - prints the games per season;
   - runs seven single-call probes and prints one JSON line each: the four NFL billing checks, then one featured close each for NCAAF 2020, MLB 2024 and MLS 2024 (30 credits each at most).

   Check:
   - **Games per season.** Compare them with the estimates in `strategy-research/output/odds_5m_seasons.csv`. A season far below its estimate probably means a window in the config starts or ends too early; widen the window and rerun (cached sweeps cost nothing). Gaps in a league's coverage show up here too.
   - **Featured NFL, 10 books, 3 markets.** It must bill **30**. If it bills more, stop: the whole plan's cost model is wrong.
   - **Event-odds props, 10 books.** It must bill **10 × markets returned** (at most 60). This decides the cost of F2 and F3.
   - **Props, Pinnacle only.** Which prop markets Pinnacle quotes. That decides whether prop CLV can use a sharp fair line.
   - **Featured NFL 2020, sharp books.** Whether LowVig is in the 2020 data. If it isn't, 2020–21 sharp lines rest on Pinnacle and BetOnline.
   - **Featured NCAAF 2020, us10.** Whether Pinnacle prices college football in the earliest history (`books_returned`). If it doesn't, the CFB sharp close for 2020 rests on BetOnline and LowVig, and the Rule HT re-grade starts where Pinnacle does.
   - **Featured MLB 2024 and MLS 2024.** Whether totals and Pinnacle are in each sport's history (`markets_returned`, `books_returned`). If either is missing, the matching heat pull (HB1 or HS1) has nothing to grade against: tell the owner and skip it rather than substituting a book.
3. **Plan (free):**
   ```bash
   uv run markets odds5m plan
   ```
   It prints calls and the upper-bound credits per pull from the real schedules, with the pull's group and a running total. HB1 and HS1 stop with a message until step 6 has written their game list; that's expected. The estimate for day one is 238,590 (F1 162,210; F2 45,600; the rest small). If F1 or F2 comes out more than about 10% above its estimate, stop and tell the owner before pulling: a schedule window is probably wrong.
   - **Where 4,440,000 comes from:** 5,000,000 − 531,630 (the `--floor` reserve) − about 10,700 (the probe) − about 9,200 (October's live use on the same key: alerts 248, close capture ~385, trigger poller ~2,600, props log ~2,520, NBA collector from Oct 20 ~3,460) ≈ 4,448,500, rounded down. The floor stops every run at 4.47M spent, so a plan above this line can't finish anyway. Day one plus every gate is 2,304,050, so the ceiling only matters if a gate is misread.
4. **One week per sport for F1 and F2**, to check coverage before the full spend. Dry run first to see the cost, then set `--max-credits` a little above it:
   ```bash
   uv run markets odds5m week --pull F1,F2                     # prints the upper bound per pull
   uv run markets odds5m week --pull F1,F2 --confirm --max-credits 6000
   ```
   Each pull covers the first week of its latest unsealed season. Use `--week-of YYYY-MM-DD` to pick another week. After each pull, a `coverage:` line prints:
   - books returned and `missing_books` (books with no rows at all);
   - markets returned;
   - snapshots that came back empty;
   - the lag between the requested and returned snapshot, in minutes. It should be about 0–5, or 0–10 before September 2022.

   A book missing for a whole sport, or a market that never appears, is a decision for the hub: drop it from the config's book list, or accept it.
5. **F1, then F2, one at a time.** Set `--max-credits` to the plan figure plus about 5%:
   ```bash
   uv run markets odds5m full --pull F1 --confirm --max-credits 170000
   uv run markets odds5m check --pull F1
   uv run markets odds5m full --pull F2 --confirm --max-credits 48000
   uv run markets odds5m check --pull F2
   ```
   - At the default 8 requests a second, F1's roughly 5,400 calls take about 12 minutes and F2's 4,600 about 10. `--rate 20` is safe if nothing else is using the key heavily (the API allows 30).
   - If a run stops, read the `STOPPED:` line. A budget or floor stop is expected. A circuit-breaker stop means something needs a look before rerunning.
6. **The NBA sample week (N0), 7,540 credits, through the NBA pipeline, not the bulk puller.** PLAN.md §8 step 3 requires it before any full season; the week's Kalshi candles and trades are already cached, and the snapshots land where N1 will look:
   ```bash
   uv run markets odds-plan --start 2026-01-05 --end 2026-01-11                              # free: 754 snapshots, 7,540 credits
   uv run markets odds-pull --start 2026-01-05 --end 2026-01-11 --confirm --max-credits 8000
   uv run markets build
   uv run markets backtest --start 2026-01-05 --end 2026-01-11                               # H1, H2, lead-lag -> reports/
   ```
   Report the H1 and H2 tables to the hub: they are N1's gate.
7. **Heat closes (HB1, HS1), trigger first.** Run the free weather joins ([below](#weather-joins-for-the-heat-hypotheses-free-after-the-probe)), then:
   ```bash
   uv run markets weather qualifying                          # applies the registered triggers -> data/weather/heat_qualifying.csv
   uv run markets odds5m plan --pull HB1,HS1                  # the closes those games need, and the cost
   uv run markets odds5m full --pull HB1,HS1 --confirm --max-credits 16000
   uv run markets odds5m check --pull HB1,HS1
   ```
   `qualifying` prints, per hypothesis and season, the games at open venues, how many have a day-1 forecast, and how many qualify. Report those counts before pulling. The estimate is at most 4,380 for MLB (146 games) and 8,160 for soccer (about 272 matches), one close slot per game; the real counts replace them. The Open-Meteo fetch takes four or five daily runs, so this step usually lands a few days after the rest of day one. That's fine: nothing else waits on it.
8. **Stop.** Nothing else is pulled on day one. Reconcile credits against the manifest:
   ```bash
   uv run python -c "import duckdb; print(duckdb.sql(\"SELECT pull, count(*) calls, sum(credits_last) billed, sum(expected_credits) upper_bound, max(remaining) FROM 'data/raw/_manifest/oddsapi_manifest.csv' GROUP BY 1 ORDER BY 1\"))"
   ```
   The NBA week is logged by the NBA pipeline's own fetch log, not this manifest; add its `credits spent this run` line from step 6.

## Gated pulls: decided by about October 20

Each of these runs only when its gate has been read and passed. The gates are written in
[`odds-api-credits.md`](../../strategy-research/odds-api-credits.md#gated-inside-the-month-2065460-at-most-decided-by-about-october-20)
and in `strategy-research/odds_5m.py`; the short form:

| Pull | Credits at most | Gate | Command |
|---|---|---|---|
| F3a: NFL props 2025 at T−24h and the close | 34,200 | #41's pre-registration is written (line-vs-median hypothesis, distribution model, de-vig method, the free mean-minus-median gaps). Posted lines aren't on disk, so this slice is where the check runs. | `full --pull F3 --seasons 2025 --confirm --max-credits 36000` |
| F3b: NFL props 2023–24 and the 2026 games played | 102,600 | On 2025, the posted line sits above the empirical median in at least 3 of the 4 yardage markets, and the under's excess win rate over the de-vigged close is positive pooled | `full --pull F3 --confirm --max-credits 108000` (the 2025 slice is cached, so only the rest is fetched) |
| N1: NBA 2025-26 at 5 minutes, less the sample week | 486,440 | The sample week shows an H1 edge (net-of-fee flags with fills and positive CLV to Pinnacle's close) or an H2 lag (median catch-up lag ≥ 10 minutes), per PLAN.md | `full --pull N1 --confirm --max-credits 510000` |
| F4: hourly football, net of F1 | 1,442,220 | H16b on F1's daily grid: fading a move of a point or more earns ≥ 0.25 points of CLV with the interval above zero, in both sports, in 4 of 6 seasons | `full --pull F4 --confirm --max-credits 1520000`; about 48,000 calls, roughly two hours at `--rate 8` |

- The gate reads are analysis on data already pulled; they need no credits. Their results go to the hub, and the owner decides. A gate that isn't read by October 25 is a "no" for the month: the history doesn't expire, and March buys the same data with the 2026 season complete.
- Never widen a gate after reading the data. If a result is close, that's a "no".

## Weather joins, for the heat hypotheses (free; after the probe)

These need the schedules the probe writes. Open-Meteo, the MLB Stats API and ESPN are free and keyless, but they're blocked from the cloud, so all of this runs on the Mac. The hypotheses are pre-registered in [`docs/HEAT_HYPOTHESES.md`](HEAT_HYPOTHESES.md); amendment 4 makes them descriptive and closes-only. Nothing here joins odds or scores.

```bash
uv run markets weather check                      # venue tables: expect 0 problems
uv run markets weather venues --confirm           # game-level venues: MLB Stats API (every MLB game) and ESPN
                                                  # (Copa America 2024, Club World Cup 2025, Gold Cup 2025);
                                                  # about 60 + 30 calls; --leagues-too adds ESPN for the leagues (~350)
uv run markets weather plan                       # games placed, games unplaced (with why), Open-Meteo requests
uv run markets weather fetch --confirm --max-calls 9000   # one request per venue-month; rerun the next day for the rest
                                                  # (--max-calls is in weighted calls: a month counts as 2-3)
uv run markets weather join                       # -> data/weather/game_weather.parquet + unresolved.csv
uv run markets weather qualifying                 # -> data/weather/heat_qualifying.csv, the games HB1 and HS1 pull
```

- **Unplaced games.** `plan` lists them by reason. For "unknown home team", add the Odds API's spelling to `aliases` in `config/venues/soccer_homes.csv` or `mlb_homes.csv`, then rerun. Never guess a venue.
- **Rough size.** About 2,000 requests for MLB and 8,000–11,000 for soccer, archive and previous-run together. Open-Meteo counts a month-long request as 3 calls (one per 14 days), so that's about 30,000–39,000 weighted calls: four or five daily runs at `--max-calls 9000`, under the free tier's 10,000 a day. A run paces itself at 1.25 weighted calls a second (under the 5,000-an-hour limit), so each takes about two hours. `plan` prints the weighted total. Only the 2024–25 seasons feed the triggers, so `--sports` can narrow a run, but the whole table is cheap and useful.
- **Report to the hub:**
  - the `plan` counts (placed, unplaced by reason);
  - how many games have a day-1 forecast;
  - the `qualifying` counts per hypothesis and season, before any odds are joined.

## Afterwards

- Raw responses stay on the Mac. `data/` is gitignored, and nothing here commits them.
- Compact derived tables go into git only after the terms-of-use check (owner decision 6 in the plan).
- Report to the hub:
  - the probe's JSON lines, including the three coverage probes;
  - the `plan` totals;
  - each pull's final `run_calls` line and `coverage:` line;
  - the NBA week's H1/H2 tables;
  - the `qualifying` counts;
  - the reconciliation table.
