# Bàn giao ScholarGraph

NEXT_TASK: SG-011

## Trạng thái — 2026-09-16T00:05:00+07:00

- SG-010 **DONE**: Audit chất lượng dữ liệu BEIR (SciFact và SCIDOCS) hoàn tất toàn diện; báo cáo [beir_data_audit.json](../artifacts/reports/beir_data_audit.json), [DATA_CARD.md](../docs/DATA_CARD.md) và bộ kiểm thử [test_data_integrity.py](../tests/unit/test_data_integrity.py) đã nghiệm thu; fresh-context review [SG-010-REVIEW-20260915.md](reviews/SG-010-REVIEW-20260915.md) đạt **PASS** (0 findings).
- SG-000 đến SG-007, SG-009, SG-010, SG-013 đều đã **DONE**.
- Task **SG-008** giữ nguyên trạng thái **TODO** (hoãn thực hiện theo chỉ đạo trực tiếp của người dùng: *"Khoan không động vào task SG-008 nhé"*).
- Task **SG-012** (BM25 pilot thật) phụ thuộc `[SG-008, SG-010, SG-011]`. Vì SG-008 bị hoãn và SG-011 chưa làm, SG-012 chưa thể chạy pilot metric thật. Tuy nhiên thiết kế kiến trúc BM25 và chiến lược pilot đã được phân tích hoàn chỉnh.
- Task **SG-011** (Split và leakage checks) phụ thuộc `[SG-004, SG-010]` $\to$ Hiện đã **đủ 100% điều kiện tiên quyết để triển khai ngay**.
- Phiên coordinator/worker SESSION-20260915-020 hoàn tất; không còn active assignment.
- Toàn bộ suite test dự án: **88 passed in 26.42s** (10/10 test cases integrity mới PASS).

## Bằng chứng và Phát hiện chính của SG-010

- **Mã nguồn và Báo cáo:**
  - [src/scholargraph/ingest/beir_audit.py](../src/scholargraph/ingest/beir_audit.py)
  - [artifacts/reports/beir_data_audit.json](../artifacts/reports/beir_data_audit.json)
  - [docs/DATA_CARD.md](../docs/DATA_CARD.md)
  - [tests/unit/test_data_integrity.py](../tests/unit/test_data_integrity.py)
- **Toàn vẹn tham chiếu & ID:** 100% ID duy nhất, không orphan queries/corpus IDs trong qrels, không duplicate qrels, ánh xạ canonical round-trip đạt 100%.
- **Dị thường SCIDOCS (344 documents thiếu abstract):**
  - Trong 25.657 documents của SCIDOCS, đúng 344 documents có abstract rỗng (chỉ có tiêu đề).
  - Cả 344 documents đều được đánh giá trong tập qrels test; trong đó có đúng **115 documents mang nhãn liên quan dương tính (`score = 1`)**.
  - Tuân thủ Giao thức v1: giữ nguyên vẹn 100% trong benchmark, không lọc bỏ ngầm, lập chỉ mục bằng tiêu đề.
- **Dị thường SciFact (Trùng lặp truy vấn Train–Test upstream):**
  - Không gian ID phân tách hoàn toàn (0 overlapping IDs).
  - Có 2 câu truy vấn trong tập test trùng 100% văn bản với 2 câu trong tập train upstream của BEIR:
    - Test `1292` & Train `1291` (*"There is no association between HNF4A mutations and diabetes risks."*) $\to$ doc `56893404`.
    - Test `870` & Train `871` (*"Obesity decreases life quality."*) $\to$ doc `195689316`.
  - Đã ghi nhận minh bạch trong Data Card và report để phòng ngừa rủi ro rò rỉ khi phân tích lỗi per-query.

## Bước tiếp theo khi được giao

1. **Về SG-011 (Split và leakage checks):**
   - Phụ thuộc SG-004 và SG-010 đều đã DONE; là task tiếp theo trong pipeline M2.
   - Triển khai `configs/split_policy.json`, `tests/unit/test_split_leakage.py`, `artifacts/reports/split_audit.json`.
2. **Về SG-008 & SG-012:**
   - Khi người dùng cho phép mở lại SG-008 (Kiểm chứng evaluator), triển khai `evaluator.py`, golden fixtures và đối chiếu trec_eval.
   - Sau khi SG-008 và SG-011 hoàn tất, SG-012 sẽ được mở khóa để chạy BM25 pilot thật trên SciFact và SCIDOCS.
