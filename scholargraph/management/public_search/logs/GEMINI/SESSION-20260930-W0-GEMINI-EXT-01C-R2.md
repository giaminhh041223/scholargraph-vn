# SESSION-20260930-W0-GEMINI-EXT-01C-R2 — Sửa Validator & UX Fixtures theo Gate Coordinator (`EXT-01C`)

- **Ngày thực hiện:** `2026-09-30T10:05:00+07:00` (Coordinator checkpoint timestamp)
- **Task ID:** `EXT-01C` — Luồng UI và request/response examples (Vòng sửa W0 R2)
- **Worker / Role:** `GEMINI` (Owner `EXT-01C`, Reviewer: `MUSE`, Coordinator: `COORDINATOR`)
- **Dispatch ID nhận bàn giao:** `DISPATCH-20260930-W0-GEMINI`
- **Worker Execution Session ID:** `SESSION-20260930-W0-GEMINI-EXT-01C-R2`
- **Checkout / Project Root:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/`
- **Git Branch:** `codex/public-search-gemini`
- **Authoritative SOL Contract Reference (READ-ONLY):**
  - Checkout: `D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/`
  - Proposed SOL Head: `cb64c59a714085f1c453284fdfba76de3efb086e`
  - Contract Code Commit: `774aeef0bfc42c636779f739c3fb4fbb8e9e37c4`
  - Contract Module: `src/scholargraph/public_search/contracts.py` (v1.0.0, schema 1, trạng thái: PROPOSED_SOL_R2_RECONCILED)
  - Quyền sửa SOL contract trong lượt này: **KHÔNG** (giữ nguyên hợp đồng nguồn).

---

## 1. Mục tiêu phiên làm việc & Xử lý toàn diện phản hồi Gate Coordinator R2

1. **Khắc phục 3 trường hợp bypass thoát mã 0 (Destructive Mutation Bypasses):**
   - *Thay `contract_type="Unknown"` ở example_01:* Validator đối chiếu `contract_type` với `ALLOWED_CONTRACT_TYPES` và map chính xác sang `PAYLOAD_KEYS`, từ chối type lạ hoặc nhiều payloads cùng lúc.
   - *Xóa rỗng root `ui_states_covered`:* Validator kiểm tra đẳng thức tập hợp `root_ui_states == EXPECTED_UI_STATES` và `root_ui_states == observed_ui_states`.
   - *Xóa rỗng `ui_states_demonstrated` ở mọi example:* Validator kiểm tra `observed_ui_states == EXPECTED_UI_STATES`, bắt buộc gom đủ 9 trạng thái UI.

2. **Khớp chính xác Contract Type và Payload Type:**
   - Mỗi `contract_type` ánh xạ 1:1 sang đúng payload key (`SearchEnvelope` / `SearchEnvelope_StorageError` $\rightarrow$ `envelope`, `SearchEnvelope_CacheScenarios` $\rightarrow$ `subcases`, `SearchRequest_ValidationError` $\rightarrow$ `invalid_request_payload`, `LibraryEntry` $\rightarrow$ `library_entry`).
   - Bắt lỗi khi thiếu payload, có nhiều hơn một payload key, hoặc mismatch giữa contract_type và payload.

3. **Kiểm tra đẳng thức độ phủ (Coverage Declarations):**
   - Yêu cầu `ui_states_covered` và `truth_table_cases_covered` ở root phải bằng chính xác cả tập quan sát động (`observed`) và tập chuẩn bắt buộc (`EXPECTED_*`).
   - Kiểm tra nghiêm ngặt cache subcases trong `example_09`: từ chối mọi trường hợp thiếu hoặc thừa subcases ngoài bộ chuẩn 3 case (`A_cached_fresh`, `B_refresh_failure_does_not_mask_with_old_cache`, `C_explicit_open_stale_snapshot`).

4. **Sửa ranh giới kiểm tra rò rỉ (Leakage Boundary):**
   - Đổi cơ chế sang duyệt đệ quy dictionary keys (`check_leakage_boundary`): phát hiện các trường metadata cấm (`labels`, `qrels`, `splits`, `benchmark_input`).
   - Cho phép các từ khóa như `held_out`, `splits` xuất hiện bình thường trong văn bản truy vấn/tiêu đề người dùng mà không bị chặn nhầm.
   - Thêm positive test kiểm chứng văn bản chứa `held_out` trong request query text vẫn pass hợp lệ và bảo toàn nguyên vẹn provenance trace của `SearchEnvelope`.

5. **Kiểm thử điểm số và bản ghi dị dạng:**
   - Biến dị trường `score` thực tế trong `RankedHit` (`score = -1.0`, vi phạm ràng buộc `gt=0`) thay vì dùng key giả lập ngoài hợp đồng.
   - Thêm negative test cho JSON cú pháp sai (malformed JSON) và bản ghi text-only rỗng tiêu đề (`title = ""`), đảm bảo lỗi xuất phát đúng từ khiếm khuyết được chỉ định.

6. **Hiệu chỉnh Provenance Sidecar & CLI Validation:**
   - Cập nhật `ux_examples.sidecar.json` đúng mốc thời gian coordinator `2026-09-30T10:05:00+07:00`, SOL head `cb64c59a...`, commit `774aeef0...`, version `1.0.0`, không tự sinh content hash.
   - Thêm tham số `--sidecar` vào CLI, bắt buộc kiểm tra provenance; thoát mã 1 nếu thiếu sidecar file.

7. **Bộ kiểm thử phá hủy CLI Subprocess (16 Negative Cases):**
   - Mở rộng từ 6 negative cases ban đầu thành 16 cases phá hủy chạy độc lập qua subprocess kiểm tra exit code 1:
     1. Thiếu file sidecar.
     2. Thiếu file fixture.
     3. JSON cú pháp sai (malformed JSON).
     4. Thiếu trường bắt buộc ở root (`schema_version`).
     5. Thiếu trường bắt buộc ở envelope (`overall`).
     6. Bản ghi text-only có tiêu đề rỗng (`title = ""`).
     7. Điểm số RRF âm (`score = -1.0` trên `RankedHit`).
     8. Vi phạm đẳng thức bộ đếm (`raw = 999`).
     9. Bơm trường metadata benchmark bị cấm (`qrels`).
     10. Biến dị `contract_type="Unknown"`.
     11. Xóa rỗng root `ui_states_covered`.
     12. Xóa rỗng `ui_states_demonstrated` ở toàn bộ examples.
     13. Thiếu cache subcase C ở example_09.
     14. Thừa cache subcase D lạ ở example_09.
     15. Nhiều payload keys cùng xuất hiện trong một example.
     16. Mismatch giữa contract_type và payload key.
   - Positive checks: 13 typed objects hợp lệ (10 envelopes gồm 3 cache subcases, 1 request 422, 1 library entry, 1 title-only PaperRecord), cùng test case văn bản chứa `held_out`.

---

## 2. Danh sách tệp đã chỉnh sửa (Owned Deliverables)

1. `tests/fixtures/public_search/gemini/validate_fixtures.py`: Validator hoàn thiện với 16 CLI negative cases, chống bypass, kiểm tra đệ quy leakage, và xác thực sidecar.
2. `tests/fixtures/public_search/gemini/ux_examples.sidecar.json`: Cập nhật provenance SOL head `cb64c59`, commit `774aeef`, checkpoint `2026-09-30T10:05:00+07:00`.
3. `tests/fixtures/public_search/gemini/ux_examples.json`: Giữ header đồng bộ SOL head `cb64c59` và commit `774aeef`.
4. `docs/public_search/UX_SPEC.md`: Cập nhật trạng thái hợp đồng `PROPOSED_SOL_R2_RECONCILED`.
5. `management/public_search/logs/GEMINI/SESSION-20260930-W0-GEMINI-EXT-01C-R2.md`: Session log chi tiết này.
6. `management/public_search/packets/GEMINI/EXT-01C-R2.md`: Packet bàn giao gọn dưới 10 dòng.

*Ghi chú bảo toàn lịch sử:* Giữ nguyên các tệp R1 (`SESSION-20260930-W0-GEMINI-EXT-01C-R1.md` và `EXT-01C-R1.md`), không ghi đè.

---

## 3. Lệnh kiểm chứng chuyển giao cho Coordinator (Commands: NOT_RUN)

Do môi trường tuân thủ chính sách native file tools only (không chạy lệnh shell trực tiếp), các lệnh kiểm chứng sau được ghi nhận trạng thái **NOT_RUN** để Coordinator thực thi xác thực:

```powershell
# Chạy script kiểm chứng 13 typed objects, positive checks và 16 negative CLI subprocess cases
& "D:\Web_mining_20261\scholargraph\.venv\Scripts\python.exe" tests\fixtures\public_search\gemini\validate_fixtures.py --fixture tests\fixtures\public_search\gemini\ux_examples.json --sidecar tests\fixtures\public_search\gemini\ux_examples.sidecar.json
```
