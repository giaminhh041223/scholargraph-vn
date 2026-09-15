# Gói nghiệm thu SG-010 — Audit chất lượng dữ liệu (Cập nhật sau Review F1–F5)

- **Task ID:** SG-010.
- **Tiêu đề:** Audit chất lượng dữ liệu.
- **Mốc / Tuần:** M2 / Tuần 2; Ưu tiên: CORE.
- **Vai trò:** D/R.
- **Phụ thuộc:** SG-009 (DONE).
- **Trạng thái:** Sẵn sàng tái nghiệm thu (Ready for Re-review).

## 1. Phạm vi và Khắc phục Review Codex

Theo [TASKS.md](../../docs/TASKS.md#sg-010), [RESEARCH_PROTOCOL.md](../../docs/RESEARCH_PROTOCOL.md) và biên bản review [SG-010-CODEX-REVIEW-20260916.md](SG-010-CODEX-REVIEW-20260916.md):
- **F1 [P1] - Động hóa kết luận kiểm tra & CLI gate:**
  - `run_full_beir_audit` tính toán động toàn bộ danh sách lỗi `errors`, cờ `audit_passed` và trạng thái `referential_integrity_status` thay vì trả kết luận PASS tĩnh.
  - CLI `beir_audit.py` thoát mã lỗi `sys.exit(1)` khi có vi phạm toàn vẹn dữ liệu.
  - `audit_scifact_train_test_overlap` tính toán động `status` (PASS/FAIL) và `verdict` theo số lượng ID/text overlap thực tế.
  - Kiểm tra canonical roundtrip 100% ID trên toàn bộ danh mục tài liệu và câu truy vấn.
- **F2 [P2] - Độc lập hóa và nâng cấp kiểm thử tự động:**
  - `tests/unit/test_data_integrity.py` không đọc file JSON tĩnh mà thực thi trực tiếp logic của auditor.
  - Thêm 5 negative test cases với dữ liệu synthetic lỗi (duplicate corpus ID, orphan qrels, conflicting scores, missing both title & text, train-test query ID collision, failing gate).
  - Thêm live test chạy trực tiếp `run_full_beir_audit` trên dữ liệu thật BEIR ra thư mục tạm.
  - Thêm consistency tests tự động đối chiếu các mã băm và thống kê trong `DATA_CARD.md` với manifests và audit report.
- **F3 [P2] - Chuẩn hóa mã băm SHA-256 trong Data Card:**
  - Cập nhật đúng 100% các giá trị SHA-256 trong bảng 2.2 của `DATA_CARD.md` khớp với `beir_scifact.json`, `beir_scidocs.json` và file thô trên đĩa.
- **F4 [P2] - Đồng bộ hóa thống kê độ dài từ vựng:**
  - Chuẩn hóa toàn bộ min, max, mean, std, median, percentiles trong Section 4 của `DATA_CARD.md` khớp hoàn toàn với báo cáo máy đọc `beir_data_audit.json`.
- **F5 [P2] - Chính xác hóa giấy phép bản quyền:**
  - Phân định rõ ràng: SciFact gồm claims/evidence (CC BY 4.0) và abstracts (ODC-By 1.0); SCIDOCS (CC BY 4.0 - yêu cầu ghi công, không phải CC0); BEIR code package (Apache-2.0).

## 2. Đầu ra và Bằng chứng

- **Mã nguồn Audit:** [src/scholargraph/ingest/beir_audit.py](../../src/scholargraph/ingest/beir_audit.py)
- **Tài liệu Data Card:** [docs/DATA_CARD.md](../../docs/DATA_CARD.md)
- **Kiểm thử tự động:** [tests/unit/test_data_integrity.py](../../tests/unit/test_data_integrity.py)
- **Báo cáo dữ liệu máy đọc:** [artifacts/reports/beir_data_audit.json](../../artifacts/reports/beir_data_audit.json)

## 3. Kết quả kiểm tra chính

1. **Pytest module tính toàn vẹn:** `pytest tests/unit/test_data_integrity.py -v` $\to$ **13/13 passed in 20.56s** (bao gồm 5 negative tests, 3 unit tests, 3 live tests, 2 consistency tests).
2. **Pytest toàn bộ suite:** `pytest tests -q` $\to$ **91/91 passed in 22.22s**.
3. **Project Continuity Validator:** `.\scripts\check_project.ps1` $\to$ **PASS** (exit code 0).
