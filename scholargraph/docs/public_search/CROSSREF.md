# Enrichment DOI bằng Crossref — EXT-09

Crossref cung cấp sidecar metadata cho một DOI chính xác. `Source` của hợp đồng tìm kiếm v1 vẫn chỉ là `openalex`/`arxiv`; CLI này không thêm nguồn tìm kiếm, không sửa bản ghi đã lưu và không đọc benchmark, split hoặc nhãn nghiên cứu.

Chạy từ `D:/Web_mining_20261/scholargraph`:

```powershell
.venv/Scripts/python.exe scripts/enrich_public.py --project-root . --doi 10.21105/joss.09260 --output-dir data/public_search/phase_b/crossref-joss-09260
```

Mỗi lần chạy cần thư mục output mới. Thư mục đã tồn tại bị từ chối, kể cả run lỗi; không ghi đè hoặc coi raw cũ là lần đo mới. Output phải nằm trong `data/public_search/` của project. JSON trên stdout có `status=success|failed`; lỗi trả exit **1**, trợ giúp exit **0**. Script tự thêm `src` vào import path và xuất UTF-8 trên Windows.

DOI lấy từ các record của crawler JOSS có thể truyền trực tiếp qua `--doi`. Với bản ghi `PaperRecord` v1 đã hợp lệ và có DOI, dùng lựa chọn thay thế:

```powershell
.venv/Scripts/python.exe scripts/enrich_public.py --project-root . --record-json data/public_search/phase_b/inputs-107/original-record.json --output-dir data/public_search/phase_b/crossref-original
```

`--doi` và `--record-json` loại trừ nhau. `--record-json` nhận một `PaperRecord` đầy đủ, không nhận toàn bộ envelope tìm kiếm hoặc định dạng riêng của crawler. Bản gốc nằm trong `enrichment.original`; các giá trị khác Crossref nằm trong `enrichment.conflicts`, với giá trị và provenance hai phía. Không có lệnh cập nhật library tự động. Đường dẫn record phải nằm trong `data/public_search/`.

## Policy và HTTP

Cấu hình bắt buộc ở `configs/public_crossref.json`, có endpoint cố định `https://api.crossref.org/works`, public anonymous, concurrency **1** và interval ít nhất **1 giây**. Timestamp/hash policy lấy từ snapshot chính thức đã lưu tại `data/public_search/phase_b/policy-107/manifest.json`; khi chạy phải có raw policy đúng SHA-256. Không gửi email hay key giả. [Policy Crossref chính thức](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/).

Request duy nhất là `GET /works/{DOI được percent-encode}`; DOI returned phải khớp DOI normalized requested. Lock và cooldown dùng chung trong một process; nhiều CLI process hoặc server worker không chia sẻ quota. Chạy tuần tự. Headers rate/concurrency/retry được ghi khi có; malformed/duplicate/incomplete headers báo lỗi. Nếu server cung cấp rate thấp hơn, cooldown tăng theo interval/limit. Không suy header vắng mặt thành quota quan sát được.

Timeout mỗi request 20 giây, deadline gồm cả lock/cooldown 30 giây, body tối đa 2.000.000 byte theo config mặc định. HTTP không follow redirect. Yêu cầu encoding identity; compressed response không được hỗ trợ để giữ cap byte rõ ràng. Không tự retry (`max_retries=0`); 404/429/403/network/timeout/content-type/schema/body quá lớn đều FAIL, người gọi quyết định retry sau. Retry-After dạng số giây được hỗ trợ; dạng khác FAIL tường minh.

## Raw và bằng chứng

`result.json` được ghi atomic; raw nhận được giữ trong `raw.json`, có hash/byte count và `request.complete_body`. Khi quá cap, raw giữ phần đầu trong cap, `complete_body=false`, enrichment không thành công. Nếu không nhận body do lỗi mạng/header, raw có thể null. Không thay phép đo vắng mặt bằng zero hoặc chuỗi rỗng. Thư mục có tệp dở không được dùng lại; kiểm tra nó trước khi chọn run ID mới.

Sidecar strict chứa DOI/title/type bắt buộc, metadata tùy chọn nullable, unavailable fields và provenance từng trường gồm raw path/hash/raw field/parser version. Trường tùy chọn vắng hoặc danh sách tác giả/venue rỗng ghi null và `availability=unavailable`; trường đã có nhưng sai kiểu/giá trị FAIL. Crossref score hợp lệ có thể tồn tại trong raw, nhưng không dùng để xếp hạng. Các key nhãn/split/qrels bị từ chối đệ quy, kể cả alias như `test_labels` và `datasetSplit`.

Để kiểm parser offline, chỉ định fixture dưới `data/public_search/` bằng `--payload`; kết quả luôn `synthetic=true`, `retrieved_at=null`, `request.attempted=false`, không claim provenance của lần gọi mạng thật:

```powershell
.venv/Scripts/python.exe scripts/enrich_public.py --project-root . --doi 10.1234/synthetic --payload data/public_search/fixtures/crossref.json --output-dir data/public_search/synthetic-crossref-run
```

Lệnh fixture trên cần tạo fixture hợp lệ trước; không cung cấp dataset giả trong thư mục core. Kiểm thử deterministic và subprocess được chạy trên thư mục tạm bằng:

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m pytest tests/unit/test_public_crossref.py -q
```

Author đã chạy **98 tests PASS**. Pilot mạng thật và independent review do coordinator thực hiện sau khi pin snapshot; tài liệu này không tự nhận live pilot hoàn thành hay relevance đã được đo.
