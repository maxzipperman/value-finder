"""F1 as pulled: the football archive bundle's priority-1 manifest, read through `--handoff` (issue #101).

`uv run markets price-engine --handoff <bundle> --handoff-root <sha256>` reads F1 from what the football archive
bundle (strategy-research/football_archive/acquisition/football-archive-v4 on the research/football-archive-v4
branch, PR 99) bought and reused, instead of planning the legacy F1 call set from saved schedules. Amendment 2 to
docs/PRICE_ENGINE_PREREGISTRATION.md (a DRAFT until the hub registers it) says why and what differs.

What this module does, and nothing else:
  1. It checks the bundle folder file by file against its own FREEZE.json, and the root of those hashes against
     the root given on the command line (the one the hub approved). Any changed, missing or extra file (a
     `__pycache__` folder included) refuses the run here, before any code in the folder runs and before any
     response is read.
  2. It imports the bundle's frozen `cache_handoff.py` from that folder (it is never copied into the engine) and
     calls `build_handoff(bundle, root, runtime)`, which runs the bundle's own validator over the whole bundle,
     requires a completed recent slice and an outcome-blind coverage report, and checks every paid response and
     receipt and every reused response in `reuse/` against its recorded hash.
  3. `as_calls(handoff, bulk.Call)` gives one `bulk.Call` per priority-1 request, each checked to have the cache key
     the manifest recorded, and `ReadOnlyCache(handoff, runtime/data/raw)` finds each response (the 12 reused ones
     in the bundle's `reuse/`, the paid ones in the runtime cache), re-checking its hash on every lookup. It cannot
     fetch or write.
  4. Each call's `sealed` flag is set from the config's season windows at the call's requested time, as the legacy
     plan sets it for its own calls; `as_calls` leaves every call unsealed. It can only leave rows out.

The calls and the cache then go to the registered `run(cfg, calls, cache)` unchanged: no threshold, flag, entry,
grading or decision rule differs, and the registered filters (sealed seasons in `bulk.load_rows`, the snapshot at or
after kickoff, the 7-day window, the 60-minute entry rule) apply to every snapshot exactly as they do to legacy F1.

Safety. The bundle folder holds Python code, and reading it runs that code. It must be the frozen bundle the hub
approved, pinned by its root; step 1 makes sure the code that runs is byte for byte the code that root names. While
the bundle's code runs: its folder is first on `sys.path`, bytecode writing is off (so nothing is written into the
folder), any module of the same name already loaded is set aside, and opening a network connection raises. After,
the folder leaves `sys.path`, its modules leave `sys.modules`, the set-aside modules come back, and the folder is
checked against FREEZE.json once more.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import re
import socket
import sys
from contextlib import contextmanager
from pathlib import Path

from ...oddsapi import bulk

RUNTIME_DEFAULT = "football-acquisition-runtime"     # the v4 executor's runtime folder, next to the bundle folder
FREEZE = "FREEZE.json"


class HandoffRefused(RuntimeError):
    """The bundle (or what it bought) did not verify; nothing was read from it."""


def _canonical(value) -> bytes:
    # the bundle validator's canonical JSON, by which its root is the sha256 of the file-hash map
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen(bundle: Path, root: str) -> str:
    """Refuse unless every file in `bundle` matches FREEZE.json's hash for it, no file is missing or extra, and the
    root of that hash map is both FREEZE.json's and `root`. Returns the root. Runs no code from the folder."""
    bundle = Path(bundle)
    if not re.fullmatch(r"[0-9a-f]{64}", root or ""):
        raise HandoffRefused("--handoff-root must be the bundle's 64-character sha256 root, as the hub approved it")
    if not (bundle / FREEZE).is_file():
        raise HandoffRefused(f"{bundle} has no {FREEZE}: not a frozen bundle folder")
    try:
        cert = json.loads((bundle / FREEZE).read_text())
        expected, cert_root = dict(cert["file_sha256"]), cert["bundle_root_sha256"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HandoffRefused(f"{FREEZE} is not a freeze certificate ({type(exc).__name__})") from None
    actual = {str(p.relative_to(bundle)): _sha(p) for p in sorted(bundle.rglob("*"))
              if p.is_file() and p.name != FREEZE}
    if actual != expected:
        changed = sorted(k for k in actual.keys() & expected.keys() if actual[k] != expected[k])
        extra, missing = sorted(actual.keys() - expected.keys()), sorted(expected.keys() - actual.keys())
        parts = [f"{label} {len(names)} ({', '.join(names[:5])}{', ...' if len(names) > 5 else ''})"
                 for label, names in (("changed", changed), ("extra", extra), ("missing", missing)) if names]
        raise HandoffRefused("bundle files differ from its FREEZE.json: " + "; ".join(parts))
    computed = hashlib.sha256(_canonical(actual)).hexdigest()
    if computed != cert_root:
        raise HandoffRefused(f"the bundle's file hashes give root {computed}, not FREEZE.json's {cert_root}")
    if computed != root:
        raise HandoffRefused(f"the bundle's root is {computed}, not the pinned --handoff-root {root}")
    return computed


def _no_network(*_a, **_k):
    raise HandoffRefused("the bundle's code tried to open a network connection; the handoff reads only")


@contextmanager
def _bundle_code(bundle: Path):
    """The bundle folder importable for the duration, with nothing written into it and no network."""
    names = {p.stem for p in bundle.glob("*.py")} | {p.name for p in bundle.iterdir() if (p / "__init__.py").is_file()}
    set_aside = {k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] in names}
    saved = (sys.dont_write_bytecode, list(sys.path), socket.socket.connect, socket.create_connection,
             socket.getaddrinfo)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(bundle))
    socket.socket.connect = socket.create_connection = socket.getaddrinfo = _no_network
    try:
        yield
    finally:
        sys.dont_write_bytecode, sys.path[:] = saved[0], saved[1]
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = saved[2:]
        for k in [k for k in sys.modules if k.split(".")[0] in names]:
            sys.modules.pop(k)
        sys.modules.update(set_aside)


def load(bundle, root: str, cfg: dict, runtime=None) -> tuple[list, object, dict]:
    """(calls, cache, info) for `run(cfg, calls, cache)`, from a verified bundle and its completed runtime."""
    bundle = Path(bundle).resolve()
    runtime = Path(runtime).resolve() if runtime else bundle.parent / RUNTIME_DEFAULT
    verify_frozen(bundle, root)
    with _bundle_code(bundle):
        try:
            spec = importlib.util.spec_from_file_location("cache_handoff", bundle / "cache_handoff.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            handoff = module.build_handoff(bundle, root, runtime)
            calls = module.as_calls(handoff, bulk.Call)
            cache = module.ReadOnlyCache(handoff, runtime / "data" / "raw")
        except HandoffRefused:
            raise
        except Exception as exc:        # the bundle's own checks (ValueError, its Halt, a missing ledger file, ...)
            raise HandoffRefused(f"the bundle's handoff refused: {type(exc).__name__}: {exc}") from None
    verify_frozen(bundle, root)         # nothing was written into the bundle while its code ran
    if handoff.get("bundle_root_sha256") != root or len(calls) != len(handoff["entries"]):
        raise HandoffRefused("the handoff does not describe the pinned bundle")
    calls = [dataclasses.replace(c, sealed=bulk.is_sealed(cfg, c.sport, c.at)) for c in calls]
    reused = sum(Path(e["response_path"]).is_relative_to(bundle / "reuse") for e in handoff["entries"])
    info = {"bundle": str(bundle), "runtime": str(runtime), "bundle_root_sha256": root,
            "request_set_sha256": handoff.get("request_set_sha256"),
            "coverage_report_sha256": handoff.get("coverage_report_sha256"), "calls": len(calls), "reused": reused}
    return calls, cache, info
