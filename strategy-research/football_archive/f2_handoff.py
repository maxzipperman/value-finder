"""Shared fail-closed F2 ancestry gate for the older and N0 acquisition stages.

The union verifier and certificate pins are filled only after PR119's final
review. No downstream packet can be prepared while either pin is absent.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types


FIRST_ROOT = "059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4"
SECOND_ROOT = "4053703d09fdcedb6ce1608c8a5a0d09d3e702a6426891463163224e10af792e"
PILOT_ROOT = "cbe125474acf46becd3f7e01903675ece864adb683cdc73734bad7e1635dddcc"
FIRST_POST = "cc2f17d3289ac1dbebac6bcf5d828f4384f2ea4c9d88829c2d8510a014a57313"
SECOND_POST = "d10808cb0ba3962ff3abdef5d48c09cb53d3a95733e0b3b6c2bc605feccee3aa"
FIRST_PROPOSAL = "8e8bb95f87b7b51e04eca912e1a30db44578f2746d33b5ccc3ad796a435aeb30"
SECOND_PROPOSAL = "1c94c10be95b9097ec598a982df2caf2509292d45385322c8e035dcc771cadfb"
FIRST_MISSING = "850c02077a7ef01010d277ad63cff3a88847548a9a1a70424fa8252ccf632c9a"
SECOND_MISSING = "cbacd1c8b9929a1386777465ca18148ea7feb7a88e6917542cca3a9ff4eba719"
FIRST_TRANSITION_COMMIT = "20bcaa35d3d5b6f93d292062c2480e3edb82a83a"
# PR121's reviewed execution head, authenticated by the hub's exact offline
# approval on PR99; the subsequent downstream checkout commit is unrelated.
SECOND_TRANSITION_COMMIT = "3f29479fd8c9c5798ceb08b0c2d26d3c0e2706cb"

# PR119's bootstrap is self-contained and captures/hashes the entire sibling
# dependency/packet map before importing the reviewed union implementation.
# All final byte/root/ledger pins stay absent until its completed packet exists.
FINAL_ROOT = "7485bc1230aeaf069a21e0a75ca9d93002c2e8abccdddaa706e45c5aa63aa467"
FINAL_LEDGER_SHA256 = "84ff08834943ab4418d69efa9c5ce9355d0be20931fee20df149937a5064d0cd"
UNION_BOOTSTRAP_PATH = Path(__file__).resolve().parent / "union-v1/downstream.py"
UNION_BOOTSTRAP_SHA256 = None
UNION_PACKET_PATH = Path(__file__).resolve().parent / "union-v1/F3a"
UNION_PACKET_ROOT = None
UNION_CERTIFICATE_SHA256 = None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def regular_bytes(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Shared F2 proof source must be a regular file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Shared F2 proof source must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def verify_partial(root, ledger_path, state, ledger_sha256):
    """Accept only the two exact reconciled F2 ledgers, never a status class."""
    pins = {
        FIRST_ROOT: (FIRST_POST, FIRST_PROPOSAL, FIRST_MISSING),
        SECOND_ROOT: (SECOND_POST, SECOND_PROPOSAL, SECOND_MISSING),
    }
    if root not in pins:
        raise ValueError("Unknown partial F2 ancestor")
    expected_sha, proposal, request_id = pins[root]
    attempt = state.get("attempts", {}).get(request_id, {})
    resolution = state.get("missing_resolution", {})
    expected_parent = PILOT_ROOT if root == FIRST_ROOT else FIRST_ROOT
    if (ledger_sha256 != expected_sha or state.get("bundle_root_sha256") != root
            or state.get("status") != "event_epoch_partial_reconciled"
            or state.get("pending") is not None or state.get("stopped") is not None
            or state.get("predecessor_seed", {}).get("root") != expected_parent
            or resolution.get("proposal_sha256") != proposal
            or attempt.get("status") != "missing" or type(attempt.get("reserved_credits")) is not int
            or attempt["reserved_credits"] != 20 or type(attempt.get("billed_credits")) is not int
            or attempt["billed_credits"] != 0 or not Path(ledger_path).is_file()):
        raise ValueError("Uncertified partial F2 ancestor")
    return expected_sha


def verified_union_module():
    if (not UNION_BOOTSTRAP_PATH or not re.fullmatch("[a-f0-9]{64}", UNION_BOOTSTRAP_SHA256 or "")
            or not UNION_PACKET_PATH or not re.fullmatch("[a-f0-9]{64}", UNION_PACKET_ROOT or "")
            or not re.fullmatch("[a-f0-9]{64}", UNION_CERTIFICATE_SHA256 or "")
            or not re.fullmatch("[a-f0-9]{64}", FINAL_LEDGER_SHA256 or "")):
        raise ValueError("Final reviewed F2 union proof is not published")
    path = Path(UNION_BOOTSTRAP_PATH)
    packet = Path(UNION_PACKET_PATH)
    if packet != path.parent / "F3a":
        raise ValueError("Union packet must accompany its pinned bootstrap")
    data = regular_bytes(path)
    if sha_bytes(data) != UNION_BOOTSTRAP_SHA256:
        raise ValueError("Reviewed F2 union bootstrap bytes changed before import")
    bootstrap = types.ModuleType("reviewed_f2_downstream_bootstrap")
    bootstrap.__file__ = str(path)
    exec(compile(data, str(path), "exec"), bootstrap.__dict__)
    if not callable(getattr(bootstrap, "load_verified_union", None)):
        raise ValueError("Reviewed F2 union bootstrap has no captured loader")
    return bootstrap.load_verified_union(packet, UNION_PACKET_ROOT)


def verify_full_union(final_ledger_path):
    """Require PR119's independently pinned deep evidence proof before use."""
    module = verified_union_module()
    certificate = Path(UNION_PACKET_PATH) / "union-certificate.json"
    if sha_bytes(regular_bytes(certificate)) != UNION_CERTIFICATE_SHA256:
        raise ValueError("Reviewed F2 union certificate bytes changed")
    final_ledger_path = Path(final_ledger_path).resolve()
    final_sha = sha(final_ledger_path)
    if final_ledger_path.parent.name != FINAL_ROOT or final_sha != FINAL_LEDGER_SHA256:
        raise ValueError("Exact completed F2 ledger pin changed")
    proof = module.verify_downstream_union(final_ledger_path,
        certificate_path=certificate, first_transition_commit=FIRST_TRANSITION_COMMIT,
        second_transition_commit=SECOND_TRANSITION_COMMIT, authenticate=True)
    if not isinstance(proof, tuple) or len(proof) != 2:
        raise ValueError("Full F2 union verifier returned no certificate and coverage")
    cert, coverage = proof
    if (sha_bytes(regular_bytes(certificate)) != UNION_CERTIFICATE_SHA256
            or sha(final_ledger_path) != final_sha):
        raise ValueError("F2 union evidence changed during verification")
    if (not isinstance(cert, dict) or not isinstance(coverage, dict)
            or cert.get("schema") != "completed-f2-union-certificate-v2"
            or cert.get("continuation_root") != FINAL_ROOT
            or cert.get("continuation_commit") != SECOND_TRANSITION_COMMIT
            or cert.get("continuation_ledger_sha256") != final_sha
            or cert.get("partial_ledger_sha256") != FIRST_POST
            or cert.get("second_partial_ledger_sha256") != SECOND_POST
            or cert.get("request_slots") != 1773 or cert.get("opportunity_count") != 1774
            or not re.fullmatch("[a-f0-9]{64}", cert.get("response_evidence_sha256", ""))
            or not re.fullmatch("[a-f0-9]{64}", cert.get("coverage_sha256", ""))
            or cert.get("outcomes_joined") is not False or cert.get("purchase_authorized") is not False
            or coverage.get("schema") != "completed-f2-union-v2"
            or coverage.get("acquisition_complete") is not True
            or coverage.get("root") != FINAL_ROOT or coverage.get("ledger_sha256") != final_sha
            or coverage.get("missing_categories") != cert.get("missing_categories")
            or coverage.get("offline_approvals_authenticated_live") is not True
            or sha_bytes(canonical(coverage.get("response_evidence"))) != cert["response_evidence_sha256"]
            or sha_bytes(canonical({k: v for k, v in coverage.items()
                                    if k != "offline_approvals_authenticated_live"}) + b"\n") != cert["coverage_sha256"]
            or sha_bytes(canonical(cert) + b"\n") != UNION_CERTIFICATE_SHA256):
        raise ValueError("Full F2 union proof differs from the reviewed contract")
    return sha_bytes(canonical({"certificate_sha256": UNION_CERTIFICATE_SHA256,
        "final_ledger_sha256": final_sha, "coverage_sha256": cert["coverage_sha256"],
        "response_evidence_sha256": cert["response_evidence_sha256"]}))
