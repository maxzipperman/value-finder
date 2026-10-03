# Local coding model comparison, October 2–3, 2026

LOCAL-BECAUSE: hardware. Owner-authorized comparison, issue #146 / PR #147. **Keep Qwen3.6 and add bounded roles for the challengers. There is no demonstrated overall replacement.** Thirty-eight local requests covered six task types, including an actual dashboard helper. No live checkout, private data, paid call, research variant or production job was changed.

## Role recommendations

| Model and tested mode | Useful role | Evidence and restriction |
| --- | --- | --- |
| Qwen3.6:35b, thinking off for test drafts | Keep as existing general helper; odds regression drafts | Correct oracle accepted and all eight odds mutants caught in 31 seconds. Other code drafts still have errors. |
| Qwen3.8:27b, thinking on | Supervised implementation/debugging drafts; code review | 52/53 checks on both code tasks; found all four review defects. 82–106 seconds for code, with huge-int error normalization missing. Thinking off introduced a nonexistent API and incorrect selector ordering. |
| gpt-oss:20b, medium reasoning | Quick independent review and structured extraction; optional small code drafts | Four review defects found in 30 seconds; exact adversarial extraction in seven seconds; implementation 52/53 in 27 seconds. Its odds test suite rejected correct code, so do not trust it to define acceptance criteria. |
| Gemma4:26b, thinking off | Fast small helper-test drafts and extraction; optional review/draft fallback | Actual UTC helper accepted; five of six planted mutations caught in 13 seconds, plus general offset diagnostic. Exact extraction in four seconds. Review found four categories but only three fully explained. Its odds tests rejected correct code. |

These are supervised roles alongside Grok, Muse, Gemini and Qwen3.6, not approval authority, independent research confirmation or an installed automatic router. Model output remains a proposal. Check code with independent tests and review; verify claims against source evidence. Model lineage can correlate mistakes.

## Thinking-enabled first pass

All models had the same six prompts, temperature 0, seed 42, 16,384 context tokens, 8,192 output-token cap, and 300-second deadline. Thinking was true for Qwens/Gemma and medium for GPT-OSS. Architecture-specific controls are not equal computation. Each task had one attempt and no feedback.

| Task | Qwen3.6 35B | Qwen3.8 27B | GPT-OSS 20B | Gemma4 26B |
| --- | --- | --- | --- | --- |
| Two-file implementation, 53 checks | Truncated, 72s | 52/53, 82s | 52/53, 27s | Truncated, 63s |
| Debug buggy modules, 53 checks | Truncated, 77s | 52/53, 106s | 50/53, 76s | Truncated, 63s |
| Odds test suite: accept oracle, catch eight mutants | Truncated, 75s | Truncated, 160s | Rejects oracle, 71s | Truncated, 59s |
| Actual UTC parser test suite: accept helper, catch six mutants | Truncated, 72s | Truncated, 146s | Truncated, 77s | Truncated, 64s |
| Seeded review, manual explanation check | 4/4, 41s | 4/4, 82s | 4/4, 30s | Truncated, 70s |
| Exact extraction from adversarial synthetic logs | Pass, 19s | Pass, 16s | Pass, 7s | Pass, 15s |

“Truncated” means the cap was exhausted and no complete usable answer was returned. Empty content, unfinished code and malformed JSON count as failures; nothing was silently repaired. GPT-OSS's scientific-notation test expected `1e3` to produce 1000/1100 instead of 100/1100 and therefore rejected the correct odds implementation.

The 52/53 implementation scores use the amended AST allowance for the harmless `type(value).__name__` error-label form, documented in PLAN.md and source-filter-validation.json. The original filter rejected those outputs; candidate text and functional fixtures were unchanged.

All completed implementations missed the huge integer conversion case: `10**1000` must yield ValueError rather than OverflowError. GPT-OSS debugging also missed invalid `asof` types. Review findings were read independently: both Qwens and GPT-OSS identified all four genuine categories without an independent false finding. Qwen3.8 incorrectly mentioned zero probability in its negative-odds explanation; GPT-OSS mentioned values above one. The actual formula gives negative probabilities for valid negative odds below -100 and divides by zero at -100. Their main defect diagnoses are valid, but these phrases are not reliable facts.

## Separate no-thinking diagnostic round

Repeated the four code-writing tasks for both Qwens and Gemma after cap failures, with identical prompts/options and no corrective feedback. Gemma also repeated review/extraction because thinking mode did not produce a usable review. Selection of this round was informed by first-round failures; it is not a preregistered independent replication and scores are not pooled.

| Task | Qwen3.6, thinking off | Qwen3.8, thinking off | Gemma4, thinking off |
| --- | --- | --- | --- |
| Implementation | Invalid JSON, 16s | 44/53, 16s | 52/53, 13s |
| Debugging | 48/53, 14s | 51/53, 16s | 50/53, 13s |
| Odds test drafts | Oracle accepted, 8/8 mutants, 31s | Source-filter rejection; also wrong expectations, 53s | Rejects correct oracle, 13s |
| Actual UTC parser test drafts | Helper accepted, 5/6 mutants, 20s | Truncated, 146s | Helper accepted, 5/6 mutants, 13s |
| Review | Not repeated | Not repeated | Four categories; three complete explanations, 4s |
| Extraction | Not repeated | Not repeated | Exact pass, 4s |

Qwen3.6 returned two separate JSON objects for implementation, so it failed packaging without salvage. Its debugging draft did not skip non-string timestamps. Qwen3.8's implementation invented `float.isfinite()`; its debugging selected the oldest row. Its odds tests used blocked `exc_type.__name__` reflection and, on manual inspection, incorrectly required valid `+100` and `1e100` strings to be rejected. It was not executed through a relaxed filter. Gemma's odds tests expected valid results for forbidden odds 1 and -1; its debugging missed invalid `asof` types. Thus faster generation is not an across-the-board quality improvement.

Both valid parser suites missed the predeclared mutant that only mishandles `-04:00`; their offset tests used other offsets. A **separate post-result diagnostic**, `supplemental-offset-diagnostic.json`, confirms both catch a general offset-relabeling error. This supplements interpretation and does not revise the original 5/6 score. Gemma's review omitted `last_update <= snapshot` while correctly identifying the decision-time gate, so line-localization's automated 5/5 is not a complete manual review score.

## Reproducibility and limits

`inventory.json` freezes exact installed digests and artifact bytes. `summary.json` records per-request latency, load, prefill, generation, tokens, thinking characters, sampled allocation and checks. Request, response, reasoning and acceptance artifacts remain in each model folder. Reasoning text is evidence of output behavior, never an instruction to execute.

Ollama `/api/ps` allocation samples for the first implementation were about 20.9 GiB for Qwen3.6, 17.0 GiB for Qwen3.8 and 12.0 GiB for GPT-OSS, fully assigned to GPU according to that telemetry. Gemma reported about 1.2 GiB despite an 18.7 GB artifact; that inconsistent number is **not accepted as a RAM estimate**. These samples are not exact peak or total machine memory. Latencies include load/runtime effects, are single observations, and do not establish a throughput benchmark. Each request used keep_alive=0. No other user's model was stopped.

The oracle passes all 53 functional cases, eight odds mutations and six parser mutations were independently demonstrated detectable, and the AST filter has separate validation. Generated source was inspected before grading in the ordinary restricted sandbox with a 15-second deadline. AST filtering alone is not a security boundary. Hidden fixtures were not provided to candidates.

This is a small bounded evaluation, not proof of autonomous repo editing, tool use, long-context reasoning, production readiness or general research accuracy. No Q8, Ornith or Llama was tested. New Ollama catalog versions can differ from installed frozen digests. Compare Q8 against an explicitly matched lower-precision artifact before attributing differences to precision.

To grade existing artifacts after source inspection, use `expanded.py grade MODEL` and `real_helper.py grade MODEL` in the ordinary sandbox. For Qwen suffixed no-thinking folders, the general CLI also marks uncollected review/extraction as missing; the saved acceptance files deliberately include only collected tasks. Inference collection is through guarded `generate.py`, one request per invocation, with a lock, exact installed digest checks and busy/memory deferral. Do not use legacy generation branches in the grading modules. No model pulls or cloud fallback are part of this experiment.

The hub relayed a separate reviewer’s offline reconciliation/replay of the original 38-request report at commit098a7afd034d8c09e8fd217186e6ea0b887b185b on October3 ([review comment](https://github.com/maxzipperman/value-finder/pull/147#issuecomment-5966896455)). It found no blocking issues for evidence-only reporting or bounded supervised draft roles and requested the source-filter disclosure above. That review does not cover the later Q8 or hard-pair extension.


Later local extensions are author graded separately in [HARD_RESULTS.md](HARD_RESULTS.md); the38-request results here remain the frozen original round. Cloud experiments have their own [OPENROUTER_PLAN.md](OPENROUTER_PLAN.md) and are not part of this report.
