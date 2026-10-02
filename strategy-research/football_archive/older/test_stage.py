"""Adverse offline ancestry and cross-store cache checks."""
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
    parent = {"bundle_root_sha256": stage.SOURCE_ROOT, "pending": None, "stopped": None,
              "status": "recent_complete_stopped_before_older", "probe_credits": 1687,
              "other_usage_reserved": 5, "attempts": {"prior": {"reserved_credits": 30,
                  "status": "completed", "cache_key": "a" * 20}}, "cache_reuse": {}}
    path = write_ledger(stage.SOURCE_ROOT, parent)
    monkeypatch.setattr(stage, "RECENT_LEDGER_SHA256", stage.sha(path))
    child_root = "b" * 64
    child = {"bundle_root_sha256": child_root, "pending": None, "stopped": None,
             "status": "event_epoch_complete", "probe_credits": 1687,
             "other_usage_reserved": 35, "attempts": {}, "cache_reuse": {},
             "predecessor_seed": {"root": stage.SOURCE_ROOT, "ledger_path": str(path),
                 "ledger_sha256": stage.sha(path), "probe_credits": 1687,
                 "cumulative_debit_without_probe": 35}}
    child_path = write_ledger(child_root, child)
    return path, child_path, child


def test_child_must_carry_actual_parent_debit(chain):
    _, child_path, child = chain
    assert stage.seed(child_path, [])["cumulative_debit_without_probe"] == 35
    child["other_usage_reserved"] = 0
    stage.write(child_path, child)
    with pytest.raises(ValueError, match="Child cumulative debit decreased"):
        stage.seed(child_path, [])


@pytest.mark.parametrize("value", [-1, True])
def test_negative_or_boolean_child_debit_rejected(chain, value):
    _, child_path, child = chain
    child["other_usage_reserved"] = value
    stage.write(child_path, child)
    with pytest.raises(ValueError, match="Invalid ancestor accounting value"):
        stage.seed(child_path, [])


def test_generator_preserves_ancestor_cache_key_check(chain):
    parent_path, _, _ = chain
    paid = {"request_id": "new-request", "cache_key": "a" * 20}
    with pytest.raises(ValueError, match="Ancestor cache would be repurchased"):
        stage.seed(parent_path, (row for row in [paid]))


def test_external_raw_store_overlap_blocks_paid_row(tmp_path, monkeypatch):
    external = tmp_path / "legacy-external-store"
    row = {"request_id": "new-request", "sport": "americanfootball_nfl",
           "source": "oddsapi/hist_odds", "cache_key": "c" * 20, "max_new_credits": 30}
    folder = external / row["sport"] / row["source"] / "2022-12-31"
    folder.mkdir(parents=True)
    (folder / (row["cache_key"] + ".parquet")).write_bytes(b"synthetic exact-key hit")
    monkeypatch.setattr(stage, "raw_roots", lambda exclude_root=None: [str(external)])
    with pytest.raises(ValueError, match="Existing exact paid cache key"):
        stage.reconcile_cache([row], tmp_path)
