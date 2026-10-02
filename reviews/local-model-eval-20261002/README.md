# Local coding model evaluation — October 2, 2026

Issue: #109. Owner requested testing installed local models on Value Finder.

LOCAL-BECAUSE: hardware: measures model inference on the owner's Mac Studio.

Baseline commit: 8426c95e51f82e8f43f1450527ae90df49d5833d.

Protocol fixed before inference: three bounded, standard-library Python tasks, identical prompts and synthetic acceptance cases for each installed model. Tasks: repair strict daily scheduling in a deliberately mutated dashboard helper; repair secret scrubbing in a deliberately mutated dashboard helper; implement a synthetic historical quote selector using both snapshot and bookmaker clocks. First response is scored without correction. No production changes, research hypothesis fitting, paid calls, live job execution or sealed outcome access. Model output executes only in a temporary directory under a restricted local sandbox; it receives no tools or credentials. This is snippet evaluation, not a test of autonomous repository work.

## Results

At the initial Qwen trial, only `qwen3-coder:30b` was available from the running Ollama service. LM Studio's localhost server was unavailable and its standard models folder contained no model files. Devstral was not downloaded at that initial inventory check. The owner then downloaded it; the comparison follows below.

Model: Qwen3-Coder 30.5B, GGUF Q4_K_M, digest `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca`. Download size 18,556,700,761 bytes. Options: temperature 0, seed 42, context 8,192, maximum generation 2,400 tokens. Ollama reported 19 GB loaded, 100% GPU.

| Task | First pass | After one feedback turn | First-pass wall time | Generation speed |
|---|---:|---:|---:|---:|
| Strict daily scheduling | 5/5 | unchanged | 7.62 s | 77.9 tokens/s |
| Secret scrubber repair | 6/7 | 7/7 | 9.05 s | 71.6 tokens/s |
| Synthetic two-clock quote selection | 20/22 | 22/22 | 8.15 s | 71.0 tokens/s |
| Total | 31/34 | 34/34 | 24.83 s | — |

First pass fully solved one of three tasks. The scrubber response returned the deliberately damaged implementation unchanged, leaving standalone Bearer tokens visible. The quote selector correctly handled clock ordering, decision/kickoff boundaries, offsets, prices and ties but crashed when either timestamp value was None. One feedback turn per failed task repaired these failures (6.84 and 6.06 seconds respectively). Feedback exposes failed case names/errors; repaired scores are not held-out validation.

Harness validation: unmodified project helpers passed all 12 helper cases; the injected scheduling defect failed two cases and the injected scrub defect failed one. The 22 quote cases are independently specified synthetic acceptance checks; this is a newly specified utility, not an identified production bug. No generated change was applied to a production module.

Memory observations during this run: loaded model 19 GB with 8K context; current swap 8.06 MiB at the sampled point. The memory-pressure utility reported 57% system-wide free at the later sampled point; this is its own accounting, not the screenshot widget's metric. No baseline or peak telemetry was captured, so swap cannot be attributed to this test and these are not peak RAM measurements. The model was unloaded when testing ended. No other app was closed.

## Recommendation and limits

Use Qwen for bounded drafts and tests, with deterministic acceptance checks and review. Do not give it unattended control over paid pulls, redaction, research decisions or live jobs based on this trial. It generated useful code quickly but failed explicit robustness/security requirements on two tasks initially. Preserve the hub/isolated-checkout/PR workflow. Ordinary git-only coding retains the cloud-first default; this test needed local hardware.

This is three snippet tasks, one deterministic attempt each, and one feedback turn for failed tasks. It is not autonomous repository navigation, tool calling, patch application, a full test-suite run, a statistically representative model benchmark, or a profitability/research result. Larger context settings and longer tasks remain untested. The comparison below supports a provisional preference on these three tasks only, not a general model ranking.

Evidence: `evaluate.py`, `harness-validation.json`, saved prompts/responses/generated candidates/metrics and acceptance results in the model subdirectories. All fixtures and token-like strings are synthetic. No API credits were spent and no sealed outcomes were read.

Follow-up protocol, recorded after first-pass scoring and before repair inference: give one feedback turn to each failed task, including the exact failed case names and error text. Re-run the full same acceptance suite; keep first-pass scores unchanged. This measures correction effort and is separate from first-pass reliability.


## Devstral comparison (same day, after owner download)

Model: `devstral-small-2:latest`, 24.0B GGUF Q4_K_M, digest `24277f07f62db8f9cb68e9dfc679ea1818a7fbac47a50eff0a701d3f645b63c8`. Download size 15,177,374,099 bytes. Identical prompts, 34 acceptance checks, inference options and one feedback turn per failed task. No new tasks or acceptance criteria were added. Qwen was unloaded before this run; no other model was loaded.

| Task | Qwen first pass | Devstral first pass | Qwen after feedback | Devstral after feedback |
|---|---:|---:|---:|---:|
| Strict scheduling | 5/5 | 5/5 | 5/5 | 5/5 |
| Secret scrubber | 6/7 | 0/7 | 7/7 | 7/7 |
| Two-clock quote selector | 20/22 | 17/22 | 22/22 | 17/22 |
| Total | 31/34 | 22/34 | 34/34 | 29/34 |

Both models fully solved one of the three tasks initially. After feedback Qwen solved all three and Devstral two. Per-check totals are not independent measures of broad coding ability: a module-load failure loses multiple cases, while a selector rejecting every negative-odds row can pass invalid-row cases yet fail every positive acceptance case in this suite.

Devstral initially replaced the ENV_NAMES identifiers with literal `***`, making ENV_VALUE's regex invalid (`nothing to repeat at position 11`), and left the missing standalone Bearer redaction unchanged. One feedback turn restored identifiers and Bearer redaction. Its quote selector used `str(price).replace('.', '', 1).isdigit()`, rejecting valid negative prices including -110; feedback added timezone normalization but left that validation bug intact. Five quote checks remained failed. No further correction attempts were made, to preserve the same feedback budget as Qwen.

Devstral first-pass wall times: scheduling 12.29 s, scrubber 19.68 s, quotes 14.05 s, total 46.02 s (Qwen 24.83 s). Generation speed 35.7–36.0 tokens/s (Qwen 71.0–77.9). Wall time includes model loading/prompt evaluation; response lengths differed, and runs were not repeated or controlled for background workloads. Devstral repair turns took 27.95 and 21.25 s.

Ollama reported 16 GB loaded, 100% GPU, 8,192 context (Qwen 19 GB). Swap before and during Devstral remained 8.06 MiB at the two sampled points. The later memory-pressure free figure was 62%; no continuous peak measurement. Devstral was unloaded afterward. These memory figures do not establish behavior at larger contexts.

Recommendation: provisionally prefer Qwen for supervised Value Finder coding drafts on this Mac. It was faster and required fewer successful corrections here. Devstral saves roughly 3 GB in the reported loaded configuration but did not fix the quote task within the shared feedback budget. This does not justify unattended model control or a broad benchmark ranking. The next meaningful evaluation would be a bounded multi-file task with tool use, actual patch application and the project's tests.


## GLM protocol extension (before inference)

Owner authorized testing GLM-4.7-Flash while Qwen3.6 downloads. Same prompts, acceptance checks, 8K context, temperature, seed, 2,400-token budget and single-feedback procedure. For the primary comparison, GLM's optional thinking is explicitly disabled (`think: false`) to test direct coding responses like the non-thinking Qwen-Coder and Devstral runs. Record exact request settings and any reasoning separately. This does not evaluate GLM with reasoning enabled. Ollama was updated after the first two models; timing is observational and not a controlled runtime-version benchmark. No Qwen download process is stopped.

GLM supplemental protocol, recorded after direct first-pass grading and before reasoning-mode inference: send the same original prompts as fresh conversations with `think: true` and an 8,192-token generation budget to accommodate reasoning plus code. Same acceptance suite, no feedback or failure hints in those fresh requests. Save in a separate `-thinking` directory; do not replace direct scores. Larger token budget and reasoning make this an additional operating-mode test, not the same cost-controlled comparison.

GLM diagnostic protocol extension before additional inference: the greedy reasoning scrub task exhausted its 8,192-token budget. The installed model's parameters specify temperature 1, top_p 0.95, min_p 0.01, repeat_penalty 1. Test fresh original prompts using these installed sampling defaults (omit the harness temperature override), thinking enabled, and a 4,096-token output budget within 8K context. Save separately as `-default-thinking`; no feedback hints. This is an additional configuration trial, not a replacement for the earlier scores; three tasks/configurations tried must all be reported.


## Qwen3.6 protocol extension (before inference)

Qwen3.6:35b became available while GLM testing completed. Continue the owner's installed-model evaluation on the same three direct-response prompts and 34 acceptance checks: `think: false`, temperature 0, seed 42, 8K context, 2,400 generation tokens, one feedback round per failed task. Save separately, with no hints from other models. This tests direct coding mode only. Use one loaded model and unload afterward.


## GLM results

Model: `glm-4.7-flash:latest`, 29.9B GGUF Q4_K_M, digest `4475827791a269b02c8ec49b1c3bc1abb5846bacf3fae015b75d33986322d8f6`, download 19,019,270,897 bytes, Ollama 0.35.0. Twelve requests across three configurations (including direct-mode feedback) were tried; all saved, no selected-success reporting.

| Configuration | Scheduling | Scrubber | Quotes | Total checks | Wall time for three responses |
|---|---:|---:|---:|---:|---:|
| Direct, greedy, first pass | 3/5 | 6/7 | 13/22 | 22/34 | 20.63 s |
| Direct, one feedback round | 5/5 | 6/7 | 13/22 | 24/34 | 19.54 s additional |
| Thinking, greedy, 8,192 output budget | 5/5 | no final code | 17/22 | 22/34 completed checks | 241.15 s |
| Thinking, installed sampling defaults, 4,096 budget | 5/5 | no final code | no final code | 5/34 completed checks | 190.07 s |

Token-limit cases are unfinished attempts, not executable-code failures; their associated checks cannot pass without a candidate. Thinking modes are separate supplemental conditions with different token budgets, not equal-cost comparisons. The installed default sampling parameters were temperature 1, top_p .95, min_p .01, repeat_penalty 1. All other primary comparison options were unchanged.

Direct mode initially retained the scheduling >= defect and omitted standalone Bearer redaction. Its quote selector called nonexistent `datetime.math.isfinite` and would negate a timestamp string in its sort key. Feedback fixed scheduling but changed the bad function call only to nonexistent `datetime.isfinite`, retaining quote failures and the redaction omission. Greedy thinking consumed all 8,192 tokens on scrubbing without a final response; its completed quote implementation rejected valid negative odds. Default-sampling thinking exhausted 4,096 tokens on both scrub and quote tasks. No further tuning trials were run.

Direct generation speed was 80.7–93.8 tokens/s. Reasoning counts include reasoning tokens and must not be interpreted as final-code generation speed. Loaded memory was 19 GB, 100% GPU at 8K context; swap remained 8.06 MiB before and during sampling, memory-pressure free sample 59%. Peak RAM was not measured. GLM was unloaded afterward without stopping Ollama or the Qwen3.6 download.

Recommendation: retain original Qwen-Coder ahead of GLM for these bounded coding tasks. GLM did not demonstrate a reliability advantage here, including the explicitly tested default-sampling reasoning mode. Output budgets, quantization, limited cases and changed Ollama version limit general conclusions. No production module, paid request, registered research or live job was touched.


## Qwen3.6 results and updated recommendation

Model `qwen3.6:35b`, 35.5B GGUF Q4_K_M, digest `a7eb95c53bcf96b4bdd008d0fab4a5dac88047d9c1a7a9ab88ed453423fbd87c`, download 22,621,314,381 bytes. Ollama 0.35.0, direct mode (`think: false`), same primary settings and cases. It passed 5/5 scheduling, 6/7 scrubbing and 22/22 quote checks: 33/34 initially, two fully solved tasks out of three. The single feedback turn repaired standalone Bearer redaction, producing 34/34. Native reasoning mode was not tested for Qwen3.6.

First-pass wall times were 5.18, 4.45 and 5.56 seconds (15.19 s total). Generated-token speed 136.5–149.7 tokens/s. The single repair took 4.56 s. Ollama reported 22 GB loaded, 100% GPU at 8K context. Swap sample remained 8.06 MiB, memory-pressure free sample 49%; no peak measurement. The model was unloaded after the trial.

| Primary direct coding trial | First pass | After one feedback per failed task | Fully solved tasks initially | First-answer total | Loaded size |
|---|---:|---:|---:|---:|---:|
| Qwen3.6 35B | 33/34 | 34/34 | 2/3 | 15.19 s | 22 GB |
| Qwen3-Coder 30B | 31/34 | 34/34 | 1/3 | 24.83 s | 19 GB |
| Devstral Small 2 24B | 22/34 | 29/34 | 1/3 | 46.02 s | 16 GB |
| GLM-4.7-Flash 30B | 22/34 | 24/34 | 0/3 | 20.63 s | 19 GB |

Provisionally prefer Qwen3.6 in direct mode for bounded supervised code drafts on this Mac; original Qwen-Coder remains the lower-memory fallback. GLM's three tested configurations did not demonstrate an advantage on these tasks. Do not infer broad coding percentages from dependent checks, generalize to autonomous repository work, or claim a controlled speed benchmark across changed runtime versions/background workloads. Next useful evidence is a bounded multi-file patch with tool use, meaningful project tests and independent review. No unattended routing, provider settings or production behavior were changed.
