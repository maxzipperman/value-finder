"""Hub-only N0 NBA acquisition using the reviewed v4 accounting/HTTP stack.

The CLI is offline by default. A paid run needs --confirm, a committed packet,
an exact hub approval/current commit, and a key file. It never retries a send.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import stage


def source_executor(bundle):
    bundle = Path(bundle)
    sys.path.insert(0, str(bundle))
    spec = importlib.util.spec_from_file_location("nba_n0_reviewed_v4_executor", bundle / "executor.py")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    from validator import verify
    verify(bundle, stage.V4_ROOT, check_cache=True)
    return base


def checkout_clean(packet):
    repo = Path(subprocess.check_output(["git", "-C", str(packet), "rev-parse", "--show-toplevel"], text=True).strip())
    paths = [packet / name for name in (*stage.FILES, "FREEZE.json")]
    paths.extend([Path(__file__), Path(stage.__file__)])
    relative = [str(p.resolve().relative_to(repo)) for p in paths]
    subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", *relative],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "diff", "--exit-code", "HEAD", "--", *relative],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def exact_approval(base, authorization, manifest, root, commit, live):
    if authorization.get("stage") != "N0" or authorization.get("priority") != "N0":
        raise base.Halt("Explicit N0 stage approval required")
    internal = {**authorization, "priority": 1}
    bridge = {**manifest, "new_credits_by_priority": {"1": stage.CAP}}
    base.validate_authorization(internal, bridge, root, commit)
    if live:
        base.verify_live_hub_comment(internal)
    reconciliation = authorization.get("account_reconciliation")
    base.validate_reconciliation(reconciliation, root)
    if reconciliation.get("account_only_recovery") or "pre_run_other_usage_budget_debit" in reconciliation:
        raise base.Halt("Automatic recovery and debit overrides are disabled")
    ceiling = reconciliation["max_baseline_used"]
    line = f"APPROVED account ceiling: max-baseline-used {ceiling}, root {root}"
    if line not in authorization["hub_go_ahead"]["comment_body"].splitlines():
        raise base.Halt("Account ceiling must be authenticated by the hub comment")
    if authorization["execution_commit"] != commit:
        raise base.Halt("Reviewed execution commit changed")
    return internal, bridge


def global_settled(current_root):
    for path in stage.RUNTIME_BASE.glob("*/spending-ledger.json"):
        if path.parent.name == current_root:
            continue
        state = json.loads(path.read_text())
        if state.get("pending") or state.get("stopped"):
            raise ValueError("Unresolved global acquisition epoch")


def internal_rows(rows):
    return [{**row, "priority": 1} for row in rows]


def run(packet, root, bundle, authorization, *, key, fake_session=None, checkpoint=lambda _: None):
    packet, bundle = Path(packet).resolve(), Path(bundle).resolve()
    manifest, rows, predecessor = stage.verify_packet(packet, root)
    base = source_executor(bundle)
    commit = checkout_clean(packet)
    runtime = base.runtime_path(root)
    base.execution_context(packet, root, runtime)
    if base.current_runtime() != json.loads((bundle / "runtime-lock.json").read_text()):
        raise base.Halt("Reviewed v4 runtime differs")
    internal_auth, bridge_manifest = exact_approval(base, authorization, manifest, root, commit, fake_session is None)
    stage.seed(predecessor["ledger_path"], rows)
    stage.reconcile(rows, root)
    global_settled(root)
    bridge_rows = internal_rows(rows)
    bridge_manifest["requests"] = bridge_rows
    protocol = json.loads((bundle / "protocol.json").read_text())
    probe = json.loads((bundle / "probe-spending-ledger.json").read_text())
    stage.RUNTIME_BASE.mkdir(parents=True, exist_ok=True)
    global_lock = (stage.RUNTIME_BASE / "followup-purchase.lock").open("a")
    ledger = client = None
    try:
        fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage.verify_packet(packet, root)
        global_settled(root)
        stage.reconcile(rows, root)
        base.register_runtime(runtime, root, internal_auth)
        ledger = base.Ledger(runtime, protocol, bridge_manifest, root, internal_auth, probe)
        if ledger.state.get("predecessor_seed") not in (None, predecessor):
            raise base.Halt("N0 predecessor changed; no budget reset")
        ledger.state["predecessor_seed"] = predecessor
        ledger.state["other_usage_reserved"] = max(ledger.state["other_usage_reserved"],
                                                    predecessor["cumulative_debit_without_probe"])
        ledger.save()
        ledger.budget_check(0)
        for rid, attempt in ledger.state["attempts"].items():
            receipt = runtime / "receipts" / (rid + ".json")
            if (attempt["status"] != "completed" or base.sha(receipt) != attempt["receipt_sha256"]
                    or base.sha(Path(attempt["response_path"])) != attempt["response_sha256"]):
                raise base.Halt("Existing N0 response/receipt changed; no repurchase")
        RawCache, read_record, BulkClient, Call, new_session, remember_secret, scrub = base.vendor_imports(bundle, runtime)
        key = key() if callable(key) else key
        if not key or len(key) < 8:
            raise base.Halt("Missing API key")
        remember_secret(key)
        session = base.GuardedSession(fake_session or new_session(), ledger, bridge_rows)
        session.ledger_key = key
        cache = RawCache(runtime / "data/raw")
        client = BulkClient(cache, max_credits=stage.CAP - ledger.reserved(),
                            floor=protocol["budgets"]["account_reserve_floor"], rate_per_sec=4,
                            max_retries=0, session=session, api_key=key,
                            alarm_margin=protocol["billing_reconciliation"]["bulk_client_alarm_margin_credits"])
        if fake_session:
            client.limiter.wait = lambda: None
        ledger.checkpoint = checkpoint
        account = client.account()
        ledger.account(base.integer(account["used"]), base.integer(account["remaining"]))
        base.atomic(runtime / "run-manifest.json", {"stage": "N0", "packet_root": root,
            "source_files": stage.EXPECTED, "predecessor": predecessor,
            "external_authorization_sha256": hashlib.sha256(stage.canonical(authorization)).hexdigest(),
            "internal_priority_bridge": 1, "commit": commit, "runtime": base.current_runtime(),
            "scope": "exact NBA oddsapi_hist h2h rows; no outcomes; no retries; no replan"})
        for row, effective in zip(rows, bridge_rows):
            rid = row["request_id"]
            attempt = ledger.state["attempts"].get(rid)
            cached = cache.lookup("nba", "oddsapi_hist", row["cache_key"])
            if attempt:
                if attempt["status"] != "completed" or cached is None or base.sha(cached) != attempt["response_sha256"]:
                    raise base.Halt("Completed N0 cache changed or missing")
                continue
            if cached is not None:
                raise base.Halt("Unreconciled N0 cache; no repurchase")
            call = Call("NBA_N0", "nba", "oddsapi_hist", row["path"],
                        tuple(sorted(row["params"].items())),
                        __import__("datetime").datetime.fromisoformat(row["requested_utc"].replace("Z", "+00:00")),
                        10, False, cache_sport="nba")
            if call.key != row["cache_key"]:
                raise base.Halt("NBA vendored cache identity differs")
            ledger.reserve(effective)
            checkpoint("after_reservation")
            record = client.fetch(call)
            checkpoint("after_transport")
            cached = cache.lookup("nba", "oddsapi_hist", row["cache_key"])
            if cached is None:
                raise base.Halt("N0 response missing from local cache")
            with cached.open("rb") as f:
                os.fsync(f.fileno())
            base.durable_directory(cached.parent)
            ledger.complete(effective, record, cached)
            checkpoint("after_completion")
        stage.verify_packet(packet, root)
        ledger.state["status"] = "nba_n0_epoch_complete"
        ledger.save()
        return {"status": ledger.state["status"], "paid_calls": len(ledger.state["attempts"]),
                "reserved_new_credits": ledger.reserved(), "billed_new_credits": ledger.billed(),
                "cumulative_reserved": 1687 + ledger.state["other_usage_reserved"] + ledger.reserved(),
                "provider_used": ledger.state["provider_used"], "provider_remaining": ledger.state["provider_remaining"],
                "coverage_review_required": True}
    except BaseException:
        if ledger:
            ledger.halt("N0 epoch stopped; reservations retained; no automatic recovery")
        raise
    finally:
        if client:
            client.session.close()
        if ledger:
            ledger.close()
        global_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if not args.confirm:
        manifest, _, prior = stage.verify_packet(args.packet, args.root)
        print(json.dumps({"offline": True, "new_credits": manifest["new_credits"], "predecessor": prior["root"]}))
        return
    if not args.authorization or not args.key_file:
        raise SystemExit("Exact authorization and key-file required")
    def load_key():
        from dotenv import dotenv_values
        return dotenv_values(args.key_file).get("ODDS_API_KEY")
    try:
        result = run(args.packet, args.root, args.bundle, json.loads(args.authorization.read_text()), key=load_key)
        print(json.dumps(result, indent=2))
    except BaseException:
        raise SystemExit("STOPPED: no automatic resend; preserve N0 ledger, receipts and reservations") from None


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
