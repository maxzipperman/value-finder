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
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = "4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d"
SOURCE_MANIFEST_SHA256 = "ab6e72a7e3bfc1f1b1ccdbc0a2b496eebd141097c80fc36dd96b684b4e25bb47"
RECENT_LEDGER_SHA256 = "eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190"
COVERAGE_SHA256 = "adb6c303948a18de52b9213bc2afacf7886213598ac3d64e05d45b3f7919d3e3"
RUNTIME_BASE = Path.home() / "Library/Application Support/ValueFinder/football-acquisition-state"
MAX_CREDITS = 68010


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


def seed(ledger_path, paid_rows):
    ledger_path = Path(ledger_path).resolve()
    root = ledger_path.parent.name
    if len(root) != 64 or ledger_path != RUNTIME_BASE / root / "spending-ledger.json":
        raise ValueError("Predecessor outside fixed runtime root")
    ledger_hash = sha(ledger_path)
    ledger = json.loads(ledger_path.read_text())
    if (ledger["bundle_root_sha256"] != root or ledger["pending"] is not None
            or ledger["stopped"] is not None or ledger["probe_credits"] != 1687
            or ledger["status"] not in ("recent_complete_stopped_before_older", "event_epoch_complete")
            or any(a["status"] not in ("completed", "missing") for a in ledger["attempts"].values())):
        raise ValueError("Predecessor is not completed and settled")
    if root == SOURCE_ROOT and ledger_hash != RECENT_LEDGER_SHA256:
        raise ValueError("Original recent ledger pin changed")
    paid_ids = {r["request_id"] for r in paid_rows}
    paid_keys = {r["cache_key"] for r in paid_rows}
    ancestors = set()
    current = ledger
    while True:
        current_root = current["bundle_root_sha256"]
        if current_root in ancestors:
            raise ValueError("Cyclic predecessor chain")
        ancestors.add(current_root)
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
        if not prior or prior["root"] in ancestors:
            raise ValueError("Missing or cyclic ancestor pin")
        prior_path = Path(prior["ledger_path"]).resolve()
        if prior_path != RUNTIME_BASE / prior["root"] / "spending-ledger.json" or sha(prior_path) != prior["ledger_sha256"]:
            raise ValueError("Ancestor ledger path or hash changed")
        current = json.loads(prior_path.read_text())
        if (current["bundle_root_sha256"] != prior["root"] or current["pending"] or current["stopped"]
                or current["status"] not in ("recent_complete_stopped_before_older", "event_epoch_complete")
                or any(a["status"] not in ("completed", "missing") for a in current["attempts"].values())):
            raise ValueError("Ancestor ledger unsettled")
        debit = current["other_usage_reserved"] + sum(a["reserved_credits"] for a in current["attempts"].values())
        if debit != prior["cumulative_debit_without_probe"] or prior["probe_credits"] != 1687:
            raise ValueError("Ancestor cumulative debit changed")
    debit = ledger["other_usage_reserved"] + sum(a["reserved_credits"] for a in ledger["attempts"].values())
    if 1687 + debit + MAX_CREDITS > 250000 or 1687 + debit + MAX_CREDITS > 400000:
        raise ValueError("Older stage exceeds cumulative ceiling")
    return {"root": root, "ledger_path": str(ledger_path), "ledger_sha256": ledger_hash,
            "probe_credits": 1687, "cumulative_debit_without_probe": debit}


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


def freeze(packet):
    packet = Path(packet)
    names = ("manifest.json", "requests.json", "request-list.csv", "seed.json", "coverage-decision.json")
    files = {name: sha(packet / name) for name in names}
    files["code/stage.py"] = sha(__file__)
    files["code/execute.py"] = sha(Path(__file__).with_name("execute.py"))
    root = hashlib.sha256(canonical(files)).hexdigest()
    write(packet / "FREEZE.json", {"root": root, "files": files})
    return root


def prepare(bundle, coverage_path, predecessor_ledger, packet):
    manifest, older = source(bundle)
    accepted = coverage(coverage_path)
    predecessor = seed(predecessor_ledger, (r for r in older if r["max_new_credits"]))
    packet = Path(packet)
    packet.mkdir(parents=True, exist_ok=False)
    write(packet / "requests.json", older)
    (packet / "request-list.csv").write_bytes(csv_bytes(bundle, older))
    write(packet / "seed.json", predecessor)
    write(packet / "coverage-decision.json", accepted)
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
    expected_names = {"manifest.json", "requests.json", "request-list.csv", "seed.json",
                      "coverage-decision.json", "code/stage.py", "code/execute.py"}
    packet_names = {name for name in expected_names if not name.startswith("code/")} | {"FREEZE.json"}
    if set(cert["files"]) != expected_names or {p.name for p in packet.iterdir()} != packet_names:
        raise ValueError("Unexpected packet files")
    files = {name: sha(packet / name) for name in expected_names if not name.startswith("code/")}
    files["code/stage.py"] = sha(__file__)
    files["code/execute.py"] = sha(Path(__file__).with_name("execute.py"))
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
    prior = json.loads((packet / "seed.json").read_text())
    if prior != seed(prior["ledger_path"], (r for r in older if r["max_new_credits"])):
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
