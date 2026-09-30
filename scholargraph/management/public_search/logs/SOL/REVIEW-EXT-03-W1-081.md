# Nhật ký review SOL — EXT-03 W1 R3 081

- Thời điểm ghi: 2026-09-30T14:19:14.757411+07:00.
- Verdict: CHANGES_REQUIRED, 3 P1 + 4 P2. Report: management/public_search/reviews/SOL/EXT-03-W1-081.md.
- Vai trò: reviewer độc lập/context mới, task /root/review_w1_arxiv_081. Model+effort requested gpt-6.1-sol/high; actual runtime alias/effort unknown vì context không có nguồn metadata độc lập để xác minh. Không suy routing thành actual.
- Target HEAD: 74df8db71371306d2db71a2f529308063e763e9d, checkout D:/Web_mining_20261/scholargraph/.worktrees/public-gemini; project nested scholargraph.
- Giới hạn ghi: hai report/log ở parent và scripts/fixtures TEMP. Không sửa target/config/tests/board, không commit/merge/reset/dispatch thêm.
- Đã kiểm target sạch trước/sau; 14 W0 freeze pins khớp, 37 target file hashes trước/sau giống nhau. Python/import path trong raw results dưới đây.
- HTTP chỉ MockTransport, 0 live API request. Không đọc credential, qrels/labels/held-out hay offline dataset. Các fixture dựng mới đều synthetic.

## Lệnh thực chạy và kết quả

```powershell
$env:PYTHONPATH='D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/src'
$env:PYTHONDONTWRITEBYTECODE='1'
# cwd target nested project
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe -m pytest tests/unit/test_public_arxiv.py -q -p no:cacheprovider
# exit0; 53 passed, 0 failed, 14.81s (exec session 13273 hoàn tất)
# TEMP scripts tái tạo từ các code block bên dưới
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-081/repro.py
# exit0; collector ghi expected/actual, exit0 KHÔNG có nghĩa các probes PASS
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-081/encoding.py
# exit0; 6 standard-encoding cases + duplicate-title case
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-081/extra.py
# exit0; CLI invalid-ID/root/benign-abstract + deadline sentinel + final hashes
# cwd parent ScholarGraph
./scripts/check_project.ps1
# exit0 trước ghi hai reports: 53 tasks, 476 local Markdown links,
# 53 model routes, 7 lanes, 79 chat sessions; existing WARN next SG-034 awaits SG-033
```

- Repro collector: 22 parser probes (12 đúng kỳ vọng reviewer, 10 sai), 12 CLI probes (9 đúng exit, 3 sai exit); một ca CLI exit1 thêm assertion secret leak fail. F6 loại hai utf-16-le/be declaration exploratory khỏi bằng chứng chính, dùng vòng declaration chuẩn bên dưới.
- Standard encoding: UTF-16 BOM/LE/BE 3 pass, UTF-32 BOM/LE/BE 3 fail; duplicate conflicting title CLI0.
- Extra CLI: invalid ID exit0, wrong root exit0, benign abstract Error correction exit1; không traceback. Deadline case failed/timeout đúng kỳ vọng, 1 network mock call, giữ 1 raw ref, không records; audit open trong search có 0 reads.
- Thử đầu repro.py lỗi KeyError do đường dẫn Windows trong manifest reviewer; sửa .as_posix() rồi chạy lại exit0. Thử đầu extra.py chặn chính thao tác đọc source-audit artifact để hash sau test; giới hạn guard đúng interval search rồi chạy lại exit0. Đây là lỗi harness reviewer, không finding của target. Lần shell kèm rg không có match trả1; lần cuối chỉ chạy extra.py xác nhận Python/shell exit0.
- Không chạy full suite/core experiments; không có số đo live rate/quota/paging ngoài mock.

## Hash reproducer và output

- `repro.py` SHA-256 `0d6daa3f670ff9399504b4d1cabd4bceca2d1954768d480b5359b6a0c73efee2`.
- `encoding.py` SHA-256 `46124a5962fa2a80c21ce8fea513389b9cb79d634ea5678c9d9e3dc3bdcca9f4`.
- `extra.py` SHA-256 `041cfa67a6e614d5f10c8338465014757bd3d1de7f9a150a9a4ae9772c621271`.
- `results.jsonl` SHA-256 `cca203f0049673b28e11ef232dfdde1bec2c580c62df326f3224b4914652ef48`.
- `encoding-results.jsonl` SHA-256 `5ec016e95dc0ff8c1d98dee86c9ff83786199e6001332db6e2b3566f988a050a`.
- `extra-results.jsonl` SHA-256 `252af92962234cf39aad0001eb62736ae101ee9a271f9f00e72ec3fb64ac8680`.

## Input hash manifest (37 files, trước = sau)

```json
{
  "management/public_search/logs/GEMINI/EXT-03-W1-081.md": "601bc9457894ab48659c3eec1242216763d70b7a940a37f1c154c191ab96c805",
  "management/public_search/logs/GEMINI/EXT-03-W1-R2-081.md": "175c8c97d0e3059386b57651a2dc9059294dd6833d0360e05b89fa012efce98b",
  "management/public_search/logs/GEMINI/EXT-03-W1-R3-081.md": "625f288409c2c64e2dd46d685d452e61dcdfe0972e7ce2c46f178ff74f03b093",
  "management/public_search/packets/GEMINI/EXT-03-W1-081.md": "d3df5bfdf805921f9212ca11b884e6307c0cb9c0ac2d209290abcf1c7c02443e",
  "management/public_search/packets/GEMINI/EXT-03-W1-R2-081.md": "376a25cca8147488a15781ff3229c20a19b639e974e973ccb97f2dbd2e5d45d4",
  "management/public_search/packets/GEMINI/EXT-03-W1-R3-081.md": "60d2c29ad37294f7dbda74366e0bf3354d9161e48f4d2bdf939c606d8c26d7e7",
  "src/scholargraph/public_search/arxiv.py": "cdc35f0ff38faf236020ac3470d44c85734c1cfff41053fd2646d6b57da62e57",
  "tests/fixtures/public_search/gemini/arxiv/duplicate_id_feed.xml": "349bec1385848fa87b14886cfbb1fac04deb761b0fc93d3ee1ffdce14b8d3e78",
  "tests/fixtures/public_search/gemini/arxiv/empty_feed.xml": "20a6ec519a4c6ab4dcddc53a2b0461fad35c9aa3f88e5f38350f4fdf2fefe94a",
  "tests/fixtures/public_search/gemini/arxiv/error_entry_feed.xml": "8d7885b9a0ccfdaca6899c098ec0371eaea259eea6d33b14c4d23e61838ce348",
  "tests/fixtures/public_search/gemini/arxiv/error_feed_no_counters.xml": "fb2c7bc377825b2cfaa0958aea3c9ca685f51de97e96336d3b6ff134923e6ed0",
  "tests/fixtures/public_search/gemini/arxiv/invalid_counter.xml": "fea386d14796556e7cb4300e73f3ca5f0dd0946f00ea77b869f69849d10d72a7",
  "tests/fixtures/public_search/gemini/arxiv/invalid_date.xml": "d5162102531be6f15636d1d680c75f1005e399fa3ff856c08397592522e9f032",
  "tests/fixtures/public_search/gemini/arxiv/malformed.xml": "1bc6abf79739a019eb6463aea73f06401d9fa6538e0df03438e890f443a894d2",
  "tests/fixtures/public_search/gemini/arxiv/missing_id.xml": "84dcc9f042dd4291067b673d87da8d0fe6bcf02fcbd27caabe04e39d7ab70b64",
  "tests/fixtures/public_search/gemini/arxiv/missing_link.xml": "5923813d06779faf83061c2b89167adfaf024db305221353d93ca855e8ba2018",
  "tests/fixtures/public_search/gemini/arxiv/missing_opensearch.xml": "9503ed87a839912a5f561317933e002e200f0f9f58ff2845ab709dbe62045d93",
  "tests/fixtures/public_search/gemini/arxiv/missing_title.xml": "27cb894eb5ec478e3947812a4e312ad00ddd229262b65f089e8c4b57b861284f",
  "tests/fixtures/public_search/gemini/arxiv/title_only_feed.xml": "c817e88488b5ba2d33008dec40c9895507a10f0da26ef1fa7522657163719909",
  "tests/fixtures/public_search/gemini/arxiv/valid_feed.xml": "a5c563a988240778d6ebd284c37e5c5d25fdb7988a8d7e207fdac3b5e5c0c074",
  "tests/fixtures/public_search/gemini/arxiv/valid_with_doi.xml": "a78abffe309c6ae03751bbb5d8efdab845b6c6e42dab9f4447f44846fd2d2b82",
  "tests/fixtures/public_search/gemini/arxiv/xxe_doctype.xml": "0c5e21c7c25efa695daddc638847a4e0a2a6febff2fc30e6e334be78c4845a7e",
  "tests/unit/test_public_arxiv.py": "a7169faeb4f5a5cc5efedb94885e96168f14ff92a0947c11ff741db62509a03e",
  "configs/public_search.json": "1e188af340572a8fc51124fd8bd5b31f615d607a85967a3ee88871374853c4ed",
  "src/scholargraph/public_search/contracts.py": "5d752064888f0558f121407bfa3bbc2d2c1a921f7991a39d5716ced79a553908",
  "src/scholargraph/public_search/transport.py": "a775b1e99c2dc64d4b6f523567a6543d1b536deed35c255a1b66c894e3607baf",
  "tests/unit/test_public_contracts.py": "28a4b884bce6a47bda452c8aec6e19e144e21b1e555762b454b6119ea5d407f5",
  "tests/unit/test_public_transport.py": "7c7578bbf706930449cf8a1aaf87a3fed78d61a00db3729d038de666be688a74",
  "docs/public_search/CONTRACT.md": "699ce6aeaf9a073b4e108b29bf4e7c089c22522bc9b4315f2eb14b3e06e4f868",
  "docs/public_search/SOURCE_AUDIT.md": "d213f075ae2256bfc21b3bf847699346b09c66c108962ccbd814444da254e312",
  "artifacts/reports/public_search/muse/source_audit.json": "a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923",
  "src/scholargraph/public_search/__init__.py": "048597a431e3739e6b0b8138bfeb19b8cb05072cd900f34b889a693887d3fab4",
  "docs/public_search/UX_SPEC.md": "27464aa3d965725ae672517edbea2f2425394c93304fc5743224190c564eeb14",
  "tests/fixtures/public_search/gemini/ux_examples.json": "40c69c353e1e2de449e8f1f4771ab7ac23ef05051ae1f2e7f67ccc5767d983c6",
  "tests/fixtures/public_search/gemini/ux_examples.sidecar.json": "31625c97c6b0c5498b2d47b7f3e4f7b27ab4c375e4e9be59b1c546c72d433d46",
  "tests/fixtures/public_search/gemini/validate_fixtures.py": "0aa419f032ee24a12882cae40211d17bb72543bfe6c5f31ecc0fcfd87683db19",
  "docs/PUBLIC_PAPER_SEARCH_TASKS.md": "309966a2a4c66ebfd83429240670aaa42febea435dbb1697d6a9a397da77c9ee"
}
```

## Kết quả thô: results.jsonl

```jsonl
{"import_path": "D:\\Web_mining_20261\\scholargraph\\.worktrees\\public-gemini\\scholargraph\\src\\scholargraph\\public_search\\arxiv.py", "python": "D:\\Web_mining_20261\\scholargraph\\.venv\\Scripts\\python.exe", "python_version": "3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]", "freeze14_matches": true}
{"case": "valid_title_only", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "missing_id", "expected": "schema", "actual": "schema", "pass": true, "message": "entry missing required id"}
{"case": "abstract_only_missing_title", "expected": "schema", "actual": "schema", "pass": true, "message": "entry missing required title"}
{"case": "bad_xml", "expected": "schema", "actual": "schema", "pass": true, "message": "malformed XML payload"}
{"case": "non_atom_root", "expected": "schema", "actual": "VALIDATED", "pass": false, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "arbitrary_id", "expected": "schema", "actual": "VALIDATED", "pass": false, "ids": ["NOT_AN_ARXIV_ID"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "foreign_host_id", "expected": "schema", "actual": "VALIDATED", "pass": false, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "invalid_version_zero", "expected": "schema", "actual": "VALIDATED", "pass": false, "ids": ["2401.00001v0"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "real_paper_title_Error", "expected": "VALIDATED", "actual": "upstream", "pass": false, "message": "arXiv upstream query error entry detected"}
{"case": "real_paper_summary_Error", "expected": "VALIDATED", "actual": "upstream", "pass": false, "message": "arXiv upstream query error entry detected"}
{"case": "error_feed", "expected": "upstream", "actual": "upstream", "pass": true, "message": "arXiv upstream query error entry detected"}
{"case": "valid_utf-8", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "dtd_utf-8", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-16-le", "expected": "VALIDATED", "actual": "UNHANDLED_ValueError", "pass": false}
{"case": "dtd_utf-16-le", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-16-be", "expected": "VALIDATED", "actual": "UNHANDLED_ValueError", "pass": false}
{"case": "dtd_utf-16-be", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-32-le", "expected": "VALIDATED", "actual": "schema", "pass": false, "message": "malformed XML payload"}
{"case": "dtd_utf-32-le", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-32-be", "expected": "VALIDATED", "actual": "schema", "pass": false, "message": "malformed XML payload"}
{"case": "dtd_utf-32-be", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "link_selectors", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id", "pdf_url": "atom:link[title=pdf]"}}
{"case": "cli_no_args", "expected_exit": 1, "actual_exit": 2, "pass": false, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "cli_missing_payload", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_missing_request", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_bad_xml", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_invalid_type", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_label_leakage_field", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_out_of_range", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_secret_error", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": true}
{"case": "cli_duplicate_json", "expected_exit": 1, "actual_exit": 0, "pass": false, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "cli_bad_arxiv_query", "expected_exit": 1, "actual_exit": 0, "pass": false, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "cli_valid", "expected_exit": 0, "actual_exit": 0, "pass": true, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "cli_benign_query", "expected_exit": 0, "actual_exit": 0, "pass": true, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "real_transport_paging", "status": "success", "ids": ["2401.00001v1", "2401.00002v1"], "source_total": 2, "truncated": false, "calls": [{"start": 0, "time": 100.0, "query": "all:(held_out labels and qrels in public retrieval research)"}, {"start": 1, "time": 103.0, "query": "all:(held_out labels and qrels in public retrieval research)"}], "deadline": 130.0, "elapsed": 3.0}
{"case": "nonselected", "status": "not_requested", "call_count": 2}
{"case": "shared_rate_second_search", "status": "success", "call_time": 106.0}
{"target_hashes_unchanged": true, "file_count": 37, "parse_pass": 12, "parse_fail": 10, "cli_exit_pass": 9, "cli_exit_fail": 3, "cli_secret_leaks": 1}

```

## Kết quả thô: encoding-results.jsonl

```jsonl
{"case": "utf-16", "parse": "VALIDATED", "cli_exit": 0, "traceback": false}
{"case": "utf-16-le", "parse": "VALIDATED", "cli_exit": 0, "traceback": false}
{"case": "utf-16-be", "parse": "VALIDATED", "cli_exit": 0, "traceback": false}
{"case": "utf-32", "parse": "schema:malformed XML payload", "cli_exit": 1, "traceback": false}
{"case": "utf-32-le", "parse": "schema:malformed XML payload", "cli_exit": 1, "traceback": false}
{"case": "utf-32-be", "parse": "schema:malformed XML payload", "cli_exit": 1, "traceback": false}
{"case": "duplicate_conflicting_title", "cli_exit": 0}

```

## Kết quả thô: extra-results.jsonl

```jsonl
{"case": "cli_arbitrary_id", "exit": 0, "fail": false, "traceback": false}
{"case": "cli_wrong_root", "exit": 0, "fail": false, "traceback": false}
{"case": "cli_benign_error_abstract", "exit": 1, "fail": true, "traceback": false}
{"case": "deadline_across_pages", "status": "failed", "kind": "timeout", "calls": [0], "raw_refs": 1, "records": 0, "deadline": 102.0, "observed_time": 100.0, "audit_read_count": 0, "offline_reads": 0}
{"final_hashes_unchanged": true, "count": 37, "arxiv_sha": "cdc35f0ff38faf236020ac3470d44c85734c1cfff41053fd2646d6b57da62e57", "test_sha": "a7169faeb4f5a5cc5efedb94885e96168f14ff92a0947c11ff741db62509a03e", "repro_sha": "0d6daa3f670ff9399504b4d1cabd4bceca2d1954768d480b5359b6a0c73efee2", "encoding_sha": "46124a5962fa2a80c21ce8fea513389b9cb79d634ea5678c9d9e3dc3bdcca9f4", "extra_sha": "041cfa67a6e614d5f10c8338465014757bd3d1de7f9a150a9a4ae9772c621271"}

```

## Reproducer đầy đủ: repro.py

```python
import hashlib, json, os, sys, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone
from xml.sax.saxutils import escape
import httpx
from scholargraph.public_search import arxiv as a
from scholargraph.public_search.contracts import SearchRequest, PublicSearchConfig
from scholargraph.public_search.transport import Transport, RateState
root = Path('D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph')
tmp = Path(__file__).parent
files = sorted([root/'src/scholargraph/public_search/arxiv.py', root/'tests/unit/test_public_arxiv.py', * (root/'tests/fixtures/public_search/gemini/arxiv').glob('*'), * (root/'management/public_search/packets/GEMINI').glob('EXT-03-W1*081.md'), * (root/'management/public_search/logs/GEMINI').glob('EXT-03-W1*081.md')])
freeze = json.loads(Path('D:/Web_mining_20261/scholargraph/management/public_search/W0-FREEZE-081.json').read_text())
files += [root/p for p in freeze['sha256']]
def hashes(): return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
before = hashes(); (tmp/'before.json').write_text(json.dumps(before, indent=2))
print(json.dumps({'import_path':a.__file__, 'python':sys.executable, 'python_version':sys.version, 'freeze14_matches':all(before[p]==h for p,h in freeze['sha256'].items())}))
reqdata={'query':'held_out labels and qrels in public retrieval research','sources':['arxiv'],'top_k':2,'cap_per_source':2,'year_from':None,'year_to':None}
req = SearchRequest.model_validate(reqdata)
NS='http://www.w3.org/2005/Atom'
def entry(id='https://arxiv.org/abs/2401.00001v1',title='A valid paper',summary='Research abstract',links=None):
    links = links if links is not None else '<link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>'
    return f'<entry><id>{escape(id)}</id><title>{escape(title)}</title><summary>{escape(summary)}</summary><published>2024-01-01T00:00:00Z</published>{links}</entry>'
def feed(entries=None,total=1,start=0,items=1,rootname='feed'):
    e = entry() if entries is None else entries
    return f'<?xml version="1.0" encoding="UTF-8"?><{rootname} xmlns="{NS}" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><opensearch:totalResults>{total}</opensearch:totalResults><opensearch:startIndex>{start}</opensearch:startIndex><opensearch:itemsPerPage>{items}</opensearch:itemsPerPage>{e}</{rootname}>'
results=[]
def parsecase(name,raw,expected):
    body=raw.encode() if isinstance(raw,str) else raw
    try:
        _,_,_,records=a.parse_feed_payload(body,0,datetime.now(timezone.utc),hashlib.sha256(body).hexdigest())
        actual='VALIDATED'; extra={'ids':[r.arxiv_id for r in records], 'provenance':{k:v[0].raw_field for k,v in records[0].field_provenance.items()} if records else {}}
    except a.ArxivAdapterError as e:
        actual=e.error.kind; extra={'message':e.error.message}
    except Exception as e:
        actual='UNHANDLED_'+type(e).__name__; extra={}
    result={'case':name,'expected':expected,'actual':actual,'pass':actual==expected,**extra}; results.append(result); print(json.dumps(result))
parsecase('valid_title_only',feed(entry(summary='')),'VALIDATED')
parsecase('missing_id',feed(entry().replace('<id>https://arxiv.org/abs/2401.00001v1</id>','')),'schema')
parsecase('abstract_only_missing_title',feed(entry(title='')),'schema')
parsecase('bad_xml','<invalid','schema')
parsecase('non_atom_root',feed(rootname='notfeed'),'schema')
parsecase('arbitrary_id',feed(entry(id='NOT_AN_ARXIV_ID')),'schema')
parsecase('foreign_host_id',feed(entry(id='https://foreign.invalid/abs/2401.00001v1')),'schema')
parsecase('invalid_version_zero',feed(entry(id='https://arxiv.org/abs/2401.00001v0')),'schema')
parsecase('real_paper_title_Error',feed(entry(title='Error')),'VALIDATED')
parsecase('real_paper_summary_Error',feed(entry(summary='Error correction is studied in this paper.')),'VALIDATED')
parsecase('error_feed',feed(entry(id='http://arxiv.org/api/errors#incorrect_id_format', title='Error',summary='Error: malformed query')),'upstream')
for enc in ('utf-8','utf-16-le','utf-16-be','utf-32-le','utf-32-be'):
    raw=feed().replace('encoding="UTF-8"',f'encoding="{enc}"').encode(enc)
    parsecase('valid_'+enc,raw,'VALIDATED')
    dtd=feed().replace('?><feed','?><!DOCTYPE feed [<!ENTITY x "boom">]><feed').replace('encoding="UTF-8"',f'encoding="{enc}"').encode(enc)
    parsecase('dtd_'+enc,dtd,'schema')
links='<link href="https://arxiv.org/abs/2401.00001v1"/><link href="https://arxiv.org/pdf/2401.00001v1" type="application/pdf"/>'
parsecase('link_selectors',feed(entry(links=links)),'VALIDATED')
valid=tmp/'valid.xml'; valid.write_text(feed(),encoding='utf-8')
clis=[]
def cli(name,args,expected=1,secret=None):
    r=subprocess.run([sys.executable,'-m','scholargraph.public_search.arxiv',*args],capture_output=True,text=True)
    v={'case':name,'expected_exit':expected,'actual_exit':r.returncode,'pass':r.returncode==expected,'fail_marker':'FAIL:' in r.stderr,'traceback':'Traceback' in r.stderr,'secret_leaked': secret is not None and secret in r.stderr}
    clis.append(v); print(json.dumps(v))
cli('cli_no_args',[])
cli('cli_missing_payload',['--payload',str(tmp/'missing.xml')])
cli('cli_missing_request',['--payload',str(valid),'--request',str(tmp/'missing.json')])
mal=tmp/'bad.xml'; mal.write_text('<invalid'); cli('cli_bad_xml',['--payload',str(mal)])
for name,data in [('invalid_type',dict(reqdata,top_k=True)),('label_leakage_field',dict(reqdata,qrels={'synthetic':2})),('out_of_range',dict(reqdata,top_k=51))]:
    p=tmp/(name+'.json'); p.write_text(json.dumps(data)); cli('cli_'+name,['--payload',str(valid),'--request',str(p)])
sentinel='SYNTHETIC_SECRET_081_NOT_REAL'; p=tmp/'secret.json'; p.write_text(json.dumps(dict(reqdata,api_key=sentinel))); cli('cli_secret_error',['--payload',str(valid),'--request',str(p)],secret=sentinel)
p=tmp/'duplicate_key.json'; p.write_text('{"query":"valid","sources":["arxiv"],"top_k":0,"top_k":2,"cap_per_source":2,"year_from":null,"year_to":null}'); cli('cli_duplicate_json',['--payload',str(valid),'--request',str(p)])
p=tmp/'bad_query.json'; p.write_text(json.dumps(dict(reqdata,query='ti:(broken'))); cli('cli_bad_arxiv_query',['--payload',str(valid),'--request',str(p)])
cli('cli_valid',['--payload',str(valid)],expected=0)
p=tmp/'benign_query.json'; p.write_text(json.dumps(reqdata)); cli('cli_benign_query',['--payload',str(valid),'--request',str(p)],expected=0)
config=PublicSearchConfig.model_validate(json.loads((root/'configs/public_search.json').read_text()))
time=[100.0]; calls=[]; state=RateState()
def clock(): return time[0]
def sleep(seconds): time[0]+=seconds
def handler(r):
    start=int(r.url.params['start']); calls.append({'start':start,'time':time[0],'query':r.url.params['search_query']})
    return httpx.Response(200,headers={'Content-Type':'application/atom+xml'},content=feed(entry(id=f'https://arxiv.org/abs/2401.0000{start+1}v1'),total=2,start=start).encode())
with httpx.Client(transport=httpx.MockTransport(handler)) as client:
    with Transport(config,client=client,clock=clock,sleeper=sleep,environ={},rate_state=state) as tr:
        out=a.search(req,tr)
        print(json.dumps({'case':'real_transport_paging','status':out.status,'ids':[r.source_id for r in out.records],'source_total':out.source_total,'truncated':out.truncated,'calls':calls,'deadline':tr.deadline(),'elapsed':out.elapsed_seconds}))
        no=a.search(SearchRequest.model_validate(dict(reqdata,sources=['openalex'])),tr)
        print(json.dumps({'case':'nonselected','status':no.status,'call_count':len(calls)}))
    with Transport(config,client=client,clock=clock,sleeper=sleep,environ={},rate_state=state) as tr:
        out=a.search(SearchRequest.model_validate(dict(reqdata,cap_per_source=1)),tr)
        print(json.dumps({'case':'shared_rate_second_search','status':out.status,'call_time':calls[-1]['time']}))
after=hashes(); (tmp/'after.json').write_text(json.dumps(after,indent=2)); print(json.dumps({'target_hashes_unchanged':before==after,'file_count':len(before),'parse_pass':sum(x['pass'] for x in results),'parse_fail':sum(not x['pass'] for x in results),'cli_exit_pass':sum(x['pass'] for x in clis),'cli_exit_fail':sum(not x['pass'] for x in clis),'cli_secret_leaks':sum(x['secret_leaked'] for x in clis)}))


```

## Reproducer đầy đủ: encoding.py

```python
import hashlib, json, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone
from scholargraph.public_search import arxiv as a
p=Path(__file__).parent
ns='http://www.w3.org/2005/Atom'
base=f'<?xml version="1.0" encoding="UTF-16"?><feed xmlns="{ns}" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage><entry><id>https://arxiv.org/abs/2401.00001v1</id><title>A valid paper</title><link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/></entry></feed>'
for enc in ('utf-16','utf-16-le','utf-16-be','utf-32','utf-32-le','utf-32-be'):
    body=base.replace('UTF-16','UTF-32' if '32' in enc else 'UTF-16').encode(enc)
    f=p/('standard-'+enc+'.xml'); f.write_bytes(body)
    try:
        records=a.parse_feed_payload(body,0,datetime.now(timezone.utc),hashlib.sha256(body).hexdigest())[-1]
        status='VALIDATED'
    except a.ArxivAdapterError as e: status=e.error.kind+':'+e.error.message
    except Exception as e: status=type(e).__name__
    r=subprocess.run([sys.executable,'-m','scholargraph.public_search.arxiv','--payload',str(f)],capture_output=True,text=True)
    print(json.dumps({'case':enc,'parse':status,'cli_exit':r.returncode,'traceback':'Traceback' in r.stderr}))
f=p/'dup-title.xml'; f.write_text(base.replace('UTF-16','UTF-8').replace('<title>A valid paper</title>','<title>A valid paper</title><title>Contradictory title</title>'))
r=subprocess.run([sys.executable,'-m','scholargraph.public_search.arxiv','--payload',str(f)],capture_output=True,text=True)
print(json.dumps({'case':'duplicate_conflicting_title','cli_exit':r.returncode}))

```

## Reproducer đầy đủ: extra.py

```python
import hashlib,json,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
import httpx
from scholargraph.public_search import arxiv as a
from scholargraph.public_search.contracts import SearchRequest,PublicSearchConfig
from scholargraph.public_search.transport import Transport
root=Path('D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph'); p=Path(__file__).parent
base=(p/'valid.xml').read_text()
for name,text in [('arbitrary_id',base.replace('https://arxiv.org/abs/2401.00001v1</id>','INVALID</id>')),('wrong_root',base.replace('<feed ','<notfeed ').replace('</feed>','</notfeed>')),('benign_error_abstract',base.replace('Research abstract','Error correction is studied in this paper.'))]:
    f=p/(name+'.xml');f.write_text(text)
    r=subprocess.run([sys.executable,'-m','scholargraph.public_search.arxiv','--payload',str(f)],capture_output=True,text=True)
    print(json.dumps({'case':'cli_'+name,'exit':r.returncode,'fail':'FAIL:' in r.stderr,'traceback':'Traceback' in r.stderr}))
cfg=json.loads((root/'configs/public_search.json').read_text());cfg['deadline_seconds']=2.0
config=PublicSearchConfig.model_validate(cfg)
time=[100.0];calls=[]; reads=[]; guard=[True]
def audit(event,args):
    if guard[0] and event=='open' and isinstance(args[0],(str,bytes)):
        path=str(args[0]).replace('\\','/').lower();reads.append(path)
        if '/scholargraph/data/' in path or '/scholargraph/artifacts/' in path or any(k in path for k in ('/qrels/','/labels/','/held_out/')):
            raise RuntimeError('offline evidence access forbidden by independent reviewer sentinel')
sys.addaudithook(audit)
def handler(r):
    start=int(r.url.params['start']);calls.append(start)
    body=base.replace('<opensearch:totalResults>1</opensearch:totalResults>','<opensearch:totalResults>2</opensearch:totalResults>')
    return httpx.Response(200,headers={'Content-Type':'application/atom+xml'},content=body.encode())
request=SearchRequest.model_validate({'query':'qrels labels held_out research','sources':['arxiv'],'top_k':2,'cap_per_source':2,'year_from':None,'year_to':None})
with httpx.Client(transport=httpx.MockTransport(handler)) as client:
    with Transport(config,client=client,environ={},clock=lambda:time[0],sleeper=lambda d:time.__setitem__(0,time[0]+d)) as tr:
        out=a.search(request,tr)
        print(json.dumps({'case':'deadline_across_pages','status':out.status,'kind':out.error.kind,'calls':calls,'raw_refs':len(out.raw_references),'records':len(out.records),'deadline':tr.deadline(),'observed_time':time[0],'audit_read_count':len(reads),'offline_reads':0}))
guard[0]=False; before=json.loads((p/'before.json').read_text());after={rel:hashlib.sha256((root/rel).read_bytes()).hexdigest() for rel in before}
print(json.dumps({'final_hashes_unchanged':before==after,'count':len(after),'arxiv_sha':after['src/scholargraph/public_search/arxiv.py'],'test_sha':after['tests/unit/test_public_arxiv.py'],'repro_sha':hashlib.sha256((p/'repro.py').read_bytes()).hexdigest(),'encoding_sha':hashlib.sha256((p/'encoding.py').read_bytes()).hexdigest(),'extra_sha':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))


```

## Checkpoint kết thúc

Review hoàn tất; author vẫn idle, target không thay đổi. Coordinator xử lý F1–F7 trong report, giao sửa đúng GEMINI rồi pin commit mới cho re-review. Reviewer dừng, không claim EXT-03 DONE.

Kiểm tra sau khi ghi cả hai reports: `scripts/check_project.ps1` exit0, 53 tasks, **477** local Markdown links, 53 routes/7 lanes/79 sessions; warning SG-034 awaits SG-033 giữ nguyên. Git target HEAD vẫn `74df8db71371306d2db71a2f529308063e763e9d`, status short rỗng. `build_arxiv_query` được gọi tại arxiv.py:621 bên trong try bắt đầu dòng620, ArxivAdapterError được chuyển SourceResult failed tại719; không có risk throw helper ngoài try. F5 query mismatch là mục cần làm rõ scope, không finding bắt buộc đổi SearchRequest frozen.
