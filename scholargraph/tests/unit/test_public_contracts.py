"""Synthetic v1 fixtures; no research labels or live source claims."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError
from scholargraph.public_search.contracts import (
    SearchRequest, PaperRecord, SourceResult, RawReference, SearchError, FusionCounts,
    FusionResult, RankedHit, SearchSnapshot, SearchEnvelope, load_config, cache_key, digest,
    overall_status, error_http_status, read_json,
)
ROOT=Path(__file__).resolve().parents[2]
SHA="a"*64

def request(**changes):
    row=dict(query="  Graph Mining  ",sources=["arxiv","openalex"],top_k=10,
             cap_per_source=50,year_from=None,year_to=None)
    row.update(changes)
    return SearchRequest.model_validate(row)

def paper_row():
    nullable=["abstract","publication_year","doi","arxiv_id","venue","pdf_url",
              "license","open_access_status","citation_count","authors"]
    row=dict(source="openalex",source_id="W1",title="Synthetic title",landing_url="https://example.org/paper",
             retrieved_at=datetime(2026,9,30,tzinfo=timezone.utc),raw_sha256=SHA,parser_version="synthetic-1",
             authors_availability="missing",missing_fields=nullable,field_provenance={})
    row.update({name:None for name in nullable})
    row["field_provenance"]={key:[dict(source="openalex",source_id="W1",raw_sha256=SHA,raw_field=key)]
                              for key in ["title","source_id","landing_url"]}
    return row

def result(source,status):
    record=paper_row(); record["source"]=source
    for entries in record["field_provenance"].values():
        for entry in entries: entry["source"]=source
    return SourceResult(source=source,status=status,records=[PaperRecord.model_validate(record)] if status=="success" else [],
        error=SearchError(kind="timeout",message="synthetic timeout",source=source,retry_after_seconds=None,record_index=None) if status=="failed" else None,
        source_total=None,elapsed_seconds=0.1 if status!="not_requested" else None,
        filter_coverage="none",truncated=False if status!="not_requested" else None,
        raw_references=[RawReference(raw_id="synthetic-response",sha256=SHA,byte_count=12)] if status=="success" else [])

def test_request_normalization_refresh_key():
    cfg=load_config(ROOT/"configs/public_search.json")
    r=request(); assert r.query=="Graph Mining" and r.sources==["arxiv","openalex"]
    hashes={s:SHA for s in r.sources}
    assert cache_key(r,cfg,hashes)==cache_key(request(refresh=True),cfg,hashes)
    assert cache_key(r,cfg,hashes)!=cache_key(request(query="graph mining"),cfg,hashes)
    assert cache_key(r,cfg,hashes)!=cache_key(r,cfg.model_copy(update={"config_version":"changed"}),hashes)
    with pytest.raises(ValueError): cache_key(r,cfg,{})

@pytest.mark.parametrize("changes",[
    {"query":" "},{"query":"x"*501},{"sources":[]},{"sources":["arxiv","arxiv"]},
    {"sources":["other"]},{"top_k":True},{"top_k":0},{"cap_per_source":51},
    {"year_from":True},{"year_from":1799},{"year_to":2101},{"year_from":2025,"year_to":2024},
    {"refresh":1},{"qrels":{}}
])
def test_bad_request(changes):
    with pytest.raises(ValidationError): request(**changes)

@pytest.mark.parametrize("field",["query","sources","top_k","cap_per_source","year_from","year_to"])
def test_missing_required_request(field):
    row=request().model_dump(); del row[field]
    with pytest.raises(ValidationError): SearchRequest.model_validate(row)

def test_title_only_and_json_roundtrip():
    p=PaperRecord.model_validate(paper_row()); assert p.abstract is None
    assert PaperRecord.model_validate_json(p.model_dump_json())==p

@pytest.mark.parametrize("changes",[
    {"title":" "},{"title":None},{"source_id":" "},{"publication_year":True},
    {"doi":"invalid-doi"},{"citation_count":-1},{"citation_count":True},{"publication_year":float("nan")},
    {"landing_url":"javascript:alert(1)"},{"landing_url":"https://user:secret@example.org"},
    {"pdf_url":"file:///tmp/file"},{"landing_url":"https://example.org/\nfoo"},
    {"missing_fields":[]},{"field_provenance":{}},{"authors_availability":"known"},
    {"retrieved_at":datetime(2026,9,30)},
])
def test_malformed_paper(changes):
    row=paper_row(); row.update(changes)
    with pytest.raises(ValidationError): PaperRecord.model_validate(row)

@pytest.mark.parametrize("field",["source","source_id","title","landing_url","raw_sha256","parser_version","abstract"])
def test_missing_paper_field(field):
    row=paper_row(); del row[field]
    with pytest.raises(ValidationError): PaperRecord.model_validate(row)

@pytest.mark.parametrize("statuses,hits,expected",[
    (("empty","empty"),0,"empty"),(("success","empty"),1,"success"),
    (("success","success"),0,"empty"),(("empty","failed"),0,"partial_failure"),
    (("success","failed"),1,"partial_failure"),(("failed","failed"),0,"failed"),
])
def test_overall_truth_table(statuses,hits,expected):
    assert overall_status([result(s,st) for s,st in zip(["openalex","arxiv"],statuses)],request(),hits)==expected

def test_source_and_overall_fail_loud():
    row=result("openalex","failed").model_dump(); row["error"]=None
    with pytest.raises(ValidationError): SourceResult.model_validate(row)
    row=result("openalex","success").model_dump(); row["raw_references"]=[]
    with pytest.raises(ValidationError): SourceResult.model_validate(row)
    with pytest.raises(ValueError): overall_status([],request(),0)
    with pytest.raises(ValueError): overall_status([result("openalex","empty")]*2,request(),0)
    with pytest.raises(ValueError): overall_status([result("openalex","empty"),result("arxiv","failed")],request(),1)

@pytest.mark.parametrize("coverage", ["server", "bounded_pool"])
def test_not_requested_rejects_filter_coverage(coverage):
    row = dict(source="openalex", status="not_requested", records=[], error=None,
               source_total=None, elapsed_seconds=None, filter_coverage=coverage,
               truncated=None, raw_references=[])
    with pytest.raises(ValidationError, match="filter_coverage=none"):
        SourceResult.model_validate(row)

def test_not_requested_with_none_is_valid():
    row = dict(source="openalex", status="not_requested", records=[], error=None,
               source_total=None, elapsed_seconds=None, filter_coverage="none",
               truncated=None, raw_references=[])
    assert SourceResult.model_validate(row).filter_coverage == "none"

def test_priorities():
    def err(kind): return SearchError(kind=kind,message="synthetic",source=None,retry_after_seconds=None,record_index=None)
    assert error_http_status([])==200
    assert error_http_status([err("timeout"),err("quota")])==503
    assert error_http_status([err("storage"),err("quota")])==500
    assert error_http_status([err("auth")])==502
    assert error_http_status([err("request"),err("storage")])==422

def test_empty_snapshot_and_failure_envelope():
    counts=FusionCounts(raw=0,valid=0,invalid=0,excluded_by_year=0,eligible=0,groups=0,duplicate_excess=0,returned=0)
    now=datetime.now(timezone.utc)
    snap=SearchSnapshot(schema_version=1,contract_version="1.0.0",snapshot_id="synthetic-empty",request=request(),
        config_sha256=SHA,adapter_sha256={s:SHA for s in request().sources},
        source_results=[result(s,"empty") for s in request().sources],fusion=FusionResult(hits=[],counts=counts),
        overall="empty",fetched_at=now,expires_at=now+timedelta(days=1))
    envelope=SearchEnvelope(schema_version=1,contract_version="1.0.0",overall="empty",snapshot=snap,errors=[],stale=False,cached=False)
    assert SearchEnvelope.model_validate_json(envelope.model_dump_json())==envelope
    row=snap.model_dump(); row["overall"]="success"
    with pytest.raises(ValidationError): SearchSnapshot.model_validate(row)
    row=envelope.model_dump(); row.update(overall="failed",snapshot=None)
    with pytest.raises(ValidationError): SearchEnvelope.model_validate(row)

@pytest.mark.parametrize("changes",[{"raw":1},{"eligible":1},{"returned":1},{"groups":True},{"raw":float("inf")}])
def test_count_identities(changes):
    row=dict(raw=0,valid=0,invalid=0,excluded_by_year=0,eligible=0,groups=0,duplicate_excess=0,returned=0); row.update(changes)
    with pytest.raises(ValidationError): FusionCounts.model_validate(row)

@pytest.mark.parametrize("mutation",["missing_sources","missing_timeout","false_verified","nan","unsafe_root","bool_budget"])
def test_bad_config_in_temp(tmp_path,mutation):
    row=json.loads((ROOT/"configs/public_search.json").read_text())
    if mutation=="missing_sources": del row["sources"]["arxiv"]
    if mutation=="missing_timeout": del row["sources"]["openalex"]["timeout_seconds"]
    if mutation=="false_verified": row["sources"]["openalex"]["source_policy_verified"]=False
    if mutation=="nan": row["deadline_seconds"]=float("nan")
    if mutation=="unsafe_root": row["data_root"]="data/raw/beir"
    if mutation=="bool_budget": row["sources"]["openalex"]["max_body_bytes"]=True
    p=tmp_path/"config.json"; p.write_text(json.dumps(row))
    with pytest.raises(ValueError): load_config(p)

def test_duplicate_json(tmp_path):
    p=tmp_path/"config.json"; p.write_text('{"sources": {}, "sources": {}}')
    with pytest.raises(ValueError): read_json(p)

def test_boundary_subprocess_and_leakage(tmp_path):
    # Synthetic qrels/held-out sentinels must not be opened by config/request validation.
    (tmp_path/"qrels.tsv").write_text("FORBIDDEN LABEL SENTINEL")
    (tmp_path/"held_out.json").write_text("FORBIDDEN HELD OUT SENTINEL")
    config=tmp_path/"config.json"; config.write_bytes((ROOT/"configs/public_search.json").read_bytes())
    req=tmp_path/"request.json"; req.write_text(request().model_dump_json())
    env=dict(os.environ,PYTHONPATH=str(ROOT/"src"))
    command=[sys.executable,"-m","scholargraph.public_search.contracts","--config",str(config),"--request",str(req)]
    good=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True)
    assert good.returncode==0 and "VALIDATED" in good.stdout
    config.unlink()
    bad=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True)
    assert bad.returncode==1 and "FAIL" in bad.stderr
    config.write_bytes((ROOT/"configs/public_search.json").read_bytes())
    req.write_text('{"query":"abstract only"}')
    bad=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True)
    assert bad.returncode==1
    config.write_text('{"schema_version": 1, "schema_version": 1}')
    bad=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True)
    assert bad.returncode==1

def test_instrumented_no_label_reads(tmp_path,monkeypatch):
    sentinel=tmp_path/"qrels.tsv"; sentinel.write_text("FORBIDDEN")
    opened=[]; original=Path.open
    def guarded(path,*args,**kwargs):
        opened.append(path)
        assert path!=sentinel, "leakage"
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guarded)
    cfg=load_config(ROOT/"configs/public_search.json")
    cache_key(request(),cfg,{s:SHA for s in request().sources})
    assert opened==[ROOT/"configs/public_search.json"]


@pytest.mark.parametrize("statuses,hit_count,overall",[
    (("empty","empty"),0,"empty"),(("success","empty"),1,"success"),
    (("success","success"),0,"empty"),(("empty","failed"),0,"partial_failure"),
    (("success","failed"),1,"partial_failure"),(("failed","failed"),0,"failed"),
])
def test_full_envelope_examples(statuses,hit_count,overall):
    sources=[result(s,st) for s,st in zip(["openalex","arxiv"],statuses)]
    records=[r for sr in sources for r in sr.records]
    hits=[]
    if hit_count:
        rec=records[0]
        hits=[RankedHit(canonical_id="synthetic:W1",rank=1,score=1/61,display=rec,
                        source_records=[rec],source_ranks={rec.source:1},conflicts={})]
    n=len(records)
    counts=FusionCounts(raw=n,valid=n,invalid=0,excluded_by_year=n-hit_count,
                        eligible=hit_count,groups=hit_count,duplicate_excess=0,returned=hit_count)
    now=datetime(2026,9,30,tzinfo=timezone.utc)
    snapshot=SearchSnapshot(schema_version=1,contract_version="1.0.0",snapshot_id="synthetic-example",
        request=request(),config_sha256=SHA,adapter_sha256={s:SHA for s in request().sources},
        source_results=sources,fusion=FusionResult(hits=hits,counts=counts),overall=overall,
        fetched_at=now,expires_at=now+timedelta(days=1))
    errors=[sr.error for sr in sources if sr.error is not None]
    envelope=SearchEnvelope(schema_version=1,contract_version="1.0.0",snapshot=snapshot,overall=overall,
                            errors=errors,stale=False,cached=False)
    assert SearchEnvelope.model_validate_json(envelope.model_dump_json())==envelope
    assert (error_http_status(errors)==200)==(overall in {"success","empty"})


def test_version_bool_and_endpoint_rejected(tmp_path):
    row=json.loads((ROOT/"configs/public_search.json").read_text())
    p=tmp_path/"config.json"
    row["schema_version"]=True; p.write_text(json.dumps(row))
    with pytest.raises(ValueError): load_config(p)
    row["schema_version"]=1; row["sources"]["openalex"]["endpoint"]="http://127.0.0.1/private"
    p.write_text(json.dumps(row))
    with pytest.raises(ValueError): load_config(p)


@pytest.mark.parametrize("score",[float("nan"),float("inf"),-1.,0.,True])
def test_nonfinite_or_invalid_scores(score):
    rec=PaperRecord.model_validate(paper_row())
    with pytest.raises(ValidationError):
        RankedHit(canonical_id="synthetic",rank=1,score=score,display=rec,
                  source_records=[rec],source_ranks={"openalex":1},conflicts={})


@pytest.mark.parametrize("mutation",["title_missing","abstract_only","title_only","bad_format"])
def test_persisted_adversarial_records(tmp_path,mutation):
    row=PaperRecord.model_validate(paper_row()).model_dump(mode="json")
    if mutation=="title_missing": del row["title"]
    if mutation=="abstract_only":
        row["title"]=None; row["abstract"]="synthetic abstract"
    if mutation=="bad_format": row["citation_count"]="100"
    path=tmp_path/"synthetic-paper.json"; path.write_text(json.dumps(row))
    if mutation=="title_only":
        assert PaperRecord.model_validate_json(path.read_bytes()).abstract is None
    else:
        with pytest.raises(ValidationError): PaperRecord.model_validate_json(path.read_bytes())
