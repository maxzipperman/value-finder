# Local coding model evaluation — October 2, 2026

Issue: #109. Owner requested testing installed local models on Value Finder.

LOCAL-BECAUSE: hardware: measures model inference on the owner's Mac Studio.

Baseline commit: 8426c95e51f82e8f43f1450527ae90df49d5833d.

Protocol fixed before inference: three bounded, standard-library Python tasks, identical prompts and synthetic acceptance cases for each installed model. Tasks: repair strict daily scheduling in a deliberately mutated dashboard helper; repair secret scrubbing in a deliberately mutated dashboard helper; implement a synthetic historical quote selector using both snapshot and bookmaker clocks. First response is scored without correction. No production changes, research hypothesis fitting, paid calls, live job execution or sealed outcome access. Model output executes only in a temporary directory under a restricted local sandbox; it receives no tools or credentials. This is snippet evaluation, not a test of autonomous repository work.

Results pending. Record response text, acceptance results, Ollama timing and token counts, and memory observations. Compare only models actually available locally. Model quantization and context are part of the result.
