"""Pure settlement primitives; no file/network reads or claims of executable ROI.

NFL column provenance: nfl-weather/scripts/build_player_week.py KEEP. CFB has no
reviewed player outcome source here and is explicitly unsupported. Mapping a column
is not authority to grade: callers must verify matching, participation and book
settlement terms. Absence of a weekly row is NOT a general sportsbook void rule.
"""
from dataclasses import dataclass
import math

NFL = 'americanfootball_nfl'
CFB = 'americanfootball_ncaaf'
# Explicit prospective mappings only; primary grader still uses its four registered markets.
NFL_COLUMNS = {
    'player_reception_yds': ('receiving_yards',),
    'player_rush_yds': ('rushing_yards',),
    'player_pass_yds': ('passing_yards',),
    'player_receptions': ('receptions',),
    'player_field_goals': ('fg_made',),
    'player_kicking_points': ('fg_made', 'pat_made'),
}


@dataclass(frozen=True)
class Settlement:
    status: str
    win: int | None = None
    profit_per_unit: float | None = None


def number(value):
    if isinstance(value, bool): return None
    try: result = float(value)
    except (TypeError, ValueError): return None
    return result if math.isfinite(result) else None


def statistic(sport, market, stats):
    """Explicit supported mappings; do not trust precomputed kicking_points with null-fill."""
    if sport != NFL or market not in NFL_COLUMNS:
        return None, 'unsupported_sport_or_market'
    values = [number(stats.get(c)) for c in NFL_COLUMNS[market]]
    if any(v is None for v in values): return None, 'missing_statistic'
    if market == 'player_kicking_points': return 3 * values[0] + values[1], ''
    return values[0], ''


def settle(*, side, line, decimal_price, value, participation, terms_verified=False):
    """participation: eligible, void, or unknown, established by market/book terms.

    Never create the complementary side from a one-sided listing. The caller passes
    the offered side and its own price. Push/void returns stake, hence profit zero.
    """
    if not terms_verified: return Settlement('unverified_settlement_terms')
    if side not in ('Over', 'Under'): return Settlement('unsupported_side')
    line, price = number(line), number(decimal_price)
    if line is None or price is None or price <= 1: return Settlement('invalid_quote')
    if participation == 'void': return Settlement('void', profit_per_unit=0.)
    if participation != 'eligible': return Settlement('unknown_participation')
    value = number(value)
    if value is None: return Settlement('missing_statistic')
    if value == line: return Settlement('push', profit_per_unit=0.)
    win = int(value > line if side == 'Over' else value < line)
    return Settlement('settled', win, price - 1 if win else -1.)


def exposure_key(*, sport, season, game_id, player_id, market):
    """Dependence group excludes book/time/side/line, not a deduplication or trial count."""
    if season not in (2023, 2024, 2025): raise ValueError('Unsupported or sealed season')
    if not all((sport, game_id, player_id, market)): raise ValueError('Unresolved exposure identity')
    return sport, season, game_id, player_id, market
