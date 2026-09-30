# PR 63: the fixer's report (on top of cc14201)

- **Branch and commits.** Worked in `/home/user/value-finder` on `claude/quirky-goldberg-81hwy6`, which started at cc14201. I made seven commits, one per numbered fix, cc14201..e40035e. I pushed, merged and switched nothing.
- **Safety.** Every run used fake sessions or 127.0.0.1, with key `FAKESECRETKEY999` and `MARKETS_DATA_DIR` under `$S/fix`. I opened no `.env`.
- **Files I did not touch:** nfl-weather/, cfb-weather/, any PREREGISTRATION.md or STRATEGY.md, CLAUDE.md, the price engine and its registration.
- **Unchanged logic:** rules 1–9, the margin formula, rule 6's rise handling, and the `headers` verdict logic.
- `S=/tmp/claude-0/-home-user-value-finder/d7012428-080d-54f3-a1da-3ceb35298eec/scratchpad`

## Result

- **Full suite at e40035e:** 259 passed. That is cc14201's 245 plus 14 new test nodes. Command: `uv run pytest -q -o addopts="" -p no:cacheprovider`, from sharp-markets/, 160 s.
- **New tests fail on cc14201's code.** I checked every new test against the clean cc14201 checkout (`$S/pr63`) with `$S/fix/on_cc.sh`, which copies the current `tests/test_bulk.py` to `$S/fix/cc` and runs it with `$S/pr63`'s code. All of them fail there and pass here.
- **Lint:** `ruff check` finds nothing new; the 7 findings it reports are in files I didn't touch, same as on cc14201.
- **`git diff cc14201 --stat`:**
  ```
   STATUS.md                                    |   2 +-
   sharp-markets/config/odds5m.yaml             |   9 +-
   sharp-markets/docs/ODDS5M_DAY_ONE.md         |  37 ++--
   sharp-markets/src/markets/oddsapi/bulk.py    | 132 +++++++++----
   sharp-markets/src/markets/oddsapi/client.py  |   2 +-
   sharp-markets/src/markets/oddsapi/headers.py |  12 +-
   sharp-markets/tests/test_bulk.py             | 270 ++++++++++++++++++++++++++-
   7 files changed, 391 insertions(+), 73 deletions(-)
  ```

### Fingerprints

**How I ran them:**
- Reviewer A's `step6/fingerprint.py` and `compare.py`.
- One set of synthetic schedules for all three checkouts (`gen_schedules.py` over the union of main's and cc14201's windows).
- Checkouts: cc14201 (`$S/pr63`), HEAD (the working tree) and origin/main (`$S/main63`).
- Outputs: `$S/fix/fp/cmp_*.txt`.

**Thursday's clock (2026-10-01T12:00Z):**
- **cc14201 vs HEAD:** identical. `only on main: 0 only on branch: 0`, with no sealed-flag differences, over 153,355 fingerprints each. That covers every pull's full, slice and `week auto` plans, the P0 sweeps and billing probes, and odds-pull's sample week (742 calls, the same URLs, parameters, upper bound, cache keys and files).
- **main vs HEAD:** only the approved NHL change differs, 13 fingerprints: 3 P0 `/events` sweeps (Sep 28–30) and 10 synthetic H1 calls.

**March clock (2027-03-01T12:00Z), cc14201 vs HEAD:**
- The revert only removes calls: 71 only in cc14201, 0 only in HEAD.
- Every removed call is NCAAF, dated 2027-01-25 to 01-27:

  | Pull | Calls removed | Credits at most |
  |---|---|---|
  | F1 | 6 | 180 |
  | F4 | 52 | 1,560 |
  | F5 | 8 | 240 |
  | F6 | 4 | 160 |
  | P0 (the Jan 27 sweep) | 1 | 1 |

  These are the synthetic games dated after Jan 25, 2027 (the title game at 2027-01-26T00:30Z, plus the generator's boundary games).
- **The title game alone** (reviewer A's `title_game.py`):
  - cc14201: `F1: 8 more calls, 240 / F4: 169, 5,070 / F5: 2, 60 / F6: 1, 40` (≈5,410).
  - HEAD: `title game season/sealed: None False; F1: 0 / F4: 0 / F5: 0 / F6: 0`.

**March clock, main vs HEAD:**
- 10 H1 calls (the approved NHL change) and 10 P0 sweeps.
- The 10 sweeps are 3 NHL, 5 MLS (Dec 12–20) and 2 K League (Dec 12, 14). They come from the MLS and K League window ends, which the brief said to leave. They add at most 7 one-credit sweeps, and only to a probe run after mid-December (for example a March re-probe). No pull is affected.

### The key, rechecked

- **Reviewer A's 38-case key scan** (CLI at DEBUG, a raw 127.0.0.1 server, Ctrl-C and ENOSPC), rerun on HEAD: `$S/fix/revA_rerun/step8/runner_head.out`.
  - All 38 cases are clean, and the per-case statuses match cc14201's.
  - The printed lines differ only in port numbers, and in one dropped-connection case whose timing gave `ReadTimeout` instead of `RemoteDisconnected` (both take the same path).
- **Reviewer A's step 9** (audit cases C1–C4), rerun on HEAD: `step9_head.out`. It is identical to cc14201's except the C4 `--retry-404` line (fix 5).

## The fixes

### 1. The NCAAF 2026 window ends Jan 25, 2027, as on main (7f385be)

- **Change:**
  - `config/odds5m.yaml`: `to: 2027-01-27` goes back to `2027-01-25`. The comment says the title game (2027-01-26T00:30Z) is the one exception to the header's rule: it is in no window, nothing plans it, and `load_rows` judges any row of it by its call. Moving the end would add about 5,410 credits to March, and that is the hub's decision.
  - The NHL start and the MLS and K League ends are kept.
  - `STATUS.md` now says the MLS and K League windows take in their finals, which no pull buys, and that NCAAF keeps Jan 25, with the title game left to the hub.
  - The runbook's sealed-holdout paragraph names the exception.
  - `strategy-research/odds-api-credits.md` never mentioned the NCAAF change, so nothing there changed.
- **Tests:**
  - **New, `test_nothing_bought_changed_since_main_but_the_nhl_start`:**
    - The NCAAF 2026 window ends 2027-01-25.
    - Against main's config (`git show 4bf0497:sharp-markets/config/odds5m.yaml`, parsed by `load_config`), books, featured, pulls, groups, `history_from` and `sweep_every_days` are identical.
    - The window changes are exactly {NHL 2026-27 `from`, MLS 2026 `to`, K League 2026 `to`}.
    - The only one inside a window that a pull buys from (a pull covers the sport and its season passes only_seasons/skip_seasons) is the NHL start.
  - **Why the pinned commit and not `origin/main`:** 4bf0497 is origin/main today. Comparing with `origin/main` would fail on the Mac once this PR merges, because main would then equal the branch and day-one step 1 says everything passes. The test skips if the commit is missing from the git history. The NCAAF assertion runs before that point, so it never skips.
  - **Changed, `test_every_sealed_window_holds_its_first_and_last_game_in_utc[americanfootball_ncaaf-last]`:** now asserts that the window ends 2027-01-25 and that the title game falls in no window.
- **Before and after on cc14201:** both tests fail there (`assert date(2027, 1, 27) == date(2027, 1, 25)`) and pass here. The fingerprints are above.

### 2. Every stop latches the client, and every answer is counted before its body can crash anything (8e43528)

- **Change** (`bulk.py`; rules 1–9 untouched):
  - **The session raising something else.** Any error other than a Stop or an OSError, raised while the request is out, is an attempt with no answer (`_get`): its upper bound is counted to the end of the run (rule 2), the traceback is logged with the key blanked, and the run stops with `unexpected error, probably a bug; tell the hub before rerunning (RuntimeError: ...). It came from sending the request, which got no answer. It may still have been billed, so its upper bound, N credits, is counted ...`. At the free key check nothing is counted, and it stops before the first paid call.
  - **A 200 whose body can't be interpreted.** The new `_interpret` covers a body that isn't JSON, a JSON object whose `data` isn't a list, object or null, and a body that crashes the documented-cost or envelope code (for example `bookmakers: 5`). Such a 200:
    - counts the larger of what it reported and its upper bound;
    - gets its manifest row, with blank envelope fields where they can't be read;
    - is not cached (`_Unusable` is raised before the cache keeps it);
    - stops the run with a plain line: `<path> at <time>: the API answered HTTP 200 with JSON it cannot read ('...'). It was not cached, so a rerun asks again. It counted 60 credits, the larger of what it reported and its upper bound (x-requests-last '20').`
    - An error answer's documented cost stays 0 whatever its body holds, and its unreadable envelope is left blank.
  - **Any other error inside a client method.** For example a bug while an answer is saved, or a cache that can't be read. It becomes the Stop its STOPPED line gives (`_as_stop`, shared with `_stopped_by`, so the wording is the same as before). Before that stop is kept, `_count_out` counts what was out:
    - an answer that came back and wasn't counted: the larger of what it reported and its upper bound, with no manifest row;
    - a request with no answer: its upper bound.
    - The client keeps that stop and refuses every later attempt with it.
- **Behaviour change the hub should know about:** a 200 that isn't JSON is one kind of "body that can't be interpreted", so it now counts at least its upper bound, where it used to count what it reported. `test_a_full_disk_or_a_body_that_is_not_json_stops_with_the_summary` changed from `spent == 20` to `60` for that reason. Question 2 below.
- **Tests (new):**
  - `test_any_other_error_the_session_raises_counts_the_attempt_and_stops_the_client`: a RuntimeError on the second paid call counts 20 + 60 (`unanswered` 60); the later fetch is refused with the same stop object and sends nothing; the key is not in the log; at the key check the error is a CircuitBreaker and counts 0.
  - `test_a_200_it_cannot_interpret_counts_its_upper_bound_gets_its_row_and_stops[3]`: bodies with `data` 5, `data` "abc", and `bookmakers` 5. Each counts 20 + 60, has two manifest rows, leaves the garbled answer uncached, prints a plain STOPPED line with rerun, and refuses later.
  - `test_any_other_error_in_a_fetch_counts_what_came_back_and_stops_the_client[2]`:
    - `write_record` raising ValueError: counts 20 + 60 and latches `unexpected error ...`;
    - the cache lookup raising PermissionError: counts 20 and latches `a file could not be read or written ...`;
    - both stay refused after `monkeypatch.undo()`.
  - Changed: `test_ctrl_c_inside_the_accounting_of_an_answer_...[before its count]` now raises Ctrl-C at the entry of `_account` instead of inside `_envelope`. It is the same moment (the answer is back and not yet counted), but `_envelope` now also runs before the answer is cached. It passes on cc14201 too.
- **Before** (reviewer A's `rules.py` and `rules2.py` on cc14201):
  ```
  [BAD] R2/Q3 a non-requests exception from the session: counted=30 ... stopped='unexpected error ...'; later fetch: sent (paid=2)
  garbled 200 body {'timestamp': 'x', 'data': 5}: counted after the stop=0 (x-requests-last 30), cached=True, ... later fetch: SENT (paid 1 -> 2)
  ```
  The 30 counted in the first line came from the later call, which the stopped client still sent.
- **After** (the same scripts on HEAD, `$S/fix/revA_rerun/*_head.out`):
  ```
  [OK ] R2/Q3 ...: counted=30 paid=1 stopped="unexpected error, probably a bug; ... (RuntimeError: urllib3 surprise). It came from sending the request, which got no answer. It may still have been billed, so its upper bound, 30 credits, is counted ..."; later fetch: refused
  garbled 200 body {'timestamp': 'x', 'data': 5}: counted after the stop=30 (x-requests-last 30), cached=False, manifest rows=['account', 'F1'], stopped='... the API answered HTTP 200 with JSON it cannot read ...'; later fetch: refused (CircuitBreaker)
     rerun over that cache: paid=2 counted=60   (the garbled call is asked again, since it was not cached)
  ```

### 3. A raw socket error from the session is an attempt with no answer (0fb8f29)

- **Change:** an OSError raised while the request is out (a raw TimeoutError or ConnectionResetError that `requests` didn't wrap) is a transport error.
  - It counts its upper bound to the end of the run.
  - It stops with `no answer from the Odds API (TimeoutError: socket timed out; not retried). Nothing was cached for this call, so a rerun asks again. It may still have been billed, so its upper bound, ... is counted ...` (rerun).
  - It is not retried: stopping is the safe direction. See question 5.
  - An OSError from the cache or the disk keeps its existing lines ("the cache could not be read", "could not be saved ...: is the disk full?", "a file could not be read or written").
- **Test:** `test_a_raw_socket_error_from_the_session_is_an_attempt_with_no_answer[TimeoutError, ConnectionResetError]`. It counts 20 + 60 (`unanswered` 60), the line starts `no answer from the Odds API (`, the call is not cached, and the client refuses later.
- **Before (cc14201):** `STOPPED: the cache could not be read (Connection reset). Nothing was fetched.`, and 20 counted.
- **After:** `R2 a raw TimeoutError ... counts the upper bound: [OK] counted=30 paid=1 stopped="no answer from the Odds API (TimeoutError: socket timed out; not retried) ..."`

### 4. A stopped client refuses the key check (7bb0c5f)

- **Change:** `account()` raises `self.stopped` when the client has stopped. It sends nothing, and `start`, `lowest` and the count are unchanged.
- **Test:** `test_the_key_check_of_a_client_that_stopped_is_refused_with_the_same_stop[the alarm, billed above its upper bound, a session error]`.
- **Before:** `account() on the stopped client: requests sent 2 -> 3; start=1000000 lowest=1000000 unexplained=-30`.
- **After:** `account()` raises the alarm's CircuitBreaker (`the account has fallen by 99,970 credits ...`), the same object. Reviewer A's `rules2.py` now stops at that call; see `rules2_head.err`.

### 5. A `--retry-404` call answered with an error is on the pull's line (0e7b6eb)

- **The change is small, so I made it.** `fetch` now marks an answer as an error by its own status (not one of the client's `cache_statuses`) instead of by whether the call is still cached.
  - A cached 404 asked again and answered 5xx keeps its 404, and it is counted on the `done:`/`stopped:` line like every error answer.
  - A 404 asked again that is still a 404 is not an error.
  - Nothing else changes (the count, the budget, the cache). For a first run the two conditions are equivalent.
- **Test:** `test_a_cached_404_asked_again_and_answered_with_an_error_shows_on_the_summary_line`.
- **Before** (reviewer A's step 9, C4): `done: 4 fetched, credits 60 (this run 60), remaining 4,999,940, cached 404s 2`
- **After:** `done: 4 fetched (1 answered with an error and not saved; a rerun asks again), credits 60 (this run 60), remaining 4,999,94…, cached 404s 2`
- The step 9 output is otherwise byte-identical to cc14201's.

### 6. Runbook (c23c19a), `sharp-markets/docs/ODDS5M_DAY_ONE.md`

- **a. F3's plan line (C m1).** Day one step 3 now says that on October 1 F3's line shows about 108,300, not the plan's 136,800, because only the 2026 games already played count. F3b's dry run likewise shows about 74,100 against 102,600. Both figures are from reviewer C's rehearsal logs, which used the real NFL kickoffs. The published estimates are unchanged.
- **b. A balance that couldn't be read (C m2).** It is off the rerun list in the paragraph under the table and is on the tell-the-hub list there and in day-one step 2's list. That now agrees with its table row and with the probe's own `Tell the hub before rerunning` (`rerun=False`).
- **c. What can still be lost (B2).** One sentence added: credits added during an under-reporting run add to the loss.
  - A top-up no larger than the margin looks like an out-of-date reading, so the loss grows by its size. In reviewer B's simulation, F1 charged twice what it reported, a 15,000-credit top-up took the loss from 15,780 to 30,780.
  - After a larger top-up the run restarts from a reading that may be late, so the charges of the answers it lags can go unseen again.
- **d. After an alarm (B3a).** The alarm row now says to rerun with the larger of what `headers` advises now and the margin written down after the probe, because `headers` looks back only one run. Day one step 5's alarm bullet says the same: the larger of the advice and A30 (A60 for F3a and the NBA week).
- **e. Two runs at once (B4).** Near the floor, each can go past it by a few calls, or by as many calls as the balance header is late: 100 calls, 3,000 credits, about 7 cents with a header 100 answers late.
- **f. The "If a run stops" table covers the new lines:**
  - `... with JSON it cannot read (...)`, in the not-JSON row, now saying it counts the larger of what it said and its most possible cost;
  - `no answer from the Odds API (...; not retried)`, in the network row;
  - what `unexpected error` now counts, in its row.
  - I grepped every `raise`/`print` of a stop in `bulk.py`, `client.py`, `ingest.py` and `cli.py`: each maps to a row.
  - The protections list says an unreadable 200 counts at least its upper bound, and that a `--retry-404` error answer is on the pull's line.
  - The BulkClient and odds-pull client docstrings say the same.

### 7. Cosmetic (e40035e)

- `headers` prints "1 answer" (singular) in the requests, longest-stretch, lateness and advice lines. The verdict line already did.
- `key ok:` formats `x-requests-used` like the other numbers, or prints `unknown` when it can't be read. That applies to odds5m, odds-pull and `balance`.
- No existing test parsed these lines. New test: `test_the_headers_stage_and_the_key_check_print_their_counts_plainly`.
- **Before:** `longest stretch in a row: 1 answers`, `2 x 1 answers x 30`, `12421 used`.
- **After:** `1 answer`, `2 x 1 answer x 30`, `12,421 used`.

## Not fixed, and why

- **B1: default-margin false alarms on 60-credit pulls.** With the default margin, F3a and odds-pull right after it false-alarm under a header that runs up to 100 answers late with varying lateness. Fixing it needs a new rule (a different default margin), which is the hub's call. The runbook's printed commands already carry A60, and reviewer B found 0 false alarms with it.
- **B3b and B3c: `headers`' lateness figure.** It is unreliable for varying headers, and it overstates the probe when an out-of-date rise hides expensive probes. Fixing either would change the headers stage's verdict or lateness logic, which I was told not to change. B3a is handled in the runbook (fix 6d). None of these caused a false alarm or a missed stop in reviewer B's runs.
- **C's note on N1:** N1 plans the NBA playoffs, but its 486,440 figure covers only the regular season. That is outside this PR's accounting, and the real schedule isn't in the cloud. The hub should know before N1's gate.
- **A's observation:** `check`/`coverage()` counts sealed games (counts only, no prices). The code is unchanged from main; it is the hub's call.
- **Bug paths without a manifest row:** after an error other than a Stop (only reachable through a code bug, not an API body), `_count_out` counts the answer but writes no row. Writing the row could fail in the same way.

## Questions for the hub

1. **The CFP title game.** Should March buy the NCAAF 2026 title game (2027-01-26T00:30Z)?
   - **As committed:** no. The window ends Jan 25, 2027, as on main; the game is in no window, so nothing plans it, and any row of it is judged by its call (left out when the call is sealed).
   - **If yes:** set `to: 2027-01-27`. That adds about 5,410 credits at most to March (F1 +8 calls, F4 +169, F5 +2, F6 +1, plus 1 sweep). Then update `test_nothing_bought_changed_since_main_but_the_nhl_start` (the change set and the NCAAF assertion) and the NCAAF line of the sealed-window test.
2. **The count for a 200 that isn't JSON.** Such an answer now counts the larger of what it reported and its upper bound, where it used to count what it reported, because its documented cost can't be worked out. I applied the brief's wording for "a 200 whose body cannot be interpreted" to it too. It only makes a run that is stopping anyway count more. Keep it?
3. **B1, the default margin for 60-credit pulls.** Raise it (for example to at least 2 × 100 × the call's upper bound, 12,000 for 60-credit calls), or accept that the runbook's A60 is required on F3a and odds-pull.
4. **MLS and K League window ends.** They add at most 7 one-credit sweeps, and only to a probe run after mid-December (a March re-probe). No pull buys those seasons. Accept, as the brief said to leave them?
5. **Raw socket errors.** A raw socket error from the session now stops the run at once, counted at its upper bound, and is not retried. Should it be retried like a `requests` ConnectionError instead? That would be a change in `markets.http`.

## Files

- Commits: 7f385be, 8e43528, 0fb8f29, 7bb0c5f, 0e7b6eb, c23c19a, e40035e, on `claude/quirky-goldberg-81hwy6`. Not pushed.
- Scripts and outputs: `$S/fix/on_cc.sh` (runs the working tree's tests against cc14201's code), `$S/fix/fp/` (fingerprint runs and comparisons), `$S/fix/revA_rerun/` (reviewer A's harnesses rerun on HEAD).
- Cleanup: I deleted every cache and data folder I created (`$S/fix/data`, the fingerprint data folders, the harness data folders and the fingerprint JSONs). `$S/pr63` and `$S/main63` show no changes.

## Addendum: the fix review's four findings (`review/FIXREVIEW.md`), e40035e..2be2877

**Full suite:** 262 passed. That is the 259 from before, plus 2 test nodes for item 1 and 1 for item 3. Every new or changed test fails on cc14201's code (`fix/on_cc.sh`). None of these commits touches rules 1–9, the margin, rule 6 or the `headers` verdicts.

### 1. c1bf725: an answer counted before a bug keeps its row, or the STOPPED line says what the row held (finding 1, major by the letter)

- **Code change.** This was a small, safe change, so I made it in the code as well as the documents. After an error other than a Stop, `_count_out` now writes the manifest row of an answer that was already counted, as the Ctrl-C path does; both paths now share `_write_unlogged`. If the row can't be written, the STOPPED line says so and says what the row would have held. The line also says how the other kinds of cut-short attempt were counted.
- **Documents.** The runbook's `unexpected error` row and its Manifest bullet now say exactly this.
- **Test:** `test_an_answer_counted_before_a_bug_keeps_its_count_and_its_row_or_the_line_says_what_it_held`, in two cases:
  - **The row can't be written** (a lone-surrogate timestamp): the answer is counted at 20, and the line says what its row would have held.
  - **A bug in `_saw_balance` after the count:** the row is now written, and both answers have rows.
- **Before (e40035e, the reviewer's `surrogate.py`):**
  ```
  counted 20; manifest rows ['account']; STOPPED: unexpected error, probably a bug; tell the hub before rerunning (UnicodeEncodeError: ...)
  ```
- **After:**
  ```
  ... (UnicodeEncodeError: ...). The answer that had come back was counted at what it cost, 20 credits. Its manifest row could not be written (...); it would have held HTTP 200, credits_last 20, cache key e1f0f62b5360b2e2de2b.
  ```

### 2. a2e8f3d: the not-JSON row tells you not to rerun when the charge is above the upper bound (finding 2, minor)

- **Before:** the row said only "Rerun later ...".
- **After:** it adds: "If the line ends `more than its upper bound of M`, tell the hub and don't rerun, as for any charge above the most a call can cost." That matches the code's `rerun=False` and the probe's own hint.

### 3. 58d71e7: "not retried" comes before the socket error's text (finding 3, cosmetic)

- **Before:** `no answer from the Odds API (TimeoutError: ...?apiKey=REDACTED not retried)`. The semicolon was lost.
- **After:** `no answer from the Odds API (not retried; TimeoutError: timed out: .../odds?apiKey=REDACTED). Nothing was cached ...`
- The runbook row now quotes `(not retried; ...)`.
- The test adds an error whose text ends in a URL with the key. The key is blanked, and the line keeps everything else.

### 4. 2be2877: the --retry-404 line names the flag a rerun needs (finding 4, cosmetic)

- **Before:** `done: 2 fetched (2 answered with an error and not saved; a rerun asks again)`
- **After** (in a `--retry-404` run): `done: 2 fetched (2 answered with an error and not saved; a rerun with --retry-404 asks again)`
- Other runs are unchanged. The runbook's `--retry-404` sentence quotes the new line.

**Not changed:** the reviewer's observation that `run_calls` reads the cache outside its `try` (in `_todo` and the cached-404 count) is pre-existing and was not in the list. The questions for the hub above still stand.
