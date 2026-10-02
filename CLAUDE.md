# Value Finder: working rules

Paper-only sports-betting research: find prices the market gets wrong, and prove each one on a pre-registered forward test before any money goes in. One git repo, [maxzipperman/value-finder](https://github.com/maxzipperman/value-finder) (private), with a separate project in each folder.

**Current state and what's next:** [`STATUS.md`](STATUS.md). Read it before starting work.
**Backlog:** GitHub issues with the `idea` label (`gh issue list --label idea`).

## Layout

| Folder | What it is | Tests |
|---|---|---|
| `sharp-markets/` | Kalshi vs sharp-book pipeline (uv, DuckDB). Has its own `CLAUDE.md`, which applies on top of this one. | `uv run pytest` |
| `nfl-weather/` | NFL weather study, Rule B forward test, alerts, report | `.venv/bin/python -m pytest -q` |
| `cfb-weather/` | College football version of nfl-weather | `.venv/bin/python -m pytest -q tests` |
| `strategy-research/` | 109-variant strategy screen and ranked ideas | `nfl-weather/.venv/bin/python strategy-research/screen.py` from the repo root |
| `thesis-research/`, `thesis/` | Literature review of the 2014 thesis, and the thesis as text | None |
| `dashboard/` | Local, read-only dashboard on 127.0.0.1:8787 (standard-library Python; `ops/install_dashboard.sh` runs it at login). Its evidence list is `dashboard/content/evidence.json`. | `uv run --project dashboard pytest -q` from the repo root |
| `menubar/` | Menu-bar light for the Mac: a small Swift app that shows a green, amber, red or gray dot from the dashboard's `/api/summary`, the only address it reads (`ops/build_menubar.sh`, then `ops/install_menubar.sh`, installs it). | `ops/build_menubar.sh && menubar/tests/run_selftests.sh` from the repo root |

Each project has its own virtual environment. Don't share environments or install one project's dependencies into another's.

## Rules for every project

- **Paper only.** Never write, import or call order-placement code. API clients are GET-only.
- **No lookahead.** A signal at time `t` may only use data timestamped at or before `t`.
- **Pre-register before forward-testing.** Write a rule, its gates and its decision criteria into that project's `STRATEGY.md` / `PREREGISTRATION.md` before its first eligible game. Changes are dated amendments made before any affected outcome is known. Never edit a rule mid-season.
- **Count what you tried.** Report the number of variants tested alongside any result, and judge it against a multiple-testing bar.
- **Grade on price.** Grade on CLV at the price actually taken. Rules that bet *at* the close are graded on win rate and ROI at that price instead (see #4).
- **Secrets and data stay local.** API keys go in each project's `.env`, which is gitignored; `.env.example` holds the names only. Anything under `data/`, `.venv/`, parquet and DuckDB files are gitignored and must be re-creatable from scripts.
- **Paid APIs are cache-first.** Odds API calls need an explicit credit budget. Reruns read the cache.
- **One plan for every purchase (the owner's rule, Sep 30, 2026).** Every plan to spend paid credits or money lives in this repo, and the hub keeps the one list of what is bought next (`STATUS.md`, "Paid data"). A chat outside the hub (Codex, a cloud worker, another Claude chat) may propose a plan only as a pull request against that list; it never runs its own bulk download, keeps its own request list outside the repo, or spends on the paid key without the hub's go-ahead for that exact list. Before any paid run, check that no other plan covers the same calls.
- **Shared weather code.** `market.py`, `features.py`, `models.py`, `notify.py`, `quota.py` and `runlog.py` are copied between `nfl-weather` and `cfb-weather`. A change to one copy is made to both. Tests fail if `quota.py`, `runlog.py` or the pricing block of `market.py` differ.
- **Frozen means a committed file.** The pricing cohorts (`*/data/processed/pricing_cohort.json`) have registered hashes, and every alert run checks them. Changing one needs a dated amendment.
- **Log, don't drop.** Every alert run leaves a row in `data/forward/runs.csv`, finished or failed. Scorers count every excluded ledger row by reason and list them with `--list-excluded`. Error text is scrubbed of keys (`runlog.scrub`) before it is recorded or sent.
- **The dashboard only reads.** `dashboard/` and `menubar/` never write to a project's data, never change a rule, and start nothing but the scorers in preview (`--now`) and `launchctl list` / `print`.

## The hub

One chat manages the project: **Codex "hub chat"** (thread `01a0f4c8-b074-70a3-87be-07f4bdc156df`). The owner assigned this handoff October 1, 2026, recorded on PR #99. Claude chats and the auditor serve as workers. Work stays in isolated checkouts; the live checkout and scheduled jobs remain protected. The hub never archives itself.

- **Model routing (owner update, October 2, 2026).** Prefer installed offline coding models for suitable bounded tasks, with Qwen first and independent checks ([`ops/LOCAL_CODING_MODELS.md`](ops/LOCAL_CODING_MODELS.md)). This is an exception to the September 29 cloud-first rule. Other work needing only git goes to the cloud worker on cloud session credits. Local paid cloud-model workers remain limited to work needing this Mac; the plan's limits are kept for the hub. When starting a local offline worker, state `LOCAL-BECAUSE: hardware: runs the owner-preferred offline coding model on this Mac.` The existing hook remains enabled ([`ops/CLOUD_FIRST.md`](ops/CLOUD_FIRST.md)).
- **Codex coordination (the owner, Sep 30, 2026).** The Codex hub executes API requests within the owner’s scope and records exact request-list and credit-budget approval first. Coordination is only through pull requests and comments; nothing merges until both have commented `AGREE <sha>` on the current head, and the hub does every merge touching rules, registrations, money, scorers or live jobs. The full arrangement is in [`AGENTS.md`](AGENTS.md).
- **`/hub`** runs one check-in. It covers status, deadlines, PRs, worker chats and Mac health, then does small Mac-only jobs itself and spawns workers for the rest. The rules are in `.claude/commands/hub.md`. A daily check-in runs at about 9 AM while the app is open.
- **Workers get one issue each,** on their own branch, with one PR that links the issue.
  - **The cloud worker** is one standing cloud chat (the hub finds it with `ListAgents`; its title changes with its latest task). It gets git-only work unsuitable for the bounded offline model route, and uses cloud session credits. The hub sends it briefs with `SendMessage`. It merges its own analysis, docs and data PRs, but asks before touching rules, money or the alert jobs.
  - **Offline coding workers** follow the bounded route in `ops/LOCAL_CODING_MODELS.md`; they run installed model inference on this Mac.
  - **Local paid cloud-model worker chats** get anything that needs the Mac's keys or raw data. Each one works in its own worktree. **Nothing but the hub works in `~/code/value-finder` itself, and nothing switches branches there**, because the launchd alert, close-capture and ledger jobs run whatever is checked out.
- **Workers are cleaned up automatically.** The account setting "Auto-archive sessions when their pull request closes" archives each worker once its PR merges.
- **A local worker chat reports back** through its PR and comments: the results and anything that failed.

## Cloud sessions

A cloud checkout has only what's in git. `ops/cloud_setup.sh` (a SessionStart hook in `.claude/settings.json`) builds each project's venv when `CLAUDE_CODE_REMOTE=true`, and does nothing on the Mac.

- **Available in the cloud:** code, docs, outputs, `*/data/processed/` (the analysis datasets, about 8 MB), `nfl-weather/data/raw/odds/sbr_open_close.parquet`, and the forward-test ledgers on the `ledgers` branch (`git show origin/ledgers:nfl-weather/ledger.csv`). A launchd job (`ops/install_ledger_sync.sh`) pushes them nightly.
- **Mac only:** the raw caches (weather, play-by-play, the Kalshi candles in `sharp-markets/data/raw`, `markets.duckdb`), the `.env` keys, and the alert jobs. Paid Odds API pulls run on the Mac, where the cache lives.
- The default network allows PyPI and GitHub (including nflverse's `games.csv`), but not Open-Meteo, Meteostat, Kalshi or The Odds API. Anything needing those runs on the Mac.
- After rebuilding processed data on the Mac, commit it. New files in `data/processed/` are picked up automatically.

## Workflow

- One branch and one pull request per change. Link the issue (`Closes #n`).
- Update `STATUS.md` in the same pull request whenever a project, a forward test or a backlog item changes state.
- New ideas become GitHub issues labeled `idea`, the project they belong to, and `no-new-data` or `needs-data`.
- The alert jobs (`com.nflweather.alerts`, `com.cfbweather.alerts`) run from `~/code/value-finder/{nfl,cfb}-weather`. Don't move or rename those folders without rerunning `scripts/install_alerts.sh` from the new location.
