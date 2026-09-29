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

Home (`#home`), Board (`#board`, with `?sport=nfl|cfb&signals=1`), a game (`#game/<id>`), Forward tests
(`#tests`), Jobs and records (`#jobs`, and `#jobs/records` for `ops/RUN_RECORDS.md`), Thursday's pull (`#pull`)
and Research (`#research`). Data refreshes every 60 seconds; the server re-reads the files at most every 30
seconds (and works out the board's rows at most once a minute from each read) and runs each scorer preview at
most every 10 minutes.

## What it reads, and the only programs it starts

Reads: `{nfl,cfb}-weather/data/forward/` `ledger.csv`, `runs.csv`, `closes.csv`, `alert_state.json`,
`alerts.log` (its last 500 KB), `decisions.csv`, `fills.csv`; `STATUS.md`; `ops/RUN_RECORDS.md`;
`sharp-markets/data/raw/_manifest/oddsapi_manifest.csv`; `dashboard/content/*.json`;
`~/.cache/value-finder/odds_quota.json` (only its time and balance fields, never the key's fingerprint);
the schedule keys of the four jobs' files in `~/Library/LaunchAgents/`; the last line of
`~/Library/Logs/valuefinder-closecapture.log` and `valuefinder-ledgersync.log`. It never opens a `.env` file.

Starts (from fixed lists in `vfdash/commands.py`, never with a shell): each project's
`scripts/score_forward.py --ledger <root>/<project>/data/forward/ledger.csv --now <UTC time>` with that
project's `.venv/bin/python` in the project folder (a preview, which never records a decision);
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

`signals_live` counts Rule B at either price and Rule HT, as the alert jobs count signals in `runs.csv`. The
NFL model lean is logged as a watch, not a signal, so it is not in `signals_live`; the Home screen shows the
number of live leans beside it ("Model leans, which are watches, not signals: 3"). Counting leans as signals
is a one-line change (`is_signal` in `vfdash/words.py`) if the hub decides they should be.

A ledger is read by its column names. One without `snapshot_utc`, `game_id` or its kickoff columns
(`gameday` and `gametime`; for college football `start_utc` or `kick_et`), and a `runs.csv` without `run_utc`
and `status`, can't be read: the light turns amber and says which column is missing. Each row's logging time
is read as a time; the latest run is the latest time that can be read, and a row whose time can't be read is
left out and counted in a note.
