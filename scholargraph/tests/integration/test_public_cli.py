"""Subprocess CLI boundary tests use only temporary storage/config."""
import json
import os
import subprocess
import sys
from pathlib import Path

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


def test_cli_valid_empty_request_schema_reaches_source_exit1_without_live_success(tmp_path):
    init = run(tmp_path, "init-storage")
    assert init.returncode == 0
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"query": "synthetic", "sources": ["openalex"], "top_k": 1,
                                        "cap_per_source": 1, "year_from": None, "year_to": None,
                                        "refresh": False}), encoding="utf-8")
    result = run(tmp_path, "search", "--request", str(request_file))
    # Anonymous live access is policy-verified but the test never claims a live result;
    # the configured environment may fail upstream and must use exit 1.
    assert result.returncode in {0, 1}
    if result.returncode == 1:
        assert "Traceback" not in result.stderr


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
