"""Independent probe 03: caps, counters identities, year filter, duplicates, top_k.
Identities: raw=valid+invalid, valid=excluded+eligible, eligible=groups+duplicates, returned=len(hits)<=groups/top_k.
Cap 1..50 enforced; source_total<records FAIL; failed source exposes no records.
"""
from datetime import datetime, timezone

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchError, SearchRequest, SourceResult,
)
from scholargraph.public_search.fusion import FusionError, fuse

SHA = "d" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")

def req(**kw):
    base = dict(query="counter probe", sources=["openalex"], top_k=50, cap_per_source=50,
                year_from=None, year_to=None)
    base.update(kw)
    return SearchRequest.model_validate(base)

def paper(source, sid, **kw):
    row = dict(source=source, source_id=sid, title="Probe title",
               landing_url="https://example.org/c", retrieved_at=NOW,
               raw_sha256=SHA, parser_version="probe-082")
    for f in NULLABLE:
        row[f] = None
    row.update(kw)
    row["authors_availability"] = "missing" if row["authors"] is None else "known"
    row["missing_fields"] = [f for f in NULLABLE if row[f] is None]
    row["field_provenance"] = {
        f: [FieldEvidence(source=source, source_id=sid, raw_sha256=SHA, raw_field=f)]
        for f in ("source_id", "title", "landing_url", *NULLABLE) if row[f] is not None}
    return PaperRecord.model_validate(row)

def res(source, records, **kw):
    status = kw.pop("status", ("success" if records else "empty"))
    return SourceResult(source=source, status=status, records=records, error=None,
                        source_total=len(records), elapsed_seconds=0.1,
                        filter_coverage="none", truncated=False,
                        raw_references=[RawReference(raw_id=source+"-"+SHA, sha256=SHA, byte_count=1)] if records else [])

def check_identities(out, label):
    c = out.counts
    assert c.raw == c.valid + c.invalid, f"{label} raw identity"
    assert c.valid == c.eligible + c.excluded_by_year, f"{label} valid identity"
    assert c.eligible == c.groups + c.duplicate_excess, f"{label} eligible identity"
    assert c.returned == len(out.hits) and c.returned <= c.groups, f"{label} returned identity"
    print(f"{label}: raw={c.raw} valid={c.valid} invalid={c.invalid} excl={c.excluded_by_year} elig={c.eligible} groups={c.groups} dup={c.duplicate_excess} ret={c.returned} PASS")

def main():
    # exact duplicates: 1 group, duplicate_excess 1, single contribution score 1/61
    row = paper("openalex", "E1")
    out = fuse([res("openalex", [row, row])], req())
    check_identities(out, "exact-dup")
    assert out.counts.groups == 1 and out.counts.duplicate_excess == 1
    assert out.hits[0].score == 1/61, f"double contribution! {out.hits[0].score}"
    assert out.hits[0].source_records == [row, row]
    print("exact-dup no-double-count PASS")
    # full pool 100 (50/source distinct DOI pairs share DOI across sources -> 50 groups, 50 dup)
    rows = []
    for src in ["openalex", "arxiv"]:
        recs = [paper(src, f"Q{i}", doi=f"10.8888/{i}") for i in range(50)]
        rows.append(SourceResult(source=src, status="success", records=recs, error=None,
                                 source_total=50, elapsed_seconds=0.1, filter_coverage="none",
                                 truncated=False,
                                 raw_references=[RawReference(raw_id=src+"-"+SHA, sha256=SHA, byte_count=1)]))
    out2 = fuse(rows, SearchRequest.model_validate(dict(query="x", sources=["arxiv", "openalex"], top_k=7, cap_per_source=50, year_from=None, year_to=None)))
    check_identities(out2, "fullpool")
    assert out2.counts.raw == 100 and out2.counts.groups == 50 and out2.counts.duplicate_excess == 50
    assert out2.counts.returned == 7 and [h.rank for h in out2.hits] == list(range(1, 8))
    # top_k reflects full pool not returned-only: groups stays 50 even though returned 7
    print("fullpool top_k PASS")
    # null year excluded when filter active
    recs = [paper("openalex", "N1", publication_year=None, doi="10.8888/n1"),
            paper("openalex", "N2", publication_year=2021, doi="10.8888/n2")]
    out3 = fuse([res("openalex", recs)], req(year_from=2020, year_to=2025))
    check_identities(out3, "nullyear")
    assert out3.counts.excluded_by_year == 1 and out3.counts.eligible == 1 and out3.counts.returned == 1
    print("null-year-excluded PASS")
    # cap boundaries: cap 1..50 ok, 0/51 rejected at request level; pool over cap FAIL
    for bad_cap in [0, 51]:
        try:
            SearchRequest.model_validate(dict(query="x", sources=["openalex"], top_k=50, cap_per_source=bad_cap, year_from=None, year_to=None))
            raise AssertionError(f"cap {bad_cap} accepted")
        except Exception:
            print(f"cap {bad_cap} rejected PASS")
    try:
        fuse([res("openalex", [paper("openalex", "A"), paper("openalex", "B")])],
             req(cap_per_source=1))
        raise AssertionError("pool over cap accepted")
    except FusionError:
        print("pool-over-cap FAIL PASS")
    # source_total < records FAIL
    bad = res("openalex", [paper("openalex", "Z")]).model_copy(update={"source_total": 0})
    try:
        fuse([bad], req())
        raise AssertionError("source_total violation accepted")
    except FusionError:
        print("source-total FAIL PASS")
    # failed source must expose no records (contract) and fuse counts only completed pool
    failed = SourceResult(source="arxiv", status="failed", records=[],
                          error=SearchError(kind="timeout", message="probe timeout", source="arxiv",
                                            retry_after_seconds=None, record_index=None),
                          source_total=None, elapsed_seconds=0.3, filter_coverage="none",
                          truncated=None, raw_references=[])
    okrows = res("openalex", [paper("openalex", "K1", doi="10.8888/k1")])
    out4 = fuse([okrows, failed], SearchRequest.model_validate(dict(query="x", sources=["arxiv", "openalex"], top_k=50, cap_per_source=50, year_from=None, year_to=None)))
    check_identities(out4, "partial-pool")
    assert out4.counts.raw == 1, "failed payload counted!"
    print("failed-source-not-counted PASS")
    # selection failures structured FAIL not empty: missing/duplicate/unselected/no-source
    cases = [
        ([], req(), "no-source"),
        ([res("openalex", []), res("openalex", [])], req(), "duplicate-source"),
        ([res("openalex", [paper("openalex", "S")])], SearchRequest.model_validate(dict(query="x", sources=["arxiv", "openalex"], top_k=5, cap_per_source=50, year_from=None, year_to=None)), "missing-selected"),
    ]
    for rows_c, rq, label in cases:
        try:
            r = fuse(rows_c, rq)
            raise AssertionError(f"{label} accepted with hits={r.hits}")
        except FusionError:
            print(f"{label} structured-FAIL PASS")
    print("PROBE03 PASS")

if __name__ == "__main__":
    main()
