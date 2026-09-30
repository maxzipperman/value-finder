# Audit 3: the code that will grade Thursday's results, before there are any

You are auditing a private research repo on this Mac. You have shell access. This is the third outside
audit. The first two (`reviews/2026-09-29-astra-audit.md`, and the two files in
`~/Documents/Codex/2026-09-29/audit-2/`) covered the alert jobs and the code that spends API credits.
This one covers the code that turns data into a verdict.

**Why now.** On Thursday, October 1, 2026 two things happen for the first time. A large set of historical
odds ("F1") is bought, and a registered backtest, the price engine, runs on it the same day. And at
5:00 PM Pacific the first college football game that can count toward a registered forward test kicks
off. Both pieces of code implement rules that were written down before any result existed. A defect
found today is a fix. The same defect found on Friday is a change made after seeing results, and the
result it touches can no longer be trusted. So find them today.

**Write your report to a new file: `~/Documents/Codex/2026-09-29/audit-3/<your-name>-audit-3.md`.**
Put scratch work under `~/Documents/Codex/2026-09-29/audit-3/scratch/`. Do not write into the repo, and
do not overwrite any existing file.

## The project in six lines

- **Value Finder** is paper-only sports-betting research. No real money, no order placement, GET-only API clients.
- Repo: `~/code/value-finder` (GitHub `maxzipperman/value-finder`, private), on `main` at `4bf0497` or later. Write the commit you audited at the top of your report. Two changes may merge while you work: a dashboard change that adds a `--json` output to the two scorers, and a small NBA study under `sharp-markets/src/markets/research/kaggle_h3.py`. Neither is in scope.
- Rules for every project are in `CLAUDE.md`. Current state is in `STATUS.md`.
- The project counts every variant it has ever tested (273 today) and judges any new result against p < 0.05 divided by that count.
- Two launchd jobs run the weather alerts four times a day (7:30 AM, 11:30 AM, 3:30 PM, 7:30 PM Pacific) from `~/code/value-finder/nfl-weather` and `~/code/value-finder/cfb-weather`. A third captures closing lines every 15 minutes. A fourth publishes the ledgers at 11:45 PM.
- The registered documents are `sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md`, `nfl-weather/PREREGISTRATION.md` (amendments 1 to 7) and `cfb-weather/PREREGISTRATION.md` (amendments 1 to 5).

## Hard rules

1. **Spend nothing.** Never pass `--confirm` to any `markets` command. Never call The Odds API, paid or free.
2. **Do not run `scripts/alerts.py` at all, not even with `--dry-run`.** Each run uses one of the 489 credits left on the free key, and the live alerts need them until Thursday. Never run `scripts/capture_close.py`. Never run a scorer (`scripts/score_forward.py`) without `--now` and without `--ledger` pointing at a copy or a file you built. Work from copies and from synthetic inputs; `tests/test_review.py` in each weather project shows how to drive an alert run with no network.
3. **Do not open, print or copy any `.env` file, or anything under `~/.kaggle/`.** Do not print a key or a token. If you see one in a log, a cache file or a manifest, report the file and line, not the value.
4. **Read-only on `~/code/value-finder`.** No edits, no commits, no branch switches, no `git pull`. `git fetch`, `git log`, `git diff`, `git show` and `git archive` are fine. The jobs run whatever is checked out there. To change or run other versions of the code, export them to your scratch folder (for example `git -C ~/code/value-finder archive 751ff67 | tar -x -C <scratch>/at-registration`).
5. **Do not touch launchd** (no `load`, `unload`, `kickstart`, `bootout`). `launchctl list` and `launchctl print` are fine.
6. **The rules are registered. Do not propose new ones.** A finding is a place where the code does not do what its registration says, where the registration contradicts itself, or where a number it quotes cannot be reproduced. A better threshold, a better flag or a better test is out of scope.
7. Report only what you reproduced. For each finding give the command you ran and its output.

Run project code with each project's own environment: `nfl-weather/.venv/bin/python`,
`cfb-weather/.venv/bin/python`, and `uv run` inside `sharp-markets/`. Suites at `4bf0497`:
sharp-markets 144 passed, nfl-weather 323, cfb-weather 316.

## Part A: the price engine (about 60% of your time)

The code is `sharp-markets/src/markets/research/price_engine/` (about 1,350 lines: `quotes.py`,
`engine.py`, `model.py`, `outcomes.py`, `run.py`, `fixture.py`). Its tests are
`sharp-markets/tests/test_price_engine.py`. It was registered by the merge of pull request 56, commit
`751ff67`. It runs with `uv run markets price-engine`; `--fixture` runs it on a small synthetic set.
No F1 data exists yet, so every check uses inputs you build, as `fixture.py` does.

Try to break each claim.

| # | Claim in the registration | What would break it |
|---|---|---|
| A1 | **Entries never look ahead** (sections 4 and 5). No snapshot at or after kickoff is an entry, and both the kickoff listed in that snapshot and the latest-listed kickoff must be more than 60 minutes away. | A bet from a snapshot inside the last hour, or after kickoff. Test a kickoff moved earlier, moved later, moved twice, a game postponed to another day, and an event whose id changes. Check that a row is timed by the snapshot time the API **returned**, not the time that was requested, and that a book's `last_update` never times a bet. |
| A2 | **The close** (section 6) is a book's quote in its last snapshot before kickoff, and only within 60 minutes of kickoff. | A quote at the kickoff instant or after it used as the close. A close from more than 60 minutes out. The close of a game whose kickoff moved. A bet with no Pinnacle close that is graded anyway, or dropped without being counted. |
| A3 | **2026 is sealed** (section 2): the backtest never reads a 2026 quote or a 2026 score. | Put one synthetic 2026 game in a scratch cache and in scratch score tables. Any trace of it in `bets.parquet`, `results.csv`, the counts in `dropped.csv`, or the calibration table. |
| A4 | **The arithmetic of the fair price** (sections 3, 4 and 6). | Reproduce with your own few lines, not the project's functions: the Shin de-vig on three price pairs; the blend at 0.55 / 0.30 / 0.15 with one book missing; the totals example in section 4 (52.4% and 52.2%; expected value of −1.9% and −2.3% at −115, +0.1% and −0.3% at −110); the spread example in section 6 (45.3% and 55.4%). Then compare with what the code returns. Any figure in the document that you cannot reproduce is a finding. |
| A5 | **One bet per game, market, side and variant:** the first flagged snapshot, at the flagged book with the best expected value (section 5). | Two bets on one side. A later snapshot chosen over an earlier one. A result that changes when the input rows are shuffled (run the same input in three orders and compare the outputs byte for byte). LowVig or BetOnline treated as a retail book. |
| A6 | **Signs and orientation** (section 6). | For each of the six kinds of bet (over, under, home and away spread, home and away moneyline) build one bet whose close moved toward it and one whose close moved away, and check the sign of the closing-line value in cents and in points. Then the result: a game where the feed's home team is the score table's away team (a neutral site, a bowl), and a push. |
| A7 | **Matching a game to its final score** (`outcomes.match`). A wrong match gives a wrong result and no error. | Two games between the same teams in one season (a regular-season game and a conference championship or a playoff). Two games of one school inside the 36-hour window. School names that share words (Miami and Miami of Ohio; the several "State" pairs). A postponed game. Say what the code logs for an unmatched game. |
| A8 | **The statistics** (sections 6 and 7): standard errors clustered by game; a one-sided p-value; the bar is 0.05 / 271 as registered, whatever the project's count is now. | Recompute `cmean` on a synthetic cell with your own arithmetic, including a cell where both sides of one game are bets. A cell with fewer than 100 bets, or fewer than 100 with a Pinnacle close, that still gets a verdict. |
| A9 | **`engine.decide` implements section 7 exactly:** the too-few rule, kills K1 to K4, conditions A1 to A6. | For each rule, build the smallest summary that breaks only that rule and check the verdict. Then try missing values: in Python a missing number compared with zero is false, so a missing closing-line value could pass a kill that reads "at or below zero". |
| A10 | **38 variants, 8 of them deciding, and nothing else can select a rule** (section 8). | A row count in `results.csv` other than 38. List every constant in `price_engine/` and say for each whether the registration states its value. A constant the registration does not state is a fork nobody counted. |
| A11 | **Frozen since registration.** | `git diff 751ff67..HEAD` on the engine's folder and on the registration. Then everything the engine imports: `bulk.load_rows` and the cache (changed by pull request 57 and possibly 63), `devig_shin`, `p_under_at`, the two `pricing_cohort.json` files, the processed score tables. Run `--fixture` from an export of `751ff67` and from `HEAD` and compare `results.csv`. Any difference needs a dated amendment; say whether one exists. |
| A12 | **It will run on Thursday.** | Block the network and run it: it must not try to connect. With no F1 data it must say there is nothing to backtest. Then size: F1 is about 4,500 calls, each listing every game of the sport with up to 10 books and 3 markets. Estimate the rows, the memory and the run time from the code, and if you can, build a synthetic cache of that size in scratch and time it. A crash on Thursday would mean repairing registered code after the data exists. |

Also answer, briefly:

- **A13.** What does `tests/test_price_engine.py` *not* establish? Up to five gaps, most important first.
- **A14.** Read the registration as a sceptical referee would. Is there any outcome of Thursday's run that the document does not say how to read? Is there any sentence that lets the owner choose between two readings after seeing the result?

## Part B: the first live signal, from alert to verdict (about 30%)

College football's wind rule ("Rule B") can signal on games from Thursday, October 1, 5:00 PM Pacific.
Its high-total rule ("Rule HT") starts October 6, and the NFL's wind rule October 8. Nothing has
signalled yet. The rules and their readings are in the two `PREREGISTRATION.md` files; the newest
amendments (NFL 6 and 7, college football 4 and 5) were registered on September 29 and no outside
reviewer has read them against the code.

Build a synthetic month in scratch: a ledger with signals, a schedule, closing lines and final scores.
Run the scorers on it with `--ledger`, `--now` and the schedule options (`--help` lists them). Check:

| # | Claim in the amendments | What would break it |
|---|---|---|
| B1 | The entry is the line and price in the **first** row where the game signalled. | A later or better row used as the entry. A row logged at or after kickoff counted. "Before kickoff" is the earlier of the row's kickoff and the schedule's; test a kickoff that moved each way after the signal. |
| B2 | The close comes from one odds-feed event per game: one the rule book priced, else the one nearest the kickoff, never one more than 6 hours away. At most 20 closes per capture. | Two feed events for one game (a rematch, a duplicate listing) where the wrong one's close is taken. A game left with no close and no record of why. |
| B3 | A bet is **void** if the kickoff moved more than 24 hours or there is no result after 30 days. A **pending** bet holds a decision open. | A void bet that still counts in the record. A decision made final while a bet is pending. A horizon date read in the wrong time zone. |
| B4 | A decision is recorded **once**, in `data/forward/decisions.csv`, and never rewritten. | A second run that changes a recorded line. A damaged or shortened record that is accepted, or published by `ops/sync_ledgers.sh`. Use scratch copies; `--test-record` and the script's own tests show how. |
| B5 | The keep test uses the **wider** of two half-widths: the plain one (Student's t, n − 1) and the one grouped by the Eastern date of kickoff (t, game days − 1). Fewer than 2 game days is inconclusive. | Recompute both on a 40-bet synthetic ledger with your own arithmetic. A game that kicks off late on a Saturday night Pacific falls on Sunday in Eastern time: which day does the code use? |
| B6 | The clock. | Daylight saving ends Sunday, November 1, 2026. Run the schedule helpers (`board.next_scheduled_run`, `is_last_run_before`) and the scorers across that night. A game with no kickoff time set. The turn of the year. |
| B7 | What the owner is told. | Read the alert text the code would send for a signal (from the code and its tests, not by running an alert). Does it give the number and the price to take, and the time? Does anything in it read as advice to bet real money, or as a proven edge? |
| B8 | The nightly publication. | After 11:45 PM Pacific: `git -C ~/code/value-finder fetch` then `git show origin/ledgers --stat`. Are both ledgers and both `runs.csv` files there, and is the absence of `decisions.csv` (none exists yet) handled without an error? If you run before then, say so. |

Pick **ten sentences** from the four newest amendments that state what the code does, other than the
ones above, and test each on a small synthetic input. Say which ten you picked and what happened.

## Part C: the spending code, only if it has merged (about 10%)

Pull request 63 closes the six findings C1 to C6 of the second audit. Check
`git -C ~/code/value-finder log --oneline -20 | grep "#63"`.

- **If it is merged:** rerun your audit-2 scripts (`~/Documents/Codex/2026-09-29/audit-2/scratch/`) against the current source and give one line per finding: closed or not, with the output. Then read `sharp-markets/docs/ODDS5M_DAY_ONE.md` as the owner will on Thursday morning, top to bottom, and run every step that is free (the ones without `--confirm`). Report any step whose output is not what the page says.
- **If it is not merged:** export the branch to scratch (`git fetch`, then `git archive origin/bulk-puller-followup`), do the same there, and say plainly that you audited a branch.

## Known and accepted: do not report these

- The price engine's main test passes almost automatically if Pinnacle is efficient (registration, section 7 and decision 6), and its H2 flag is negative expected value at its weakest (decision 7).
- The totals conversion rests on a small windy cohort that overlaps the backtest seasons (section 3).
- The NFL keep test keeps a rule with no edge 5.8 to 7.4% of the time, against an intended 2.5% (STATUS.md).
- Rule HT on a game with no kickoff time uses a midnight placeholder (issue 69).
- The service-academy result of 46 to 13 is unverified (issue 54).

## Out of scope

New strategy ideas, new hypotheses, refactors, style, naming, documentation polish, the dashboard and
the menu-bar light, and anything in `thesis/` or `thesis-research/`.

## The report

1. **Verdict, in three lines.** Can Thursday's price-engine result be trusted as registered? Can the first forward-test signal be graded as registered? Yes, yes with changes (list them), or no.
2. **Findings, most severe first, at most 15.** For each:
   - a one-line title;
   - severity: **blocker** (a registered result would be wrong, would use information from the future, or would read sealed data), **major** (the code does not do what a registered sentence says, or a quoted number cannot be reproduced), or **minor**;
   - file and line, and the registered sentence it conflicts with;
   - the command you ran and the output that proves it;
   - the smallest fix, and whether that fix changes a registered rule (if it does, say so: it needs a dated amendment before Thursday).
3. **What held up.** One line per claim (A1 to A14, B1 to B8, the ten sentences, C) that survived, with what you tested.
4. **What you couldn't check,** and why.
