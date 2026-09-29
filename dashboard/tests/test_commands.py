"""Every command the dashboard can start is in the fixed list, and each scorer command contains --now."""
from __future__ import annotations

import ast
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import ENDPOINTS, Running, make_store

from vfdash import commands

PKG = Path(__file__).resolve().parents[1] / "vfdash"
NOW = datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc)


def test_every_command_started_is_allowed(store, runner):
    served = Running(store)
    try:
        for path in ENDPOINTS:
            served.get(path)
    finally:
        served.close()
    assert runner.calls
    uid = os.getuid()
    allowed_exact = [["/bin/launchctl", "list"]] + [["/bin/launchctl", "print", f"gui/{uid}/{label}"]
                                                     for label in commands.JOB_LABELS]
    for cmd, cwd, timeout in runner.calls:
        assert store.allowed.check(cmd, cwd), cmd
        if cmd[0] == "/bin/launchctl":
            assert cmd in allowed_exact and cwd is None
        else:
            assert cmd[1] == "scripts/score_forward.py"
            assert "--now" in cmd and cmd[cmd.index("--now") + 1]
            assert cmd[cmd.index("--ledger") + 1].startswith(str(store.cfg.root))
            assert timeout == 60
    assert any(c[0][1:2] == ["list"] for c in runner.calls)
    assert sum(1 for c in runner.calls if "--now" in c[0]) == 2


def test_scorer_command_shape(tmp_path):
    for project in commands.PROJECTS:
        cmd, cwd = commands.scorer_command(tmp_path / "code", tmp_path / "data", project, NOW)
        assert cmd == [str(tmp_path / "code" / project / ".venv" / "bin" / "python"), "scripts/score_forward.py",
                       "--ledger", str(tmp_path / "data" / project / "data" / "forward" / "ledger.csv"),
                       "--now", "2026-10-02T17:00:00"]
        assert cwd == str(tmp_path / "code" / project)
    with pytest.raises(ValueError):
        commands.scorer_command(tmp_path, tmp_path, "sharp-markets", NOW)
    with pytest.raises(ValueError):
        commands.launchctl_print_command("com.apple.Finder")


@pytest.mark.parametrize("cmd", [
    ["/bin/launchctl", "load", "x.plist"],
    ["/bin/launchctl", "bootout", f"gui/{os.getuid()}/com.nflweather.alerts"],
    ["/bin/launchctl", "kickstart", f"gui/{os.getuid()}/com.nflweather.alerts"],
    ["/bin/launchctl", "print", f"gui/{os.getuid()}/com.apple.Finder"],
    ["/bin/launchctl", "list", "extra"],
    ["launchctl", "list"],
    ["/bin/sh", "-c", "launchctl list"],
    ["git", "status"],
])
def test_other_commands_are_refused(tmp_path, cmd):
    allowed = commands.Allowed(tmp_path, tmp_path)
    assert not allowed.check(cmd, None)
    with pytest.raises(PermissionError):
        commands.run(cmd, None, allowed, 5)


def test_scorer_variants_are_refused(tmp_path):
    allowed = commands.Allowed(tmp_path / "code", tmp_path / "data")
    good, cwd = commands.scorer_command(tmp_path / "code", tmp_path / "data", "nfl-weather", NOW)
    assert allowed.check(good, cwd)
    no_now = good[:4]
    assert not allowed.check(no_now, cwd)
    assert not allowed.check(good[:4] + ["--now", "2026-10-02T17:00:00; rm -rf /"], cwd)
    assert not allowed.check(good + ["--test-record"], cwd)
    assert not allowed.check(good[:1] + ["scripts/alerts.py"] + good[2:], cwd)
    assert not allowed.check(good, str(tmp_path))                      # wrong working directory
    other = [good[0], good[1], "--ledger", "/etc/passwd", "--now", "2026-10-02T17:00:00"]
    assert not allowed.check(other, cwd)
    assert not allowed.check(["/usr/bin/python3"] + good[1:], cwd)
    with pytest.raises(PermissionError):
        commands.run(no_now, cwd, allowed, 5)


def test_store_refuses_before_any_runner(root, home):
    store = make_store(root, home)
    with pytest.raises(PermissionError):
        store._run(["/bin/launchctl", "unload", "x"], None, 5)


def test_subprocess_is_only_used_in_commands_py():
    """Only commands.py starts programs, and only through subprocess.run without a shell."""
    for path in PKG.glob("*.py"):
        tree = ast.parse(path.read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        banned = {"system", "popen", "Popen", "spawn", "execv", "execvp", "startfile", "check_output", "call"}
        assert not (banned & names), (path.name, banned & names)
        if path.name != "commands.py":
            assert "subprocess" not in path.read_text(), path.name
    text = (PKG / "commands.py").read_text()
    assert "shell=False" in text and "shell=True" not in text


def test_no_order_placement_or_writes_in_the_package():
    for path in PKG.glob("*.py"):
        text = path.read_text()
        for word in ("place_order", "requests.post", "urlopen", "http.client", "socket.create_connection",
                     ".write_text(", ".write_bytes(", "os.remove", "os.unlink", "shutil.rmtree", "os.replace",
                     "os.rename", "mkdir("):
            assert word not in text, (path.name, word)
        for mode in ('"w"', "'w'", '"a"', "'a'", '"wb"', '"ab"', '"x"', '"r+"'):
            assert f"open({mode}" not in text and f", {mode})" not in text, (path.name, mode)


def test_real_run_uses_a_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "sk-should-not-leak")
    scorers = tmp_path / "code"
    for project in commands.PROJECTS:
        (scorers / project / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, scorers / project / ".venv" / "bin" / "python")
        (scorers / project / "scripts").mkdir()
        (scorers / project / "scripts" / "score_forward.py").write_text(
            "import os, sys\nprint(sorted(os.environ))\nprint(os.getcwd())\n"
            "import time\nif os.path.basename(os.getcwd()) == 'cfb-weather': time.sleep(5)\n")
    allowed = commands.Allowed(scorers, tmp_path / "data")
    cmd, cwd = commands.scorer_command(scorers, tmp_path / "data", "nfl-weather", NOW)
    r = commands.run(cmd, cwd, allowed, 30)
    assert r.ok
    assert "ODDS_API_KEY" not in r.stdout and "PYTHONDONTWRITEBYTECODE" in r.stdout
    assert r.stdout.strip().endswith(str(Path(cwd).resolve())) or cwd in r.stdout
    cmd, cwd = commands.scorer_command(scorers, tmp_path / "data", "cfb-weather", NOW)
    r = commands.run(cmd, cwd, allowed, 1)
    assert r.timed_out and not r.ok


CONFIGS = {"nfl-weather": PKG.parents[1] / "nfl-weather" / "nflweather" / "config.py",
           "cfb-weather": PKG.parents[1] / "cfb-weather" / "cfbweather" / "config.py"}


def folders_config_creates(path: Path) -> set[str]:
    """The folders a project's config.py creates when it is imported, relative to the project folder: the
    `for p in (...): p.mkdir(...)` loop, with each name worked out from the assignments above it."""
    tree = ast.parse(path.read_text())
    names: dict[str, str] = {}

    def value(node) -> str:
        if isinstance(node, ast.Name):
            return names[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = value(node.left)
            return f"{left}/{value(node.right)}" if left else value(node.right)
        raise ValueError(ast.dump(node))
    out = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "ROOT":
                names["ROOT"] = ""
                continue
            try:
                names[node.targets[0].id] = value(node.value)
            except (ValueError, KeyError):
                pass
        elif isinstance(node, ast.For) and "mkdir" in ast.unparse(node):
            out |= {value(e) for e in node.iter.elts}
    assert out, f"no folder loop found in {path}"
    return out


@pytest.mark.parametrize("project", commands.PROJECTS)
def test_scorer_folders_match_config(project):
    """The folders the dashboard checks before starting a scorer are the ones its config.py would create."""
    if not CONFIGS[project].exists():
        pytest.skip("no config.py in this checkout")
    assert set(commands.SCORER_FOLDERS[project]) == folders_config_creates(CONFIGS[project])


def test_missing_scorer_python_is_reported_not_raised(tmp_path):
    allowed = commands.Allowed(tmp_path, tmp_path)
    cmd, cwd = commands.scorer_command(tmp_path, tmp_path, "nfl-weather", NOW)
    r = commands.run(cmd, cwd, allowed, 5)
    assert r.missing and not r.ok
