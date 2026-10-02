# Crawler HTML JOSS — EXT-10 R3

Crawler thu metadata từ một listing JOSS và các trang paper liên kết trực tiếp, bằng stdlib HTMLParser/httpx/Pydantic đang có. Schema riêng `JossPaperRecord` giữ hợp đồng public-search v1 nguyên trạng. Author ban đầu GEMINI; bản sửa R3 SOL; model/effort runtime cụ thể unknown, không dùng tên model được đề xuất làm bằng chứng đã chạy.

## Chạy CLI

Từ `D:/Web_mining_20261/scholargraph`:

```powershell
.venv/Scripts/python.exe scripts/crawl_public.py --project-root . --config configs/public_site_joss.json --run-dir data/public_search/joss/runs/pilot-r3
.venv/Scripts/python.exe scripts/crawl_public.py --project-root . --config configs/public_site_joss.json --run-dir data/public_search/joss/runs/pilot-r3 --resume
```

Đây là lệnh pilot để coordinator chạy sau khi pin snapshot; author R3 chưa chạy live. Run mới phải có thư mục mới; run đã tồn tại chỉ mở bằng `--resume`. `--query` lọc title/author cục bộ sau crawl, không sửa bản ghi lưu trên đĩa. Script bootstrap `src`, xuất UTF-8 trên Windows; `--help` exit0, lỗi usage/config/network/parse/integrity exit1 với JSON stderr. Trước khởi tạo hoặc khi checkpoint chưa được xác minh, counters là null. Lỗi parse raw đã xác minh giữ counters lịch sử thực.

## Phạm vi, policy và điều tốc

URL mạng chỉ gồm HTTPS host `joss.theoj.org`: `/robots.txt`, `/papers/published.html`, `/papers/10.21105/joss.<digits>`. `/about` được đọc từ policy snapshot đã có; không fetch `/about`, PDF, JavaScript hoặc host ngoài. DOI ở citation phải khớp canonical landing URL. PDF/abstract URL metadata phải HTTPS cùng host, không credentials, query/fragment, cổng lạ hoặc traversal; chúng không trở thành frontier.

`configs/public_site_joss.json` bắt buộc, extra fields bị từ chối. Config khóa schema1/site/parser/origin/start/robots/conditions, depth1, interval3–60s, pages1–100, papers1–50, body1KB–10MB, timeout0.5–120s; mặc định pages5/papers3/body1MB/timeout30s. `data_root` chỉ là `data/public_search/joss` hoặc thư mục con. Policy manifest/raw phải đầy đủ và khớp SHA-256; thiếu file không được bypass.

Mỗi crawler chạy tuần tự, một request tại một thời điểm. Dùng một crawler/CLI worker và không chạy các CLI đồng thời: cooldown không điều phối giữa nhiều crawler instance/process. Đồng hồ monotonic giãn request ít nhất3s; Crawl-delay hữu hạn >=0 và Request-rate số nguyên dương `requests/seconds` tăng interval một cách bảo thủ theo giá trị lớn nhất mọi group. Wait vượt deadline FAIL trước HTTP. Robots rỗng/comment-only hợp lệ; HTML garbage, directive lạ, nhóm thiếu User-agent, malformed/nonfinite delay hoặc rate bị từ chối. Robots được fetch lại mỗi resume hợp lệ và kiểm quyền listing/cached papers/frontier.

DNS preflight kiểm tất cả địa chỉ resolver trả về phải global; rỗng/private/loopback bị từ chối trước `client.send`. Đây là preflight, **không pin DNS vào kết nối HTTP**; resolver/socket của httpx có thể resolve lại và preflight DNS chưa có timeout tổng được chứng minh. Không nhận đã bảo vệ đầy đủ DNS rebinding. HTTP không follow redirect; MIME exact, duplicate content headers, body/Content-Length quá cap và compressed response bị từ chối. Request yêu cầu identity bytes. Timeout còn lại truyền cho httpx; deadline kiểm sau send và giữa các lần đọc. Không tuyên bố ngắt một socket read đang block đúng tại deadline tuyệt đối; timeout của httpx giới hạn operation đó.

## Raw, checkpoint và resume

Guard kiểm lexical project/public JOSS trước resolve, rồi kiểm resolved containment độc lập; mọi ancestor và file/thư mục artifact phải không phải `is_symlink()` hoặc `is_junction()`. Guard bao gồm raw, robots, checkpoint/records và `.tmp`; Windows native junction đã được tái hiện trong temp và bị từ chối. Không có thao tác xóa/move thư mục để bỏ qua guard.

`fetch_attempts` ghi UUID, URL/time, attempted/success/status, raw path/hash và complete_body. `attempted=true` chỉ tại `client.send`, nên private DNS có0HTTP attempts/0failed_attempted_calls. Robots bytes đã nhận được lưu theo `robots/<UUID>.txt` trước parse; lỗi UTF-8/directive/denial giữ raw cùng checkpoint failed. Raw HTML lưu theo hash. Stream quá cap giữ phần đầu trong cap và complete_body=false; lỗi header trước đọc body có thể không có raw. Không overwrite raw có nội dung khác, không dùng filename chỉ chính xác tới giây.

`records.json` và `checkpoint.json` đều được ghi `.tmp` + flush/fsync/replace tại mỗi checkpoint. Hai tệp không phải một giao dịch filesystem chung; nếu bị ngắt giữa hai lần replace và chúng lệch nhau, resume FAIL tường minh. Chỉ resume sau xác minh schema literal1, aware timestamps/thứ tự, SHA-256/parser/config, uniqueness/caps/URL/fetch evidence, file records và tất cả raw references.

Listing raw được parse lại để tính links_found/duplicate_links/frontier theo thứ tự normalized thực tế. **Mọi fetched paper được parse lại trước robots/quota/statuscomplete**, gồm paper chưa có record do lần trước parse lỗi. Record được đối chiếu toàn bộ model_dump, gồm provenance, với raw và fetch entry. Paper dị dạng còn nguyên trên raw vẫn FAIL/CLI1, không refetch, không chuyển thành success rỗng. Missing/corrupt/poison records/checkpoint/raw FAIL trước HTTP. Complete chỉ khi đã có listing hợp lệ, không còn fetched paper chưa parse, và cap đạt hoặc frontier rỗng.

Counters định nghĩa: pages_fetched đếm HTML thành công đã lưu (listing + papers), robots không tính vào page cap; papers_parsed/unique_papers bằng số record DOI/ID duy nhất; links/duplicate_links đến từ raw listing. failed_attempted_calls đếm các lần send có lỗi HTTP/transport/media/body, gồm robots; parse/policy denial không được cộng vào counter này. JSON thành công có http_attempts/http_successes tổng từ audit, gồm robots refresh và history. Lỗi parse/policy được phân loại riêng trong checkpoint.error; không claim có lịch sử đầy đủ mọi lần parser được gọi lại.

## Metadata và kiểm thử

Paper bắt buộc citation_title/DOI/author/publication_date/journal_title, ngày đúng lịch và DOI đúng landing; contradictory singletons, bất kỳ author rỗng (kể cả khi có author hợp lệ khác), research metadata attributes/names hoặc timestamp/parser API không hợp lệ đều FAIL. Guard tên trường so khớp các sentinel và alias normalized như `test_labels`, `train_split`, `qrels`, có prefix citation/research; không nhận substring `label` trong thuộc tính HTML công cộng `aria-label`/`data-label` là nhãn nghiên cứu. Metadata có `aria-label` và sentinel thật vẫn bị từ chối vì sentinel. Parser ghi toàn bộ tên meta trong provenance.meta_fields, không chỉ citation tags. Trường này là danh sách tên, không nội dung token/label. Các key labels/splits/qrels/scores trong checkpoint bị từ chối đệ quy; metadata name/provenance cũng được kiểm tra.

```powershell
$env:PYTHONPATH = 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv/Scripts/python.exe -m pytest tests/unit/test_public_site_crawler.py -q -p no:cacheprovider
```

R3 author chạy115 tests PASS, gồm poison đầy đủ trước HTTP, cached malformed paper ở hai budget, real subprocess CLI1, network-interrupted resume exact counters/no refetch, bốn junction Windows native, malformed robots/raw preservation, required fields/DOI/calendar/author/singleton/leakage, missing policy files, bodycap/redirect/header/deadline. Fixtures synthetic trong temp; không đọc benchmark/splits/qrels hoặc thay nhãn core.

Pilot coordinator trên R3 commit `e627fc551fcb917fb6d96890a8ac9fcaf46ce087` đã **FAIL** vì `aria-label` bị nhầm thành research label; robots/listing/first paper đều HTTP200, HTML pages2/records0/failed HTTP0. Run `data/public_search/joss/runs/live-r3-107` giữ nguyên FAIL/raw/history. R4 sửa hẹp guard; parse offline chính raw đầu DOI08883 SHA-256 `d17c21553d6ad58c4360f3fecf3c4a2cf39daef308580fa490ffef224ccd4c67` thành công và có31meta_fields, không gọi mạng hay sửa cohort cũ. Parser schema version vẫn `joss-citation-1.0.0` ở giai đoạn trước release; code commit/SHA snapshot phân biệt R3/R4 và không relabel kết quả R3. Coordinator chạy run R4 **mới** để đo pilot, chưa suy live/relevance/sustained availability từ parse offline.
