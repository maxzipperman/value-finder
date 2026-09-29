"""Ledgers grow to about 100,000 rows a season: reading one must stay under a second, and the next read (after
the jobs append a run) reads only the new lines."""
from __future__ import annotations

import time
from datetime import timedelta

from conftest import NFL_HEADER, Clock, make_home, make_root, make_store, nfl_row

from vfdash import api

ROWS = 100_000


def big_ledger(path, rows=ROWS):
    teams = [f"T{i:02d}" for i in range(32)]
    lines = [NFL_HEADER]
    snap_n = 0
    for n in range(rows):
        if n % 16 == 0:
            snap_n += 1
        day = 1 + (n // 16) % 28
        snap = f"2026-10-{1 + snap_n % 28:02d}T{(snap_n % 4) * 4 + 2:02d}:30:07Z"
        a, h = teams[n % 32], teams[(n + 7) % 32]
        lines.append(nfl_row(snap, f"2026_{day:02d}_{a}_{h}_{n // 1000}", f"2026-11-{day:02d}", "13:00", a, h,
                             "no_trigger" if n % 50 else "SIGNAL", wind=f"{(n % 23) + 0.123456789:.9f}"))
    path.write_text("\n".join(lines) + "\n")


def test_hundred_thousand_rows_under_a_second(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path)
    ledger = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    big_ledger(ledger)
    clock = Clock()
    store = make_store(root, home, clock=clock)
    t = time.perf_counter()
    store.snapshot()
    first = time.perf_counter() - t
    assert len(store.ledgers["nfl"].rows) == ROWS
    assert first < 1.0, f"first read took {first:.2f} s"
    # each request after that uses the cached read
    t = time.perf_counter()
    for _ in range(5):
        api.summary(store)
        api.board(store)
    assert time.perf_counter() - t < 1.0
    # the jobs append a run; the next refresh reads only those lines
    with ledger.open("a") as f:
        f.write(nfl_row("2026-10-30T14:30:07Z", "2026_05_NEW_ONE", "2026-11-01", "13:00", "NEW", "ONE",
                        "SIGNAL") + "\n")
    clock.t += timedelta(seconds=31)
    t = time.perf_counter()
    store.snapshot()
    again = time.perf_counter() - t
    assert len(store.ledgers["nfl"].rows) == ROWS + 1
    assert again < 0.5, f"refresh took {again:.2f} s"
