# PR 63 review, reviewer A: the rules, what is bought, sealed data, the key, and the audit's cases

- Branch `bulk-puller-followup` at cc14201 (`$S/pr63`), compared with origin/main at 4bf0497 (`$S/main63`). `S=/tmp/claude-0/-home-user-value-finder/d7012428-080d-54f3-a1da-3ceb35298eec/scratchpad`.
- Scope: brief steps 1, 2, 6, 7, 8 and 9, plus a check of the paths the branch touches. Other reviewers covered the large simulations, the `headers` verdicts and the runbook rehearsal, so I did not run those.
- Everything ran against fake sessions or raw HTTP servers on 127.0.0.1, with `ODDS_API_KEY=FAKESECRETKEY999` and `MARKETS_DATA_DIR` inside `$S/revA`. I made no outside request and fixed nothing.
- `$S/main63` is back to clean (`git status` shows nothing). I deleted every cache and data folder I created; the scripts and outputs are still in `$S/revA`.
- The branch suite passes: 245 passed (`uv run pytest -q -o addopts="" -p no:cacheprovider`, 152 s).

## Findings

### 1. MAJOR: the new NCAAF 2026 window end changes what the March pulls buy
- **What it breaks:** step 6 and the brief's "Nothing that gets bought may change except the approved NHL window". By the severity table this is major: "a change to what is bought other than the NHL's three sweeps and H1's 27 calls".
- **Where:** `config/odds5m.yaml:49` moves the NCAAF 2026 sealed window's end from 2027-01-25 to 2027-01-27. The CFP title game kicks off at 2027-01-26T00:30Z. On main that game is in no window, so no pull plans it. On the branch it is in the sealed 2026 season, so every NCAAF pull plans it once its kickoff is past.
- **Thursday:** no effect. The fingerprints at 2026-10-01T12:00Z differ only by the approved NHL calls (see step 6).
- **A March clock (2027-03-01T12:00Z):** run on the same synthetic schedules, only the branch plans these calls: F1 +6, F4 +52, F5 +8, F6 +4 (NCAAF, all dated 2027-01-25 to 01-27), and H1 +10 (the approved NHL change).
- **The title game on its own** (`$S/revA/step6/title_game.py`, branch code, clock 2027-03-01):
  ```
  title game season/sealed on the branch: 2026 True
  F1: 8 more calls, at most 240 credits
  F4: 169 more calls, at most 5,070 credits
  F5: 2 more calls, at most 60 credits
  F6: 1 more calls, at most 40 credits
  ```
  That is about 5,410 credits at most, all for sealed data, in the gated and March pulls.
- **Commands:**
  ```
  CLOCK=2027-03-01T12:00:00+00:00 uv run python $S/revA/step6/fingerprint.py <out>   # on each checkout
  python3 $S/revA/step6/compare.py ...
  ```
  The full output is in `$S/revA/step6/compare_march.txt`.
- **Also checked:** the MLS (`:111`, to 2026-12-20) and K League (`:169`, to 2026-12-14) window ends also moved, but no pull in the config buys MLS or K League 2026, and the March fingerprint shows no difference for them.
- **Already disclosed:** the branch's STATUS.md says "the later ends of three sealed windows (NCAAF, MLS, K League) put their finals into the March pulls". Only the NHL change is listed as approved.
- **For the hub:** accept this purchase change, or keep the old end date (the title game would then fall in no window, and load_rows judges a game in no window by its call).

### 2. MAJOR by the letter (Q3), small in practice: after an "unexpected error" stop the client stays usable, and the attempt that raised is not counted
- **What it breaks:** Q3 ("after any stop, the client refuses every later attempt with the same stop"). It also misses rules 1 and 2 for that one attempt.
- **Why it happens:** `_latched` (`bulk.py:487-496`, line 493) keeps only `Stop` and `KeyboardInterrupt`. Any other exception raised inside `fetch()` ends the run in `run_calls` as `unexpected error, probably a bug; tell the hub before rerunning`, but `client.stopped` stays `None`.
- **Two ways I triggered it** (`$S/revA/rules.py` and `$S/revA/rules2.py`):
  - **A session that raises `RuntimeError`:**
    ```
    [BAD] R2/Q3 a non-requests exception from the session: counted, and the client refuses later
          counted=30 paid=2 stopped='unexpected error, probably a bug; tell the hub before rerunning (RuntimeError: urllib3 surprise)'; later fetch: sent (paid=2)
    ```
    The request that raised counted nothing. The 30 shown is from the later call, which the stopped client still sent.
  - **A 200 whose JSON `data` is a number or a boolean:** `_envelope` runs `len(data or [])` (`bulk.py:441`). `_account` calls it at `bulk.py:767`, before the count at `bulk.py:776`. So the answer is cached but counted as 0, although it reported 30. A rerun finds it in the cache and never counts it.
    ```
    garbled 200 body {'timestamp': 'x', 'data': 5}: counted after the stop=0 (x-requests-last 30), cached=True, manifest rows=['account', 'F1'], stopped="unexpected error, probably a bug; tell the hub before rerunning (TypeError: object of type 'int' has no len())"; later fetch: SENT (paid 1 -> 2)
       rerun over that cache: paid=1 counted=30 stopped=None -> the garbled call is never asked or counted again
    ```
- **Why the practical impact is small:**
  - Both triggers are fault cases. `requests` wraps transport errors, and the real API does not send scalar `data`.
  - Through the CLI the run ends at once. `stage_pull` breaks, `stage_probe` skips the billing probes, and `pull_snapshots` returns. So no further call is made unless the same client object is reused in library code.
  - The shortfall in the count is one call.

### 3. minor: a raw `OSError` from the session is reported as a cache read error and is not counted
- **What it breaks:** rule 2, in a fault case.
- **Where:** `bulk.py:697-700`. When no answer has come back yet, `except OSError: raise CircuitBreaker("the cache could not be read ... Nothing was fetched.")`. That cannot tell a socket error from a cache error.
- **Output** (`$S/revA/rules.py`, the fake session raises `TimeoutError`):
  ```
  [BAD] R2 a raw TimeoutError (OSError) from the session counts the upper bound
        counted=0 paid=1 stopped='the cache could not be read (socket timed out). Nothing was fetched.'
  ```
- **Effect:** the stop is kept by the client, and the run stops. The count is short by one upper bound, and the message is wrong. It needs `requests` to let a raw `OSError` through, which it does not normally do.

### 4. minor: `account()` on a stopped client still sends the free key check and resets `start` and `lowest`
- **What it breaks:** Q3 read literally ("refuses every later attempt").
- **Where:** `bulk.py:629-636` never checks `self.stopped`.
- **Output** (`$S/revA/rules2.py`):
  ```
  after the alarm: start=1000000 lowest=900000 unexplained=99970 stopped=True
  account() on the stopped client: requests sent 2 -> 3; start=1000000 lowest=1000000 unexplained=-30; stopped still set=True
  ```
- **Effect:** paid calls are still refused, because `fetch` raises the stop. But the client's `remaining` and `unexplained` no longer describe the stopped run. The rules harness shows the same thing ("key check SENT") after every kind of stop.
- **Reachable?** Only through library reuse. `pull_snapshots(client=...)` would call `account()` on an injected client that had already stopped.

### 5. minor: with `--retry-404`, a cached 404 that is asked again and answered 5xx does not appear in the summary line
- **What it breaks:** C4 visibility. Nothing is lost.
- **Where:** `bulk.py:707-710`. The old 404 is still cached, so the call is taken off `not_saved`, and the error count at `bulk.py:938` misses it.
- **Output** (`$S/revA/step9.py`, `--retry-404` at `--max-credits 65`): the server answered 200, 404, 500 (all seven attempts) and 200. The line printed was `done: 4 fetched, credits 60 (this run 60), remaining 4,999,940, cached 404s 2`, with no "answered with an error". Only a WARNING log line shows the 500.
- **Behaviour otherwise correct:** the 404 is kept, and only a 200 replaces one.

### Observations (not findings)
- **`check` / `coverage()` counts sealed games** (books, markets and number of games; no prices). The code is the same as main's. It is metadata only, and the hub can decide whether that is acceptable (see step 7).

## Step 1: the tests the branch adds or rewrites, run on main

**How I ran it:**
- I compared the test functions of the two versions with the Python AST (`$S/revA/step1/difftests.py`).
- I copied the branch's test files into `$S/main63/sharp-markets/tests` under new names (`*_revA.py`) and ran each selected test node in its own process on main's code and venv (`$S/revA/step1/each.py`). Then I deleted the copies.

**What the branch adds and rewrites:**
- **Added:** 54 test functions, 103 test nodes (53 functions in `test_bulk.py`, 1 in `test_analysis.py`).
- **Rewritten:** 8 functions, 11 nodes (7 in `test_bulk.py`, 1 in `test_http.py`).
- **Removed:** 1, `test_a_balance_that_rises_or_makes_no_sense_is_not_believed`, which tested the old accounting.

**Results on main:**

| | Nodes | Fail on main | Pass on main |
|---|---|---|---|
| Added | 103 | 80 | 23 |
| Rewritten | 11 | 7 | 4 |
| **Total** | **114** | **87** | **27** |

- Six of the 87 failures are Ctrl-C tests. On main the `KeyboardInterrupt` escapes the code and aborts pytest (exit 2).
- The other failures include `AttributeError`s for names main lacks, plus assertion failures and missing `SystemExit`s.

**The 27 that pass on main, and why:**
- **`test_every_sealed_window_holds_its_first_and_last_game_in_utc`:** 18 of its 22 parameters pass. Those windows are unchanged, and main's config already holds those games. The 4 that fail on main are exactly the changed windows: ncaaf-last, nhl-first, mls-last and kleague-last.
- **`test_the_floor_holds_with_a_late_balance[0]`, `[3]` and `[0-3 at random]`:** main's old accounting also held the floor. These are regression guards for the new rule.
- **`test_an_empty_result_reported_as_free_goes_on`:** main already went on after an empty result billed at 0.
- **`test_a_body_is_kept_exactly_as_sent_unless_it_holds_the_key[False]`:** main never changed bodies. The `[True]` case fails on main.
- **Rewritten `test_full_takes_seasons_only_as_one_declared_slice`:** main already refused the same `--seasons` cases.
- **Rewritten `test_odds_pull_billing_fails_closed[None]`, `[abc]` and `[9.5]`:** main's odds-pull already stopped on unreadable billing. The rewrite runs it through the new client.

## Step 2: the code against the rule

**How I checked:**
- I read `bulk.py` (BulkClient, run_calls and the stages), `headers.py`, `client.py`, `ingest.py`, `http.py`, `cache.py` and `cli.py`.
- **Bulk puller:** `$S/revA/rules.py` has 64 targeted fake-session cases (output in `rules.out`); `rules2.py` holds the follow-ups.
- **odds-pull:** `$S/revA/rules_oddspull.py` ran 12 cases through `OddsApiClient` and `pull_snapshots` (output in `rules_oddspull.out`).
- **Scoring:** the first pass scored 6 of 64 cases "BAD". I re-checked each by hand; the other 4 were my own wrong expectations, so the only real ones are findings 2 and 3:
  - `x-requests-last` 29.1 rounds up to 30, which equals the documented 30.
  - The 429 case stopped correctly on the alarm.
  - The varying-lateness case was too small for its margin; it was rerun properly in `rules2.py`.
  - In the rule 7 case, the second call was correctly allowed.

**Old balance accounting:** none is left.
- There is no counting of falls toward the budget. `counted` only grows, by an answer's cost or an unanswered attempt's upper bound.
- `unanswered` is never cleared, and no breaker looks at the balance.
- The only "in a row" breaker is the error-status one (`max_errors` 5, the "repeated errors" the brief keeps).
- The only change made on a rise is rule 6 (`_saw_balance`).
- Evidence: ten answers each followed by a 400-credit fall beyond the reported cost gave `counted=300`, `unexplained=4000`, no stop.

**Rule by rule** (all implemented as written in both the bulk puller and odds-pull, except where findings 2–4 say otherwise):

| Rule | Status | Evidence |
|---|---|---|
| 1 | implemented | See the bullet list below the table. |
| 2 | implemented, except findings 2 and 3 | A timeout counts 30 and stays counted, even when later readings show it was never billed: `counted=210 unanswered=30 unexplained=-30`. Seven dropped connections count 7 × 30 and stop. |
| 3 | implemented | See "Old balance accounting" above. |
| 3a | implemented | A 500 reporting 300 on a bound of 30, budget 60: `paid=1 counted=300 … (HTTP 500, not retried) billed 300 credits`, the same in odds-pull. A 503 with no billing header counts 30, then the retry runs. A 429's balance is read (`lowest=900000`) and set off the alarm before any retry. A retry refused on the budget: `retrying … could cost 30; 30 of the 50-credit run budget is counted`. A 502 reporting 31 stops with no retry. |
| 3b | implemented | The check before each attempt holds exactly: budget 90 allows 3 calls and refuses the 4th; budget 89 refuses the 3rd. A sweep of budgets from 30 to 198, with a billed 503 before every 200, never counted past the budget. The past-budget check after an answer is at `bulk.py:830`; only the branch's own test reaches it, with the check before each call switched off. |
| 4 | implemented | 531,630 against a floor of 531,630 starts. 531,629 refuses. No header or "abc" refuses. |
| 5 | implemented | `lowest` updated from every readable balance, retried answers included. |
| 6 | implemented | See the bullet list below the table. |
| 7 | implemented | See the bullet list below the table. |
| 8 | implemented | See the bullet list below the table. |
| 9 | implemented | A 200 with no balance stops with floor 1 and goes on with floor 0. As before, only a 200 counts as "billed" here: a retried 500 that reports 30 with no balance goes on to the retry. |
| Q3 | implemented, except findings 2 and 4 | See the bullet list below the table. |

- **Rule 1 in detail:**
  - A 200 whose `x-requests-last` is missing, `abc`, empty, `-1`, `nan`, `inf`, `30, 30` or a space counts 30 and stops ("billing could not be read"). odds-pull behaves the same, at 10.
  - Reporting 10 or 0 against a documented 30 counts 30 and stops ("cannot be trusted"). An /events sweep that lists a game and reports 0 counts 1 and stops. An empty 200 reported at 0 goes on.
  - Reporting 30 against a documented 20 counts 30.
  - A reported cost above the bound stops: 200 reporting 31, 404 reporting 300, 400 reporting 31 and 200 reporting `1e3` each count the reported figure. odds-pull reporting 11 on a bound of 10 does the same.
- **Rule 6 in detail:**
  - With a margin of 5,000, a rise of exactly 5,000 is out of date: `warned=0 start=1000000 lowest=999970 stale=1`, and the tally is logged once when the pull ends.
  - A rise of 5,001 is credits added: `warned=1 start=1005031 lowest=1004941`, where start = balance + count so far (1,004,971 + 60).
  - Two real top-ups give two warnings.
  - A header whose lateness varies from 0 to 3 answers, with the API charging twice what it reports, still ends on the alarm. Over 5 seeds the loss beyond the count was at most 5,130, within the margin plus 3 × 60 (5,180).
- **Rule 7 in detail:**
  - When the lowest balance binds: lowest 999,029 minus 30 is 998,999, below the floor of 999,000, so the run stops. Lowest 999,030 minus 30 equals the floor and is allowed.
  - With a frozen header, start minus count binds: a floor of 999,900 allows 3 calls, then `999,910 credits remain at most`.
- **Rule 8 in detail:**
  - The margin is 5,000 at 30,000, 17,000 at 170,000 and at 170,009, 152,000 at 1,520,000, and 5,000 at 0.
  - An unexplained fall of 5,000 goes on; 5,001 stops with the three-cause text and `Run 'uv run markets odds5m headers --pull F1' and tell the hub before rerunning` (odds-pull says `--pull N0`).
  - Through the CLI, `--alarm-margin 299` and `-5` are refused (argparse exit 2). `300` and `23,940` are accepted.
  - `--alarm-margin` is refused on `plan`.
  - The line after the key check reads `alarm margin: 17,000 credits (the default: the larger of 5,000 and 10% of --max-credits)` or `alarm margin: 300 credits (set by --alarm-margin)`, for odds5m and odds-pull alike.
- **Q3 in detail:**
  - After each of these stops, a later `fetch` is refused with the same stop and nothing is sent: budget, floor, above the upper bound, alarm, unreadable billing, network, Ctrl-C, 401, five errors in a row. odds-pull behaves the same for every stop I tried.
  - The one exception works: the probe skips a sport after five 422 answers and goes on.
- **Ctrl-C** between an answer's count and its manifest row (raised inside `_saw_balance`, or inside `_log`) counts the answer once with one row, and the STOPPED line says so (`$S/revA/ctrlc_mid.py`).

## Step 6: nothing bought changed, at Thursday's clock

**How I ran it:**
- **Synthetic schedules:** `$S/revA/step6/gen_schedules.py` wrote one set, used by both checkouts. It has games every two days inside the union of both configs' windows, games on every window boundary ±1 day, the NHL games of Sep 27–Oct 1, and each sealed window's first and last game. It also wrote a synthetic `heat_qualifying.csv` so HB1 and HS1 plan.
- **Fingerprints:** `$S/revA/step6/fingerprint.py`, clock 2026-10-01T12:00Z, each checkout with its own code and config. It covers:
  - the P0 sweeps and the P0 billing probes (through a recording fake client);
  - every pull's `full` plan, F3's two slices and every pull's `week auto` plan;
  - odds-pull's sample week (2026-01-05 to 01-11, schedule A: 742 snapshots, 7,420 credits), recorded by actually pulling against a fake session and reading the cache files.
- **Fingerprint contents:** URL path, params without apiKey, upper bound, cache key, and cache sport and source.
- **Totals:** main 153,342 fingerprints, branch 153,355.

**Result** (`$S/revA/step6/compare_thursday.txt`):
- **Only on main:** 0.
- **Only on the branch:** 13.
  - 3 P0 sweeps: `/historical/sports/icehockey_nhl/events` at 2026-09-28, 09-29 and 09-30 06:00Z, 1 credit each. The sweep total is 10,431 on main and 10,434 on the branch.
  - 10 H1 calls, all sealed: the daily-close snapshots and closes for the synthetic NHL games of Sep 28–30. This is the approved H1 change. The count follows my synthetic schedule, not the real one's 27.
- **odds-pull's sample week:** identical, 742 calls, same URLs, params, upper bound (10), cache keys and files (`nba/oddsapi_hist/<date>/<key>.parquet`).
- **Billing probes and every other pull:** identical.
- **Sealed flags:** none differs between the two checkouts for the same call.
- **At a March clock:** see finding 1.

## Step 7: sealed data (`$S/revA/step7.py`, output in `step7.out`)

- **Sealed flags:** on the branch's config, every sealed window's first and last game is sealed, and so are the NHL's 2026-09-29T21:00Z, 09-29T23:30Z and 09-30T23:00Z games. Each window's first and last day is sealed at 00:59Z and at 23:59Z.
- **`bulk.load_rows`:** I cached snapshots listing each of those games plus an unsealed control game, under calls marked unsealed and also marked sealed.
  - Result: `rows returned 96; sealed-game rows returned: []; controls: 96; left out: {'sealed season': 96}`.
  - With `include_sealed=True`: 192 rows.
  - An H1 pull of the NHL openers at Thursday's clock plans 11 calls, all sealed. `load_rows` then returns 0 rows and leaves out 56.
- **`markets build` (`sharp_odds_rows`, `include_sealed` default False):**
  - NBA pipeline: kept only `control`, left out `{'2026-27': 8}`.
  - NFL pipeline: kept only `control`, left out `{'2026': 8}`.
  - NHL openers, read by pointing the NBA pipeline at `icehockey_nhl`: kept only `control`, left out `{'2026-27': 16}`.
- **`check` / `coverage()`:** does not leave sealed games out. It prints `"games": 3, "books": {"pinnacle": 56}, "markets": {"h2h": 56}` for the NHL openers. That is counts only, with no prices or rows, and the code is unchanged from main. I list it as an observation for the hub, not a finding.

## Step 8: the key (`$S/revA/step8/case.py` and `runner.py`, output in `runner.out`)

**How I ran it:**
- 38 cases, each in its own process. Each ran the real `markets.cli.main` with its logging at DEBUG (basicConfig at DEBUG, then the CLI's own handler scrubbing).
- The API was a raw-socket HTTP server on 127.0.0.1. For Ctrl-C and the full disk it was a fake session.
- Commands:
  - `odds5m full --pull H1 --sports icehockey_nhl --confirm ...`
  - `odds5m probe --sports soccer_fifa_club_world_cup --confirm ...`
  - `odds5m balance --confirm`
  - `odds-pull --start 2026-01-05 --end 2026-01-11 --confirm ...` (the Kalshi context replaced by a fixed plan)
- **Conditions:**
  - a connection refused; a dropped connection; a real read timeout (`ReadTimeout … read timeout=0.5`);
  - a 302 whose Location carries `apiKey=`, followed once, and a redirect loop (`TooManyRedirects`);
  - a malformed header line holding the key and the URL, which urllib3 logs as `Failed to parse headers (url=…)`;
  - `x-requests-last`, `x-requests-remaining`, `X-Echo` and `X-Key` echoing the key;
  - 401, 429 and 500 bodies (and a 500 on /sports) echoing the full request URL and the key;
  - a 200 body echoing them;
  - Ctrl-C (`KeyboardInterrupt` carrying the key in its message);
  - ENOSPC while writing the cache, and ENOSPC while writing the manifest.

**What I scanned:** stdout, stderr (every log line, 2 to 78 DEBUG lines per case), exception text, and every file under `MARKETS_DATA_DIR` (manifest CSV, schedule and cache parquet decoded row by row, raw bytes). I searched for `FAKESECRETKEY999`, its URL-encoded forms (identical for this key), `FAKESECRET` and `SECRETKEY999`.

**Result:**
- All 38 cases are clean.
- **The redaction really happened:** `REDACTED` appears where the key was, for example `url: /v4/sports?apiKey=REDACTED`, `x-requests-last 'REDACTED'`, and the cached 200 body's `"key": "REDACTED"`.
- **The stops worked:** `STOPPED` lines, exit status 1, and `the API echoed the key in an answer with data` logged once for each such answer.

## Step 9: the outside audit's cases (`$S/revA/step9.py`, output in `step9.out`; `$S/revA/c5.py`)

- **C1, odds-pull, two calls expected at 10 credits that each report 300:**
  - Balance 531,000 under a floor of 531,630: `paid requests=0`, `STOPPED before the first paid call, nothing spent: the account has 531,000 credits left, already below the floor of 531,630`.
  - Balance 531,700, above the floor: `paid=1 counted=300`, stopped `billed 300 credits; it should cost at most 10`.
  - No floor: the same, `paid=1 counted=300`.
  - The branch's cache keys are unchanged (see step 6).
- **C2, a retried 500 reporting an overcharge:**
  - Bulk puller: `paid=1 counted=300 fetched=0 … (HTTP 500, not retried) billed 300 credits`.
  - odds-pull: the same.
  - No call returned as done over budget in the budget sweep (see rule 3b).
- **C3, the key in a body:** through a real 127.0.0.1 server, a 200 body without the key was stored byte for byte. The body had UTF-8 `São Paulo`, `Atlético – MG 😀`, `é` escapes, `1.50` and `2.600`, near-miss strings `FAKESECRETKEY99` and `fakesecretkey999`, a literal `REDACTED`, and a trailing `\r\n  `. The echoed body had the key blanked.
  ```
  plain: server sent 431 bytes, stored 431; identical=True; key in stored=False; REDACTED count=1
  echo: server sent 351 bytes, stored 335; identical=False; key in stored=False; REDACTED count=2
  manifest sha256 of plain = sha256 of the body as stored: True
  manifest sha256 of echo = sha256 of the body as stored: True
  ```
- **C4, cached 404s:**
  - First run: `done: 12 fetched, credits 240 …, cached 404s 4`, and `check` reports `"cached_404": 4`.
  - Rerun without the option: nothing is sent, and the line still says `cached 404s 4`.
  - Dry run: `4 to fetch (4 of them cached 404s asked again), at most 120 credits`.
  - With `--retry-404 --max-credits 65`: 60 counted. The server answered 200 (replaced), 404 (the file is untouched), 500 on all seven attempts (the 404 is kept) and 200 (replaced).
  - See finding 5 for how the summary line reports the 500.
- **C5, the NBA close:**

  | Snapshots | Branch close | main close |
  |---|---|---|
  | 0.50 at T−5m, 0.99 at T | 0.50 | 0.99 |
  | 0.51 at T−1s | 0.51 | 0.99 |
  | only at and after T | None | 0.99 |

  - The 16 post-tip minutes with a sharp fair stay in `analysis_1m`, and post-tip rows stay in `sharp_fair`.
- **Every other place a close or pre-game price is chosen:**
  - `analysis/data.py:89`, the close: `m.commence_time > f.snapshot_ts` (strict, the fix).
  - `analysis/data.py:102`, `load_sharp`: `f.snapshot_ts < g.commence_time` (strict).
  - `oddsapi/bulk.py:153`, `close_time`: `floor5(kick - 5 min)`, requested at least 5 minutes before kickoff.
  - `build/sql.py:110`: the ASOF joins are `<= ts` on the 1-minute grid (open to commence + 15 min, which keeps post-tip minutes for lead-lag).
  - `analysis/backtest.py:54, 104, 159, 182`: signals and fills need `ms.mtt > 0`, so strictly before tip.
  - `research/nfl_weather.py:39` and `105`: T−5m is the last candle with `end_ts <=` kickoff − 5 min.
  - `build/run.py:152`, `odds_covered`: `lo <= t <= hi` includes the tip itself. This is a coverage flag, not a price.
  - `research/kaggle_h3.py`: MGM's closing splits come from the dataset; no timestamp is chosen.
  - The registered price engine, which I did not touch: `research/price_engine/quotes.py:161` drops `snap >= kickoff` or `snap >= commence`, and `engine.py:192-195` takes each book's close as its last pre-kickoff quote within 60 minutes. Both are strictly before.
- **Price engine untouched:** `git -C $S/pr63 diff origin/main...HEAD -- sharp-markets/src/markets/research/price_engine sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md` is empty (0 bytes).

## Paths the branch touches

- **Frozen paths:** `git diff --name-only origin/main...HEAD` lists nothing under `nfl-weather/` or `cfb-weather/`, and no `PREREGISTRATION.md`, `STRATEGY.md` or `CLAUDE.md`. The 18 files touched are all in `sharp-markets/`, plus `STATUS.md` and `strategy-research/odds-api-credits.md`.
- **PLAN.md:** it gets a dated C5 note, added without rewording the existing text.

## What I did not check, and why

- **Other reviewers' areas:** the false-stop and missed-stop simulations, the `headers` stage's verdicts and advised margins, and the runbook rehearsal (including whether every STOPPED message is in "If a run stops").
- **An untested difference in `headers.py`:** it restarts its replay on a rise of more than 5,000 (`DEFAULT_MARGIN`), while a run uses its own margin (for example 17,000 at `--max-credits 170000`). I did not test whether that matters for any verdict.
- **Rule 3b's past-budget check after an answer:** no input I could build reaches it without switching off the check before each attempt. Only the branch's own test exercises it (see the rule 3b row).
- **Fingerprint counts:** they come from synthetic schedules, so they show which calls differ, not the real numbers. The approved H1 change is 27 calls on the real schedule; I did not reproduce that number.
