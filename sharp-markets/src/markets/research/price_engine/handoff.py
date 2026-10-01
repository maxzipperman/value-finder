"""F1 as pulled: the football archive bundle's priority-1 manifest, read through `--handoff` (issue #101).

`uv run markets price-engine --handoff <bundle> --handoff-root <sha256> [--handoff-runtime <dir>]` reads F1 from what
the football archive bundle (strategy-research/football_archive/acquisition/football-archive-v4 on the
research/football-archive-v4 branch, PR 99) bought and reused, instead of planning the legacy F1 call set from saved
schedules. Amendment 2 to docs/PRICE_ENGINE_PREREGISTRATION.md (a DRAFT until the hub registers it) says why and
what differs.

What this module does, and nothing else:
  0. It refuses every run until amendment 2 is registered: `REGISTERED_ROOT` below is None until the hub fills it
     in at registration (with the amendment's root blank), and `--handoff-root` must equal it.
  1. It reads the bundle folder file by file, refusing any symbolic link (to a file or a folder) and anything that
     is not a regular file or a folder, and checks every file against its own FREEZE.json, and the root of those
     hashes against the pinned root. Any changed, missing or extra file (a `__pycache__` folder included), a name
     that is not valid UTF-8, or a file or folder that cannot be listed or read, refuses the run here, before any
     code in the folder runs and before any response is parsed (this step reads and hashes every file, the reused
     responses in `reuse/` included, but parses none of them).
  2. It imports the bundle's frozen `cache_handoff.py` (it is never copied into the engine) and calls
     `build_handoff(bundle, root, runtime)`, which runs the bundle's own validator over the whole bundle, requires a
     completed recent slice and an outcome-blind coverage report, and checks every paid response and receipt and
     every reused response in `reuse/` against its recorded hash. The runtime is the v4 executor's fixed folder,
     `RUNTIME_BASE/<root>` (`~/Library/Application Support/ValueFinder/football-acquisition-state/<root>`), unless
     `--handoff-runtime` names another.
  3. `as_calls(handoff, bulk.Call)` gives one `bulk.Call` per priority-1 request, in manifest order, each checked to
     have the cache key the manifest recorded, and `ReadOnlyCache(handoff, runtime/data/raw)` finds each response
     (the 12 reused ones in the bundle's `reuse/`, the paid ones in the runtime cache), re-checking its hash on every
     lookup. It cannot fetch or write. A response that changes, disappears or cannot be read after loading refuses
     the run (HandoffRefused) when it is looked up. A paid request the bundle's run accepted as missing (a terminal
     failure the hub approved, entry status `accepted_missing`, no response path or hash) keeps its call and its
     place, and its lookup gives no response, so `bulk.load_rows` reads no row from it: it is absent data, counted
     in the report, never fetched. A lookup that gives no response for any other call, or a response for one marked
     missing, refuses the run.
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
that were hashed in step 1. So none of the bundle's modules is run from a file swapped between the check and the
import, and nothing in the folder can shadow another module (a `pyarrow` or `json` in the bundle is never imported;
everything outside `BUNDLE_MODULES` resolves as it would without the bundle). No bytecode is written.

Once the bundle's code has loaded, these are checked and put back as they were, and a change to any of them refuses
the run: the four import routes (`sys.path`, `sys.meta_path`, `sys.path_hooks`, `sys.path_importer_cache`,
each the same object holding the same entries, none of them deleted, though the entries that
`importlib.invalidate_caches()` deletes may go), the folder of every `FileFinder` that
`sys.path_importer_cache` already held, and `builtins.__import__`. New `sys.path_importer_cache` entries that Python's
own path finder makes for folders an import searched are expected and dropped, unless the folder is the bundle
folder or inside it: that means the folder was on the import path, if only for a moment, and refuses the run. So does
any module that has appeared in `sys.modules` from a file in the bundle folder other than the `BUNDLE_MODULES` served
from the frozen bytes (it is removed). A thread the bundle's code started that is still running when it has loaded
refuses the run too (it cannot be stopped). Changes to the objects those routes hold (beyond a FileFinder's folder),
to `sys.modules` beyond the check above, to builtins beyond `__import__`, or made by a thread that has already ended
or that was started below the `threading` module, are not detected: they rest on the review behind the registered
root. The folder is checked against FREEZE.json again afterwards, so the bundle's code writing into it refuses the
run, and so does a change to the runtime's spending ledger.

What remains is not a sandbox, and nothing here makes an unreviewed root safe. The bundle's code runs in this
process, so it could patch the engine, the engine's own checks included (`verify_frozen`, `bulk.is_sealed`, this
module): every guarantee above depends on the code review behind the registered root. It can read and write any file
this process can (the re-check covers only the folder and the ledger). The bundle's code and `bulk.load_rows` read
data again by path after the hash check, so a file swapped and put back before the re-check is not seen; that needs a
concurrent local writer, who could edit the engine anyway. The network block is partial, and covers only the
loading: `socket.socket.connect`, `socket.create_connection` and `socket.getaddrinfo` raise while the bundle's code
loads (`build_handoff`, `as_calls` and `ReadOnlyCache(...)`), but `connect_ex`, `sendto`, a subprocess or a C
extension are not blocked. The bundle's `ReadOnlyCache.lookup` runs later, inside `run()`, outside that block; today
it does no I/O beyond hashing the response. Setting modules of the same name aside and restoring them afterwards is
bookkeeping so the engine's own imports are untouched, not isolation.
"""
from __future__ import annotations

import builtins
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
import threading
import zipimport
from collections import Counter
from contextlib import contextmanager
from copy import copy
from pathlib import Path

from ...oddsapi import bulk

# The v4 executor's fixed runtime (executor.RUNTIME_BASE / root, outside every git checkout): its spending ledger,
# receipts, coverage report and data/raw. --handoff-runtime defaults to it, for the --handoff-root given.
RUNTIME_BASE = "~/Library/Application Support/ValueFinder/football-acquisition-state"
FREEZE = "FREEZE.json"
LEDGER = "spending-ledger.json"
# The bundle's modules the handoff runs: cache_handoff.build_handoff imports validator and executor;
# validator.verify imports builder (and executor); executor.validate_response imports price_eligibility. Only these
# are served, and only from the frozen bytes. (coverage_report and the vendored archive_markets package are imported
# only by the executor's paid run, never on this path.)
BUNDLE_MODULES = ("cache_handoff", "validator", "builder", "executor", "price_eligibility")

# The bundle root amendment 2 registers. None until the hub registers the amendment: the hub fills it in at
# registration, together with the amendment's root blank marked ⟨hub⟩, and --handoff refuses every run until then.
REGISTERED_ROOT: str | None = None


class HandoffRefused(RuntimeError):
    """The bundle (or what it bought) did not verify, and the run stops with nothing reported and nothing written.

    `before_read` is True only for a refusal raised before any of the bundle's code runs (the registration, the
    frozen-folder check and the spending ledger's first read), so before any response is parsed. Every later one
    (the bundle's own checks, the re-checks after its code has run, a response that changed on lookup) is False:
    by then the bundle's code has parsed responses."""

    before_read = False


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
    except OSError as exc:              # an I/O error on read, say
        raise HandoffRefused(f"cannot read {path} ({type(exc).__name__}: {exc.strerror or exc})") from None
    finally:
        os.close(fd)


def _walk(bundle: Path) -> dict[str, bytes]:
    """Every file under `bundle` by its relative path, read once. Refuses any symbolic link, to a file or a folder,
    anywhere in the bundle, any entry that is neither a regular file nor a folder (a FIFO, a socket, a device), and
    any name that is not valid UTF-8 (no frozen root can cover it: the canonical JSON of the hash map is UTF-8), and
    any folder or file that cannot be listed or read (a HandoffRefused, not a traceback)."""
    out: dict[str, bytes] = {}

    def visit(folder: Path, rel: str) -> None:
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:          # a folder this process may not list, say
            raise HandoffRefused(f"cannot list {folder} ({type(exc).__name__}: {exc.strerror or exc})") from None
        for e in entries:
            name = f"{rel}{e.name}"
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                raise HandoffRefused(f"the bundle holds a name that is not valid UTF-8, {name!r}") from None
            try:
                is_link, is_folder, is_file = e.is_symlink(), e.is_dir(follow_symlinks=False), e.is_file(follow_symlinks=False)
            except OSError as exc:
                raise HandoffRefused(f"cannot inspect {e.path} ({type(exc).__name__}: {exc.strerror or exc})") from None
            if is_link:
                raise HandoffRefused(f"the bundle holds a symbolic link, {name}: a frozen bundle holds only regular "
                                     "files and folders")
            if is_folder:
                visit(Path(e.path), f"{name}/")
            elif is_file:
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
    """First on sys.meta_path while the bundle's code loads: answers for BUNDLE_MODULES only, from the frozen bytes."""

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


ROUTES = ("path", "meta_path", "path_hooks", "path_importer_cache")


def _import_state() -> dict:
    """The import system's routes: each object (in case it is rebound or deleted) and a copy of what it holds."""
    return {name: (getattr(sys, name, None), copy(getattr(sys, name, None))) for name in ROUTES}


def _under(path, folder: Path) -> bool:
    """Whether `path` (an import-cache key or a module's file) is `folder` or inside it, comparing resolved paths. A
    path that cannot be resolved counts as inside: it cannot be shown to be elsewhere."""
    try:
        return Path(os.path.abspath(os.fsdecode(path))).resolve().is_relative_to(folder)
    except (TypeError, ValueError, OSError, RuntimeError):
        return True


def _absolute(key) -> bool:
    try:
        return os.path.isabs(os.fsdecode(key))
    except (TypeError, ValueError):
        return True


def _route_change(name: str, obj, held, finder, bundle: Path) -> str | None:
    """What the bundle's code changed in one import route (see _restore_import_state), or None."""
    now = getattr(sys, name, None)
    if now is None:
        return f"sys.{name}, deleted"
    if name != "path_importer_cache":
        expected = [finder, *held] if name == "meta_path" else held
        same = now is obj and len(now) == len(expected) and all(a is b for a, b in zip(now, expected))
        return None if same else f"sys.{name}"
    if now is not obj or not isinstance(now, dict):
        return f"sys.{name}"
    new = [k for k in now if k not in held]
    ours = [k for k in new if _under(k, bundle)]
    if ours:
        return f"sys.{name}, an entry for the bundle folder ({ours[0]}): the folder was on the import path"
    # importlib.invalidate_caches() deletes every entry whose finder is None or whose key is a relative path
    # (PathFinder.invalidate_caches), and Python makes such an entry again when it needs one: a deleted entry of that
    # kind is not a change (it is put back all the same)
    same = all(now[k] is v if k in now else (v is None or not _absolute(k)) for k, v in held.items()) and all(
        now[k] is None or type(now[k]) in (importlib.machinery.FileFinder, zipimport.zipimporter) for k in new)
    return None if same else f"sys.{name}"


def _restore_import_state(before: dict, finder, bundle: Path) -> list[str]:
    """Put sys.path, sys.meta_path, sys.path_hooks and sys.path_importer_cache back as `before` holds them (the
    original objects, with their original contents, an attribute the bundle's code deleted included), and name each
    one the bundle's code changed. `finder` is the handoff's own, expected first on sys.meta_path. New
    path_importer_cache entries of the kinds Python's path finder makes itself (a FileFinder or zipimporter, or None,
    for a folder an import searched) are dropped, not reported, unless the folder is `bundle` or inside it. A route
    that cannot be checked counts as changed, and every route is put back whatever the others hold."""
    changed = []
    for name, (obj, held) in before.items():
        try:
            change = _route_change(name, obj, held, finder, bundle)
        except Exception:
            change = f"sys.{name}, which could not be checked"
        if change:
            changed.append(change)
        if obj is None:
            continue
        setattr(sys, name, obj)
        if isinstance(obj, dict):
            obj.clear()
            obj.update(held)
        else:
            obj[:] = held
    return changed


def _modules_from_bundle(before: dict, bundle: Path) -> list[str]:
    """Remove, and name, each module that appeared in sys.modules (new, or in place of the one `before` holds) from a
    file in the bundle folder, by its spec's origin or its `__file__`, and that the handoff's frozen loader did not
    run. A module that cannot be inspected counts as one."""
    found = []
    for k, m in list(sys.modules.items()):
        if k in before and before[k] is m:
            continue
        try:
            try:
                d = vars(m)
            except TypeError:
                d = {}
            spec = d.get("__spec__")
            origin = getattr(spec, "origin", None) if getattr(spec, "has_location", False) else None  # not "built-in"
            places = [p for p in (origin, d.get("__file__")) if isinstance(p, (str, bytes))]
            loader = getattr(spec, "loader", None) if spec is not None else d.get("__loader__")
            ours = any(_under(p, bundle) for p in places) and not isinstance(loader, _FrozenLoader)
        except Exception:
            ours = True
        if ours:
            found.append(k)
            if k in before:
                sys.modules[k] = before[k]
            else:
                sys.modules.pop(k, None)
    return found


@contextmanager
def _bundle_code(bundle: Path, sources: dict[str, bytes]):
    """The bundle's frozen modules importable for the duration, nothing written, the main connection calls blocked,
    and the import system as it was afterwards (a change the bundle's code made to it, as the module docstring lists,
    refuses the run)."""
    bundle = Path(bundle).resolve()
    finder = _FrozenFinder(bundle, sources)
    set_aside = {k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] in BUNDLE_MODULES}
    saved = (sys.dont_write_bytecode, socket.socket.connect, socket.create_connection, socket.getaddrinfo)
    imports = _import_state()
    modules = dict(sys.modules)
    import_fn = builtins.__import__
    finders = [(f, f.path) for f in sys.path_importer_cache.values() if isinstance(f, importlib.machinery.FileFinder)]
    threads = set(threading.enumerate())
    sys.dont_write_bytecode = True
    sys.meta_path.insert(0, finder)
    socket.socket.connect = socket.create_connection = socket.getaddrinfo = _no_network
    in_flight = None
    try:
        yield
    except BaseException as exc:
        in_flight = exc
        raise
    finally:
        sys.dont_write_bytecode = saved[0]
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = saved[1:]
        changed, running = [], []

        def check(label: str, fn) -> None:
            try:
                found = fn()
            except Exception:
                found = f"{label}, which could not be checked"
            if found:
                changed.append(found)

        def import_function():
            if getattr(builtins, "__import__", None) is not import_fn:
                builtins.__import__ = import_fn
                return "builtins.__import__"

        def finder_folders():
            moved = [(f, path) for f, path in finders if getattr(f, "path", None) != path]
            for f, path in moved:
                f.path = path
                f.invalidate_caches()
            if moved:
                return f"the folder of a FileFinder in sys.path_importer_cache ({moved[0][1]})"

        def bundle_modules():
            loaded = _modules_from_bundle(modules, bundle)
            if loaded:
                return f"sys.modules, {', '.join(loaded[:5])} loaded from the bundle folder"

        try:
            changed += _restore_import_state(imports, finder, bundle)
            check("builtins.__import__", import_function)
            check("the FileFinders in sys.path_importer_cache", finder_folders)
            check("sys.modules", bundle_modules)
            try:
                running = [t.name for t in threading.enumerate() if t not in threads and t.is_alive()]
            except Exception:
                running = ["threads that could not be checked"]
        finally:
            for k in [k for k in sys.modules if k.split(".")[0] in BUNDLE_MODULES]:
                sys.modules.pop(k)
            sys.modules.update(set_aside)
        problems = []
        if changed:
            problems.append(f"the bundle's code changed the import system ({'; '.join(changed)}); "
                            "it was put back as it was")
        if running:
            problems.append(f"the bundle's code left {len(running)} thread(s) running ({', '.join(running[:5])})")
        if problems and (in_flight is None or isinstance(in_flight, Exception)):
            if in_flight is not None:   # the bundle's own check had already failed: say so too
                problems.append(f"the run had already been refused ({in_flight})")
            raise HandoffRefused("; ".join(problems))


class _RefusingCache:
    """The bundle's ReadOnlyCache, with a response that changed, disappeared or cannot be read after loading refusing
    the run (HandoffRefused) instead of surfacing as a bare ValueError or OSError. `missing` holds the (sport, source,
    cache key) of each call the handoff marks `accepted_missing`: the bundle's lookup must give no response for
    those (the engine then reads no row from them), and must give one for every other call; either way round
    refuses the run. Everything else is the bundle's object. Its lookup runs inside `run()`, outside `_bundle_code`'s
    network block and import-system check."""

    def __init__(self, cache, missing=frozenset()):
        self._cache, self._missing = cache, frozenset(missing)

    def lookup(self, sport, source, key):
        try:
            found = self._cache.lookup(sport, source, key)
        except ValueError as exc:
            raise HandoffRefused(f"a response changed after the handoff was loaded ({exc})") from None
        except OSError as exc:
            raise HandoffRefused(f"a response could not be read after the handoff was loaded "
                                 f"({type(exc).__name__}: {exc.strerror or exc})") from None
        if (sport, source, key) in self._missing:
            if found is not None:
                raise HandoffRefused(f"the handoff marks {sport}/{key} accepted_missing, yet its cache gave a response")
            return None
        if found is None:
            raise HandoffRefused(f"the handoff's cache gave no response for {sport}/{key}, which it does not mark "
                                 "accepted_missing")
        return found

    def __getattr__(self, name):
        return getattr(self._cache, name)


def _ledger_sha(runtime: Path) -> str:
    try:
        return hashlib.sha256(_read_regular(runtime / LEDGER)).hexdigest()
    except HandoffRefused:
        raise HandoffRefused(f"the runtime folder {runtime} has no readable {LEDGER}") from None


def _entry_ok(entry: dict) -> bool:
    """A handoff entry is a response (no status, a path and a hash) or accepted_missing (no path, no hash)."""
    if entry.get("status") == "accepted_missing":
        return entry.get("response_path") is None and entry.get("response_sha256") is None
    return entry.get("status") is None and entry.get("response_path") is not None


def default_runtime(root: str) -> Path:
    """The v4 executor's fixed runtime folder for `root`: RUNTIME_BASE/<root>, `~` expanded."""
    return Path(RUNTIME_BASE).expanduser() / root


def load(bundle, root: str, cfg: dict, runtime=None) -> tuple[list, object, dict]:
    """(calls, cache, info) for `run(cfg, calls, cache)`, from a verified bundle and its completed runtime (by default
    `default_runtime(root)`)."""
    bundle = Path(bundle).resolve()
    try:                                # before any of the bundle's code runs, so before any response is parsed
        if not re.fullmatch(r"[0-9a-f]{64}", root or ""):
            raise HandoffRefused("--handoff-root must be the bundle's 64-character sha256 root, as the hub approved it")
        runtime = (Path(runtime).expanduser() if runtime else default_runtime(root)).resolve()
        _check_registered(root)
        root, sources = _verify(bundle, root)
        if "cache_handoff" not in sources:
            raise HandoffRefused("the frozen bundle has no cache_handoff.py")
        ledger_sha = _ledger_sha(runtime)
    except HandoffRefused as exc:
        exc.before_read = True
        raise
    with _bundle_code(bundle, sources):
        try:
            module = importlib.import_module("cache_handoff")
            handoff = module.build_handoff(bundle, root, runtime)
            calls = module.as_calls(handoff, bulk.Call)
            cache = module.ReadOnlyCache(handoff, runtime / "data" / "raw")
        except HandoffRefused:
            raise
        except (Exception, SystemExit) as exc:  # the bundle's own checks (ValueError, its Halt, a missing ledger
            # file, ...), or an exit; a KeyboardInterrupt is left alone
            raise HandoffRefused(f"the bundle's handoff refused: {type(exc).__name__}: {exc}") from None
    verify_frozen(bundle, root)         # nothing was written into the bundle while its code ran
    if _ledger_sha(runtime) != ledger_sha:
        raise HandoffRefused(f"the runtime's {LEDGER} changed while the handoff was read")
    entries = handoff["entries"]
    if (handoff.get("bundle_root_sha256") != root or len(calls) != len(entries)
            or any(c.key != e["request"]["cache_key"] for c, e in zip(calls, entries))):
        raise HandoffRefused("the handoff does not describe the pinned bundle")
    missing = [e for e in entries if e.get("status") == "accepted_missing"]
    odd = [e for e in entries if not _entry_ok(e)]
    if odd:
        raise HandoffRefused(f"the handoff has an entry that is neither a response with its path nor accepted_missing "
                             f"without one (status {odd[0].get('status')!r}; {len(odd)} such)")
    calls = [dataclasses.replace(c, sealed=bulk.is_sealed(cfg, c.sport, c.at)) for c in calls]
    reused = sum(e["response_path"] is not None and Path(e["response_path"]).is_relative_to(bundle / "reuse")
                 for e in entries)
    info = {"bundle": str(bundle), "runtime": str(runtime), "bundle_root_sha256": root,
            "request_set_sha256": handoff.get("request_set_sha256"),
            "coverage_report_sha256": handoff.get("coverage_report_sha256"), "spending_ledger_sha256": ledger_sha,
            "calls": len(calls), "reused": reused, "accepted_missing": len(missing),
            "accepted_missing_reasons": dict(sorted(Counter(str(e.get("reason")) for e in missing).items()))}
    keys = {(e["request"]["sport"], e["request"]["source"], e["request"]["cache_key"]) for e in missing}
    return calls, _RefusingCache(cache, keys), info
