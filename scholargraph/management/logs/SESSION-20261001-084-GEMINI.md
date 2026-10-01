# Nhật ký Phiên `SESSION-20261001-084-GEMINI` — EXT-05A R4 Corrective Author Pass

- **Phiên:** `SESSION-20261001-084-GEMINI`
- **Thời gian:** 2026-10-01T08:15:00+07:00
- **Model:** Gemini 3.8 Flash High
- **Vai trò:** Implementation Worker
- **Task liên quan:** `EXT-05A` (Public Search UI Wave W2, Author R4 Corrective Pass)
- **Target checkout:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph`
- **Starting HEAD:** `7f9b89159b0243b89a9f0536621761f741c20d43`
- **Báo cáo kiểm toán tiếp nhận:** `management/public_search/reviews/SOL/UI-W2-AUDIT-083.md` (Reviewer SOL fresh audit 083)

---

## 1. Nội dung khắc phục chi tiết theo 3 phát hiện của SOL 083

### Phát hiện 1 (P1): `validateSourceResult` thiếu required presence và type guard cho `source_total`, `elapsed_seconds`, `truncated`
- **Nguyên nhân:** Trước R4, `validateSourceResult` chỉ kiểm tra allowed keys và đọc các trường này trong nhánh `not_requested`. Khi thiếu khóa (`delete`) hoặc truyền sai kiểu (string, số âm), validator chấp nhận ngầm (`ACCEPT`).
- **Khắc phục tại `ui/static/public_search.js`:**
  1. Bổ sung vòng lặp kiểm tra thuộc tính sở hữu bắt buộc:
     `for (const key of requiredKeys) { if (!Object.prototype.hasOwnProperty.call(res, key)) throw new Error("SourceResult thiếu trường bắt buộc: " + key); }`
  2. Bổ sung type và range guard chặt chẽ:
     - `source_total`: phải là `null` hoặc số nguyên không âm (`isStrictInteger(val) && val >= 0`).
     - `elapsed_seconds`: phải là `null` hoặc số thực không âm (`isStrictFloat(val) && val >= 0`).
     - `truncated`: phải là `null` hoặc `boolean` (`typeof val === "boolean"`).
  3. Bảo toàn ngữ nghĩa `not_requested`: yêu cầu cả 3 trường trên bắt buộc là `null`, `filter_coverage === "none"`, `records` và `raw_references` rỗng. Nếu nguồn được kích hoạt (attempted), bắt buộc `elapsed_seconds !== null`.

### Phát hiện 2 (P1): `isIsoTimeWithTz` nhận năm `0000` và offset `+23:59/-23:59` mà Python contract loại bỏ
- **Nguyên nhân:** Regex `\d{4}` nhận năm `0000`, và kiểm tra `tzH <= 23 && tzM <= 59` nhận `+23:59`/`-23:59`; `new Date()` normalize các giá trị này. Trong khi đó, Python `datetime` (miền 1..9999) và Pydantic/Speedate (giới hạn offset ISO 8601 theo chuẩn múi giờ thực địa `[-12:00, +14:00]`) lập tức `REJECT`.
- **Khắc phục tại `ui/static/public_search.js`:**
  1. Kiểm tra năm khớp Python contract: `if (year < 1 || year > 9999) return false;` loại bỏ năm 0000.
  2. Kiểm tra offset múi giờ khớp miền ISO 8601 / RFC 3339 / Speedate:
     - Dấu `+`: `totalTzMin <= 14 * 60` (tối đa +14:00).
     - Dấu `-`: `totalTzMin <= 12 * 60` (tối đa -12:00).
     - Loại bỏ dứt khoát `+23:59`, `-23:59`, `+24:00`.
  3. Xuất `isIsoTimeWithTz` trong module exports để phục vụ kiểm thử đơn vị độc lập.

### Phát hiện 3 (P1/P0): `savePaperToLibrary` từ chối response idempotent từ store khi giữ `snapshot_id` ban đầu
- **Nguyên nhân:** Theo hợp đồng lưu trữ `store.py:493–533`, khi lưu trùng bài báo đã tồn tại từ một snapshot mới hơn, store giữ nguyên bản ghi gốc (với `snapshot_id` và provenance ban đầu). Trước R4, `savePaperToLibrary` so sánh cứng `entry.snapshot_id !== targetSnapshotId`, dẫn đến coi response idempotent hợp lệ của server là lỗi và hiện banner thất bại. Đồng thời ở harness Suite 7, mock fetch trả canonical_id không đồng nhất với hit đang lưu.
- **Khắc phục tại `ui/static/public_search.js` & `node_test_runner.js`:**
  1. Tại `savePaperToLibrary`: xác thực nghiêm ngặt định danh bài báo (`entry.canonical_id === canonicalId` và `entry.hit.canonical_id === canonicalId`). Không từ chối khi `entry.snapshot_id` giữ nguyên giá trị gốc từ server; coi đây là thành công idempotent, cập nhật nút sang `save_idempotent`, hiển thị thời điểm `saved_at`, và giữ nguyên dữ liệu bằng chứng trung thực của server.
  2. Tại `node_test_runner.js` Suite 7: `libraryFetch` trả về `savedEntry` đồng nhất cho cả POST và GET `/public/library`.
  3. Bổ sung test case đối kháng phá hủy: kiểm tra lưu trùng từ snapshot khác và kiểm tra phản hồi sai lệch `canonical_id` bắt buộc báo lỗi to và reset nút.

---

## 2. Kiểm thử Đối kháng Bổ sung (Destructive / Adversarial Testing)

1. **`tests/fixtures/public_search/gemini/ui/node_test_runner.js`:**
   - Suite 2: Thêm 7 ca phá hủy cho `SourceResult` (thiếu `source_total`, thiếu `truncated`, thiếu `elapsed_seconds`, kiểu string, số âm, `not_requested` chứa số liệu).
   - Suite 2: Thêm 6 ca kiểm tra `isIsoTimeWithTz` (năm 0000, `+23:59`, `-23:59`, `+24:00`, `+07:00`, `Z`, và envelope mutations).
   - Suite 7: Thêm ca kiểm tra lưu trùng giữ `snapshot_id` gốc và ca phản hồi `canonical_id` sai lệch.
   - Suite 9: Giữ nguyên cơ chế xóa banner giữa các ca kiểm thử export âm bản (`clearBanners()`).
2. **`tests/fixtures/public_search/gemini/ui/ui_fixtures.json`:**
   - Thêm 6 fixture malformed envelopes: `missing_source_total`, `missing_truncated`, `source_total_string`, `truncated_string`, `calendar_year0000`, `calendar_offset_large`.
3. **`tests/unit/test_public_ui.py`:**
   - Thêm 3 hàm test đối kháng cấp Python:
     * `test_adversarial_source_result_required_fields_and_types`
     * `test_adversarial_datetime_year_and_offset_rejection`
     * `test_adversarial_idempotent_library_entry_preserves_original_snapshot`

---

## 3. Danh mục tệp đã sửa đổi (Owned Paths Only)

1. `ui/static/public_search.js` (validator và save logic)
2. `tests/fixtures/public_search/gemini/ui/node_test_runner.js` (DOM harness assertions và self-consistent responses)
3. `tests/fixtures/public_search/gemini/ui/ui_fixtures.json` (bổ sung 6 fixture đối kháng)
4. `tests/unit/test_public_ui.py` (bổ sung 3 test functions)
5. `management/logs/SESSION-20261001-084-GEMINI.md` (nhật ký phiên worker)
6. `management/public_search/worker_packets/gemini-ui-w2-r4-packet.md` (gói bàn giao R4 cho Coordinator)

*Không sửa đổi:* Contracts, store, backend, reviewer reports, state/board/HANDOFF, hoặc các tệp ngoài quyền sở hữu.
