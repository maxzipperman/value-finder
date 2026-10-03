# Harder project-specific local-model comparison — in progress

LOCAL-BECAUSE: hardware. Synthetic Value Finder quote-selection and code-review tasks; no production data or execution. Original 38-request report and reviewer validation remain separate; new extension is author grading, not separate reviewer approval.

## Current controlled results

Selection: 78 hidden behavioral checks; review: five seeded causes checked manually, not the automatic JSON/schema score. A generation failure gets no semantic score.

| Model / mode | Selection | Review true causes / 5 | False findings | Selection / review seconds |
|---|---:|---:|---:|---:|
| Qwen3.8 Q4 thinking, drafting disabled | Repeat-limit failure (documented recovery) | 5 | 0 | 120 / 149 |
| Qwen3.8 Q8 thinking, drafting disabled | 77/78 | 5 | 0 | 315 / 202 |
| Qwen3.8 Q4 fast, drafting disabled | 77/78 | 2 | 1 | 42 / 13 |
| Qwen3.8 Q8 fast, drafting disabled | 77/78 | 2 | 0 | 66 / 16 |
| Qwen3.6 fast champion anchor | 40/78 | 3 | 1 | 36 / 16 |
| GPT-OSS medium | Repeat-limit failure | 5 | 1 | 24 / 48 |
| Gemma4 fast | 77/78 | 4 | 0 | 14 / 5 |
| Ornith thinking | Empty final answer, length limit | Empty final answer, length limit | Not assessable | 80 / 75 |

Q4 native-drafting diagnostic completed: selection77/78 in88s, review5/5 with0 false findings in72s. Restoring the installed drafting default allowed a usable greedy thinking selection answer; it still accepts out-of-range integers and includes an ineffective string-id versus integer-index comparison. Manufacturer-recommended thinking sampling Q4 selection completed:78/78 in147s. Q8 same-profile selection77/78 in320s, again accepts out-of-range integers; Q4 sampled fast review3/5 in13s, with an overstatement about retaining first input on ties. Q8 sampled fast review3/5 in20s adds one false/out-of-contract warning about aware ISO parsing. Both sampled fast reviews miss lexical offset ordering and negative-odds probability; thinking mode remains the stronger review option in these cases. These failure-informed single-draw diagnostics are separate from the greedy matched pair; no hidden cases or feedback were supplied. This table is not a universal ranking or an equal-compute comparison; model/mode profiles differ. Hard tasks were declared before inference, while diagnostic changes followed observed failures without providing solutions or hidden fixtures.

Both Qwen thinking reviews identify all five causes, with small explanatory inaccuracies (-100 exception; Q8 calls complementary probabilities reciprocal). GPT-OSS falsely claims Python3.14 cannot parse Z timestamps. Gemma misses negative-odds probability; Qwen3.6 reverses the correct American-odds formulas. Some tie-break findings overstate loss of first input on identical clock strings: strict > retains that case. Manual records: [hard-review-manual.json](hard-review-manual.json).

The greedy Qwen3.8 selection drafts fail the out-of-float-range integer case: some crash, others accept an invalid record. The separate sampled Q4 diagnostic passes this case and all78 checks; sampled Q8 still accepts the invalid record. Gemma accepts nonfinite positive infinity. Qwen3.6 adds broken offset parsing and batch-aborting malformed clock handling. No draft is production-ready merely because most checks pass.

The reference passes all78 cases and all eight deliberately faulty implementations are detected; [hard-pair-harness-validation.json](hard-pair-harness-validation.json). Inspect candidate source before executing AST-restricted grading in the ordinary sandbox. No candidate has been given test failures or patched by the grader.

## Limits and role guidance

Preliminary: keep Qwen3.8 Q4 as the economical general draft option, use thinking for nuanced reviews, and consider Gemma fast for bounded quick drafts/review assistance. GPT-OSS can provide a second review, but every claim needs checking. Ornith's thinking mode has not delivered a usable final answer under this budget; check a separately declared fast diagnostic before any role recommendation. Qwen3.6's earlier test-drafting strengths do not establish reliable harder selection code.

Exact model digests/artifact sizes: [inventory.json](inventory.json). Q4/Q8 metadata matches architecture/version/template, but does not prove identical prequantized weights. Initial Q4 has default drafting4; matched hard tests disable drafting for both. No causal precision-only claim. Memory samples are approximate Ollama allocation telemetry, not proof of total fit or absence of swapping. This is one draw per task/configuration, not a stable benchmark or independent extension validation.

## Owner-requested budget diagnostics pending

After the owner questioned unfinished tests, prospective separate diagnostics were declared: Ornith hard tasks thinking with output16384/context32768/deadline600 (double output, larger context), and Q8 original regression with only time300→600 and original output8192/context16384. Native/sampling/fast modes remain separate. Current sequential collectors complete the original six-task extensions before queued Ornith fast/extended and Q8 runtime-only diagnostic. No old results are overwritten; no solutions or grading feedback supplied. Completion and grading remain pending, and no new Dot handoff has been sent yet.

Original six-task extension progress: Q8 multifile52/53 in271s; regression and review each timed out at300s, so no review capability grade is assigned. Ornith multifile/regression each reached8192 output tokens with empty final answers (~83/77s); no semantic/test-suite score is assigned. Remaining tasks and larger-budget diagnostics are pending.

Original extraction: both Q8 and Ornith exactly match the expected schema/facts and ignore adversarial instructions in synthetic logs. Q8 takes56.45s, Ornith15.11s. Ornith original review also reaches8192 tokens with empty final answer in81.62s. This is a narrowly demonstrated extraction role, not broader review/code quality.

Owner requested selective further budget escalation (BUDGET_LADDER.md, prospective57c5579). Queued16k actual UTC-parser test drafts for the four earlier models whose thinking suites were truncated; inspect/grade before any32k extension. Completion, correctness and compute are distinct outcomes. Completed wrong answers are not automatically rerolled; repeated reasoning/no progress/memory constraints stop escalation.
