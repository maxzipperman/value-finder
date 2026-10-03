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

Q4 regression also reports stop below cap: 9,629 generated tokens, 340.70s, empty final and 23,535 characters of thinking. [Response](ceiling-local/qwen3.8-27b/regression-result.json) and [acceptance](ceiling-local/qwen3.8-27b/regression-acceptance.json) record delivery failure without executing or salvaging the hidden draft. No oracle or mutation credit, and no higher-cap escalation based on this stop finish.

## Separate matched API32K decisions, prospective before execution

Author inspection of capped baseline thinking qualifies six of the 18 declared conditional targets: DeepSeek implementation/hard-selection and MiMo implementation/debugging/regression/hard-selection. Their saved drafts continue concrete source or behavioral-test construction/JSON packaging. One attempt each keeps original prompts, temperature0, reasoning mode and seed42, changes only output8K to32K and deadline600 to1800s, and preserves the baseline. These are progress diagnostics, not corrected solutions or blinded initial comparisons. [All18 decisions and baseline digests](openrouter-budget-decisions.json) distinguish approvals from denials/deferrals.

DeepSeek debugging/regression digit runaway and repeated review enumeration do not qualify. MiMo finished reviews are not rerolled. GLM baseline errors/deferred tasks lack an available matched baseline; its unfinished multifile packaging is deferred under preserved provider-outage evidence, with a distinct pinned-provider integrated experiment already declared.

Six qualified requests reserve at most$0.11718916 at frozen rate caps. Together with the prior$0.10296242 conservative reservation and all nine stress maxima$0.40233936, the prospective total is$0.62249094 under the same owner$1 allowance. Actual ledger/account checks remain mandatory before each call. **None of these32K calls is running or completed yet.** They must wait until active queue98555 exits and no inference/uncertain call is present. No competing collector, budget reset, hidden feedback, automatic higher tier or failed-request retry.

Q4 sampled thinking review completes in289.29s and identifies9/10 distinct real causes with0false,0duplicates and no incorrect times.py-control flag. It misses the quote ID tie rule. [Complete findings](ceiling-local/qwen3.8-27b/review-response.txt), [manual audit](ceiling-local/qwen3.8-27b/manual-review.json). Valid source review delivery contrasts with its two empty coding finals in this task round; one draw establishes only a supervised review candidate, not autonomous routing or a general champion.

## GPT-OSS medium: capped coding responses

Implementation and regression both consume32,768 tokens with length finish and empty final (348.78s/346.76s). [Implementation result](ceiling-local/gpt-oss-20b/implementation-result.json), [regression result](ceiling-local/gpt-oss-20b/regression-result.json) and separate acceptance files preserve delivery failures: no candidate source/tests executed, no semantic implementation or oracle/mutation credit.

Unlike useful unfinished source construction, implementation thinking repeats the literal “- Enough.”10,092 times. Regression repeatedly serializes the same suite, with six run_tests headers and recurrent initial assertions; its tail includes an incorrect expectation that an event mismatch should erase independent runs. [Progress audit](ceiling-local/gpt-oss-20b/progress-inspection.json) binds the exact results and repeat locations. Hidden drafts are not salvaged as answers or given mutation credit. [64K decisions](ceiling-budget-decisions.json) deny both due to repetition/no meaningful progress, preserving the original length failures. Review remains separately queued. This failure does not invalidate earlier bounded review aptitude.

GPT-OSS medium review finishes in199.58s. [Full response](ceiling-local/gpt-oss-20b/review-response.txt) covers8/10 real causes across seven actionable findings (one combines lexical ordering and filter-after-reduction). It misses quote ID tie and strict expiry, falsely flags correct times.py for trailingZ, and adds an inaccurate status-hierarchy claim despite the contract forbidding status preference. Python3.14 trailingZ acceptance was reproduced directly. [Manual audit](ceiling-local/gpt-oss-20b/manual-review.json) separates these inaccuracies from true causes; schema acceptance is not review correctness. Completed review does not qualify for more tokens.

## Gemma4 fast: delivered drafts with contract and packaging errors

Implementation stops after3,067 tokens/27.23s but returns five files instead of the specified four, so packaging rejects before any generated-code execution. Manual source inspection also found omitted positive-attempt validation, overflow handling and invalid rejection of whitespace-only events. Regression stops after2,084 tokens/19.16s inside a Markdown fence, rejected as delivered; the visible suite additionally imports prohibited traceback and expects10 successful rows despite a valid partial job contributing3 more. No oracle/mutation credit and no stripping/repairing output for grading.

Review stops after466 tokens/8.07s inside a Markdown fence, also a JSON-only delivery failure. Separately, the [manual semantic audit](ceiling-local/gemma4-26b/manual-review.json) of all seven visible findings identifies5/10 real causes and2false tie claims. The concatenated run key collision explanation is a valid additional consequence. It misses negative probability, lexical time order, missing quote ID tie, expiry boundary and pending-as-failure. Correct times.py is not flagged. Fast visible analysis may still be useful with supervision; this round provides no accepted machine-delivery or implementation/test score. [Saved responses and acceptance](ceiling-local/gemma4-26b/) preserve all failures. All three stop below32K, so [64K escalation is denied](ceiling-budget-decisions.json).

## Prompt and grading limits

The common contract includes both implementation and test-output clauses, followed by a task-specific instruction that explicitly repeats the required artifact (four files, or only tests.py). The five-file answers fail that final instruction, but shared schemas may contribute to confusion. Strict delivery scores therefore measure usable contract-following output in this particular prompt; they do not establish underlying coding incapacity. Fence/file-bundle normalization was not performed, so rejected artifacts have no hidden semantic score. A future clarification experiment would be a separately declared prompt change, not an equivalent rerun or post-hoc repair. Other important gaps remain tool use, multi-turn correction, long-input recall and actual production execution.
