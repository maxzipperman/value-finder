# Value Finder: instructions for Codex and any other agent

**Read [`CLAUDE.md`](CLAUDE.md) and [`STATUS.md`](STATUS.md) before doing anything. Every rule in `CLAUDE.md` applies to you in full**, word for word, as if it were written here: paper only, no lookahead, pre-register before forward-testing, count what you tried, secrets and data stay local, cache-first paid APIs, the shared weather code, and the rest. Where a project folder has its own `CLAUDE.md` (for example `sharp-markets/CLAUDE.md`), it applies on top. This file adds only how you coordinate with the hub.

## Coordination: one hub, one plan

- **The hub is the Claude chat "Value Finder — hub".** It decides what runs, merges what touches rules, money or the live jobs, and keeps `STATUS.md`. You are a worker, like its other workers.
- **One plan for every purchase.** Any plan that spends paid credits or money lives in this repo, on the one list in `STATUS.md` ("Paid data"). Propose changes to it only as a pull request. Never run a bulk download, keep a request list outside the repo, or spend on a paid key without the hub's go-ahead for that exact list. Before any paid call, check that no other plan covers the same calls.
- **Your work is a pull request.** One branch and one pull request per change, linking its issue. Put a section "Report for the hub" in the description, ending with `READY FOR THE HUB` or `NOT READY` and the reason. Don't merge anything that touches a rule, a registration, money, a scorer or the alert jobs: the hub does.
- **Never work in `~/code/value-finder` itself, and never switch its branch.** The scheduled jobs (alerts, close capture, ledger sync) run whatever is checked out there. Use your own clone or a `git worktree` elsewhere. Never load, unload or install a launchd job; never run `scripts/alerts.py` or `scripts/capture_close.py`; run a scorer only with `--now` and `--ledger` on a copy.
- **Keep your work in the repo, not in a private folder.** Plans, protocols, request lists, simulations and reviews go on a branch (the lab's is `research/expanded-local-lab`), so the hub can see them. A file left untracked in the live checkout blocks the hub's checks: put it on a branch instead.
- **Tell the hub what you're doing.** Open the pull request (draft is fine) when you start, not when you finish. Long notes for the hub can go on the `hub-briefs` branch under `notes/`.
- **Spend tokens like the owner's money.** The owner's rule is cloud first for anything that needs only git.
