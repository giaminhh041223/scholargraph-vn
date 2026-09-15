# Gói nghiệm thu SG-010 — Audit chất lượng dữ liệu

- **Task ID:** SG-010.
- **Tiêu đề:** Audit chất lượng dữ liệu.
- **Mốc / Tuần:** M2 / Tuần 2; Ưu tiên: CORE.
- **Vai trò:** D/R.
- **Phụ thuộc:** SG-009 (DONE).
- **Trạng thái:** Sẵn sàng nghiệm thu (Ready for Review).

## 1. Phạm vi và Tiêu chuẩn nghiệm thu

Theo [TASKS.md](../../docs/TASKS.md#sg-010) và [RESEARCH_PROTOCOL.md](../../docs/RESEARCH_PROTOCOL.md):
1. **Toàn vẹn ID & Tham chiếu Qrels:** Mọi ID corpus và query là duy nhất; mọi query-id và corpus-id trong qrels đều tồn tại trong danh mục; không có cặp trùng lặp hoặc xung đột điểm số; ánh xạ canonical ID lossless.
2. **Missing text / Phân bố nhãn / Trùng lặp:** Thống kê độ dài văn bản theo chuẩn tokenizer Protocol v1 (`(?u)\b\w+\b`, Unicode casefold); kiểm tra thiếu abstract/title.
3. **Giữ nguyên raw benchmark & báo cáo dị thường:** Không lọc ngầm tập dữ liệu để làm đẹp điểm số; ghi nhận rõ ràng các dị thường.

## 2. Đầu ra và Bằng chứng

- **Mã nguồn Audit:** [src/scholargraph/ingest/beir_audit.py](../../src/scholargraph/ingest/beir_audit.py)
- **Tài liệu Data Card:** [docs/DATA_CARD.md](../../docs/DATA_CARD.md)
- **Kiểm thử tự động:** [tests/unit/test_data_integrity.py](../../tests/unit/test_data_integrity.py)
- **Báo cáo dữ liệu máy đọc:** [artifacts/reports/beir_data_audit.json](../../artifacts/reports/beir_data_audit.json)

## 3. Kết quả kiểm tra chính

1. **Pytest toàn bộ suite:** `pytest tests -q` $\to$ **88 passed in 26.42s** (10/10 test cases mới về data integrity đều PASS).
2. **Project Continuity Validator:** `.\scripts\check_project.ps1` $\to$ **PASS** (exit code 0, 202 local markdown links).
3. **Phát hiện dị thường học thuật quan trọng:**
   - **SCIDOCS:** Đúng 344 tài liệu thiếu abstract (chỉ có tiêu đề). Tất cả 344 tài liệu này đều nằm trong tập qrels test; trong đó có đúng **115 tài liệu mang nhãn liên quan dương tính (`score = 1`)**. Đã ghi nhận trong Data Card và Giao thức; giữ nguyên 100% trong index, không lọc bỏ.
   - **SciFact:** Toàn bộ 5.183 tài liệu có đủ tiêu đề và tóm tắt. Phát hiện 2 câu truy vấn trong tập test trùng 100% văn bản với 2 câu truy vấn trong tập train upstream của BEIR:
     - `Test 1292` & `Train 1291` (*"There is no association between HNF4A mutations and diabetes risks."* $\to$ doc `56893404`).
     - `Test 870` & `Train 871` (*"Obesity decreases life quality."* $\to$ doc `195689316`).
     Không gian ID hoàn toàn phân tách (`query_id_overlap_count = 0`). Đây là đặc tính vốn có của dữ liệu gốc upstream và được ghi nhận minh bạch.
