"""UI smoke check (SG-036): end-to-end through the real API + templates.

Loads /, runs a search, opens the top paper, lists recommendations, and checks
loading/error/no-result states via HTTP (no browser needed). Writes
artifacts/reports/ui_smoke.md. Exit 1 on any failure.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from scholargraph.api.app import app


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        client = TestClient(app, raise_server_exceptions=False)
        checks: list[str] = []
        r = client.get("/")
        if r.status_code != 200 or "ScholarGraph VN" not in r.text or "/static/app.js" not in r.text:
            return fail("index page missing markers")
        checks.append("index 200 with app.js marker")
        r = client.get("/static/app.js")
        if r.status_code != 200 or "fetch" not in r.text:
            return fail("static app.js not served")
        checks.append("static js served offline (no CDN references: "
                      + str("http" not in r.text.replace("http://localhost", "")))
        if "https://" in r.text or 'src="http' in r.text:
            return fail("external CDN reference in UI")
        for method in ("bm25", "dense", "hybrid"):
            s = client.get("/search", params={"q": "diabetes treatment", "method": method, "top_k": 5})
            if s.status_code != 200 or len(s.json()["results"]) != 5:
                return fail(f"search {method} failed")
            checks.append(f"search {method} 5 results")
        top = client.get("/search", params={"q": "diabetes", "top_k": 1}).json()["results"][0]
        p = client.get(f"/paper/{top['doc_id']}")
        if p.status_code != 200 or p.json()["doc_id"] != top["doc_id"]:
            return fail("paper detail failed")
        checks.append(f"detail {top['doc_id']}")
        rel = client.get(f"/recommend/{top['doc_id']}", params={"top_k": 5})
        if rel.status_code != 200 or len(rel.json()["results"]) != 5:
            return fail("recommend failed")
        checks.append("related 5 results")
        empty = client.get("/search", params={"q": "zxqvkjwx", "method": "bm25", "top_k": 5})
        if len(empty.json().get("results", [])) != 0:
            return fail("no-results path returned rows")
        checks.append(f"no-results path status={empty.status_code} n=0")
        bad = client.get("/search", params={"q": "   ", "method": "bm25"})
        if bad.status_code not in (400, 422):
            return fail("error state not surfaced")
        checks.append("error state surfaced")
        missing_js = "không có" in (ROOT / "ui" / "templates" / "search.html").read_text(encoding="utf-8")
        if not missing_js:
            return fail("missing-metadata wording absent")
        checks.append("missing-metadata wording present=True")
        out = ROOT / "artifacts" / "reports" / "ui_smoke.md"
        out.write_text("# UI smoke (SG-036)\n\n- Generated: "
                       + datetime.now(timezone.utc).isoformat()
                       + "\n- Backend: real API (TestClient, no mocks)\n\n"
                       + "".join(f"- {c}\n" for c in checks), encoding="utf-8")
        print("\n".join(checks))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
