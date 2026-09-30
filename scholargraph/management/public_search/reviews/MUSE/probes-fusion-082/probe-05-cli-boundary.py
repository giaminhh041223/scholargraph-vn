"""Independent probe 05: CLI boundary via subprocess.
Duplicate JSON / nonfinite / args / missing path / schema / extra labels -> FAIL exit1 redacted.
Valid failed/partial -> exit1 despite hits. Valid empty -> exit0. No production search claim.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchRequest, SourceResult,
    SearchError,
)

SHA = "f" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")

def mkreq(sources=("openalex",)):
    return SearchRequest.model_validate(dict(query="cli probe", sources=list(sources), top_k=50,
                                             cap_per_source=50, year_from=None, year_to=None))

def mkpaper(sid="C1"):
    row = dict(source="openalex", source_id=sid, title="CLI title",
               landing_url="https://example.org/c", retrieved_at=NOW,
               raw_sha256=SHA, parser_version="probe-082")
    for f in NULLABLE:
        row[f] = None
    row["authors_availability"] = "missing"
    row["missing_fields"] = list(NULLABLE)
    row["field_provenance"] = {
        f: [FieldEvidence(source="openalex", source_id=sid, raw_sha256=SHA, raw_field=f)]
        for f in ("source_id", "title", "landing_url")}
    return PaperRecord.model_validate(row)

def mkres(records, status=None):
    if status is None:
        status = "success" if records else "empty"
    return SourceResult(source="openalex", status=status, records=records, error=None,
                        source_total=len(records), elapsed_seconds=0.1,
                        filter_coverage="none", truncated=False,
                        raw_references=[RawReference(raw_id="openalex-"+SHA, sha256=SHA, byte_count=1)] if records else [])

def run_cli(tmp, req_text, res_text, extra=()):
    rq = Path(tmp) / "rq.json"
    rs = Path(tmp) / "rs.json"
    if req_text is not None:
        rq.write_text(req_text, encoding="utf-8")
    if res_text is not None:
        rs.write_text(res_text, encoding="utf-8")
    env = dict(os.environ)
    return subprocess.run([sys.executable, "-m", "scholargraph.public_search.fusion",
                           "--request", str(rq), "--source-results", str(rs), *extra],
                          capture_output=True, text=True, timeout=20, env=env)

def main():
    tmp = tempfile.mkdtemp(prefix="probe05-082-")
    print(f"tmp={tmp}")
    req_json = mkreq().model_dump_json()
    ok_json = "[" + mkres([mkpaper()]).model_dump_json() + "]"
    # valid success -> 0
    r = run_cli(tmp, req_json, ok_json)
    print(f"valid-success exit={r.returncode} stdout_len={len(r.stdout)} stderr={r.stderr!r}")
    assert r.returncode == 0, r.stderr
    # valid empty -> 0
    r = run_cli(tmp, req_json, "[" + mkres([]).model_dump_json() + "]")
    print(f"valid-empty exit={r.returncode}")
    assert r.returncode == 0
    # valid failed source -> exit1 WITH hits available
    failed = SourceResult(source="openalex", status="failed", records=[], error=SearchError(
        kind="timeout", message="probe timeout", source="openalex",
        retry_after_seconds=None, record_index=None),
        source_total=None, elapsed_seconds=0.2, filter_coverage="none", truncated=None, raw_references=[])
    r = run_cli(tmp, req_json, "[" + failed.model_dump_json() + "]")
    print(f"valid-failed exit={r.returncode} stdout={r.stdout[:200]!r} stderr={r.stderr!r}")
    assert r.returncode == 1 and r.stderr.startswith("FAIL:")
    # partial (need 2-source request)
    req2 = SearchRequest.model_validate(dict(query="cli probe", sources=["arxiv", "openalex"], top_k=50, cap_per_source=50, year_from=None, year_to=None))
    ok_oa = SourceResult(source="openalex", status="success", records=[mkpaper()], error=None,
                         source_total=1, elapsed_seconds=0.1, filter_coverage="none", truncated=False,
                         raw_references=[RawReference(raw_id="openalex-"+SHA, sha256=SHA, byte_count=1)])
    fail_ax = SourceResult(source="arxiv", status="failed", records=[], error=SearchError(
        kind="timeout", message="probe timeout", source="arxiv", retry_after_seconds=None, record_index=None),
        source_total=None, elapsed_seconds=0.2, filter_coverage="none", truncated=None, raw_references=[])
    r = run_cli(tmp, req2.model_dump_json(), "[" + ok_oa.model_dump_json() + "," + fail_ax.model_dump_json() + "]")
    out = json.loads(r.stdout)
    print(f"partial exit={r.returncode} returned={out['counts']['returned']} stderr={r.stderr!r}")
    assert r.returncode == 1 and out["counts"]["returned"] == 1
    # adversarial: each must exit1, redacted, no traceback
    rows = json.loads("[" + mkres([mkpaper()]).model_dump_json() + "]")
    cases = {}
    cases["missing_request"] = (None, json.dumps(rows), ())
    cases["missing_results"] = (req_json, None, ())
    cases["syntax"] = ('{"query":', json.dumps(rows), ())
    cases["duplicate"] = (req_json[:-1] + ',"query":"SENTINEL_CLI"', json.dumps(rows), ())
    cases["nonfinite"] = (req_json.replace('"top_k":50', '"top_k":NaN'), json.dumps(rows), ())
    import copy as _copy
    r2 = _copy.deepcopy(rows); del r2[0]["records"][0]["title"]
    cases["missing_title"] = (req_json, json.dumps(r2), ())
    rr = _copy.deepcopy(rows); del rr[0]["records"][0]["title"]; rr[0]["records"][0]["abstract"] = "SENTINEL_CLI"
    cases["text_only"] = (req_json, json.dumps(rr), ())
    rb = json.loads(json.dumps(rows)); rb[0]["records"][0]["publication_year"] = True
    cases["bad_year"] = (req_json, json.dumps(rb), ())
    rl = json.loads(json.dumps(rows)); rl[0]["records"][0]["labels"] = "SENTINEL_CLI"
    cases["extra_labels"] = (req_json, json.dumps(rl), ())
    cases["missing_source"] = (req_json, "[]", ())
    cases["args"] = (req_json, json.dumps(rows), ("--unknown", "SENTINEL_CLI"))
    cases["wrong_root"] = (req_json, "{}", ())
    for name, (q, s, ex) in cases.items():
        run = run_cli(tmp + "-" + name.replace("_", ""), q, s, ex) if False else None
        # use same tmp but distinct filenames via direct subprocess with temp files
        import tempfile as tf
        d = tf.mkdtemp(prefix="p05-" + name + "-")
        rq = Path(d) / "rq.json"; rs = Path(d) / "rs.json"
        if q is not None:
            rq.write_text(q, encoding="utf-8")
        if s is not None:
            rs.write_text(s, encoding="utf-8")
        env = dict(os.environ)
        run = subprocess.run([sys.executable, "-m", "scholargraph.public_search.fusion",
                              "--request", str(rq), "--source-results", str(rs), *ex],
                             capture_output=True, text=True, timeout=20, env=env)
        redacted = ("SENTINEL_CLI" not in run.stdout + run.stderr)
        notrace = ("Traceback" not in run.stderr)
        print(f"{name} exit={run.returncode} redacted={redacted} notrace={notrace} stderr={run.stderr[:80]!r}")
        assert run.returncode == 1, f"{name} exit {run.returncode}"
        assert run.stderr.startswith("FAIL:"), f"{name} stderr {run.stderr!r}"
        assert redacted and notrace, f"{name} leak/traceback"
    # no-args -> exit1
    run = subprocess.run([sys.executable, "-m", "scholargraph.public_search.fusion"],
                         capture_output=True, text=True, timeout=20)
    print(f"no-args exit={run.returncode} stderr={run.stderr!r}")
    assert run.returncode == 1 and run.stderr.startswith("FAIL:")
    print("PROBE05 PASS")

if __name__ == "__main__":
    main()
