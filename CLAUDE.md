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
- **Purchases and coordination:** follow [GOVERNANCE.md](GOVERNANCE.md); STATUS.md holds the sole paid queue.
- **Shared weather code.** `market.py`, `features.py`, `models.py`, `notify.py`, `quota.py` and `runlog.py` are copied between `nfl-weather` and `cfb-weather`. A change to one copy is made to both. Tests fail if `quota.py`, `runlog.py` or the pricing block of `market.py` differ.
- **Frozen means a committed file.** The pricing cohorts (`*/data/processed/pricing_cohort.json`) have registered hashes, and every alert run checks them. Changing one needs a dated amendment.
- **Log, don't drop.** Every alert run leaves a row in `data/forward/runs.csv`, finished or failed. Scorers count every excluded ledger row by reason and list them with `--list-excluded`. Error text is scrubbed of keys (`runlog.scrub`) before it is recorded or sent.
- **The dashboard only reads.** `dashboard/` and `menubar/` never write to a project's data, never change a rule, and start nothing but the scorers in preview (`--now`) and `launchctl list` / `print`.

## Coordination

[GOVERNANCE.md](GOVERNANCE.md) is authoritative for the hub, review tiers,
purchases/recovery, isolated execution and concise handoffs. Read it with this
file and STATUS.md. `/hub` performs the operational check-in described in
`.claude/commands/hub.md`; it grants no additional authority.

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
