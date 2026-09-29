# Run records: what the alert jobs leave behind

The NFL and CFB alert jobs run four times a day on the Mac (7:30 AM, 11:30 AM, 3:30 PM and 7:30 PM). Each project keeps
its records in its own `data/forward/` folder (`nfl-weather/data/forward/`, `cfb-weather/data/forward/`).
Every night at 23:45 `ops/sync_ledgers.sh` copies the ledger, `runs.csv`, `alerts.log`, `closes.csv` and
`fills.csv` to the `ledgers` branch on GitHub, so there is a dated copy outside the Mac.

## The four files

| File | What it is |
|---|---|
| `runs.csv` | One row per alert run, whether it finished or failed. It says when the run happened, whether it was `ok` or `failed`, how many games were on the board, how many signals there were, and how many games had a price. If a run failed, it says where and why. |
| `alerts.log` | Everything the job printed: each alert it sent, "nothing new", and for a failed run one line starting `run failed`. Keys are blanked (`apiKey=***`) before anything is printed or recorded, because this file goes to GitHub. |
| `alert_state.json` | The job's memory of which alerts it has already sent for each game, so you never get the same alert twice. For the NFL it also remembers each game's last wind forecast and total, which is how it spots a LINE LAG. It is saved again right after each alert goes out. |
| `ledger.before-v3-2026-09-28.csv` (NFL), `ledger.before-cfb-v3-2026-09-28.csv` (CFB) | The ledger as it stood before the one-time rewrite that added the new columns (Sep 28–29). It never changes again. Keep it: it shows that no old row was altered. |

The ledger itself (`ledger.csv`) is the forward test. Never edit it or its backup by hand.

## Reading `runs.csv`

| Column | Meaning |
|---|---|
| `run_utc` | When the run finished, in UTC (7 hours ahead of Pacific time in summer, 8 in winter). |
| `status` | `ok` or `failed`. |
| `games`, `signals` | Games on the board, and how many were a signal (NFL: Rule B at either price; CFB: Rule B plus Rule HT). |
| `priced` | Games with any posted total. |
| `rule_priced` | Games priced at the rule's own book: Pinnacle for the NFL; Pinnacle or DraftKings through The Odds API for CFB. Added Sep 29, 2026, so older rows leave it blank. |
| `unmapped` | Team names in the odds feed that matched no scheduled game (those games arrive with no price). |
| `error` | Why a failed run failed. On an `ok` run it is usually empty (see the note below). |

**Check `rule_priced` against `priced`.** If `rule_priced` is 0 while `priced` is not, the odds service was
down or out of credits, and every game was priced at the backup instead (for the NFL, the consensus
line; for CFB, ESPN). An NFL Rule B signal at a backup price is a "secondary price" signal: it is logged,
but it is not part of the registered test. One such run is nothing to worry about. Several in a row, tell
the hub.

**An `ok` run with text in `error`.** That happens only when `alert_state.json` was damaged and couldn't be
read. The run still saved its ledger row and sent its alerts, so it counts as `ok`. The damaged file is
kept beside the new one as `alert_state.corrupt-<time>.json`, and the job started over from an empty memory.
Expect some alerts you have already had to arrive once more. Tell the hub, so it can find out what damaged
the file.

## What a `failed` row means

A run is `failed` when it could not finish one of its steps, or when an alert could not be built or sent.
The `error` column starts with the step:

| Step in the error | Was the ledger row saved? | What happened |
|---|---|---|
| `while building the board` | No | A download failed (the schedule, the forecasts or the odds). Usually the internet or a data site was briefly down. |
| `while saving the ledger` | No | The file couldn't be written, most often because the disk is full. |
| `while reading the alert state` | Yes | `alert_state.json` couldn't be opened at all. The job leaves it untouched and sends no alerts. |
| `while building the alerts` | Yes | One game's alert text failed. The other games' alerts still went out. That game keeps its last wind and total, so a LINE LAG isn't lost. |
| `while sending the alerts` | Yes | The notification service couldn't be reached. Every alert sent before that was saved as sent. The rest go out on the next run, and none is sent twice. |
| `while saving the alert state` | Yes | Every alert went out, but the job couldn't record which (usually a full disk). Some may arrive again on the next run. |

## When you get a "run failed" notice

1. Nothing is ever bet automatically, so no money is at stake. The notice names the step and the reason.
2. If the step is `building the board` and it happens once, do nothing: the next scheduled run usually
   works. If two runs in a row fail, or a signal is close to kickoff, tell the hub.
3. For any other step, tell the hub. It reads `runs.csv` and the last lines of `alerts.log`, and fixes it.
4. If you need to know right away what the job would send, the hub (or you, from the project folder) can run
   `.venv/bin/python scripts/alerts.py --dry-run`. A dry run prints the alerts, sends nothing, adds no ledger
   row and spends no odds credits.
5. Don't delete `alert_state.json` to "reset" things. Every alert you have already had would be sent again,
   and the NFL job would lose the wind history it needs for LINE LAG.
