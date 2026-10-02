"""Synthetic regressions for PR 104; no scores, cohorts, credentials or fitting."""
from collections import Counter
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from markets.research.price_engine import engine, quotes

NFL = 'americanfootball_nfl'
CFG = {'sports': {NFL: {'windows': [{'from': date(2024, 1, 1), 'to': date(2024, 12, 31),
                                    'label': '2024', 'sealed': False}]}}}


def rows(eid, snap, kick, home='H', away='A', market='totals'):
    names = ('Over', 'Under') if market == 'totals' else (home, away)
    return [dict(sport=NFL, odds_event_id=eid, snapshot_ts=snap, commence_time=kick,
                 home_team=home, away_team=away, bookmaker='draftkings', market_key=market,
                 market_last_update=snap, book_last_update=snap, outcome_name=name,
                 point=44.5 if market == 'totals' else (-3.5 if name == home else 3.5)
                 if market == 'spreads' else None, price_decimal=1.91) for name in names]


def load(monkeypatch, batch, cache=None):
    monkeypatch.setattr(quotes.bulk, 'load_rows', lambda *a, **k: batch)
    return quotes.load_quotes(CFG, [object()], cache)


def entries(q):
    v = next(v for v in engine.VARIANTS if v.sport == NFL and v.market == 'totals' and v.primary)
    return engine.entries(q.assign(side='under', dec=1.91, ev_pinnacle=.03,
                                   ev_blend=.03, pin_line=44.5), v)


def test_later_correction_cannot_admit_eight_day_old_decision(monkeypatch):
    early = rows('e', '2024-09-01T16:00:00Z', '2024-09-09T16:00:00Z')
    later = rows('e', '2024-09-02T16:00:00Z', '2024-09-07T16:00:00Z')
    baseline, _ = load(monkeypatch, early)
    revised, drops = load(monkeypatch, early + later)
    assert baseline.empty
    assert list(entries(revised).snap) == [pd.Timestamp('2024-09-02T16:00:00Z')]
    assert drops['more_than_7_days_before_kickoff'] == 1


def test_two_provider_ids_cannot_create_two_entries(monkeypatch):
    q, drops = load(monkeypatch, rows('id1', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z')
                    + rows('id2', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z'))
    assert q.empty
    assert drops['multiple_provider_ids_for_game'] == 2


@pytest.mark.parametrize('market', ['h2h', 'spreads', 'totals'])
def test_changed_orientation_cannot_compare_opposing_teams(monkeypatch, market):
    q, drops = load(monkeypatch, rows('swap', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z', market=market)
                    + rows('swap', '2024-09-08T18:55:00Z', '2024-09-08T19:00:00Z',
                           home='A', away='H', market=market))
    assert q.empty
    assert drops['changed_team_orientation'] == 2


def test_frozen_canonical_binding_handles_midnight_and_revised_kickoff(monkeypatch):
    cache = SimpleNamespace(canonical_event_map={(NFL, 'id1'): 'canonical', (NFL, 'id2'): 'canonical'},
                            canonical_team_aliases={(NFL, 'H'): 'team:h', (NFL, 'A'): 'team:a'})
    q, drops = load(monkeypatch, rows('id1', '2024-09-07T16:00:00Z', '2024-09-08T23:30:00Z')
                    + rows('id2', '2024-09-07T16:00:00Z', '2024-09-09T00:30:00Z'), cache)
    assert q.empty
    assert drops['multiple_provider_ids_for_game'] == 2


def test_rematch_is_not_quarantined_as_a_duplicate(monkeypatch):
    q, drops = load(monkeypatch, rows('week1', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z')
                    + rows('week2', '2024-09-14T16:00:00Z', '2024-09-15T19:00:00Z'))
    assert len(q) == 2
    assert drops['multiple_provider_ids_for_game'] == 0


def test_unbound_listing_and_unknown_team_are_explicit(monkeypatch):
    cache = SimpleNamespace(canonical_event_map={(NFL, 'known'): 'canonical'},
                            canonical_team_aliases={(NFL, 'H'): 'team:h'})
    q, drops = load(monkeypatch, rows('unknown', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z')
                    + rows('known', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z'), cache)
    assert q.empty
    assert drops['unbound_or_ambiguous_canonical_game'] == 1
    assert drops['unresolved_canonical_team'] == 1


def test_stable_single_listing_keeps_its_prices_and_canonical_id(monkeypatch):
    cache = SimpleNamespace(canonical_event_map={(NFL, 'provider'): 'canonical'},
                            canonical_team_aliases={(NFL, 'H'): 'team:h', (NFL, 'A'): 'team:a'})
    q, drops = load(monkeypatch, rows('provider', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z',
                                    market='spreads'), cache)
    assert len(q) == 1 and q.iloc[0].event_id == 'canonical'
    assert (q.iloc[0].home, q.iloc[0].away, q.iloc[0].line, q.iloc[0].dec_a) == ('H', 'A', -3.5, 1.91)
    assert not any(drops.values())


def test_known_aliases_must_match_the_bound_game_teams(monkeypatch):
    cache = SimpleNamespace(canonical_event_map={(NFL, 'provider'): 'canonical'},
                            canonical_team_aliases={(NFL, 'H'): 'team:h', (NFL, 'A'): 'team:a'},
                            canonical_game_teams={'canonical': frozenset(('team:h', 'team:other'))})
    q, drops = load(monkeypatch, rows('provider', '2024-09-07T16:00:00Z', '2024-09-08T19:00:00Z'), cache)
    assert q.empty and drops['unresolved_canonical_team'] == 1
