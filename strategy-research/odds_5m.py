"""The 5M-credit Odds API month, as the owner decided it on Sep 28, 2026 after the plan review
(plan-review-2026-09-28.md; issue #38): a small day-one pull, two pulls gated on results inside the month,
the props pull behind its own pre-registration (#41), and the rest in a March 2027 month. No API calls,
no downloads.

Called by odds_budget.py; run on its own with
    nfl-weather/.venv/bin/python strategy-research/odds_5m.py [--no-save]

Tiers
* day_one   runs on Oct 1 (docs: sharp-markets/docs/ODDS5M_DAY_ONE.md), under DAY_ONE_CAP in all
* gated     runs inside the month only when its written gate passes (the gate text is in the table)
* march     the March 2027 month, each with its own gate
* replaced  B1 and S1, the full MLB and soccer histories, replaced by the close-only HB1 and HS1
* dropped   X3, by the owner; deferred: X2

Counts
* NFL and CFB: exact, from the processed schedules (odds_budget.py's helpers). 2026 uses 2025 as a
  stand-in for the season's full size, so every football figure is an upper bound; credits_2026 is the
  2026 share, and credits_2026_by_oct1 the part of it that exists on Oct 1 (games kicked off by then).
  The difference is what a March month completes.
* NBA, NHL, MLB and soccer: season STRUCTURE estimates (games, days in the season window, distinct
  kickoff slots), written out below with their assumptions. Day one's probe (`markets odds5m probe`)
  pulls the real schedules from the Odds API's historical /events endpoint and replaces them.
* Heat closes: the review's free counts of qualifying games (HEAT_QUALIFYING), one close slot each,
  an upper bound; `markets weather qualifying` gives the real day-1 forecast counts on the Mac.

Costs (official docs): historical featured /odds = 10 x markets x book groups per snapshot, covering
every game of the sport; historical event odds = 10 x markets x groups per game per snapshot.
Up to 10 bookmakers = 1 group. Featured here = h2h, spreads, totals (3 markets) at 10 books = 30.

The 2026 season of every sport is a SEALED HOLDOUT: what exists is pulled with its season (history can't
be bought cheaper later) but nothing analyses it until a hypothesis about it is pre-registered.
"""
import argparse
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "output"
HIST, FEAT = 10, 3                 # historical multiplier; featured markets (h2h, spreads, totals)
PER_SNAP = HIST * FEAT             # one featured snapshot at up to 10 books
DAY_ONE_CAP = 400_000              # owner decision, Sep 28: day one stays under this
CEILING = 4_440_000                # the hard drop line for the whole month (ODDS5M_DAY_ONE.md): 5M less the
                                   # floor, the probe and October's live use, rounded down
RESERVE = 300_000                  # probes, the live uses during the month, mistakes
X3_TO_RESERVE = 231_630            # X3's credits, assigned to the reserve by the owner (Sep 28)
FLOOR = RESERVE + X3_TO_RESERVE    # 531,630: `markets odds5m --floor`, the account balance no run goes below
DAY_ONE = pd.Timestamp("2026-10-01", tz="UTC")
DROPPED = {"X3"}
PROBE = 10_700                     # ~10,400 /events sweeps at 1 credit + 7 billing and coverage probes (<= 270)
NBA_WEEK_SNAPS = 754               # schedule A, Jan 5-11, 2026 (sharp-markets/docs/PLAN.md s3)
N1_SEASON_SNAPS = 49_398           # schedule D, the full 2025-26 season (PLAN.md s3)
# Free counts from the plan review (Appendix B): games in 2024-25 whose observed weather met the registered
# trigger at an open venue. MLB 146 (ERA5 first-pitch temperature >= 90 F); soccer about 225 league matches
# plus about 47 tournament matches (19:00-local heat index >= 90 F). The day-1 forecast counts replace them.
HEAT_QUALIFYING = {"HB1": 146, "HS1": 225 + 47}
TIERS = ["day_one", "gated", "march", "replaced", "dropped", "deferred"]

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
    """Exact NFL/CFB counts from odds_budget.py (2026 = 2025 stand-in), plus by_oct1: the 2026 games
    that had kicked off before Oct 1, 2026 and their snapshot counts (what day one can actually pull)."""
    import odds_budget as ob
    nfl, cfb = ob.nfl_games(), ob.cfb_games()
    out = {}
    for name, d in (("NFL", nfl), ("CFB", cfb)):
        daily = ob.per_season(d, lambda x: len(ob.grid(x.kick, 7 * ob.D, None, at=16)))
        hourly = ob.per_season(d, lambda x: len(ob.grid(x.kick, 7 * ob.D, ob.H)))
        games = ob.per_season(d, len)
        played = d[(d.season == 2026) & (d.kick < DAY_ONE)]
        by_oct1 = dict(daily=len(ob.grid(played.kick, 7 * ob.D, None, at=16)),
                       hourly=len(ob.grid(played.kick, 7 * ob.D, ob.H)), games=len(played))
        out[name] = dict(daily=daily, hourly=hourly, games=games, by_oct1=by_oct1)
    return out


# The act-or-drop rules (plan review section 3, with the Sep 28 research sweep's two corrections, #41 and #42).
GATES = {
    "F3a": ("Only after #41's free pre-registration, before any prop line is seen: #10 rewritten as 'the posted line "
            "sits above the empirical median of the player's outcome distribution, and the under's price is not "
            "asymmetric enough to remove the edge'; the distribution model and the de-vig method registered; the "
            "2023-25 mean-minus-median gap per market computed from player_week.parquet and kicks.parquet. Posted "
            "lines are not on disk, so the line-vs-median check itself runs on this 2025 slice."),
    "F3b": ("Only if, on the 2025 slice (F3a), the posted line sits above the empirical median in at least 3 of the "
            "4 yardage markets and the under's excess win rate over the de-vigged close is positive pooled. If the "
            "lines sit at the median, F3b moves to March and only the kicking markets (#21) stay in play."),
    "N1": ("Only if the sample week shows an H1 edge (net-of-fee edge flags with fills and positive CLV to Pinnacle's "
           "close) or an H2 lag (median catch-up lag of 10 minutes or more), exactly as PLAN.md s8 step 3 and s9 "
           "decision 2 require. Decide by about Oct 20."),
    "F4": ("Only if H16b passes on F1's daily grid (#42): a move of a point or more on day t reverses by the close, "
           "graded on CLV; fading it earns at least 0.25 points of CLV with the 95% interval above zero, in both "
           "sports, in 4 of 6 seasons. Decide by about Oct 20. H16a (fade the move at the close, graded on ROI, must "
           "beat the vig) is a separate variant with a free SBR pre-check for 2007-21; it does not unlock F4."),
    "H1": "March 2027, only if the price engine worked on football (F1's rule) and a data-use line has been written.",
    "N2": "March 2027, only if the price engine worked on football (F1's rule) and a data-use line has been written.",
    "F5": ("March 2027, only if Rule HT's re-grade at Pinnacle's close (F1, 2020-25) keeps its win rate above the "
           "break-even of the prices; the team-totals slice at the close (36,980) is the part worth having."),
    "F6": "March 2027, only if #10 passes on NFL (F3) and a 30-credit probe finds CFB props at the close.",
}


def plan():
    fb = football_counts()
    s = structured_rows()
    daily_fb = sum(sum(v["daily"].values()) for v in fb.values())
    hourly_fb = sum(sum(v["hourly"].values()) for v in fb.values())
    daily_26 = sum(v["daily"][2026] for v in fb.values())
    hourly_26 = sum(v["hourly"][2026] for v in fb.values())
    daily_oct1 = sum(v["by_oct1"]["daily"] for v in fb.values())
    hourly_oct1 = sum(v["by_oct1"]["hourly"] for v in fb.values())
    nfl_p = sum(fb["NFL"]["games"][y] for y in range(2023, 2027))      # props/alternates exist from 2023-05-03
    cfb_p = sum(fb["CFB"]["games"][y] for y in range(2023, 2027))
    nfl_25, nfl_26, nfl_oct1 = fb["NFL"]["games"][2025], fb["NFL"]["games"][2026], fb["NFL"]["by_oct1"]["games"]
    cfb_26, cfb_oct1 = fb["CFB"]["games"][2026], fb["CFB"]["by_oct1"]["games"]
    snaps = lambda sport, exclude=(): int(s[(s.sport == sport) & ~s.season.isin(exclude)].snapshots.sum())  # noqa: E731
    soccer = [n for n in s.sport.unique() if n in SOCCER_WHY]
    nba_other = snaps("NBA", exclude=("2025-26",))
    f3_snap = HIST * 6 * 2                                              # 6 prop markets at T-24h and the close

    P = [  # id, tier, pull, arithmetic, credits, credits_2026, credits_2026_by_oct1, value (1-5), primary hypothesis
        ("P0", "day_one", "Probe: key check (free), historical /events sweeps for all 16 sport keys (exact schedules), "
         "7 billing and coverage probes (NFL billing x4; NCAAF 2020, MLB 2024 and MLS 2024 featured closes)",
         "~10,400 sweeps x 1 + 7 probes at <= 30-60", PROBE, 0, 0, 5,
         "Settles the billing multiplier, Pinnacle's NCAAF history in 2020, and MLB and MLS totals history"),
        ("F1", "day_one", "NFL+CFB featured, 10 books, daily 16:00 UTC for 7 days pre-kickoff + every close, 2020-26",
         f"{PER_SNAP} x {daily_fb:,} snapshots", PER_SNAP * daily_fb, PER_SNAP * daily_26, PER_SNAP * daily_oct1, 4,
         "Price engine (#8); Rule HT and Rule B re-graded at Pinnacle's close; H16a and H16b (#16, #42)"),
        ("F2", "day_one", "NFL alternate spreads and alternate totals at T-24h and the close, 2023-26 "
         "(no T-2h snapshot: no hypothesis; no team totals: the M4 pre-check failed)",
         f"10 x 2 mkts x 2 snaps x {nfl_p:,} games", HIST * 2 * 2 * nfl_p, HIST * 2 * 2 * nfl_26, HIST * 2 * 2 * nfl_oct1, 3,
         "Alternate lines misprice key-number crossings vs recent-era margins"),
        ("N0", "day_one", "NBA sample week Jan 5-11, 2026 at schedule A, h2h, 3 sharp books "
         "(`markets odds-pull --schedule A`, PLAN.md s8; the snapshots land in N1's cache)",
         f"10 x {NBA_WEEK_SNAPS} snapshots", HIST * NBA_WEEK_SNAPS, 0, 0, 4,
         "H1/H2 on the sample week: the gate for N1"),
        ("HB1", "day_one", "MLB heat closes: 10 books at the close of each 2024-25 game whose day-1 forecast temperature "
         "at first pitch is >= 90 F at an open park (`markets weather qualifying` lists them first)",
         f"{PER_SNAP} x <= {HEAT_QUALIFYING['HB1']} qualifying games, one close slot each (upper bound)",
         PER_SNAP * HEAT_QUALIFYING["HB1"], 0, 0, 2,
         "B-H1, descriptive only (HEAT_HYPOTHESES.md amendment 4): the over's record at Pinnacle's close in hot games"),
        ("HS1", "day_one", "Soccer heat closes: 10 books at the close of each 2024-25 league or tournament match whose "
         "day-1 forecast heat index at kickoff is >= 90 F at an open venue",
         f"{PER_SNAP} x <= {HEAT_QUALIFYING['HS1']} qualifying matches, one close slot each (upper bound)",
         PER_SNAP * HEAT_QUALIFYING["HS1"], 0, 0, 2,
         "S-H1, descriptive only (amendment 4): the under's record at Pinnacle's close in hot matches"),
        ("F3a", "gated", "NFL props: pass/rush/rec yds, receptions, kicking points, FGs made at T-24h and the close, "
         "the 2025 season", f"{f3_snap} x {nfl_25:,} games", f3_snap * nfl_25, 0, 0, 3,
         "#10 as rewritten by #41: the posted line sits above the empirical median; kicking-points unders in wind/cold (#21)"),
        ("F3b", "gated", "NFL props, the same markets and snapshots, 2023-24 and the 2026 games played",
         f"{f3_snap} x {nfl_p - nfl_25:,} games", f3_snap * (nfl_p - nfl_25), f3_snap * nfl_26, f3_snap * nfl_oct1, 3,
         "#10 on 2023-25 (act if the under beats the de-vigged close with p < 0.01 in each year and each market)"),
        ("N1", "gated", "NBA 2025-26 at 5-min resolution, h2h, 3 sharp books (PLAN.md schedule D), less the sample week",
         f"10 x ({N1_SEASON_SNAPS:,} - {NBA_WEEK_SNAPS}) snapshots", HIST * (N1_SEASON_SNAPS - NBA_WEEK_SNAPS), 0, 0, 2,
         "H1/H2 on the full season (PLAN.md)"),
        ("F4", "gated", "NFL+CFB featured, 10 books, HOURLY for 7 days pre-kickoff, 2020-26, net of F1 "
         "(every F1 snapshot is on the hourly grid and shares the cache)",
         f"{PER_SNAP} x ({hourly_fb:,} - {daily_fb:,}) snapshots", PER_SNAP * (hourly_fb - daily_fb),
         PER_SNAP * (hourly_26 - daily_26), PER_SNAP * (hourly_oct1 - daily_oct1), 3,
         "Hour-to-hour moves reverse before the close (#16); only worth asking if H16b holds daily"),
        ("H1", "march", "NHL featured (moneyline, puck line, totals), daily + every close, 2020-26 (estimate)",
         f"{PER_SNAP} x {snaps('NHL'):,} snapshots (estimate)", PER_SNAP * snaps("NHL"), 0, 0, 2,
         "Soft-price flags at the best price (the price engine on a second sport)"),
        ("N2", "march", "NBA featured, daily + every close, seasons other than 2025-26 (estimate)",
         f"{PER_SNAP} x {nba_other:,} snapshots (estimate)", PER_SNAP * nba_other, 0, 0, 2,
         "Soft-price flags at the best price (the price engine on a second sport)"),
        ("F5", "march", "CFB alternate lines and team totals at T-24h and close, 2023-26",
         f"10 x 3 mkts x 2 snaps x {cfb_p:,} games", HIST * 3 * 2 * cfb_p, HIST * 3 * 2 * cfb_26, HIST * 3 * 2 * cfb_oct1, 2,
         "Rule HT-style shrinkage shows up in team totals and alternates"),
        ("F6", "march", "CFB props (4 yardage markets) at the close, 2023-26 (upper bound; thin coverage)",
         f"10 x 4 mkts x {cfb_p:,} games", HIST * 4 * cfb_p, HIST * 4 * cfb_26, HIST * 4 * cfb_oct1, 1,
         "Median-vs-mean props in CFB"),
        ("B1", "replaced", "MLB featured (moneyline, run line, totals), daily + every close, 2020-26 (estimate)",
         f"{PER_SNAP} x {snaps('MLB'):,} snapshots (estimate)", PER_SNAP * snaps("MLB"), 0, 0, 3,
         "Replaced by HB1 on Sep 29 (#38): heat is descriptive and closes-only, so the full history buys nothing"),
        ("S1", "replaced", "Soccer heat leagues and tournaments, featured (h2h 3-way, spreads, totals), daily + every close",
         f"{PER_SNAP} x {sum(snaps(n) for n in soccer):,} snapshots (estimate)",
         PER_SNAP * sum(snaps(n) for n in soccer), 0, 0, 3, "Replaced by HS1 on Sep 29 (#38), for the same reason"),
        ("X3", "dropped", "Exchange book group (Kalshi, Polymarket, Novig, ProphetX), hourly, 2025",
         "10 x 3 x 7,721 snapshots", 231_630, 0, 0, 1, "Better data is free from Kalshi and Polymarket directly"),
        ("X2", "deferred", "5-min NFL+CFB totals for 72h before windy kickoffs, 2024-25",
         "10 x 1 x 70,558 snapshots", 705_580, 0, 0, 1, "Forecast-run timing; needs run-issue timestamps first (#40)"),
    ]
    p = pd.DataFrame(P, columns=["id", "tier", "pull", "arithmetic", "credits", "credits_2026", "credits_2026_by_oct1",
                                 "value", "primary_hypothesis"])
    p["gate"] = p.id.map(GATES).fillna("")
    p["dropped"] = p.id.isin(DROPPED)
    p["in_plan"] = p.tier.isin(["day_one", "gated"])          # what the October month may buy
    p["cumulative"] = p.credits.where(p.in_plan, 0).cumsum()
    return p, s, dict(daily_fb=daily_fb, hourly_fb=hourly_fb, nfl_p=nfl_p, cfb_p=cfb_p, daily_26=daily_26,
                      daily_oct1=daily_oct1, hourly_26=hourly_26, hourly_oct1=hourly_oct1)


def totals(p):
    """The figures the docs quote. Upper bounds count a full 2026 season; 'on Oct 1' removes the 2026 games
    not yet played, which a March month completes."""
    remainder = p.credits_2026 - p.credits_2026_by_oct1
    day = p[p.tier == "day_one"]
    gated = p[p.tier == "gated"]
    return {
        "day_one_upper": int(day.credits.sum()),
        "day_one_on_oct1": int(day.credits.sum() - remainder[day.index].sum()),
        "gated_upper": int(gated.credits.sum()),
        "month_max_upper": int(day.credits.sum() + gated.credits.sum()),
        "march_completion_without_f4": int(remainder[p.id.isin(["F1", "F2", "F3b"])].sum()),
        "march_completion_f4": int(remainder[p.id == "F4"].sum()),
        "march_pulls": int(p[p.tier == "march"].credits.sum()),
        "unallocated_if_every_gate_passes": int(5_000_000 - FLOOR - day.credits.sum() - gated.credits.sum()),
    }


def live_month():
    """Live uses during and after the month (credits per month; live calls are 1x, not 10x)."""
    rows = [
        ("Alerts, NFL + CFB (10 books a call)", "4 runs x 31 days x 2 sports", 248),
        ("Close capture (one call per kickoff slot)", "~137 NFL + CFB slots", 137),
        ("Trigger poller: every 10 min while a Rule B wind trigger is active", "~6 polls/h x 72 h x ~6 trigger windows", 2_600),
        ("NFL props, alternates, team totals log (event odds)", "70 games x 9 mkts x 4 snaps", 70 * 9 * 4),
        # As shipped (sharp-markets/config/sports/nba.yaml): a 56 h window before each tip, so in season
        # some game is always inside it and every 5-minute tick acts: 288 a day, 30-31 days (8,640-8,928).
        # One-minute final-2h ticks, if turned on, add up to ~205 a game day (27 game days).
        ("NBA collector, PLAN.md s7 (5-min h2h ticks, 56 h window; + 1-min final 2 h if on)",
         "288 ticks x 31 days + 27 game days x 0-205", 288 * 31 + 27 * 205),
    ]
    return pd.DataFrame(rows, columns=["live use", "arithmetic", "credits_per_month"])


def main(save=True):
    p, s, c = plan()
    live = live_month()
    t = totals(p)
    if save:
        p.to_csv(OUT / "odds_5m_plan.csv", index=False)
        s.to_csv(OUT / "odds_5m_seasons.csv", index=False)
        live.to_csv(OUT / "odds_5m_live.csv", index=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 95)
    print("\n5M month, the reviewed design (owner decisions Sep 28, #38). Credits are upper bounds; football counts a "
          "full 2026 season as 2025's stand-in.")
    print(p[["id", "tier", "value", "credits", "credits_2026", "credits_2026_by_oct1", "cumulative", "pull"]].to_string(index=False))
    print(f"\nDay one (P0, F1, F2, N0, HB1, HS1): {t['day_one_upper']:,} upper bound; {t['day_one_on_oct1']:,} exists on "
          f"Oct 1 (cap {DAY_ONE_CAP:,}: {'ok' if t['day_one_upper'] < DAY_ONE_CAP else 'OVER'})")
    print(f"Gated inside the month (F3a, F3b, N1, F4): {t['gated_upper']:,}; day one plus every gate {t['month_max_upper']:,} "
          f"against the {CEILING:,} ceiling ({'ok' if t['month_max_upper'] <= CEILING else 'OVER'})")
    print(f"Floor {FLOOR:,} ({RESERVE:,} plus X3's {X3_TO_RESERVE:,}); unallocated if every gate passes "
          f"{t['unallocated_if_every_gate_passes']:,}")
    print(f"March 2027: the 2026 completions, {t['march_completion_without_f4']:,} for F1, F2 and F3b, plus "
          f"{t['march_completion_f4']:,} for F4 if it was earned; the March pulls (H1, N2, F5, F6) {t['march_pulls']:,} "
          f"upper bound, each behind its gate")
    print("\nGates (verbatim in odds-api-credits.md):")
    for _, r in p[p.gate != ""].iterrows():
        print(f"  {r.id}: {r.gate}")
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
