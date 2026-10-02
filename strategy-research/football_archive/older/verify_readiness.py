"""Offline, outcome-blind check of the frozen priority-2 request identities.

Run from any checkout with --recent-ledger and --pilot-ledger pointing at the
completed, read-only acquisition ledgers. This never opens a paid transport.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "acquisition/football-archive-v4"
EXPECTED_ROOT = "4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(recent_path, pilot_path):
    manifest = json.loads((BUNDLE / "request-manifest.json").read_text())
    freeze = json.loads((BUNDLE / "FREEZE.json").read_text())
    assert freeze["bundle_root_sha256"] == EXPECTED_ROOT
    assert digest(BUNDLE / "request-list.csv") == manifest["request_list_sha256"]
    canonical = json.dumps(manifest["requests"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == manifest["request_set_sha256"]
    older = [r for r in manifest["requests"] if r["priority"] == 2]
    recent = [r for r in manifest["requests"] if r["priority"] == 1]
    paid = [r for r in older if r["max_new_credits"] == 30]
    reused = [r for r in older if r["max_new_credits"] == 0]
    assert (len(older), len(paid), len(reused)) == (2279, 2267, 12)
    assert sum(r["max_new_credits"] for r in older) == 68010
    assert len({r["request_id"] for r in older}) == len(older)
    assert len({r["cache_key"] for r in older}) == len(older)
    assert {r["request_id"] for r in older}.isdisjoint(r["request_id"] for r in recent)
    assert {r["cache_key"] for r in older}.isdisjoint(r["cache_key"] for r in recent)
    assert all(not r["sealed"] and set(r["seasons"]) <= {2020, 2021, 2022} for r in older)
    assert all(r["retry_allowance"] == 0 and r["max_credits"] == 30 for r in older)
    assert all(r["params"]["markets"] == "h2h,spreads,totals" for r in older)
    assert all(r["params"]["date"] == r["requested_utc"] and r["requested_utc"].endswith(":00Z") for r in older)
    for row in reused:
        assert digest(BUNDLE / row["cache_source"]) == row["cache_sha256"]

    recent_ledger = json.loads(recent_path.read_text())
    pilot_ledger = json.loads(pilot_path.read_text())
    assert recent_ledger["bundle_root_sha256"] == EXPECTED_ROOT
    assert recent_ledger["status"] == "recent_complete_stopped_before_older"
    assert pilot_ledger["status"] == "event_epoch_complete"
    assert recent_ledger["pending"] is None and pilot_ledger["pending"] is None
    assert Counter(a["status"] for a in recent_ledger["attempts"].values()) == {"completed": 2760, "missing": 1}
    assert Counter(a["status"] for a in pilot_ledger["attempts"].values()) == {"completed": 48}
    prior_ids = set(recent_ledger["attempts"]) | set(recent_ledger["cache_reuse"]) | set(pilot_ledger["attempts"]) | set(pilot_ledger["cache_reuse"])
    prior_cache = {a["cache_key"] for ledger in (recent_ledger, pilot_ledger) for a in ledger["attempts"].values()}
    assert {r["request_id"] for r in paid}.isdisjoint(prior_ids)
    assert {r["cache_key"] for r in paid}.isdisjoint(prior_cache)
    assert len(recent_ledger["cache_reuse"]) == 12
    return {
        "frozen_bundle_root_sha256": EXPECTED_ROOT,
        "request_set_sha256": manifest["request_set_sha256"],
        "request_list_sha256": manifest["request_list_sha256"],
        "older_request_slots": len(older),
        "older_paid_request_slots": len(paid),
        "older_reused_request_slots": len(reused),
        "maximum_new_credits": 68010,
        "seasons": sorted({s for r in older for s in r["seasons"]}),
        "sports": dict(Counter(r["sport"] for r in older)),
        "paid_request_overlap_with_completed_recent_and_pilot_ledgers": 0,
        "paid_cache_key_overlap_with_completed_recent_and_pilot_ledgers": 0,
        "recent_ledger_sha256": digest(recent_path),
        "pilot_ledger_sha256": digest(pilot_path),
        "reused_cache_hashes_checked": True,
        "outcomes_joined": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recent-ledger", type=Path, required=True)
    parser.add_argument("--pilot-ledger", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.recent_ledger, args.pilot_ledger), indent=2, sort_keys=True))
