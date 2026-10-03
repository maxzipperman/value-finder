# Owner-requested selective budget ladder

Prospective October3: Max asked to increase budgets until unfinished tests finish, only where models have room for improvement. Preserve every prior attempt. This is an adaptive, failure-informed diagnostic, not a blind fixed-budget ranking, nor rerolling completed incorrect answers until one passes.

## Initial targeted extensions

After the existing sequential collectors finish, run one actual dashboard UTC-parser test-drafting task (`real-helper`) with thinking enabled for each Qwen3.6:35b, Qwen3.8:27b Q4, GPT-OSS:20b medium and Gemma4:26b. Each original thinking attempt hit8192 tokens without a usable final suite. They qualify because Qwen3.6/Gemma fast suites accept the correct helper and catch5/6 mutations, Qwen3.8 has useful code/review drafts and GPT-OSS useful code/review/extraction results. This tests a missing or improvable role on a project helper, not already completed semantic failures.

Tier16k: output16384/context32768/deadline1200, original temp0/seed42/mode/default drafting; original prompts and hidden grader unchanged. Separate budget16k- folders. One attempt each; no feedback. No blanket rerun of all six tasks. Existing Ornith hard16k and Q8 runtime-only diagnostics keep their own folders/caps and run first.

## Conditional next steps

Only after manual inspection/grading, consider tier32k (output32768/context65536) if prior tier remains genuinely capped before a usable answer AND extra budget showed meaningful progress rather than repetition. Deadline1200 for ordinary targets;2400 for Q8 to permit its observed slower generation. Same other settings and prompt. Allowed targets: the four real-helper tasks above; Q8 original regression or real-helper; Ornith hard-selection/hard-review. Q8 tier16k regression follows its existing time-only600s diagnostic if still capped; Q8 helper tier16k may follow its original300s timeout. Neither Q8 extra task is automatic: record a manual reason first.

Before each32k or Q8 tier16k request, author writes an entry keyed MODEL|TASK|TIER in budget-decisions.json with proceed=true and a concrete evidence-based reason. This is a progress decision under Max's authorization, not independent review signoff. Stop when a complete answer is delivered even if its code/tests are wrong; incorrect assertions, missed defects and malformed finished packaging are semantic quality outcomes, not automatic grounds for more budget. Stop on server repeat errors, unchanged repetitive reasoning, worsening/no meaningful progress, memory constraints or32k ceiling. Explain if further resources might still help; do not silently keep escalating. Do not use completed hidden-test failures as repair feedback or send solutions.

Higher tiers require at least50% system-wide free percentage before loading (approximate guard, not proof of fit), exact installed digests, same busy/lock checks, one request at a time and keep_alive0. Never stop another user's model. Preserve sampled allocation, actual mode/settings, load/generation/wall time, correctness, false findings and all attempts. Grade only inspected source in ordinary restricted sandbox with15s deadline. Correct oracle acceptance precedes mutant counts. No autonomous production/research authority. Update existing PR147/report and confirmed Dot only after verified usefulness; no merges/paid calls/private data.
