# Audit 3, addendum (Tuesday, September 29, 8:20 PM Pacific): what changed since the script was written

Paste this with the original script. Where the two disagree, this addendum wins.

## The main change: audit the amended price engine, not the one on `main`

Since the script was written, the hub's own checkers found twelve defects in the price engine (D1 to D12
below), and a dated amendment that addresses them is drafted and reviewed but **not yet registered**: pull
request 85, branch `price-engine-amendment-1`. The hub registers it (merges it) on **Wednesday, September 30,
at about 9:00 AM Pacific**, before Thursday's pull. Your report is most useful if it is in
`~/Documents/Codex/2026-09-29/audit-3/astra-audit-3.md` by **8:30 AM Wednesday**, so that what you find goes
into the amendment before it is registered.

So for Part A, work on the branch, not on `main`:

```
git -C ~/code/value-finder fetch origin price-engine-amendment-1
git -C ~/code/value-finder archive origin/price-engine-amendment-1 | tar -x -C <your scratch>/amended
```

(`git archive` and `tar` read the checkout without changing it. Do not check the branch out in
`~/code/value-finder`.) Compare with an export of `751ff67` (the registering commit) and of `origin/main`.

### What the checkers found (do not report these again unless the amendment fails to fix or state them)

| # | Finding | The amendment's answer |
|---|---|---|
| D1 | Two F1 calls answered with the same snapshot inside one batch of 50 dropped the whole snapshot, logged under the wrong reason | Repaired: a snapshot is read once and the second copy is counted as `duplicate_snapshot` |
| D2 | Condition A2 counted seasons by bets with a Pinnacle close; the registered sentence counts all bets; the two disagree in both directions | A season counts with 20 or more bets; it is "above zero" only with 20 or more graded bets and mean CLV above zero; A2 needs 3 counted seasons, 3 seasons with 20 or more graded bets, and all counted seasons but at most one above zero |
| D3 | K2 never fires with no matched result, so a cell could "act" with no realized result at all | A primary cell with fewer than 100 bets that have a final score cannot reach "act" |
| D4 | K3 has no tie rule for the book with the most bets | Each tied book is removed in turn; K3 kills if any removal leaves CLV at or below zero |
| D5 | The 9-day early cut drops a quote the 7-day rule keeps when a game is moved earlier by more than 2 days | Stated as a known limit |
| D6 | The college team-name prefix rule can send a plausible spelling to the wrong school | An alias table before the prefix rule; a names-only check on the probe's schedules on Thursday before any price is opened |
| D7 | The score readers loaded 2026 rows and then dropped them, though the registration says "never loads" | The readers filter on season as they read |
| D8 | H2's "biggest gap, then best price" is coded as gap × 1000 + price | Stated |
| D9 | The outside audit's size projection was wrong by about 10× | Measured: about 3 minutes and 7.6 GB at full size on made-up data of F1's shape |
| D10 | The college football alert has no paper-only marker | Left for the hub (tied to the owner's money-gate decision) |
| D11 | `origin/ledgers` had no `runs.csv` yet | The first run of the new nightly copy is tonight at 11:45 PM |
| D12 | The outside audit's own evidence was broken in places | Noted |

### What to do on the branch (this replaces the weighting of Part A; the A-table's claims still apply)

1. **Does the code do what the amendment's text says, item by item?** Read the new "Amendment 1" section of
   `sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md` against the diff. Every sentence must be true of the
   code.
2. **Does the amendment change anything it does not declare?** Run `uv run markets price-engine --fixture` on
   the `751ff67` export and on the branch, and compare `results.csv`, `dropped.csv` and the content of
   `bets.parquet`. Then build a larger made-up input of your own with repeated snapshots, missing Pinnacle
   closes, moved kickoffs, pushes, tied books and names that need the aliases. Every number that differs
   between `751ff67` and the branch must be explained by a numbered item of the amendment.
3. **Is any verdict now EASIER to reach than under the registration as written?** Construct cells that pass
   under the branch and fail under the registered text, for A2, K2, K3 and the loading repair. The hub's
   position is that the loading repair and the aliases add data (so a verdict can move either way) and that
   every other item only makes a verdict harder. Test that position.
4. **What did everyone miss?** The A-table's claims A1 to A14 still stand as the checklist. Lookahead (A1, A2),
   the sealed season (A3), signs and orientation (A6), score matching (A7) and the decision rule (A9) matter
   most; break-test them on the branch with your own synthetic inputs.
5. **The names preflight** (`names_preflight.py` on the branch): does it read names, kickoffs and event ids
   only, never a price or a result? Could it be run on Thursday's probe schedules without opening a price?

## Part B: unchanged, plus one optional item

Everything in Part B stands. One addition, if time allows:

- **B9.** A draft amendment for Rule HT and games with no kickoff time is on branch `rule-ht-no-kickoff-time`
  (pull request 86; not registered; Rule HT starts October 6). Its reading: a game with no kickoff time set is
  not eligible for Rule HT until the time is set. Does the code on that branch do what the draft says, can it
  use information from after the real kickoff, and does the scorer treat a game whose time was set late the way
  the draft says?

## Part C: audit pull request 87's head, which holds pull request 63 plus its last fixes

Pull request 63 is still open. Its last independent review produced fixes, which are on branch
`claude/quirky-goldberg-81hwy6` (pull request 87, into `bulk-puller-followup`). Audit that branch. If 87 has
merged by the time you run, audit `origin/bulk-puller-followup` instead. Your C1 to C6 are the checklist;
rerun your audit-2 scripts against it.

## Updated facts

- `main` has moved: it is at `30444ec` or later. The weather projects' alert code did not change today; the
  scorers did not change on `main`.
- Suite counts on `main` now: nfl-weather 338 passed and 1 skipped; cfb-weather 330 passed and 2 skipped;
  sharp-markets 190; dashboard 258. On the amendment branch, sharp-markets has more.
- Free Odds API credits: 485. Hard rule 2 stands: never run `scripts/alerts.py`, not even with `--dry-run`.
- The repo now has `ops/mac_check.sh` (a read-only check of this Mac) and a PreToolUse hook in
  `.claude/settings.json` that concerns Claude sessions only; neither is in scope.
- The owner moves the project to a new Mac on Wednesday from about 11:40 AM; run your audit before then.

## Report

As in the script, with one more line in the verdict: **is pull request 85 safe to register as it stands, and
if not, which sentence or line must change first?**
