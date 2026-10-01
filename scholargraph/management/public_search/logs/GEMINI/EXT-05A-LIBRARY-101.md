# Nhật ký Phiên: EXT-05A-LIBRARY-101
## Khắc phục Lỗi Tích hợp P1: Wire Envelope Bất đồng bộ trong Thư viện UI

- **Mã phiên / Gói:** `EXT-05A-LIBRARY-101`
- **Task ID:** `EXT-05A`
- **Vai trò:** GEMINI author (UI Library Integration)
- **Model yêu cầu:** `gemini-3.8-flash-high` / `high`
- **Model thực tế:** `unknown`
- **Thời gian:** 2026-10-01T13:40:00+07:00
- **Workspace:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph`
- **Trạng thái kiểm thử:** `NOT_RUN` (do Antigravity runtime từ chối quyền `run_command`, tuân thủ không bypass lệnh, chuyển giao Coordinator chạy xác minh)

---

## 1. Bối cảnh & Phát hiện Thực nghiệm (Mock vs. Browser Thực tế)

- Trên trình duyệt thật (`/public/ui` kết nối backend FastAPI):
  - Tìm kiếm trả 3 hits hợp lệ từ OpenAlex cache.
  - Khi người dùng click nút "Lưu vào thư viện" (POST `/public/library`), backend trả về HTTP 200 OK với thân JSON:
    `{ "contract_version": "1.0.0", "entry": { ... }, "errors": [] }`.
  - UI ném lỗi hiển thị: `'LibraryEntry chứa trường không được phép: contract_version'` do UI cũ gọi `validateLibraryEntry(entry)` trực tiếp trên toàn bộ thân envelope.
  - Khi người dùng click tab "Thư viện" (GET `/public/library`), backend trả về:
    `{ "contract_version": "1.0.0", "entries": [ ... ], "errors": [] }`.
    UI cũ đòi hỏi mảng trần (`Array.isArray(entries)`), dẫn đến từ chối dữ liệu.
- Trong bộ kiểm thử `node_test_runner.js` cũ:
  - Mock fetch trước đó đã trả về bare object và bare array thay vì đúng cấu trúc envelope của backend. Do đó, test runner cũ báo PASS giả tạo, che giấu lỗi tích hợp P1 trên môi trường thật.

---

## 2. Công việc Đã Thực hiện (Chỉ sửa trong worktree cô lập)

1. **`ui/static/public_search.js`:**
   - Xây dựng hàm `validateLibrarySaveEnvelope(env)`: Kiểm tra cấu trúc envelope JSON bắt buộc gồm đúng 3 trường `["contract_version", "entry", "errors"]`, cấm extra fields, bắt buộc `contract_version === "1.0.0"`, `errors` là mảng rỗng khi 200, và xác thực đệ quy `validateLibraryEntry(env.entry)`. Tuyệt đối không fallback ngầm sang bare entry.
   - Xây dựng hàm `validateLibraryListEnvelope(env)`: Kiểm tra cấu trúc envelope JSON bắt buộc gồm đúng 3 trường `["contract_version", "entries", "errors"]`, cấm extra fields, bắt buộc `contract_version === "1.0.0"`, `errors` là mảng rỗng khi 200, và xác thực đệ quy từng bản ghi `validateLibraryEntry(item)`. Từ chối dứt khoát bare array.
   - Củng cố `validateLibraryEntry(entry)`: Kiểm tra sự hiện diện của toàn bộ 5 trường bắt buộc (`canonical_id`, `snapshot_id`, `saved_at`, `hit`, `incomplete_sources`).
   - Cập nhật `savePaperToLibrary`: Bóc tách thông tin lỗi chi tiết khi `!res.ok`, xác thực envelope qua `validateLibrarySaveEnvelope(envelope)` khi HTTP 200, và lấy `envelope.entry` để cập nhật trạng thái giao diện idempotent.
   - Cập nhật `loadLibrary`: Bóc tách thông tin lỗi chi tiết khi `!res.ok`, xác thực envelope qua `validateLibraryListEnvelope(envelope)` khi HTTP 200, và lấy `envelope.entries`.
   - Xuất khẩu `validateLibrarySaveEnvelope` và `validateLibraryListEnvelope` trong module `PublicSearchUI`.

2. **`tests/fixtures/public_search/gemini/ui/ui_fixtures.json`:**
   - Thêm `library_save_envelope` (synthetic wire hợp lệ).
   - Thêm `library_list_envelope` (synthetic wire hợp lệ).
   - Thêm 16 ca kiểm thử phá hủy trong `malformed_library_envelopes` bao gồm thiếu trường, sai phiên bản, thừa trường, có lỗi trong HTTP 200, bare entry/array cũ, và bản ghi con bị lỗi.

3. **`tests/fixtures/public_search/gemini/ui/node_test_runner.js`:**
   - Sửa Suite 7 để mock fetch trả về đúng cấu trúc backend wire envelope cho cả POST và GET.
   - Bổ sung Suite 7B kiểm thử toàn diện cả positive cases, negative cases (16 ca phá hủy), kiểm thử phá hủy chống bare payloads, và kiểm thử xử lý non-2xx HTTP errors.

4. **Tạo gói bàn giao:**
   - `management/public_search/packets/GEMINI/EXT-05A-LIBRARY-101.md`.

---

## 3. Trạng thái Lệnh & Bàn giao Kế tiếp

- **Commands Actual / NOT_RUN:**
  - `NOT_RUN`: Quyền chạy lệnh terminal bị Antigravity runtime từ chối (`permission check failed for command: user denied permission to run command`).
  - Không thực hiện bất kỳ lệnh shell/Git hay cố gắng bypass nào.
- **Bàn giao cho Coordinator:**
  1. Chạy kiểm chứng:
     `node tests/fixtures/public_search/gemini/ui/node_test_runner.js --fixtures tests/fixtures/public_search/gemini/ui/ui_fixtures.json --ux-examples tests/fixtures/public_search/ux_examples.json`
  2. Tính lại mã băm SHA-256 cho `ui_fixtures.json` và cập nhật vào `tests/fixtures/public_search/gemini/ui/ui_fixtures.sidecar.json`.
  3. Kiểm tra tích hợp trực tiếp trên trình duyệt tại `/public/ui` với chức năng Lưu bài vào thư viện.
