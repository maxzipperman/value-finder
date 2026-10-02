"""Hub-only older bulk-odds driver using the immutable v4 accounting/HTTP stack.

Offline verification is the CLI default. A paid run requires --confirm, an
exact approved packet/current commit, and a key file. No automatic recovery.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import types

import stage


def verified_v4_bytes(bundle):
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("Frozen v4 bundle must be an ordinary directory")
    def regular(path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Frozen v4 source permits regular files only")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(fd)
    if any(p.is_symlink() for p in bundle.rglob("*")):
        raise ValueError("Frozen v4 source contains a symlink")
    captured = {str(p.relative_to(bundle)): regular(p) for p in bundle.rglob("*")
                if p.is_file() and p.name != "FREEZE.json"}
    files = {name: hashlib.sha256(data).hexdigest() for name, data in captured.items()}
    cert = json.loads(regular(bundle / "FREEZE.json"))
    root = hashlib.sha256(stage.canonical(files)).hexdigest()
    if files != cert["file_sha256"] or root != cert["bundle_root_sha256"] or root != stage.SOURCE_ROOT:
        raise ValueError("Frozen v4 source bytes or pinned root changed before import")
    return captured


def source_executor(bundle):
    bundle = Path(bundle)
    stage.source(bundle)
    captured = verified_v4_bytes(bundle)
    sys.path.insert(0, str(bundle))
    def module(name, filename):
        result = types.ModuleType(name)
        result.__file__ = str(bundle / filename)
        exec(compile(captured[filename], result.__file__, "exec"), result.__dict__)
        return result
    base = module("older_reviewed_v4_executor", "executor.py")
    builder = module("older_reviewed_v4_builder", "builder.py")
    eligibility = module("older_reviewed_v4_eligibility", "price_eligibility.py")
    validator = module("older_reviewed_v4_validator", "validator.py")
    previous = {name: sys.modules.get(name) for name in ("builder", "executor", "price_eligibility")}
    try:
        sys.modules.update(builder=builder, executor=base, price_eligibility=eligibility)
        validator.verify(bundle, stage.SOURCE_ROOT, check_cache=True)
    finally:
        for name, prior in previous.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    return base


def checkout_clean(packet):
    repo = Path(subprocess.check_output(["git", "-C", str(packet), "rev-parse", "--show-toplevel"], text=True).strip())
    paths = [packet / name for name in ("FREEZE.json", "manifest.json", "requests.json", "request-list.csv",
             "seed.json", "coverage-decision.json", "cache-reconciliation.json")]
    paths.extend([Path(__file__), Path(stage.__file__), stage.F2_HANDOFF_PATH])
    relative = [str(p.resolve().relative_to(repo)) for p in paths]
    subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", *relative],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "diff", "--exit-code", "HEAD", "--", *relative],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def exact_approval(base, authorization, manifest, root, commit, live):
    if authorization.get("priority") != 2 or authorization.get("stage") != "older-priority-2":
        raise base.Halt("Explicit older priority-2 approval required")
    # v4's immutable Ledger is priority-1-only. The internal compatibility
    # view changes only the non-identity priority field after exact source
    # verification; the external approval and frozen packet remain priority 2.
    internal = {**authorization, "priority": 1}
    bridge_manifest = {**manifest, "new_credits_by_priority": {"1": stage.MAX_CREDITS}}
    base.validate_authorization(internal, bridge_manifest, root, commit)
    if live:
        base.verify_live_hub_comment(internal)
    reconciliation = authorization.get("account_reconciliation")
    base.validate_reconciliation(reconciliation, root)
    if reconciliation.get("account_only_recovery") or "pre_run_other_usage_budget_debit" in reconciliation:
        raise base.Halt("Automatic recovery or debit override disabled")
    ceiling = reconciliation["max_baseline_used"]
    line = f"APPROVED account ceiling: max-baseline-used {ceiling}, root {root}"
    if line not in authorization["hub_go_ahead"]["comment_body"].splitlines():
        raise base.Halt("Account ceiling must be authenticated by the hub comment")
    if authorization["execution_commit"] != commit:
        raise base.Halt("Exact reviewed execution commit changed")
    return internal, bridge_manifest


def cache_hits(row, exclude_root=None):
    hits = set()
    for raw in stage.raw_roots(exclude_root):
        directory = Path(raw) / row["sport"] / row["source"]
        hits.update(p.resolve() for p in directory.glob(f"*/{row['cache_key']}.parquet"))
    return sorted(hits)


def preflight_cache(rows, bundle, exclude_root=None):
    return stage.reconcile_cache(rows, bundle, exclude_root)


def global_settled(current_root):
    for path in stage.RUNTIME_BASE.glob("*/spending-ledger.json"):
        if path.parent.name == current_root:
            continue
        state = json.loads(path.read_text())
        if state.get("pending") or state.get("stopped"):
            raise ValueError("Unresolved global acquisition epoch")


def internal_rows(rows):
    return [{**row, "priority": 1} for row in rows]


def run(packet, root, bundle, coverage_path, authorization, *, key, fake_session=None, checkpoint=lambda _: None):
    packet, bundle = Path(packet).resolve(), Path(bundle).resolve()
    manifest, rows, predecessor = stage.verify_packet(packet, root, bundle, coverage_path)
    base = source_executor(bundle)
    commit = checkout_clean(packet)
    runtime = base.runtime_path(root)
    base.execution_context(packet, root, runtime)
    if base.current_runtime() != json.loads((bundle / "runtime-lock.json").read_text()):
        raise base.Halt("Reviewed v4 runtime differs")
    internal_auth, bridge_manifest = exact_approval(base, authorization, manifest, root, commit, fake_session is None)
    base.validate_reconciliation(internal_auth["account_reconciliation"], root)
    preflight_cache(rows, bundle, root)
    stage.seed(predecessor["ledger_path"], (r for r in rows if r["max_new_credits"]), require_f2=True)
    global_settled(root)
    source_rows = internal_rows(rows)
    bridge_manifest["requests"] = source_rows
    protocol = json.loads((bundle / "protocol.json").read_text())
    probe = json.loads((bundle / "probe-spending-ledger.json").read_text())
    stage.RUNTIME_BASE.mkdir(parents=True, exist_ok=True)
    global_lock = (stage.RUNTIME_BASE / "followup-purchase.lock").open("a")
    ledger = client = None
    try:
        fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage.verify_packet(packet, root, bundle, coverage_path)
        global_settled(root)
        preflight_cache(rows, bundle, root)
        base.register_runtime(runtime, root, internal_auth)
        ledger = base.Ledger(runtime, protocol, bridge_manifest, root, internal_auth, probe)
        if ledger.state.get("predecessor_seed") not in (None, predecessor):
            raise base.Halt("Predecessor changed; no restart reset")
        ledger.state["predecessor_seed"] = predecessor
        ledger.state["other_usage_reserved"] = max(ledger.state["other_usage_reserved"],
                                                    predecessor["cumulative_debit_without_probe"])
        ledger.save()
        ledger.budget_check(0)
        existing = ledger.state["attempts"]
        for rid, attempt in existing.items():
            receipt = runtime / "receipts" / (rid + ".json")
            if (attempt["status"] != "completed" or base.sha(receipt) != attempt["receipt_sha256"]
                    or base.sha(Path(attempt["response_path"])) != attempt["response_sha256"]):
                raise base.Halt("Existing older response evidence missing or changed")
        verified_v4_bytes(bundle)
        RawCache, read_record, BulkClient, Call, new_session, remember_secret, scrub = base.vendor_imports(bundle, runtime)
        for row in rows:
            if not row["max_new_credits"]:
                base.validate_response(row, read_record(bundle / row["cache_source"]), protocol)
        key = key() if callable(key) else key
        if not key or len(key) < 8:
            raise base.Halt("Missing API key")
        remember_secret(key)
        session = base.GuardedSession(fake_session or new_session(), ledger, source_rows)
        session.ledger_key = key
        cache = RawCache(runtime / "data/raw")
        client = BulkClient(cache, max_credits=stage.MAX_CREDITS - ledger.reserved(),
                            floor=protocol["budgets"]["account_reserve_floor"], rate_per_sec=4,
                            max_retries=0, session=session, api_key=key,
                            alarm_margin=protocol["billing_reconciliation"]["bulk_client_alarm_margin_credits"])
        if fake_session:
            client.limiter.wait = lambda: None
        ledger.checkpoint = checkpoint
        account = client.account()
        ledger.account(base.integer(account["used"]), base.integer(account["remaining"]))
        base.atomic(runtime / "run-manifest.json", {
            "stage": "older-priority-2", "packet_root": root, "source_root": stage.SOURCE_ROOT,
            "predecessor": predecessor, "external_authorization_sha256": hashlib.sha256(stage.canonical(authorization)).hexdigest(),
            "internal_priority_bridge": 1, "commit": commit, "runtime": base.current_runtime(),
            "scope": "exact frozen priority-2 rows; no outcomes; no retries; no replan"})
        for row, effective in zip(rows, source_rows):
            rid = row["request_id"]
            if row["max_new_credits"] == 0:
                if ledger.state["cache_reuse"].get(rid) not in (None, row["cache_sha256"]):
                    raise base.Halt("Reused evidence changed")
                ledger.state["cache_reuse"][rid] = row["cache_sha256"]
                ledger.save()
                continue
            attempt = ledger.state["attempts"].get(rid)
            cached = cache.lookup(row["sport"], row["source"], row["cache_key"])
            if attempt:
                if attempt["status"] != "completed" or cached is None or base.sha(cached) != attempt["response_sha256"]:
                    raise base.Halt("Completed older response missing or changed")
                continue
            if cached is not None:
                raise base.Halt("Unreconciled older cache; no repurchase")
            call = Call("FOOTBALL_ARCHIVE_OLDER", row["sport"], row["source"], row["path"],
                        tuple(sorted(row["params"].items())),
                        __import__("datetime").datetime.fromisoformat(row["requested_utc"].replace("Z", "+00:00")),
                        row["max_credits"], False, cache_sport=row["sport"])
            if call.key != row["cache_key"]:
                raise base.Halt("Vendored cache identity differs")
            ledger.reserve(effective)
            checkpoint("after_reservation")
            record = client.fetch(call)
            checkpoint("after_transport")
            cached = cache.lookup(row["sport"], row["source"], row["cache_key"])
            if cached is None:
                raise base.Halt("Older response missing from cache")
            with cached.open("rb") as f:
                os.fsync(f.fileno())
            base.durable_directory(cached.parent)
            ledger.complete(effective, record, cached)
            checkpoint("after_completion")
        stage.verify_packet(packet, root, bundle, coverage_path)
        ledger.state["status"] = "older_epoch_complete"
        ledger.save()
        return {"status": ledger.state["status"], "paid_calls": len(ledger.state["attempts"]),
                "reserved_new_credits": ledger.reserved(), "billed_new_credits": ledger.billed(),
                "cumulative_reserved": 1687 + ledger.state["other_usage_reserved"] + ledger.reserved(),
                "provider_used": ledger.state["provider_used"], "provider_remaining": ledger.state["provider_remaining"],
                "coverage_review_required": True}
    except BaseException:
        if ledger:
            ledger.halt("Older epoch stopped; reservations retained; review before recovery")
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
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if not args.confirm:
        manifest, _, prior = stage.verify_packet(args.packet, args.root, args.bundle, args.coverage)
        print(json.dumps({"offline": True, "new_credits": manifest["new_credits"], "predecessor": prior["root"]}))
        return
    if not args.authorization or not args.key_file:
        raise SystemExit("Exact authorization and key-file required")
    def load_key():
        from dotenv import dotenv_values
        return dotenv_values(args.key_file).get("ODDS_API_KEY")
    try:
        result = run(args.packet, args.root, args.bundle, args.coverage,
                     json.loads(args.authorization.read_text()), key=load_key)
        print(json.dumps(result, indent=2))
    except BaseException:
        raise SystemExit("STOPPED: no automatic resend; preserve runtime ledger, receipts and reservations") from None


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
