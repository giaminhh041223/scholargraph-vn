# Gói nghiệm thu SG-010 — Audit chất lượng dữ liệu (Cập nhật sau Recheck R1–R2)

- **Task ID:** SG-010.
- **Tiêu đề:** Audit chất lượng dữ liệu.
- **Mốc / Tuần:** M2 / Tuần 2; Ưu tiên: CORE.
- **Vai trò:** D/R.
- **Phụ thuộc:** SG-009 (DONE).
- **Trạng thái:** Đã hoàn thành (DONE - All findings closed).

## 1. Phạm vi và Khắc phục Review Codex

Theo [TASKS.md](../../docs/TASKS.md#sg-010), [RESEARCH_PROTOCOL.md](../../docs/RESEARCH_PROTOCOL.md), biên bản review [SG-010-CODEX-REVIEW-20260916.md](SG-010-CODEX-REVIEW-20260916.md) và biên bản recheck [SG-010-CODEX-RECHECK-20260916.md](SG-010-CODEX-RECHECK-20260916.md):
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
- **R1 [P2] - Động hóa 100% narrative explanation trong auditor:**
  - Các chuỗi giải thích cho `scifact_empty_text_documents`, `scifact_train_test_query_leakage`, và `scidocs_empty_abstract_documents` được sinh động 100% từ kết quả kiểm tra và bộ đếm thực tế; không còn chuỗi tĩnh mâu thuẫn khi chạy trên các fixture khác snapshot thật.
  - Bổ sung kiểm thử hồi quy `test_dynamic_narrative_explanations_synthetic` xác nhận trên các fixture 0-overlap, 1-overlap và custom missingness.
- **R2 [P2] - Phân rã chính xác số cặp nhãn 0 của SCIDOCS empty-text documents:**
  - Bổ sung bộ đếm phân rã vào `audit_raw_qrels` (`empty_text_docs_zero_only_count` = 229, `empty_text_docs_both_count` = 15, `empty_text_zero_pairs_in_zero_only_docs_count` = 262, `empty_text_zero_pairs_in_positive_docs_count` = 17, `empty_text_total_pairs_count` = 466).
  - Sửa đổi Section 5.2 của `DATA_CARD.md` phân định rõ: 115 tài liệu có liên kết dương tính (187 cặp nhãn 1; trong đó 15 tài liệu có thêm 17 cặp nhãn 0), 229 tài liệu chỉ có nhãn 0 (262 cặp nhãn 0), tổng cộng 279 cặp nhãn 0 trên toàn bộ 344 tài liệu.
  - Bổ sung kiểm thử hồi quy `test_scidocs_empty_text_relevance_breakdown_and_datacard`.

## 2. Đầu ra và Bằng chứng

- **Mã nguồn Audit:** [src/scholargraph/ingest/beir_audit.py](../../src/scholargraph/ingest/beir_audit.py)
- **Tài liệu Data Card:** [docs/DATA_CARD.md](../../docs/DATA_CARD.md)
- **Kiểm thử tự động:** [tests/unit/test_data_integrity.py](../../tests/unit/test_data_integrity.py)
- **Báo cáo dữ liệu máy đọc:** [artifacts/reports/beir_data_audit.json](../../artifacts/reports/beir_data_audit.json)
- **Biên bản xử lý Recheck:** [SG-010-CODEX-RECHECK-RESOLUTION-20260916.md](SG-010-CODEX-RECHECK-RESOLUTION-20260916.md)

## 3. Kết quả kiểm tra chính

1. **Pytest module tính toàn vẹn:** `pytest tests/unit/test_data_integrity.py -v` $\to$ **15/15 passed in 21.95s** (bao gồm 5 negative tests, 3 unit tests, 3 live tests, 2 consistency tests, 2 narrative/partition regression tests).
2. **Pytest toàn bộ suite:** `pytest tests -q` $\to$ **93/93 passed in 43.36s**.
3. **Project Continuity Validator:** `.\scripts\check_project.ps1` $\to$ **PASS** (exit code 0).
