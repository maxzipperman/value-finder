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

DeepSeek first implementation used provider OpenInference:304.41s,8192 reasoning tokens, whitespace-only final content, length finish; reported cost$0.00639392. No usable code to grade. Latency reflects this gateway/provider and requested reasoning configuration, not an intrinsic model-speed claim. Debugging also reached8192 reasoning tokens with no usable final code in241.28s, reported$0.00639652, same provider. Both empty answers are graded as failed delivery, without executing reasoning. Odds-test drafting likewise reached8192 with empty final at240.99s, cost$0.006393088. Reported cost for these three requests totals$0.019183528; remaining costs are pending. Other distinct requests continue sequentially; no retry of capped results. Initial cached-token price-format preflight error happened before any paid inference, was corrected with offline price-unit checks, and is separate from model capability/attempt scores.

Final roles/comparison, total experiment cost and completion remain pending. Account balance/whole-account usage are never included here or committed. No autonomous task routing or tool-agent capability is established by these single-turn tests.


## October3 collection checkpoint — not final

DeepSeek completed all7 original requests: six non-extraction tasks ended at8192 with empty/whitespace final answers; extraction is exact. Its reported experiment cost sums$0.038670489. GLM implementation likewise ends8192 empty,99.14s,$0.00410608; the next debugging call returns provider Relace HTTP520 and stops the paid queue. Eight billed responses report$0.042776569 in total. The failed attempt retains its full maximum reservation; no zero-charge claim. Error was notified once. An explicit digest-bound error audit permits only remaining distinct frozen baseline requests, never retrying GLM debugging. Space Bunny16k is still collecting; its first two coding diagnostics remain length-limited with empty final answers. Completion/mutation grading and capability-ceiling comparisons remain pending.

A cumulative$1 reservation guard now covers all paid phases and passed four offline adverse-case checks. The harder integrated synthetic contract and four-module reference are drafts in ceiling/; hidden interaction checks, mutants, review source, prompts and resource manifest still must be validated/frozen before any stress inference. No stress results or model allocation claims yet.

Continuation checkpoint: the next distinct GLM regression request also returned Relace HTTP520 after0.487s. No prior request was retried. Collector stopped again; this second error remains unreviewed/fully reserved. GLM provider is repeatedly unavailable, so do not keep issuing its remaining tasks blindly. MiMo has not yet been attempted. Before continuing, prospectively record a GLM deferral and a guarded MiMo-only pass of the original frozen unattempted requests, preserving both errors and reservations. All four free16k diagnostics completed with empty final answers at length16384 (182.90/177.31/232.01/159.63s); no source was delivered or executed. Higher free/code diagnostics still require meaningful-progress inspection/declaration.


October3 next checkpoint: GLM4 remaining baseline requests now explicitly classified provider-unavailable/deferred; both failed attempts retain maximum reservations and digest audits. MiMo-only continuation runs unchanged7 originally frozen requests, serially. First2 collected MiMo code tasks reach length8192 with empty finals (141.79/136.91s,$0.00232868/$0.00234812); no code execution or semantic success. New ceiling preparation now has182 explicit trusted cases/reference passes,16 killed mutants,197 full implementation checks, draft review10-cause inventory and correct times.py control. Seeded-review counterexample validation, model modes/resource request manifest/freeze and stress collection still pending. Author harness validation is not independent signoff.


Baseline collection terminal:17 paid attempts (15 responses,2 GLM provider520 errors),4 GLM requests deferred/unavailable;7 free baseline +4 free16k. Reported paid charges$0.055236609, conservative reserves$0.10296242 including errors. MiMo hard selection empty length8192 in100.55s,$0.00232472; hard review5/5 real causes,0false with minor -100 exception in107.66s,$0.00209972. MiMo seeded review4seeded+validoffset,0false; extraction exact. Four MiMo code finals empty. Author semantic grades, markdown JSON fence deviations noted. New frozen integrated round starts only from CEILING_EXECUTION_PLAN.md; budgets/modes/providers changed, no pooling with these screens.

## Matched32K progress diagnostic — in progress

Six of the18 declared conditional targets qualified prospectively from concrete unfinished baseline reasoning;12 denied/deferred. Output32768/deadline1800, original synthetic prompts/temp0/seed42/reasoning/provider filters, distinct folders and no feedback. Session4995 is the sole active collector; no capped baseline or error is retried. Saved metadata are indexed separately in [openrouter32k-summary.json](openrouter32k-summary.json), preserving earlier32-task screening summary.

First DeepSeek/OpenInference multifile diagnostic ended after322.00s/9623completiontokens with finish_reason=error, embedded502/provider_unavailable: provider says generation stopped for repetition. Final is one whitespace character; ordinary restricted grading rejects JSON without executing any source. Saved reasoning contains33 exact repetitions of a valid100-string acceptance phrase. No further escalation warranted. [Manual audit](openrouter-paid32k/deepseek--deepseek-v4.1-flash/multifile-manual-inspection.json) preserves the error and original capped attempt.

Gateway usage.cost explicitly reports$0, while cost_details.upstream_inference_cost reports$0.00751478. These are distinct supplied fields, not proof of zero final account charge/refund; combined guard retains the maximum token reservation. Aggregate reported gateway trial costs remain$0.202413438 sofar, with prior unknown errors fully reserved. The collector saved this embedded provider error as a result envelope and continued to the next DISTINCT planned hard-selection request, not a retry. Summary classifies it as provider_error rather than a successful completion. Embedded-error stop behavior needs explicit guard review before any future unattended trial; do not interrupt the currently uncertain paid call or modify loaded collectors.

Remaining qualified requests/grades/final synthesis/allocation handoffs are pending. No independent signoff or installed routing.

### First matched32K delivery results

DeepSeek hard-selection/OpenInference exhausts32768tokens (all32768reasoning) in1205.97s with empty final, reported$0.025563382. Original hard grader rejects missing select_books; no functional78-case score/sourceexecution. Declared32K diagnostic ceiling reached; no automatic escalation.

MiMo multifile/InferenceNet stops in329.04s with26725completion/25634reasoning tokens, reported$0.00751501. Complete two-file source inspected before unchanged defaultrestricted15s expanded grader:52/53. Original AST permits its static __all__ names/type labels, no supplemental exception needed. Latest/absolute time/gates/identity checks pass; sole frozen failure is10**1000 expectedValueError, candidate accepts huge int and returns0.0. **Contract caveat:** lighter prompt says finite int without explicitly requiring finite-float representability; huge ints are mathematically finite. Keep frozen score but seek independent contract/oracle validation before calling this an unambiguous prompt violation. The integrated contract explicitly includes finite-float representability. No source repair/feedback/reroll, stopsbelowcap. [Source audit](openrouter-paid32k/xiaomi--mimo-v2.6-flash/multifile-manual-inspection.json).

Matcheddiagnostic status now2results/1embeddedprovidererror/1MiModebuggingpending/2notstarted. Gatewayreported aggregate experiment costs$0.235491830 sofar; reserves remain conservative. Local original/extension and cloud screen scores unchanged.

MiMo matched32K debugging completes340.82s/24973completion/23924reasoning, reported$0.00704227. Fulltwofile source inspected before originalrestricted15s grader52/53; same hugeint finitefloat oracle caveat as multifile. Manualparser additionally stripswhitespace/acceptslowercasez; trustedPythonparser controls rejectboth, but lighterprompt not explicitlybound tofromisoformat, so separateboundarynote/no extra hidden-score claim. Purecode/noIO/feedback/repair. Completedstopbelowcap, no escalation. MiMoregression is nowpending, hardselection unstarted; reportedaggregate$0.242534100 sofar.
