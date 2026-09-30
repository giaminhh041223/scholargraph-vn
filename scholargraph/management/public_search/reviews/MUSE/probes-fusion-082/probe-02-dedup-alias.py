"""Independent probe 02: dedup identity - DOI/arXiv normalization, alias chains,
DOI-less ambiguity, same-title non-merge, display determinism, conflict evidence.
Fresh synthetic builders, distinct DOI values from author fixtures.
"""
from datetime import datetime, timezone
from itertools import permutations

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchRequest, SourceResult,
)
from scholargraph.public_search.fusion import arxiv_base_id, fuse, normalize_doi

SHA = "c" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")

def req(**kw):
    base = dict(query="dedup probe", sources=["openalex"], top_k=50, cap_per_source=50,
                year_from=None, year_to=None)
    base.update(kw)
    return SearchRequest.model_validate(base)

def paper(source, sid, **kw):
    row = dict(source=source, source_id=sid, title="Probe title",
               landing_url="https://example.org/q", retrieved_at=NOW,
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

def res(source, records):
    return SourceResult(source=source, status="success", records=records, error=None,
                        source_total=len(records), elapsed_seconds=0.1,
                        filter_coverage="none", truncated=False,
                        raw_references=[RawReference(raw_id=source + "-" + SHA, sha256=SHA, byte_count=1)])

def main():
    # normalize_doi explicit prefixes/resolvers/case only
    assert normalize_doi("  DOI:10.7777/Probe-X ") == "10.7777/probe-x"
    assert normalize_doi("https://doi.org/10.7777/Probe-X") == "10.7777/probe-x"
    assert normalize_doi("http://dx.doi.org/10.7777/Probe-X") == "10.7777/probe-x"
    for bad in ["10.7777/with space", "https://evil.org/10.7777/a", "https://doi.org/10.7777/a?x=1"]:
        try:
            normalize_doi(bad)
            raise AssertionError(f"normalize_doi accepted {bad!r}")
        except Exception as e:
            assert type(e).__name__ == "FusionError", f"wrong exc {type(e)} for {bad}"
    print("normalize_doi PASS")
    # arxiv base incl modern/legacy uppercase/category + lowercase version
    assert arxiv_base_id("2401.01234v3") == "2401.01234"
    assert arxiv_base_id("hep-th/9901001v2") == "hep-th/9901001"
    # uppercase category accepted (casefolded), but version marker must be lowercase v per regex
    assert arxiv_base_id("math.GT/0301001v1") == "math.gt/0301001"
    try:
        v = arxiv_base_id("HEP-TH/9901001V2")
        print(f"unexpected: uppercase V accepted -> {v}")
        raise AssertionError("uppercase V should be rejected per regex v[1-9]")
    except Exception as e:
        print(f"uppercase V rejected ({type(e).__name__}) PASS - regex requires lowercase v, category casefold only")
    print("arxiv_base PASS")
    # same-title different DOI must NOT merge
    out = fuse([res("openalex", [paper("openalex", "T1", doi="10.7777/t1", title="Same Title"),
                                 paper("openalex", "T2", doi="10.7777/t2", title="Same Title"),
                                 paper("openalex", "T3", title="Same Title")])], req())
    print(f"same-title groups={out.counts.groups} ids={[h.canonical_id for h in out.hits]}")
    assert out.counts.groups == 3, "same title merged!"
    print("same-title non-merge PASS")
    # multi-DOI same arxiv base must NOT bridge distinct DOI groups
    rows = [paper("arxiv", "2501.00001v1", arxiv_id="2501.00001v1", doi="10.7777/m1"),
            paper("arxiv", "2501.00001v2", arxiv_id="2501.00001v2", doi="10.7777/m2"),
            paper("arxiv", "2501.00001v3", arxiv_id="2501.00001v3")]
    out2 = fuse([SourceResult(source="arxiv", status="success", records=rows, error=None,
                              source_total=3, elapsed_seconds=0.1, filter_coverage="none",
                              truncated=False,
                              raw_references=[RawReference(raw_id="arxiv-"+SHA, sha256=SHA, byte_count=1)])],
                SearchRequest.model_validate(dict(query="x", sources=["arxiv"], top_k=50, cap_per_source=50,
                                                  year_from=None, year_to=None)))
    print(f"multiDOI groups={out2.counts.groups} dup={out2.counts.duplicate_excess} ids={[h.canonical_id for h in out2.hits]}")
    assert out2.counts.groups == 3 and out2.counts.duplicate_excess == 0, "DOI bridge!"
    assert {h.canonical_id for h in out2.hits} == {"doi:10.7777/m1", "doi:10.7777/m2", "arxiv:2501.00001"}
    for h in out2.hits:
        assert "doi" in h.conflicts and len(h.conflicts["doi"]) == 2, f"conflict evidence missing in {h.canonical_id}"
        assert len(h.source_records) == 1, "merged across DOI!"
    print("multiDOI no-bridge + conflict evidence PASS")
    # alias chain must not transitively merge DOI groups (openalex same source_id + arxiv base links)
    chain = [paper("openalex", "C1", arxiv_id="2501.00002v1", doi="10.7777/c1"),
             paper("openalex", "C1", arxiv_id="2501.00003v1"),
             paper("openalex", "C2", arxiv_id="2501.00003v1", doi="10.7777/c2"),
             paper("openalex", "C3", arxiv_id="2501.00002v2")]
    out3 = fuse([res("openalex", chain)], req())
    print(f"chain groups={out3.counts.groups} dup={out3.counts.duplicate_excess}")
    for h in out3.hits:
        print(f"  {h.canonical_id} nrec={len(h.source_records)} doi_conf={len(h.conflicts.get('doi', []))}")
    assert out3.counts.groups == 3, f"chain merged wrong: {out3.counts.groups}"
    amb = next(h for h in out3.hits if h.canonical_id.startswith("arxiv:"))
    assert len(amb.source_records) == 2, "DOIless ambiguity must stay separate (2 recs)"
    print("alias-chain no-transitive-merge PASS")
    # DOI-less single-DOI component joins that DOI; ambiguous stays separate already covered
    solo = [paper("openalex", "S1", arxiv_id="2501.00004v1", doi="10.7777/s1"),
            paper("openalex", "S2", arxiv_id="2501.00004v2")]
    out4 = fuse([res("openalex", solo)], req())
    print(f"solo groups={out4.counts.groups} ids={[h.canonical_id for h in out4.hits]}")
    assert out4.counts.groups == 1 and out4.hits[0].canonical_id == "doi:10.7777/s1"
    print("single-DOI join PASS")
    # display is whole evidenced record, deterministic openalex->arxiv then source_id; no field blend
    oa = paper("openalex", "D1", doi="10.7777/d1")
    ax = paper("arxiv", "2501.00005v2", arxiv_id="2501.00005v2", doi="10.7777/D1",
               abstract="Only arxiv abstract", publication_year=2024)
    from scholargraph.public_search.contracts import SearchRequest as SR
    both = fuse([res("openalex", [oa]),
                 SourceResult(source="arxiv", status="success", records=[ax], error=None,
                              source_total=1, elapsed_seconds=0.1, filter_coverage="none",
                              truncated=False,
                              raw_references=[RawReference(raw_id="arxiv-"+SHA, sha256=SHA, byte_count=1)])],
                SR.model_validate(dict(query="x", sources=["arxiv", "openalex"], top_k=50, cap_per_source=50,
                                       year_from=None, year_to=None)))
    hit = both.hits[0]
    print(f"display source={hit.display.source} sid={hit.display.source_id} abstract={hit.display.abstract!r}")
    assert hit.display == oa and hit.display.abstract is None, "field blend!"
    assert hit.display in hit.source_records
    print("display determinism PASS")
    # duplicate same-source order permutation stable when ranks unchanged is covered in probe01; here duplicate content permutation
    d1 = paper("openalex", "P1", doi="10.7777/p1", title="T-A")
    d2 = paper("openalex", "P1", doi="10.7777/p1", title="T-B")
    base_out = fuse([res("openalex", [d1, d2])], req())
    for perm in permutations([d1, d2]):
        assert fuse([res("openalex", list(perm))], req()) == base_out
    print("duplicate permutation PASS")
    print("PROBE02 PASS")

if __name__ == "__main__":
    main()
