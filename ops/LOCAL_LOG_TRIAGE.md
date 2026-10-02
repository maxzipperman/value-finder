# Local log triage

LOCAL-BECAUSE: hardware: uses the owner-installed Qwen3.6 model and reads Mac-only run records.

Owner authorized recurring read-only log triage on October 2, 2026. Implementation stays in an isolated checkout. Only the existing NFL and CFB data/forward/runs.csv files are inputs. No alert execution, launchd changes, research data access, .env reads, paid APIs, repairs, merges or chat-to-chat messages.

Hourly heartbeat in this Codex chat runs a pinned worker. It checks files deterministically first. Healthy/unchanged checks do not call the model or notify. Reports identify newly active failures, escalation from one to multiple failures, recovered problems and unreadable/malformed sources. Historical failures already followed by healthy runs do not generate an initial backlog.

Only project, UTC run timestamp, status and classified step/error enums go to Ollama. Raw errors, unrecognized text, URLs, credentials and model tools never go to the model. Explanations are untrusted drafts; verified facts and source references remain separate. Busy/unavailable Ollama or invalid output produces a deterministic fallback, not a repair or another provider call. One model at a time; worker-owned inference unloads after the request.

The worker owns only its separate state and report directory. Locking and atomic writes prevent overlap and duplicate reports. It never writes into the source repository. Tests must cover chronology/offsets, malformed inputs, rotations/recovery, deduplication, overlapping runs, output validation, prompt injection/secret non-disclosure, busy/offline inference and crash-safe state/report ordering. Live smoke checks verify source files are unchanged. Scheduler setup and exact reviewed worker hash will be recorded here before enabling the heartbeat.

## Operation

The Codex app heartbeat checks hourly while the Mac/app are available. This scheduler uses some Codex usage; the explanations run through local Ollama. The worker itself is standard-library Python. The live source files are only `~/code/value-finder/{nfl-weather,cfb-weather}/data/forward/runs.csv`. It does not inspect ledgers, historical caches, sealed outcomes, .env or arbitrary log paths. A stale job is still the existing dashboard's responsibility; this worker explains newly observed recorded problems.

On first check, current unresolved problems are eligible; old failures followed by success are quiet. Repeated matching failures escalate once at the second run. A healthy recorded run clears an active problem; a new episode is reportable even if recovery occurred between checks. CSV record numbers are references, not guaranteed physical line numbers for multiline CSV. Rotations retaining the active episode preserve identity; dropping the episode's first failure may generate a new notice. Reports are durable before detector state advances; delivery through the app is best effort, not an exactly-once notification guarantee.

The worker refuses redirects and environment proxies, reads only the local Ollama endpoint, pins the tested model digest and never pulls models. It uses `keep_alive: 0` so inference releases memory automatically. A loaded model makes it defer to deterministic reporting. A fixed read-only `/usr/bin/memory_pressure -Q` check also defers inference below 45% reported free memory or when the check fails; this is a conservative heuristic, not a precise available-byte estimate or a guarantee against swap. No launchd job is installed.

State/report files are private to this chat under `local-log-triage/runtime`, outside both source repositories. The heartbeat executes the isolated `ops/local_log_triage.py` only after checking its SHA-256: `8d25b22678cbd4d11a8afe4518f5874ed8805a9bfe4bb7082b6f23c9c00eb074`. Changes require validation and an explicit scheduler update; it never fetches or runs a moving branch automatically. The deployed pilot is the owner-authorized isolated copy on this PR, not an unreviewed modification to the live alert pipeline.

Validation: `python3 -m unittest discover -s ops/tests -p test_local_log_triage.py -v` passes 23 cases. Live read-only smoke check was quiet, and both run-record file hashes were unchanged. Synthetic end-to-end inference classified a timeout and repeated checks stayed quiet; fake credential/instruction text never entered the prompt/report. Synthetic evidence is included below `ops/triage-validation/`; private operational reports stay outside git.
