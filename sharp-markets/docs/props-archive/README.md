# Props archive analysis repair — PR #133

Related to #10 and #130. LOCAL-BECAUSE: the bounded 2025 F3a receipt/quote coverage
check requires the Mac cache. No credentials, API calls, outcomes or 2026-season data.

`markets props-grade --archive-runtime <completed-F3a-runtime>` reads only the exact
570-request F3a packet and immutable completed ledger, verifies every receipt/cache
hash and request identity, and prints an outcome-blind coverage report. It never
uses the legacy generic cache planner. For a minimal standalone coverage process,
run `python -B src/markets/research/props_grade/archive.py --runtime <runtime>` from
sharp-markets. No automatic downloads, repairs or output files.

The returned quote records retain the actual T24/CLOSE_T10 opportunity, snapshot and
request times, side/price, identity and eligibility reasons. The book-choice report
uses offered-line presence, with separate full request/opportunity denominators.
It is not a strategy result or a claim that quotes were executable at first play.

The [timing/stat amendment](AMENDMENT-DRAFT.md) remains DRAFT. The section8 entry is
a pending mechanical candidate, not parsed as active book selection. Real CLI
grading is disabled pending independent review and hub registration. Fixtures still
run on synthetic data. Existing primary hypothesis and decision criteria are intact.

`settlement.py` provides pure side-aware settlement with explicit price, known
statistic, participation and verified-terms inputs. Six NFL market mappings are
explicit; CFB and other markets return unsupported until their joins/policies are
reviewed. It does not read outcomes or create an expanded backtest. The original
NFL grader now excludes unknown/conflicting statistics instead of filling them
with zero. A known zero still settles normally; conflicting duplicates are not summed.

The [expanded discovery draft](EXPLORATORY-PROTOCOL-DRAFT.md) separates the existing
primary hypothesis from new sport/market/direction/cadence trials. Expanded grading
requires a finite declared matrix and count, sport-specific matching and settlement
terms. Those are intentionally unresolved where input sources are unverified.

Budget: zero. No purchase, registration, outcome join or model fit is authorized.
Independent review must be supplied by another worker; this author cannot supply
its own AGREE. Acquisition PR #132 and the new purchase-coverage gate are separate.
