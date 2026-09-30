# Log re-review SOL — EXT-03 W1 R4 081

- Ghi lúc 2026-09-30T14:55:23.415743+07:00; verdict CHANGES_REQUIRED với 2 P2 R4-F1/R4-F2. Report: management/public_search/reviews/SOL/EXT-03-W1-R4-081.md.
- Reused original reviewer context /root/review_w1_arxiv_081, không fresh context mới; requested gpt-6.1-sol/high, actual model alias/effort unknown theo context metadata khả dụng.
- Target read-only đối với reviewer, HEAD 095150c48b5fbf4cb46ff2f3af9aa4b3436dea16; Git status short rỗng lúc bắt đầu. Cuối lượt có untracked storage review outputs `scholargraph/management/public_search/logs/GEMINI/REVIEW-EXT-04A-W1-081.md` và `scholargraph/management/public_search/reviews/GEMINI/` của reviewer khác. 41 scoped snapshot hashes vẫn bất biến. Python parent 3.12.14/import arxiv đúng target như raw results.
- 41 target hashes trước/sau giống nhau: 37 original target files + 4 R4/R4-CLOSE packet/log files; cả14 W0 freeze pins khớp. Không sửa code/tests/config/board/git. Chỉ ghi hai report/log mới và TEMP.
- R3 parent review report SHA2566623c3088509a76e8d2bad1385b7da696e74c5bcd19d8a9d0c97bef96e8850f3; log SHA2561563d803af658adbb669d0fe36243b381c887c17a9a5d0d72917a63e06784584, vẫn khớp; không đổi lịch sử.
- ADR020 accepted: CLI request schema/payload-only, không compile query; UTF32unsupported/FAIL rõ. Giữ frozen contract. Target whitespace-only cleanup dòng909 đã bao phủ trong reviewer67focusedtests.
- Author provenance:2 runs INTERNAL500 sau ghi files vẫn FAIL; fresh author closeout run b30fd17d/session11c38d90-0129-46e0-80fb-c0777cd0cdcc PASS theo coordinator. Author NOT_RUN cho tests khác coordinator/reviewer67passed thật. Không suy author runtime/model metadata từ routing.
- 0 live API, 0 credentials/labels/qrels/offline datasets đọc, không install dependencies. HTTP dùng httpx.MockTransport, fixtures synthetic mới trong TEMP.

## Commands/exit kết quả thực

```powershell
$env:PYTHONPATH='D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/src'
$env:PYTHONDONTWRITEBYTECODE='1'
# cwd target nested project
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe -m pytest tests/unit/test_public_arxiv.py -q -p no:cacheprovider
# exec session91418 exit0:67passed,0failed,15.35s
# TEMP scripts bên dưới, mỗi lệnh exit0 ở collector
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-r4-081/repro.py
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-r4-081/encoding.py
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-r4-081/r4-probes.py
D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe C:/Users/ADMIN/AppData/Local/Temp/sg-ext03-sol-review-r4-081/extra.py
```

- Collector exits0 chỉ nghĩa thu results thành công. 22/22 parser old probes đúng expected,12/12CLI old probes đúng exit expected,0secret leaks. Standard encoding6cases:UTF16BOM/LE/BE VALIDATED/CLI0;UTF32BOM/LE/BE unsupported/schema/CLI1. Duplicate title CLI1.
- Positive probes giữtitle-only/Error-title/Error-correction/barelink/PDF type-only; arbitraryID/offhost/v0/root/missingrequired fail. F5 query grammar string CLI0 là đúng approvedscope; không gọi đó livepass. Các declaration utf-16-le/be exploratory không được dùng cho claimpositiveUTF16; standard declarationUTF16 mới là evidence.
- Rawlink selectors phản ánh atom:link[href] và type=application/pdf; related URL containinglicense→None/missing; explicit rellicense→known/provenance correct.
- Real Transport paging/order/source_total/truncated/deadline/rate/state nonselected giữ đúng; deadline2s/interval3s→failedtimeout,records0,rawref1;openaudit sentinel trong search0reads/0offline reads.
- New7probes:3CLIrequesterrors đềuexit1/FAIL nhưngschema-type vàJSONsyntax bị message sai duplicatekey;2malformedIDportURL CLI0 sai;2licensecases đúng. R4-F1/R4-F2 cầnauthor sửa, không broaden tests tiếp.

## Script/output SHA256

- `repro.py` SHA-256 `6ac328087782cca829e7b7ec3c928d17e6d9a6e9c507265b0c69dffae18d33c8`.
- `encoding.py` SHA-256 `4147c5805921cf13cb436313808f93004f8a30dec840c0127241025a27fcb23e`.
- `extra.py` SHA-256 `041cfa67a6e614d5f10c8338465014757bd3d1de7f9a150a9a4ae9772c621271`.
- `r4-probes.py` SHA-256 `20098a0b456eaea239b56b81fde69667e68f50ee8157c48894dc0ffb956e838d`.
- `results.jsonl` SHA-256 `64899f466d3fcde3d3c7a2bd22027d072c65a7ce60bde5f36f08138ad4f77c79`.
- `encoding-results.jsonl` SHA-256 `b0e1c6f1cae0ef4a0789de56e9631402eb8996fa974df7196a852fb83003396f`.
- `extra-results.jsonl` SHA-256 `c0d9911c56c5d219b15fd4d251eda18d654d10f0ef932fd76dae0270a8587603`.
- `r4-probes-results.jsonl` SHA-256 `4c0fb8117d7fafc6c5984aa70d400b8f1727707ddbbc2cbeb5828b6cbb43470a`.

## Target manifest41files (trước = sau)

```json
{
  "management/public_search/logs/GEMINI/EXT-03-W1-081.md": "601bc9457894ab48659c3eec1242216763d70b7a940a37f1c154c191ab96c805",
  "management/public_search/logs/GEMINI/EXT-03-W1-R2-081.md": "175c8c97d0e3059386b57651a2dc9059294dd6833d0360e05b89fa012efce98b",
  "management/public_search/logs/GEMINI/EXT-03-W1-R3-081.md": "625f288409c2c64e2dd46d685d452e61dcdfe0972e7ce2c46f178ff74f03b093",
  "management/public_search/logs/GEMINI/EXT-03-W1-R4-081.md": "f6362579dd6aad6f012c851e659de9e348543eefcfaabd8a0360ac558bafccaf",
  "management/public_search/logs/GEMINI/EXT-03-W1-R4-CLOSE-081.md": "1795d4bbc74701ea691f3ce0d3a28f2f50b950a42cfa56b2bd98c55ac5191a0b",
  "management/public_search/packets/GEMINI/EXT-03-W1-081.md": "d3df5bfdf805921f9212ca11b884e6307c0cb9c0ac2d209290abcf1c7c02443e",
  "management/public_search/packets/GEMINI/EXT-03-W1-R2-081.md": "376a25cca8147488a15781ff3229c20a19b639e974e973ccb97f2dbd2e5d45d4",
  "management/public_search/packets/GEMINI/EXT-03-W1-R3-081.md": "60d2c29ad37294f7dbda74366e0bf3354d9161e48f4d2bdf939c606d8c26d7e7",
  "management/public_search/packets/GEMINI/EXT-03-W1-R4-081.md": "66f8805088809c378534ed6cb2a13877e77eb6480fb21a55950813b75d263f64",
  "management/public_search/packets/GEMINI/EXT-03-W1-R4-CLOSE-081.md": "bdbf530cbe2529e32418d1edf1722fe58de94529f5324e083818d9a8b385373b",
  "src/scholargraph/public_search/arxiv.py": "02f09b0733f8697d9942ea7a611f75dac9842a08da5f630b1a729e538e6d1af2",
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
  "tests/unit/test_public_arxiv.py": "0689dcea263a486010daf48f3a890439b19133c6808d8f863692a63f3c981d2a",
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

## Rawresults results.jsonl

```jsonl
{"import_path": "D:\\Web_mining_20261\\scholargraph\\.worktrees\\public-gemini\\scholargraph\\src\\scholargraph\\public_search\\arxiv.py", "python": "D:\\Web_mining_20261\\scholargraph\\.venv\\Scripts\\python.exe", "python_version": "3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]", "freeze14_matches": true}
{"case": "valid_title_only", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "missing_id", "expected": "schema", "actual": "schema", "pass": true, "message": "entry must contain exactly one atom:id"}
{"case": "abstract_only_missing_title", "expected": "schema", "actual": "schema", "pass": true, "message": "entry has empty title after normalization"}
{"case": "bad_xml", "expected": "schema", "actual": "schema", "pass": true, "message": "malformed XML payload"}
{"case": "non_atom_root", "expected": "schema", "actual": "schema", "pass": true, "message": "root element must be Atom feed, got {http://www.w3.org/2005/Atom}notfeed"}
{"case": "arbitrary_id", "expected": "schema", "actual": "schema", "pass": true, "message": "entry has invalid arXiv ID format"}
{"case": "foreign_host_id", "expected": "schema", "actual": "schema", "pass": true, "message": "entry id URL host is not arXiv"}
{"case": "invalid_version_zero", "expected": "schema", "actual": "schema", "pass": true, "message": "entry has invalid arXiv ID format"}
{"case": "real_paper_title_Error", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "real_paper_summary_Error", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "error_feed", "expected": "upstream", "actual": "upstream", "pass": true, "message": "arXiv upstream query error entry detected"}
{"case": "valid_utf-8", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[rel=alternate]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id"}}
{"case": "dtd_utf-8", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-16-le", "expected": "schema", "actual": "schema", "pass": true, "message": "malformed XML payload"}
{"case": "dtd_utf-16-le", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-16-be", "expected": "schema", "actual": "schema", "pass": true, "message": "malformed XML payload"}
{"case": "dtd_utf-16-be", "expected": "schema", "actual": "schema", "pass": true, "message": "XML DOCTYPE declaration forbidden"}
{"case": "valid_utf-32-le", "expected": "schema", "actual": "schema", "pass": true, "message": "unsupported XML declared encoding: UTF-32 is not supported"}
{"case": "dtd_utf-32-le", "expected": "schema", "actual": "schema", "pass": true, "message": "unsupported XML declared encoding: UTF-32 is not supported"}
{"case": "valid_utf-32-be", "expected": "schema", "actual": "schema", "pass": true, "message": "unsupported XML declared encoding: UTF-32 is not supported"}
{"case": "dtd_utf-32-be", "expected": "schema", "actual": "schema", "pass": true, "message": "unsupported XML declared encoding: UTF-32 is not supported"}
{"case": "link_selectors", "expected": "VALIDATED", "actual": "VALIDATED", "pass": true, "ids": ["2401.00001v1"], "provenance": {"title": "atom:title", "source_id": "atom:id", "landing_url": "atom:link[href]", "abstract": "atom:summary", "publication_year": "atom:published", "arxiv_id": "atom:id", "pdf_url": "atom:link[type=application/pdf]"}}
{"case": "cli_no_args", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_missing_payload", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_missing_request", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_bad_xml", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_invalid_type", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_label_leakage_field", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_out_of_range", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_secret_error", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_duplicate_json", "expected_exit": 1, "actual_exit": 1, "pass": true, "fail_marker": true, "traceback": false, "secret_leaked": false}
{"case": "cli_bad_arxiv_query", "expected_exit": 0, "actual_exit": 0, "pass": true, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "cli_valid", "expected_exit": 0, "actual_exit": 0, "pass": true, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "cli_benign_query", "expected_exit": 0, "actual_exit": 0, "pass": true, "fail_marker": false, "traceback": false, "secret_leaked": false}
{"case": "real_transport_paging", "status": "success", "ids": ["2401.00001v1", "2401.00002v1"], "source_total": 2, "truncated": false, "calls": [{"start": 0, "time": 100.0, "query": "all:(held_out labels and qrels in public retrieval research)"}, {"start": 1, "time": 103.0, "query": "all:(held_out labels and qrels in public retrieval research)"}], "deadline": 130.0, "elapsed": 3.0}
{"case": "nonselected", "status": "not_requested", "call_count": 2}
{"case": "shared_rate_second_search", "status": "success", "call_time": 106.0}
{"target_hashes_unchanged": true, "file_count": 41, "parse_pass": 22, "parse_fail": 0, "cli_exit_pass": 12, "cli_exit_fail": 0, "cli_secret_leaks": 0}

```

## Rawresults encoding-results.jsonl

```jsonl
{"case": "utf-16", "parse": "VALIDATED", "cli_exit": 0, "traceback": false}
{"case": "utf-16-le", "parse": "VALIDATED", "cli_exit": 0, "traceback": false}
{"case": "utf-16-be", "parse": "VALIDATED", "cli_exit": 0, "traceback": false}
{"case": "utf-32", "parse": "schema:unsupported XML declared encoding: UTF-32 is not supported", "cli_exit": 1, "traceback": false}
{"case": "utf-32-le", "parse": "schema:unsupported XML declared encoding: UTF-32 is not supported", "cli_exit": 1, "traceback": false}
{"case": "utf-32-be", "parse": "schema:unsupported XML declared encoding: UTF-32 is not supported", "cli_exit": 1, "traceback": false}
{"case": "duplicate_conflicting_title", "cli_exit": 1}

```

## Rawresults r4-probes-results.jsonl

```jsonl
{"case": "schema_type", "exit": 1, "stderr": "FAIL: invalid request JSON: duplicate keys detected", "traceback": false}
{"case": "malformed_json", "exit": 1, "stderr": "FAIL: invalid request JSON: duplicate keys detected", "traceback": false}
{"case": "duplicate_keys", "exit": 1, "stderr": "FAIL: invalid request JSON: duplicate keys detected", "traceback": false}
{"case": "invalid_port", "exit": 0, "valid": true, "traceback": false}
{"case": "port_out_of_range", "exit": 0, "valid": true, "traceback": false}
{"case": "related_license_unknown", "license": null, "missing": true, "raw_field": null}
{"case": "explicit_license", "license": "https://publisher.invalid/license", "missing": false, "raw_field": "atom:link[rel=license]"}

```

## Rawresults extra-results.jsonl

```jsonl
{"case": "cli_arbitrary_id", "exit": 1, "fail": true, "traceback": false}
{"case": "cli_wrong_root", "exit": 1, "fail": true, "traceback": false}
{"case": "cli_benign_error_abstract", "exit": 0, "fail": false, "traceback": false}
{"case": "deadline_across_pages", "status": "failed", "kind": "timeout", "calls": [0], "raw_refs": 1, "records": 0, "deadline": 102.0, "observed_time": 100.0, "audit_read_count": 0, "offline_reads": 0}
{"final_hashes_unchanged": true, "count": 41, "arxiv_sha": "02f09b0733f8697d9942ea7a611f75dac9842a08da5f630b1a729e538e6d1af2", "test_sha": "0689dcea263a486010daf48f3a890439b19133c6808d8f863692a63f3c981d2a", "repro_sha": "6ac328087782cca829e7b7ec3c928d17e6d9a6e9c507265b0c69dffae18d33c8", "encoding_sha": "4147c5805921cf13cb436313808f93004f8a30dec840c0127241025a27fcb23e", "extra_sha": "041cfa67a6e614d5f10c8338465014757bd3d1de7f9a150a9a4ae9772c621271"}

```

## Reproducer repro.py

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
    return f'<?xml version="1.0" encoding="UTF-8"?><{rootname} xmlns="{NS}" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><id>https://arxiv.org/api/synthetic-feed</id><title>Synthetic feed</title><updated>2024-01-01T00:00:00Z</updated><opensearch:totalResults>{total}</opensearch:totalResults><opensearch:startIndex>{start}</opensearch:startIndex><opensearch:itemsPerPage>{items}</opensearch:itemsPerPage>{e}</{rootname}>'
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
    parsecase('valid_'+enc,raw,'schema' if '32' in enc or enc in ('utf-16-le','utf-16-be') else 'VALIDATED')
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
p=tmp/'bad_query.json'; p.write_text(json.dumps(dict(reqdata,query='ti:(broken'))); cli('cli_bad_arxiv_query',['--payload',str(valid),'--request',str(p)],expected=0)
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

## Reproducer encoding.py

```python
import hashlib, json, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone
from scholargraph.public_search import arxiv as a
p=Path(__file__).parent
ns='http://www.w3.org/2005/Atom'
base=f'<?xml version="1.0" encoding="UTF-16"?><feed xmlns="{ns}" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><id>https://arxiv.org/api/synthetic-feed</id><title>Synthetic feed</title><updated>2024-01-01T00:00:00Z</updated><opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage><entry><id>https://arxiv.org/abs/2401.00001v1</id><title>A valid paper</title><link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/></entry></feed>'
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

## Reproducer r4-probes.py

```python
import hashlib,json,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from scholargraph.public_search import arxiv as a
p=Path(__file__).parent;base=(p/'valid.xml').read_text()
req={'query':'valid','sources':['arxiv'],'top_k':2,'cap_per_source':2,'year_from':None,'year_to':None}
for name,value in [('schema_type',json.dumps(dict(req,top_k=True))),('malformed_json','{"query":'),('duplicate_keys','{"query":"a","query":"b"}')]:
    f=p/(name+'.json');f.write_text(value)
    r=subprocess.run([sys.executable,'-m','scholargraph.public_search.arxiv','--payload',str(p/'valid.xml'),'--request',str(f)],capture_output=True,text=True)
    print(json.dumps({'case':name,'exit':r.returncode,'stderr':r.stderr.strip(),'traceback':'Traceback' in r.stderr}))
for name,id in [('invalid_port','https://arxiv.org:not-a-port/abs/2401.00001v1'),('port_out_of_range','https://arxiv.org:99999/abs/2401.00001v1')]:
    f=p/(name+'.xml');f.write_text(base.replace('https://arxiv.org/abs/2401.00001v1</id>',id+'</id>'))
    r=subprocess.run([sys.executable,'-m','scholargraph.public_search.arxiv','--payload',str(f)],capture_output=True,text=True)
    print(json.dumps({'case':name,'exit':r.returncode,'valid':r.returncode==0,'traceback':'Traceback' in r.stderr}))
for name,link in [('related_license_unknown','<link href="https://publisher.invalid/license" rel="related"/>'),('explicit_license','<link href="https://publisher.invalid/license" rel="license"/>')]:
    body=base.replace('</entry>',link+'</entry>').encode()
    r=a.parse_feed_payload(body,0,datetime.now(timezone.utc),hashlib.sha256(body).hexdigest())[-1][0]
    print(json.dumps({'case':name,'license':r.license,'missing':'license' in r.missing_fields,'raw_field':r.field_provenance['license'][0].raw_field if r.license is not None else None}))

```

## Reproducer extra.py

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

## Handoff

OriginalF1–F7 reproducerfixes đạt ADR020 scope; haiP2 R4-F1/R4-F2 cònmở. Coordinator giaoGemini sửaexceptiondiagnosis vàIDURLport validation, thêmregression,pincommitnew,re-review focused. Reviewer dừng, không claimEXT03DONE.

Kiểm continuity cuối lượt: parent `./scripts/check_project.ps1` exit1; `FAIL: Broken link in EXT-03-W1-081.md: ../../../docs/PUBLIC_PAPER_SEARCH_TASKS.md`. Tra đúng file `management/public_search/logs/GEMINI/EXT-03-W1-081.md:17`; đường dẫn thiếu một level. Log Gemini ngoài quyền ghi reviewer, đã báo coordinator. Không thay file đó, không claim checker PASS. HEAD target giữ nguyên; scoped 41 hashes/14 W0 pins không đổi. Giữ report/log R3 đóng trước bất biến.
