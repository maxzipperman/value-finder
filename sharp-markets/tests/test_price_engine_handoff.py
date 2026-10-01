"""`markets price-engine --handoff`: F1 as pulled by the football archive bundle (issue #101; amendment 2, DRAFT).

Every bundle here is made up. Its responses are the engine's synthetic fixture (nothing in it is data), written by
main's RawCache, which the bundle vendors byte for byte; its `cache_handoff.py` is the frozen file from the bundle
(tests/frozen/football_archive_cache_handoff.py.frozen, checked against the bundle's FREEZE.json hash); its
validator and executor are small stand-ins with the checks the handoff relies on. No network, no key, no real
response, no 2026 data."""
import dataclasses
import hashlib
import importlib.machinery
import json
import os
import shutil
import socket
import subprocess
import sys
from argparse import Namespace
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from markets.cache import Fetched
from markets.oddsapi import bulk
from markets.research.price_engine import fixture, handoff
from markets.research.price_engine import run as pe_run

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "frozen" / "football_archive_cache_handoff.py.frozen"
# FROZEN_SHA256 and BRANCH_FILE pin v4's cache_handoff.py as frozen today (its hash in the bundle's FREEZE.json, and
# where it is on the research branch). A re-freeze of the bundle that changes cache_handoff.py must update the
# .frozen copy, FROZEN_SHA256 and, for a new bundle folder, BRANCH_FILE together.
# cache_handoff.py's sha256 as FREEZE.json lists it (file_sha256["cache_handoff.py"], v4 root 410289fe...), not the
# hash of FREEZE.json itself
FROZEN_SHA256 = "abfc4035c8ac947c69e874ab22d75cbc1c2f3aef2ef0023f32efee9b809be8bf"
BRANCH_FILE = ("origin/research/football-archive-v4:strategy-research/football_archive/acquisition/"
               "football-archive-v4/cache_handoff.py")
REUSED = 12
RUNTIME = "football-acquisition-runtime"     # the made-up bundles' runtime, next to the bundle (handed in explicitly)
NFL, CFB = fixture.NFL, fixture.CFB

VALIDATOR = '''"""Made-up bundle (test only): the frozen file set and root, as the real validator checks them first."""
import hashlib, json
from pathlib import Path
def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
def verify(folder, expected_root=None, check_cache=False):
    folder = Path(folder); cert = json.loads((folder / 'FREEZE.json').read_text())
    actual = {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'FREEZE.json'}
    if actual != cert['file_sha256']: raise ValueError('Frozen file set or bytes changed')
    root = hashlib.sha256(canonical(actual)).hexdigest()
    if root != cert['bundle_root_sha256'] or (expected_root is not None and root != expected_root):
        raise ValueError('Independently pinned root mismatch')
    return {'bundle_root_sha256': root}
'''
EXECUTOR = '''"""Made-up bundle (test only): the response identity check the handoff runs on every response."""
import json
class Halt(RuntimeError): pass
def validate_response(row, record, protocol):
    if (record['cache_key'] != row['cache_key'] or record['sport'] != row['sport'] or record['source'] != row['source']
        or record['url'] != 'https://api.the-odds-api.com/v4' + row['path'] or json.loads(record['params_json']) != row['params']):
        raise Halt('Response request identity mismatch')
    if record['http_status'] != 200: raise Halt('HTTP response requires inspection')
'''


def _canonical(v) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def freeze(bundle: Path) -> str:
    files = {str(p.relative_to(bundle)): _sha(p) for p in sorted(bundle.rglob("*"))
             if p.is_file() and p.name != "FREEZE.json"}
    root = hashlib.sha256(_canonical(files)).hexdigest()
    (bundle / "FREEZE.json").write_text(json.dumps({"bundle_root_sha256": root, "file_sha256": files}))
    return root


def extra_calls(cache) -> list:
    """Snapshots the legacy plan never asks for, written into the fixture's cache: an evening decision slot
    (02:30 UTC, n1's day), one 40 minutes before n1's kickoff, and an alternate close 5 minutes after it."""
    out = []
    for at in ("2024-09-08T02:30:00Z", "2024-09-08T16:20:00Z", "2024-09-08T17:05:00Z"):
        t = fixture.t(at)
        c = bulk.Call("F1", NFL, bulk.SRC_ODDS, f"/historical/sports/{NFL}/odds",
                      bulk._odds_params(fixture.CFG["books"]["us10"], fixture.CFG["featured"], t), t, 30, False,
                      cache_sport=NFL)
        cache.get_or_fetch(sport=NFL, source=c.source, data_date=t.date().isoformat(), url=c.url,
                           params=dict(c.params), fetch=lambda t=t: Fetched(200, {}, json.dumps(fixture.body(t, NFL))))
        out.append(c)
    return out


def make_bundle(tmp: Path, calls: list, cache, missing: dict | None = None) -> tuple[Path, Path, str]:
    """A made-up frozen bundle and a completed runtime holding `calls`: the first REUSED in the bundle's reuse/,
    the rest as completed paid responses in the runtime's RawCache layout. Returns (bundle, runtime, root).

    `missing` maps the index of a paid call to a reason: the bundle's run accepted that call as missing, as the v4
    executor's accept_as_missing records it (attempt status `missing`, a receipt, and for `snapshot_lag` the saved
    HTTP 200 it rejected, left in the runtime's raw cache at the call's cache path; for `http_5xx` no response)."""
    bundle, runtime = tmp / "acquisition" / "football-archive-test", tmp / "acquisition" / RUNTIME
    (bundle / "reuse").mkdir(parents=True)
    shutil.copyfile(FROZEN, bundle / "cache_handoff.py")
    (bundle / "validator.py").write_text(VALIDATOR)
    (bundle / "executor.py").write_text(EXECUTOR)
    (bundle / "protocol.json").write_text("{}")
    rows, attempts, reuse = [], {}, {}
    for i, c in enumerate(calls):
        params = dict(c.params)
        rid = hashlib.sha256(_canonical({"source": c.source, "url": bulk.BASE_URL + c.path, "params": params})).hexdigest()
        src = cache.lookup(c.cache_sport, c.source, c.key)
        row = {"request_id": rid, "sport": c.sport, "source": c.source, "path": c.path, "params": params,
               "requested_utc": bulk.iso(c.at), "cache_key": c.key, "priority": 1, "max_credits": 30,
               "max_new_credits": 30, "cache_source": None, "cache_sha256": None, "sealed": False,
               "purposes": ["test"]}
        if i in (missing or {}):
            assert i >= REUSED, "only a paid call can be accepted as missing"
            reason, dest = missing[i], None
            if reason == "snapshot_lag":
                dest = (runtime / "data" / "raw" / c.cache_sport / c.source / c.at.date().isoformat()
                        / f"{c.key}.parquet")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
            receipt = runtime / "receipts" / f"{rid}.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps({"request_id": rid, "status": "accepted_missing", "reason": reason}))
            attempts[rid] = {"status": "missing", "missing_reason": reason,
                             "response_path": str(dest.resolve()) if dest else None,
                             "response_sha256": _sha(dest) if dest else None, "receipt_sha256": _sha(receipt)}
        elif i < REUSED:
            dest = bundle / "reuse" / f"{c.key}.parquet"
            shutil.copyfile(src, dest)
            row.update(max_new_credits=0, cache_source=f"reuse/{c.key}.parquet", cache_sha256=_sha(dest))
            reuse[rid] = _sha(dest)
        else:
            dest = runtime / "data" / "raw" / c.cache_sport / c.source / c.at.date().isoformat() / f"{c.key}.parquet"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            receipt = runtime / "receipts" / f"{rid}.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps({"request_id": rid, "record_sha256": _sha(dest)}))
            attempts[rid] = {"status": "completed", "response_path": str(dest.resolve()), "response_sha256": _sha(dest),
                             "receipt_sha256": _sha(receipt)}
        rows.append(row)
    (bundle / "request-manifest.json").write_text(json.dumps({"requests": rows, "request_count": len(rows),
                                                              "request_set_sha256": hashlib.sha256(_canonical(rows)).hexdigest()}))
    root = freeze(bundle)
    (runtime / "spending-ledger.json").write_text(json.dumps({
        "bundle_root_sha256": root, "pending": None, "stopped": None, "status": "recent_complete_stopped_before_older",
        "attempts": attempts, "cache_reuse": reuse}))
    (runtime / "coverage-report.json").write_text(json.dumps({"bundle_root_sha256": root, "outcomes_joined": False,
                                                              "all_recent_requests_completed": True}))
    return bundle, runtime, root


def load(bundle: Path, root: str, cfg: dict, runtime=None):
    """handoff.load with the made-up bundle's runtime, next to it (the default is the executor's fixed folder)."""
    return handoff.load(bundle, root, cfg, runtime or Path(bundle).parent / RUNTIME)


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("handoff_fixture")
    cfg, calls, cache, scores = fixture.build(tmp)
    calls = calls + extra_calls(cache)
    return cfg, calls, cache, scores


def refreeze(bundle: Path, runtime: Path, monkeypatch) -> str:
    """Re-freeze a bundle changed on purpose: its new root in FREEZE.json, the runtime's records and the registration."""
    root = freeze(bundle)
    for f in ("spending-ledger.json", "coverage-report.json"):
        v = json.loads((runtime / f).read_text())
        (runtime / f).write_text(json.dumps({**v, "bundle_root_sha256": root}))
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", root)
    return root


@pytest.fixture
def made(fx, tmp_path, monkeypatch):
    cfg, calls, cache, scores = fx
    bundle, runtime, root = make_bundle(tmp_path, calls, cache)
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", root)     # as the hub fills it in when it registers amendment 2
    return cfg, calls, cache, scores, bundle, runtime, root


def test_the_frozen_cache_handoff_is_the_bundles():
    assert _sha(FROZEN) == FROZEN_SHA256
    try:
        branch = subprocess.run(["git", "show", BRANCH_FILE], capture_output=True, cwd=HERE, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git not available")
    if branch.returncode != 0:
        pytest.skip("research/football-archive-v4 not fetched here")
    assert branch.stdout == FROZEN.read_bytes()


def test_the_handoff_gives_the_same_quotes_as_the_calls_handed_in(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, info = load(bundle, root, cfg)
    assert [c.key for c in hcalls] == [c.key for c in calls]
    assert info["calls"] == len(calls) and info["reused"] == REUSED and info["bundle_root_sha256"] == root
    assert info["spending_ledger_sha256"] == _sha(runtime / "spending-ledger.json")
    direct = pe_run.run(cfg, calls, cache, scores=scores)
    via = pe_run.run(cfg, hcalls, hcache, scores=scores)
    pd.testing.assert_frame_equal(via["quotes"], direct["quotes"])
    assert via["drops"] == direct["drops"] and via["sealed_calls"] == direct["sealed_calls"] > 0
    pd.testing.assert_frame_equal(via["results"], direct["results"])
    for v in direct["graded"]:
        pd.testing.assert_frame_equal(via["graded"][v], direct["graded"][v])
    # the extra snapshots were read like any other: the decision slot is in the quotes
    assert (via["quotes"].snap == pd.Timestamp("2024-09-08T02:30:00Z")).any()


def test_the_reused_responses_are_found_in_the_bundles_reuse_folder(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, info = load(bundle, root, cfg)
    found = [hcache.lookup(c.cache_sport, c.source, c.key) for c in hcalls]
    assert all(p is not None for p in found)
    in_reuse = [p for p in found if p.parent == bundle.resolve() / "reuse"]
    assert len(in_reuse) == REUSED == info["reused"]
    assert {p.stem for p in in_reuse} == {c.key for c in calls[:REUSED]}
    q = pe_run.run(cfg, hcalls[:REUSED], hcache, scores=scores)["quotes"]
    assert len(q) and set(q.snap) <= {pd.Timestamp(c.at) for c in calls[:REUSED]}
    with pytest.raises(RuntimeError, match="Read-only"):
        hcache.get_or_fetch()


def test_sealed_2026_rows_never_reach_the_engine(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, _ = load(bundle, root, cfg)
    in_2026 = [c for c in hcalls if c.at.year == 2026]
    assert in_2026 and all(c.sealed for c in in_2026)
    # the registered filter in bulk.load_rows drops them even as as_calls hands them over (every call unsealed)
    left_out = Counter()
    rows = bulk.load_rows(cfg, [dataclasses.replace(c, sealed=False) for c in hcalls], hcache, left_out=left_out)
    assert rows and not [r for r in rows if r["commence_time"].startswith("2026")]
    assert left_out["sealed season"] > 0
    res = pe_run.run(cfg, hcalls, hcache, scores=scores)
    assert not res["quotes"].event_id.isin(["n26", "c26"]).any() and "2026" not in set(res["quotes"].season)
    assert not any(g.event_id.isin(["n26", "c26"]).any() for g in res["graded"].values() if len(g))


def test_no_snapshot_at_or_after_kickoff_and_no_entry_inside_the_last_hour(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, _ = load(bundle, root, cfg)
    res = pe_run.run(cfg, hcalls, hcache, scores=scores)
    q = res["quotes"]
    assert (q.snap < q.kickoff).all() and (q.snap < q.commence).all()
    alt = q.snap == pd.Timestamp("2024-09-08T17:05:00Z")       # the alternate close, after n1's kickoff
    assert alt.any() and not (alt & (q.event_id == "n1")).any()   # it still lists n2, which kicks off later
    without = pe_run.run(cfg, hcalls[:-1], hcache, scores=scores)
    assert res["drops"]["at_or_after_kickoff"] > without["drops"]["at_or_after_kickoff"]
    # the slot 40 minutes before n1's kickoff is loaded (it can be a close) but is never an entry
    assert ((q.snap == pd.Timestamp("2024-09-08T16:20:00Z")) & (q.event_id == "n1")).any()
    bets = pd.concat([g for g in res["graded"].values() if len(g)])
    assert len(bets) and ((bets.kickoff - bets.snap) > timedelta(minutes=60)).all()
    assert ((bets.commence - bets.snap) > timedelta(minutes=60)).all()


def _no_import(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the bundle's code was imported")
    monkeypatch.setattr(handoff._FrozenLoader, "exec_module", refuse)
    monkeypatch.setattr(handoff.importlib, "import_module", refuse)


@pytest.mark.parametrize("change", ["reuse_byte", "code_byte", "manifest_byte", "extra_file", "pycache", "missing_file"])
def test_a_bundle_whose_hashes_do_not_verify_is_refused_before_any_code_runs(made, monkeypatch, change):
    cfg, calls, cache, scores, bundle, runtime, root = made
    if change == "reuse_byte":
        p = next((bundle / "reuse").iterdir())
        b = bytearray(p.read_bytes())
        b[len(b) // 2] ^= 1                     # one bit of one byte
        p.write_bytes(bytes(b))
    elif change == "code_byte":
        p = bundle / "cache_handoff.py"
        p.write_bytes(p.read_bytes().replace(b"Read-only", b"Read-onlY"))
    elif change == "manifest_byte":
        p = bundle / "request-manifest.json"
        p.write_bytes(p.read_bytes()[:-1] + b" ")
    elif change == "extra_file":
        (bundle / "sitecustomize.py").write_text("raise SystemExit('ran')\n")
    elif change == "pycache":
        (bundle / "__pycache__").mkdir()
        (bundle / "__pycache__" / "validator.cpython-312.pyc").write_bytes(b"x")
    else:
        next((bundle / "reuse").iterdir()).unlink()
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="differ from its FREEZE.json") as refused:
        load(bundle, root, cfg)
    assert refused.value.before_read


def test_a_root_other_than_the_pinned_one_is_refused(made, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="not the root registered"):
        load(bundle, "0" * 64, cfg)
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", "0" * 64)       # registered and pinned, but not this bundle's
    with pytest.raises(handoff.HandoffRefused, match="not the pinned"):
        load(bundle, "0" * 64, cfg)
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", root)
    for bad in (None, "", root[:63], root.upper()):
        with pytest.raises(handoff.HandoffRefused, match="64-character"):
            load(bundle, bad, cfg)
    # a FREEZE.json whose root is not its own hash map's
    cert = json.loads((bundle / "FREEZE.json").read_text())
    (bundle / "FREEZE.json").write_text(json.dumps({**cert, "bundle_root_sha256": "f" * 64}))
    with pytest.raises(handoff.HandoffRefused, match="not FREEZE.json's"):
        load(bundle, root, cfg)


@pytest.mark.parametrize("change", ["paid_response", "receipt", "incomplete", "outcomes_joined", "wrong_ledger_root"])
def test_the_bundles_own_checks_still_refuse(made, change):
    """The engine's check covers the frozen folder; build_handoff covers what was bought (the runtime)."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    ledger_path = runtime / "spending-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    if change == "paid_response":
        p = Path(next(iter(ledger["attempts"].values()))["response_path"])
        p.write_bytes(p.read_bytes() + b"x")
    elif change == "receipt":
        p = next((runtime / "receipts").iterdir())
        p.write_text(p.read_text() + " ")
    elif change == "incomplete":
        ledger_path.write_text(json.dumps({**ledger, "status": "running"}))
    elif change == "outcomes_joined":
        p = runtime / "coverage-report.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), "outcomes_joined": True}))
    else:
        ledger_path.write_text(json.dumps({**ledger, "bundle_root_sha256": "e" * 64}))
    with pytest.raises(handoff.HandoffRefused, match="the bundle's handoff refused: ValueError") as refused:
        load(bundle, root, cfg)
    assert not refused.value.before_read          # the bundle's code had started reading responses


def test_a_changed_response_after_loading_is_refused_on_lookup(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, _ = load(bundle, root, cfg)
    p = hcache.lookup(hcalls[-1].cache_sport, hcalls[-1].source, hcalls[-1].key)
    p.write_bytes(p.read_bytes() + b"x")
    with pytest.raises(handoff.HandoffRefused, match="changed after the handoff was loaded.*Changed response bytes"):
        pe_run.run(cfg, hcalls, hcache, scores=scores)


def test_nothing_is_written_into_the_bundle_and_nothing_of_it_stays_loaded(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    sys.modules["validator"] = marker = type(sys)("validator")      # an unrelated module of the same name
    path_before, flag_before = list(sys.path), sys.dont_write_bytecode
    try:
        load(bundle, root, cfg)
        assert sys.modules["validator"] is marker
    finally:
        sys.modules.pop("validator", None)
    assert sys.path == path_before and sys.dont_write_bytecode == flag_before
    assert not [k for k in sys.modules if k in ("executor", "cache_handoff")]
    assert not list(bundle.rglob("__pycache__")) and handoff.verify_frozen(bundle, root) == root
    assert socket.getaddrinfo is not handoff._no_network and socket.socket.connect is not handoff._no_network


def test_the_bundles_code_cannot_open_a_connection(made, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    p = bundle / "cache_handoff.py"
    p.write_text(p.read_text() + "\nimport socket\nsocket.create_connection(('127.0.0.1', 9))\n")
    root = refreeze(bundle, runtime, monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="network"):
        load(bundle, root, cfg)


def test_the_command_reads_the_handoff_and_writes_the_report(made, tmp_path, monkeypatch, capsys):
    cfg, calls, cache, scores, bundle, runtime, root = made
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    real_run = pe_run.run
    monkeypatch.setattr(pe_run, "run", lambda c, k, h: real_run(c, k, h, scores=scores))
    out = tmp_path / "out"
    assert pe_run.main(Namespace(fixture=False, out=str(out), handoff=str(bundle), handoff_root=root,
                                 handoff_runtime=str(runtime))) == 0
    printed = capsys.readouterr().out
    assert f"{len(calls):,} calls, {REUSED} of them reused" in printed and "variants tested: 38" in printed
    report = (out / "report.md").read_text()
    assert f"Bundle root `{root}`" in report and "(amendment 2)" in report
    assert f"spending ledger `{_sha(runtime / 'spending-ledger.json')}`" in report
    assert f"**{pe_run.DAILY_NOTE} {pe_run.HANDOFF_NOTE}**" in report
    assert "evening decision slots" in pe_run.HANDOFF_NOTE and "27 of the legacy plan's close" in pe_run.HANDOFF_NOTE
    assert pe_run.HANDOFF_NOTE in printed
    real_run(cfg, calls, cache, scores=scores)["results"].to_csv(tmp_path / "direct.csv", index=False)
    assert (out / "results.csv").read_bytes() == (tmp_path / "direct.csv").read_bytes()


def test_the_command_refuses_a_bad_bundle_and_bad_flag_combinations(made, tmp_path, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    with pytest.raises(SystemExit, match=r"refused \(before any response is parsed, nothing written\)"):
        pe_run.main(Namespace(fixture=False, out=str(tmp_path / "o"), handoff=str(bundle), handoff_root="0" * 64,
                              handoff_runtime=None))
    # refused by the bundle's own checks, after its code started reading responses: no claim that none was read
    p = runtime / "coverage-report.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "outcomes_joined": True}))
    with pytest.raises(SystemExit, match=r"refused \(nothing reported, nothing written\): the bundle's handoff"):
        pe_run.main(Namespace(fixture=False, out=str(tmp_path / "o"), handoff=str(bundle), handoff_root=root,
                              handoff_runtime=str(runtime)))
    with pytest.raises(SystemExit, match="alternatives"):
        pe_run.main(Namespace(fixture=True, out=None, handoff=str(bundle), handoff_root=root, handoff_runtime=None))
    with pytest.raises(SystemExit, match="need --handoff"):
        pe_run.main(Namespace(fixture=False, out=None, handoff=None, handoff_root=root, handoff_runtime=None))
    assert not (tmp_path / "o").exists()


def test_the_cli_has_the_options():
    out = subprocess.run([sys.executable, "-c", "import sys; from markets.cli import main; main(sys.argv[1:])",
                          "price-engine", "--help"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    for flag in ("--handoff BUNDLE", "--handoff-root SHA256", "--handoff-runtime DIR", "--fixture"):
        assert flag in out.stdout


def test_nothing_is_read_until_amendment_2_registers_a_root(made, monkeypatch, tmp_path):
    cfg, calls, cache, scores, bundle, runtime, root = made
    _no_import(monkeypatch)
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", None)       # as merged: the hub fills it in at registration
    with pytest.raises(handoff.HandoffRefused, match="amendment 2 is not registered"):
        load(bundle, root, cfg)
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    with pytest.raises(SystemExit, match=r"refused \(before any response is parsed, nothing written\): amendment 2 is "
                                         "not registered"):
        pe_run.main(Namespace(fixture=False, out=str(tmp_path / "o"), handoff=str(bundle), handoff_root=root,
                              handoff_runtime=None))
    assert not (tmp_path / "o").exists()


def test_the_registered_root_is_unset_until_the_hub_registers_amendment_2():
    # the file as committed (tests monkeypatch the attribute): the hub sets it when it registers amendment 2, and then
    # updates this test with it
    assert "\nREGISTERED_ROOT: str | None = None\n" in Path(handoff.__file__).read_text()


def _evil_package(where: Path, name: str, marker: Path) -> Path:
    (where / name).mkdir(parents=True)
    (where / name / "__init__.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\ndef verify(*a, **k): return {{}}\n")
    return where / name


@pytest.mark.parametrize("kind", ["dir_package", "dir_shadowing_pyarrow", "dir_in_reuse", "file_same_bytes",
                                  "file_extra"])
def test_a_symbolic_link_anywhere_in_the_bundle_is_refused_before_any_code_runs(made, monkeypatch, tmp_path, kind):
    """A linked folder is not descended by a glob and a linked file hashes as its target; both are refused outright."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    marker, evil = tmp_path / "MARKER", tmp_path / "evil"
    if kind == "dir_package":           # a package named like a bundle module wins over validator.py on sys.path
        os.symlink(_evil_package(evil, "validator", marker), bundle / "validator", target_is_directory=True)
    elif kind == "dir_shadowing_pyarrow":
        os.symlink(_evil_package(evil, "pyarrow", marker), bundle / "pyarrow", target_is_directory=True)
    elif kind == "dir_in_reuse":
        os.symlink(_evil_package(evil, "more", marker), bundle / "reuse" / "more", target_is_directory=True)
    elif kind == "file_same_bytes":     # the hash matches, since reading follows the link; still refused
        evil.mkdir()
        shutil.copyfile(bundle / "validator.py", evil / "validator.py")
        (bundle / "validator.py").unlink()
        os.symlink(evil / "validator.py", bundle / "validator.py")
    else:
        evil.mkdir()
        (evil / "x.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
        os.symlink(evil / "x.py", bundle / "sitecustomize.py")
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="symbolic link"):
        load(bundle, root, cfg)
    with pytest.raises(handoff.HandoffRefused, match="symbolic link"):
        handoff.verify_frozen(bundle, root)
    assert not marker.exists()


def test_an_entry_that_is_not_a_regular_file_or_folder_is_refused(made, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs here")
    os.mkfifo(bundle / "reuse" / "pipe")
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="not a regular file or a folder"):
        load(bundle, root, cfg)


def test_a_freeze_certificate_below_the_top_level_is_refused(made, monkeypatch):
    """The validator leaves every FREEZE.json out of its hash map, so a nested one would be an unhashed file."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    (bundle / "reuse" / "FREEZE.json").write_text("{}")
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="FREEZE.json below its top level"):
        load(bundle, root, cfg)


def test_a_frozen_package_in_the_bundle_cannot_shadow_pyarrow_or_the_standard_library(made, monkeypatch, tmp_path):
    """Even frozen into FREEZE.json (so the root covers them), a bundle's `pyarrow/` and `json.py` are never imported:
    only the bundle modules the handoff needs are served, and everything else resolves as it would without it."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    import pyarrow
    import pyarrow.parquet
    marker = tmp_path / "MARKER"
    _evil_package(bundle, "pyarrow", marker)
    (bundle / "pyarrow" / "parquet.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    (bundle / "json.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    root = refreeze(bundle, runtime, monkeypatch)
    before = {k: sys.modules[k] for k in ("pyarrow", "pyarrow.parquet", "json")}
    hcalls, hcache, info = load(bundle, root, cfg)
    assert info["calls"] == len(calls) and not marker.exists()
    assert all(sys.modules[k] is v for k, v in before.items())
    assert not Path(pyarrow.parquet.__file__).is_relative_to(bundle)


def test_a_bundle_module_missing_from_the_frozen_set_is_not_found_elsewhere(made, monkeypatch, tmp_path):
    """The real validator imports builder. A `builder` on sys.path outside the bundle is never used for it."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    marker, elsewhere = tmp_path / "MARKER", tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "builder.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    monkeypatch.syspath_prepend(str(elsewhere))
    p = bundle / "validator.py"
    p.write_text(p.read_text().replace("import hashlib, json", "import hashlib, json\nimport builder"))
    root = refreeze(bundle, runtime, monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="ModuleNotFoundError: builder.py is not in the frozen bundle"):
        load(bundle, root, cfg)
    assert not marker.exists() and "builder" not in sys.modules


def test_a_file_swapped_after_the_check_is_never_run(made, monkeypatch, tmp_path):
    """The bundle's modules run from the bytes that were hashed, not from the folder, so a swap between the check
    and the import runs nothing (and the re-check afterwards refuses the run)."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    marker, real = tmp_path / "MARKER", handoff._verify

    def check_then_swap(b, r):
        out = real(b, r)
        (bundle / "cache_handoff.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
        return out
    monkeypatch.setattr(handoff, "_verify", check_then_swap)
    # the frozen cache_handoff.py ran (its validator then saw the swap); the swapped-in file did not
    with pytest.raises(handoff.HandoffRefused, match="the bundle's handoff refused: ValueError: Frozen file set"):
        load(bundle, root, cfg)
    assert not marker.exists()


@pytest.mark.parametrize("target", ["protocol.json", "../" + RUNTIME + "/spending-ledger.json"])
def test_a_write_by_the_bundles_code_is_caught_by_the_recheck(made, monkeypatch, target):
    """A stand-in validator that passes its own check and then appends one byte to a bundle file (or to the
    runtime's spending ledger): the check after the bundle's code has run refuses the run."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    p = bundle / "validator.py"
    p.write_text(p.read_text() + f"""
_verify = verify
def verify(folder, expected_root=None, check_cache=False):
    out = _verify(folder, expected_root, check_cache)
    p = Path(folder) / {target!r}
    p.write_bytes(p.read_bytes() + b" ")
    return out
""")
    root = refreeze(bundle, runtime, monkeypatch)
    match = "differ from its FREEZE.json: changed 1" if target == "protocol.json" else "spending-ledger.json changed"
    with pytest.raises(handoff.HandoffRefused, match=match) as refused:
        load(bundle, root, cfg)
    assert not refused.value.before_read          # the same check as before the code ran, but after it


def test_a_missing_spending_ledger_is_refused_before_any_code_runs(made, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    (runtime / "spending-ledger.json").unlink()
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="no readable spending-ledger.json") as refused:
        load(bundle, root, cfg)
    assert refused.value.before_read


def test_the_command_refuses_a_response_changed_after_loading(made, tmp_path, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    real_run = pe_run.run

    def tamper_then_run(c, k, h):
        p = h.lookup(k[-1].cache_sport, k[-1].source, k[-1].key)
        p.write_bytes(p.read_bytes() + b"x")
        return real_run(c, k, h, scores=scores)
    monkeypatch.setattr(pe_run, "run", tamper_then_run)
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match=r"refused \(nothing reported, nothing written\): a response changed after"):
        pe_run.main(Namespace(fixture=False, out=str(out), handoff=str(bundle), handoff_root=root,
                              handoff_runtime=str(runtime)))
    assert not out.exists()


def test_a_response_deleted_after_loading_is_refused_on_lookup(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, _ = load(bundle, root, cfg)
    hcache.lookup(hcalls[-1].cache_sport, hcalls[-1].source, hcalls[-1].key).unlink()
    with pytest.raises(handoff.HandoffRefused, match="could not be read after the handoff was loaded "
                                                     r"\(FileNotFoundError") as refused:
        pe_run.run(cfg, hcalls, hcache, scores=scores)
    assert not refused.value.before_read


# Each changes one route of the import system from the bundle's frozen validator, while its code loads.
IMPORT_CHANGES = {
    "path": "import sys\nsys.path.insert(0, str(Path(__file__).parent))\n",     # what executor.vendor_imports does
    "meta_path": ("import sys, importlib.abc\nclass _Finder(importlib.abc.MetaPathFinder):\n"
                  "    def find_spec(self, *a, **k): return None\nsys.meta_path.append(_Finder())\n"),
    "path_hooks": "import sys\nsys.path_hooks.insert(0, lambda p: (_ for _ in ()).throw(ImportError()))\n",
    "path_importer_cache": ("import sys, importlib.abc\nclass _Finder(importlib.abc.PathEntryFinder):\n"
                            "    def find_spec(self, *a, **k): return None\n"
                            "sys.path_importer_cache[str(Path(__file__).parent)] = _Finder()\n"),
}


@pytest.mark.parametrize("route", list(IMPORT_CHANGES))
def test_a_change_to_the_import_system_by_the_bundles_code_is_refused_and_put_back(made, monkeypatch, tmp_path, route):
    """A frozen module that leaves an import route behind (the reviewer's case: the bundle folder inserted at the
    front of sys.path, as the real executor.vendor_imports does) is refused, and the route is put back, so a file
    swapped into the folder afterwards is never imported."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    p = bundle / "validator.py"
    p.write_text(p.read_text() + IMPORT_CHANGES[route])
    root = refreeze(bundle, runtime, monkeypatch)
    before = {k: (getattr(sys, k), list(getattr(sys, k)) if k != "path_importer_cache" else dict(getattr(sys, k)))
              for k in IMPORT_CHANGES}
    with pytest.raises(handoff.HandoffRefused, match=rf"changed the import system \(sys\.{route}[,;)]") as refused:
        load(bundle, root, cfg)
    assert not refused.value.before_read
    for k, (obj, held) in before.items():
        now = getattr(sys, k)
        assert now is obj
        if k == "path_importer_cache":
            assert all(now.get(key, "missing") is v for key, v in held.items())
        else:
            assert len(now) == len(held) and all(a is b for a, b in zip(now, held))
    assert str(bundle) not in sys.path and handoff._FrozenFinder not in map(type, sys.meta_path)
    marker = tmp_path / "MARKER"
    (bundle / "swapped_in.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    with pytest.raises(ModuleNotFoundError):
        __import__("swapped_in")
    assert not marker.exists() and "swapped_in" not in sys.modules


def test_a_name_that_is_not_valid_utf8_is_refused(made, monkeypatch):
    """A FREEZE.json can list a file name that is not valid UTF-8 (by its surrogate escape); no root can cover it."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    raw = os.fsencode(bundle / "reuse") + b"/bad\xff.json"
    try:
        with open(raw, "wb") as f:
            f.write(b"{}")
    except OSError:
        pytest.skip("this file system refuses names that are not valid UTF-8")
    name = "reuse/" + os.fsdecode(b"bad\xff.json")
    cert = json.loads((bundle / "FREEZE.json").read_text())
    cert["file_sha256"][name] = hashlib.sha256(b"{}").hexdigest()
    (bundle / "FREEZE.json").write_text(json.dumps(cert))         # ensure_ascii: the lone surrogate as \\udcff
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="not valid UTF-8") as refused:
        load(bundle, root, cfg)
    assert refused.value.before_read



def _with_validator_code(made, monkeypatch, code: str, files: dict | None = None):
    """The made-up bundle with `code` appended to its frozen validator (and `files` added), re-frozen and registered."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    p = bundle / "validator.py"
    p.write_text(p.read_text() + code)
    for name, text in (files or {}).items():
        (bundle / name).parent.mkdir(parents=True, exist_ok=True)
        (bundle / name).write_text(text)
    return cfg, bundle, refreeze(bundle, runtime, monkeypatch)


# Each imports a module from a file in the bundle folder, other than through the handoff's frozen loader, and leaves
# sys.path as it found it (the reviewer's probe A, and two variants).
TEMPORARY_IMPORTS = {
    "folder": ("import sys\n_b = str(Path(__file__).parent)\nsys.path.insert(0, _b)\nimport helper_mod\n"
               "sys.path.remove(_b)\n", "helper_mod.py"),
    "subfolder": ("import sys\n_b = str(Path(__file__).parent / 'lib')\nsys.path.insert(0, _b)\nimport helper_mod\n"
                  "sys.path.remove(_b)\n", "lib/helper_mod.py"),
    "by_file": ("import sys, importlib.util\n"
                "_s = importlib.util.spec_from_file_location('helper_mod', Path(__file__).parent / 'helper_mod.py')\n"
                "_m = importlib.util.module_from_spec(_s)\nsys.modules['helper_mod'] = _m\n_s.loader.exec_module(_m)\n",
                "helper_mod.py"),
}


@pytest.mark.parametrize("how", list(TEMPORARY_IMPORTS))
def test_a_module_imported_from_the_bundle_folder_for_a_moment_is_refused(made, monkeypatch, how):
    """The folder put on sys.path only while one import runs leaves sys.path as it was, but the import searched the
    folder (a path_importer_cache entry for it) and ran a file from disk rather than from the hashed bytes."""
    code, name = TEMPORARY_IMPORTS[how]
    cfg, bundle, root = _with_validator_code(made, monkeypatch, code, {name: "X = 1\n"})
    cache_before = dict(sys.path_importer_cache)
    match = "an entry for the bundle folder" if how != "by_file" else r"sys\.modules, helper_mod loaded from the bundle"
    with pytest.raises(handoff.HandoffRefused, match=match) as refused:
        load(bundle, root, cfg)
    assert "helper_mod loaded from the bundle folder" in str(refused.value) and not refused.value.before_read
    assert "helper_mod" not in sys.modules
    assert not [k for k in sys.path_importer_cache if handoff._under(k, bundle)]
    assert all(sys.path_importer_cache.get(k, "missing") is v for k, v in cache_before.items())


def test_the_bundles_frozen_modules_still_load_through_the_checks(made, monkeypatch):
    """The modules the handoff serves are run by its frozen loader, so the check on sys.modules passes them."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    ran, real = [], handoff._FrozenLoader.exec_module

    def spy(self, module):
        ran.append(module.__name__)
        return real(self, module)
    monkeypatch.setattr(handoff._FrozenLoader, "exec_module", spy)
    hcalls, hcache, info = load(bundle, root, cfg)
    assert sorted(ran) == ["cache_handoff", "executor", "validator"] and info["calls"] == len(calls)


def test_a_replaced_import_function_is_refused_and_put_back(made, monkeypatch):
    import builtins
    before = builtins.__import__
    cfg, bundle, root = _with_validator_code(made, monkeypatch, (
        "import builtins\n_o = builtins.__import__\n"
        "def _imp(*a, **k): return _o(*a, **k)\nbuiltins.__import__ = _imp\n"))
    with pytest.raises(handoff.HandoffRefused, match=r"import system \(builtins\.__import__\)"):
        load(bundle, root, cfg)
    assert builtins.__import__ is before


def test_a_file_finder_pointed_at_the_bundle_folder_is_refused_and_put_back(made, monkeypatch, tmp_path):
    """The reviewer's probe B: a FileFinder already in sys.path_importer_cache, for a folder on sys.path, made to
    look in the bundle folder, so a file swapped in after the check would be imported later."""
    target = next(k for k, v in sys.path_importer_cache.items()
                  if type(v) is importlib.machinery.FileFinder and k in sys.path)
    finder, path = sys.path_importer_cache[target], sys.path_importer_cache[target].path
    cfg, bundle, root = _with_validator_code(made, monkeypatch, (
        f"import sys\n_f = sys.path_importer_cache[{target!r}]\n_f.path = str(Path(__file__).parent)\n"
        "_f.invalidate_caches()\n"))
    with pytest.raises(handoff.HandoffRefused, match="the folder of a FileFinder"):
        load(bundle, root, cfg)
    assert sys.path_importer_cache[target] is finder and finder.path == path
    marker = tmp_path / "MARKER"
    (bundle / "swapped_later.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n")
    with pytest.raises(ModuleNotFoundError):
        __import__("swapped_later")
    assert not marker.exists()


def test_a_thread_left_running_by_the_bundles_code_is_refused(made, monkeypatch):
    import threading
    before = set(threading.enumerate())
    cfg, bundle, root = _with_validator_code(made, monkeypatch, (
        "import threading, time\n"
        "threading.Thread(target=time.sleep, args=(0.5,), name='bundle-thread', daemon=True).start()\n"))
    try:
        with pytest.raises(handoff.HandoffRefused, match=r"left 1 thread\(s\) running \(bundle-thread\)"):
            load(bundle, root, cfg)
    finally:
        for t in set(threading.enumerate()) - before:
            t.join(5)


def test_an_exit_by_the_bundles_code_is_a_refusal_and_an_interrupt_is_not(made, monkeypatch):
    cfg, bundle, root = _with_validator_code(made, monkeypatch, "raise SystemExit('bundle says bye')\n")
    with pytest.raises(handoff.HandoffRefused, match="the bundle's handoff refused: SystemExit: bundle says bye") as r:
        load(bundle, root, cfg)
    assert not r.value.before_read
    p = bundle / "validator.py"
    p.write_text(p.read_text().replace("raise SystemExit('bundle says bye')", "raise KeyboardInterrupt"))
    root = refreeze(bundle, made[5], monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        load(bundle, root, cfg)
    assert not [k for k in sys.modules if k in ("validator", "executor", "cache_handoff")]


def test_a_deleted_import_route_is_refused_and_everything_is_put_back(made, monkeypatch):
    """The reviewer's probe E: `del sys.path_hooks` broke the restore, leaving the bundle's modules loaded."""
    hooks, meta = sys.path_hooks, list(sys.meta_path)
    cfg, bundle, root = _with_validator_code(made, monkeypatch, "import sys\ndel sys.path_hooks\n")
    sys.modules["validator"] = marker = type(sys)("validator")      # an unrelated module of the same name, set aside
    try:
        with pytest.raises(handoff.HandoffRefused, match=r"import system \(sys\.path_hooks, deleted\)"):
            load(bundle, root, cfg)
        assert sys.path_hooks is hooks and sys.modules["validator"] is marker
    finally:
        sys.modules.pop("validator", None)
        if not hasattr(sys, "path_hooks"):
            sys.path_hooks = hooks
    assert not [k for k in sys.modules if k in ("executor", "cache_handoff")]
    assert len(sys.meta_path) == len(meta) and all(a is b for a, b in zip(sys.meta_path, meta))


def test_invalidating_the_import_caches_is_not_a_change(made, monkeypatch):
    """importlib.invalidate_caches() deletes the None and relative-path entries of sys.path_importer_cache; Python
    makes them again when needed, so that is not refused, and they are put back."""
    monkeypatch.setitem(sys.path_importer_cache, "/no/such/folder/for/the/handoff/test", None)
    monkeypatch.setitem(sys.path_importer_cache, "relative-folder-for-the-handoff-test", None)
    cfg, bundle, root = _with_validator_code(made, monkeypatch, "import importlib\nimportlib.invalidate_caches()\n")
    load(bundle, root, cfg)
    assert sys.path_importer_cache["/no/such/folder/for/the/handoff/test"] is None
    assert sys.path_importer_cache["relative-folder-for-the-handoff-test"] is None


def test_an_import_change_during_a_failed_check_names_both(made, monkeypatch):
    cfg, bundle, root = _with_validator_code(made, monkeypatch, (
        "import sys\nsys.path.insert(0, str(Path(__file__).parent))\nraise ValueError('the bundle check failed')\n"))
    with pytest.raises(handoff.HandoffRefused, match=r"import system \(sys\.path[;)].*the run had already been "
                                                     r"refused \(the bundle's handoff refused: ValueError: the bundle "
                                                     r"check failed\)"):
        load(bundle, root, cfg)
    assert str(bundle) not in sys.path


@pytest.mark.parametrize("how", ["chmod", "scandir", "read"])
def test_a_folder_or_file_that_cannot_be_listed_or_read_is_refused_before_any_code_runs(made, monkeypatch, how):
    import errno
    cfg, calls, cache, scores, bundle, runtime, root = made
    reuse = bundle / "reuse"
    if how == "chmod":
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("running as root, a folder's permissions do not stop it being listed")
        os.chmod(reuse, 0)
    elif how == "scandir":
        real = os.scandir

        def scandir(path="."):
            if Path(path).name == "reuse":
                raise PermissionError(errno.EACCES, "Permission denied", str(path))
            return real(path)
        monkeypatch.setattr(handoff.os, "scandir", scandir)
    else:
        def fdopen(*a, **k):
            raise OSError(errno.EIO, "Input/output error")
        monkeypatch.setattr(handoff.os, "fdopen", fdopen)
    _no_import(monkeypatch)
    try:
        with pytest.raises(handoff.HandoffRefused, match="cannot list" if how != "read" else "cannot read .*EIO|"
                           "cannot read .*Input/output error") as refused:
            load(bundle, root, cfg)
    finally:
        os.chmod(reuse, 0o755)
    assert refused.value.before_read


# ---------------------------------------------------------------- accepted_missing (PR 99's refreeze at 6112d70)
# The decision slot at 02:30 UTC (an extra call), accepted as missing for snapshot lag with its rejected HTTP 200 left
# in the runtime's raw cache, and a college close, accepted as missing for an HTTP 5xx with no response saved.
MISSING = {36: "snapshot_lag", 24: "http_5xx"}


@pytest.fixture
def made_missing(fx, tmp_path, monkeypatch):
    cfg, calls, cache, scores = fx
    assert calls[36].at == fixture.t("2024-09-08T02:30:00Z") and calls[24].sport == CFB
    bundle, runtime, root = make_bundle(tmp_path, calls, cache, missing=MISSING)
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", root)
    return cfg, calls, cache, scores, bundle, runtime, root


def _no_fetch(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a request was sent")
    monkeypatch.setattr(bulk.BulkClient, "_get", refuse)
    monkeypatch.setattr(bulk.BulkClient, "fetch", refuse)


def test_an_accepted_missing_call_is_absent_data_counted_and_never_fetched(made_missing, monkeypatch):
    """Each call keeps its manifest position; the lookup gives nothing for the missing ones (the saved 200 that the
    bundle's run rejected for lag is in the runtime's raw cache at the call's path, and is still not read), so the
    run is the same as handing in the calls without them."""
    cfg, calls, cache, scores, bundle, runtime, root = made_missing
    _no_fetch(monkeypatch)
    hcalls, hcache, info = load(bundle, root, cfg)
    assert [c.key for c in hcalls] == [c.key for c in calls]
    assert info["calls"] == len(calls) and info["reused"] == REUSED and info["accepted_missing"] == 2
    assert info["accepted_missing_reasons"] == {"http_5xx": 1, "snapshot_lag": 1}
    rows = json.loads((bundle / "request-manifest.json").read_text())["requests"]
    assert info["accepted_missing_requests"] == [
        {"request_id": rows[i]["request_id"], "reason": MISSING[i], "cache_key": calls[i].key} for i in sorted(MISSING)]
    for i in MISSING:
        assert hcache.lookup(hcalls[i].cache_sport, hcalls[i].source, hcalls[i].key) is None
    saved = [a["response_path"] for a in json.loads((runtime / "spending-ledger.json").read_text())["attempts"].values()
             if a["status"] == "missing"]
    assert sorted(map(bool, saved)) == [False, True] and Path(next(filter(None, saved))).is_file()
    via = pe_run.run(cfg, hcalls, hcache, scores=scores)
    minus = pe_run.run(cfg, [c for i, c in enumerate(calls) if i not in MISSING], cache, scores=scores)
    full = pe_run.run(cfg, calls, cache, scores=scores)
    pd.testing.assert_frame_equal(via["quotes"], minus["quotes"])
    assert via["drops"] == minus["drops"] and via["calls"] == len(calls)
    pd.testing.assert_frame_equal(via["results"], minus["results"])
    for v in minus["graded"]:
        pd.testing.assert_frame_equal(via["graded"][v], minus["graded"][v])
    # and the missing calls mattered: their snapshots are in the full run's quotes, and in none of the handoff's
    gone = {pd.Timestamp(calls[i].at) for i in MISSING}
    assert gone <= set(full["quotes"].snap) and not gone & set(via["quotes"].snap)


def test_the_command_counts_the_accepted_missing_calls(made_missing, tmp_path, monkeypatch, capsys):
    cfg, calls, cache, scores, bundle, runtime, root = made_missing
    _no_fetch(monkeypatch)
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    real_run = pe_run.run
    monkeypatch.setattr(pe_run, "run", lambda c, k, h: real_run(c, k, h, scores=scores))
    out = tmp_path / "out"
    assert pe_run.main(Namespace(fixture=False, out=str(out), handoff=str(bundle), handoff_root=root,
                                 handoff_runtime=str(runtime))) == 0
    line = ("2 accepted as missing by the bundle's run (absent data: no response, no row read, never fetched; by "
            "reason: http_5xx 1, snapshot_lag 1)")
    printed, report = capsys.readouterr().out, (out / "report.md").read_text()
    assert line in printed and line in report
    # report.md lists each one by the manifest's request_id, for the hub to match against its approvals; the
    # command's own line stays short and points there
    rows = json.loads((bundle / "request-manifest.json").read_text())["requests"]
    for i in MISSING:
        rid = rows[i]["request_id"]
        assert f"- `{rid}`: {MISSING[i]}, cache key `{calls[i].key}`" in report and rid not in printed
    assert f"{line}; request ids in report.md (amendment 2)" in printed
    real_run(cfg, [c for i, c in enumerate(calls) if i not in MISSING], cache,
             scores=scores)["results"].to_csv(tmp_path / "minus.csv", index=False)
    assert (out / "results.csv").read_bytes() == (tmp_path / "minus.csv").read_bytes()


def test_no_response_for_a_call_not_marked_accepted_missing_is_refused(made):
    """With every call bought, a lookup that comes back empty is not quietly a missing call: it refuses the run."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, info = load(bundle, root, cfg)
    assert info["accepted_missing"] == 0
    c = hcalls[-1]
    del hcache._cache.index[(c.cache_sport, c.source, c.key)]      # the bundle's cache loses one response
    with pytest.raises(handoff.HandoffRefused, match="gave no response for .* which it does not mark accepted_missing"):
        pe_run.run(cfg, hcalls, hcache, scores=scores)


def test_a_response_for_a_call_marked_accepted_missing_is_refused(made_missing):
    cfg, calls, cache, scores, bundle, runtime, root = made_missing
    hcalls, hcache, _ = load(bundle, root, cfg)
    c = hcalls[36]
    path = cache.lookup(c.cache_sport, c.source, c.key)
    hcache._cache.index[(c.cache_sport, c.source, c.key)] = {"response_path": str(path), "response_sha256": _sha(path)}
    with pytest.raises(handoff.HandoffRefused, match="marks .* accepted_missing, yet its cache gave a response"):
        pe_run.run(cfg, hcalls, hcache, scores=scores)


@pytest.mark.parametrize("change", ["receipt", "source"])
def test_the_bundles_own_checks_refuse_a_changed_missing_record(made_missing, change):
    cfg, calls, cache, scores, bundle, runtime, root = made_missing
    rows = json.loads((bundle / "request-manifest.json").read_text())["requests"]
    rid = next(r["request_id"] for r in rows if r["cache_key"] == calls[36].key)       # the one with a saved source
    attempt = json.loads((runtime / "spending-ledger.json").read_text())["attempts"][rid]
    p = runtime / "receipts" / f"{rid}.json" if change == "receipt" else Path(attempt["response_path"])
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(handoff.HandoffRefused, match=f"Changed missing {change}"):
        load(bundle, root, cfg)


def test_an_entry_marked_missing_that_names_a_response_is_refused(made_missing, monkeypatch):
    """The engine's own check on the handoff: accepted_missing means no response path and no hash."""
    cfg, calls, cache, scores, bundle, runtime, root = made_missing
    p = bundle / "cache_handoff.py"
    p.write_text(p.read_text() + (
        "\n_build = build_handoff\ndef build_handoff(*a):\n    h = _build(*a)\n"
        "    for e in h['entries']:\n        if e.get('status') == 'accepted_missing': e['response_path'] = 'x'\n"
        "    return h\n"))
    root = refreeze(bundle, runtime, monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="neither a response with its path nor accepted_missing"):
        load(bundle, root, cfg)


BAD_REASONS = ["http_5xx\n- `forged`: http_404", "http_404 ", "http_418", "", None, 404]


def test_the_missing_reasons_are_the_ones_the_bundles_executor_can_record():
    """executor.accept_as_missing at 6112d70 records http_404 (a saved 404), snapshot_lag (a lagged HTTP 200) or
    http_5xx (an observed 5xx), and halts on any other."""
    assert handoff.MISSING_REASONS == ("http_404", "http_5xx", "snapshot_lag")


@pytest.mark.parametrize("reason", BAD_REASONS)
def test_an_accepted_missing_reason_the_executor_cannot_record_is_refused(fx, tmp_path, monkeypatch, reason):
    """A reason with a newline (which would add a line to report.md) or any value outside the executor's three stops
    the run before anything is reported or written."""
    cfg, calls, cache, scores = fx
    bundle, runtime, root = make_bundle(tmp_path, calls, cache, missing={24: reason})
    monkeypatch.setattr(handoff, "REGISTERED_ROOT", root)
    with pytest.raises(handoff.HandoffRefused, match="accepted_missing reason the bundle's executor cannot record"):
        load(bundle, root, cfg)
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match=r"nothing reported, nothing written\): .*cannot record"):
        pe_run.main(Namespace(fixture=False, out=str(out), handoff=str(bundle), handoff_root=root,
                              handoff_runtime=str(runtime)))
    assert not out.exists()


@pytest.mark.parametrize("reason", BAD_REASONS)
def test_the_output_line_and_the_report_refuse_a_reason_the_executor_cannot_record(made_missing, monkeypatch,
                                                                                  tmp_path, reason):
    """The same check wherever the reason is printed: the command's output line (`_missing_line`) and report.md's
    list by request id, even for an `info` that did not come from `handoff.load`."""
    cfg, calls, cache, scores, bundle, runtime, root = made_missing
    _, _, info = load(bundle, root, cfg)
    counted = {**info, "accepted_missing_reasons": {**info["accepted_missing_reasons"], reason: 1}}
    with pytest.raises(handoff.HandoffRefused, match="cannot record"):
        pe_run._missing_line(counted)
    listed = {**info, "accepted_missing_requests": [*info["accepted_missing_requests"][:1],
                                                    {**info["accepted_missing_requests"][1], "reason": reason}]}
    res = pe_run.run(cfg, [c for i, c in enumerate(calls) if i not in MISSING], cache, scores=scores)
    pe_run.report({**res, "handoff": info}, res["results"], fixture=False)          # the real info reports
    with pytest.raises(handoff.HandoffRefused, match="cannot record"):
        pe_run.report({**res, "handoff": listed}, res["results"], fixture=False)
    real_load = handoff.load
    monkeypatch.setattr(handoff, "load", lambda *a: (*real_load(*a)[:2], counted))
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match="cannot record"):
        pe_run.main(Namespace(fixture=False, out=str(out), handoff=str(bundle), handoff_root=root,
                              handoff_runtime=str(runtime)))
    assert not out.exists()


def test_the_runtime_defaults_to_the_executors_fixed_folder(made, monkeypatch, tmp_path):
    """--handoff-runtime defaults to ~/Library/Application Support/ValueFinder/football-acquisition-state/<root>, the
    v4 executor's runtime for that root (`~` expanded)."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    fixed = home / "Library" / "Application Support" / "ValueFinder" / "football-acquisition-state" / root
    assert handoff.default_runtime(root) == fixed
    shutil.copytree(runtime, fixed)
    for f in ("spending-ledger.json", "coverage-report.json"):
        (runtime / f).unlink()                  # only the fixed folder can serve them now
    hcalls, hcache, info = handoff.load(bundle, root, cfg)
    assert info["runtime"] == str(fixed.resolve()) and len(hcalls) == len(calls)
    assert info["spending_ledger_sha256"] == _sha(fixed / "spending-ledger.json")
    with pytest.raises(handoff.HandoffRefused, match="no readable spending-ledger.json"):
        handoff.load(bundle, root, cfg, runtime)       # the explicit folder still wins


@pytest.mark.parametrize("how", ["no such user", "no home"])
def test_a_runtime_folder_whose_home_cannot_be_found_is_refused_before_any_code_runs(made, monkeypatch, tmp_path, how):
    """`~nosuchuser/...` given, or the default folder with no home folder to expand `~` to: a HandoffRefused before
    any of the bundle's code runs, not a bare RuntimeError."""
    cfg, calls, cache, scores, bundle, runtime, root = made
    _no_import(monkeypatch)
    if how == "no such user":
        given = "~no-such-user-value-finder-test/x"
    else:
        import pwd

        def no_entry(*_a):
            raise KeyError("no passwd entry")
        monkeypatch.delenv("HOME", raising=False)
        monkeypatch.setattr(pwd, "getpwuid", no_entry)
        given = None
        with pytest.raises(handoff.HandoffRefused, match="cannot expand ~"):
            handoff.default_runtime(root)
    with pytest.raises(handoff.HandoffRefused, match="cannot expand ~") as refused:
        handoff.load(bundle, root, cfg, given)
    assert refused.value.before_read
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    with pytest.raises(SystemExit, match=r"refused \(before any response is parsed, nothing written\): cannot expand"):
        pe_run.main(Namespace(fixture=False, out=str(tmp_path / "o"), handoff=str(bundle), handoff_root=root,
                              handoff_runtime=given))
    assert not (tmp_path / "o").exists()


@pytest.mark.parametrize("root", ["", "0" * 63, "0" * 65, "A" * 64, "../" + "0" * 61, "0" * 64 + "/x", None])
def test_the_default_runtime_refuses_a_root_that_is_not_a_sha256(root):
    with pytest.raises(handoff.HandoffRefused, match="64-character sha256 root"):
        handoff.default_runtime(root)
    assert handoff.default_runtime("0" * 64).name == "0" * 64
