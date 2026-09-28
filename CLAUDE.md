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

Each project has its own virtual environment. Don't share environments or install one project's dependencies into another's.

## Rules for every project

- **Paper only.** Never write, import or call order-placement code. API clients are GET-only.
- **No lookahead.** A signal at time `t` may only use data timestamped at or before `t`.
- **Pre-register before forward-testing.** Write a rule, its gates and its decision criteria into that project's `STRATEGY.md` / `PREREGISTRATION.md` before its first eligible game. Changes are dated amendments made before any affected outcome is known. Never edit a rule mid-season.
- **Count what you tried.** Report the number of variants tested alongside any result, and judge it against a multiple-testing bar.
- **Grade on price.** Grade on CLV at the price actually taken. Rules that bet *at* the close are graded on win rate and ROI at that price instead (see #4).
- **Secrets and data stay local.** API keys go in each project's `.env`, which is gitignored; `.env.example` holds the names only. Anything under `data/`, `.venv/`, parquet and DuckDB files are gitignored and must be re-creatable from scripts.
- **Paid APIs are cache-first.** Odds API calls need an explicit credit budget. Reruns read the cache.
- **Shared weather code.** `market.py`, `features.py`, `models.py` and `notify.py` are copied between `nfl-weather` and `cfb-weather`. A change to one copy is made to both.

## Workflow

- One branch and one pull request per change. Link the issue (`Closes #n`).
- Update `STATUS.md` in the same pull request whenever a project, a forward test or a backlog item changes state.
- New ideas become GitHub issues labeled `idea`, the project they belong to, and `no-new-data` or `needs-data`.
- The alert jobs (`com.nflweather.alerts`, `com.cfbweather.alerts`) run from `~/code/value-finder/{nfl,cfb}-weather`. Don't move or rename those folders without rerunning `scripts/install_alerts.sh` from the new location.
