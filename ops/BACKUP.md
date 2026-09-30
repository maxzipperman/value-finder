# Backing up the paid data

The odds history bought on October 1 can't be downloaded again without paying again, and the forward-test records
can't be re-created at all. Until they are also on a second disk, one failed disk loses both.

## What is copied

`ops/backup_data.sh` copies three groups into a folder named `value-finder-backup` on the drive you name. Sizes are
from September 29, 2026, before the paid pull (a `--check` of the laptop).

| Group | What | Size today |
|---|---|---|
| 1. The paid data | `sharp-markets/data/raw` (the bulk cache and its `_manifest` folder; the `raw` folder of `MARKETS_DATA_DIR` when that is set in Terminal), and `nfl-weather/data/raw/oddsapi*` and `cfb-weather/data/raw/oddsapi*` | 3,920 files, 47.9 MB. Day one adds about 3 GB (about 16 GB if F4 is earned). |
| 2. The forward-test records | `nfl-weather/data/forward` and `cfb-weather/data/forward`: ledgers, run records, saved forecasts, and the decision record once there is one. Each run also keeps a dated copy in `forward-snapshots/`. | 222 files, 0.4 MB |
| 3. Slow to re-create | `~/.cache/value-finder` (the forecast archive, five to six hours to download, and the credit balance file) and `sharp-markets/data/markets.duckdb` (54 MB) | 2,643 files, 1.9 GB |

The first backup writes about 2.0 GB. **Never copied:** key files, whatever the mix of capital and small letters
(`.env` and any name like `.ENV`, `.env.local`, `prod.env`, `env`, and `.netrc`, `kaggle.json`, `.kaggle`, `*.pem`,
`*.p12`, `*.key`, `id_rsa*`, `id_ed25519*`, and any name containing `secret`, `credential`, `password`, `api_key`,
`api-key` or `apikey`, and `*token*.json`, `service-account*.json`; the output names every one it leaves out, and the
script never opens them; keys are replaced from the account page, never restored), `.venv` and `.git` folders,
Finder's `.DS_Store` and `._` files, and half-written `*.tmp` files. **Also left out:** `data/processed` and
`sharp-markets/reports` (git has them), the weather projects' other raw folders (weather, play-by-play, schedules:
free to download again), `sharp-markets/data/weather` (the free weather joins re-create it), `sharp-markets/data/collector`
(the forward collector's own state), and the launchd jobs.

The script only reads this Mac. On the drive it never deletes anything: a file it replaces, in any of the three
groups, is first kept in `value-finder-backup/replaced/<date and time>/`, a folder no earlier run used. So
`replaced/` grows: each time `markets.duckdb` has changed, its older copy (54 MB today) is kept there. The script
never empties it; when the drive runs short of space, the hub decides which old folders there can go. Links are
copied as links, and what they point to is not copied. Each backup adds a line to `value-finder-backup/backup-log.txt`.

## Where the backup can live

**Which Mac, and where.** You told the hub the backup goes to the Mac Studio, and you move to the Studio on
Wednesday, so from Thursday the data lives on the Studio and the copy goes from the Studio to the laptop (over the
home network, (b) below) or to an external drive ((a) below).

Run the backup on the Mac where the pulls ran: from Thursday, the Studio. Its first line names the checkout and the
Mac by its computer name ("Backing up /Users/.../value-finder on <the Studio's name> to ..."), and after each pull the
group 1 file count under "On this Mac now" should have grown. If it names the laptop, or the count hasn't grown,
stop: it is backing up the wrong Mac.

**(a) An external drive.** Formatting erases the drive, so use an empty one. In Disk Utility (Command-Space, type
Disk Utility, press Return):

1. View menu: Show All Devices.
2. In the sidebar, under External, click the drive's top line (its maker and size), not the line indented under it. Check the size: erasing the wrong disk deletes everything on it.
3. Click Erase. Name: `VFBackup`. Format: **APFS (Encrypted)**. Scheme: GUID Partition Map.
4. Type a password twice. Keep it somewhere other than these two Macs: without it the backup can't be opened.
5. Click Erase, then Done.

When the drive is plugged in, macOS should ask for that password and offer to remember it in the keychain; if it
remembers it, anyone who can open that Mac can open the drive. Then, in Terminal on the Studio:

```
cd ~/code/value-finder
```

```
ops/backup_data.sh /Volumes/VFBackup
```

An encrypted disk image made on the same Mac (Disk Utility, File > New Image) is not a backup: its file sits on that
Mac's own disk, so the script refuses it. So is a folder on that Mac's own disk. If `MARKETS_DATA_DIR` puts the data
on an external drive (checklist, "Before buying", step 2), the backup needs a different drive, and `MARKETS_DATA_DIR`
must be set in Terminal the same way as for the pulls: the first lines of the output name the folder it reads.

*Tested:* the script, on a disk image standing in for the drive (APFS, not encrypted, and once ExFAT), with a
stand-in `diskutil` that reports it as a USB drive. *Not tested:* a real external drive, an encrypted one, the Disk
Utility steps, and the password prompt.

**(b) The laptop, over the home network (from Wednesday, after the move).** These are your settings to change, on
the laptop:

1. In Finder, make a folder named `VFLaptop` in your home folder.
2. System Settings > General > Sharing: turn on **File Sharing**. Click the (i) next to it, click + under Shared Folders, and add `VFLaptop`. Your user needs Read & Write.
3. System Settings > Privacy & Security > FileVault: make sure it is on, so the copy is encrypted on the laptop's disk.
4. At the bottom of the Sharing pane, note the laptop's local hostname, for example `Maxs-MacBook-Air.local`.
5. While a backup runs, keep the laptop plugged in, open and on the same network: if it sleeps, the copy stops.

Remote Login, in the same Sharing pane, isn't needed: the script copies to a folder the Studio has opened, not over
SSH. On the Studio, in Finder: Go > Connect to Server, type `smb://` and the laptop's hostname, sign in with the
laptop's user name and password, and choose `VFLaptop`. Then, in Terminal on the Studio:

```
cd ~/code/value-finder
```

```
ops/backup_data.sh /Volumes/VFLaptop
```

*Not tested:* none of (b) could be tried before the Studio arrives. If a drive or folder was last backed up from the
laptop, the Studio's first run there stops with "This backup was last made from" the laptop; add `--new-source` to
that one run, and only then.

## When

- **Once on Wednesday, after the move**, on the Studio, as soon as the drive or the laptop's folder is ready, so the whole step is proven before money is spent.
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

Groups 1 and 2 and `Snapshots of the forward-test records` should each say OK. The group 3 line starts with `--`
instead, because `--check` does not compare group 3. Files the alert jobs wrote since the backup are listed under an
OK line as "new or changed since the last backup"; that is expected. A line that ends "Stopped before copying
anything." is a refusal, and its sentence says why: the drive isn't there, can't be written to, is on the same disk
as the data, is a cloud folder (`--allow-cloud` overrides that one), is too small, or holds a backup made from another
Mac or checkout.

**If a line says FAIL**, the file names follow it:

- "changed on this Mac while this ran", or "the copy stopped with an error" (the error is printed above; often a full or unplugged drive): fix that and run the backup again.
- "missing on the backup" or "no copy on the backup yet": run the backup (without `--check`).
- "is smaller on this Mac", "is on the backup but no longer on this Mac", or "is a link (or folder, or file) on this Mac but ... on the backup": something changed here that a backup should not copy over blindly, so the backup kept its own copy. **Stop pulling and send the lines to the hub.** If the change was made on purpose, the hub runs the backup with `--accept-changes`, which moves the backup's copies into `replaced/` (never deletes them) and copies this Mac's.
- "not on this Mac, but the backup has it": a whole folder is gone from this Mac. Stop pulling and tell the hub before restoring anything. If it was removed on purpose, `--accept-changes` moves the backup's copy of that folder into `replaced/`.
- "differs (content)": both copies have the same size and time but not the same contents, so one is damaged. The backup leaves it alone. Delete nothing; send the lines to the hub. For a paid response, the hub reads the body out of each `.parquet` copy and compares its SHA-256 with the manifest row (the manifest hashes the body, not the file). For a forward record, it compares with the snapshots and the `ledgers` branch on GitHub.
- "could not be read on this Mac" (for example "File name too long"): the script could not look at that file, so it is not backed up. Tell the hub.
- A FAIL under "Snapshots": that snapshot was damaged on the drive. Never restore from it; tell the hub.
- "has a line break in its name": the script can't check that file. The hub renames it.

A line "a partial copy that a stopped backup left" is harmless: a copy that was cut off (an unplugged drive, say) left
it, beside a file of the same name. The hub's next `--accept-changes` moves such leftovers into `replaced/`. A
snapshot named `.incomplete-...` is never restored from; once a later snapshot has been verified, the hub may delete
it. If the same FAIL comes back twice, stop and tell the hub.

## How to restore

Restores are done with the hub. Nothing is deleted: the damaged copy is moved aside under a name with today's date
and time, the backup is copied back, then checked. **First the hub pauses every job that writes to these folders
(the alerts, close capture, the trigger poller, the props log and the NBA collector) and the nightly ledger copy, and
checks that none is left running:**

```
for j in com.nflweather.alerts com.cfbweather.alerts com.valuefinder.closecapture com.valuefinder.triggerpoll com.valuefinder.propslog com.valuefinder.nbacollector com.valuefinder.ledgersync; do launchctl bootout "gui/$(id -u)/$j" 2>/dev/null; done; launchctl list | grep -E 'nflweather|cfbweather|closecapture|triggerpoll|propslog|nbacollector|ledgersync' || echo "All paused."
```

Nothing is copied back until that prints "All paused." Afterwards the hub starts them again:

```
for j in com.nflweather.alerts com.cfbweather.alerts com.valuefinder.closecapture com.valuefinder.triggerpoll com.valuefinder.propslog com.valuefinder.nbacollector com.valuefinder.ledgersync; do [ ! -f ~/Library/LaunchAgents/$j.plist ] || launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/$j.plist; done
```

**The paid data** (with `MARKETS_DATA_DIR` set, use `$MARKETS_DATA_DIR` in place of
`~/code/value-finder/sharp-markets/data` in the first command):

```
cd ~/code/value-finder/sharp-markets/data
```

```
mv raw "raw.damaged-$(date +%Y%m%d-%H%M%S)" && [ ! -e raw ] && echo "Moved aside."
```

```
rsync -a --exclude='.*.??????' --exclude='.*.??????????' /Volumes/VFBackup/value-finder-backup/sharp-markets/data/raw/ raw/
```

```
cd ~/code/value-finder && ops/backup_data.sh /Volumes/VFBackup --check
```

The check compares both ways, so a file the restore missed shows as FAIL. The two `--exclude` parts skip partial
copies a stopped backup may have left. The same steps restore `nfl-weather/data/raw/oddsapi`,
`cfb-weather/data/raw/oddsapi` and the forecast archive (from `value-finder-backup/home-cache/value-finder/` to
`~/.cache/value-finder/`). **`markets.duckdb`** goes back with the write-ahead file beside it, if there is one: the
first command moves this Mac's two files aside under a dated name that no earlier restore used, the second copies the
backup's back.

```
cd ~/code/value-finder/sharp-markets/data && t=$(date +%Y%m%d-%H%M%S) && [ ! -e "markets.duckdb.damaged-$t" ] && mv markets.duckdb "markets.duckdb.damaged-$t" && { [ ! -e markets.duckdb.wal ] || mv markets.duckdb.wal "markets.duckdb.wal.damaged-$t"; } && echo "Moved aside."
```

```
rsync -a /Volumes/VFBackup/value-finder-backup/sharp-markets/data/markets.duckdb* ./
```

**The forward-test records are restored only from a snapshot taken before the damage, never merged by hand.** List
the snapshots; their names are UTC dates and times, and only finished, checked ones are listed (one that did not
finish is hidden, named `.incomplete-...`):

```
ls /Volumes/VFBackup/value-finder-backup/forward-snapshots
```

Pick the last one before the damage, and use it only if the last `--check` said OK for the snapshots and its line in
`backup-log.txt` says "verified". For nfl-weather (cfb-weather is the same with its name), with that snapshot's name,
copy it into a new folder, `forward.restored`, beside the damaged one (if a `forward.restored` is already there from
an earlier try, rename it first):

```
cd ~/code/value-finder/nfl-weather/data
```

```
rsync -a /Volumes/VFBackup/value-finder-backup/forward-snapshots/2026-10-05T183012Z/nfl-weather/data/forward/ forward.restored/
```

Compare the copy with the snapshot, both ways. It prints the sentence only when they match; anything else it prints
is a difference, and then stop and tell the hub:

```
diff -rq /Volumes/VFBackup/value-finder-backup/forward-snapshots/2026-10-05T183012Z/nfl-weather/data/forward forward.restored && echo "The restored folder matches the snapshot."
```

Then swap the two folders. The damaged one keeps a dated name, and the restored one takes its place only if nothing
else has taken it:

```
mv forward "forward.damaged-$(date +%Y%m%d-%H%M%S)" && [ ! -e forward ] && mv forward.restored forward && echo "Restored."
```

Copy no rows from the damaged folder into the restored one; tell the hub which snapshot you used. The next backup
will say FAIL for the rows and files the snapshot didn't have (the backup keeps them); the hub settles that with
`--accept-changes`. The nightly copy of the ledgers on GitHub (the `ledgers` branch) is a second record to compare
against.

For the hub: the tests are `ops/tests/test_backup_data.sh`; `value-finder-backup/source.txt` records the Mac,
checkout and data folder of the last backup.
