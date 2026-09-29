"""The nightly copy to the ledgers branch (ops/sync_ledgers.sh) never loses a line of the published decision record
(nfl-weather amendment 7, cfb-weather amendment 5, section 3). The reviews of pull request 64 found that the copy
could lose one: a line lost from the live decisions.csv was published with the shortened file, the copy no longer
held it, and the next real run of the scorer decided it again. Now a decisions.csv replaces the published copy only
when it holds every line of that copy and starts with the same header line; otherwise the published copy is kept,
one line says which project's record was not published and why, and every other file is synced as usual.

Every test runs the script on a throwaway repository whose origin is a local bare repository, with HOME (and so
the script's own clone) inside tmp_path. Nothing outside tmp_path is read or written."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEADER = ("decision_id,rule,horizon,horizon_utc,decided_utc,n_bets,verdict,numbers,ledger_rows,"
          "ledger_rows_sha256\n")
A = 'RULE_B:2026,Rule B,after Week 18 of 2026,2027-01-10T18:00:00Z,2027-01-20T17:00:00Z,40,KEEP,"{""n"": 1}",1 2,aa\n'
B = 'MODEL_LEAN:2026,model lean,after Week 18 of 2026,2027-01-10T18:00:00Z,2027-01-21T17:00:00Z,40,DROP,"{}",3,bb\n'
C = ('MODEL_LEAN:2026-27,model lean,after the 2027 regular season,2028-01-09T18:00:00Z,2028-01-20T17:00:00Z,50,KEEP,'
     '"{}",4,cc\n')
NOT_PUBLISHED = "nfl-weather: decisions.csv not published ({}); the published copy is kept as it is"


class Sync:
    """A throwaway repository with ops/sync_ledgers.sh, its origin a local bare repository."""

    def __init__(self, tmp_path):
        self.repo, self.remote = tmp_path / "repo", tmp_path / "remote.git"
        self.env = dict(os.environ, HOME=str(tmp_path / "home"), GIT_CEILING_DIRECTORIES=str(tmp_path),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="t",
                        GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        self.git("init", "-q", "--bare", str(self.remote))
        (self.repo / "ops").mkdir(parents=True)
        shutil.copy(ROOT.parent / "ops" / "sync_ledgers.sh", self.repo / "ops")
        self.git("init", "-q", str(self.repo))
        self.git("-C", str(self.repo), "remote", "add", "origin", str(self.remote))
        self.night = 0

    def git(self, *a):
        return subprocess.run(["git", *a], check=True, capture_output=True, text=True, env=self.env).stdout

    def write(self, files):
        """files: {path under the repo: text, or None to remove it}."""
        for name, text in files.items():
            path = self.repo / name
            if text is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode())

    def run(self, files):
        """One night: every project's ledger changes, `files` are written, and the script runs. Returns its exit
        status and printout."""
        self.night += 1
        self.write({f"{p}/data/forward/ledger.csv": f"snapshot_utc\nnight {self.night}\n"
                    for p in ("nfl-weather", "cfb-weather")} | files)
        r = subprocess.run(["bash", str(self.repo / "ops" / "sync_ledgers.sh")], capture_output=True, text=True,
                           env=self.env)
        return r.returncode, r.stdout + r.stderr

    def published(self, name):
        """The file as the ledgers branch of the bare repository holds it, or None."""
        r = subprocess.run(["git", "--git-dir", str(self.remote), "show", f"ledgers:{name}"], capture_output=True,
                           env=self.env)
        return r.stdout.decode() if r.returncode == 0 else None


NFL, CFB = "nfl-weather/data/forward/decisions.csv", "cfb-weather/data/forward/decisions.csv"


def test_a_longer_record_is_published(tmp_path):
    s = Sync(tmp_path)
    code, out = s.run({NFL: HEADER + A})
    assert code == 0 and s.published("nfl-weather/decisions.csv") == HEADER + A            # the first copy
    code, out = s.run({NFL: HEADER + A + B})
    assert code == 0 and s.published("nfl-weather/decisions.csv") == HEADER + A + B
    assert "not published" not in out and s.published("nfl-weather/ledger.csv") == "snapshot_utc\nnight 2\n"


LOST = "it has lost or changed a line that the published copy holds"
CASES = {"shortened": (HEADER + B, LOST),
         "cut back to its header": (HEADER, LOST),
         "a line changed": (HEADER + A.replace("KEEP", "DROP") + B, LOST),
         "a line lost and another added": (HEADER + A + C, LOST),
         "missing": (None, "the file is missing"),
         "empty": ("", "the file is empty"),
         "damaged, no header": (A + B + C, "its first line is not the published copy's header"),
         "damaged, its last line cut": (HEADER + A + B + C[:40],
                                        "its last line is cut (the file does not end with a line break)")}


@pytest.mark.parametrize("case", CASES)
def test_a_record_that_lost_a_line_is_not_published_and_everything_else_is(tmp_path, case):
    text, why = CASES[case]
    s = Sync(tmp_path)
    assert s.run({NFL: HEADER + A + B, CFB: HEADER})[0] == 0
    assert s.published("nfl-weather/decisions.csv") == HEADER + A + B
    code, out = s.run({NFL: text, CFB: HEADER + A, "cfb-weather/data/forward/closes.csv": "game_id\n401\n"})
    assert code == 0, (case, out)                                          # the sync never fails over it
    assert s.published("nfl-weather/decisions.csv") == HEADER + A + B, case  # the published copy is kept as it is
    assert NOT_PUBLISHED.format(why) in out, (case, out)
    assert out.count("not published") == 1, case                           # one line, for that project only
    for p in ("nfl-weather", "cfb-weather"):                                # every other file is still synced
        assert s.published(f"{p}/ledger.csv") == "snapshot_utc\nnight 2\n", (case, p)
    assert s.published("cfb-weather/decisions.csv") == HEADER + A, case
    assert s.published("cfb-weather/closes.csv") == "game_id\n401\n", case
    if text is not None:
        assert (s.repo / NFL).read_bytes() == text.encode(), case           # the live file is left as it is
    code, out = s.run({NFL: HEADER + A + B + C})                           # repaired, with a new decision: published
    assert code == 0 and "not published" not in out, case
    assert s.published("nfl-weather/decisions.csv") == HEADER + A + B + C, case


def test_the_scorer_s_restore_lets_the_next_copy_publish_again(tmp_path):
    """The whole cycle: the file lost a line, so the copy was kept; the next real run of the scorer appends the
    copy's line back (section 3); the file then holds every published line again and is published, new lines too."""
    s = Sync(tmp_path)
    s.run({NFL: HEADER + A + B})
    assert "not published" in s.run({NFL: HEADER + B + C})[1]              # A lost, C recorded since: kept back
    assert s.published("nfl-weather/decisions.csv") == HEADER + A + B
    code, out = s.run({NFL: HEADER + B + C + A})                           # the scorer appended A from the copy
    assert code == 0 and "not published" not in out
    assert s.published("nfl-weather/decisions.csv") == HEADER + B + C + A
