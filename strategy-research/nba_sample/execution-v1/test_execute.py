"""No-network full N0 execution and adverse accounting/transport paths."""
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
    bundle = HERE.parents[2] / "strategy-research/football_archive/acquisition/football-archive-v4"
    spec = importlib.util.spec_from_file_location("n0_test_v4_executor", bundle / "executor.py")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base, bundle


def approval(root, manifest, ceiling=100000):
    commit = "b" * 40
    cap = manifest["new_credits"]
    body = (f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set "
            f"{manifest['request_set_sha256']}, budget {cap} credits, commit {commit}")
    reconciliation = {"status": "approved", "bundle_root_sha256": root,
        "baseline_mode": "capture_first_free_check", "reason": "synthetic N0 test",
        "owner_note": "SYNTHETIC TEST ONLY", "max_baseline_used": ceiling,
        "billing_period_utc": datetime.now(timezone.utc).strftime("%Y-%m")}
    return {"status": "approved", "bundle_root_sha256": root, "stage": "N0", "priority": "N0",
        "max_new_credits": cap, "human_authorization_evidence": "SYNTHETIC TEST ONLY",
        "execution_commit": commit, "account_reconciliation": reconciliation,
        "hub_go_ahead": {"status": "approved", "bundle_root_sha256": root,
            "request_set_sha256": manifest["request_set_sha256"],
            "request_list_sha256": manifest["request_list_sha256"], "budget_credits": cap,
            "commit": commit, "comment_url": "https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1",
            "comment_body": body + "\n" + f"APPROVED account ceiling: max-baseline-used {ceiling}, root {root}"}}


def test_exact_n0_approval_and_ceiling_binding():
    base, _ = frozen_base()
    root = "a" * 64
    manifest = {"request_list_sha256": stage.EXPECTED["request-list.csv"],
                "request_set_sha256": stage.REQUEST_SET_SHA256, "new_credits": stage.CAP}
    auth = approval(root, manifest)
    internal, bridge = execute.exact_approval(base, auth, manifest, root, "b" * 40, live=False)
    assert auth["priority"] == "N0" and internal["priority"] == 1
    assert bridge["new_credits_by_priority"] == {"1": 7540}
    bad = {**auth, "priority": 1}
    with pytest.raises(base.Halt, match="N0 stage"):
        execute.exact_approval(base, bad, manifest, root, "b" * 40, live=False)
    bad = {**auth, "account_reconciliation": {**auth["account_reconciliation"], "max_baseline_used": 100001}}
    with pytest.raises(base.Halt, match="ceiling"):
        execute.exact_approval(base, bad, manifest, root, "b" * 40, live=False)


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    base, bundle = frozen_base()
    sys.path.insert(0, str(bundle))
    _, rows = stage.source()
    root = "f" * 64
    manifest = {"request_list_sha256": stage.EXPECTED["request-list.csv"],
                "request_set_sha256": stage.REQUEST_SET_SHA256, "new_credits": stage.CAP}
    predecessor = {"root": "e" * 64, "ledger_path": "synthetic", "ledger_sha256": "0" * 64,
                   "probe_credits": 1687, "cumulative_debit_without_probe": 85489}
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path / "global")
    monkeypatch.setattr(stage, "verify_packet", lambda *args: (manifest, rows, predecessor))
    monkeypatch.setattr(stage, "seed", lambda *args: predecessor)
    monkeypatch.setattr(stage, "reconcile", lambda *args: {"exact_cache_overlap": 0})
    monkeypatch.setattr(execute, "source_executor", lambda *args: base)
    monkeypatch.setattr(execute, "checkout_clean", lambda *args: "b" * 40)
    monkeypatch.setattr(execute, "global_settled", lambda *args: None)
    monkeypatch.setattr(base, "runtime_path", lambda *args: stage.RUNTIME_BASE / root)
    monkeypatch.setattr(base, "execution_context", lambda *args: None)
    monkeypatch.setattr(base, "register_runtime", lambda *args: None)
    monkeypatch.setattr(base, "current_runtime", lambda: json.loads((bundle / "runtime-lock.json").read_text()))
    return base, bundle, rows, root, manifest, stage.RUNTIME_BASE / root


class FakeResponse:
    def __init__(self, body, headers, status=200):
        self.text, self.headers, self.status_code = body, headers, status


class FakeSession:
    def __init__(self, mode="ok"):
        from requests.adapters import HTTPAdapter
        self.adapters = {"https": HTTPAdapter(max_retries=0)}
        self.mode, self.calls, self.paid_keys = mode, [], []
        self.used, self.remaining = 100000, 4900000

    def get(self, url, params=None, **kwargs):
        assert kwargs["allow_redirects"] is False
        self.calls.append(url)
        if url.endswith("/sports"):
            return FakeResponse("[]", {"x-requests-last": "0", "x-requests-used": str(self.used),
                                       "x-requests-remaining": str(self.remaining)})
        if self.mode == "timeout":
            import requests
            raise requests.Timeout("synthetic no-network timeout")
        params = dict(params)
        params.pop("apiKey", None)
        assert url == "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds"
        assert params["markets"] == "h2h" and params["bookmakers"] == "pinnacle,lowvig,betonlineag"
        assert params["date"] not in self.paid_keys
        self.paid_keys.append(params["date"])
        self.used += 10
        self.remaining -= 10
        at = datetime.fromisoformat(params["date"].replace("Z", "+00:00"))
        stamp = lambda dt: dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        body = json.dumps({"timestamp": stamp(at - timedelta(minutes=5)),
                           "previous_timestamp": stamp(at - timedelta(minutes=10)),
                           "next_timestamp": stamp(at), "data": []})
        headers = {"x-requests-last": "10", "x-requests-used": str(self.used),
                   "x-requests-remaining": str(self.remaining)}
        if self.mode == "overcharge":
            headers["x-requests-last"] = "11"
        if self.mode == "bad_billing":
            headers.pop("x-requests-last")
        return FakeResponse(body, headers, 429 if self.mode == "http429" else 200)

    def close(self):
        pass


def test_full_754_row_synthetic_purchase(synthetic_run):
    base, bundle, rows, root, manifest, runtime = synthetic_run
    fake = FakeSession()
    result = execute.run(runtime, root, bundle, approval(root, manifest),
                         key="SYNTHETIC_KEY_ONLY", fake_session=fake)
    assert result["status"] == "nba_n0_epoch_complete"
    assert result["paid_calls"] == len(fake.paid_keys) == 754
    assert result["reserved_new_credits"] == result["billed_new_credits"] == 7540
    assert result["provider_used"] == 107540 and result["provider_remaining"] == 4892460
    assert len(fake.calls) == 755 and len(set(fake.paid_keys)) == 754
    ledger = json.loads((runtime / "spending-ledger.json").read_text())
    assert not ledger["pending"] and not ledger["stopped"]
    assert all(a["status"] == "completed" and a["reserved_credits"] == 10 for a in ledger["attempts"].values())


def test_crash_after_reservation_never_resends(synthetic_run):
    base, bundle, rows, root, manifest, runtime = synthetic_run
    fake = FakeSession()
    class PowerLoss(BaseException):
        pass
    def crash(point):
        if point == "after_reservation":
            raise PowerLoss()
    with pytest.raises(PowerLoss):
        execute.run(runtime, root, bundle, approval(root, manifest),
                    key="SYNTHETIC_KEY_ONLY", fake_session=fake, checkpoint=crash)
    ledger = json.loads((runtime / "spending-ledger.json").read_text())
    assert ledger["pending"] == rows[0]["request_id"] and ledger["stopped"]
    assert ledger["attempts"][rows[0]["request_id"]]["reserved_credits"] == 10
    assert len(fake.calls) == 1  # Only the free account check happened.
    second = FakeSession()
    with pytest.raises(base.Halt, match="Pending paid attempt"):
        execute.run(runtime, root, bundle, approval(root, manifest),
                    key="SYNTHETIC_KEY_ONLY", fake_session=second)
    assert not second.calls


@pytest.mark.parametrize("mode", ["http429", "timeout", "overcharge", "bad_billing"])
def test_first_bad_transport_stops_without_retry(synthetic_run, mode):
    base, bundle, rows, root, manifest, runtime = synthetic_run
    fake = FakeSession(mode)
    with pytest.raises(Exception):
        execute.run(runtime, root, bundle, approval(root, manifest),
                    key="SYNTHETIC_KEY_ONLY", fake_session=fake)
    ledger = json.loads((runtime / "spending-ledger.json").read_text())
    assert ledger["pending"] == rows[0]["request_id"] and ledger["stopped"]
    assert len(fake.calls) == 2  # Free account check and one attempted paid GET.
    assert ledger["attempts"][rows[0]["request_id"]]["reserved_credits"] >= 10


def test_wrong_stage_rejected_before_key_or_runtime(synthetic_run):
    base, bundle, rows, root, manifest, runtime = synthetic_run
    auth = approval(root, manifest)
    auth["priority"] = 1
    reads = []
    with pytest.raises(base.Halt, match="N0 stage"):
        execute.run(runtime, root, bundle, auth, key=lambda: reads.append(True), fake_session=FakeSession())
    assert not reads and not runtime.exists()


def test_real_global_pending_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path)
    other = tmp_path / ("c" * 64)
    other.mkdir()
    (other / "spending-ledger.json").write_text(json.dumps({"pending": "attempt", "stopped": "halted"}))
    with pytest.raises(ValueError, match="Unresolved global"):
        execute.global_settled("d" * 64)


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
    monkeypatch.setattr(stage, "V4_ROOT", root)
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
    monkeypatch.setattr(stage, "V4_ROOT", root)
    if change == "extra":
        (bundle / "extra.py").write_text("pass\n")
    elif change == "missing":
        (bundle / "executor.py").unlink()
    else:
        (bundle / "linked.py").symlink_to(bundle / "executor.py")
    with pytest.raises(ValueError, match="source|before import"):
        execute.verified_v4_bytes(bundle)


def test_v4_loader_executes_verified_capture_even_if_file_changes_after_capture(tmp_path, monkeypatch):
    bundle = tmp_path / "source"
    bundle.mkdir()
    files = {"executor.py": b"CAPTURED = True\n", "builder.py": b"pass\n",
             "price_eligibility.py": b"pass\n", "validator.py": b"def verify(*args, **kwargs): pass\n"}
    for name, data in files.items():
        (bundle / name).write_bytes(data)
    marker = tmp_path / "reopened-untrusted-source"
    actual_verify = execute.verified_v4_bytes
    def change_after_capture(path):
        captured = actual_verify(path)
        (bundle / "executor.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
        return captured
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    root = hashlib.sha256(stage.canonical(hashes)).hexdigest()
    stage.write(bundle / "FREEZE.json", {"bundle_root_sha256": root, "file_sha256": hashes})
    monkeypatch.setattr(stage, "V4_ROOT", root)
    monkeypatch.setattr(execute, "verified_v4_bytes", change_after_capture)
    assert execute.source_executor(bundle).CAPTURED is True
    assert not marker.exists()
