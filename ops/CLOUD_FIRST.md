# Cloud first

**The rule, in your words (September 29, 2026):** "i would prefer to use Cloud session credits vs local on mac claude chats".

**Owner update, October 2, 2026:** prefer the installed offline coding models when appropriate. [ops/LOCAL_CODING_MODELS.md](LOCAL_CODING_MODELS.md) defines a bounded exception: local Qwen drafts suitable coding tasks; tests and the supervising assistant validate the result. Other git-only work still uses cloud session credits. This does not move ordinary work to local paid cloud-model workers.

**In plain words:** try an installed offline model for a small task with clear acceptance checks. If unsuitable or unavailable, use the cloud worker for git-only work. Local paid cloud-model workers still need a real Mac requirement. Hub coordination and all other project controls remain in force.

## What runs where

| Where | What | Paid from |
|---|---|---|
| Offline coding worker | Bounded suitable drafts, tests, documentation and refactors, with independent validation | Local inference; supervising cloud chat may still consume credits |
| The cloud worker | Git-only work unsuitable for or not completed by the offline coding route | Cloud session credits |
| A local paid cloud-model worker chat, agent or workflow | Only work that needs this Mac, and it says which need | The plan |
| The hub itself | Check-ins, small Mac-only jobs, merging, `STATUS.md` | The plan |

For an offline-model task, use the existing truthful hardware reason:

    LOCAL-BECAUSE: hardware: runs the owner-preferred offline coding model on this Mac.

The hardware reason applies to actual local inference, not a local paid cloud-model worker doing ordinary git-only work. Do not disable the hook or change the hub's provider settings to implement this preference. Cloud workers without access to the Mac's local endpoint use the cloud route and record that limitation.

## What you will see

A hook ([`hooks/cloud_first.py`](hooks/cloud_first.py), set in `.claude/settings.json`) checks three tools, `Agent`, `Task` and `Workflow`, whenever a chat on this Mac uses them in this repo, the hub and local worker chats alike. When a call doesn't say why it needs the Mac, the hook blocks it, and the chat tells you so. It then either sends the work to the cloud worker, or starts it again with a line giving its reason:

    LOCAL-BECAUSE: <reason>: <one sentence>

The reason is one of `keys`, `raw-data`, `jobs`, `live-checkout`, `hardware`, `home-token` or `owner-asked`, and the sentence must say something real (at least 15 characters; the exact checks are in the hook's docstring). For a workflow the line goes in its script, as a comment. A workflow whose script the hook can't read, such as a built-in one started by name, is always blocked: pass the script inline, or switch the rule off. If the hook breaks or its file is missing, it lets the call through, so it never stops the hub on the day of a pull. Cloud sessions are never blocked.

The hub also reports the plan's weekly figure at each check-in (you read it on the app's usage page; the hub asks for it if you haven't given it). Above 60% it starts no local paid cloud-model worker without your word, except a job that protects the live forward tests or the paid data; above 85% it starts no local paid cloud-model worker at all. These subscription thresholds do not forbid offline inference, but a supervising cloud chat still consumes its own allowance.

## Switching it off (your decision)

- Set `VF_CLOUD_FIRST=off` in the environment the app runs in (for example `launchctl setenv VF_CLOUD_FIRST off`, then quit and reopen the app; it lasts until the Mac restarts). *Untested:* the hub confirms on the Mac that a variable set this way reaches the hooks. Or
- remove the `PreToolUse` block from `.claude/settings.json`.

## What it doesn't cover

- The hub's own chat runs on this Mac and on the plan, because it needs the Mac.
- A worker chat you start yourself by clicking is your own choice. (Its agents and workflows are still checked.)
- The hook sees only `Agent`, `Task` and `Workflow` calls. It does not catch a `SendMessage` that resumes an existing local agent, a skill that forks a subagent, `spawn_task`, or the agents a workflow script starts (those are covered only through the script's own line).
- `.claude/commands/review-ideas.md` starts parallel subagents: run on this Mac, they now need the line, or the review goes to the cloud.
