"""Early H3 test on the Kaggle MGM Grand NBA splits (caseydurfee/mgm-grand-nba-betting-data, CC BY-SA 4.0).

Question: does money% − ticket% divergence (a proxy for sharp money) predict results beyond the closing line?
Limits (stated in every report): one retail book (BetMGM via Yahoo), closing splits only, no timing — so reverse
line movement cannot be tested; the comparison line is MGM's own close, not Pinnacle's (that waits for the full pull).
"""
from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import defaultdict
from datetime import date, datetime

import requests

from ..build.run import connect
from ..settings import RAW_DIR, REPORTS_DIR, env, utcnow
from ..sport import load_teams
from ..stats import mean_se, ols_hc1

DATASET = "caseydurfee/mgm-grand-nba-betting-data"
# Last regular-season date per season (games after this are play-in/playoffs).
REGULAR_END = {"2021-22": date(2022, 4, 10), "2022-23": date(2023, 4, 9), "2023-24": date(2024, 4, 14),
               "2024-25": date(2025, 4, 13), "2025-26": date(2026, 4, 12)}
THRESHOLDS = (5, 10, 15)


def download(force: bool = False) -> bytes:
    """Cache-first download of the dataset zip to data/raw/nba/kaggle_mgm/{date}/ (needs KAGGLE_* in .env)."""
    base = RAW_DIR / "nba" / "kaggle_mgm"
    existing = sorted(base.glob("*/dataset.zip"))
    if existing and not force:
        return existing[-1].read_bytes()
    r = requests.get(f"https://www.kaggle.com/api/v1/datasets/download/{DATASET}",
                     auth=(env("KAGGLE_USERNAME"), env("KAGGLE_KEY")), timeout=120)
    r.raise_for_status()
    out = base / utcnow().date().isoformat() / "dataset.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return r.content


def load_rows(blob: bytes) -> tuple[list[dict], list[str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        text = z.read(name).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), reader.fieldnames or []


def _f(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _b(v):
    return {"true": True, "false": False, "1": True, "0": False, "1.0": True, "0.0": False}.get(str(v).strip().lower())


def _date(v):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(v)[:19], fmt).date()
        except ValueError:
            continue
    return None


def _season(d: date) -> str:
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _devig(a, b):
    if not a or not b or a <= 1 or b <= 1:
        return None
    ia, ib = 1 / a, 1 / b
    return ia / (ia + ib)


def run_h3() -> dict:
    teams = load_teams("nba")
    rows, fields = load_rows(download())
    unknown, games = defaultdict(int), []
    for r in rows:
        d = _date(r.get("game_date"))
        home, away = teams.from_name(r.get("home_team")), teams.from_name(r.get("away_team"))
        for n, c in ((r.get("home_team"), home), (r.get("away_team"), away)):
            if c is None:
                unknown[n] += 1
        if d is None or home is None or away is None:
            continue
        season = _season(d)
        g = {"source_game_key": r.get("game_id"), "game_date": d, "season": season, "home": home, "away": away,
             "phase": "regular" if d <= REGULAR_END.get(season, date.max) else "postseason"}
        for mk, (s1, s2) in {"money": ("home", "away"), "spread": ("home", "away"), "total": ("over", "under")}.items():
            for side in (s1, s2):
                p = f"{mk}_{side}_"
                g[f"{mk}_{side}"] = {"dec": _f(r.get(p + "decimal_odds")), "stake": _f(r.get(p + "stake_percentage")),
                                     "wager": _f(r.get(p + "wager_percentage")), "won": _b(r.get(p + "won")),
                                     "line": _f(r.get(p + "points"))}
        games.append(g)

    results = {"n_rows": len(rows), "n_games": len(games), "fields": fields, "unknown_teams": dict(unknown)}
    tests = []
    for market in ("money", "spread"):
        sides = []
        for g in games:
            h, a = g[f"{market}_home"], g[f"{market}_away"]
            if h["won"] is None or a["won"] is None or (not h["won"] and not a["won"]):   # missing or push
                continue
            fair_h = _devig(h["dec"], a["dec"])
            if fair_h is None or h["stake"] is None or h["wager"] is None:
                continue
            for side, o, fair in (("home", h, fair_h), ("away", a, 1 - fair_h)):
                sides.append({"season": g["season"], "phase": g["phase"], "side": side, "fair": fair, "dec": o["dec"],
                              "won": int(bool(o["won"])), "div": (o["stake"] or 0) - (o["wager"] or 0),
                              "resid": int(bool(o["won"])) - fair, "profit": (o["dec"] - 1) if o["won"] else -1.0})
        for k in THRESHOLDS:
            sharp = [s for s in sides if s["div"] >= k]
            for scope, subset in (("all", sharp), ("regular", [s for s in sharp if s["phase"] == "regular"]),
                                  *((f"season {se}", [s for s in sharp if s["season"] == se])
                                    for se in sorted({s["season"] for s in sharp}))):
                rm, rse, n = mean_se([s["resid"] for s in subset])
                pm, pse, _ = mean_se([s["profit"] for s in subset])
                tests.append({"market": market, "k": k, "scope": scope, "n": n, "win_rate": mean_se([s["won"] for s in subset])[0],
                              "mean_fair": mean_se([s["fair"] for s in subset])[0], "resid": rm, "resid_se": rse,
                              "roi": pm, "roi_se": pse, "fav_share": mean_se([int(s["fair"] > 0.5) for s in subset])[0]})
        # continuous: home-side residual on divergence, with fair-prob decile dummies (controls favorite-longshot bias)
        home = [s for s in sides if s["side"] == "home"]
        deciles = [min(int(s["fair"] * 10), 9) for s in home]
        dummies = sorted(set(deciles))[1:]
        X = [[s["div"] / 10, *[int(d == q) for q in dummies]] for s, d in zip(home, deciles)]
        reg = ols_hc1([s["resid"] for s in home], X, ["div_per_10pts", *[f"fair_decile_{q}" for q in dummies]])
        results[f"{market}_regression"] = next(r for r in reg if r["term"] == "div_per_10pts")
        results[f"{market}_n_sides"] = len(sides)
    results["tests"] = tests
    results["n_variants"] = len(THRESHOLDS) * 2 + 2

    # store closing splits in the shared `splits` table; count how many map to Kalshi games
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS splits (sport VARCHAR, dataset VARCHAR, collected_ts TIMESTAMPTZ, is_closing BOOLEAN,
                   source_game_key VARCHAR, game_id VARCHAR, game_date DATE, market VARCHAR, side VARCHAR, team_code VARCHAR,
                   bets_pct DOUBLE, handle_pct DOUBLE, line DOUBLE, price_decimal DOUBLE)""")
    con.execute("DELETE FROM splits WHERE dataset = 'kaggle_mgm'")
    kalshi = {}
    if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'games'").fetchone()[0]:
        kalshi = {(d, a, h): gid for gid, d, a, h in con.execute(
            "SELECT game_id, game_date_et, away_code, home_code FROM games WHERE sport = 'nba'").fetchall()}
    out = []
    for g in games:
        gid = kalshi.get((g["game_date"], g["away"], g["home"]))
        for mk in ("money", "spread", "total"):
            for side in (("home", "away") if mk != "total" else ("over", "under")):
                o = g[f"{mk}_{side}"]
                out.append(("nba", "kaggle_mgm", None, True, g["source_game_key"], gid, g["game_date"],
                            {"money": "ml"}.get(mk, mk), side,
                            g["home"] if side == "home" else g["away"] if side == "away" else None,
                            o["wager"], o["stake"], o["line"], o["dec"]))
    con.executemany("INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", out)
    results["kalshi_joined_games"] = len({(r[4]) for r in out if r[5]})
    con.close()
    results["report"] = _report(results)
    return results


def _fmt(x, nd=3, pct=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x * 100:.1f}%" if pct else f"{x:+.{nd}f}"


def _report(res: dict):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "h3_kaggle_mgm.md"
    L = ["# H3 (early) — MGM money% vs ticket% divergence, NBA (Kaggle, CC BY-SA 4.0)", "",
         "Limits: one retail book (BetMGM via Yahoo), **closing** splits only, no timestamps → reverse line movement is "
         "not testable; the benchmark is MGM's own de-vigged close (Pinnacle-close version waits for the full pull).", "",
         f"- rows {res['n_rows']:,}; usable games {res['n_games']:,}; unknown team names {res['unknown_teams'] or 'none'}",
         f"- ML sides {res.get('money_n_sides', 0):,}, ATS sides {res.get('spread_n_sides', 0):,} (pushes excluded)",
         f"- games that map to a Kalshi KXNBAGAME event: {res['kalshi_joined_games']:,}",
         f"- **n_variants_tested = {res['n_variants']}** (3 thresholds × ML/ATS + 2 regressions)", "",
         "## Continuous test: (won − MGM fair) on divergence, fair-prob decile controls (HC1)",
         "| market | coef per +10 pts of (money% − ticket%) | SE | p | n |", "|---|---|---|---|---|"]
    for mk, label in (("money", "moneyline"), ("spread", "spread (ATS)")):
        r = res.get(f"{mk}_regression")
        if r:
            L.append(f"| {label} | {_fmt(r['coef'], 4)} | {_fmt(r['se'], 4)} | {r['p']:.3f} | {r['n']:,} |")
    L += ["", "## Threshold tests: back the side where money% − ticket% ≥ k at MGM's closing price",
          "| market | k | scope | n | win rate | mean fair | win − fair (± SE) | ROI (± SE) | share favorites |",
          "|---|---|---|---|---|---|---|---|---|"]
    for t in res["tests"]:
        L.append(f"| {t['market']} | {t['k']} | {t['scope']} | {t['n']:,} | {_fmt(t['win_rate'], pct=True)} | "
                 f"{_fmt(t['mean_fair'], pct=True)} | {_fmt(t['resid'])} ± {_fmt(t['resid_se'])} | "
                 f"{_fmt(t['roi'])} ± {_fmt(t['roi_se'])} | {_fmt(t['fav_share'], pct=True)} |")
    path.write_text("\n".join(L) + "\n")
    return path
