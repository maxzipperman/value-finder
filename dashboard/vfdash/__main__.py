"""uv run --project dashboard python -m vfdash --port 8787 [--root PATH] [--scorer-root PATH] [--home PATH]

There is no --host: the dashboard listens on 127.0.0.1 only."""
from __future__ import annotations

import argparse
from pathlib import Path

from .data import Config, Store
from .server import serve
from .words import local_zone

HERE = Path(__file__).resolve().parent            # dashboard/vfdash
CHECKOUT = HERE.parents[1]                         # the repo checkout the dashboard lives in


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vfdash", description="Value Finder: a local, read-only dashboard.")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--root", type=Path, default=CHECKOUT,
                    help="the repo checkout to read, or a copy laid out like it (default: the checkout it lives in)")
    ap.add_argument("--scorer-root", type=Path, default=None,
                    help="where the scorers and their Pythons live (default: --root); the previews always read "
                         "--root's ledgers, with --now")
    ap.add_argument("--home", type=Path, default=Path.home(),
                    help="home folder for ~/Library/LaunchAgents, ~/Library/Logs and ~/.cache/value-finder")
    a = ap.parse_args(argv)
    if not 1 <= a.port <= 65535:
        ap.error("--port must be between 1 and 65535")
    root = a.root.expanduser().resolve()
    cfg = Config(root=root, scorer_root=(a.scorer_root or root).expanduser().resolve(),
                 home=a.home.expanduser().resolve(), content=HERE.parent / "content", tz=local_zone(), port=a.port)
    serve(Store(cfg), a.port)


if __name__ == "__main__":
    main()
