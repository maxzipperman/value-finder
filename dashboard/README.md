# Dashboard: a local, read-only view on the Mac

One page at <http://127.0.0.1:8787/> showing the forward tests, the board of upcoming games, the scheduled jobs,
Thursday's pull and the research, from the files the jobs write. Paper only: it places no bet, changes no file
the jobs own, and listens on 127.0.0.1 only. Python standard library only; nothing is loaded from the internet.

```bash
uv run --project dashboard python -m vfdash --port 8787        # from the repo root; Ctrl-C stops it
ops/install_dashboard.sh                                        # run it at login and keep it running
ops/install_dashboard.sh --print-plist                          # show the job file it would write; changes nothing
ops/uninstall_dashboard.sh                                      # remove that
uv run --project dashboard pytest -q                            # the tests
```

`--root PATH` reads a copy of the repo instead of the checkout it lives in (for tests and rehearsals);
`--scorer-root PATH` says where the scorers and their Pythons are when `--root` is a copy; `--home PATH` stands
in for the home folder (launchd files, logs, the credit file).

Only one copy can listen on a port. A second one (say, the `dashboard` preview in `.claude/launch.json` while
the login job runs) prints one sentence saying the port is in use and stops; the install script checks the
port before it starts the job.

Times are shown in the Mac's own time zone, read from `/etc/localtime` (the zone launchd uses for the jobs'
schedules), not from a `TZ` setting: `TZ=... uv run ...` in a rehearsal doesn't change the times shown.

## Screens

Home (`#home`), Signals (`#signals`, with `?sport=nfl|cfb&rule=<rule id>&result=won|lost|push|pending|void`),
Board (`#board`, with `?sport=nfl|cfb&signals=1`), a game (`#game/<id>`), Forward tests (`#tests`), Jobs and
records (`#jobs`, and `#jobs/records` for `ops/RUN_RECORDS.md`), Thursday's pull (`#pull`) and Research
(`#research`). Data refreshes every 60 seconds; the server re-reads the files at most every 30 seconds (and works
out the board's rows at most once a minute from each read) and runs each scorer preview at most every 10 minutes.

To add a screen: one entry in `SCREENS` in `vfdash/static/app.js` (its address, its `/api/...` answer and the
function that draws it), one link in the navigation in `vfdash/static/index.html`, one route in `vfdash/server.py`
and one builder in `vfdash/api.py`. A chart is drawn with `timeChart` in `app.js` (inline SVG, nothing loaded):
reference lines (`refs`), a smallest span for the axis (`minSpan`) and, for a win-rate chart, `floorAtMost: 40` so
its axis starts at 40% or lower, with break-even (52.4% at −110) passed as a reference line.

## Signals: one colour, badges, and the log

One colour is kept for signals and used for nothing else (violet, `--signal` in `app.css`): a filled **Signal**
badge (a rule fired at its registered price), the same colour outlined for **Signal, backup price** (the NFL wind
rule at the consensus line when Pinnacle had no quote; logged apart, not part of the decision), and a tinted row for
a game whose newest row is a signal (on the Signals screen, the row of the rule that signals on that newest row: a
model lean's row is never tinted). A **watch** gets a quiet outlined badge in the neutral colour: the NFL model
lean, and a wind trigger that didn't become a signal (no price, a price too high, a value not above zero, or outside
the 1 to 3 day window; the alert job sends a watch for each). Green, amber and red stay for job health and deadlines.
Every badge carries its word. The rules are `badge` and `strongest` in `vfdash/words.py`.

Home opens with the live signals, one row each (the badge, the game, the kickoff, the rule, the number and price to
take, a better number if a book logged one, and how long until kickoff), above the four numbers; with none it says
"No signal is live." and when the next run is. The browser tab shows the count, "(1) Value Finder", on every screen.
The Board lists "Signals" and then "Everything else", each with its count, under a legend.

The Signals screen lists every bet the scorers count, newest first, from each scorer's `--json` document (the same
preview, kept 10 minutes, whose "text" is the report on the Forward tests screen): the kickoff, the game, the rule,
the entry (number, price, book and when it was logged), the close and where it came from, the closing-line value,
the final total, the result and the units. A row opens the game's page. Above it, for each rule and for the signal
rules together (the model lean, a watch, is totalled on its own): the record, the units, the return per bet placed,
the mean closing-line value with the registered interval, and the count toward the decision, each with its sample
size, whether it clears the multiple-testing bar (read from STATUS.md's "Variants" bullet), and "Paper bets. No
money was placed." The per-rule numbers are the scorer's own; the totals for rules together, the p-values and the
charts are worked out in `vfdash/signals.py` from the scorer's bets: the win rate's one-sided p is exact, each bet
winning with the break-even chance of its own price (the test the college football scorer registers for Rule HT);
the closing-line value's is the larger of the plain t-test's and the one grouped by game day (the two the registered
interval is the wider of). Two charts, cumulative units by date and closing-line value per bet with its running
mean, say what they found in their titles ("not distinguishable from break-even" when it isn't), draw break-even or
zero as a line, and never span less than 4 units or points, so a small difference never fills the chart; with fewer
than 2 settled bets each is a sentence instead. The totals and charts ignore the result filter.

Before the first signal the screen says which rule starts when, worked out from `content/forward_tests.json` (the
date in each test's `starts_text`, else its `starts_utc` in Eastern time). If a scorer fails, takes more than 60
seconds or prints something that is not its document (not one JSON object with its report as "text" and its tests,
each with an id, counts and bets; or more than 20 MB), the screen says so and lists, from the ledgers, the games whose
rows include a signal since their rule started, without results.

## What it reads, and the only programs it starts

Reads: `{nfl,cfb}-weather/data/forward/` `ledger.csv`, `runs.csv`, `closes.csv`, `alert_state.json`,
`alerts.log` (its last 500 KB), `decisions.csv`, `fills.csv`; `STATUS.md`; `ops/RUN_RECORDS.md`;
`sharp-markets/data/raw/_manifest/oddsapi_manifest.csv`; `dashboard/content/*.json`;
`~/.cache/value-finder/odds_quota.json` (only its time and balance fields, never the key's fingerprint);
the schedule keys of the four jobs' files in `~/Library/LaunchAgents/`; the last line of
`~/Library/Logs/valuefinder-closecapture.log` and `valuefinder-ledgersync.log`. It never opens a `.env` file.

Starts (from fixed lists in `vfdash/commands.py`, never with a shell): each project's
`scripts/score_forward.py --ledger <root>/<project>/data/forward/ledger.csv --now <UTC time> --json` with that
project's `.venv/bin/python` in the project folder (a preview, which never records a decision; `--json` makes it
print its report and its graded bets as one JSON document, and changes nothing else);
`/bin/launchctl list`; `/bin/launchctl print gui/<uid>/<label>` for the four jobs.

What a scorer preview does besides printing: importing its package (`nflweather/config.py`,
`cfbweather/config.py`) creates the project's `data/raw`, `data/processed`, `output/tables` and a few more
folders when they are missing; and when the project's `data/forward/decisions.csv` is missing, the scorer reads
its nightly copy with `git show` (read-only). In the live checkout every one of those folders exists, so a
preview changes nothing. The dashboard checks them first (`SCORER_FOLDERS` in `vfdash/commands.py`, which a
test compares with both `config.py` files) and, if any is missing, does not start the scorer and says why.

Anything that looks like a key is blanked before it is shown: the jobs' logs, a run's error, the alert log and
a scorer's output use the same patterns as the jobs' own `runlog.scrub` (a test keeps the two the same), and
whatever follows `ODDS_API_KEY`, `CFBD_API_KEY`, `KAGGLE_KEY` or `NTFY_TOPIC` is blanked too.

## The menu-bar light's contract

`GET /api/summary` returns exactly `generated_utc`, `health` (`ok`, `warn`, `fail`), `signals_live`,
`games_on_board`, `next_run_local` (`HH:MM`), `credits_remaining` (integer or null) and `problems` (plain
sentences). The rules are at the top of `vfdash/health.py`. "More than 5 hours" counts only the hours between
7:30 AM and 11:30 PM local, so a quiet night never turns the light amber or red.

`games_on_board`, `signals_live`, the Home screen's numbers and the Board are all worked out from one set of
games (`board_set` in `vfdash/api.py`), so the light and the board never disagree: every game in each sport's
latest run that hasn't kicked off, plus every game whose newest row has no kickoff time set, whose date (Eastern)
hasn't ended, and which the latest run no longer lists (see below). A game with a time set that the latest run
doesn't list is in neither, whatever its older rows say. The set is worked out once per read of the files and
minute, so the light and every screen asked in the same minute get the same games.

`signals_live` counts Rule B at either price and Rule HT on those games, as the alert jobs count signals in
`runs.csv`. The NFL model lean is logged as a watch, not a signal, so it is not in `signals_live`; the Home
screen shows the number of leans on the board beside it ("Model leans, which are watches, not signals: 3").
Counting leans as signals is a one-line change (`is_signal` in `vfdash/words.py`) if the hub decides they
should be.

A ledger is read by its column names. One without `snapshot_utc`, `game_id` or its kickoff columns
(`gameday` and `gametime`; for college football `start_utc` or `kick_et`), and a `runs.csv` without `run_utc`
and `status`, can't be read: the light turns amber and says which column is missing. Each row's logging time
is read as a time; the latest run is the latest time that can be read, and a row whose time can't be read is
left out and counted in a note. A row logged more than 5 minutes later than now (a clock set ahead when it was
written) is left out until its time comes, so it never becomes the latest run; it is counted and named in the
notes, and the light turns amber.

A game whose kickoff time isn't set yet (the college job logs it with cfbfastR's placeholder, midnight Eastern
at the start of the game's date, and with `wx_src` `time_tbd` at an outdoor venue; or an NFL row with no
`gametime`) is shown as "Time not set" with its date. It stays on the board, in `games_on_board` and, if one of
its rules signals, in `signals_live` until its date has passed in Eastern time. The college job logs only games
whose kickoff is after now, so its first run after the placeholder midnight (7:30 AM Pacific on game day) no
longer lists such a game, hours before it is played; the board then shows the game's last logged row with "Time
not set. Last logged Fri Oct 9, 7:30 PM." Rule B can't signal on such a game (it has no forecast), but Rule HT is
priced without one, so the college job can log a Rule HT signal on it.

## What the board shows beside a game

"Wind rule's value" is Rule B's expected value for the under (`ev_under`), from the rule's registered pricing
model (the frozen cohort of outdoor games with 15+ mph wind). The jobs log it on nearly every priced row, but the
Board and Game screens show it only on a Rule B signal (`SIGNAL`, `SIGNAL_SECONDARY`) and on a `negative_ev` row,
where the value, not above zero, is what says why there is no signal. On every other row, including those where
the wind trigger was met but the game is outside the 1 to 3 day window, the price is too high or there is no
price, a positive value would read as a priced edge on a game that is not a signal, so a dash is shown and the
Rules column says why. The value at the best number (`ev_best_line`) is shown on a signal only: on a `negative_ev`
row it can be above zero at another book. "Lean model's chance of the under" (`p_under`) is the NFL lean model's,
a different model, in its own column and only for outdoor NFL games with a forecast (`wx_src` `era5`, the lean
rule's own gate); where the lean model isn't run the Rules column says why ("Not an outdoor game", "Open roof, not
counted", "No forecast yet") rather than "No lean".

The line under the board says whether Rule B clears the project's multiple-testing bar, read from the evidence
list every time (its Rule B results are the entries with `rule-b` in their id), and that neither number is a
proven edge.

## Connections

A request must arrive in full within 15 seconds: a connection that sends part of one and waits, or drips it a
byte at a time, is closed. At start-up the dashboard raises its own limit on open files from launchd's 256 to
4,096, so a pile of connections can't stop it answering. A link inside `vfdash/static` is never followed or
served, and a data file that is a link to a `.env` file is not opened (the screen says so).
