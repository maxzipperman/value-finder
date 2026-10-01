"""F1 as pulled: the football archive bundle's priority-1 manifest, read through `--handoff` (issue #101).

`uv run markets price-engine --handoff <bundle> --handoff-root <sha256>` reads F1 from what the football archive
bundle (strategy-research/football_archive/acquisition/football-archive-v4 on the research/football-archive-v4
branch, PR 99) bought and reused, instead of planning the legacy F1 call set from saved schedules. Amendment 2 to
docs/PRICE_ENGINE_PREREGISTRATION.md (a DRAFT until the hub registers it) says why and what differs.

What this module does, and nothing else:
  0. It refuses every run until amendment 2 is registered: `REGISTERED_ROOT` below is None until the hub fills it
     in at registration (with the amendment's root blank), and `--handoff-root` must equal it.
  1. It reads the bundle folder file by file, refusing any symbolic link (to a file or a folder) and anything that
     is not a regular file or a folder, and checks every file against its own FREEZE.json, and the root of those
     hashes against the pinned root. Any changed, missing or extra file (a `__pycache__` folder included) refuses
     the run here, before any code in the folder runs and before any response is read.
  2. It imports the bundle's frozen `cache_handoff.py` (it is never copied into the engine) and calls
     `build_handoff(bundle, root, runtime)`, which runs the bundle's own validator over the whole bundle, requires a
     completed recent slice and an outcome-blind coverage report, and checks every paid response and receipt and
     every reused response in `reuse/` against its recorded hash.
  3. `as_calls(handoff, bulk.Call)` gives one `bulk.Call` per priority-1 request, each checked to have the cache key
     the manifest recorded, and `ReadOnlyCache(handoff, runtime/data/raw)` finds each response (the 12 reused ones
     in the bundle's `reuse/`, the paid ones in the runtime cache), re-checking its hash on every lookup. It cannot
     fetch or write. A response that changes after loading refuses the run (HandoffRefused), as in step 1.
  4. Each call's `sealed` flag is set from the config's season windows at the call's requested time; `as_calls`
     leaves every call unsealed. The legacy plan marks a call sealed when any game it serves kicks off in a sealed
     window, but the manifest does not name every call's games (its evening decision slots name none), so the
     requested time stands in. For this bundle the two agree: no priority-1 call is sealed either way. The flag
     only matters for a row whose own game time is in no season window, and it can only leave rows out.

The calls and the cache then go to the registered `run(cfg, calls, cache)` unchanged: no threshold, flag, entry,
grading or decision rule differs, and the registered filters (sealed seasons in `bulk.load_rows`, the snapshot at or
after kickoff, the 7-day window, the 60-minute entry rule) apply to every snapshot exactly as they do to legacy F1.

Safety. The bundle folder holds Python code, and reading it runs that code inside this process, with this process's
rights. What makes that acceptable is the pinned root and the review behind it: the hub approves one frozen root
after reviewing that root's code, registers it in `REGISTERED_ROOT`, and step 1 makes sure the code that runs is byte
for byte the code that root names. Concretely, the bundle's modules are never imported from the folder: the folder
is not put on `sys.path`, and a finder placed first on `sys.meta_path` serves only `BUNDLE_MODULES` (the modules
`cache_handoff` imports, directly or through them), each only if its file is in FREEZE.json, compiled from the bytes
that were hashed in step 1. So a file swapped between the check and the import is never run, and nothing in the
folder can shadow another module (a `pyarrow` or `json` in the bundle is never imported; everything outside
`BUNDLE_MODULES` resolves as it would without the bundle). No bytecode is written. The folder is checked against
FREEZE.json again afterwards, so the bundle's code writing into it refuses the run.

What remains is not a sandbox, and nothing here makes an unreviewed root safe. The bundle's code can read and write
any file this process can (the re-check covers only the folder), and the network block is partial:
`socket.socket.connect`, `socket.create_connection` and `socket.getaddrinfo` raise while it runs, but `connect_ex`,
`sendto`, a subprocess or a C extension are not blocked. Setting modules of the same name aside and restoring them
afterwards is bookkeeping so the engine's own imports are untouched, not isolation.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import json
import os
import re
import socket
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

from ...oddsapi import bulk

RUNTIME_DEFAULT = "football-acquisition-runtime"     # the v4 executor's runtime folder, next to the bundle folder
FREEZE = "FREEZE.json"
LEDGER = "spending-ledger.json"
# The bundle's modules the handoff runs: cache_handoff imports validator and executor; validator imports builder;
# executor.validate_response imports price_eligibility. Only these are served, and only from the frozen bytes.
BUNDLE_MODULES = ("cache_handoff", "validator", "builder", "executor", "price_eligibility")

# The bundle root amendment 2 registers. None until the hub registers the amendment: the hub fills it in at
# registration, together with the amendment's root blank marked ⟨hub⟩, and --handoff refuses every run until then.
REGISTERED_ROOT: str | None = None


class HandoffRefused(RuntimeError):
    """The bundle (or what it bought) did not verify; nothing was read from it."""


def _canonical(value) -> bytes:
    # the bundle validator's canonical JSON, by which its root is the sha256 of the file-hash map
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _read_regular(path: Path) -> bytes:
    """A regular file's bytes, refusing a symbolic link or anything else put in its place since it was listed."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise HandoffRefused(f"cannot open {path} as a regular file ({exc.strerror})") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise HandoffRefused(f"{path} is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as f:
            return f.read()
    finally:
        os.close(fd)


def _walk(bundle: Path) -> dict[str, bytes]:
    """Every file under `bundle` by its relative path, read once. Refuses any symbolic link, to a file or a folder,
    anywhere in the bundle, and any entry that is neither a regular file nor a folder (a FIFO, a socket, a device)."""
    out: dict[str, bytes] = {}

    def visit(folder: Path, rel: str) -> None:
        with os.scandir(folder) as it:
            entries = sorted(it, key=lambda e: e.name)
        for e in entries:
            name = f"{rel}{e.name}"
            if e.is_symlink():
                raise HandoffRefused(f"the bundle holds a symbolic link, {name}: a frozen bundle holds only regular "
                                     "files and folders")
            if e.is_dir(follow_symlinks=False):
                visit(Path(e.path), f"{name}/")
            elif e.is_file(follow_symlinks=False):
                out[name] = _read_regular(Path(e.path))
            else:
                raise HandoffRefused(f"the bundle holds {name}, which is not a regular file or a folder")

    if Path(bundle).is_symlink() or not Path(bundle).is_dir():
        raise HandoffRefused(f"{bundle} is not a folder")
    visit(Path(bundle), "")
    return out


def _verify(bundle: Path, root: str) -> tuple[str, dict[str, bytes]]:
    """(root, {module name: frozen source bytes} for the BUNDLE_MODULES in the bundle). See verify_frozen."""
    bundle = Path(bundle)
    if not re.fullmatch(r"[0-9a-f]{64}", root or ""):
        raise HandoffRefused("--handoff-root must be the bundle's 64-character sha256 root, as the hub approved it")
    files = _walk(bundle)
    if FREEZE not in files:
        raise HandoffRefused(f"{bundle} has no {FREEZE}: not a frozen bundle folder")
    nested = sorted(k for k in files if k != FREEZE and k.rsplit("/", 1)[-1] == FREEZE)
    if nested:
        # the bundle's validator leaves every file of that name out of its hash map; only the top-level one is a cert
        raise HandoffRefused(f"the bundle holds {FREEZE} below its top level ({', '.join(nested[:5])})")
    try:
        cert = json.loads(files.pop(FREEZE))
        expected, cert_root = dict(cert["file_sha256"]), cert["bundle_root_sha256"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HandoffRefused(f"{FREEZE} is not a freeze certificate ({type(exc).__name__})") from None
    actual = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
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
    return computed, {m: files[f"{m}.py"] for m in BUNDLE_MODULES if f"{m}.py" in files}


def verify_frozen(bundle: Path, root: str) -> str:
    """Refuse unless the bundle holds only regular files and folders (no symbolic link anywhere), every file matches
    FREEZE.json's hash for it, no file is missing or extra, and the root of that hash map is both FREEZE.json's and
    `root`. Returns the root. Runs no code from the folder."""
    return _verify(bundle, root)[0]


def _check_registered(root) -> None:
    if REGISTERED_ROOT is None:
        raise HandoffRefused("amendment 2 is not registered: no bundle root is registered for --handoff "
                             "(handoff.REGISTERED_ROOT), so it reads nothing until the hub registers the amendment")
    if root != REGISTERED_ROOT:
        raise HandoffRefused(f"--handoff-root {root} is not the root registered with amendment 2, {REGISTERED_ROOT}")


class _FrozenLoader(importlib.abc.Loader):
    """Runs one bundle module from the bytes that were hashed, never from the file."""

    def __init__(self, source: bytes, origin: str):
        self.source, self.origin = source, origin

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        exec(compile(self.source, self.origin, "exec", dont_inherit=True), module.__dict__)


class _FrozenFinder(importlib.abc.MetaPathFinder):
    """First on sys.meta_path while the bundle's code runs: answers for BUNDLE_MODULES only, from the frozen bytes."""

    def __init__(self, bundle: Path, sources: dict[str, bytes]):
        self.bundle, self.sources = bundle, sources

    def find_spec(self, name, path=None, target=None):
        if name not in BUNDLE_MODULES:
            return None                     # everything else resolves as it would without the bundle
        if name not in self.sources:
            raise ModuleNotFoundError(f"{name}.py is not in the frozen bundle", name=name)
        origin = str(self.bundle / f"{name}.py")
        spec = importlib.machinery.ModuleSpec(name, _FrozenLoader(self.sources[name], origin), origin=origin)
        spec.has_location = True            # __file__ names the frozen file (builder.py reads its own folder)
        return spec


def _no_network(*_a, **_k):
    raise HandoffRefused("the bundle's code tried to open a network connection; the handoff reads only")


@contextmanager
def _bundle_code(bundle: Path, sources: dict[str, bytes]):
    """The bundle's frozen modules importable for the duration, nothing written, the main connection calls blocked."""
    finder = _FrozenFinder(bundle, sources)
    set_aside = {k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] in BUNDLE_MODULES}
    saved = (sys.dont_write_bytecode, socket.socket.connect, socket.create_connection, socket.getaddrinfo)
    sys.dont_write_bytecode = True
    sys.meta_path.insert(0, finder)
    socket.socket.connect = socket.create_connection = socket.getaddrinfo = _no_network
    try:
        yield
    finally:
        sys.dont_write_bytecode = saved[0]
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = saved[1:]
        sys.meta_path[:] = [f for f in sys.meta_path if f is not finder]
        for k in [k for k in sys.modules if k.split(".")[0] in BUNDLE_MODULES]:
            sys.modules.pop(k)
        sys.modules.update(set_aside)


class _RefusingCache:
    """The bundle's ReadOnlyCache, with a response that changed after loading refusing the run (HandoffRefused)
    instead of surfacing as a bare ValueError. Everything else is the bundle's object."""

    def __init__(self, cache):
        self._cache = cache

    def lookup(self, sport, source, key):
        try:
            return self._cache.lookup(sport, source, key)
        except ValueError as exc:
            raise HandoffRefused(f"a response changed after the handoff was loaded ({exc})") from None

    def __getattr__(self, name):
        return getattr(self._cache, name)


def _ledger_sha(runtime: Path) -> str:
    try:
        return hashlib.sha256(_read_regular(runtime / LEDGER)).hexdigest()
    except HandoffRefused:
        raise HandoffRefused(f"the runtime folder {runtime} has no readable {LEDGER}") from None


def load(bundle, root: str, cfg: dict, runtime=None) -> tuple[list, object, dict]:
    """(calls, cache, info) for `run(cfg, calls, cache)`, from a verified bundle and its completed runtime."""
    bundle = Path(bundle).resolve()
    runtime = Path(runtime).resolve() if runtime else bundle.parent / RUNTIME_DEFAULT
    if not re.fullmatch(r"[0-9a-f]{64}", root or ""):
        raise HandoffRefused("--handoff-root must be the bundle's 64-character sha256 root, as the hub approved it")
    _check_registered(root)
    root, sources = _verify(bundle, root)
    if "cache_handoff" not in sources:
        raise HandoffRefused("the frozen bundle has no cache_handoff.py")
    ledger_sha = _ledger_sha(runtime)
    with _bundle_code(bundle, sources):
        try:
            module = importlib.import_module("cache_handoff")
            handoff = module.build_handoff(bundle, root, runtime)
            calls = module.as_calls(handoff, bulk.Call)
            cache = module.ReadOnlyCache(handoff, runtime / "data" / "raw")
        except HandoffRefused:
            raise
        except Exception as exc:        # the bundle's own checks (ValueError, its Halt, a missing ledger file, ...)
            raise HandoffRefused(f"the bundle's handoff refused: {type(exc).__name__}: {exc}") from None
    verify_frozen(bundle, root)         # nothing was written into the bundle while its code ran
    if _ledger_sha(runtime) != ledger_sha:
        raise HandoffRefused(f"the runtime's {LEDGER} changed while the handoff was read")
    if handoff.get("bundle_root_sha256") != root or len(calls) != len(handoff["entries"]):
        raise HandoffRefused("the handoff does not describe the pinned bundle")
    calls = [dataclasses.replace(c, sealed=bulk.is_sealed(cfg, c.sport, c.at)) for c in calls]
    reused = sum(Path(e["response_path"]).is_relative_to(bundle / "reuse") for e in handoff["entries"])
    info = {"bundle": str(bundle), "runtime": str(runtime), "bundle_root_sha256": root,
            "request_set_sha256": handoff.get("request_set_sha256"),
            "coverage_report_sha256": handoff.get("coverage_report_sha256"), "spending_ledger_sha256": ledger_sha,
            "calls": len(calls), "reused": reused}
    return calls, _RefusingCache(cache), info
