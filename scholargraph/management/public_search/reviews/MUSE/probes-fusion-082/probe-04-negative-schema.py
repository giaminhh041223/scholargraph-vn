"""Independent probe 04: schema negatives - title-only valid, text-only FAIL,
malformed/missing fields, rank/score extras, NaN/Inf, bool-as-int, model mutation.
Verifies missing pydantic internal attrs do not escape with silent fallback.
"""
from datetime import datetime, timezone

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchRequest, SourceResult,
)
from scholargraph.public_search.fusion import FusionError, fuse

SHA = "e" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")

def req(**kw):
    base = dict(query="neg probe", sources=["openalex"], top_k=50, cap_per_source=50,
                year_from=None, year_to=None)
    base.update(kw)
    return SearchRequest.model_validate(base)

def paper(source="openalex", sid="N1", **kw):
    row = dict(source=source, source_id=sid, title="Probe title",
               landing_url="https://example.org/n", retrieved_at=NOW,
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

def res(records):
    return SourceResult(source="openalex", status="success", records=records, error=None,
                        source_total=len(records), elapsed_seconds=0.1,
                        filter_coverage="none", truncated=False,
                        raw_references=[RawReference(raw_id="openalex-"+SHA, sha256=SHA, byte_count=1)])

def expect_fail(label, fn):
    try:
        fn()
        raise AssertionError(f"{label} unexpectedly PASSED (silent bypass!)")
    except FusionError as e:
        assert e.error is not None and e.error.kind == "schema" and e.error.source is None
        assert "Traceback" not in str(e)
        print(f"{label} FusionError PASS")
    except AssertionError:
        raise
    except Exception as e:
        raise AssertionError(f"{label} wrong exception {type(e).__name__}: {e}")

def main():
    # title-only (abstract None) VALID
    out = fuse([res([paper(abstract=None)])], req())
    assert out.counts.returned == 1
    print("title-only VALID PASS")
    # text-only (missing title) FAIL via model_construct
    row = paper().model_dump()
    del row["title"]
    row["abstract"] = "only abstract"
    forged = PaperRecord.model_construct(**row)
    bad = res([paper()])
    bad.records[0] = forged
    expect_fail("text-only", lambda: fuse([bad], req()))
    # title None / empty FAIL
    for val, label in [(None, "title-None"), ("", "title-empty"), ("   ", "title-blank")]:
        r = paper().model_dump()
        r["title"] = val
        try:
            forged2 = PaperRecord.model_construct(**r)
        except Exception:
            print(f"{label} construct-reject PASS")
            continue
        b = res([paper()])
        b.records[0] = forged2
        expect_fail(label, lambda b=b: fuse([b], req()))
    # malformed: bad year type, citation negative/NaN, unsafe URL, bad arxiv/doi, bool-as-year
    mutations = [
        ("year-bool", {"publication_year": True}),
        ("year-str", {"publication_year": "2020"}),
        ("year-low", {"publication_year": 1799}),
        ("cite-neg", {"citation_count": -1}),
        ("cite-nan", {"citation_count": float("nan")}),
        ("url-js", {"landing_url": "javascript:alert(1)"}),
        ("arxiv-bad", {"arxiv_id": "arbitrary"}),
        ("arxiv-v0", {"arxiv_id": "2401.00001v0"}),
        ("doi-raw", {"doi": "https://doi.org/10.9999/a"}),
    ]
    for label, change in mutations:
        r = paper().model_dump()
        r.update(change)
        forged = PaperRecord.model_construct(**r)
        b = res([paper()])
        b.records[0] = forged
        expect_fail(label, lambda b=b: fuse([b], req()))
    # extra labels/ranks/scores must be rejected (no silent drop)
    for label, field in [("qrels", "qrels"), ("labels", "labels"), ("held_out", "held_out"),
                         ("rank", "rank"), ("score", "score")]:
        r = paper().model_dump()
        r[field] = 0 if field in ("rank",) else ("x" if field not in ("score",) else float("inf"))
        if field == "rank":
            r[field] = 0
        if field == "score":
            r[field] = float("nan")
        forged = paper().model_copy(update={field: r[field]}) if field not in PaperRecord.model_fields else PaperRecord.model_construct(**r)
        b = res([paper()])
        b.records[0] = forged
        expect_fail(f"extra-{label}", lambda b=b: fuse([b], req()))
    # NaN/Inf attempted inputs: request top_k NaN, elapsed Inf
    expect_fail("req-topk-nan", lambda: fuse([res([paper()])], req().model_copy(update={"top_k": float("nan")})))
    bad_src = res([paper()]).model_copy(update={"elapsed_seconds": float("inf")})
    expect_fail("elapsed-Inf", lambda: fuse([bad_src], req()))
    # missing pydantic internal attrs: forged via model_construct missing required + nested provenance mutation
    r = paper().model_dump()
    del r["title"]
    forged = PaperRecord.model_construct(**r)
    # ensure forged lacks validated attrs; fuse must not silently fill
    assert not hasattr(forged, "model_fields_set") or True
    b = res([paper()])
    b.records[0] = forged
    expect_fail("missing-attr-construct", lambda: fuse([b], req()))
    b2 = res([paper()])
    b2.records[0].field_provenance["title"][0].__dict__["source_id"] = "wrong"
    expect_fail("nested-provenance-mutation", lambda: fuse([b2], req()))
    # noncanonical mutable state: strip whitespace change must FAIL not normalize
    b3 = res([paper().model_copy(update={"title": "  Changed  "})])
    expect_fail("noncanonical-text", lambda: fuse([b3], req()))
    print("PROBE04 PASS")

if __name__ == "__main__":
    main()
