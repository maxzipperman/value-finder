"""The 5M-credit Odds API month: every candidate historical pull across sports, ranked by research
value, with a cut line at the history budget (no API calls, no downloads).

Called by odds_budget.py; run on its own with
    nfl-weather/.venv/bin/python strategy-research/odds_5m.py [--no-save]

Counts
* NFL and CFB: exact, from the processed schedules (odds_budget.py's helpers; 2026 uses 2025 as a
  stand-in because its schedule is incomplete).
* NBA, NHL, MLB and soccer: season STRUCTURE estimates (games, days in the season window, distinct
  kickoff slots), written out below with their assumptions, because their schedules aren't
  reachable from the cloud. Day one's probe (sharp-markets `markets odds5m probe`) pulls the real
  schedules from the Odds API's historical /events endpoint (1 credit a call) and replaces them.

Costs (official docs): historical featured /odds = 10 x markets x book groups per snapshot, covering
every game of the sport; historical event odds = 10 x markets x groups per game per snapshot.
Up to 10 bookmakers = 1 group. Featured here = h2h, spreads, totals (3 markets) at 10 books = 30.

The 2026 season of every sport is a SEALED HOLDOUT: it is pulled while credits last (history can't be
bought cheaper later) but nothing analyses it until a hypothesis about it is pre-registered.
"""
import argparse
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "output"
HIST, FEAT = 10, 3                 # historical multiplier; featured markets (h2h, spreads, totals)
PER_SNAP = HIST * FEAT             # one featured snapshot at up to 10 books
HISTORY_BUDGET = 4_500_000         # the owner's target for history
RESERVE = 300_000                  # probes, the live uses during the month, mistakes

# ---------------------------------------------------------------- season structures (estimates)
# (season label, games, days in the season window, distinct kickoff slots, sealed holdout?)
# slots = regular games x slot ratio + postseason games x 0.95. Ratios: NBA 0.64 is exact for 2025-26
# (791 tip slots / 1,233 games, sharp-markets/docs/PLAN.md); the others are from typical start-time
# clustering (NHL 7:00/7:30 pm ET waves 0.45; MLB 0.66; MLS 0.45; Liga MX 0.70; Brasileirao 0.55;
# J1 0.45; K League 0.50; tournaments 0.90). Days include the 7 days before the first game.
def _s(label, reg, post, days, ratio, sealed=False):
    return (label, reg + post, days + 7, round(reg * ratio + post * 0.95), sealed)


SPORTS = {
    "basketball_nba": ("NBA", "2020-06-27", [
        _s("2019-20 restart", 88, 83, 74, 0.64), _s("2020-21", 1086, 85, 211, 0.64),
        *[_s(f"{y}-{y - 1999:02d}", 1236, 84, 240, 0.64) for y in range(2021, 2025)],
        _s("2025-26", 1236, 84, 240, 0.64)]),
    "icehockey_nhl": ("NHL", "2020-06-29", [
        _s("2019-20 restart", 52, 78, 59, 0.45), _s("2020-21", 868, 84, 176, 0.45),
        *[_s(f"{y}-{y - 1999:02d}", 1312, 86, 250, 0.45) for y in range(2021, 2026)]]),
    "baseball_mlb": ("MLB", "2020-06-30", [
        _s("2020", 898, 53, 97, 0.66), *[_s(str(y), 2430, 43, 215, 0.66) for y in range(2021, 2026)],
        _s("2026", 2430, 43, 215, 0.66, sealed=True)]),
    "soccer_usa_mls": ("MLS", "2020-06-27", [
        _s("2020", 260, 18, 150, 0.45), _s("2021", 459, 13, 285, 0.45), _s("2022", 476, 13, 285, 0.45),
        _s("2023", 493, 29, 285, 0.45), _s("2024", 493, 29, 285, 0.45), _s("2025", 510, 29, 285, 0.45),
        _s("2026", 510, 29, 285, 0.45, sealed=True)]),
    "soccer_mexico_ligamx": ("Liga MX", "2020-07-15", [
        _s("2020 Apertura", 153, 20, 150, 0.70), *[_s(str(y), 306, 36, 330, 0.70) for y in range(2021, 2026)],
        _s("2026", 306, 36, 330, 0.70, sealed=True)]),
    "soccer_brazil_campeonato": ("Brasileirao", "2020-07-28", [
        *[_s(str(y), 380, 0, 240, 0.55) for y in range(2020, 2026)], _s("2026", 380, 0, 240, 0.55, sealed=True)]),
    "soccer_japan_j_league": ("J1 League", "2020-06-23", [
        _s("2020", 306, 0, 170, 0.45), _s("2021", 380, 0, 280, 0.45), _s("2022", 306, 0, 270, 0.45),
        _s("2023", 306, 0, 270, 0.45), _s("2024", 380, 0, 280, 0.45), _s("2025", 380, 0, 280, 0.45),
        _s("2026 special half-season", 180, 0, 140, 0.45, sealed=True)]),
    "soccer_korea_kleague1": ("K League 1", "2020-06-06", [
        _s("2020", 162, 0, 180, 0.50), *[_s(str(y), 228, 0, 260, 0.50) for y in range(2021, 2026)],
        _s("2026", 228, 0, 260, 0.50, sealed=True)]),
    "soccer_fifa_world_cup": ("World Cups", "2022-04-03", [
        _s("2022 Qatar (Nov-Dec, cooled stadiums: a heat control)", 64, 0, 29, 0.90),
        _s("2026 North America", 104, 0, 39, 0.90, sealed=True)]),
    "soccer_uefa_european_championship": ("Euro 2024", "2021-05-19", [_s("2024", 51, 0, 31, 0.90)]),
    "soccer_conmebol_copa_america": ("Copa America 2024", "2024-04-10", [_s("2024", 32, 0, 25, 0.90)]),
    "soccer_fifa_club_world_cup": ("Club World Cup 2025", "2025-05-27", [_s("2025", 63, 0, 30, 0.90)]),
    "soccer_concacaf_gold_cup": ("Gold Cup 2025", "2025-06-09", [_s("2025", 31, 0, 23, 0.90)]),
    "soccer_concacaf_leagues_cup": ("Leagues Cup 2025", "2025-07-25", [_s("2025", 45, 0, 34, 0.90)]),
}
SOCCER_WHY = {
    "MLS": "US summer: Houston, Dallas, Austin, Orlando, Miami, Kansas City play afternoon/evening games in heat",
    "Liga MX": "Monterrey, Guadalajara and Tijuana heat, plus altitude (Mexico City, Toluca) as a control",
    "Brasileirao": "tropical and inland heat (Cuiaba, Fortaleza, Rio) through most of the season",
    "J1 League": "Japanese summer heat and humidity (July-August matches); winter matches are the control",
    "K League 1": "Korean summer heat and humidity; similar calendar to J1",
    "World Cups": "2022 Qatar is a cooled-stadium control; 2026 North America is the prime heat test (sealed)",
    "Euro 2024": "German summer, occasional heat waves; a cooler control for the US tournaments",
    "Copa America 2024": "US summer venues, several heat complaints",
    "Club World Cup 2025": "US summer, widely reported extreme heat and midday kickoffs",
    "Gold Cup 2025": "US summer venues",
    "Leagues Cup 2025": "US summer, MLS vs Liga MX",
}


def structured_rows():
    rows = []
    for key, (name, since, seasons) in SPORTS.items():
        for label, games, days, slots, sealed in seasons:
            rows.append(dict(sport=name, key=key, season=label, games=games, days=days, slots=slots,
                             snapshots=days + slots, sealed=sealed, history_from=since))
    return pd.DataFrame(rows)


def football_counts():
    """Exact NFL/CFB counts from odds_budget.py (2026 = 2025 stand-in)."""
    import odds_budget as ob
    nfl, cfb = ob.nfl_games(), ob.cfb_games()
    out = {}
    for name, d in (("NFL", nfl), ("CFB", cfb)):
        daily = ob.per_season(d, lambda x: len(ob.grid(x.kick, 7 * ob.D, None, at=16)))
        hourly = ob.per_season(d, lambda x: len(ob.grid(x.kick, 7 * ob.D, ob.H)))
        games = ob.per_season(d, len)
        out[name] = dict(daily=daily, hourly=hourly, games=games)
    return out


def plan():
    fb = football_counts()
    s = structured_rows()
    daily_fb = sum(sum(v["daily"].values()) for v in fb.values())
    hourly_fb = sum(sum(v["hourly"].values()) for v in fb.values())
    nfl_p = sum(fb["NFL"]["games"][y] for y in range(2023, 2027))      # props/alternates exist from 2023-05-03
    cfb_p = sum(fb["CFB"]["games"][y] for y in range(2023, 2027))
    snaps = lambda sport, exclude=(): int(s[(s.sport == sport) & ~s.season.isin(exclude)].snapshots.sum())  # noqa: E731
    soccer = [n for n in s.sport.unique() if n in SOCCER_WHY]
    nba_other = snaps("NBA", exclude=("2025-26",))

    P = [  # id, pull, arithmetic, credits, value (1-5), primary hypothesis (data-use plan)
        ("F1", "NFL+CFB featured, 10 books, daily 16:00 UTC for 7 days pre-kickoff + every close, 2020-26",
         f"{PER_SNAP} x {daily_fb:,} snapshots", PER_SNAP * daily_fb, 4,
         "Soft-book prices beyond the sharp fair line earn CLV (price engine, #8)"),
        ("F2", "NFL alternate spreads, alternate totals, team totals at T-24h, T-2h, close, 2023-26",
         f"10 x 3 mkts x 3 snaps x {nfl_p:,} games", HIST * 3 * 3 * nfl_p, 3,
         "Alternate lines misprice key-number crossings vs recent-era margins"),
        ("F3", "NFL props: pass/rush/rec yds, receptions, kicking points, FGs made at T-48h, T-24h, T-2h, close, 2023-26",
         f"10 x 6 mkts x 4 snaps x {nfl_p:,} games", HIST * 6 * 4 * nfl_p, 3,
         "Yardage-prop unders beat 50% (#10); kicking-points unders in wind/cold (#21)"),
        ("F4", "NFL+CFB featured, 10 books, HOURLY for 7 days pre-kickoff, 2020-26",
         f"{PER_SNAP} x {hourly_fb:,} snapshots", PER_SNAP * hourly_fb, 3,
         "Hour-to-hour line moves reverse before the close (#16)"),
        ("S1", "Soccer heat leagues and tournaments, featured (h2h 3-way, spreads, totals), daily + every close",
         f"{PER_SNAP} x {sum(snaps(n) for n in soccer):,} snapshots (estimate)",
         PER_SNAP * sum(snaps(n) for n in soccer), 3,
         "Kickoff heat index >= threshold (PR D) -> under at the close"),
        ("B1", "MLB featured (moneyline, run line, totals), daily + every close, 2020-26",
         f"{PER_SNAP} x {snaps('MLB'):,} snapshots (estimate)", PER_SNAP * snaps("MLB"), 3,
         "Open-air park weather (PR D) -> totals; wind in -> under"),
        ("N1", "NBA 2025-26 at 5-min resolution, h2h, 3 sharp books (PLAN.md schedule D)",
         "10 x 1 mkt x 49,398 snapshots, less cached", HIST * (49_398 - 754 - 791), 2,
         "H1/H2: Kalshi static edge and lag vs Pinnacle (PLAN.md)"),
        ("N2", "NBA featured, daily + every close, seasons other than 2025-26",
         f"{PER_SNAP} x {nba_other:,} snapshots (estimate)", PER_SNAP * nba_other, 2,
         "Favorite-longshot bias and soft-price flags at the best price"),
        ("H1", "NHL featured (moneyline, puck line, totals), daily + every close, 2020-26",
         f"{PER_SNAP} x {snaps('NHL'):,} snapshots (estimate)", PER_SNAP * snaps("NHL"), 2,
         "Favorite-longshot bias and soft-price flags (no weather: indoor)"),
        ("F5", "CFB alternate lines and team totals at T-24h and close, 2023-26",
         f"10 x 3 mkts x 2 snaps x {cfb_p:,} games", HIST * 3 * 2 * cfb_p, 2,
         "Rule HT-style shrinkage shows up in team totals and alternates"),
        ("F6", "CFB props (4 yardage markets) at the close, 2023-26 (upper bound; thin coverage)",
         f"10 x 4 mkts x {cfb_p:,} games", HIST * 4 * cfb_p, 1, "Median-vs-mean props in CFB"),
        ("X3", "Exchange book group (Kalshi, Polymarket, Novig, ProphetX), hourly, 2025",
         "10 x 3 x 7,721 snapshots", 231_630, 1, "Better data is free from Kalshi and Polymarket directly"),
        ("X2", "5-min NFL+CFB totals for 72h before windy kickoffs, 2024-25",
         "10 x 1 x 70,558 snapshots", 705_580, 1, "Forecast-run timing; needs run-issue timestamps first"),
    ]
    p = pd.DataFrame(P, columns=["id", "pull", "arithmetic", "credits", "value", "primary_hypothesis"])
    p = p.sort_values(["value", "credits"], ascending=[False, True], kind="stable").reset_index(drop=True)
    p["cumulative"] = p.credits.cumsum()
    p["in_plan"] = p.cumulative <= HISTORY_BUDGET
    return p, s, dict(daily_fb=daily_fb, hourly_fb=hourly_fb, nfl_p=nfl_p, cfb_p=cfb_p)


def live_month():
    """Live uses during and after the month (credits per month; live calls are 1x, not 10x)."""
    rows = [
        ("Alerts, NFL + CFB (10 books a call)", "4 runs x 31 days x 2 sports", 248),
        ("Close capture (one call per kickoff slot)", "~137 NFL + CFB slots", 137),
        ("Trigger poller: every 10 min while a Rule B wind trigger is active", "~6 polls/h x 72 h x ~6 trigger windows", 2_600),
        ("NFL props, alternates, team totals log (event odds)", "70 games x 9 mkts x 4 snaps", 70 * 9 * 4),
        ("NBA collector, PLAN.md s7 (5-min h2h ticks + 1-min final 2 h)", "27 game days x (144-288 + 0-205)", 14_175),
    ]
    return pd.DataFrame(rows, columns=["live use", "arithmetic", "credits_per_month"])


def main(save=True):
    p, s, c = plan()
    live = live_month()
    if save:
        p.to_csv(OUT / "odds_5m_plan.csv", index=False)
        s.to_csv(OUT / "odds_5m_seasons.csv", index=False)
        live.to_csv(OUT / "odds_5m_live.csv", index=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 110)
    print("\n5M month: historical pulls ranked by research value (cut line at "
          f"{HISTORY_BUDGET:,}; reserve {RESERVE:,})")
    print(p[["id", "value", "credits", "cumulative", "in_plan", "pull"]].to_string(index=False))
    inp = p[p.in_plan]
    print(f"\nIn plan: {inp.credits.sum():,} credits of history + {RESERVE:,} reserve = "
          f"{inp.credits.sum() + RESERVE:,} of 5,000,000; below the cut: {', '.join(p[~p.in_plan].id)} "
          f"({p[~p.in_plan].credits.sum():,})")
    print("\nSeason structures (estimates for non-football sports; the probe replaces them):")
    print(s.groupby("sport", sort=False).agg(seasons=("season", "size"), games=("games", "sum"),
                                             snapshots=("snapshots", "sum"), sealed=("sealed", "sum")).to_string())
    print("\nLive uses per month (1 credit per market per group per call):")
    print(live.to_string(index=False))
    print(f"Total live, high case: {live.credits_per_month.sum():,} a month")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true")
    main(save=not ap.parse_args().no_save)
