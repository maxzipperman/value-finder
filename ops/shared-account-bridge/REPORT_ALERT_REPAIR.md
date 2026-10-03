# Alert occurrence repair: current implementation evidence

Issue #166 / PR #167. Hub-authorized source-only contract repair after the P1
alert collision finding. Close restart repair at4243a6ce passed independent focused
caller/crash/conflict testing; prior reports/evidence are historical for acceptance.

Tested clean source: `cb1bc9ec2aba4739fd298dd8ee93064a24e4ec7f`.
All three separate bound project runs passed: **204 targeted checks**
(40 accounting/integration/identity,23 sharp,80 NFL,61 CFB). EVIDENCE_*_ALERT_REPAIR.json
bind exact source/default/dependency/test inputs, commands, environment, clean
commit and successful return codes. Final report-only head reuses unchanged tested
identities; independent disposition and current-head CI remain separate.

## Reproduction and bounded correction

Datetime-derived Pacific examples (no hand-copied bucket integers):

| Date/zone | Intended morning occurrence | Delayed actual start | Normal11:30 occurrence |
| --- | --- | --- | --- |
| Oct3 PDT | 2026-10-03T14:30:00Z | 2026-10-03T16:01:00Z (09:01 local) | 2026-10-03T18:30:00Z |
| Dec3 PST | 2026-12-03T15:30:00Z | 2026-12-03T16:01:00Z (08:01 local) | 2026-12-03T19:30:00Z |

In both cases the old delayed/current actual-time calculations share the UTC16–20h
four-hour bucket, although they represent distinct scheduled observations. The
bot's daylight08:01/UTC12–16h example was arithmetically wrong; the source defect
is confirmed by these corrected examples.

Remove the14400-second fallback for alert roles. `--scheduled-occurrence-utc`
now provides a literal canonical token through alert run, board, weather client
and shared admission. Neither the script nor the client infers an occurrence from
actual execution time. Scripts validate before model/paid/ledger/key side effects;
clients and admission independently reject a missing or invalid alert token.

The fixed reviewed contract is America/Los_Angeles07:30/11:30/15:30/19:30 LOCAL,
encoded as YYYY-MM-DDTHH:MM:00Z. Validate actual date/calendar, correct local
schedule/timezone/DST, nonfuture occurrence and expiry at the next local scheduled
occurrence. The19:30→07:30 overnight interval is12h normally and11h/13h across DST,
not another four-hour epoch. Older/coalesced/ambiguous triggers fail closed.
The occurrence token is identity; quote time remains actual receipt observed UTC.

**Validation is not scheduler authentication.** A caller-supplied CLI string is
NOT proof that launchd actually triggered that occurrence. Current installers
supply no occurrence token and are unchanged. Trusted producer, authenticated/
reviewed trigger binding, actual host schedule/timezone and coalescing/restart
semantics remain activation prerequisites. Normal alert invocation without token
is held even if no key exists; nonpaid --dry-run/--test and board price-disabled
preview paths retain their existing behavior. No --now capture/preview semantics
change, and no new registration, timezone job setting or schedule is installed.

Tests supply synthetic explicit tokens and paused decision clocks: delayed morning
and normal11:30 each cause their own admitted send; same-occurrence restart reuses
the first receipt; saved quote stamps remain delayed ACTUAL observation time. Both
real weather caller chains are covered for PST/PDT. Pure adverse checks cover
future, stale/wrong date, missing, malformed/noncanonical, wrong local slot and
ambiguous token, normal/DST overnight boundaries, literal board forwarding, and
actual alert run rejection before board/key access. Preview needs no identity.
Test-only fixture generation is not imported by production or a trigger producer.

## Evidence and remaining gates

Complete tested identities:

- sharp: `1999b5ed5f8b3deff63db9efa51dedca648626fffc88aa6866c83160203f5f28`
- nfl: `48638c47d8778b7eed8307afe97f1d397b8e74b11997fdbe0fa22ec603b4ca4d`
- cfb: `0149089ca13812e5f55a5732366c5cdd0157b10b1a7b25e8aab8cb8185fce5ba`

Existing close, replay, crash, concurrency, revocation, caller and localhost HTTP
checks all reran with current source. External DNS case still excluded. No provider,
credentials, live jobs, raw runtime/account state, outcomes/holdouts or executed
freezes were accessed/changed. Credits spent: zero.

Ready for targeted independent source review; deployment remains NOT READY.
Production/installer unconditional hold remains. Historical enforcement/exclusion,
lock order, complete writer inventory, authenticated cumulative account baseline,
exact live authority AND trusted alert occurrence production/binding must precede
separately reviewed activation. No CLI validation claim removes those gates.
