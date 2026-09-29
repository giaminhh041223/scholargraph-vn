"""Cross-module integration checks — task SG-039 (all flows on real data).

Flows (no mocks, no synthetic substitution):
 1. ingest manifests pinned (BEIR/OpenAlex/graph) + sha verification,
 2. indexes loadable (dense scifact + BM25 corpus),
 3. search/paper/recommend/graph/UI end-to-end via TestClient,
 4. IDs/self/duplicates/filters/cache integrity (cache = deterministic repeat),
 5. missing model/index/graph failure paths (fail-loud),
 6. Vietnamese queries return honest structure (no relevance claim).

Writes artifacts/reports/integration_checks.md. Exit 1 on any failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RESULTS: list[tuple[str, bool, str]] = []
REPORT_NAME = "artifacts/reports/integration_checks.md"


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))


def write_report(results: list[tuple[str, bool, str]], out: Path) -> int:
    """Persist results; returns 1 when any check failed (pure, unit-tested)."""
    fails = [n for n, ok, _ in results if not ok]
    out.write_text("# Integration checks (SG-039)\n\n- Generated: "
                   + datetime.now(timezone.utc).isoformat()
                   + f"\n- Result: {len(results) - len(fails)}/{len(results)} PASS\n\n"
                   + "".join(f"- [{'x' if ok else '!'}] {n}" + (f" — {d}" if d else "") + "\n"
                             for n, ok, d in results), encoding="utf-8")
    return 1 if fails else 0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    try:
        from fastapi.testclient import TestClient
        from scholargraph.api.app import app
        from scholargraph.ingest.beir_loader import sha256_file
        from scholargraph.retrieval.bm25 import load_corpus
        from scholargraph.retrieval.dense import ExactDenseIndex

        # 1. ingest manifests + pins (all assertions must be able to fail)
        m_beir = json.loads((ROOT / "data" / "manifests" / "beir_scifact.json").read_text(encoding="utf-8"))
        check("manifest beir_scifact", m_beir.get("counts", {}).get("corpus") == 5183
              and m_beir.get("counts", {}).get("splits", {}).get("train", {}).get("queries") == 809,
              f"corpus={m_beir.get('counts', {}).get('corpus')}")
        mom = json.loads((ROOT / "data" / "manifests" / "openalex_core.json").read_text(encoding="utf-8"))
        check("manifest openalex_core", mom.get("status") == "COMPLETED"
              and mom.get("postprocess", {}).get("processed_works") == 18251, mom.get("status"))
        gm = json.loads((ROOT / "data" / "manifests" / "graph_core.json").read_text(encoding="utf-8"))
        check("manifest graph_core", gm.get("status") == "COMPLETED"
              and gm.get("counts", {}).get("internal_directed_edges_postmask") == 26186,
              f"status={gm.get('status')}")
        art = mom["artifacts"]["works_jsonl"]
        check("openalex snapshot sha", sha256(ROOT / art["path"]) == art["sha256"], art["sha256"][:16])
        check("graph audit artifact pinned", (gm.get("audit") or {}).get("status") == "PASS",
              f"audit={((gm.get('audit') or {}).get('status'))}")

        # 2. indexes loadable
        idx = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / "scifact" / "bge-base-en-v1.5__a5beb1e3")
        check("dense scifact index", idx.matrix.shape == (5183, 768), str(idx.matrix.shape))
        corpus = load_corpus(ROOT / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl", dataset="scifact")
        check("bm25 corpus", corpus.document_count == 5183, str(corpus.document_count))

        # 3. end-to-end API
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/health")
        check("GET /health", r.status_code == 200 and r.json()["docs"] == 5183, str(r.status_code))
        methods_ok = True
        dup_in_results = False
        for method in ("bm25", "dense", "hybrid"):
            s = client.get("/search", params={"q": "diabetes treatment", "method": method, "top_k": 5})
            if s.status_code != 200 or len(s.json()["results"]) != 5:
                methods_ok = False
            else:
                ids = [x["doc_id"] for x in s.json()["results"]]
                if len(set(ids)) != len(ids):
                    dup_in_results = True
        check("search x3 methods", methods_ok, "")
        check("no duplicates in results", methods_ok and not dup_in_results, "")
        top = client.get("/search", params={"q": "diabetes", "top_k": 1}).json()["results"][0]["doc_id"]
        check("paper detail", client.get(f"/paper/{top}").status_code == 200, top)
        rel = client.get(f"/recommend/{top}", params={"top_k": 5}).json()["results"]
        check("recommend 5 excl self", len(rel) == 5 and top not in [x["doc_id"] for x in rel], "")
        check("UI /", "ScholarGraph VN" in client.get("/").text, "")
        gh = client.get("/graph/openalex:W1678356000", params={"cap": 5})
        gbody = gh.json() if gh.status_code == 200 else {}
        gcounts = gbody.get("counts") or {}
        check("graph hub endpoint", gh.status_code == 200
              and gcounts.get("neighbor_nodes_total") == 5341
              and gcounts.get("neighbor_nodes_returned") == 5,
              f"status={gh.status_code} counts={gcounts}")

        # 4. IDs/self/duplicates/filters/cache
        import numpy as np
        ids = list(idx.doc_ids)
        check("doc_ids unique+sorted", len(set(ids)) == len(ids) and ids == sorted(ids), str(len(ids)))
        norms = np.linalg.norm(np.asarray(idx.matrix, dtype=np.float32), axis=1)
        check("embeddings L2", bool((np.abs(norms - 1.0) < 1e-3).all()), f"min={float(norms.min()):.5f}")
        f = client.get("/search", params={"q": "diabetes", "method": "bm25", "top_k": 10,
                                          "title_must_contain": "diabetes"})
        check("title filter", f.status_code == 200 and all(
            "diabetes" in (x.get("title") or "").casefold() for x in f.json()["results"]), "")
        r1 = client.get("/search", params={"q": "diabetes treatment", "method": "hybrid", "top_k": 5}).json()["results"]
        r2 = client.get("/search", params={"q": "diabetes treatment", "method": "hybrid", "top_k": 5}).json()["results"]
        check("deterministic repeat query", r1 == r2, "identical rows on rerun")
        check("index checksum re-verify", sha256(ROOT / "artifacts" / "indexes" / "scifact"
              / "bge-base-en-v1.5__a5beb1e3" / "embeddings.npy") == idx.manifest["artifacts"]["embeddings"]["sha256"], "")
        check("unknown doc 404", client.get("/paper/beir:scifact:0").status_code == 404, "")
        check("bad top_k 400", client.get("/search", params={"q": "x", "top_k": 500}).status_code == 400, "")

        # 5. missing paths fail loud (index + model + graph-data + export)
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        p1 = subprocess.run([sys.executable, "-m", "scholargraph.retrieval.dense",
                             "verify", "--corpus", "nope"], capture_output=True, text=True,
                            cwd=ROOT, env=env)
        check("missing index nonzero exit", p1.returncode != 0, f"exit={p1.returncode}")
        from scholargraph.retrieval.dense import ExactDenseIndex as _EDI
        try:
            _EDI.load(ROOT / "artifacts" / "indexes" / "does_not_exist")
            check("missing model raises", False, "no exception")
        except Exception as exc:
            check("missing model raises", True, type(exc).__name__)
        check("missing graph doc 404",
              client.get("/graph/openalex:W0000000000").status_code == 404, "")
        p2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_references.py"),
                             "--doc-ids", "beir:scifact:nope", "--output",
                             str(ROOT / "artifacts" / "reports" / "tmp_bad_export.json")],
                            capture_output=True, text=True, cwd=ROOT, env=env)
        check("export unknown doc nonzero exit", p2.returncode != 0, f"exit={p2.returncode}")

        # export flow on real demo IDs (P1-1)
        demo = json.loads((ROOT / "configs" / "demo.json").read_text(encoding="utf-8"))
        exp_out = ROOT / "artifacts" / "reports" / "integration_export.json"
        p3 = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_references.py"),
                             "--doc-ids", *demo["export_doc_ids"], "--output", str(exp_out)],
                            capture_output=True, text=True, cwd=ROOT, env=env)
        exp_ok = p3.returncode == 0 and exp_out.is_file()
        if exp_ok:
            payload = json.loads(exp_out.read_text(encoding="utf-8"))
            exp_ok = payload.get("counts", {}).get("exported") == 4
        check("export flow 4 demo IDs", exp_ok, f"exit={p3.returncode}")

        # 6. Vietnamese queries: honest structure, no relevance claim
        vn = json.loads((ROOT / "data" / "annotations" / "vn_query_manifest.json").read_text(encoding="utf-8"))
        for split_name in ("dev", "test"):
            q = next(x for x in vn["queries"] if x.get("split") == split_name)
            text = q.get("text_vi", q.get("text", q.get("query", "")))
            ok = bool(text)
            if ok:
                s = client.get("/search", params={"q": text, "method": "bm25", "top_k": 3})
                ok = s.status_code == 200 and "results" in s.json()
            check(f"vn {split_name} query honest 200", ok,
                  f"{q.get('query_id')} (structure only, no relevance claim)")
    except Exception as exc:  # noqa: BLE001 - top boundary
        import traceback
        traceback.print_exc()
        check("unexpected exception", False, f"{type(exc).__name__}: {exc}")

    fails = [n for n, ok, _ in RESULTS if not ok]
    out = ROOT / REPORT_NAME
    code = write_report(RESULTS, out)
    print(f"integration: {len(RESULTS) - len(fails)}/{len(RESULTS)} -> {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
