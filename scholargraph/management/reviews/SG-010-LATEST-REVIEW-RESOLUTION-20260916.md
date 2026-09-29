# SG-010 — Khắc phục phát hiện Review mới nhất (L1, L2 & 3 Phát hiện Kháng nghị Chống Lỗi Ngầm)

- **Thời điểm:** 2026-09-16T10:00:00+07:00
- **Tài liệu review đối chiếu:** [SG-010-LATEST-CODEX-REVIEW-20260916.md](SG-010-LATEST-CODEX-REVIEW-20260916.md) & Phản hồi Review bổ sung từ Codex (2026-09-16)
- **Trạng thái:** **ALL 5 FINDINGS RESOLVED / PASS**

---

## 1. Khắc phục L1 [P1] — Thiếu required qrels split (SCIDOCS test.tsv) bị bỏ qua

### Vấn đề được nêu trong Review
- Bản sửa trước dùng `.get("test", {})` khi đọc SCIDOCS split. Khi file `scidocs/qrels/test.tsv` bị thiếu hoặc đổi tên (ví dụ: `test.tsv.disabled`), auditor chỉ audit các split tìm thấy (danh sách rỗng), không kiểm tra xem split bắt buộc theo protocol có tồn tại hay không.
- Hậu quả: `splits_audit` rỗng, `loader_verification` không chạy, các giá trị đo đạc bị thay thế bằng 0 trong narrative, `errors` rỗng $\to$ `audit_passed=True` và CLI thoát mã 0 dù thiếu tập nhãn bắt buộc.

### Giải pháp kỹ thuật đã triển khai
1. **Định nghĩa ràng buộc split bắt buộc:**
   Bổ sung mapping cố định `REQUIRED_SPLITS`:
   - `scifact`: `("train", "test")`
   - `scidocs`: `("test",)`
2. **Kiểm tra trong `audit_single_dataset`:**
   - So khớp các file `*.tsv` tìm thấy trong `qrels/` với `required_splits`.
   - Nếu thiếu split bắt buộc, ghi nhận vào `missing_required_splits` của dataset.
   - Thử nghiệm loader offline (`BeirLoader.load`) trên **tất cả** các split bắt buộc. Nếu file bị thiếu, loader sẽ ném lỗi `BeirDataError("Missing BEIR qrels split: ...")` và được ghi nhận trạng thái `FAIL` trong `loader_verification`.
3. **Kiểm tra trong `audit_scifact_train_test_overlap`:**
   - Kiểm tra chủ động sự tồn tại của `queries.jsonl`, `train.tsv` và `test.tsv` trước khi mở file. Trả về `status: "FAIL"` nếu thiếu file.
4. **Đánh giá integrity gate động:**
   - Duyệt `missing_required_splits` cho mỗi dataset: nếu có split thiếu, thêm lỗi vào `integrity_errors`.
   - Duyệt `loader_verification`: bắt buộc mọi split phải đạt `PASS`.
   - Duyệt `cross_split_checks`: nếu có lỗi thiếu file hoặc va chạm ID, thêm vào `integrity_errors`.
   - Nếu `integrity_errors` có phần tử: `audit_passed = False`, `referential_integrity_status` báo `FAIL`, `all_integrity_checks_passed = False`.
5. **Không thay thế phép đo chưa thực hiện bằng 0:**
   - Nếu `test` split bị thiếu, `scidocs_qrel_impact` được đặt là `None`; các trường `appears_in_test_qrels` và `appears_as_positive_in_test_qrels` đặt là `None` (không gán 0).
   - CLI in danh sách lỗi ra `sys.stderr` và thoát với mã lỗi `1` (`sys.exit(1)`).

---

## 2. Khắc phục L2 [P2] — Narrative báo đủ title dù chỉ kiểm tra abstract

### Vấn đề được nêu trong Review
- Nhánh `empty_or_missing_text_count == 0` trước đây vội vàng kết luận: *"All ... documents have both non-empty title and abstract..."* mà không kiểm tra `empty_or_missing_title_count`.
- Khi tài liệu là text-only (`title: ""`, `text: "..."`), `empty_or_missing_text_count == 0` nhưng `empty_or_missing_title_count > 0`. Việc tuyên bố có cả hai trường là sai thực tế.

### Giải pháp kỹ thuật đã triển khai
Tách bạch đầy đủ 4 kịch bản missingness dựa trên cả hai bộ đếm `empty_or_missing_text_count` và `empty_or_missing_title_count`:
1. **Đủ cả 2 trường (`empty_text == 0` và `empty_title == 0`):**
   - SciFact: `"All {scifact_corpus_size:,} SciFact documents have both non-empty title and abstract."`
   - SCIDOCS: `"All {scidocs_corpus_size:,} SCIDOCS documents have both non-empty title and abstract text."`
2. **Text-only (`empty_text == 0` và `empty_title > 0`):**
   - SciFact: `"All {scifact_corpus_size:,} SciFact documents have non-empty abstract text; {scifact_empty_title_count:,} document(s) have empty title (text-only)."`
   - SCIDOCS: `"All {scidocs_corpus_size:,} SCIDOCS documents have non-empty abstract text; {scidocs_empty_title_count:,} document(s) have empty title (text-only)."`
3. **Title-only (`empty_text > 0` và `empty_title == 0`):**
   - SciFact: `"Found {scifact_empty_count:,} SciFact documents with empty abstract/text out of {scifact_corpus_size:,} total documents."`
   - SCIDOCS: Mô tả động provenance, tỉ lệ và điểm relevance thực tế.
4. **Thiếu hỗn hợp trong corpus (`empty_text > 0` và `empty_title > 0`):**
   - Mô tả chính xác số lượng tài liệu thiếu abstract và số lượng tài liệu thiếu title riêng biệt.
5. **Thiếu cả hai trên cùng 1 tài liệu (`empty_both_count > 0`):**
   - Tiếp tục bị chặn bởi dynamic integrity gate (`{d_name}: {count} document(s) missing both title and text`).

---

## 3. Khắc phục 3 Phát hiện Codex Bổ sung (Tuân thủ Anti-Silent-Bypass Protocol)

### Phát hiện 1 [P1] — Input hỏng không tạo báo cáo audit FAIL có cấu trúc
- **Vấn đề:** Khi thiếu `corpus.jsonl`/`queries.jsonl`, qrels sai header, qrels có dòng dị dạng, hoặc score không phải số nguyên, script ném exception unhandled và crash giữa chừng, không lưu file báo cáo `beir_data_audit.json`.
- **Giải pháp:**
  - Trong `audit_single_dataset`: kiểm tra sự tồn tại của `corpus_file`, `queries_file`, bọc toàn bộ khối đọc và parse trong `try...except Exception as exc:`. Khi có lỗi, ghi nhận vào `dataset_errors` và gán status `FAIL`.
  - Trong `audit_raw_qrels`: kiểm tra chuyển đổi `score = int(s_str)`, nếu không phải số nguyên ném `ValueError` kèm số dòng và tên file.
  - Trong `run_full_beir_audit`: bọc `audit_single_dataset` và `audit_scifact_train_test_overlap` an toàn, thu thập toàn bộ `dataset_errors` vào `integrity_errors`. Báo cáo JSON `beir_data_audit.json` được **luôn luôn ghi xuống đĩa trước khi trả về**, bảo đảm `audit_passed: false` và liệt kê chi tiết các lỗi.
  - CLI `__main__` đọc kết quả, in thông báo `AUDIT FAILED` cùng chi tiết lỗi ra stderr và thoát mã lỗi `1`.

### Phát hiện 2 [P1] — Báo cáo nói "không có overlap" khi phép đo không chạy được
- **Vấn đề:** Khi thiếu `scifact/train.tsv`, `audit_scifact_train_test_overlap` trả về `status: FAIL` với placeholder `exact_overlap_count=0` và `id_overlap_count=0`. Nhánh `if exact_overlap_count == 0 and id_overlap_count == 0:` đã đánh giá `True` và in câu narrative: `"No query ID overlap and no query text exact overlap detected..."` dù phép đo đã bị hủy.
- **Giải pháp:**
  - Kiểm tra `if overlap_audit.get("status") == "FAIL":` trước tiên.
  - Nếu `status == "FAIL"`: narrative nêu rõ lý do thất bại, ví dụ: `"FAIL: Cannot audit query leakage between SciFact train and test splits: Missing required SciFact split(s): train.tsv."`
  - Tuyệt đối không phát biểu "No query ID overlap" khi chưa thực hiện được phép đo.
  - Chỉ khi `status == "PASS"` và số lượng overlap bằng 0 mới phát biểu không có overlap.

### Phát hiện 3 [P2] — Narrative văn bản title-only còn hardcode snapshot SCIDOCS
- **Vấn đề:** Code giả định dữ liệu luôn là `"official SCIDOCS BEIR snapshot"`, điểm relevance luôn là `"score=1"`, và in `"All 1 of these 2 document(s)"` khi số tài liệu title-only xuất hiện trong qrels nhỏ hơn tổng số tài liệu title-only.
- **Giải pháp:**
  - Tổng quát hóa xuất xứ: Chỉ gọi là `"In the official SCIDOCS BEIR snapshot"` nếu kích thước corpus đúng bằng 25,657 và số doc title-only đúng bằng 344; ngược lại mô tả `"In the SCIDOCS dataset snapshot ({scidocs_corpus_size:,} docs)"`.
  - Tổng quát hóa tỉ lệ xuất hiện trong qrels:
    - Nếu `in_qrels_count == scidocs_empty_text_count`: `"All {in_qrels_count} of these documents appear in the test split qrels"`.
    - Nếu `0 < in_qrels_count < scidocs_empty_text_count`: `"{in_qrels_count} of these {scidocs_empty_text_count} document(s) appear in the test split qrels"`.
    - Nếu `in_qrels_count == 0`: `"None of these {scidocs_empty_text_count} document(s) appear in the test split qrels"`.
  - Tổng quát hóa điểm số: Trong `audit_raw_qrels`, thu thập tập hợp các điểm relevance dương `empty_text_positive_scores`. Trong narrative, hiển thị động `score={pos_scores[0]}` hoặc `scores in {pos_scores}` dựa trên thực tế đo được.

---

## 4. Kiểm thử Hồi quy Toàn diện & Negative Adversarial Testing

Bổ sung 3 nhóm kiểm thử phá hủy trong `tests/unit/test_data_integrity.py`:
1. `test_malformed_inputs_produce_structured_fail_report` (Parametrized trên 6 kịch bản phá hủy):
   - `missing_corpus`: thiếu file `corpus.jsonl`.
   - `missing_queries`: thiếu file `queries.jsonl`.
   - `bad_qrels_header`: header qrels không đúng `query-id\tcorpus-id\tscore`.
   - `malformed_qrels_row`: dòng qrels thiếu cột (chỉ có 2 cột thay vì 3).
   - `non_integer_score`: score trong qrels là chuỗi không phải số nguyên.
   - `corrupted_json_corpus`: file corpus chứa dòng JSON lỗi cú pháp.
   $\to$ Mọi trường hợp đều sinh file JSON có cấu trúc trên đĩa, `audit_passed: false`, ghi nhận đúng thông điệp lỗi, và subprocess CLI thoát với mã lỗi 1.
2. `test_scifact_missing_split_overlap_narrative_avoids_false_no_overlap`:
   - Xác nhận narrative khi thiếu `train.tsv` bắt đầu bằng `"FAIL: Cannot audit query leakage..."`, không bao giờ chứa `"No query ID overlap"`.
3. `test_title_only_narrative_generalization_non_official_and_custom_scores`:
   - Xác nhận snapshot tùy biến (2 tài liệu, 1 xuất hiện trong qrels với score=2) sinh đúng:
     - `"In the SCIDOCS dataset snapshot (2 docs)"` (không hardcode snapshot chính thức).
     - `"1 of these 2 document(s) appear in the test split qrels"` (không in "All 1 of these 2").
     - `"score=2"` (không hardcode score=1).

**Kết quả kiểm thử thực tế:**
- `pytest tests/unit/test_data_integrity.py -v`: **25/25 passed in 21.72s**.
- Toàn bộ suite dự án: `pytest tests -q`: **165/165 passed in 61.27s**.
- Chạy live auditor trên snapshot đóng băng thực tế: **PASS**, xuất ra [artifacts/reports/beir_data_audit.json](../../artifacts/reports/beir_data_audit.json).
- Project continuity check: `.\scripts\check_project.ps1` **PASS (exit code 0)**.
