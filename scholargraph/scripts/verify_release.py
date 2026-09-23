"""Release verification for a fresh checkout (SG-041).

Checks, fail-loud (exit 1) with the first gap reported:
  1. Python version matches the locked runtime.
  2. Required third-party packages import with compatible versions.
  3. Every file pinned in configs/frozen_main.json exists with matching SHA-256
     (data / splits / graph / models / configs / dense indexes / VN cache).
  4. Model snapshots for the pinned revisions are present locally.
  5. Notebooks, CLI entry points (importable), demo config and docs exist.
  6. --write-manifest regenerates docs/RELEASE_MANIFEST.md from live evidence
     (hashes recomputed, never copied).

Usage: verify_release.py [--write-manifest PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TASK_ID = "SG-041"
MODULE_VERSION = "sg041-1.0.0"
REQUIRED_PYTHON = (3, 12)
REQUIRED_PACKAGES = {
    "pydantic": "2.0.0", "fastapi": "0.110.0", "uvicorn": "0.28.0",
    "jinja2": "3.1.0", "networkx": "3.0", "numpy": "1.26.0",
    "scipy": "1.12.0", "httpx": "0.27.0", "tqdm": "4.66.0",
    "torch": None, "transformers": None, "pytest": "8.0.0",
}
CLI_MODULES = [
    "scholargraph.retrieval.bm25", "scholargraph.retrieval.tfidf",
    "scholargraph.retrieval.hybrid", "scholargraph.retrieval.dense",
    "scholargraph.retrieval.cross_lingual", "scholargraph.evaluation.metrics",
    "scholargraph.evaluation.runner", "scholargraph.api.app",
]
MODEL_SNAPSHOTS = [
    ("BAAI/bge-base-en-v1.5", "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"),
    ("intfloat/multilingual-e5-base", "d128750597153bb5987e10b1c3493a34e5a4502a"),
    ("Helsinki-NLP/opus-mt-vi-en", "c8d2853e77f5fae31124d993e0b35176b1c8914e"),
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", None),
]
STATIC_PATHS = [
    "requirements.lock", "configs/protocol_v1.json", "configs/frozen_main.json",
    "notebooks/compute_smoke.ipynb", "notebooks/encode_corpus.ipynb",
    "configs/demo.json", "docs/DEMO_SCRIPT.md", "docs/ENVIRONMENT.md",
    "scripts/offline_smoke.py", "scripts/export_references.py",
    "scripts/integration_checks.py", "scripts/run_demo.ps1",
]


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _version_at_least(have: str, minimum: str) -> bool:
    def parts(s: str) -> list[int]:
        return [int(p) for p in str(s).split("+")[0].split(".")[:3] if p.isdigit()]
    a, b = parts(have), parts(minimum)
    length = max(len(a), len(b))
    return (a + [0] * (length - len(a))) >= (b + [0] * (length - len(b)))


def check_python() -> dict:
    if sys.version_info[:2] != REQUIRED_PYTHON:
        raise RuntimeError(
            f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} required, "
            f"running {sys.version.split()[0]}")
    return {"python": sys.version.split()[0], "executable": sys.executable}


def check_packages() -> dict:
    found: dict[str, str] = {}
    for name, minimum in REQUIRED_PACKAGES.items():
        try:
            mod = importlib.import_module(name)
        except ImportError:
            raise RuntimeError(f"Missing required package: {name}")
        ver = getattr(mod, "__version__", "unknown")
        if minimum is not None and ver != "unknown" and not _version_at_least(ver, minimum):
            raise RuntimeError(f"Package {name}=={ver} below minimum {minimum}")
        found[name] = ver
    return found


def check_freeze() -> dict:
    fpath = ROOT / "configs" / "frozen_main.json"
    freeze = json.loads(fpath.read_text(encoding="utf-8"))
    checked = 0

    def _one(rel: str, want: str) -> None:
        nonlocal checked
        p = ROOT / rel
        if not p.is_file():
            raise RuntimeError(f"Frozen file absent: {rel}")
        if hashlib.sha256(p.read_bytes()).hexdigest() != want:
            raise RuntimeError(f"Frozen file drift: {rel}")
        checked += 1

    for group in ("scifact", "scidocs", "openalex"):
        for rel, want in freeze["data"][group].items():
            _one(rel, want)
    for rel, want in {**freeze["splits"], **freeze["graph"]}.items():
        _one(rel, want)
    for rel, want in {**freeze["models"], **freeze["configs"]}.items():
        _one(rel, want)
    index_paths = {
        "scifact_bge": "artifacts/indexes/scifact/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
        "scidocs_bge": "artifacts/indexes/scidocs/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
        "openalex_bge": "artifacts/indexes/openalex_core_text/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
        "scifact_e5_multilingual": "artifacts/indexes/multilingual/intfloat-multilingual-e5-base__d1287505/embeddings.npy",
        "openalex_e5_multilingual": "artifacts/indexes/multilingual/e5_openalex_core_text/embeddings.npy",
    }
    for label, want in freeze["dense_index_pins"].items():
        _one(index_paths[label], want)
    cache = ROOT / "data/processed/vn/translations_cache.json"
    if hashlib.sha256(cache.read_bytes()).hexdigest() != freeze["translation_pin"]["cache_sha256"]:
        raise RuntimeError("translations_cache.json drift")
    checked += 1
    return {"files_checked": checked, "freeze_sha256": hashlib.sha256(fpath.read_bytes()).hexdigest()}


def _snapshot_candidates(model_id: str) -> list[Path]:
    roots = [ROOT / "artifacts" / "cache" / "huggingface" / "hub",
             ROOT / "artifacts" / "cache",
             Path.home() / ".cache" / "huggingface" / "hub"]
    slug = "models--" + model_id.replace("/", "--")
    out: list[Path] = []
    for base in roots:
        if (base / slug).is_dir():
            out.append(base / slug)
    return out


def check_models() -> dict:
    found: dict[str, dict] = {}
    for model_id, revision in MODEL_SNAPSHOTS:
        cands = _snapshot_candidates(model_id)
        if not cands:
            if revision is None:
                found[model_id] = {"present": False, "note": "fallback model; fetch on demand"}
                continue
            raise RuntimeError(f"Model snapshot absent locally: {model_id}")
        rev_ok = None if revision is None else any(
            (c / "snapshots" / revision).is_dir() for c in cands)
        if revision is not None and not rev_ok:
            raise RuntimeError(f"Pinned revision absent for {model_id}@{revision[:8]}")
        found[model_id] = {"present": True, "locations": [str(c) for c in cands],
                           "revision_ok": rev_ok}
    return found


def check_statics() -> dict:
    missing = [rel for rel in STATIC_PATHS if not (ROOT / rel).is_file()]
    if missing:
        raise RuntimeError(f"Missing release files: {missing}")
    mods: dict[str, bool] = {}
    for name in CLI_MODULES:
        try:
            importlib.import_module(name)
            mods[name] = True
        except Exception as exc:
            raise RuntimeError(f"CLI module not importable: {name} ({type(exc).__name__})")
    return {"static_files": len(STATIC_PATHS), "cli_modules": mods}


def git_head() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, cwd=ROOT, timeout=30)
        head = out.stdout.strip()
        return head if len(head) == 40 else None
    except Exception:
        return None


def run_all() -> dict:
    report = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
              "generated_at": datetime.now(timezone.utc).isoformat()}
    report["python"] = check_python()
    report["packages"] = check_packages()
    report["freeze"] = check_freeze()
    report["models"] = check_models()
    report["statics"] = check_statics()
    report["git_head"] = git_head()
    report["status"] = "PASS"
    return report


def write_manifest(report: dict, path: Path) -> None:
    freeze = json.loads((ROOT / "configs" / "frozen_main.json").read_text(encoding="utf-8"))
    lines = ["# RELEASE MANIFEST (SG-041) — generated, do not hand-edit", "",
             f"Generated: {report['generated_at']} by verify_release.py "
             f"({MODULE_VERSION}). Re-run to regenerate.",
             f"Git HEAD: `{report['git_head']}`. Python: `{report['python']['python']}`.",
             f"Freeze: `configs/frozen_main.json` sha256 `{report['freeze']['freeze_sha256']}` "
             f"({report['freeze']['files_checked']} files re-hashed live).",
             "",
             "## Environment lock",
             "",
             "Full pin: `requirements.lock` (generated by `pip freeze` in the tested venv).",
             "Key versions measured in this checkout:",
             ""]
    for name in ("torch", "transformers", "numpy", "scipy", "fastapi", "uvicorn",
                 "pydantic", "pytest", "pytrec_eval-terrier"):
        if name in report["packages"]:
            lines.append(f"- {name}=={report['packages'][name]}")
    lines += ["",
              "## Data and model provenance (all hashes live-verified above)",
              "",
              "- Raw BEIR snapshots: SciFact + SCIDOCS (hashes in frozen_main.json §data).",
              "- OpenAlex core snapshot 18.251 works + text-subset 18.250 (1 textless excluded, ADR-017).",
              "- Splits: SciFact dev 809/test 300, SCIDOCS test 1000, graph split (masked 26.186).",
              "- Models: bge-base-en-v1.5@a5beb1e3, multilingual-e5-base@d1287505, "
              "opus-mt-vi-en@c8d2853e (snapshots verified present).",
              "- Evaluator: sg008-1.0.0 (trec_eval cross-checked, max err 1.67e-16).",
              "",
              "## Notebooks",
              "",
              "- notebooks/compute_smoke.ipynb (SG-002 CPU + Colab T4 pilot).",
              "- notebooks/encode_corpus.ipynb (SG-019 shard encode recipe).",
              "",
              "## Reproduce",
              "",
              "See docs/REPRODUCE.md for fresh-environment instructions and run_demo.ps1 "
              "for the 5-minute offline demo.",
              ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify release readiness (SG-041)")
    ap.add_argument("--write-manifest", default=None)
    args = ap.parse_args(argv)
    try:
        report = run_all()
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        return fail(f"{type(exc).__name__}: {exc}")
    print(json.dumps({"status": report["status"],
                      "freeze_files": report["freeze"]["files_checked"],
                      "git_head": (report["git_head"] or "")[:12]}, indent=2))
    if args.write_manifest:
        try:
            write_manifest(report, ROOT / args.write_manifest)
            print(f"manifest -> {args.write_manifest}")
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
