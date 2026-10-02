# Local log triage

LOCAL-BECAUSE: hardware: uses the owner-installed Qwen3.6 model and reads Mac-only run records.

Owner authorized recurring read-only log triage on October 2, 2026. Implementation stays in an isolated checkout. Only the existing NFL and CFB data/forward/runs.csv files are inputs. No alert execution, launchd changes, research data access, .env reads, paid APIs, repairs, merges or chat-to-chat messages.

Hourly heartbeat in this Codex chat runs a pinned worker. It checks files deterministically first. Healthy/unchanged checks do not call the model or notify. Reports identify newly active failures, escalation from one to multiple failures, recovered problems and unreadable/malformed sources. Historical failures already followed by healthy runs do not generate an initial backlog.

Only project, UTC run timestamp, status and classified step/error enums go to Ollama. Raw errors, unrecognized text, URLs, credentials and model tools never go to the model. Explanations are untrusted drafts; verified facts and source references remain separate. Busy/unavailable Ollama or invalid output produces a deterministic fallback, not a repair or another provider call. One model at a time; worker-owned inference unloads after the request.

The worker owns only its separate state and report directory. Locking and atomic writes prevent overlap and duplicate reports. It never writes into the source repository. Tests must cover chronology/offsets, malformed inputs, rotations/recovery, deduplication, overlapping runs, output validation, prompt injection/secret non-disclosure, busy/offline inference and crash-safe state/report ordering. Live smoke checks verify source files are unchanged. Scheduler setup and exact reviewed worker hash will be recorded here before enabling the heartbeat.
