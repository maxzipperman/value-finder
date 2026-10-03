"""Separate, exact older lag reconciliation and never-sent continuation.

Default operations only verify. Actual state changes and paid sends are hub-only.
Operational pins/certificates/approval archives stay local, outside git.
"""
from __future__ import annotations

import argparse
import builtins
import copy
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parent
OLD_ROOT = "03391fd2c0bf224f053aae102fe1e3c520db58f9fa97837d34244e4fc54988c0"
OLD_COMMIT = "4167aad74520661731157a77dac0af9f3fc1febe"
SOURCE_ROOT = "4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d"
OLD_PACKET = ARCHIVE / "older/older-2020-22"
BUNDLE = ARCHIVE / "acquisition/football-archive-v4"
RUNTIME_BASE = Path.home() / "Library/Application Support/ValueFinder/football-acquisition-state"
REMAINING_COUNT, NEW_CAP, PROBE = 1786, 53580, 1687
PARTIAL_STATUS = "older_epoch_partial_reconciled"
FILES = ("manifest.json", "requests.json", "request-list.csv", "seed.json",
         "partial-binding.json", "exact-lag-policy.json", "cache-reconciliation.json")


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
    prefix = "older_lag_capture_" + identity({n: digest(b) for n, b in captured.items()})[:16]

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
        if name.split(".")[0] not in external:
            raise ImportError("Undeclared external import: " + name)
        return original(name, globals, locals, fromlist, 0)
    return load


def historical(packet=OLD_PACKET, bundle=BUNDLE):
    """Authenticate entire executed packet BEFORE compiling historical helpers."""
    packet, bundle = Path(packet), Path(bundle)
    cert = read(packet / "FREEZE.json")
    code_paths = {"code/stage.py": packet.parent / "stage.py",
                  "code/execute.py": packet.parent / "execute.py",
                  "code/f2_handoff.py": packet.parent.parent / "f2_handoff.py"}
    expected = {"manifest.json", "requests.json", "request-list.csv", "seed.json",
                "coverage-decision.json", "cache-reconciliation.json"} | set(code_paths)
    if set(cert["files"]) != expected or {p.name for p in packet.iterdir()} != (expected - set(code_paths)) | {"FREEZE.json"}:
        raise ValueError("Historical packet inventory changed")
    captured = {name: regular(code_paths[name] if name in code_paths else packet / name) for name in expected}
    hashes = {name: digest(data) for name, data in captured.items()}
    if cert != {"files": hashes, "root": OLD_ROOT} or identity(hashes) != OLD_ROOT:
        raise ValueError("Historical packet/code root changed before import")
    load = closed_modules({Path(n).stem: captured[n] for n in code_paths},
                          {Path(n).stem: p for n, p in code_paths.items()})
    stage, old = load("stage"), load("execute")
    stage.source(bundle)
    vcert = read(bundle / "FREEZE.json")
    vcaptured = {str(p.relative_to(bundle)): regular(p) for p in bundle.rglob("*")
                 if p.is_file() and p.name != "FREEZE.json"}
    vhashes = {n: digest(b) for n, b in vcaptured.items()}
    if (vhashes != vcert["file_sha256"] or identity(vhashes) != SOURCE_ROOT
            or vcert["bundle_root_sha256"] != SOURCE_ROOT):
        raise ValueError("Complete v4 dependency inventory changed before import")
    py = {n: b for n, b in vcaptured.items() if n.endswith(".py")}
    names = {n: (n[:-12] if n.endswith("/__init__.py") else n[:-3]).replace("/", ".") for n in py}
    vload = closed_modules({names[n]: b for n, b in py.items()}, {names[n]: bundle / n for n in py})
    base = vload("executor")
    vload("validator").verify(bundle, SOURCE_ROOT, check_cache=True)
    return stage, old, base, vload


def lag_record(row, record, *, limit=600):
    """A lagged HTTP200 is missing only; this never validates a usable quote."""
    if (record.get("http_status") != 200 or record.get("cache_key") != row["cache_key"]
            or record.get("sport") != row["sport"] or record.get("source") != row["source"]
            or record.get("url") != "https://api.the-odds-api.com/v4" + row["path"]
            or json.loads(record["params_json"]) != row["params"]):
        raise ValueError("Lag record HTTP/request identity differs")
    body = json.loads(record["body"])
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise ValueError("Historical body/data missing")
    returned = stamp(body["timestamp"])
    lag = (stamp(row["requested_utc"]) - returned).total_seconds()
    if lag <= limit or not stamp(body["previous_timestamp"]) < returned < stamp(body["next_timestamp"]):
        raise ValueError("Not a known lagged historical snapshot with valid neighbors")
    headers = json.loads(record["headers_json"])
    last, used, remaining = [integer(headers.get(k)) for k in
                             ("x-requests-last", "x-requests-used", "x-requests-remaining")]
    if last > row["max_new_credits"] or row["max_new_credits"] != 30:
        raise ValueError("Lag bill exceeds original reservation")
    return {"lag_seconds": lag, "billed": last, "used": used, "remaining": remaining, "headers": headers}


def record_at(path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    data = regular(path)
    rows = pq.read_table(pa.BufferReader(data)).to_pylist()
    if len(rows) != 1:
        raise ValueError("Exactly one cached record required")
    return rows[0], digest(data)


def response_path(runtime, row):
    directory = Path(runtime) / "data/raw" / row["sport"] / row["source"]
    matches = list(directory.glob("*/" + row["cache_key"] + ".parquet"))
    if len(matches) != 1:
        raise ValueError("Exactly one cached response required")
    regular(matches[0])
    return matches[0]


def check_history(state, rows, runtime, base, protocol, *, pending=True):
    allow = {r["request_id"]: r for r in rows if r["max_new_credits"]}
    expected_pending = state["pending"] if pending else None
    if (len(state["attempts"]) != 481 or state["probe_credits"] != PROBE or state["slice_cap"] != 68010
            or set(state["attempts"]) - set(allow) or len(set(a["cache_key"] for a in state["attempts"].values())) != 481):
        raise ValueError("Original attempted scope or accounting baseline differs")
    receipts = []
    for rid, attempt in state["attempts"].items():
        row = allow[rid]
        if (attempt["reserved_credits"] != 30 or type(attempt["reserved_credits"]) is not int
                or attempt["cache_key"] != row["cache_key"] or attempt.get("send_started") is not True):
            raise ValueError("Original durable reservation/send identity differs")
        if rid == expected_pending:
            if attempt["status"] != "pending":
                raise ValueError("Pending original attempt changed")
            continue
        if attempt["status"] != "completed":
            raise ValueError("Unexpected historical terminal category")
        path = response_path(runtime, row)
        record, record_sha = record_at(path)
        receipt_path = Path(runtime) / "receipts" / (rid + ".json")
        receipt_bytes = regular(receipt_path)
        receipt = json.loads(receipt_bytes)
        base.validate_response(row, record, protocol)
        if (Path(attempt["response_path"]).absolute() != path.absolute() or attempt["response_sha256"] != record_sha
                or attempt["receipt_sha256"] != digest(receipt_bytes) or receipt["request_id"] != rid
                or receipt["cache_key"] != row["cache_key"] or receipt["record_sha256"] != record_sha
                or identity(receipt["record"]) != identity(record) or receipt["body_sha256"] != digest(record["body"].encode())
                or receipt["headers"] != json.loads(record["headers_json"])
                or type(attempt["billed_credits"]) is not int
                or attempt["billed_credits"] != integer(receipt["headers"]["x-requests-last"])
                or not 0 <= attempt["billed_credits"] <= 30):
            raise ValueError("Historical receipt/response/billing evidence changed")
        receipts.append([rid, record_sha, digest(receipt_bytes)])
    if len(receipts) != 480 or sum(a.get("billed_credits", 0) for a in state["attempts"].values()) != 14400:
        raise ValueError("Original completed scope/billing differs")
    return identity(sorted(receipts))


def pure_missing(base, state, protocol, row, record, path, record_sha):
    """Apply the reviewed counter rules to a private copy; no constructor/save."""
    observed = lag_record(row, record)
    result = copy.deepcopy(state)
    rid = row["request_id"]
    attempt = result["attempts"][rid]
    if result["pending"] != rid or attempt["status"] != "pending" or attempt["reserved_credits"] != 30:
        raise ValueError("Not the exactly reserved pending attempt")
    billing = {k: observed["headers"][k] for k in ("x-requests-last", "x-requests-used", "x-requests-remaining")}
    if attempt.get("observed_http_status") != 200 or attempt.get("observed_billing_headers") != billing:
        raise ValueError("Observed billing/HTTP evidence differs from cache")
    ledger = base.Ledger.__new__(base.Ledger)
    ledger.state, ledger.protocol = result, protocol
    ledger.save = lambda: None
    ledger.measure_counters(observed["used"], observed["remaining"],
                            ledger.billed() - result["epoch"]["start_billed"] + observed["billed"])
    receipt = {"request_id": rid, "cache_key": row["cache_key"], "status": "missing",
               "reason": "snapshot_lag", "record_sha256": record_sha,
               "body_sha256": digest(record["body"].encode()), "headers": observed["headers"],
               "record": record, "usable_quote": False}
    attempt.update(status="missing", missing_reason="snapshot_lag", billed_credits=observed["billed"],
                   response_path=str(Path(path).absolute()), response_sha256=record_sha,
                   receipt_sha256=digest(canonical(receipt) + b"\n"))
    result.update(pending=None, stopped=None, status=PARTIAL_STATUS)
    ledger.budget_check(0)
    return result, receipt, observed


def preview(pins, original_auth, coverage_path, *, stopped_bytes=None):
    stage, old, base, _ = historical()
    # The executed root authenticates its original cache inventory as historical
    # evidence. Later child caches cannot be compared to a pre-purchase inventory.
    # Revalidate immutable source/coverage/ancestry here; the successor separately
    # reconciles every untouched key against today's stores under the shared lock.
    _, rows = stage.source(BUNDLE)
    manifest, parent = read(OLD_PACKET / "manifest.json"), read(OLD_PACKET / "seed.json")
    if (read(OLD_PACKET / "requests.json") != rows
            or regular(OLD_PACKET / "request-list.csv") != stage.csv_bytes(BUNDLE, rows)
            or read(OLD_PACKET / "coverage-decision.json") != stage.coverage(coverage_path)
            or parent != stage.seed(parent["ledger_path"], (r for r in rows if r["max_new_credits"]), require_f2=True)):
        raise ValueError("Historical source/coverage/predecessor differs")
    runtime = RUNTIME_BASE / OLD_ROOT
    if stage.RUNTIME_BASE != RUNTIME_BASE or base.runtime_path(OLD_ROOT) != runtime:
        raise ValueError("Fixed runtime namespace differs")
    data = regular(runtime / "spending-ledger.json") if stopped_bytes is None else stopped_bytes
    if digest(data) != pins["stopped_ledger_sha256"]:
        raise ValueError("Exact stopped ledger hash differs")
    state = json.loads(data)
    if (state["bundle_root_sha256"] != OLD_ROOT or state["status"] != "halted" or not state["stopped"]
            or state["pending"] != pins["request_id"] or state["predecessor_seed"] != parent):
        raise ValueError("Exact stopped parent/pending identity differs")
    reused = {r["request_id"]: r["cache_sha256"] for r in rows if not r["max_new_credits"]}
    if any(reused.get(rid) != value for rid, value in state["cache_reuse"].items()):
        raise ValueError("Original reused identities differ")
    # The original approval is archived evidence, never live send permission.
    internal, _ = old.exact_approval(base, original_auth, manifest, OLD_ROOT, OLD_COMMIT, live=False)
    auth_sha = identity(internal)
    if state["authorization_sha256"] != auth_sha:
        raise ValueError("Historical authorization differs")
    reg = read(RUNTIME_BASE / "registrations" / (OLD_ROOT + ".json"))
    if reg != {"bundle_root_sha256": OLD_ROOT, "authorization_sha256": auth_sha, "runtime_path": str(runtime)}:
        raise ValueError("Original central registration differs")
    if read(runtime / "INITIALIZED.json") != {"bundle_root_sha256": OLD_ROOT, "probe_credits": PROBE}:
        raise ValueError("Original initialization differs")
    run = read(runtime / "run-manifest.json")
    if (run.get("stage") != "older-priority-2" or run.get("packet_root") != OLD_ROOT
            or run.get("source_root") != SOURCE_ROOT or run.get("predecessor") != parent
            or run.get("external_authorization_sha256") != identity(original_auth)
            or run.get("internal_priority_bridge") != 1 or run.get("commit") != OLD_COMMIT
            or run.get("runtime") != read(BUNDLE / "runtime-lock.json")):
        raise ValueError("Executed original run manifest differs")
    protocol = read(BUNDLE / "protocol.json")
    history_sha = check_history(state, rows, runtime, base, protocol)
    row = next(r for r in rows if r["request_id"] == pins["request_id"])
    path = response_path(runtime, row)
    record, response_sha = record_at(path)
    if response_sha != pins["response_sha256"]:
        raise ValueError("Exact pending response hash differs")
    post, receipt, observed = pure_missing(base, state, protocol, row, record, path, response_sha)
    if observed["billed"] != 30 or sum(a["reserved_credits"] for a in post["attempts"].values()) != 14430:
        raise ValueError("Exact stopped response bill/reservation differs")
    remaining = remaining_rows(rows, post)
    proposal = {"version": 1, "old_root": OLD_ROOT, "old_commit": OLD_COMMIT,
        "source_root": SOURCE_ROOT, "recovery_code_sha256": sha(__file__), "protocol_sha256": sha(HERE / "PROTOCOL.md"),
        "prior_ledger_sha256": digest(data), "request_id": row["request_id"], "response_sha256": response_sha,
        "receipt_sha256": digest(canonical(receipt) + b"\n"), "history_sha256": history_sha,
        "old_request_set_sha256": manifest["request_set_sha256"], "old_csv_sha256": manifest["request_list_sha256"],
        "original_authorization_sha256": identity(original_auth), "run_manifest_sha256": sha(runtime / "run-manifest.json"),
        "seed": parent, "observed": observed, "reserved": 14430, "billed": 14430,
        "remaining_set_sha256": identity(remaining), "remaining_count": REMAINING_COUNT, "remaining_cap": NEW_CAP}
    proposal_sha = identity(proposal)
    post["older_lag_reconciliation"] = {"proposal_sha256": proposal_sha, "prior_ledger_sha256": digest(data)}
    certificate = {"proposal": proposal, "proposal_sha256": proposal_sha, "post_ledger_sha256": digest(canonical(post) + b"\n")}
    return certificate, post, receipt, base


def remaining_rows(rows, state):
    if state.get("pending") or state.get("stopped") or state.get("status") != PARTIAL_STATUS:
        raise ValueError("Actual certified settled partial required")
    if any(a["status"] not in ("completed", "missing") for a in state["attempts"].values()):
        raise ValueError("Parent retains an uncertain attempt")
    paid = [r for r in rows if r["max_new_credits"]]
    remaining = [r for r in paid if r["request_id"] not in state["attempts"]]
    if (len(rows), len(paid), len(state["attempts"]), len(remaining), sum(r["max_new_credits"] for r in remaining)) != (2279, 2267, 481, REMAINING_COUNT, NEW_CAP):
        raise ValueError("Exact remaining original scope differs")
    if len({r["cache_key"] for r in remaining}) != REMAINING_COUNT:
        raise ValueError("Remaining identity conflict")
    if {r["cache_key"] for r in remaining} & {a["cache_key"] for a in state["attempts"].values()}:
        raise ValueError("Attempted cache identity would be repurchased")
    return remaining


def active_authority(auth, required_lines, *, commit=None, authenticate=True):
    hub = auth.get("hub_go_ahead", {})
    body = hub.get("comment_body", "")
    if (auth.get("status") != "approved" or not auth.get("human_authorization_evidence")
            or not re.fullmatch("[a-f0-9]{40}", auth.get("execution_commit", ""))
            or (commit is not None and auth["execution_commit"] != commit)
            or hub.get("status") != "approved"
            or not re.fullmatch(r"https://github\.com/maxzipperman/value-finder/pull/(99|129)#issuecomment-[0-9]+", hub.get("comment_url", ""))
            or any(re.search(r"\b(HALTED|EXHAUSTED|REVOKED|NOT APPROVED)\b", line, re.I) for line in body.splitlines())
            or any(body.splitlines().count(line) != 1 for line in required_lines)):
        raise ValueError("Fresh active exact hub authority required")
    if authenticate:
        cid = hub["comment_url"].rsplit("-", 1)[-1]
        live = json.loads(subprocess.check_output(["gh", "api", "repos/maxzipperman/value-finder/issues/comments/" + cid], text=True))
        if (live.get("html_url") != hub["comment_url"] or live.get("body") != body
                or live.get("user", {}).get("login") != "maxzipperman"):
            raise ValueError("Live exact hub authority changed")


def offline_authority(auth, certificate, *, commit=None, authenticate=True):
    p = certificate["proposal"]
    if (auth.get("proposal_sha256") != certificate["proposal_sha256"]
            or auth.get("prior_ledger_sha256") != p["prior_ledger_sha256"]
            or auth.get("request_id") != p["request_id"] or auth.get("response_sha256") != p["response_sha256"]):
        raise ValueError("Offline approval does not bind exact local evidence")
    line = (f"APPROVED offline snapshot lag: proposal {certificate['proposal_sha256']}, root {OLD_ROOT}, "
            f"commit {auth.get('execution_commit', '')}")
    active_authority(auth, [line], commit=commit, authenticate=authenticate)


def clean_commit(paths):
    repo = Path(subprocess.check_output(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], text=True).strip())
    relative = [str(Path(p).absolute().relative_to(repo)) for p in paths]
    subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", *relative], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "diff", "--exit-code", "HEAD", "--", *relative], check=True, stdout=subprocess.DEVNULL)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def durable_bytes(path, data, base):
    path = Path(path)
    if path.exists():
        if regular(path) != data:
            raise ValueError("Existing reconciliation evidence conflicts")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    base.durable_directory(path.parent)


def install(certificate_path, pins_path, original_auth_path, approval_path, coverage_path, *, checkpoint=lambda _: None):
    """Hub only. Ledger is written LAST; this function never sends or loads a key."""
    cert, pins, original, approval = map(read, (certificate_path, pins_path, original_auth_path, approval_path))
    commit = clean_commit([__file__, HERE / "PROTOCOL.md"])
    offline_authority(approval, cert, commit=commit)
    runtime = RUNTIME_BASE / OLD_ROOT
    with (RUNTIME_BASE / "followup-purchase.lock").open("a") as global_lock, (runtime / "acquisition.lock").open("a") as local_lock:
        fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(local_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current, post, receipt, base = preview(pins, original, coverage_path)
        if current != cert:
            raise ValueError("Exact reviewed offline certificate changed")
        offline_authority(approval, cert, commit=commit)
        directory = runtime / "older-lag-recovery-v1"
        durable_bytes(directory / "stopped-ledger.json", regular(runtime / "spending-ledger.json"), base)
        checkpoint("after_backup")
        for name, obj in (("pins.json", pins), ("original-authorization.json", original),
                          ("certificate.json", cert), ("offline-approval.json", approval)):
            durable_bytes(directory / name, canonical(obj) + b"\n", base)
        checkpoint("after_authority")
        durable_bytes(runtime / "receipts" / (pins["request_id"] + ".json"), canonical(receipt) + b"\n", base)
        checkpoint("after_receipt")
        if sha(runtime / "spending-ledger.json") != pins["stopped_ledger_sha256"]:
            raise ValueError("Original ledger changed before certified transition")
        base.atomic(runtime / "spending-ledger.json", post)
        checkpoint("after_transition")
        if sha(runtime / "spending-ledger.json") != cert["post_ledger_sha256"]:
            raise ValueError("Installed partial differs")
        return {"status": PARTIAL_STATUS, "paid_calls": 0, "ledger_sha256": cert["post_ledger_sha256"]}


def verified_partial(coverage_path):
    runtime = RUNTIME_BASE / OLD_ROOT
    directory = runtime / "older-lag-recovery-v1"
    cert = read(directory / "certificate.json")
    current, post, receipt, base = preview(read(directory / "pins.json"), read(directory / "original-authorization.json"),
                                        coverage_path, stopped_bytes=regular(directory / "stopped-ledger.json"))
    if current != cert or sha(runtime / "spending-ledger.json") != cert["post_ledger_sha256"] or read(runtime / "spending-ledger.json") != post:
        raise ValueError("ACTUAL installed certified partial required; preview is not a predecessor")
    if regular(runtime / "receipts" / (cert["proposal"]["request_id"] + ".json")) != canonical(receipt) + b"\n":
        raise ValueError("Installed missing receipt changed")
    # Historical offline authority binds the ORIGINAL transition commit.
    offline_authority(read(directory / "offline-approval.json"), cert)
    return cert, post, base


def policy(rows):
    return {"version": 1, "reason": "snapshot_lag", "eligible_request_ids": sorted(r["request_id"] for r in rows),
        "request_set_sha256": identity(rows), "maximum_missing": REMAINING_COUNT,
        "maximum_reserved_missing_credits": NEW_CAP, "http_status": 200,
        "known_lag_greater_than_seconds": 600, "usable_quote_maximum_lag_seconds": 600,
        "identity": "exact original sport/source/url/params/cache key", "body": "historical data list and ordered aware neighbors",
        "billing": "exact nonnegative last/used/remaining; last <= original 30 reservation",
        "retain_full_reservation": True, "retain_observed_bill": True, "retain_full_denominator": True,
        "usable_quote": False, "automatic_retries": 0, "pending_repair": False}


def cache_inventory(rows, stage, exclude_root=None):
    roots = stage.raw_roots(exclude_root)
    for row in rows:
        if any(list((Path(raw) / row["sport"] / row["source"]).glob("*/" + row["cache_key"] + ".parquet")) for raw in roots):
            raise ValueError("Exact remaining paid cache overlap; no repurchase")
    return {"raw_roots": roots, "paid_exact_overlap": 0, "request_count": REMAINING_COUNT,
            "unrelated_cache_files_read": False}


def remaining_csv(rows):
    reader = csv.DictReader(io.StringIO(regular(OLD_PACKET / "request-list.csv").decode(), newline=""))
    keys = [r["cache_key"] for r in rows]
    lines = [r for r in reader if r["cache_key"] in set(keys)]
    if [r["cache_key"] for r in lines] != keys:
        raise ValueError("Original remaining CSV identity/order differs")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
    writer.writeheader(); writer.writerows(lines)
    return out.getvalue().encode()


def packet_content(packet):
    packet = Path(packet)
    if {p.name for p in packet.iterdir()} != set(FILES) | {"FREEZE.json"}:
        raise ValueError("Successor packet inventory changed")
    files = {n: sha(packet / n) for n in FILES}
    files.update({"code/recovery.py": sha(__file__), "policy/PROTOCOL.md": sha(HERE / "PROTOCOL.md"),
                  "dependencies/old-root": OLD_ROOT, "dependencies/v4-root": SOURCE_ROOT})
    return files


def prepare(packet, coverage_path):
    # All actual predecessor verification occurs BEFORE even creating output.
    cert, state, _ = verified_partial(coverage_path)
    stage, _, _, _ = historical()
    rows = remaining_rows(read(OLD_PACKET / "requests.json"), state)
    caches = cache_inventory(rows, stage)
    debit = integer(state["other_usage_reserved"]) + sum(integer(a["reserved_credits"]) for a in state["attempts"].values())
    if PROBE + debit + NEW_CAP > 250000:
        raise ValueError("Successor would exceed cumulative first-tranche ceiling")
    seed = {"root": OLD_ROOT, "ledger_path": str(RUNTIME_BASE / OLD_ROOT / "spending-ledger.json"),
        "ledger_sha256": cert["post_ledger_sha256"], "probe_credits": PROBE,
        "cumulative_debit_without_probe": debit, "f2_union_proof_sha256": state["predecessor_seed"]["f2_union_proof_sha256"]}
    binding = {"old_root": OLD_ROOT, "old_commit": OLD_COMMIT, "proposal_sha256": cert["proposal_sha256"],
               "certificate_sha256": identity(cert), "post_ledger_sha256": cert["post_ledger_sha256"]}
    csv_data = remaining_csv(rows)
    manifest = {"stage": "older-lag-continuation", "priority": 2, "source_root": SOURCE_ROOT,
        "original_root": OLD_ROOT, "original_request_count": 2279, "original_reuse_count": 12,
        "retained_parent_attempts": 481, "request_count": REMAINING_COUNT, "new_credits": NEW_CAP,
        "request_set_sha256": identity(rows), "request_list_sha256": digest(csv_data),
        "policy_sha256": identity(policy(rows)), "outcomes_joined": False}
    packet = Path(packet)
    packet.mkdir(parents=True, exist_ok=False)
    values = {"manifest.json": manifest, "requests.json": rows, "seed.json": seed,
        "partial-binding.json": binding, "exact-lag-policy.json": policy(rows), "cache-reconciliation.json": caches}
    for name, obj in values.items():
        (packet / name).write_bytes(canonical(obj) + b"\n")
    (packet / "request-list.csv").write_bytes(csv_data)
    # No transient self/commit identity in content; external approval binds HEAD.
    hashes = {n: sha(packet / n) for n in FILES}
    hashes.update({"code/recovery.py": sha(__file__), "policy/PROTOCOL.md": sha(HERE / "PROTOCOL.md"),
                   "dependencies/old-root": OLD_ROOT, "dependencies/v4-root": SOURCE_ROOT})
    root = identity(hashes)
    (packet / "FREEZE.json").write_bytes(canonical({"root": root, "files": hashes}) + b"\n")
    return root


def verify_packet(packet, root, coverage_path):
    packet = Path(packet)
    hashes = packet_content(packet)
    if read(packet / "FREEZE.json") != {"root": root, "files": hashes} or identity(hashes) != root:
        raise ValueError("Successor content identity changed")
    cert, state, base = verified_partial(coverage_path)
    rows = remaining_rows(read(OLD_PACKET / "requests.json"), state)
    m = read(packet / "manifest.json")
    expected_m = {"stage": "older-lag-continuation", "priority": 2, "source_root": SOURCE_ROOT,
        "original_root": OLD_ROOT, "original_request_count": 2279, "original_reuse_count": 12,
        "retained_parent_attempts": 481, "request_count": REMAINING_COUNT, "new_credits": NEW_CAP,
        "request_set_sha256": identity(rows), "request_list_sha256": digest(remaining_csv(rows)),
        "policy_sha256": identity(policy(rows)), "outcomes_joined": False}
    seed = read(packet / "seed.json")
    expected_seed = {"root": OLD_ROOT, "ledger_path": str(RUNTIME_BASE / OLD_ROOT / "spending-ledger.json"),
        "ledger_sha256": cert["post_ledger_sha256"], "probe_credits": PROBE,
        "cumulative_debit_without_probe": integer(state["other_usage_reserved"]) + sum(integer(a["reserved_credits"]) for a in state["attempts"].values()),
        "f2_union_proof_sha256": state["predecessor_seed"]["f2_union_proof_sha256"]}
    binding = {"old_root": OLD_ROOT, "old_commit": OLD_COMMIT, "proposal_sha256": cert["proposal_sha256"],
               "certificate_sha256": identity(cert), "post_ledger_sha256": cert["post_ledger_sha256"]}
    stage, _, _, _ = historical()
    if (m != expected_m or seed != expected_seed or read(packet / "requests.json") != rows
            or regular(packet / "request-list.csv") != remaining_csv(rows)
            or read(packet / "exact-lag-policy.json") != policy(rows) or read(packet / "partial-binding.json") != binding
            or read(packet / "cache-reconciliation.json") != cache_inventory(rows, stage, root)):
        raise ValueError("Exact actual parent/remaining list/policy/cache inventory differs")
    base.execution_context(packet, root, base.runtime_path(root))
    if PROBE + seed["cumulative_debit_without_probe"] + NEW_CAP > 250000:
        raise ValueError("Successor cumulative ceiling exceeded")
    return m, rows, seed, base


def paid_authority(auth, m, root, commit, base, *, authenticate=True):
    rec = auth.get("account_reconciliation", {})
    if (auth.get("stage") != "older-lag-continuation" or auth.get("priority") != 2
            or auth.get("bundle_root_sha256") != root or auth.get("max_new_credits") != NEW_CAP
            or rec.get("account_only_recovery") or "pre_run_other_usage_budget_debit" in rec
            or not re.fullmatch(r"https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+", auth.get("hub_go_ahead", {}).get("comment_url", ""))):
        raise ValueError("Distinct exact successor authority required; no recovery/debit override")
    base.validate_reconciliation(rec, root)
    lines = [f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {NEW_CAP} credits, commit {commit}",
             f"APPROVED content: root {root}, stage older-lag-continuation",
             f"APPROVED account ceiling: max-baseline-used {rec['max_baseline_used']}, root {root}",
             f"APPROVED account reconciliation: sha256 {identity(rec)}, root {root}",
             f"APPROVED snapshot lag policy: sha256 {m['policy_sha256']}, max-missing {REMAINING_COUNT}, root {root}"]
    active_authority(auth, lines, commit=commit, authenticate=authenticate)
    internal = {**auth, "priority": 1}
    bridge = {**m, "new_credits_by_priority": {"1": NEW_CAP}}
    base.validate_authorization(internal, bridge, root, commit)
    return internal, bridge


def continuation_ledger(base, finite_policy):
    allowed = set(finite_policy["eligible_request_ids"])
    class LagLedger(base.Ledger):
        def complete(self, row, record, path):
            # HTTP/status/identity/body/billing failures never become generic missing.
            try:
                lag = (stamp(row["requested_utc"]) - stamp(json.loads(record["body"])["timestamp"])).total_seconds()
            except (ValueError, KeyError, TypeError):
                return super().complete(row, record, path)
            if lag <= 600:
                return super().complete(row, record, path)
            if row["request_id"] not in allowed or finite_policy != policy(self.original_rows):
                raise ValueError("Lag outside exact finite prospective policy")
            if sum(a["status"] == "missing" for a in self.state["attempts"].values()) >= REMAINING_COUNT:
                raise ValueError("Finite missing maximum exceeded")
            post, receipt, _ = pure_missing(base, self.state, self.protocol, row, record, path, sha(path))
            base.atomic(self.folder / "receipts" / (row["request_id"] + ".json"), receipt)
            self.checkpoint("after_receipt")
            # Preserve the continuation state; partial status belongs only to parent.
            post["status"] = "running"
            self.state = post
            self.save()
    return LagLedger


def terminal_evidence(ledger, rows, base, finite_policy):
    allow = {r["request_id"]: r for r in rows}
    for rid, attempt in ledger.state["attempts"].items():
        if rid not in allow or attempt["status"] not in ("completed", "missing"):
            raise ValueError("Unknown/nonterminal successor attempt")
        row = allow[rid]
        path = response_path(ledger.folder, row)
        record, record_sha = record_at(path)
        receipt_bytes = regular(ledger.folder / "receipts" / (rid + ".json"))
        receipt = json.loads(receipt_bytes)
        if (type(attempt["reserved_credits"]) is not int or attempt["reserved_credits"] != 30
                or attempt["cache_key"] != row["cache_key"] or attempt.get("send_started") is not True
                or Path(attempt["response_path"]).absolute() != path.absolute()
                or attempt["response_sha256"] != record_sha or attempt["receipt_sha256"] != digest(receipt_bytes)
                or receipt["request_id"] != rid or receipt["cache_key"] != row["cache_key"]
                or receipt["record_sha256"] != record_sha or identity(receipt["record"]) != identity(record)
                or receipt["body_sha256"] != digest(record["body"].encode())
                or receipt["headers"] != json.loads(record["headers_json"])
                or type(attempt["billed_credits"]) is not int or not 0 <= attempt["billed_credits"] <= 30
                or attempt["billed_credits"] != integer(receipt["headers"]["x-requests-last"])):
            raise ValueError("Successor receipt/cache/billing evidence changed; no repurchase")
        if attempt["status"] == "missing":
            if (rid not in finite_policy["eligible_request_ids"] or receipt.get("status") != "missing"
                    or receipt.get("reason") != "snapshot_lag" or receipt.get("usable_quote") is not False):
                raise ValueError("Unapproved successor missing category")
            lag_record(row, record)
        else:
            base.validate_response(row, record, ledger.protocol)


def run(packet, root, coverage_path, auth, *, key, fake_session=None, checkpoint=lambda _: None):
    """Hub-only sends; no pending repair, no automatic retries, no list regeneration."""
    m, rows, seed, base = verify_packet(packet, root, coverage_path)
    commit = clean_commit([__file__, HERE / "PROTOCOL.md", *(Path(packet) / n for n in (*FILES, "FREEZE.json"))])
    internal, bridge = paid_authority(auth, m, root, commit, base)
    if base.current_runtime() != read(BUNDLE / "runtime-lock.json"):
        raise ValueError("Reviewed runtime differs")
    effective = [{**row, "priority": 1} for row in rows]
    bridge["requests"] = effective
    runtime = base.runtime_path(root)
    with (RUNTIME_BASE / "followup-purchase.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m2, rows2, seed2, base = verify_packet(packet, root, coverage_path)
        if (m2, rows2, seed2) != (m, rows, seed):
            raise ValueError("Successor inputs changed under shared lock")
        stage, old, _, _ = historical()
        old.global_settled(root)
        internal, bridge = paid_authority(auth, m, root, commit, base)
        bridge["requests"] = effective
        if (runtime / "spending-ledger.json").exists() and read(runtime / "spending-ledger.json").get("status") == "older_epoch_complete":
            raise ValueError("Completed successor authority is exhausted; use read-only verification")
        base.register_runtime(runtime, root, internal)
        cls = continuation_ledger(base, policy(rows))
        ledger = cls(runtime, read(BUNDLE / "protocol.json"), bridge, root, internal, read(BUNDLE / "probe-spending-ledger.json"))
        ledger.original_rows = rows
        client = None
        try:
            if ledger.state.get("predecessor_seed") not in (None, seed):
                raise ValueError("Successor predecessor changed")
            ledger.state["predecessor_seed"] = seed
            ledger.state["other_usage_reserved"] = max(ledger.state["other_usage_reserved"], seed["cumulative_debit_without_probe"])
            ledger.save(); ledger.budget_check(0)
            terminal_evidence(ledger, rows, base, policy(rows))
            RawCache, _, BulkClient, Call, new_session, remember_secret, _ = base.vendor_imports(BUNDLE, runtime)
            secret = key() if callable(key) else key
            if not secret or len(secret) < 8:
                raise ValueError("Missing API key")
            remember_secret(secret)
            class AuthorizedSession(base.GuardedSession):
                def get(self, url, **kwargs):
                    # Fresh exact live authority is checked before EVERY send.
                    paid_authority(auth, m, root, commit, base)
                    if packet_content(packet) != read(Path(packet) / "FREEZE.json")["files"]:
                        raise ValueError("Successor source/content changed before send")
                    return super().get(url, **kwargs)
            session = AuthorizedSession(fake_session or new_session(), ledger, effective)
            session.ledger_key = secret
            cache = RawCache(runtime / "data/raw")
            client = BulkClient(cache, max_credits=NEW_CAP - ledger.reserved(), floor=ledger.protocol["budgets"]["account_reserve_floor"],
                               rate_per_sec=4, max_retries=0, session=session, api_key=secret,
                               alarm_margin=ledger.protocol["billing_reconciliation"]["bulk_client_alarm_margin_credits"])
            if fake_session:
                client.limiter.wait = lambda: None
            ledger.checkpoint = checkpoint
            account = client.account()
            ledger.account(integer(account["used"]), integer(account["remaining"]))
            base.atomic(runtime / "run-manifest.json", {"stage": "older-lag-continuation", "packet_root": root,
                "predecessor": seed, "source_root": SOURCE_ROOT, "external_authorization_sha256": identity(auth),
                "internal_priority_bridge": 1, "commit": commit, "runtime": base.current_runtime(),
                "policy_sha256": m["policy_sha256"], "scope": "exact never-sent original rows; no retries; no outcomes"})
            for row, effective_row in zip(rows, effective):
                if row["request_id"] in ledger.state["attempts"]:
                    continue
                if cache.lookup(row["sport"], row["source"], row["cache_key"]) is not None:
                    raise ValueError("Unreconciled own cache; no repurchase")
                if cache_inventory([row], stage, root)["paid_exact_overlap"]:
                    raise ValueError("External cache overlap")
                call = Call("FOOTBALL_ARCHIVE_OLDER_LAG", row["sport"], row["source"], row["path"],
                            tuple(sorted(row["params"].items())), stamp(row["requested_utc"]), row["max_credits"], False, cache_sport=row["sport"])
                if call.key != row["cache_key"]:
                    raise ValueError("Original request cache identity differs")
                ledger.reserve(effective_row); checkpoint("after_reservation")
                record = client.fetch(call); checkpoint("after_transport")
                path = response_path(runtime, row)
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
                base.durable_directory(path.parent); checkpoint("after_response_durability")
                ledger.complete(effective_row, record, path); checkpoint("after_completion")
            terminal_evidence(ledger, rows, base, policy(rows))
            if set(ledger.state["attempts"]) != {row["request_id"] for row in rows}:
                raise ValueError("Full successor denominator not completed")
            verify_packet(packet, root, coverage_path)
            ledger.state["status"] = "older_epoch_complete"; ledger.save()
            return {"status": "older_epoch_complete", "root": root, "ledger_sha256": sha(ledger.path),
                "new_requests": len(ledger.state["attempts"]), "reserved": ledger.reserved(), "billed": ledger.billed(),
                "missing": sum(a["status"] == "missing" for a in ledger.state["attempts"].values()),
                "original_denominator": 2279, "coverage_review_required": True}
        except BaseException:
            ledger.halt("Older successor stopped; full reservations retained; no automatic repair/resend")
            raise
        finally:
            if client:
                client.session.close()
            ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preview", "install", "prepare", "verify", "run"))
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--pins", type=Path)
    parser.add_argument("--original-authorization", type=Path)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--root")
    parser.add_argument("--confirm-offline", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if args.operation == "preview":
        if not args.pins or not args.original_authorization or not args.certificate:
            parser.error("Local pins/original authorization/output certificate required")
        cert, _, _, _ = preview(read(args.pins), read(args.original_authorization), args.coverage)
        if args.certificate.exists():
            if read(args.certificate) != cert:
                raise ValueError("Existing certificate differs")
        else:
            args.certificate.write_bytes(canonical(cert) + b"\n")
        print(json.dumps({"offline": True, "proposal_sha256": cert["proposal_sha256"], "paid_calls": 0}))
    elif args.operation == "install":
        if not args.confirm_offline or not all((args.pins, args.original_authorization, args.certificate, args.authorization)):
            parser.error("Hub-only --confirm-offline and exact local evidence/authority required")
        print(json.dumps(install(args.certificate, args.pins, args.original_authorization, args.authorization, args.coverage)))
    elif args.operation == "prepare":
        if not args.packet:
            parser.error("New packet output required")
        print(json.dumps({"root": prepare(args.packet, args.coverage), "new_cap": NEW_CAP}))
    elif args.operation == "verify" or not args.confirm_paid:
        if not args.packet or not args.root:
            parser.error("Packet/root required")
        m, _, _, _ = verify_packet(args.packet, args.root, args.coverage)
        print(json.dumps({"offline": True, "new_cap": m["new_credits"]}))
    else:
        if not all((args.packet, args.root, args.authorization, args.key_file)):
            parser.error("Hub-only --confirm-paid and exact packet/root/authority/key-file required")
        def key():
            from dotenv import dotenv_values
            return dotenv_values(args.key_file).get("ODDS_API_KEY")
        print(json.dumps(run(args.packet, args.root, args.coverage, read(args.authorization), key=key)))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
