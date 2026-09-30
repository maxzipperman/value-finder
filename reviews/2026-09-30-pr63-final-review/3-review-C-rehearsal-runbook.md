# Reviewer C: Thursday rehearsal and the runbook (PR 63, branch at cc14201)

Scope: brief step 5 (REHEARSE THURSDAY), the runbook's `headers` step, the "If a run stops" table, the paragraph on what
can still be lost, the NHL and C6 numbers, and step 10 (cleanup). I fixed nothing. The checkout `$S/pr63` is unchanged
(`git status --short` is empty). Nothing reached any host other than 127.0.0.1, and no `.env` was opened.

## Verdict

- **No blocker and no major finding in my part.** I ran every day-one command in `sharp-markets/docs/ODDS5M_DAY_ONE.md`
  in order, as printed, against a fake Odds API that bills as the v4 docs say. Each one exited 0.
- **The counts agree for every command.** Credits the server billed = what the run counted = the manifest's
  `credits_last`, command by command.
  - Day one: **18,495 requests = 18,495 manifest rows**, and **228,201 credits** on all three.
  - With the extras (the `--retry-404` example, F3b, N1 and F4): 111,859 = 111,859 and 1,840,321 on all three.
  - The (sha256, credits) multisets of server and manifest are identical.
- **The new `headers` step works on the happy path.** I ran it twice: with a live balance header, and with a header
  that runs 100 answers late (A30 = 6,000, A60 = 12,000). Every command then finished with no alarm.
- **The "If a run stops" table lists every STOPPED message the code can print.**
- **The loss paragraph is right.** "What can still be lost" says what finding (c) requires. The NHL numbers (10,434
  sweeps; H1 +27 calls, at most 810 credits) and the C6 note agree everywhere they appear.
- **Three minor findings and one minor note**, listed below.

## Setup: what I built, what I synthesized, what I skipped

Scripts are in `$S/revC/`.

**`fake_api.py`**, a `ThreadingHTTPServer` on 127.0.0.1:18765.
- **Billing:**
  - `/v4/sports` is free.
  - Historical `/events` bills 1 when it lists any event, 0 when empty.
  - Historical featured `/odds` and historical event odds bill 10 × markets returned × regions (a `bookmakers` list of up
    to 10 books is one region).
  - An empty answer, an error or a 404 bills 0. An unknown event, or an absent snapshot (about 1% of event-odds calls,
    chosen by a deterministic hash), answers 404 and bills 0.
- **Headers:** `x-requests-last`, `x-requests-used` and `x-requests-remaining` are live on every answer.
- **Account:** 5,000,000 credits. Any key other than `FAKESECRETKEY999` gets a 401.
- **Server-side counting:** every request is appended to `requests.jsonl` (path, params without the key, status,
  billed, balance, sha256 of the body sent). `/__stats` returns the counters and is not counted.
- **Data:**
  - `/events` lists the games starting in the next 4 days.
  - Featured odds list the games that started in the last 3 hours, or start within the next 7.5 days (NFL) or 2 days
    (every other sport). Every requested book (fanatics and espnbet only from 2024) quotes every requested market.
  - Prop calls return 4 of the 6 F3 markets before 2025 and all 6 from 2025; Pinnacle alone returns 3.
  - Snapshots are on a 5-minute grid, 10-minute before September 2022.
- **Restart:** I restarted the server once, between the probe and `headers`, to turn off Nagle's algorithm, which cut
  the rate from 10 to about 45 requests a second. The account carried over by replaying the request log (balance
  4,989,669 before and after). Every command starts with a key check, so the code cannot see a restart.

**`synth.py`, the schedules.**
- NFL and NCAAF use the repo's own kickoffs (`nfl-weather` and `cfb-weather` `data/processed/games.parquet`, 2020–26;
  CFB games with at least one FBS team, as `strategy-research/odds_budget.py` selects them). So F1, F2 and F3 plan
  exactly what the PR's fingerprint says: F1 4,602 calls, 138,060 upper bound; F2 1,806.
- The other 14 sport keys get synthetic games: a few a day inside each season window, and fewer in the last 60 days.
- NHL 2026-27 opens with the real opening-night game, Florida at Carolina at 2026-09-29T21:00Z, and has 3 games on each
  of Sep 29 and Sep 30.

**`run_markets.py`, the wrapper.** Each `uv run markets ...` in the runbook ran as
`uv run python run_markets.py ...`, which calls the branch's `markets.cli.main(argv)` with the argv unchanged. It:
- sets `bulk.BASE_URL` and `client.BASE_URL` to `http://127.0.0.1:18765/v4`;
- sets the clock to Thursday by replacing `markets.settings.utcnow` before any other `markets` module is imported. Every
  module binds `from ..settings import utcnow`, and the wrapper asserts that each one got the fake. The clock is
  **2026-10-01T13:00Z plus the real time since the rehearsal started**, the same clock the server uses;
- refuses every socket `connect` or `create_connection` to anything but 127.0.0.1, and removes the proxy variables.
  `UV_OFFLINE=1` is set for every command, and a watchdog stops any command whose process tree passes 4 GB (none did;
  the peak was 2.7 GB, in the price engine);
- makes the rate limiter 25 times faster (8/s becomes 200/s) to save wall time. It changes nothing that is counted.

**Environment of every command:**
- `ODDS_API_KEY=FAKESECRETKEY999`;
- `MARKETS_DATA_DIR` and `MARKETS_REPORTS_DIR` in `$S/revC`;
- `PYTEST_ADDOPTS="-p no:cacheprovider"` for `uv run pytest` only, so no cache folder was written into the checkout.

**Synthesized inputs** (the cloud has none of the Mac's):
- **The NBA sample week.** `setup_kalshi.py` ran the branch's own Kalshi code (`discover`, `fetch_candles`,
  `fetch_trades`, `fetch_event_fees`) with an in-process fake session, so the records, keys and folders are the ones
  the Mac has. It wrote 93 KXNBAGAME events and 186 markets for ET dates 2026-01-01..14, matching the synthetic NBA
  Odds API schedule, plus 636,120 one-minute candles and 7,440 trades. The week has 48 games, so `odds-plan` gives 662
  snapshots and 6,620 credits instead of 754 and 7,540. That is still under `--max-credits 8000`, so the command ran as
  printed.
- **The heat games.** `weather join` found no forecasts, because the cloud can't reach Open-Meteo, so
  `weather qualifying` wrote 0 rows. After step 7's `weather qualifying`, `synth_qualifying.py` wrote a synthetic
  `heat_qualifying.csv` with 146 MLB and 272 soccer games from 2024 and 2025 (the runbook's estimates). It planned 139
  and 269 calls.

**Skipped:**
- `weather venues --confirm` and `weather fetch --confirm --max-calls 9000`: they need the MLB Stats API, ESPN and
  Open-Meteo.
- Day one step 1 (putting the key in the `.env` files): the key came from the environment instead.
- `git pull`: switching branches is forbidden, and the checkout is cc14201.

**`A30` and `A60`** were passed exactly as `headers` printed them: `--alarm-margin 5,000`.

## Rehearsal totals (live balance header)

| # | Command (as printed; A30 = A60 = `5,000`, as `headers` printed) | Exit | Server requests | Server billed | Run counted | Manifest rows | Manifest credits_last |
|---|---|---|---|---|---|---|---|
| 0 | `uv run pytest` (245 passed) | 0 | 0 | 0 | | 0 | 0 |
| 1 | `uv run markets odds5m probe` | 0 | 0 | 0 | | 0 | 0 |
| 2 | `uv run markets odds5m plan` | 0 | 0 | 0 | | 0 | 0 |
| 3 | `uv run markets odds5m probe --confirm --max-credits 11000` | 0 | 10,442 | 10,331 | 10,331 | 10,442 | 10,331 |
| 4 | `uv run markets odds5m headers --pull P0` | 0 | 0 | 0 | | 0 | 0 |
| 5 | `uv run markets odds5m headers --pull P0 --per-call 60` | 0 | 0 | 0 | | 0 | 0 |
| 6 | `uv run markets odds5m plan` | 0 | 0 | 0 | | 0 | 0 |
| 7 | `uv run markets odds5m plan --pull F3 --seasons 2025` | 0 | 0 | 0 | | 0 | 0 |
| 8 | `uv run markets odds5m week --pull F1,F2` | 0 | 0 | 0 | | 0 | 0 |
| 9 | `uv run markets odds5m week --pull F1,F2 --confirm --max-credits 6000 --alarm-margin 5,000` | 0 | 90 | 2,090 | 2,090 | 90 | 2,090 |
| 10 | `uv run markets odds5m headers --pull F1` | 0 | 0 | 0 | | 0 | 0 |
| 11 | `uv run markets odds5m headers --pull F1 --per-call 60` | 0 | 0 | 0 | | 0 | 0 |
| 12 | `uv run markets odds5m full --pull F1 --confirm --max-credits 170000 --alarm-margin 5,000` | 0 | 4,546 | 128,100 | 128,100 | 4,546 | 128,100 |
| 13 | `uv run markets odds5m check --pull F1` | 0 | 0 | 0 | | 0 | 0 |
| 14 | `uv run markets odds5m full --pull F2 --confirm --max-credits 48000 --alarm-margin 5,000` (17 cached 404s) | 0 | 1,773 | 35,100 | 35,100 | 1,773 | 35,100 |
| 15 | `uv run markets odds5m check --pull F2` | 0 | 0 | 0 | | 0 | 0 |
| 16 | `uv run markets odds5m full --pull F3 --seasons 2025 --confirm --max-credits 36000 --alarm-margin 5,000` (8 cached 404s) | 0 | 571 | 33,720 | 33,720 | 571 | 33,720 |
| 17 | `uv run markets odds5m check --pull F3 --seasons 2025` | 0 | 0 | 0 | | 0 | 0 |
| 18 | `uv run markets price-engine` | 0 | 0 | 0 | | 0 | 0 |
| 19 | `uv run markets odds-plan --start 2026-01-05 --end 2026-01-11` | 0 | 0 | 0 | | 0 | 0 |
| 20 | `uv run markets odds-pull --start 2026-01-05 --end 2026-01-11 --confirm --max-credits 8000 --alarm-margin 5,000` | 0 | 663 | 6,620 | 6,620 | 663 | 6,620 |
| 21 | `uv run markets build` | 0 | 0 | 0 | | 0 | 0 |
| 22 | `uv run markets backtest --start 2026-01-05 --end 2026-01-11` | 0 | 0 | 0 | | 0 | 0 |
| 23–26 | `uv run markets weather check` / `plan` / `join` / `qualifying` (`venues --confirm` and `fetch --confirm` skipped: network) | 0 | 0 | 0 | | 0 | 0 |
| 27 | `uv run markets weather qualifying` (step 7), then the synthetic heat list | 0 | 0 | 0 | | 0 | 0 |
| 28 | `uv run markets odds5m plan --pull HB1,HS1` | 0 | 0 | 0 | | 0 | 0 |
| 29 | `uv run markets odds5m full --pull HB1,HS1 --confirm --max-credits 16000 --alarm-margin 5,000` | 0 | 409 | 12,240 | 12,240 | 409 | 12,240 |
| 30 | `uv run markets odds5m check --pull HB1,HS1` | 0 | 0 | 0 | | 0 | 0 |
| 31 | step 8's `uv run python -c "import duckdb; ... GROUP BY ROLLUP (pull) ..."` | 0 | 0 | 0 | | 0 | 0 |
| 32 | `uv run markets odds5m balance --confirm` | 0 | 1 | 0 | | 1 | 0 |
| | **Day one** | | **18,495** | **228,201** | **228,201** | **18,495** | **228,201** |
| 33 | extra: `uv run markets odds5m full --pull F2 --retry-404` (dry, for N) | 0 | 0 | 0 | | 0 | 0 |
| 34 | extra: the runbook's example, `... full --pull F2 --retry-404 --confirm --max-credits 400` (17 asked again, still 404, kept) | 0 | 18 | 0 | 0 | 18 | 0 |
| 35 | gated: `full --pull F3 --seasons 2023,2024,2026 --confirm --max-credits 108000 --alarm-margin 5,000` | 0 | 1,236 | 52,120 | 52,120 | 1,236 | 52,120 |
| 36–37 | gated, dry: `full --pull N1`, `full --pull F4` | 0 | 0 | 0 | | 0 | 0 |
| 38 | gated: `full --pull N1 --confirm --max-credits 510000 --alarm-margin 5,000` (budget stop; see below) | 1 | 51,193 | 510,000 | 510,000 | 51,193 | 510,000 |
| 39 | gated: `full --pull F4 --confirm --max-credits 1520000 --alarm-margin 5,000` | 0 | 40,916 | 1,050,000 | 1,050,000 | 40,916 | 1,050,000 |
| 40–41 | step 8's reconciliation and `balance --confirm` again | 0 | 1 | 0 | | 1 | 0 |
| | **Everything** | | **111,859** | **1,840,321** | **1,840,321** | **111,859** | **1,840,321** |

**Step 8's table after day one:**

| pull | calls | billed | upper_bound | lowest_balance |
|---|---|---|---|---|
| F1 | 4,600 | 129,510 | 138,000 | 4,859,479 |
| F2 | 1,806 | 35,780 | 36,120 | 4,824,379 |
| F3 | 570 | 33,720 | 34,200 | 4,790,659 |
| HB1 | 139 | 4,170 | 4,170 | 4,779,869 |
| HS1 | 269 | 8,070 | 8,070 | 4,771,799 |
| N0 | 662 | 6,620 | 6,620 | 4,784,039 |
| P0 | 10,441 | 10,331 | 10,704 | 4,989,669 |
| account | 7 | 0 | – | 4,784,039 |
| **all** | **18,494** | **228,201** | **237,884** | **4,771,799** |

The `all` row's lowest balance equals what `balance --confirm` then printed (4,771,799).

`verify.py` compares the server's request log with the manifest:
- after day one: 18,495 requests and 18,495 rows; 228,201 billed and 228,201 in `credits_last`, with no blank rows;
  identical (sha256, credits) multisets; statuses 200 × 18,470 and 404 × 25 on both sides;
- after everything: 111,859 and 111,859; 1,840,321 and 1,840,321; identical multisets; 404 × 51 on both.

Because the sha256 multisets match, every stored body is byte for byte what the server sent (C3's second half). A DuckDB
scan of all 165,772 cached records (and 72,430 in the second rehearsal) found no `FAKESECRETKEY999` and no `apiKey` in
`url`, `params_json`, `headers_json` or `body`. The key is also in no log or manifest.

**Key lines printed, in order:**
- **Probe.**
  - Dry run: `P0 /events sweeps: 10,434 calls across 16 sports (1 credit each, 0 when empty); billing and coverage probes: at most 270 more`.
  - Paid: `key ok: HTTP 200, 5,000,000 credits remaining, 0 used; floor 531,630`, then
    `alarm margin: 5,000 credits (the default: the larger of 5,000 and 10% of --max-credits)`.
  - Then `done: 10,434 fetched, credits 10,111 (this run 10,111), remaining 4,989,889, cached 404s 0`, the games per
    season for all 16 keys (NHL `2026-27: 34`), the seven JSON probe lines (featured NFL `billed "30"`; props
    `billed "40"` with `billing_rule "10 x 4 markets returned = 40"`; Pinnacle props 30; NFL 2020 sharp, NCAAF 2020,
    MLB 2024 and MLS 2024 each 30), and `P0 done: credits this run 10,331, remaining 4,989,669`.
- **Plan after the probe:** F1 4,602 calls, 138,000 to fetch (2 calls cached by the probes); F2 1,806 and 36,120;
  F3 1,806 and 108,300 `(all seasons; ...)`; HB1 and HS1 `waits for ...`; N1 70,244; F4 45,517; H1 6,878; N2 5,563;
  F5 6,190; F6 3,095. `plan --pull F3 --seasons 2025`: 570 calls, 34,200.
- **Each paid pull:** `key ok: ...`, then `alarm margin: 5,000 credits (set by --alarm-margin)`, then
  `<pull>: N calls, C cached, T to fetch, at most U credits`, then `done: ... (this run ...) ..., cached 404s N` and a
  `coverage:` line. Examples:
  - F1: `done: 4,545 fetched, credits 128,100 (this run 128,100), remaining 4,859,479, cached 404s 0`;
  - F2: `... credits 35,100 ..., cached 404s 17`;
  - F3a: `... credits 33,720 ..., cached 404s 8`;
  - N0: `nba odds-pull (N0): 662 calls, 0 cached, 662 to fetch, at most 6,620 credits`, then
    `done: 662 fetched, credits 6,620 (this run 6,620), remaining 4,784,039, cached 404s 0`;
  - HS1: `done: 269 fetched, credits 8,070 (this run 12,240), ...`.
- **N1 as printed** stopped on its budget, exit 1:
  - `STOPPED: the next call could cost 10; 510,000 of the 510,000-credit run budget is counted`
  - `stopped: 51,192 fetched, credits 510,000 (this run 510,000), remaining 4,209,679, cached 404s 0`
  - The synthetic NBA 2025-26 season plans 70,244 calls and 695,820 credits, more than the budget. The count stopped
    at exactly `--max-credits`. The dry rerun the runbook prescribes then printed
    `N1  70,244 calls, 18,390 to fetch, at most 183,900 credits`. See note N1 below for the real schedule.
- **F4:** `F4: 45,517 calls, 4,602 cached, 40,915 to fetch, at most 1,227,450 credits`. F1's snapshots were reused, as
  `odds-api-credits.md` says, and the run ended `done: 40,915 fetched, credits 1,050,000 ...`.

## The new `headers` step, walked exactly as written

**First rehearsal, live header:**
- `headers --pull P0`:
  - `requests: 10,441 answers; the run counted 10,331 credits for them`
  - `the balance: 5,000,000 at the key check, lowest 4,989,669: a fall of 10,331`
  - `charged answers that showed no fall in the balance: 0 of 10,118; the longest stretch in a row: 0 answers`
  - `rises in the balance: 0`
  - `The balance header is live: every charge shows in the answer that made it.`
  - `Smallest --alarm-margin advised for a pull whose calls cost up to 30 credits: 5,000 (the larger of 5,000 and 2 x 0 answers x 30)`
- `--per-call 60` printed the same advice, 5,000.
- A30 = A60 = `5,000`, passed as printed; `--alarm-margin 5,000` was accepted.
- On F1's week-sized pull, `headers --pull F1` said the same: the run covered pulls F1 and F2, 89 answers, live,
  5,000 and 5,000.
- `headers` makes no network request: it ran and exited 0 with `socket.connect`, `create_connection` and `getaddrinfo`
  all raising. The server saw 0 requests from any `headers` run.

**Second rehearsal, a realistic late header.** `fake_api_lag.py` with `FAKE_LAG=100` reports `x-requests-remaining`
as it stood 100 answers earlier. I used fresh caches and a fresh account, and ran day one's paid commands in the
runbook's order:
- The probe finished (`P0 done`).
- `headers --pull P0`: `charged answers that showed no fall ...: 365 of 10,118; the longest stretch in a row: 100 answers`,
  then `The balance header runs late by up to 100 answers.` It advised **6,000** for 30-credit calls and **12,000** for
  60-credit calls, which is 2 × 100 × U.
- The week ran with `--alarm-margin 6,000`.
- `headers --pull F1` said `late by up to 100 answers` (100 carried over from the probe's run; 1 in this run) and
  advised 6,000 and 12,000 again.
- Then, each with no alarm and exit 0:
  - F1 and F2 with `--alarm-margin 6,000`;
  - F3a and the NBA week with `12,000`;
  - HB1 and HS1 with `6,000`.
- Totals: 18,495 requests and 18,495 manifest rows; 228,201 billed, counted and in the manifest; identical multisets.
- `balance --confirm` then printed 4,774,769, 30 below step 8's `all` lowest of 4,774,799. That is "at or a little
  below", as step 8 says.

## Does every runbook sentence match what its command printed?

**Everything else checked matches.** I compared the sentences in "Before buying" 1, 3 and 4; Day one 2 (the four things
the probe does, `P0 done`, the checks on `billed`, `expected_max`, `markets_returned`, `books_returned` and
`billing_rule`, the headers step and its bullets), 3, 4 (the coverage line's fields, lag 0–5), 5, 6 (odds-pull's
printed sequence, the N0 rows), 7 and 8 (the rows, `calls` counting answers, `all`, the lowest balance against
`balance --confirm`), and the summary-line example in "How a run protects the credits". I also checked the refusal
paragraph under the table:
- `plan --alarm-margin 5000`, `headers --alarm-margin 5000`, `check --retry-404`, `balance` without `--confirm`,
  `full --pull F3` and `full --pull HB1,HS1` before the list exists each exit 1 with their reason;
- `--alarm-margin 299` exits 2;
- dry runs and `headers` exit 0.

The mismatches are these, all minor:

**m1 (minor): step 3 says F3's line shows "about 136,800", but on Thursday's clock it prints about 108,300.**
- The sentence: "F3's line here covers all its seasons (about 136,800) and ends ``(all seasons; ...)``".
- Printed: `F3  day_one      1,806 calls  at most     108,300 credits to fetch ...` from the real NFL kickoffs 2023–26.
  Only the 2026 games played by Oct 1 count; the 136,800 includes the whole 2026 season.
- The same applies to the gated table: F3b "102,600" against `F3: 1,236 calls, 1 cached, 1,235 to fetch, at most 74,100 credits`.
- The runbook already says this for F2 ("at most 2,280 ...; the rehearsal's schedules gave 1,806"), and the C6 note
  says the figures are estimates. The printed figure is lower, so no check trips. It is still a number the operator will
  not see.

**m2 (minor): the paragraph under the table gives the wrong next step for an unreadable balance.**
- The paragraph says ``Rerun the same command until it prints `P0 done` ...`` follows "... a lost balance ...". Its
  `Tell the hub before rerunning ...` list (and step 2's list in parentheses) does not name an unreadable balance.
- The only lost-balance stop a CLI run can reach is `the balance could not be read: ...`. `the account balance is
  unknown ...` needs `start` to be `None`, which a run that passed its key check never has.
- For `the balance could not be read`, the probe prints "Tell the hub before rerunning". Reproduced with
  `$S/revC/extra/lost_balance.py`: an NFL-only probe whose 4th answer lacks `x-requests-remaining` printed
  `STOPPED: the balance could not be read: ...`, `P0 stopped: ...`, and
  `Tell the hub before rerunning: a rerun could buy more ...`, with `rerun flag: False`.
- The table's own row for this line is right ("tell the hub before rerunning"). Only the paragraph's classification is
  off. Cause: `bulk.py:827` raises `CircuitBreaker` with the default `rerun=False`.

**m3 (cosmetic): two printed lines have small formatting slips.**
- `headers` prints `the longest stretch in a row: 1 answers`. The verdict line fixes " 1 answers"; this line doesn't
  (`headers.py:138-139`).
- `key ok:` prints the used count unformatted (`12421 used`, `1840321 used`) next to formatted figures. It is the raw
  header (`bulk.py:1093`, `1113`). The runbook never quotes it.

**Not a mismatch:** `odds-plan`'s "754 snapshots, 7,540 credits" can't be compared, because the Kalshi week is
synthetic. The printed format matches the runbook's quotation line for line (`nba odds-pull (N0): ... calls, 0 cached,
... to fetch, at most ... credits`, then `done: ... fetched, credits ... (this run ...), remaining ..., cached 404s 0`).

## Does "If a run stops" list every STOPPED message?

Yes. I grepped `src/markets` for every `STOPPED` print, every `raise Stop`, `BudgetExceeded`, `CircuitBreaker`,
`TooManyErrors` and `OddsApiError`, and every string `_stopped_by` returns. Each one maps to a table row:

| Code (file:line) | What follows `STOPPED:` | Table row |
|---|---|---|
| `bulk.py:581` | `{the next call \| retrying ...} could cost N; X of the M-credit run budget is counted[ (... attempts that got no answer ...)]` | `... could cost N; X of the M-credit run budget is counted` |
| `bulk.py:586` | `the account balance is unknown, so the floor of F can't be checked ...` | `the account balance is unknown ...` |
| `bulk.py:590` | `X credits remain at most; ... could cost N, and the floor is F` | the floor row |
| `bulk.py:617` | `no answer from the Odds API after the retries (...)` | the network row |
| `bulk.py:642/645/647/650/653` (key check, as `STOPPED before the first paid call, nothing spent: ...`, or `STOPPED: ...` from `balance`) | manifest row not written; key rejected (401); `/v4/sports` returned HTTP N; no readable balance; below the floor | the first row |
| `bulk.py:699` | `the cache could not be read (...)` | the disk row |
| `bulk.py:793` | `...: the API answered HTTP 200 with a body that is not JSON ...` or `...: the response could not be saved (...): is the disk full? ...` (plus `The manifest row could not be written either.`) | the non-JSON row and the disk row |
| `bulk.py:797` | `... billed N credits; it should cost at most M ...` (with `(HTTP 500, not retried)` on a retried answer) | the billed-above row |
| `bulk.py:800` | `the account has fallen by N credits more than this run counted (the margin is M; ...)` | the alarm row |
| `bulk.py:814/816` | `the Odds API rejected the key (401)`; `HTTP 429 after retries ...` | the 401 and 429 rows |
| `bulk.py:818/822/827` | `the billing could not be read: ...`; `the billing cannot be trusted: ...`; `the balance could not be read: ...` | their three rows |
| `bulk.py:831` | `... took the count to X, past the M-credit run budget` | the count-past-budget row |
| `bulk.py:839` | `N errors in a row; the last was HTTP ...` | the errors row |
| `client.py:76` (odds-pull) | `Odds API /historical/... -> HTTP N: ... Nothing was cached for it.` | the odds-pull row |
| `bulk.py:880/884/887` (`_stopped_by`) | `interrupted (Ctrl-C). ...`; `a file could not be read or written (...)`; `unexpected error, probably a bug; ...` | the Ctrl-C, disk and bug rows |
| `bulk.py:1170` | `the sweeps did not finish for N sport(s) ...` | the sweeps row |
| `bulk.py:1435/1437/1440`, `cli.py:267` | `interrupted (Ctrl-C)...`; `a file could not be read or written ...`; any Stop reaching `main` | the Ctrl-C, disk and other rows |
| `ingest.py:36` (odds-pull) | `STOPPED before the first paid call, nothing spent: the plan needs N credits, more than --max-credits M`, or the key-check reasons, or a full disk | the first row, which names odds-pull's plan case |
| `bulk.py:494/719` (a stopped client reused) | the first stop again, or `interrupted (Ctrl-C)` | as above |

Nothing is missing. The only imprecision is the paragraph under the table (m2).

## "What can still be lost", the NHL numbers, and C6

**The loss paragraph** (runbook lines 67–73, and the PR description's section of the same name) matches finding (c).
It does not say honest billing headers mean nothing can be lost. It says:
- one call charged above its most possible cost passes the budget by the difference, "however large, even when the
  answer reports that charge honestly";
- with under-reporting, the loss is "up to the margin, plus the charges of as many answers as the balance header is
  late, plus one call's extra";
- with "no limit if the balance never moves, which `headers` shows after the probe".

The arithmetic holds: 5,000 × $119 / 5,000,000 = $0.119, about 12 cents; 17,000 gives $0.40.

**The NHL numbers agree everywhere they appear:**
- **Sweep count.** Main's config at Thursday 13:00Z gives 10,431 sweeps (NHL 1,570); the branch gives 10,434
  (NHL 1,573), so +3. Both the dry and the paid probe printed 10,434. The upper bound is 10,434 + 270 = 10,704, which
  matches "about 10,700" in the runbook (lines 121, 162), `odds-api-credits.md` (P0 "~10,700") and STATUS ("about
  10.7K").
- **H1.** "27 more snapshots / at most 810 more credits" appears in `odds-api-credits.md`, STATUS ("at most 810 more
  credits in H1") and the PR description. 27 × 30 = 810. Checking the 27 itself needs the real NHL schedule; that
  fingerprint is another reviewer's job.

**The C6 note** is in the runbook (lines 15–19) and in `odds-api-credits.md` (line 81): the figures are estimates, and
what binds is `plan` after the probe plus each `--max-credits`. Every `--max-credits` in the runbook is above its figure:

| Pull | `--max-credits` | Figure it must exceed |
|---|---|---|
| F1 | 170,000 | 164,910 (audit) |
| F4 | 1,520,000 | 1,483,650 (audit) |
| F2 | 48,000 | 45,600 |
| F3a | 36,000 | 34,200 |
| HB1+HS1 | 16,000 | 12,540 |
| F3b | 108,000 | 102,600 |
| N1 | 510,000 | 486,440 |
| N0 | 8,000 | 7,540 |
| probe | 11,000 | 10,704 |

## Note (minor, outside Thursday; the real case is not reproduced)

**N1 plans the NBA playoffs, but its figure covers only the regular season.** N1's credits (486,440 = 10 × (49,398 −
754)) come from PLAN.md §3, whose 49,398 is "Full 2025-26 reg. season" (164 game days). N1's config
(`only_seasons: ["2025-26"]`, window 2025-10-01..2026-06-25) plans every game in that window, playoffs included.
Reproduced in-process: two synthetic games on 2026-05-20 and 2026-06-15 are labelled `2025-26` and add 1,352 planned
calls (13,520 credits). On the real schedule, N1's `plan` may come out well above 486,440 and its `--max-credits
510000`. The run would then budget-stop, as my synthetic one did (safely, at exactly 510,000), and the runbook's budget
row says to tell the owner if a pull is more than about 10% over its figure. I could not check the real size: the cloud
has no real NBA schedule. This is for the hub to know before the gate, not a defect of this PR's accounting.

**Observation (not a finding):** the price engine peaked at 2.7 GB of memory on the rehearsal's F1. In my fake, CFB
featured snapshots list only the next two days' games; the real ones list more, so the real run on the Mac will need
more.

## What I could not check

- The real numbers that need real data: `odds-plan`'s 754 snapshots and 7,540 credits; H1's +27; the real N1 plan.
- The real API's billing and header behaviour.
- `weather venues --confirm` and `weather fetch --confirm` (they need the network).
- The runbook's timings at 8 requests a second: I ran at 200 a second. Its arithmetic is consistent (5,400 / 8 = 11
  minutes; 2,280 / 8 = 4.75 minutes; 570 / 8 = 71 seconds).

## Cleanup (step 10)

- Deleted every cache and data folder I created (`$S/revC/data`, `$S/revC/lag/data`, `$S/revC/extra` data), the price
  engine's `bets.parquet`, and `__pycache__`.
- Kept the scripts, the per-command logs (`$S/revC/logs`, `$S/revC/lag/logs`), `results.jsonl`, the gzipped server
  request logs and this report.
- Both fake servers are stopped. The `pr63` checkout is unchanged.
