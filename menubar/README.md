# The menu-bar light

A small Mac app that puts a wind symbol with a coloured dot in the menu bar, so you can see at a
glance whether the scheduled jobs are running and whether any signal is live. It has no window
and no Dock icon.

It reads one thing: the dashboard's summary at `http://127.0.0.1:8787/api/summary`, once a
minute. The dashboard decides everything; the light only shows what the dashboard says. So the
light needs the dashboard running. Without it, the dot is gray.

## What it shows

| Dot | Meaning |
|---|---|
| Green | All jobs ran and nothing needs you. |
| Amber | Something needs a look: for example the newest ledger row is more than 5 hours old, credits are low on the free plan, or the dashboard couldn't read one of its files. |
| Red | A scheduled job has a problem: an alert run was recorded as failed, a job last exited with an error, or an alert job hasn't run for more than 5 hours during the day (7:30 AM to 11:30 PM). |
| Gray | The dashboard isn't running, isn't answering, or sent something the light couldn't read. |

A number beside the symbol is how many signals are live: games not yet kicked off whose latest
logged row is a signal under any rule. A signal means a pre-registered rule fired in the paper
forward test. It is not evidence that the rule works; the dashboard shows each forward test with
its sample size.

The menu, top to bottom: one line in plain words ("All jobs ran. No signals.", "1 signal is
live.", "The dashboard is not running."), the next alert run, the credits left, each problem the
dashboard reports, **Open dashboard**, the time of the last check, and **Quit**.

## Build, install, remove

```sh
ops/build_menubar.sh        # compiles it into menubar/build/Value Finder.app (kept out of git)
ops/install_menubar.sh      # copies it to ~/Applications and prints the next steps
open "$HOME/Applications/Value Finder.app"
ops/uninstall_menubar.sh    # removes the copy from ~/Applications (quit it first)
```

To have it start when you log in: System Settings > General > Login Items. Under "Open at
Login", click +, then choose Value Finder in the Applications folder inside your home folder.
The scripts never add the login item themselves.

To update it after a change: quit it (Quit in its menu), build, install, open.

## What it never does

- It never asks any address but the dashboard's summary, and it refuses any address that isn't
  on this Mac (http on 127.0.0.1). It ignores proxies and never follows a redirect.
- It never sends a notification. The alert jobs already do that.
- It never reads or writes a file. It keeps no cache and no cookies. (macOS may remember its place
  in the menu bar in the app's own preferences.)
- It never starts another program, except that **Open dashboard** opens
  `http://127.0.0.1:8787/` in your default browser.
- It has nothing to do with placing bets. Paper only.

## Checking it without opening it

The app has a self-test that asks an address once, prints what the light would show, and exits
without putting anything in the menu bar:

```sh
"menubar/build/Value Finder.app/Contents/MacOS/ValueFinder" --selftest http://127.0.0.1:8787/api/summary
```

`menubar/tests/run_selftests.sh` reruns the saved cases in `menubar/tests/expected/` against a
stand-in server (`menubar/tests/stub_server.py`) on a free local port, and also checks that
the app asked each address exactly once, followed no redirect, refused addresses off this Mac,
connected only to the stand-in, wrote no cache or saved-state files, and that its code names
only the two dashboard addresses. Run it after building. `--update` rewrites the expected files
after a deliberate change to the wording.

## The files

| File | What it does |
|---|---|
| `Sources/Address.swift` | The two fixed addresses, and the rule that only 127.0.0.1 is ever asked. |
| `Sources/Fetcher.swift` | The one GET request: no cache, no cookies, no proxy, no redirects, 10-second limit. |
| `Sources/Summary.swift` | Checks every field of the answer. A missing field or a wrong type means gray. |
| `Sources/DisplayState.swift` | Turns an answer into the dot, the number and the menu lines. |
| `Sources/Icon.swift` | Draws the wind symbol, the dot and the number. |
| `Sources/LightApp.swift` | The menu-bar item and the once-a-minute check. |
| `Sources/Main.swift` | Starts the app, or runs the self-test. |
| `Info.plist` | No Dock icon, bundle id `com.valuefinder.menubar`, local networking only. |
