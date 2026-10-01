# Football archive v3 — prepared for review

Manifest: 5,052 calls, including 24 reused probe calls and 5,028 new paid calls.
Recent ceiling: 82,830; older ceiling: 68,010; including probe: 152,527 credits.
No new spending is authorized by this freeze. The executor accepts priority 1 only and requires a separate owner approval artifact pinned to the full root and exact recent ceiling.

The 54 timing-discrepant games produce 50 distinct alternate slots, 22 already requested (covering 25 games), and 28 new calls at 840 credits.
Alternate close selection is based only on timing and freshness, never favorable prices. Missing actual-play evidence leaves a scheduled proxy uncertified; unresolved material conflicts remain diagnostic.

The provider-observed registry includes unmatched IDs. The external NFL index is played-game metadata. Neither universe alone establishes a complete historical betting opportunity denominator. The recent unmatched inventory adds no blind extra purchases.

Portable offline checks: run Python with -B, run `python -B validator.py . PINNED_ROOT`, then `python -B -m pytest -q -p no:cacheprovider test_v3.py` with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Tests use temporary copies and fake transports; no API/key/outcome/holdout access.
Offline executor preflight: `python -B executor.py --root PINNED_ROOT`. Live execution is deferred until owner review; no approval file is included.

The runtime lock pins Python and HTTP/parquet distributions. All imported market-client source is vendored and hashed. Raw runtime responses, receipts and ledgers live outside this immutable bundle.
A provider monthly reset or other key activity halts for reconciliation; it cannot reset local budget or enable another send.
The executor stops before older seasons. Coverage report publication is not approval to purchase older seasons.
