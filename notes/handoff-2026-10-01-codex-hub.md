# Handoff: Codex acts as hub from Thu Oct 1, 2026 (~21:20 UTC) until the owner restores the Claude hub on Mon Oct 5/6

The owner's decision, Oct 1, 2026: the Claude hub's weekly plan limit is spent (98%); Codex is the hub until it resets Monday, and the owner makes the Claude chat the hub again himself.

## State at handoff
- PR 99 merged (fc09623), PR 102 merged (57ca73d). Bundle root 4468a94c…; APPROVED paid run bound to fc09623 (82,830 credits).
- The run stopped at request 313 of 2,761 on a stale provider snapshot (CFB 2023-10-15 16Z). 312 responses bought, 9,390 credits. The hub approved the missing response and an account-only recovery (capture mode, max_baseline_used 11183, debit 1693) at https://github.com/maxzipperman/value-finder/pull/99#issuecomment-5940475590. Codex posts the post-acceptance ledger hash before resuming.
- Amendment 2 of the price engine (sharp-markets) is a DRAFT: the Claude hub dates it, sets REGISTERED_ROOT = 4468a94c…, and merges, before any F1 price is read. Not before Monday.
- PR 86 (cfb-weather amendment 7, Rule HT and games with no kickoff time): Codex AGREE at 2a43be4; the Claude hub has NOT reviewed it. It must be registered (dated, running count, STRATEGY.md note) before Rule HT's first eligible game, Oct 6, 5 PM PT. If Codex registers it, the owner is the second party, and the dating must precede the game.
- PR 96 (Codex lab trials, count floor 294→314): draft, not reviewed.
- Day-one runbook after the bundle: F2 (48K), F3a (36K), N0 NBA week (8K), heat closes (16K). Each needs the hub's go-ahead for the exact command and cap, and the owner's word for the money.
- Live jobs on the Mac Studio: alerts (4x daily), close capture (15 min), ledger sync (23:45). Dashboard not installed here; the owner runs ops/install_dashboard.sh.
- Running count of variants: 288 (NFL splits run adds 6; PR 96 proposes 314). Nothing new registered today.
- The hub's agreements record is notes/hub-agreements.md on this branch; a comment is the Claude hub's only if listed there.

## While Codex is the hub
- The two-party rule (AGENTS.md) assumed two agents. With one, the owner is the second check on anything paid, any rule or registration change, and any merge touching scorers or live jobs.
- Nothing installs, loads or unloads a launchd job but the owner.
- No new spending plan outside STATUS.md "Paid data".
- The Claude hub's rules of record stay: CLAUDE.md, AGENTS.md, .claude/commands/hub.md.
