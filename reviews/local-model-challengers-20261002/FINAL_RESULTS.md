# Completed model comparison and proposed supervised allocation

Keep Qwen3.6 as the established helper, add Qwen3.8Q4 for nuanced selection/review, and use MiMo as the most promising tested inexpensive API coding fallback. Space Bunny is a useful temporary second reviewer/extractor. No overall champion replacement, automatic router or final approval authority is demonstrated.

## Completed scope and cost

| Phase | Planned slots | Terminal outcomes | Evidence |
|---|---:|---|---|
|Original local|38|38 captured responses, including delivery/truncation failures|[Original report](README.md), independently replayed at098a7afd/comment5966896455|
|Local extensions|44|38responses/6errors|[Hard/mode/budget report](HARD_RESULTS.md), author grades|
|Cloud screen/free16K|32|26responses/2GLM520errors/4provider deferrals|[Cloud screen](OPENROUTER_RESULTS.md), [metadata](openrouter-summary.json)|
|Integrated capability|30|28responses/1GLM429error/1provider deferral|[Integrated evidence](CEILING_RESULTS.md), [metadata](ceiling-summary.json)|
|Matched32K|6 qualified of18 conditional targets|5responses/1embeddedDeepSeek502error;12 other targets denied/deferred before inference|[Matched metadata/grades](openrouter32k-summary.json)|

150 planned benchmark slots total:100local,50cloud. Five cloud slots were provider-deferred without inference, so145 benchmark attempts, plus the separately disclosed initial probe. Responses include empty/truncated/malformed/incorrect answers; response count is not acceptance. No uncertain/error request was retried, no completed wrong answer was rerolled, and all original scores remain.

Gateway-reported aggregate experiment cost **$0.256213190**: screen$0.055236609 +integrated$0.147176829 +matched$0.053799752. Conservative phase-accounted maxima total **$0.588140440**, below the single owner$1 authorization; this is trial reservation accounting, not account balance/usage disclosure. Three transport errors retain unknown-cost maxima. Embedded DeepSeek502 reports gatewaycost0 but upstreamcost$0.00751478; no claim of zero final charge/refund. Future paid execution needs its own scope/budget authorization.

## Task allocation proposed to the hub

| Task | Prefer | Fallback / restriction | Evidence |
|---|---|---|---|
|Small odds regression drafts|Qwen3.6 thinking off|Q8 time-only mode or MiMo if Mac busy; validate correct oracle first|Qwen36 oracle accepted8/8mutants31s; Q8 time-only406s; MiMo matched32K463s/$0.007743,8assertion catches/0leaked-exception credit|
|Adversarial quote eligibility/selection drafts|Qwen3.8Q4 sampled thinking|Human/reviewer verification; avoid genericfastmode substitution|78/78hardchecks147s; Q8same77/78~320s. Single adaptive draw, not precision causality|
|Nuanced interacting code review|Qwen3.8Q4 thinking|Space Bunny temporary second view; MiMo supervised alternative if structured delivery is checked|Q4integrated9/10real0false289s; SpaceBunny9/10real0false128s/$0 with different miss; MiMovisible10/10real0false225s/$0.005440 but malformedJSON. No approval authority|
|Complex multi-module implementation draft|LocalQ8 only when resources justify its demonstrated scope; otherwise escalate|MiMo validated inexpensive API draft candidate; independent replay required before automatic use|Q8narrowcompatibility supplement197/197 but0/4directhelpers; MiMo exact-source supplement197/197+4/4helpers267s/$0.006323. OriginalASTrejections retained; neither is exhaustive/fullcontract acceptance|
|Small implementation/debugging draft|Qwen3.8Q4 thinking / existing local helper with tests|MiMo32K fallback when local unavailable|LocalQ4 original52/53~82–106s; MiMo matched52/53~329–341s/<$0.008each. Sole frozen hugeint failure has lightercontract/oracle caveat below|
|Fast synthetic extraction/helper tests|Gemmafast / GPTmedium / Qwen36|SpaceBunny temporary cloud extraction; MiMo cheap alternative|Original exact extraction and bounded helper suites; GPT/Gemma reject some correct odds suites, so not acceptance authorities|
|Approval, live jobs, money, strategy/research conclusions|Existing hub/reviewer gates and escalation|No tested model gets autonomous authority from this benchmark|No production/tool-agent/outcome-quality test occurred|

Do not allocate new default roles to Ornith based on this trial: thinking delivery limits and fast integration/interface failures remain. GLM provider availability is insufficiently reliable (two baseline520s and integrated429); unattempted tasks are unavailable, not semantic grades. DeepSeek sampled integration can draft substantial code, but31-minute implementation and19-minute9/10review offer no demonstrated efficiency advantage over tested alternatives; greedy matched profile still loops/truncates. Do not treat that as a universal model incapability claim.

Space Bunny preview expiresOct5 under the supplied public launch terms. No durable default, private inputs or automatic paid replacement. All cloud inputs were synthetic; existing local helper controls are historical. The tested settings do not authorize heavy-volume use or confidential input.

## Limits that change interpretation

- All extensions/cloud/integrated grades are **author grades**, not independent methodology signoff. Original38 alone has separate reviewer replay. Before autonomous routing, validate contracts, source filters, hidden fixtures and claims independently.
- Exact installed digests/artifact bytes are in[inventory.json](inventory.json); actual model/provider/canonical identifiers, settings, tokens and latencies are in saved request/catalog/result indexes. Q4/Q8 metadata does not prove identical prequantized checkpoint weights. Family modes, tokenization, provider precision, budgets and adaptive single draws differ; no causal quantization/equal-compute/global ranking.
- Main integrated197checks missed direct helper asof coverage. Separate prospective exact-source probes: Q8/DeepSeek0/4, SpaceBunny/MiMo4/4. Preserve original denominators. MiMo/Q8 narrow AST diagnostics were committed before execution, kept original rejection, used restricted15s sandbox and adverse controls. Never generalize these exceptions to arbitrary source.
- Lighter odds prompt says finite int without explicitly requiring finite-float representability. Frozen oracle rejects10**1000; mathematically finite huge integers make the sole52/53failure an independent contract/oracle-review question. Integrated contract explicitly specifies finite-float representability. Do not retroactively change scores or call the lighter boundary an unambiguous prompt violation.
- MiMo hardselection violates explicit math/datetime-only imports (re/collections), original loadingrejection/no78semantic score; visible whitespace-only identifier filtering also differs from nonempty-string contract. MiMo integratedregression has repeatedkeyword SyntaxError/error swallowing; review has malformedJSON. Code/review aptitude and reliable delivered artifacts are separate.
- Local memory samples are approximate runtime allocation, not total/peak RAM proof; Gemma inconsistent telemetry is not accepted as memory-fit evidence. One model/request at a time, busy/free-memory/nativecontext checks andkeepalive0; no other user's model unloaded. Cloud deadlines include gateway/provider waiting, no clean local/cloud generation-speed causality.
- Empty finals, length, repetition, schema/import/source failures, semantic errors and provider deferrals are retained separately. No hidden reasoning/source/fence salvage beyond the originally declared parsers, no feedback/patches sent back to models.

## Collector error safeguard

After all inference ended, the paid collector was fixed to stop on HTTP200 choice-level errors or finish_reason=error, in addition to top-level errors. Eight offline adverse/valid/saved-response checks pass; result is saved before unchanged stopped/error persistence, retaining maximum reservation and no retry. [Validation](openrouter-embedded-error-validation.json). No new inference ran after this guard repair; prior freeze9de2e484 preserved asceiling/freeze-v3.json, newguard-only freeze265b3cf10c20b32e22f988da3ccb4a2cc53fbfe586f97d218bc5f348b7540c21 verifies all pinned artifacts. Original DeepSeek embedded-error continuation to a DISTINCT approved request remains disclosed, not rewritten as a successful completion.

Evidence is ready for hub review and supervised task allocation. Independent validation and existing spend/merge/live-job gates remain; no automatic routing installed or jobs reassigned by this report.
