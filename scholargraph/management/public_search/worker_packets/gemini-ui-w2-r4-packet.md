# Gói Bàn Giao Worker EXT-05A R4 — Gemini UI W2 Corrective Pass

- **Mã gói:** `gemini-ui-w2-r4-packet`
- **Thời gian:** 2026-10-01T08:20:00+07:00
- **Tác giả / Model:** Gemini 3.8 Flash High (Implementation Worker)
- **Task liên quan:** `EXT-05A` (Public Search UI Wave W2, Author R4 Corrective Pass)
- **Target checkout:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph`
- **Baseline Commit HEAD:** `7f9b89159b0243b89a9f0536621761f741c20d43`
- **Báo cáo kiểm toán tiếp nhận:** `management/public_search/reviews/SOL/UI-W2-AUDIT-083.md` (Reviewer SOL fresh audit 083)
- **Nhật ký phiên worker:** `management/logs/SESSION-20261001-084-GEMINI.md`

---

## 1. Tóm tắt khắc phục 3 phát hiện từ SOL Audit 083

### Phát hiện 1: `validateSourceResult` strict required presence & type guards
- **Khắc phục tại [`ui/static/public_search.js`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/static/public_search.js):**
  - Bổ sung xác thực thuộc tính sở hữu bắt buộc (`Object.prototype.hasOwnProperty.call(res, key)`) cho toàn bộ 9 khóa: `source`, `status`, `records`, `error`, `source_total`, `elapsed_seconds`, `filter_coverage`, `truncated`, `raw_references`. Thiếu bất kỳ khóa nào đều ném ngoại lệ rõ ràng (`SourceResult thiếu trường bắt buộc: <key>`).
  - Kiểm tra kiểu dữ liệu và miền giá trị (nullable per contract):
    - `source_total`: phải là `null` hoặc số nguyên không âm (`isStrictInteger(val) && val >= 0`).
    - `elapsed_seconds`: phải là `null` hoặc số thực không âm (`isStrictFloat(val) && val >= 0`).
    - `truncated`: phải là `null` hoặc `boolean` (`typeof val === "boolean"`).
  - Giữ vững ngữ nghĩa `not_requested`: yêu cầu bắt buộc `source_total === null`, `elapsed_seconds === null`, `truncated === null`, `filter_coverage === "none"`, `raw_references.length === 0`.
  - Nguồn được truy vấn (attempted) bắt buộc phải có `elapsed_seconds !== null`.

### Phát hiện 2: `isIsoTimeWithTz` khớp miền `datetime` Python & Pydantic Speedate
- **Khắc phục tại [`ui/static/public_search.js`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/static/public_search.js):**
  - Chặn năm 0000: `if (year < 1 || year > 9999) return false;` loại bỏ năm 0000 theo đúng miền `datetime.datetime` (1..9999) của Python.
  - Chặn offset ngoài khoảng địa lý chuẩn ISO 8601 (`[-12:00, +14:00]`):
    - Dấu `+`: tối đa `+14:00` (`totalTzMin <= 14 * 60`).
    - Dấu `-`: tối đa `-12:00` (`totalTzMin <= 12 * 60`).
    - Loại bỏ dứt khoát `+23:59`, `-23:59`, `+24:00` mà trước đó JavaScript `Date` ngầm chấp nhận.
  - Xuất `isIsoTimeWithTz` trong exports để phục vụ kiểm thử đơn vị độc lập.

### Phát hiện 3: `savePaperToLibrary` chấp nhận response idempotent bảo toàn snapshot gốc
- **Khắc phục tại [`ui/static/public_search.js`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/static/public_search.js) & [`tests/fixtures/public_search/gemini/ui/node_test_runner.js`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ui/node_test_runner.js):**
  - Theo hợp đồng `store.py:493–533`, khi lưu trùng bài báo đã tồn tại từ một snapshot mới hơn, store giữ nguyên bản ghi gốc (bảo toàn `snapshot_id` ban đầu và provenance trung thực).
  - Loại bỏ điều kiện so sánh cứng `entry.snapshot_id === targetSnapshotId`. Thay vào đó, kiểm tra nghiêm ngặt danh tính bài báo: `entry.canonical_id === canonicalId` và `entry.hit.canonical_id === canonicalId`.
  - Cập nhật trạng thái nút thành `Đã có trong thư viện (save_idempotent) lúc <saved_at>`, không hiển thị banner thất bại.
  - Nếu server trả sai lệch `canonical_id`, vẫn bắt buộc báo lỗi to và hiển thị banner thất bại (chống suy yếu validation).
  - Tại harness Suite 7: mock fetch trả về `savedEntry` tự đồng nhất cho cả POST và GET `/public/library`.

---

## 2. Kiểm thử Đối kháng Phá hủy Bổ sung (Destructive / Adversarial Testing)

1. **[`tests/fixtures/public_search/gemini/ui/node_test_runner.js`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ui/node_test_runner.js):**
   - Suite 2: Thêm 7 ca phá hủy cho `SourceResult` (thiếu `source_total`, thiếu `truncated`, thiếu `elapsed_seconds`, sai kiểu string, số âm, `not_requested` chứa số liệu).
   - Suite 2: Thêm 6 ca kiểm tra `isIsoTimeWithTz` (năm 0000, offset `+23:59`, `-23:59`, `+24:00`, `+07:00`, `Z`, và envelope fetched_at mutations).
   - Suite 7: Thêm ca kiểm tra lưu trùng giữ `snapshot_id` gốc của server và ca phản hồi `canonical_id` sai lệch bắt buộc thất bại rõ ràng.
   - Suite 9: Đảm bảo xóa banner giữa các ca export âm bản (`clearBanners()`).
2. **[`tests/fixtures/public_search/gemini/ui/ui_fixtures.json`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ui/ui_fixtures.json):**
   - Thêm 6 fixture malformed envelopes: `missing_source_total`, `missing_truncated`, `source_total_string`, `truncated_string`, `calendar_year0000`, `calendar_offset_large`.
3. **[`tests/unit/test_public_ui.py`](file:///D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/unit/test_public_ui.py):**
   - Bổ sung 3 hàm kiểm thử đối kháng cấp Python:
     * `test_adversarial_source_result_required_fields_and_types`: kiểm tra 7 đột biến của `SourceResult`.
     * `test_adversarial_datetime_year_and_offset_rejection`: kiểm tra năm 0000 và offset `+23:59`.
     * `test_adversarial_idempotent_library_entry_preserves_original_snapshot`: kiểm tra lưu trùng giữ snapshot_id gốc và từ chối sai lệch canonical_id.

---

## 3. Danh mục tệp đã sửa đổi (Owned Paths Only)

| Đường dẫn tệp | Mục đích thay đổi |
|---|---|
| `ui/static/public_search.js` | Sửa `validateSourceResult`, `isIsoTimeWithTz`, `savePaperToLibrary` |
| `tests/fixtures/public_search/gemini/ui/node_test_runner.js` | Thêm probes đối kháng Suite 2, 7, 9 và chuẩn hóa mock response |
| `tests/fixtures/public_search/gemini/ui/ui_fixtures.json` | Thêm 6 fixture malformed envelopes |
| `tests/unit/test_public_ui.py` | Bổ sung 3 hàm pytest kiểm thử đối kháng cho 3 phát hiện |
| `management/logs/SESSION-20261001-084-GEMINI.md` | Nhật ký phiên chi tiết của worker |
| `management/public_search/worker_packets/gemini-ui-w2-r4-packet.md` | Gói bàn giao kỹ thuật cho Coordinator |

*Cam kết phạm vi:* Tuyệt đối không chạm vào `contracts.py`, `store.py`, `service.py`, `tasks.json`, `state.json`, `HANDOFF.md`, các báo cáo reviewer, hoặc bất kỳ tệp ngoài quyền sở hữu.

---

## 4. Lệnh kiểm chứng dành cho Coordinator (Verification Commands)

Người điều phối (Coordinator) có thể chạy các lệnh sau trong thư mục target checkout:

```powershell
# 1. Chạy Node DOM Test Harness đầy đủ (tất cả 9 suites bao gồm probes mới)
node tests/fixtures/public_search/gemini/ui/node_test_runner.js --fixtures tests/fixtures/public_search/gemini/ui/ui_fixtures.json --ux-examples tests/fixtures/public_search/gemini/ux_examples.json

# 2. Chạy toàn bộ Unit Tests và CLI boundary bằng pytest
pytest tests/unit/test_public_ui.py -q

# 3. (Tùy chọn) Chạy trực tiếp script probe tái hiện của SOL 083 để kiểm tra 7/7 ca đều PASS
node management/public_search/reviews/SOL/probes-ui-083/probe-ui-083.js
```
