# Reviewer B: simulations (steps 3, 4) and the `headers` stage and margin (step 8b), PR 63 at cc14201

Scope: false stops, missed stops, the `headers` stage and `--alarm-margin`, against the branch's real `BulkClient`,
`run_calls`, `OddsApiClient`/`pull_snapshots` and the real `markets` CLI, with an in-process fake Odds API. Nothing was
fixed, nothing was spent, no `.env` was opened, the key was `FAKESECRETKEY999` everywhere.
`S=/tmp/claude-0/-home-user-value-finder/d7012428-080d-54f3-a1da-3ceb35298eec/scratchpad`; everything of mine is in `$S/revB`.

## Verdict in three lines

1. With the margins the runbook prints (`--alarm-margin A30/A60` from `headers`), no honest run stopped on the alarm in any
   realistic setting (15,640 simulated runs of step 3; every day-one command in sequence), and every overcharging API
   stopped on the alarm within the stated bound (step 4).
2. With the DEFAULT margin (5,000) a 60-credit pull (F3a) whose balance header runs late by a varying 0-100 answers
   false-alarms in 100 of 100 runs, and odds-pull right after F3a in up to 92 of 100: rule 6 misreads an out-of-date
   rise above 5,000 as credits added. The runbook's printed commands avoid it (A60), and it clears the runbook's way.
3. `headers` gives the right verdict and advice on every first-run manifest with a fixed header, but its lateness figure
   is unreliable for varying headers (wrong kind, or 8x too large) and for a run that starts right after another run
   (a fixed 100-answer lateness reads as 2); none of these caused a false alarm or a missed stop in my day-one runs.

## How it was run (the harness)

- `$S/revB/fakeapi.py`: `FakeAPI.get(url, params=None, timeout=None)` returns objects with `status_code`, `headers`,
  `text`, `json()` (the approach of `tests/test_bulk.py`'s `FakeOddsApi`/`Ledger`). It keeps the true balance and a
  history of it after every answer (the key check included). Behaviours: true cost reported always (documented cost:
  10 x markets returned x regions; 1 for a sweep that lists games, 0 for an empty one); balance header `live`, `late`
  by k answers (fixed), `late_rand` (0..k drawn per answer), `steps` (refreshed every N answers), `frozen`; timeouts at
  a rate, billed or not (a billed one enters the history, the client sees `ReadTimeout`); other spenders per simulated
  hour (lumps), per answer, or one lump at a random answer; overcharging `mult` (2x, 10x) or `flat` (300 reported as
  30), optionally only from answer m on; top-ups at answer m. Simulated clock: 1/8 s per request plus every backoff
  sleep (all sleeps patched to advance the clock; the rate limiter patched out). The header state carries across
  clients on one fake, so a key check can read a stale balance, as it would on the real key.
- Profiles: F1 (featured, us10, 3 markets: 30 each), F3 (event props, 6 markets asked, 2-6 returned: 20-60, upper 60),
  F3a-all-60 (every prop quoted), F2 (20), N0 (odds-pull's NBA snapshot: 10), P0 (the real config's 10,434 sweeps at
  Thursday's clock, 75% listing games), P0+ (every sweep listing games, then the seven probes: 10,704 at most).
- `$S/revB/sim.py` drives `BulkClient` + `run_calls` (cache in memory as the branch's `fast` fixture does; manifest writes
  off for speed; `Call.key` memoized, same values). After every stopped run it asks the same client for another
  uncached call and checks it raises the SAME stop and sends nothing.
- `$S/revB/hdr.py`, `hdr_seeds.py`: manifests written by the real client (real `_log`), then
  `uv run markets odds5m headers ...` through the CLI in a subprocess with `$S/revB/hook/sitecustomize.py`, which
  refuses `socket.socket`, `socket.create_connection` and `socket.getaddrinfo` and logs every attempt with its stack.
- `$S/revB/cli_seq.sh`: the runbook's new step through the real CLI (`probe --confirm`, `headers`, `week`, `headers`,
  `full`), the fake routed in-process by the same hook (`requests.Session.get` patched; state pickled between commands).
- Memory/CPU rule: at most 2 simulation processes at a time, each under `ulimit -v 4000000`. The first launch grew to
  ~900 MB (stopped clients sit in a reference cycle with their Stop's traceback until a full GC); I killed both,
  added `gc.collect()` after each run and resumed: ~100-160 MB each from then on. No run approached 4 GB.
- Seeds: 100 per setting, EXCEPT settings with no randomness at all in them (F1 with a fixed lag, steps, frozen, live:
  F1 always bills 30, so every seed is the same run): 10 seeds; frozen missed-stop runs: 3; resumed deterministic runs:
  10; `headers` scenarios: seed 0 through the CLI plus 30 seeds for the varying headers.
- Procedure note: one check of mine (`uv run markets odds-pull --start 2026-01-05 --end 2026-01-11 --max-credits 8000
  --alarm-margin 12,000`, no `--confirm`, to see that `12,000` is accepted) built the NBA `Context`, which tried to
  reach `api.elections.kalshi.com` through the proxy 7 times; the hook refused every attempt before it connected, so
  nothing left the machine. That is the NBA pipeline's existing cache-first behaviour, not this PR's code.

## Step 3: false stops (honest API)

Budget = plan + 5% (F1 157,500, F3 315,000) unless named; probe 11,000; floor 531,630; start 5,000,000.
"budget stop (timeouts)" = a budget stop with unanswered attempts counted (never without: the column "NOT timeouts" is
0 everywhere). "count < charged" = runs whose count was ever below what the API charged: 0 everywhere. "refused after
stop" = stopped clients that refused a further attempt with the same stop and sent nothing.

Totals: 178 settings, 15,640 runs. FALSE ALARMS: 330, all with the default 5,000 margin on 60-credit pulls (F3a, and
odds-pull right after F3a) under a header late by 85-100 answers; 0 with the margin the runbook prints. Floor stops: 0.
Budget stops without timeouts: 0.

Highlights (full table below):

| setting | runs | finished | budget (timeouts) | floor | FALSE ALARMS | other |
|---|---|---|---|---|---|---|
| F1, F3, P0: live; late 1, 2, 3; late 0-3; steps 50, 400; frozen; others 5/h, 50/h, 500/h, 500 in one lump | 10-100 each | all | 0 | 0 | 0 | 0 |
| F1, F3, P0: late 20, 100 (fixed and 0-20, 0-100 varying), steps 100, default margin and advised | 10-100 each | all | 0 | 0 | 0 | 0 |
| F1 timeouts 1% (billed or not) | 100+100 | 200 | 0 | 0 | 0 | 0 |
| F1 timeouts 5% unbilled / billed | 100 / 100 | 33 / 33 | 67 / 67 | 0 | 0 | 0 |
| F1 timeouts 20% unbilled / billed | 100 / 100 | 0 / 0 | 95 / 95 | 0 | 0 | 5 / 5 no answer after 7 tries |
| F3 timeouts 1%, 5% | 400 | 400 | 0 | 0 | 0 | 0 |
| F3 timeouts 20% | 200 | 190 | 0 | 0 | 0 | 10 no answer after 7 tries |
| P0 (75% of sweeps list games) timeouts 1%, 5% | 400 | 400 | 0 | 0 | 0 | 0 |
| P0 timeouts 20% | 200 | 180 | 0 | 0 | 0 | 20 no answer after 7 tries |
| P0+ as Thursday runs it (10,704 at most, budget 11,000): live, late 0-100, steps 100, others 500/h, timeouts 1% | 600 | 600 | 0 | 0 | 0 | 0 |
| P0+ timeouts 5% (billed or not) | 200 | 0 | 200 | 0 | 0 | 0 |
| P0+ timeouts 20% | 200 | 0 | 184 | 0 | 0 | 16 no answer |
| WORST REALISTIC (late 0-100 + 5% billed timeouts + 500 in one lump): F1 / F3 / P0 / P0+ | 400 | 25 / 100 / 100 / 0 | 75 / 0 / 0 / 100 | 0 | 0 | 0 |
| back to back (500 calls just before on one key): F1, F3 x late 3, 0-3, 20, 0-20, 100, 0-100, steps 50, 100, 400; default and advised | 2,210 | all | 0 | 0 | 0 | 0 |
| DAY ONE sequence, each command right after the one before, + 500 others per run: F1 full, F2 full, F3a (props 2-6 quoted), odds-pull, HB1/HS1 x live, late 100, late 0-100, steps 100; default and runbook margin | 3,500 | all | 0 | 0 | 0 | 0 |
| **DAY ONE, F3a with every prop quoted (60 a call) after F2, late 0-100 + 500 others, DEFAULT margin 5,000** | 100 | 0 | 0 | 0 | **100** | 0 |
| F3a (60 a call) on a fresh key, nobody else spending, late 0-100, DEFAULT margin | 100 | 0 | 0 | 0 | **100** | 0 |
| same, late 0-85 / late 0-80 | 100 / 100 | 97 / 100 | 0 | 0 | **3** / 0 | 0 |
| same, late 0-100, `--alarm-margin 12,000` (A60) | 100 | 100 | 0 | 0 | 0 | 0 |
| F3a with props 2-6 quoted (20-60), late 0-100, default | 100 | 100 | 0 | 0 | 0 | 0 |
| F3a (60 a call) after F2, late 100 fixed / steps 100 + 500 others, default | 200 | 200 | 0 | 0 | 0 | 0 |
| odds-pull after F3a at 60, steps 100 + 500 others, default | 100 | 100 | 0 | 0 | 0 | 0 |
| **odds-pull right after F3a at 60, late 100 fixed + 500 others, DEFAULT margin** | 100 | 8 | 0 | 0 | **92** | 0 |
| **odds-pull right after F3a at 60, late 0-100 + 500 others, DEFAULT margin** | 100 | 65 | 0 | 0 | **35** | 0 |
| odds-pull after F3a at 60, late 100 fixed, nobody else spending, default | 100 | 100 | 0 | 0 | 0 | 0 |
| odds-pull and F3a (60 a call) in the day-one sequence with `--alarm-margin` A60 (12,000; 11,880 for steps), late 100, late 0-100, steps 100 | 600 | 600 | 0 | 0 | 0 | 0 |

The probe's 11,000 leaves 296 credits of slack over its 10,704 upper bound, so 5% of tries timing out stops it on its
budget every time (P0+ rows); the runbook's answer (rerun until `P0 done`, the sweeps already fetched are free) applies.

Full table (every setting): see "Appendix A" at the end.

## Step 4: missed stops (API charging more than it reports)

Loss = credits charged for this run's requests minus the run's count. Bound = margin + lag x the charge per answer +
one call's extra (charge - upper bound); for 0-3 at random the lag is 3.

| setting | runs | stopped on the alarm | max loss beyond the count | bound | within |
|---|---|---|---|---|---|
| F1 2x: live / late 1 / 2 / 3 / 0-3 | 10/10/10/10/100 | all | 15,780 / 15,840 / 15,900 / 15,960 / 15,930 | 15,780 / 15,840 / 15,900 / 15,960 / 15,960 | yes |
| F1 10x: live / late 1 / 2 / 3 / 0-3 | 10/10/10/10/100 | all | 15,930 / 16,200 / 16,470 / 16,740 / 16,740 | 16,020 / 16,320 / 16,620 / 16,920 / 16,920 | yes |
| F1 flat 300 reported 30: live / late 1 / 2 / 3 / 0-3 | 10/10/10/10/100 | all | 15,930 / 16,200 / 16,470 / 16,740 / 16,740 | 16,020 / 16,320 / 16,620 / 16,920 / 16,920 | yes |
| F3 2x: live / late 1 / 2 / 3 / 0-3 | 100 each | all | 31,560 / 31,670 / 31,800 / 31,860 / 31,810 | 31,560 / 31,680 / 31,800 / 31,920 / 31,920 | yes |
| F3 10x: live / late 1 / 2 / 3 / 0-3 | 100 each | all | 32,040 / 32,580 / 33,030 / 33,480 / 33,480 | 32,040 / 32,640 / 33,240 / 33,840 / 33,840 | yes |
| P0 2x: live / late 1 / 2 / 3 / 0-3 | 100 each | all | 5,001 / 5,003 / 5,005 / 5,007 / 5,006 | 5,001 / 5,003 / 5,005 / 5,007 / 5,007 | yes |
| P0 10x: live / late 1 / 2 / 3 / 0-3 | 100 each | all | 5,004 / 5,013 / 5,022 / 5,031 / 5,031 | 5,009 / 5,019 / 5,029 / 5,039 / 5,039 | yes |
| F1 2x / 10x / flat 300, balance never moves | 3 each | none: all 5,000 calls bought | 150,000 / 1,350,000 / 1,350,000 | no limit | as the runbook says (ODDS5M_DAY_ONE.md:71, "with no limit if the balance never moves, which `headers` shows after the probe") |
| F1 top-up 1,000,000 at 20%, then 2x: live / late 3 / late 0-3 | 10/10/100 | all | 15,810 / 15,900 / 16,020 | 15,780 / 15,960 / 15,960 | **30 and 60 over** (finding B2) |
| F1 top-up 15,000 (at most the margin) at 20%, then 2x: live / late 3 / late 0-3 | 10/10/100 | all | 30,780 / 30,960 / 30,960 | 15,780 / 15,960 / 15,960 | **over by the top-up** (finding B2) |
| F1 top-up 3,000 at 20%, then 2x: live / late 3 / late 0-3 | 10/10/100 | all | 18,780 / 18,960 / 18,930 | 15,780 / 15,960 / 15,960 | **over by the top-up** (finding B2) |

Two runs at once on one key (two clients alternating call by call in random order, each budget 20,000, default
margin 5,000, F1 calls, 100 seeds each), how far the account went below the floor (531,630):

| header | starting 3,000 above the floor | starting 30,000 above the floor |
|---|---|---|
| live | 30 (1 call), both stopped on the floor | 0: both stopped on the ALARM (each sees the other's spending) |
| late 3 | 120 (4 calls) | 0 (alarm) |
| late 0-100 | up to 960 (mean 500) | 0 (alarm) |
| steps 100 | up to 2,970 | 0 (alarm) |
| late 100 | 3,000 (100 calls) | 0 (alarm) |

Resumed run over a partly filled cache (F1 5,000 calls; the first run stops on a 75,000 budget; rerun with the rest +
5%, default margin 7,878 or the advised one): honest API with live, late 100, steps 100, late 0-100 (+500 others in
the rerun), and with `--alarm-margin` 6,000 / 5,940: the rerun finished in 10/10 (100/100 for 0-100), loss 0. API
charging 2x (live, late 3): run 1 stopped on the alarm with 7,530 / 7,710 lost (margin 7,500 + 30 / + 3 x 60 + 30);
a rerun anyway (the runbook says tell the hub first) stopped on its own alarm with 14,970 / 15,030 lost (its margin
14,962 / 14,943): each run is bounded by its own margin; nothing carries over.

## Step 8b: the `headers` stage and the margin

Verdict table (seed 0, every `headers` call through `uv run markets odds5m headers ...` with sockets blocked):

| header model (fake API) | true lateness | `headers --pull P0` verdict (probe: 10,434 sweeps + 7 probes) | lateness shown | A30 / A60 shown | 2 x true lateness x U (min 5,000) | right? | `headers --pull F1` after the week | F1 1,000-call run on a fresh key | next pulls with that advice (week, F1, F2, F3a, odds-pull, HB1/HS1) |
|---|---|---|---|---|---|---|---|---|---|
| live | 0 | live | 0 | 5,000 / 5,000 | 5,000 / 5,000 | yes | live; 5,000 / 5,000 | live; 5,000 / 5,000 | all 6 finished |
| late 3 | 3 | late by up to 3 answers | 3 | 5,000 / 5,000 | 5,000 / 5,000 | yes | late by up to 3; 5,000 / 5,000 | late by up to 3; 5,000 / 5,000 | all 6 finished |
| late 0-3 at random | 3 | late by up to 3 answers | 3 | 5,000 / 5,000 | 5,000 / 5,000 | yes | late by up to 3; 5,000 / 5,000 | late by up to 3; 5,000 / 5,000 | all 6 finished |
| late 20 | 20 | late by up to 20 answers | 20 | 5,000 / 5,000 | 5,000 / 5,000 | yes | late by up to 20; 5,000 / 5,000 | late by up to 20; 5,000 / 5,000 | all 6 finished |
| late 0-20 at random | 20 | late by up to 21 answers | 21 | 5,000 / 5,000 | 5,000 / 5,000 | yes (seed 0; see stability) | late by up to 21; 5,000 / 5,000 | late by up to 18; 5,000 / 5,000 | all 6 finished |
| late 100 | 100 | late by up to 100 answers | 100 | 6,000 / 12,000 | 6,000 / 12,000 | yes | late by up to 100; 6,000 / 12,000 | late by up to 100; 6,000 / 12,000 | all 6 finished |
| late 0-100 at random | 100 | late by up to 100 answers | 100 | 6,000 / 12,000 | 6,000 / 12,000 | yes on P0; the F1 run says "steps, about every 96", 5,700 / 11,400 | late by up to 100; 6,000 / 12,000 | steps, about every 96; 5,700 / 11,400 | all 6 finished |
| steps 50 | 49 | steps, about every 50 answers | 49 | 5,000 / 5,880 | 5,000 / 5,880 | yes | steps, about every 50 | steps, about every 50 | all 6 finished |
| steps 100 | 99 | steps, about every 100 answers | 99 | 5,940 / 11,880 | 5,940 / 11,880 | yes | steps, about every 105 | steps, about every 100 | all 6 finished |
| another spender takes 500 during the probe | 0 | fell by 500 credits more than the run counted | 0 | 5,000 / 5,000 | 5,000 / 5,000 | yes | live | fell by 500 | all 6 finished (500 more taken in each) |
| API charges 2x what it reports | 0 | fell by 5,001 credits more than the run counted | 0 | 5,000 / 5,000 | - | yes | - | fell by 5,010 | not run: the probe itself stopped on the alarm (`fallen by 5,001`) |
| top-up 1,000,000 mid-run | 0 | live; rises: `1: +999,999 (credits added)` | 0 | 5,000 / 5,000 | 5,000 / 5,000 | yes | live | live | all 6 finished |
| late 100 + another spender 500 | 100 | late by up to 100 answers | 100 | 6,000 / 12,000 | 6,000 / 12,000 | advice yes; the 500 is not reported (inside the allowance, choice 2 below) | late by up to 100 | late by up to 100 | all 6 finished |
| steps 400 (fault case) | 399 | steps, about every 402 answers | 399 | 23,940 / 47,880 | 23,940 / 47,880 | yes | steps, about every 400 | steps, about every 500 | all 6 finished |
| late 200 (fault case) | 200 | late by up to 200 answers | 200 | 12,000 / 24,000 | 12,000 / 24,000 | yes | late by up to 200 | late by up to 200 | all 6 finished |
| frozen (fault case) | never moves | steps, about every 10,442 answers | 10,441 | 626,460 / 1,252,920 | - | fault: A30 above 60,000, the runbook stops day one | same | steps, about every 1,001; 60,000 / 120,000 | all 6 finished |
| no run of that pull | - | `There is no run of that pull in the manifest.` (P0 asked of an F1-only manifest; F1 asked of a P0-only one; no manifest file at all), exit 0 | | | | yes | | | |
| manifest unreadable (a directory) | - | `headers: the manifest could not be read (Is a directory): ...`, exit 1 | | | | yes | | | |

Every verdict printed was one line of the brief's fixed set (a regex over the whole output found exactly one). Every
`headers` command exited 0 (1 only for the unreadable manifest). Socket attempts over the 126 `headers` commands and the
CLI walks: none, apart from urllib3's import-time IPv6 check in every Python process (one `AF_INET6` socket created to
bind `::1`, never connected: `urllib3/util/connection.py:126 _has_ipv6`), which the hook also refused.
"Next pulls" = the week at A30, `headers --pull F1`, the larger advice kept, then F1 (5,000 calls, 170,000), F2
(2,280, 48,000), F3a (570, 36,000) and odds-pull (754, 8,000) at A60, HB1/HS1 (420, 16,000) at A30, one key, header
state carried over: every honest scenario, fault cases included, finished all six.

Stability over 30 seeds for the varying headers (manifests from the real client, read by `headers.analyze`, the function
the stage prints):

| manifest | header | verdicts (of 30) | lateness shown, min-max | true | smallest A30 / A60 shown | 2 x true x U |
|---|---|---|---|---|---|---|
| P0 | late 0-3 | late 30 | 3-87 | 3 | 5,000 / 5,000 | 5,000 / 5,000 |
| P0 | late 0-20 | late 30 | 20-231 | 20 | 5,000 / 5,000 (largest 13,860 / 27,720) | 5,000 / 5,000 |
| P0 | late 0-100 | late 24, steps 6 | 97-289 | 100 | 5,820 / 11,640 | 6,000 / 12,000 |
| P0 | late 100, steps 100 | late 30 / steps 30 | 100 / 99 | 100 / 99 | 6,000 / 12,000; 5,940 / 11,880 | same |
| F1 1,000 calls | late 0-3 / 0-20 | late 30 / late 30 | 3 / 18-19 | 3 / 20 | 5,000 / 5,000 | 5,000 / 5,000 |
| F1 1,000 calls | late 0-100 | steps 29, late 1 | 91-99 | 100 | 5,460 / 10,920 | 6,000 / 12,000 |
| week (F1 150 + F2 60) after a probe-like run | late 0-3 / 0-20 | late 30 / late 29, steps 1 | 3-89 / 19-169 | 3 / 20 | 5,000 / 5,000 | 5,000 / 5,000 |
| week after a probe-like run | late 0-100 | late 18, steps 12 | 88-196 | 100 | 5,280 / 10,560 | 6,000 / 12,000 |

The runbook's new step through the real CLI (`$S/revB/cli_seq.sh`, NFL only, `--sports americanfootball_nfl`):
header late 100 fixed: `probe --confirm --max-credits 11000` printed `key ok: ...` then `alarm margin: 5,000 credits
(the default: ...)`, `P0 done`; `headers --pull P0` said `late by up to 100 answers`, advised 6,000 and (per-call 60)
12,000; `week --pull F1 ... --alarm-margin 6,000` printed `alarm margin: 6,000 credits (set by --alarm-margin)` and
finished; `headers --pull F1` late by 100, 6,000 / 12,000; `full --pull F1 ... --max-credits 170000 --alarm-margin
6000`: `done: 1,534 fetched, credits 46,020`, billed 46,020. Then `headers --pull F1` on that full run said `late by up
to 2 answers`, advice 5,000 (finding B3). Header refreshed every 100: 5,940 / 11,880 all through, every run finished.

`--alarm-margin`: `299`, `0`, `-5` refused by argparse with `argument --alarm-margin: 299 is below 300; the alarm's
margin is at least 300 credits`, exit 2 (odds5m and odds-pull); `300` and `23,940` accepted; with `plan` or `headers`:
`--alarm-margin works with probe, week and full, not plan`, exit 1. The margin in force is printed on the line after
`key ok:` by probe, week, full (CLI) and odds-pull (`pull_snapshots` in-process: `alarm margin: 5,000 credits (the
default: ...)` and, with 12,000, `alarm margin: 12,000 credits (set by --alarm-margin)`).

After any stop the same client refuses every later attempt (`$S/revB/stopcheck.py`): budget before a call, count past
the budget after an answer (rule 3b, provoked by switching off only the budget part of the pre-check), floor, alarm,
billed above the upper bound, billing unreadable, billing untrusted, balance unreadable with a floor, 5 errors in a row,
401, 429 after retries, no answer after the retries, a retried 500 billed above its bound, Ctrl-C with a request out,
and odds-pull's client billed above its bound: each time three further `fetch` calls raised the same stop object and
sent 0 requests. In the step 3/4 simulations every stopped run (budget, alarm, network) passed the same check.

## Findings

### B1. BLOCKER under this review's test (default margin); not reproduced with the runbook's printed commands. With the default margin, an honest F3a with a balance header late by a varying 0-100 answers stops on the alarm; so does odds-pull right after F3a.

- Rule/brief: step 3 (false stops); the brief's claim "a balance header that is late, by any number of answers and by
  a varying number, ... can never stop an honest run"; realistic set (late up to 100, varying; others up to 500).
- Commands (from `$S/pr63/sharp-markets`, `MARKETS_DATA_DIR=$S/revB/data ODDS_API_KEY=FAKESECRETKEY999`):
  `uv run python $S/revB/repro_f3a.py 0` (one run, logging on) and `uv run python $S/revB/sim.py $S/revB/step3c.json 0 1 out`
  (100 seeds each).
- Output (570 event-odds calls at 60, reported truly; budget 36,000 as the runbook's F3a; fresh key; nobody else spending):
  ```
  alarm margin: 5,000 credits (the default: the larger of 5,000 and 10% of --max-credits)
  WARNING markets.oddsapi.bulk: the reported balance rose from 4,991,360 to 4,996,760 during the run, more than the margin of 5,000: credits were added or the month renewed; the run starts again from there
    STOPPED: the account has fallen by 5,160 credits more than this run counted (the margin is 5,000; ...
  API charged 9,360; run counted 9,360; charged beyond the count 0; others spent 0
  ```
  100/100 runs (late 0-100), 3/100 (late 0-85), 0/100 (late 0-80). In the day-one sequence: F3a after F2 with 500
  others, 100/100; odds-pull right after F3a (every prop quoted), header late 100 fixed + 500 others, 92/100; late
  0-100 + 500 others, 35/100 (all default margin 5,000). With `--alarm-margin 12,000` (or the 11,880 steps advice):
  0/100 in every one of these.
- Cause: rule 6 as the hub wrote it, implemented exactly (bulk.py:564-572): a reading from 90 answers back is 5,400
  higher (90 x 60), more than the 5,000 margin, so it is taken as credits added and the run restarts from a stale
  balance; when the header catches up the gap shows as an unexplained fall. For odds-pull, the key check reads a
  balance that hides F3a's last 100 answers (6,000), plus 500 from others. Whenever lateness x per-call cost exceeds
  the margin this happens; 100 x 60 = 6,000 is inside the realistic set, the default margin is 5,000.
- Why not a blocker as printed: the runbook's F3a and odds-pull commands carry `--alarm-margin A60`, and `headers`
  on the probe advised at least 11,640 for this header (30 seeds of `hdr_seeds.py`; 11,640-12,360 in the 10 of `clear_f3a.py`); with 12,000 or 11,880, 0 false alarms. It is also cheap to clear:
  `$S/revB/clear_f3a.py 10` ran probe, F2 and F3a at the default margin on one key; F3a false-alarmed 10/10;
  `uv run markets odds5m headers --pull F3 --per-call 60` said late by up to 95-99 answers (or "steps, about every
  96-99") and advised 11,400-11,880; the rerun with it finished 10/10.
- No code fix within the rule: it needs a hub decision (for example a default margin of at least 2 x 100 x the call's
  upper bound, i.e. 12,000 for 60-credit pulls, or accept that the runbook's A60 is required on F3a and odds-pull).

### B2. BLOCKER by the brief's literal definition (fault case: credits lost beyond what the runbook states); the fix is one runbook sentence or a hub decision, not code. Credits added mid-run, followed by under-reporting, add to the loss.

- Rule: runbook's "What can still be lost" (ODDS5M_DAY_ONE.md:67-73): "up to the margin, plus the charges of as many
  answers as the balance header is late, plus one call's extra".
- Command: `uv run python $S/revB/sim.py $S/revB/step4.json 0 1 out` (settings "F1 ; top-up ...").
- Output (F1, 2x from answer 1,000 on, margin 15,750): a top-up of 3,000 or 15,000 (at most the margin) just before:
  loss 18,780 and 30,780 against the stated 15,780 (live); 18,930-18,960 and 30,960 against 15,960 (late 3, 0-3).
  A top-up of 1,000,000: 15,810 against 15,780 (live), 16,020 against 15,960 (late 0-3).
- Cause: rule 6 (bulk.py:564-572). A rise at most the margin is ignored as out of date, so the added credits absorb
  overcharges before the alarm can see them: the loss grows by the addition. A rise above the margin restarts the
  count from the reading that shows it, which absorbs the overcharge of the answers between the top-up and that
  reading (one or two calls' extra, 30-60 here).
- Realism: credits are added mid-month only by a plan change or the renewal (large), so a small addition during an
  under-reporting run is unlikely; the 1,000,000 case is off by 30-60 credits. A sentence such as "plus any credits
  added during the run, if no more than the margin, plus one more call's extra when credits are added" would make the
  runbook match.

### B3. MAJOR (the `headers` verdict or advice wrong on test manifests); low practical impact. `headers`' lateness figure is unreliable in three ways.

- Rule: brief step 8b ("Is the verdict right each time ... advised margin the larger of the default and 2 x lateness x
  the per-call cost?").
- (a) A fixed lateness is invisible in a run that starts right after another run. `$S/revB/cli_seq.sh late100
  '{"header":"late","k":100,"seed":1,"sweep_data_share":0.9}'`: after `full --pull F1` (run straight after the week),
  `uv run markets odds5m headers --pull F1` printed:
  ```
    charged answers that showed no fall in the balance: 9 of 1,534; the longest stretch in a row: 2 answers
    the header's lateness: 2 answers (... in this run or the paid run before it; 2 in this run)
  The balance header runs late by up to 2 answers.
  Smallest --alarm-margin advised for a pull whose calls cost up to 30 credits: 5,000
  ```
  (true lateness 100: 6,000 / 12,000). Cause: the stretch appears only when the key check is current; a late key
  check shows the previous run's charges in the first answers as falls. `_runs` (headers.py:44-56) looks one run back,
  which rescues `headers --pull F1` after the week (the probe is the run before) but not later pulls.
- (b) A lateness that varies 0-100 is often called "refreshed in steps" and measured low: F1 1,000-call manifests,
  29/30 seeds `The balance header is refreshed in steps, about every 92-100 answers`, lateness 91-99, advice down to
  5,460 / 10,920 (vs 6,000 / 12,000); the week after a probe, 12/30 "steps", advice down to 5,280 / 10,560. Cause:
  headers.py:109 (`2 * no_fall > charged` means "steps"; with a uniformly varying lag about half of the charged
  answers show no fall), and the maximum of a random lag is sampled, not known.
- (c) The probe's lateness is overstated when an out-of-date rise hides the seven 30-60-credit probes: header late by
  at most 20 answers, `uv run python $S/revB/over.py` then `uv run markets odds5m headers --pull P0`:
  ```
    the header's lateness: 166 answers (the longer of that stretch and the answers' worth of charges hidden by the largest out-of-date rise ...)
  The balance header runs late by up to 166 answers.
  Smallest --alarm-margin advised ... 30 credits: 9,960 ... 60 credits: 19,920
  ```
  (30 seeds: 20-231 answers, A60 up to 27,720, true need 5,000). Cause: headers.py:92 converts the largest rise into
  answers with the run's average charge per answer (`stale * len(run) / counted`, about 0.92 on the probe), while
  the rise is a few expensive answers. This is the PR's "choice 1".
- Impact found: none of the three caused a false alarm or a missed stop in my runs. (a) and (b) err low but the factor 2
  covers them (hidden amount at most 100 x 60 = 6,000 < 10,560), and the runbook keeps the larger figure from the
  probe; (c) errs high: a margin up to 27,720 widens the fault-case loss bound by about 22,700 credits (about 54 cents).
  (a) matters after an alarm on a later pull: `headers` on that pull can advise less than the probe did; the runbook's
  "use the larger figure" line (step 4) covers day one, but the alarm row of the table says to rerun "with the
  `--alarm-margin` it advises", which could be the smaller figure.

### B4. MAJOR by the "runbook sentence" rule, low impact: two runs at once go more than "a few calls" past the floor when the header is late.

- Runbook ODDS5M_DAY_ONE.md:86: "Run one `markets` command at a time: two at once see each other's spending (far from
  the floor that raises the alarm; near it, each can go a few calls past the floor)."
- Command: `uv run python $S/revB/step4x.py out.json`. Output (two F1 clients 3,000 above the floor, 100 seeds): live
  30 below the floor (1 call), late 3: 120 (4 calls), late 0-100: up to 960, steps 100: up to 2,970, late 100: 3,000
  (100 calls). Far from the floor (30,000 above) both stopped on the alarm, as the sentence says.
- Cause: each client's estimate of the balance (bulk.py:548-550) sees the other's charges only as late as the header.
  Running two at once is forbidden by the runbook, and 3,000 credits is 7 cents of a 531,630 reserve; the sentence
  could say "a few calls, or as many as the header is late".

### Questions for the hub (the PR's three choices, judged against the brief)

1. Lateness = the longer of the brief's stretch and "the answers' worth of charges hidden by the largest out-of-date
   rise", in this run or the run before. Consistent with the brief's intent (measure lateness; when in doubt a wider
   margin), a deviation from its wording. It errs high on the probe (B3c) and does not fix the back-to-back blind spot
   (B3a). No false alarm or missed stop in the realistic set came from it.
2. "Fell by more than counted" only above max(200, 1% of the count) + lateness x the largest charge (headers.py:105).
   Consistent with the brief's rules as far as I could test: another spender of 500 during the probe, and 2x
   overcharging, both gave the fourth verdict. But the allowance grows with lateness: with a header late by 100 the
   probe's allowance is 6,200 credits, so a 500 spender is reported as "late by up to 100" (table above), and a probe
   overcharge up to about 6,200 would not produce the fourth verdict (the probe's own alarm at 5,000 still bounds it).
   Also: the realistic set allows 500 credits of other spending per run, and 500 during the probe gives the fourth
   verdict, i.e. "stop day one and tell the owner"; that is the brief's own instruction for that verdict, so a
   question, not a false stop.
3. The 60,000 day-one threshold on A30: consistent with the rules; in the realistic set A30 is at most 6,000 (header
   late 100), far below. A header that never moves gives A30 626,460 on the probe, so day one stops. On a
   1,000-answer run the same header gives exactly 60,000, which is not "above 60,000"; day one applies the check to the
   probe (10,441 answers), so it does not matter there.

### Minor

- The probe's budget (11,000 for 10,704 at most) stops the probe on its budget in 100/100 runs when 5% of tries time
  out (P0+ rows); expected, and the runbook's "rerun until `P0 done`" handles it.

## Checked and found correct

- Step 3: no honest run stopped on the floor, on the budget without timeouts, or on the alarm, in any realistic
  setting with the default margin for 30-credit, 20-credit, 10-credit and 1-credit pulls (F1, F2, N0, HB1, probe),
  including back-to-back runs and the day-one sequence; the count was never below what was charged; budget stops
  appeared only with timeouts (and then always with `unanswered` > 0).
- Step 4: every overcharging setting (2x, 10x, flat 300 as 30; live, late 1-3, 0-3) stopped on the alarm, 100%, loss
  within margin + lag x charge + one call's extra; the frozen-balance case has no limit, as the runbook says.
- Q3: after every kind of stop the client refuses further attempts with the same stop and sends nothing (14 kinds +
  odds-pull), and in every stopped simulation.
- `headers`: one verdict of the fixed set, exit 0, no network, advice = max(5,000, 2 x lateness x U) for the lateness it
  shows (U 30 and 60), right verdicts for live, fixed late 3/20/100, steps 50/100, another spender, 2x, a 1,000,000
  top-up, no run; honest next pulls with its advice all finished (fault cases steps 400, late 200 and frozen too).
- `--alarm-margin` below 300 refused (exit 2) on odds5m and odds-pull; margin printed right after `key ok:`.

## Not checked

- The full runbook rehearsal (all sports, every command as printed) is another reviewer's; my CLI walks used
  `--sports americanfootball_nfl`. odds-pull through the CLI with `--confirm` needs the Kalshi sample-week cache
  (not in this checkout); I ran `pull_snapshots` in-process instead.
- Lateness measured in time rather than answers (a header that catches up while nobody calls) was not modelled; my
  lateness is in answers, as the brief defines it, which is the pessimistic case between commands.

## Files

Scripts: `$S/revB/fakeapi.py`, `sim.py`, `mkspecs.py` (specs `step3.json`, `step3b.json`, `step3c.json`,
`step4.json`), `analyze.py`, `step4x.py`, `stopcheck.py`, `hdr.py`, `hdr_seeds.py`, `over.py`, `repro_f3a.py`,
`clear_f3a.py`, `oddspull_margin.py`, `cli_seq.sh`, `hook/sitecustomize.py`. Raw results: `step3_0.out`, `step3_1.out`,
`step3b.out`, `step3c.out`, `step4.out`, `step4x.json`, `hdr.out`, `hdr_seeds.json`, `stopcheck.out`, `cli_late100.log`,
`cli_steps100.log`, `clear_f3a.log`. Tables: `step3_table.md`, `step4_table.md`, `hdr_table.md`.

## Appendix A: step 3, every setting

| group | setting | runs | finished | budget stop (timeouts) | budget stop (NOT timeouts) | floor | FALSE ALARMS | other stops | count < charged | refused after stop | margin |
|---|---|---|---|---|---|---|---|---|---|---|---|
| isolated | F1 ; live ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late 1 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late 2 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late 3 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late rand 0-3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; steps every 50 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; steps every 400 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; frozen ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; timeouts 1% unbilled ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; timeouts 5% unbilled ; default margin | 100 | 33 | 67 | 0 | 0 | **0** | 0 | 0 | 67/67 | 15,750 |
| isolated | F1 ; timeouts 20% unbilled ; default margin | 100 | 0 | 95 | 0 | 0 | **0** | no-answer-after-retries 5 | 0 | 100/100 | 15,750 |
| isolated | F1 ; timeouts 1% billed ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; timeouts 5% billed ; default margin | 100 | 33 | 67 | 0 | 0 | **0** | 0 | 0 | 67/67 | 15,750 |
| isolated | F1 ; timeouts 20% billed ; default margin | 100 | 0 | 95 | 0 | 0 | **0** | no-answer-after-retries 5 | 0 | 100/100 | 15,750 |
| isolated | F1 ; others 5/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; others 50/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; others 500/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late 20 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late 20 ; advised 5,000 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | F1 ; late rand 0-20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late rand 0-20 ; advised 5,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | F1 ; late 100 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late 100 ; advised 6,000 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| isolated | F1 ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; late rand 0-100 ; advised 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| isolated | F1 ; steps every 100 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; steps every 100 ; advised 5,940 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,940 |
| isolated | F1 ; others 500 in one lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| isolated | F1 ; WORST REALISTIC: late rand 0-100 + 5% billed timeouts + others 500 lump ; default margin | 100 | 25 | 75 | 0 | 0 | **0** | 0 | 0 | 75/75 | 15,750 |
| isolated | F3 ; live ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late 1 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late 2 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late 3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late rand 0-3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; steps every 50 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; steps every 400 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; frozen ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; timeouts 1% unbilled ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; timeouts 5% unbilled ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; timeouts 20% unbilled ; default margin | 100 | 95 | 0 | 0 | 0 | **0** | no-answer-after-retries 5 | 0 | 5/5 | 31,500 |
| isolated | F3 ; timeouts 1% billed ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; timeouts 5% billed ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; timeouts 20% billed ; default margin | 100 | 95 | 0 | 0 | 0 | **0** | no-answer-after-retries 5 | 0 | 5/5 | 31,500 |
| isolated | F3 ; others 5/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; others 50/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; others 500/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late 20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late 20 ; advised 5,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | F3 ; late rand 0-20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late rand 0-20 ; advised 5,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | F3 ; late 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late 100 ; advised 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| isolated | F3 ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; late rand 0-100 ; advised 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| isolated | F3 ; steps every 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; steps every 100 ; advised 11,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 11,880 |
| isolated | F3 ; others 500 in one lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | F3 ; WORST REALISTIC: late rand 0-100 + 5% billed timeouts + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| isolated | P0 ; live ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late 1 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late 2 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late 3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late rand 0-3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; steps every 50 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; steps every 400 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; frozen ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; timeouts 1% unbilled ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; timeouts 5% unbilled ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; timeouts 20% unbilled ; default margin | 100 | 90 | 0 | 0 | 0 | **0** | no-answer-after-retries 10 | 0 | 10/10 | 5,000 |
| isolated | P0 ; timeouts 1% billed ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; timeouts 5% billed ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; timeouts 20% billed ; default margin | 100 | 90 | 0 | 0 | 0 | **0** | no-answer-after-retries 10 | 0 | 10/10 | 5,000 |
| isolated | P0 ; others 5/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; others 50/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; others 500/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late 20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late rand 0-20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; steps every 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; others 500 in one lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| isolated | P0 ; WORST REALISTIC: late rand 0-100 + 5% billed timeouts + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| back-to-back | F1 after 500 F1 ; late 3 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; late rand 0-3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; steps every 50 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; steps every 50 ; advised 5,000 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| back-to-back | F1 after 500 F1 ; late 20 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; late 20 ; advised 5,000 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| back-to-back | F1 after 500 F1 ; late rand 0-20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; late rand 0-20 ; advised 5,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| back-to-back | F1 after 500 F1 ; late 100 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; late 100 ; advised 6,000 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| back-to-back | F1 after 500 F1 ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; late rand 0-100 ; advised 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| back-to-back | F1 after 500 F1 ; steps every 100 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; steps every 100 ; advised 5,940 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,940 |
| back-to-back | F1 after 500 F1 ; steps every 400 ; default margin | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 15,750 |
| back-to-back | F1 after 500 F1 ; steps every 400 ; advised 23,940 | 10 | 10 | 0 | 0 | 0 | **0** | 0 | 0 | - | 23,940 |
| back-to-back | F3 after 500 F3 ; late 3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; late rand 0-3 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; steps every 50 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; steps every 50 ; advised 5,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,880 |
| back-to-back | F3 after 500 F3 ; late 20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; late 20 ; advised 5,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| back-to-back | F3 after 500 F3 ; late rand 0-20 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; late rand 0-20 ; advised 5,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| back-to-back | F3 after 500 F3 ; late 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; late 100 ; advised 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| back-to-back | F3 after 500 F3 ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; late rand 0-100 ; advised 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| back-to-back | F3 after 500 F3 ; steps every 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; steps every 100 ; advised 11,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 11,880 |
| back-to-back | F3 after 500 F3 ; steps every 400 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 31,500 |
| back-to-back | F3 after 500 F3 ; steps every 400 ; advised 47,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 47,880 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; live + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 17,000 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; late 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 17,000 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; late 100 + others 500 lump ; runbook A30 = 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; late rand 0-100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 17,000 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; late rand 0-100 + others 500 lump ; runbook A30 = 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 17,000 |
| day-one sequence | DAY ONE F1 full (5,000 of ~5,400 calls, 170,000) after F1,F2 week ; steps every 100 + others 500 lump ; runbook A30 = 5,940 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,940 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; live + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; late 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; late 100 + others 500 lump ; runbook A30 = 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; late rand 0-100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; late rand 0-100 + others 500 lump ; runbook A30 = 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F2 full (2,280 calls, 48,000) after F1 full ; steps every 100 + others 500 lump ; runbook A30 = 5,940 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,940 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; live + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; late 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; late 100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; late rand 0-100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; late rand 0-100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE F3a (570 calls, 36,000) after F2 full ; steps every 100 + others 500 lump ; runbook A60 = 11,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 11,880 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; live + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; late 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; late 100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; late rand 0-100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; late rand 0-100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE odds-pull N0 (754 calls, 8,000) after F3a ; steps every 100 + others 500 lump ; runbook A60 = 11,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 11,880 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; live + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; late 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; late 100 + others 500 lump ; runbook A30 = 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; late rand 0-100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; late rand 0-100 + others 500 lump ; runbook A30 = 6,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 6,000 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence | DAY ONE HB1,HS1 (~420 closes, 16,000) after odds-pull ; steps every 100 + others 500 lump ; runbook A30 = 5,940 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,940 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; live ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; steps every 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; timeouts 1% unbilled ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; timeouts 5% unbilled ; default margin | 100 | 0 | 100 | 0 | 0 | **0** | 0 | 0 | 100/100 | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; timeouts 20% unbilled ; default margin | 100 | 0 | 92 | 0 | 0 | **0** | no-answer-after-retries 8 | 0 | 100/100 | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; timeouts 1% billed ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; timeouts 5% billed ; default margin | 100 | 0 | 100 | 0 | 0 | **0** | 0 | 0 | 100/100 | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; timeouts 20% billed ; default margin | 100 | 0 | 92 | 0 | 0 | **0** | no-answer-after-retries 8 | 0 | 100/100 | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes; 10,704 at most) ; others 500/h ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| probe as run | P0+ (every sweep lists games, then the 7 probes) ; WORST REALISTIC: late rand 0-100 + 5% billed timeouts + others 500 lump ; default margin | 100 | 0 | 100 | 0 | 0 | **0** | 0 | 0 | 100/100 | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) odds-pull N0 (754 calls, 8,000) after F3a ; late 100 + others 500 lump ; default margin | 100 | 8 | 0 | 0 | 0 | **92** | 0 | 0 | 92/92 | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) F3a (570 calls, 36,000) after F2 full ; late 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) odds-pull N0 (754 calls, 8,000) after F3a ; late 100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) F3a (570 calls, 36,000) after F2 full ; late 100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) odds-pull N0 (754 calls, 8,000) after F3a ; late rand 0-100 + others 500 lump ; default margin | 100 | 65 | 0 | 0 | 0 | **35** | 0 | 0 | 35/35 | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) F3a (570 calls, 36,000) after F2 full ; late rand 0-100 + others 500 lump ; default margin | 100 | 0 | 0 | 0 | 0 | **100** | 0 | 0 | 100/100 | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) odds-pull N0 (754 calls, 8,000) after F3a ; late rand 0-100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) F3a (570 calls, 36,000) after F2 full ; late rand 0-100 + others 500 lump ; runbook A60 = 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) odds-pull N0 (754 calls, 8,000) after F3a ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) F3a (570 calls, 36,000) after F2 full ; steps every 100 + others 500 lump ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) odds-pull N0 (754 calls, 8,000) after F3a ; steps every 100 + others 500 lump ; runbook A60 = 11,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 11,880 |
| day-one sequence, F3a all 60 | DAY ONE (every prop quoted: F3a at 60 a call) F3a (570 calls, 36,000) after F2 full ; steps every 100 + others 500 lump ; runbook A60 = 11,880 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 11,880 |
| F3a isolated | F3a (570 calls, 36,000) at 60 a call, fresh key, no other spending ; late rand 0-100 ; default margin | 100 | 0 | 0 | 0 | 0 | **100** | 0 | 0 | 100/100 | 5,000 |
| F3a isolated | F3a (570 calls, 36,000) at 60 a call, fresh key, no other spending ; late rand 0-85 ; default margin | 100 | 97 | 0 | 0 | 0 | **3** | 0 | 0 | 3/3 | 5,000 |
| F3a isolated | F3a (570 calls, 36,000) at 60 a call, fresh key, no other spending ; late rand 0-80 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| F3a isolated | F3a (570 calls, 36,000) at 60 a call, fresh key, no other spending ; late rand 0-100 ; --alarm-margin 12,000 | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 12,000 |
| F3a isolated | F3a (570 calls, 36,000), props 2-6 quoted (20-60 a call), fresh key ; late rand 0-100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |
| F3a isolated | odds-pull N0 (754, 8,000) after F3a at 60 a call, no other spending ; late 100 ; default margin | 100 | 100 | 0 | 0 | 0 | **0** | 0 | 0 | - | 5,000 |

## Appendix B: step 4, every setting

| setting | runs | stopped on the alarm | other stops | max loss beyond the count | bound: margin + lag x charge + one call's extra | within | max fetched |
|---|---|---|---|---|---|---|---|
| F1 ; 2x ; live | 10 | 10 | 0 | 15,780 | 15,780 | yes | 526 |
| F1 ; 2x ; late 1 | 10 | 10 | 0 | 15,840 | 15,840 | yes | 528 |
| F1 ; 2x ; late 2 | 10 | 10 | 0 | 15,900 | 15,900 | yes | 530 |
| F1 ; 2x ; late 3 | 10 | 10 | 0 | 15,960 | 15,960 | yes | 532 |
| F1 ; 2x ; late rand 0-3 | 100 | 100 | 0 | 15,930 | 15,960 | yes | 531 |
| F1 ; 10x ; live | 10 | 10 | 0 | 15,930 | 16,020 | yes | 59 |
| F1 ; 10x ; late 1 | 10 | 10 | 0 | 16,200 | 16,320 | yes | 60 |
| F1 ; 10x ; late 2 | 10 | 10 | 0 | 16,470 | 16,620 | yes | 61 |
| F1 ; 10x ; late 3 | 10 | 10 | 0 | 16,740 | 16,920 | yes | 62 |
| F1 ; 10x ; late rand 0-3 | 100 | 100 | 0 | 16,740 | 16,920 | yes | 62 |
| F1 ; flat 300 reported 30 ; live | 10 | 10 | 0 | 15,930 | 16,020 | yes | 59 |
| F1 ; flat 300 reported 30 ; late 1 | 10 | 10 | 0 | 16,200 | 16,320 | yes | 60 |
| F1 ; flat 300 reported 30 ; late 2 | 10 | 10 | 0 | 16,470 | 16,620 | yes | 61 |
| F1 ; flat 300 reported 30 ; late 3 | 10 | 10 | 0 | 16,740 | 16,920 | yes | 62 |
| F1 ; flat 300 reported 30 ; late rand 0-3 | 100 | 100 | 0 | 16,740 | 16,920 | yes | 62 |
| F3 ; 2x ; live | 100 | 100 | 0 | 31,560 | 31,560 | yes | 814 |
| F3 ; 2x ; late 1 | 100 | 100 | 0 | 31,670 | 31,680 | yes | 815 |
| F3 ; 2x ; late 2 | 100 | 100 | 0 | 31,800 | 31,800 | yes | 818 |
| F3 ; 2x ; late 3 | 100 | 100 | 0 | 31,860 | 31,920 | yes | 820 |
| F3 ; 2x ; late rand 0-3 | 100 | 100 | 0 | 31,810 | 31,920 | yes | 814 |
| F3 ; 10x ; live | 100 | 100 | 0 | 32,040 | 32,040 | yes | 101 |
| F3 ; 10x ; late 1 | 100 | 100 | 0 | 32,580 | 32,640 | yes | 102 |
| F3 ; 10x ; late 2 | 100 | 100 | 0 | 33,030 | 33,240 | yes | 103 |
| F3 ; 10x ; late 3 | 100 | 100 | 0 | 33,480 | 33,840 | yes | 104 |
| F3 ; 10x ; late rand 0-3 | 100 | 100 | 0 | 33,480 | 33,840 | yes | 101 |
| P0 ; 2x ; live | 100 | 100 | 0 | 5,001 | 5,001 | yes | 6,810 |
| P0 ; 2x ; late 1 | 100 | 100 | 0 | 5,003 | 5,003 | yes | 6,811 |
| P0 ; 2x ; late 2 | 100 | 100 | 0 | 5,005 | 5,005 | yes | 6,815 |
| P0 ; 2x ; late 3 | 100 | 100 | 0 | 5,007 | 5,007 | yes | 6,816 |
| P0 ; 2x ; late rand 0-3 | 100 | 100 | 0 | 5,006 | 5,007 | yes | 6,814 |
| P0 ; 10x ; live | 100 | 100 | 0 | 5,004 | 5,009 | yes | 775 |
| P0 ; 10x ; late 1 | 100 | 100 | 0 | 5,013 | 5,019 | yes | 776 |
| P0 ; 10x ; late 2 | 100 | 100 | 0 | 5,022 | 5,029 | yes | 777 |
| P0 ; 10x ; late 3 | 100 | 100 | 0 | 5,031 | 5,039 | yes | 778 |
| P0 ; 10x ; late rand 0-3 | 100 | 100 | 0 | 5,031 | 5,039 | yes | 777 |
| F1 ; 2x ; frozen | 3 | 0 | {'finished': 3} | 150,000 | none (frozen header: no limit) | - | 5,000 |
| F1 ; 10x ; frozen | 3 | 0 | {'finished': 3} | 1,350,000 | none (frozen header: no limit) | - | 5,000 |
| F1 ; flat 300 reported 30 ; frozen | 3 | 0 | {'finished': 3} | 1,350,000 | none (frozen header: no limit) | - | 5,000 |
| F1 ; top-up 1,000,000 at 20% then 2x ; live | 10 | 10 | 0 | 15,810 | 15,780 (+ top-up 1,000,000 if it is <= margin) | yes, with the top-up | 1,526 |
| F1 ; top-up 1,000,000 at 20% then 2x ; late 3 | 10 | 10 | 0 | 15,900 | 15,960 (+ top-up 1,000,000 if it is <= margin) | yes | 1,529 |
| F1 ; top-up 1,000,000 at 20% then 2x ; late rand 0-3 | 100 | 100 | 0 | 16,020 | 15,960 (+ top-up 1,000,000 if it is <= margin) | yes, with the top-up | 1,533 |
| F1 ; top-up 15,000 at 20% then 2x ; live | 10 | 10 | 0 | 30,780 | 15,780 (+ top-up 15,000 if it is <= margin) | yes, with the top-up | 2,025 |
| F1 ; top-up 15,000 at 20% then 2x ; late 3 | 10 | 10 | 0 | 30,960 | 15,960 (+ top-up 15,000 if it is <= margin) | yes, with the top-up | 2,031 |
| F1 ; top-up 15,000 at 20% then 2x ; late rand 0-3 | 100 | 100 | 0 | 30,960 | 15,960 (+ top-up 15,000 if it is <= margin) | yes, with the top-up | 2,031 |
| F1 ; top-up 3,000 at 20% then 2x ; live | 10 | 10 | 0 | 18,780 | 15,780 (+ top-up 3,000 if it is <= margin) | yes, with the top-up | 1,625 |
| F1 ; top-up 3,000 at 20% then 2x ; late 3 | 10 | 10 | 0 | 18,960 | 15,960 (+ top-up 3,000 if it is <= margin) | yes, with the top-up | 1,631 |
| F1 ; top-up 3,000 at 20% then 2x ; late rand 0-3 | 100 | 100 | 0 | 18,930 | 15,960 (+ top-up 3,000 if it is <= margin) | yes, with the top-up | 1,630 |
