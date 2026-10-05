# Danh mục Kiểm tra Gói Nộp Cuối — `SUBMISSION_CHECKLIST` (SG-045)

> **Trạng thái gói nộp:** Toàn bộ công cụ, mã nguồn, 746 kiểm thử tự động, chỉ mục bằng chứng ([evidence_index.json](../artifacts/reports/evidence_index.json)), biểu đồ SVG (`reports/figures/*.svg`), và bản thảo báo cáo/slides/Q&A phía Agent (`G0`–`G4`) **đã hoàn tất 100%**.
> Tuy nhiên, theo đúng quy tắc chống gian lận học thuật (`SG-045`: *"Không DONE nếu thiếu core evidence"*), bảng trạng thái dự án giữ nguyên `DONE = 42` và **chờ hai thành viên con người hoàn tất 3 cổng bắt buộc (`H-1`, `H-2`, `H-3`)** dưới đây trước khi đóng `SG-030`, `SG-033`, `SG-034`, `SG-042`, `SG-043`, `SG-044`, `SG-045`.

---

## 1. Trạng thái các Hạng mục Kỹ thuật & Học thuật Đã Khóa (Verified PASS)

| Hạng mục | Tạo phẩm / Lệnh kiểm chứng | Trạng thái |
|---|---|---|
| **Hợp nhất kho chính & Bảo toàn Byte-Exact (`SG-051`)** | `.gitattributes` (`* -text`), `git cat-file -t e959f68` (`commit`), `git cat-file -t dcca385` (`commit`) | **PASS (`DONE`)** |
| **Vệ sinh kiểm thử & Cô lập dữ liệu Freeze (`SG-052`)** | `pytest tests -q` (không chạm `mtime`/`sha256` của `works_text.jsonl`), đủ 3 nhánh fallback hybrid API | **PASS (`DONE`)** |
| **Đóng băng cấu hình chính (`SG-027`)** | [frozen_main.json](../configs/frozen_main.json) (`sha256 = 34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557`), [SG-027-REVIEW-20260929.md](../management/reviews/SG-027-REVIEW-20260929.md) | **PASS (`DONE`)** |
| **Chạy tập Test niêm phong Track A & B (`SG-028`)** | [main_results.md](../artifacts/reports/main_results.md), [main_run_registry.json](../artifacts/reports/main_run_registry.json), [SG-028-REVIEW-20260929.md](../management/reviews/SG-028-REVIEW-20260929.md) (`|diff| = 0.00e+00` trên 45/45 con số) | **PASS (`DONE`)** |
| **Nghiên cứu cắt bỏ & Độ bền vững (`SG-029`)** | [ablation.md](../artifacts/reports/ablation.md), [robustness.md](../artifacts/reports/robustness.md), [SG-029-REVIEW-20260929.md](../management/reviews/SG-029-REVIEW-20260929.md) | **PASS (`DONE`)** |
| **Hồ sơ hiệu năng thực tế (`SG-040`)** | [performance.md](../artifacts/reports/performance.md), [SG-040-REVIEW-20260929.md](../management/reviews/SG-040-REVIEW-20260929.md) | **PASS (`DONE`)** |
| **Đóng gói tái lập & Launcher Offline (`SG-041`)** | [REPRODUCE.md](REPRODUCE.md), [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md), `scripts/run_demo.ps1` (`13/13 PASS`), [SG-041-REVIEW-20260929.md](../management/reviews/SG-041-REVIEW-20260929.md) | **PASS (`DONE`)** |
| **Chỉ mục bằng chứng, Biểu đồ & Kiểm chứng Claims (`CX-4`)** | [evidence_index.json](../artifacts/reports/evidence_index.json), `reports/figures/*.svg`, `python scripts/verify_claims.py` (`PASS`) | **PASS (Sẵn sàng)** |
| **Bản thảo Báo cáo, Slides & 18 Câu hỏi Phản biện (`GM-6`)** | [final_report.md](../reports/final_report.md), [CLAIMS_CHECKLIST.md](CLAIMS_CHECKLIST.md), [defense_slides.md](../reports/defense_slides.md), [DEFENSE_QA.md](DEFENSE_QA.md) | **PASS (Sẵn sàng)** |

---

## 2. Các Cổng Con Người Còn Lại Cần Hai Thành Viên Thực Hiện (`H-1`, `H-2`, `H-3`)

Để hoàn tất 7 task cuối cùng (`SG-030`, `SG-033`, `SG-034`, `SG-042`, `SG-043`, `SG-044`, `SG-045`), hai thành viên thực hiện theo đúng trình tự sau:

### Bước 1 — Cổng `H-1` (`SG-030` — Đọc 24 Error Packets)
1. Cả hai thành viên cùng đọc 24 ca lỗi trong `artifacts/reports/error_packets.json` và ghi nhận thảo luận chung vào [ERROR_ANALYSIS.md](ERROR_ANALYSIS.md).
2. Chuyển trạng thái `SG-030` từ `REVIEW` $\to$ `DONE` trong `management/tasks.json`.

### Bước 2 — Cổng `H-2` & `SG-034` (`SG-033` $\to$ `SG-034` — Gán nhãn Tiếng Việt & Đóng băng VN)
> Bộ query hiện hành là **v2** (`vn2:`, [ADR-023](../management/DECISIONS.md)). Nhãn v1 không dùng cho đánh giá. Mặc định của các script vẫn trỏ v1, nên luôn truyền đường dẫn v2 như dưới đây.

1. **Gán nhãn Dev trước (`227` cặp):** Hai thành viên mở `label_tool.html` trong `artifacts/vn_labeling_kit_SG033_v2.zip` (xem `HUONG_DAN_GAN_NHAN.md`) và chấm độc lập 10 truy vấn `dev` (nên làm 5 query pilot `vn2:dev:001`–`005` trước). Kết quả xuất ra là `vn2_labels_A_dev.jsonl` / `vn2_labels_B_dev.jsonl`.
2. **Gộp và đo độ đồng thuận trước thảo luận:**
   ```powershell
   .\.venv\Scripts\python.exe scripts\manage_vn_labels.py merge --file-a vn2_labels_A_dev.jsonl --file-b vn2_labels_B_dev.jsonl --output data/annotations/v2/vn_labels_dev.jsonl
   .\.venv\Scripts\python.exe scripts\score_vn_agreement.py --labels data/annotations/v2/vn_labels_dev.jsonl
   ```
3. **Phân xử bất đồng trên Dev (`round = "adjudicated"`) và chạy khóa cấu hình Dev (`SG-034`):**
   ```powershell
   .\.venv\Scripts\python.exe scriptsun_vn_eval.py --phase freeze-dev --pool data/annotations/v2/vn_pool.json --labels data/annotations/v2/vn_labels_dev.jsonl
   ```
   Kiểm tra `configs/frozen_vn.json`, đặt `"human_approved": true` sau khi duyệt.
4. **Gán nhãn Test (`452` cặp) và chấm điểm Test một lần (`SG-034`):** Gộp `vn2_labels_{A,B}_test.jsonl` và phân xử như bước 2–3, sau đó chạy `eval-test` với **cùng** `--pool`. Nếu pool khác với pool đã ghim lúc freeze, lệnh sẽ exit 1.
   ```powershell
   .\.venv\Scripts\python.exe scriptsun_vn_eval.py --phase eval-test --pool data/annotations/v2/vn_pool.json --labels data/annotations/v2/vn_labels_test.jsonl
   .\.venv\Scripts\python.exe scriptsuild_evidence_index.py
   ```
   Cập nhật bảng Track C trong [final_report.md](../reports/final_report.md) và [CLAIMS_CHECKLIST.md](CLAIMS_CHECKLIST.md), sau đó đóng `SG-033` và `SG-034` sang `DONE`.

### Bước 3 — Cổng `H-3` (`SG-042`, `SG-043`, `SG-044`, `SG-045`)
1. **Tái lập chéo bởi thành viên thứ hai (`SG-042`):** Thành viên thứ hai chạy lại baseline văn bản và nhánh đồ thị, xuất JSON kết quả và chạy:
   ```powershell
   .\.venv\Scripts\python.exe scripts\compare_reproduction.py --reproducer <ten_thanh_vien_2> --candidate <duong_dan_json> --output-dir artifacts/reports
   ```
2. **Duyệt sở hữu báo cáo (`SG-043`) & Diễn tập 2 lần đổi vai (`SG-044`):**
   - Kiểm tra lại `.\.venv\Scripts\python.exe scripts\verify_claims.py`.
   - Ghi thời lượng 2 lần diễn tập vào [rehearsal_notes.md](../artifacts/reports/rehearsal_notes.md).
3. **Chốt gói nộp cuối (`SG-045`):**
   ```powershell
   .\.venv\Scripts\python.exe scripts\verify_release.py --write-manifest
   powershell -ExecutionPolicy Bypass -File scripts\check_project.ps1
   ```
