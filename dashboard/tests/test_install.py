"""The install script writes a valid launchd file for com.valuefinder.dashboard (checked from its text; the
script itself is never run by the tests)."""
from __future__ import annotations

import plistlib
import re
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"


def rendered_plist(root="/Users/me/code/value-finder", home="/Users/me") -> dict:
    text = (OPS / "install_dashboard.sh").read_text()
    body = text.split("<<PLIST\n", 1)[1].split("\nPLIST\n", 1)[0]
    values = {"LABEL": "com.valuefinder.dashboard", "PY": f"{root}/dashboard/.venv/bin/python", "PORT": "8787",
              "ROOT": root, "LOG": f"{home}/Library/Logs/value-finder-dashboard.log", "HOME": home}
    body = re.sub(r"\$(\w+)", lambda m: values[m.group(1)], body)
    return plistlib.loads(body.encode())


def test_install_plist():
    p = rendered_plist()
    assert p["Label"] == "com.valuefinder.dashboard"
    assert p["ProgramArguments"] == ["/Users/me/code/value-finder/dashboard/.venv/bin/python", "-m", "vfdash",
                                     "--port", "8787", "--root", "/Users/me/code/value-finder"]
    assert p["RunAtLoad"] is True and p["KeepAlive"] is True
    assert p["StandardOutPath"] == p["StandardErrorPath"] == "/Users/me/Library/Logs/value-finder-dashboard.log"
    assert "--host" not in p["ProgramArguments"]


def test_print_plist_changes_nothing():
    """--print-plist prints the job file and exits before anything that installs, writes or starts a job;
    and the port is checked before the job is started."""
    text = (OPS / "install_dashboard.sh").read_text()
    lines = text.splitlines()
    at = lambda s: next(i for i, ln in enumerate(lines) if s in ln and not ln.lstrip().startswith("#"))  # noqa: E731
    printed = at('"--print-plist" ]]; then plist; exit 0; fi')
    for later in ("sync --project", "launchctl bootout", "lsof", 'plist > "$PLIST"', "launchctl bootstrap"):
        assert at(later) > printed, later
    assert at("lsof") < at('plist > "$PLIST"') < at("launchctl bootstrap")
    assert "--print-plist" in lines[5] or any("--print-plist" in ln for ln in lines[:8])     # documented at the top


def test_a_second_copy_says_so_in_one_sentence(tmp_path, capsys):
    """A copy started while another holds the port prints one plain sentence and exits 1, not a traceback."""
    import socket
    from vfdash.__main__ import main
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        code = main(["--port", str(port), "--root", str(tmp_path), "--home", str(tmp_path)])
    finally:
        s.close()
    err = capsys.readouterr().err
    assert code == 1
    assert f"already using port {port}" in err and "Traceback" not in err and len(err.strip().splitlines()) == 1


def test_scripts_follow_the_house_style():
    install = (OPS / "install_dashboard.sh").read_text()
    uninstall = (OPS / "uninstall_dashboard.sh").read_text()
    for text in (install, uninstall):
        assert text.startswith("#!/bin/zsh\n") and "set -euo pipefail" in text
        assert 'LABEL="com.valuefinder.dashboard"' in text
    assert "File > Add to Dock" in install and "http://127.0.0.1:$PORT/" in install
    assert 'rm -f "$PLIST"' in uninstall and "bootout" in uninstall
    # nothing else is removed or changed
    assert uninstall.count("rm ") == 1
