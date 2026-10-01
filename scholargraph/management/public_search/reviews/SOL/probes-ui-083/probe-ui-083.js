const fs=require("fs"),path=require("path");
const target="D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph";
const UI=require(path.join(target,"ui/static/public_search.js"));
const runner=require(path.join(target,"tests/fixtures/public_search/gemini/ui/node_test_runner.js"));
const ux=JSON.parse(fs.readFileSync(path.join(target,"tests/fixtures/public_search/gemini/ux_examples.json")));
const good=ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope;
let pass=0,fail=0;function report(ok,id,d){console.log((ok?"[PASS] ":"[FAIL] ")+id+" :: "+d);ok?pass++:fail++;}function clone(x){return JSON.parse(JSON.stringify(x));}
const cases=[
 ["missing_source_total",e=>{delete e.snapshot.source_results[0].source_total;}],
 ["missing_truncated",e=>{delete e.snapshot.source_results[0].truncated;}],
 ["source_total_string",e=>{e.snapshot.source_results[0].source_total="wrong";}],
 ["truncated_string",e=>{e.snapshot.source_results[0].truncated="wrong";}],
 ["calendar_year0000",e=>{e.snapshot.fetched_at="0000-01-01T00:00:00Z";}],
 ["calendar_offset+23:59",e=>{e.snapshot.fetched_at="2026-01-01T00:00:00+23:59";}]
];
for(const [id,mut] of cases){let e=clone(good),threw=false;mut(e);try{UI.validateEnvelope(e);}catch(_){threw=true;}report(threw,id,threw?"reject":"ACCEPT malformed payload");}
(async function(){
 const doc=runner.createMockDOM();
 UI.init({document:doc,fetchFn:async function(url,opt){
   return {ok:true,status:200,json:async function(){const h=clone(good.snapshot.fusion.hits[0]);return {canonical_id:h.canonical_id,snapshot_id:"snap-original",saved_at:"2026-10-01T01:00:00Z",hit:h,incomplete_sources:false};}};
 }});
 UI.renderSearchResults(good,false);
 await UI.savePaperToLibrary(good.snapshot.fusion.hits[0],doc.createElement("button"));
 const b=doc.getElementById("banner-region").textContent;
 report(!b.includes("Lưu bài báo thất bại"),"idempotent_existing_snapshot","server original snapshot should be accepted; actual banner="+b);
 console.log("SUMMARY",{pass,fail});process.exit(fail?1:0);
})();
