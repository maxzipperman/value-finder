# NBA sample acquisition preparation

Mac-only: fixed January5–11,2026 NBA2025–26 listing metadata and local exact-key caches. Related to the approved October queue and issue#38. No Odds API key, paid call, game-result access, strategy result or sealed2026–27 input.

The free historical Kalshi catalog yields56 scheduled event identities. Only event/market tickers, titles, open/close and expected-expiration timestamps are selected; settlement/results never select or exclude an event. Every event remains even if it was cancelled, contingent or later rescheduled. Tip proxy is the existing NBA pipeline's expected-expiration minus3hours and is used for acquisition windows only, never actual-first-play certification.

Existing scheduleA produces754 featured NBA h2h snapshots at Pinnacle/LowVig/BetOnline: at most7540credits. URL/parameter/source/cache identity matches the existing NBA OddsApiClient, not generic football F1. Fresh exact-key scan found no existing NBA response for these keys in the listed stores. The list is reviewable and non-executable; no forecast or market price picked its slots. All timestamps and intended windows are retained in metadata.json and requests.json. Post-tip requests are descriptive input only, never pregame entries.

Free Kalshi history is already cached:112 markets across56 events,259778 price minutes,112 logical requests and seven additional transient429 retries, all resolved. This used zero Odds API credits. Future free pulls use4RPS. Raw bodies stay local; the receipt reports only acquisition counts, not performance.

Regeneration: prepare.py obtains free metadata cache-first; exact_list.py generates the candidate list; free_candles.py obtains the fixed free windows cache-first. Paid execution requires a separately reviewed shared cumulative driver, exact frozen packet, all current cache/ancestor overlap checks, the then-current clean predecessor and hub root/list/budget/commit approval. Current F2 stop blocks any new paid root until reviewed reconciliation.

## Report for the hub

READY for candidate-list and metadata review; NOT READY for paid execution. Maximum7540credits inside the existing8000N0cap; prior/cumulative use does not reset. No credentials, paid call, outcome join, grading or merge.
