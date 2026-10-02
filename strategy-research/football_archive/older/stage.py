"""Offline priority-2 packet adapter for the separately reviewed shared executor.

This module has no paid transport, API key reader, recovery, or live-run command.
The executor must call verify_packet immediately before acquiring its global lock
and again under that lock before the first reservation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import mmap
import os
from pathlib import Path
import stat
import types


ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
PROJECT = REPO.parent
SOURCE_ROOT = "4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d"
SOURCE_MANIFEST_SHA256 = "ab6e72a7e3bfc1f1b1ccdbc0a2b496eebd141097c80fc36dd96b684b4e25bb47"
RECENT_LEDGER_SHA256 = "eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190"
COVERAGE_SHA256 = "adb6c303948a18de52b9213bc2afacf7886213598ac3d64e05d45b3f7919d3e3"
RUNTIME_BASE = Path.home() / "Library/Application Support/ValueFinder/football-acquisition-state"
MAX_CREDITS = 68010
F2_HANDOFF_PATH = REPO / "strategy-research/football_archive/f2_handoff.py"
F2_HANDOFF_SHA256 = "fabf3da704b22737e0eb6182be0c8d554be06e44a7238805c1df0ebe06ab2a27"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    Path(path).write_bytes(canonical(value) + b"\n")


def f2_handoff():
    if F2_HANDOFF_PATH.is_symlink():
        raise ValueError("Shared F2 gate must be a regular file")
    fd = os.open(F2_HANDOFF_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Shared F2 gate must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read()
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != F2_HANDOFF_SHA256:
        raise ValueError("Shared F2 gate bytes changed before import")
    module = types.ModuleType("older_reviewed_f2_handoff")
    module.__file__ = str(F2_HANDOFF_PATH)
    exec(compile(data, str(F2_HANDOFF_PATH), "exec"), module.__dict__)
    return module


def source(bundle):
    bundle = Path(bundle).resolve()
    cert = json.loads((bundle / "FREEZE.json").read_text())
    expected = cert["file_sha256"]
    if (cert["bundle_root_sha256"] != SOURCE_ROOT or hashlib.sha256(canonical(expected)).hexdigest() != SOURCE_ROOT
            or any(p.is_symlink() for p in bundle.rglob("*"))):
        raise ValueError("Frozen v4 source root or file type changed")
    actual = {str(p.relative_to(bundle)): sha(p) for p in bundle.rglob("*") if p.is_file() and p.name != "FREEZE.json"}
    if actual != expected or actual["request-manifest.json"] != SOURCE_MANIFEST_SHA256:
        raise ValueError("Frozen v4 source bytes changed")
    manifest = json.loads((bundle / "request-manifest.json").read_text())
    rows = manifest["requests"]
    if (hashlib.sha256(canonical(rows)).hexdigest() != manifest["request_set_sha256"]
            or sha(bundle / "request-list.csv") != manifest["request_list_sha256"]):
        raise ValueError("Frozen request list changed")
    older = [r for r in rows if r["priority"] == 2]
    if (len(older), sum(r["max_new_credits"] == 30 for r in older),
            sum(r["max_new_credits"] == 0 for r in older)) != (2279, 2267, 12):
        raise ValueError("Older request denominator changed")
    if sum(r["max_new_credits"] for r in older) != MAX_CREDITS:
        raise ValueError("Older budget changed")
    for row in older:
        if (row["sealed"] or not set(row["seasons"]) <= {2020, 2021, 2022}
                or row["retry_allowance"] != 0 or row["max_credits"] != 30
                or row["params"]["markets"] != "h2h,spreads,totals"
                or row["params"]["date"] != row["requested_utc"]):
            raise ValueError("Older row scope changed")
        if row["max_new_credits"] == 0 and sha(bundle / row["cache_source"]) != row["cache_sha256"]:
            raise ValueError("Frozen reused response changed")
    return manifest, older


def coverage(coverage_path):
    path = Path(coverage_path)
    if sha(path) != COVERAGE_SHA256:
        raise ValueError("Accepted coverage artifact changed")
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        if mm.find(b'"all_recent_requests_completed":true') < 0 or mm.find(b'"outcomes_joined":false') < 0:
            raise ValueError("Recent acquisition or outcome boundary changed")
        key = b'"before_older_slice"'
        start = mm.find(key)
        if start < 0:
            raise ValueError("Missing pre-older coverage")
        snippet = mm[start + len(key):start + len(key) + 2_000_000].decode()
    section, _ = json.JSONDecoder().raw_decode(snippet[snippet.index("{"):])
    if (section["identity_and_opportunity_accounting"] != {
            "matched": 6880, "matched_no_valid_pregame_listing": 4, "unmatched_observed_opportunity": 350}
            or section["valid_reference_pairs"] != 192314
            or len(section["sport_season_month_book_market_lead_first_observed_strata"]) != 5280):
        raise ValueError("Coverage decision denominator changed")
    return {"sha256": COVERAGE_SHA256, "recent_complete": True, "outcomes_joined": False,
            "acceptance_scope": "acquisition accounting only; not opportunity completeness, actual-play or strategy value"}


def seed(ledger_path, paid_rows, *, require_f2=False):
    paid_rows = list(paid_rows)
    gate = f2_handoff()
    ledger_path = Path(ledger_path).resolve()
    root = ledger_path.parent.name
    if len(root) != 64 or ledger_path != RUNTIME_BASE / root / "spending-ledger.json":
        raise ValueError("Predecessor outside fixed runtime root")
    ledger_hash = sha(ledger_path)
    ledger = json.loads(ledger_path.read_text())
    if (ledger["bundle_root_sha256"] != root or ledger["pending"] is not None
            or ledger["stopped"] is not None or type(ledger["probe_credits"]) is not int
            or ledger["probe_credits"] != 1687
            or (ledger["status"] not in ("recent_complete_stopped_before_older", "event_epoch_complete")
                and root not in (gate.FIRST_ROOT, gate.SECOND_ROOT))
            or any(a["status"] not in ("completed", "missing") for a in ledger["attempts"].values())):
        raise ValueError("Predecessor is not completed and settled")
    if root == SOURCE_ROOT and ledger_hash != RECENT_LEDGER_SHA256:
        raise ValueError("Original recent ledger pin changed")
    paid_ids = {r["request_id"] for r in paid_rows}
    paid_keys = {r["cache_key"] for r in paid_rows}
    ancestors = set()
    current = ledger
    current_path = ledger_path
    partial_roots = set()
    union_proof = None
    while True:
        current_root = current["bundle_root_sha256"]
        if current_root in ancestors:
            raise ValueError("Cyclic predecessor chain")
        ancestors.add(current_root)
        if current_root in (gate.FIRST_ROOT, gate.SECOND_ROOT):
            gate.verify_partial(current_root, current_path, current, sha(current_path))
            partial_roots.add(current_root)
        if (type(current["probe_credits"]) is not int or current["probe_credits"] != 1687
                or type(current["other_usage_reserved"]) is not int or current["other_usage_reserved"] < 0
                or any(type(a["reserved_credits"]) is not int or a["reserved_credits"] < 0
                       for a in current["attempts"].values())):
            raise ValueError("Invalid ancestor accounting value")
        registered = RUNTIME_BASE / "registrations" / (current_root + ".json")
        initialized = RUNTIME_BASE / current_root / "INITIALIZED.json"
        if (not registered.is_file() or not initialized.is_file()
                or json.loads(registered.read_text()).get("bundle_root_sha256") != current_root
                or json.loads(initialized.read_text()).get("bundle_root_sha256") != current_root):
            raise ValueError("Ancestor central registration or initialization missing")
        if paid_ids & (set(current["attempts"]) | set(current["cache_reuse"])):
            raise ValueError("Ancestor request would be repurchased")
        if paid_keys & {a["cache_key"] for a in current["attempts"].values()}:
            raise ValueError("Ancestor cache would be repurchased")
        if current_root == SOURCE_ROOT:
            if sha(RUNTIME_BASE / SOURCE_ROOT / "spending-ledger.json") != RECENT_LEDGER_SHA256:
                raise ValueError("Original recent ledger pin changed")
            break
        prior = current.get("predecessor_seed")
        if (not prior or prior["root"] in ancestors or type(prior["probe_credits"]) is not int
                or prior["probe_credits"] != 1687
                or type(prior["cumulative_debit_without_probe"]) is not int
                or prior["cumulative_debit_without_probe"] < 0):
            raise ValueError("Missing or cyclic ancestor pin")
        prior_path = Path(prior["ledger_path"]).resolve()
        if prior_path != RUNTIME_BASE / prior["root"] / "spending-ledger.json" or sha(prior_path) != prior["ledger_sha256"]:
            raise ValueError("Ancestor ledger path or hash changed")
        parent = json.loads(prior_path.read_text())
        if (parent["bundle_root_sha256"] != prior["root"] or parent["pending"] or parent["stopped"]
                or (parent["status"] not in ("recent_complete_stopped_before_older", "event_epoch_complete")
                    and prior["root"] not in (gate.FIRST_ROOT, gate.SECOND_ROOT))
                or type(parent["probe_credits"]) is not int or parent["probe_credits"] != 1687
                or type(parent["other_usage_reserved"]) is not int or parent["other_usage_reserved"] < 0
                or any(type(a["reserved_credits"]) is not int or a["reserved_credits"] < 0
                       for a in parent["attempts"].values())
                or any(a["status"] not in ("completed", "missing") for a in parent["attempts"].values())):
            raise ValueError("Ancestor ledger unsettled")
        debit = parent["other_usage_reserved"] + sum(a["reserved_credits"] for a in parent["attempts"].values())
        if debit != prior["cumulative_debit_without_probe"] or prior["probe_credits"] != 1687:
            raise ValueError("Ancestor cumulative debit changed")
        if current["other_usage_reserved"] < debit:
            raise ValueError("Child cumulative debit decreased below ancestor")
        if prior["root"] == gate.SECOND_ROOT:
            if union_proof is not None or current_root in (gate.FIRST_ROOT, gate.SECOND_ROOT):
                raise ValueError("Duplicate or misplaced full F2 union")
            union_proof = gate.verify_full_union(current_path)
        if current_root == gate.SECOND_ROOT and prior["root"] != gate.FIRST_ROOT:
            raise ValueError("Second F2 partial does not follow first")
        if current_root == gate.PILOT_ROOT and prior["root"] != SOURCE_ROOT:
            raise ValueError("F2 pilot does not follow original F1")
        current = parent
        current_path = prior_path
    if require_f2 and (partial_roots != {gate.FIRST_ROOT, gate.SECOND_ROOT} or union_proof is None):
        raise ValueError("Both exact partial F2 ancestors and full union are required")
    debit = ledger["other_usage_reserved"] + sum(a["reserved_credits"] for a in ledger["attempts"].values())
    if 1687 + debit + MAX_CREDITS > 250000 or 1687 + debit + MAX_CREDITS > 400000:
        raise ValueError("Older stage exceeds cumulative ceiling")
    result = {"root": root, "ledger_path": str(ledger_path), "ledger_sha256": ledger_hash,
              "probe_credits": 1687, "cumulative_debit_without_probe": debit}
    if union_proof is not None:
        result["f2_union_proof_sha256"] = union_proof
    return result


def csv_bytes(bundle, older):
    with (Path(bundle) / "request-list.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        lines = [row for row in reader if row["priority"] == "2"]
    if len(lines) != len(older) or [r["cache_key"] for r in lines] != [r["cache_key"] for r in older]:
        raise ValueError("Older CSV differs from source order")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(lines)
    return output.getvalue().encode()


def raw_roots(exclude_root=None):
    roots = {Path.home() / "code/value-finder/sharp-markets/data/raw",
             REPO / "sharp-markets/data/raw",
             Path.home() / "Documents/Codex/2026-10-02/value-finder-download-worker/implementation/sharp-markets/data/raw"}
    roots.update(PROJECT.glob("*/sharp-markets/data/raw"))
    pilot = ROOT / "followups/F2-pilot/cache-reconciliation.json"
    roots.update(Path(p) for p in json.loads(pilot.read_text())["raw_roots"])
    if RUNTIME_BASE.exists():
        roots.update(RUNTIME_BASE.glob("*/data/raw"))
    excluded = (RUNTIME_BASE / exclude_root / "data/raw").resolve() if exclude_root else None
    return sorted({str(p.resolve()) for p in roots if p.resolve() != excluded})


def reconcile_cache(older, bundle, exclude_root=None):
    roots = raw_roots(exclude_root)
    for row in older:
        matches = set()
        for raw in roots:
            directory = Path(raw) / row["sport"] / row["source"]
            matches.update(p.resolve() for p in directory.glob(f"*/{row['cache_key']}.parquet"))
        if row["max_new_credits"] and matches:
            raise ValueError("Existing exact paid cache key; no repurchase")
        if not row["max_new_credits"]:
            if sha(Path(bundle) / row["cache_source"]) != row["cache_sha256"]:
                raise ValueError("Frozen reused cache changed")
            if any(sha(path) != row["cache_sha256"] for path in matches):
                raise ValueError("Conflicting reused cache copy")
    return {"status": "reconciled", "request_count": len(older),
            "paid_count": sum(bool(r["max_new_credits"]) for r in older),
            "new_credits": MAX_CREDITS, "raw_roots": roots,
            "paid_exact_cache_overlap": 0, "unrelated_cache_files_read": False}


def freeze(packet):
    packet = Path(packet)
    names = ("manifest.json", "requests.json", "request-list.csv", "seed.json", "coverage-decision.json",
             "cache-reconciliation.json")
    files = {name: sha(packet / name) for name in names}
    files["code/stage.py"] = sha(__file__)
    files["code/execute.py"] = sha(Path(__file__).with_name("execute.py"))
    files["code/f2_handoff.py"] = sha(F2_HANDOFF_PATH)
    root = hashlib.sha256(canonical(files)).hexdigest()
    write(packet / "FREEZE.json", {"root": root, "files": files})
    return root


def prepare(bundle, coverage_path, predecessor_ledger, packet):
    manifest, older = source(bundle)
    accepted = coverage(coverage_path)
    predecessor = seed(predecessor_ledger, (r for r in older if r["max_new_credits"]), require_f2=True)
    packet = Path(packet)
    packet.mkdir(parents=True, exist_ok=False)
    write(packet / "requests.json", older)
    (packet / "request-list.csv").write_bytes(csv_bytes(bundle, older))
    write(packet / "seed.json", predecessor)
    write(packet / "coverage-decision.json", accepted)
    write(packet / "cache-reconciliation.json", reconcile_cache(older, bundle))
    write(packet / "manifest.json", {
        "stage": "older-priority-2", "source_bundle_root": SOURCE_ROOT,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_request_set_sha256": manifest["request_set_sha256"],
        "source_request_list_sha256": manifest["request_list_sha256"],
        "request_count": len(older), "new_request_count": 2267, "reuse_count": 12,
        "new_credits": MAX_CREDITS, "priority": 2,
        "request_set_sha256": hashlib.sha256(canonical(older)).hexdigest(),
        "request_list_sha256": sha(packet / "request-list.csv"),
        "coverage_report_sha256": COVERAGE_SHA256,
        "outcomes_joined": False, "authorization": "required separately for exact packet root, list, budget and commit"})
    return freeze(packet)


def verify_packet(packet, root, bundle, coverage_path):
    packet = Path(packet)
    cert = json.loads((packet / "FREEZE.json").read_text())
    if any(p.is_symlink() or p.is_dir() for p in packet.iterdir()):
        raise ValueError("Packet contains nonregular files")
    expected_names = {"manifest.json", "requests.json", "request-list.csv", "seed.json", "cache-reconciliation.json",
                      "coverage-decision.json", "code/stage.py", "code/execute.py", "code/f2_handoff.py"}
    packet_names = {name for name in expected_names if not name.startswith("code/")} | {"FREEZE.json"}
    if set(cert["files"]) != expected_names or {p.name for p in packet.iterdir()} != packet_names:
        raise ValueError("Unexpected packet files")
    files = {name: sha(packet / name) for name in expected_names if not name.startswith("code/")}
    files["code/stage.py"] = sha(__file__)
    files["code/execute.py"] = sha(Path(__file__).with_name("execute.py"))
    files["code/f2_handoff.py"] = sha(F2_HANDOFF_PATH)
    if files != cert["files"] or hashlib.sha256(canonical(files)).hexdigest() != root or cert["root"] != root:
        raise ValueError("Older packet root or code changed")
    source_manifest, older = source(bundle)
    frozen_rows = json.loads((packet / "requests.json").read_text())
    manifest = json.loads((packet / "manifest.json").read_text())
    if frozen_rows != older or manifest != {
        "stage": "older-priority-2", "source_bundle_root": SOURCE_ROOT,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_request_set_sha256": source_manifest["request_set_sha256"],
        "source_request_list_sha256": source_manifest["request_list_sha256"],
        "request_count": 2279, "new_request_count": 2267, "reuse_count": 12,
        "new_credits": MAX_CREDITS, "priority": 2,
        "request_set_sha256": hashlib.sha256(canonical(older)).hexdigest(),
        "request_list_sha256": sha(packet / "request-list.csv"),
        "coverage_report_sha256": COVERAGE_SHA256,
        "outcomes_joined": False, "authorization": "required separately for exact packet root, list, budget and commit"}:
        raise ValueError("Older packet is not exact frozen source slice")
    if (packet / "request-list.csv").read_bytes() != csv_bytes(bundle, older):
        raise ValueError("Older CSV differs from frozen source")
    if json.loads((packet / "coverage-decision.json").read_text()) != coverage(coverage_path):
        raise ValueError("Coverage acceptance artifact differs")
    if json.loads((packet / "cache-reconciliation.json").read_text()) != reconcile_cache(older, bundle, root):
        raise ValueError("Exact-key cache inventory changed")
    prior = json.loads((packet / "seed.json").read_text())
    if prior != seed(prior["ledger_path"], (r for r in older if r["max_new_credits"]), require_f2=True):
        raise ValueError("Older predecessor changed")
    return manifest, older, prior


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--predecessor-ledger", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"offline": True, "root": prepare(args.bundle, args.coverage,
        args.predecessor_ledger, args.packet), "new_credits": MAX_CREDITS}))
