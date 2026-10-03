"""uv run --project dashboard python -m vfdash --port 8787 [--root PATH] [--scorer-root PATH] [--home PATH]

There is no --host: the dashboard listens on 127.0.0.1 only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .data import Config, Store
from .server import PortInUse, serve
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
    ap.add_argument("--operations-root", type=Path, help="Reviewed repository containing current STATUS and queue; live data still comes from --root")
    a = ap.parse_args(argv)
    if not 1 <= a.port <= 65535:
        ap.error("--port must be between 1 and 65535")
    root = a.root.expanduser().resolve()
    cfg = Config(root=root, scorer_root=(a.scorer_root or root).expanduser().resolve(),
                 home=a.home.expanduser().resolve(), content=HERE.parent / "content", tz=local_zone(), port=a.port,
                 operations_root=a.operations_root.expanduser().resolve() if a.operations_root else None)
    try:
        serve(Store(cfg), a.port)
    except PortInUse:
        print(f"The dashboard could not start: something else on this Mac is already using port {a.port} "
              f"(often another copy of the dashboard; http://127.0.0.1:{a.port}/ may already work).",
              file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
