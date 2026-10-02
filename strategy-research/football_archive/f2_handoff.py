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

# PR119 must publish one self-contained, read-only downstream verifier and its
# final certificate. The reviewed byte hashes are pinned here before use.
UNION_VERIFIER_PATH = None
UNION_VERIFIER_SHA256 = None
UNION_CERTIFICATE_PATH = None
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
    if (not UNION_VERIFIER_PATH or not re.fullmatch("[a-f0-9]{64}", UNION_VERIFIER_SHA256 or "")
            or not UNION_CERTIFICATE_PATH or not re.fullmatch("[a-f0-9]{64}", UNION_CERTIFICATE_SHA256 or "")
            or not re.fullmatch("[a-f0-9]{40}", SECOND_TRANSITION_COMMIT or "")):
        raise ValueError("Final reviewed F2 union proof is not published")
    path = Path(UNION_VERIFIER_PATH)
    data = regular_bytes(path)
    if sha_bytes(data) != UNION_VERIFIER_SHA256:
        raise ValueError("Reviewed F2 union verifier bytes changed before import")
    module = types.ModuleType("reviewed_f2_downstream_union")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    if not callable(getattr(module, "verify_downstream_union", None)):
        raise ValueError("Reviewed F2 union verifier has no downstream entrypoint")
    return module


def verify_full_union(final_ledger_path):
    """Require PR119's independently pinned deep evidence proof before use."""
    module = verified_union_module()
    certificate = Path(UNION_CERTIFICATE_PATH)
    if sha_bytes(regular_bytes(certificate)) != UNION_CERTIFICATE_SHA256:
        raise ValueError("Reviewed F2 union certificate bytes changed")
    final_ledger_path = Path(final_ledger_path).resolve()
    final_sha = sha(final_ledger_path)
    proof = module.verify_downstream_union(final_ledger_path,
        certificate_path=certificate, first_transition_commit=FIRST_TRANSITION_COMMIT,
        second_transition_commit=SECOND_TRANSITION_COMMIT, authenticate=True)
    if (sha_bytes(regular_bytes(certificate)) != UNION_CERTIFICATE_SHA256
            or sha(final_ledger_path) != final_sha):
        raise ValueError("F2 union evidence changed during verification")
    if (not isinstance(proof, dict) or proof.get("status") != "full_f2_union_verified"
            or proof.get("final_root") != final_ledger_path.parent.name
            or proof.get("final_ledger_sha256") != final_sha
            or proof.get("certificate_sha256") != UNION_CERTIFICATE_SHA256
            or proof.get("first_partial") != {"root": FIRST_ROOT, "ledger_sha256": FIRST_POST,
                                                "transition_commit": FIRST_TRANSITION_COMMIT}
            or proof.get("second_partial") != {"root": SECOND_ROOT, "ledger_sha256": SECOND_POST,
                                                 "transition_commit": SECOND_TRANSITION_COMMIT}
            or proof.get("request_slots") != 1773 or proof.get("opportunities") != 1774
            or not re.fullmatch("[a-f0-9]{64}", proof.get("disjoint_ownership_sha256", ""))):
        raise ValueError("Full F2 union proof differs from the reviewed contract")
    return sha_bytes(canonical(proof))
