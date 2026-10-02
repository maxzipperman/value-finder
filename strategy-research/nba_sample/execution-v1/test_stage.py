"""Outcome-blind N0 source, packet, ancestor and cache boundaries."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage


def write_ledger(root, state):
    folder = stage.RUNTIME_BASE / root
    folder.mkdir(parents=True)
    stage.write(folder / "spending-ledger.json", state)
    stage.write(folder / "INITIALIZED.json", {"bundle_root_sha256": root})
    registrations = stage.RUNTIME_BASE / "registrations"
    registrations.mkdir(exist_ok=True)
    stage.write(registrations / (root + ".json"), {"bundle_root_sha256": root})
    return folder / "spending-ledger.json"


@pytest.fixture
def chain(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path)
    parent = {"bundle_root_sha256": stage.V4_ROOT, "pending": None, "stopped": None,
              "status": "recent_complete_stopped_before_older", "probe_credits": 1687,
              "other_usage_reserved": 5, "attempts": {"prior": {"reserved_credits": 30,
                  "status": "completed", "cache_key": "a" * 20}}, "cache_reuse": {}}
    path = write_ledger(stage.V4_ROOT, parent)
    monkeypatch.setattr(stage, "RECENT_LEDGER_SHA256", stage.sha(path))
    child_root = "b" * 64
    child = {"bundle_root_sha256": child_root, "pending": None, "stopped": None,
             "status": "older_epoch_complete", "probe_credits": 1687,
             "other_usage_reserved": 35, "attempts": {}, "cache_reuse": {},
             "predecessor_seed": {"root": stage.V4_ROOT, "ledger_path": str(path),
                 "ledger_sha256": stage.sha(path), "probe_credits": 1687,
                 "cumulative_debit_without_probe": 35}}
    child_path = write_ledger(child_root, child)
    return path, child_path, child


def test_exact_source_and_cache_identity():
    manifest, rows = stage.source()
    assert manifest["games"] == 56 and len(rows) == 754
    assert sum(r["max_new_credits"] for r in rows) == 7540
    assert {r["sport"] for r in rows} == {"nba"}
    assert {r["source"] for r in rows} == {"oddsapi_hist"}
    assert {r["odds_sport_key"] for r in rows} == {"basketball_nba"}
    assert len({r["cache_key"] for r in rows}) == 754


def test_candidate_packet_round_trip_and_tamper(chain, tmp_path, monkeypatch):
    _, child_path, _ = chain
    original_seed = stage.seed
    monkeypatch.setattr(stage, "seed", lambda path, rows, **kwargs: original_seed(path, rows))
    packet = tmp_path / "packet"
    root = stage.prepare(child_path, packet)
    manifest, rows, predecessor = stage.verify_packet(packet, root)
    assert len(rows) == 754 and manifest["new_credits"] == 7540
    assert predecessor["root"] == "b" * 64
    altered = json.loads((packet / "requests.json").read_text())
    altered[0]["max_new_credits"] = 0
    stage.write(packet / "requests.json", altered)
    with pytest.raises(ValueError, match="frozen root"):
        stage.verify_packet(packet, root)


def test_real_packet_requires_both_f2_partials_and_union(chain, tmp_path):
    _, child_path, _ = chain
    with pytest.raises(ValueError, match="Both exact partial F2"):
        stage.prepare(child_path, tmp_path / "blocked-packet")


def test_child_cannot_drop_real_parent_debit(chain):
    _, child_path, child = chain
    assert stage.seed(child_path, [])["cumulative_debit_without_probe"] == 35
    child["other_usage_reserved"] = 0
    stage.write(child_path, child)
    with pytest.raises(ValueError, match="Cumulative debit decreased"):
        stage.seed(child_path, [])


@pytest.mark.parametrize("value", [-1, True])
def test_negative_or_boolean_carry_rejected(chain, value):
    _, child_path, child = chain
    child["other_usage_reserved"] = value
    stage.write(child_path, child)
    with pytest.raises(ValueError, match="unsettled"):
        stage.seed(child_path, [])


def test_generator_ancestor_cache_key_check(chain):
    _, child_path, _ = chain
    row = {"request_id": "new-request", "cache_key": "a" * 20}
    with pytest.raises(ValueError, match="Ancestor cache overlap"):
        stage.seed(child_path, (r for r in [row]))


def test_pilot_cannot_be_final_n0_predecessor(chain):
    parent_path, _, _ = chain
    with pytest.raises(ValueError, match="completed older stage"):
        stage.seed(parent_path, [])


def test_external_exact_cache_key_stops_preparation(tmp_path, monkeypatch):
    row = stage.source()[1][0]
    external = tmp_path / "external-nba-store"
    folder = external / "nba/oddsapi_hist/2026-01-03"
    folder.mkdir(parents=True)
    (folder / (row["cache_key"] + ".parquet")).write_bytes(b"synthetic exact-key hit")
    monkeypatch.setattr(stage, "raw_roots", lambda own_root=None: [str(external)])
    with pytest.raises(ValueError, match="Existing exact NBA paid cache"):
        stage.reconcile([row])


def test_cross_checkout_inventory_skips_nonexistent_self_store_and_finds_actual_peers(tmp_path, monkeypatch):
    checkout = tmp_path / "project/checkout"
    archive = checkout / "strategy-research/football_archive"
    (archive / "followups/F2-pilot").mkdir(parents=True)
    (archive / "recovery-v1/F2-continuation").mkdir(parents=True)
    (archive / "recovery-v2/F2-second-continuation").mkdir(parents=True)
    historic_project = tmp_path / "historic"
    historic = historic_project / "old/sharp-markets/data/raw"
    sibling = historic_project / "new/sharp-markets/data/raw"
    sibling.mkdir(parents=True)
    stage.write(archive / "followups/F2-pilot/cache-reconciliation.json", {"raw_roots": [str(historic)]})
    stage.write(archive / "recovery-v1/F2-continuation/cache-reconciliation.json", {"raw_roots": [str(historic)]})
    stage.write(archive / "recovery-v2/F2-second-continuation/cache-reconciliation.json", {"raw_roots": [str(historic)]})
    peer = tmp_path / "project/peer/sharp-markets/data/raw"
    peer.mkdir(parents=True)
    global_raw = tmp_path / "global" / ("a" * 64) / "data/raw"
    global_raw.mkdir(parents=True)
    monkeypatch.setattr(stage, "REPO", checkout)
    monkeypatch.setattr(stage, "PROJECT", checkout.parent)
    monkeypatch.setattr(stage, "RUNTIME_BASE", tmp_path / "global")
    roots = set(stage.raw_roots())
    assert str((checkout / "sharp-markets/data/raw").resolve()) not in roots
    assert {str(historic.resolve()), str(sibling.resolve()), str(peer.resolve()),
            str(global_raw.resolve())} <= roots
    self_store = checkout / "sharp-markets/data/raw"
    self_store.mkdir(parents=True)
    assert str(self_store.resolve()) in stage.raw_roots()
    assert str(global_raw.resolve()) not in stage.raw_roots("a" * 64)
