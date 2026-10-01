# Gói Bàn giao Kỹ thuật: EXT-05A-LIBRARY-101
## Khắc phục Lỗi Bất đồng bộ Wire Envelope Thư viện UI (Save & List)

- **Mã gói (Patch ID):** `EXT-05A-LIBRARY-101`
- **Task ID:** `EXT-05A` (Public Search UI Integration)
- **Tác giả / Vai trò:** GEMINI author (UI Library Integration)
- **Model yêu cầu (Requested Model/Effort):** `gemini-3.8-flash-high` / `high`
- **Model thực tế (Actual Model/Effort):** `unknown` (không thể tự xác minh trong môi trường sandbox)
- **Thời gian hoàn tất:** 2026-10-01T13:40:00+07:00
- **Workspace:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph`
- **Trạng thái kiểm thử:** `NOT_RUN` (Antigravity runtime từ chối quyền `run_command`; bàn giao cho Coordinator chạy kiểm chứng)

---

## 1. Bản chất Vấn đề & Đối chiếu Mock vs. Browser Thực tế (P1 Integration Bug)

### 1.1 Hiện tượng trên Browser Thực tế (`/public/ui`)
Khi người dùng chạy tìm kiếm công khai (OpenAlex cached 3 hits) và bấm nút **"Lưu vào thư viện"** (POST `/public/library`):
- Backend xử lý thành công và trả về mã HTTP `200 OK`.
- Tuy nhiên, giao diện UI lại bật banner lỗi:
  > `'LibraryEntry chứa trường không được phép: contract_version'`
- Đồng thời, khi chuyển sang tab Thư viện (GET `/public/library`), UI mong đợi một mảng thuần (`Array.isArray(entries)`), dẫn đến việc không thể hiển thị danh sách bài đã lưu.

### 1.2 Nguyên nhân Gốc rễ: Bất đồng bộ Hợp đồng Wire Envelope (Mock vs. Backend)
- **Backend hợp đồng đóng băng (`public_routes.py`):**
  - POST `/public/library`: trả về envelope `{ "contract_version": "1.0.0", "entry": LibraryEntry, "errors": [] }`.
  - GET `/public/library`: trả về envelope `{ "contract_version": "1.0.0", "entries": [LibraryEntry, ...], "errors": [] }`.
  - Trong khi đó, mô hình Pydantic `LibraryEntry` (`contracts.py`) chỉ chứa các trường: `["canonical_id", "snapshot_id", "saved_at", "hit", "incomplete_sources"]`, tuyệt đối không chứa `contract_version`.
- **Lỗi ở UI cũ:**
  - Hàm `savePaperToLibrary` gọi trực tiếp `validateLibraryEntry(entry)` trên toàn bộ JSON response của backend. Do envelope có chứa `contract_version` và `errors`, hàm `validateLibraryEntry` kích hoạt `hasExtraKeys` và ném lỗi `"LibraryEntry chứa trường không được phép: contract_version"`.
  - Hàm `loadLibrary` kiểm tra `if (!Array.isArray(entries))` trên response JSON của backend (vốn là đối tượng envelope có khóa `entries`), gây từ chối dữ liệu.
- **Lỗ hổng trong Harness Test cũ:**
  - Mock fetch trong `node_test_runner.js` trước đây đã giả lập sai lệch khi trả về `savedEntry` trực tiếp (bare object) và `[savedEntry]` trực tiếp (bare array), khiến bộ test runner báo PASS giả tạo và che giấu lỗi tích hợp P1 này.

---

## 2. Chi tiết Giải pháp Kỹ thuật (Anti-Silent-Bypass Protocol)

Tất cả các thay đổi được thực hiện cô lập tuyệt đối bên trong worktree `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph`, không can thiệp backend, không sửa board điều phối, không sửa parent repository.

### 2.1 Bổ sung Bộ Xác thực Wire Envelope Nghiêm ngặt trong `ui/static/public_search.js`
1. **`validateLibrarySaveEnvelope(env)`:**
   - Bắt buộc `env` là đối tượng JSON (loại bỏ primitive, null, bare array).
   - Kiểm tra khóa cho phép (`allowedKeys`): chính xác `["contract_version", "entry", "errors"]`. Cấm extra keys.
   - Kiểm tra khóa bắt buộc: `contract_version`, `entry`, `errors` đều phải tồn tại.
   - Kiểm tra phiên bản: `env.contract_version === "1.0.0"`.
   - Kiểm tra danh sách lỗi: `env.errors` phải là mảng, và trên phản hồi HTTP 200 thành công thì `env.errors.length === 0`.
   - Kiểm tra và xác thực đệ quy bản ghi bài báo: `validateLibraryEntry(env.entry)`.
   - **Tuyệt đối không fallback ngầm sang bare entry:** nếu thiếu wrapper envelope, hàm ném lỗi rõ ràng ngay lập tức.
2. **`validateLibraryListEnvelope(env)`:**
   - Bắt buộc `env` là đối tượng JSON. Nếu nhận bare array `[...]`, ném lỗi rõ ràng: `"LibraryListEnvelope phải là đối tượng JSON (không chấp nhận bare array)"`.
   - Khóa cho phép: chính xác `["contract_version", "entries", "errors"]`.
   - Khóa bắt buộc: `contract_version`, `entries`, `errors`.
   - Kiểm tra `contract_version === "1.0.0"`.
   - Kiểm tra `env.errors` là mảng và rỗng trên phản hồi thành công.
   - Kiểm tra `env.entries` là mảng và xác thực từng phần tử bằng `validateLibraryEntry(item)`.
3. **Củng cố `validateLibraryEntry(entry)`:**
   - Bổ sung vòng lặp kiểm tra sự hiện diện bắt buộc của toàn bộ 5 trường: `canonical_id`, `snapshot_id`, `saved_at`, `hit`, `incomplete_sources`.
4. **Xử lý phản hồi lỗi Non-2xx trong `savePaperToLibrary` và `loadLibrary`:**
   - Khi `!res.ok`, bóc tách cấu trúc lỗi `SearchError` từ `SearchEnvelope` hoặc `detail` của FastAPI để hiển thị thông báo lỗi chi tiết trên banner/container, đồng thời phục hồi trạng thái nút bấm cho phép thử lại.

### 2.2 Cập nhật Fixture Thử nghiệm trong `tests/fixtures/public_search/gemini/ui/ui_fixtures.json`
- Bổ sung `library_save_envelope` (synthetic wire hợp lệ).
- Bổ sung `library_list_envelope` (synthetic wire hợp lệ).
- Bổ sung 16 kịch bản phá hủy (Negative / Adversarial testing) trong `malformed_library_envelopes`:
  1. `save_missing_contract_version`
  2. `save_wrong_contract_version` (`"2.0.0"`)
  3. `save_missing_entry`
  4. `save_missing_errors`
  5. `save_non_empty_errors` (chứa lỗi trong HTTP 200)
  6. `save_extra_keys` (chứa khóa không được phép)
  7. `save_legacy_bare_entry` (bare entry không wrapper)
  8. `save_invalid_nested_entry` (thiếu `canonical_id`)
  9. `list_missing_contract_version`
  10. `list_wrong_contract_version`
  11. `list_missing_entries`
  12. `list_missing_errors`
  13. `list_non_empty_errors`
  14. `list_extra_keys`
  15. `list_legacy_bare_array` (bare array không wrapper)
  16. `list_invalid_nested_entry`
- Toàn bộ fixture mới đều gắn cờ `synthetic: true`.

### 2.3 Nâng cấp Bộ Test Harness trong `tests/fixtures/public_search/gemini/ui/node_test_runner.js`
- **Suite 7:** Cập nhật mock fetch trả về đúng cấu trúc backend wire envelope `{ contract_version: "1.0.0", entry: ..., errors: [] }` và `{ contract_version: "1.0.0", entries: [...], errors: [] }`.
- **Suite 7B (Mới):**
  - Kiểm thử chấp nhận valid wire envelope cho save và list.
  - Quét toàn bộ 16 trường hợp malformed và xác nhận đều bị ném lỗi và từ chối.
  - Kiểm thử phá hủy Anti-Silent-Bypass: từ chối bare entry và bare array.
  - Kiểm thử xử lý lỗi Non-2xx HTTP 422 trên POST và HTTP 500 trên GET.

### 2.4 Luồng Xuất Thư viện (Export Flow)
- Đã rà soát `exportLibrary("json")` và `exportLibrary("bibtex")`:
  - Backend trả về raw JSON array bytes (`media_type="application/json"`) và raw BibTeX text (`media_type="text/x-bibtex"`).
  - UI client tải thẳng qua `res.text()` và kích hoạt tải tệp Blob/URL. Luồng này hoàn toàn tương thích và không bị ảnh hưởng bởi lỗi envelope.

---

## 3. Danh mục Tệp Thay đổi (Exact Paths)

1. `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/static/public_search.js`
   - Bổ sung `validateLibrarySaveEnvelope`, `validateLibraryListEnvelope`.
   - Củng cố `validateLibraryEntry`.
   - Cập nhật `savePaperToLibrary` và `loadLibrary` xử lý wire envelope & non-2xx errors.
   - Xuất khẩu các hàm validator mới.
2. `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ui/ui_fixtures.json`
   - Thêm `library_save_envelope`, `library_list_envelope`, `malformed_library_envelopes` (16 ca phá hủy).
3. `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ui/node_test_runner.js`
   - Cập nhật mock fetch Suite 7 theo đúng backend wire envelope.
   - Bổ sung Suite 7B kiểm thử toàn diện wire envelope và negative cases.
4. `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/management/public_search/packets/GEMINI/EXT-05A-LIBRARY-101.md` (tệp hiện tại).
5. `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/management/logs/GEMINI/EXT-05A-LIBRARY-101.md` (nhật ký phiên).

---

## 4. Báo cáo Thực thi Lệnh & Yêu cầu Điều phối (Commands Actual / NOT_RUN)

- **Trạng thái thực thi:** `NOT_RUN`
  - Lệnh gọi CLI bị Antigravity runtime từ chối với lỗi: `permission check failed for command: user denied permission to run command`.
  - Tuân thủ chỉ thị, Agent tuyệt đối không gọi terminal/shell/Git để bypass.
- **Yêu cầu dành cho Coordinator:**
  1. Chạy bộ kiểm thử Node.js DOM Harness:
     ```bash
     node tests/fixtures/public_search/gemini/ui/node_test_runner.js --fixtures tests/fixtures/public_search/gemini/ui/ui_fixtures.json --ux-examples tests/fixtures/public_search/ux_examples.json
     ```
  2. Tính toán lại SHA-256 của `ui_fixtures.json` và cập nhật vào `tests/fixtures/public_search/gemini/ui/ui_fixtures.sidecar.json` (trường `target_fixture_sha256` hiện giữ `"NOTMEASURED"` vì không được phép chạy lệnh băm).
  3. Chạy kiểm thử pytest liên quan tại parent repo và kiểm tra trực tiếp trên browser tại `/public/ui`.

---

## 5. Các Điểm Cần Lưu ý Còn Lại (Remaining Findings)
- Tệp sidecar `tests/fixtures/public_search/gemini/ui/ui_fixtures.sidecar.json` giữ giá trị `"NOTMEASURED"` cho trường `target_fixture_sha256` để tránh tự bịa giá trị mã băm.
- Luồng lưu bài hiện tại đã được bảo vệ đầy đủ:
  - Idempotency giữ nguyên snapshot_id ban đầu khi lưu lại từ snapshot mới.
  - Phản hồi từ chối mismatch `canonical_id`.
  - Xử lý mượt mà cảnh báo `incomplete_sources=true`.
  - Hiển thị banner lỗi rõ ràng khi gặp non-2xx status code.

## Coordinator integration addendum
Parent sidecar đã được tính SHA256 thật (không còn NOTMEASURED). Root sửa harness synthetic metadata, UTF8 subprocess, strict error handling và sources serializer;24 targeted pytest PASS/exit0. Browser save/list PASS,6 entries; download observation NOT_RUN do tool timeout. Fresh W5 review tiếp theo.
