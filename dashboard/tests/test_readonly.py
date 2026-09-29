"""READ-ONLY: every endpoint, run against a temp copy of the fixtures, changes no file under the root or the
home folder (names, sizes, modification times) and creates nothing new."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from conftest import ENDPOINTS, FakeRunner, Running, copy_content, make_home, make_root, make_store

from vfdash import commands


def state(*dirs: Path) -> dict:
    out = {}
    for d in dirs:
        for dirpath, dirnames, filenames in os.walk(d):
            for name in dirnames + filenames:
                p = Path(dirpath) / name
                st = os.lstat(p)
                out[str(p)] = (st.st_size if not p.is_dir() else 0, st.st_mtime_ns, st.st_mode)
    return out


def test_every_endpoint_changes_nothing(tmp_path):
    fixtures = tmp_path / "fixtures"
    make_root(fixtures)
    make_home(fixtures)
    copy = tmp_path / "copy"
    shutil.copytree(fixtures, copy, symlinks=True)
    root, home = copy / "repo", copy / "home"
    content = copy_content(tmp_path / "content")
    before = state(root, home, content)
    store = make_store(root, home, content=content)
    served = Running(store)
    try:
        for _ in range(2):
            for path in ENDPOINTS + ["/", "/static/app.js", "/static/app.css", "/api/game?id=..%2F..%2Fetc",
                                     "/api/nope", "/static/../STATUS.md"]:
                served.get(path)
    finally:
        served.close()
    assert state(root, home, content) == before


def stand_in_scorers(scorers: Path, folders: bool = True):
    """A stand-in for each project's scorer that, like the real ones (their config.py), creates its project's
    folders when it is imported and they are missing, then prints its arguments."""
    for project in commands.PROJECTS:
        (scorers / project / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, scorers / project / ".venv" / "bin" / "python")
        (scorers / project / "scripts").mkdir()
        (scorers / project / "scripts" / "score_forward.py").write_text(
            "import sys, json\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "import helper\nprint('args', json.dumps(sys.argv[1:]))\n")
        (scorers / project / "helper.py").write_text(
            "from pathlib import Path\nROOT = Path(__file__).resolve().parent\n"
            f"for rel in {commands.SCORER_FOLDERS[project]!r}:\n    (ROOT / rel).mkdir(parents=True, exist_ok=True)\n")
        if folders:
            for rel in commands.SCORER_FOLDERS[project]:
                (scorers / project / rel).mkdir(parents=True, exist_ok=True)


def real_runner_store(root, home, scorers):
    store = make_store(root, home, scorer_root=scorers, runner=None)
    launchd = FakeRunner()                            # the Mac's own launchd is never asked in a test

    def runner(cmd, cwd, timeout):                    # the scorers: commands.run, with the allow-list check
        if cmd[0] == commands.LAUNCHCTL:
            return launchd(cmd, cwd, timeout)
        return commands.run(cmd, cwd, store.allowed, timeout)
    store.runner = runner
    return store


def test_real_scorer_subprocess_changes_nothing(tmp_path):
    """The scorer path with a real child process: a stand-in scorer that only prints. Its folder and the data
    root are unchanged afterwards, and no bytecode is written (PYTHONDONTWRITEBYTECODE)."""
    root, home = make_root(tmp_path / "f"), make_home(tmp_path / "f")
    scorers = tmp_path / "scorers"
    stand_in_scorers(scorers)
    before = state(root, home, scorers)
    store = real_runner_store(root, home, scorers)
    res = store.scorer("nfl-weather", wait=True)
    assert res.status == "ok", (res.status, res.error)
    assert '"--now"' in res.text and str(root / "nfl-weather" / "data" / "forward" / "ledger.csv") in res.text
    assert state(root, home, scorers) == before


def test_a_scorer_that_would_create_folders_is_not_started(tmp_path):
    """Importing a real scorer creates its project's data and output folders when they are missing. The
    dashboard then doesn't start it, says why in plain words, and nothing is created."""
    root, home = make_root(tmp_path / "f"), make_home(tmp_path / "f")
    scorers = tmp_path / "scorers"
    stand_in_scorers(scorers, folders=False)
    (scorers / "nfl-weather" / "data" / "raw").mkdir(parents=True)          # one of them is there
    before = state(root, home, scorers)
    store = real_runner_store(root, home, scorers)
    from vfdash import api
    d = api.tests_screen(store)
    assert state(root, home, scorers) == before
    for g in d["groups"]:
        s = g["scorer"]
        assert s["status"] == "skipped" and s["text"] == "" and s["ran"] is None
        assert "was not started" in s["words"] and "never changes the project folders" in s["words"]
    nfl = d["groups"][0]["scorer"]["words"]
    assert "nfl-weather/output/figures" in nfl and "nfl-weather/data/raw," not in nfl
    started = [t for t in d["groups"][1]["tests"] if t["started"]]
    assert started and started[0]["progress"] == "The scorer was not started; 1 signal logged (from the ledger)"
