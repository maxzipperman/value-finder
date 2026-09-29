# The 5M month: day-one checklist

For the hub, on the Mac, once the owner has bought the 5M plan on Thursday, October 1, 2026. The plan, its
gates and its March list are in
[`strategy-research/odds-api-credits.md`](../../strategy-research/odds-api-credits.md#the-5m-month-owner-decisions-september-28-2026-rewritten-september-29).
The pulls are defined in [`config/odds5m.yaml`](../config/odds5m.yaml) and run by
`uv run markets odds5m <stage>` (code: `src/markets/oddsapi/bulk.py`). Everything is GET-only.

Run every command from `sharp-markets/`.

**Day one buys at most 272,790 credits** (about 244K of it exists on October 1; the rest is 2026 games not yet played):
the probe, F1, F2, the first slice of F3, the NBA sample week, and the heat closes. Then it stops. F3b, N1 and F4 are
gated (below). The **hard ceiling for the whole month is 4,440,000 credits**, and day one plus every gate is 2,304,050.

## If a run stops

Every run that spends (`odds5m probe`, `week` and `full` with `--confirm`, and `odds-pull --confirm`) ends in one of
two ways. Either it finishes: each pull prints a `done:` line and the command exits with status 0. Or it stops: it
prints one `STOPPED:` line, then its summary (`stopped:` for a pull, `P0 stopped:` for the probe), and exits with
status 1. It never ends in a Python error dump. Nothing fetched is lost: every answer is saved before it is used, so
running the same command again picks up where it stopped. To see the balance without spending anything, run
`uv run markets odds5m balance --confirm`.

| The `STOPPED:` line says | What it means | What to do |
|---|---|---|
| `STOPPED before the first paid call, nothing spent: ...` | The free key check refused to start the run: the key was rejected, the check didn't answer cleanly or without a readable balance, the balance is already below the floor, or the disk is full. For `odds-pull` it also means the plan needs more than `--max-credits`. | Read the rest of the line. A rejected key: check `ODDS_API_KEY` in `sharp-markets/.env`. No clean answer: wait a few minutes and run the same command again. Below the floor: stop and tell the owner. Disk full: free space ([Before buying](#before-buying), step 2). |
| `... could cost N; X of the M-credit run budget is counted` | The budget stop: the next call (or the retry of one) could take the run past `--max-credits`. | Run the same command without `--confirm` to see what is left, then rerun it with `--max-credits` a little above that. If the whole pull comes out more than about 10% above its plan figure, tell the owner first. |
| `... X credits remain at most; ... could cost N, and the floor is 531,630` | The floor stop: the account could drop below the reserve. | On day one this is an alarm, not a routine stop: about 4.47 million credits would be gone. Stop, run `balance --confirm`, and tell the owner. |
| `the account balance is unknown, so the floor of 531,630 can't be checked` | The run lost track of the balance. | Run `balance --confirm`, then the same command again; a new run reads the balance before it starts. |
| `... billed N credits; it should cost at most M` | One call cost more than its most possible cost. | Tell the hub. Don't rerun: the cost model may be wrong. |
| `the billing could not be read: ...` | A successful answer didn't say what it cost. The most it could cost was counted. | Tell the hub before rerunning. The answer is saved, so a rerun won't buy it again. |
| `the billing cannot be trusted: ... reported N credits ..., less than the M the API's documentation charges for what came back` | A successful answer said it cost less than the API's own price list charges for what it returned (a 0 for a page of odds, say). The price-list figure was counted. | Tell the hub before rerunning. |
| `the account is being charged more than the API reports: ...` | On three calls in a row the balance fell by more than each call said it cost, plus its most possible cost. | Run `balance --confirm` and compare it with the lowest balance in the manifest (Day one, step 8). Tell the hub; don't rerun. |
| `the balance could not be read: ...` | A successful answer didn't say what is left. | Run `balance --confirm`, then tell the hub before rerunning. |
| `the Odds API rejected the key (401)` | The key stopped working mid-run. | Check `ODDS_API_KEY` in `sharp-markets/.env`, run `balance --confirm`, then rerun. |
| `HTTP 429 after retries (quota used up or rate limited): ...` | The API refused more requests. | Run `balance --confirm`. If credits are left, wait a few minutes and rerun; for `odds5m`, add `--rate 4` if it happens again. |
| `N errors in a row; the last was HTTP ...` | The API kept answering with errors. | Tell the hub before rerunning. |
| `no answer from the Odds API after the retries (...)` | The network or the API was down for more than a minute and a half. | When the connection is back, run `balance --confirm` (it shows what the failed tries really cost), then the same command again. |
| `... the API answered HTTP 200 with a body that is not JSON (...)` | A successful answer was not data (a web page from a network problem, say). It was counted and not saved. | Rerun later; a rerun asks for it again. If it happens twice, tell the hub. |
| `... could not be saved (...): is the disk full?`, `... could not be written ...`, `a file could not be read or written (...)` or `the cache could not be read (...)` | The disk is full or can't be read. An answer that couldn't be saved was counted and will be bought again. | Free some space ([Before buying](#before-buying), step 2), then rerun. |
| `interrupted (Ctrl-C) ...` | You pressed Ctrl-C. The call that was out is counted at its most possible cost. | A rerun of the same command resumes from the saved answers. That one call may be bought again. |
| `the sweeps did not finish for N sport(s) (...), so their schedules were not saved` | The probe's `/events` sweeps for those sports didn't all come back. The schedule files from before are kept. | Rerun the probe until it prints `P0 done` (Day one, step 2). |
| `Odds API /historical/... -> HTTP ...: ... Nothing was cached for it.` (`odds-pull` only) | The API answered the NBA pipeline with an error instead of the snapshot (`odds-pull` stops at the first one). | Tell the hub before rerunning. |
| `unexpected error, probably a bug; tell the hub before rerunning (...)` | A bug. | Tell the hub before rerunning. |

A command refused before it calls anything (`full --pull F3` without `--seasons`, `full --pull HB1,HS1` before their
game list exists, `balance` without `--confirm`) prints why and exits with status 1 as well. A dry run of `probe`,
`plan`, `week` or `full` exits 0.

**What can still be lost beyond `--max-credits`.** With honest billing headers, nothing. But the API charges for a
call before we see its answer, so our side can only count after the fact, and it can only see what the API tells it.
So a run can end past its budget or its floor by: one call's most possible cost (30 credits for F1, 20 for F2, 60 for
F3, 10 for the NBA week) when the balance arrives one answer late and a timed-out try was charged; that one call's
charge when a call is billed above its most possible cost; three calls' charges (four if the balance is also late)
when the API charges more than it reports by more than a call's most possible cost (a smaller extra never stops the
run, but the budget still holds, because the run counts the balance; the credits just buy less data); the one call
that was out at a Ctrl-C, which a rerun may buy again; and one call when two runs share the key near the floor. Only
an API that reports less than it charges while its balance never moves could spend past the budget without a stop,
and only on answers our code can't price above what was reported (a snapshot where some of the markets asked for, or
all the odds, are missing). Nothing in the answers would show that; the account page on the Odds API site would.

## How a run protects the credits

- **Dry run by default.** Without `--confirm`, no stage calls the API. Every stage without `--confirm` prints what it would do and the most it could cost.
- **A key check before anything is spent.** Every `--confirm` run starts with the free `/v4/sports` call, and `odds-pull` now does the same. The run refuses to start, and prints `STOPPED before the first paid call, nothing spent: ...`, when:
  - the key is rejected (check `ODDS_API_KEY` in `sharp-markets/.env`);
  - the check doesn't come back cleanly, or comes back without a readable balance (wait a few minutes and run the same command again);
  - the balance is already below the floor. The message gives both numbers. Stop and tell the owner;
  - the disk is too full to write the check's row in the manifest.
- **Run budget.** `--max-credits N` is checked before each call, and before each retry of a call, against the most that call could cost. What the run counts as spent is the largest of three figures:
  - what the answers say they cost (`x-requests-last`);
  - what the API's documentation charges for what came back: 10 × the markets returned (of those asked for) × regions for odds, 1 for a list of games, nothing for an empty answer;
  - how far the account's balance has actually fallen since the key check.

  So a call the API bills twice (a first try that timed out but was still charged) still counts, and so does a call reported as free. A run stays within N, with the exceptions in [If a run stops](#if-a-run-stops).
  - Other uses of the key while a run is going (the alerts, the collectors) also lower the balance, so they count toward N. That is about 300 credits a day in October (Day one, step 3), and only makes a run stop a little early. Run one `markets` command at a time, though: two pulls at once would each count the other's spending.
  - When the balance falls by more than a call said it cost, the run prints a line saying so (`the balance fell by ..., more than the ... this call was counted at`). One now and then is the other uses of the key, or a retried call. If it happens on three calls in a row by more than the call's most possible cost, the run stops: `STOPPED: the account is being charged more than the API reports`. In a simulation of 100 runs of 5,000 calls each, other uses of the key at their real rate (a few credits an hour) never stopped a run this way. For F1's calls it takes another program spending more than 30 credits between each of our calls, three calls running; for the probe's sweeps (most possible cost 1), another program paying for a call between about 1 in 20 of ours, which is 0.4 calls a second. Well before that, others' spending passes the 5% margin in `--max-credits` and the run stops on its budget instead.
- **Reserve floor.** `--floor` defaults to 531,630: the 300K reserve plus the 231,630 freed by dropping X3. `odds-pull` has the same default. The run stops before the account's remaining credits could drop below it, counting any try that got no answer as if it had been charged. If the run ever loses track of the balance, it stops rather than guess (`STOPPED: the account balance is unknown ...`). It never believes a balance that goes up during a run, or one that makes no sense; it keeps the lower figure.
- **Billing the run can't read, or can't trust.** Every paid answer should say what it cost (`x-requests-last`) and what is left (`x-requests-remaining`).
  - If a successful answer doesn't say what it cost, or says something that isn't a number, the run counts the most that call could have cost, keeps the answer, and stops: `STOPPED: the billing could not be read ...`. A cost with a fraction is rounded up.
  - If it says less than the documentation charges for what came back, the run counts the documented cost, keeps the answer, and stops: `STOPPED: the billing cannot be trusted ...`.
  - If it doesn't say what is left, the run stops: `STOPPED: the balance could not be read ...`.
  - What to do: tell the hub before rerunning. The answer is saved, so a rerun won't buy it again, but the next call would probably have the same problem. To read the balance without spending anything, run `uv run markets odds5m balance --confirm`. It makes only the free key check and prints `key ok: ... credits remaining`. Compare that with the lowest balance in the manifest (Day one, step 8).
  - A "not found" (404) or error answer without a readable cost doesn't stop the run, because the API's documentation doesn't charge for answers with no data. The run still counts the most that call could have cost, so the budget errs toward stopping early. Errors still stop the run after 5 in a row (`odds-pull` stops at the first).
- **Network failures.** Each call gets up to seven tries, spread over at least a minute and a half. A try that gets no answer might still have been charged, so the run counts the most it could have cost. That count comes off only by as much as the balance shows was really charged, or two balance readings later, when even a balance that arrives one answer late has caught up. The run checks the budget and the floor again before each new try. If the API still can't be reached, the run stops with `STOPPED: no answer from the Odds API ...`. Nothing is saved for that call, so when the connection is back, the same command picks up where it stopped. Run `balance --confirm` first if you want to see what the failed tries really cost.
- **Answers that can't be kept.** If the disk is full, or a successful answer isn't readable data (for example a web page from a network problem), the run counts the call and stops (`STOPPED: ... could not be saved ...: is the disk full?`, or `STOPPED: ... a body that is not JSON`). Neither is saved, so a rerun asks again. A full disk means that call is bought again on the rerun, so free space first ([Before buying](#before-buying), step 2). A full disk anywhere else in a run (the key check, a schedule file) also ends with a `STOPPED:` line.
- **Ctrl-C.** Pressing Ctrl-C ends the run with `STOPPED: interrupted (Ctrl-C) ...`, the summary line and exit status 1. The call that was out at that moment may have been charged, so it is counted at its most possible cost. Running the same command again resumes from the saved answers; that one call may be bought again.
- **The key never shows.** Error messages, error pages the server sends back, the collector's heartbeat notes and every log line of a `markets` command show the key as `REDACTED`. A saved "not found" answer is stored the same way.
- **Every run ends with a summary and an exit status.** After any `STOPPED:` line, each pull prints `done:` or `stopped:` with that pull's own calls fetched and credits, the credits of the whole run in brackets, and the balance: for example `done: 34 fetched, credits 680 (this run 2,330), remaining 4,987,091`. The probe ends with `P0 done:` or `P0 stopped:`. A billing, network or disk problem, and a bug, end in these lines, never in a Python error dump; a bug's `STOPPED:` line starts `unexpected error, probably a bug`. The command exits with status 0 when it is done and 1 when it stopped.
- **Groups, not `all`.** `--pull` takes pull IDs or a group from the config: `day_one` (F1, F2, F3, HB1, HS1), `gated` (N1, F4), `march` (H1, N2, F5, F6). The `full` stage refuses `--pull all`, so nothing runs every pull in the config by accident.
- **F3 only by season slice.** F3 is bought in two slices: F3a is `--seasons 2025` (day one) and F3b is `--seasons 2023,2024,2026` (gated). `full` and `week` refuse F3 unless `--seasons` names exactly one of those, in any order; a trailing comma or an empty entry (`--seasons 2025,`) is ignored. So `full --pull F3` alone is refused, and so are four seasons at once, a season that doesn't exist, `full --pull day_one`, and a `week` of any season outside the slice. `full` also refuses `--seasons` for every other pull, because the plan buys those whole: `full --pull day_one --seasons 2025` would otherwise have cut F1 and F2 down to 2025 without a word. The dry run shows the same refusals, so you see them before spending, and each refusal prints the F3a and F3b commands. This is `require_seasons` on F3 in the config. It changes nothing about what a slice fetches or where it is stored.
- **Circuit breaker.** The run stops at once:
  - when a call bills more than its most possible cost (`x-requests-last` above 10 × markets × regions, or above 1 for `/events`);
  - when a call reports less than the documented cost of what it returned;
  - when the balance falls by more than the reported cost plus the most possible cost on three calls in a row;
  - on HTTP 401 (key rejected);
  - on HTTP 429 after retries (quota used up);
  - after 5 errors in a row.

  The breaker can only see what a call cost after the API has billed it, so no code on our side can stop one overbilling call from being paid for. That is why the probe runs first: it tries one call of each kind before any pull. It is also why `--max-credits` stays tight on the first run of each kind of call.
- **The probe follows the same rules.** Its seven single calls go through the same budget, floor, billing and circuit-breaker checks. The first stop ends the probes, and the ones after it are listed as `not run`. A sport's schedule is saved only when all of its `/events` sweeps came back, so a probe that stops never replaces a good schedule with part of one.
- **Cache first and resumable.** Every answer is stored before it is used, under `data/raw/{sport_key}/oddsapi/...`. N1 is the exception: it is stored under `data/raw/nba/oddsapi_hist/`, where `markets build` (the NBA by default) reads it, and where the sample week's `odds-pull` snapshots go too. Rerunning a command skips everything saved, so a stopped or interrupted run resumes for free. Errors aren't saved, so they are retried.
- **Manifest.** Every answered request gets a row in `data/raw/_manifest/oddsapi_manifest.csv` (under `MARKETS_DATA_DIR` if you set it), including `odds-pull`'s, whose pull is `N0`. Each row has:
  - the requested and returned snapshot times;
  - credits billed (blank when the answer didn't say; the run counted the call's most possible cost instead) and credits remaining;
  - the SHA-256 of the body;
  - the cache key;
  - the sealed flag.
- **Sealed holdout.** Sealed seasons are pulled but never read by default:
  - the 2026 seasons of NFL and CFB;
  - 2026-27 for NBA and NHL;
  - calendar 2026 for MLB and soccer, including the 2026 World Cup.

  `bulk.load_rows()` leaves those rows out unless `include_sealed=True`, which only a pre-registered test may pass. The seasons change if the owner decides differently (decision 1). In that case, edit `sealed:` in the config before the pull. Each sealed season's dates in the config start at least a day before its first game and end at least a day after its last one, in UTC; the comment above each gives the two games and where the dates come from. (The NHL's 2026-27 season opened on September 29, two days before its window starts; the hub decides whether to move it, which adds three `/events` sweeps to the probe.)

  `markets build` reads `data/raw/nba/oddsapi_hist/` directly, where N1 and `odds-pull` store their snapshots, so it has its own guard. It leaves out odds rows for games in a sealed season, prints how many (`odds rows left out for games in sealed seasons`), and records them as a `sealed_odds_left_out` anomaly. A row with no readable game time is left out too, because its season can't be told; it is recorded as an `odds_row_without_commence_time` anomaly. A saved answer that isn't readable data is skipped, counted (`cached odds responses that could not be read, skipped`) and recorded as an `odds_body_unreadable` anomaly. (`bulk.load_rows()` judges a row with no game time by its call instead: left out when the call was in a sealed season.) The puller also refuses to plan a sealed-season call for any pull stored in another pipeline's folder (N1).

## Before buying

1. `git pull` on main, then `uv run pytest`. Everything passes, including `tests/test_bulk.py`, which covers the puller and `odds-pull` against mocked responses, `tests/test_http.py`, which checks that the key never shows in error text, and `tests/test_weather.py`, which covers the heat triggers. One test is marked `xfailed`: the NHL window, above.
2. Check free disk space: plan for about 3 GB under `data/raw/` for day one (about 16 GB if F4 is later earned; an extrapolation from two live responses). If the internal disk is short, point `MARKETS_DATA_DIR` at an external one, and set it the same way for every command in this checklist, step 8's included.
3. Run `uv run markets odds5m probe` (no `--confirm`). It prints the `/events` sweep calls per sport, about 10,400 in all (10,431 on the morning of October 1), and the number of probes.
4. Run `uv run markets odds5m plan` (free). With no schedules yet it prints ``no schedule yet for [...]: run `markets odds5m probe --confirm` first``, then one line per pull in group order: F1, F2, F3, HB1 and HS1 (`day_one`), N1 and F4 (`gated`), and H1, N2, F5 and F6 (`march`). Every line shows `0 calls`. HB1's and HS1's lines end ``waits for `markets weather qualifying` (.../data/weather/heat_qualifying.csv is not written yet); counted as 0 for now``, where `...` is the data folder. It exits with status 0. That's all expected.

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

   **Rerun the probe until it prints `P0 done` before going on.** If it stops, the sports whose sweeps didn't finish are listed as `incomplete, schedule not saved`, and their schedule files stay as they were. The sweeps already fetched are saved, so the rerun buys only what is missing.

   Check:
   - **Games per season.** Compare them with the estimates in `strategy-research/output/odds_5m_seasons.csv`. A season far below its estimate probably means a window in the config starts or ends too early; widen the window and rerun (saved sweeps cost nothing). Gaps in a league's coverage show up here too.
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
   It prints one line per pull, in group order: the pull, its group, its calls, the most it could cost (`at most ... credits to fetch`), a running total (`cumulative`) and its sealed calls. HB1 and HS1 print ``0 calls  waits for `markets weather qualifying` (.../data/weather/heat_qualifying.csv is not written yet); counted as 0 for now`` until step 7 has written their game list; that's expected, and the plan goes on to N1, F4 and the March pulls. It exits with status 0. The estimate for day one is 272,790 (F1 162,210; F2 45,600; F3's 2025 slice 34,200; the rest small).
   - F3's line here covers all its seasons (about 136,800) and ends ``(all seasons; `full` needs one slice: --seasons 2025 (F3a), --seasons 2023,2024,2026 (F3b))``. For the day-one slice, run `uv run markets odds5m plan --pull F3 --seasons 2025` and compare that with 34,200.
   - If F1, F2 or F3's 2025 slice comes out more than about 10% above its estimate, stop and tell the owner before pulling: a schedule window is probably wrong.
   - **Where 4,440,000 comes from:** 5,000,000 − 531,630 (the `--floor` reserve) − about 10,700 (the probe) − about 9,200 (October's live use on the same key: alerts 248, close capture ~385, trigger poller ~2,600, props log ~2,520, NBA collector from Oct 20 ~3,460) ≈ 4,448,500, rounded down. The floor stops every run at 4.47M spent, so a plan above this line can't finish anyway. Day one plus every gate is 2,304,050, so the ceiling only matters if a gate is misread.
4. **One week per sport for F1 and F2**, to check coverage before the full spend. Dry run first to see the cost, then set `--max-credits` a little above it:
   ```bash
   uv run markets odds5m week --pull F1,F2                     # prints the most each pull could cost
   uv run markets odds5m week --pull F1,F2 --confirm --max-credits 6000
   ```
   Each pull covers the first week of its latest unsealed season. Use `--week-of YYYY-MM-DD` to pick another week. After each pull, a `coverage:` line prints:
   - books returned and `missing_books` (books with no rows at all);
   - markets returned;
   - snapshots that came back empty;
   - the lag between the requested and returned snapshot, in minutes. It should be about 0–5, or 0–10 before September 2022.

   A book missing for a whole sport, or a market that never appears, is a decision for the hub: drop it from the config's book list, or accept it.
5. **F1, then F2, then F3's 2025 slice, one at a time.** Set `--max-credits` to the plan figure plus about 5%:
   ```bash
   uv run markets odds5m full --pull F1 --confirm --max-credits 170000
   uv run markets odds5m check --pull F1
   uv run markets odds5m full --pull F2 --confirm --max-credits 48000
   uv run markets odds5m check --pull F2
   uv run markets odds5m full --pull F3 --seasons 2025 --confirm --max-credits 36000     # F3a: the 2025 season only
   uv run markets odds5m check --pull F3 --seasons 2025
   ```
   - At the default 8 requests a second, F1's calls (at most about 5,400) take about 12 minutes, F2's (at most 2,280, since each costs 20; the rehearsal's schedules gave 1,806) about 5, and F3a's 570 about a minute. `--rate 20` is safe if nothing else is using the key heavily (the API allows 30).
   - If a run stops, read the `STOPPED:` line and do what [If a run stops](#if-a-run-stops) says for it. In short:
     - **Budget stop** (`... run budget is counted`): the pull needed more than `--max-credits`. Run the same command without `--confirm` to see what is left to fetch, then rerun it with `--max-credits` a little above that. If the whole pull comes out more than about 10% above its plan figure, stop and tell the owner first.
     - **Floor stop** (`... the floor is 531,630`): on day one this is an alarm, not a routine stop. The account starts near 5,000,000, so reaching the floor means about 4.47 million credits are gone. Stop and tell the owner; run `balance --confirm` to read the balance.
     - **Ctrl-C** (`interrupted`): run the same command again; it resumes, and may buy again the one call that was out.
     - **Anything else** (the circuit breaker, billing or a balance that couldn't be read or trusted, a network failure, a full disk, an unexpected error): something needs a look. Tell the hub before rerunning.
   - F3 always needs exactly one slice: `--seasons 2025` is F3a, the day-one slice (34,200 at most); F3b (`--seasons 2023,2024,2026`) is gated (below). The puller refuses anything else, in `full` and in `week`, dry run included. Without the guard, `full --pull F3` would have pulled all of 2023–26 (136,800).
   - **The price-engine backtest (#8, #53), free, once F1 is in.**
     - The rules are registered: [`PRICE_ENGINE_PREREGISTRATION.md`](PRICE_ENGINE_PREREGISTRATION.md), September 29, 2026 (PR #56), before F1 existed; the run must come after it. At registration `PRIOR_COUNT` in `price_engine/engine.py` and the file's section 8 were set to STATUS.md's running count that day, 233 (so 271 with its 38 variants, bar p < 0.000185). The tests fail if the two disagree.
     - Then run `uv run markets price-engine`. It needs no credits, and it writes `reports/price_engine/report.md` and `results.csv`.
     - Report its eight primary verdicts to the hub.
6. **The NBA sample week (N0), 7,540 credits, through the NBA pipeline, not the bulk puller.** PLAN.md §8 step 3 requires it before any full season; the week's Kalshi candles and trades are already cached, and the snapshots land where N1 will look:
   ```bash
   uv run markets odds-plan --start 2026-01-05 --end 2026-01-11                              # free: 754 snapshots, 7,540 credits
   uv run markets odds-pull --start 2026-01-05 --end 2026-01-11 --confirm --max-credits 8000
   uv run markets build
   uv run markets backtest --start 2026-01-05 --end 2026-01-11                               # H1, H2, lead-lag -> reports/
   ```
   Report the H1 and H2 tables to the hub: they are N1's gate.

   `odds-pull` prints the plan again, then the key check (`key ok: ...`), then `nba odds-pull (N0): 754 calls, 0 cached, 754 to fetch, at most 7,540 credits` and, when it is done, `done: 754 fetched, credits ... (this run ...), remaining ...`. It is the NBA pipeline's older command, but it now spends through the same code as `odds5m`, with the same protections: the free key check first, the same floor (`--floor`, default 531,630), the budget checked before every call and retry, the billing and balance checks, the circuit breaker, and a `STOPPED:` line with its summary on every stop. It still refuses to start when the plan is above `--max-credits`. Each paid request gets a manifest row with pull `N0`. It stops at the first error answer, and it never saves an answer that isn't readable data. If it stops, read [If a run stops](#if-a-run-stops); tell the hub before rerunning.
7. **Heat closes (HB1, HS1), trigger first.** Run the free weather joins ([below](#weather-joins-for-the-heat-hypotheses-free-after-the-probe)), then:
   ```bash
   uv run markets weather qualifying                          # applies the registered triggers -> data/weather/heat_qualifying.csv
   uv run markets odds5m plan --pull HB1,HS1                  # the closes those games need, and the cost
   uv run markets odds5m full --pull HB1,HS1 --confirm --max-credits 16000
   uv run markets odds5m check --pull HB1,HS1
   ```
   `qualifying` prints, per hypothesis and season, the games at open venues, how many have a day-1 forecast, and how many qualify. Report those counts before pulling. The estimate is at most 4,380 for MLB (146 games) and 8,160 for soccer (about 272 matches), one close slot per game; the real counts replace them. The Open-Meteo fetch takes four or five daily runs, so this step usually lands a few days after the rest of day one. That's fine: nothing else waits on it.
8. **Stop.** Nothing else is pulled on day one. Reconcile credits against the manifest. This reads the manifest wherever the data folder is (`MARKETS_DATA_DIR`, if you set it, or `sharp-markets/data`), one row per pull (`account` is the free key checks, `N0` the NBA week) and a last row, `all`, for the totals:
   ```bash
   uv run python -c "import duckdb; from markets.settings import RAW_DIR; print(duckdb.sql(f\"SELECT coalesce(pull, 'all') AS pull, count(*) AS calls, sum(credits_last) AS billed, sum(expected_credits) AS upper_bound, min(remaining) AS lowest_balance FROM read_csv('{RAW_DIR}/_manifest/oddsapi_manifest.csv') GROUP BY ROLLUP (pull) ORDER BY pull NULLS LAST\"))"
   uv run markets odds5m balance --confirm                    # free: the balance now
   ```
   - A blank `credits_last` means that answer didn't say what it cost. The run counted that row's `upper_bound` instead, and the `billed` sum leaves it out.
   - `lowest_balance` is the lowest balance each pull saw; the `all` row's is the lowest of the day. Compare it with what `balance --confirm` prints now. The balance now should be at or a little below it (the alerts and collectors keep spending); well below it means something was charged that the manifest doesn't show: tell the hub.

## Gated pulls: decided by about October 20

Each of these runs only when its gate has been read and passed. The gates are written in
[`odds-api-credits.md`](../../strategy-research/odds-api-credits.md#gated-inside-the-month-2031260-at-most-decided-by-about-october-20)
and in `strategy-research/odds_5m.py`; the short form:

| Pull | Credits at most | Gate | Command |
|---|---|---|---|
| F3b: NFL props 2023–24 and the 2026 games played | 102,600 | On the 2025 slice, graded as #10's pre-registration draft says (`strategy-research/README.md`, idea 7; it goes into a pre-registration file before the rows are joined to outcomes): the pooled excess under rate over the de-vigged close is positive in the primary markets (receiving and rushing yards), and the posted line sits above the player's same-season median in both | `full --pull F3 --seasons 2023,2024,2026 --confirm --max-credits 108000` (F3 needs `--seasons`; the 2025 slice is already cached) |
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
  - each pull's final `done:` line and `coverage:` line;
  - the NBA week's H1/H2 tables;
  - the `qualifying` counts;
  - the reconciliation table.
