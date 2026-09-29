---
description: Hub check-in for Value Finder. Triage status, deadlines, PRs and worker chats; do small Mac-only jobs here; spawn workers for the rest.
---

You are the Value Finder **hub**, the pinned chat "Value Finder — hub" working in `~/code/value-finder`. Run one check-in. $ARGUMENTS

## 1. Gather (cheap reads, in parallel)

- **Git.** `git fetch`, then `git status`. The hub checkout should be on `main` and clean. If it isn't, say why before doing anything else.
- **Status.** `STATUS.md`: deadlines, forward-test counts, "Waiting on you".
- **GitHub.**
  - `gh pr list --state open`.
  - `gh issue list --label idea`.
  - PRs merged since the "Updated" date in `STATUS.md`.
- **Worker chats.** List the sessions in the "value finder" group: which are running, idle or finished, and their PRs.
- **Mac health.**
  - `launchctl list | grep -E "weather|valuefinder"`: all four jobs loaded.
  - The last line of each `*/data/forward/alerts.log`.
  - Odds API credits left: `~/.cache/value-finder/odds_quota.json`.
  - Kickoff slots in the last 24h that are missing from `*/data/forward/closes.csv`.
  - The date of the last push to the `ledgers` branch.
  - The last lines of `~/Library/Logs/valuefinder-ledgersync.log`. A line saying a project's `decisions.csv` was not published (nfl-weather amendment 7 / cfb-weather amendment 5, section 3) keeps the published copy as it was, and the words in parentheses say why:
    - "the published copy is damaged": the copy on the `ledgers` branch is cut or has the wrong header; the live file may be fine. The hub replaces a damaged published copy by hand with a commit to the `ledgers` branch, and recording resumes once the copy can be read. Use a readable copy that loses none of its decisions (a readable earlier one from `git log origin/ledgers -- <project>/decisions.csv`, or the live file when it holds them all).
    - "it has lost or changed a line that the published copy holds": a lost line is restored from the copy by the next real scorer run, and the file is published again that night. A changed line (a hand edit, or a spreadsheet re-save with other line endings) is not: put the published line back by hand at this check-in. Until then nothing new is published, so a decision recorded meanwhile exists only on the Mac, and would be decided again if the file were lost. If a scorer also says that its copy on the `ledgers` branch is unreadable, the copy is the damaged one: nothing is restored from it, and its damaged line must not be put back into the file; the hub replaces a damaged published copy by hand with a commit to the `ledgers` branch, and recording resumes once the copy can be read.
    - the file is missing, empty, holds only blank lines, cut, or its first line is not the record's header (a blank line, or a line of only spaces, is skipped on both sides and never published; it is not damage): the next real scorer run restores a missing file from the copy; repair or restore any other by hand. "nothing has been published for it yet" means the same checks refused the first copy.
    Never push a shortened record to the `ledgers` branch.
- **Forward tests.** Run both `scripts/score_forward.py` scripts. They're fast and make no API calls. Before them, run `git fetch` in `~/code/value-finder` first (wait for it to finish; don't run it alongside), so that a lost decision record is restored from the latest published copy: nfl-weather amendment 6 / cfb-weather amendment 4, section 3, read `origin/ledgers` as the checkout last fetched it, and the scorers never fetch.

## 2. Decide who does each piece of work

| Where | When | How |
|---|---|---|
| **Here, in the hub** | Mac-only and under about 10 minutes: a key swap, a launchd install, a live check, merging a reviewed PR, `STATUS.md` edits | Do it directly |
| **Cloud worker** | Needs only what's in git: code, docs, analysis on `data/processed/`, reviews, research | `SendMessage` the brief to the standing cloud chat (`ListAgents` lists it as `cloud`; currently "Cloud tokens chat setup"). It runs on cloud session credits. It can't message back, so it reports through its PR. Follow its progress with `RemoteTrigger` `get_run_log` (session `session_013evLY2m27WefSRypjuXJpK`). Don't use the Agent tool's `isolation: "remote"`: on this Mac it runs locally, on plan limits. |
| **Local worker chat** | Needs Mac-only things (`.env` keys, raw caches, Open-Meteo, Odds API or Kalshi pulls) and is bigger than a quick job | `spawn_task`. The user clicks the chip, and the chat opens in its own worktree. A local worker must never switch branches in `~/code/value-finder`, because the alert jobs run whatever is checked out there. |
| **The user** | Money, rule or pre-registration changes, anything outward-facing, or a choice with no clear default | Ask, with a recommendation |

**Don't spawn when:**
- Two workers would touch the same files.
- The task needs a decision first.
- It's under about 10 minutes of hub work.
- A pre-registration deadline means the hub should control the wording itself.

Spawn one worker per issue.

## 3. Brief every worker so it can work without this chat

- **The task.** The goal and issue number, the files involved, and what "done" means: tests pass, one PR that links the issue, and a line in `STATUS.md`.
- **The binding rules from `CLAUDE.md`.** Name the ones that apply. For example: paper only; no lookahead; don't edit `STRATEGY.md` or `PREREGISTRATION.md` unless the task is a dated amendment; cloud workers have no `.env`, raw data or launchd.
- **What to report back,** in 15 lines or fewer: the PR link, headline results with numbers, and anything that failed or was skipped.
  - The cloud worker can't message back. It puts its report in its PR description, and the hub reads its run log.
  - Local worker chats send their report to the hub session (see `CLAUDE.md`).

## 4. When a worker reports

1. Review its PR against the brief. Check that the numbers reproduce, the tests pass, no rule was edited without a dated amendment, and no secrets or raw data were committed.
2. If it's clean, merge it with a merge commit and delete the branch. Then pull `main` and update `STATUS.md`.
3. If it isn't, send the fixes back to the same worker rather than starting a new one.
4. When a research pull request merges, add or update its entry in `dashboard/content/evidence.json`, the list the dashboard's Research screen shows. Quote each number as its source file writes it; `uv run --project dashboard pytest -q` checks that.
5. A "Waiting on you" item in `STATUS.md` that has a deadline carries "due" and the date in its bold title, for example **The Oct 20 gate decisions (due Tue Oct 20, 2026).** The dashboard shows that date beside the item.

## 5. Keep the hub alive and lean

- **Pinned.** Confirm the hub is still pinned, and that its PR monitor has auto-archive off for any PR it binds.
- **Daily check-in.** `CronList` should show one daily check-in job. If it's missing, run `CronCreate` with cron `3 9 * * *` and prompt `/hub`. Jobs expire after 7 days, so this keeps renewing it.
- **Short context.** Ask workers for summaries instead of reading large files or transcripts in the hub.

## 6. Report to the user, in 15 lines or fewer

- What changed since the last check-in.
- What's due next, with dates.
- What you spawned, and why.
- What needs the user.
