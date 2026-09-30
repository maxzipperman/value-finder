"""Tests for ops/hooks/cloud_first.py, the cloud-first PreToolUse hook (ops/CLOUD_FIRST.md).

Each test runs the hook as a subprocess with the hook's JSON on standard input, as Claude Code does.
From the repo root:

    uv run --project dashboard pytest -q ops/tests

The hook runs under the same Python as pytest; set HOOK_PYTHON to try another one (for example the
Mac's /usr/bin/python3, which is 3.9).
"""

import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "cloud_first.py"
PYTHON = os.environ.get("HOOK_PYTHON") or sys.executable
REASONS = ["keys", "raw-data", "jobs", "live-checkout", "hardware", "home-token", "owner-asked"]
SECRET = "SECRET-7f3a9c-DO-NOT-ECHO"
GOOD = "LOCAL-BECAUSE: keys: it needs the Odds API key in the .env files"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    return p


def run(payload, home=None, project=None, env=None, raw=None):
    """Run the hook; return (exit code, stdout, stderr)."""
    e = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_REMOTE", "VF_CLOUD_FIRST", "CLAUDE_PROJECT_DIR")}
    if home is not None:
        e["HOME"] = str(home)
    if project is not None:
        e["CLAUDE_PROJECT_DIR"] = str(project)
    e.update(env or {})
    data = raw if raw is not None else json.dumps(payload).encode()
    p = subprocess.run([PYTHON, str(HOOK)], input=data, capture_output=True, env=e, timeout=30)
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def agent(prompt, description="a task", tool="Agent", **extra):
    d = {"tool_name": tool, "tool_input": {"prompt": prompt, "description": description},
         "hook_event_name": "PreToolUse", "session_id": "s1"}
    d.update(extra)
    return d


def workflow(**tool_input):
    return {"tool_name": "Workflow", "tool_input": tool_input, "hook_event_name": "PreToolUse"}


def blocked(result):
    code, out, err = result
    assert code == 2, (code, err)
    assert out == ""
    assert "cloud-first" in err and "SendMessage" in err and "LOCAL-BECAUSE" in err
    assert "CLAUDE.md" in err and "ops/CLOUD_FIRST.md" in err
    return err


def allowed(result):
    code, out, err = result
    assert (code, out, err) == (0, "", ""), (code, out, err)


# --- Agent and Task -------------------------------------------------------------------------------

def test_agent_without_the_line_is_blocked(home):
    err = blocked(run(agent("Review the PR " + SECRET), home))
    for reason in REASONS:
        assert reason in err


def test_agent_with_the_line_is_allowed(home):
    allowed(run(agent("Pull the odds.\n" + GOOD + "\nThen report."), home))


def test_task_is_treated_like_agent(home):
    blocked(run(agent("Review the PR", tool="Task"), home))
    allowed(run(agent(GOOD, tool="Task"), home))


def test_the_line_in_the_description_counts(home):
    allowed(run(agent("Review the PR", description=GOOD), home))


@pytest.mark.parametrize("reason", REASONS)
def test_each_reason_is_allowed(home, reason):
    allowed(run(agent("LOCAL-BECAUSE: %s: an explanation that is long enough" % reason), home))


@pytest.mark.parametrize("reason", ["cheap", "git", "KEYS", "raw_data", "", "keys-and-more"])
def test_a_reason_not_on_the_list_is_blocked(home, reason):
    blocked(run(agent("LOCAL-BECAUSE: %s: an explanation that is long enough" % reason), home))


@pytest.mark.parametrize("explanation", ["", "short", "fourteen chars", "   fourteen chars   ", "12345678901234 */"])
def test_an_explanation_under_15_characters_is_blocked(home, explanation):
    blocked(run(agent("LOCAL-BECAUSE: keys: " + explanation), home))


def test_exactly_15_characters_is_enough(home):
    allowed(run(agent("LOCAL-BECAUSE: jobs: " + "x" * 15), home))


@pytest.mark.parametrize("explanation", [
    "." * 15,                                  # long enough, but no letters or digits
    "\u200b" * 15,                             # zero-width spaces: 15 characters, nothing written
    "a.b.c.d.e.f.g.h.i",                       # 17 characters, only 9 letters
    "<one sentence on why>",                   # the template, not filled in
    "<one sentence on why it needs this Mac>",
])
def test_an_explanation_without_ten_letters_or_digits_or_unfilled_is_blocked(home, explanation):
    blocked(run(agent("LOCAL-BECAUSE: keys: " + explanation), home))


def test_ten_letters_or_digits_among_15_characters_is_enough(home):
    allowed(run(agent("LOCAL-BECAUSE: keys: ab-cd-ef-gh-ij."), home))
    allowed(run(agent("LOCAL-BECAUSE: keys: Odds API key, see .env <here>"), home))  # "<" later is fine


@pytest.mark.parametrize("line", [
    "   LOCAL-BECAUSE: keys: indented by spaces is fine",
    "\tLOCAL-BECAUSE:keys:no spaces around the colons",
    "LOCAL-BECAUSE: keys : a space before the second colon",
    "// LOCAL-BECAUSE: keys: as a JavaScript comment",
    "# LOCAL-BECAUSE: keys: as a shell or Python comment",
    " * LOCAL-BECAUSE: keys: inside a block comment",
    "/* LOCAL-BECAUSE: keys: a one-line block comment */",
])
def test_accepted_line_forms(home, line):
    allowed(run(agent("text\n" + line + "\nmore"), home))


@pytest.mark.parametrize("line", [
    "Please note LOCAL-BECAUSE: keys: not at the start of the line",
    "- LOCAL-BECAUSE: keys: a markdown bullet is not a comment",
    "local-because: keys: the marker is upper case only",
    "LOCAL-BECAUSE keys: the first colon is missing here",
    "LOCAL-BECAUSE: keys the second colon is missing here",
])
def test_rejected_line_forms(home, line):
    blocked(run(agent("text\n" + line + "\nmore"), home))


def test_the_line_must_be_its_own_line_not_split(home):
    blocked(run(agent("LOCAL-BECAUSE: keys:\nit needs the Odds API key"), home))


@pytest.mark.parametrize("separator", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_only_lf_crlf_and_cr_start_a_line(home, separator):
    blocked(run(agent("hello " + separator + GOOD), home))


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_crlf_and_cr_prompts_with_the_line_are_allowed(home, newline):
    allowed(run(agent(newline.join(["Pull the odds.", GOOD, "Then report."])), home))


# --- Workflow -------------------------------------------------------------------------------------

SCRIPT_WITH = "export const meta = {name: 'x', description: 'y'}\n// " + GOOD + "\nawait agent('go')\n"
SCRIPT_WITHOUT = "export const meta = {name: 'x', description: 'y'}\nawait agent('go " + SECRET + "')\n"


def test_workflow_script_with_the_line_is_allowed(home):
    allowed(run(workflow(script=SCRIPT_WITH), home))


def test_workflow_script_without_the_line_is_blocked(home):
    blocked(run(workflow(script=SCRIPT_WITHOUT), home))


def test_an_inline_script_is_judged_alone(home, project):
    with_line, without_line = project / "with.js", project / "without.js"
    with_line.write_text(SCRIPT_WITH)
    without_line.write_text(SCRIPT_WITHOUT)
    d = project / ".claude" / "workflows"
    d.mkdir(parents=True)
    (d / "saved.js").write_text(SCRIPT_WITH)
    # The inline script has the line: allowed, whatever the file says.
    allowed(run(workflow(script=SCRIPT_WITH, scriptPath=str(without_line)), home, project))
    allowed(run(workflow(script=SCRIPT_WITH, scriptPath=str(project / "missing.js")), home, project))
    # The inline script lacks the line: blocked, even though the file or the saved workflow has it.
    blocked(run(workflow(script=SCRIPT_WITHOUT, scriptPath=str(with_line)), home, project))
    blocked(run(workflow(script=SCRIPT_WITHOUT, name="saved"), home, project))
    # An empty inline script falls back to the file.
    allowed(run(workflow(script="", scriptPath=str(with_line)), home, project))


def test_workflow_by_script_path_whose_file_holds_the_line(home, project):
    f = home / ".claude" / "sessions" / "wf.js"
    f.parent.mkdir(parents=True)
    f.write_text(SCRIPT_WITH)
    allowed(run(workflow(scriptPath=str(f)), home, project))


def test_workflow_by_script_path_under_the_project(home, project):
    f = project / "wf.js"
    f.write_text(SCRIPT_WITH)
    allowed(run(workflow(scriptPath=str(f)), home, project))
    allowed(run(dict(workflow(scriptPath="wf.js"), cwd=str(project)), home))  # relative to cwd


def test_workflow_by_script_path_whose_file_lacks_the_line(home, project):
    f = home / "wf.js"
    f.write_text(SCRIPT_WITHOUT)
    err = blocked(run(workflow(scriptPath=str(f)), home, project))
    assert SECRET not in err


def test_workflow_by_script_path_whose_file_is_missing(home, project):
    code, out, err = run(workflow(scriptPath=str(home / ("missing-" + SECRET + ".js"))), home, project)
    assert code == 2 and out == ""
    assert "could not be read" in err
    assert SECRET not in err


def test_workflow_file_outside_project_and_home_is_not_read(tmp_path, home, project):
    outside = tmp_path / "elsewhere" / "wf.js"
    outside.parent.mkdir()
    outside.write_text(SCRIPT_WITH)
    code, _, err = run(workflow(scriptPath=str(outside)), home, project)
    assert code == 2 and "could not be read" in err
    code, _, err = run(workflow(scriptPath=str(home / ".." / "elsewhere" / "wf.js")), home, project)
    assert code == 2 and "could not be read" in err


def test_workflow_symlink_out_of_home_is_not_read(tmp_path, home, project):
    outside = tmp_path / "elsewhere.js"
    outside.write_text(SCRIPT_WITH)
    (home / "link.js").symlink_to(outside)
    code, _, err = run(workflow(scriptPath=str(home / "link.js")), home, project)
    assert code == 2 and "could not be read" in err


@pytest.mark.parametrize("filename", [".env", ".env.local", "prod.env", "PROD.ENV", ".ENV", "x.Env"])
def test_workflow_env_file_is_never_read(home, project, filename):
    f = home / filename
    f.write_text(SCRIPT_WITH)
    code, _, err = run(workflow(scriptPath=str(f)), home, project)
    assert code == 2 and "could not be read" in err


def test_workflow_symlink_to_an_env_file_is_not_read(home, project):
    (home / "prod.env").write_text(SCRIPT_WITH)
    (home / "wf.js").symlink_to(home / "prod.env")
    code, _, err = run(workflow(scriptPath=str(home / "wf.js")), home, project)
    assert code == 2 and "could not be read" in err


def test_workflow_by_name_never_picks_an_env_file(home, project):
    d = project / ".claude" / "workflows"
    d.mkdir(parents=True)
    (d / "prod.env").write_text(SCRIPT_WITH)
    (d / ".env").write_text(SCRIPT_WITH)
    for name in ("prod", "prod.env", "env"):
        code, _, err = run(workflow(name=name), home, project)
        assert code == 2 and "could not be read" in err, name
    (d / "prod.js").write_text(SCRIPT_WITH)
    allowed(run(workflow(name="prod"), home, project))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs here")
def test_workflow_fifo_is_not_read_and_does_not_hang(home, project):
    fifo = home / "wf.js"
    os.mkfifo(str(fifo))
    start = time.monotonic()
    code, _, err = run(workflow(scriptPath=str(fifo)), home, project)
    assert time.monotonic() - start < 5.0
    assert code == 2 and "could not be read" in err


def test_workflow_directory_and_huge_file_are_not_read(home, project):
    code, _, err = run(workflow(scriptPath=str(home)), home, project)
    assert code == 2 and "could not be read" in err
    big = home / "big.js"
    big.write_text("// " + GOOD + "\n" + "x" * (3 * 1024 * 1024))
    code, _, err = run(workflow(scriptPath=str(big)), home, project)
    assert code == 2 and "could not be read" in err


def test_workflow_by_name(home, project):
    d = project / ".claude" / "workflows"
    d.mkdir(parents=True)
    (d / "pull-review.js").write_text(SCRIPT_WITH)
    (d / "plain.js").write_text(SCRIPT_WITHOUT)
    allowed(run(workflow(name="pull-review"), home, project))
    blocked(run(workflow(name="plain"), home, project))
    code, _, err = run(workflow(name="nowhere"), home, project)
    assert code == 2 and "could not be read" in err
    assert "built-in workflow" in err and "switch the rule off" in err
    code, _, err = run(workflow(name="../plain"), home, project)
    assert code == 2 and "could not be read" in err


def test_workflow_by_name_in_home(home, project):
    d = home / ".claude" / "workflows"
    d.mkdir(parents=True)
    (d / "sweep.js").write_text(SCRIPT_WITH)
    allowed(run(workflow(name="sweep"), home, project))


# --- Switches, other tools, bad input ------------------------------------------------------------

def test_cloud_session_is_allowed(home):
    allowed(run(agent("Review the PR"), home, env={"CLAUDE_CODE_REMOTE": "true"}))
    blocked(run(agent("Review the PR"), home, env={"CLAUDE_CODE_REMOTE": "false"}))


@pytest.mark.parametrize("value", ["off", "OFF", " off "])
def test_owner_switch_off_is_allowed(home, value):
    allowed(run(agent("Review the PR"), home, env={"VF_CLOUD_FIRST": value}))


def test_owner_switch_other_values_keep_the_rule(home):
    blocked(run(agent("Review the PR"), home, env={"VF_CLOUD_FIRST": "on"}))


@pytest.mark.parametrize("tool", ["Bash", "Read", "SendMessage", "Agents", "mcp__x__Agent", "Workflows"])
def test_other_tools_pass(home, tool):
    allowed(run({"tool_name": tool, "tool_input": {"prompt": "anything"}}, home))


@pytest.mark.parametrize("raw", [b"not json " + SECRET.encode(), b"", b"[1, 2]", b"\xff\xfe\x00"])
def test_input_that_is_not_json_passes_with_a_warning(home, raw):
    code, out, err = run(None, home, raw=raw)
    assert code == 0 and out == ""
    assert err.count("\n") == 1 and "cloud-first check could not run" in err
    assert SECRET not in err


@pytest.mark.parametrize("payload", [
    {"tool_input": {"prompt": "x"}},
    {"tool_name": "Agent"},
    {"tool_name": "Agent", "tool_input": "a string"},
    {"tool_name": "Agent", "tool_input": {}},
    {"tool_name": "Workflow", "tool_input": {"args": [1]}},
])
def test_a_missing_field_passes_with_a_warning(home, payload):
    code, out, err = run(payload, home)
    assert code == 0 and out == "" and "cloud-first check could not run" in err


def test_five_megabytes_returns_within_two_seconds(home):
    cases = [
        agent("x" * (5 * 1024 * 1024)),                                   # no line at all
        agent(("filler text line\n" * 330000) + GOOD),                    # the line at the very end
        agent("LOCAL-BECAUSE: " * 370000),                                # one huge line of markers
        agent("LOCAL-BECAUSE: keys:" + " " * (5 * 1024 * 1024) + "x"),     # huge whitespace run
        agent(("// LOCAL-BECAUSE: keys: short\n") * 180000),              # many near-misses
    ]
    expected = [2, 0, 2, 2, 2]
    for payload, want in zip(cases, expected):
        start = time.monotonic()
        code, _, _ = run(payload, home)
        assert time.monotonic() - start < 2.0
        assert code == want


def test_nothing_of_the_input_appears_in_the_output(home, project):
    payloads = [
        agent("Review " + SECRET, description=SECRET),
        agent(SECRET, tool="Task"),
        workflow(script="// " + SECRET),
        workflow(scriptPath=str(home / SECRET)),
        workflow(name=SECRET),
        {"tool_name": "Agent", "tool_input": SECRET},
        {"tool_name": SECRET, "tool_input": {"prompt": SECRET}},
    ]
    for payload in payloads:
        _, out, err = run(payload, home, project)
        assert SECRET not in out and SECRET not in err


def test_the_hook_parses_as_python_3_9():
    ast.parse(HOOK.read_text(), feature_version=(3, 9))


# --- .claude/settings.json and the command it runs -----------------------------------------------

REPO = HOOK.parents[2]
# The hook runs only if its file is there: `python3 <missing file>` exits 2, and exit 2 would block.
COMMAND = 'f="$CLAUDE_PROJECT_DIR/ops/hooks/cloud_first.py"; [ -f "$f" ] && [ -r "$f" ] || exit 0; python3 "$f"'


def settings():
    return json.loads((REPO / ".claude" / "settings.json").read_text())


def test_settings_hold_both_hooks():
    hooks = settings()["hooks"]
    assert set(hooks) == {"SessionStart", "PreToolUse"}
    # SessionStart exactly as on main before this change.
    assert hooks["SessionStart"] == [
        {"hooks": [{"type": "command", "command": '"$CLAUDE_PROJECT_DIR"/ops/cloud_setup.sh', "timeout": 900}]}
    ]
    assert hooks["PreToolUse"] == [
        {"matcher": "Agent|Task|Workflow", "hooks": [{"type": "command", "command": COMMAND, "timeout": 10}]}
    ]


def run_command(payload, project_dir):
    """Run the settings' command string under /bin/sh, as the app does."""
    e = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_REMOTE", "VF_CLOUD_FIRST", "CLAUDE_PROJECT_DIR")}
    if project_dir is not None:
        e["CLAUDE_PROJECT_DIR"] = str(project_dir)
    command = settings()["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    p = subprocess.run(["/bin/sh", "-c", command], input=json.dumps(payload).encode(),
                       capture_output=True, env=e, timeout=30)
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def test_the_command_fails_open_when_the_hook_file_is_missing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run_command(agent("Review the PR"), empty) == (0, "", "")
    assert run_command(agent("Review the PR"), None) == (0, "", "")  # CLAUDE_PROJECT_DIR unset


def test_the_command_runs_the_hook_when_it_is_there():
    code, _, err = run_command(agent("Review the PR"), REPO)
    assert code == 2 and "cloud-first" in err
    assert run_command(agent(GOOD), REPO) == (0, "", "")
