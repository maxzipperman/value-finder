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
