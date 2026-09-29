"""The nightly copy to the ledgers branch (ops/sync_ledgers.sh) never loses a line of the published decision record
(nfl-weather amendment 7, cfb-weather amendment 5, section 3). The reviews of pull request 64 found that the copy
could lose one: a line lost from the live decisions.csv was published with the shortened file, the copy no longer
held it, and the next real run of the scorer decided it again. Now a decisions.csv replaces the published copy only
when it holds every line of that copy and starts with the same header line; otherwise the published copy is kept,
one line says which project's record was not published and why, and every other file is synced as usual.

The third review of pull request 64 added three cases: the first copy was published unchecked (a cut or empty file
became the published copy); a damaged published copy was reported as if the live file were at fault; and while a
changed line holds the file back, a decision recorded since is not published either, which the amendments now state.

Every test runs the script on a throwaway repository whose origin is a local bare repository, with HOME (and so
the script's own clone) inside tmp_path. Nothing outside tmp_path is read or written, except reading the scorers
and the amendments."""
import ast
import os
import re
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

    def publish_by_hand(self, name, text):
        """A commit to the ledgers branch made outside the script (a hand repair gone wrong, say), from the script's
        own clone, so the next night's pull finds it."""
        clone = Path(self.env["HOME"]) / "code" / ".value-finder-ledgers"
        (clone / name).write_bytes(text.encode())
        self.git("-C", str(clone), "add", name)
        self.git("-C", str(clone), "commit", "-q", "-m", "by hand")
        self.git("-C", str(clone), "push", "-q", "origin", "ledgers")
        assert self.published(name) == text


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
         "damaged, no header": (A + B + C, "its first line is not the record's header"),
         "damaged, its last line cut": (HEADER + A + B + C[:40], "its last line is cut, with no line break at the end"),
         "re-saved with other line endings, and a line added": ((HEADER + A + B).replace("\n", "\r\n") + C, LOST)}


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


# ================================================================== the third review of pull request 64 (Sep 29)
def record_cols(project):
    """A scorer's RECORD_COLS, read from its source (the scorer runs on import, so it isn't imported)."""
    tree = ast.parse((ROOT.parent / project / "scripts" / "score_forward.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "RECORD_COLS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{project}'s scorer has no RECORD_COLS")


def test_the_nightly_copy_checks_the_header_the_scorers_write():
    script = (ROOT.parent / "ops" / "sync_ledgers.sh").read_text()
    header = re.search(r'^RECORD_HEADER="([^"]+)"$', script, re.M)[1]
    for project in ("nfl-weather", "cfb-weather"):
        assert ",".join(record_cols(project)) == header, project
    assert header + "\n" == HEADER


FIRST = {"cut": (HEADER + A[:40], "its last line is cut, with no line break at the end"),
         "empty": ("", "the file is empty"),
         "no header": (A, "its first line is not the record's header"),
         "another file's header": ("snapshot_utc\n" + A, "its first line is not the record's header")}


@pytest.mark.parametrize("case", FIRST)
def test_the_first_copy_is_checked_too(tmp_path, case):
    """The review's sync_guard: with nothing published yet, a cut or empty decisions.csv became the published copy,
    and a cut copy then stopped all recording until the hub repaired the ledgers branch by hand."""
    text, why = FIRST[case]
    s = Sync(tmp_path)
    code, out = s.run({NFL: text, CFB: HEADER + A})
    assert code == 0, (case, out)
    assert s.published("nfl-weather/decisions.csv") is None, case                  # nothing published for it
    assert f"nfl-weather: decisions.csv not published ({why}); nothing has been published for it yet" in out, case
    assert out.count("not published") == 1, case
    assert s.published("cfb-weather/decisions.csv") == HEADER + A, case             # everything else is synced
    assert s.published("nfl-weather/ledger.csv") == "snapshot_utc\nnight 1\n", case
    code, out = s.run({NFL: HEADER + A})                                          # repaired: published
    assert code == 0 and "not published" not in out and s.published("nfl-weather/decisions.csv") == HEADER + A


def test_no_record_yet_publishes_nothing_and_says_nothing(tmp_path):
    """Until the first decision (December at the earliest) there is no decisions.csv: nothing to publish or report."""
    s = Sync(tmp_path)
    code, out = s.run({})
    assert code == 0 and "not published" not in out and s.published("nfl-weather/decisions.csv") is None
    assert s.published("nfl-weather/ledger.csv") == "snapshot_utc\nnight 1\n"


def test_a_first_copy_saved_with_other_line_endings_is_published_as_the_scorers_read_it(tmp_path):
    s = Sync(tmp_path)
    crlf = (HEADER + A).replace("\n", "\r\n")
    assert "not published" not in s.run({NFL: crlf})[1]
    assert s.published("nfl-weather/decisions.csv") == crlf
    assert "not published" not in s.run({NFL: crlf + B})[1]                    # the scorer appends: still published
    assert s.published("nfl-weather/decisions.csv") == crlf + B


DAMAGED_COPY = {"no header": (A, "its first line is not the record's header"),
                "cut": (HEADER + A + B[:40], "its last line is cut, with no line break at the end")}


@pytest.mark.parametrize("case", DAMAGED_COPY)
def test_a_damaged_published_copy_is_named_as_the_damaged_one(tmp_path, case):
    """The review's sync_guard: with a damaged published copy and a good live file, the line said the live file had
    lost a line or had the wrong header, which could send the hub to "fix" a good file."""
    copy, why = DAMAGED_COPY[case]
    s = Sync(tmp_path)
    s.run({NFL: HEADER + A})
    s.publish_by_hand("nfl-weather/decisions.csv", copy)
    code, out = s.run({NFL: HEADER + A + B, CFB: HEADER + C})
    assert code == 0, (case, out)
    assert (f"nfl-weather: decisions.csv not published (the published copy is damaged: {why}); the published copy is "
            "kept as it is, and the hub replaces it by hand") in out, (case, out)
    assert out.count("not published") == 1, case
    assert s.published("nfl-weather/decisions.csv") == copy, case                 # never replaced here
    assert s.published("cfb-weather/decisions.csv") == HEADER + C, case           # everything else is synced
    assert s.published("nfl-weather/ledger.csv") == "snapshot_utc\nnight 2\n", case
    assert (s.repo / NFL).read_text() == HEADER + A + B, case                     # the live file is left alone


def test_an_empty_published_copy_is_replaced_only_by_a_good_file(tmp_path):
    """An empty copy holds no line, so a good file replaces it, as a first copy would be published; a damaged file
    doesn't."""
    s = Sync(tmp_path)
    s.run({NFL: HEADER + A})
    s.publish_by_hand("nfl-weather/decisions.csv", "")
    out = s.run({NFL: A})[1]
    assert ("nfl-weather: decisions.csv not published (its first line is not the record's header); the published copy "
            "is kept as it is") in out and s.published("nfl-weather/decisions.csv") == ""
    assert "not published" not in s.run({NFL: HEADER + A})[1]
    assert s.published("nfl-weather/decisions.csv") == HEADER + A


def test_while_a_changed_line_holds_the_record_back_a_new_decision_is_not_published_either(tmp_path):
    """The review's e2e_window: the live file was re-saved with other line endings, which the scorers still read, so
    a decision recorded the next day went into it; the nightly copy held the whole file back, that decision too, and
    when the file was then lost the decision was made again. Amendments 7 and 5, section 3, now state this case: a
    decision recorded while the file is held back is on the Mac only until the hub puts the changed line back and the
    next nightly copy publishes the file."""
    s = Sync(tmp_path)
    s.run({NFL: HEADER + A})
    code, out = s.run({NFL: (HEADER + A).replace("\n", "\r\n") + B})             # re-saved, then B recorded
    assert code == 0 and NOT_PUBLISHED.format(LOST) in out
    assert s.published("nfl-weather/decisions.csv") == HEADER + A                # B is not published
    code, out = s.run({NFL: HEADER + A + B})                                     # the hub puts the line endings back
    assert code == 0 and "not published" not in out
    assert s.published("nfl-weather/decisions.csv") == HEADER + A + B
    for project, n in (("nfl-weather", 7), ("cfb-weather", 5)):
        text = (ROOT.parent / project / "PREREGISTRATION.md").read_text().split(f"## Amendment {n} ")[1]
        three = " ".join(text.split("### 3.")[1].split("\n### ")[0].split())
        assert ("while the nightly copy holds the file back because a published line in it has changed" in three
                and "the one case left is a decision recorded and lost on the same day" not in three.lower()), project
