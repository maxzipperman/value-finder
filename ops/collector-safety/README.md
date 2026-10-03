# Collector repair and adoption boundary

Issue #164 / PR #165 repairs the existing PR #125 collector deployment only.
Schedules, markets, books, active-game selection and registered rules stay as before.
No live files, credentials, provider requests or outcomes were accessed by this author.

## Reproduced defects and smallest repairs

- `nfl-weather/scripts/log_props.py` previously marked a slot captured only after a
  response/raw write, and explicitly reattempted failures while the slot stayed open.
  A process death after sending but before marking captured could buy it twice.
  The paid `_get` now uses the event ID/offset as a pre-send durable attempt identity.
- `sharp-markets/src/markets/collector.py::_odds_get` previously passed
  `max_retries=2`. Its tick lock checked existence then wrote a file; simultaneous
  entrants could both pass, and restart times made different paid cache keys.
  Named paid odds calls now pass through one zero-retry GET guard; free NBA event
  calls use zero retries and no redirects. A retained-inode kernel lock replaces
  check/write/unlink. A paid poll is keyed to its UTC cadence window.
- The NFL/CFB background paths previously followed redirects. The guard passes
  `allow_redirects=False` and rejects sessions configured with transport retries.
  Registered alert/close paths are unaffected.
- Existing quota files are post-response observations, not durable budget admission.
  The new collector guard serializes admission under a shared ledger lock, reserves
  full market/book upper bounds before HTTP and keeps every reservation. Props
  reserves 9 even if a response costs less. A pending/error/missing billing response,
  unexpected account usage or modified receipt halts further collector admission.
  Response receipt and terminal ledger are independently replaced/fsynced, including
  directory fsync. A crash between either write leaves the pending attempt blocked.

## Explicit configuration interface — no authority provided by this PR

Installer requires `VF_COLLECTOR_ENVELOPE` (absolute file path) and
`VF_COLLECTOR_ENVELOPE_SHA256` (64 lowercase hex digits), and passes them to each
plist. Metadata preflight occurs before key comparison or any launchd mutation.
Deleting/changing the file revokes admission. The executing checkout must be clean
and at the envelope's exact commit. Every paid attempt revalidates under the lock.

Envelope schema (all fields required; no extra fields):

| Field | Meaning |
| --- | --- |
| `version` | 1 |
| `source_sha` | Exact 40-character executing commit, including installed integration |
| `approval` | Hub's independently verified current approval reference; text is provenance, not proof |
| `month`, `valid_until_utc` | Current UTC YYYY-MM and exclusive UTC expiry |
| `account_fingerprint` | SHA256(key) first 12 hex; never the key |
| `account_ceiling` | Finite cumulative monthly ceiling, including prior/all other usage |
| `plan_credits`, `reserve_floor` | Account size and protected remainder; ceiling cannot exceed plan minus reserve |
| `ledger` | Absolute shared ledger path; its `.lock` sibling must already exist |
| `shared_writers` | Reviewed inventory of every competing account writer; listing a writer does not integrate it |
| `collectors` | Exactly `nfl-trigger`, `cfb-trigger`, `nfl-props`, `nba`, each with finite positive `cap`, full-match URL `path_pattern`, exact four public `params` (`bookmakers`, `markets`, `oddsFormat`, `dateFormat`) |

Only the named live football/NBA GET odds paths can be admitted. Request parameters
are compared exactly to approval scope. No API key belongs in this metadata.

Ledger schema: `version=1`, `envelope_sha256`, `baseline_used` (reconciled account
usage before this envelope), `external_reserved` (cumulative other-writer upper
bounds since baseline), `external_state` (`ready` only admits; pending/blocked halt), `attempts` (ID-indexed collector reservations). Every attempt
has `label`, `slot`, `request_sha256`, `reserved`, `state`, `receipt_sha256`.
The helper requires an already initialized ledger: it never creates/replaces a
missing ledger or bootstraps a new epoch. Pending/failed attempts cannot be repaired
or resent by this helper. Completed receipts must still match their saved hashes.
Monthly rollover, changed approval/commit or recovery needs hub reconciliation;
this PR grants none automatically. Reservations conservatively remain at their
upper bounds after success, so it can stop earlier than actual billing would require.

**Shared-account integration seam:** all other writers must acquire the same
`ledger + '.lock'` inode before admission, reserve their full upper bound in
`external_reserved`, enforce the same account ceiling/reserve, fsync before HTTP,
set `external_state=pending` before their send, and retain uncertain reservations
with a blocked state. Only a reconciled success can restore `ready`. This PR does not retrofit alerts, close capture
or historical executors. A manifest listing them is not evidence of that bridge.
Before deployment the hub must either integrate those writers with independent
review/evidence or approve/enforce a nonoverlapping arrangement with reconciled
account state. The guard halts on provider usage above accounted upper bounds;
that is a detection circuit breaker, not a substitute for coordinating other writers.
Do not rotate/delete the lock inode, reset totals, or treat legacy quota.json as this
ledger. Config/ledger files must be on the same trusted local durable filesystem
for their lock/rename/fsync contract; restrict their write permissions to the hub.

## Existing limits and remaining deployment prerequisites

PR #125 owner installation scope exists. The October plan's 4,440,000 monthly
ceiling and 531,630 reserve are account limits, while the 14,100–20,000 live monthly
figure is an estimate. None is an exact new collector envelope. Exhausted acquisition
tranches provide no live authority. No cap is invented or populated here.

Before hub installation: independent exact-head review and required CI; current
approved source/scope/hash/finite collector caps/expiry; reconciled baseline and
shared-writer accounting bridge (or approved enforced nonoverlap); precreated durable
ledger/lock; current runtime source and environment readiness. Review configuration
and ledger state before the installer's RunAtLoad jobs can act. Missing either live
approval or bridge remains a deployment blocker. The dashboard PR #163 metadata-only
status producer remains a separate dependency; this guard does not report fabricated
missed windows or treat receipt absence as no opportunity.

Synthetic tests cover death after reservation, disk failure before send/after response/
before terminal write, repeated slots, concurrent admission, real NBA tick-lock overlap,
9-market props reservations, caps/shared ceiling, revoked/missing authority, status/
billing anomalies, corrupted receipts and named NFL/CFB/NBA transport integrations.
Existing NBA cadence/cache/quota tests mock admission explicitly to retain their scope;
the new tests exercise actual guard admission. HTTP regressions use fake sessions or
localhost only; the pre-existing external `.invalid` DNS test is excluded.

**READY FOR THE HUB for independent implementation review. NOT READY for deployment:**
no exact live envelope or approved shared-account bridge has been supplied.
