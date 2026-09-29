"""Makes `uv run --project dashboard pytest -q`, typed at the repo root, run the dashboard's tests only.

pytest looks for its settings where it is started, so from the repo root it would otherwise collect every
project's tests with the dashboard's Python (which has none of their packages). This plugin is installed only
in the dashboard's own environment (an entry point in dashboard/pyproject.toml). It acts only when pytest is
given no paths and is started in the folder that holds this dashboard/; then it adds dashboard/tests."""
from __future__ import annotations

from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1]


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, args, parser):
    ns = early_config.known_args_namespace
    if getattr(ns, "file_or_dir", None):
        return
    here = Path(early_config.invocation_params.dir).resolve()
    if here != DASHBOARD.parent or not (DASHBOARD / "tests").is_dir():
        return
    tests = str(DASHBOARD / "tests")
    args.append(tests)
    ns.file_or_dir = [tests]
