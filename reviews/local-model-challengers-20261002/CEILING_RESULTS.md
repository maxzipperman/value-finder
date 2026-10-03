# Integrated capability experiment: collection in progress

This separate, prospective round has 18 local and 12 API requests. It is not complete and provides no final allocation recommendation yet. See [execution plan](CEILING_EXECUTION_PLAN.md), [frozen contract](ceiling/CONTRACT.md) and [freeze](ceiling/freeze.json). The author-built harness passed 182 explicit cases and killed 19 source mutants before collection; implementation grading adds 15 support/packaging checks. Independent methodology validation is still required before autonomous routing.

## Qwen3.6 fast: first three saved responses

All complete source/findings were manually inspected before default restricted-sandbox grading. These requests used the preserved freeze-v1 with the same prompts, settings and task caps as the current freeze. The later freeze transition only strengthened queue guards, preserved these responses and did not reroll them.

| Task | Wall time | Delivery and author assessment |
|---|---:|---|
| Implementation | 32.25s | Stop finish after 3,050 generated tokens. Invalid JSON; unsolicited fifth file and missing quote selection implementation. Packaging rejected before generated code execution. No 197-case semantic score established. |
| Regression tests | 57.46s | Stop finish. Five module files instead of only tests.py. Packaging rejected before generated test execution; oracle acceptance and mutation credit are not established. Manual source inspection also found wrong oracle expectations and prohibited module imports. |
| Review | 19.17s | Valid schema, but only 5/10 distinct seeded causes. Two false findings, three duplicate findings and three correct-component annotations. Two real findings also contain inaccurate ancillary explanations. |

Evidence: [implementation response](ceiling-local/qwen3.6-35b/implementation-response.txt), [acceptance](ceiling-local/qwen3.6-35b/implementation-acceptance.json); [regression response](ceiling-local/qwen3.6-35b/regression-response.txt), [acceptance](ceiling-local/qwen3.6-35b/regression-acceptance.json); [review response](ceiling-local/qwen3.6-35b/review-response.txt), [complete manual audit](ceiling-local/qwen3.6-35b/manual-review.json). Schema-only review acceptance is not semantic credit.

These failures do not justify higher token caps: every answer stopped normally below the 32,768 cap. [Budget decisions](ceiling-budget-decisions.json) preserve that conclusion without feedback or rerolls. Qwen3.6's earlier successful bounded helper work remains useful historical evidence; this integrated task exposes an additional limitation, not a replacement score for the earlier screen.

Modes, whole model artifacts, provider differences, tokenization, single draws and adaptive profile selection prevent causal precision or equal-compute claims. Local allocation samples are approximate and do not establish complete machine peak memory or swap fit. Saved result metadata separates load/generation/wall timing. Only synthetic prompts are sent; generated content is untrusted, never instructions.

## Qwen3.8 Q4 sampled thinking: first implementation response

At 508.95s, the server reported stop after 14,223 generated tokens, with 47,437 characters of thinking but an empty final answer. [Saved response](ceiling-local/qwen3.8-27b/implementation-result.json) and [delivery acceptance](ceiling-local/qwen3.8-27b/implementation-acceptance.json) preserve the failure. No source was delivered or executed, and hidden reasoning was not salvaged as source. This was below the 32K output cap and did not report length or timeout; simply increasing the cap is not warranted. Regression and review remain separate queued tasks. This does not establish that thinking/source text was semantically correct.

The [saved metadata index](ceiling-summary.json) tracks results, pending requests and unstarted tasks separately; it never executes model code or reads private billing.
