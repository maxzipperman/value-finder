"""SQL for typed tables and analysis views. Every table carries `sport`; all timestamps are TIMESTAMPTZ (UTC)."""
from __future__ import annotations

OHLC = ("open", "high", "low", "close")


def _px(obj: str, side: str, k: str) -> str:
    return f"CAST(coalesce({obj}->'{side}'->>'{k}_dollars', {obj}->'{side}'->>'{k}') AS DECIMAL(6,4))"


def candles_sql(sport: str, glob: str) -> str:
    cols = [f"{_px('c', side, k)} AS {side}_{k}" for side in ("yes_bid", "yes_ask") for k in OHLC]
    cols += [f"{_px('c', 'price', k)} AS price_{k}" for k in (*OHLC, "mean", "previous")]
    return f"""
    CREATE OR REPLACE TABLE kalshi_candles AS
    WITH r AS (
      SELECT json_extract_string(params_json, '$.market_ticker') AS market_ticker,
             json_extract_string(params_json, '$.endpoint') AS endpoint,
             CAST(json_extract_string(params_json, '$.period_interval') AS SMALLINT) AS period_min,
             unnest(json_extract(body, '$.candlesticks[*]')) AS c
      FROM read_parquet('{glob}') WHERE http_status = 200
    ), x AS (
      SELECT '{sport}' AS sport, market_ticker, period_min,
             to_timestamp(CAST(c->>'end_period_ts' AS BIGINT)) AS end_ts,
             {", ".join(cols)},
             CAST(coalesce(c->>'volume_fp', c->>'volume') AS DECIMAL(18,2)) AS volume,
             CAST(coalesce(c->>'open_interest_fp', c->>'open_interest') AS DECIMAL(18,2)) AS open_interest,
             endpoint
      FROM r
    )
    SELECT DISTINCT ON (sport, market_ticker, period_min, end_ts) * FROM x
    ORDER BY sport, market_ticker, period_min, end_ts
    """


def trades_sql(sport: str, glob: str) -> str:
    return f"""
    CREATE OR REPLACE TABLE kalshi_trades AS
    WITH r AS (
      SELECT unnest(json_extract(body, '$.trades[*]')) AS t FROM read_parquet('{glob}') WHERE http_status = 200
    )
    SELECT DISTINCT ON (trade_id) '{sport}' AS sport, t->>'trade_id' AS trade_id, t->>'ticker' AS market_ticker,
           CAST(t->>'created_time' AS TIMESTAMPTZ) AS created_time,
           CAST(coalesce(t->>'count_fp', t->>'count') AS DECIMAL(18,2)) AS count,
           CAST(t->>'yes_price_dollars' AS DECIMAL(6,4)) AS yes_price,
           CAST(t->>'no_price_dollars' AS DECIMAL(6,4)) AS no_price,
           coalesce(t->>'taker_outcome_side', t->>'taker_side') AS taker_outcome_side,
           t->>'taker_book_side' AS taker_book_side,
           coalesce(CAST(t->>'is_block_trade' AS BOOLEAN), false) AS is_block_trade
    FROM r ORDER BY trade_id
    """


# Trades are bucketed to the candle whose inclusive end_ts covers them: (T - 1 min, T].
YES_TAKER_1M = """
CREATE OR REPLACE TABLE kalshi_yes_taker_1m AS
SELECT sport, market_ticker,
       date_trunc('minute', created_time - INTERVAL 1 MICROSECOND) + INTERVAL 1 MINUTE AS minute_end_ts,
       coalesce(sum(count) FILTER (WHERE taker_outcome_side = 'yes'), 0) AS yes_taker_volume,
       sum(count) AS all_volume,
       sum(count * yes_price) / sum(count) AS vwap_yes
FROM kalshi_trades WHERE NOT is_block_trade
GROUP BY ALL
"""

SHARP_ODDS = """
CREATE OR REPLACE TABLE sharp_odds AS
SELECT DISTINCT ON (sport, snapshot_ts, odds_event_id, bookmaker, market_key, outcome_name)
       sport, CAST(snapshot_ts AS TIMESTAMPTZ) AS snapshot_ts, CAST(requested_ts AS TIMESTAMPTZ) AS requested_ts,
       odds_event_id, CAST(commence_time AS TIMESTAMPTZ) AS commence_time, home_team, away_team, home_code, away_code,
       bookmaker, CAST(book_last_update AS TIMESTAMPTZ) AS book_last_update, market_key,
       CAST(market_last_update AS TIMESTAMPTZ) AS market_last_update, outcome_name, team_code,
       CAST(price_decimal AS DECIMAL(8,4)) AS price_decimal, origin
FROM stg_sharp_odds
ORDER BY sport, snapshot_ts, odds_event_id, bookmaker, market_key, outcome_name, requested_ts
"""


def sharp_fair_sql(weights: dict[str, float]) -> str:
    values = ", ".join(f"('{b}', {w})" for b, w in weights.items())
    return f"""
    CREATE OR REPLACE TABLE sharp_book_fair AS
    WITH o AS (
      SELECT * FROM sharp_odds WHERE market_key = 'h2h' AND team_code IS NOT NULL AND price_decimal > 1
    ), s AS (
      SELECT sport, snapshot_ts, odds_event_id, bookmaker, count(*) AS n_outcomes,
             sum(1.0 / CAST(price_decimal AS DOUBLE)) AS overround
      FROM o GROUP BY ALL
    )
    SELECT o.sport, o.snapshot_ts, o.odds_event_id, o.bookmaker, o.team_code, o.market_last_update,
           (1.0 / CAST(o.price_decimal AS DOUBLE)) / s.overround AS fair, s.overround
    FROM o JOIN s USING (sport, snapshot_ts, odds_event_id, bookmaker)
    WHERE s.n_outcomes = 2;

    CREATE OR REPLACE TABLE sharp_fair AS
    SELECT f.sport, f.snapshot_ts, f.odds_event_id, f.team_code,
           max(fair) FILTER (WHERE bookmaker = 'pinnacle') AS pin_fair,
           max(fair) FILTER (WHERE bookmaker = 'lowvig') AS lowvig_fair,
           max(fair) FILTER (WHERE bookmaker = 'betonlineag') AS bol_fair,
           sum(fair * w) / sum(w) AS blend_fair,
           CASE WHEN count(*) > 1 THEN stddev_samp(fair) ELSE 0 END AS blend_std,
           string_agg(bookmaker, ',' ORDER BY bookmaker) AS books_used,
           max(market_last_update) FILTER (WHERE bookmaker = 'pinnacle') AS pin_last_update
    FROM sharp_book_fair f JOIN (VALUES {values}) AS wts(bookmaker, w) USING (bookmaker)
    GROUP BY ALL;
    """


def analysis_sql(*, fair_source: str, ffill_max_min: int, sharp_max_min: int, taker_rate: float) -> str:
    """1-minute pre-game grid per market (open -> commence + 15m). No lookahead: every ASOF join is `<= ts`."""
    fair_col = {"pinnacle": "pin_fair", "blend": "blend_fair"}[fair_source]
    move_joins, move_cols = [], []
    for n in (5, 15, 30, 60):
        move_joins.append(f"""
        ASOF LEFT JOIN (SELECT sport, odds_event_id, team_code, snapshot_ts AS snap_{n}, pin_fair AS pin_fair_{n}
                        FROM sharp_fair) f{n}
          ON s.sport = f{n}.sport AND s.odds_event_id = f{n}.odds_event_id AND s.team_code = f{n}.team_code
         AND s.ts_minus_{n} >= f{n}.snap_{n}""")
        move_cols.append(f"""CASE WHEN epoch(s.ts_minus_{n} - f{n}.snap_{n}) / 60 <= {sharp_max_min}
                              AND epoch(s.ts - s.sharp_snapshot_ts) / 60 <= {sharp_max_min}
                             THEN s.pin_fair - f{n}.pin_fair_{n} END AS sharp_move_last_{n}min""")
    # The unnest(generate_series) grid gets a tiny cardinality estimate, which makes DuckDB pick a nested-loop
    # ASOF join (asof_loop_join_threshold); force the sort-merge ASOF operator (194s -> 0.6s, identical output).
    return f"""
    SET asof_loop_join_threshold = 0;
    CREATE OR REPLACE TABLE analysis_1m AS
    WITH mk AS (
      SELECT m.sport, m.market_ticker, m.game_id, m.team_code, m.team_code = g.home_code AS is_home,
             g.odds_event_id, g.commence_time, g.split, g.fee_multiplier, g.game_date_et,
             CASE WHEN m.team_code = g.home_code THEN g.home_b2b ELSE g.away_b2b END AS b2b,
             CASE WHEN m.team_code = g.home_code THEN g.away_b2b ELSE g.home_b2b END AS opp_b2b,
             CASE m.result WHEN 'yes' THEN 1 WHEN 'no' THEN 0 END AS result, m.open_time
      FROM kalshi_markets m JOIN games g USING (sport, game_id)
      WHERE g.match_status = 'matched'
        AND NOT EXISTS (SELECT 1 FROM excluded_markets x WHERE x.sport = m.sport AND x.market_ticker = m.market_ticker)
    ), grid AS (
      SELECT mk.*, unnest(generate_series(date_trunc('minute', open_time) + INTERVAL 1 MINUTE,
                                          commence_time + INTERVAL 15 MINUTE, INTERVAL 1 MINUTE)) AS ts
      FROM mk
    ), g2 AS (
      SELECT *, ts - INTERVAL 5 MINUTE AS ts_minus_5, ts - INTERVAL 15 MINUTE AS ts_minus_15,
             ts - INTERVAL 30 MINUTE AS ts_minus_30, ts - INTERVAL 60 MINUTE AS ts_minus_60 FROM grid
    ), k AS (
      SELECT g2.*, c.end_ts AS candle_end_ts, c.yes_bid_close, c.yes_ask_close, c.yes_ask_open, c.volume AS candle_volume
      FROM g2 ASOF LEFT JOIN kalshi_candles c
        ON g2.sport = c.sport AND g2.market_ticker = c.market_ticker AND g2.ts >= c.end_ts
    ), s AS (
      SELECT k.*, f.snapshot_ts AS sharp_snapshot_ts, f.pin_fair, f.blend_fair, f.blend_std, f.books_used, f.pin_last_update
      FROM k ASOF LEFT JOIN sharp_fair f
        ON k.sport = f.sport AND k.odds_event_id = f.odds_event_id AND k.team_code = f.team_code AND k.ts >= f.snapshot_ts
    ), m AS (
      SELECT s.*, {", ".join(move_cols)}
      FROM s {" ".join(move_joins)}
    ), q AS (
      SELECT *,
        epoch(ts - candle_end_ts) / 60 AS fill_age_min,
        candle_end_ts IS DISTINCT FROM ts AS is_filled,
        epoch(ts - sharp_snapshot_ts) / 60 AS sharp_age_min,
        CASE WHEN epoch(ts - candle_end_ts) / 60 <= {ffill_max_min} THEN yes_bid_close END AS yes_bid,
        CASE WHEN epoch(ts - candle_end_ts) / 60 <= {ffill_max_min} THEN yes_ask_close END AS yes_ask
      FROM m
    )
    SELECT sport, game_id, game_date_et, market_ticker, team_code, is_home, ts, split,
           yes_bid, yes_ask,
           CASE WHEN yes_bid IS NOT NULL AND yes_ask IS NOT NULL THEN (yes_bid + yes_ask) / 2 END AS mid,
           yes_ask - yes_bid AS spread,
           CASE WHEN is_filled THEN 0 ELSE candle_volume END AS volume,
           is_filled, fill_age_min,
           CASE WHEN NOT is_filled THEN yes_ask_open END AS yes_ask_open_raw,
           CASE WHEN sharp_age_min <= {sharp_max_min} THEN pin_fair END AS pin_fair,
           CASE WHEN sharp_age_min <= {sharp_max_min} THEN blend_fair END AS blend_fair,
           CASE WHEN sharp_age_min <= {sharp_max_min} THEN {fair_col} END AS fair_prob,
           '{fair_source}' AS fair_source, blend_std, books_used,
           sharp_snapshot_ts, sharp_age_min, pin_last_update,
           CAST({taker_rate} * fee_multiplier * yes_ask * (1 - yes_ask) AS DOUBLE) AS fee_per_contract,
           CASE WHEN sharp_age_min <= {sharp_max_min} THEN
                {fair_col} - CAST(yes_ask AS DOUBLE) - CAST({taker_rate} * fee_multiplier * yes_ask * (1 - yes_ask) AS DOUBLE)
           END AS edge_vs_ask_net_of_fee,
           sharp_move_last_5min, sharp_move_last_15min, sharp_move_last_30min, sharp_move_last_60min,
           epoch(commence_time - ts) / 60 AS minutes_to_tip,
           CASE WHEN sharp_age_min <= {sharp_max_min} THEN {fair_col} > 0.5 END AS is_favorite,
           b2b, opp_b2b, result, commence_time, fee_multiplier
    FROM q
    ORDER BY sport, market_ticker, ts
    """


# Both YES asks summing below $1 is a locked profit before fees. "fresh" = both legs quoted by a candle in the
# last minute (not forward-filled); "fee_positive" = still below $1 after both taker fees.
ASK_SUM_LT_1 = """
SELECT a.sport, a.game_id, count(*) AS minutes,
       count(*) FILTER (WHERE a.minutes_to_tip > 0) AS pregame_minutes,
       min(a.ts) AS first_ts, max(a.ts) AS last_ts, min(a.yes_ask + b.yes_ask) AS min_sum,
       count(*) FILTER (WHERE a.fill_age_min <= 1 AND b.fill_age_min <= 1) AS fresh_minutes,
       count(*) FILTER (WHERE a.yes_ask + b.yes_ask + a.fee_per_contract + b.fee_per_contract < 1) AS fee_positive_minutes
FROM analysis_1m a JOIN analysis_1m b
  ON a.sport = b.sport AND a.game_id = b.game_id AND a.ts = b.ts AND a.market_ticker < b.market_ticker
WHERE a.yes_ask IS NOT NULL AND b.yes_ask IS NOT NULL AND a.yes_ask + b.yes_ask < 1
GROUP BY ALL
"""

CANDLE_TRADE_RECON = """
SELECT c.sport, c.market_ticker, sum(c.volume) AS candle_volume, coalesce(sum(t.all_volume), 0) AS trade_volume,
       sum(c.volume) - coalesce(sum(t.all_volume), 0) AS diff
FROM kalshi_candles c
LEFT JOIN kalshi_yes_taker_1m t ON c.sport = t.sport AND c.market_ticker = t.market_ticker AND c.end_ts = t.minute_end_ts
GROUP BY ALL
"""
