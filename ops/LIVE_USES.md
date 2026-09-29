# Live uses on a paid Odds API plan

Three launchd jobs for the 5M month and after. They come from the budget in [`strategy-research/odds-api-credits.md`](../strategy-research/odds-api-credits.md#after-the-month-live-uses).

All three are **logging only and GET-only**. None of them:
- sends an alert;
- changes Rule B, Rule HT, their gates or their scoring;
- touches the alert, close-capture or ledger jobs.

The hub installs them on the Mac with `ops/install_live_uses.sh` once the paid key is in the three `.env` files.

| Job | Every | What it logs | Credits | Output |
|---|---|---|---|---|
| `com.valuefinder.triggerpoll` | 10 min | For NFL and CFB games whose latest ledger row has a Rule B wind trigger and a kickoff within 4 days, every book's total and prices. It shows how the price moves between the four daily alert runs. | 1 per sport per run with a trigger; about 2,600 a month | `{nfl,cfb}-weather/data/forward/trigger_polls.csv`; raw responses in `data/raw/oddsapi/live/` |
| `com.valuefinder.propslog` | 15 min | Every NFL game's props, alternate lines and team totals at T−48h, T−24h, T−2h and the close (2–20 minutes before kickoff). The markets and books match the historical F2/F3 pulls. | Up to 9 per snapshot; about 2,520 a month | `nfl-weather/data/forward/props_log.csv`; raw responses in `nfl-weather/data/raw/oddsapi/props/` |
| `com.valuefinder.nbacollector` | 1 min (acts every 5) | The NBA collector from `sharp-markets/docs/PLAN.md` §7, from the Oct 20 opener. While any game is between 56h before tip and 15 minutes after, each acting tick fetches Kalshi's open game markets (free) and Pinnacle, LowVig and BetOnline moneylines (1 credit). | About 8,640–8,930 a month: in season some game is always inside the 56h window, so it acts every 5 minutes all day (288 a day). Up to about 14,460 if one-minute final-2h ticks are turned on | `sharp-markets/data/raw/nba/collector_{kalshi,oddsapi}/`; heartbeats in `sharp-markets/data/collector/nba/runs.csv` |

## Credits: the background kind

Each job sets `ODDS_QUOTA_KIND=background`. The shared quota guard (`quota.py` in both weather projects, mirrored in `sharp-markets/src/markets/collector.py`) then applies two rules:

- **Paid plan only.** The plan size is read from the last response (used + remaining). On the free 500-credit plan, or before anything has been recorded in a new month, background jobs make no Odds API call at all. `ODDS_API_TIER=paid|free` overrides this.
- **Background floor.** A background job stops when fewer than max(2,000, 2% of the plan) credits remain: 100,000 on the 5M plan and 2,000 on the 20K plan. The alerts and close capture always keep their credits. `ODDS_BACKGROUND_FLOOR` overrides the floor.
- **Setting the overrides.** `ODDS_API_TIER` and `ODDS_BACKGROUND_FLOOR` are read from the process environment only; the weather projects never load `.env` into it, so a line in `.env` does nothing. Set them when running the installer, which writes them into each job's plist, for example `ODDS_API_TIER=paid ODDS_BACKGROUND_FLOOR=150000 ops/install_live_uses.sh`. Rerun the installer without them to go back to the defaults.
- **One key.** The three projects share one quota file, and each record carries a fingerprint of the key that made the call (the first 12 hex digits of its SHA-256; never the key). A project ignores records made with a different key, so one key's plan never sets another's tier or floor. The installer refuses to install unless `ODDS_API_KEY` is the same in all three `.env` files.

The alerts, close capture and manual runs behave exactly as before on every plan.

One refinement applies to everyone: a response without quota headers (a network-level error page) no longer overwrites the last known quota.

## Install, check, remove

```bash
ops/install_live_uses.sh                        # all three
ops/install_live_uses.sh triggerpoll propslog   # some
ops/install_live_uses.sh --remove               # all three off
tail -f ~/Library/Logs/valuefinder-{triggerpoll,propslog,nbacollector}.log
```

- **Before Oct 20**, the NBA collector does nothing. Its start date is `collector.start` in `sharp-markets/config/sports/nba.yaml`.
- **One-minute ticks in the final 2 hours** (PLAN.md §3, about +100 credits a day) are off. Set `collector.final_every_min: 1` to turn them on, if the sample shows that lag is resolved inside one 5-minute snapshot.
- **Sleep gaps.** The Mac has to be awake for any of this. Missed props slots stay missing and are never imputed. The collector's `runs.csv` records the gap since the previous tick, so sleep gaps are measured rather than hidden.
