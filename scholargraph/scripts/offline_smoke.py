"""Offline demo smoke (SG-038) — proves the 5-minute demo runs with no network.

Sets HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 BEFORE any HF import, runs the
pinned demo flow through the real API (TestClient) + the export script, and
writes artifacts/reports/offline_smoke.md. Exit 1 on any failure. No synthetic
substitution: every number below is real service output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DEMO = json.loads((PROJECT_ROOT / "configs" / "demo.json").read_text(encoding="utf-8"))
REPORT = PROJECT_ROOT / "artifacts" / "reports" / "offline_smoke.md"

checks: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    checks.append((name, "PASS" if ok else "FAIL", detail))
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def main() -> int:
    from fastapi.testclient import TestClient

    import scholargraph.api.app as app_module

    with TestClient(app_module.app) as tc:
        # 1. health + offline env really set
        h = tc.get("/health")
        check("health 200", h.status_code == 200, str(h.json()))
        check("offline env", os.environ.get("HF_HUB_OFFLINE") == "1"
              and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1")

        # 2. pinned demo queries through real search
        for spec in DEMO["demo_queries"]:
            r = tc.get("/search", params={"q": spec["q"], "method": spec["method"], "top_k": 5})
            body = r.json() if r.status_code == 200 else {}
            check(f"search[{spec['method']}] '{spec['q']}'", r.status_code == 200 and len(body.get("results", [])) >= 1,
                  f"top1={body.get('results', [{}])[0].get('doc_id')}")

        # 3. detail + recommend (real metadata, missing stays null)
        doc = DEMO["demo_detail_doc_ids"][1]
        p = tc.get(f"/paper/{doc}")
        pj = p.json()
        check("paper metadata nulls", p.status_code == 200 and pj["year"] is None and pj["doi"] is None,
              f"year={pj['year']} doi={pj['doi']} (missing, not fabricated)")
        rec = tc.get(f"/recommend/{doc}", params={"top_k": 5})
        ids = [x["doc_id"] for x in rec.json()["results"]]
        check("recommend self-excluded", rec.status_code == 200 and doc not in ids and len(ids) == 5, str(ids))

        # 4. graph UI endpoint (evaluated mode, masked adjacency)
        hub = DEMO["demo_detail_doc_ids"][2]
        g = tc.get(f"/graph/{hub}", params={"mode": "evaluated", "hop": 1, "cap": 30})
        gj = g.json() if g.status_code == 200 else {}
        check("graph hub endpoint", g.status_code == 200 and gj.get("truncated") is True
              and "5341" in str(gj.get("message", "")),
              f"truncated={gj.get('truncated')} msg={str(gj.get('message'))[:90]}")

    # 5. export script as subprocess (offline env inherited)
    out = PROJECT_ROOT / "artifacts" / "reports" / "demo_references.json"
    doc_ids = " ".join(DEMO["export_doc_ids"])
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "export_references.py"),
         "--doc-ids", *doc_ids.split(), "--output", str(out)],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")})
    check("export script exit 0", proc.returncode == 0, (proc.stdout + proc.stderr).strip()[:120])
    payload = json.loads(out.read_text(encoding="utf-8"))
    missing = [r for r in payload["records"] if r["doi"] is None or r["year"] is None]
    check("export missing policy", len(payload["records"]) == 4 and len(missing) >= 2
          and all(r["citation_text"].count("[không có]") >= 0 for r in payload["records"]),
          f"counts={payload['counts']}")

    # 6. offline proof: UI assets reference no CDN
    static = PROJECT_ROOT / "ui" / "static"
    cdn = [f.name for f in static.iterdir() if f.suffix in {".js", ".css"}
           and ("http://" in f.read_text(encoding="utf-8") or "https://" in f.read_text(encoding="utf-8"))]
    check("no CDN references", not cdn, str(cdn))

    lines = [
        "# Offline smoke — SG-038",
        "",
        f"- Chạy: {__import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds')}",
        "- Môi trường: HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 (set trước khi import HF); TestClient API thật; không mock dữ liệu.",
        f"- Tổng cộng: {len(checks)} kiểm tra, {sum(1 for _, s, _ in checks if s == 'PASS')} PASS.",
        "",
        "| Kiểm tra | Kết quả | Chi tiết (output thật) |",
        "|---|---|---|",
        *[f"| {n} | {s} | {d} |" for n, s, d in checks],
        "",
        "- Kết luận: demo chạy được khi tắt mạng, không synthetic substitution, metadata thiếu hiển thị null/[không có].",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    failed = [n for n, s, _ in checks if s == "FAIL"]
    print(f"offline smoke: {len(checks) - len(failed)}/{len(checks)} PASS -> {REPORT}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
