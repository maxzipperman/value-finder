"""Tests for ops/mac_check.sh, the read-only check of one Mac, and for the commands on ops/MOVE_TO_NEW_MAC.md.

Each test builds a fake home folder: a git repo at ~/code/value-finder with the four projects (small stand-in
packages, fake .env files, fake data and forward-test records), ~/Library/LaunchAgents, ~/.cache/value-finder
and ~/.kaggle. launchctl, pmset, system_profiler, sw_vers, df, gh, uv, swift and xcode-select are stubs on the
PATH. The stub launchctl answers 'list' and 'print' from files outside the home folder and records any other
command it gets; the tests require that it never gets one. Run from the repo root with nfl-weather's Python:

    nfl-weather/.venv/bin/python -m pytest -q ops/tests
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parents[1]
REPO_ROOT = OPS.parent
SCRIPT = OPS / "mac_check.sh"
PAGE = OPS / "MOVE_TO_NEW_MAC.md"
JOBS = ["com.nflweather.alerts", "com.cfbweather.alerts", "com.valuefinder.closecapture",
        "com.valuefinder.ledgersync"]
UID = os.getuid()
NOW = int(datetime(2026, 9, 30, 16, 30, tzinfo=timezone.utc).timestamp())   # 9:30 AM Pacific, a quiet hour
RESIDUALS = [1.5, -2.0, 3.25, 0.5]
COHORT_HASH = hashlib.sha256(json.dumps(sorted(RESIDUALS)).encode()).hexdigest()   # the stand-in market.py's hash

# Every value below must never appear in the check's output or in a manifest.
SECRETS = {
    "nfl-weather": {"ODDS_API_KEY": "FAKE-odds-7f3a9c11", "NTFY_TOPIC": "fake-topic-q8w7e6r5"},
    "cfb-weather": {"ODDS_API_KEY": "FAKE-odds-7f3a9c11", "CFBD_API_KEY": "FAKE-cfbd-0d1e2f3a",
                    "NTFY_TOPIC": "fake-topic-q8w7e6r5"},
    "sharp-markets": {"ODDS_API_KEY": "FAKE-odds-7f3a9c11", "KAGGLE_USERNAME": "fake-kaggle-user-91",
                      "KAGGLE_KEY": "FAKE-kaggle-key-4b5c6d"},
}
GH_TOKEN = "gho_FAKEtokenThatMustNeverShow0123"
KAGGLE_TOKEN = "FAKE-kaggle-access-token-aa55"
HELPER_TOKEN = "ghp_FAKEHELPERTOKEN123456"
ALL_SECRETS = sorted({v for d in SECRETS.values() for v in d.values()} | {GH_TOKEN, KAGGLE_TOKEN, HELPER_TOKEN})

MARKET_PY = '''import hashlib, json
from .config import PROC
def cohort_hash(resid):
    return hashlib.sha256(json.dumps(sorted(resid)).encode()).hexdigest()
def pricing_cohort(registered=None):
    resid = sorted(json.loads((PROC / "pricing_cohort.json").read_text())["residuals"])
    if registered is not None and cohort_hash(resid) != registered:
        raise ValueError("pricing_cohort.json is not the registered cohort")
    return resid
'''
# like the real config.py, importing it makes a folder; the check must never let that happen
CONFIG_PY = '''from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
(RAW / "made-by-config-import").mkdir(parents=True, exist_ok=True)
'''


def write(path: Path, text: str | bytes, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    if mode is not None:
        path.chmod(mode)
    return path


def plist(label: str, args: list[str], wd: str | None, log: str, env: dict | None = None) -> str:
    a = "".join(f"<string>{x}</string>" for x in args)
    w = f"<key>WorkingDirectory</key><string>{wd}</string>" if wd else ""
    e = ("<key>EnvironmentVariables</key><dict>" + "".join(f"<key>{k}</key><string>{v}</string>" for k, v in env.items())
         + "</dict>") if env else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            f'<plist version="1.0"><dict><key>Label</key><string>{label}</string>'
            f'<key>ProgramArguments</key><array>{a}</array>{w}{e}'
            '<key>StartInterval</key><integer>900</integer>'
            f'<key>StandardOutPath</key><string>{log}</string><key>StandardErrorPath</key><string>{log}</string>'
            '</dict></plist>\n')


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "HOME": str(repo), "GIT_CONFIG_NOSYSTEM": "1"})


class FakeMac:
    """A fake home folder with the repo, keys, data and job files, plus stub system commands."""

    def __init__(self, tmp: Path, jobs: str = "loaded"):
        self.tmp, self.home = tmp, tmp / "home"
        self.repo = self.home / "code" / "value-finder"
        self.stubs, self.launchd = tmp / "stubs", tmp / "launchd"
        self.forbidden = tmp / "forbidden.log"
        self.ac_sleep, self.laptop, self.autorestart, self.free_kb = 0, False, "1", 400_000_000
        self.tz = "America/Los_Angeles"
        self.build_repo()
        self.build_home()
        (self.launchd / "loaded").mkdir(parents=True)
        self.write_launchd()
        if jobs in ("loaded", "files"):
            for j in JOBS:
                self.install(j, loaded=(jobs == "loaded"))

    # -- the repo -------------------------------------------------------------------------------------------
    def build_repo(self) -> None:
        r = self.repo
        write(r / ".gitignore", ".env\n**/data/*\n!**/data/processed/\n.venv/\n__pycache__/\n.claude/\n")
        write(r / "ops" / "capture_closes.sh", "#!/bin/bash\n")
        write(r / "ops" / "sync_ledgers.sh", "#!/bin/bash\n")
        write(r / "ops" / "poll_triggers.sh", "#!/bin/bash\n")
        for proj, pkg in (("nfl-weather", "nflweather"), ("cfb-weather", "cfbweather")):
            p = r / proj
            write(p / pkg / "__init__.py", "")
            write(p / pkg / "config.py", CONFIG_PY)
            write(p / pkg / "market.py", MARKET_PY)
            write(p / pkg / "board.py", f'PRICING_COHORT_SHA256 = "{COHORT_HASH}"   # amendment\n')
            write(p / "PREREGISTRATION.md", f"The registered cohort hash is {COHORT_HASH}.\n")
            write(p / "README.md", "uv venv --python 3.12 .venv\n")
            write(p / "scripts" / "alerts.py", "")
            write(p / "scripts" / "log_props.py", "")
            write(p / "data" / "processed" / "pricing_cohort.json", json.dumps({"residuals": RESIDUALS}))
            write(p / "data" / "processed" / "games.csv", "game_id,total\nA,41.5\n")
            write(p / ".env.example", "".join(f"{k}=\n" for k in SECRETS[proj]))
        write(r / "sharp-markets" / "src" / "markets" / "__init__.py", "")
        write(r / "sharp-markets" / "pyproject.toml", 'requires-python = ">=3.12"\n')
        write(r / "sharp-markets" / ".env.example", "# names only\nODDS_API_KEY=\nKAGGLE_USERNAME=\nKAGGLE_KEY=\n")
        write(r / "dashboard" / "vfdash" / "__init__.py", "")
        write(r / "dashboard" / "pyproject.toml", 'requires-python = ">=3.12"\n')
        git(r, "init", "-q", "-b", "main")
        git(r, "add", "-A")
        git(r, "commit", "-q", "-m", "fake repo")
        git(r, "update-ref", "refs/remotes/origin/main", "HEAD")

        # keys, written the ways each project reads them: the weather projects take only NAME=value lines
        # (here with quotes and CRLF endings in cfb-weather); sharp-markets reads with python-dotenv
        nfl, cfb, sm = SECRETS["nfl-weather"], SECRETS["cfb-weather"], SECRETS["sharp-markets"]
        write(r / "nfl-weather" / ".env", f"# keys\nODDS_API_KEY={nfl['ODDS_API_KEY']}\nNTFY_TOPIC={nfl['NTFY_TOPIC']}\n",
              0o600)
        write(r / "cfb-weather" / ".env", "".join(f'{k}="{v}"\r\n' for k, v in cfb.items()), 0o600)
        write(r / "sharp-markets" / ".env", "".join(f"export {k} = {v}\n" for k, v in sm.items()), 0o600)

        # data and forward-test records
        write(r / "nfl-weather" / "data" / "forward" / "ledger.csv",
              "snapshot_utc,rules_version,game_id,gameday,gametime,away_team,home_team\n"
              "2026-09-30T14:30:00Z,v3-2026-09-28,2026_05_DET_CAR,2026-10-04,13:00,DET,CAR\n")
        write(r / "nfl-weather" / "data" / "forward" / "runs.csv",
              "run_utc,job,rules_version,status,games,signals,priced,unmapped,error,rule_priced\n"
              "2026-09-30T14:30:07Z,nfl-alerts,v3-2026-09-28,ok,16,0,16,,,16\n")
        write(r / "nfl-weather" / "data" / "forward" / "alert_state.json", "{}\n")
        write(r / "nfl-weather" / "data" / "forward" / "forecasts" / "0a1b2c.json.gz", b"\x1f\x8bfake")
        write(r / "nfl-weather" / "data" / "raw" / "oddsapi" / "live" / "2026-09-30T143000Z.json", "[]\n")
        write(r / "nfl-weather" / "data" / "raw" / "weather" / "cache1.json", "{}\n")
        write(r / "cfb-weather" / "data" / "forward" / "ledger.csv",
              "snapshot_utc,rules_version,game_id,kick_et,away_team,home_team,venue,start_utc\n"
              '2026-09-30T14:30:00Z,cfb-v3,401871049,Thu 10-01 20:00,Western Kentucky,New Mexico State,'
              '"Aggie Memorial Stadium, Las Cruces",2026-10-02 00:00:00+00:00\n')
        write(r / "cfb-weather" / "data" / "forward" / "runs.csv",
              "run_utc,job,rules_version,status,games,signals,priced,unmapped,error,rule_priced\n"
              "2026-09-30T14:30:14Z,cfb-alerts,cfb-v3-2026-09-28,ok,60,0,56,,,56\n")
        write(r / "cfb-weather" / "data" / "forward" / "alert_state.json", "{}\n")
        write(r / "cfb-weather" / "data" / "raw" / "oddsapi" / "live" / "2026-09-30T143000Z.json", "[]\n")
        write(r / "sharp-markets" / "data" / "markets.duckdb", b"fake duckdb")
        write(r / "sharp-markets" / "data" / "raw" / "_manifest" / "oddsapi_manifest.csv", "sha256\n")

        # environments: real Python venvs (standard library only); the two installed packages are linked in
        # the way an editable install does it
        for proj in ("nfl-weather", "cfb-weather", "sharp-markets", "dashboard"):
            v = r / proj / ".venv"
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(v)], check=True)
        for proj, src in (("sharp-markets", r / "sharp-markets" / "src"), ("dashboard", r / "dashboard")):
            site = next((r / proj / ".venv" / "lib").glob("python3*/site-packages"))
            write(site / "_editable.pth", f"{src}\n")

    def build_home(self) -> None:
        write(self.home / ".kaggle" / "access_token", KAGGLE_TOKEN, 0o600)
        write(self.home / ".cache" / "value-finder" / "odds_quota.json", '{"remaining": 400}\n')
        write(self.home / ".cache" / "value-finder" / "mos" / "a.csv", "x\n")
        write(self.home / ".cache" / "value-finder" / "mos" / "b.csv", "y\n")
        write(self.home / ".gitconfig", "[credential]\n\thelper = osxkeychain\n")
        (self.home / "Library" / "LaunchAgents").mkdir(parents=True)
        (self.home / "Library" / "Logs").mkdir(parents=True)
        (self.home / "tmp").mkdir()                    # TMPDIR: a temporary file there would show as a change

    def add_paid(self, n: int = 3) -> list[Path]:
        base = self.repo / "sharp-markets" / "data" / "raw" / "nfl" / "oddsapi" / "hist_odds" / "2025-10-05"
        files = [write(base / f"k{i:04d}.parquet", b"PAR1" + bytes([i]) * (100 + i)) for i in range(n)]
        files.append(write(self.repo / "sharp-markets" / "data" / "raw" / "nba" / "oddsapi_hist" / "2025-01-02" /
                           "n1.parquet", b"PAR1nba"))
        return files

    # -- jobs -----------------------------------------------------------------------------------------------
    def job_args(self, label: str, root: Path) -> tuple[list[str], str | None, str]:
        logs = f"{self.home}/Library/Logs/{label}.log"
        if label == "com.nflweather.alerts":
            return [f"{root}/nfl-weather/.venv/bin/python", f"{root}/nfl-weather/scripts/alerts.py"], \
                f"{root}/nfl-weather", f"{root}/nfl-weather/data/forward/alerts.log"
        if label == "com.cfbweather.alerts":
            return [f"{root}/cfb-weather/.venv/bin/python", f"{root}/cfb-weather/scripts/alerts.py"], \
                f"{root}/cfb-weather", f"{root}/cfb-weather/data/forward/alerts.log"
        if label == "com.valuefinder.closecapture":
            return ["/bin/bash", f"{root}/ops/capture_closes.sh"], None, logs
        if label == "com.valuefinder.ledgersync":
            return ["/bin/bash", f"{root}/ops/sync_ledgers.sh"], None, logs
        if label == "com.valuefinder.dashboard":      # as ops/install_dashboard.sh writes it: --root is the repo
            return [f"{root}/dashboard/.venv/bin/python", "-m", "vfdash", "--port", "8787", "--root", f"{root}"], \
                f"{root}/dashboard", logs
        if label == "com.valuefinder.propslog":
            return [f"{root}/nfl-weather/.venv/bin/python", f"{root}/nfl-weather/scripts/log_props.py"], \
                f"{root}/nfl-weather", logs
        return ["/bin/bash", f"{root}/ops/poll_triggers.sh"], f"{root}", logs

    def plist_path(self, label: str) -> Path:
        return self.home / "Library" / "LaunchAgents" / f"{label}.plist"

    def install(self, label: str, loaded: bool = True, root: Path | None = None, env: dict | None = None) -> None:
        args, wd, log = self.job_args(label, root or self.repo)
        write(self.plist_path(label), plist(label, args, wd, log, env))
        if loaded:
            self.load(label)

    def load(self, label: str, exit_code: int = 0) -> None:
        write(self.launchd / "loaded" / label,
              f"gui/{UID}/{label} = {{\n\tactive count = 0\n\tpath = {self.plist_path(label)}\n"
              f"\ttype = LaunchAgent\n\tstate = not running\n\n\tprogram = /bin/bash\n\truns = 3\n"
              f"\tlast exit code = {exit_code}\n\n\tresource coalition = {{\n\t\tstate = active\n\t}}\n}}\n")
        self.write_launchd()

    def unload(self, label: str) -> None:
        (self.launchd / "loaded" / label).unlink(missing_ok=True)
        self.write_launchd()

    def write_launchd(self) -> None:
        loaded = sorted(p.name for p in (self.launchd / "loaded").glob("*")) if (self.launchd / "loaded").exists() else []
        write(self.launchd / "list.txt",
              "PID\tStatus\tLabel\n-\t0\tcom.apple.weatherd\n" + "".join(f"-\t0\t{l}\n" for l in loaded))

    # -- stubs and runs -------------------------------------------------------------------------------------
    def write_stubs(self) -> None:
        f, d = self.forbidden, self.launchd
        battery_profile = "printf 'Battery Power:\\n sleep                1\\n'" if self.laptop else ":"
        batt = ("printf ' -InternalBattery-0 (id=1)\\t69%%\\n'" if self.laptop
                else "printf \"Now drawing from 'AC Power'\\n\"")
        restart = f"printf ' autorestart          {self.autorestart}\\n'" if self.autorestart is not None else ":"
        stubs = {
            "launchctl": f'''case "$1" in
  list) cat "{d}/list.txt"; exit 0 ;;
  print) l="${{2##*/}}"; if [ -f "{d}/loaded/$l" ]; then cat "{d}/loaded/$l"; exit 0; fi
         echo "Could not find service \\"$l\\"" >&2; exit 113 ;;
esac
echo "launchctl $*" >> "{f}"; exit 1''',
            "pmset": f'''case "$*" in
  "-g custom") printf 'AC Power:\\n sleep                {self.ac_sleep}\\n displaysleep         10\\n'
               {battery_profile} ;;
  "-g batt") {batt} ;;
  "-g") printf ' sleep                {self.ac_sleep}\\n'; {restart} ;;
  *) echo "pmset $*" >> "{f}"; exit 1 ;;
esac''',
            "system_profiler": "printf '      Model Name: Mac Studio\\n'",
            "sw_vers": 'case "$1" in -productVersion) echo 26.0 ;; -buildVersion) echo 25A100 ;; esac',
            "df": f"printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n"
                  f"/dev/disk3s5 900000000 1000 {self.free_kb} 1% /System/Volumes/Data\\n'",
            "gh": f'''if [ "$*" = "auth status" ]; then
  printf 'github.com\\n  Logged in to github.com account fakeuser (keyring)\\n  - Token: {GH_TOKEN}\\n' >&2; exit 0
fi
echo "gh $*" >> "{f}"; exit 1''',
            "uv": f'[ "$1" = "--version" ] && {{ echo "uv 0.9.27"; exit 0; }}; echo "uv $*" >> "{f}"; exit 1',
            "swift": 'echo "Apple Swift version 6.2"',
            "xcode-select": f'[ "$1" = "-p" ] && {{ echo /Library/Developer/CommandLineTools; exit 0; }}; '
                            f'echo "xcode-select $*" >> "{f}"; exit 1',
        }
        for name, body in stubs.items():
            write(self.stubs / name, "#!/bin/bash\n" + body + "\n", 0o755)
        lt = self.tmp / "localtime"
        if lt.is_symlink():
            lt.unlink()
        lt.symlink_to(f"/var/db/timezone/zoneinfo/{self.tz}")

    def run(self, *args: str, now: int = NOW, home: Path | None = None) -> subprocess.CompletedProcess:
        self.write_stubs()
        home = home or self.home
        env = {"HOME": str(home), "PATH": f"{self.stubs}:/usr/bin:/bin:/usr/sbin:/sbin",
               "TMPDIR": str(home / "tmp"), "USER": os.environ.get("USER", "tester"), "LANG": "en_US.UTF-8",
               "TZ": "America/Los_Angeles", "MAC_CHECK_LOCALTIME": str(self.tmp / "localtime"),
               "MAC_CHECK_NOW": str(now), "GIT_CONFIG_NOSYSTEM": "1"}
        return subprocess.run(["/bin/bash", str(SCRIPT), *args], env=env, capture_output=True, text=True,
                              timeout=120)

    def copy_to(self, tmp_path: Path, name: str = "studio") -> "FakeMac":
        """The other Mac: this home folder copied with times kept (as rsync -a does), no job installed."""
        other = FakeMac.__new__(FakeMac)
        other.__dict__.update(self.__dict__)
        other.tmp = tmp_path / name
        other.home = other.tmp / "home"
        other.repo = other.home / "code" / "value-finder"
        other.stubs, other.launchd, other.forbidden = other.tmp / "stubs", other.tmp / "launchd", other.tmp / "forbidden.log"
        shutil.copytree(self.home, other.home, symlinks=True, copy_function=shutil.copy2)
        (other.launchd / "loaded").mkdir(parents=True)
        other.write_launchd()
        for j in JOBS:
            other.plist_path(j).unlink(missing_ok=True)
        return other


def lines(r: subprocess.CompletedProcess, status: str) -> list[str]:
    return [l for l in r.stdout.splitlines() if l.startswith(status + " ")]


def snapshot(root: Path) -> dict:
    """Every file, folder and link under root, with its size, time and content hash."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = p.lstat()
            if p.is_symlink():
                out[str(p)] = ("link", os.readlink(p))
            elif p.is_dir():
                out[str(p)] = ("dir", st.st_mtime_ns, st.st_mode)
            else:
                out[str(p)] = ("file", st.st_size, st.st_mtime_ns, st.st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def manifest_keys(path: Path, project: str) -> list[str]:
    for line in path.read_text().splitlines():
        f = line.split("\t")
        if f[0] == "keys" and f[1] == project:
            return [n for n in f[2].split(",") if n]
    raise AssertionError(f"no keys line for {project}")


@pytest.fixture
def mac(tmp_path):
    m = FakeMac(tmp_path)
    yield m
    assert not m.forbidden.exists(), "the check ran a command that changes things: " + m.forbidden.read_text()


# -- the live Mac ---------------------------------------------------------------------------------------------
def test_live_mac_with_everything_in_place_passes(mac):
    r = mac.run("--role", "live")
    assert r.returncode == 0, r.stdout + r.stderr
    assert lines(r, "FAIL") == []
    for j in JOBS:
        assert f"OK   {j}: loaded, idle, last exit 0; its file points into this repo" in r.stdout
    assert r.stdout.count("the code's own check passes") == 2
    assert "Next kickoff in the ledgers Thu Oct 1, 5:00 PM, College: Western Kentucky at New Mexico State" in r.stdout
    assert "A quiet time to move the jobs" in r.stdout
    assert "records: 4 files in data/forward and 1 saved odds responses, hashed" in r.stdout
    assert "OK   sharp-markets/.env: yours only (mode 600); values set for ODDS_API_KEY, KAGGLE_USERNAME, KAGGLE_KEY" in r.stdout
    assert "Summary:" in r.stdout.splitlines()[-1]


def test_live_mac_missing_a_job_fails(mac):
    mac.unload("com.valuefinder.closecapture")
    mac.plist_path("com.valuefinder.closecapture").unlink()
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert ("FAIL com.valuefinder.closecapture: not installed on this Mac. If this is the Mac that should run the "
            "jobs (and no move is under way), install it:") in r.stdout
    assert "~/code/value-finder/ops/install_close_capture.sh" in r.stdout


def test_live_job_file_there_but_not_loaded_fails(mac):
    mac.unload("com.nflweather.alerts")
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert "FAIL com.nflweather.alerts: its file is there but it is not loaded" in r.stdout


def test_live_job_pointing_at_another_repo_fails(mac, tmp_path):
    other = tmp_path / "elsewhere" / "value-finder"
    mac.install("com.nflweather.alerts", root=other)
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert any("com.nflweather.alerts" in l and "points outside this repo" in l for l in lines(r, "FAIL"))


def test_live_job_pointing_into_a_workers_worktree_fails(mac):
    # the installers take their paths from where they are run, so one run from a worker's worktree points there
    worktree = mac.repo / ".claude" / "worktrees" / "wf_worker-1"
    for p in ("nfl-weather/.venv/bin/python", "nfl-weather/scripts/alerts.py"):
        write(worktree / p, "")
    mac.install("com.nflweather.alerts", root=worktree)
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert any(l.startswith("FAIL com.nflweather.alerts: loaded, idle, last exit 0, but its file points into a "
                            "worker's folder (~/code/value-finder/.claude/worktrees/wf_worker-1/") for l in lines(r, "FAIL"))
    assert "OK   com.nflweather.alerts" not in r.stdout


def test_the_dashboard_pointing_at_the_repo_itself_is_fine(mac):
    mac.install("com.valuefinder.dashboard")
    r = mac.run("--role", "live")
    assert r.returncode == 0, r.stdout
    assert "OK   com.valuefinder.dashboard: loaded, idle, last exit 0; its file points into this repo" in r.stdout


def test_live_job_with_a_failed_last_run_warns(mac):
    mac.load("com.cfbweather.alerts", exit_code=1)
    r = mac.run("--role", "live")
    assert r.returncode == 0
    assert any(l.startswith("WARN com.cfbweather.alerts: loaded, idle, last exit 1") for l in r.stdout.splitlines())


def test_live_uses_print_the_command_that_puts_back_exactly_these(mac):
    env = {"ODDS_QUOTA_KIND": "background", "ODDS_API_TIER": "paid", "ODDS_BACKGROUND_FLOOR": "150000"}
    mac.install("com.valuefinder.triggerpoll", env=env)
    mac.install("com.valuefinder.propslog", env=env)
    r = mac.run("--role", "live")
    out = r.stdout.splitlines()
    i = out.index("OK   Paid-plan live uses installed: triggerpoll propslog. To put back exactly these, with the "
                  "same settings, after removing them (write this down):")
    assert out[i + 1] == ("       ODDS_API_TIER=paid ODDS_BACKGROUND_FLOOR=150000 "
                          "~/code/value-finder/ops/install_live_uses.sh triggerpoll propslog")
    # with other settings in each, one command per job
    mac.install("com.valuefinder.propslog", env={"ODDS_QUOTA_KIND": "background"})
    r = mac.run("--role", "live")
    assert "       ODDS_API_TIER=paid ODDS_BACKGROUND_FLOOR=150000 ~/code/value-finder/ops/install_live_uses.sh triggerpoll" in r.stdout
    assert "       ~/code/value-finder/ops/install_live_uses.sh propslog" in r.stdout


# -- the standby Mac ------------------------------------------------------------------------------------------
def test_standby_mac_running_the_jobs_fails_and_prints_the_unload_commands(mac):
    r = mac.run("--role", "standby")
    assert r.returncode == 1
    out = r.stdout.splitlines()
    i = out.index("FAIL This Mac is not the live one, and it is running the jobs. Unload them now:")
    for n, j in enumerate(JOBS):
        assert out[i + 1 + n] == f"       launchctl bootout gui/{UID}/{j}"
        assert f"       mv ~/Library/LaunchAgents/{j}.plist ~/value-finder-parked-jobs/" in out
    assert "       mkdir -p ~/value-finder-parked-jobs" in out
    for j in JOBS:
        assert f"FAIL {j}: loaded, idle, last exit 0, on a Mac that is not the live one" in out


def test_standby_mac_without_jobs_passes(tmp_path):
    m = FakeMac(tmp_path, jobs="none")
    r = m.run("--role", "standby")
    assert r.returncode == 0, r.stdout
    for j in JOBS:
        assert f"OK   {j}: not installed here, as it should be on a standby Mac" in r.stdout
    assert "This Mac is not the live one" not in r.stdout
    assert not m.forbidden.exists()


def test_standby_job_files_left_in_place_fail_even_when_not_loaded(tmp_path):
    m = FakeMac(tmp_path, jobs="files")
    r = m.run("--role", "standby")
    assert r.returncode == 1
    assert "FAIL This Mac is not the live one, and its job files are in place: they start at the next login." in r.stdout
    assert "launchctl bootout" not in r.stdout
    assert "       mv ~/Library/LaunchAgents/com.nflweather.alerts.plist ~/value-finder-parked-jobs/" in r.stdout
    assert not m.forbidden.exists()


def test_a_credit_spending_live_use_on_the_standby_mac_fails(tmp_path):
    m = FakeMac(tmp_path, jobs="none")
    m.install("com.valuefinder.triggerpoll")
    r = m.run("--role", "standby")
    assert r.returncode == 1
    assert f"       launchctl bootout gui/{UID}/com.valuefinder.triggerpoll" in r.stdout


def test_the_dashboard_is_allowed_on_the_standby_mac(tmp_path):
    m = FakeMac(tmp_path, jobs="none")
    m.install("com.valuefinder.dashboard")
    r = m.run("--role", "standby")
    assert r.returncode == 0, r.stdout
    assert "This Mac is not the live one" not in r.stdout


def test_the_role_is_required(mac):
    r = mac.run()
    assert r.returncode == 2
    assert "--role live" in r.stdout and "--role standby" in r.stdout


# -- keys -----------------------------------------------------------------------------------------------------
def test_no_key_value_reaches_the_output_or_the_manifest(mac, tmp_path):
    # a sign-in helper whose configured text holds a token: only a label may be printed
    write(mac.home / ".gitconfig", '[credential "https://github.com"]\n\thelper = "!f() { echo username=x; '
          f'echo password={HELPER_TOKEN}; }}; f"\n')
    manifest = tmp_path / "laptop.manifest"
    runs = [mac.run("--role", "live", "--manifest", str(manifest)), mac.run("--role", "standby"),
            mac.run("--role", "live", "--compare", str(manifest))]
    text = manifest.read_text()
    for r in runs:
        for s in ALL_SECRETS:
            assert s not in r.stdout and s not in r.stderr, s
            assert s[-8:] not in r.stdout, s
    for s in ALL_SECRETS:
        assert s not in text and s[-8:] not in text, s
    assert "keys\tnfl-weather\tODDS_API_KEY,NTFY_TOPIC" in text.splitlines()
    assert "keys\tcfb-weather\tODDS_API_KEY,CFBD_API_KEY,NTFY_TOPIC" in text.splitlines()
    assert "gh is signed in to GitHub as fakeuser" in runs[0].stdout
    assert "OK   git signs in to GitHub with another helper (its text is not shown)" in runs[0].stdout
    assert "echo username" not in runs[0].stdout
    assert "OK   ODDS_API_KEY is the same in all 3 .env files, as each project reads it" in runs[0].stdout


@pytest.mark.parametrize("helper,label", [("osxkeychain", "the macOS keychain (osxkeychain)"),
                                          ("!/opt/homebrew/bin/gh auth git-credential", "gh (gh auth setup-git)"),
                                          ("store --file /tmp/x", "a plain file on disk (store)")])
def test_the_sign_in_helper_is_shown_as_a_label(mac, helper, label):
    write(mac.home / ".gitconfig", f'[credential "https://github.com"]\n\thelper = "{helper}"\n')
    r = mac.run("--role", "live")
    assert f"OK   git signs in to GitHub with {label} (the nightly ledger copy pushes with it)" in r.stdout
    assert "/opt/homebrew/bin/gh auth" not in r.stdout and "/tmp/x" not in r.stdout


def notify_env_reader():
    """nflweather.notify._env, taken from the project's own source, reading .env from a folder we choose."""
    src = (REPO_ROOT / "nfl-weather" / "nflweather" / "notify.py").read_text()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_env")
    ns = {"os": os}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "notify._env", "exec"), ns)
    return ns


@pytest.mark.parametrize("lines_", [
    ["ODDS_API_KEY=FAKE-odds-7f3a9c11"],
    ["  ODDS_API_KEY='FAKE-odds-7f3a9c11'  "],
    ["export ODDS_API_KEY=FAKE-odds-7f3a9c11"],
    ["ODDS_API_KEY = FAKE-odds-7f3a9c11"],
    ["ODDS_API_KEY=FAKE-odds-7f3a9c11", "ODDS_API_KEY="],          # the last line wins
    ["ODDS_API_KEY=", "ODDS_API_KEY=FAKE-odds-7f3a9c11"],
    ["# ODDS_API_KEY=FAKE-odds-7f3a9c11"],
    ['ODDS_API_KEY=""'],
])
def test_the_check_reads_a_weather_env_file_the_way_the_project_does(mac, tmp_path, lines_):
    env = mac.repo / "nfl-weather" / ".env"
    env.write_text("\n".join(lines_ + [f"NTFY_TOPIC={SECRETS['nfl-weather']['NTFY_TOPIC']}"]) + "\n")
    ns = notify_env_reader()
    ns["ROOT"] = mac.repo / "nfl-weather"
    saved = os.environ.pop("ODDS_API_KEY", None)
    try:
        project_has_it = ns["_env"]("ODDS_API_KEY") is not None
    finally:
        if saved is not None:
            os.environ["ODDS_API_KEY"] = saved
    manifest = tmp_path / "m.manifest"
    r = mac.run("--role", "live", "--manifest", str(manifest))
    assert ("ODDS_API_KEY" in manifest_keys(manifest, "nfl-weather")) == project_has_it, r.stdout
    assert (r.returncode == 0) == project_has_it
    assert SECRETS["nfl-weather"]["ODDS_API_KEY"] not in r.stdout


def test_export_and_spaced_lines_fail_in_a_weather_project(mac):
    (mac.repo / "cfb-weather" / ".env").write_text(
        f"export ODDS_API_KEY={SECRETS['cfb-weather']['ODDS_API_KEY']}\nCFBD_API_KEY=x\n"
        f"NTFY_TOPIC = {SECRETS['cfb-weather']['NTFY_TOPIC']}\n")
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert ("FAIL cfb-weather/.env writes ODDS_API_KEY NTFY_TOPIC as 'export NAME=…' or 'NAME = …'. This project "
            "reads only lines of the form NAME=value, so to it there is no value.") in r.stdout
    assert "OK   cfb-weather/.env" not in r.stdout


def test_a_comment_after_a_weather_key_fails(mac):
    (mac.repo / "nfl-weather" / ".env").write_text(
        f"ODDS_API_KEY={SECRETS['nfl-weather']['ODDS_API_KEY']}   # the paid key\nNTFY_TOPIC=t\n")
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert "FAIL nfl-weather/.env has a space inside the value of: ODDS_API_KEY (a comment after it?)" in r.stdout
    assert "the paid key" not in r.stdout


def test_env_file_readable_by_others_or_missing_a_key_fails(mac):
    env = mac.repo / "nfl-weather" / ".env"
    env.write_text(f"ODDS_API_KEY={SECRETS['nfl-weather']['ODDS_API_KEY']}\nNTFY_TOPIC=   # none yet\n")
    env.chmod(0o644)
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert "FAIL nfl-weather/.env can be read by others (mode 644). Make it yours only:" in r.stdout
    assert "       chmod 600 ~/code/value-finder/nfl-weather/.env" in r.stdout
    assert "FAIL nfl-weather/.env has no value for: NTFY_TOPIC (the jobs need it)" in r.stdout
    assert SECRETS["nfl-weather"]["ODDS_API_KEY"] not in r.stdout


def test_an_env_file_nobody_can_read_is_not_called_readable_by_others(mac):
    (mac.repo / "nfl-weather" / ".env").chmod(0o000)
    try:
        r = mac.run("--role", "live")
    finally:
        (mac.repo / "nfl-weather" / ".env").chmod(0o600)
    assert r.returncode == 1
    assert "can be read by others" not in r.stdout
    assert "FAIL nfl-weather/.env can't be read, even by you (mode 0). Make it readable by you only:" in r.stdout


def test_a_different_odds_key_in_one_project_warns(mac):
    (mac.repo / "sharp-markets" / ".env").write_text("ODDS_API_KEY=FAKE-other-key-123\n")
    r = mac.run("--role", "live")
    assert any(l.startswith("WARN ODDS_API_KEY is not the same in every .env file") for l in r.stdout.splitlines())
    assert "FAKE-other-key-123" not in r.stdout


def test_missing_env_file_and_kaggle_token_mode(mac):
    (mac.repo / "cfb-weather" / ".env").unlink()
    (mac.home / ".kaggle" / "access_token").chmod(0o644)
    r = mac.run("--role", "live")
    assert "FAIL cfb-weather/.env is missing. Copy it from the other Mac (never by AirDrop or a cloud drive)" in r.stdout
    assert "FAIL ~/.kaggle/access_token has mode 644, not 600:" in r.stdout
    assert KAGGLE_TOKEN not in r.stdout


# -- registered files -----------------------------------------------------------------------------------------
def test_the_cohort_check_uses_the_code_and_creates_no_folder(mac):
    r = mac.run("--role", "live")
    assert "OK   nfl-weather: the code's own check passes (4 games; registered hash " + COHORT_HASH[:12] in r.stdout
    assert not (mac.repo / "nfl-weather" / "data" / "raw" / "made-by-config-import").exists()
    assert not (mac.repo / "cfb-weather" / "data" / "raw" / "made-by-config-import").exists()


def test_an_unregistered_cohort_fails(mac):
    board = mac.repo / "cfb-weather" / "cfbweather" / "board.py"
    board.write_text('PRICING_COHORT_SHA256 = "' + "0" * 64 + '"\n')
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert "FAIL cfb-weather: the pricing cohort is not the registered one" in r.stdout


def test_a_changed_cohort_file_fails(mac):
    (mac.repo / "nfl-weather" / "data" / "processed" / "pricing_cohort.json").write_text('{"residuals": [9.0]}')
    r = mac.run("--role", "live")
    fails = lines(r, "FAIL")
    assert "FAIL nfl-weather: pricing_cohort.json differs from the committed file. Changing it needs a dated amendment" in fails
    assert any(l.startswith("FAIL nfl-weather: the pricing cohort is not the registered one") for l in fails)


# -- manifest and compare -------------------------------------------------------------------------------------
RECORDS_OK = "OK   Records: all {n} forward-test records are here, the same byte for byte as on the other Mac"


def test_compare_finds_a_changed_ledger_a_missing_file_and_an_extra_file(mac, tmp_path):
    manifest = tmp_path / "laptop.manifest"
    assert mac.run("--role", "live", "--manifest", str(manifest)).returncode == 0
    fwd = mac.repo / "nfl-weather" / "data" / "forward"
    with open(fwd / "ledger.csv", "a") as f:
        f.write("2026-09-30T18:30:00Z,v3-2026-09-28,2026_05_DET_CAR,2026-10-04,13:00,DET,CAR\n")
    (mac.repo / "cfb-weather" / "data" / "forward" / "runs.csv").unlink()
    write(fwd / "alert_state.corrupt-20260930T1830Z.json", "{")
    (mac.home / ".cache" / "value-finder" / "mos" / "b.csv").unlink()
    r = mac.run("--role", "live", "--compare", str(manifest))
    assert r.returncode == 1
    fails = lines(r, "FAIL")
    assert any(l.startswith("FAIL Record differs from the other Mac: nfl-weather/data/forward/ledger.csv") for l in fails)
    assert "FAIL Record missing here: cfb-weather/data/forward/runs.csv" in fails
    assert ("FAIL Record here that the other Mac does not have: "
            "nfl-weather/data/forward/alert_state.corrupt-20260930T1830Z.json") in fails
    assert any(l.startswith("WARN Folder differs: ~/.cache/value-finder has 2 files") for l in r.stdout.splitlines())
    assert "OK   Records: all" not in r.stdout
    assert "OK   Same as the manifest" not in r.stdout


def test_compare_with_a_faithful_copy_passes_and_a_lost_file_time_warns(mac, tmp_path):
    manifest = tmp_path / "laptop.manifest"
    assert mac.run("--role", "live", "--manifest", str(manifest)).returncode == 0
    n = sum(1 for l in manifest.read_text().splitlines() if l.startswith("record\t"))
    studio = mac.copy_to(tmp_path)
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 0, r.stdout
    assert RECORDS_OK.format(n=n) in r.stdout
    assert any(l.startswith("OK   Same as the manifest written 2026-09-30T16:30:00Z on Mac Studio") for l in r.stdout.splitlines())
    assert f": {n} records byte for byte, 0 paid files, 4 folders, the cohorts, the key names and the commit" in r.stdout
    os.utime(studio.repo / "cfb-weather" / "data" / "forward" / "ledger.csv", (NOW - 3600, NOW - 3600))
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 0
    assert ("WARN Record has the same content but another file time: cfb-weather/data/forward/ledger.csv "
            "(copied without keeping times?)") in r.stdout
    assert RECORDS_OK.format(n=n) in r.stdout


def test_compare_ignores_a_write_in_progress(mac, tmp_path):
    # runlog.py and board.py write ledger.csv.tmp and the like, then rename it; a copy can catch one
    manifest = tmp_path / "laptop.manifest"
    write(mac.repo / "nfl-weather" / "data" / "forward" / "runs.csv.tmp", "half a row")
    assert mac.run("--role", "live", "--manifest", str(manifest)).returncode == 0
    assert ".tmp" not in manifest.read_text()
    studio = mac.copy_to(tmp_path)
    (studio.repo / "nfl-weather" / "data" / "forward" / "runs.csv.tmp").unlink()
    write(studio.repo / "cfb-weather" / "data" / "forward" / "ledger.csv.tmp", "stale")
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 0, r.stdout
    assert "OK   Same as the manifest written" in r.stdout


def test_compare_fails_when_the_two_macs_are_at_other_commits(mac, tmp_path):
    manifest = tmp_path / "laptop.manifest"
    assert mac.run("--role", "live", "--manifest", str(manifest)).returncode == 0
    studio = mac.copy_to(tmp_path)
    write(studio.repo / "ops" / "new_script.sh", "#!/bin/bash\n")
    git(studio.repo, "add", "-A")
    git(studio.repo, "commit", "-q", "-m", "a newer commit")
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 1
    assert any(l.startswith("FAIL The repo is at another commit here (") and "git pull --ff-only on both Macs" in l
               for l in lines(r, "FAIL"))
    assert "OK   Same as the manifest" not in r.stdout


def test_compare_fails_when_a_copy_changed_a_file_git_tracks(mac, tmp_path):
    # what 'rsync -a laptop/data/ studio/data/' does when the laptop's data/processed is older than the Studio's
    manifest = tmp_path / "laptop.manifest"
    assert mac.run("--role", "live", "--manifest", str(manifest)).returncode == 0
    studio = mac.copy_to(tmp_path)
    write(studio.repo / "nfl-weather" / "data" / "processed" / "games.csv", "game_id,total\nA,40.5\n")
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 1
    assert any(l.startswith("FAIL Not clean: 1 files that git tracks are changed here") for l in lines(r, "FAIL"))
    assert "        M nfl-weather/data/processed/games.csv" in r.stdout
    # without --compare the same state is only a warning (the hub's own edits can leave the checkout unclean)
    r = studio.run("--role", "standby")
    assert any(l.startswith("WARN Not clean: 1 changed") for l in r.stdout.splitlines())


def test_compare_checks_every_paid_file(mac, tmp_path):
    paid = mac.add_paid()
    manifest = tmp_path / "laptop.manifest"
    r = mac.run("--role", "live", "--manifest", str(manifest))
    assert "OK   Paid odds data (not a cache: it can't be had again without paying): 4 files" in r.stdout
    assert sum(1 for l in manifest.read_text().splitlines() if l.startswith("paid\t")) == 4
    studio = mac.copy_to(tmp_path)
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 0, r.stdout
    assert "OK   Paid odds data: all 4 files are here, each the same size as on the other Mac" in r.stdout
    # a copy cut short: one file missing, one cut
    rel = [p.relative_to(mac.repo) for p in paid]
    (studio.repo / rel[0]).unlink()
    with open(studio.repo / rel[1], "r+b") as f:
        f.truncate(10)
    r = studio.run("--role", "standby", "--compare", str(manifest))
    assert r.returncode == 1
    assert f"FAIL Paid odds file missing here: {rel[0]}" in r.stdout
    assert any(l.startswith(f"FAIL Paid odds file has another size here: {rel[1]} (10 bytes here") for l in lines(r, "FAIL"))


def test_compare_with_something_that_is_not_a_manifest_proves_nothing(mac, tmp_path):
    other = write(tmp_path / "studio.manifest", "")
    r = mac.run("--role", "standby", "--compare", str(other))
    assert r.returncode == 1
    assert "OK   Records: all" not in r.stdout


def test_a_manifest_is_not_written_over_another_file(mac, tmp_path):
    other = write(tmp_path / "notes.txt", "my notes\n")
    r = mac.run("--role", "live", "--manifest", str(other))
    assert r.returncode == 1
    assert other.read_text() == "my notes\n"


def test_record_names_the_manifest_cannot_hold_fail(mac, tmp_path):
    fwd = mac.repo / "nfl-weather" / "data" / "forward"
    for name in ("with\ttab.csv", "with\nnewline.csv", "back\\slash.csv", "with space.csv"):
        write(fwd / name, "x\n")
    manifest = tmp_path / "laptop.manifest"
    r = mac.run("--role", "live", "--manifest", str(manifest))
    assert r.returncode == 1
    assert ("FAIL 3 record or paid files have a tab, a line break or a backslash in their name (shown as ?), so the "
            "check can't fingerprint them. Tell the hub:") in r.stdout
    assert "       nfl-weather/data/forward/with?tab.csv" in r.stdout
    for line in manifest.read_text().splitlines():
        if line.startswith("record\t"):
            f = line.split("\t")
            assert len(f) == 5 and re.fullmatch(r"[0-9a-f]{64}", f[2]), line
    assert "record\tnfl-weather/data/forward/with space.csv\t" in manifest.read_text()


def test_a_linked_record_folder_fails(mac, tmp_path):
    fwd = mac.repo / "nfl-weather" / "data" / "forward"
    elsewhere = tmp_path / "elsewhere-forward"
    shutil.move(str(fwd), str(elsewhere))
    fwd.symlink_to(elsewhere)
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert any(l.startswith("FAIL nfl-weather/data/forward is a link to another place") for l in lines(r, "FAIL"))


def test_a_linked_data_folder_fails(mac, tmp_path):
    cache = mac.home / ".cache" / "value-finder"
    elsewhere = tmp_path / "elsewhere-cache"
    shutil.move(str(cache), str(elsewhere))
    cache.symlink_to(elsewhere)
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert any(l.startswith("FAIL ~/.cache/value-finder is a link to another place") for l in lines(r, "FAIL"))


# -- the check changes nothing --------------------------------------------------------------------------------
def test_the_check_changes_nothing(mac, tmp_path):
    for proj in ("nfl-weather", "cfb-weather", "sharp-markets", "dashboard"):
        write(mac.repo / proj / "pytest.py", 'print("3 passed in 0.01s")\n')
    mac.add_paid()
    manifest = tmp_path / "outside-home.manifest"
    mac.run("--role", "live", "--manifest", str(manifest))
    before = snapshot(mac.home)
    for args in (["--role", "live"], ["--role", "standby"], ["--role", "live", "--tests"],
                 ["--role", "standby", "--compare", str(manifest)]):
        mac.run(*args)
    assert snapshot(mac.home) == before
    assert list((mac.home / "tmp").iterdir()) == []


# -- tests, clock, power, disk --------------------------------------------------------------------------------
def test_tests_option_reports_each_suite(mac):
    for proj in ("nfl-weather", "sharp-markets", "dashboard"):
        write(mac.repo / proj / "pytest.py", 'print("12 passed, 1 skipped in 0.50s")\n')
    write(mac.repo / "cfb-weather" / "pytest.py",
          'print("FAILED tests/test_x.py::test_y - boom")\nprint("1 failed, 2 passed in 0.02s")\nraise SystemExit(1)\n')
    r = mac.run("--role", "live", "--tests")
    assert any(l.startswith("OK   nfl-weather tests: 12 passed, 1 skipped (") for l in r.stdout.splitlines())
    assert any(l.startswith("FAIL cfb-weather tests: 1 failed, 2 passed (") for l in r.stdout.splitlines())
    assert "       FAILED tests/test_x.py::test_y - boom" in r.stdout
    assert r.returncode == 1


def test_the_optional_dashboard_without_an_environment_only_warns(mac):
    for proj in ("nfl-weather", "cfb-weather", "sharp-markets"):
        write(mac.repo / proj / "pytest.py", 'print("3 passed in 0.01s")\n')
    shutil.rmtree(mac.repo / "dashboard" / ".venv")
    r = mac.run("--role", "live", "--tests")
    assert r.returncode == 0, r.stdout
    assert "WARN dashboard tests: not run (no working environment)" in r.stdout


def test_a_time_zone_other_than_pacific_fails(mac):
    mac.tz = "Europe/London"
    r = mac.run("--role", "live")
    assert r.returncode == 1
    assert any(l.startswith("FAIL Time zone is Europe/London, not America/Los_Angeles") for l in lines(r, "FAIL"))


@pytest.mark.parametrize("free_kb,status", [(5_000_000, "FAIL"), (30_000_000, "WARN"), (200_000_000, "OK  ")])
def test_disk_space(mac, free_kb, status):
    mac.free_kb = free_kb
    r = mac.run("--role", "live")
    assert any(l.startswith(status) and "free on the disk" in l for l in r.stdout.splitlines())


def test_sleep_and_restart_on_the_live_mac(mac):
    mac.ac_sleep = 10
    r = mac.run("--role", "live")
    assert "WARN Goes to sleep after 10 min without use." in r.stdout
    mac.ac_sleep, mac.laptop = 0, True
    r = mac.run("--role", "live")
    assert "WARN This Mac is a laptop: it sleeps when its lid is closed, and on battery after 1 min." in r.stdout
    mac.laptop, mac.autorestart = False, "0"
    r = mac.run("--role", "live")
    assert "WARN Will not start again by itself after a power cut" in r.stdout
    mac.autorestart = None                     # a desktop whose pmset -g has no autorestart line
    r = mac.run("--role", "live")
    assert "WARN Could not read whether this Mac starts again by itself after a power cut." in r.stdout
    mac.laptop = True                          # a laptop has no such setting to read: nothing said
    r = mac.run("--role", "live")
    assert "power cut" not in r.stdout


def at(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


def test_quiet_time(mac):
    r = mac.run("--role", "live", now=at(2026, 9, 30, 17, 59))                 # 10:59 AM Pacific: 11:30 in 31 min
    assert ("Not a quiet time to move the jobs: a run starts within 90 minutes, and a run due while no Mac has the "
            "jobs doesn't happen") in r.stdout
    r = mac.run("--role", "live", now=at(2026, 9, 30, 16, 1))                  # 9:01 AM: 11:30 in 2 h 29 min
    assert "A quiet time to move the jobs" in r.stdout
    r = mac.run("--role", "live", now=at(2026, 10, 1, 5, 30))                  # 10:30 PM Wed: the 23:45 ledger copy
    assert "Next run by the clock 23:45 (the nightly ledger copy) (in 1 h 15 min)." in r.stdout
    assert "Not a quiet time to move the jobs" in r.stdout
    r = mac.run("--role", "live", now=at(2026, 10, 1, 19, 30))                 # 12:30 PM Thu, kickoff at 5
    assert "Not a quiet time to move the jobs: a game kicks off within 3 hours" not in r.stdout
    r = mac.run("--role", "live", now=at(2026, 10, 1, 21, 30))                 # 2:30 PM Thu: 15:30 run, kickoff at 5
    assert ("Not a quiet time to move the jobs: a run starts within 90 minutes, and a run due while no Mac has the "
            "jobs doesn't happen, and a game kicks off within 3 hours") in r.stdout
    assert r.returncode == 0


def test_no_upcoming_kickoff_is_not_called_quiet(mac):
    r = mac.run("--role", "live", now=at(2026, 10, 20, 16, 30))                # every ledger game is in the past
    assert ("No upcoming kickoff in this Mac's ledgers, so the check can't tell when the next game is. Not known to "
            "be a quiet time") in r.stdout
    assert "A quiet time to move the jobs" not in r.stdout


# -- the owner's page -----------------------------------------------------------------------------------------
LAPTOP = "maxzipperman@MacBook-Air-2.local"
REMOTE_PATHS = ("code/value-finder/", ".cache/value-finder", ".kaggle/access_token",
                ".claude/projects/-Users-maxzipperman-code-value-finder/memory/", "laptop.manifest", "studio.manifest")


def page_commands() -> list[str]:
    out, inside = [], False
    for raw in PAGE.read_text().splitlines():
        s = raw.strip()
        if s.startswith("```"):
            inside = not inside
            continue
        if inside and s:
            out.append(s)
    return out


def test_every_code_box_on_the_page_holds_one_command_without_a_comment():
    text = PAGE.read_text()
    for block in re.findall(r"```\n(.*?)```", text, flags=re.S):
        assert len([l for l in block.splitlines() if l.strip()]) == 1, block
    for c in page_commands():
        assert " #" not in c, c                    # zsh, the Terminal's shell, doesn't take comments by default


@pytest.mark.parametrize("shell", [["/bin/zsh", "-f"], ["/bin/bash", "--norc", "--noprofile"]])
def test_the_page_copy_commands_reach_the_laptop(shell, tmp_path):
    # zsh reads "$LAPTOP:c..." as $LAPTOP with a modifier; each command must name the laptop exactly
    assert not [c for c in page_commands() if "$LAPTOP:" in c]
    cmds =[c for c in page_commands() if c.startswith("rsync ") and "LAPTOP" in c]
    assert len(cmds) >= 15
    assert f"LAPTOP={LAPTOP}" in page_commands()
    script = (f"LAPTOP={LAPTOP}\n"
              'rsync() { for a in "$@"; do printf "%s\\n" "$a"; done; printf -- "--END--\\n"; }\n' + "\n".join(cmds) + "\n")
    r = subprocess.run([*shell, "-c", script], capture_output=True, text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    groups = [g.strip().splitlines() for g in r.stdout.split("--END--") if g.strip()]
    assert len(groups) == len(cmds)
    for cmd, args in zip(cmds, groups):
        remote = [a for a in args if "@" in a]
        local = [a for a in args if not a.startswith("-") and "@" not in a and a not in ("/processed/", "*.tmp")
                 and not a.startswith("/raw/")]
        assert len(remote) == 1 and len(local) == 1, (cmd, args)
        assert remote[0].startswith(LAPTOP + ":"), (cmd, remote)
        assert remote[0][len(LAPTOP) + 1:].startswith(REMOTE_PATHS), (cmd, remote)
        assert local[0].startswith(str(tmp_path) + "/"), (cmd, local)       # ~ became the home folder


def test_the_page_copies_leave_out_what_git_holds_and_writes_in_progress():
    cmds = [c for c in page_commands() if c.startswith("rsync ")]
    for c in cmds:
        if "/data/" in c or c.endswith(".cache/value-finder/"):       # every folder of data, both ways
            assert "--exclude '*.tmp'" in c, c
        if re.search(r'"\$\{LAPTOP\}:code/value-finder/(nfl|cfb)-weather/data/"', c):
            assert "--exclude '/processed/'" in c, c
        if "nfl-weather/data/\"" in c and c.index("${LAPTOP}") < c.index("~/"):
            assert "--exclude '/raw/odds/sbr_open_close.parquet'" in c, c
        assert "--delete" not in c, c


def test_hub_check_in_only_reports():
    hub = (REPO_ROOT / ".claude" / "commands" / "hub.md").read_text()
    line = next(l for l in hub.splitlines() if "ops/mac_check.sh" in l)
    assert "never installs, reinstalls or unloads a job" in line
    assert "origin/main" in line and "move" in line
