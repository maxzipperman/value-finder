"""The only programs the dashboard can start, built from fixed lists.

* each project's scorer, `scripts/score_forward.py`, always with `--now` (a preview, which can never
  record a decision), run by that project's own Python with the project folder as the working directory;
* `launchctl list`;
* `launchctl print gui/<uid>/<label>` for the four scheduled jobs.

Nothing a browser sends reaches a command: the scorer's paths come from the server's own settings, its
time from the server's clock, and a label from JOB_LABELS. `run()` checks every command against
`allowed()` before it starts anything, and never uses a shell.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LAUNCHCTL = "/bin/launchctl"
PROJECTS = ("nfl-weather", "cfb-weather")
JOB_LABELS = ("com.nflweather.alerts", "com.cfbweather.alerts", "com.valuefinder.closecapture",
              "com.valuefinder.ledgersync")
SCORER = "scripts/score_forward.py"
SCORER_TIMEOUT = 60
LAUNCHCTL_TIMEOUT = 10
NOW_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


# Importing a scorer's package creates these folders in its project when they are missing (the for loop at the
# end of nflweather/config.py and cfbweather/config.py). The dashboard never writes, so it starts a scorer only
# when every one of them is already there; a test checks this list against both config.py files.
SCORER_FOLDERS = {
    "nfl-weather": ("data/raw", "data/processed", "output/tables", "output/figures", "data/raw/pbp",
                    "data/raw/weather"),
    "cfb-weather": ("data/raw", "data/processed", "output/tables", "data/raw/meteostat", "data/raw/cfbfastr"),
}


def scorer_python(scorer_root: Path, project: str) -> Path:
    return scorer_root / project / ".venv" / "bin" / "python"


def folders_a_scorer_would_create(scorer_root: Path, project: str) -> list[str]:
    """The folders (as project/relative/path) that starting this scorer would create; [] when none, and when
    there is no scorer to start (run() then reports it missing)."""
    if not (scorer_root / project / SCORER).is_file():
        return []
    return [f"{project}/{rel}" for rel in SCORER_FOLDERS[project] if not (scorer_root / project / rel).is_dir()]


def scorer_command(scorer_root: Path, data_root: Path, project: str, now: datetime) -> tuple[list[str], str]:
    """(command, working directory) for a scorer preview on `data_root`'s ledger at `now`."""
    if project not in PROJECTS:
        raise ValueError(f"no scorer for {project!r}")
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    cmd = [str(scorer_python(scorer_root, project)), SCORER,
           "--ledger", str(data_root / project / "data" / "forward" / "ledger.csv"),
           "--now", stamp]
    return cmd, str(scorer_root / project)


def launchctl_list_command() -> list[str]:
    return [LAUNCHCTL, "list"]


def launchctl_print_command(label: str) -> list[str]:
    if label not in JOB_LABELS:
        raise ValueError(f"not a Value Finder job: {label!r}")
    return [LAUNCHCTL, "print", f"gui/{os.getuid()}/{label}"]


@dataclass(frozen=True)
class Allowed:
    scorer_root: Path
    data_root: Path

    def check(self, cmd: list[str], cwd: str | None) -> bool:
        """True only for a command built by one of the functions above, with these settings."""
        if not isinstance(cmd, list) or not all(isinstance(c, str) for c in cmd):
            return False
        if cmd == launchctl_list_command():
            return cwd is None
        if len(cmd) == 3 and cmd[:2] == [LAUNCHCTL, "print"]:
            return cwd is None and cmd[2] in {f"gui/{os.getuid()}/{label}" for label in JOB_LABELS}
        for project in PROJECTS:
            if (len(cmd) == 6 and cmd[0] == str(scorer_python(self.scorer_root, project)) and cmd[1] == SCORER
                    and cmd[2] == "--ledger"
                    and cmd[3] == str(self.data_root / project / "data" / "forward" / "ledger.csv")
                    and cmd[4] == "--now" and NOW_FORMAT.match(cmd[5])
                    and cwd == str(self.scorer_root / project)):
                return True
        return False


@dataclass
class Result:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    code: int | None = None
    timed_out: bool = False
    missing: bool = False
    seconds: float = 0.0


def clean_env() -> dict:
    """A small environment: no keys or tokens from the dashboard's own environment reach a child, and
    Python writes no bytecode files into the project folders."""
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}


def run(cmd: list[str], cwd: str | None, allowed: Allowed, timeout: int) -> Result:
    """Start one allowed command, without a shell, and wait at most `timeout` seconds."""
    if not allowed.check(cmd, cwd):
        raise PermissionError(f"not an allowed command: {cmd!r}")
    if not Path(cmd[0]).exists() or (cwd is not None and not Path(cwd).is_dir()):
        return Result(ok=False, missing=True)
    start = datetime.now(timezone.utc)
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=False,
                           stdin=subprocess.DEVNULL, env=clean_env(), errors="replace")
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return Result(ok=False, stdout=out, timed_out=True, seconds=float(timeout))
    except OSError as e:
        return Result(ok=False, stderr=f"{type(e).__name__}: {e.strerror or e}", missing=True)
    secs = (datetime.now(timezone.utc) - start).total_seconds()
    return Result(ok=p.returncode == 0, stdout=p.stdout, stderr=p.stderr, code=p.returncode, seconds=secs)
