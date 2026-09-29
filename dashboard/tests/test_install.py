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
