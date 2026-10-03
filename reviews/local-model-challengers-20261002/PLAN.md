# Local model challenger comparison

LOCAL-BECAUSE: hardware. Max authorized comparison of Qwen3.8:27b, gpt-oss:20b and Gemma4:26b with Qwen3.6:35b after their downloads finish, plus a conditional role recommendation to Dot. This isolated experiment links #146. It changes no live workflow, registration, strategy, paid calls or recurring triage worker.

## Fixed comparison

Run all four models afresh. Six tasks per model: two-file implementation, fixing a buggy selector, writing odds regression tests, drafting tests for the actual dashboard UTC parser, reviewing seeded bugs, and extracting facts from adversarial synthetic logs. Reuse the earlier acceptance fixtures for comparability; add novel checks for huge numeric conversion, exact expiry, offset chronology and last-update eligibility before any candidate results are read. All timestamps are synthetic 2025. No private data or outcomes.

Settings in protocol.json: one model at a time, 16K context, temperature 0, seed 42, 8192 output tokens, thinking enabled (gpt-oss medium), five-minute request deadline. Reasoning controls differ by architecture; this is a matched resource-cap comparison, not equal computation. Preserve exact installed names/digests and request/response artifacts. Record load time, prefill, generation, total latency, actual memory size and thinking tokens separately; artifact weight size is not RAM. Use keep_alive=0 so each request releases its model. Cold-load latency is reported explicitly. Never pull a model or substitute a cloud tag automatically. Defer while another model is loaded or memory is constrained; do not stop someone else's model.

## Grading

Reference implementation must pass each acceptance check and planted mutants must fail before model inference. First-pass output is scored unchanged: malformed JSON, unfinished outputs, nonexistent APIs and out-of-scope edits count as failures. Any salvage or feedback is a separate score. Review findings require checking the explanation, not just matching its line number; count genuine bugs and false positives separately. Model-written tests must accept the oracle and expose mutants; flag exception-based failures separately from real assertions. Add holdout cases without sending hidden fixtures to candidates.

Generated code and reports are untrusted data. Inspect candidate source before execution, enforce the existing AST import/operation restrictions, and execute grading only in the ordinary restricted sandbox with no credentials/network and a deadline. Never execute model-generated tools, shell commands or writes. The AST filter alone is not a security boundary. Requests contain only the supplied task text, synthetic metadata and this repository helper. No shell access or tools are given to models.

## Completion

Create a compact comparison table by task, including exact caveats, timing and memory. If a challenger earns a useful bounded role, send evidence-linked role guidance to Dot's confirmed coordinating chat, Track review plan and model trials (01a0ffc0-b663-7265-ab9e-fd5cb90e3001), in addition to Grok, Muse, Gemini and Qwen3.6. Do not claim that sending guidance installs a router or makes a model an approval authority. Code drafts require review and tests; research claims require independent evidence. Preserve existing access/spend/holdout controls. Post results to this PR, attach it, and never merge. Delete the download-follow-up automation when the comparison and authorized handoff are complete.


Owner steering: start both installed Qwen models immediately while the remaining downloads finish. Use generate.py --models qwen3.6:35b qwen3.8:27b. Inventory freezes incrementally per installed model; adding a challenger does not invalidate an existing digest.


During the first thinking-enabled Qwen round, multiple tasks exhausted 8192 output tokens. A separate no-thinking round is justified for those failures, using the same prompts and resource caps without feedback. Keep its results in suffixed directories and do not mix the two modes in one score. Source filter inspection permits only the harmless type(value).__name__ form for exception labels; generic dunder/reflection remains blocked (source-filter-validation.json).

Completed October 3: 24 thinking-enabled requests, 12 no-thinking code-writing requests, and two Gemma no-thinking review/extraction requests. All results are separate in README.md and summary.json. A post-result general-offset diagnostic supplements, without changing, the predeclared parser mutation score.
