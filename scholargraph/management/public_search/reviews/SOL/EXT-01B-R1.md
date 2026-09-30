# Review độc lập EXT-01B — R1

- Verdict: **CHANGES_REQUIRED**. Có 1 P1 và 3 P2 vi phạm acceptance; chưa đủ gate W0. Không chuyển task DONE.
- Assignment: `REV-W0-01B-R1-SOL`; session `/root/review_source_audit_r1`; reviewer runtime được giao `gpt-6.1-sol`, effort `high`, context review mới. Model/effort implementation MUSE vẫn **unknown**.
- Thời điểm: `2026-09-30T09:13:00+07:00`.
- Checkout reviewer: `D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph`, branch `codex/public-search-sol`, base trước review `93f8c75e7599a96598f36421254608f3ccb081fc`.
- Target implementation pin: `8cee172edd2b295b95ec06323efbb6b900a11371`, branch `codex/public-search-muse`, checkout `D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph`. Report/log mới của reviewer khác trong MUSE không thuộc review này.
- Phạm vi đọc: root AGENTS/state/HANDOFF/tasks/routing/registry/decisions/protocol; extension board/card/plan/dispatch; SOURCE_AUDIT, JSON audit, packet MUSE, manifest và toàn bộ 6 raw/meta files. Chỉ grep auth trong prior-art ingest. Không đọc labels/qrels/frozen benchmark, không gọi live search API và không sửa implementation/board.

## Findings

### F1 — P1: SHA arXiv trong JSON audit sai

**Path:** `artifacts/reports/public_search/muse/source_audit.json:1`, JSON pointer `/sources/arxiv/live_probe/sha256`.

Chuỗi khai báo là `e38e577822f80ed9e8555322c5865e34ecc60b604a4e448efbf6b779ecc4e3b86494`, dài **68** hex; SHA-256 thực tế của raw 4.457 bytes là `e38e577822f80ed9e8555322c5865e34ecc60b604a2af1bd767effa08535254c`. MANIFEST và arxiv meta cùng khớp hash thực tế. JSON máy đọc vì thế không truy ngược được về evidence nó tuyên bố; JSON syntax pass không phải integrity pass.

**Reproducer:** `Get-FileHash data/public_search/muse/source_pilot/arxiv_search.body -Algorithm SHA256` tại checkout MUSE rồi đối chiếu pointer trên. Reviewer-validator subprocess trên copy nguyên trạng trả **1**, stderr `FAIL audit arxiv_search sha256`. Copy synthetic chỉ sửa hash này trả **0**; tác giả/raw gốc chưa bị sửa.

**Next fix:** tính hash từ raw bằng cùng routine dùng để tạo manifest, sửa JSON và thêm regression đối chiếu audit ↔ meta ↔ manifest ↔ bytes. Không thay raw để khớp hash sai.

### F2 — P2: Auth delta tạo gate keyed probe không có căn cứ

**Paths:** `docs/public_search/SOURCE_AUDIT.md:21`, `:49`, `:52`, `:57`; `source_audit.json:1` các trường `auth_delta`, `proposals`, `unverified`; packet MUSE các đoạn keyed auth blocker.

Audit suy từ API overview rằng Bearer chưa rõ, yêu cầu user key và keyed probe trước EXT-02. Trang [OpenAlex Authentication](https://help.openalex.org/api/authentication/) hiện xác nhận **cả `api_key` parameter và Authorization Bearer hoạt động giống nhau** (Sending your key, dòng web 34–42, cập nhật 2026-08-19). Prior-art Bearer không mâu thuẫn docs. Anonymous 200 đã có trong raw, nên tạo tài khoản/key không phải điều kiện để nghiệm thu source audit. Một 429 rồi 200 chưa chứng minh pilot nhất thiết cần key hoặc giảm scope.

**Reproducer:** đọc official Authentication trên và đối chiếu audit dòng 21–24. Keyed runtime và sustained anonymous throughput chưa đo là giới hạn hợp lệ; scheme được docs hỗ trợ là fact đã xác minh.

**Next fix/policy delta:** ghi hai scheme được hỗ trợ, lựa chọn scheme/redaction cho SOL; phân biệt documented auth và keyed live untested. Giữ downstream pilot trong budget/deadline, tôn trọng 429 và FAIL khi hết deadline. Key là lựa chọn người dùng nếu thực sự cần, không điều kiện giả của review.

### F3 — P2: Retry timing/headers/auth/request provenance không đủ để tái kiểm

**Paths:** `data/public_search/muse/source_pilot/openalex_retry.meta.json:1`; `docs/public_search/SOURCE_AUDIT.md:5`, `:16`, `:17`, `:35`; packet MUSE đoạn “Retry-After honored”.

Retry meta chỉ có status, elapsed duration, bytes/hash, retry_after null và remaining; thiếu URL/method/request auth mode, response headers/date, start/end/wait timestamps. Manifest chỉ hash file, không bổ sung dữ kiện còn thiếu. `elapsed_s=1.939` không chứng minh đã chờ 40 s sau Retry-After 33. `remaining="990"` không giữ được header gốc để kiểm units/limit/reset/cost hoặc việc redaction. Hai response khác có server Date 00:57:20 và 00:57:25 UTC; chúng không xác lập thứ tự/timing của retry. “4 s gap” là lời tác giả kể, không timestamp client được lưu.

**Reproducer:** đọc toàn bộ 8 dòng retry meta; chỉ có các keys nêu trên. Hai URLs được lưu cho 429/arXiv; retry request URL/auth không được lưu. OpenAlex payload `meta.x_query.url` mô tả query server, không chứng minh client header/key hay wait.

**Next fix:** tìm log/capture gốc nếu còn để bổ sung provenance và tính chênh lệch thời gian; tuyệt đối không dựng timestamp/headers đã mất. Nếu không còn, hạ các timing/header/auth statements thành author-reported/unverified và ghi rõ giới hạn. Lần capture sau lưu request identity, redacted headers, auth mode, client times và retry wait tường minh. Audit phải liệt kê filter/paging đã quan sát (first page) và phần chỉ có docs/chưa chạy; không cần reviewer gọi thêm API cho R1.

### F4 — P2: Narrative nói đã verified DOI arXiv dù 0/2 entries có DOI

**Path:** `docs/public_search/SOURCE_AUDIT.md:37`–`:38`.

Toàn bộ payload có 2 entries, **0** `arxiv:doi`, 2 `arxiv:journal_ref` và 2 `arxiv:primary_category`. DOI là field được docs mô tả, chưa xuất hiện trong pilot; gộp nó vào “entry fields verified” không khớp 1:1 với dữ liệu. Không được điền DOI giả hoặc suy DOI từ title.

**Reproducer:** parse Atom namespace `http://arxiv.org/schemas/atom`, đếm `entry/arxiv:doi`; kết quả 0. Hai DOI lookups đều null/absent.

**Next fix:** ghi coverage explicit và phân loại DOI documented/unobserved. Các field có thật được giữ ở verified; optional thiếu vẫn được chấp nhận, không gọi lỗi record.

## Evidence và phép tái đếm

| Evidence | Kết quả thực tế |
|---|---|
| MANIFEST ↔ toàn 6 raw/meta files | 6/6 SHA-256 khớp; raw gốc chưa bị đổi |
| OpenAlex 429 | 253 bytes; status 429; JSON `retryAfter=33`; header `retry-after=33` |
| OpenAlex 200 | 101.458 bytes; 3 works; `meta.count=976071`, `page=1`, `per_page=3`, `cost_usd=0.001` |
| OpenAlex coverage toàn 3 works | 3 ID/title/year/DOI/authorships/non-null abstracts; authors 5+6+9=20; abstract positions 149+169+157=475; references 123+174+511=808 |
| arXiv 200 | 4.457 bytes; Atom feed; 2 entries; totalResults 186833, startIndex 0, itemsPerPage 2 |
| arXiv coverage toàn 2 entries | 2 ID/title/published/updated/summary/category/primary_category/journal_ref; authors 8+2=10; 2 HTML và 2 PDF links; DOI 0/2 |
| Request counters | 3 represented captures = OpenAlex 2 + arXiv 1; status 200×2 + 429×1; 5 returned records total, không phải toàn bộ 976071+186833 matches |
| Filter/paging/auth evidence | 429 URL search `graph neural networks`, per-page 3; arXiv all:electron, start 0, max_results 2. Không year filter/second page/keyed capture; retry auth request metadata thiếu |
| Header/secret scan | 429 và arXiv saved headers không có credential-bearing auth/cookie/token keys; không key query trong 2 saved URLs. Retry headers absent nên không chứng nhận redaction đầy đủ cho cả ba captures |

Hai sources có phản hồi thật đủ để chứng minh truy cập nhỏ đã xảy ra. Metadata không chứng minh tổng network attempts ngoài ba captures; `3` là số evidence local được lưu, không phép đo sustained reliability. Source audit không có ranking/scores/splits để kiểm score bounds hoặc split overlap thật; leakage sentinel dưới đây chỉ kiểm trust boundary synthetic.

## Official docs và policy cho coordinator/SOL

- Basic anonymous use và key tăng budget 10× có nguồn chính thức; đây không phải suy luận. [OpenAlex API overview](https://help.openalex.org/api/) và [Example costs](https://help.openalex.org/access/example-costs/) ghi no-key $0.10/day, account $1/day, search $1/1000 calls; 30 calls sẽ là $0.03 nếu mỗi call charged $0.001. Phép tính này không dự đoán throttle, retry count, IP budget còn lại hoặc pilot pass. Payload thực tế có cost_usd 0.001; không suy remaining 990 thành 990 search calls.
- [Authentication](https://help.openalex.org/api/authentication/) hỗ trợ cả hai auth schemes; source policy cần budget/header units, Retry-After, bounded deadline và redaction cả URL/exception. Thiếu key khi mode bắt buộc keyed phải FAIL, không fallback anonymous.
- [arXiv Terms](https://info.arxiv.org/help/api/tou.html) đã được reviewer truy cập thành công qua link từ manual sau open trực tiếp ban đầu lỗi restricted URL. Terms áp dụng ≤1 legacy request/3 s và single connection trên toàn bộ machines được kiểm soát; descriptive metadata dùng CC0, PDF redistribution cần quyền/license. [Manual](https://info.arxiv.org/help/api/user-manual.html) xác nhận Atom/query/start/max_results/error feeds; đây là docs evidence, không second-page live test.
- Source config giữ policy gate theo card; coordinator/SOL chỉ đổi verified khi findings acceptance được xử lý và source policy được review. Không làm W1/freeze/DONE từ R1 này. Query pilot mới vẫn cần xác nhận theo plan; không đọc benchmark để tự tạo query.

## Reviewer probes và giới hạn

Temporary evidence trong checkout SOL: `data/public_search/sol/review_ext01b_r1/`, git-ignored; validator **reviewer-only**, không production CLI. Copy raw không biến synthetic mutation thành live evidence. Dùng root `.venv/Scripts/python.exe` read-only; mọi subprocess không network.

| Case | Exit code | Observation |
|---|---:|---|
| as_delivered | 1 | SHA arXiv JSON audit sai |
| synthetic_control_hash_repaired | 0 | 3 requests, 2×200+1×429, 3 works+2 entries |
| missing_manifest / missing_raw | 1 / 1 | FAIL missing resource |
| corrupt_payload / corrupt_manifest_hash | 1 / 1 | FAIL hash |
| wrong_counter | 1 | FAIL works counter |
| title_only (chỉ giữ id/title; optional metadata absent) | 0 | Không giả abstract; required title/id vẫn hợp lệ |
| missing_title / abstract_only (empty title) / wrong_format | 1 / 1 / 1 | FAIL required title/type |
| leakage_sentinel | 1 | FAIL synthetic label/sentinel field |

12 subprocess cases khớp 12 expected outcomes; 9 destructive fixtures đều exit1, 2 positive controls exit0, delivered bundle exit1. Title-only đã được rerun sau khi bỏ toàn bộ optional metadata, vẫn exit0 (13 invocations tổng). Validator chỉ kiểm evidence integrity/basic schema/sentinel, không chứng nhận adapter/transport/production CLI hoặc lịch sử request. Timing/redaction mocks của production transport không được chạy ở review này; source audit author chỉ báo JSON syntax validation và handled live429, chưa có bằng chứng test production CLI. Không bịa production CLI khi EXT-05B chưa có.

Re-run local reviewer command từ checkout SOL:

```powershell
& 'D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe' data/public_search/sol/review_ext01b_r1/reviewer_validator.py data/public_search/sol/review_ext01b_r1/as_delivered
# Expected: exit 1, FAIL audit arxiv_search sha256
```

## Bàn giao và dừng

Coordinator gửi F1–F4 cho tác giả MUSE khi user cho tiếp tục: sửa JSON integrity, auth/gate wording, missing-provenance disclosure và DOI coverage; tác giả thêm regression rồi commit snapshot mới. Reviewer re-review trên pin mới sau dispatch riêng. Theo yêu cầu mới nhất của user, **dừng sau report/log/commit R1 hiện tại**, không tự nhận fixes/re-review/W1. P2 vi phạm acceptance cũng chặn PASS theo card §6. Không sửa shared board hay tuyên bố task DONE.
