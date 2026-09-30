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


@pytest.mark.parametrize("worker,output", [
    ("GEMINI", "{}"),
    ("GEMINI", '{"status":"FAIL"}'),
    ("GEMINI", '{"status":"SUCCESS","conversation_id":"a","response":""}'),
    ("GEMINI", '{"status":"SUCCESS","conversation_id":null,"response":"ACK"}'),
    ("GEMINI", "{malformed}"),
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


@pytest.mark.parametrize("case", ["no_config", "missing_model", "missing_executable", "wrong_checkout", "zero_exit_error"])
def test_required_resources_and_zero_exit_error(tmp_path, monkeypatch, capsys, case):
    monkeypatch.setattr(control, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--worker", "GEMINI", "--smoke"])
    project = tmp_path / ".worktrees/public-gemini/scholargraph"
    project.mkdir(parents=True)
    executable = tmp_path / "fake.exe"
    executable.touch()
    channel = {"model_id": "fixture-model", "executable": str(executable), "project_root": str(project)}
    if case == "missing_model":
        del channel["model_id"]
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
        return FailedTurn()

    monkeypatch.setattr(control.subprocess, "Popen", launch)
    assert control.main() == 1
    assert json.loads(capsys.readouterr().err)["status"] == "FAIL"
