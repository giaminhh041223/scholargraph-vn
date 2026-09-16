# Báo cáo xử lý phát hiện Codex Recheck (R1 & R2) — Task SG-010

- **Thời điểm:** 2026-09-16T01:56:00+07:00
- **Bản review gốc:** [SG-010-CODEX-RECHECK-20260916.md](SG-010-CODEX-RECHECK-20260916.md)
- **Trạng thái trước sửa:** CHANGES_REQUIRED (P1 đã đóng, còn 2 P2: R1 và R2).
- **Kết luận sau sửa:** **PASS TOÀN BỘ — ĐÃ GIẢI QUYẾT TRIỆT ĐỂ R1 VÀ R2.**

---

## 1. Chi tiết khắc phục các phát hiện

### R1 — [P2] Động hóa 100% phần narrative explanation trong Auditor
- **Hiện tượng cũ:** `anomalies_summary.scifact_train_test_query_leakage.explanation` ghi tĩnh `"exactly 2 queries: test query 1292 matches train query 1291..."`; `scifact_empty_text_documents.explanation` ghi tĩnh `"All 5,183 SciFact documents..."`. Khi chạy trên synthetic fixture khác snapshot thật, chuỗi giải thích bị mâu thuẫn với số đếm thực tế.
- **Biện pháp khắc phục trong `src/scholargraph/ingest/beir_audit.py`:**
  - `scifact_empty_text_documents.explanation`: Sinh chuỗi động theo `total_documents` và `empty_or_missing_text_count`.
    - Nếu 0 document thiếu: `All {scifact_corpus_size:,} SciFact documents have both non-empty title and abstract.`
    - Nếu có document thiếu: `Found {scifact_empty_count:,} SciFact documents with empty abstract/text out of {scifact_corpus_size:,} total documents.`
  - `scifact_train_test_query_leakage.explanation`: Sinh chuỗi động từ `overlap_audit` (`cross_split_checks.scifact_train_vs_test`).
    - Nếu 0 overlap: `No query ID overlap and no query text exact overlap detected between SciFact train and test splits (status: {overlap_audit['status']}). {overlap_audit['verdict']}`
    - Nếu có overlap: Định dạng động danh sách cặp query từ `query_text_exact_overlap_details` và trích dẫn số `shared_relevant_documents_count`.
  - `scidocs_empty_abstract_documents.explanation`: Sinh chuỗi động từ các bộ đếm phân rã chính xác của qrels.
- **Kiểm thử tự động bổ sung:**
  - `test_dynamic_narrative_explanations_synthetic` trong `tests/unit/test_data_integrity.py`:
    - Chạy trên fixture synthetic 1 document, 0 overlap: xác nhận không còn chứa các chuỗi tĩnh `"1292"`, `"1291"`, `"exactly 2 queries"`, `"5,183"`; xuất đúng thông điệp 0 overlap và 1 document.
    - Chạy trên fixture synthetic với custom query overlap: xác nhận xuất đúng query ID và query text của fixture.
    - Chạy trên fixture synthetic có document thiếu abstract: xác nhận đếm đúng số document thiếu.

---

### R2 — [P2] Phân rã chính xác số cặp nhãn 0 của 344 tài liệu SCIDOCS thiếu text
- **Hiện tượng cũ:** Tại dòng 91 của `docs/DATA_CARD.md`, câu diễn đạt cũ gộp toàn bộ 279 cặp nhãn 0 vào nhóm 229 tài liệu, làm sai lệch phân bổ 17 cặp nhãn 0 thuộc 15 tài liệu có cả liên kết dương tính.
- **Bản chất dữ liệu thực tế đã xác thực:**
  - Tổng số tài liệu SCIDOCS thiếu text: **344 tài liệu**.
  - Tổng số cặp đánh giá trong test qrels: **466 cặp** (187 cặp nhãn 1, **279 cặp nhãn 0**).
  - Phân rã theo tài liệu:
    - **115 tài liệu** xuất hiện trong ít nhất một cặp dương tính (187 cặp nhãn 1). Trong số 115 tài liệu này, có **15 tài liệu** đồng thời xuất hiện trong **17 cặp mang nhãn 0** với các query khác.
    - **229 tài liệu còn lại** hoàn toàn chỉ xuất hiện với nhãn không liên quan (tổng cộng **262 cặp nhãn 0**).
    - Tổng cặp nhãn 0: $262 + 17 = 279$ cặp.
- **Biện pháp khắc phục:**
  1. Trong `src/scholargraph/ingest/beir_audit.py` (`audit_raw_qrels`):
     - Bổ sung đếm chi tiết vào `empty_text_docs_impact`: `empty_text_docs_zero_only_count` (229), `empty_text_docs_both_count` (15), `empty_text_zero_pairs_in_zero_only_docs_count` (262), `empty_text_zero_pairs_in_positive_docs_count` (17), `empty_text_total_pairs_count` (466).
  2. Trong `docs/DATA_CARD.md` (Mục 5.2):
     - Diễn đạt chính xác 100% từng nhóm tài liệu, số lượng cặp nhãn 1 và nhãn 0, bảo đảm tính nhất quán toán học hoàn hảo.
  3. Kiểm thử tự động bổ sung:
     - `test_scidocs_empty_text_relevance_breakdown_and_datacard` trong `tests/unit/test_data_integrity.py`: Xác thực độc lập các số đếm trên qrels thật và kiểm tra sự hiện diện nhất quán trong `docs/DATA_CARD.md`.

---

## 2. Kết quả kiểm chứng thực tế

1. **Unit tests tính toàn vẹn:**
   - Lệnh: `pytest tests/unit/test_data_integrity.py -v`
   - Kết quả: **15/15 tests PASSED in 21.95s** (bao gồm 2 test cases mới cho R1 và R2).
2. **Full test suite dự án:**
   - Lệnh: `pytest -q`
   - Kết quả: **93/93 tests PASSED in 43.36s** (không có cảnh báo hay lỗi hồi quy).
3. **Project continuity check:**
   - Lệnh: `.\scripts\check_project.ps1`
   - Kết quả: **PASS (exit code 0)**, 50 task cards, 220 internal links.
