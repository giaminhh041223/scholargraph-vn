"""Independent probe 01: hand-calculated RRF k=60, best ORIGINAL rank before year filter.
One contribution per source per group, rank 1-based, tie by canonical_id.
Permutation of source_results must NOT change results while true upstream
order change MUST change ranks. No author helper reuse: fresh builders.
"""
from datetime import datetime, timezone

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchError, SearchRequest, SourceResult,
)
from scholargraph.public_search.fusion import fuse

SHA = "b" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")

def mkreq(**kw):
    base = dict(query="hand rrf probe", sources=["openalex", "arxiv"], top_k=50,
                cap_per_source=50, year_from=None, year_to=None)
    base.update(kw)
    return SearchRequest.model_validate(base)

def mkpaper(source, sid, **kw):
    row = dict(source=source, source_id=sid, title="Probe title",
               landing_url="https://example.org/p", retrieved_at=NOW,
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

def mkresult(source, records, status=None):
    if status is None:
        status = "success" if records else "empty"
    return SourceResult(
        source=source, status=status, records=records,
        error=None, source_total=len(records),
        elapsed_seconds=0.2, filter_coverage="none", truncated=False,
        raw_references=[RawReference(raw_id=source + "-" + SHA, sha256=SHA, byte_count=2)] if records else [])

def main():
    # Layout: openalex order [A(group doi:10.5555/aaa), B(group doi:10.5555/bbb)]
    #         arxiv order [B first rank1, A second rank2]
    # Expected: A score = 1/(60+1) [oa rank1] + 1/(60+2) [ax rank2]; B = 1/(60+2)+1/(60+1) -> tie -> canonical a first.
    oa = mkresult("openalex", [mkpaper("openalex", "OA1", doi="10.5555/aaa"),
                               mkpaper("openalex", "OA2", doi="10.5555/bbb")])
    ax = mkresult("arxiv", [mkpaper("arxiv", "AX1", doi="10.5555/bbb"),
                            mkpaper("arxiv", "AX2", doi="10.5555/aaa")])
    req = mkreq()
    out = fuse([oa, ax], req)
    exp = 1/61 + 1/62
    print(f"groups={out.counts.groups} eligible={out.counts.eligible} raw={out.counts.raw}")
    for h in out.hits:
        print(f"hit {h.canonical_id} score={h.score!r} ranks={h.source_ranks}")
    assert out.counts.model_dump() == dict(raw=4, valid=4, invalid=0, excluded_by_year=0,
                                           eligible=4, groups=2, duplicate_excess=2, returned=2)
    assert abs(out.hits[0].score - exp) < 1e-15 and abs(out.hits[1].score - exp) < 1e-15
    assert out.hits[0].canonical_id == "doi:10.5555/aaa", "tie must break by canonical_id"
    assert out.hits[0].source_ranks == {"arxiv": 2, "openalex": 1}
    assert out.hits[1].source_ranks == {"arxiv": 1, "openalex": 2}
    # Permutation of source_results list must NOT change results (same ranks per source)
    out_perm = fuse([ax, oa], req)
    assert out_perm == out, "source_results permutation changed result"
    print("permutation invariance PASS")
    # True upstream order change MUST change ranks: swap arxiv order -> B rank1/A rank2 becomes A rank1/B rank2
    ax_swapped = mkresult("arxiv", [mkpaper("arxiv", "AX2", doi="10.5555/aaa"),
                                    mkpaper("arxiv", "AX1", doi="10.5555/bbb")])
    out2 = fuse([oa, ax_swapped], req)
    print(f"after swap: {[ (h.canonical_id, h.source_ranks) for h in out2.hits ]}")
    # Now A has rank1 in both sources: score 2/61; B has rank2 both: 2/62 -> order still a first but scores differ
    assert abs(out2.hits[0].score - 2/61) < 1e-15, f"got {out2.hits[0].score}"
    assert abs(out2.hits[1].score - 2/62) < 1e-15
    assert out2 != out, "upstream order change must change scores"
    print("upstream order sensitivity PASS")
    # Year filter keeps ORIGINAL rank: records years [2010(rank1,excluded), 2021(rank2,kept), 2022(rank3,kept)] with year_from=2020
    filt_recs = [mkpaper("openalex", "Y1", publication_year=2010, doi="10.5555/y1"),
                 mkpaper("openalex", "Y2", publication_year=2021, doi="10.5555/y2"),
                 mkpaper("openalex", "Y3", publication_year=2022, doi="10.5555/y3")]
    filt_out = fuse([mkresult("openalex", filt_recs)], mkreq(sources=["openalex"], year_from=2020))
    print(f"filter scores={[h.score for h in filt_out.hits]} excluded={filt_out.counts.excluded_by_year}")
    assert filt_out.counts.excluded_by_year == 1 and filt_out.counts.eligible == 2
    assert filt_out.hits[0].score == 1/62 and filt_out.hits[1].score == 1/63, "must use original positions 2,3 not 1,2"
    print("original-rank-before-filter PASS")
    print("PROBE01 PASS")

if __name__ == "__main__":
    main()
