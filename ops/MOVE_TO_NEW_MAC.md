# Moving Value Finder to the Mac Studio

This page moves the scheduled jobs and the data from the laptop (the MacBook Air) to the Mac Studio. Follow it with the two Macs side by side.

- Every command goes into Terminal (Applications > Utilities > Terminal). Paste it, press Return, and compare what you see with the words under it.
- Each box holds one command. `~` means your home folder.
- Each step says which Mac it's on: **On the laptop** or **On the Mac Studio**.
- Nothing here places a bet or changes a rule. The dry runs and the test notification spend no Odds API credit.

## 1. The one rule

**At every moment, exactly one Mac has the jobs loaded.**

| Job | What it does | When (Mac time) |
|---|---|---|
| `com.nflweather.alerts` | NFL weather alerts; writes the NFL ledger and `runs.csv` | 7:30, 11:30, 15:30, 19:30 |
| `com.cfbweather.alerts` | The same for college football | 7:30, 11:30, 15:30, 19:30 |
| `com.valuefinder.closecapture` | Records the closing total 2–20 minutes before each kickoff | every 15 minutes |
| `com.valuefinder.ledgersync` | Copies the ledgers to the `ledgers` branch on GitHub | 23:45 |

The three paid-plan live uses in [`LIVE_USES.md`](LIVE_USES.md) follow the same rule once they are installed, because they spend credits too. The dashboard is allowed on both Macs: it only reads.

If both Macs ran the jobs, every alert would come twice and every credit would be spent twice. The two ledgers would drift apart, and both Macs would push to the `ledgers` branch each night. The forward tests are registered, and a ledger written by two machines can't be trusted afterwards.

Migration Assistant copies the job files along with everything else, and they start at the new Mac's first login. That's why route A below starts by keeping them off the new Mac.

**How to see which Mac runs the jobs.** Run this on either Mac:

```
launchctl list | grep -E 'com\.(nflweather|cfbweather|valuefinder)\.'
```

The Mac that runs them shows four lines (seven once the live uses are installed, plus one for the dashboard if you install it). The other Mac shows nothing, or only the dashboard's line.

**The check does the same and more.** On the Mac that runs the jobs:

```
~/code/value-finder/ops/mac_check.sh --role live
```

On the other Mac:

```
~/code/value-finder/ops/mac_check.sh --role standby
```

Each line starts OK, WARN or FAIL, and the last line counts them. The check changes nothing. On a standby Mac, any job that's loaded is a FAIL that says *"This Mac is not the live one, and it is running the jobs. Unload them now:"*, followed by the exact commands. Run them straight away.

The hub runs the same check at every check-in, and only reports what it finds. It never installs or removes a job itself: the commands are yours to run.

## 2. What moves, and what doesn't

The sizes are what the check measured on the laptop on September 29.

| What | Where on the laptop | Size | How it reaches the Mac Studio |
|---|---|---|---|
| The code | `~/code/value-finder` | small | Cloned from GitHub (route B), or copied by Migration Assistant (route A). Both Macs are brought to the same version from GitHub before the handover |
| The keys | `nfl-weather/.env`, `cfb-weather/.env`, `sharp-markets/.env`, `~/.kaggle/access_token` | under 1 KB | You copy them with `rsync` (section 5). Never by AirDrop, iCloud Drive, Dropbox, Google Drive or email |
| NFL data, with the NFL forward-test records | `nfl-weather/data` | 553 MB | Copied, except the files that come with the code (below) |
| College football data, with its records | `cfb-weather/data` | 1.6 GB | Copied, except the files that come with the code |
| Kalshi data, `markets.duckdb`, and after Thursday the paid odds data | `sharp-markets/data` | 101 MB (about 3 GB more after Thursday's download) | Copied. **Not a cache:** the paid data can't be had again without paying, so the check lists every paid file and the compare step fails if one is missing or cut short |
| The forecast archive and the Odds API credit file | `~/.cache/value-finder` | 1.9 GB | Copied |
| The forward-test records | each weather project's `data/forward/` (ledger, `runs.csv`, `alert_state.json`, the saved forecasts, later `decisions.csv`), plus the saved odds responses in `data/raw/oddsapi/live/` | small (46 and 176 files) | Inside the data folders above. The check fingerprints (hashes) every one, and the compare step proves each arrived byte for byte |
| The analysis datasets | each weather project's `data/processed/`, and `nfl-weather/data/raw/odds/sbr_open_close.parquet` | about 8 MB | **Come with the code from GitHub, never copied.** The copy commands leave them out, so an older copy can't overwrite a newer committed file |
| The Python environments | a `.venv` folder in `nfl-weather`, `cfb-weather`, `sharp-markets` and `dashboard` | about 1.5 GB | **Rebuilt, never copied.** An environment holds the paths of the Mac that built it, so a copied one can break in quiet ways |
| The job files | four files in `~/Library/LaunchAgents` | tiny | **Installed fresh** with the installers, never copied |
| The nightly sync's own clone | `~/code/.value-finder-ledgers` | 7 MB | Not needed: the first nightly sync on the Mac Studio makes a new one |
| Local extras that hold no key | the thesis PDF, `sharp-markets/reference/` (13 MB), `.claude/settings.local.json`, `~/Library/Logs/valuefinder-*.log` | small | Optional. AirDrop is fine for these |
| The Claude app's chats and memory | see section 8 | | See section 8 |
| Worker chats' folders | `~/code/value-finder/.claude/worktrees` | | Not copied in route B. A worker's finished work lives in its pull request |

About 4.2 GB in all, before Thursday's download.

## 3. When

**The hub's advice:** Thursday, October 1 runs on the laptop, exactly as rehearsed, unless the laptop can't do it. Set up the Mac Studio beside it (section 4), with no jobs on it. Move the jobs and the data in a quiet hour afterwards, with section 6.

**Why.** Thursday has three firsts:

- You buy a month of paid odds data, and a long download runs. It was rehearsed on the laptop.
- A registered backtest runs on that data.
- At 5:00 PM Pacific, the first college football game that counts toward a registered forward test kicks off.

A move adds new things at once: new environments, new paths, keys in new files, new notification permissions. Doing that on the one day when a mistake costs the most (bought credits, a registered kickoff that can't be replayed) adds risk for no gain. The laptop can do Thursday. Day one needs about 3 GB of disk, and the laptop had 79.7 GB free on September 29. It must stay open and plugged in, because it sleeps with the lid closed.

**Quiet hours.** Start the handover only when:

- no job is due by the clock within 90 minutes (the alert runs at 7:30, 11:30, 15:30 and 19:30, and the nightly ledger copy at 23:45), and the last run has finished;
- no game kicks off within 3 hours, because close capture needs a running job at every kickoff;
- no long download (the paid pull) is running on the laptop.

The handover takes about 30 to 60 minutes. While it runs, no Mac has the jobs. **A run that falls due in that time does not happen.** Nothing runs it later: `runs.csv` simply has no row for it. That is why you start with 90 minutes clear.

The best window is a weekday morning. Start between 7:40 (after the 7:30 run has finished) and 10:00, so that you finish well before 11:30. Weekday college games start in the afternoon Pacific at the earliest, and the NFL has no weekday-morning games. For example, Friday, October 2 (if the download is done) or Monday, October 5. Avoid Saturdays and Sundays: games start from 6:30 AM Pacific (NFL games in London) and run all day.

**How to see the next run and the next kickoffs:**

- The check, on the laptop, whose ledgers are the current ones. Its "Clock and power" part has a line like *"Next alert run 11:30 (in 3 h 50 min). Next kickoff in the ledgers Fri Oct 2, 4:00 PM, College: Pittsburgh at Virginia Tech (in 8 h 20 min). A quiet time to move the jobs"*. Anything else (*"Not a quiet time…"*, or *"Not known to be a quiet time…"* when the ledgers show no game ahead) means wait, or look the games up yourself.
- The dashboard, if it's running: the Board screen, <http://127.0.0.1:8787/#board>, lists the upcoming games with their kickoff times in Mac time. To start it by hand (Control-C stops it):

  ```
  uv run --project ~/code/value-finder/dashboard python -m vfdash --port 8787
  ```
- The ledger itself. In Finder, select `~/code/value-finder/cfb-weather/data/forward/ledger.csv` and press the space bar. Quick Look shows it without changing it. Never open a ledger in Numbers or Excel: saving can change it. The `kick_et` column is Eastern time (3 hours ahead of Pacific). For the NFL, `gameday` and `gametime` are Eastern too. Look at the rows with the latest `snapshot_utc`.

**If you decide to move before Thursday.** Then these things change:

- The only long quiet window is Wednesday evening, after the 19:30 run has finished, until Thursday 6:00 AM. The handover must be finished, and the Mac Studio's jobs installed, before the 7:30 run on Thursday. The nightly ledger copy at 23:45 falls inside that window: if the jobs are not on either Mac then, that night's copy doesn't happen, and the next night's copy includes everything.
- The paid key goes into the Mac Studio's three `.env` files, not the laptop's. The download and the backtest run on the Mac Studio. Before buying, redo the free "Before buying" steps of [`ODDS5M_DAY_ONE.md`](../sharp-markets/docs/ODDS5M_DAY_ONE.md) there: `git pull`, `uv run pytest`, the probe without `--confirm`, and the plan.
- The hub runs the day-one checklist "on the Mac". Today the hub chat lives in the Claude app on the laptop and works in the laptop's folder, so it would need to move too (section 8). The other choice is to type the day-one commands yourself on the Mac Studio.
- Keep the laptop ready to take the jobs back (section 7) until Thursday's 5:00 PM kickoff has its close recorded.

## 4. Set up the Mac Studio, with no jobs on it

Pick a route. Both end with the same Mac Studio: the repo at `~/code/value-finder`, new environments, the tools, and no jobs.

- **Route B (clean setup) is the one I'd use for Value Finder.** The laptop keeps running everything while you set up. No job file is ever copied. Only about 4 GB moves.
- **Route A (Migration Assistant)** is for when you want your whole laptop on the Mac Studio: apps, documents, settings. It needs care with the job files.

**On the Mac Studio, whichever route:**

- Use the same account name as on the laptop, `maxzipperman`. Then every path (`/Users/maxzipperman/...`) is the same on both Macs, and so is the Claude memory folder's name.
- Let Setup Assistant set the time zone from your location. The check fails on any zone but America/Los_Angeles.
- Before the handover, set it never to sleep (section 8, first point). From the moment it runs the jobs, a sleeping Mac misses runs and closes.

### Route A: Migration Assistant

**Why the first step is on the laptop.** A job file that arrives on the Mac Studio starts at its first login, before you can type anything; close capture even runs the moment it loads. Unloading the jobs on the Mac Studio afterwards is too late to be sure. So the reliable guard is that no job file arrives at all: you take the four files off the laptop just before the copy is made, and put them back only when no later copy can be taken. The network kept off at the first login, and the check as the first thing you run, are the second and third guards.

What I could not test: Migration Assistant itself; Time Machine's settings; whether Setup Assistant lets you transfer with no internet connection; whether the laptop's jobs keep running while it copies; and whether Homebrew (`uv`, `gh`) comes across. The steps are built so that none of that can start the jobs twice, and step 3 lets you see for yourself that it didn't.

1. **Before anything else, keep the job files out of the copy.** First choose where the copy comes from:
   - **(a) Straight from the laptop.** The laptop shows only Migration Assistant until the copy is done, so treat its jobs as stopped for that time. The whole laptop (about 380 GB) can take hours over Wi-Fi; a Thunderbolt cable between the Macs is faster. Do it in a long quiet window with no download running and no kickoff (section 3). Wednesday evening after the 19:30 run is one; the laptop must be running its jobs again (step 4) before 7:30 AM Thursday.
   - **(b) From a Time Machine backup of the laptop.** The laptop keeps working. This needs a Time Machine drive. **First, on the laptop,** open System Settings > General > Time Machine > Options, and set "Back up frequency" to **Manually**. Otherwise a later automatic backup, made after the jobs are back, would hold the job files again, and Setup Assistant might offer that one.

   Then, **on the laptop,** in a quiet hour (section 3):

   Run the check, and look at its "Jobs" part:

   ```
   ~/code/value-finder/ops/mac_check.sh --role live
   ```

   If it lists paid-plan live uses, write down the command it prints under *"To put back exactly these…"*. It puts back the same jobs with the same settings later.

   Wait until no job is running. In this list, the first column must show `-` for every line:

   ```
   launchctl list | grep -E 'com\.(nflweather|cfbweather|valuefinder)\.'
   ```

   Then remove the four jobs. Each command unloads a job and deletes its job file. The installers write the files again later, so nothing is lost.

   ```
   ~/code/value-finder/nfl-weather/scripts/install_alerts.sh --remove
   ```
   ```
   ~/code/value-finder/cfb-weather/scripts/install_alerts.sh --remove
   ```
   ```
   ~/code/value-finder/ops/install_close_capture.sh --remove
   ```
   ```
   ~/code/value-finder/ops/install_ledger_sync.sh --remove
   ```

   Each one prints `removed com.…`. If you wrote down a live-uses command, remove those too:

   ```
   ~/code/value-finder/ops/install_live_uses.sh --remove
   ```

   Then check that none is left. Every job should show as `OK … not installed here`:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby
   ```

   - For (a): start Migration Assistant on the laptop right after this.
   - For (b): in the Time Machine menu, choose Back Up Now and wait until it finishes. Write down the date and time the backup finished (Time Machine settings show "Latest backup"). Then put the jobs back on the laptop at once (step 4).
2. **On the Mac Studio,** in a quiet hour, go through Setup Assistant and choose to transfer from a Mac (a), or from the Time Machine backup (b). For (b), if it lists more than one backup, choose the one whose date and time you wrote down. Transfer your user account. If you can, don't join Wi-Fi and leave the Ethernet cable out until step 3 is done, and use a Thunderbolt cable for (a). A job that did slip through then can't reach the internet: it can't send an alert or spend a credit. If Setup Assistant insists on a network, join Wi-Fi. Step 3 still catches any job.
3. **On the Mac Studio, the first thing after you log in,** open Terminal and run:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby
   ```

   In its "Jobs" part, every job should say `OK … not installed here, as it should be on a standby Mac`. If you see *"This Mac is not the live one…"*, run each command it prints under that line, then run the check again. The other parts will show WARN and FAIL lines (old environments, perhaps missing tools). Steps 5 to 7 fix them.
4. **On the laptop** (for (a), once the transfer has finished and you're logged in again; for (b), right after the backup), put the jobs back:

   ```
   ~/code/value-finder/nfl-weather/scripts/install_alerts.sh
   ```
   ```
   ~/code/value-finder/cfb-weather/scripts/install_alerts.sh
   ```
   ```
   ~/code/value-finder/ops/install_close_capture.sh
   ```
   ```
   ~/code/value-finder/ops/install_ledger_sync.sh
   ```

   Each prints `installed com.…`. If you removed live uses, run the command you wrote down in step 1, exactly as written. Then:

   ```
   ~/code/value-finder/ops/mac_check.sh --role live
   ```

   All four jobs should say `OK … loaded`. The laptop is running the jobs again, as rehearsed. For (b), leave Time Machine on Manually until the Mac Studio's step 3 check has passed; then set it back to how you want it.
5. **On the Mac Studio,** connect to the network. If the check said `uv`, `gh` or `git` is missing, do route B's steps 2 to 4. If `gh` isn't signed in, do route B's step 4.
6. **On the Mac Studio,** rebuild the environments ("Rebuild the environments" below). The copied ones hold the laptop's paths.
7. **On the Mac Studio,** run the check again with `--role standby`. The Mac Studio's data is the copy from the transfer day. The handover (section 6) brings the code up to date and copies the records fresh from the laptop anyway.

### Route B: a clean setup

1. **On the Mac Studio,** in Setup Assistant, choose not to transfer anything ("Not now"). Create the account `maxzipperman`. Join your network.
2. Install Homebrew. It also installs Apple's Command Line Tools, which include `git`. The command is the one on <https://brew.sh>:

   ```
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   It asks for your Mac password. When it finishes, it prints "Next steps" with two or three commands. Run those too.
3. Install `uv` and `gh`:

   ```
   brew install uv gh
   ```
4. Sign in to GitHub, then let `git` use that sign-in, because the nightly ledger copy pushes to GitHub:

   ```
   gh auth login
   ```

   Choose GitHub.com, HTTPS, "Yes" to authenticate Git, and "Login with a web browser".

   ```
   gh auth setup-git
   ```
5. Get the code:

   ```
   mkdir -p ~/code
   ```
   ```
   git clone https://github.com/maxzipperman/value-finder.git ~/code/value-finder
   ```
6. Rebuild the environments (below).
7. Copy the keys and a first copy of the data (section 5). The laptop keeps running its jobs meanwhile. This copy is a rehearsal, and the handover copies the records again.
8. Run the check:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby
   ```

   What you should see: no FAIL. Every job says "not installed here". The environments import their packages. The keys, the two cohort checks and the data folders say OK. Read any WARN; most are for later (a newer commit on GitHub, Swift, the Kaggle names).

### Rebuild the environments (both routes)

**On the Mac Studio.** Each project gets a new environment from its own files. Rerunning these is safe.

```
uv venv --clear --python 3.12 ~/code/value-finder/nfl-weather/.venv
```
```
uv pip install --python ~/code/value-finder/nfl-weather/.venv/bin/python -r ~/code/value-finder/nfl-weather/requirements.txt
```
```
uv venv --clear --python 3.12 ~/code/value-finder/cfb-weather/.venv
```
```
uv pip install --python ~/code/value-finder/cfb-weather/.venv/bin/python -r ~/code/value-finder/cfb-weather/requirements.txt
```
```
uv venv --clear --python 3.12 ~/code/value-finder/sharp-markets/.venv
```
```
uv sync --frozen --project ~/code/value-finder/sharp-markets
```
```
uv venv --clear --python 3.12 ~/code/value-finder/dashboard/.venv
```
```
uv sync --frozen --project ~/code/value-finder/dashboard
```

What you should see: `Creating virtual environment at: …` after each `uv venv`, and `Installed … packages` after each install. `uv` downloads Python 3.12 the first time if the Mac doesn't have it. In the check, the "Python environments" part should then show four OK lines, such as `OK nfl-weather: Python 3.12.11, imports nflweather`.

## 5. Copying the keys and data (for route B's first copy, and for the handover)

The copies run **on the Mac Studio** and pull from the laptop over your home network, with `rsync -a`. It keeps each file's time and permissions, and it copies a link as a link without following it. Rerunning it is safe: it sends only what changed. It never deletes anything on the receiving Mac.

The copy commands leave out two things on purpose: each weather project's `data/processed/` (and one file in `nfl-weather/data/raw/odds/`), which come with the code from GitHub, and files ending in `.tmp`, which are writes in progress that the jobs rename a moment later.

1. **On the laptop,** turn on Remote Login: System Settings > General > Sharing > Remote Login. Under "Allow access for", choose only your own account. The same pane shows the laptop's **local hostname** at the bottom; on September 29 it was `MacBook-Air-2.local`. You turn Remote Login off again at the end of the move.
2. **On the Mac Studio,** tell this Terminal window where the laptop is. Use your account name and the local hostname from step 1:

   ```
   LAPTOP=maxzipperman@MacBook-Air-2.local
   ```

   This lasts only for this Terminal window. In a new window, type it again. The commands below write it as `${LAPTOP}`, with the curly brackets: Terminal's shell (zsh) reads `$LAPTOP:` followed by a letter as something else, and the copy would go to the wrong place.
3. Copy the data. The first command asks whether to trust the laptop (type `yes`), and every command asks for the laptop's login password. Nothing shows while you type the password.

   **What you should see:** apart from those questions (and, the first time, a line saying the laptop was added to the list of known hosts), nothing at all. The prompt comes back when the copy is done. **If a command prints anything else, stop:** a line with the word `error`, or one starting `rsync` or `openrsync`, means that copy did not finish. Don't go on to the next step. Check the hostname in step 2 and that Remote Login is on, then run the same command again.

   ```
   rsync -a --exclude '/processed/' --exclude '/raw/odds/sbr_open_close.parquet' --exclude '*.tmp' "${LAPTOP}:code/value-finder/nfl-weather/data/" ~/code/value-finder/nfl-weather/data/
   ```
   ```
   rsync -a --exclude '/processed/' --exclude '*.tmp' "${LAPTOP}:code/value-finder/cfb-weather/data/" ~/code/value-finder/cfb-weather/data/
   ```
   ```
   rsync -a --exclude '*.tmp' "${LAPTOP}:code/value-finder/sharp-markets/data/" ~/code/value-finder/sharp-markets/data/
   ```
   ```
   mkdir -p ~/.cache
   ```
   ```
   rsync -a --exclude '*.tmp' "${LAPTOP}:.cache/value-finder/" ~/.cache/value-finder/
   ```
4. Copy the keys. Each file stays readable by you only (`rsync -a` keeps that). The same rule applies: anything printed besides the password question means stop.

   ```
   rsync -a "${LAPTOP}:code/value-finder/nfl-weather/.env" ~/code/value-finder/nfl-weather/.env
   ```
   ```
   rsync -a "${LAPTOP}:code/value-finder/cfb-weather/.env" ~/code/value-finder/cfb-weather/.env
   ```
   ```
   rsync -a "${LAPTOP}:code/value-finder/sharp-markets/.env" ~/code/value-finder/sharp-markets/.env
   ```
   ```
   mkdir -p ~/.kaggle
   ```
   ```
   rsync -a "${LAPTOP}:.kaggle/access_token" ~/.kaggle/access_token
   ```
5. Optional, route B only: the Claude memory folder (section 8) and the project's local Claude settings.

   ```
   mkdir -p ~/.claude/projects/-Users-maxzipperman-code-value-finder
   ```
   ```
   rsync -a "${LAPTOP}:.claude/projects/-Users-maxzipperman-code-value-finder/memory/" ~/.claude/projects/-Users-maxzipperman-code-value-finder/memory/
   ```
   ```
   rsync -a "${LAPTOP}:code/value-finder/.claude/settings.local.json" ~/code/value-finder/.claude/settings.local.json
   ```

**A key typed by hand** (the paid key on Thursday, say) goes on a line of its own, written exactly `NAME=value`: no `export` in front, no spaces around the `=` sign, nothing after the value. The weather projects read only lines of that form. The check says FAIL when a line isn't.

If you'd rather not turn on Remote Login, an external drive formatted APFS works too: copy with the same `rsync -a` options onto the drive on the laptop, then off it on the Mac Studio. Don't use a drive formatted exFAT, which loses the permissions. Delete the keys from the drive afterwards.

What I could not test: `rsync` between two Macs. I tested `rsync -a` with these options only on one Mac (macOS 26.3 ships openrsync). There it kept file times, kept a key file readable by the owner only, copied links as links, left out `processed/` and the `.tmp` files, made a missing folder, and a second run brought over only the changes. The commands' wording was run through zsh and bash with a stand-in for `rsync`, to check that each one names the laptop and the right folder. The check's compare step (section 6, step 8) is what proves each real copy.

## 6. The handover

Do this in a quiet hour (section 3), with about 90 minutes before the next run. Before you start: both Macs are on the same network, Remote Login is on at the laptop (section 5, step 1), and the Mac Studio is set up (section 4) with no FAIL in its standby check. The laptop stays the Mac that runs the jobs until step 5, and the Mac Studio takes over at step 11.

1. **On the laptop,** check the timing:

   ```
   ~/code/value-finder/ops/mac_check.sh --role live
   ```

   Its "Clock and power" part must say "A quiet time to move the jobs". If it says anything else, wait. In its "Jobs" part, if it lists paid-plan live uses, write down the command it prints under *"To put back exactly these…"*.
2. **Pause the hub.** In the hub chat, tell it: "I'm starting the move to the Mac Studio now." Then quit the Claude app on the laptop, and on the Mac Studio if it's open there (Claude menu > Quit Claude). Its daily check-in at about 9 AM must not run while no Mac has the jobs: until the move is done, it would see a Mac without jobs. You open the app again at step 14.
3. **On the laptop,** wait until the last run has finished. In this list, the first column must show `-` (not running) for every job:

   ```
   launchctl list | grep -E 'com\.(nflweather|cfbweather|valuefinder)\.'
   ```

   Also check that the last line of each `runs.csv` is the latest run. Its time is in UTC, 7 hours ahead of Pacific in summer (7:30 AM Pacific is `14:30Z`), and it should say `ok`:

   ```
   tail -n 1 ~/code/value-finder/nfl-weather/data/forward/runs.csv
   ```
   ```
   tail -n 1 ~/code/value-finder/cfb-weather/data/forward/runs.csv
   ```
4. **Bring both Macs to the same version of the code from GitHub.** On the laptop:

   ```
   git -C ~/code/value-finder pull --ff-only
   ```

   Then the same on the Mac Studio. What you should see on each: `Already up to date.`, or `Updating …` and `Fast-forward` with a list of files. If either prints a line starting `fatal` or `error`, stop: nothing has changed yet, and the laptop still runs the jobs. Open the Claude app again and tell the hub.

   Then, on each Mac, show the version:

   ```
   git -C ~/code/value-finder rev-parse --short HEAD
   ```

   Both Macs must show the same seven characters. If they don't, a change reached GitHub in between: run the `pull` command on both Macs again.
5. **On the laptop,** remove the jobs:

   ```
   ~/code/value-finder/nfl-weather/scripts/install_alerts.sh --remove
   ```
   ```
   ~/code/value-finder/cfb-weather/scripts/install_alerts.sh --remove
   ```
   ```
   ~/code/value-finder/ops/install_close_capture.sh --remove
   ```
   ```
   ~/code/value-finder/ops/install_ledger_sync.sh --remove
   ```

   If you wrote down a live-uses command in step 1, remove those too:

   ```
   ~/code/value-finder/ops/install_live_uses.sh --remove
   ```

   **From now until step 11, no Mac runs the jobs.** A run that falls due in that time does not happen and is never made up. Note the time now.
6. **On the laptop,** check that no job is left, and write the manifest: a file of counts and fingerprints of the data and every record, with no key and no file content in it.

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby --manifest ~/laptop.manifest
   ```

   What you should see: every job `OK … not installed here`, and at the end `OK Written to ~/laptop.manifest: … records, … paid files and 4 folders`.
7. **On the Mac Studio,** copy the data and the keys again (section 5, steps 2 to 4, with the same "anything printed means stop" rule). Only the changes travel, so it's quick. Then fetch the manifest:

   ```
   rsync -a "${LAPTOP}:laptop.manifest" ~/laptop.manifest
   ```
8. **On the Mac Studio,** compare:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby --compare ~/laptop.manifest
   ```

   What you must see: **no FAIL line anywhere**, and, under "Compared with the other Mac's manifest", the line `OK   Records: all N forward-test records are here, the same byte for byte as on the other Mac` (N is a number: it was 235 on the laptop on September 29, and grows with every run). Don't go on without both.
   - A FAIL starting "Record" means a forward-test record differs, is missing or is extra. Copy again (step 7) and compare again. If it still fails, stop and go back to the laptop (section 7). The laptop's copy is untouched.
   - A FAIL saying "The repo is at another commit" means a change reached GitHub between the two pulls. Do step 4 again on both Macs, then step 6 on the laptop, the last command of step 7, and compare again.
   - A FAIL starting "Not clean" means files that come with the code were changed on the Mac Studio. Stop and tell the hub (open the Claude app for that); section 7 takes you back meanwhile.
   - A FAIL starting "Paid odds file" means the paid data didn't all arrive. Run the `sharp-markets/data` copy of section 5 again, and compare again.
   - A WARN "Folder differs" where this Mac has more files than the other is expected: leftovers from an earlier copy, since `rsync` never deletes. Any other WARN you don't understand: stop and ask the hub.
9. **On the Mac Studio,** run the four test suites:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby --tests
   ```

   What you should see: four lines like `OK nfl-weather tests: 322 passed (166 s)`. Each suite takes two or three minutes on the laptop. A FAIL here means stop and go back (section 7).
10. **On the Mac Studio,** do a dry run of each alert. It downloads the schedule and the forecasts, prints what it would send, and sends nothing. It spends no Odds API credit, because it uses the backup prices (NFL: the consensus line; college: ESPN), and it writes no ledger row, no run record and no alert state ([`RUN_RECORDS.md`](RUN_RECORDS.md)).

    ```
    cd ~/code/value-finder/nfl-weather
    ```
    ```
    .venv/bin/python scripts/alerts.py --dry-run
    ```
    ```
    cd ~/code/value-finder/cfb-weather
    ```
    ```
    .venv/bin/python scripts/alerts.py --dry-run
    ```

    What you should see: a line like `… checked 14 outdoor games, nothing new` (or `checked 60 FBS games`), or `ALERT` lines for alerts it would send. A line with `run failed` means stop and go back (section 7).
11. **On the Mac Studio,** install the jobs. This step has started as soon as the first of these commands has run, even if a later one fails; that matters in section 7.

    ```
    ~/code/value-finder/nfl-weather/scripts/install_alerts.sh
    ```
    ```
    ~/code/value-finder/cfb-weather/scripts/install_alerts.sh
    ```
    ```
    ~/code/value-finder/ops/install_close_capture.sh
    ```
    ```
    ~/code/value-finder/ops/install_ledger_sync.sh
    ```

    Each prints `installed com.…`. Close capture runs once right away. It spends a credit only if a kickoff is 2 to 20 minutes off, and in a quiet hour none is.

    If you removed live uses in step 5, run the command you wrote down in step 1, exactly as written.
12. **On the Mac Studio,** it is now the live Mac:

    ```
    ~/code/value-finder/ops/mac_check.sh --role live
    ```

    Every job should say `OK … loaded, idle`. Then send one test notification. You should get a Mac banner and a phone push. It spends no credit:

    ```
    cd ~/code/value-finder/nfl-weather
    ```
    ```
    .venv/bin/python scripts/alerts.py --test
    ```

    If the banner doesn't show, look in System Settings > Notifications for Script Editor and allow it. The phone push is the one that matters.
13. **On the laptop,** check that nothing is loaded:

    ```
    ~/code/value-finder/ops/mac_check.sh --role standby
    ```

    Every job should say `OK … not installed here`. Leave Remote Login on until step 15 is done: section 7 needs it.
14. **Tell the hub the move is done, before anything else.** Open the Claude app again and tell the hub: "The move is done. The Mac Studio has run the jobs since" and the time of step 11, and which scheduled run, if any, fell between step 5 and step 11. It records in `STATUS.md` which Mac runs the jobs, from which time, and updates `CLAUDE.md`. From then on its check-ins check each Mac in its right role.
15. **Watch the first real run on the Mac Studio.** After the next 7:30, 11:30, 15:30 or 19:30, run:

    ```
    tail -n 1 ~/code/value-finder/nfl-weather/data/forward/runs.csv
    ```
    ```
    tail -n 1 ~/code/value-finder/cfb-weather/data/forward/runs.csv
    ```

    Each shows a new line with that run's time (in UTC) and `ok`. The morning after, check that the nightly copy worked:

    ```
    tail -n 3 ~/Library/Logs/valuefinder-ledgersync.log
    ```

    It should end with `ledgers pushed` or `ledgers unchanged`. When all of this is right, turn off Remote Login on the laptop.
16. **Leave the laptop's copy of the data untouched for two weeks.** Don't delete it, and don't run the project's scripts there. It's the backup. After two weeks, the hub can say whether the laptop's copy can be archived.

## 7. If something goes wrong: going back to the laptop

**First, whatever went wrong and whenever, on the Mac Studio:** remove its jobs. These commands are safe even if nothing was installed there; each prints `removed com.…`.

```
~/code/value-finder/nfl-weather/scripts/install_alerts.sh --remove
```
```
~/code/value-finder/cfb-weather/scripts/install_alerts.sh --remove
```
```
~/code/value-finder/ops/install_close_capture.sh --remove
```
```
~/code/value-finder/ops/install_ledger_sync.sh --remove
```
```
~/code/value-finder/ops/install_live_uses.sh --remove
```

Then check it. Every job must say `OK … not installed here`. If it prints *"This Mac is not the live one…"*, run each command it prints, and check again:

```
~/code/value-finder/ops/mac_check.sh --role standby
```

**Then, if step 11 of the handover had not started** (no installer had run on the Mac Studio), nothing on the Mac Studio wrote a record: the dry runs write none. **On the laptop,** put the jobs back:

```
~/code/value-finder/nfl-weather/scripts/install_alerts.sh
```
```
~/code/value-finder/cfb-weather/scripts/install_alerts.sh
```
```
~/code/value-finder/ops/install_close_capture.sh
```
```
~/code/value-finder/ops/install_ledger_sync.sh
```

If you removed live uses, run the command you wrote down, exactly as written. Then:

```
~/code/value-finder/ops/mac_check.sh --role live
```

Every job should say `OK … loaded`. Open the Claude app, and tell the hub what went wrong and at what times the jobs stopped and started.

**If step 11 had started** (even one installer), the Mac Studio may have written records. They go back to the laptop, so the forward test stays one continuous record. Do it in a quiet hour if you can. If a run is due, go on anyway: a run missed during the switch simply doesn't happen (and a missed close is reported as missing), while two Macs running the jobs would spoil the record.

1. **On the Mac Studio** (its jobs already removed, above), write its manifest:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby --manifest ~/studio.manifest
   ```
2. **On the laptop,** keep a copy of the laptop's own records before anything is copied back:

   ```
   ditto ~/code/value-finder/nfl-weather/data/forward ~/value-finder-laptop-records/nfl-weather-forward
   ```
   ```
   ditto ~/code/value-finder/cfb-weather/data/forward ~/value-finder-laptop-records/cfb-weather-forward
   ```
3. **On the Mac Studio** (Remote Login still on at the laptop; type the `LAPTOP=…` line of section 5 again if this is a new Terminal window), copy back what the Mac Studio wrote: the two record folders, the saved odds responses, the credit file and the manifest. As in section 5, each command prints nothing but the password question when it works; anything else means stop.

   ```
   rsync -a --exclude '*.tmp' ~/code/value-finder/nfl-weather/data/forward/ "${LAPTOP}:code/value-finder/nfl-weather/data/forward/"
   ```
   ```
   rsync -a --exclude '*.tmp' ~/code/value-finder/cfb-weather/data/forward/ "${LAPTOP}:code/value-finder/cfb-weather/data/forward/"
   ```
   ```
   rsync -a --exclude '*.tmp' ~/code/value-finder/nfl-weather/data/raw/oddsapi/live/ "${LAPTOP}:code/value-finder/nfl-weather/data/raw/oddsapi/live/"
   ```
   ```
   rsync -a --exclude '*.tmp' ~/code/value-finder/cfb-weather/data/raw/oddsapi/live/ "${LAPTOP}:code/value-finder/cfb-weather/data/raw/oddsapi/live/"
   ```
   ```
   rsync -a ~/.cache/value-finder/odds_quota.json "${LAPTOP}:.cache/value-finder/odds_quota.json"
   ```
   ```
   rsync -a ~/studio.manifest "${LAPTOP}:studio.manifest"
   ```

   If the paid download or the NBA collector ran on the Mac Studio, copy its data back too:

   ```
   rsync -a --exclude '*.tmp' ~/code/value-finder/sharp-markets/data/ "${LAPTOP}:code/value-finder/sharp-markets/data/"
   ```
4. **On the laptop,** compare:

   ```
   ~/code/value-finder/ops/mac_check.sh --role standby --compare ~/studio.manifest
   ```

   What you must see: **no FAIL line anywhere**, and the line `OK   Records: all N forward-test records are here, the same byte for byte as on the other Mac`. WARN lines for folders that differ are expected here: the laptop's caches are older than the Mac Studio's. If it says "The repo is at another commit", run `git -C ~/code/value-finder pull --ff-only` on both Macs, write the Mac Studio's manifest again (step 1), copy it again (the last command of step 3), and compare again. Any other FAIL: don't put the jobs back; tell the hub.
5. **On the laptop,** put the jobs back (the four installers above, and the live-uses command if you wrote one down), and run the check with `--role live`.
6. Open the Claude app and tell the hub, and say at what time each Mac stopped and started.

**If the check ever finds both Macs running the jobs,** stop the standby Mac's jobs at once with the commands the check prints. Then tell the hub straight away, with the times. The hub compares the two ledgers and the two `runs.csv` files and settles which rows stand. Rows are logged, never dropped, so the double rows stay visible in the record.

## 8. After the move

- **Keep the Mac Studio awake.** In System Settings > Energy (called Energy Saver on older macOS), turn on "Prevent automatic sleeping when the display is off" and "Start up automatically after a power failure". The display may sleep; the Mac must not. These are your settings to change. The check warns when the Mac goes to sleep by itself, when it won't start again after a power cut, and when it can't read that setting.
- **Log in after every restart.** The jobs run only while you are logged in. After a power cut or a macOS update, they wait at the login screen until you log in. To keep macOS from restarting by itself during the season: in System Settings > General > Software Update > Automatic Updates, turn off "Install macOS updates" and leave "Install Security Responses and system files" on.
- **The dashboard and the menu-bar light** can go on the Mac Studio. The dashboard runs at <http://127.0.0.1:8787/>; the light's Swift comes with the Command Line Tools:

  ```
  ~/code/value-finder/ops/install_dashboard.sh
  ```
  ```
  ~/code/value-finder/ops/build_menubar.sh
  ```
  ```
  ~/code/value-finder/ops/install_menubar.sh
  ```

  If you installed the dashboard on the laptop, remove it there. Otherwise it shows the jobs as missing:

  ```
  ~/code/value-finder/ops/uninstall_dashboard.sh
  ```
- **The Claude app.**
  - Install it from <https://claude.ai/download> and sign in. With route A it comes across, and it may ask you to sign in again.
  - **What's known about the hub chat.** It's a local chat. Its record is kept in files on the laptop: `~/Library/Application Support/Claude/` and `~/.claude/projects/`. Route A copies those folders; route B doesn't.
  - **What's not known.** Whether the Claude app on the Mac Studio shows the copied hub chat and lets it carry on, and whether its daily check-in moves with it. None of this was tested.
  - **The simplest plan.** Start a new hub chat on the Mac Studio. Open a Claude Code chat in `~/code/value-finder`, name it "Value Finder — hub", pin it, keep it out of auto-archive, and type `/hub`. It reads `CLAUDE.md`, `STATUS.md` and the memory folder. `CLAUDE.md` names the hub's chat (today `local_446fc83e-…`), and the new hub updates that line with its own in its first pull request.
  - **The memory folder** is plain files: `~/.claude/projects/-Users-maxzipperman-code-value-finder/memory/` (`MEMORY.md` and the notes it lists). Its name comes from the repo's path, so it works only with the same account name and `~/code/value-finder`. Route A copies it. For route B, copy it with section 5, step 5.
  - **One hub at a time.** Once the new hub runs on the Mac Studio, stop using the old one on the laptop, or quit the Claude app there. A hub checks only the Mac it runs on. At a check-in it only reports: it never installs or removes a job, and it takes the live Mac's name from `STATUS.md` on GitHub, so a Mac that hasn't pulled yet can't mislead it.
- **The daily check-in** runs at about 9 AM while the Claude app is open. The hub renews it at each check-in (`hub.md`, section 5), so the new hub sets it up at its first `/hub`. On an always-on Mac Studio, leave the app open.
- **Local worker chats** run on the Mac where they were started. Let them finish, or let the hub start new ones on the Mac Studio. The cloud worker doesn't change.

## 9. What the new Mac changes for the research

- **Always on:** the alert runs and the closes no longer depend on the laptop's lid being open. Fewer are recorded as missing, and a missing one is never filled in afterwards.
- **Disk:** 1 TB instead of the laptop's 460 GB (79.7 GB free on September 29). Day one's download (about 3 GB) and F4, if it's earned (about 16 GB), fit with room to spare.
- **Speed:** the 18-core M5 Max with 64 GB runs the simulations (like the 40,000-path keep-test check) and the backtests faster, and bigger ones fit in memory.
- **It doesn't change how many games there are.** The forward tests still need their 40 signals and their seasons, so no decision comes sooner.
- **Every variant still counts.** Faster runs make it cheap to try more variants, and each one still counts toward the multiple-testing bar.

## What was not tested

- Migration Assistant, in either form, and Time Machine's "Manually" setting and backup choice. Whether Setup Assistant allows a transfer with no internet. Whether the laptop's jobs run during a transfer. Whether Homebrew comes across.
- `rsync` between two Macs over the network. The options were tested only within one Mac, and the commands' wording in zsh and bash with a stand-in for `rsync`.
- The installers, the jobs and the notifications on the Mac Studio. The check ran on the laptop (macOS 26.3) and in the test suite's fake home folders (`ops/tests/`), not on the Mac Studio.
- Whether a copied hub chat works in the Claude app on another Mac, and whether a hub follows its new instruction to only report. That instruction is in `.claude/commands/hub.md`; the pause in step 2 of the handover is there so that nothing depends on it during the move.
