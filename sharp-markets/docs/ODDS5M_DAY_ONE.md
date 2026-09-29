# The 5M month: day-one checklist

For the hub, on the Mac, once the owner has bought the 5M plan. The plan and its ranking are in
[`strategy-research/odds-api-credits.md`](../../strategy-research/odds-api-credits.md#the-5m-month-owner-decision-september-28-2026).
The pulls are defined in [`config/odds5m.yaml`](../config/odds5m.yaml) and run by
`uv run markets odds5m <stage>` (code: `src/markets/oddsapi/bulk.py`). Everything is GET-only.

Run every command from `sharp-markets/`.

## How a run protects the credits

- **Dry run by default.** Without `--confirm`, no stage calls the API. Every stage without `--confirm` prints what it would do and the most it could cost.
- **Run budget.** `--max-credits N` is checked before each call against that call's upper-bound cost, so a run can never go over N.
- **Reserve floor.** `--floor` defaults to 531,630: the 300K reserve plus the 231,630 freed by dropping X3. The run stops before the account's remaining credits would drop below it.
- **Circuit breaker.** The run stops at once:
  - when a call bills more than its upper bound (`x-requests-last` above 10 × markets × regions, or above 1 for `/events`);
  - on HTTP 401 (key rejected);
  - on HTTP 429 after retries (quota used up);
  - after 5 errors in a row.
- **Cache first and resumable.** Every response is stored before it is used, under `data/raw/{sport_key}/oddsapi/...`. N1 is the exception: it is stored under `data/raw/nba/oddsapi_hist/`, where `markets build --sport nba` reads it. Rerunning a command skips everything cached, so a stopped or interrupted run resumes for free. Errors aren't cached, so they are retried.
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

1. `git pull` on main, then `uv run pytest`. Everything passes, including `tests/test_bulk.py`, which covers the puller against mocked responses.
2. Check free disk space: plan for about 10 GB under `data/raw/`. If the internal disk is short, point `MARKETS_DATA_DIR` at an external one.
3. Run `uv run markets odds5m probe` (no `--confirm`). It prints the `/events` sweep calls per sport, about 10,400 in all.

## Day one

1. **New key, in all three `.env` files.** Put the paid key in `sharp-markets/.env`, `nfl-weather/.env` and `cfb-weather/.env` as `ODDS_API_KEY=...`, the same key in each.
   - The three projects share one quota file (`~/.cache/value-finder/odds_quota.json`). Each record carries a fingerprint of the key that made the call, and a project ignores records made with a different key. With one key everywhere, the alerts, close capture and live uses all see the paid plan's real balance.
   - `ops/install_live_uses.sh` refuses to install the live uses unless the three keys match.
2. **Probe (P0), about 10,600 credits at most:**
   ```bash
   uv run markets odds5m probe --confirm --max-credits 11000
   ```
   It does four things:
   - checks the key for free (`/v4/sports`) and prints the credits remaining;
   - sweeps historical `/events` for all 16 sport keys and writes exact schedules to `data/raw/_schedules/`;
   - prints the games per season;
   - runs four billing probes and prints one JSON line each.

   Check:
   - **Games per season.** Compare them with the estimates in `strategy-research/output/odds_5m_seasons.csv`. A season far below its estimate probably means a window in the config starts or ends too early; widen the window and rerun (cached sweeps cost nothing). Gaps in a league's coverage show up here too.
   - **Featured NFL, 10 books, 3 markets.** It must bill **30**. If it bills more, stop: the whole plan's cost model is wrong.
   - **Event-odds props, 10 books.** It must bill **10 × markets returned** (at most 60). This decides the cost of F2, F3, F5 and F6.
   - **Props, Pinnacle only.** Which prop markets Pinnacle quotes. That decides whether prop CLV can use a sharp fair line.
   - **Featured NFL 2020, sharp books.** Whether LowVig is in the 2020 data. If it isn't, 2020–21 sharp lines rest on Pinnacle and BetOnline.
3. **Plan (free):**
   ```bash
   uv run markets odds5m plan
   ```
   It prints calls and the upper-bound credits per pull from the real schedules, in value order, with a running total. The PR A estimate was 4.18M for F1 through F6 (X3 was dropped by the owner). If the running total passes **4,440,000**, drop pulls from the bottom of the list (F6 first, then N1) rather than trimming seasons, and tell the owner. Never go below the 531,630-credit reserve: that's 300K plus X3's credits, which the owner assigned to the reserve.
   - Where 4,440,000 comes from: 5,000,000 − 531,630 (the `--floor` reserve) − about 10,600 (the probe) − about 9,200 (October's live use on the same key: alerts 248, close capture ~385, trigger poller ~2,600, props log ~2,520, NBA collector from Oct 20 ~3,460) ≈ 4,448,600, rounded down. The floor stops every run at 4.47M spent, so a plan above this line can't finish anyway.
4. **One week per sport**, to check coverage before the big spend. Dry run first to see the cost, then set `--max-credits` a little above it:
   ```bash
   uv run markets odds5m week                                 # prints the upper bound per pull
   uv run markets odds5m week --confirm --max-credits 60000
   ```
   Each pull covers the first week of its latest unsealed season. Use `--week-of YYYY-MM-DD` to pick another week. After each pull, a `coverage:` line prints:
   - books returned and `missing_books` (books with no rows at all);
   - markets returned;
   - snapshots that came back empty;
   - the lag between the requested and returned snapshot, in minutes. It should be about 0–5, or 0–10 before September 2022.

   A book missing for a whole sport, or a market that never appears, is a decision for the hub: drop it from the config's book list, or accept it.
5. **Full pulls, one at a time, in plan order.** For each pull, set `--max-credits` to its plan figure plus about 5%:
   ```bash
   uv run markets odds5m full --pull F1 --confirm --max-credits 170000
   uv run markets odds5m check --pull F1
   uv run markets odds5m full --pull F2 --confirm --max-credits 110000
   ...
   ```
   The order is F1, F2, F3, B1, S1, F4, H1, N2, F5, N1, F6.
   - At the default 8 requests a second, the whole plan (about 160,000 calls) takes about 6 hours. The API allows 30 a second, so `--rate 20` is safe if nothing else is using the key heavily.
   - If a run stops, read the `STOPPED:` line. A budget or floor stop is expected. A circuit-breaker stop means something needs a look before rerunning.
6. **Reconcile credits** against the manifest:
   ```bash
   uv run python -c "import duckdb; print(duckdb.sql(\"SELECT pull, count(*) calls, sum(credits_last) billed, sum(expected_credits) upper_bound, max(remaining) FROM 'data/raw/_manifest/oddsapi_manifest.csv' GROUP BY 1 ORDER BY 1\"))"
   ```

## Weather joins, for the heat hypotheses (free; after the probe)

These need the schedules the probe writes. Open-Meteo, the MLB Stats API and ESPN are free and keyless, but they're blocked from the cloud, so all of this runs on the Mac. The hypotheses are pre-registered in [`docs/HEAT_HYPOTHESES.md`](HEAT_HYPOTHESES.md). Nothing here joins odds or scores.

```bash
uv run markets weather check                      # venue tables: expect 0 problems
uv run markets weather venues --confirm           # game-level venues: MLB Stats API (every MLB game) and ESPN
                                                  # (Copa America 2024, Club World Cup 2025, Gold Cup 2025);
                                                  # about 60 + 30 calls; --leagues-too adds ESPN for the leagues (~350)
uv run markets weather plan                       # games placed, games unplaced (with why), Open-Meteo requests
uv run markets weather fetch --confirm --max-calls 9000   # one request per venue-month; rerun the next day for the rest
uv run markets weather join                       # -> data/weather/game_weather.parquet + unresolved.csv
```

- **Unplaced games.** `plan` lists them by reason. For "unknown home team", add the Odds API's spelling to `aliases` in `config/venues/soccer_homes.csv` or `mlb_homes.csv`, then rerun. Never guess a venue.
- **Rough size.** About 2,000 requests for MLB and 8,000–11,000 for soccer, archive and previous-run together. That's two days on Open-Meteo's free tier of 10,000 calls a day.
- **Report to the hub:**
  - the `plan` counts (placed, unplaced by reason);
  - how many games have a day-1 forecast;
  - how many qualify under each trigger in 2024–25.

  Count the qualifying games before any odds are joined; the pre-registration needs at least 150 per hypothesis.

## Afterwards

- Raw responses stay on the Mac. `data/` is gitignored, and nothing here commits them.
- Compact derived tables go into git only after the terms-of-use check (owner decision 4 in the plan).
- Report to the hub:
  - the probe's JSON lines;
  - the `plan` totals;
  - each pull's final `run_calls` line and `coverage:` line;
  - the reconciliation table.
