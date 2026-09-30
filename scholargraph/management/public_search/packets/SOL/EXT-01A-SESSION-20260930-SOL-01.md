# EXT-01A — SOL — đề nghị REVIEW

- Session thực thi SESSION-20260930-SOL-01; dispatch DISPATCH-20260930-W0-SOL.
- Chat 01a0efcc-2062-7d01-b687-10d249b56cbe; actual model/effort unknown.
- Checkout D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph;
  branch codex/public-search-sol; base 46328b2be70d17c644fe3351724a5c9f8702eb35.
- Implementation head **30434f0c173ec6fdef01f367a3fe783e427d438f**, commit trước dd6ec4ec251c321d179b6f7fde41266770ac7d46.
  Commit packet/log sau đó không đổi code review. Không merge/push parent.
- Contract1.0.0/schema1/config1.0.0-unverified; canonical config SHA256 65cc0ce4d28a1947d9af74353f49f301d7fb9adf074d67620896d844218b33d8.

## Owned outputs và SHA256 bytes

- `docs/public_search/CONTRACT.md`: `b71cb186b2680946923d36bf750744ba2f658f91bcec5e4694f30d5e865ee6ca`
- `configs/public_search.json`: `9f2069f22cdfffa6021cb480a756b994663636820579cf31cbe02672ea4e5ce2`
- `src/scholargraph/public_search/__init__.py`: `048597a431e3739e6b0b8138bfeb19b8cb05072cd900f34b889a693887d3fab4`
- `src/scholargraph/public_search/contracts.py`: `6a9a3d464dc7e8b68661ced95122515809ca77b916f602c107b963e02845878c`
- `src/scholargraph/public_search/transport.py`: `a775b1e99c2dc64d4b6f523567a6543d1b536deed35c255a1b66c894e3607baf`
- `tests/unit/test_public_contracts.py`: `a8fc4ca046748c3bb498e23e5c6889adfd25e497fa239f6ba7504d290b599720`
- `tests/unit/test_public_transport.py`: `c8688c1edfb4eb34b94352931a8d4145506c2f04dcaa8f02aaac8834fd020317`
- `requirements.lock`: `b68fcdc47fdbc67460e8384087e0fde8d62fc8fe820a6cf9b220283e0298d57d`

## Inputs và symbols

Inputs: AGENTS/core governance/protocol, plan/cards, root dispatch/board, API app/service
và ingest OpenAlex đã đọc. Không đọc labels/qrels/held-out/data core; không sửa frozen downloader.
Outputs: strict SearchRequest/PaperRecord/FieldEvidence/SourceResult/SearchError/RawReference,
RankedHit/FusionCounts/FusionResult/SearchSnapshot/SearchEnvelope/LibraryEntry,
PublicSearchConfig/SourcePolicy, typing-only PublicAdapter/PublicStore;
load_config/read_json/digest/cache_key/overall_status/error_http_status.
Transport/RateState/TransportError/TransportResponse: fixed shared-request deadline,
source locks/rate/cooldown across requests, auth header, endpoint allowlist, cap/retry/redaction.
CONTRACT.md mô tả exact proposed adapter/fusion/store/lifecycle signatures, refresh/key,
overall truth table, executable synthetic examples. Không import implementation chưa có.

## Lệnh và kết quả thật

Tại project SOL, mỗi shell phải set PYTHONPATH riêng:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
& 'D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe' -m pytest tests/unit/test_public_contracts.py tests/unit/test_public_transport.py -q
./scripts/check_project.ps1
git diff --cached --check
```

- Pytest cuối trên implementation head **108 passed in 1.63s**, exit0.
- Python executable root .venv như lệnh; scholargraph.__file__ ở SOL/src/scholargraph/__init__.py;
  httpx0.28.1, pydantic2.13.5. Không install/đổi lock. Lock bytes hash ở trên.
- Whitespace check sau normalize LF exit0. Chỉ owned paths commit.
- Continuity **FAIL exit1, 51 issues**: missing core artifacts/data và lecture links
  không có trong worktree. Không claim full-project PASS; cần environment core đầy đủ
  để coordinator kiểm gate. Không copy/fake artifacts để bypass.
- Lịch sử failed checks và sửa ghi trong log cùng session (timestamp guard, fixture MIME,
  UTF8 helper, missing PYTHONPATH helper, CRLF). Shell overall exit0 không chứng minh helper pass.

## Adversarial và leakage

- tmp_path: config/file/source/required key thiếu, duplicate JSON/NaN/unsafe data root;
  persisted title-only PASS, missing title/abstract-only/wrong format FAIL.
- Schema: required-null, bool-as-int, invalid years/DOI/count identities,
  NaN/Inf scores, unsafe URLs, missing provenance/raw hash, error/status mismatch.
- Sáu overall cases được kiểm cả function lẫn full snapshot/envelope JSON round-trip.
- Subprocess boundary module: valid config/request exit0; missing config, malformed
  request, duplicate config JSON exit1. Đây là validator, chưa production search CLI;
  CLI thật phải recheck tại EXT-05B/06, không gọi fixture là production.
- HTTP mocked: 401/403 không retry/fallback, 429 numeric/date quá deadline FAIL,
  malformed headers, oversized stream, timeout bounded retries, redirect FAIL,
  param encoding/secrets redaction, concurrent same-source serialization,
  retained cooldown và shared RateState across requests.
- Synthetic label/held-out sentinel ở tmp_path; Path.open instrumentation ở load/cache
  chỉ đọc config và không mở qrels sentinel. Full split/integration leakage audit
  NOT_RUN, EXT-06 xử lý; không suy unit boundary thành full leakage certification.

## Gate còn mở và bước tiếp theo

Live sources/model API, latency/pilot/relevance, offline full regression, storage transaction
chưa chạy. Tất cả HTTP fixtures synthetic, không source live evidence. EXT-01B audit/policy delta
chưa nhận: cả hai source_policy_verified=false, live FAIL trước mạng. Store signatures cần
MUSE review, chưa PASS/freeze. W0 chỉ chốt sau policy delta và review ba outputs.

Đề nghị coordinator chuyển REVIEW và giao MUSE review đúng head trên; chưa tự sửa board/DONE
hoặc mở EXT-02. Không process dài do SOL khởi chạy còn lại. Next executable: MUSE rerun hai
unit files và boundary/auth/quota repro; findings giao SOL sửa owned paths, version delta
nếu đổi contract, commit/packet/re-review mới. Log: management/public_search/logs/SOL/SESSION-20260930-SOL-01.md.
