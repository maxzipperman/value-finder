# Common rules for every reviewer of PR 63 (read fully before starting)

You are an INDEPENDENT REVIEWER of pull request 63 in maxzipperman/value-finder (branch bulk-puller-followup,
head cc14201). It changes the code that spends the owner's paid Odds API credits on Thursday, October 1, 2026.
The full brief, including THE ACCOUNTING RULE the code must implement exactly and the hub's severity definitions,
is at: /tmp/claude-0/-home-user-value-finder/d7012428-080d-54f3-a1da-3ceb35298eec/scratchpad/brief1.md . Read it all.

Checkouts (already created; do NOT create or remove git worktrees, do NOT commit, push, merge or switch branches):
- The branch under review, detached at cc14201: $S/pr63   (sharp-markets/.venv already built: run from $S/pr63/sharp-markets with `uv run ...`)
- origin/main, detached at 4bf0497:               $S/main63 (sharp-markets/.venv already built)
  where S=/tmp/claude-0/-home-user-value-finder/d7012428-080d-54f3-a1da-3ceb35298eec/scratchpad
Suites: from sharp-markets/, `uv run pytest -q -o addopts="" -p no:cacheprovider` : branch 245 passed, main 144 passed.

HARD RULES
1. YOU FIX NOTHING. Do not edit any tracked file in $S/pr63. You may temporarily copy branch test files into
   $S/main63 to see whether they fail on main, but restore it afterwards (`git -C $S/main63 checkout -- . && git -C $S/main63 clean -fdq -e .venv`).
   Put every script, harness, fake server and output of yours under your own scratch folder (named in your task).
2. SPEND NOTHING. Never call the real Odds API, Kalshi, Open-Meteo or any outside host. Use fake sessions (objects with a
   .get(url, params=..., timeout=...) method, as the branch's tests do) or servers on 127.0.0.1 only. Use the made-up key
   FAKESECRETKEY999 (set ODDS_API_KEY=FAKESECRETKEY999 in the environment of anything you run). Never open a .env file.
   Set MARKETS_DATA_DIR to a folder inside your own scratch folder for every command, so no cache is written into the checkout.
3. MEMORY AND CPU: the machine has 4 cores and 15 GB shared with other reviewers. At most 2 worker processes of yours at a
   time for simulations; stop any run that passes 4 GB (run heavy scripts under `ulimit -v 4000000` or check with /usr/bin/time -v).
   If that forces fewer seeds or shorter runs than the brief asks, do fewer and SAY SO with the numbers you actually ran.
4. Report ONLY what you reproduced. Each finding: severity (blocker / major / minor, by the brief's "What counts as realistic"
   and severity definitions), a one-line title, the rule or brief step it breaks, the exact command, the relevant output
   (trimmed), and file:line of the cause if you found it. Also list what you checked and found correct (briefly), and anything
   you could not check and why. Do not speculate without reproducing; mark anything unreproduced as "not reproduced".
5. Write your full report to the file named in your task (markdown), and return a concise summary (findings with severity,
   plus the key numbers asked for) as your final message.
6. Delete any cache/data you created under MARKETS_DATA_DIR when done (keep your scripts and report).
