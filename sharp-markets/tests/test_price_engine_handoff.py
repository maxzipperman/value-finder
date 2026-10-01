"""`markets price-engine --handoff`: F1 as pulled by the football archive bundle (issue #101; amendment 2, DRAFT).

Every bundle here is made up. Its responses are the engine's synthetic fixture (nothing in it is data), written by
main's RawCache, which the bundle vendors byte for byte; its `cache_handoff.py` is the frozen file from the bundle
(tests/frozen/football_archive_cache_handoff.py.frozen, checked against the bundle's FREEZE.json hash); its
validator and executor are small stand-ins with the checks the handoff relies on. No network, no key, no real
response, no 2026 data."""
import dataclasses
import hashlib
import json
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
FROZEN_SHA256 = "0692338c1eb02db7f542cf1bcda6bf76d9042fc11a16466bdd5c5d7349693cb0"   # FREEZE.json, v4 root 09c29ac0...
BRANCH_FILE = ("origin/research/football-archive-v4:strategy-research/football_archive/acquisition/"
               "football-archive-v4/cache_handoff.py")
REUSED = 12
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


def make_bundle(tmp: Path, calls: list, cache) -> tuple[Path, Path, str]:
    """A made-up frozen bundle and a completed runtime holding `calls`: the first REUSED in the bundle's reuse/,
    the rest as completed paid responses in the runtime's RawCache layout. Returns (bundle, runtime, root)."""
    bundle, runtime = tmp / "acquisition" / "football-archive-test", tmp / "acquisition" / handoff.RUNTIME_DEFAULT
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
        if i < REUSED:
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


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("handoff_fixture")
    cfg, calls, cache, scores = fixture.build(tmp)
    calls = calls + extra_calls(cache)
    return cfg, calls, cache, scores


@pytest.fixture
def made(fx, tmp_path):
    cfg, calls, cache, scores = fx
    bundle, runtime, root = make_bundle(tmp_path, calls, cache)
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
    hcalls, hcache, info = handoff.load(bundle, root, cfg)
    assert [c.key for c in hcalls] == [c.key for c in calls]
    assert info["calls"] == len(calls) and info["reused"] == REUSED and info["bundle_root_sha256"] == root
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
    hcalls, hcache, info = handoff.load(bundle, root, cfg)
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
    hcalls, hcache, _ = handoff.load(bundle, root, cfg)
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
    hcalls, hcache, _ = handoff.load(bundle, root, cfg)
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
    monkeypatch.setattr(handoff.importlib.util, "spec_from_file_location", refuse)


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
    with pytest.raises(handoff.HandoffRefused, match="differ from its FREEZE.json"):
        handoff.load(bundle, root, cfg)


def test_a_root_other_than_the_pinned_one_is_refused(made, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    _no_import(monkeypatch)
    with pytest.raises(handoff.HandoffRefused, match="not the pinned"):
        handoff.load(bundle, "0" * 64, cfg)
    for bad in (None, "", root[:63], root.upper()):
        with pytest.raises(handoff.HandoffRefused, match="64-character"):
            handoff.load(bundle, bad, cfg)
    # a FREEZE.json whose root is not its own hash map's
    cert = json.loads((bundle / "FREEZE.json").read_text())
    (bundle / "FREEZE.json").write_text(json.dumps({**cert, "bundle_root_sha256": "f" * 64}))
    with pytest.raises(handoff.HandoffRefused, match="not FREEZE.json's"):
        handoff.load(bundle, root, cfg)


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
    with pytest.raises(handoff.HandoffRefused, match="the bundle's handoff refused: ValueError"):
        handoff.load(bundle, root, cfg)


def test_a_changed_response_after_loading_is_refused_on_lookup(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    hcalls, hcache, _ = handoff.load(bundle, root, cfg)
    p = hcache.lookup(hcalls[-1].cache_sport, hcalls[-1].source, hcalls[-1].key)
    p.write_bytes(p.read_bytes() + b"x")
    with pytest.raises(ValueError, match="Changed response bytes"):
        pe_run.run(cfg, hcalls, hcache, scores=scores)


def test_nothing_is_written_into_the_bundle_and_nothing_of_it_stays_loaded(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    sys.modules["validator"] = marker = type(sys)("validator")      # an unrelated module of the same name
    path_before, flag_before = list(sys.path), sys.dont_write_bytecode
    try:
        handoff.load(bundle, root, cfg)
        assert sys.modules["validator"] is marker
    finally:
        sys.modules.pop("validator", None)
    assert sys.path == path_before and sys.dont_write_bytecode == flag_before
    assert not [k for k in sys.modules if k in ("executor", "cache_handoff")]
    assert not list(bundle.rglob("__pycache__")) and handoff.verify_frozen(bundle, root) == root
    assert socket.getaddrinfo is not handoff._no_network and socket.socket.connect is not handoff._no_network


def test_the_bundles_code_cannot_open_a_connection(made):
    cfg, calls, cache, scores, bundle, runtime, root = made
    p = bundle / "cache_handoff.py"
    p.write_text(p.read_text() + "\nimport socket\nsocket.create_connection(('127.0.0.1', 9))\n")
    root = freeze(bundle)
    for f in ("spending-ledger.json", "coverage-report.json"):
        v = json.loads((runtime / f).read_text())
        (runtime / f).write_text(json.dumps({**v, "bundle_root_sha256": root}))
    with pytest.raises(handoff.HandoffRefused, match="network"):
        handoff.load(bundle, root, cfg)


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
    assert f"Bundle root `{root}`" in report and "amendment 2, a DRAFT" in report
    real_run(cfg, calls, cache, scores=scores)["results"].to_csv(tmp_path / "direct.csv", index=False)
    assert (out / "results.csv").read_bytes() == (tmp_path / "direct.csv").read_bytes()


def test_the_command_refuses_a_bad_bundle_and_bad_flag_combinations(made, tmp_path, monkeypatch):
    cfg, calls, cache, scores, bundle, runtime, root = made
    monkeypatch.setattr(pe_run.bulk, "load_config", lambda: cfg)
    with pytest.raises(SystemExit, match=r"refused \(no price read"):
        pe_run.main(Namespace(fixture=False, out=str(tmp_path / "o"), handoff=str(bundle), handoff_root="0" * 64,
                              handoff_runtime=None))
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
