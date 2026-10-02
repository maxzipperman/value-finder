# Offline coding models

The owner requested on October 2, 2026: prefer the installed offline coding models when appropriate. This is a bounded exception to cloud-first routing, not a replacement for the hub.

## When to use them

Prefer `qwen3-coder:30b` for a task with a small, explicit scope and a result that the supervising assistant can check independently. Examples: draft a helper against a specified input/output contract; add regression tests for a reproduced bug; explain a sanitized traceback; update documentation from verified facts; or refactor a small function while preserving its existing tests. Start with synthetic fixtures. Any use of copied historical data must follow the project's registered eligibility and sealed-period controls.

Use `devstral-small-2:latest` only as an optional alternative or comparison. The owner-Mac trial in [PR #110](https://github.com/maxzipperman/value-finder/pull/110) favored Qwen: 31/34 checks initially and 34/34 after feedback, versus Devstral's 22/34 and 29/34. These were three snippet tasks, not an autonomous-agent benchmark. The trial used 8K context; Qwen loaded about 19 GB, Devstral 16 GB. Larger contexts and multi-file autonomy remain untested.

Use the cloud assistants for complex repository changes, ambiguous requirements, broad architecture, independent final review, or tasks that cannot fit the local model's configured context without discarding relevant instructions. Keep research decisions, preregistration, paid authorization and live-job authority with the hub and existing controls. A local model may draft supporting code, but its answer is not approval or evidence of a betting edge.

The owner's preference authorizes suitable use without a new routing question each time. Record the model chosen and why. If the local endpoint is unavailable to the worker, explain the limitation and use the normal cloud route; never expose the Mac's local server publicly to make it reachable.

## Where to use them

The installed models run through Ollama on this Mac. For a simple offline conversation:

```sh
ollama run qwen3-coder:30b
# Optional alternative:
ollama run devstral-small-2:latest
```

For a coding interface, Ollama's installed launcher supports Claude Code. Start a dedicated worker from an isolated checkout:

```sh
ollama launch claude --model qwen3-coder:30b
```

Review the launcher's provider configuration prompts and use a dedicated worker configuration. Do not change the coordinator's provider settings, credentials or running session. The local model is Qwen even though the interface is Claude Code. The launcher itself is not proof that file edits, tool use or all project instructions work; verify them on a bounded task before using it more broadly.

A supervising assistant with local access can also submit bounded prompts to Ollama's loopback API (`http://127.0.0.1:11434/api/chat`), as in the evaluation harness in PR #110. Remote cloud workers cannot assume access to that endpoint. Downloaded model inference runs locally; orchestration in a cloud assistant and any enabled external tools may still use network or credits. For an offline task, disable external network tools, cloud model fallback and paid API access; inference being local does not make the entire coding interface offline automatically.

## Worker procedure

1. Read AGENTS.md, CLAUDE.md, STATUS.md and applicable project instructions. Work in an isolated clone/worktree, never the live checkout. Pass the relevant instructions explicitly to a bounded API prompt; do not assume the model discovers them.
2. Give one task, named files, its input/output contract and meaningful acceptance checks. Do not send credentials, .env contents, live ledgers or sealed outcomes. Use scrubbed logs and only authorized data copies.
3. Load one model at a time. Start with modest context sufficient for the task, verify that instructions are not truncated, and unload the model when finished. If memory pressure becomes high or the live jobs are affected, stop the model work.
4. Treat generated code as untrusted. Review it before running it in the restricted workspace; keep network, paid keys and live-job operations unavailable. An offline model can still generate code that calls an API, so local inference alone is not an execution boundary.
5. Run appropriate existing tests and acceptance checks. Inspect the diff for scope, data timing, logging/redaction and both shared weather copies where applicable. Give at most one focused feedback round before escalating a persistent failure to the cloud assistant. Log the failed attempt rather than treating a corrected score as first-pass success.
6. Report the model, checks, remaining failures and any fallback in the issue/PR. The supervising assistant owns validation; merges follow the existing current-head agreement and hub rules.

When an orchestration hook needs a local reason, use:

```text
LOCAL-BECAUSE: hardware: runs the owner-preferred offline coding model on this Mac.
```

This preference is a routing instruction. It does not install an automatic dispatcher, create a scheduled job, switch any running assistant's model or grant additional execution permissions.
