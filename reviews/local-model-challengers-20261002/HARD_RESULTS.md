# Project-specific local-model extensions — author grading complete

Qwen3.8 Q4 remains the economical coding-draft option in this trial. Thinking reviews are substantially stronger than fast reviews. Q8 can draft useful tests if allowed enough wall time, but these results do not show a consistent improvement that justifies its larger allocation. Qwen3.6 remains useful for test drafts; Gemma fast is useful for quick bounded drafts. No Ornith coding role is recommended from these configurations.

LOCAL-BECAUSE: hardware. All44 extension requests have terminal artifacts and author grades/progress decisions:38 results,6 errors,0 pending. Together with the separate original38 requests,82 benchmark attempts are preserved, plus one separately recorded one-token Q4 configuration probe. Original38 reviewer replay at [PR147 comment](https://github.com/maxzipperman/value-finder/pull/147#issuecomment-5966896455) does not validate these extensions. Independent methodology/claim validation remains required before automatic routing. No live changes or merges.

## Hard selection and review

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
| Ornith fast | 32/78 | 4 | 2 | 8 / 9 |

Q4 native-drafting diagnostic completed: selection77/78 in88s, review5/5 with0 false findings in72s. Restoring the installed drafting default allowed a usable greedy thinking selection answer; it still accepts out-of-range integers and includes an ineffective string-id versus integer-index comparison. Manufacturer-recommended thinking sampling Q4 selection completed:78/78 in147s. Q8 same-profile selection77/78 in320s, again accepts out-of-range integers; Q4 sampled fast review3/5 in13s, with an overstatement about retaining first input on ties. Q8 sampled fast review3/5 in20s adds one false/out-of-contract warning about aware ISO parsing. Both sampled fast reviews miss lexical offset ordering and negative-odds probability; thinking mode remains the stronger review option in these cases. These failure-informed single-draw diagnostics are separate from the greedy matched pair; no hidden cases or feedback were supplied. This table is not a universal ranking or an equal-compute comparison; model/mode profiles differ. Hard tasks were declared before inference, while diagnostic changes followed observed failures without providing solutions or hidden fixtures.

Both Qwen thinking reviews identify all five causes, with small explanatory inaccuracies (-100 exception; Q8 calls complementary probabilities reciprocal). GPT-OSS falsely claims Python3.14 cannot parse Z timestamps. Gemma misses negative-odds probability; Qwen3.6 reverses the correct American-odds formulas. Some tie-break findings overstate loss of first input on identical clock strings: strict > retains that case. Manual records: [hard-review-manual.json](hard-review-manual.json).

The greedy Qwen3.8 selection drafts fail the out-of-float-range integer case: some crash, others accept an invalid record. The separate sampled Q4 diagnostic passes this case and all78 checks; sampled Q8 still accepts the invalid record. Gemma accepts nonfinite positive infinity. Qwen3.6 adds broken offset parsing and batch-aborting malformed clock handling. No draft is production-ready merely because most checks pass.

The reference passes all78 cases and all eight deliberately faulty implementations are detected; [hard-pair-harness-validation.json](hard-pair-harness-validation.json). Inspect candidate source before executing AST-restricted grading in the ordinary sandbox. No candidate has been given test failures or patched by the grader.

## Original newcomer six-task rounds

Historical controls are the original [README](README.md)/[summary](summary.json) at098a7afd, not fresh randomized repetitions. Exact newer request/result/grade paths are indexed in [extension-summary.json](extension-summary.json).

| Model, thinking | Implementation | Debugging | Odds test draft | Seeded review | UTC helper tests | Extraction |
|---|---|---|---|---|---|---|
| Qwen3.8 Q8 |52/53,271s|52/53,206s|Timeout300s|Timeout300s|Timeout300s|Exact,56s|
| Ornith |Empty at8192,83s|Empty at8192,79s|Empty at8192,77s|Empty at8192,82s|Empty at8192,83s|Exact,15s|

Both Q8 completed code answers leave huge-integer conversion OverflowError unnormalized. Ornith length-limited answers contain reasoning but no final deliverable; reasoning is not salvaged as finished code. Extraction correctly ignores embedded instructions in synthetic logs; this is a narrow demonstrated role, already covered by faster models in the original round.

## Selective resource increases

Prospective settings/stopping rules: [BUDGET_LADDER.md](BUDGET_LADDER.md), declared at57c5579. Every prior failure remains. No grading feedback, hidden checks or solutions were supplied; each diagnostic is a single new attempt with distinct artifacts. Completed wrong answers are not rerolled.

| Diagnostic | Final delivery / correctness | Wall / load / generation seconds |
|---|---|---|
| Q8 odds tests, deadline300→600 only |Completed; oracle accepted,8/8 frozen mutants caught|406.50 /4.58 /401.09|
| Qwen3.6 helper, output16384/context32768 |Completed at8355 tokens; oracle accepted,5/6 frozen mutants caught|82.41 /5.07 /76.63|
| Qwen3.8 Q4 helper, output16384/context32768 |Stop at9078 tokens, empty final; repetitive reasoning, no suite|159.75 /5.82 /152.79|
| GPT-OSS medium helper, output16384/context32768 |Completed at9650 tokens; rejects oracle, no mutant score|95.47 /3.06 /92.05|
| Gemma thinking helper, output16384/context32768 |Length16384, empty final; repeated same final checks|119.59 /5.11 /113.45|
| Ornith thinking hard selection, output16384/context32768 |Length16384, empty final; no delivery progress|148.12 / see indexed telemetry|
| Ornith thinking hard review, output16384/context32768 |Length16384, empty final; no delivery progress|149.19 / see indexed telemetry|

Q8 odds suite in [time-extended folder](time-extended-qwen3.8-27b-q8_0/acceptance.json) catches all8 mutations after accepting oracle; the original300s timeout remains. Its7,408 output tokens completed within8192, so output escalation was unnecessary. Qwen3.6 [helper suite](budget16k-qwen3.6-35b/real-helper-acceptance.json) misses the frozen -04:00 relabelled-offset mutant despite checking other offsets. This is5/6 frozen coverage, not proof of general inability to test offsets. Several caught mutant errors are propagated TypeError/ValueError rather than explicit AssertionError; report exception distinction honestly.

GPT-OSS [helper suite](budget16k-gpt-oss-20b/real-helper-response.txt) wrongly expects timezone.utc.dst()==timedelta(0), where Python3.14 returns None. It also invents rejection expectations for otherwise accepted ISO variants. Oracle rejection means no mutant credit. Q4 ended normally with no answer, before its output ceiling; extra output does not fix this observed delivery failure. Gemma and Ornith spend the extra allowance repeating completed plans/check lists. [budget-decisions.json](budget-decisions.json) records32k denials and the optional Q8-helper stop; no32k inference was warranted or performed. This stops these configurations, not every possible configuration of each model.

## Evidence, settings and useful bounded roles

[PLAN.md](PLAN.md)/[protocol.json](protocol.json) give every prospective mode/cap. [inventory.json](inventory.json) freezes exact digests and artifact sizes; [q8-ornith-metadata.json](q8-ornith-metadata.json) records checkpoint/runtime metadata. [extension-summary.json](extension-summary.json) indexes all44 request/prompt hashes, mode/options, terminal status, output lengths, latency and grades. Cold-load time is included in wall time and listed separately from generation; the difference also contains prefill/overhead. Failed requests have no reliable load/generation split.

Initial six-task caps: thinking true (GPT medium), temp0/seed42/context16384/output8192/deadline300. Hard controlled caps use deadline600 and draft0; native Q4 restores drafting4. Published-profile sampling uses the exact profiles in PLAN, one stochastic draw. Helper16k diagnostics use deadline1200 and native defaults. Q4/Q8 metadata matches architecture/version/template but cannot prove identical prequantized weights. Historical/native/sampled/extended modes are not pooled or presented as causal precision gains or equal-compute rankings.

Sampled allocations are approximate Ollama model telemetry: Q4 about18.4GB, Q8 about30.4GB, Qwen3.6 about22.5GB, GPT about12.9GB, Ornith about22.1GB on recent runs. Gemma helper reports1.39GB against an18.73GB artifact and prior hard allocation17.98GB: inconsistent telemetry, not proof of tiny memory use. These are samples, not measured peaks, whole-Mac memory or evidence of zero swap.

Provisional role advice, requiring reviewed/tested outputs and independent extension validation before autonomous routing:

- Qwen3.8 Q4: code drafts with manufacturer thinking sampling; nuanced reviews with thinking/native drafting. Sampled selection78/78 versus Q8 77/78 in this one draw. No general superiority claim.
- Qwen3.6: regression-test drafts, especially fast mode from the original round; helper thinking can finish with a16k allowance but adds time without improved frozen coverage. Its hard selection40/78 and false probability diagnosis preclude broad unattended code/review authority.
- Gemma fast: quick bounded parser-test/code drafts and review assistance; hard selection77/78 and review4/5 indicate edge cases/missed causes. Thinking helper escalation gives no usable suite here.
- GPT-OSS medium: second-review assistance/extraction, with factual checking; hard review5/5 plus false Z warning, hard selection repeat-limit, helper oracle rejection.
- Q8: optional slower odds-test draft or thinking review, when a second opinion is worth its larger allocation. Useful odds suite406s versus original Qwen3.6 fast suite31s does not establish cost-effective default replacement. No consistent upgrade over Q4 demonstrated.
- Ornith: no added coding/review role; extraction exact but redundant, fast hard code32/78 and review4/5 plus2 false findings, thinking did not finalize at8k/16k. No further budget increase justified by the inspected progress.

The OpenRouter experiment is a separate prospective synthetic-only extension in [OPENROUTER_PLAN.md](OPENROUTER_PLAN.md). It does not change these local grades or represent a fresh local control round. No router/default has been installed and no model is an approval authority.
