# Local coding model evaluation — October 2, 2026

Issue: #109. Owner requested testing installed local models on Value Finder.

LOCAL-BECAUSE: hardware: measures model inference on the owner's Mac Studio.

Baseline commit: 8426c95e51f82e8f43f1450527ae90df49d5833d.

Protocol fixed before inference: three bounded, standard-library Python tasks, identical prompts and synthetic acceptance cases for each installed model. Tasks: repair strict daily scheduling in a deliberately mutated dashboard helper; repair secret scrubbing in a deliberately mutated dashboard helper; implement a synthetic historical quote selector using both snapshot and bookmaker clocks. First response is scored without correction. No production changes, research hypothesis fitting, paid calls, live job execution or sealed outcome access. Model output executes only in a temporary directory under a restricted local sandbox; it receives no tools or credentials. This is snippet evaluation, not a test of autonomous repository work.

## Results

Only `qwen3-coder:30b` was available from the running Ollama service. LM Studio's localhost server was unavailable and its standard models folder contained no model files. Devstral was not downloaded as of the final inventory check; no head-to-head conclusion is possible.

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

This is three snippet tasks, one deterministic attempt each, and one feedback turn for failed tasks. It is not autonomous repository navigation, tool calling, patch application, a full test-suite run, a statistically representative model benchmark, or a profitability/research result. Larger context settings and longer tasks remain untested. No model-to-model ranking is justified yet.

Evidence: `evaluate.py`, `harness-validation.json`, saved prompts/responses/generated candidates/metrics and acceptance results in the model subdirectories. All fixtures and token-like strings are synthetic. No API credits were spent and no sealed outcomes were read.

Follow-up protocol, recorded after first-pass scoring and before repair inference: give one feedback turn to each failed task, including the exact failed case names and error text. Re-run the full same acceptance suite; keep first-pass scores unchanged. This measures correction effort and is separate from first-pass reliability.
