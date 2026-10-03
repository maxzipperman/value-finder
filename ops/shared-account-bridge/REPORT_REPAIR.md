# Close restart repair: current source evidence

Issue #166 / PR #167. Independent initial disposition: NOT READY at c36b502,
one reproduced P2: mutable tries changed the close ID within the same tick.
Initial REPORT/EVIDENCE files are historical and superseded for current acceptance.

Tested clean source: `ed975adf4e83fe143a541d064941279a8d7545ee`.
The final evidence/report-only commit reuses identical tested inputs.
All three separate source-bound project runs passed: **195 targeted checks**
(35 accounting/integration, 23 sharp collector/cache/localhost HTTP, 78 NFL,
59 CFB). EVIDENCE_*_REPAIR.json bind exact source/default/dependency/test inputs,
commands, environments, return codes and clean tested commit. One external DNS
case remains excluded; localhost HTTP cases passed. No provider calls.

## Bounded correction

Close identity is the immutable scheduled 15-minute tick, separate for each role.
Due membership and mutable try counts cannot change it. Exact URL/public params
remain bound by admission's request hash: changing the actual request still fails,
rather than becoming a different request's cache hit. All-games feed selection
parameters are unchanged. The original saved receipt/quote clock is preserved.

Both scripts now recover an existing prepared output transaction before selection
or transport, and skip a previously applied observation before another send/row/try.
A durable prepared application record binds original before/after CSV and state
bytes; its hash is integrity, not independent authorization. Under a persistent
output lock, fsync/replace CSV, then state (including applied observation marker),
then complete the record. A crash after either output resumes the same prepared
record, never appends again or increments a try again. Conflicting output bytes
halt instead of being replaced. The output lock is never held during account HTTP.
This does not unify or replace acquisition runners or their locks.

Successful conclusive empty CFB responses carry provenance and can mark the tick
without changing existing empty-feed counter handling. Quota skips, held admission
and uncertain transport return unmarked fallback frames. Pending account attempts
still globally halt same-tick and later-tick requests.

Actual source caller regressions in both projects run real account admission with
synthetic keys/feeds/journals and temporary close outputs: first incomplete response
persists state, restart30s later sends/reserves/applies nothing new, next eligible
scheduled tick makes the allowed second observation. Three variants per project
cover normal application and failures AFTER durable CSV or state writes. Recovery
keeps output bytes/counts and try count1 on restart, then allows try2 at the later
eligible tick. Both projects also prove uncertain transport prevents any output
application and further send; CFB distinguishes successful empty from uncertainty.

Existing synthetic two-observation examples were re-timed from arbitrary repeated
invocations within one tick to two eligible scheduled ticks; expected quote clocks
were updated accordingly. Their selection/matching/missing-close assertions and
primary captured/tries comparisons remain. Dedicated new tests inspect application
markers and actual durable state, rather than hiding those fields. MAX_TRIES2,
2–20-minute scheduled window, launchd cadence and registration/scoring stay unchanged.
No independent first-play timing claim is added.

## Remaining disposition

Ready for independent repair review once final identities and CI are verified.
Deployment remains NOT READY: unconditional production/installer hold unchanged;
historical integration or enforced exclusion, lock-order proof, complete writer
inventory, authenticated cumulative baseline and exact live authority remain gates.
No runtime seed, keys, paid calls, outcomes/holdouts, live jobs or executed freezes
were accessed or changed. Credits spent: zero.
