# Backing up the paid data

The odds history bought on October 1 can't be downloaded again without paying again, and the forward-test records
can't be re-created at all. This laptop has no Time Machine drive, so until there is a backup, one failed disk loses both.

## What is copied

`ops/backup_data.sh` copies three groups into a folder named `value-finder-backup` on the drive you name. Sizes are
from September 29, 2026, before the paid pull.

| Group | What | Size today |
|---|---|---|
| 1. The paid data | `sharp-markets/data/raw` (the bulk cache and its `_manifest` folder, or the `raw` folder of `MARKETS_DATA_DIR` when that is set), and `nfl-weather/data/raw/oddsapi*` and `cfb-weather/data/raw/oddsapi*` | 3,918 files, 47.5 MB. Day one adds about 3 GB (about 16 GB if F4 is earned). |
| 2. The forward-test records | `nfl-weather/data/forward` and `cfb-weather/data/forward`: ledgers, run records, saved forecasts, and the decision record once there is one. Each run also keeps a dated copy in `forward-snapshots/`. | 222 files, 0.4 MB |
| 3. Slow to re-create | `~/.cache/value-finder` (the forecast archive, five to six hours to download, and the credit balance file) and `sharp-markets/data/markets.duckdb` | 2,643 files, 1.9 GB |

**Never copied:** `.env` files (keys are replaced from the Odds API account page, never restored), `~/.kaggle`,
`.venv` and `.git` folders, and Finder's `.DS_Store` files. **Also left out**, because git has them or they are free
to download again: `data/processed`, the weather projects' other raw folders (weather, play-by-play, schedules),
`sharp-markets/data/weather` and `reports`, and the launchd jobs.

The script only reads this Mac. On the drive it adds and replaces files and never deletes one, so a file removed
here stays in the backup. Links are copied as links. Each backup adds a line to `value-finder-backup/backup-log.txt`.

## Where the backup can live

**(a) An external drive.** Formatting erases the drive, so use an empty one. In Disk Utility (Command-Space, type
Disk Utility, press Return):

1. View menu: Show All Devices.
2. In the sidebar, under External, click the drive's top line (its maker and size), not the line indented under it. Check the size: erasing the wrong disk deletes everything on it.
3. Click Erase. Name: `VFBackup`. Format: **APFS (Encrypted)**. Scheme: GUID Partition Map.
4. Type a password twice. Keep it somewhere other than this laptop: without it the backup can't be opened.
5. Click Erase, then Done. The drive now asks for that password each time it is plugged in.

Then, in Terminal:

```
cd ~/code/value-finder
```

```
ops/backup_data.sh /Volumes/VFBackup
```

If `MARKETS_DATA_DIR` puts the data on an external drive (checklist, "Before buying", step 2), the backup needs a
different drive; the script refuses the same one. Set `MARKETS_DATA_DIR` for the backup the same way as for the
pulls: the first lines of the output name the folder it reads.

*Tested:* the script, on a disk image standing in for the drive (APFS, not encrypted; encryption doesn't change
what the script sees). *Not tested:* a real external drive, and the Disk Utility steps.

**(b) The Mac Studio, over the home network.** These are your settings to change, on the Studio:

1. System Settings > General > Sharing: turn on **File Sharing**. Click the (i) next to it, click + under Shared Folders, and add a folder named `VFStudio`. Your user needs Read & Write.
2. System Settings > Privacy & Security > FileVault: make sure it is on, so the copy is encrypted on the Studio's disk.
3. At the bottom of the Sharing pane, note the Studio's local hostname, for example `Maxs-Mac-Studio.local`.

Remote Login, in the same Sharing pane, isn't needed: the script copies to a folder the laptop has opened, not over
SSH. On the laptop, in Finder: Go > Connect to Server, type `smb://` and the hostname, sign in with the Studio's user
name and password, and choose `VFStudio`. Then:

```
ops/backup_data.sh /Volumes/VFStudio
```

*Not tested:* none of (b) could be tried before the Studio arrives. Once the live jobs move to the Studio, the
data lives there, and the Studio no longer backs it up: use the external drive then.

## When

- **Once before Thursday**, as soon as the drive is ready, so the whole step is proven before money is spent. Today that writes about 2 GB, most of it the forecast archive.
- **Thursday, after each pull** of the day-one checklist (`sharp-markets/docs/ODDS5M_DAY_ONE.md`, "Day one"), once it has finished: after step 2 (the probe), step 4 (the week of F1 and F2), each of the three pulls in step 5 (F1, F2, then F3's 2025 slice), step 6 (the NBA sample week) and step 7 (the heat closes, usually a few days later). At step 8, after the reconciliation, run it once more. The checklist itself will point here once its own pull request has merged.
- **Then once a day** while the paid month runs, and after each gated pull (F3b, N1, F4).
- **Never while a `markets` command runs:** the manifest and `markets.duckdb` would be copied half-written.

## What you should see

It lists what is on this Mac and how much it will write, copies, then compares every file of groups 1 and 2 on both
sides. The last lines read like this, with that day's numbers in place of the dots:

```text
OK    Group 1, the paid data: ... each has the same size and SHA-256 on the backup.
OK    Group 2, the forward-test records: ... on the backup and in the snapshot forward-snapshots/2026-10-01T183012Z.
--    Group 3, slow to re-create: ... copied; not compared file by file (it can be re-created, slowly).
Backup finished: groups 1 and 2 match file for file. ...
```

The next morning, this reads every file on the drive again and copies nothing. Both groups should say OK; files the
alert jobs wrote since the backup are listed under the OK line as "new or changed since the last backup", which is
expected (the next backup copies them):

```
ops/backup_data.sh /Volumes/VFBackup --check
```

A line that ends "Stopped before copying anything." is a refusal, and its sentence says why: the drive isn't
there, can't be written to, is on the same disk as the data, is a cloud folder (`--allow-cloud` overrides that one),
or is too small.

**If a line says FAIL**, the file names follow it:

- "changed on this Mac while this ran": a job wrote to the file during the backup. Run the same command again.
- "missing on the backup" or "no copy on the backup yet": run the backup (without `--check`).
- "differs (content)" alone: both copies have the same size and time but not the same contents, so one of them is damaged. The backup leaves it alone. Delete nothing; send the lines to the hub. For the paid data, the manifest holds each response's SHA-256, which tells which copy is right.
- "not on this Mac": the folder is gone from the laptop. Stop pulling and tell the hub before restoring anything.
- "the copy stopped with an error": the error is printed above it (often a full or unplugged drive). Fix that and run again.

If the same FAIL comes back twice, stop and tell the hub.

## How to restore

Move the damaged folder aside rather than deleting it, copy the backup back, then check. For the paid data:

```
mv ~/code/value-finder/sharp-markets/data/raw ~/code/value-finder/sharp-markets/data/raw.damaged
```

```
rsync -a /Volumes/VFBackup/value-finder-backup/sharp-markets/data/raw/ ~/code/value-finder/sharp-markets/data/raw/
```

```
ops/backup_data.sh /Volumes/VFBackup --check
```

The same two steps restore `nfl-weather/data/raw/oddsapi`, `cfb-weather/data/raw/oddsapi`, `markets.duckdb`, and
the forecast archive (from `value-finder-backup/home-cache/value-finder/mos/` to `~/.cache/value-finder/mos/`).

**The forward-test records are restored only from a snapshot taken before the damage, never merged by hand.** Do it
with the hub, which pauses the alert jobs first (they write to these folders every few hours). List the snapshots;
their names are UTC dates and times:

```
ls /Volumes/VFBackup/value-finder-backup/forward-snapshots
```

Pick the last one before the damage. For nfl-weather (cfb-weather is the same with its name), with that snapshot's name:

```
mv ~/code/value-finder/nfl-weather/data/forward ~/code/value-finder/nfl-weather/data/forward.damaged
```

```
rsync -a /Volumes/VFBackup/value-finder-backup/forward-snapshots/2026-10-05T183012Z/nfl-weather/data/forward/ ~/code/value-finder/nfl-weather/data/forward/
```

Copy no rows from the damaged folder into the restored one; tell the hub which snapshot you used. The nightly copy
of the ledgers on GitHub (the `ledgers` branch) is a second record to compare against.

For the hub: the tests are `ops/tests/test_backup_data.sh`.
