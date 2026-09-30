#!/usr/bin/env python3
"""PreToolUse hook: the owner's cloud-first rule (September 29, 2026). See ops/CLOUD_FIRST.md.

Claude Code runs this before every Agent, Task or Workflow call in this repo, with the hook's JSON on
standard input. Work that needs only what is in git goes to the cloud worker; a local agent or workflow
must say why it needs this Mac, with a line in its prompt:

    LOCAL-BECAUSE: <reason>: <at least 15 characters of explanation>

Exit 0 and print nothing: the call goes ahead. Exit 2 with a message on standard error: the call is
blocked and the message goes back to the chat.

How the line is read:
- It is one line of the text. Spaces or tabs may come before it, and so may one comment marker
  (`//`, `/*`, `*` or `#`), so a workflow script can carry it as a comment.
- `LOCAL-BECAUSE:` and the reason are matched exactly, lower case for the reason. Spaces around the
  second colon are allowed.
- The explanation is what follows the second colon, with a trailing `*/` and the surrounding
  whitespace removed. It must be at least 15 characters long (characters, not bytes), hold at least
  10 letters or digits, and not start with `<` (an unfilled `<one sentence ...>` template).
- Lines are split only at LF, CRLF and CR, not at the other characters str.splitlines() splits at
  (vertical tab, form feed, U+001C to U+001E, U+0085, U+2028 and U+2029).
- Agent and Task: looked for in `prompt` and `description`. Workflow: in `script` when it is a
  non-empty string (then only there, even if `scriptPath` or `name` is also given); otherwise, for a
  workflow started from a file (`scriptPath`) or by `name`, in that file, if it can be found under the
  project folder ($CLAUDE_PROJECT_DIR or the session's cwd) or the home folder. A saved workflow `name`
  is looked up as .claude/workflows/<name>[.ext] under each of those folders; that location is an
  assumption, to be confirmed on the Mac.
- A workflow file that cannot be read is a deliberate block, not a failure: one that is missing, lies
  outside those folders (after following symlinks), is not a regular file (checked on the opened file,
  so a FIFO swapped in cannot hang the hook), is a .env file (a name starting with `.env`, or ending in
  `.env`), or is over 2 MB. So a built-in or plugin workflow started by `name`, with no file in those
  folders, is always blocked, even with a reason; pass its script inline with the line instead.

Other tools pass. So does every call when CLAUDE_CODE_REMOTE is "true" (a cloud session) or
VF_CLOUD_FIRST is "off" (the owner's switch; case and surrounding spaces ignored).

It fails open: input that is not JSON, a missing field, or any unexpected error lets the call through,
with one line on standard error saying the check could not run. It writes no file, makes no network
request, reads no .env file, and never prints the tool's input.

Known leftover: a tool input nested deeply enough (about a thousand levels of JSON arrays or objects)
makes the JSON parser raise RecursionError, and that fails open like every other unexpected error:
the call is allowed, with the one-line warning. The brief's fail-open rule wins over closing this.

.claude/settings.json runs this file only if it exists and is readable (otherwise the call goes ahead):
without that guard, python3 exits 2 when it cannot open the script, and exit 2 would block every call.

Standard library only; Python 3.9 or later (macOS's own python3 is 3.9).
"""

import json
import os
import re
import stat
import sys

REASONS = ("keys", "raw-data", "jobs", "live-checkout", "hardware", "home-token", "owner-asked")
MIN_EXPLANATION = 15  # characters
MIN_ALNUM = 10  # letters or digits among them
MARKER = "LOCAL-BECAUSE:"
MAX_SCRIPT_BYTES = 2 * 1024 * 1024  # a workflow file bigger than this is not read (and so is blocked)

# Anchored at the start of one line; no nested or overlapping repeats, so it runs in linear time.
LINE = re.compile(
    r"[ \t]*(?:(?://|/\*|\*|#)[ \t]*)?LOCAL-BECAUSE:[ \t]*("
    + "|".join(re.escape(r) for r in REASONS)
    + r")[ \t]*:(.*)\Z"
)
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
NEWLINES = re.compile(r"\r\n|\r|\n")

BLOCK_MESSAGE = """\
Blocked by the owner's cloud-first rule (September 29, 2026): this {what} would run on this Mac, on the plan's limits.
- Work that needs only what is in git goes to the cloud worker: send it the brief with SendMessage (a long brief goes in a file on the hub-briefs branch, briefs/<date>-<n>-<name>.md, and the message names the file).
- Work that needs this Mac can run here: start it again with this line in its prompt{where}:
    LOCAL-BECAUSE: <reason>: <one sentence on why it needs this Mac>
  where <reason> is one of: keys, raw-data, jobs, live-checkout, hardware, home-token, owner-asked.
The rule is in CLAUDE.md ("The hub") and ops/CLOUD_FIRST.md."""

UNREADABLE_MESSAGE = """\
Blocked by the owner's cloud-first rule (September 29, 2026): the workflow's script could not be read, so the hook cannot see a LOCAL-BECAUSE line in it.
- Work that needs only what is in git goes to the cloud worker with SendMessage (a long brief goes in a file on the hub-briefs branch).
- Work that needs this Mac: pass the script inline (`script`), or keep the file under the project or home folder, with this line in it as a comment:
    // LOCAL-BECAUSE: <reason>: <one sentence on why it needs this Mac>
  where <reason> is one of: keys, raw-data, jobs, live-checkout, hardware, home-token, owner-asked.
- A saved or built-in workflow whose file isn't in the project's or home folder's .claude/workflows can't be checked: pass the script inline with the line, or the owner can switch the rule off.
The rule is in CLAUDE.md ("The hub") and ops/CLOUD_FIRST.md."""


class UnexpectedInput(Exception):
    """The input is not what the check expects; let the call through."""


class Unreadable(Exception):
    """A workflow file could not be found or read; block."""


def has_reason_line(text):
    """True when some line of `text` is a valid LOCAL-BECAUSE line."""
    if not isinstance(text, str) or MARKER not in text:
        return False
    for line in NEWLINES.split(text):
        if MARKER not in line:
            continue
        m = LINE.match(line)
        if not m:
            continue
        explanation = m.group(2).strip()
        if explanation.endswith("*/"):
            explanation = explanation[:-2].strip()
        if _explains(explanation):
            return True
    return False


def _explains(explanation):
    """At least 15 characters, at least 10 of them letters or digits, and not an unfilled `<...>`."""
    return (
        len(explanation) >= MIN_EXPLANATION
        and sum(1 for c in explanation if c.isalnum()) >= MIN_ALNUM
        and not explanation.startswith("<")
    )


def _roots(hook_input):
    """Folders a workflow file may be read from: the project, the session's cwd, and home."""
    roots = []
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), hook_input.get("cwd"), os.path.expanduser("~")):
        if not isinstance(candidate, str) or not os.path.isabs(candidate):
            continue
        real = os.path.realpath(candidate)
        if real != os.path.dirname(real) and os.path.isdir(real) and real not in roots:  # never "/"
            roots.append(real)
    return roots


def _inside(path, roots):
    return any(os.path.commonpath([path, root]) == root for root in roots)


def _is_env(filename):
    """A .env file: its name starts with `.env` (.env, .env.local) or ends in `.env` (prod.env)."""
    lower = filename.lower()
    return lower.startswith(".env") or os.path.splitext(lower)[1] == ".env"


OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)


def _read_script(path, roots):
    """Read a workflow file, only from under `roots`, only a regular file, never a .env, capped."""
    real = os.path.realpath(path)
    if not _inside(real, roots):
        raise Unreadable()
    if _is_env(os.path.basename(path)) or _is_env(os.path.basename(real)):
        raise Unreadable()
    try:
        # Open first (non-blocking, so a FIFO cannot hang the hook), then check what was opened.
        fd = os.open(real, OPEN_FLAGS)
    except OSError:
        raise Unreadable()
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_SCRIPT_BYTES:
            raise Unreadable()
        chunks, size = [], 0
        while size <= MAX_SCRIPT_BYTES:
            chunk = os.read(fd, MAX_SCRIPT_BYTES + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    except OSError:
        raise Unreadable()
    finally:
        os.close(fd)
    if size > MAX_SCRIPT_BYTES:
        raise Unreadable()
    return b"".join(chunks).decode("utf-8", errors="replace")


def _script_from_path(script_path, hook_input, roots):
    if not isinstance(script_path, str) or not script_path or "\0" in script_path:
        raise Unreadable()
    path = os.path.expanduser(script_path)
    if not os.path.isabs(path):
        base = hook_input.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
        if not isinstance(base, str) or not os.path.isabs(base):
            raise Unreadable()
        path = os.path.join(base, path)
    return _read_script(path, roots)


def _script_from_name(name, roots):
    """A saved workflow: <project>/.claude/workflows/<name>[.ext] or ~/.claude/workflows/<name>[.ext]."""
    if not isinstance(name, str) or not SAFE_NAME.match(name) or ".." in name:
        raise Unreadable()
    for root in roots:
        folder = os.path.join(root, ".claude", "workflows")
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            continue
        for entry in entries:
            if _is_env(entry):
                continue
            if entry == name or os.path.splitext(entry)[0] == name:
                try:
                    return _read_script(os.path.join(folder, entry), roots)
                except Unreadable:
                    continue
    raise Unreadable()


def decide(hook_input):
    """Return None to allow, or the message to block with."""
    if not isinstance(hook_input, dict):
        raise UnexpectedInput()
    tool = hook_input.get("tool_name")
    if not isinstance(tool, str):
        raise UnexpectedInput()
    if tool not in ("Agent", "Task", "Workflow"):
        return None
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        raise UnexpectedInput()

    if tool in ("Agent", "Task"):
        prompt, description = tool_input.get("prompt"), tool_input.get("description")
        if not isinstance(prompt, str) and not isinstance(description, str):
            raise UnexpectedInput()
        if has_reason_line(prompt) or has_reason_line(description):
            return None
        return BLOCK_MESSAGE.format(what="agent", where=" (or its description)")

    # Workflow
    script, script_path, name = tool_input.get("script"), tool_input.get("scriptPath"), tool_input.get("name")
    if not any(isinstance(v, str) and v for v in (script, script_path, name)):
        raise UnexpectedInput()
    if isinstance(script, str) and script:  # an inline script is the one that runs: judge only it
        if has_reason_line(script):
            return None
        return BLOCK_MESSAGE.format(what="workflow", where=" (in the script, as a comment)")
    roots = _roots(hook_input)
    try:
        if isinstance(script_path, str) and script_path:
            text = _script_from_path(script_path, hook_input, roots)
        else:
            text = _script_from_name(name, roots)
    except Unreadable:
        return UNREADABLE_MESSAGE
    if has_reason_line(text):
        return None
    return BLOCK_MESSAGE.format(what="workflow", where=" (in the workflow's script, as a comment)")


def main():
    try:
        raw = sys.stdin.buffer.read()  # read it all first, so the app never writes into a closed pipe
        if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
            return 0  # a cloud session uses cloud credits; its own subagents are fine
        if os.environ.get("VF_CLOUD_FIRST", "").strip().lower() == "off":
            return 0  # the owner's switch
        hook_input = json.loads(raw.decode("utf-8", errors="replace"))
        message = decide(hook_input)
    except Exception as exc:  # fail open: a broken check must never stop the hub
        # Only the error's type is printed: its text could quote the tool's input.
        sys.stderr.write("cloud-first check could not run (%s); the call was allowed.\n" % type(exc).__name__)
        return 0
    if message is None:
        return 0
    sys.stderr.write(message + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
