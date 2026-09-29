# Dashboard: a local, read-only view on the Mac

One page at <http://127.0.0.1:8787/> showing the forward tests, the board of upcoming games, the scheduled jobs,
Thursday's pull and the research, from the files the jobs write. Paper only: it places no bet, changes no file
the jobs own, and listens on 127.0.0.1 only. Python standard library only; nothing is loaded from the internet.

```bash
uv run --project dashboard python -m vfdash --port 8787        # from the repo root; Ctrl-C stops it
ops/install_dashboard.sh                                        # run it at login and keep it running
ops/uninstall_dashboard.sh                                      # remove that
uv run --project dashboard pytest -q                            # the tests
```

`--root PATH` reads a copy of the repo instead of the checkout it lives in (for tests and rehearsals);
`--scorer-root PATH` says where the scorers and their Pythons are when `--root` is a copy; `--home PATH` stands
in for the home folder (launchd files, logs, the credit file).

## Screens

Home (`#home`), Board (`#board`, with `?sport=nfl|cfb&signals=1`), a game (`#game/<id>`), Forward tests
(`#tests`), Jobs and records (`#jobs`, and `#jobs/records` for `ops/RUN_RECORDS.md`), Thursday's pull (`#pull`)
and Research (`#research`). Data refreshes every 60 seconds; the server re-reads the files at most every 30
seconds and runs each scorer preview at most every 10 minutes.

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

## The menu-bar light's contract

`GET /api/summary` returns exactly `generated_utc`, `health` (`ok`, `warn`, `fail`), `signals_live`,
`games_on_board`, `next_run_local` (`HH:MM`), `credits_remaining` (integer or null) and `problems` (plain
sentences). The rules are at the top of `vfdash/health.py`. "Signals" are Rule B at either price and Rule HT,
as in `runs.csv`; the NFL model lean is a watch and doesn't count. "More than 5 hours" counts only the hours
between 7:30 AM and 11:30 PM local, so a quiet night never turns the light amber or red.
