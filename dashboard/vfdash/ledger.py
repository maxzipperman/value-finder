"""The two forward-test ledgers, read once per cache period and kept as compact rows.

The NFL and CFB ledgers have different headers (and older rows leave newer columns blank), so each row is
reduced to the same fixed set of fields, found by column name. A column the ledger doesn't have is blank;
a column the dashboard doesn't know is ignored."""
from __future__ import annotations

from datetime import datetime
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
        folder, self.name, label = SPORTS[sport]
        self.path = root / folder / "data" / "forward" / "ledger.csv"
        self.csv = AppendOnlyCSV(self.path, label, picker)
        self._derived_key = None
        self._kick_memo: dict = {}
        self.by_game: dict[str, list[int]] = {}
        self.latest_snapshot = ""
        self.latest_rows: list[int] = []

    # ------------------------------------------------------------ reading
    def refresh(self) -> "Ledger":
        self.csv.refresh()
        key = (self.csv._key, len(self.csv.rows))
        if key != self._derived_key:
            self._derive()
            self._derived_key = key
        return self

    @property
    def rows(self):
        return self.csv.rows

    @property
    def readable(self) -> bool:
        return self.csv.readable

    @property
    def note(self) -> str:
        return self.csv.note

    def _derive(self):
        by_game: dict[str, list[int]] = {}
        snap_i, gid_i = I["snapshot_utc"], I["game_id"]
        latest = ""
        for n, r in enumerate(self.csv.rows):
            by_game.setdefault(r[gid_i], []).append(n)
            if r[snap_i] > latest:
                latest = r[snap_i]
        for idx in by_game.values():                    # time order, whatever order the lines were written in
            idx.sort(key=lambda n: self.csv.rows[n][snap_i])
        self.by_game = by_game
        self.latest_snapshot = latest
        self.latest_rows = [n for n, r in enumerate(self.csv.rows) if r[snap_i] == latest] if latest else []

    # ------------------------------------------------------------ one row
    def logged(self, r) -> datetime | None:
        return words.parse_utc(r[I["snapshot_utc"]])

    def kickoff(self, r) -> datetime | None:
        if self.sport == "nfl":
            key = (r[I["gameday"]], r[I["gametime"]])
            if key not in self._kick_memo:
                self._kick_memo[key] = words.eastern_kickoff(*key)
            return self._kick_memo[key]
        key = (r[I["start_utc"]], r[I["kick_et"]], r[I["snapshot_utc"]][:7])
        if key not in self._kick_memo:
            self._kick_memo[key] = words.cfb_kickoff(r[I["start_utc"]], r[I["kick_et"]], self.logged(r))
        return self._kick_memo[key]

    def signal(self, r) -> bool:
        return any(words.is_signal(rule, r[I[rule]]) for rule in RULES[self.sport])

    def latest_row(self, game_id: str):
        idx = self.by_game.get(game_id)
        return self.csv.rows[idx[-1]] if idx else None

    def game_rows(self, game_id: str) -> list:
        return [self.csv.rows[n] for n in self.by_game.get(game_id, [])]


def get(r, name: str) -> str:
    return r[I[name]]
