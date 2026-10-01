"""Subprocess CLI boundary tests use only temporary storage/config."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.test_public_service import cfg


PYTHON = r"D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "search_public.py"


def run(tmp_path, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    return subprocess.run([PYTHON, str(SCRIPT), "--project-root", str(tmp_path), "--config", str(cfg(tmp_path)), *args],
                          text=True, capture_output=True, timeout=30, env=env)


def test_cli_init_storage_is_explicit_and_idempotent(tmp_path):
    first = run(tmp_path, "init-storage")
    second = run(tmp_path, "init-storage")
    assert first.returncode == 0 and second.returncode == 0
    assert json.loads(first.stdout)["status"] == "INITIALIZED"
    assert (tmp_path / "data/public_search/service-test/library.sqlite3").is_file()


def test_cli_missing_store_and_invalid_request_exit1(tmp_path):
    missing = run(tmp_path, "search", "--query", "synthetic")
    assert missing.returncode == 1 and missing.stdout == "" and "FAIL" in missing.stderr
    assert "Traceback" not in missing.stderr
    init = run(tmp_path, "init-storage")
    assert init.returncode == 0
    invalid = run(tmp_path, "search", "--request", str(tmp_path / "missing.json"))
    assert invalid.returncode == 1 and "FAIL" not in invalid.stdout


@pytest.mark.parametrize("args", [
    (), ("unknown-command",), ("library", "--offset", "abc"),
    ("library", "--limit", "secret-invalid-integer"),
    ("export", "--format", "xml"), ("export",), ("results",),
    ("search", "--unknown-flag", "secret-flag-value"),
    ("--unknown-global-flag", "secret-global-value", "library"),
])
def test_cli_parser_errors_are_structured_fail_exit1(tmp_path, args):
    result = run(tmp_path, *args)
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.startswith("FAIL: ")
    envelope = json.loads(result.stderr.removeprefix("FAIL: "))
    assert envelope["overall"] == "failed" and envelope["snapshot"] is None
    assert len(envelope["errors"]) == 1 and envelope["errors"][0]["kind"] == "request"
    assert envelope["errors"][0]["message"] == "invalid or missing CLI input"
    assert "Traceback" not in result.stderr and "secret-" not in result.stderr
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("args", [("--help",), ("search", "--help"),
                                  ("library", "--help"), ("export", "--help")])
def test_cli_help_remains_successful(tmp_path, args):
    result = run(tmp_path, *args)
    assert result.returncode == 0 and "usage:" in result.stdout
    assert result.stderr == "" and not (tmp_path / "data").exists()


def test_cli_unexpected_adapter_failure_keeps_partial_results_exit1(tmp_path):
    config = cfg(tmp_path)
    harness = tmp_path / "partial_cli.py"
    harness.write_text(
        "import runpy,sys,time\n"
        "from scholargraph.public_search import service\n"
        "from tests.unit.test_public_service import MemoryStore,source_result_success\n"
        "original=service.PublicSearchService\n"
        "def bad(request,transport):\n"
        "    time.sleep(0.01)\n"
        "    raise RuntimeError('secret-adapter-token')\n"
        "def factory(root,config):\n"
        "    return original(root,config,store=MemoryStore(),adapters={\n"
        "        'openalex':bad,'arxiv':lambda r,t:source_result_success('arxiv')})\n"
        "service.PublicSearchService=factory\n"
        f"sys.argv=[{str(SCRIPT)!r},'--project-root',{str(tmp_path)!r},'--config',{str(config)!r},\n"
        "          'search','--query','synthetic']\n"
        f"runpy.run_path({str(SCRIPT)!r},run_name='__main__')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SCRIPT.parents[1] / "src"), str(SCRIPT.parents[1])])}
    result = subprocess.run([PYTHON, str(harness)], text=True, capture_output=True, timeout=30, env=env)
    assert result.returncode == 1 and result.stderr == ""
    envelope = json.loads(result.stdout)
    assert envelope["overall"] == "partial_failure"
    assert len(envelope["snapshot"]["fusion"]["hits"]) == 1
    assert envelope["snapshot"]["fusion"]["hits"][0]["display"]["source"] == "arxiv"
    failed = next(row for row in envelope["snapshot"]["source_results"] if row["source"] == "openalex")
    assert failed["source"] == "openalex" and failed["status"] == "failed"
    assert failed["elapsed_seconds"] >= 0.01 and failed["error"]["kind"] == "schema"
    assert len(envelope["errors"]) == 1 and "secret-adapter-token" not in result.stdout


def test_cli_corrupt_existing_store_exit1_without_rebuild(tmp_path):
    init = run(tmp_path, "init-storage")
    assert init.returncode == 0
    db = tmp_path / "data/public_search/service-test/library.sqlite3"
    db.write_bytes(b"not sqlite")
    result = run(tmp_path, "search", "--query", "synthetic")
    assert result.returncode == 1
    assert result.stdout == "" and "FAIL" in result.stderr
    assert "Traceback" not in result.stderr
    assert db.read_bytes() == b"not sqlite"


def test_cli_valid_empty_request_reaches_source_without_network(tmp_path):
    init = run(tmp_path, "init-storage")
    assert init.returncode == 0
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"query": "synthetic", "sources": ["openalex"], "top_k": 1,
                                        "cap_per_source": 1, "year_from": None, "year_to": None,
                                        "refresh": False}), encoding="utf-8")
    harness = tmp_path / "empty_cli.py"
    harness.write_text(
        "import runpy,sys\n"
        "from scholargraph.public_search import service\n"
        "from tests.unit.test_public_service import source_result_empty\n"
        "original=service.PublicSearchService\n"
        "def factory(root,config):\n"
        "    return original(root,config,adapters={\n"
        "        'openalex':lambda r,t:source_result_empty('openalex'),\n"
        "        'arxiv':lambda r,t:source_result_empty('arxiv')})\n"
        "service.PublicSearchService=factory\n"
        f"sys.argv=[{str(SCRIPT)!r},'--project-root',{str(tmp_path)!r},'--config',{str(cfg(tmp_path))!r},\n"
        f"          'search','--request',{str(request_file)!r}]\n"
        f"runpy.run_path({str(SCRIPT)!r},run_name='__main__')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SCRIPT.parents[1] / "src"), str(SCRIPT.parents[1])])}
    result = subprocess.run([PYTHON, str(harness)], text=True, capture_output=True, timeout=30, env=env)
    assert result.returncode == 0 and result.stderr == ""
    envelope = json.loads(result.stdout)
    assert envelope["overall"] == "empty" and envelope["errors"] == []
    assert len(envelope["snapshot"]["source_results"]) == 1
    assert envelope["snapshot"]["source_results"][0]["source"] == "openalex"
    assert envelope["snapshot"]["source_results"][0]["status"] == "empty"


def test_cli_json_is_utf8_under_legacy_windows_encoding(tmp_path):
    """Run the real script entry point with a local Unicode envelope, no HTTP."""
    harness = tmp_path / "unicode_cli.py"
    harness.write_text(
        "import runpy,sys,json\n"
        "from scholargraph.public_search import service\n"
        "class Envelope:\n"
        "    errors=[]\n"
        "    def model_dump_json(self): return json.dumps({'title':'Tiếng Việt ü'},ensure_ascii=False)\n"
        "class Service:\n"
        "    def __init__(self,*args): pass\n"
        "    def search(self,request): return Envelope()\n"
        "service.PublicSearchService=Service\n"
        f"sys.argv=[{str(SCRIPT)!r},'search','--query','synthetic']\n"
        f"runpy.run_path({str(SCRIPT)!r},run_name='__main__')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(SCRIPT.parents[1] / "src"), "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run([sys.executable, str(harness)], capture_output=True, timeout=30, env=env)
    assert result.returncode == 0
    assert json.loads(result.stdout.decode("utf-8"))["title"] == "Tiếng Việt ü"
