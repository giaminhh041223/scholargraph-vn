"""Coordinator channel integrity; these fixtures never invoke a model."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/run_public_worker.py"
spec = importlib.util.spec_from_file_location("public_worker_control", SCRIPT)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def test_valid_responses():
    assert control.parse_response("GEMINI", json.dumps({
        "status": "SUCCESS", "conversation_id": "gem-session", "response": "ACK"})) == ("gem-session", "ACK")
    stream = "diagnostic banner\n" + "\n".join(json.dumps(event) for event in [
        {"type": "text", "sessionID": "muse-session", "part": {"text": "ACK"}},
        {"type": "step_finish", "sessionID": "muse-session", "part": {"reason": "stop"}}])
    assert control.parse_response("MUSE", stream) == ("muse-session", "ACK")


def test_denied_write_is_failure_even_with_text_and_normal_stop():
    events = [
        {"type": "tool_use", "sessionID": "s", "part": {"state": {
            "status": "error", "error": "The user has specified a rule which prevents you from using this specific tool call."}}},
        {"type": "text", "sessionID": "s", "part": {"text": "write blocked, STOP"}},
        {"type": "step_finish", "sessionID": "s", "part": {"reason": "stop"}},
    ]
    with pytest.raises(ValueError, match="action was denied"):
        control.parse_response("MUSE", "\n".join(json.dumps(e) for e in events))


def test_worktree_relative_edit_permissions_preserve_scope(tmp_path):
    import fnmatch
    cwd = tmp_path / "public-muse/scholargraph"
    cwd.mkdir(parents=True)
    rules = control.edit_permissions(cwd, ["src/store.py", "logs/MUSE/"])

    def action(path):
        hits = [value for pattern, value in rules.items() if fnmatch.fnmatchcase(path, pattern)]
        return hits[-1]

    for path in ["scholargraph/src/store.py", "scholargraph\\src\\store.py",
                 "scholargraph/logs/MUSE/packet.md", "scholargraph\\logs\\MUSE\\packet.md"]:
        assert action(path) == "allow"
    for path in ["scholargraph/src/arxiv.py", "scholargraph/logs/GEMINI/packet.md",
                 "../other/scholargraph/src/store.py", "scholargraph/management/tasks.json"]:
        assert action(path) == "deny"


@pytest.mark.parametrize("paths", [[], ["../../parent.py"], [None], [""]])
def test_invalid_edit_scope_fails(tmp_path, paths):
    with pytest.raises(ValueError):
        control.edit_permissions(tmp_path.resolve(), paths)


def test_cli_denied_tool_exits_one(tmp_path):
    project = tmp_path / ".worktrees/public-muse/scholargraph"
    project.mkdir(parents=True)
    config = tmp_path / "management/public_search/channels.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"channels": {"MUSE": {
        "model_id": "opencode/fixture", "reasoning_effort": "xhigh",
        "executable": sys.executable, "project_root": str(project),
        "allowed_write_paths": ["src/store.py"]}}}), encoding="utf-8")
    auth = tmp_path / ".local/share/opencode/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"opencode": {"type": "api", "key": "SYNTHETIC_NOT_A_KEY"}}), encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Synthetic denied-write turn; never contacts a model.", encoding="utf-8")
    bootstrap = tmp_path / "denied_cli.py"
    bootstrap.write_text(f'''
import importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("control", {str(SCRIPT)!r})
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
c.ROOT = Path({str(tmp_path)!r})
c.Path.home = classmethod(lambda cls: Path({str(tmp_path)!r}))
os.environ.pop("OPENCODE_CONFIG_CONTENT", None)
class Turn:
    returncode = 0
    def communicate(self, timeout):
        events = [
            {{"type":"tool_use","sessionID":"s","part":{{"state":{{"status":"error","error":"The user has specified a rule which prevents you from using this specific tool call."}}}}}},
            {{"type":"text","sessionID":"s","part":{{"text":"STOP"}}}},
            {{"type":"step_finish","sessionID":"s","part":{{"reason":"stop"}}}}]
        return "\\n".join(json.dumps(e) for e in events).encode(), b""
c.subprocess.Popen = lambda *args, **kwargs: Turn()
sys.argv = [str(c.ROOT / "runner.py"), "--worker", "MUSE", "--mode", "work", "--prompt-file", {str(prompt)!r}]
sys.exit(c.main())
''', encoding="utf-8")
    result = subprocess.run([sys.executable, str(bootstrap)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    failure = json.loads(result.stderr)
    assert failure["status"] == "FAIL"
    assert "action was denied" in failure["reason"]
    assert "SYNTHETIC_NOT_A_KEY" not in result.stdout + result.stderr


@pytest.mark.parametrize("worker,output", [
    ("GEMINI", "{}"),
    ("GEMINI", '{"status":"FAIL"}'),
    ("GEMINI", '{"status":"SUCCESS","conversation_id":"a","response":""}'),
    ("GEMINI", '{"status":"SUCCESS","conversation_id":null,"response":"ACK"}'),
    ("GEMINI", "{malformed}"),
    ("GEMINI", '{"status":"SUCCESS","conversation_id":"a","response":"DONE","denied_actions":[{"action":"command"}]}'),
    ("MUSE", "banner only"),
    ("MUSE", '{"type":"error","sessionID":"a"}'),
    ("MUSE", '{"type":"text","sessionID":"a","part":{"text":"ACK"}}'),
    ("MUSE", '{"type":"text","sessionID":"a","part":{}}\n{"type":"step_finish","sessionID":"a"}'),
    ("MUSE", '{"type":"text","sessionID":"a","part":{"text":"ACK"}}\n{"type":"step_finish","sessionID":"b"}'),
    ("MUSE", '{"type":"text","sessionID":"a","part":{"text":"ACK"}}\n{malformed}'),
    ("MUSE", '{"type":"text","sessionID":"a","part":{"text":"ACK"}}\n{"type":"step_finish","sessionID":"a","part":{"reason":"tool-calls"}}'),
])
def test_incomplete_or_invalid_response_fails(worker, output):
    with pytest.raises((ValueError, KeyError, TypeError)):
        control.parse_response(worker, output)


@pytest.mark.parametrize("options", [
    ["--worker", "GEMINI", "--prompt-file", "missing.txt"],
    ["--worker", "GEMINI", "--smoke", "--timeout", "0"],
    ["--worker", "GEMINI", "--smoke", "--mode", "work"],
])
def test_cli_bad_input_exits_one(tmp_path, options):
    result = subprocess.run([sys.executable, str(SCRIPT), *options], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert json.loads(result.stderr)["status"] == "FAIL"


@pytest.mark.parametrize("case", ["no_config", "missing_model", "missing_effort", "invalid_effort", "missing_executable", "wrong_checkout", "zero_exit_error"])
def test_required_resources_and_zero_exit_error(tmp_path, monkeypatch, capsys, case):
    monkeypatch.setattr(control, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--worker", "GEMINI", "--smoke"])
    project = tmp_path / ".worktrees/public-gemini/scholargraph"
    project.mkdir(parents=True)
    executable = tmp_path / "fake.exe"
    executable.touch()
    channel = {"model_id": "fixture-model", "reasoning_effort": "max", "executable": str(executable), "project_root": str(project)}
    if case == "missing_model":
        del channel["model_id"]
    elif case == "missing_effort":
        del channel["reasoning_effort"]
    elif case == "invalid_effort":
        channel["reasoning_effort"] = "unsupported"
    elif case == "missing_executable":
        executable.unlink()
    elif case == "wrong_checkout":
        channel["project_root"] = str(tmp_path)
    config = tmp_path / "management/public_search/channels.json"
    config.parent.mkdir(parents=True)
    if case != "no_config":
        config.write_text(json.dumps({"channels": {"GEMINI": channel}}), encoding="utf-8")

    class FailedTurn:
        returncode = 0

        def communicate(self, timeout):
            return b'{"status":"FAIL"}', b""

    def launch(*args, **kwargs):
        assert case == "zero_exit_error", "Must fail before starting a process"
        command = args[0]
        assert command[command.index("--effort") + 1] == "max"
        return FailedTurn()

    monkeypatch.setattr(control.subprocess, "Popen", launch)
    assert control.main() == 1
    assert json.loads(capsys.readouterr().err)["status"] == "FAIL"
