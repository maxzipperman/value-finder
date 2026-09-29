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

**These figures are estimates (note added September 29, 2026).** They were worked out before any schedule existed, on
a time grid slightly different from the puller's: an outside audit recomputed F1 at 164,910 against the 162,210 here,
and F4 net of F1 at 1,483,650 against 1,442,220. They are left as published. What binds on the day is what
`markets odds5m plan` prints from the real schedules after the probe, and each command's `--max-credits`. Every
`--max-credits` below is above the audit's figure for its pull (F1 170,000; F4 1,520,000).

## If a run stops

Every run that spends (`odds5m probe`, `week` and `full` with `--confirm`, and `odds-pull --confirm`) ends in one of
two ways. Either it finishes: each pull prints a `done:` line and the command exits with status 0. Or it stops: it
prints one `STOPPED:` line, then its summary (`stopped:` for a pull, `P0 stopped:` for the probe), and exits with
status 1. The one exception is a run refused before its first paid call (the first row below): nothing was bought, so
it prints only its `STOPPED` line, with no summary, and exits with status 1. A run never ends in a Python error dump.
Nothing fetched is lost: every answer is saved before it is used, so running the same command again picks up where it
stopped. To see the balance without spending anything, run `uv run markets odds5m balance --confirm`.

| The `STOPPED:` line says | What it means | What to do |
|---|---|---|
| `STOPPED before the first paid call, nothing spent: ...` (from `balance --confirm`, the same reasons print as `STOPPED: the free key check ...`, `STOPPED: the Odds API rejected the key ...` and so on) | The free key check refused to start the run: the key was rejected, the check didn't answer cleanly or without a readable balance, the balance is already below the floor, or the disk is full. For `odds-pull` it also means the plan needs more than `--max-credits`. | Read the rest of the line. A rejected key: check `ODDS_API_KEY` in `sharp-markets/.env`. No clean answer: wait a few minutes and run the same command again. Below the floor: stop and tell the owner. Disk full: free space ([Before buying](#before-buying), step 2). |
| `... could cost N; X of the M-credit run budget is counted` | The budget stop: the next try (or a retry) could take the count past `--max-credits`. If the line adds `(... of it for attempts that got no answer and may have been billed)`, that much is tries that timed out, each counted at its most possible cost. | Run the same command without `--confirm` to see what is left, then rerun it with `--max-credits` a little above that. If the whole pull comes out more than about 10% above its plan figure, tell the owner first. |
| `... took the count to X, past the M-credit run budget` | An answer counted more than the check before it allowed for. | Tell the hub before rerunning. |
| `... X credits remain at most; ... could cost N, and the floor is 531,630` | The floor stop: the account could drop below the reserve. | On day one this is an alarm, not a routine stop: about 4.47 million credits would be gone. Stop, run `balance --confirm`, and tell the owner. |
| `the account balance is unknown, so the floor of 531,630 can't be checked` | The run lost track of the balance. | Run `balance --confirm`, then the same command again; a new run reads the balance before it starts. |
| `... billed N credits; it should cost at most M` | One answer said it cost more than the most that call can cost. It was counted as it said. If the line has `(HTTP 500, not retried)` or another error status, it was an error answer, and the call was not tried again. | Tell the hub. Don't rerun: the cost model may be wrong. |
| `the billing could not be read: ...` | A successful answer didn't say what it cost. The most it could cost was counted. | Tell the hub before rerunning. The answer is saved, so a rerun won't buy it again. |
| `the billing cannot be trusted: ... reported N credits ..., less than the M the API's documentation charges for what came back` | A successful answer said it cost less than the API's own price list charges for what it returned (a 0 for a page of odds, say). The price-list figure was counted. | Tell the hub before rerunning. |
| `the account has fallen by N credits more than this run counted (the margin is M; ...)` | The account's balance has fallen further than everything the run counted, by more than the margin (300 credits, or 5% of `--max-credits` when that is more). Either something else is spending on this key, or the API charges more than it reports, or the balance the API reports runs behind its charges: then calls already charged (the previous command's last ones, say) look like spending this run didn't count, though nothing is wrong with the billing. A rehearsal whose fake API refreshed the balance only every 400 answers stopped F2 this way right after F1. | Run `balance --confirm`, note the time, and tell the hub. The hub checks the other jobs' logs for that time (the props log, the alerts, the trigger poller). If they explain the fall, rerun the same command. If they don't, don't rerun. |
| `the balance could not be read: ...` | A successful answer didn't say what is left. | Run `balance --confirm`, then tell the hub before rerunning. |
| `the Odds API rejected the key (401)` | The key stopped working mid-run. | Check `ODDS_API_KEY` in `sharp-markets/.env`, run `balance --confirm`, then rerun. |
| `HTTP 429 after retries (quota used up or rate limited): ...` | The API refused more requests. | Run `balance --confirm`. If credits are left, wait a few minutes and rerun; for `odds5m`, add `--rate 4` if it happens again. |
| `N errors in a row; the last was HTTP ...` | The API kept answering with errors. (In the probe, a sport whose sweeps are refused five times in a row with an HTTP 4xx is skipped instead, and the probe goes on with the next sport: see the sweeps row below. Five server errors in a row, HTTP 5xx, still stop it.) | Tell the hub before rerunning. |
| `no answer from the Odds API after the retries (...)` | The network or the API was down for more than a minute and a half. Each try that got no answer is counted at its most possible cost. | When the connection is back, run `balance --confirm`, then the same command again (the rerun's count starts from zero). |
| `... the API answered HTTP 200 with a body that is not JSON (...)` | A successful answer was not data (a web page from a network problem, say). It was counted and not saved. | Rerun later; a rerun asks for it again. If it happens twice, tell the hub. |
| `... could not be saved (...): is the disk full?`, `... could not be written ...`, `a file could not be read or written (...)` or `the cache could not be read (...)` | The disk is full or can't be read. An answer that couldn't be saved was counted and will be bought again. | Free some space ([Before buying](#before-buying), step 2), then rerun. |
| `interrupted (Ctrl-C). ...` | You pressed Ctrl-C. The line says what happened to the call that was out: a request with no answer yet, so it is counted at its most possible cost and a rerun may buy it again; or its answer had come back, so it is counted at what it cost (and if it was saved, a rerun won't buy it again); or `No request was out` (the next one was still waiting, so nothing more is counted); or `No call was out`. | Run the same command again; it resumes from the saved answers. |
| `the sweeps did not finish for N sport(s), so their schedules were not saved: ...` | The probe's `/events` sweeps for those sports didn't all come back, or came back with no games. For each sport the line says which: how many sweeps got an error answer (with the date and HTTP status of the first three), how many were skipped (a sport is skipped after five refusals in a row) or never reached; or that all its sweeps came back but listed no games while some were answered 404; or that they listed no games and the saved schedule, which has games, was kept. The schedule files from before are kept, and the other sports' schedules are saved. | Sweeps that got an error or weren't reached: rerun the probe (Day one, step 2); it buys only what is missing. If a rerun stops again on the same sweeps, or the line says the sweeps listed no games, don't rerun: tell the hub, which decides whether to go on without that sport. |
| `Odds API /historical/... -> HTTP ...: ... Nothing was cached for it.` (`odds-pull` only) | The API answered the NBA pipeline with an error instead of the snapshot (`odds-pull` stops at the first one). | Tell the hub before rerunning. |
| `unexpected error, probably a bug; tell the hub before rerunning (...)` | A bug. | Tell the hub before rerunning. |

A command refused before it calls anything (`full --pull F3` without `--seasons`, `full --pull HB1,HS1` before their
game list exists, `balance` without `--confirm`, `--retry-404` with a stage other than `week` or `full`) prints why
and exits with status 1 as well. A dry run of `probe`, `plan`, `week` or `full` exits 0.

The probe's last line after a stop says which of two things comes next. After a budget stop, a network failure, a full
disk, Ctrl-C, a rejected key, a rate limit (429), an answer that wasn't data, `the account balance is unknown`, or sweeps
that didn't finish, it says ``Rerun the same command until it prints `P0 done` ...`` (and, if it stops the same way
twice, to tell the hub). After a billing alarm (a call billed above its most possible cost, billing that can't be read
or trusted, a balance that can't be read, the account falling further than the run counted, the count past the
budget), the floor, repeated error answers, sweeps that listed no games, or a bug, it says `Tell the hub before
rerunning ...`: then don't rerun. A rerun would buy more of the same, and the answers behind the alarm are saved, so
the rerun wouldn't stop on them again and could end `P0 done` with the alarm gone from the screen.

**What can still be lost beyond `--max-credits`.** The run counts a call only once its answer is in, so three things
can pass the budget. A call charged above its most possible cost: the run stops right after it, having paid the
difference, however large, even when the answer reports that charge honestly. If the API charges more than it reports:
up to the margin plus one call's extra, plus the charges of as many answers as the balance header is late, before the
alarm stops the run (the margin is 8,500 credits on F1, the largest day-one pull: about 20 cents at $119 for 5,000,000
credits); with no limit if the balance never moves, or if it is late by a number of answers that keeps changing,
because then an old balance looks like credits added and the run starts again from it. Credits really added during a
run (a top-up, the monthly renewal) also forgive whatever went unexplained before them. And at Ctrl-C, the call that
was out, which a rerun may buy again. Two runs that share the key near the floor can each take as many calls past it as
the balance is late, plus one.

The run counts a featured snapshot with some of the markets asked for missing at 10 × the markets that came back,
because it isn't yet known whether the API bills the markets asked for (as its documentation says) or the ones
returned, and counting the markets asked for would stop every run at such a snapshot if the API bills the returned
ones. If one of Thursday's featured probes comes back with a market missing, its bill settles it, and the hub decides
then.

## How a run protects the credits

- **Dry run by default.** Without `--confirm`, no stage calls the API. Every stage without `--confirm` prints what it would do and the most it could cost.
- **A key check before anything is spent.** Every `--confirm` run, `odds-pull`'s included, starts with the free `/v4/sports` call. The run refuses to start (`STOPPED before the first paid call, nothing spent: ...`) when the key is rejected, the check doesn't come back cleanly or without a readable balance, the balance is already below the floor, or the disk is too full to write the check's row in the manifest.
- **What the run counts.** `--max-credits N` is checked before every try, first or retry, against the most that call could cost, and the run stops once its count passes N. It counts:
  - every answer, at the larger of what it says it cost (`x-requests-last`, a fraction rounded up) and what the API's documentation charges for what came back: 10 × the markets returned (of those asked for) × regions for odds, 1 for a list of games, nothing for an empty answer or an error. An error answer that is about to be retried (HTTP 429 or 5xx) is an answer too, counted before the retry;
  - every try that got no answer (a timeout, a dropped connection) at the most it could cost, to the end of the run, because it may have been charged. In a simulation of 5,000-call pulls with the usual 5% margin, tries timing out on up to 3 calls in 100 never stopped a run; on 5 in 100, 41 of 50 runs stopped on their budget near the end, and a rerun finishes them.

  The balance never adds to this count.
- **The balance: the floor and one alarm.** `--floor` defaults to 531,630: the 300K reserve plus the 231,630 freed by dropping X3 (`odds-pull` has the same default). Before every try the run checks that the try can't take the balance below it, going by the lower of the lowest balance an answer has reported and the key check's balance less the count. The alarm: when the account has fallen further than the run counted by more than the margin (300 credits, or 5% of `--max-credits` when that is more: 8,500 for F1, 550 for the probe), the run stops (`STOPPED: the account has fallen by ...`). Other uses of the key (about 300 credits a day in October, Day one, step 3) come nowhere near that during a run, but run one `markets` command at a time. A balance a few answers late did not stop an honest run in simulations (single 5,000-call pulls, late by a fixed 1 to 3 answers or by 0 to 3 varying: 100 runs of 100 finished for the probe's sweeps, F1, F3 and the NBA week). A balance held back longer can: the credits it doesn't show yet look like spending the run didn't count. With the balance refreshed only every 400 answers, F2 run right after F1, and the NBA week right after F3a, stopped on the alarm in 100 simulated runs of 100, and so did a week stage whose balance sometimes came from a copy 11 answers behind. Whether the real API does this is unknown until Thursday; the hub has the question. If the balance goes up during a run (credits added, the monthly renewal, or an out-of-date reading after a current one), the run starts again from the new balance and logs a warning (the first time, then a count at the end of the pull).
- **Billing the run can't read, or can't trust.** Every paid answer should say what it cost (`x-requests-last`) and what is left (`x-requests-remaining`). A successful answer that doesn't say what it cost counts the most it could cost and stops the run (`STOPPED: the billing could not be read ...`); one that says less than the documentation charges for what came back counts the documented cost and stops it (`... cannot be trusted ...`); one that doesn't say what is left stops it (`... balance could not be read ...`). The answer is saved, so a rerun won't buy it again; tell the hub before rerunning. A "not found" (404) or error answer without a readable cost counts the most it could cost and the run goes on. To read the balance without spending anything, run `uv run markets odds5m balance --confirm`.
- **Network failures.** Each call gets up to seven tries, spread over at least a minute and a half. If the API still can't be reached, the run stops with `STOPPED: no answer from the Odds API ...`. Nothing is saved for that call, so when the connection is back, the same command picks up where it stopped.
- **Answers that can't be kept.** If the disk is full, or a successful answer isn't readable data (for example a web page from a network problem), the run counts the call and stops (`STOPPED: ... could not be saved ...: is the disk full?`, or `STOPPED: ... a body that is not JSON`). Neither is saved, so a rerun asks again. A full disk means that call is bought again on the rerun, so free space first ([Before buying](#before-buying), step 2). A full disk anywhere else in a run (the key check, a schedule file) also ends with a `STOPPED:` line.
- **Ctrl-C.** Pressing Ctrl-C ends the run with `STOPPED: interrupted (Ctrl-C) ...`, the summary line and exit status 1. The line says how the call that was out was counted: at its most possible cost if its request had gone and no answer had come back, at what it cost if its answer had (with its manifest row), and not at all if no request was out (the next one was waiting for the rate limit or for a retry). Running the same command again resumes from the saved answers.
- **The key never shows.** Error messages, `STOPPED:` lines, the billing headers (if a server or proxy ever echoed the request into them), the collector's heartbeat notes and every log line of a `markets` command show the key as `REDACTED`. Every answer's body, successful or not, has the key blanked before it is saved, printed or logged: exactly the key and its URL-encoded forms, and nothing else, so a body that doesn't hold the key is saved exactly as the server sent it. If an answer with data ever held the key, the run logs a warning that the API echoed it.
- **Every run ends with a summary and an exit status.** After any `STOPPED:` line, each pull prints `done:` or `stopped:` with that pull's own calls fetched and credits, the credits of the whole run in brackets, the balance, and how many of the pull's calls are saved 404s (left out of the line printed after Ctrl-C, or after a full disk outside a pull, which doesn't read the cache): for example `done: 34 fetched, credits 680 (this run 2,330), remaining 4,987,078, cached 404s 0` (F2's line in step 4 of Day one, in a rehearsal). If some calls got an error answer (not saved, so a rerun asks for them again), the line says how many after `fetched`. The probe ends with `P0 done:` or `P0 stopped:`. A billing, network or disk problem, and a bug, end in these lines, never in a Python error dump; a bug's `STOPPED:` line starts `unexpected error, probably a bug`. The command exits with status 0 when it is done and 1 when it stopped.
- **Groups, not `all`.** `--pull` takes pull IDs or a group from the config: `day_one` (F1, F2, F3, HB1, HS1), `gated` (N1, F4), `march` (H1, N2, F5, F6). The `full` stage refuses `--pull all`, so nothing runs every pull in the config by accident.
- **F3 only by season slice.** F3 is bought in two slices: F3a is `--seasons 2025` (day one) and F3b is `--seasons 2023,2024,2026` (gated). `full` and `week` refuse F3 unless `--seasons` names exactly one of those, in any order; a trailing comma or an empty entry (`--seasons 2025,`) is ignored. So `full --pull F3` alone is refused, and so are four seasons at once, a season that doesn't exist, `full --pull day_one`, and a `week` of any season outside the slice. `full` also refuses `--seasons` for every other pull, because the plan buys those whole: `full --pull day_one --seasons 2025` would otherwise have cut F1 and F2 down to 2025 without a word. The dry run shows the same refusals, so you see them before spending, and each refusal prints the F3a and F3b commands. This is `require_seasons` on F3 in the config. It changes nothing about what a slice fetches or where it is stored.
- **Circuit breaker.** The run stops at once when an answer says it cost more than the call's most possible cost (`x-requests-last` above 10 × markets × regions, or above 1 for `/events`; an error answer about to be retried is then not retried), when a successful answer's cost can't be read or is below its documented cost, when the account falls further than the run counted by more than the margin, on HTTP 401 (key rejected), on HTTP 429 after retries (quota used up), and after 5 errors in a row (in the probe, a sport whose sweeps are refused five times in a row with an HTTP 4xx is skipped instead, and the other sports go on). The breaker can only see what a call cost after the API has billed it, so no code on our side can stop one overbilling call from being paid for. That is why the probe runs first: it tries one call of each kind before any pull. It is also why `--max-credits` stays tight on the first run of each kind of call.
- **The probe follows the same rules.** Its seven single calls go through the same budget, floor, billing and circuit-breaker checks. The first stop ends the probes, and the ones after it are listed as `not run`. A sport's schedule is saved only when all of its `/events` sweeps came back, so a probe that stops never replaces a good schedule with part of one; and an empty schedule is never saved when some of the sport's sweeps were answered 404, or over a saved schedule that has games. A sweep that got an error answer holds up only its own sport: the other schedules are saved and the seven probes still run (unless the sport is the NFL, whose games they start from), and the probe ends `STOPPED: the sweeps did not finish ...` with the sweep's date and HTTP status. A sport whose sweeps are refused five times in a row (HTTP 4xx) is skipped, and the count starts again with the next sport. After a stop, the probe's last line says whether to rerun or to tell the hub first ([If a run stops](#if-a-run-stops)).
- **Cache first and resumable.** Every answer is stored before it is used, under `data/raw/{sport_key}/oddsapi/...`. N1 is the exception: it is stored under `data/raw/nba/oddsapi_hist/`, where `markets build` (the NBA by default) reads it, and where the sample week's `odds-pull` snapshots go too. Rerunning a command skips everything saved, so a stopped or interrupted run resumes for free. Errors other than 404 are never saved, so a rerun asks for them again. A 404 (the API has nothing for that event or time) is saved as "nothing there at that time", so reruns don't ask again for thousands of absent events: each pull's `done:` or `stopped:` line counts them (`cached 404s N`; not the one after Ctrl-C), and so do `check` and the `coverage:` line (`cached_404`). To ask a pull's saved 404s again, add `--retry-404` to its `week` or `full` command (for example `uv run markets odds5m full --pull F2 --retry-404 --confirm --max-credits N`); the usual budget and floor apply, and a saved 404 is replaced only by a successful answer.
- **Manifest.** Every answer gets a row in `data/raw/_manifest/oddsapi_manifest.csv` (under `MARKETS_DATA_DIR` if you set it), an error answer that was retried included, and so does `odds-pull`'s, whose pull is `N0`. Each row has:
  - the requested and returned snapshot times;
  - credits billed (blank when the answer didn't say; the run counted the call's most possible cost instead) and the balance the answer reported;
  - the SHA-256 of the body as saved (after the key is blanked, if the body held it);
  - the cache key;
  - the sealed flag.
- **Sealed holdout.** Sealed seasons are pulled but never read by default:
  - the 2026 seasons of NFL and CFB;
  - 2026-27 for NBA and NHL;
  - calendar 2026 for MLB and soccer, including the 2026 World Cup.

  `bulk.load_rows()` leaves those rows out unless `include_sealed=True`, which only a pre-registered test may pass. The seasons change if the owner decides differently (decision 1). In that case, edit `sealed:` in the config before the pull. Each sealed season's dates in the config start at least a day before its first game and end at least a day after its last one, in UTC; the comment above each gives the two games and where the dates come from. (The NHL's 2026-27 season opened on September 29; its window starts September 28 since the hub's decision of September 29, which added three `/events` sweeps to the probe. A row whose game still falls in no season is judged by the call that fetched it: `load_rows()` leaves it out when that call was planned for a sealed game.)

  `markets build` reads `data/raw/nba/oddsapi_hist/` directly, where N1 and `odds-pull` store their snapshots, so it has its own guard. It leaves out odds rows for games in a sealed season, prints how many (`odds rows left out for games in sealed seasons`), and records them as a `sealed_odds_left_out` anomaly. A row with no readable game time is left out too, because its season can't be told; it is recorded as an `odds_row_without_commence_time` anomaly. A row whose game falls in no season is left out when the snapshot was taken inside a sealed season, and counted with that season (`2026-27 (game in no window)`). A saved answer that isn't readable data is skipped, counted (`cached odds responses that could not be read, skipped`) and recorded as an `odds_body_unreadable` anomaly. (`bulk.load_rows()` judges a row with no game time by its call instead: left out when the call was planned for a sealed game.) The puller also refuses to plan a sealed-season call for any pull stored in another pipeline's folder (N1).

## Before buying

1. `git pull` on main, then `uv run pytest`. Everything passes, including `tests/test_bulk.py`, which covers the puller and `odds-pull` against mocked responses, `tests/test_http.py`, which checks that the key never shows in error text, and `tests/test_weather.py`, which covers the heat triggers.
2. Check free disk space: plan for about 3 GB under `data/raw/` for day one (about 16 GB if F4 is later earned; an extrapolation from two live responses). If the internal disk is short, point `MARKETS_DATA_DIR` at an external one, and set it the same way for every command in this checklist, step 8's included.
3. Run `uv run markets odds5m probe` (no `--confirm`). It prints the `/events` sweep calls per sport, about 10,400 in all (10,434 on the morning of October 1), and the number of probes.
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

   **Go on only once the probe prints `P0 done`.** If it stops, its last line says what to do ([If a run stops](#if-a-run-stops), the paragraph under the table):
   - ``Rerun the same command until it prints `P0 done` ...`` (for example after a budget stop, a network failure, a full disk, Ctrl-C, or sweeps that didn't finish): do what the table says for the `STOPPED:` line, then rerun it. If it stops the same way twice, tell the hub. The sports whose sweeps didn't finish are listed as `incomplete, schedule not saved`, and their schedule files stay as they were. The sweeps already fetched are saved, so the rerun buys only what is missing.
   - `Tell the hub before rerunning ...` (after a billing alarm, the floor, repeated error answers, sweeps that listed no games, or a bug): don't rerun. A rerun would buy more, and it wouldn't show the alarm again. The probe's JSON lines still show what each probe billed (`billed`) against its most possible cost (`expected_max`).

   A sport whose sweeps are refused five times in a row (an HTTP 4xx answer, such as a date outside the API's history) is skipped after the fifth, and the probe goes on with the other sports; the `STOPPED:` line at the end gives the refused sweeps' dates and HTTP status and how many were skipped. If a rerun stops again on the same sweeps, don't keep rerunning: tell the hub. By then the other sports' schedules are saved and the seven probes have run, so the hub can decide to go on without that sport. The one exception is the NFL: the seven probes start from NFL games, so if it is the NFL's sweeps that are refused, the probes wait (`billing probes skipped: no NFL 2024 game in the schedule`). Five server errors in a row (HTTP 5xx) stop the whole probe with `STOPPED: 5 errors in a row ...` and `Tell the hub before rerunning`.

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
   - snapshots that came back empty, and calls saved as 404s (`cached_404`);
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
     - **Anything else** (the circuit breaker, billing or a balance that couldn't be read or trusted, the account falling further than the run counted, a network failure, a full disk, an unexpected error): something needs a look. Tell the hub before rerunning.
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

   `odds-pull` prints the plan again, then the key check (`key ok: ...`), then `nba odds-pull (N0): 754 calls, 0 cached, 754 to fetch, at most 7,540 credits` and, when it is done, `done: 754 fetched, credits 7,540 (this run 7,540), remaining ..., cached 404s 0`. It is the NBA pipeline's older command, but it now spends through the same code as `odds5m`, with the same protections: the free key check first, the same floor (`--floor`, default 531,630), the same count checked against the budget before every try, the billing checks, the alarm, the circuit breaker, and a `STOPPED:` line with its summary on every stop. It still refuses to start when the plan is above `--max-credits`. Each answer gets a manifest row with pull `N0`. It stops at the first error answer, and it never saves an answer that isn't readable data. If it stops, read [If a run stops](#if-a-run-stops); tell the hub before rerunning.
7. **Heat closes (HB1, HS1), trigger first.** Run the free weather joins ([below](#weather-joins-for-the-heat-hypotheses-free-after-the-probe)), then:
   ```bash
   uv run markets weather qualifying                          # applies the registered triggers -> data/weather/heat_qualifying.csv
   uv run markets odds5m plan --pull HB1,HS1                  # the closes those games need, and the cost
   uv run markets odds5m full --pull HB1,HS1 --confirm --max-credits 16000
   uv run markets odds5m check --pull HB1,HS1
   ```
   `qualifying` prints, per hypothesis and season, the games at open venues, how many have a day-1 forecast, and how many qualify. Report those counts before pulling. The estimate is at most 4,380 for MLB (146 games) and 8,160 for soccer (about 272 matches), one close slot per game; the real counts replace them. The Open-Meteo fetch takes four or five daily runs, so this step usually lands a few days after the rest of day one. That's fine: nothing else waits on it.
8. **Stop.** Nothing else is pulled on day one. Reconcile credits against the manifest. This reads the manifest wherever the data folder is (`MARKETS_DATA_DIR`, if you set it, or `sharp-markets/data`), one row per pull (`account` is the free key checks, `N0` the NBA week) and a last row, `all`, for the totals; `calls` counts answers, an error answer that was retried included:
   ```bash
   uv run python -c "import duckdb; from markets.settings import RAW_DIR; print(duckdb.sql(f\"SELECT coalesce(pull, 'all') AS pull, count(*) AS calls, sum(credits_last) AS billed, sum(expected_credits) AS upper_bound, min(remaining) AS lowest_balance FROM read_csv('{RAW_DIR}/_manifest/oddsapi_manifest.csv') GROUP BY ROLLUP (pull) ORDER BY pull NULLS LAST\"))"
   uv run markets odds5m balance --confirm                    # free: the balance now
   ```
   - A blank `credits_last` means that answer didn't say what it cost. The run counted that row's `upper_bound` instead, and the `billed` sum leaves it out.
   - `lowest_balance` is the lowest balance the API reported during each pull; the `all` row's is the lowest of the day. Compare it with what `balance --confirm` prints now. The balance now should be at or a little below it (the alerts and collectors keep spending); well below it means something was charged that the manifest doesn't show: tell the hub.

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
