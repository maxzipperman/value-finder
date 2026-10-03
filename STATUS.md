# Value Finder: status

Updated October 3, 2026. This page records current decisions and the sole purchase
queue; it is not spending or registration authority. The previous status is
preserved [verbatim in the historical archive](docs/status-archive/README.md).

## Projects

| Project | Current work | Source of truth |
|---|---|---|
| NFL / CFB weather | Registered forward tests; signal counts require current preview evidence | [NFL strategy](nfl-weather/STRATEGY.md), [CFB strategy](cfb-weather/STRATEGY.md) |
| Football archive | F1 recent, F2 and F3a complete; accepted coverage pilot supports a finite successor acquisition | [Completion audit PR104](https://github.com/maxzipperman/value-finder/pull/104), [PR151 recovery report](reviews/pass150-timeout-recovery/REPORT.md) |
| NFL / CFB props | Coverage-first acquisition; held groups remain held | [Coverage report workflow](strategy-research/coverage-pilot-completion-v1/WORKFLOW.md) |
| NBA / sharp markets | N0 preparation waits for the actual completed predecessor receipt | [N0 follow-on](https://github.com/maxzipperman/value-finder/pull/128), [research reports](sharp-markets/reports/) |
| Forecast/style discovery | Six-model discovery setup; 2026 football remains sealed | [Research protocol](strategy-research/forecast_style_protocol.json) |
| Dashboard / menu bar | Read-only operational view; no rule or job change here | [Dashboard](dashboard/), [Mac move](ops/MOVE_TO_NEW_MAC.md) |

## Forward tests

The live Mac (the one that runs the scheduled jobs): the Mac Studio (since Sep 30, 2026, moved by ops/MOVE_TO_NEW_MAC.md, "Route A, one way"). The MacBook Air runs none of them.

| Rule | Scoring starts | Decision authority |
|---|---|---|
| NFL Rule B | Week 5, October 8, 2026 | [NFL registration and amendments](nfl-weather/PREREGISTRATION.md) |
| CFB Rule B | October 1, 2026 | [CFB registration and amendments](cfb-weather/PREREGISTRATION.md) |
| CFB Rule HT | October 7, 2026, 00:00 UTC | Same CFB registration; paper through 2027 |

Current signals/CLV come from the live ledgers and preview scorers, not the
historical zero counts. This status cleanup changes no trigger, timing, grading,
stake or registration. Paper-only project policy remains in force.

- **Variants:** running count **294**; unchanged by this governance migration.
  Reader-compatible running-count expression: 0.05 / 294.
  Registered families, eligibility and multiplicity remain controlled by their protocols.

## Paid data — sole current queue

The 5M month is already purchased. F1 recent is complete (2,761 paid requests,
82,830 credits); its approval is exhausted and it must not be repurchased.
F2 and F3a are also complete. Original receipts, probe accounting and conservative
reservations remain immutable. [Public completion receipts](https://github.com/maxzipperman/value-finder/pull/99).

| Order | State / next action | Maximum new credits / authority |
|---|---|---|
| 1 | Hub-owned PR151 successor: finish or reconcile its actual terminal receipt before any follow-on; never resend attempted/pending IDs | Frozen 1,290 untouched requests / 66,480-credit total cap, not a fresh remaining balance. [Exact recovery scope](reviews/pass150-timeout-recovery/REPORT.md); PR99 exact authority governs |
| 2 | N0: prepare against actual completed predecessor root and final ledger, then obtain exact list/executor/account approval | Candidate 754 requests / 7,540 credits, not approved by this page; [PR128](https://github.com/maxzipperman/value-finder/pull/128) |
| 3 | Qualifying MLB/soccer heat closes: free joins and finite reviewed gap list first | No new approved cap; coverage/eligibility gate remains |
| Held | CFB2021–22 totals and CFB2023–25 props; NBA full season and hourly football require their own gates | No bulk release or automatic spend |

The running owner artifact stays at
[/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/football-older-recovery-hub/HUB_PROGRESS.md](/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/football-older-recovery-hub/HUB_PROGRESS.md).
It mirrors verified progress; it grants no execution authority. This PR does not
write that artifact. [October planning reference](sharp-markets/docs/OCTOBER_2026_QUEUE.md)
is historical/supporting context, not a second current queue. All purchases stay
hub-only, one at a time, with exact reviewed lists, shared cache/ledger/lock checks,
retained reservations, cumulative ceilings and live revocation checks.

## Waiting on you

0. **Monthly reset date.** Confirm the prepaid credit reset date for the completion buffer; this does not block already approved work. Backup remains optional under the October 2 owner waiver.
2. **Remaining October gate decisions (due Tue Oct 20, 2026).** Hub supplies the registered NBA H1/H2 and football H16b reads when eligible. The owner acquisition-only props override is already recorded; old F3b profitability gating is not a new purchase condition. No outcome join or grading is enabled by this status note.
4. **Phone alerts.** Optional subscription remains as previously documented; credentials stay local.
8. **NFL scorer readings (due Thu Oct 8, 2026).** The already registered readings stand; any owner-requested change requires a dated amendment before affected outcomes. The CFB decision window is past and remains historical, not reopened here.
11. **Multiple-testing families before 2027 rules.** The single running-count bar remains until an explicit prospective registered family decision; this PR changes none of it.

## Keeping this current

Hub updates only changed decisions/queue states with evidence links. Governance is
owned by [GOVERNANCE.md](GOVERNANCE.md), research conventions by [CLAUDE.md](CLAUDE.md).
Append historical snapshots without changing existing snapshot bytes. GitHub issues
hold the [backlog](https://github.com/maxzipperman/value-finder/issues); do not copy
historical narrative back into the current queue.
