# Log re-review SOL — EXT-03 W1 R5 081

- Ghi lúc 2026-09-30T15:19:08.111493+07:00.
- Verdict PASS, R4-F1/R4-F2 đóng; original F1–F7 đóng theo R4/ADR020 scope. Report management/public_search/reviews/SOL/EXT-03-W1-R5-081.md.
- Original reviewer context reused /root/review_w1_arxiv_081; không fresh context mới. Requested gpt-6.1-sol/high, actual alias/effort unknown theo metadata context.
- Target read-only HEAD049a2b86aa309dcdd5b4885b1ac25a8150b93200, repo public-gemini/nested scholargraph; Git status short rỗng trước/cuối; reviewer không code/test/config/board/git writes.
- 43 scoped target file hashes trước/sau0 đổi, 14 W0 pins khớp. Files tăng2 R5 packet/log so41 R4; old4 SOL report/log hashes giữ nguyên bên dưới.
- Author provenance: coordinator cung cấp fresh GEMINI R5 session66093fce-d949-4d55-b7c2-fb56c49e1135 CLI0, author packet tests NOT_RUN. First coordinator R5 run69passed1failed(emptyport); coordinator bổ sung2lineguard parsed.netloc.endswith(':') tại313–314, commit049a2b8 trên e3a7608. Full final70pass là coordinator, không gán choauthor.
- Không live HTTP, credentials/qrels/labels/held-out/offline datasets hoặc install. Synthetic TEMP fixture; injected mock transport only. Không full core suite hoặc research runs.

## Lệnh và kết quả thực

```powershell
$env:PYTHONPATH='D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/src'
$env:PYTHONDONTWRITEBYTECODE='1'
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-r5-081/repro.py
# exit0,14passed/0failed,43hashes0changes,14freeze pinsmatch (exec44435)
# cwd target nested project
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe -m pytest tests/unit/test_public_arxiv.py -q -p no:cacheprovider -k 'request_diagnostic_distinction or url_id_port_validation or strict_arxiv_id_validation or secret_error_redaction or duplicate_json_keys_fails'
# reviewer exit0,7passed/63deselected,6.74s
# coordinator command/result read-only from data/public_search/control/w1-081/gemini-tests-r5-final.log
# full focused70passed21.09s exit0, not reviewer full run
```

14 independent cases = 10 actual CLI subprocess +4 direct search cases. Cases/outputs below: exact previous booltopk/schema vs malformedJSON vs duplicateJSON diagnosis, synthetic secret redaction; invalid/nonnumeric/outofrange/empty port CLI1+searchfailed/schema; valid443/title-only/querylabelwordspositive; missingpayload CLI1. Script exit1 if assertion/hash mismatch, no fakePASS from collector exit alone. No additional broad audit.

## Closed SOL reports/logs immutable hashes

- `management/public_search/reviews/SOL/EXT-03-W1-081.md` SHA-256 `6623c3088509a76e8d2bad1385b7da696e74c5bcd19d8a9d0c97bef96e8850f3`.
- `management/public_search/logs/SOL/REVIEW-EXT-03-W1-081.md` SHA-256 `1563d803af658adbb669d0fe36243b381c887c17a9a5d0d72917a63e06784584`.
- `management/public_search/reviews/SOL/EXT-03-W1-R4-081.md` SHA-256 `8f3f4b1a7fe438f0086e6456d344755d9c379957c288527bb729a0af1ccb8776`.
- `management/public_search/logs/SOL/REVIEW-EXT-03-W1-R4-081.md` SHA-256 `743f507a5d50f25c480d634b213ac07aa229788f7fa0e86c98e6acd65c572d06`.
- TEMP `repro.py` SHA-256 `1dcc046f329550fda110701bfd89abbd2f938793d98c35586dcd40fffcf9be06`.
- TEMP `results.jsonl` SHA-256 `c9558f8df9f258dd014ea72de249c018ecfe6be5a7fe6cbf977ad31e2fd6a450`.

## Input43hashmanifest (before = after)

```json
{
  "artifacts/reports/public_search/muse/source_audit.json": "a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923",
  "configs/public_search.json": "1e188af340572a8fc51124fd8bd5b31f615d607a85967a3ee88871374853c4ed",
  "docs/PUBLIC_PAPER_SEARCH_TASKS.md": "309966a2a4c66ebfd83429240670aaa42febea435dbb1697d6a9a397da77c9ee",
  "docs/public_search/CONTRACT.md": "699ce6aeaf9a073b4e108b29bf4e7c089c22522bc9b4315f2eb14b3e06e4f868",
  "docs/public_search/SOURCE_AUDIT.md": "d213f075ae2256bfc21b3bf847699346b09c66c108962ccbd814444da254e312",
  "docs/public_search/UX_SPEC.md": "27464aa3d965725ae672517edbea2f2425394c93304fc5743224190c564eeb14",
  "management/public_search/logs/GEMINI/EXT-03-W1-081.md": "601bc9457894ab48659c3eec1242216763d70b7a940a37f1c154c191ab96c805",
  "management/public_search/logs/GEMINI/EXT-03-W1-R2-081.md": "175c8c97d0e3059386b57651a2dc9059294dd6833d0360e05b89fa012efce98b",
  "management/public_search/logs/GEMINI/EXT-03-W1-R3-081.md": "625f288409c2c64e2dd46d685d452e61dcdfe0972e7ce2c46f178ff74f03b093",
  "management/public_search/logs/GEMINI/EXT-03-W1-R4-081.md": "f6362579dd6aad6f012c851e659de9e348543eefcfaabd8a0360ac558bafccaf",
  "management/public_search/logs/GEMINI/EXT-03-W1-R4-CLOSE-081.md": "1795d4bbc74701ea691f3ce0d3a28f2f50b950a42cfa56b2bd98c55ac5191a0b",
  "management/public_search/logs/GEMINI/EXT-03-W1-R5-081.md": "8a65fa2e758444aec3ce1c9acf3520c869e092a75e631a7298d769f119220f83",
  "management/public_search/packets/GEMINI/EXT-03-W1-081.md": "d3df5bfdf805921f9212ca11b884e6307c0cb9c0ac2d209290abcf1c7c02443e",
  "management/public_search/packets/GEMINI/EXT-03-W1-R2-081.md": "376a25cca8147488a15781ff3229c20a19b639e974e973ccb97f2dbd2e5d45d4",
  "management/public_search/packets/GEMINI/EXT-03-W1-R3-081.md": "60d2c29ad37294f7dbda74366e0bf3354d9161e48f4d2bdf939c606d8c26d7e7",
  "management/public_search/packets/GEMINI/EXT-03-W1-R4-081.md": "66f8805088809c378534ed6cb2a13877e77eb6480fb21a55950813b75d263f64",
  "management/public_search/packets/GEMINI/EXT-03-W1-R4-CLOSE-081.md": "bdbf530cbe2529e32418d1edf1722fe58de94529f5324e083818d9a8b385373b",
  "management/public_search/packets/GEMINI/EXT-03-W1-R5-081.md": "6eaa1ddd37177b939e9d9e4c69d642959f1f50b7cda74aa3a691714abf136c09",
  "src/scholargraph/public_search/__init__.py": "048597a431e3739e6b0b8138bfeb19b8cb05072cd900f34b889a693887d3fab4",
  "src/scholargraph/public_search/arxiv.py": "7524a8f48bd2af8a4992af501a0abc73225acb6edaaee81899f2e39577b0a566",
  "src/scholargraph/public_search/contracts.py": "5d752064888f0558f121407bfa3bbc2d2c1a921f7991a39d5716ced79a553908",
  "src/scholargraph/public_search/transport.py": "a775b1e99c2dc64d4b6f523567a6543d1b536deed35c255a1b66c894e3607baf",
  "tests/fixtures/public_search/gemini/arxiv/duplicate_id_feed.xml": "349bec1385848fa87b14886cfbb1fac04deb761b0fc93d3ee1ffdce14b8d3e78",
  "tests/fixtures/public_search/gemini/arxiv/empty_feed.xml": "20a6ec519a4c6ab4dcddc53a2b0461fad35c9aa3f88e5f38350f4fdf2fefe94a",
  "tests/fixtures/public_search/gemini/arxiv/error_entry_feed.xml": "8d7885b9a0ccfdaca6899c098ec0371eaea259eea6d33b14c4d23e61838ce348",
  "tests/fixtures/public_search/gemini/arxiv/error_feed_no_counters.xml": "fb2c7bc377825b2cfaa0958aea3c9ca685f51de97e96336d3b6ff134923e6ed0",
  "tests/fixtures/public_search/gemini/arxiv/invalid_counter.xml": "fea386d14796556e7cb4300e73f3ca5f0dd0946f00ea77b869f69849d10d72a7",
  "tests/fixtures/public_search/gemini/arxiv/invalid_date.xml": "d5162102531be6f15636d1d680c75f1005e399fa3ff856c08397592522e9f032",
  "tests/fixtures/public_search/gemini/arxiv/malformed.xml": "1bc6abf79739a019eb6463aea73f06401d9fa6538e0df03438e890f443a894d2",
  "tests/fixtures/public_search/gemini/arxiv/missing_id.xml": "84dcc9f042dd4291067b673d87da8d0fe6bcf02fcbd27caabe04e39d7ab70b64",
  "tests/fixtures/public_search/gemini/arxiv/missing_link.xml": "203d9cbf6cb3067737e1a84ad5217de8a9e978deb09c1070f319254962023b56",
  "tests/fixtures/public_search/gemini/arxiv/missing_opensearch.xml": "9503ed87a839912a5f561317933e002e200f0f9f58ff2845ab709dbe62045d93",
  "tests/fixtures/public_search/gemini/arxiv/missing_title.xml": "27cb894eb5ec478e3947812a4e312ad00ddd229262b65f089e8c4b57b861284f",
  "tests/fixtures/public_search/gemini/arxiv/title_only_feed.xml": "c817e88488b5ba2d33008dec40c9895507a10f0da26ef1fa7522657163719909",
  "tests/fixtures/public_search/gemini/arxiv/valid_feed.xml": "a5c563a988240778d6ebd284c37e5c5d25fdb7988a8d7e207fdac3b5e5c0c074",
  "tests/fixtures/public_search/gemini/arxiv/valid_with_doi.xml": "a78abffe309c6ae03751bbb5d8efdab845b6c6e42dab9f4447f44846fd2d2b82",
  "tests/fixtures/public_search/gemini/arxiv/xxe_doctype.xml": "0c5e21c7c25efa695daddc638847a4e0a2a6febff2fc30e6e334be78c4845a7e",
  "tests/fixtures/public_search/gemini/ux_examples.json": "40c69c353e1e2de449e8f1f4771ab7ac23ef05051ae1f2e7f67ccc5767d983c6",
  "tests/fixtures/public_search/gemini/ux_examples.sidecar.json": "31625c97c6b0c5498b2d47b7f3e4f7b27ab4c375e4e9be59b1c546c72d433d46",
  "tests/fixtures/public_search/gemini/validate_fixtures.py": "0aa419f032ee24a12882cae40211d17bb72543bfe6c5f31ecc0fcfd87683db19",
  "tests/unit/test_public_arxiv.py": "bdce6badbf2c21ea39822e341abaf0f732ae2be6a4c110b2491efd121e5d163b",
  "tests/unit/test_public_contracts.py": "28a4b884bce6a47bda452c8aec6e19e144e21b1e555762b454b6119ea5d407f5",
  "tests/unit/test_public_transport.py": "7c7578bbf706930449cf8a1aaf87a3fed78d61a00db3729d038de666be688a74"
}
```

## Results

```jsonl
{"python": "D:\\Web_mining_20261\\scholargraph\\.venv\\Scripts\\python.exe", "python_version": "3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]", "import_path": "D:\\Web_mining_20261\\scholargraph\\.worktrees\\public-gemini\\scholargraph\\src\\scholargraph\\public_search\\arxiv.py", "freeze14_matches": true}
{"case": "schema_type", "exit": 1, "expected_exit": 1, "stderr": "FAIL: invalid request schema", "secret_leak": false, "traceback": false, "pass": true}
{"case": "malformed_json", "exit": 1, "expected_exit": 1, "stderr": "FAIL: invalid request JSON: malformed JSON syntax", "secret_leak": false, "traceback": false, "pass": true}
{"case": "duplicate_keys", "exit": 1, "expected_exit": 1, "stderr": "FAIL: invalid request JSON: duplicate keys detected", "secret_leak": false, "traceback": false, "pass": true}
{"case": "secret_schema", "exit": 1, "expected_exit": 1, "stderr": "FAIL: invalid request schema", "secret_leak": false, "traceback": false, "pass": true}
{"case": "cli_invalid_port", "exit": 1, "expected_exit": 1, "stderr": "FAIL: schema error: entry id URL has invalid syntax or port", "secret_leak": false, "traceback": false, "pass": true}
{"case": "search_invalid_port", "status": "failed", "kind": "schema", "calls": 1, "pass": true}
{"case": "cli_out_of_range_port", "exit": 1, "expected_exit": 1, "stderr": "FAIL: schema error: entry id URL has invalid syntax or port", "secret_leak": false, "traceback": false, "pass": true}
{"case": "search_out_of_range_port", "status": "failed", "kind": "schema", "calls": 1, "pass": true}
{"case": "cli_empty_port", "exit": 1, "expected_exit": 1, "stderr": "FAIL: schema error: entry id URL has invalid syntax or port", "secret_leak": false, "traceback": false, "pass": true}
{"case": "search_empty_port", "status": "failed", "kind": "schema", "calls": 1, "pass": true}
{"case": "cli_valid_port", "exit": 0, "expected_exit": 0, "stderr": "", "secret_leak": false, "traceback": false, "pass": true}
{"case": "search_valid_port", "status": "success", "kind": null, "calls": 1, "pass": true}
{"case": "valid_title_only_and_benign_query", "exit": 0, "expected_exit": 0, "stderr": "", "secret_leak": false, "traceback": false, "pass": true}
{"case": "missing_payload", "exit": 1, "expected_exit": 1, "stderr": "FAIL: payload file does not exist: C:\\Users\\ADMIN\\AppData\\Local\\Temp\\sg-ext03-sol-review-r5-081\\missing.xml", "secret_leak": false, "traceback": false, "pass": true}
{"cases": 14, "passed": 14, "failed": 0, "hash_count": 43, "changed_hashes": [], "arxiv_sha": "7524a8f48bd2af8a4992af501a0abc73225acb6edaaee81899f2e39577b0a566", "test_sha": "bdce6badbf2c21ea39822e341abaf0f732ae2be6a4c110b2491efd121e5d163b"}

```

## Reproducer source

```python
import hashlib,json,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
from scholargraph.public_search import arxiv as a
from scholargraph.public_search.contracts import SearchRequest
from scholargraph.public_search.transport import TransportResponse
root=Path('D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph');tmp=Path(__file__).parent
freeze=json.loads(Path('D:/Web_mining_20261/scholargraph/management/public_search/W0-FREEZE-081.json').read_text())
files=[root/'src/scholargraph/public_search/arxiv.py',root/'tests/unit/test_public_arxiv.py',*(root/'tests/fixtures/public_search/gemini/arxiv').glob('*'),*(root/'management/public_search/packets/GEMINI').glob('EXT-03-W1*081.md'),*(root/'management/public_search/logs/GEMINI').glob('EXT-03-W1*081.md'),*[root/f for f in freeze['sha256']]]
def hashes():return {f.relative_to(root).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)}
before=hashes();(tmp/'before.json').write_text(json.dumps(before,indent=2))
print(json.dumps({'python':sys.executable,'python_version':sys.version,'import_path':a.__file__,'freeze14_matches':all(before[f]==h for f,h in freeze['sha256'].items())}))
base='''<?xml version="1.0" encoding="UTF-8"?><!-- synthetic=true; independent reviewer fixture --><feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><id>https://arxiv.org/api/synthetic-feed</id><title>Synthetic feed</title><updated>2024-01-01T00:00:00Z</updated><opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage><entry><id>https://arxiv.org/abs/2401.00001v1</id><title>Valid title-only paper</title><published>2024-01-01T00:00:00Z</published><link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/></entry></feed>'''
valid=tmp/'valid.xml';valid.write_text(base)
request={'query':'held_out labels and qrels research','sources':['arxiv'],'top_k':1,'cap_per_source':1,'year_from':None,'year_to':None}
sentinel='SYNTHETIC_SECRET_R5_REVIEW_NOT_REAL';checks=[]
def cli(name,payload,req=None,expected=1,message=None):
    args=[sys.executable,'-m','scholargraph.public_search.arxiv','--payload',str(payload)]
    if req is not None:args+=['--request',str(req)]
    p=subprocess.run(args,capture_output=True,text=True)
    ok=p.returncode==expected and 'Traceback' not in p.stderr and sentinel not in p.stderr+p.stdout
    if expected==1:ok=ok and 'FAIL:' in p.stderr
    if message is not None:ok=ok and p.stderr.strip()==message
    if expected==0:ok=ok and json.loads(p.stdout)['status']=='VALIDATED'
    result={'case':name,'exit':p.returncode,'expected_exit':expected,'stderr':p.stderr.strip(),'secret_leak':sentinel in p.stderr+p.stdout,'traceback':'Traceback' in p.stderr,'pass':bool(ok)};checks.append(result);print(json.dumps(result))
for name,data,message in [
    ('schema_type',json.dumps(dict(request,top_k=True)),'FAIL: invalid request schema'),
    ('malformed_json','{"query":','FAIL: invalid request JSON: malformed JSON syntax'),
    ('duplicate_keys','{"query":"a","query":"b"}','FAIL: invalid request JSON: duplicate keys detected'),
    ('secret_schema',json.dumps(dict(request,api_key=sentinel)),'FAIL: invalid request schema')]:
    f=tmp/(name+'.json');f.write_text(data);cli(name,valid,f,message=message)
class MockTransport:
    def __init__(self,body):self.body=body;self.calls=0
    def clock(self):return 100.0
    def deadline(self):return 200.0
    def get(self,source,params,*,deadline):
        self.calls+=1
        return TransportResponse(self.body,hashlib.sha256(self.body).hexdigest(),'application/atom+xml',0.01,1)
for name,id,expected in [
    ('invalid_port','https://arxiv.org:not-a-port/abs/2401.00001v1',1),
    ('out_of_range_port','https://arxiv.org:99999/abs/2401.00001v1',1),
    ('empty_port','https://arxiv.org:/abs/2401.00001v1',1),
    ('valid_port','https://arxiv.org:443/abs/2401.00001v1',0)]:
    raw=base.replace('https://arxiv.org/abs/2401.00001v1</id>',id+'</id>').encode();f=tmp/(name+'.xml');f.write_bytes(raw)
    cli('cli_'+name,f,expected=expected)
    t=MockTransport(raw);result=a.search(SearchRequest.model_validate(request),t)
    if expected==1:ok=result.status=='failed' and result.error.kind=='schema' and not result.records and len(result.raw_references)==1
    else:ok=result.status=='success' and result.records[0].arxiv_id=='2401.00001v1' and result.records[0].abstract is None and 'abstract' in result.records[0].missing_fields
    item={'case':'search_'+name,'status':result.status,'kind':result.error.kind if result.error is not None else None,'calls':t.calls,'pass':ok};checks.append(item);print(json.dumps(item))
good=tmp/'valid_request.json';good.write_text(json.dumps(request));cli('valid_title_only_and_benign_query',valid,good,expected=0)
cli('missing_payload',tmp/'missing.xml')
after=hashes();(tmp/'after.json').write_text(json.dumps(after,indent=2))
changed=[f for f in before if before[f]!=after[f]]
summary={'cases':len(checks),'passed':sum(x['pass'] for x in checks),'failed':sum(not x['pass'] for x in checks),'hash_count':len(before),'changed_hashes':changed,'arxiv_sha':after['src/scholargraph/public_search/arxiv.py'],'test_sha':after['tests/unit/test_public_arxiv.py']};print(json.dumps(summary));sys.exit(0 if summary['failed']==0 and not changed else 1)

```

## Closeout

Reviewer PASS cho đúng target049a2b8; coordinator quyết định EXT03 acceptance/integration. ADR020 CLI schema-only/UTF32unsupported vẫn áp dụng, không live evidence mới. Prior closed reports giữ nguyên. Reviewer không dispatch hoặc triển khai thêm.

Parent `./scripts/check_project.ps1` sau ghi đủ report/log **exit0**, 53 tasks/483 local Markdown links/53 routes/7 lanes/79 chat sessions. Warning SG-034 awaits SG-033 đã có sẵn, ngoài EXT03. Broken link log Gemini cũ đã được coordinator sửa ở parent, target lịch sử giữ nguyên. Không gán patch này cho reviewer. Final scoped hash check:43files0changes, HEAD049a2b8 unchanged, target status short rỗng.
