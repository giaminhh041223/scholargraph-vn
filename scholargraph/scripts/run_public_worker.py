"""Direct, bounded CLI turn for the public-search workers. No scheduler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def edit_permissions(cwd, write_paths):
    """OpenCode edit asks with paths relative to the Git worktree root."""
    if not isinstance(write_paths, list) or not write_paths:
        raise ValueError("Authorized write paths missing")
    edits = {"*": "deny"}
    for relative in write_paths:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("Authorized write path must be relative")
        resolved = (cwd / relative).resolve()
        if not resolved.is_relative_to(cwd):
            raise ValueError("Authorized write path escapes worker checkout")
        repo_relative = resolved.relative_to(cwd.parent).as_posix()
        for pattern in (str(resolved), resolved.as_posix(), repo_relative,
                        repo_relative.replace("/", "\\")):
            suffix = ("\\*" if "\\" in pattern else "/*") if relative.endswith("/") else ""
            edits[pattern + suffix] = "allow"
    return edits


def parse_response(worker, output):
    if worker == "GEMINI":
        result = json.loads(output)
        if result["status"] != "SUCCESS":
            raise ValueError("Antigravity turn failed")
        if "denied_actions" in result and result["denied_actions"]:
            raise ValueError("Antigravity required action was denied")
        session, response = result["conversation_id"], result["response"]
    else:
        events = []
        for line in output.splitlines():
            # OpenCode can emit diagnostics before its NDJSON event stream.
            if line.lstrip().startswith("{"):
                events.append(json.loads(line))
        if not events or any(event["type"] == "error" for event in events):
            raise ValueError("OpenCode missing events or returned an error")
        for event in events:
            if event["type"] == "tool_use":
                state = event["part"]["state"]
                if state["status"] == "error" and "rule which prevents" in state["error"]:
                    raise ValueError("OpenCode required tool action was denied")
        sessions = {event["sessionID"] for event in events}
        if len(sessions) != 1:
            raise ValueError("OpenCode session mismatch")
        session = sessions.pop()
        response = "".join(event["part"]["text"] for event in events
                           if event["type"] == "text")
        finishes = [event for event in events if event["type"] == "step_finish"]
        if not finishes:
            raise ValueError("OpenCode completion event missing")
        if finishes[-1]["part"]["reason"] != "stop":
            raise ValueError("OpenCode final step did not complete normally")
    if not isinstance(session, str) or not session.strip():
        raise ValueError("Session ID missing")
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Worker response missing")
    return session, response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=["GEMINI", "MUSE"], required=True)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--mode", choices=["plan", "work"], default="plan")
    parser.add_argument("--session")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    run_dir = None
    summary = None
    try:
        if not 1 <= args.timeout <= 7200:
            raise ValueError("Timeout must be 1..7200 seconds")
        if args.smoke == (args.prompt_file is not None):
            raise ValueError("Choose exactly one of --smoke and --prompt-file")
        if args.smoke and (args.mode != "plan" or args.session):
            raise ValueError("Smoke requires a new plan session")
        config = json.loads((ROOT / "management/public_search/channels.json").read_text(encoding="utf-8"))
        channel = config["channels"][args.worker]
        executable = Path(channel["executable"])
        cwd = Path(channel["project_root"]).resolve()
        expected = ROOT / ".worktrees" / ("public-" + args.worker.lower()) / "scholargraph"
        if cwd != expected.resolve() or not cwd.is_dir():
            raise ValueError("Unexpected or missing worker checkout")
        if not executable.is_file():
            raise ValueError("Worker executable missing")
        model = channel["model_id"]
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Model ID missing")
        effort = channel["reasoning_effort"]
        supported = {"GEMINI": {"low", "medium", "high", "max"},
                     "MUSE": {"minimal", "low", "medium", "high", "xhigh"}}
        if effort not in supported[args.worker]:
            raise ValueError("Unsupported reasoning effort for configured channel")
        nonce = "SCHOLARGRAPH_" + args.worker + "_CHANNEL_OK"
        prompt = ("Do not use tools, read files, run commands, or modify anything. Reply exactly " + nonce + "."
                  if args.smoke else args.prompt_file.read_text(encoding="utf-8-sig"))
        if not prompt.strip() or len(prompt) > 16000:
            raise ValueError("Prompt must be nonempty and at most 16000 characters")
        env = os.environ.copy()
        if args.worker == "GEMINI":
            command = [str(executable), "--model", model, "--effort", effort,
                       "--add-dir", str(ROOT), "--mode",
                       "plan" if args.mode == "plan" else "accept-edits",
                       "--output-format", "json", "--print-timeout", str(args.timeout) + "s"]
            if args.session:
                command += ["--conversation", args.session]
            command += ["--print", prompt]
        else:
            # A separate CLI database avoids the installed desktop/CLI schema mismatch.
            runtime = ROOT / "data/public_search/control"
            env["XDG_DATA_HOME"] = str(runtime / "opencode-runtime")
            env["XDG_STATE_HOME"] = str(runtime / "opencode-state")
            if model.startswith("opencode/"):
                auth = json.loads((Path.home() / ".local/share/opencode/auth.json").read_text(encoding="utf-8"))
                credential = auth["opencode"]
                if credential["type"] != "api" or not isinstance(credential["key"], str) or not credential["key"].strip():
                    raise ValueError("OpenCode API credential missing or unsupported")
                if "OPENCODE_CONFIG_CONTENT" in env:
                    raise ValueError("Resolve existing process config override before dispatch")
                # Reuse saved auth in memory; do not copy keys into the project runtime.
                overrides = {"provider": {"opencode": {"options": {"apiKey": credential["key"]}}}}
                if args.mode == "work":
                    edits = edit_permissions(cwd, channel["allowed_write_paths"])
                    overrides["permission"] = {
                        "external_directory": {"*": "deny", str(ROOT) + "\\*": "allow", ROOT.as_posix() + "/*": "allow"},
                        "edit": edits,
                        "read": {"*": "allow", "*.env": "deny", "*.env.*": "deny", "*qrels*": "deny", "*labels*": "deny"},
                        "bash": {"*": "allow", "git push*": "deny", "git reset --hard*": "deny", "rm -rf*": "deny"},
                        "task": "deny", "question": "deny", "webfetch": "deny", "websearch": "deny"}
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps(overrides)
            command = [str(executable), "run", "--pure", "--model", model, "--variant", effort,
                       "--agent", "plan" if args.mode == "plan" else "build", "--format", "json"]
            if args.session:
                command += ["--session", args.session]
            command += [prompt]
        run_dir = ROOT / "data/public_search/control/runs" / str(uuid.uuid4())
        summary = {"worker": args.worker, "requested_model_id": model, "mode": args.mode,
                   "requested_reasoning_effort": effort,
                   "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "status": "RUNNING"}
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            process.kill()
            process.communicate()
            raise ValueError("Worker timeout; turn is not complete")
        # Local ignored diagnostics; never print provider payloads or secrets to the chat.
        (run_dir / "stdout.log").write_bytes(stdout)
        (run_dir / "stderr.log").write_bytes(stderr)
        summary["process_exit_code"] = process.returncode
        if process.returncode != 0:
            raise ValueError("Worker process failed with exit code " + str(process.returncode))
        session, response = parse_response(args.worker, stdout.decode("utf-8"))
        if args.smoke and response.strip() != nonce:
            raise ValueError("Smoke response does not match nonce")
        summary.update(status="PASS", session_id=session, response=response)
        (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "PASS", "session_id": session, "evidence": str(run_dir)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Generic messages intentionally exclude raw config/provider response bodies.
        reason = str(error) if isinstance(error, ValueError) else "Required resource or field unavailable"
        failure = {"status": "FAIL", "error_type": type(error).__name__, "reason": reason}
        if run_dir is not None and summary is not None:
            summary.update(status="FAIL", error_type=type(error).__name__, reason=reason)
            failure["evidence"] = str(run_dir)
            try:
                (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            except OSError as evidence_error:
                failure["evidence_save_error"] = type(evidence_error).__name__
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
