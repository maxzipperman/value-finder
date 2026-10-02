"""No-network adverse paths for the priority-2 compatibility bridge."""
import importlib.util
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import execute
import stage


def frozen_base():
    bundle = HERE.parent / "acquisition/football-archive-v4"
    spec = importlib.util.spec_from_file_location("older_test_v4_executor", bundle / "executor.py")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base, bundle


def approval(root, manifest):
    commit = "b" * 40
    cap = manifest["new_credits"]
    body = (f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set "
            f"{manifest['request_set_sha256']}, budget {cap} credits, commit {commit}")
    reconciliation = {"status": "approved", "bundle_root_sha256": root,
        "baseline_mode": "capture_first_free_check", "reason": "synthetic test",
        "owner_note": "SYNTHETIC TEST ONLY", "max_baseline_used": 1700,
        "billing_period_utc": datetime.now(timezone.utc).strftime("%Y-%m")}
    return {"status": "approved", "bundle_root_sha256": root, "stage": "older-priority-2",
        "priority": 2, "max_new_credits": cap, "human_authorization_evidence": "SYNTHETIC TEST ONLY",
        "execution_commit": commit, "account_reconciliation": reconciliation,
        "hub_go_ahead": {"status": "approved", "bundle_root_sha256": root,
            "request_set_sha256": manifest["request_set_sha256"],
            "request_list_sha256": manifest["request_list_sha256"], "budget_credits": cap,
            "commit": commit, "comment_url": "https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1",
            "comment_body": body + "\n" + f"APPROVED account ceiling: max-baseline-used 1700, root {root}"}}


def test_exact_priority_two_approval_bridges_without_changing_frozen_row():
    base, bundle = frozen_base()
    root = "a" * 64
    manifest = {"request_list_sha256": "1" * 64, "request_set_sha256": "2" * 64,
                "new_credits": stage.MAX_CREDITS}
    auth = approval(root, manifest)
    internal, bridge = execute.exact_approval(base, auth, manifest, root, "b" * 40, live=False)
    assert auth["priority"] == 2 and internal["priority"] == 1
    assert bridge["new_credits_by_priority"] == {"1": stage.MAX_CREDITS}
    bad = {**auth, "priority": 1}
    with pytest.raises(base.Halt, match="priority-2"):
        execute.exact_approval(base, bad, manifest, root, "b" * 40, live=False)
    bad = {**auth, "account_reconciliation": {**auth["account_reconciliation"], "max_baseline_used": 1800}}
    with pytest.raises(base.Halt, match="ceiling"):
        execute.exact_approval(base, bad, manifest, root, "b" * 40, live=False)


def test_durable_reservation_never_resends_after_crash(tmp_path):
    base, bundle = frozen_base()
    cfg = json.loads((bundle / "protocol.json").read_text())
    probe = json.loads((bundle / "probe-spending-ledger.json").read_text())
    original = next(r for r in json.loads((bundle / "request-manifest.json").read_text())["requests"]
                    if r["priority"] == 2 and r["max_new_credits"] == 30)
    effective = execute.internal_rows([original])[0]
    assert original["priority"] == 2 and effective["priority"] == 1
    root = "c" * 64
    external = approval(root, {"request_list_sha256": "1" * 64,
                               "request_set_sha256": "2" * 64, "new_credits": stage.MAX_CREDITS})
    internal, manifest = execute.exact_approval(base, external,
        {"request_list_sha256": "1" * 64, "request_set_sha256": "2" * 64, "new_credits": stage.MAX_CREDITS},
        root, "b" * 40, live=False)
    manifest["requests"] = [effective]
    ledger = base.Ledger(tmp_path / root, cfg, manifest, root, internal, probe)
    ledger.account(1687, 4998313)
    ledger.reserve(effective)
    assert json.loads(ledger.path.read_text())["attempts"][original["request_id"]]["status"] == "pending"
    ledger.close()
    with pytest.raises(base.Halt, match="Pending paid attempt"):
        base.Ledger(tmp_path / root, cfg, manifest, root, internal, probe)


def test_completed_existing_cache_is_excluded_from_new_purchase_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path)
    row = {"sport": "americanfootball_nfl", "source": "oddsapi/hist_odds", "cache_key": "a" * 20}
    own_root = "b" * 64
    own = tmp_path / own_root / "data/raw" / row["sport"] / row["source"] / "2025"
    own.mkdir(parents=True)
    (own / (row["cache_key"] + ".parquet")).write_bytes(b"synthetic")
    assert execute.cache_hits(row, own_root) == []
    other = tmp_path / ("c" * 64) / "data/raw" / row["sport"] / row["source"] / "2025"
    other.mkdir(parents=True)
    (other / (row["cache_key"] + ".parquet")).write_bytes(b"synthetic")
    assert len(execute.cache_hits(row, own_root)) == 1


def test_confirm_rejects_wrong_stage_before_key_or_transport(tmp_path, monkeypatch):
    base, bundle = frozen_base()
    root = "d" * 64
    manifest = {"request_list_sha256": "1" * 64, "request_set_sha256": "2" * 64,
                "new_credits": stage.MAX_CREDITS}
    auth = approval(root, manifest)
    auth["priority"] = 1
    monkeypatch.setattr(stage, "verify_packet", lambda *args: (manifest, [], {}))
    monkeypatch.setattr(execute, "source_executor", lambda *args: base)
    monkeypatch.setattr(execute, "checkout_clean", lambda *args: "b" * 40)
    monkeypatch.setattr(base, "runtime_path", lambda *args: tmp_path / root)
    monkeypatch.setattr(base, "execution_context", lambda *args: None)
    monkeypatch.setattr(base, "current_runtime", lambda: json.loads((bundle / "runtime-lock.json").read_text()))
    key_reads = []
    with pytest.raises(base.Halt, match="priority-2"):
        execute.run(tmp_path, root, bundle, tmp_path / "coverage", auth,
                    key=lambda: key_reads.append(True), fake_session=object())
    assert not key_reads and not (tmp_path / root).exists()


def test_global_pending_epoch_blocks_new_root(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path)
    other = tmp_path / ("e" * 64)
    other.mkdir()
    (other / "spending-ledger.json").write_text(json.dumps({"pending": "attempt", "stopped": None}))
    with pytest.raises(ValueError, match="Unresolved global"):
        execute.global_settled("f" * 64)


@pytest.mark.parametrize("tampered", ["executor.py", "validator.py"])
def test_changed_v4_code_never_executes_before_freeze_check(tmp_path, monkeypatch, tampered):
    bundle = tmp_path / "source"
    bundle.mkdir()
    for name in ("executor.py", "validator.py"):
        (bundle / name).write_text("pass\n")
    files = {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
             for name in ("executor.py", "validator.py")}
    root = hashlib.sha256(stage.canonical(files)).hexdigest()
    stage.write(bundle / "FREEZE.json", {"bundle_root_sha256": root, "file_sha256": files})
    monkeypatch.setattr(stage, "SOURCE_ROOT", root)
    monkeypatch.setattr(stage, "source", lambda *args: None)
    marker = tmp_path / "untrusted-code-ran"
    (bundle / tampered).write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
    with pytest.raises(ValueError, match="before import"):
        execute.source_executor(bundle)
    assert not marker.exists()


@pytest.mark.parametrize("change", ["extra", "missing", "symlink"])
def test_v4_file_inventory_rejects_shape_changes(tmp_path, monkeypatch, change):
    bundle = tmp_path / "source"
    bundle.mkdir()
    (bundle / "executor.py").write_text("pass\n")
    files = {"executor.py": hashlib.sha256((bundle / "executor.py").read_bytes()).hexdigest()}
    root = hashlib.sha256(stage.canonical(files)).hexdigest()
    stage.write(bundle / "FREEZE.json", {"bundle_root_sha256": root, "file_sha256": files})
    monkeypatch.setattr(stage, "SOURCE_ROOT", root)
    if change == "extra":
        (bundle / "extra.py").write_text("pass\n")
    elif change == "missing":
        (bundle / "executor.py").unlink()
    else:
        (bundle / "linked.py").symlink_to(bundle / "executor.py")
    with pytest.raises(ValueError, match="source|before import"):
        execute.verified_v4_bytes(bundle)


def test_v4_loader_executes_verified_capture_after_file_changes(tmp_path, monkeypatch):
    bundle = tmp_path / "source"
    bundle.mkdir()
    files = {"executor.py": b"CAPTURED = True\n", "builder.py": b"pass\n",
             "price_eligibility.py": b"pass\n", "validator.py": b"def verify(*args, **kwargs): pass\n"}
    for name, data in files.items():
        (bundle / name).write_bytes(data)
    marker = tmp_path / "reopened-untrusted-source"
    original_verify = execute.verified_v4_bytes
    def change_after_capture(path):
        captured = original_verify(path)
        (bundle / "executor.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
        return captured
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    root = hashlib.sha256(stage.canonical(hashes)).hexdigest()
    stage.write(bundle / "FREEZE.json", {"bundle_root_sha256": root, "file_sha256": hashes})
    monkeypatch.setattr(stage, "SOURCE_ROOT", root)
    monkeypatch.setattr(stage, "source", lambda *args: None)
    monkeypatch.setattr(execute, "verified_v4_bytes", change_after_capture)
    assert execute.source_executor(bundle).CAPTURED is True
    assert not marker.exists()


@pytest.mark.parametrize("crash_at", [None, "after_reservation"])
def test_confirm_path_reserves_before_send_and_refuses_resend(tmp_path, monkeypatch, crash_at):
    from requests.adapters import HTTPAdapter
    base, bundle = frozen_base()
    sys.path.insert(0, str(bundle))
    root = "f" * 64
    row = next(r for r in json.loads((bundle / "request-manifest.json").read_text())["requests"]
               if r["priority"] == 2 and r["max_new_credits"] == 30)
    manifest = {"request_list_sha256": "1" * 64, "request_set_sha256": "2" * 64,
                "new_credits": stage.MAX_CREDITS}
    auth = approval(root, manifest)
    prior = {"root": "e" * 64, "ledger_path": "synthetic", "ledger_sha256": "0" * 64,
             "probe_credits": 1687, "cumulative_debit_without_probe": 85489}
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path)
    monkeypatch.setattr(stage, "verify_packet", lambda *args: (manifest, [row], prior))
    monkeypatch.setattr(stage, "seed", lambda *args, **kwargs: prior)
    monkeypatch.setattr(execute, "source_executor", lambda *args: base)
    monkeypatch.setattr(execute, "checkout_clean", lambda *args: "b" * 40)
    monkeypatch.setattr(execute, "preflight_cache", lambda *args: None)
    monkeypatch.setattr(execute, "global_settled", lambda *args: None)
    monkeypatch.setattr(base, "runtime_path", lambda *args: tmp_path / root)
    monkeypatch.setattr(base, "execution_context", lambda *args: None)
    monkeypatch.setattr(base, "register_runtime", lambda *args: None)
    monkeypatch.setattr(base, "current_runtime", lambda: json.loads((bundle / "runtime-lock.json").read_text()))
    calls = []
    class Response:
        def __init__(self, text, headers):
            self.text, self.headers, self.status_code = text, headers, 200
    class Session:
        adapters = {"https": HTTPAdapter(max_retries=0)}
        def get(self, url, params=None, **kwargs):
            calls.append(url)
            assert kwargs["allow_redirects"] is False
            if url.endswith("/sports"):
                return Response("[]", {"x-requests-last": "0", "x-requests-used": "1687",
                                       "x-requests-remaining": "4998313"})
            at = datetime.fromisoformat(row["requested_utc"].replace("Z", "+00:00"))
            stamp = lambda dt: dt.isoformat(timespec="seconds").replace("+00:00", "Z")
            body = json.dumps({"timestamp": stamp(at - timedelta(minutes=5)),
                "previous_timestamp": stamp(at - timedelta(minutes=10)),
                "next_timestamp": stamp(at), "data": []})
            return Response(body, {"x-requests-last": "30", "x-requests-used": "1717",
                                   "x-requests-remaining": "4998283"})
        def close(self):
            pass
    class PowerLoss(BaseException):
        pass
    def crash(point):
        if point == crash_at:
            raise PowerLoss()
    if crash_at:
        with pytest.raises(PowerLoss):
            execute.run(tmp_path, root, bundle, tmp_path / "coverage", auth,
                        key="SYNTHETIC_KEY_ONLY", fake_session=Session(), checkpoint=crash)
    else:
        result = execute.run(tmp_path, root, bundle, tmp_path / "coverage", auth,
                             key="SYNTHETIC_KEY_ONLY", fake_session=Session(), checkpoint=crash)
        assert result["status"] == "older_epoch_complete"
        assert result["reserved_new_credits"] == result["billed_new_credits"] == 30
        assert len(calls) == 2
        return
    ledger = json.loads((tmp_path / root / "spending-ledger.json").read_text())
    assert ledger["pending"] == row["request_id"] and ledger["stopped"]
    assert ledger["attempts"][row["request_id"]]["reserved_credits"] == 30
    assert len(calls) == 1  # Free account check only; crash occurred before paid send.
    with pytest.raises(base.Halt, match="Pending paid attempt"):
        execute.run(tmp_path, root, bundle, tmp_path / "coverage", auth,
                    key="SYNTHETIC_KEY_ONLY", fake_session=Session())
    assert len(calls) == 1
