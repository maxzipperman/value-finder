"""Offline, exact N0 packet and cumulative-predecessor verifier.

No paid transport, key reader, outcome access or source-list mutation lives here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

import successor151


SOURCE = Path(__file__).resolve().parents[1]
REPO = SOURCE.parents[1]
PROJECT = REPO.parent
V4_ROOT = "4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d"
RECENT_LEDGER_SHA256 = "eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190"
EXPECTED = {
    "manifest.json": "3af23667237af91216a83b6d7d57e73806792bd6cb5c9b00d07e73aaf8cab45b",
    "metadata.json": "c251339f57ccae7b7323e93907cb3cf2575ddb93551f6aaaa0705fe9da306e3b",
    "requests.json": "9871c5e478f9e8ab93730520a4ef8b2e892f7f698a6cc90a6f7407cf01c6764a",
    "request-list.csv": "b9232db3a473992a88c04640ff579d9a834ab7f61c723cd9032b73b7f115c7e5",
    "free-inputs-receipt.json": "71cfe69b30afd8701a4d88a2364d73a21af566eab398617a46685957b49c89e9",
    "exact_list.py": "a325fccdc8ccb3a5b254fdfcef0b32040124cd81166596c10f10ef213459924f",
}
REQUEST_SET_SHA256 = "b4894a5b1b837372d0a5aa7e649abe49b79840b5b6f1ef4836233c192a51a6a5"
CAP = 7540
RUNTIME_BASE = Path.home() / "Library/Application Support/ValueFinder/football-acquisition-state"
TERMINAL = {"recent_complete_stopped_before_older", "event_epoch_complete", "older_epoch_complete"}
F2_HANDOFF_PATH = REPO / "strategy-research/football_archive/f2_handoff.py"
F2_HANDOFF_SHA256 = "49d0ed2c01a1aee22246a72ca0913f5e3c5659acc92a1b7dd75a643336ba1bfb"


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
    module = types.ModuleType("n0_reviewed_f2_handoff")
    module.__file__ = str(F2_HANDOFF_PATH)
    exec(compile(data, str(F2_HANDOFF_PATH), "exec"), module.__dict__)
    return module


def source():
    actual = {name: sha(SOURCE / name) for name in EXPECTED}
    if actual != EXPECTED:
        raise ValueError("Committed N0 candidate bytes changed")
    meta = json.loads((SOURCE / "metadata.json").read_text())
    receipt = json.loads((SOURCE / "free-inputs-receipt.json").read_text())
    manifest = json.loads((SOURCE / "manifest.json").read_text())
    rows = json.loads((SOURCE / "requests.json").read_text())
    if (meta["problems"] or len(meta["games"]) != 56 or meta["snapshot_count"] != 754
            or len(meta["requested_utc"]) != 754 or meta["outcomes_inspected"] is not False
            or meta["sealed_2026_27_inspected"] is not False or meta["paid_calls"] != 0
            or manifest["games"] != 56 or manifest["requests"] != 754
            or manifest["max_new_credits"] != CAP or manifest["paid_execution_enabled"] is not False
            or manifest["request_set_sha256"] != REQUEST_SET_SHA256
            or manifest["request_list_sha256"] != EXPECTED["request-list.csv"]
            or receipt["odds_api_credits"] != 0 or receipt["paid_calls"] != 0
            or receipt["markets_completed"] != 112 or receipt["price_minutes_cached"] != 259778
            or receipt["all_transient_free_429s_resolved"] is not True
            or receipt["strategy_results_computed"] is not False
            or receipt["game_outcomes_inspected"] is not False
            or receipt["sealed_2026_27_inspected"] is not False):
        raise ValueError("N0 metadata or free-input scope changed")
    if hashlib.sha256(canonical(rows)).hexdigest() != REQUEST_SET_SHA256:
        raise ValueError("N0 exact request set changed")
    if len(rows) != 754 or len({r["request_id"] for r in rows}) != 754 or len({r["cache_key"] for r in rows}) != 754:
        raise ValueError("N0 request count or identity duplicate")
    if [r["requested_utc"] for r in rows] != [t.replace("+00:00", "Z") for t in meta["requested_utc"]]:
        raise ValueError("N0 metadata times differ from executable rows")
    books = "pinnacle,lowvig,betonlineag"
    for row in rows:
        identity = {"source": "oddsapi_hist", "url": "https://api.the-odds-api.com/v4" + row["path"],
                    "params": row["params"]}
        if (row["request_id"] != hashlib.sha256(canonical(identity)).hexdigest()
                or row["cache_key"] != hashlib.sha1(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20]
                or row["sport"] != "nba" or row["odds_sport_key"] != "basketball_nba"
                or row["source"] != "oddsapi_hist" or row["path"] != "/historical/sports/basketball_nba/odds"
                or row["params"] != {"bookmakers": books, "markets": "h2h", "oddsFormat": "decimal",
                                      "dateFormat": "iso", "date": row["requested_utc"]}
                or row["max_credits"] != 10 or row["max_new_credits"] != 10
                or row["retry_allowance"] != 0 or row["sealed"] is not False):
            raise ValueError("N0 source/cache/cost identity changed")
    if sum(r["max_new_credits"] for r in rows) != CAP:
        raise ValueError("N0 cap changed")
    return manifest, rows


def raw_roots(own_root=None):
    roots = {Path(p) for p in json.loads((SOURCE / "manifest.json").read_text())["raw_roots_checked"]}
    pilot = REPO / "strategy-research/football_archive/followups/F2-pilot/cache-reconciliation.json"
    continuation = REPO / "strategy-research/football_archive/recovery-v1/F2-continuation/cache-reconciliation.json"
    final_continuation = REPO / "strategy-research/football_archive/recovery-v2/F2-second-continuation/cache-reconciliation.json"
    roots.update(Path(p) for p in json.loads(pilot.read_text())["raw_roots"])
    roots.update(Path(p) for p in json.loads(continuation.read_text())["raw_roots"])
    roots.update(Path(p) for p in json.loads(final_continuation.read_text())["raw_roots"])
    roots.add(Path.home() / "code/value-finder/sharp-markets/data/raw")
    own_store = REPO / "sharp-markets/data/raw"
    if own_store.exists():
        roots.add(own_store)
    projects = {PROJECT}
    for raw in list(roots):
        if raw.parts[-3:] == ("sharp-markets", "data", "raw"):
            projects.add(raw.parents[2].parent)
    for project in projects:
        roots.update(project.glob("*/sharp-markets/data/raw"))
    roots.update(RUNTIME_BASE.glob("*/data/raw"))
    excluded = (RUNTIME_BASE / own_root / "data/raw").resolve() if own_root else None
    return sorted({str(p.resolve()) for p in roots if p.resolve() != excluded})


def cache_hits(row, own_root=None):
    hits = set()
    for root in raw_roots(own_root):
        directory = Path(root) / row["sport"] / row["source"]
        hits.update(p.resolve() for p in directory.glob(f"*/{row['cache_key']}.parquet"))
    return sorted(hits)


def reconcile(rows, own_root=None):
    overlaps = {r["request_id"]: [str(p) for p in cache_hits(r, own_root)] for r in rows}
    overlaps = {rid: paths for rid, paths in overlaps.items() if paths}
    if overlaps:
        raise ValueError("Existing exact NBA paid cache requires reviewed reuse packet; no repurchase")
    return {"paid_request_count": len(rows), "new_credits": CAP,
            "request_set_sha256": REQUEST_SET_SHA256, "raw_roots": raw_roots(own_root), "exact_cache_overlap": 0,
            "unrelated_cache_files_read": False}


def seed(ledger_path, rows, *, require_f2=False):
    rows = list(rows)
    if Path(ledger_path) == RUNTIME_BASE / successor151.ROOT / "spending-ledger.json":
        return successor151.seed(ledger_path, rows, RUNTIME_BASE)
    if require_f2:
        raise ValueError("Only exact successor151 is an N0 predecessor; Both exact partial F2 proofs are required")
    gate = f2_handoff()
    ledger_path = Path(ledger_path).resolve()
    root = ledger_path.parent.name
    if not re.fullmatch("[a-f0-9]{64}", root) or ledger_path != RUNTIME_BASE / root / "spending-ledger.json":
        raise ValueError("Predecessor outside fixed global runtime")
    digest = sha(ledger_path)
    current = json.loads(ledger_path.read_text())
    if current["status"] != "older_epoch_complete":
        raise ValueError("N0 requires the completed older stage as its immediate predecessor")
    if root == V4_ROOT and digest != RECENT_LEDGER_SHA256:
        raise ValueError("Original F1 ledger changed")
    seen = set()
    partial_roots = set()
    union_proof = None
    current_path = ledger_path
    paid_ids = {r["request_id"] for r in rows}
    paid_keys = {r["cache_key"] for r in rows}
    while True:
        current_root = current["bundle_root_sha256"]
        if current_root in seen:
            raise ValueError("Cyclic predecessor chain")
        seen.add(current_root)
        if current_root in (gate.FIRST_ROOT, gate.SECOND_ROOT):
            gate.verify_partial(current_root, current_path, current, sha(current_path))
            partial_roots.add(current_root)
        if (current["pending"] is not None or current["stopped"] is not None
                or (current["status"] not in TERMINAL
                    and current_root not in (gate.FIRST_ROOT, gate.SECOND_ROOT))
                or type(current["probe_credits"]) is not int
                or current["probe_credits"] != 1687
                or type(current["other_usage_reserved"]) is not int or current["other_usage_reserved"] < 0
                or any(type(a["reserved_credits"]) is not int or a["reserved_credits"] < 0
                       for a in current["attempts"].values())
                or any(a["status"] not in ("completed", "missing") for a in current["attempts"].values())):
            raise ValueError("Predecessor or ancestor unsettled")
        registered = RUNTIME_BASE / "registrations" / (current_root + ".json")
        initialized = RUNTIME_BASE / current_root / "INITIALIZED.json"
        if (not registered.is_file() or not initialized.is_file()
                or json.loads(registered.read_text()).get("bundle_root_sha256") != current_root
                or json.loads(initialized.read_text()).get("bundle_root_sha256") != current_root):
            raise ValueError("Ancestor central registration missing")
        if paid_ids & (set(current["attempts"]) | set(current["cache_reuse"])):
            raise ValueError("Ancestor request overlap")
        if paid_keys & {a["cache_key"] for a in current["attempts"].values()}:
            raise ValueError("Ancestor cache overlap")
        if current_root == V4_ROOT:
            if sha(RUNTIME_BASE / V4_ROOT / "spending-ledger.json") != RECENT_LEDGER_SHA256:
                raise ValueError("Original F1 ledger pin changed")
            break
        prior = current.get("predecessor_seed")
        if (not prior or prior["root"] in seen or type(prior["probe_credits"]) is not int
                or prior["probe_credits"] != 1687
                or type(prior["cumulative_debit_without_probe"]) is not int
                or prior["cumulative_debit_without_probe"] < 0):
            raise ValueError("Missing ancestor seed")
        path = Path(prior["ledger_path"]).resolve()
        if path != RUNTIME_BASE / prior["root"] / "spending-ledger.json" or sha(path) != prior["ledger_sha256"]:
            raise ValueError("Ancestor ledger path/hash changed")
        previous = json.loads(path.read_text())
        if (previous["bundle_root_sha256"] != prior["root"] or previous["pending"] or previous["stopped"]
                or (previous["status"] not in TERMINAL
                    and prior["root"] not in (gate.FIRST_ROOT, gate.SECOND_ROOT))
                or type(previous["probe_credits"]) is not int
                or previous["probe_credits"] != 1687
                or type(previous["other_usage_reserved"]) is not int or previous["other_usage_reserved"] < 0
                or any(type(a["reserved_credits"]) is not int or a["reserved_credits"] < 0
                       for a in previous["attempts"].values())):
            raise ValueError("Ancestor ledger unsettled or invalid")
        prior_debit = previous["other_usage_reserved"] + sum(a["reserved_credits"] for a in previous["attempts"].values())
        if prior_debit != prior["cumulative_debit_without_probe"]:
            raise ValueError("Ancestor debit or root changed")
        if current["other_usage_reserved"] < prior_debit:
            raise ValueError("Cumulative debit decreased")
        if prior["root"] == gate.SECOND_ROOT:
            if union_proof is not None or current_root in (gate.FIRST_ROOT, gate.SECOND_ROOT):
                raise ValueError("Duplicate or misplaced full F2 union")
            union_proof = gate.verify_full_union(current_path)
        if current_root == gate.SECOND_ROOT and prior["root"] != gate.FIRST_ROOT:
            raise ValueError("Second F2 partial does not follow first")
        if current_root == gate.PILOT_ROOT and prior["root"] != V4_ROOT:
            raise ValueError("F2 pilot does not follow original F1")
        current = previous
        current_path = path
    if require_f2 and (partial_roots != {gate.FIRST_ROOT, gate.SECOND_ROOT} or union_proof is None):
        raise ValueError("Both exact partial F2 ancestors and full union are required")
    latest = json.loads(ledger_path.read_text())
    if latest["bundle_root_sha256"] != root:
        raise ValueError("Latest predecessor root changed")
    debit = latest["other_usage_reserved"] + sum(a["reserved_credits"] for a in latest["attempts"].values())
    if 1687 + debit + CAP > 250000 or 1687 + debit + CAP > 400000:
        raise ValueError("N0 exceeds cumulative ceiling")
    result = {"root": root, "ledger_path": str(ledger_path), "ledger_sha256": digest,
              "probe_credits": 1687, "cumulative_debit_without_probe": debit}
    if union_proof is not None:
        result["f2_union_proof_sha256"] = union_proof
    return result


FILES = ("manifest.json", "requests.json", "request-list.csv", "seed.json", "cache-reconciliation.json")


def freeze(packet):
    files = {name: sha(packet / name) for name in FILES}
    files["code/stage.py"] = sha(__file__)
    files["code/execute.py"] = sha(Path(__file__).with_name("execute.py"))
    files["code/f2_handoff.py"] = sha(F2_HANDOFF_PATH)
    files["code/successor151.py"] = sha(successor151.HERE / "successor151.py")
    files["code/successor151-pins.json"] = sha(successor151.HERE / "successor151-pins.json")
    root = hashlib.sha256(canonical(files)).hexdigest()
    write(packet / "FREEZE.json", {"root": root, "files": files})
    return root


def prepare(predecessor_ledger, packet):
    _, rows = source()
    predecessor = seed(predecessor_ledger, rows, require_f2=True)
    if predecessor.get("kind") == "exact_successor151_preparation_only":
        raise ValueError("Actual N0 packet held: prospective ceiling adoption and executor integration review required")
    cache = reconcile(rows)
    packet = Path(packet)
    packet.mkdir(parents=True, exist_ok=False)
    (packet / "requests.json").write_bytes((SOURCE / "requests.json").read_bytes())
    (packet / "request-list.csv").write_bytes((SOURCE / "request-list.csv").read_bytes())
    write(packet / "seed.json", predecessor)
    write(packet / "cache-reconciliation.json", cache)
    write(packet / "manifest.json", {"stage": "N0", "source_file_sha256": EXPECTED,
        "request_count": 754, "new_credits": CAP, "request_set_sha256": REQUEST_SET_SHA256,
        "request_list_sha256": EXPECTED["request-list.csv"], "outcomes_joined": False,
        "priority": "N0", "authorization": "separate exact hub approval required"})
    return freeze(packet)


def verify_packet(packet, root):
    packet = Path(packet)
    _, rows = source()
    cert = json.loads((packet / "FREEZE.json").read_text())
    expected_names = set(FILES) | {"code/stage.py", "code/execute.py", "code/f2_handoff.py", "code/successor151.py", "code/successor151-pins.json"}
    if (any(p.is_dir() or p.is_symlink() for p in packet.iterdir())
            or {p.name for p in packet.iterdir()} != set(FILES) | {"FREEZE.json"}
            or set(cert["files"]) != expected_names):
        raise ValueError("N0 packet file set changed")
    files = {name: sha(packet / name) for name in FILES}
    files.update({"code/stage.py": sha(__file__), "code/execute.py": sha(Path(__file__).with_name("execute.py")),
                  "code/f2_handoff.py": sha(F2_HANDOFF_PATH),
                  "code/successor151.py": sha(successor151.HERE / "successor151.py"),
                  "code/successor151-pins.json": sha(successor151.HERE / "successor151-pins.json")})
    if files != cert["files"] or hashlib.sha256(canonical(files)).hexdigest() != root or cert["root"] != root:
        raise ValueError("N0 frozen root or code changed")
    manifest = json.loads((packet / "manifest.json").read_text())
    if manifest != {"stage": "N0", "source_file_sha256": EXPECTED,
        "request_count": 754, "new_credits": CAP, "request_set_sha256": REQUEST_SET_SHA256,
        "request_list_sha256": EXPECTED["request-list.csv"], "outcomes_joined": False,
        "priority": "N0", "authorization": "separate exact hub approval required"}:
        raise ValueError("N0 manifest changed")
    if ((packet / "requests.json").read_bytes() != (SOURCE / "requests.json").read_bytes()
            or (packet / "request-list.csv").read_bytes() != (SOURCE / "request-list.csv").read_bytes()):
        raise ValueError("N0 executable rows changed")
    if json.loads((packet / "cache-reconciliation.json").read_text()) != reconcile(rows, root):
        raise ValueError("N0 cache reconciliation stale")
    prior = json.loads((packet / "seed.json").read_text())
    if prior != seed(prior["ledger_path"], rows, require_f2=True):
        raise ValueError("N0 predecessor changed")
    return manifest, rows, prior


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-ledger", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"offline": True, "root": prepare(args.predecessor_ledger, args.packet), "cap": CAP}))
