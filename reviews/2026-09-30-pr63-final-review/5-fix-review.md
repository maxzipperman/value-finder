# Review of the fix for PR 63 (cc14201..e40035e, 7 commits on claude/quirky-goldberg-81hwy6)

I did not write the branch, the reviews or the fix. I fixed nothing. Everything ran against fake sessions or servers on
127.0.0.1, with `ODDS_API_KEY=FAKESECRETKEY999` and `MARKETS_DATA_DIR` inside `$S/fixrev`. No `.env` was opened, and
nothing was committed or pushed.

- `S=/tmp/claude-0/-home-user-value-finder/d7012428-080d-54f3-a1da-3ceb35298eec/scratchpad`
- My scripts and outputs are in `$S/fixrev`. My worktree was `$S/fixrev/tree`, detached at e40035e.
- The unfixed code is `$S/pr63` (cc14201). I only ran it; `git status` there is clean.
- I used at most 2 worker processes at a time, each under `ulimit -v 4000000`. No simulation passed 100 MB RSS, and the
  largest rehearsal command peaked at 371 MB.

## Verdict

- **Safe to merge into bulk-puller-followup as far as spending goes.**
  - On the realistic API, the fix changes nothing. 580 simulated honest runs gave the same result as on cc14201, run
    for run.
  - Every kind of stop now latches: `fetch`, `account()` and `run_calls` all refuse, and nothing is sent.
  - The count is never lower than cc14201's.
  - What is bought on Thursday is identical to cc14201.
  - The suite passes after a trial merge with today's main.
  - The key is clean in 59 of 59 cases.
- **No blocker.**
- **One finding is major by the brief's letter** ("a runbook sentence that does not match the code"). In practice it
  has no effect: it arises only on a bug path, or with a fault-case body. It would take one sentence to fix, or the hub
  can accept it (finding 1).
- The other findings are minor or cosmetic.

## Findings

### 1. MAJOR by the letter (runbook sentence); no effect on spending: an answer already counted when a non-Stop error hits has no manifest row, and the fix's new "unexpected error" row misstates its count

- **Rules broken:** brief step 5/6 ("every sentence ... matches what the code prints") and the severity entry "a runbook
  sentence that does not match the code".
- **The sentences:**
  - `docs/ODDS5M_DAY_ONE.md:52` (the "unexpected error" row, rewritten in c23c19a): "A request that was out is counted
    at its most possible cost, and an answer that had come back at the larger of what it said and its most possible
    cost."
  - `:102` (the Manifest bullet, unchanged): "Every answer gets a row".
- **Reproduction** (`$S/fixrev/surrogate.py`): a 200 with data whose `timestamp` is a lone-surrogate escape (`"\ud800"`).
  It is valid JSON and interpretable, reported 20, documented 20, upper bound 30.
  ```
  cd $S/fixrev/tree/sharp-markets && ODDS_API_KEY=FAKESECRETKEY999 uv run python $S/fixrev/surrogate.py
  upper bound 30, reported 20, documented 20 -> counted 20; paid 1; manifest rows ['account']; cached True; rerun=False
  STOPPED: unexpected error, probably a bug; tell the hub before rerunning (UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 130: surrogates not allowed)
    stopped: 1 fetched, credits 20 (this run 20), remaining 999,980, cached 404s 0
  ```
  - The answer is counted at 20, not "the larger of what it said and its most possible cost" (30).
  - It has no manifest row, and it is cached, so a rerun never writes one.
  - The STOPPED line doesn't say the row is missing.
- **The same thing happens after any bug that follows the count.** My latch harness raised a ValueError in
  `_saw_balance`, and in `write_record`: in both cases the answer was counted, the manifest rows were
  `['account']`, and there was no row for it.
- **Cause:**
  - `_account` counts in its one statement (`bulk.py:832`).
  - `_log` then raises something other than an OSError, so `except OSError` (`bulk.py:838`) doesn't catch it.
  - `_latched` calls `_count_out` (`bulk.py:515`, `:595`), which rightly adds nothing, because `_answer` is already
    cleared.
  - `_unlogged` is left set and never written.
- **What was already there, and what the fix added:**
  - cc14201 counts the same 20 and writes no row either (same script on `$S/pr63`). There the client also stayed
    unlatched.
  - The missing row is pre-existing, and the fixer lists it under "Not fixed".
  - The wrong count in the table row is the fix's own sentence.
- **Impact:** none on spending. The count is rule 1's, and the client refuses everything after. Step 8's reconciliation
  would show one call and 20 credits more on the server than in the manifest.
- **A possible fix without a new rule:** one sentence in the row, for example "... or, if it had already been counted,
  at what it cost; its manifest row may then be missing". Or the hub accepts it.

### 2. minor: a 200 it can't interpret that also reports above its upper bound says "Rerun later" in the table, but the code says tell the hub

- Reproduced with a body of `{"timestamp": "x", "data": 5}` reporting 300 on a call whose bound is 30. The code returns
  `rerun=False` (`bulk.py:856`), and the line is:
  `... the API answered HTTP 200 with JSON it cannot read (...). It was not cached, so a rerun asks again. It counted 300 credits, the larger of what it reported and its upper bound (x-requests-last '300'), more than its upper bound of 30.`
- The table row (`ODDS5M_DAY_ONE.md:47`) says "Rerun later; a rerun asks for it again."
- The probe's closing hint follows `rerun=False` ("Tell the hub before rerunning").
- This was already the case for non-JSON bodies at cc14201. The fix extends it to the new kinds of body. It is a fault
  case only.

### 3. cosmetic: `; not retried` loses its semicolon when the socket error's text ends in a URL with the key

- `scrub`'s query pattern (`http.py:33`) does not stop at `;`, so it eats the semicolon after `apiKey=REDACTED`.
- Printed (key-scan case `sess_oserror`):
  `STOPPED: no answer from the Odds API (TimeoutError: socket timed out on http://127.0.0.1:.../odds?apiKey=REDACTED not retried).`
  The table quotes `(...; not retried)`.
- The key is blanked. A real raw TimeoutError carries no URL.

### 4. cosmetic: after `--retry-404`, an error answer is reported as "a rerun asks again"

- Reviewer A's `step9.py`, rerun on e40035e, prints
  `done: 4 fetched (1 answered with an error and not saved; a rerun asks again), ..., cached 404s 2`.
- A plain rerun won't ask again, because the old 404 is still cached; only a rerun with `--retry-404` does.
- The runbook's own sentence (`:66`, "keeps its 404, and the line counts it with the error answers") is right.

### Observation (pre-existing, not the fix; checked in library use only, not through the CLI)

- `run_calls` reads the cache outside its `try`, in two places: `_todo` (`bulk.py:960`) and the summary's cached-404
  count (`:995`).
- So a cache lookup that raises there escapes `run_calls` as a PermissionError traceback, not a STOPPED line.
- Nothing is sent, and the client is latched if the failure came inside a fetch.

## 1. The suite, and the new tests on cc14201

- **At e40035e:** 259 passed in 167 s (`uv run pytest -q -o addopts="" -p no:cacheprovider`, `$S/fixrev/out/suite.out`).
- **The new tests against cc14201's code:** I copied e40035e's `tests/test_bulk.py` to `$S/fixrev/cc/tests`. Then I ran
  each new or changed node in its own process, against `$S/pr63`'s code, config and venv (`$S/fixrev/each_on_cc.sh`,
  output in `$S/fixrev/out/new_on_cc.txt`).
  - **All 14 new nodes fail on cc14201:**
    - session error (1);
    - uninterpretable 200 (3);
    - other error in a fetch (2);
    - raw socket error (2);
    - key check refused (3);
    - `--retry-404` line (1);
    - headers wording (1);
    - nothing bought changed (1).
  - **The two changed assertions also fail there:** the non-JSON test (`spent == 60`), and `...[americanfootball_ncaaf-last]`.
- **The rewritten `test_ctrl_c_inside_the_accounting...[before its count]`** passes on both commits. Its cc14201 form
  (Ctrl-C at the third `_envelope` call) fails on e40035e for timing alone. That call now falls inside the second
  answer, before it is cached:
  `counted=40 billed=40 rows=['20','20'] ... counted at what it cost, 20 credits, and a rerun buys it again.`
  The count is right and the line is accurate, so the rewrite is legitimate.

## 2. Against the rule

**Reading the diff (`git diff cc14201 e40035e`, 7 files):**
- `_precheck`, `_saw_balance` (rule 6), `margin`, `remaining`, `unexplained`, the alarm, rule 9 and the if-chain after
  `problem` in `_account` are unchanged.
- The only changes to headers.py are in what it prints (`_answers`).
- No path under nfl-weather/, cfb-weather/, CLAUDE.md, any PREREGISTRATION/STRATEGY, or the price engine changed.

**The count is never lower than cc14201's** (`$S/fixrev/garbled.py`, 48 cases: 8 bodies × reported
None/0/10/30/31/300, bound 30):
- On every case, e40035e counts at least what cc14201 counted.
- They are equal wherever cc14201 didn't crash, except where a non-JSON, empty or `null` body reported less than its
  upper bound: those now count the upper bound. This is the fixer's Q2, a question for the hub.
- cc14201 counted 0 for `data` 5, `data` true and `bookmakers` 5 (the crash). It also accepted `data 'abc'` as a good
  answer: no stop, counted as reported.
- The counts show `max(reported, bound)`, so a run can pass its budget only by `reported − bound`, and only when that is
  positive. That run stops with `rerun=False`: the same allowance as rule 1's "above the upper bound".

**No double count:**
- A session error counts the upper bound once (`counted=30 unanswered=30`).
- A bug before the count gives `max(reported, bound)` once. A bug after the count adds nothing more.
- A Ctrl-C inside the accounting counts once (reviewer A's `ctrlc_mid.py`: `counted=60 manifest rows=2`).

**Honest API, no false stops** (reviewer B's `sim.py` and `fakeapi.py`, copied; 20 seeds per setting; output in
`$S/fixrev/revB/compare.txt` and `compare2.txt`):

| Setting | Runs | Finished | Budget stop (timeouts) | Floor | Alarm | Other | Count below charged |
|---|---|---|---|---|---|---|---|
| F1, P0 and P0+ × live, late 3, late 0–3, steps 50 | 240 | 240 | 0 | 0 | 0 | 0 | 0 |
| F1, 5% timeouts, unbilled and billed | 40 | 14 | 26 | 0 | 0 | 0 | 0 |
| P0 and P0+, 5% timeouts, unbilled and billed (P0+ at plan + 5%) | 80 | 80 | 0 | 0 | 0 | 0 | 0 |
| P0+ as Thursday (every sweep lists games, 11,000): live, late 3, late 0–3, steps 50 | 80 | 80 | 0 | 0 | 0 | 0 | 0 |
| P0+ as Thursday, 5% timeouts, unbilled and billed | 40 | 0 | 40 | 0 | 0 | 0 | 0 |
| F1, late 0–100 | 20 | 20 | 0 | 0 | 0 | 0 | 0 |
| P0+, late 0–100, plus 500 from others | 20 | 20 | 0 | 0 | 0 | 0 | 0 |
| F1, worst realistic (late 0–100, 5% billed timeouts, 500 from others) | 20 | 4 | 16 | 0 | 0 | 0 | 0 |
| Day one: F3a after F2, late 0–100, plus 500, at A60 12,000 | 20 | 20 | 0 | 0 | 0 | 0 | 0 |
| Day one: odds-pull after F3a, late 100, plus 500, at A60 12,000 | 20 | 20 | 0 | 0 | 0 | 0 | 0 |

- **Every run is identical to the same run on cc14201:** 580 of 580 records compare equal.
- There were no false alarms, no floor stops, and no budget stops without timeouts.
- The budget stops all come from timeouts (5% timeouts on a run budgeted at plan + 5%), as reviewer B found. The P0+
  Thursday rows match B's (0 of 200 finished).
- Every stopped client refused a further attempt with the same stop and sent nothing.
- I ran 20 seeds per setting instead of B's 100, as the brief for this job asked.

**Manifest rows on normal paths:**
- An uninterpretable 200 gets its row (tests, and my latch harness shows `rows=['account','F1']`).
- An attempt with no answer (session error, raw OSError) has no row, like a timeout, which the runbook states.
- An answer counted without a row happens only after a non-Stop error that follows the count (finding 1).

## 3. Latching (`$S/fixrev/latch.py`; output in `$S/fixrev/out/latch_e4.out` and `latch_cc.out`)

**What each case checks:** after the stop, the same client gets `fetch(new call)`, `account()` and
`run_calls([2 new calls])`. Each must raise the same Stop object, send 0 requests, and leave counted, start, lowest,
unexplained and fetched unchanged.

**e40035e: 29 of 29 OK.** The kinds of stop:
- budget; floor; alarm; unreadable balance with a floor;
- billed above the bound; reported below documented; unreadable cost;
- an uninterpretable 200 (`data` 5, not JSON, `bookmakers` 5);
- a session RuntimeError; a raw TimeoutError; a raw ConnectionResetError;
- Ctrl-C with a request out; network after retries;
- 401; 429 after retries; 5 errors in a row; a retried 500 billed above the bound;
- the count past the budget after an answer (3b); an unknown balance;
- ENOSPC on the cache; ENOSPC on the manifest; a cache read error;
- a bug in the accounting; a bug while saving.

**The probe's exception still works:**
- Five 422s in one sport give `skipped={'soccer_a': 2}`, `client.stopped=None`, and the next sport's sweeps and a later
  fetch are sent.
- Five 5xx still stop the run.
- odds-pull's first error status latches too, for `account()` and `fetch`.

**cc14201: 27 of 29 bad.**
- `account()` was sent after every kind of stop.
- The session error, the garbled 200s, the cache read error and the bugs left the client usable.

## 4. What is bought (reviewer A's `fingerprint.py` and `compare.py`; one synthetic schedule set from main's and cc14201's windows)

**Thursday's clock (2026-10-01T12:00Z):**
- **e40035e against cc14201:** the 153,355 rows are identical, in order, sealed flags included. `only on main: 0 only on
  branch: 0`. odds-pull's 742 calls are identical, down to their files and stored params.
- **e40035e against main 4bf0497:** only e40035e has 13: the 3 NHL `/events` sweeps (Sep 28–30) and 10 synthetic H1
  NHL calls. Main has 0 of its own.

**March clock:**
- **e40035e against cc14201:** only removals, 71 NCAAF calls dated 2027-01-25..27 (F1 6, F4 52, F5 8, F6 4, P0 1).
- **e40035e against main:** 20 extra: 10 H1 NHL calls, plus P0 sweeps (3 NHL, 5 MLS, 2 K League). The MLS and K League
  sweeps are the fixer's Q4.

**`test_nothing_bought_changed_since_main_but_the_nhl_start` (`git show 4bf0497:...`):**

| Where it runs | Result |
|---|---|
| A shallow clone (`--depth 1`, 4bf0497 absent) | `SKIPPED ... main's config at 4bf0497 is not in this checkout's git history`. The NCAAF assertion still ran (the ncaaf-last node passed). |
| With `git` missing from PATH | skipped |
| Full history | passed |

**Day-one step 1 after the merge:**
- origin/main has moved to 30444ec (PRs 70, 78, 81 and 83).
- `config/odds5m.yaml` has not changed on main since 415348177 (Sep 29, before 4bf0497). The new sharp-markets files on
  main are H3/Kaggle only.
- In a throwaway clone of main, `git merge --no-commit --no-ff e40035e` merged cleanly. Its config and oddsapi code are
  identical to e40035e's.
- `uv run pytest -q -o addopts="" -rs` gave **305 passed, 0 skipped** (so the pinned-commit test ran and passed).
- It will not fail day-one step 1.

## 5. The key (reviewer A's step 8 harness, extended: `$S/fixrev/revA/step8/case2.py` and `runner2.py`)

**Setup:**
- 59 cases, each in its own process: the real CLI with logging at DEBUG, a raw 127.0.0.1 server, or fake sessions.
- The 38 original cases, plus 21 new ones:
  - a garbled 200 echoing the URL and key (`data` 5; HTML; `bookmakers` 5), on full, probe and odds-pull;
  - a session RuntimeError whose message holds the full URL with `apiKey=`, on a paid call, and at the key check for
    balance, full and odds-pull;
  - a raw TimeoutError or ConnectionResetError whose text holds the URL with the key, on a paid call and at the key
    check;
  - a bug whose message quotes the key and a URL with it.

**What I scanned:** stdout, stderr (every DEBUG and ERROR line, tracebacks included), the manifest, and the schedule and
cache parquet (raw bytes and decoded rows). I searched for `FAKESECRETKEY999`, its encoded forms, `FAKESECRET` and
`SECRETKEY999`.

**Result:**
- **All 59 cases are clean.** The lines show `apiKey=REDACTED` and `REDACTED`.
- The 38 original cases print the same lines as on cc14201. The one exception is a dropped-connection case whose timing
  gave `ReadTimeout` instead of `RemoteDisconnected`, which takes the same path.
- The rehearsal's 72,022 cached records, its logs and its manifest also hold no key.

## 6. The runbook, and reviewer C's rehearsal on e40035e

**Rehearsal** (`$S/fixrev/revC`, C's `fake_api.py`, `synth.py`, `setup_kalshi.py` and `step.py`, pointed at my
worktree):
- It ran 21 commands in the runbook's order, as printed: probe dry run, plan, `probe --confirm --max-credits 11000`, both
  `headers --pull P0`, plan, plan F3 2025, week dry run, `week --confirm ... --alarm-margin 5,000`, both
  `headers --pull F1`, F1, check, F2, check, F3a (`--alarm-margin 5,000`, which is A60), check, odds-plan,
  `odds-pull ... --alarm-margin 5,000`, step 8's DuckDB query, and `balance --confirm`.
- I skipped price-engine (2.7 GB in C's run), build and backtest, the weather steps, and HB1/HS1.
- **Every command exited 0.**

| Command | Requests | Billed | Counted | Manifest rows | `credits_last` |
|---|---|---|---|---|---|
| probe | 10,442 | 10,331 | 10,331 | 10,442 | 10,331 |
| week | 90 | 2,090 | 2,090 | 90 | 2,090 |
| F1 | 4,546 | 128,100 | 128,100 | 4,546 | 128,100 |
| F2 | 1,773 | 35,100 | 35,100 | 1,773 | 35,100 |
| F3a | 571 | 33,720 | 33,720 | 571 | 33,720 |
| odds-pull | 663 | 6,620 | 6,620 | 663 | 6,620 |
| balance | 1 | 0 | – | 1 | 0 |

- **Totals:** 18,086 requests = 18,086 rows, and 215,961 billed = counted = `credits_last`.
- `verify.py` finds the (sha256, credits) multisets identical: statuses 200 × 18,061 and 404 × 25 on both sides.
- The lowest balance, 4,784,039, is the same on the server, in the manifest and in `balance --confirm`.
- Each figure equals reviewer C's cc14201 rehearsal.

**Sentences the fix changed, checked against the printed output:**
- **Checked and right:**
  - F3's plan line prints 108,300 (step 3's new sentence).
  - `key ok: ... 10,331 used` is formatted.
  - `headers` prints `0 answers` and `1 answer` (the unit test).
  - The garbled-200 line says "the larger of what it reported and its upper bound".
  - The network row's `(...; not retried)` (apart from finding 3).
  - "counts at least the call's most possible cost".
  - The paragraph under the table now puts an unreadable balance with the stops to tell the hub about (code:
    `rerun=False`).
  - The two-runs figure (100 calls, 3,000 credits, about 7 cents).
  - The top-up example (15,780 to 30,780, reviewer B's numbers).
  - The NCAAF exception in the sealed paragraph.
  - The `--retry-404` sentence.
- **Mismatches:** findings 1 and 2.

**"If a run stops":**
- I grepped every stop message constructed in bulk.py, client.py and ingest.py at both commits.
- The fix adds exactly three texts: `... JSON it cannot read`, `no answer from the Odds API (...; not retried)`, and
  `unexpected error ... It came from sending the request, which got no answer`. Each has a row.

**The loss paragraph:**
- It still says an honestly reported charge above a call's upper bound passes the budget: "having paid the difference,
  however large, even when the answer reports that charge honestly".
- Its new top-up sentences match reviewer B's simulation.
- I found nothing in it that contradicts the table or the protections list.

## What I did not check

- HB1/HS1, price-engine, build and backtest, and the weather steps in the rehearsal (see above).
- Missed-stop simulations: the fix does not touch the balance, the alarm or rule 6, and the honest runs were identical
  run for run.
- The fixer's questions for the hub (the title game; the count for a non-JSON 200; B1's default margin; the MLS and K
  League sweeps; retrying raw socket errors) are decisions, not defects.

## Cleanup

- Deleted my worktree, every MARKETS_DATA_DIR cache, the rehearsal data and state, the fingerprint data and JSONs, the
  key-scan data folders, and the throwaway clones (`shallow`, `mergetest`).
- Kept the scripts, the logs and this report.

---

# Addendum: review of the follow-up fix, e40035e..2be2877 (4 commits)

The four commits: c1bf725 (code), a2e8f3d (runbook), 58d71e7 (code), 2be2877 (code).

- I used the same rules as above, and fixed nothing.
- I made a detached worktree of 2be2877 at `$S/fixrev/tree2`, with its own `uv sync`, and removed it at the end.
- I ran e40035e's code from a `git archive` export (`$S/fixrev/e4src`, on PYTHONPATH), and cc14201's from `$S/pr63`.
- Outputs are in `$S/fixrev/out2`, `$S/fixrev/rows.py`, `$S/fixrev/revB/sim3_2b.*`, `$S/fixrev/revC/logs2`, and
  `$S/fixrev/revA/step8/{case3,runner3}.py`.

## Verdict

- **2be2877 is safe to merge into bulk-puller-followup.** The four findings above are fixed as described, and the
  runbook matches the code.
- c1bf725 writes no row twice, writes no row for an answer that wasn't counted, and changes no count.
- On the normal path, nothing changed: 80 honest runs are identical to e40035e, and a rehearsal gave billed = counted =
  manifest.
- The key is clean in 66 of 66 cases.
- **No blocker and no major.** There is one minor finding, in library use only, and one pre-existing observation for
  the hub.

## The four items

**1. c1bf725: an answer counted before a bug keeps its row, or the line says what the row held.**
- **Reproduction:** `$S/fixrev/surrogate.py`, now on 2be2877.
  ```
  counted 20; manifest rows ['account']; ... STOPPED: unexpected error ... (UnicodeEncodeError: ...). The answer that had come back was counted at what it cost, 20 credits. Its manifest row could not be written (...); it would have held HTTP 200, credits_last 20, cache key e1f0f62b5360b2e2de2b.
  ```
- **The same error without the surrogate:** a ValueError in `_saw_balance`, after the count. The row is now written.
  The latch harness shows `rows=['account', 'F1']`, where e40035e showed `['account']`.
- **`$S/fixrev/rows.py`:** 6 cases, each run on 2be2877 and on e40035e. Each makes 3 F1 calls, with the error on the 2nd.

| Case | Counted (2be2877 / e40035e) | Paid rows (2be2877 / e40035e) | Duplicate rows |
|---|---|---|---|
| `_log` writes the row, then raises | 60 / 60 | 2 / 2 | none |
| A bug after the row (alarm check) | 60 / 60 | 2 / 2 | none |
| A bug before the count (`write_record`) | 60 / 60 | 1 / 1 | none |
| A bug between the count and the row | 60 / 60 | **2** / 1 | none |
| The same, on a retried 503 | 30 / 30 | **2** / 1 | none |
| The row can never be written | 60 / 60 | 1 / 1 | none |

  - In the "bug before the count" case, the line says `... counted at 30 credits, the larger of what it reported and
    its upper bound, and has no manifest row (it would have held ...)`.
  - In the "row can never be written" case, the line says `... counted at what it cost, 30 credits. Its manifest row
    could not be written (...); it would have held ...`.
- **Why a row can't be written twice, or written for an uncounted answer:**
  - `_unlogged` is set only in the counting statement (`bulk.py` `_account`). It is cleared once `_log` returns or its
    OSError is handled.
  - `_write_unlogged` writes only when the manifest's size is unchanged since the count.
  - `_count_out` runs once, while `stopped` is None.
  - The unlogged branch adds nothing to the count. The other two branches are e40035e's, unchanged.
- **Counts:**
  - `garbled.py`: all 48 cases give the same counts as e40035e.
  - `latch.py`: 29 of 29 OK, with the same counts. Only the socket wording and the two row fixes differ.
  - Reviewer A's `rules.py`, `rules2.py`, `rules_oddspull.py` and `step9.py` differ from e40035e only in the reworded
    lines.
- **Ctrl-C:** the suite's Ctrl-C tests pass, and A's `ctrlc_mid.py` prints the same as on e40035e. The Ctrl-C path now
  shares `_write_unlogged`.

**2. a2e8f3d:** the unreadable-200 row now says "If the line ends `more than its upper bound of M`, tell the hub and
don't rerun". The line ends `..., more than its upper bound of 30.`, with `rerun=False`, so they match.

**3. 58d71e7:**
- The line now reads `no answer from the Odds API (not retried; TimeoutError: timed out: http://.../odds?apiKey=REDACTED). Nothing was cached ...`,
  as the new test node `[a URL with the key]` checks. The table row quotes `(not retried; ...)`.
- The key scan's `sess_oserror` and `sess_connreset` cases are clean.

**4. 2be2877:** the `--retry-404` line now reads `done: 4 fetched (1 answered with an error and not saved; a rerun with --retry-404 asks again), ...`
(A's step 9). This matches the runbook's cache paragraph.

## Tests

- **Suite at 2be2877:** 262 passed, in 162 s.
- **The 6 new or changed nodes:** `raw_socket_error[error0, error1, a URL with the key]`,
  `cached_404_asked_again_and_answered_with_an_error...`, and
  `an_answer_counted_before_a_bug...[its row can't be written, a bug before its row]`.
  - All 6 fail on e40035e's code and on cc14201's.
  - All 6 pass on 2be2877.

## The normal path

- **Honest API** (B's `sim.py`, 10 seeds each; F1 and P0 × live, late 3, steps 50, 5% billed timeouts): 80 runs, every
  record identical to seeds 0–9 of the e40035e run.
  - F1 with timeouts: 8 budget stops, all from timeouts. Everything else finished.
  - 0 false alarms, and no run whose count was below what was charged.
- **Rehearsal** (C's harness on 2be2877): probe, both `headers --pull P0`, plan, plan F3 2025, week dry run and
  `--confirm`, both `headers --pull F1`, F1 full, check, step 8's query, and `balance`. All exited 0.
  - probe: 10,442 requests, 10,331 billed = counted = manifest
  - week: 90 requests, 2,090 on all three
  - F1: 4,546 requests, 128,100 on all three
  - `verify.py`: 15,079 requests = 15,079 rows, and 140,521 = 140,521, with identical (sha256, credits) multisets. The
    lowest balance is 4,859,479 on both sides.
  - These are the same figures as the e40035e rehearsal. `headers` said live, and advised 5,000 for both 30- and
    60-credit calls.

## The key

- I reran the key scan with 7 more cases, 66 in all.
- The new cases:
  - a 200 whose `timestamp` is a lone surrogate and which echoes the URL and key (full, probe, odds-pull);
  - `_log` raising an error that quotes the key and a URL with it (full, odds-pull);
  - a bug after the count quoting the key, followed by a row that can't be written (full, odds-pull).
- These exercise the new "Its manifest row could not be written (...)" note, which carries the error's text.
- **All 66 are clean** (stdout, stderr at DEBUG, manifest, cache). The note prints as
  `(... apiKey=REDACTED (REDACTED))`. The rehearsal's logs hold no key either.

## Findings

### minor (library use only): the row check can be misled when the manifest did not exist before the answer

- `_write_unlogged` takes an unchanged manifest size to mean the row wasn't written.
- If the manifest doesn't exist when the answer is counted, a failing `_log` first creates the file and writes its header,
  then fails on the row. The size has then changed, so `_write_unlogged` treats the row as written.
- **Result** (surrogate body, a client with no key check): `counted 30, paid rows 0, manifest exists True, line says the
  row is missing: False`. With a key check first, the line says it: `True`.
- **Not reachable from the CLI:** `odds5m` and `odds-pull` always write the key check's row before the first paid call.
- The Ctrl-C path already had the same test.

### Observation, pre-existing and not the fix (the same on cc14201 and on main 4bf0497): a 200 with data and an unparseable `timestamp` ends `full` in a traceback

- **Reproduction:** `ONLY=body200_badts .../runner3.py`, run on each code base. The body is `{"timestamp": "not a time", "data": [...]}`.
- **What happens:** the pull finishes (`done: 11 fetched, credits 330 ...`). Then `stage_pull` calls `coverage()`, and
  `parse_ts(body.get("timestamp"))` (`bulk.py:1082`) raises `ValueError: Invalid isoformat string: 'not a time'`, which
  escapes `cli.main`.
- The same happens after the surrogate case's STOPPED line.
- **Impact:** nothing is spent or mis-counted, because it happens after the summary. With `--pull F1,F2`, F2 would not
  start.
- It contradicts the runbook's "Nothing ends in a Python error dump" in this fault case.
- The fix could not cause this; it is for the hub.

## Cleanup

- Removed `$S/fixrev/tree2` and every data folder I created: the MARKETS_DATA_DIR caches, the rehearsal data and state,
  `revA/data` and `step8/data3`, and the `e4src` export.
- Kept the scripts, the logs and this addendum.
