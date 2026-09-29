"""READ-ONLY: every endpoint, run against a temp copy of the fixtures, changes no file under the root or the
home folder (names, sizes, modification times) and creates nothing new."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from conftest import ENDPOINTS, Running, copy_content, make_home, make_root, make_store

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


def test_real_scorer_subprocess_changes_nothing(tmp_path):
    """The scorer path with a real child process: a stand-in scorer that only prints. Its folder and the data
    root are unchanged afterwards, and no bytecode is written (PYTHONDONTWRITEBYTECODE)."""
    root, home = make_root(tmp_path / "f"), make_home(tmp_path / "f")
    scorers = tmp_path / "scorers"
    for project in commands.PROJECTS:
        (scorers / project / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, scorers / project / ".venv" / "bin" / "python")
        (scorers / project / "scripts").mkdir()
        (scorers / project / "scripts" / "score_forward.py").write_text(
            "import sys, json\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "import helper\nprint('args', json.dumps(sys.argv[1:]))\n")
        (scorers / project / "helper.py").write_text("X = 1\n")
    before = state(root, home, scorers)
    cfg_store = make_store(root, home, scorer_root=scorers, runner=None)
    # the real runner: commands.run, with the allow-list check
    cfg_store.runner = lambda cmd, cwd, timeout: commands.run(cmd, cwd, cfg_store.allowed, timeout)
    res = cfg_store.scorer("nfl-weather", wait=True)
    assert res.status == "ok", (res.status, res.error)
    assert '"--now"' in res.text and str(root / "nfl-weather" / "data" / "forward" / "ledger.csv") in res.text
    assert state(root, home, scorers) == before
