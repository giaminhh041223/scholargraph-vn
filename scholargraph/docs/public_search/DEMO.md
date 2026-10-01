# Demo và xác nhận của người dùng

## Xác nhận cập nhật106

Người dùng đã trả lời **“Đã kiểm các bước và đồng ý tích hợp”**, xác nhận demo tìm kiếm/lưu bài/mở JSON-BibTeX và cho phép tích hợp cục bộ. [Approval106](../../management/public_search/HUMAN_APPROVAL-106.json) lưu bằng chứng. Human demo và tệp download là **PASS_USER_CONFIRMED**. Quan sát download tự động cũ vẫn NOT_VERIFIED; không suy mọi kịch bản lỗi live đã xảy ra. Các mục PENDING bên dưới là lịch sử trước xác nhận, không phải gate hiện tại. Đã tích hợp fast-forward vào master local tại `3b61cfc`; [kiểm sau merge](../../artifacts/reports/public_search/sol/integration-106.json) PASS (96 tests, 155 resource hashes, freeze33). phaseB vẫn DEFERRED, core human gates giữ nguyên.


**Bộ 5 query: CONFIRMED. Human demo: PENDING. Merge master: PENDING.** Xác nhận query trước đây chưa thay thế việc dùng demo và xác nhận kết quả thực tế.

## 1. Mở demo

Preview hiện tại: [http://127.0.0.1:8011/public/ui](http://127.0.0.1:8011/public/ui). Nó dùng cấu hình/store pilot [config](../../data/public_search/muse/pilot_ext06/config.json), đang có 6 entry đã lưu. Store mặc định trong [USER_GUIDE](USER_GUIDE.md) là `data/public_search/sol`, có thể có số entry khác.

Nếu preview đã dừng và helper `.tmp/ext06-095/serve_demo.py` còn tồn tại, tại thư mục ScholarGraph:

```powershell
Set-Location D:/Web_mining_20261/scholargraph
$env:PYTHONPATH = 'src'
& .venv/Scripts/python.exe .tmp/ext06-095/serve_demo.py
```

Helper là tệp tạm, không nằm trong Git. Để tái tạo trên bản checkout có dữ liệu pilot, lưu đoạn Python dưới vào `.tmp/public_demo.py`, rồi chạy `& .venv/Scripts/python.exe .tmp/public_demo.py`. Không chạy hai server trên cùng cổng; không init lại store pilot hỏng để che lỗi.

```python
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from scholargraph.api.app import app
from scholargraph.api.public_routes import set_public_service
from scholargraph.public_search.service import PublicSearchService
import uvicorn
service = PublicSearchService(root, root/'data/public_search/muse/pilot_ext06/config.json')
set_public_service(service)
try:
    uvicorn.run(app, host='127.0.0.1', port=8011)
finally:
    set_public_service(None)
    service.store.close()
```

Raw responses/SQLite của pilot được giữ cục bộ trong `data/`, không nằm hết trong Git. Nếu thiếu dữ liệu, dùng store mới mặc định theo USER_GUIDE; không kỳ vọng tái hiện 6 entries hoặc hash lịch sử trên máy mới. Server bình thường dùng cổng 8000; đợt browser này kiểm preview 8011, không ghi nhận chạy riêng cổng 8000.

## 2. Quy trình demo

Giữ hai nguồn OpenAlex + arXiv, top_k=3, cap=3, không lọc năm trong bộ pilot:

| ID | Query đã xác nhận |
|---|---|
| Q1 | knowledge graph |
| Q2 | graph neural network |
| Q3 | information retrieval |
| Q4 | scientific document search |
| Q5 | Vietnamese natural language processing |

1. Bấm **Tìm kiếm** cho từng query. Nếu cùng cấu hình còn cache, nhãn là `cached_fresh`; snapshot vẫn giữ provenance/thời gian thu thập trước.
2. Bấm nút **Làm mới từ nguồn** để kiểm live, giãn lượt ít nhất 3 giây. Đọc trạng thái từng nguồn; timeout/quota là kết quả lỗi phải ghi lại, không đánh dấu PASS cho cả hai nguồn.
3. Tìm lại cùng request để kiểm cache. Nhãn và snapshot phải khớp; không lấy thời gian source trong snapshot làm thời gian cache/browser mới.
4. Bấm **Xem chi tiết & Provenance**; đối chiếu nguồn, ID, raw hash, trường thiếu và xung đột. Liên kết bài báo có thể mở tại nguồn; module không tải PDF.
5. Lưu một bài, lưu lại cùng canonical ID, mở **Thư viện cá nhân**. Kiểm không tạo bản ghi trùng và entry giữ provenance; nếu bài đã có trước, số lượng không tăng.
6. Bấm **Xuất JSON**, **Xuất BibTeX**. **Mở hai tệp đã tải thật trên máy**: JSON là list LibraryEntry; BibTeX có `@misc` và escape. So số entry với thư viện hiện tại, không bắt buộc6 nếu bạn đã thêm bài.
7. Xem cảnh báo partial và hits nguồn tốt nếu có một nguồn lỗi. Không cố gây thêm quota bằng spam. Các kịch bản partial/paging/race có test synthetic độc lập trong regression; nếu live demo không gặp partial, ghi NOT_RUN cho quan sát live đó.
8. Mở liên kết **Quay lại Tìm kiếm nội bộ (SciFact)**. Kiểm kết quả core có provenance benchmark riêng; nếu tài nguyên core thiếu, ghi lỗi rõ. Test API/UI/graph và freeze 33 đã kiểm độc lập; không suy hành động browser từ test synthetic.

## 3. Bằng chứng đã có và phần bạn cần xác nhận

| Mục | Bằng chứng agent | Xác nhận người dùng |
|---|---|---|
| Khởi tạo/list/export/thiếu config | Lệnh CLI temp thật: [102](../../artifacts/reports/public_search/browser-101/doc-commands-102.json), [105](../../artifacts/reports/public_search/sol/doc-commands-105.json) | PENDING |
| Server và trang preview 8011 | Server đã restart code 66264a7, browser mở trang thật; không đo uptime dài hạn | PENDING |
| Live 5 query, hai nguồn | Recovery102 **CLI**: 5 refresh thành công; không coi là browser live5query | PENDING |
| Cache5query, hai nguồn | [Browser DOM102](../../artifacts/reports/public_search/browser-101/two-source-searches.json):5 cached queries; Q1 kiểm lại sau restart | PENDING |
| Save/list | Browser save/idempotency/library 6 entries + API; store pilot khác mặc định | PENDING |
| Export API / tạo download | API 200 bytes đã kiểm; Node Blob/click/revoke synthetic đã kiểm | PENDING |
| **Tệp download browser lưu thật** | **NOT_VERIFIED**: download event timeout, chưa có proof tệp lưu | **PENDING, bắt buộc mở tệp thật** |
| Partial/non-2xx/paging/race | Test synthetic và lịch sử CLI 6 partial; không bảo đảm mỗi demo live gặp partial | PENDING hoặc NOT_RUN live |
| Public/core độc lập | Regression 630 gồm API/UI/graph/export; freeze 33 unchanged | PENDING quan sát người dùng |

Export API lịch sử6 entries: JSON 52353 bytes SHA`3d6df2f6fd0c7c71365321c16c64ffcabf21f1a52bbbc5d38e206fd1a08a1d5b`; BibTeX 4628 bytes SHA`9d78dafc61711a21538e40984e9c08b71e82b78e3805de649a0f70cede59e9b5`. Hash áp dụng đúng [artifact 102](../../artifacts/reports/public_search/browser-101/summary-102.json), có thể đổi sau thao tác lưu; không yêu cầu download mới khớp hash cũ.

## 4. Ghi nhận kết quả

Ghi ngày/người thực hiện, cổng và store, query/config, kết quả từng nguồn, snapshot ID, số entry và hai tệp mở được; nêu lỗi/NOT_RUN nếu có. Không cần ký một mẫu pháp lý.

Sau khi hoàn thành, phản hồi trong chat rằng bạn đã dùng demo, đã lưu bài và mở được JSON/BibTeX, kèm lỗi còn thấy hoặc xác nhận cho phép tích hợp nhánh. Coordinator chỉ chuyển human gate sau xác nhận thực tế này.

Pilot không đo relevance bằng nhãn, SLA sản xuất hay availability dài hạn. Chi tiết số đo và giới hạn nằm ở [RELEASE_PACKET](RELEASE_PACKET.md).
