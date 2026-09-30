#!/usr/bin/env python3
"""Validator for EXT-01B source audit (MUSE, W0 R2).
Checks: audit hash <-> meta <-> MANIFEST <-> bytes; DOI full-payload;
retry provenance author-reported/unverified; observed first-page vs docs-only;
narrative-counter consistency; forbidden Bearer/keyed-probe/account gates.
FAIL prints to stderr and exits 1. No silent fallback.
"""
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"PASS: {msg}")


def require(d, key, ctx):
    if not isinstance(d, dict):
        fail(f"{ctx}: expected object, got {type(d).__name__}")
    if key not in d:
        fail(f"{ctx}: missing required key '{key}'")
    return d[key]
def parse_int_strict(value, ctx):
    # Strict integer parsing for required counters. FAIL with context on bad input. No silent fallback.
    if isinstance(value, bool):
        fail(f"{ctx}: must be integer, got bool {value!r} (F4)")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            fail(f"{ctx}: must be integer, got empty string (F4)")
        if not re.fullmatch(r"[+-]?\d+", s):
            fail(f"{ctx}: must be integer, got {value!r} (F4)")
        try:
            return int(s)
        except SystemExit:
            raise
        except Exception as e:
            fail(f"{ctx}: must be integer, got {value!r}: {e} (F4)")
    fail(f"{ctx}: must be integer, got {type(value).__name__} {value!r} (F4)")



def load_json_no_dup(path):
    p = Path(path)
    if not p.is_file():
        fail(f"missing resource: {path}")
    try:
        raw = p.read_bytes()
    except Exception as e:
        fail(f"cannot read {path}: {e}")
    try:
        text = raw.decode("utf-8")
    except Exception as e:
        fail(f"malformed (not utf-8) {path}: {e}")

    def hook(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                fail(f"malformed duplicate key '{k}' in {path}")
            d[k] = v
        return d

    try:
        return json.loads(text, object_pairs_hook=hook), text
    except SystemExit:
        raise
    except Exception as e:
        fail(f"malformed JSON {path}: {e}")


def sha256_file(path):
    p = Path(path)
    if not p.is_file():
        fail(f"missing resource: {path}")
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception as e:
        fail(f"cannot hash {path}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--pilot-dir", required=True)
    ap.add_argument("--narrative", required=True)
    a = ap.parse_args()

    audit_path = Path(a.audit)
    manif_path = Path(a.manifest)
    pilot = Path(a.pilot_dir)
    narr_path = Path(a.narrative)

    if not audit_path.is_file():
        fail(f"missing resource: audit {a.audit}")
    if not manif_path.is_file():
        fail(f"missing resource: manifest {a.manifest}")
    if not pilot.is_dir():
        fail(f"missing resource: pilot-dir {a.pilot_dir}")
    if not narr_path.is_file():
        fail(f"missing resource: narrative {a.narrative}")

    audit, audit_text = load_json_no_dup(str(audit_path))
    manif, _ = load_json_no_dup(str(manif_path))
    try:
        narr_text = narr_path.read_text(encoding="utf-8")
    except Exception as e:
        fail(f"malformed narrative {a.narrative}: {e}")

    # --- F2 forbidden gates (both files) ---
    combined = (audit_text + "\n" + narr_text).lower()
    if "bearer" in combined:
        fail("forbidden claim/gate: 'Bearer' must not appear (F2)")
    if "keyed probe" in combined:
        fail("forbidden gate: 'keyed probe' must not appear (F2)")
    if "user-created" in combined or "user created" in combined:
        fail("forbidden gate: 'user-created' account requirement must not appear (F2)")

    # required markers F2/F3
    if "author-reported/unverified" not in audit_text:
        fail("audit JSON must mark retry wait/headers/timing as author-reported/unverified (F2/F3)")
    if "author-reported/unverified" not in narr_text:
        fail("narrative must mark retry wait/headers/timing as author-reported/unverified (F2/F3)")
    if "sustained" not in audit_text.lower() or "not measured" not in audit_text.lower():
        fail("audit JSON must state sustained quota/runtime not measured (F2)")
    if "sustained" not in narr_text.lower() or "not measured" not in narr_text.lower():
        fail("narrative must state sustained quota/runtime not measured (F2)")
    if "observed first-page" not in narr_text.lower():
        fail("narrative must distinguish observed first-page (F3)")
    if "docs-only" not in narr_text.lower():
        fail("narrative must distinguish docs-only (F3)")
    low_narr = narr_text.lower()
    if ("not rebuilt" not in low_narr and "not reconstructed" not in low_narr and "does not reconstruct" not in low_narr):
        fail("narrative must state retry request URL not reconstructed/rebuilt (F3)")
    if "url missing" not in low_narr and "no `url`" not in low_narr and "no url" not in low_narr:
        fail("narrative must state retry meta has no url (sparse meta) (F3)")

    # --- manifest structure ---
    mfiles = require(manif, "files", "MANIFEST")
    if not isinstance(mfiles, dict):
        fail("MANIFEST.files must be object")

    bodies = ["arxiv_search.body", "openalex_search.body", "openalex_retry.body"]
    metas = ["arxiv_search.meta.json", "openalex_search.meta.json", "openalex_retry.meta.json"]
    for f in bodies + metas:
        if f not in mfiles:
            fail(f"MANIFEST missing entry for {f} (F1)")
        v = mfiles[f]
        if not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v):
            fail(f"MANIFEST entry {f} must be full SHA-256 hex (F1)")

    # --- hash chain F1: bytes <-> MANIFEST <-> meta <-> audit ---
    actual_body_sha = {}
    actual_body_len = {}
    for f in bodies:
        fp = pilot / f
        if not fp.is_file():
            fail(f"missing resource: pilot file {f} (F1)")
        h = sha256_file(str(fp))
        actual_body_sha[f] = h
        actual_body_len[f] = fp.stat().st_size
        if h != mfiles[f].lower():
            fail(f"hash mismatch: bytes {f} sha {h} != MANIFEST {mfiles[f]} (F1)")

    # meta files hash vs MANIFEST
    for f in metas:
        fp = pilot / f
        if not fp.is_file():
            fail(f"missing resource: pilot file {f} (F1)")
        h = sha256_file(str(fp))
        if h != mfiles[f].lower():
            fail(f"hash mismatch: meta file {f} sha {h} != MANIFEST {mfiles[f]} (F1)")

    # load metas (strict, no .get defaults)
    arxiv_meta, _ = load_json_no_dup(str(pilot / "arxiv_search.meta.json"))
    oasearch_meta, _ = load_json_no_dup(str(pilot / "openalex_search.meta.json"))
    oaretry_meta, _ = load_json_no_dup(str(pilot / "openalex_retry.meta.json"))

    for name, m in [("arxiv_search.meta.json", arxiv_meta), ("openalex_search.meta.json", oasearch_meta), ("openalex_retry.meta.json", oaretry_meta)]:
        if "sha256" not in m:
            fail(f"{name}: missing required key 'sha256' (F1)")
        if "bytes" not in m:
            fail(f"{name}: missing required key 'bytes' (F1)")

    if arxiv_meta["sha256"].lower() != actual_body_sha["arxiv_search.body"]:
        fail(f"hash mismatch: arxiv_search.meta sha {arxiv_meta['sha256']} != bytes {actual_body_sha['arxiv_search.body']} (F1)")
    if oasearch_meta["sha256"].lower() != actual_body_sha["openalex_search.body"]:
        fail(f"hash mismatch: openalex_search.meta sha != bytes (F1)")
    if oaretry_meta["sha256"].lower() != actual_body_sha["openalex_retry.body"]:
        fail(f"hash mismatch: openalex_retry.meta sha != bytes (F1)")
    if parse_int_strict(arxiv_meta["bytes"], "arxiv_search.meta.json bytes (F1)") != actual_body_len["arxiv_search.body"]:
        fail("bytes mismatch: arxiv_search.meta bytes != actual file size (F1)")
    if parse_int_strict(oasearch_meta["bytes"], "openalex_search.meta.json bytes (F1)") != actual_body_len["openalex_search.body"]:
        fail("bytes mismatch: openalex_search.meta bytes != actual file size (F1)")
    if parse_int_strict(oaretry_meta["bytes"], "openalex_retry.meta.json bytes (F1)") != actual_body_len["openalex_retry.body"]:
        fail("bytes mismatch: openalex_retry.meta bytes != actual file size (F1)")

    # audit sha must match
    sources = require(audit, "sources", "audit")
    arxiv = require(sources, "arxiv", "audit.sources")
    openalex = require(sources, "openalex", "audit.sources")
    arxiv_probe = require(arxiv, "live_probe", "audit.sources.arxiv")
    oa429 = require(openalex, "live_probe_429", "audit.sources.openalex")
    oaretry = require(openalex, "live_probe_retry", "audit.sources.openalex")

    for ctx, d in [("audit.sources.arxiv.live_probe", arxiv_probe), ("audit.sources.openalex.live_probe_429", oa429), ("audit.sources.openalex.live_probe_retry", oaretry)]:
        if "sha256" not in d:
            fail(f"{ctx}: missing required key 'sha256' (F1)")
        if "bytes" not in d:
            fail(f"{ctx}: missing required key 'bytes' (F1)")

    if arxiv_probe["sha256"].lower() != actual_body_sha["arxiv_search.body"]:
        fail(f"hash mismatch: audit arxiv sha {arxiv_probe['sha256']} != bytes {actual_body_sha['arxiv_search.body']} (F1)")
    if oa429["sha256"].lower() != actual_body_sha["openalex_search.body"]:
        fail("hash mismatch: audit openalex 429 sha != bytes (F1)")
    if oaretry["sha256"].lower() != actual_body_sha["openalex_retry.body"]:
        fail("hash mismatch: audit openalex retry sha != bytes (F1)")
    if parse_int_strict(arxiv_probe["bytes"], "audit.sources.arxiv.live_probe bytes (F1)") != actual_body_len["arxiv_search.body"]:
        fail("bytes mismatch: audit arxiv bytes != actual (F1)")
    if parse_int_strict(oa429["bytes"], "audit.sources.openalex.live_probe_429 bytes (F1)") != actual_body_len["openalex_search.body"]:
        fail("bytes mismatch: audit openalex 429 bytes != actual (F1)")
    if parse_int_strict(oaretry["bytes"], "audit.sources.openalex.live_probe_retry bytes (F1)") != actual_body_len["openalex_retry.body"]:
        fail("bytes mismatch: audit openalex retry bytes != actual (F1)")

    # --- F3 retry provenance fields in audit ---
    for k in ["wait_s_provenance", "remaining_provenance", "headers_provenance", "timing_provenance"]:
        if k not in oaretry:
            fail(f"audit.sources.openalex.live_probe_retry: missing '{k}' (must be author-reported/unverified) (F3)")
        if "author-reported/unverified" not in str(oaretry[k]):
            fail(f"audit retry {k} must be author-reported/unverified (F3)")
    obs = require(openalex, "observed_first_page", "audit.sources.openalex")
    for k in ["page", "per_page", "count"]:
        if k not in obs:
            fail(f"audit observed_first_page missing '{k}' (F3)")
    docsonly = require(openalex, "docs_only", "audit.sources.openalex")
    if not isinstance(docsonly, list) or len(docsonly) == 0:
        fail("audit docs_only must be non-empty list (F3)")

    # --- actual payload counts ---
    # arXiv: entries + doi
    try:
        raw_arxiv = (pilot / "arxiv_search.body").read_bytes()
    except Exception as e:
        fail(f"cannot read arxiv body: {e}")
    try:
        root = ET.fromstring(raw_arxiv)
    except Exception as e:
        fail(f"malformed arxiv Atom XML: {e} (F4)")
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    entries = root.findall("a:entry", ns)
    if len(entries) == 0:
        fail("malformed arxiv body: 0 entries found (F4)")
    arxiv_doi = 0
    for e in entries:
        d = e.find("arxiv:doi", ns)
        if d is not None and d.text is not None and d.text.strip() != "":
            arxiv_doi += 1
    # openalex retry body
    try:
        raw_oa = (pilot / "openalex_retry.body").read_bytes().decode("utf-8")
    except Exception as e:
        fail(f"malformed openalex retry body (not utf-8): {e}")
    try:
        oa = json.loads(raw_oa)
    except Exception as e:
        fail(f"malformed openalex retry JSON: {e}")
    if "results" not in oa or "meta" not in oa:
        fail("malformed openalex retry body: missing results/meta (F3/F4)")
    works = oa["results"]
    if not isinstance(works, list):
        fail("malformed openalex retry results: not a list")
    if "meta" not in oa:
        fail("malformed openalex retry body: missing required key \u0027meta\u0027")
    oa_meta = oa["meta"]
    if not isinstance(oa_meta, dict):
        fail("malformed openalex retry meta: meta must be object")
    if "count" not in oa_meta:
        fail("malformed openalex retry meta: missing required key \u0027count\u0027")
    oa_count = oa_meta["count"]

    # audit counters must match bodies
    if "entries_returned" not in arxiv:
        fail("audit arxiv missing entries_returned (F4)")
    if "doi_present" not in arxiv or "doi_total" not in arxiv:
        fail("audit arxiv missing doi_present/doi_total (F4)")
    audit_entries = parse_int_strict(arxiv["entries_returned"], "audit.sources.arxiv entries_returned (F4)")
    if audit_entries != len(entries):
        fail(f"counter mismatch: audit entries_returned {audit_entries} != body {len(entries)} (F4)")
    audit_doi_present = parse_int_strict(arxiv["doi_present"], "audit.sources.arxiv doi_present (F4)")
    if audit_doi_present != arxiv_doi:
        fail(f"counter mismatch: audit doi_present {audit_doi_present} != body {arxiv_doi} (F4)")
    audit_doi_total = parse_int_strict(arxiv["doi_total"], "audit.sources.arxiv doi_total (F4)")
    if audit_doi_total != len(entries):
        fail(f"counter mismatch: audit doi_total {audit_doi_total} != body entries {len(entries)} (F4)")
    if "works_returned" not in oaretry:
        fail("audit retry missing works_returned (F4)")
    audit_works = parse_int_strict(oaretry["works_returned"], "audit.sources.openalex.live_probe_retry works_returned (F4)")
    if audit_works != len(works):
        fail(f"counter mismatch: audit works_returned {audit_works} != body {len(works)} (F4)")
    audit_obs_count = parse_int_strict(obs["count"], "audit.sources.openalex.observed_first_page count (F3)")
    body_oa_count = parse_int_strict(oa_count, "openalex retry body meta.count (F3)")
    if audit_obs_count != body_oa_count:
        fail(f"counter mismatch: audit observed_first_page.count {audit_obs_count} != body meta.count {body_oa_count} (F3)")
    # totalResults is required in BOTH audit and Atom body (F5). Body missing or empty must FAIL exit 1.
    actual_tr = None
    if "totalResults" not in arxiv_probe:
        fail("audit.sources.arxiv.live_probe: missing required key totalResults (F4)")
    audit_tr = parse_int_strict(arxiv_probe["totalResults"], "audit.sources.arxiv.live_probe totalResults (F4)")
    found_tr = False
    for el in root.iter():
        if el.tag.endswith("totalResults"):
            found_tr = True
            raw_tr = "" if el.text is None else el.text.strip()
            if raw_tr == "":
                fail("malformed arxiv body: empty opensearch:totalResults (F5)")
            if not re.fullmatch(r"[+-]?\d+", raw_tr):
                fail(f"malformed arxiv body totalResults not int: {raw_tr!r} (F5)")
            try:
                actual_tr = int(raw_tr)
            except SystemExit:
                raise
            except Exception as e:
                fail(f"malformed arxiv body totalResults not int: {raw_tr!r}: {e} (F5)")
            break
    if not found_tr or actual_tr is None:
        fail("malformed arxiv body: missing required opensearch:totalResults (F5)")
    if audit_tr != actual_tr:
        fail(f"counter mismatch: audit totalResults {audit_tr} != body {actual_tr} (F4)")

    # --- narrative-counter consistency F4 ---
    expect_doi = f"{arxiv_doi}/{len(entries)}"
    if expect_doi not in narr_text:
        fail(f"narrative-counter mismatch: narrative must contain '{expect_doi}' for arxiv DOI (F4)")
    if re.search(r"doi[^\\n]{0,60}verified|verified[^\\n]{0,60}doi", narr_text, re.I):
        fail("narrative must not call DOI verified when 0/2 missing (F4)")
    # narrative must contain audit numbers
    for needle, label in [
        (str(len(entries)) + " entries", "entries"),
        (str(len(works)) + " works", "works"),
        (str(oa_count), "meta.count"),
    ]:
        if needle not in narr_text:
            fail(f"narrative-counter mismatch: narrative must contain '{needle}' ({label}) (F4)")
    if str(actual_tr) not in narr_text:
        fail(f"narrative-counter mismatch: narrative must contain totalResults {actual_tr} (F4)")
    # audit text must also contain doi fraction
    if expect_doi not in audit_text:
        fail(f"audit-counter mismatch: audit JSON must contain '{expect_doi}' (F4)")

    ok("source audit hash/meta/MANIFEST/bytes chain + DOI + provenance + narrative counters consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())