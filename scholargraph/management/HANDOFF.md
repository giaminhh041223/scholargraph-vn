# Bàn giao ScholarGraph

NEXT_TASK: SG-011

## Trạng thái — 2026-09-16T01:10:00+07:00

- SG-010 **DONE**: Đã hoàn thành audit chất lượng dữ liệu BEIR và **khắc phục toàn bộ 5 phát hiện (1 P1, 4 P2) từ bản review độc lập của Codex**. Báo cáo tái nghiệm thu [SG-010-RE-REVIEW-20260916.md](reviews/SG-010-RE-REVIEW-20260916.md) đạt **PASS** trên snapshot mới.
- SG-000 đến SG-007, SG-009, SG-010, SG-013 đều đã **DONE**.
- Task **SG-008** giữ nguyên trạng thái **TODO** (hoãn thực hiện theo chỉ đạo trực tiếp của người dùng: *"Khoan không động vào task SG-008 nhé"*).
- Task **SG-012** (BM25 pilot thật) phụ thuộc `[SG-008, SG-010, SG-011]`. Do SG-008 tạm hoãn và SG-011 chưa thực hiện, SG-012 chưa thể chạy pilot metric thật. Kiến trúc BM25 positive-IDF theo Protocol v1 đã sẵn sàng.
- Task **SG-011** (Split và leakage checks) phụ thuộc `[SG-004, SG-010]` $\to$ **Đã đủ 100% điều kiện tiên quyết để thực hiện ngay lập tức**.
- Phiên coordinator/worker SESSION-20260916-021 hoàn tất; không còn active assignment.
- Toàn bộ suite test dự án: **91 passed in 22.22s** (13/13 test cases integrity mới PASS bao gồm 5 negative synthetic tests).

## Bằng chứng và Khắc phục chính của SG-010

- **Mã nguồn và Báo cáo:**
  - [src/scholargraph/ingest/beir_audit.py](../src/scholargraph/ingest/beir_audit.py)
  - [artifacts/reports/beir_data_audit.json](../artifacts/reports/beir_data_audit.json)
  - [docs/DATA_CARD.md](../docs/DATA_CARD.md)
  - [tests/unit/test_data_integrity.py](../tests/unit/test_data_integrity.py)
  - [management/reviews/SG-010-REVIEW-PACKET.md](reviews/SG-010-REVIEW-PACKET.md)
  - [management/reviews/SG-010-CODEX-REVIEW-20260916.md](reviews/SG-010-CODEX-REVIEW-20260916.md)
  - [management/reviews/SG-010-RE-REVIEW-20260916.md](reviews/SG-010-RE-REVIEW-20260916.md)
- **Các điểm đã khắc phục theo review Codex:**
  1. **F1 [P1]:** Auditor chuyển đổi toàn bộ cơ chế sang đánh giá động (tính toán `audit_passed`, danh sách `errors`, trạng thái `referential_integrity_status` theo các bộ đếm vi phạm thực tế); CLI thoát mã lỗi 1 khi dữ liệu có lỗi; kiểm tra canonical roundtrip 100% ID.
  2. **F2 [P2]:** Tái cấu trúc kiểm thử tự động, loại bỏ đọc JSON tĩnh; bổ sung 5 negative tests với synthetic fixtures kiểm chứng việc bắt lỗi duplicate, orphan, conflict và rò rỉ ID; chủ động chạy live auditor trên dữ liệu thật ra thư mục tạm.
  3. **F3 [P2]:** Sửa 4 mã băm SHA-256 trong bảng 2.2 của Data Card khớp hoàn toàn với snapshot đóng băng và manifests.
  4. **F4 [P2]:** Đồng bộ toàn bộ số liệu min, max, mean, std, median, percentiles trong Section 4 của Data Card khớp với báo cáo máy đọc và tokenizer Protocol v1.
  5. **F5 [P2]:** Chính xác hóa giấy phép bản quyền: SciFact (CC BY 4.0 / ODC-By 1.0), SCIDOCS (CC BY 4.0 - yêu cầu attribution, không phải CC0), BEIR package (Apache-2.0).

## Bước tiếp theo khi được giao

1. **Về SG-011 (Split và leakage checks):**
   - Phụ thuộc SG-004 và SG-010 đều đã DONE; là task tiếp theo trong pipeline M2.
   - Triển khai `configs/split_policy.json`, `tests/unit/test_split_leakage.py`, `artifacts/reports/split_audit.json`.
2. **Về SG-008 & SG-012:**
   - Khi người dùng cho phép mở lại SG-008 (Kiểm chứng evaluator), triển khai `evaluator.py`, golden fixtures và đối chiếu trec_eval.
   - Sau khi SG-008 và SG-011 hoàn tất, SG-012 sẽ được mở khóa để chạy BM25 pilot thật trên SciFact và SCIDOCS.
