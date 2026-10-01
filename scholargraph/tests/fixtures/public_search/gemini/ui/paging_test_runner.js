// Synthetic fixtures only; execute the existing DOM harness against production JS.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=process.cwd();
const harness=fs.readFileSync(path.join(__dirname,'node_test_runner.js'),'utf8');
const ctx={require,console,global,process,URL,Blob};
vm.runInNewContext(harness.slice(0,harness.indexOf('async function runAllTests'))+'\nthis.makeDOM=createMockDOM;',ctx);
const fixtures=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
assert.equal(fixtures.synthetic,true);
const modulePath=path.join(root,'ui/static/public_search.js');
function setup(fetchFn){delete require.cache[require.resolve(modulePath)];const ui=require(modulePath),doc=ctx.makeDOM();ui.init({document:doc,fetchFn});doc.getElementById('q').value='synthetic audit boundary';return {ui,doc};}
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body});
async function run(){
 const a=setup(async()=>response(fixtures.partial,503));
 await a.ui.handleSearchSubmit(false);
 assert.equal(a.doc.getElementById('results').children.length,10);
 await a.ui.changeSnapshotPage(fixtures.partial.snapshot.snapshot_id,2);
 assert(a.doc.getElementById('snapshot-pagination-info').textContent.startsWith('Trang 2 / 3'));
 assert(a.doc.getElementById('banner-region').textContent.includes('partial_failure'));
 assert(!a.doc.getElementById('banner-region').textContent.includes('Chuyển trang thất bại'));

 let resolvers=[];
 const b=setup(url=>new Promise(resolve=>resolvers.push({url,resolve})));
 b.ui.renderSearchResults(fixtures.success,false);
 const p2=b.ui.changeSnapshotPage(fixtures.success.snapshot.snapshot_id,2);
 resolvers[0].resolve(response(fixtures.success));await p2;resolvers=[];
 const p3=b.ui.changeSnapshotPage(fixtures.success.snapshot.snapshot_id,3);
 const p1=b.ui.changeSnapshotPage(fixtures.success.snapshot.snapshot_id,1);
 resolvers[1].resolve(response(fixtures.success));await p1;
 resolvers[0].resolve(response(fixtures.success));await p3;
 assert(b.doc.getElementById('snapshot-pagination-info').textContent.startsWith('Trang 1 / 3'));

 let delayed;
 const history=setup(()=>new Promise(resolve=>{delayed=resolve;}));
 history.ui.renderSearchResults(fixtures.success,false);
 const pending=history.ui.changeSnapshotPage(fixtures.success.snapshot.snapshot_id,2);
 const historical=JSON.parse(JSON.stringify(fixtures.success));historical.snapshot.snapshot_id='historical-other';historical.cached=true;historical.stale=true;
 history.ui.validateEnvelope(historical);history.ui.renderSearchResults(historical,false);
 delayed(response(fixtures.success));await pending;
 assert(history.doc.getElementById('snapshot-pagination-info').textContent.includes('historical-other'));

 const foreign=JSON.parse(JSON.stringify(fixtures.success));foreign.snapshot.snapshot_id='wrong-response-id';
 const identity=setup(async()=>response(foreign));identity.ui.renderSearchResults(fixtures.success,false);
 await identity.ui.changeSnapshotPage(fixtures.success.snapshot.snapshot_id,2);
 assert(identity.doc.getElementById('snapshot-pagination-info').textContent.includes('audit-success-25'));
 assert(identity.doc.getElementById('banner-region').textContent.includes('không khớp snapshot_id'));

 const nullFail={schema_version:1,contract_version:'1.0.0',overall:'failed',snapshot:null,errors:[{kind:'storage',message:'audit failure',source:null,retry_after_seconds:null,record_index:null}],stale:false,cached:false};
 const nullPage=setup(async()=>response(nullFail));nullPage.ui.renderSearchResults(fixtures.success,false);
 await nullPage.ui.changeSnapshotPage(fixtures.success.snapshot.snapshot_id,2);
 assert(nullPage.doc.getElementById('banner-region').textContent.includes('audit failure'));
 // A subsequent save must still use the original displayed snapshot identity.
 let savedPayload;
 nullPage.ui.init({document:nullPage.doc,fetchFn:async(url,opts)=>{savedPayload=JSON.parse(opts.body);return response(nullFail,500);}});
 await nullPage.ui.savePaperToLibrary(fixtures.success.snapshot.fusion.hits[0],nullPage.doc.createElement('button'));
 assert.equal(savedPayload.snapshot_id,'audit-success-25');
 console.log('PAGING REGRESSION PASS: 5 cases');
}
run().catch(e=>{console.error(e);process.exit(1);});
