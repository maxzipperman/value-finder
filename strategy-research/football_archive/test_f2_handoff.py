"""Synthetic downstream composition tests; no runtime or network access."""
import importlib.util
import json
from pathlib import Path
import types

import pytest


SOURCE = Path(__file__).with_name("f2_handoff.py")
spec = importlib.util.spec_from_file_location("test_reviewed_f2_handoff", SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize("root,post,proposal,rid", [
    (gate.FIRST_ROOT, gate.FIRST_POST, gate.FIRST_PROPOSAL, gate.FIRST_MISSING),
    (gate.SECOND_ROOT, gate.SECOND_POST, gate.SECOND_PROPOSAL, gate.SECOND_MISSING),
])
def test_only_exact_reconciled_partial_state(root, post, proposal, rid, tmp_path):
    path = tmp_path / "spending-ledger.json"
    state = {"bundle_root_sha256": root, "status": "event_epoch_partial_reconciled",
             "pending": None, "stopped": None,
             "predecessor_seed": {"root": gate.PILOT_ROOT if root == gate.FIRST_ROOT else gate.FIRST_ROOT},
             "missing_resolution": {"proposal_sha256": proposal},
             "attempts": {rid: {"status": "missing", "reserved_credits": 20, "billed_credits": 0}}}
    path.write_text(json.dumps(state))
    assert gate.verify_partial(root, path, state, post) == post
    for altered, digest in [({**state, "status": "event_epoch_complete"}, post),
                            ({**state, "pending": rid}, post),
                            ({**state, "missing_resolution": {"proposal_sha256": "0" * 64}}, post),
                            (state, "0" * 64)]:
        with pytest.raises(ValueError, match="Uncertified"):
            gate.verify_partial(root, path, altered, digest)
    with pytest.raises(ValueError, match="Unknown partial"):
        gate.verify_partial("a" * 64, path, state, post)


def test_unpublished_union_stops_without_import_or_key(tmp_path, monkeypatch):
    marker = tmp_path / "untrusted-ran"
    code = tmp_path / "downstream.py"
    code.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_PATH", code)
    with pytest.raises(ValueError, match="not published"):
        gate.verified_union_module()
    assert not marker.exists()


def test_changed_union_code_cannot_execute_before_digest_check(tmp_path, monkeypatch):
    marker = tmp_path / "untrusted-ran"
    union_dir = tmp_path / "union"
    union_dir.mkdir()
    code = union_dir / "downstream.py"
    code.write_text("def load_verified_union(*args, **kwargs): return object()\n")
    expected = gate.sha(code)
    packet = union_dir / "F3a"
    packet.mkdir()
    certificate = packet / "union-certificate.json"
    certificate.write_text("{}")
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_PATH", code)
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_SHA256", expected)
    monkeypatch.setattr(gate, "UNION_PACKET_PATH", packet)
    monkeypatch.setattr(gate, "UNION_PACKET_ROOT", "e" * 64)
    monkeypatch.setattr(gate, "UNION_CERTIFICATE_SHA256", gate.sha(certificate))
    monkeypatch.setattr(gate, "FINAL_LEDGER_SHA256", "b" * 64)
    code.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
    with pytest.raises(ValueError, match="before import"):
        gate.verified_union_module()
    assert not marker.exists()


def test_full_union_proof_binds_two_partials_counts_and_final_ledger(tmp_path, monkeypatch):
    final = tmp_path / ("b" * 64) / "spending-ledger.json"
    final.parent.mkdir()
    final.write_text('{"status":"event_epoch_complete"}\n')
    union_dir = tmp_path / "union"
    packet = union_dir / "F3a"
    packet.mkdir(parents=True)
    certificate = packet / "union-certificate.json"
    cert = {"schema": "completed-f2-union-certificate-v2", "continuation_root": final.parent.name,
            "continuation_commit": gate.SECOND_TRANSITION_COMMIT,
            "continuation_ledger_sha256": gate.sha(final), "partial_ledger_sha256": gate.FIRST_POST,
            "second_partial_ledger_sha256": gate.SECOND_POST, "request_slots": 1773,
            "opportunity_count": 1774, "missing_categories": {"synthetic": 1},
            "outcomes_joined": False, "purchase_authorized": False}
    coverage = {"schema": "completed-f2-union-v2", "acquisition_complete": True,
                "root": final.parent.name, "ledger_sha256": gate.sha(final),
                "missing_categories": cert["missing_categories"], "response_evidence": [],
                "offline_approvals_authenticated_live": True}
    cert["response_evidence_sha256"] = gate.sha_bytes(gate.canonical(coverage["response_evidence"]))
    cert["coverage_sha256"] = gate.sha_bytes(gate.canonical({k: v for k, v in coverage.items()
        if k != "offline_approvals_authenticated_live"}) + b"\n")
    certificate.write_bytes(gate.canonical(cert) + b"\n")
    code = union_dir / "downstream.py"
    code.write_text("def load_verified_union(*args, **kwargs):\n"
                    "    class Captured:\n"
                    "        def verify_downstream_union(self, *args, **kwargs):\n"
                    "            return " + repr((cert, coverage)) + "\n"
                    "    return Captured()\n")
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_PATH", code)
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_SHA256", gate.sha(code))
    monkeypatch.setattr(gate, "UNION_PACKET_PATH", packet)
    monkeypatch.setattr(gate, "UNION_PACKET_ROOT", "e" * 64)
    monkeypatch.setattr(gate, "UNION_CERTIFICATE_SHA256", gate.sha(certificate))
    monkeypatch.setattr(gate, "FINAL_ROOT", final.parent.name)
    monkeypatch.setattr(gate, "FINAL_LEDGER_SHA256", gate.sha(final))
    binding = {"certificate_sha256": gate.sha(certificate), "final_ledger_sha256": gate.sha(final),
               "coverage_sha256": cert["coverage_sha256"],
               "response_evidence_sha256": cert["response_evidence_sha256"]}
    assert gate.verify_full_union(final) == gate.sha_bytes(gate.canonical(binding))
    altered = {**coverage, "response_evidence": [{"unreviewed": True}]}
    code.write_text("def load_verified_union(*args, **kwargs):\n"
                    "    class Captured:\n"
                    "        def verify_downstream_union(self, *args, **kwargs):\n"
                    "            return " + repr((cert, altered)) + "\n"
                    "    return Captured()\n")
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_SHA256", gate.sha(code))
    with pytest.raises(ValueError, match="differs from the reviewed contract"):
        gate.verify_full_union(final)
    altered = {**coverage, "offline_approvals_authenticated_live": False}
    code.write_text("def load_verified_union(*args, **kwargs):\n"
                    "    class Captured:\n"
                    "        def verify_downstream_union(self, *args, **kwargs):\n"
                    "            return " + repr((cert, altered)) + "\n"
                    "    return Captured()\n")
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_SHA256", gate.sha(code))
    with pytest.raises(ValueError, match="differs from the reviewed contract"):
        gate.verify_full_union(final)
    certificate.write_text('{"tampered":true}')
    with pytest.raises(ValueError, match="certificate bytes changed"):
        gate.verify_full_union(final)
    certificate.write_bytes(gate.canonical(cert) + b"\n")
    code.write_text("def load_verified_union(*args, **kwargs):\n"
                    "    class Captured:\n"
                    "        def verify_downstream_union(self, *args, certificate_path, **kwargs):\n"
                    "            certificate_path.write_text('changed during verification')\n"
                    "            return " + repr((cert, coverage)) + "\n"
                    "    return Captured()\n")
    monkeypatch.setattr(gate, "UNION_BOOTSTRAP_SHA256", gate.sha(code))
    with pytest.raises(ValueError, match="during verification"):
        gate.verify_full_union(final)


@pytest.mark.parametrize("consumer", ["older", "n0"])
def test_both_consumers_require_exact_partial_order_and_full_union(tmp_path, monkeypatch, consumer):
    archive = Path(__file__).parent
    source = (archive / "older/stage.py" if consumer == "older" else
              archive.parent / "nba_sample/execution-v1/stage.py")
    stage_spec = importlib.util.spec_from_file_location("synthetic_" + consumer + "_stage", source)
    stage = importlib.util.module_from_spec(stage_spec)
    stage_spec.loader.exec_module(stage)
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path)
    check_calls = []
    fake_gate = types.SimpleNamespace(FIRST_ROOT=gate.FIRST_ROOT, SECOND_ROOT=gate.SECOND_ROOT,
                                      PILOT_ROOT=gate.PILOT_ROOT)
    def partial(root, path, state, digest):
        check_calls.append(("partial", root))
        if (root not in (gate.FIRST_ROOT, gate.SECOND_ROOT)
                or state["status"] != "event_epoch_partial_reconciled"
                or stage.sha(path) != digest):
            raise ValueError("Uncertified partial F2 ancestor")
    def union(path):
        check_calls.append(("union", Path(path).parent.name))
        return "d" * 64
    fake_gate.verify_partial = partial
    fake_gate.verify_full_union = union
    monkeypatch.setattr(stage, "f2_handoff", lambda: fake_gate)

    def append(root, status, prior=None, attempt=None):
        state = {"bundle_root_sha256": root, "status": status, "pending": None,
                 "stopped": None, "probe_credits": 1687, "other_usage_reserved": 5,
                 "attempts": {} if attempt is None else {attempt: {"status": "missing",
                     "reserved_credits": 20, "billed_credits": 0, "cache_key": attempt[:20]}},
                 "cache_reuse": {}}
        if prior is not None:
            path, debit = prior
            state["other_usage_reserved"] = debit
            state["predecessor_seed"] = {"root": path.parent.name, "ledger_path": str(path),
                "ledger_sha256": stage.sha(path), "probe_credits": 1687,
                "cumulative_debit_without_probe": debit}
        folder = tmp_path / root
        folder.mkdir()
        path = folder / "spending-ledger.json"
        stage.write(path, state)
        stage.write(folder / "INITIALIZED.json", {"bundle_root_sha256": root})
        (tmp_path / "registrations").mkdir(exist_ok=True)
        stage.write(tmp_path / "registrations" / (root + ".json"), {"bundle_root_sha256": root})
        debit = state["other_usage_reserved"] + sum(a["reserved_credits"] for a in state["attempts"].values())
        return path, debit

    source_root = stage.SOURCE_ROOT if consumer == "older" else stage.V4_ROOT
    f1 = append(source_root, "recent_complete_stopped_before_older")
    monkeypatch.setattr(stage, "RECENT_LEDGER_SHA256", stage.sha(f1[0]))
    pilot = append(gate.PILOT_ROOT, "event_epoch_complete", f1)
    first = append(gate.FIRST_ROOT, "event_epoch_partial_reconciled", pilot, gate.FIRST_MISSING)
    second = append(gate.SECOND_ROOT, "event_epoch_partial_reconciled", first, gate.SECOND_MISSING)
    final = append("e" * 64, "event_epoch_complete", second)
    f3a = append("f" * 64, "event_epoch_complete", final)
    newest = append("a" * 64, "older_epoch_complete", f3a) if consumer == "n0" else f3a
    result = stage.seed(newest[0], [], require_f2=True)
    assert result["f2_union_proof_sha256"] == "d" * 64
    assert check_calls == [("union", "e" * 64), ("partial", gate.SECOND_ROOT),
                           ("partial", gate.FIRST_ROOT)]
    check_calls.clear()
    with pytest.raises(ValueError, match="request.*repurchased|request overlap"):
        stage.seed(newest[0], [{"request_id": gate.FIRST_MISSING,
                                  "cache_key": gate.FIRST_MISSING[:20]}], require_f2=True)
    with pytest.raises(ValueError, match="cache.*repurchased|cache overlap"):
        stage.seed(newest[0], [{"request_id": "new-request",
                                  "cache_key": gate.FIRST_MISSING[:20]}], require_f2=True)
    newest_state = json.loads(newest[0].read_text())
    stage.write(newest[0], {**newest_state, "other_usage_reserved": 0})
    with pytest.raises(ValueError, match="decreased"):
        stage.seed(newest[0], [], require_f2=True)
    stage.write(newest[0], newest_state)
    state = json.loads(first[0].read_text())
    state["status"] = "event_epoch_complete"
    stage.write(first[0], state)
    with pytest.raises(ValueError, match="hash changed|hash or|ledger path or hash"):
        stage.seed(newest[0], [], require_f2=True)


@pytest.mark.parametrize("consumer", ["older", "n0"])
def test_consumers_pin_shared_gate_before_import(tmp_path, monkeypatch, consumer):
    archive = Path(__file__).parent
    source = (archive / "older/stage.py" if consumer == "older" else
              archive.parent / "nba_sample/execution-v1/stage.py")
    stage_spec = importlib.util.spec_from_file_location("pin_" + consumer + "_stage", source)
    stage = importlib.util.module_from_spec(stage_spec)
    stage_spec.loader.exec_module(stage)
    marker = tmp_path / "gate-ran"
    altered = tmp_path / "f2_handoff.py"
    altered.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
    monkeypatch.setattr(stage, "F2_HANDOFF_PATH", altered)
    with pytest.raises(ValueError, match="before import"):
        stage.f2_handoff()
    assert not marker.exists()
