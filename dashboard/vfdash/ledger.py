"""The two forward-test ledgers, read once per cache period and kept as compact rows.

The NFL and CFB ledgers have different headers (and older rows leave newer columns blank), so each row is
reduced to the same fixed set of fields, found by column name. A column the ledger doesn't have is blank;
a column the dashboard doesn't know is ignored.

A ledger without the columns every row needs (when it was logged, the game, its kickoff) can't be read, and
says so. Each row's logging time is read as a time, never compared as text: the latest run is the latest
time that could be read, and a row whose time can't be read is left out and counted."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from operator import itemgetter
from pathlib import Path

from . import words
from .readers import AppendOnlyCSV

FIELDS = ("snapshot_utc", "rules_version", "game_id", "gameday", "gametime", "kick_et", "start_utc", "away_team",
          "home_team", "venue", "lead_days", "wx_src", "wx_wind", "wx_temp", "wx_precip", "wx_snow", "line_src",
          "total", "under", "over", "p_under", "p_market", "lean", "ev_under", "rule_b", "rule_ht", "ht_threshold",
          "best_under", "best_under_book", "best_line", "best_line_under", "best_line_book", "ev_best_line",
          "quote_utc")
I = {name: i for i, name in enumerate(FIELDS)}
ALIASES = {"total": ("total_line", "mkt_total"), "under": ("under_odds", "mkt_under"),
           "over": ("over_odds", "mkt_over")}
SPORTS = {"nfl": ("nfl-weather", "NFL", "the NFL ledger"), "cfb": ("cfb-weather", "CFB", "the college football ledger")}
RULES = {"nfl": ("rule_b", "lean"), "cfb": ("rule_b", "rule_ht")}
# Columns a ledger must have to be read at all. Each entry is a set of names, any one of which will do: a CFB
# row's kickoff is start_utc, or kick_et on rows logged before start_utc was added.
REQUIRED = {"nfl": (("snapshot_utc",), ("game_id",), ("gameday",), ("gametime",)),
            "cfb": (("snapshot_utc",), ("game_id",), ("start_utc", "kick_et"))}
# A row is logged when a run starts, a little before the dashboard may read it; one logged later than now plus
# this is left out until its time comes (a clock set ahead when it was written, or behind now).
FUTURE_SLACK = timedelta(minutes=5)


def picker(header: list[str]):
    """header -> a function turning a CSV row into a tuple of FIELDS (blank where the column is absent)."""
    pos = {h: i for i, h in enumerate(header)}
    idx = []
    for f in FIELDS:
        names = ALIASES.get(f, ()) + (f,)
        idx.append(next((pos[n] for n in names if n in pos), -1))
    get = itemgetter(*idx)
    if all(i >= 0 for i in idx):
        return get                                      # every column is there: the fast path

    def pick(row):
        row.append("")                                  # index -1 is the blank for a missing column
        return get(row)
    return pick


class Ledger:
    def __init__(self, sport: str, root: Path):
        self.sport = sport
        folder, self.name, self.short = SPORTS[sport]
        self.project = folder                           # nfl-weather or cfb-weather
        self.path = root / folder / "data" / "forward" / "ledger.csv"
        self.csv = AppendOnlyCSV(self.path, f"{self.short} ({folder}/data/forward/ledger.csv)", picker)
        self._derived_key = None
        self._kick_memo: dict = {}
        self._time_memo: dict = {}
        self.by_game: dict[str, list[int]] = {}
        self.latest_snapshot = ""                       # the latest run's time, as "2026-10-02T14:30:07Z"
        self.latest_rows: list[int] = []
        self.missing_columns: list[str] = []
        self.untimed = 0                                # rows left out: their logging time can't be read
        self.future: list[tuple[datetime, str]] = []    # rows left out: logged later than now (time, game id)
        self._future_from: datetime | None = None       # the earliest of those times

    # ------------------------------------------------------------ reading
    def refresh(self, now: datetime | None = None) -> "Ledger":
        """Read what was added. With `now`, a row logged later than now is left out until its time comes."""
        self.csv.refresh()
        key = (self.csv._key, len(self.csv.rows), tuple(self.csv.header))
        due = self._future_from is not None and (now is None or now + FUTURE_SLACK >= self._future_from)
        if key != self._derived_key or due:
            self._derive(now)
            self._derived_key = key
        return self

    @property
    def rows(self):
        return self.csv.rows

    @property
    def readable(self) -> bool:
        """Readable: the file was read, it has the columns every row needs, and when it has rows, at least one
        has a logging time that can be read."""
        return (self.csv.readable and not self.missing_columns
                and not (self.csv.rows and self.untimed == len(self.csv.rows)))

    @property
    def note(self) -> str:
        if not self.csv.readable:
            return self.csv.note
        if self.missing_columns:
            return (f"{words.cap(self.csv.label)} {words.missing_columns(self.missing_columns)}, so it can't be "
                    "read. Its games are not shown.")
        notes = [self.csv.note] if self.csv.note else []
        if self.untimed:
            if self.untimed == len(self.csv.rows):
                notes.append(f"No row of {self.csv.label} has a logging time (snapshot_utc) that can be read, so "
                             "its games are not shown.")
            else:
                notes.append(f"{words.count(self.untimed, 'row')} of {self.csv.label} "
                             f"{'has' if self.untimed == 1 else 'have'} a logging time (snapshot_utc) that can't "
                             f"be read; {'it is' if self.untimed == 1 else 'they are'} left out.")
        return " ".join(notes)

    def future_note(self, tz) -> str:
        """The rows logged later than now, counted and named (at most three by game), in local time."""
        n = len(self.future)
        named = "; ".join(f"game {gid or '(no id)'} at {words.when_full(t, tz)}" for t, gid in self.future[:3])
        more = f"; and {n - 3:,} more" if n > 3 else ""
        return (f"{words.count(n, 'row')} of {self.csv.label} {'is' if n == 1 else 'are'} logged later than now: "
                f"{named}{more}. {'It is' if n == 1 else 'They are'} left out until then.")

    def future_problem(self) -> str:
        n = len(self.future)
        return (f"{words.cap(self.short)} has {words.count(n, 'row')} logged later than now, "
                f"{'which is' if n == 1 else 'which are'} left out; check the Mac's clock.")

    def _time(self, text: str):
        """A row's logging time, read once per distinct text (a run's rows share one)."""
        t = self._time_memo.get(text, False)
        if t is False:
            t = self._time_memo[text] = words.parse_utc(text)
        return t

    def _derive(self, now: datetime | None = None):
        header = set(self.csv.header)
        self.missing_columns = [names[0] + "".join(f" (or {n})" for n in names[1:]) for names in REQUIRED[self.sport]
                                if not any(n in header for n in names)] if self.csv.readable else []
        by_game: dict[str, list[int]] = {}
        times: dict[int, object] = {}
        snap_i, gid_i = I["snapshot_utc"], I["game_id"]
        latest = None
        untimed = 0
        future: list[tuple[datetime, str]] = []
        cutoff = None if now is None else now + FUTURE_SLACK
        if not self.missing_columns:
            for n, r in enumerate(self.csv.rows):
                t = self._time(r[snap_i])
                if t is None:
                    untimed += 1
                    continue
                if cutoff is not None and t > cutoff:  # never "the latest run": left out, counted and named
                    future.append((t, r[gid_i]))
                    continue
                times[n] = t
                by_game.setdefault(r[gid_i], []).append(n)
                if latest is None or t > latest:
                    latest = t
            for idx in by_game.values():                # time order, whatever order the lines were written in
                idx.sort(key=times.__getitem__)
        self.by_game = by_game
        self.untimed = untimed
        self.future = sorted(future)
        self._future_from = self.future[0][0] if future else None
        self.latest_snapshot = words.iso_z(latest) or ""
        self.latest_rows = [n for n, t in times.items() if t == latest] if latest is not None else []

    # ------------------------------------------------------------ one row
    def logged(self, r) -> datetime | None:
        return self._time(r[I["snapshot_utc"]])

    def kickoff(self, r) -> datetime | None:
        """The kickoff as logged. For a game whose time isn't set (see time_set) it is midnight Eastern at the
        start of the game's date, which only says the date."""
        if self.sport == "nfl":
            key = (r[I["gameday"]], r[I["gametime"]])
            if key not in self._kick_memo:
                self._kick_memo[key] = words.eastern_kickoff(key[0], key[1] if key[1].strip() else "00:00")
            return self._kick_memo[key]
        key = (r[I["start_utc"]], r[I["kick_et"]], r[I["snapshot_utc"]][:7])
        if key not in self._kick_memo:
            self._kick_memo[key] = words.cfb_kickoff(r[I["start_utc"]], r[I["kick_et"]], self.logged(r))
        return self._kick_memo[key]

    def time_set(self, r) -> bool:
        """False for a game whose kickoff time isn't set yet. The college job logs one with cfbfastR's placeholder
        kickoff, midnight Eastern at the start of its date (no game in the schedule really starts then), and at an
        outdoor venue also with wx_src and rule_b "time_tbd". An NFL row with a gameday but no gametime is the
        same."""
        if self.sport == "nfl":
            return bool(r[I["gametime"]].strip())
        if "time_tbd" in (r[I["wx_src"]].strip(), r[I["rule_b"]].strip()):
            return False
        k = self.kickoff(r)
        return k is None or k.astimezone(words.EASTERN).time() != time(0, 0)

    def until(self, r) -> datetime | None:
        """Until when the game is still to be played: its kickoff; for a game whose time isn't set, the end of its
        date in Eastern time, since it may start at any hour of that day."""
        k = self.kickoff(r)
        if k is None or self.time_set(r):
            return k
        day = k.astimezone(words.EASTERN).date() + timedelta(days=1)
        return datetime.combine(day, time(0, 0), tzinfo=words.EASTERN).astimezone(timezone.utc)

    def signal(self, r) -> bool:
        return any(words.is_signal(rule, r[I[rule]]) for rule in RULES[self.sport])

    def latest_row(self, game_id: str):
        idx = self.by_game.get(game_id)
        return self.csv.rows[idx[-1]] if idx else None

    def game_rows(self, game_id: str) -> list:
        return [self.csv.rows[n] for n in self.by_game.get(game_id, [])]


def get(r, name: str) -> str:
    return r[I[name]]
