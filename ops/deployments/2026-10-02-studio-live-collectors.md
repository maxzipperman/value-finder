# Mac Studio: deploy the three existing live collectors

Issue: #124. State: ready for hub deployment; not installed by this worker.

## Owner authorization

The owner requested in Codex chat `01a0ef6a-2d3f-7d22-903d-30bf83f66528` on October 2, 2026: “i would like to load the three additiona llive connectors onto the studio”. This is authorization to deploy the existing collectors; do not ask the owner to repeat it. The hub retains control of deployment, the shared paid account and live jobs under AGENTS.md.

## Exact deployment scope

Use the existing `ops/install_live_uses.sh`, without code changes:

| Label | Schedule and purpose |
|---|---|
| `com.valuefinder.triggerpoll` | Every 600 seconds; log NFL/CFB prices while an eligible Rule B wind trigger is active |
| `com.valuefinder.propslog` | Every 900 seconds; capture eligible NFL props, alternates and team totals at registered time slots |
| `com.valuefinder.nbacollector` | Every 60 seconds, acting every five minutes from configured October 20 start; log NBA market data |

Preserve logging-only behavior, sealed 2026/2026–27 rows, paid-plan checks, shared-key/shared-quota controls, default background floor and existing collection settings. One-minute final-two-hour NBA collection stays disabled. Estimated full-month background use is about 14,100 credits in the existing plan; this is an estimate, not a new hard spending cap. The hub must reconcile background usage with active acquisition accounting before enabling it. This request creates no new historical purchase, research specification or analysis authorization.

## Mac-only preflight completed

- None of the three labels was loaded when queried with `launchctl print gui/501/<label>`.
- Installer, trigger wrapper and both weather Python entry points exist.
- NFL Python and sharp-markets `markets` entry points exist and are executable.
- `zsh -n ops/install_live_uses.sh` passed.
- Installer matches the current isolated GitHub-main checkout byte for byte: SHA256 `df87bd85ddd2e9a1547568d15cdf4b4d9839685e6043a32fc1e1380f7efe9cd1`.
- NBA config sets `collector.start: 2026-10-20`, `every_min: 5`, and `final_every_min: null`.
- No credential contents, live output rows or sealed outcomes were read. No collectors, alerts, capture jobs or API calls were executed.

## Hub execution and acceptance

After current-head review and deployment approval, the hub uses the existing installer against the intended live runtime root, so the installed paths remain valid. Do not run the installer from this temporary review clone; it derives runtime paths from its own location.

```sh
/Users/maxzipperman/code/value-finder/ops/install_live_uses.sh triggerpoll propslog nbacollector
```

The installer privately checks the same nonempty key across all three projects; no key should enter a comment, terminal transcript, source file or plist. It sets `ODDS_QUOTA_KIND=background` for every job. `RunAtLoad` means enabling the jobs can start collection immediately; do not add a second manual invocation.

Confirm all three labels are loaded with the correct live paths, intervals and background environment. Confirm first-run exit status and available heartbeat/log metadata, without inspecting sealed price/outcome rows. NBA being idle before October 20 is expected; do not mistake a loaded label for successful data collection. Confirm the original alerts, close capture and ledger jobs are unchanged. Report any runtime failure in this PR, then update STATUS.md with the actual deployment outcome.

READY FOR THE HUB
