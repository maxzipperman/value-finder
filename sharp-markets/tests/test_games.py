from markets.games import build_games
from markets.sport import load_sport, load_teams


def _market(event, suffix, exp="2026-01-08T05:30:00Z", result="yes", value=None):
    return {"ticker": f"{event}-{suffix}", "event_ticker": event, "title": "x Winner?", "yes_sub_title": suffix,
            "open_time": "2026-01-05T19:06:00Z", "close_time": "2026-01-08T05:15:52Z",
            "expected_expiration_time": exp, "settlement_ts": "2026-01-08T05:20:00Z", "status": "finalized",
            "result": result, "settlement_value_dollars": value, "volume_fp": "10.00", "_endpoint": "historical"}


def test_build_games_parsing_phases_and_exclusions():
    cfg, teams = load_sport("nba"), load_teams("nba")
    events = [{"event_ticker": "KXNBAGAME-26JAN07LALSAS", "title": "Los Angeles L at San Antonio"},
              {"event_ticker": "KXNBAGAME-26APR18HOULAL", "title": "Game 1: Houston at Los Angeles L"},
              {"event_ticker": "KXNBAGAME-25OCT10SACPOR", "title": "Sacramento vs Portland"},
              {"event_ticker": "KXNBAGAME-26JAN08MIACHI", "title": "Miami vs Chicago"}]
    markets = [_market("KXNBAGAME-26JAN07LALSAS", "SAS"), _market("KXNBAGAME-26JAN07LALSAS", "LAL", result="no"),
               _market("KXNBAGAME-26APR18HOULAL", "HOU"), _market("KXNBAGAME-26APR18HOULAL", "LAL"),
               _market("KXNBAGAME-25OCT10SACPOR", "SAC"), _market("KXNBAGAME-25OCT10SACPOR", "POR"),
               _market("KXNBAGAME-26JAN08MIACHI", "MIA", result="scalar", value="0.6900"),
               _market("KXNBAGAME-26JAN08MIACHI", "CHI", result="scalar", value="0.3100")]
    g = {x.game_id: x for x in build_games(cfg, teams, events, markets)}
    lal = g["KXNBAGAME-26JAN07LALSAS"]
    assert (lal.away_code, lal.home_code, lal.phase, lal.split) == ("LAL", "SAS", "regular", "train")
    assert lal.kalshi_est_tip.isoformat() == "2026-01-08T02:30:00+00:00"            # expected_expiration - 3h
    assert not lal.exclusions
    assert g["KXNBAGAME-26APR18HOULAL"].phase == "playoffs" and g["KXNBAGAME-26APR18HOULAL"].excluded
    assert g["KXNBAGAME-25OCT10SACPOR"].phase == "preseason"
    mia = g["KXNBAGAME-26JAN08MIACHI"]
    assert not mia.excluded                                           # market-level exclusion, not game-level
    assert {r for r, m, _ in mia.exclusions} == {"scalar_settlement"} and len(mia.exclusions) == 2


def test_malformed_event_is_logged_not_dropped():
    cfg, teams = load_sport("nba"), load_teams("nba")
    markets = [_market("KXNBAGAME-26JAN07LALSAS", "SAS")]            # only one market
    (g,) = build_games(cfg, teams, [], markets)
    assert g.excluded and any(r == "malformed_event" for r, _, _ in g.exclusions)
