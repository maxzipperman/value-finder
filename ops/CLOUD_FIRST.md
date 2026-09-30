# Cloud first

**The rule, in your words (September 29, 2026):** "i would prefer to use Cloud session credits vs local on mac claude chats".

**In plain words:** work that needs only what is in git runs in the cloud, on cloud session credits. Work runs on this Mac, on the plan's limits, only when it needs the Mac: its keys, its raw data, its scheduled jobs, its live checkout, its hardware, or a token in the home folder. The plan's limits are kept for the hub.

## What runs where

| Where | What | Paid from |
|---|---|---|
| The cloud worker | Code, docs, analysis on `data/processed/`, reviews, research: anything that needs only git | Cloud session credits |
| A local worker chat, agent or workflow | Only work that needs this Mac, and it says which need | The plan |
| The hub itself | Check-ins, small Mac-only jobs, merging, `STATUS.md` | The plan |

## What you will see

A hook ([`hooks/cloud_first.py`](hooks/cloud_first.py), set in `.claude/settings.json`) checks every agent and workflow a chat on this Mac starts in this repo, the hub and local worker chats alike. When one doesn't say why it needs the Mac, the hook blocks it, and the chat tells you so. It then either sends the work to the cloud worker, or starts it again with a line giving its reason:

    LOCAL-BECAUSE: <reason>: <one sentence>

The reason is one of `keys`, `raw-data`, `jobs`, `live-checkout`, `hardware`, `home-token` or `owner-asked`, and the sentence must be at least 15 characters, not counting spaces at either end. For a workflow the line goes in its script, as a comment (`// LOCAL-BECAUSE: ...`); a workflow whose script file the hook can't read is blocked. If the hook itself breaks, it lets the call through and says the check could not run: it never stops the hub on the day of a pull. Cloud sessions are never blocked.

The hub also reads the plan's weekly figure at each check-in. Above 60% it starts nothing local without your word, except a job that protects the live forward tests or the paid data; above 85% it starts nothing local at all.

## Switching it off (your decision)

- Set `VF_CLOUD_FIRST=off` in the environment the app runs in (for example `launchctl setenv VF_CLOUD_FIRST off`, then quit and reopen the app; it lasts until the Mac restarts), or
- remove the `PreToolUse` block from `.claude/settings.json`.

## What it doesn't cover

- The hub's own chat runs on this Mac and on the plan, because it needs the Mac.
- A worker chat you start yourself by clicking is your own choice. (Its agents and workflows are still checked.)
