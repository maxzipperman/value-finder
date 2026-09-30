# Backing up the paid data

The odds history bought on October 1 can't be downloaded again without paying again, and the forward-test records
can't be re-created at all. This laptop has no Time Machine drive, so until there is a backup, one failed disk loses both.

## What is copied

`ops/backup_data.sh` copies three groups into a folder named `value-finder-backup` on the drive you name. Sizes are
from September 29, 2026, before the paid pull (a `--check` of this laptop).

| Group | What | Size today |
|---|---|---|
| 1. The paid data | `sharp-markets/data/raw` (the bulk cache and its `_manifest` folder; the `raw` folder of `MARKETS_DATA_DIR` when that is set in Terminal), and `nfl-weather/data/raw/oddsapi*` and `cfb-weather/data/raw/oddsapi*` | 3,920 files, 47.9 MB. Day one adds about 3 GB (about 16 GB if F4 is earned). |
| 2. The forward-test records | `nfl-weather/data/forward` and `cfb-weather/data/forward`: ledgers, run records, saved forecasts, and the decision record once there is one. Each run also keeps a dated copy in `forward-snapshots/`. | 222 files, 0.4 MB |
| 3. Slow to re-create | `~/.cache/value-finder` (the forecast archive, five to six hours to download, and the credit balance file) and `sharp-markets/data/markets.duckdb` (54 MB) | 2,643 files, 1.9 GB |

The first backup writes about 2.0 GB. **Never copied:** key files (`.env` and any name like `.env.local`, `prod.env`,
`env`, `.netrc`, `kaggle.json`, `.kaggle`, `*.pem`, `*.p12`, `id_rsa*`, `id_ed25519*`, `*secret*`, `*credential*`;
the output names each one it leaves out, and the script never opens them; keys are replaced from the account page,
never restored), `.venv` and `.git` folders, Finder's `.DS_Store` files, and half-written `*.tmp` files. **Also left
out:** `data/processed` and `sharp-markets/reports` (git has them), the weather projects' other raw folders (weather,
play-by-play, schedules: free to download again), `sharp-markets/data/weather` (the free weather joins re-create it),
`sharp-markets/data/collector` (the forward collector's own state), and the launchd jobs.

The script only reads this Mac. On the drive it never deletes anything: a file it replaces is first kept in
`value-finder-backup/replaced/<date and time>/`. Links are copied as links, and what they point to is not copied.
Each backup adds a line to `value-finder-backup/backup-log.txt`.

## Where the backup can live

**(a) An external drive.** Formatting erases the drive, so use an empty one. In Disk Utility (Command-Space, type
Disk Utility, press Return):

1. View menu: Show All Devices.
2. In the sidebar, under External, click the drive's top line (its maker and size), not the line indented under it. Check the size: erasing the wrong disk deletes everything on it.
3. Click Erase. Name: `VFBackup`. Format: **APFS (Encrypted)**. Scheme: GUID Partition Map.
4. Type a password twice. Keep it somewhere other than this laptop: without it the backup can't be opened.
5. Click Erase, then Done.

When the drive is plugged in, macOS should ask for that password and offer to remember it in the keychain; if it
remembers it, anyone who can open this laptop can open the drive. Then, in Terminal:

```
cd ~/code/value-finder
```

```
ops/backup_data.sh /Volumes/VFBackup
```

An encrypted disk image made on this laptop (Disk Utility, File > New Image) is not a backup: its file sits on this
laptop's disk, so the script refuses it. So is a folder on this laptop's own disk. If `MARKETS_DATA_DIR` puts the data
on an external drive (checklist, "Before buying", step 2), the backup needs a different drive, and `MARKETS_DATA_DIR`
must be set in Terminal the same way as for the pulls: the first lines of the output name the folder it reads.

*Tested:* the script, on a disk image standing in for the drive (APFS, not encrypted), with a stand-in `diskutil`
that reports it as a USB drive. *Not tested:* a real external drive, an encrypted one, the Disk Utility steps, and
the password prompt.

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

*Not tested:* none of (b) could be tried before the Studio arrives. Once the live jobs move to the Studio, the data
lives there, and the Studio no longer backs it up: run the script on the Studio, to the external drive. Its first run
there stops with "This backup was last made from" the laptop; add `--new-source` to that one run, and only then.

## When

- **Once before Thursday**, as soon as the drive is ready, so the whole step is proven before money is spent.
- **Thursday, after each pull** of the day-one checklist (`sharp-markets/docs/ODDS5M_DAY_ONE.md`, "Day one"), once it has finished: after step 2 (the probe), step 4 (the week of F1 and F2), each of the three pulls in step 5 (F1, F2, then F3's 2025 slice), step 6 (the NBA sample week) and step 7 (the heat closes, usually a few days later). At step 8, after the reconciliation, run it once more. The checklist itself will point here once its own pull request has merged.
- **Then once a day** while the paid month runs, and after each gated pull (F3b, N1, F4).
- **Never while a `markets` command runs:** the manifest and `markets.duckdb` would be copied half-written.

## What you should see

The last lines of a backup, with that day's numbers in place of the dots:

```text
OK    Group 1, the paid data: ... each has the same size and SHA-256 on the backup.
OK    Group 2, the forward-test records: ... on the backup and in the snapshot forward-snapshots/2026-10-01T183012Z.
--    Group 3, slow to re-create: ... copied; not compared file by file (it can be re-created, slowly).
Backup finished: groups 1 and 2 match file for file. ...
```

The next morning, this reads every file on the drive again, compares both ways, checks every snapshot against the
list of files saved in it, and copies nothing:

```
ops/backup_data.sh /Volumes/VFBackup --check
```

Every line should say OK, including `OK    Snapshots of the forward-test records`. Files the alert jobs wrote since
the backup are listed under an OK line as "new or changed since the last backup"; that is expected. A line that
ends "Stopped before copying anything." is a refusal, and its sentence says why: the drive isn't there, can't be
written to, is on the same disk as the data, is a cloud folder (`--allow-cloud` overrides that one), is too small,
or holds a backup made from another Mac or checkout.

**If a line says FAIL**, the file names follow it:

- "changed on this Mac while this ran", or "the copy stopped with an error" (the error is printed above; often a full or unplugged drive): fix that and run the backup again.
- "missing on the backup" or "no copy on the backup yet": run the backup (without `--check`).
- "is smaller on this Mac", "is on the backup but no longer on this Mac", or "is a link (or folder, or file) on this Mac but ... on the backup": something changed here that a backup should not copy over blindly, so the backup kept its own copy. **Stop pulling and send the lines to the hub.** If the change was made on purpose, the hub runs the backup with `--accept-changes`, which moves the backup's copies into `replaced/` (never deletes them) and copies this Mac's.
- "not on this Mac, but the backup has it": a whole folder is gone from the laptop. Stop pulling and tell the hub before restoring anything.
- "differs (content)": both copies have the same size and time but not the same contents, so one is damaged. The backup leaves it alone. Delete nothing; send the lines to the hub. For a paid response, the hub reads the body out of each `.parquet` copy and compares its SHA-256 with the manifest row (the manifest hashes the body, not the file). For a forward record, it compares with the snapshots and the `ledgers` branch on GitHub.
- A FAIL under "Snapshots": that snapshot was damaged on the drive. Never restore from it; tell the hub.
- "has a line break in its name": the script can't check that file. The hub renames it.

A line "a partial copy that a stopped backup left" is harmless. If the same FAIL comes back twice, stop and tell the hub.

## How to restore

Move the damaged folder aside rather than deleting it, copy the backup back, then check. For the paid data (with
`MARKETS_DATA_DIR` set, use `$MARKETS_DATA_DIR/raw` in place of `~/code/value-finder/sharp-markets/data/raw` in the
first two commands):

```
mv ~/code/value-finder/sharp-markets/data/raw ~/code/value-finder/sharp-markets/data/raw.damaged
```

```
rsync -a --exclude='.*.??????' --exclude='.*.??????????' /Volumes/VFBackup/value-finder-backup/sharp-markets/data/raw/ ~/code/value-finder/sharp-markets/data/raw/
```

```
ops/backup_data.sh /Volumes/VFBackup --check
```

The check compares both ways, so a file the restore missed shows as FAIL. The two `--exclude` parts skip partial
copies a stopped backup may have left. The same three steps restore `nfl-weather/data/raw/oddsapi`,
`cfb-weather/data/raw/oddsapi` and the forecast archive (from `value-finder-backup/home-cache/value-finder/` to
`~/.cache/value-finder/`). `markets.duckdb` is one file, so its two commands have no slash at the end:

```
mv ~/code/value-finder/sharp-markets/data/markets.duckdb ~/code/value-finder/sharp-markets/data/markets.duckdb.damaged
```

```
rsync -a /Volumes/VFBackup/value-finder-backup/sharp-markets/data/markets.duckdb ~/code/value-finder/sharp-markets/data/markets.duckdb
```

**The forward-test records are restored only from a snapshot taken before the damage, never merged by hand.** Do it
with the hub, which pauses the alert jobs first (they write to these folders every few hours). List the snapshots;
their names are UTC dates and times, and only finished, checked ones are listed (one that did not finish is hidden,
named `.incomplete-...`):

```
ls /Volumes/VFBackup/value-finder-backup/forward-snapshots
```

Pick the last one before the damage, and use it only if the last `--check` said OK for the snapshots and its line in
`backup-log.txt` says "verified". For nfl-weather (cfb-weather is the same with its name), with that snapshot's name:

```
mv ~/code/value-finder/nfl-weather/data/forward ~/code/value-finder/nfl-weather/data/forward.damaged
```

```
rsync -a /Volumes/VFBackup/value-finder-backup/forward-snapshots/2026-10-05T183012Z/nfl-weather/data/forward/ ~/code/value-finder/nfl-weather/data/forward/
```

Then compare the restored folder with the snapshot, both ways. It prints the sentence only when they match; anything
else it prints is a difference:

```
diff -rq /Volumes/VFBackup/value-finder-backup/forward-snapshots/2026-10-05T183012Z/nfl-weather/data/forward ~/code/value-finder/nfl-weather/data/forward && echo "The restored folder matches the snapshot."
```

Copy no rows from the damaged folder into the restored one; tell the hub which snapshot you used. The next backup
will say FAIL for the rows and files the snapshot didn't have (the backup keeps them); the hub settles that with
`--accept-changes`. The nightly copy of the ledgers on GitHub (the `ledgers` branch) is a second record to compare
against.

For the hub: the tests are `ops/tests/test_backup_data.sh`; `value-finder-backup/source.txt` records the Mac,
checkout and data folder of the last backup.
