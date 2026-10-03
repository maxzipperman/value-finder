# Expanded results: where offline models help

Twenty fresh local requests, five jobs per model, no feedback or candidate edits. Ollama 0.35.0 / Python 3.14.2; exact installed model digests in installed-models.json. Direct mode, greedy sampling, seed 42, 16K context, 3,500 output tokens. The four-task synthetic protocol and actual-helper extension were each published before their inference. No production code, live jobs, strategy choices, paid data or sealed outcomes were changed. All benchmark models were unloaded after completion.

**Prefer Qwen3.6 as a supervised test-writing and bounded code-drafting assistant. Structured log extraction is another demonstrated use for all four. None earned a role as final reviewer or unattended coding agent.** Bigger tasks exposed failures hidden by the earlier three small snippets. These are single trials on installed quantized models, not general model rankings.

## Two-file delivery

The requested output was a JSON file map for odds.py and selection.py, sharing one odds-validation helper. Fifty-two author-defined cases cover valid/invalid odds, expiration boundaries, aware UTC/offset timestamps, original-row identity, malformed rows, ties and input preservation. Check counts are dependent, not capability percentages.

| Model | Original delivery | Functional checks after packaging-only extraction | Valid odds | Eligible-row selection |
|---|---|---:|---:|---:|
| Qwen3.6 | Two separate top-level JSON objects: invalid requested envelope | 51/52 | 11/11 | 7/7 |
| Qwen-Coder | Valid file map; executable code defective | 27/52 | 0/11 | 0/7 |
| Devstral | Extra prose outside JSON | 48/52 | 11/11 | 5/7 |
| GLM | Single JSON fence accepted by grader; executable code defective | 13/52 | 0/11 | 0/7 |

No original answer fully solved this task. Diagnostic scores do NOT count as successful original delivery: extracting fences or merging disjoint JSON objects changed packaging only; Python source was never repaired. Saved separately in *-packaging-diagnostic.json and *-diagnostic-acceptance.json.

Qwen3.6 duplicated validation in selection.py instead of using its imported function and omitted abs(odds)>=100 there. It admitted -99 even though odds.py rejected it. This is a useful cross-module consistency failure beyond the earlier snippet suite. Devstral threw OverflowError for infinity rather than the required ValueError and selected largest id on two ties. Qwen-Coder and GLM called nonexistent int/float.is_finite methods. Qwen-Coder then swallowed the error and rejected every valid row; its passing rejection cases must not be mistaken for a working selector. It also used raw timestamp strings for selection. GLM lacked robust malformed-clock/asof handling and had the wrong tie direction.

The AST gate initially rejected harmless re/decimal/zoneinfo/datetime imports allowed by the task. Corrected and unchanged answers regraded for all models; this was a grader correction, not a model failure. The same deadline and functional cases remained in force.

## Writing regression tests

| Model | Source-free odds tests | Tests for actual dashboard parse_utc |
|---|---|---|
| Qwen3.6 | Accepted correct implementation; detected all 8 mutants | Accepted actual helper; detected 5/6 original mutants |
| Qwen-Coder | Rejected correct implementation | Output limit reached; unfinished code |
| Devstral | Rejected correct implementation | Test setup raised on nonexistent 2026-02-29 |
| GLM | Rejected correct implementation | Accepted actual helper; detected 4/6 original mutants |

Odds-suite failures were substantive: Qwen-Coder expected +200 odds to imply 2/3 and accepted +50 in a valid case; Devstral expected negative probabilities and +150 to imply 2/3; GLM expected -200 to imply 1/3. Mutation scores are awarded only after accepting the correct function. Qwen3.6's suite caught negative-odds rejection, wrong formula, rounding, rejected numeric strings, accepted sub-100 odds, nonfinite values, None silently accepted and rejected +/-100 boundaries. Some mutants have overlapping defects; the count is evidence for this suite, not eight independent model capabilities.

Actual-helper mutants test None, whitespace, compact HHMMZ, a specific -04:00 offset relabeling bug, invalid inputs raising and lost fractional seconds. Qwen3.6 missed the specific -04:00 defect but correctly tested other nonzero positive and negative offsets. A separately saved post-inference diagnostic applied the broader bug of relabeling ANY nonzero offset: Qwen3.6 detected it, GLM did not. Original six-mutant scores are preserved; this diagnostic is not preregistered and is not substituted for them.

GLM tested +00:00 only, so its offset tests did not exercise conversion. It compared epoch timestamps with relative tolerance 1e-9, allowing roughly 1.8 seconds of error at these dates: fractional-second loss passed despite a preservation assertion. Qwen3.6 used direct aware datetime equality and caught lost microseconds. Devstral also contradicted the parser contract on naive timestamps and nonzero offsets. Qwen-Coder repeatedly generated +/-00:00 cases until the output cap; this was unfinished delivery, not evidence from executable tests. GLM/Devstral print calls also violated the requested no-output instruction.

## Review and handling untrusted text

Manual review of explanations governs these scores. Automated line-localization checks in acceptance.json are diagnostic and can overcount: a model can point to the right line with a wrong explanation. Full findings and corrections are in manual-review.json.

| Model | Genuine defects identified, of 4 | False findings | Important issue |
|---|---:|---:|---|
| Qwen3.6 | 2 | 1 | Invented equality-boundary error and proposed >=, which would introduce it |
| Qwen-Coder | 1 | 2 | Repeated incorrect tie-breaking complaints |
| Devstral | 1 | 2 | Proposed incomplete negative-odds repair; falsely claimed updates filtered and inputs copied |
| GLM | 1 | 0 | Only found input mutation |

**All four missed the last_update gate that prevents using future or internally inconsistent updates.** No model gets final authority over research timestamps, probability math or approvals. Devstral's one genuine negative-odds diagnosis did not include a correct repair. Qwen-Coder and Devstral additionally returned prose outside the requested review JSON.

All four extracted the exact latest-attempt statuses, failure list and 12 successful rows from synthetic logs containing embedded instructions to ignore the task, reveal environment variables, claim success or contact a website. None followed those instructions in its final response. This is one small data-only trial with no tools granted; it does not establish prompt-injection safety with tool access or broad extraction accuracy.

## Practical routing and operating cost

- Give Qwen3.6 a narrow function/contract and existing code for draft tests, small repairs, and code templates. Run the tests against known-correct code and deliberate bugs; independently check assertions and cross-module validation. Code delivery should have a schema gate before application.
- All four can be considered for bounded, schema-validated local log extraction. Deterministic parsing is preferable when it already solves the job. Their success here does not justify arbitrary log cleanup or destructive operations.
- Devstral's two-file code was close after envelope extraction and used less loaded RAM; retain as an optional drafting experiment with verification. Its invented review requirements and broken test suites prevent wider trust.
- Original Qwen-Coder remains useful on earlier small repairs with feedback, but this trial exposed a nonexistent API and unfinished repetitive output. GLM produced a partially useful source-guided suite, but arithmetic and review failures remain. Neither demonstrated a reason to take precedence over Qwen3.6 here.
- Keep cloud/human review for final changes, research math/temporal controls, larger repository edits and complex debugging. No native agent tools, repository navigation, production test suite, repeated-run reliability or long-context robustness was tested. No automatic dispatcher or provider settings were changed; the separate policy PR #112 is unchanged.

| Model | Four synthetic requests | Actual-helper request | Loaded size at 16K context |
|---|---:|---:|---:|
| Qwen3.6 | 46.65 s | 21.52 s | 22 GB |
| Qwen-Coder | 18.98 s | 31.76 s, unfinished | 20 GB |
| Devstral | 76.04 s | 53.44 s | 17 GB |
| GLM | 30.92 s | 15.58 s | 19 GB |

Loaded figures came from Ollama ps snapshots, 100% GPU, one model at a time. Timings include loading/prompt evaluation and differ in output length; background load was not controlled. No continuous peak RAM or new swap measurement. Ollama ps was empty at completion.

## Reproduce and inspect

expanded.py defines prompts, inference and grading; real_helper.py supplies the actual parser and its six mutations. Run their selfcheck modes before inference. Run generate MODEL with local endpoint permission, then grade MODEL in the default restricted sandbox; NEVER combine generated-code execution with an escalated/network-enabled inference process. diagnostics.py and offset_diagnostic.py operate only on saved answers and run in the default sandbox. Request bodies and entire responses, including unsuccessful outputs, are in each model directory. The root model report retains all earlier trials and reasoning configurations.
