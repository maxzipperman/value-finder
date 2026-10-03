# OpenRouter synthetic comparison — collecting

Owner explicitly authorized up to$1 without hub approval. The first paid round is capped at$0.50; frozen21 paid requests plus7 free baseline requests and4 declared free16k diagnostics. Key/account billing snapshots stay on this Mac. No private source/data transmitted, no live routing changes. Local controls are historical; modes/tokenization/checkpoints/provider settings differ. Author grades are not independent validation.

[OPENROUTER_PLAN.md](OPENROUTER_PLAN.md) defines the exact prompts/caps; [openrouter-summary.json](openrouter-summary.json) indexes current saved response metadata. Completed local comparison is [HARD_RESULTS.md](HARD_RESULTS.md), not cloud signoff.

## Space Bunny free baseline

Seven tasks, reasoning.enabled=true, temp0,8192 output tokens/deadline600, no seed support. Provider Stealth, exact model stealth/space-bunny-alpha, all reported costs$0.

| Task | Result | Seconds |
|---|---|---:|
| Implementation |Empty final, length8192|105.81|
| Debugging |Empty final, length8192|84.02|
| Odds test draft |Empty final, length8192|117.65|
| Seeded review |All4 seeded causes plus valid offset-order cause,0 false findings|27.12|
| Log extraction |Exact schema/facts; adversarial log instructions ignored|2.09|
| Hard selection |Empty final, length8192|97.15|
| Hard review |5/5 real causes,0 false findings; minor -100 exception omitted|21.86|

Semantic manual scores are in [manual-review.json](openrouter-space-bunny-alpha/manual-review.json). Raw seeded-review automatic line matching scores3/5 because a valid missing-gate finding points to append line12 rather than its predefined6–8 localization. The grader's four predefined categories also omit the additional valid offset cause. The manually checked gate finding is correct; schema/line matches are not semantic grades. Hard review automatic1/1 is only schema validity, not its5/5 true-cause score. All first-pass code tasks failed delivery; reasoning was not salvaged as finished source. Gateway reports reasoning_tokens0 even though reasoning text is present, so do not infer that thinking was disabled or zero compute used.

A prospective separate16k free diagnostic covers only the four capped code tasks, same prompts/settings except output8192→16384. Manual reasoning inspection shows ongoing task-specific work; no grader feedback or hidden cases supplied. Results remain pending and baseline failures remain. No default recommendation until required testing/grading; even if useful, the official Space Bunny preview endsOctober5.

## Paid collection

DeepSeek first implementation used provider OpenInference:304.41s,8192 reasoning tokens, whitespace-only final content, length finish; reported cost$0.00639392. No usable code to grade. Latency reflects this gateway/provider and requested reasoning configuration, not an intrinsic model-speed claim. Other distinct requests continue sequentially; no retry of this capped result. Initial cached-token price-format preflight error happened before any paid inference, was corrected with offline price-unit checks, and is separate from model capability/attempt scores.

Final roles/comparison, total experiment cost and completion remain pending. Account balance/whole-account usage are never included here or committed. No autonomous task routing or tool-agent capability is established by these single-turn tests.
