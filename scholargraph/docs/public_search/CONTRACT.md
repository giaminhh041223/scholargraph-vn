# Contract public paper search — 1.0.0

EXT-01A, SOL; bản đề nghị REVIEW, chưa freeze W0. Python schema tại
`src/scholargraph/public_search/contracts.py`; transport tại `transport.py`.
Source policy chưa audit: cả hai source giữ false, live FAIL trước mạng.
Không có adapter/store/service production được triển khai trong card này.

## Version và serialization

- `schema_version=1`, `contract_version=1.0.0`; config version `1.0.0-unverified`.
- `digest(model)` là SHA-256 JSON UTF-8 canonical: sorted keys, compact separators,
  ensure_ascii=false, NaN forbidden. Packet ghi thêm SHA-256 bytes của contract/config/code.
- Model strict, extra fields forbidden. Required nullable phải hiện diện với null;
  chỉ `refresh=false` có default sản phẩm tường minh. Bool không thay int/float.
- Thời điểm timezone-aware; wire JSON ISO8601. Đọc persisted model bằng
  `Model.model_validate_json(bytes)` để parse timestamp strict theo JSON semantics.
  Không dùng model_construct/model_copy như boundary validation.
- Năm 1800..2100 khai báo một lần YEAR_MIN/YEAR_MAX; budget 1..50.
- Contract đổi phải bump version và thông báo coordinator để sync/re-review downstream.

## Request và record

SearchRequest: query trim 1..500 ký tự, không casefold; sources nonempty/unique
openalex/arxiv, normalized sorted; required top_k, cap_per_source, year_from/year_to
(null allowed). year_from <= year_to. refresh boolean default false.

PaperRecord required: source/source_id/title/landing_url/retrieved_at/raw_sha256/parser_version.
Required nullable: abstract/publication_year/doi/arxiv_id/venue/pdf_url/license/
open_access_status/citation_count/authors. DOI normalized `10.<4..9 digits>/<suffix>`;
raw DOI được giữ trong payload mà field_provenance trỏ đến. OA enum open/closed/unknown
hoặc null khi không được nguồn cung cấp. Citation count integer >=0.
Authors null nghĩa thiếu, [] nghĩa nguồn xác nhận danh sách rỗng; authors_availability
missing/known phải khớp. Title-only hợp lệ; abstract-only thiếu title FAIL.

missing_fields liệt kê chính xác nullable fields bằng null, không trùng.
field_provenance có đúng các field hiện diện: source_id/title/landing_url và nullable
khác null. Mỗi field có ít nhất một FieldEvidence(source,source_id,raw_sha256,raw_field),
khớp nguồn/ID/hash record. URL HTTP(S), không credentials/control/backslash;
UI còn phải escape text. SourceRecord gốc được giữ trong RankedHit.source_records.
Conflict mapping trỏ các FieldEvidence bất đồng, không ghi đè raw.

## Source, fusion và envelope

SourceResult: source/status/records/error/source_total/elapsed_seconds/filter_coverage/
truncated/raw_references đều required. Nullable total/time/truncated không là số 0 giả.
- success có records, empty không có records, failed không expose records chưa hoàn tất.
- failed bắt buộc SearchError; status khác error=null. Error source phải khớp.
- not_requested bắt buộc `filter_coverage="none"`; không raw, records, total, elapsed hoặc truncation quan sát; không gọi mạng. `server`/`bounded_pool` ở trạng thái này là lỗi schema.
- Attempted source có elapsed_seconds đo từ clock, kể cả lỗi trước network.
- RawReference(raw_id,sha256,byte_count); raw_id là ID opaque, không URL/secret.
  Record hash phải tồn tại trong raw_references. Adapter parse/schema lỗi fail toàn source.
- filter_coverage server/bounded_pool/none; truncated null khi chưa xác định được.

`fuse(source_results: list[SourceResult], request: SearchRequest) -> FusionResult`
là pure function do EXT-04B triển khai, chưa có runtime import. RRF k60/rank 1-based,
one contribution/source/paper, tie canonical_id. RankedHit có canonical_id/rank/score,
display, source_records, source_ranks, conflicts. Score positive finite.

FusionCounts: raw=valid+invalid, valid=excluded_by_year+eligible,
eligible=groups+duplicate_excess, returned<=groups và returned=len(hits).
Trong snapshot, raw/valid đếm records từ source đã hoàn tất được đưa vào fusion;
failed-source payload/record chưa validate không nằm trong count này, nằm raw/error evidence.
Snapshot invalid=0; không gọi count này là tổng upstream records đã tải hay toàn web.
Adapter counters/pilot evidence phải khai báo riêng nếu đếm failed raw payloads.

SearchSnapshot có schema/contract, snapshot_id, request, config_sha256,
adapter_sha256 của đúng source selected, source_results, fusion, overall,
fetched_at/expires_at; expires>fetched. Hit records phải thuộc source_results.
Không dùng nhãn/qrels/held-out làm input; online namespace tách data core.

| Selected source states | Hits sau filter | Overall | HTTP / CLI |
|---|---:|---|---|
| empty + empty | 0 | empty | 200 / 0 |
| success + empty | >0 | success | 200 / 0 |
| success + success | 0 | empty | 200 / 0 |
| empty + failed | 0 | partial_failure | non-2xx / 1 |
| success + failed | >0 | partial_failure | non-2xx / 1 |
| failed + failed | 0 | failed | non-2xx / 1 |

Chỉ xét selected sources; missing selected result FAIL. Completed source gồm success/empty.
Envelope cùng shape mọi HTTP: schema_version/contract_version/overall/snapshot/errors/stale/cached.
Completed cần snapshot không errors; partial cần snapshot, failed trước snapshot có snapshot=null.
Errors có source khớp source failures trong snapshot; boundary errors như storage
có source=null được giữ thêm để áp dụng HTTP priority. Error kinds request/config/policy/auth/quota/timeout/
upstream/schema/storage; message nonempty, source/retry_after_seconds/record_index required nullable.
HTTP priority request 422 trước network; storage/config 500; quota 503; timeout 504;
upstream/schema/auth/policy 502. errors=[] HTTP200. Failure không cache success.

Examples executable (synthetic): `test_full_envelope_examples` chứa cả sáu case,
`test_empty_snapshot_and_failure_envelope` chứa null/failure và JSON round-trip.
Request JSON nhỏ:

```json
{"query":"graph mining","sources":["openalex","arxiv"],"top_k":10,"cap_per_source":50,"year_from":null,"year_to":null,"refresh":false}
```

## Adapter và transport signatures

```python
adapter.search(request: SearchRequest, transport: Transport) -> SourceResult
transport.deadline() -> float  # monotonic absolute, gọi một lần cho toàn request
transport.get(source, params: Mapping[str, str | int], *, deadline: float) -> TransportResponse
transport.close() -> None
```

Service EXT-05B tạo transport mỗi request với deadline pin lúc init; truyền transport cho hai
adapters. Adapter dùng cùng deadline đã được service pin (adapter/service implementation
phải giữ budget chung; không tạo deadline riêng từng page). TransportResponse:
body bytes, sha256, content_type, elapsed_seconds, attempts. TransportError.error là
SearchError; adapter bắt và trả failed. Adapter chịu JSON/Atom parse/required-field validation.
Không xem content-type/body bytes đã hợp lệ là schema nguồn đã parse.

GET chỉ endpoint allowlist config (OpenAlex works/arXiv query), không tải URL người dùng;
redirect bị từ chối, không follow. Một lock/source giữ từ trước rate wait đến hết request/retries,
khác source có thể chạy đồng thời. Service tái sử dụng một RateState (locks/next_times) qua mọi request-scoped Transport
để giữ cooldown/rate xuyên request trong **một process/owner**. RateState là process-local: chưa có distributed lock, shared quota coordinator hoặc bảo đảm politeness arXiv giữa nhiều process/máy. Đây là gap vận hành phải giải quyết trước khi scale nhiều worker/máy; MVP không được gọi rate này là cross-machine guarantee. Clock mặc định monotonic thread-safe; clock/sleeper inject
phải thread-safe nếu test nhiều source đồng thời. Rate khoảng cách start requests, deadline
bao gồm queue/rate/backoff/body. Inject wall_clock timezone-aware cho Retry-After HTTP-date.

Config bắt buộc cả hai source policy, endpoint, source_policy_verified,
policy_evidence_sha256, auth_mode/key_env, interval/timeout/max_retries/backoff/max_body_bytes/
content_types. Verified cần audit hash; đây là integrity anchor, chưa tự chứng minh policy đúng.
Auth bearer chỉ header, key_env bắt buộc; missing key/auth401/403 FAIL, không anonymous fallback.
Params secret names bị cấm; params httpx encoding; không log URL/raw error/header/key.
Exception messages fixed, raw upstream body chỉ giữ evidence do adapter/store quản lý.

Retry 429/500/502/503/504 và timeout/network errors; <=2 retries. Retry-After integer seconds
hoặc HTTP-date; malformed/duplicate FAIL schema. Không cắt upstream wait; vượt deadline FAIL
với retry info. Cooldown vẫn được giữ sau failure; future requests không bypass quota wait.
Response HTTP200 bắt buộc approved Content-Type, bounded decoded bytes, nonempty body;
Content-Length nếu có phải hợp lệ/capped. Parser adapter xử lý JSON/Atom malformed.
Close chỉ client transport tự tạo; injected client do caller đóng.

## Store contract — đề nghị MUSE review trước EXT-04A

Signatures trong PublicStore Protocol là typing-only, không stub implementation.
Module MUSE `store.py` xuất:

```python
initialize_store(project_root: Path, config: PublicSearchConfig) -> PublicStore
open_existing(project_root: Path, config: PublicSearchConfig) -> PublicStore
store.load_cache(cache_key: str, *, now: datetime) -> SearchSnapshot | None
store.save_snapshot(snapshot: SearchSnapshot, raw_payloads: dict[str, bytes], *, cache_key: str) -> None
store.read_snapshot(snapshot_id: str) -> SearchSnapshot
store.save_paper(snapshot_id: str, canonical_id: str, *, now: datetime) -> LibraryEntry
store.list_library(*, offset: int, limit: int) -> list[LibraryEntry]
store.export_library(format: Literal["json", "bibtex"]) -> bytes
store.close() -> None
```

LibraryEntry canonical_id/snapshot_id/saved_at/hit/incomplete_sources; ID phải khớp hit,
partial snapshot badge incomplete_sources=true. Pagination offset>=0, limit 1..100;
unknown snapshot/hit, invalid paging/format FAIL structured storage/request error,
không None/empty giả. Store errors dùng SearchError envelope qua boundary service.

Resolved data_root dưới project `data/public_search/...`, không symlink escape/core.
DB `library.sqlite3`, marker `store.json`, raw `raw/<raw_id>` (ID safe basename do store validate).
Marker schema_version/contract_version/config_sha256; DB metadata phải khớp.
Init tạo directory/schema/marker tường minh; fresh store không cần raw chưa referenced.
Normal service open_existing không tạo DB/marker; mất DB ở directory có evidence FAIL,
init cũng không rebuild. Init idempotent chỉ store hợp lệ; schema/hash corruption FAIL.

save_snapshot: dict raw_id -> exact bytes, keys đúng raw_references, verify byte counts/hash.
Persist raw atomic rồi DB snapshot + cache pointer trong một transaction. Không ghi đè
snapshot ID/raw ID khác bytes; rollback không để pointer/dangling DB reference. Raw orphan
sau crash được giữ evidence, không referenced; thiếu referenced raw khi read/save/library FAIL.
Failed/partial snapshot lưu evidence nhưng không đổi cache pointer. Completed success/empty
được cache; valid empty là successful completed request. Refresh failure giữ pointer cũ.
Không upsert làm mất provenance; duplicate save_paper trả existing identical LibraryEntry.
Export đọc validated library/raw, JSON UTF-8 hoặc BibTeX escaped; không gọi mạng.

load_cache trả None chỉ key không có hoặc hết TTL. Mismatch schema/hash/missing raw FAIL,
không None. read_snapshot trả snapshot cũ theo ID, service tính stale theo expires_at khi mở.
Cache key `cache_key(request, config, adapter_sha256)` gồm schema/contract/config digest,
query sau trim/source sorted/year/top_k/cap và selected adapter hashes. Refresh không trong key.
refresh=true bypass lookup, gọi nguồn và tạo snapshot mới; không trả cũ như success khi lỗi.

## Kiểm chứng và giới hạn

Boundary executable: `python -m scholargraph.public_search.contracts --config <file> --request <file>`.
Chỉ validate inputs, không search production. Required-file/schema lỗi exit1;
valid request exit0 không đồng nghĩa nguồn live hoạt động. Production CLI recheck EXT-05B/06.
Unit tests mock/synthetic; không source live, không core dataset/model API, không metric relevance.
Parent config đã nhập audit hash và bật source policy verified cho anonymous MVP; delta chưa được MUSE review, chưa freeze store signatures,
chưa claim reviewer PASS hoặc EXT-01A DONE. Card tiếp theo chỉ sau deps và dispatch coordinator.
