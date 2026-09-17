# Phân tích Age adjustment (SG-024)

- Công thức duy nhất được phép: `F_age(d) = F(d) × exp(-lambda × max(0, year(u) - year(d)))`, `lambda ∈ {0, 0.01, 0.03, 0.05, 0.1}` (Protocol §5.4).
- Năm tham chiếu = năm của source `year(u)`, không phải năm chạy máy. Tài liệu mới hơn source giữ weight 1.0. Thiếu năm → loại khỏi tuyến B, không điền median.
- Đây là post-fusion freshness adaptation, KHÔNG phải CiteRank/time-balanced centrality. Mọi con số dưới đây là MÔ TẢ, không chứng minh fairness/debiasing/relevance.

## 1. Đo mô tả trên snapshot thật (không phải relevance)

- Đầu vào: 300 query sources (dev 2024: 100, test 2025: 200) × toàn bộ works có năm hợp lệ ≤ year(u) (18.226/18.251 works; 22 thiếu năm + 3 ngoài biên bị loại đúng policy) = **5.133.600 cặp** query–candidate.
- `fused` đặt uniform = 1.0 để TÁCH RIÊNG hiệu ứng trọng số tuổi (không lẫn signal retrieval). Vì vậy bảng này đo hành vi của trọng số, KHÔNG dự báo rerank thật.
- Provenance: `artifacts/reports/age_exposure.json` (script `scripts/age_exposure_audit.py`, input hashes kèm trong file). Trung bình macro trên query của top-10 từng query.

| lambda | share top-10 0–2y | 3–5y | 6–10y | >10y |
|---|---|---|---|---|
| 0.0 (đối chứng) | 0.1000 (artefact ties — xem chú thích) | 0.2000 | 0.0000 | 0.7000 |
| 0.01 | 1.0000 | 0 | 0 | 0 |
| 0.03 | 1.0000 | 0 | 0 | 0 |
| 0.05 | 1.0000 | 0 | 0 | 0 |
| 0.1 | 1.0000 | 0 | 0 | 0 |

- Chú thích trung thực: với fused uniform, mọi lambda > 0 đẩy top-10 về 100% bài 0–2 tuổi (trọng số phân biệt tuyệt đối các ties); hàng lambda = 0 là thứ tự ties tùy ý (stable order), không có ý nghĩa. Với fused thật (điểm retrieval phân tán), hiệu ứng sẽ mềm hơn — mức lambda phải chọn trên dev relevance ở SG-026 sau khi gamma đã khóa, giữ đối chứng lambda = 0.
- Kết luận duy nhất được phép: age variant có TÁC ĐỘNG MẠNH tới exposure theo tuổi ngay từ lambda nhỏ nhất; đánh đổi relevance–exposure (RQ3) chỉ đo được khi có pipeline frozen (SG-026).

## 2. Tài liệu đánh đổi với paper nền tảng

- Paper nền tảng (cũ, nhiều trích dẫn) bị giảm trọng số theo hàm mũ của khoảng cách tuổi; paper mới được giữ nguyên. Đây là giả thuyết nghiên cứu (ADR-005), chưa phải novelty/SOTA, chưa đảm bảo tăng điểm.
- Mọi prior/degree/PageRank dùng trong fusion đều tính từ graph hợp lệ (masked + cutoff); `cited_by_count` hiện tại không bao giờ làm feature.
