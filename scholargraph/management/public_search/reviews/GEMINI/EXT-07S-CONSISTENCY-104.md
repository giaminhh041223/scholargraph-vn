# Báo cáo Đối soát Nhất quán Third-worker EXT-07S — GEMINI Cross-check

- **Mã Task:** `EXT-07S` (Third-worker Consistency Review cho Báo cáo Audit Backend của MUSE)
- **Báo cáo được đối soát chính:** `management/public_search/reviews/MUSE/EXT-07S-W5-R2-104.md` (MUSE R2)
- **Snapshot mục tiêu:** Parent immutable commit `66264a72ff3d921b1b47200bdae311ffab932310` (`66264a7`)
- **Third-worker Auditor:** `GEMINI` (requested `gemini-3.8-flash-high`, effort `high`)
- **Tài liệu & Artifacts đầu vào đã đối soát:**
  - `management/public_search/reviews/MUSE/EXT-07S-W5-R2-104.md` (MUSE R2)
  - `management/public_search/reviews/MUSE/EXT-07S-W5-102.md` (MUSE R1)
  - `management/public_search/logs/SOL/EXT-07S-FIX-103.md` (SOL author fix log)
  - `artifacts/reports/public_search/sol/regression-w5-104.json` (Coordinator full regression report)
  - `.worktrees/public-muse/scholargraph/management/public_search/reviews/MUSE/EXT-07G-CONSISTENCY-104.md`
  - `src/scholargraph/public_search/service.py:181-212`
  - `scripts/search_public.py:22-26,54-76,79-117`
- **Quy chế thực hiện:** File-only auditor. CẤM terminal/RunCommand/shell/Git. Không sửa mã nguồn, không sửa board điều phối.

---

## 1. Đối soát Tính Đúng đắn Kỹ thuật của Báo cáo MUSE R2 (`EXT-07S-W5-R2-104.md`)

MUSE R2 đã kiểm tra toàn diện commit sửa lỗi `66264a7` của SOL trên các phát hiện F-01, F-02 và F-03. Kết quả đối soát độc lập của GEMINI như sau:

### 1.1. Finding F-01: Đo `elapsed_seconds` Thực tế & Xử lý Ngoại lệ Nguồn (`service.py:181-212`)
- **Xác minh mã nguồn:**
  - `started = time.perf_counter()` được đặt ở đầu hàm `_source_result`, độc lập hoàn toàn với đồng hồ của transport adapter (dòng 185).
  - Nếu timer hỏng ngay từ đầu, hàm lập tức phát sinh `ServiceError(_error("config", "source elapsed time measurement failed", source))` (dòng 187).
  - Bắt các ngoại lệ mạng và schema: `TransportError` giữ nguyên mã lỗi gốc; `ValueError, TypeError, AttributeError` ánh xạ sang `schema`; các `Exception` khác (như `RuntimeError`, `OSError`) chuyển thành thông điệp lỗi tĩnh `"source execution failed"` mà không echo nội dung raw exception, ngăn chặn triệt để nguy cơ lộ API key/secret (dòng 195–200).
  - `elapsed = time.perf_counter() - started`: kiểm tra chặt chẽ `math.isfinite(elapsed)` và `elapsed >= 0` (dòng 202–204). Nếu đồng hồ hỏng (NaN hoặc âm), ném `ServiceError` cấu hình, không bao giờ gán `0` giả hay `None`.
  - Phục hồi chính xác diện bao phủ năm (`filter_coverage`): có lọc năm thì OpenAlex là `"server"`, arXiv là `"bounded_pool"`; không lọc năm là `"none"` (dòng 207–209).
  - Khi một nguồn lỗi trong tìm kiếm hai nguồn, `SourceResult` của nguồn lỗi có `status="failed"`, chứa thời gian đo thực tế và thông điệp lỗi có cấu trúc, đồng thời giữ nguyên bản ghi của nguồn thành công trong snapshot (`partial_failure`).
- **Kết luận F-01:** Phân tích của MUSE là **chính xác 100%**. Việc đóng F-01 đạt yêu cầu kỹ thuật.

### 1.2. Finding F-02: Xử lý Đối số CLI & Thoát Mã Lỗi Nghiêm ngặt (`scripts/search_public.py`)
- **Xác minh mã nguồn:**
  - Lớp `_ArgumentParser` kế thừa `argparse.ArgumentParser` và override phương thức `error(self, message)` (dòng 22–25) để luôn ném `ValueError("invalid CLI arguments")`. Toàn bộ parser con kế thừa cơ chế này.
  - Trong `main()`: khối `except (OSError, ValueError, TypeError, json.JSONDecodeError)` bắt lỗi phân tích đối số và gọi `_failure(SearchError(kind="request", message="invalid or missing CLI input", ...))` (dòng 115–117), in JSON lỗi có cấu trúc ra stderr và **thoát mã lỗi 1**. Không còn hiện tượng văng traceback thô hoặc thoát mã lỗi 2 của argparse mặc định.
  - Lệnh trợ giúp `--help` không kích hoạt `error()`, sử dụng cơ chế in hướng dẫn mặc định của argparse và **thoát mã 0**.
  - Lệnh bình thường (`init-storage`, `search` không lỗi, `library`, `export`) thoát mã 0. Lệnh `search` gặp lỗi một phần (`partial_failure`) có `envelope.errors` không rỗng nên trả về mã 1, nhưng vẫn in snapshot chứa kết quả lành lặn ra stdout.
- **Kết luận F-02:** Phân tích của MUSE là **chính xác 100%**. Việc đóng F-02 đạt yêu cầu kỹ thuật.

### 1.3. Finding F-03: Trường `arxiv_id` Nullable của OpenAlex
- MUSE ghi nhận F-03 (về việc `arxiv_id` có thể null trong dữ liệu OpenAlex khi không có DOI) là một giới hạn (limitation) về dedup alias chứ không phải lỗi chặn MVP, và chấp nhận quyết định hoãn (defer) sang Phase B của Coordinator.
- **Kết luận F-03:** Việc hoãn này là hợp lý, có căn cứ rõ ràng, không tạo thêm tính năng ngoài hợp đồng và không vi phạm tiêu chuẩn nghiệm thu của MVP.

---

## 2. Đối soát Số liệu Kiểm thử Thực nghiệm & Tính Toán Học

### 2.1. Phân giải Số ca Kiểm thử trong Báo cáo MUSE R2 (63 passed, 1 failed)
- Trong mục 1 của `EXT-07S-W5-R2-104.md`, MUSE báo cáo:
  - Chạy 4 tệp test (`test_public_service.py`, `test_public_cli.py`, `test_public_routes.py`, `test_public_adversarial.py`) với basetemp riêng: **63 passed, 1 failed, exit 1** (tổng cộng 64 ca).
  - Chạy 3 tệp test của author (`service`, `cli`, `routes`): **57 passed, exit 0**.
  - Chạy riêng `test_public_adversarial.py`: **6 passed, 1 failed** (tổng cộng 7 ca).
- **Đối soát số học:**
  $$57 \text{ (từ 3 test suites)} + 6 \text{ (passed adversarial)} = 63 \text{ passed}$$
  $$63 \text{ passed} + 1 \text{ failed} = 64 \text{ test cases tổng cộng}$$
  Số liệu hoàn toàn khớp logic toán học 1:1. Không có sự cộng gộp nhầm lẫn thành ca độc lập mới.
- **Phân tích ca thất bại duy nhất:**
  - Ca lỗi: `test_public_adversarial.py::test_mock_http_adapters_store_snapshot_and_export_without_live_network` gặp lỗi `FileNotFoundError [WinError 3]` tại `os.replace`.
  - Chẩn đoán của MUSE chỉ ra nguyên nhân là giới hạn đường dẫn Windows MAX_PATH (độ dài đường dẫn đạt **274 ký tự** do đặt basetemp sâu trong thư mục worktree con: `D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph/management/public_search/reviews/MUSE/probes-ext07s-104/pytesttemp/...`). Khi thử nghiệm đường dẫn ngắn hơn (207 ký tự), thao tác ghi file thành công bình thường.
  - Đây là hạn chế môi trường đường dẫn sâu của Windows trong worktree, không phải lỗi logic sản phẩm (product bug).

### 2.2. Xác nhận Độc lập qua Báo cáo Regression Toàn diện của Coordinator
- Tệp báo cáo chính thức của Coordinator tại parent: [`artifacts/reports/public_search/sol/regression-w5-104.json`](file:///D:/Web_mining_20261/scholargraph/artifacts/reports/public_search/sol/regression-w5-104.json):
  - Lệnh thực thi: Chạy toàn bộ 18 tệp unit/integration tests trên môi trường parent `.venv` với commit `66264a72ff3d921b1b47200bdae311ffab932310` và thư mục basetemp ngắn hơn (`.tmp\final-regression-104\pytest`).
  - Kết quả thực tế: **630 passed, 0 failed, exit 0**, thời gian chạy `321.284s`.
  - Kiểm tra đóng băng dữ liệu (Core Freeze): 33 tệp được kiểm tra trước và sau khi chạy đều giữ nguyên mã băm SHA-256 `34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557`.
  - Kết quả này xác nhận chắc chắn rằng ca thất bại trong lượt chạy của MUSE hoàn toàn do giới hạn 260 ký tự của Windows khi đặt thư mục tạm quá sâu; mã nguồn tại commit `66264a7` đạt 100% độ tin cậy và không có lỗi hồi quy.

### 2.3. Lịch sử Thực thi (Historical Executions Accounting)
- MUSE làm rõ sự khác biệt giữa **51 lần thực thi (executions)** và **50 trường hợp độc lập (distinct cases)** trong transcript R1 (`47e769...`): lần đầu chạy 1 ca `test_cli_missing...`, sau đó chạy tổ hợp 6 ca có lặp lại ca này.
- Cách giải thích của MUSE trong R2 là chính xác, duy trì tính minh bạch dữ liệu và không làm thay đổi lịch sử R1.

---

## 3. Đối soát Tính Nhất quán Chéo (Cross-consistency với EXT-07G & EXT-07M)

1. **Phản hồi về nhận xét Wording Startup của Gemini trong `EXT-07G-CONSISTENCY-104.md`:**
   - Trong `EXT-07G-CONSISTENCY-104.md` (mục 3, dòng 26–28), MUSE có đề xuất điều chỉnh câu chữ trong báo cáo của Gemini về độ trễ cache (không quy nguyên nhân vượt ngưỡng 500ms cho startup khi chưa đo decomposition).
   - **Xác nhận trạng thái:** Vấn đề này **ĐÃ ĐƯỢC GIẢI QUYẾT TRIỆT ĐỂ** ngay từ phiên bản R3 của Gemini ([`EXT-07M-W5-R3-103.md`](file:///D:/Web_mining_20261/scholargraph/management/public_search/reviews/GEMINI/EXT-07M-W5-R3-103.md)) theo phản biện nhất quán của SOL (`consistency 103`):
     > *"Phép đo CLI bao gồm startup; chưa đo riêng chi phí này nên chưa quy nguyên nhân cho startup. Báo cáo ghi nhận sự thật thực nghiệm rằng phép đo end-to-end của CLI đạt P95 là 0.5674156s và không đạt mục tiêu đề xuất < 500ms, đồng thời không đưa ra các con số suy đoán chưa đo lường về in-process hay startup ms."*
   - Do đó, nhận xét của MUSE tại dòng 27 của `EXT-07G-CONSISTENCY-104.md` hiện tại chỉ mang tính chất ghi chú lịch sử (outdated note), không phải một phát hiện mở (open finding).

2. **Phân định rõ ràng Mục tiêu Snapshot giữa các Module:**
   - 7/7 tệp thuộc phạm vi Storage, Export, Verifier và Freeze (`store.py`, `export.py`, `verify_public_search.py`, các test liên quan) giữ nguyên 100% mã băm exact từ commit `7726c83`.
   - Các sửa đổi về giao diện UI (`6a5d4e1`) chỉ tác động tới `ui/static/public_search.js` và `tests/unit/test_public_ui_paging.py`.
   - Commit `66264a7` tích hợp các sửa đổi của SOL cho backend service và CLI (`service.py`, `search_public.py`, các bài test service/cli).
   - Sự phân định ranh giới commit này được cả ba bên ghi nhận nhất quán, không xảy ra xung đột hay nhầm lẫn target audit.

---

## 4. Giới hạn Kiểm toán (Limitations)

1. **Thực thi Native của Auditor:** Là `NOT_RUN` do lệnh terminal bị runtime từ chối cấp quyền; bằng chứng kiểm thử dựa trên phân tích mã nguồn độc lập và kết quả chạy thực tế do Coordinator và MUSE cung cấp.
2. **Model Runtime:** Auditor sử dụng runtime model `unknown` (không có telemetry xác minh từ môi trường Antigravity; người dùng chỉ định `Gemini 3.8 Flash High`).
3. **Lịch sử Lỗi Upstream:** 6 lần chạy partial failure trong cohort 096 được giữ nguyên vẹn trong lịch sử tích lũy (26 runs tổng cộng = 20 success + 6 partial failure), không bị ghi đè.
4. **Mẫu Độ trễ n=5 & Mục tiêu Cache:** Mẫu đo pilot gồm 5 query; độ trễ P95 cache `0.5674156s` không đạt mục tiêu proposal `< 500ms`.
5. **Cơ chế Rate Limit:** Giới hạn tần suất request của arXiv là process-local.
6. **Xác nhận Trình duyệt của Con người:** Trạng thái human browser demo được ghi nhận chính xác là **`PENDING`**.
7. **Quy chế Dừng Review:** Báo cáo này hoàn tất chu trình đối soát nhất quán bên thứ ba; không tiếp tục mở rộng chuỗi review vô hạn. Không tiến hành EXT-08 trước khi Coordinator chính thức chốt 3 audit đạt DONE.

---

## 5. Kết luận & Phán quyết (Verdict)

**Phán quyết:** **`PASS`**

- **Căn cứ phán quyết:**
  1. Báo cáo `EXT-07S-W5-R2-104.md` của MUSE phân tích mã nguồn chính xác, đối soát toán học khớp 1:1, chẩn đoán nguyên nhân lỗi đường dẫn dài Windows khách quan và có bằng chứng đối chứng rõ ràng.
  2. Báo cáo regression toàn diện của Coordinator (`regression-w5-104.json`) với **630/630 tests PASS** khẳng định commit `66264a7` hoàn toàn không có lỗi hồi quy và bảo toàn 100% core freeze.
  3. Các phát hiện kỹ thuật F-01 và F-02 đã được SOL khắc phục triệt để theo đúng tiêu chuẩn kỹ thuật bắt buộc; F-03 được hoãn có văn bản theo đúng thẩm quyền điều phối.
  4. Tính nhất quán chéo giữa 3 báo cáo audit (EXT-07S của MUSE, EXT-07G của SOL, EXT-07M của GEMINI) đã đạt được sự đồng thuận tuyệt đối.
