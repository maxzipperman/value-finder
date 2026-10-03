"""Captured immutable module closure; explicit dynamic-loader review required."""
import builtins
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=str).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(obj):
    return digest(canonical(obj))


def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink in evidence/dependency path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Regular evidence/dependency file required")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def read(path):
    return json.loads(regular(path))


def sha(path):
    return digest(regular(path))


def integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("Exact nonnegative integer required")
    return int(value)


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("Known timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Aware timestamp required")
    return result


def closed_modules(captured, paths):
    """Compile captured bytes only; local import names derive from capture.

    No ambient sys.path resolution for local roots. Unique module identities in
    sys.modules support dataclasses; they never replace normal module names.
    External imports are stdlib or the reviewed runtime's named distributions.
    """
    modules = {}
    local_roots = {name.split(".")[0] for name in captured}
    external = sys.stdlib_module_names | {"requests", "urllib3", "pyarrow", "yaml", "dotenv",
                                         "certifi", "charset_normalizer", "idna"}
    original = builtins.__import__
    prefix = "football_metadata_capture_" + identity({n: digest(b) for n, b in captured.items()})[:16]

    def load(name):
        if name in modules:
            return modules[name]
        if name not in captured:
            raise ImportError("Undeclared captured local import: " + name)
        module = types.ModuleType(prefix + "." + name)
        module.__file__ = str(paths[name])
        package = name if Path(paths[name]).name == "__init__.py" else name.rpartition(".")[0]
        module.__package__ = package
        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": closed_import}
        if Path(paths[name]).name == "__init__.py":
            module.__path__ = []
        modules[name] = module
        sys.modules[module.__name__] = module
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(load(parent), child, module)
        exec(compile(captured[name], str(paths[name]), "exec"), module.__dict__)
        return module

    def closed_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level:
            package = (globals or {}).get("__package__")
            name = importlib.util.resolve_name("." * level + name, package)
        if name.split(".")[0] in local_roots:
            module = load(name)
            for child in fromlist or ():
                if child != "*" and name + "." + child in captured:
                    setattr(module, child, load(name + "." + child))
            return module if fromlist else load(name.split(".")[0])
        root = name.split(".")[0]
        if root not in external:
            raise ImportError("Undeclared external import: " + name)
        spec = importlib.util.find_spec(root)
        origin = getattr(spec, "origin", None)
        if origin not in ("built-in", "frozen"):
            if not origin:
                raise ImportError("Unknown dependency origin: " + root)
            path = Path(origin).absolute()
            prefix = Path(sys.base_prefix if root in sys.stdlib_module_names else sys.prefix).absolute()
            if not path.is_relative_to(prefix):
                raise ImportError("Ambient dependency outside reviewed interpreter: " + root)
            if root not in sys.stdlib_module_names and "site-packages" not in path.parts:
                raise ImportError("External dependency outside reviewed site-packages: " + root)
        return original(name, globals, locals, fromlist, 0)
    return load

