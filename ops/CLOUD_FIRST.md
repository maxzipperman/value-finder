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

A hook ([`hooks/cloud_first.py`](hooks/cloud_first.py), set in `.claude/settings.json`) checks three tools, `Agent`, `Task` and `Workflow`, whenever a chat on this Mac uses them in this repo, the hub and local worker chats alike. When a call doesn't say why it needs the Mac, the hook blocks it, and the chat tells you so. It then either sends the work to the cloud worker, or starts it again with a line giving its reason:

    LOCAL-BECAUSE: <reason>: <one sentence>

The reason is one of `keys`, `raw-data`, `jobs`, `live-checkout`, `hardware`, `home-token` or `owner-asked`. The sentence must be at least 15 characters (not counting spaces at either end), at least 10 of them letters or digits, and must not start with `<` (the template left unfilled). For a workflow the line goes in its script, as a comment (`// LOCAL-BECAUSE: ...`); when the script is passed inline, only that script counts. A workflow whose script file the hook can't read is blocked. That includes a saved, built-in or plugin workflow started by name whose file isn't in the project's or the home folder's `.claude/workflows`: it is always blocked, even with a reason, so pass the script inline with the line, or switch the rule off. (That saved workflows live in `.claude/workflows` is an assumption the hub confirms on the Mac.) If the hook itself breaks, it lets the call through and says the check could not run; if its file is missing, the call goes ahead without a word. It never stops the hub on the day of a pull. Cloud sessions are never blocked.

The hub also reports the plan's weekly figure at each check-in (you read it on the app's usage page; the hub asks for it if you haven't given it). Above 60% it starts nothing local without your word, except a job that protects the live forward tests or the paid data; above 85% it starts nothing local at all.

## Switching it off (your decision)

- Set `VF_CLOUD_FIRST=off` in the environment the app runs in (for example `launchctl setenv VF_CLOUD_FIRST off`, then quit and reopen the app; it lasts until the Mac restarts). *Untested:* the hub confirms on the Mac that a variable set this way reaches the hooks. Or
- remove the `PreToolUse` block from `.claude/settings.json`.

## What it doesn't cover

- The hub's own chat runs on this Mac and on the plan, because it needs the Mac.
- A worker chat you start yourself by clicking is your own choice. (Its agents and workflows are still checked.)
- The hook sees only `Agent`, `Task` and `Workflow` calls. It does not catch a `SendMessage` that resumes an existing local agent, a skill that forks a subagent, `spawn_task`, or the agents a workflow script starts (those are covered only through the script's own line).
- `.claude/commands/review-ideas.md` starts parallel subagents: run on this Mac, they now need the line, or the review goes to the cloud.
