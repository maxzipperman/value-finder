# NFL and CFB props archive preparation (#130, #132)

LOCAL-BECAUSE: existing Mac cache/receipts determine reuse; worker preparation only.
The owner override #131 permits broader acquisition; the October 2 CFB expansion
removes F6's purchase gate only. Existing research criteria remain unchanged.

Start with [COSTS.md](COSTS.md), [ACQUISITION-POLICY.md](ACQUISITION-POLICY.md)
and the dated [research declaration](RESEARCH-SCOPE.md). There are separate NFL
(59 keys) and CFB (33 shared standard keys) catalogs. NFL alternate support is not
assumed for CFB. The first tranche is T24/close; four earlier times are separate
increments. Under/over does not double the cost of an OU market pair.

`plan.py` generates finite, outcome-blind lists from the verified old selection
inputs. It subtracts compatible requested book/market cells, partitions residual
book groups, rejects uncertain overlaps, retains unbound/ambiguous opportunities
and requires complete per-slot availability before generating an all-core-book
price list. It has no transport or execution authority. `inventory.py` performs
read-only Mac reconciliation; its evidence paths/digests stay local. Tests exercise
partial-market union, cost bands, uncertainty, sport/season/time isolation and
missing/ambiguous historical identity. Save verification with process_guard.

`discovery/` contains exact finite metadata CSVs/manifests for review. The current
all-phase universe is incomplete, so these do not claim comprehensive coverage.
No executor is presented as independently reviewed. The separate executor must
meet the proposed policy and governance before any purchase.

**NOT READY — preparation artifacts are reviewable; paid execution remains blocked
on independent executor review, exact authority and stable global acceptance.**
No credentials, provider calls, runtime writes, grading or sealed quote reads.

Primary documentation: [API](https://the-odds-api.com/liveapi/guides/v4/),
[market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html),
[book regions](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html).

The proposed first metadata executor is [football-metadata-v1](../football-metadata-v1/README.md),
with a 1,544-credit listing-only freeze. The 7,032-credit availability stage remains
separate and cannot start automatically. The coverage-only utility reports cached
F3a presence/pairs/freshness without joining outcomes; its detailed output stays local.
