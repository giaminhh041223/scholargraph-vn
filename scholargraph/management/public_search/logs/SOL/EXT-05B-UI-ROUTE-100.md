# EXT-05B UI route — packet và nhật ký 100

- Thời điểm: 2026-10-01T13:05:47+07:00.
- Worker: `/root/public_ui_route_fix`; coordinator `/root` giao sửa tích hợp UI, mở rộng quyền chỉ navigation assertion/docstring trong `tests/unit/test_public_ui.py`.
- Model/effort cụ thể: chưa xác minh bằng metadata runtime; không lấy routing khuyến nghị làm bằng chứng.
- Workspace: `D:/Web_mining_20261/scholargraph`; Git HEAD lúc kiểm tra: `5f16994b6fcdc466711184cf73d7bdd1452f6a8e`. Không commit.

## Đầu vào và phạm vi

Đã đọc hướng dẫn workspace/con, state/HANDOFF/tasks main và extension, routing/registry/strategy, task card EXT-05A/05B/06, public contract và source/test thật. Phát hiện `/public` đang là readiness JSON; template public chưa có route render và trang nội bộ trỏ vào readiness. Test UI hiện có kiểm tra href chính xác nên cần đổi assertion cùng link.

Chỉ sửa bốn file implementation/test và packet này:

- `src/scholargraph/api/app.py`: thêm GET `/public/ui` trả template `public_search.html`, HTML response, không gọi service.
- `ui/templates/search.html`: đổi link public sang `/public/ui`.
- `tests/integration/test_public_routes.py`: thêm bốn kiểm thử route/render/readiness.
- `tests/unit/test_public_ui.py`: chỉ cập nhật assertion và mô tả navigation sang `/public/ui`.

Endpoint `/public` giữ nguyên readiness JSON. Không đổi backend service/router/schema/config/board. Không gọi mạng, không sửa dữ liệu core, không tự tạo storage khi mở UI.

## Kiểm chứng thực tế

Chạy trong workspace với `PYTHONPATH=src`:

```text
.venv/Scripts/python.exe -m pytest -q tests/integration/test_public_routes.py tests/unit/test_public_ui.py tests/integration/test_public_cli.py::test_cli_missing_store_and_invalid_request_exit1 -p no:cacheprovider --basetemp=.tmp/public-ui-route-100
```

Kết quả: **25 passed**, **2 warnings**, **5.39s**, process exit **0**. Hai warning là deprecation từ TestClient đang có.

- Route tests: **8 passed**, gồm bốn ca có sẵn và bốn ca mới. GET `/public/ui` có form, JS/CSS; tài nguyên static trả 200 khi cả getter offline/public bị thay bằng hàm sẽ làm test thất bại nếu bị gọi. GET `/` qua service synthetic có link tới trang HTML. GET `/public` với service synthetic giữ đúng JSON readiness. Với config/storage tạm chưa khởi tạo, UI vẫn 200 nhưng readiness trả **500**, `overall=failed`, `snapshot=null`, lỗi `storage`; DB không được tạo.
- UI tests: **16 passed**, gồm Node DOM harness, missing fixture/UX resource, malformed JSON, schema/type/year, leakage probe và subprocess CLI boundary. Các negative subprocess kiểm tra exit **1** bằng assertions hiện có.
- CLI missing-storage/invalid-request: **1 passed**; subprocess search khi thiếu store trả exit **1**, stderr FAIL, stdout rỗng; request path thiếu sau init cũng exit **1**. Ca này dùng temp store/config; không chạy ca CLI có khả năng gọi mạng.
- `git diff --check` trên bốn file sửa: exit **0**, không output. Diff hiện tại: **73 insertions, 7 deletions** trong bốn file.

## Bàn giao và giới hạn

Delta đã xong; worker dừng ghi source/test sau packet. Coordinator chạy checker dự án, pin snapshot và làm browser demo/review theo gate. Chưa có kiểm chứng trình duyệt từ worker này; TestClient/Node harness không được mô tả thành browser demo hoặc live upstream success. Storage lỗi vẫn cần init tường minh trước sử dụng API; trang HTML không khẳng định service sẵn sàng.

Bước executable tiếp theo: coordinator mở `/public/ui` trên app đang chạy, xác nhận form/assets và điều hướng, rồi review snapshot W5; giữ `/public` cho readiness caller.
