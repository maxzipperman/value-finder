# Brief 2 (after brief 1): write the owner's cloud-first rule into the repo, and a hook that enforces it

## You are the cloud worker. Read this first.
- This brief comes from the Value Finder hub (the owner's pinned chat on his Mac).
- You have only what is in git, and you need nothing else for this job.
- You cannot message the hub. Put your report in the pull request's description, under a heading "Report for the hub", and add one comment on the pull request when you are done.
- The repo's CLAUDE.md applies in full.

## Why
On September 29, 2026 the owner asked the hub, in these words: "can you set up and enforce a rule that i would prefer to use Cloud session credits vs local on mac claude chats".

The facts behind it, measured the same afternoon:
- The owner's plan is Pro. Its weekly limit stood at 71% used about 22 hours into the week, almost all of it from local workers and local multi-agent workflows that the hub started. The week resets on October 6. Thursday, October 1 is the project's most important day and needs the hub.
- Cloud sessions draw on cloud session credits, which are separate.
- `.claude/commands/hub.md` already routes git-only work to the cloud worker, and already says that the Agent tool's `isolation: "remote"` runs locally on this Mac. The hub did not follow its own table after its conversation was summarized: it started six local workflows and one "remote" agent that ran locally. One local reviewer's simulations filled the Mac with 76 GB of swap and nearly filled its disk. A rule in a document was not enough. That is why the owner asked for enforcement.

## The job: ONE pull request, branch cloud-first-rule, title "Cloud first: the owner's rule, and a hook that enforces it"

You may add or edit ONLY: CLAUDE.md, .claude/commands/hub.md, .claude/settings.json, ops/hooks/cloud_first.py (new), ops/tests/test_cloud_first.py (new), ops/CLOUD_FIRST.md (new), STATUS.md (one line).

### 1. CLAUDE.md, section "The hub"
Add one bullet, in the style of the bullets there, as the FIRST bullet of the list of rules for workers:

- **Cloud first (the owner's rule, September 29, 2026).** Work that needs only what is in git runs in the cloud, on cloud session credits: the hub sends the brief to the cloud worker. A local worker chat, a local agent or a local workflow is only for work that needs this Mac: its keys, its raw data, its scheduled jobs, its live checkout, its hardware, or a token in the home folder. When the hub starts anything locally it says which of those it is. The plan's own limits are kept for the hub. A hook enforces this ([`ops/CLOUD_FIRST.md`](ops/CLOUD_FIRST.md)).

Change nothing else in CLAUDE.md except: in the bullet about the cloud worker, the chat's title changes as it works, so say "one standing cloud chat (the hub finds it with `ListAgents`; its title changes with its latest task)".

### 2. .claude/commands/hub.md
- In the routing table, make the cloud worker the FIRST row and the default, and say so in the sentence above the table.
- The cloud worker row: keep what is there; add that a long brief goes into a file on the `hub-briefs` branch (`briefs/<date>-<n>-<name>.md`), and the message to the cloud worker names the file; add that the hub never sends a message to an agent that belongs to a running workflow (on this Mac that starts a second copy of the agent).
- The local rows: add "and say why it must be local".
- Add a step to the check-in (where Mac health is checked): read the plan's limits and report the weekly figure in the check-in's first lines. Above 60% of the weekly limit the hub starts nothing local without the owner's word, except a job that protects the live forward tests or the paid data. Above 85% it starts nothing local at all and says so.
- Add to "Don't spawn when": a local multi-agent workflow for work the cloud worker can do.
- Keep the file's voice and length; do not reword what you do not need to change.

### 3. The hook
`.claude/settings.json` gains a PreToolUse hook (keep the SessionStart hook exactly as it is):

    "PreToolUse": [
      { "matcher": "Agent|Task|Workflow",
        "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/ops/hooks/cloud_first.py", "timeout": 10 } ] }
    ]

`ops/hooks/cloud_first.py`, standard library only, Python 3.9 or later:
- It reads the hook's JSON from standard input (`tool_name`, `tool_input`).
- It ALLOWS (exit 0, prints nothing) when any of these holds:
  - the environment variable `CLAUDE_CODE_REMOTE` is `true` (a cloud session may use its own subagents freely);
  - the environment variable `VF_CLOUD_FIRST` is `off` (the owner's switch);
  - the tool's input holds a line that starts with `LOCAL-BECAUSE:` followed by one of the reasons `keys`, `raw-data`, `jobs`, `live-checkout`, `hardware`, `home-token`, `owner-asked`, then a colon and at least 15 characters of explanation. Look in `prompt` and `description` for Agent and Task; in `script` for Workflow; and for a Workflow started from a file (`scriptPath`) or by `name`, read the file if it can be found under the project or the home folder, and if it cannot be read, BLOCK with a sentence saying the script could not be read.
- Otherwise it BLOCKS (exit 2) and writes to standard error, in plain words: that the owner's rule is cloud first; that work which needs only what is in git goes to the cloud worker with SendMessage (a long brief as a file on the hub-briefs branch); that work which needs this Mac is started again with the line `LOCAL-BECAUSE: <reason>: <one sentence>` in its prompt, with the list of reasons; and where the rule is written (CLAUDE.md, ops/CLOUD_FIRST.md).
- It FAILS OPEN: input that is not JSON, a missing field, or any exception allows the call and writes one line to standard error saying the cloud-first check could not run. A broken hook must never stop the hub on the day of a pull.
- It writes no file, makes no network request, reads no .env, and never prints the tool's input.

`ops/tests/test_cloud_first.py` (pytest; it runs the script as a subprocess with JSON on standard input): an Agent call without the line is blocked, with the line is allowed; each reason; a reason not on the list is blocked; an explanation shorter than 15 characters is blocked; the line inside a Workflow script; a Workflow by scriptPath whose file holds the line, one whose file does not, one whose file is missing; `CLAUDE_CODE_REMOTE=true`; `VF_CLOUD_FIRST=off`; another tool name passes; input that is not JSON passes with the warning; an input of 5 MB returns within 2 seconds; nothing of the input appears in the output. Say in the pull request how to run the tests (which Python).

### 4. ops/CLOUD_FIRST.md: the owner's page, half a page
What the rule is, in his words and in plain words; what runs where (a table: cloud, local, the hub itself); what he will see when the hook blocks something (the hub says so and either sends the work to the cloud or gives its reason for running it on the Mac); the two ways to switch it off (set `VF_CLOUD_FIRST=off`, or remove the PreToolUse block from `.claude/settings.json`), and that switching it off is his decision; what it does not cover (the hub's own chat runs on the Mac and on the plan, because it needs the Mac; a worker chat he starts himself by clicking is his own choice).

### 5. STATUS.md
One line where the hub and its workers are described, or under the newest dated notes: the rule, its date, and the link to ops/CLOUD_FIRST.md.

## Review and merge
- A separate subagent of yours reviews the change as an adversary: can the hook block a call it should allow, allow one it should block, hang, crash, or leak the input; does settings.json still parse and still hold the SessionStart hook; do the documents say what the hook does. Fix what is real, and have the fix reviewed.
- DO NOT MERGE. The hook changes how the owner's app behaves, and it must be tried on the Mac first. Mark the pull request ready and write "Report for the hub": what was changed, the tests and their results, the reviewer's findings and what became of each, and the exact lines the hub should run on the Mac to try the hook before merging.
