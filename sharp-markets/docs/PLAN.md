# Sharp-vs-Kalshi research pipeline — NBA-first, sport-agnostic (PAPER ONLY)

## Context
Research-only pipeline to test "follow the sharps" on Kalshi NBA game markets. H1 tests static edge against Pinnacle's de-vigged price. H2 tests whether Kalshi lags after sharp moves. H3 tests whether betting splits confirm H2.

The project pivoted from MLB to NBA (the 2026-27 season opens Oct 20, 2026). The code is sport-agnostic so MLB, CBB and CFB can plug in later. **No order-placement code, ever.** The Kalshi client is GET-only and a test enforces it.

Everything below was verified live on 2026-09-27 against the Kalshi public API and OpenAPI spec, The Odds API docs, the reference repos, and PyPI/Kaggle metadata. Nothing has been downloaded or built yet.

---

## 1. NBA discovery findings (verified)

| Item | Finding |
|---|---|
| Series | **`KXNBAGAME`** ("NBA Game"). Fee type `quadratic_with_maker_fees`, multiplier **1**. `/series/fee_changes?show_historical=true` shows **no changes**. `KXNBAMATCHUP` is series futures, not games. |
| Discovery path | `GET /events?series_ticker=KXNBAGAME` returns all seasons' events (1,451). Markets settled before the cutoff come from `GET /historical/markets?series_ticker=` (nested markets are omitted for archived events). The historical cutoff is `market_settled_ts = 2026-07-29`, so **all of 2025-26 is on /historical**. 2026-27 will be live, so the router is still needed. |
| Coverage | KXNBAGAME started with the 2024-25 playoffs (Apr 2025). The 2025-26 season starts **Oct 10, 2025 with preseason** (43 events, incl. a Guangzhou exhibition `GUA`). Opening night is Oct 21, 2025. There are 1,363 events (2 markets each): **1,233 regular season** (incl. the NBA Cup final), 6 play-in, ~81 playoffs, 43 preseason. 2026-27 opening-night events (Oct 20) are **already listed**; 2026 preseason is not listed yet (last year it started Oct 10). |
| Ticker format | `KXNBAGAME-{YY}{MON}{DD}{AWAY}{HOME}` then `-{TEAM}`. **Away first**: 117/117 checked against ESPN. There is **no time in the ticker** (unlike MLB 2026), no G1/G2, no bare-"2" relists, and zero non-standard tickers. |
| Tip-off rule | Rules text has the date only, and `occurrence_datetime` is set on only 164/2,726 markets. **`expected_expiration_time − 3h` = ESPN tip on 115/117** (the other 2 are off by 17 min), and `expiration_time − 14d` gives the same result. So the MLB 3h rule does hold for NBA, but it's used **only for candidate matching**. Odds API `commence_time` is the source of truth. |
| Team codes | Suffixes are consistent 3-letter codes (`GSW NYK PHX SAS NOP WAS BKN UTA CHA`…), with no GS/NY/PHO/SA variants in 2024-25 or 2025-26 (those variants are ESPN's). **Display names are inconsistent:** LAC shows as "LA" or "Los Angeles C", LAL as "Los Angeles" or "Los Angeles L", NYK as "New York" or "New York K". Title order varies ("A at B" ×698, "A vs B" ×578). So we never parse the team from display text; we use the ticker suffix. |
| Phase markers | Play-in title is `"East/West Play-In: …"`; playoffs title is `"Game N: …"`. **Kalshi does not mark NBA Cup games** (ESPN notes do, e.g. "NBA Cup - Quarterfinals"). |
| Lifetime | Median 2.44 days (markets open ~56h before tip; p5 41h, p95 80h). **The MLB ">3 days = not a game" rule does not carry over.** 62 regular-season markets exceed 3 days (opening week, All-Star break, holidays). So lifetime only produces a flag (>14 days), never an exclusion. |
| Postponements | 3 games settled at a **scalar fair price**: MIA@CHI Jan 8 (court condensation) **is in the sample week**, plus DAL@MIL and DEN@MEM on Jan 25. 1,233 events vs 1,231 expected (1,230 + Cup final) suggests relisted makeups; I'll reconcile this during the build. |
| Candles | 1-minute candles are **sparse** (only minutes with activity). The cap is 5,000 candles per request. Historical responses use `close`/`volume`/`open_interest`; live responses use `close_dollars`/`volume_fp`/`open_interest_fp`. Prices are 4dp dollar strings on a 1¢ grid. |
| Trades | `GET /historical/trades?ticker=` is public and returns `count_fp`, `yes_price_dollars`, `taker_outcome_side`, `taker_book_side`, `is_block_trade`. |
| Rate limit | Basic tier is 200 tokens/s and a GET costs 10 tokens (about 20 req/s). The pipeline defaults to 10 req/s with backoff on 429/5xx that honors `Retry-After`. |

MLB note, for later: the 13 bare-"2" events are all on 2025-04-18. They are the real markets. Their 8 un-suffixed twins opened a day late, sat open until 2026-03-25, and traded only 5–262 contracts.

## 2. Evaluation of your additional sources (nothing downloaded)

| Source | Findings | Recommendation |
|---|---|---|
| **Kaggle `caseydurfee/mgm-grand-nba-betting-data`** | **CC BY-SA 4.0**. One file, `all_odds.csv` (1.6 MB). Covers 2021-22 through 2025-26 up to the All-Star break (2026-02-12), regular season and playoffs. Has ML, spread and total, each with `*_wager_percentage` (tickets), `*_stake_percentage` (money), closing odds, and a won flag. Scraped from Yahoo's internal API, so provenance is a caveat. Closing only, single retail book. | **Use it for the early H3 test.** Needs your Kaggle API token. Share-alike applies only if we redistribute derivatives. Overlaps our Kalshi train window (Oct 21 – Feb 12), so the splits can join to Kalshi games. |
| **Jon-Becker/prediction-market-analysis** | Code is MIT. The 36 GiB `.tar.zst` has no published index, so NBA coverage **can't be confirmed without downloading**. Its Kalshi trades schema (`count`, cents `yes_price`, `taker_side`, `created_time`) mirrors Kalshi's public trades API. | **Don't download.** Kalshi's own `/historical/trades` is free, per ticker, and richer (book side, block flag, fixed-point counts). Use it for the candle-volume cross-check. |
| **agenttrader** (PyPI 0.4.1) **+ pmxt** (2.54) | agenttrader has had 9 releases, all between Feb 24 and Mar 4, 2026 (stale about 7 months). It needs Python ≥3.12, has heavy dependencies (FastAPI, SQLAlchemy, Alembic, MCP, websockets), and backtests on Becker trade data: no bid/ask candles and no sportsbook feed. pmxt needs a hosted API key (traffic goes through api/trade.pmxt.dev, with custody escrow) or a Node sidecar, and it **ships order-placement APIs**. | **Keep our own** (~300 lines). It lacks as-of sharp joins, CLV against Pinnacle, and volume-capped ask fills, and it would pull trading code into our dependency tree. |
| **Fee model** (MarketsBot correction) | Kalshi's current **Fee Rounding** doc: the trade fee is rounded **up to $0.000001 per fill**. A rounding fee then restores balance precision ($0.01 for non-direct members), and a **per-order fee accumulator** rebates overpayment so the order total converges to a single equivalent fill. The fee-type doc confirms taker = 0.07×mult×C×P(1−P), and maker = 0.25×taker (0.5× for combo series). MarketsBot's "ceil to cent per fill" therefore **overcharges multi-fill orders**. KXMLBGAME's multiplier went 1 → 0.5 on 2026-08-07, so fees are time-varying. The fee PDF itself returned 429; I'll re-verify the 0.07 coefficient in step 0. | Implement `fee(order) = ceil_cent(0.07 × mult(t) × Σ Cᵢ·Pᵢ(1−Pᵢ))` with a `rounding=per_order\|per_fill\|none` switch for sensitivity; the default is per_order. The multiplier comes from `/series/fee_changes` plus `/events/fee_changes` overrides as of the fill time. Analysis-view edge uses the unrounded per-contract fee; backtest P&L uses the rounded fee at the actual order size. |

Reference repo `mmoore07129/mlb-kalshi-bot` (read only via the API; **I'll clone it to `./reference` on approval**). Patterns to reuse:
- **De-vig:** proportional (`h/(h+a)`) per book.
- **Blend:** weights `pinnacle .55 / lowvig .30 / betonlineag .15`, renormalized over the books present, plus `prob_std`.
- **CLV:** `close_fair − p_at_bet` and `close_fair/price − 1`, where the close is the last sharp snapshot before start.

Its `risk.py` fee has no rounding and ignores multiplier history. Not ported: `kalshi/client.py`, order and watch logic in `main.py`/`watcher.py`, and `risk.py` sizing.

## 3. Odds API: confirmed facts, resolution, credits

- **Historical odds** return the snapshot **at or before** `date`. Snapshots are every **5 min since Sep 2022** (10 min before that). Response shape is `{timestamp, previous_timestamp, next_timestamp, data}`.
- **Cost** is 10 × markets × regions. `bookmakers=` counts as one region per 10 books. So `bookmakers=pinnacle,lowvig,betonlineag&markets=h2h` costs **10 credits per snapshot**.
- **Regions:** Pinnacle is `eu`, LowVig `us`, BetOnline `us` and `eu`. The docs note that Pinnacle odds come "from public website which may incur a delay".
- **Live odds** (forward collector) cost 1 credit per call.
- The quota headers are `x-requests-remaining`, `x-requests-used` and `x-requests-last`; every call is logged.
- Bookmaker-level `last_update` is deprecated; **market-level `last_update`** exists. Whether it's present in historical h2h I'll check in the sample week.
- **Plans** (all include history): 20K credits $30/mo, 100K $59, 5M $119, 15M $249.

**Effective resolution for H2:**
- A Pinnacle move is only known to within one 5-min snapshot, plus the Odds API's scrape delay. Market `last_update` may narrow the timing, but it's used for *measuring* lag only, never for the trade decision.
- Kalshi resolution is 1 minute.
- ⇒ **H2 is testable historically for lags of about ≥5–10 min.** Sub-5-min lag can't be resolved from history. If the sample week shows most catch-up happens inside one snapshot, the forward collector should poll live odds every **1 min in the final 2h** (about +100 credits/day).

**Snapshot schedules.** Costs are computed from the real 2025-26 tip times: 56 sample-week games, 1,233 season games, 164 game days. Each snapshot covers all games, and windows are unioned on the 5-min grid.

| Schedule | Sample week Jan 5–11 | Full 2025-26 reg. season |
|---|---|---|
| **A (proposed)**: 5m in [tip−2h, tip+15m] · 15m in [tip−6h, tip−2h] · 60m from market open to tip−6h | 754 snaps · **7,540 cr** | 16,990 · **169,900 cr** |
| B lean: 5m last 2h · 60m before | 657 · 6,570 | 14,906 · 149,060 |
| C heavy: 5m last 6h · 30m before | 1,145 · 11,450 | 25,048 · 250,480 |
| D max: 5m continuous, market open → tip+15m | 2,427 · 24,270 | 49,398 · **493,980** |

- **Sample week:** A. It fits any paid plan.
- **Full season:** A already needs more than the 100K plan, so one month on the **5M plan ($119)**. At that point **D costs the same money** and gives 5-min coverage everywhere, so I recommend D for the full pull.
- **Optional:** Pinnacle closing lines for the Kaggle H3 test need one snapshot per distinct tip time (791 in 2025-26). That's about 8K credits per season, about 40K for 2021-22 through 2025-26.

## 4. File / module structure (uv project)
```
pyproject.toml  uv.lock  .env.example  .gitignore(.env, data/, reference/)  CLAUDE.md  README.md
config/
  sports/nba.yaml   # series_ticker, odds_sport_key, tip_rule(exp−3h), season+phase windows, cup dates, exclusion rules
  sports/mlb.yaml   # KXMLBGAME/baseball_mlb (collector shakeout)
  teams/nba.csv     # code, kalshi_codes, odds_api_names (+"LA Clippers"…), espn_codes, conference
  backtest.yaml     # blend weights, thresholds X={2,3,5}, windows, staleness, participation cap, train/validate dates
src/markets/
  settings.py  sport.py            # env/paths/UTC helpers; SportConfig + alias resolver (unknown name → anomaly, never guess)
  http.py      storage.py          # rate limiter+backoff, cache-first fetch; atomic raw-Parquet writer, fetch_log, DuckDB migrations
  kalshi/  client.py (GET-only) · discover.py · candles.py (window, <5000 chunks, cutoff router) · trades.py · normalize.py
  oddsapi/ client.py (hist+live, credit ledger, --max-credits guard) · schedule.py (plan + estimate)
  fees.py  devig.py
  build/   games.py (match, phases, B2B, exclusions, anomalies) · sql/*.sql (DDL + views)
  analysis/ views.sql · fills.py · clv.py · h1_static.py · h2_lag.py · report.py
  research/kaggle_h3.py
  collector/ run.py (one idempotent tick, lockfile, heartbeat) · splits/ (gated) · launchd/*.plist.template
  cli.py   # markets discover|candles|trades|odds-plan|odds-pull|build|backtest|report|collect|h3-kaggle
tests/  fixtures/  test_fees · test_devig · test_asof_no_lookahead · test_matching · test_chunking · test_ffill · test_no_order_code
data/raw/{sport}/{source}/{date}/*.parquet   data/markets.duckdb   data/logs/
```

## 5. DuckDB schemas (`data/markets.duckdb`; every table has `sport`; all `TIMESTAMPTZ` UTC)
Types: prices `DECIMAL(6,4)`, counts `DECIMAL(18,2)`, decimal odds `DECIMAL(8,4)`, probabilities `DECIMAL(9,6)`.
- **games**: `sport, game_id(=event_ticker) PK, season, game_date_et, away_code, home_code, kalshi_est_tip, odds_event_id, commence_time, tip_diff_min, tip_diff_flag(>30m), home_away_swapped, commence_changed, phase(regular|preseason|play_in|playoffs|cup_final), is_nba_cup, away_b2b, home_b2b, match_status, split(train|validate|forward)`
- **kalshi_markets**: `sport, market_ticker PK, game_id, team_code, yes_sub_title, open_time, close_time, expected_expiration_time, settlement_ts, result, settlement_value, endpoint(historical|live), raw_path`
- **kalshi_candles** (sparse, as received): `sport, market_ticker, period_min, end_ts, yes_bid_{o,h,l,c}, yes_ask_{o,h,l,c}, price_{o,h,l,c,mean,prev} NULL, volume, open_interest, endpoint`. PK `(sport, market_ticker, period_min, end_ts)`.
- **kalshi_trades**: `sport, trade_id PK, market_ticker, created_time, count, yes_price, no_price, taker_outcome_side, taker_book_side, is_block_trade`
  - View **kalshi_yes_taker_1m**: `sport, market_ticker, minute_end_ts, yes_taker_volume, all_volume, vwap_yes`. Minutes are bucketed to match candle `end_ts` semantics; this drives the fill cap.
- **variants**: `variant_id(config hash) PK, hypothesis, params_json, split, run_ts, n_signals, n_fills`. Every report prints `n_variants_tested`.
- **bt_bets / bt_leadlag / bt_summary**: per-bet fills (requested vs filled qty, entry, fee, CLV variants, P&L), per-event lead-lag rows, and aggregated tables keyed by `variant_id`.
- **sharp_odds** (long): `sport, snapshot_ts, requested_ts, odds_event_id, commence_time, home_team, away_team, bookmaker, market_key, market_last_update, team_code, price_decimal, origin(historical|live)`. PK `(sport, snapshot_ts, odds_event_id, bookmaker, team_code)`.
  - View **sharp_fair**: per snapshot × team, with `pin_fair`, `lowvig_fair`, `bol_fair`, `blend_fair`, `blend_std`, `books_used`.
- **results**: `sport, game_id, market_ticker, result, settlement_type(binary|scalar), settlement_value, settled_ts`
- **splits**: `sport, dataset(kaggle_mgm|<forward source>), collected_ts, is_closing, source_game_key, game_id NULL, market(ml|spread|total), team_code/side, bets_pct, handle_pct, line, price`
- **excluded_markets**: `sport, market_ticker, game_id, reason, detail, rule_version, logged_at`. PK `(sport, market_ticker, reason)`.
- **anomalies**: `sport, kind, game_id, market_ticker, ts, detail`. Kinds: `ask_sum_lt_1`, `tip_diff_gt_30m`, `lifetime_gt_14d`, `scalar_settlement`, `unmatched_kalshi`, `unmatched_odds`, `unknown_team_name`, `commence_changed`.
- **kalshi_tob** (collector): `sport, collected_ts, market_ticker, yes_bid, yes_ask, yes_bid_size, yes_ask_size, last_price, volume, open_interest`
- **fetch_log**: `cache_key PK, sport, source, url, params, fetched_at, http_status, raw_path, rows, credits_used`
- **collector_runs**: `run_ts PK, sports, status, n_tob, n_odds, n_splits, credits, error`. View **collector_gaps**: run gaps >7.5 min inside active windows.
- View **v_analysis**, on a 1-min grid per market from open to commence+15m:
  - Columns: `sport, game_id, market_ticker, team_code, ts, yes_bid, yes_ask, volume, is_filled, fill_age_min, fair_prob, fair_source, sharp_snapshot_ts, sharp_age_min, fee_per_contract, edge_vs_ask_net_of_fee, sharp_move_last_{5,15,30,60}min, minutes_to_tip, is_favorite, b2b, result, split`.
  - Kalshi values come from a LEFT ASOF join of candles on `end_ts ≤ ts`.
  - Forward-filled rows get `is_filled=true` and `volume=0`; bid/ask become NULL when `fill_age > 30 min`.
  - The sharp line comes from a LEFT ASOF join on **`snapshot_ts ≤ ts`** (never `last_update`). It becomes NULL when `sharp_age > 65 min` (the hourly tier plus slack).

**Matching:**
- Kalshi game ↔ Odds API event on the unordered team pair plus nearest `commence_time` to `kalshi_est_tip` within ±18h, one-to-one.
- Swapped home/away is flagged (international games).
- A diff over 30 min is flagged.
- The match rate and every unmatched game are reported.

## 6. Backtest design
- **Fill model** (approved change):
  - The signal at `t` uses only data ≤ `t`.
  - The fill happens at the next minute's `yes_ask_open`, never below the decision ask.
  - Quantity is capped by participation × **YES-taker volume** in (t, t+1m]. That's the trades with `taker_outcome_side='yes'`, meaning buy-YES or sell-NO, which consume YES-ask liquidity. They're aggregated to a 1-min view `kalshi_yes_taker_1m`.
  - **Default participation is 25%; 100% is the sensitivity case.** Candle volume is kept only as a reconciliation check.
  - Every report shows **fill rate**: the % of signals with any fill, plus average filled / requested size.
  - Trades are therefore pulled for every backtested market, not just as a cross-check.
- **Overfitting guard** (approved change):
  - Thresholds (θ, X, W, entry buckets) are tuned on train only (≤ 2026-01-31).
  - Validate is evaluated once per frozen config.
  - Every results table carries `n_variants_tested` next to the metrics.
  - A `variants` registry table logs each config hash, split and timestamp.
  - The sample week is all train, so its results are descriptive only.
- **CLV:**
  - Primary: `pin_close_fair − entry_ask`, gross and net of fee.
  - Also: `pin_close_fair/entry_ask − 1`, and line-move CLV `pin_close_fair − fair_at_entry`.
  - The close is the last snapshot ≤ `commence_time`.
  - *Note, September 29, 2026: the code takes the last snapshot strictly before `commence_time` (`<`, as `load_sharp` already did), since an outside audit (Astra, finding C5) showed that a snapshot taken at the scheduled start, possibly in-play, became the close. Snapshots at and after the start stay in `sharp_fair` and `analysis_1m` for the lead-lag analysis.*
- **Other metrics:** EV, ROI and bet count. Breakdowns by edge bucket, minutes to tip (>24h, 6–24h, 2–6h, 90–120m, 30–90m, 0–30m), favorite/underdog, and B2B.
- **Selection:** one entry per market per strategy variant (the first qualifying signal). Train runs through 2026-01-31; validate runs Feb 1 – Apr 12.
- **H1:** `edge_vs_ask_net_of_fee ≥ θ`.
- **H2:**
  - A move is a Pinnacle fair change ≥ X pts (2/3/5) within W (5/15/30 min), detected at `snapshot_ts`.
  - Lag is the minutes until the Kalshi mid closes 50% and 80% of the gap, capped at 120 min or tip.
  - Also reported: edge available at t0+1m, and a separate breakout for moves ≤90 min before tip.
- **H2 lead-lag, both directions** (approved change; descriptive measurement, not a trade signal, so it may look forward):
  - Events come from both venues: Pinnacle fair moves (as above) and Kalshi mid moves ≥ X within W, from 1-min candles.
  - For each event, the other venue is classified as `pinnacle_first`, `kalshi_first`, `same_bucket` (within one 5-min snapshot, unresolvable), or `no_follow`. "Follows" means a same-direction move ≥50% of the magnitude within ±60 min.
  - **Lead-lag summary:** who moves first, how often, and median/p75 lead in minutes and magnitude, by X, W and minutes-to-tip bucket. Plus a cross-correlation of 5-min Δfair vs Δmid at lags −60…+60 min.
  - Pinnacle timing is computed twice: from `snapshot_ts` (conservative) and from market `last_update` (partly corrects the Odds API scrape delay). A `kalshi_first` result that survives the `last_update` timing is the robust finding.
- **Kaggle H3:**
  - Divergence D = money% − ticket%, with thresholds k ∈ {5, 10, 15}.
  - Measures: residual versus MGM de-vigged close (calibration), ML and ATS ROI on the sharp side, split by season.
  - Pinnacle close as an option. Reverse line movement isn't testable with closing-only data.

## 7. Forward collector
- **Tick** runs every 5 min via a launchd LaunchAgent (`StartInterval 300`, `RunAtLoad`). Steps:
  1. Skip fast if no open event tips within the window.
  2. Kalshi top of book from `GET /events?series_ticker=…&status=open&with_nested_markets=true` (public, 1 call per sport).
  3. Odds API live h2h for the 3 books (1 credit).
  4. Splits, once a source is approved.
- **Storage:** one append-only Parquet per source per tick (write temp, then rename). A lockfile prevents overlapping ticks, and a heartbeat row goes to `collector_runs`.
- **Sleep:** gaps are computed from heartbeats. launchd coalesces missed runs on wake, and any gap found at startup is logged.
- **Shakeout:** MLB postseason from Sep 29. It runs daily, the format is known, and `KXMLBGAME` is at mult 0.5. I'll add NBA preseason as soon as Kalshi lists it, then NBA on Oct 20. CFB is Saturday-only and its series ticker is unverified, so I'm not recommending it.

**Splits sources (ToS):**
- **Action Network:** ToS explicitly bans "robot, spider" and page-scrape access with no personal-use carve-out. **Excluded.**
- **VSIN** (`data.vsin.com/betting-splits/?source=dk`): DraftKings plus a Circa comparison, both handle% and bets%, updated every 5 min. The full splits need VSIN Pro. **I couldn't find a ToS page (every guessed URL returned 404).** No scraping until you've read their terms or gotten permission.
- **SportsDataIO:** licensed API; the `BettingSplit` object has `BetPercentage`, `MoneyPercentage` and `Created`/`LastSeen` (time series). Trial data is scrambled and pricing is by quote. **This is the ToS-clean choice.**
- **Yahoo/BetMGM** (the Kaggle source): scraping-based. **Excluded** for forward collection.

## 8. Order of work (approved: sample week Jan 5–11, 2026 only)
0. **Setup in `~/code/sharp-markets`:**
   - `git init`, `uv init`. You'll add the private GitHub remote. `.gitignore` covers `.env`, `data/`, `reference/`.
   - `.env.example` with `ODDS_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`. Keys live only in `.env`.
   - `CLAUDE.md`: paper-only, no lookahead, cache first, UTC everywhere, log don't drop, sport-agnostic.
   - Clone the reference repo into `./reference` (read-only) and re-verify the fee PDF.
1. Discover all KXNBAGAME events and markets (raw → Parquet), then log exclusions and anomalies.
2. Pull candles and **trades** for the 56 sample-week games (112 markets). Reconcile candle volume against trades and build `kalshi_yes_taker_1m`.
3. Run `odds-plan` (schedule A: 754 snapshots / 7,540 credits). `odds-pull --confirm --max-credits 8000` hard-stops at the budget. **No full-season pull until you've reviewed the sample.**
4. Build games, matching, `sharp_fair` and `v_analysis`. Report match rate, unmatched games, tip diffs, ask-sum<1 cases, and the scalar MIA@CHI game (excluded from P&L/CLV, kept in anomalies).
5. Run H1 and H2 (including the lead-lag summary, fill rate, and `n_variants_tested`) on the sample week. **⏸ STOP: show you the results.**
6. Run the Kaggle H3 test against **MGM's own closing line only**; the Pinnacle-close version waits for the full pull. **⏸ STOP: show you the results.**
7. Only after your review: build the collector (Kalshi + Pinnacle, no splits) and install the LaunchAgent for the MLB postseason shakeout. Include the optional `caffeinate -s` wrapper for game windows, and log gaps.

## 9. Decisions (approved)
1. **Folder:** `~/code/sharp-markets`, a git repo with a private remote you add. `.gitignore` covers `.env`, `data/`, `reference/`.
2. **Odds API:** schedule A for the sample week only, `--max-credits 8000`. No full-season pull until the sample is reviewed.
3. **Splits:** none for now. You're getting a SportsDataIO quote. No VSIN or Action Network scraping.
4. **NBA Cup:** one-time ESPN pull → `config/nba_cup_2025_26.csv` for your review.
5. **Scalar/postponed games:** excluded from P&L/CLV and kept in `anomalies`.
6. **Kaggle:** you'll add the token to `.env`. Compare against MGM close first; the Pinnacle-close version comes after the full pull.
7. **Sleep:** accept and log gaps, with an optional caffeinate wrapper.
8. **Fills:** 25% of YES-taker volume by default, 100% sensitivity, fill rate reported.
9. **Overfitting:** tune on train only; `n_variants_tested` appears on every report.
10. **Lead-lag:** measured in both directions (Kalshi-first vs Pinnacle-first).

Remaining input needed at runtime: `ODDS_API_KEY` in `.env` before step 3, and the Kaggle token before step 6. If either is missing, I'll stop at that step and ask.

## Verification
- **Unit tests:**
  - Fees: the Kalshi doc worked example; per_order vs per_fill vs none; multiplier as of date.
  - De-vig and blend renormalization.
  - Chunking stays ≤5,000 per request.
  - Forward fill nulls at >30 min and sets volume 0.
  - Matching fixtures include swapped home/away and an unknown name.
  - `test_no_order_code`: a Kalshi client method other than GET, or a `portfolio/orders` path, fails the test.
- **No-lookahead SQL assertion:** zero rows where `sharp_snapshot_ts > ts` or where candle `end_ts > ts`.
- **Idempotence:** a second run of the sample week makes **0 HTTP requests and spends 0 credits** (checked via `fetch_log`).
- **Sample-week report:** 56/56 games matched (or the unmatched ones listed), candle volume reconciled with trades, credits used ≤ 8,000, and the first H1/H2 tables. The H1/H2 tables include the lead-lag summary, fill rate at 25% and 100%, and `n_variants_tested`.
- **Git hygiene:** `git status` shows no `.env`, `data/` or `reference/`, and `git check-ignore` confirms all three.
